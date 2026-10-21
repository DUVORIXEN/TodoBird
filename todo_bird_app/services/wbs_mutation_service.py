"""
TODO BIRD — WBS Mutation Authority
Phase 1E

Single transactional authority for persistent WBS structure changes.

Canonical storage model:
- Task entities are project-level WBS roots.
- Subtask entities belong to one owning main task.
- A top-level subtask has parent_subtask_id IS NULL.
- A nested subtask has parent_subtask_id=<subtask id>.
- position is sibling-local ordering authority.

This service never converts task <-> subtask and never writes derived
schedule/progress/Actual rollup fields.
"""

from dataclasses import dataclass
from typing import Any, Optional, List, Tuple

from todo_bird_app.services.wbs_service import (
    EntityRef,
    WBSService,
)


@dataclass(frozen=True)
class WBSMutationResult:
    success: bool
    reason_code: str = ""
    message: str = ""
    key: Optional[EntityRef] = None
    parent_key: Optional[EntityRef] = None
    old_position: Optional[int] = None
    new_position: Optional[int] = None


class WBSMutationService:
    """
    Canonical persistent WBS hierarchy mutation authority.

    The Qt model remains a read-only snapshot adapter.
    UI/controllers request mutation here, then rebuild WBS/rollups/Gantt.
    """

    OK = "OK"
    ERR_NODE_NOT_FOUND = "NODE_NOT_FOUND"
    ERR_PARENT_NOT_FOUND = "PARENT_NOT_FOUND"
    ERR_SELF_PARENT = "SELF_PARENT"
    ERR_CYCLE = "CYCLE_DETECTED"
    ERR_CROSS_TASK = "CROSS_TASK_MOVE"
    ERR_CROSS_PROJECT = "CROSS_PROJECT_MOVE"
    ERR_TASK_PARENT_FORBIDDEN = "TASK_PARENT_FORBIDDEN"
    ERR_ALREADY_BOUNDARY = "ALREADY_AT_BOUNDARY"
    ERR_INVALID_DIRECTION = "INVALID_DIRECTION"
    ERR_INVALID_ENTITY = "INVALID_ENTITY"
    ERR_INVALID_DROP = "INVALID_DROP"

    # ------------------------------------------------------------
    # Basic typed lookup helpers
    # ------------------------------------------------------------

    @staticmethod
    def _task_row(cur, task_id: int):
        return cur.execute(
            """
            SELECT id, project_id, position
            FROM tasks
            WHERE id = ?
            """,
            (int(task_id),),
        ).fetchone()

    @staticmethod
    def _subtask_row(cur, subtask_id: int):
        return cur.execute(
            """
            SELECT id, task_id, parent_subtask_id, position
            FROM subtasks
            WHERE id = ?
            """,
            (int(subtask_id),),
        ).fetchone()

    @classmethod
    def _project_id_for_key(cls, cur, key: EntityRef):
        if key.entity_type == "task":
            row = cls._task_row(cur, key.entity_id)
            return row["project_id"] if row else None

        row = cls._subtask_row(cur, key.entity_id)
        if not row:
            return None

        owner = cls._task_row(cur, row["task_id"])
        return owner["project_id"] if owner else None

    @classmethod
    def _owner_task_id(cls, cur, key: EntityRef) -> Optional[int]:
        if key.entity_type == "task":
            row = cls._task_row(cur, key.entity_id)
            return int(row["id"]) if row else None

        row = cls._subtask_row(cur, key.entity_id)
        return int(row["task_id"]) if row else None

    # ------------------------------------------------------------
    # Sibling authority
    # ------------------------------------------------------------

    @classmethod
    def _siblings(
        cls,
        cur,
        key: EntityRef,
    ) -> Tuple[List[int], Optional[int], Optional[int]]:
        """
        Returns:
            sibling IDs in canonical DB position order,
            owner task id,
            parent_subtask_id

        For task roots, owner_task_id/parent_subtask_id are None.
        """

        if key.entity_type == "task":
            row = cls._task_row(cur, key.entity_id)
            if not row:
                return [], None, None

            rows = cur.execute(
                """
                SELECT id
                FROM tasks
                WHERE project_id IS ?
                ORDER BY position ASC, created_at ASC, id ASC
                """,
                (row["project_id"],),
            ).fetchall()

            return [int(r["id"]) for r in rows], None, None

        row = cls._subtask_row(cur, key.entity_id)
        if not row:
            return [], None, None

        owner_task_id = int(row["task_id"])
        parent_id = row["parent_subtask_id"]

        if parent_id is None:
            rows = cur.execute(
                """
                SELECT id
                FROM subtasks
                WHERE task_id = ?
                  AND parent_subtask_id IS NULL
                ORDER BY position ASC, created_at ASC, id ASC
                """,
                (owner_task_id,),
            ).fetchall()
        else:
            rows = cur.execute(
                """
                SELECT id
                FROM subtasks
                WHERE task_id = ?
                  AND parent_subtask_id = ?
                ORDER BY position ASC, created_at ASC, id ASC
                """,
                (owner_task_id, int(parent_id)),
            ).fetchall()

        return (
            [int(r["id"]) for r in rows],
            owner_task_id,
            int(parent_id) if parent_id is not None else None,
        )

    @staticmethod
    def _write_positions(
        cur,
        entity_type: str,
        ordered_ids: List[int],
    ) -> None:
        """
        Normalize sibling positions densely to 0..N-1.

        Dense positions prevent drift/duplicates after repeated editing.
        """

        table = "tasks" if entity_type == "task" else "subtasks"

        for pos, entity_id in enumerate(ordered_ids):
            cur.execute(
                f"UPDATE {table} SET position = ? WHERE id = ?",
                (int(pos), int(entity_id)),
            )

    # ------------------------------------------------------------
    # Reorder: Move Up / Move Down
    # ------------------------------------------------------------

    @classmethod
    def move_sibling(
        cls,
        db_manager: Any,
        key: EntityRef,
        direction: int,
    ) -> WBSMutationResult:
        """
        Move one entity one slot among its current siblings.

        direction:
            -1 => up
            +1 => down

        Does not change parent/project/task ownership.
        """

        if direction not in (-1, 1):
            return WBSMutationResult(
                False,
                cls.ERR_INVALID_DIRECTION,
                "Direction must be -1 or +1.",
                key=key,
            )

        with db_manager.get_connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.cursor()

                siblings, _, _ = cls._siblings(cur, key)

                if key.entity_id not in siblings:
                    conn.rollback()
                    return WBSMutationResult(
                        False,
                        cls.ERR_NODE_NOT_FOUND,
                        f"{key} was not found in its sibling scope.",
                        key=key,
                    )

                old_idx = siblings.index(key.entity_id)
                new_idx = old_idx + direction

                if new_idx < 0 or new_idx >= len(siblings):
                    conn.rollback()
                    return WBSMutationResult(
                        False,
                        cls.ERR_ALREADY_BOUNDARY,
                        "Item is already at that sibling boundary.",
                        key=key,
                        old_position=old_idx,
                        new_position=old_idx,
                    )

                siblings[old_idx], siblings[new_idx] = (
                    siblings[new_idx],
                    siblings[old_idx],
                )

                cls._write_positions(
                    cur,
                    key.entity_type,
                    siblings,
                )

                conn.commit()

                return WBSMutationResult(
                    True,
                    cls.OK,
                    "Sibling order updated.",
                    key=key,
                    old_position=old_idx,
                    new_position=new_idx,
                )

            except Exception:
                conn.rollback()
                raise

    @classmethod
    def move_up(
        cls,
        db_manager: Any,
        key: EntityRef,
    ) -> WBSMutationResult:
        return cls.move_sibling(
            db_manager,
            key,
            -1,
        )

    @classmethod
    def move_down(
        cls,
        db_manager: Any,
        key: EntityRef,
    ) -> WBSMutationResult:
        return cls.move_sibling(
            db_manager,
            key,
            +1,
        )

    # ------------------------------------------------------------
    # Canonical Add Child authority — Phase 1E.5
    # ------------------------------------------------------------

    @classmethod
    def create_child(
        cls,
        db_manager: Any,
        parent_key: EntityRef,
        title: str,
    ) -> WBSMutationResult:
        """
        Atomically create one WBS child.

        Storage invariant:
        - Task parent -> direct Subtask
        - Subtask parent -> nested Subtask
        - Task entities themselves always remain WBS roots

        The append position is resolved and written inside the same
        BEGIN IMMEDIATE transaction so concurrent/repeated creation
        cannot produce an accidental duplicate sibling position.
        """

        clean_title = str(title or "").strip()

        if not clean_title:
            return WBSMutationResult(
                False,
                cls.ERR_INVALID_ENTITY,
                "Child task name cannot be empty.",
                parent_key=parent_key,
            )

        if parent_key.entity_type not in (
            "task",
            "subtask",
        ):
            return WBSMutationResult(
                False,
                cls.ERR_INVALID_ENTITY,
                "Unsupported WBS parent entity.",
                parent_key=parent_key,
            )

        with db_manager.get_connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.cursor()

                # ------------------------------------------------
                # Resolve canonical owner + parent.
                # ------------------------------------------------
                if parent_key.entity_type == "task":
                    parent_task = cls._task_row(
                        cur,
                        parent_key.entity_id,
                    )

                    if not parent_task:
                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            cls.ERR_PARENT_NOT_FOUND,
                            f"Parent not found: {parent_key}",
                            parent_key=parent_key,
                        )

                    owner_task_id = int(
                        parent_task["id"]
                    )
                    parent_subtask_id = None

                else:
                    parent_subtask = cls._subtask_row(
                        cur,
                        parent_key.entity_id,
                    )

                    if not parent_subtask:
                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            cls.ERR_PARENT_NOT_FOUND,
                            f"Parent not found: {parent_key}",
                            parent_key=parent_key,
                        )

                    owner_task_id = int(
                        parent_subtask["task_id"]
                    )
                    parent_subtask_id = int(
                        parent_subtask["id"]
                    )

                    owner = cls._task_row(
                        cur,
                        owner_task_id,
                    )

                    if not owner:
                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            cls.ERR_PARENT_NOT_FOUND,
                            "Owning main task no longer exists.",
                            parent_key=parent_key,
                        )

                # ------------------------------------------------
                # Deterministic append position INSIDE transaction.
                # ------------------------------------------------
                if parent_subtask_id is None:
                    row = cur.execute(
                        """
                        SELECT COALESCE(MAX(position), -1) + 1
                            AS next_position
                        FROM subtasks
                        WHERE task_id = ?
                          AND parent_subtask_id IS NULL
                        """,
                        (
                            owner_task_id,
                        ),
                    ).fetchone()
                else:
                    row = cur.execute(
                        """
                        SELECT COALESCE(MAX(position), -1) + 1
                            AS next_position
                        FROM subtasks
                        WHERE task_id = ?
                          AND parent_subtask_id = ?
                        """,
                        (
                            owner_task_id,
                            parent_subtask_id,
                        ),
                    ).fetchone()

                position = int(
                    row["next_position"]
                    if row is not None
                    else 0
                )

                # ------------------------------------------------
                # Use the canonical subtasks schema directly inside
                # this transaction.
                #
                # Defaults deliberately mirror DatabaseManager's
                # insert_subtask defaults. We do not manufacture
                # schedule/actual data merely because a hierarchy
                # child was created.
                # ------------------------------------------------
                cur.execute(
                    """
                    INSERT INTO subtasks (
                        task_id,
                        parent_subtask_id,
                        title,
                        description,
                        is_completed,
                        position,
                        planned_date,
                        due_date,
                        planned_start_time,
                        planned_end_time,
                        estimated_duration,
                        priority,
                        progress,
                        show_in_gantt,
                        dependencies,
                        icon,
                        image_path,
                        is_pinned,
                        pin_color,
                        pin_position,
                        actual_start_date,
                        actual_end_date,
                        actual_start_time,
                        actual_end_time,
                        actual_duration,
                        planned_effort_minutes,
                        daily_dedication_minutes,
                        allocation_mode
                    )
                    VALUES (
                        ?, ?, ?, '',
                        0, ?,
                        NULL, NULL, NULL, NULL,
                        0, 'Medium', 0, 0,
                        '[]', '', '',
                        0, '#E95420', 0,
                        NULL, NULL, NULL, NULL,
                        0, 0, 0, 'fixed_daily'
                    )
                    """,
                    (
                        owner_task_id,
                        parent_subtask_id,
                        clean_title,
                        position,
                    ),
                )

                new_id = int(
                    cur.lastrowid
                )

                conn.commit()

                return WBSMutationResult(
                    True,
                    cls.OK,
                    "Child task created.",
                    key=EntityRef.subtask(
                        new_id
                    ),
                    parent_key=parent_key,
                    old_position=None,
                    new_position=position,
                )

            except Exception:
                conn.rollback()
                raise

    # ------------------------------------------------------------
    # Child append-position authority
    # ------------------------------------------------------------

    @classmethod
    def next_child_position(
        cls,
        db_manager: Any,
        parent_key: EntityRef,
    ) -> int:
        """
        Return deterministic append position for a new child.

        Task parent:
            child is top-level subtask.

        Subtask parent:
            child is nested subtask.
        """

        with db_manager.get_connection() as conn:
            cur = conn.cursor()

            if parent_key.entity_type == "task":
                task = cls._task_row(
                    cur,
                    parent_key.entity_id,
                )
                if not task:
                    raise ValueError(
                        f"Parent not found: {parent_key}"
                    )

                row = cur.execute(
                    """
                    SELECT COALESCE(MAX(position), -1) + 1 AS next_pos
                    FROM subtasks
                    WHERE task_id = ?
                      AND parent_subtask_id IS NULL
                    """,
                    (int(parent_key.entity_id),),
                ).fetchone()

                return int(row["next_pos"])

            parent = cls._subtask_row(
                cur,
                parent_key.entity_id,
            )
            if not parent:
                raise ValueError(
                    f"Parent not found: {parent_key}"
                )

            row = cur.execute(
                """
                SELECT COALESCE(MAX(position), -1) + 1 AS next_pos
                FROM subtasks
                WHERE task_id = ?
                  AND parent_subtask_id = ?
                """,
                (
                    int(parent["task_id"]),
                    int(parent_key.entity_id),
                ),
            ).fetchone()

            return int(row["next_pos"])

    # ------------------------------------------------------------
    # Reparent validation foundation for future indent/drag-drop
    # ------------------------------------------------------------

    @classmethod
    def validate_reparent(
        cls,
        db_manager: Any,
        key: EntityRef,
        new_parent_key: EntityRef,
    ) -> WBSMutationResult:
        """
        Validate a future hierarchy move without mutating anything.

        Important storage rule:
        - task entities cannot acquire a parent.
        - subtask may parent only beneath its existing owning task.
        """

        if key.entity_type == "task":
            return WBSMutationResult(
                False,
                cls.ERR_TASK_PARENT_FORBIDDEN,
                "Main tasks are WBS roots and cannot be indented.",
                key=key,
                parent_key=new_parent_key,
            )

        if key == new_parent_key:
            return WBSMutationResult(
                False,
                cls.ERR_SELF_PARENT,
                "An item cannot become its own parent.",
                key=key,
                parent_key=new_parent_key,
            )

        with db_manager.get_connection() as conn:
            cur = conn.cursor()

            moving = cls._subtask_row(
                cur,
                key.entity_id,
            )
            if not moving:
                return WBSMutationResult(
                    False,
                    cls.ERR_NODE_NOT_FOUND,
                    f"Node not found: {key}",
                    key=key,
                    parent_key=new_parent_key,
                )

            owner_task_id = int(moving["task_id"])

            if new_parent_key.entity_type == "task":
                parent_task = cls._task_row(
                    cur,
                    new_parent_key.entity_id,
                )

                if not parent_task:
                    return WBSMutationResult(
                        False,
                        cls.ERR_PARENT_NOT_FOUND,
                        f"Parent not found: {new_parent_key}",
                        key=key,
                        parent_key=new_parent_key,
                    )

                if int(parent_task["id"]) != owner_task_id:
                    return WBSMutationResult(
                        False,
                        cls.ERR_CROSS_TASK,
                        "A subtask cannot move to a different main task implicitly.",
                        key=key,
                        parent_key=new_parent_key,
                    )

            elif new_parent_key.entity_type == "subtask":
                parent = cls._subtask_row(
                    cur,
                    new_parent_key.entity_id,
                )

                if not parent:
                    return WBSMutationResult(
                        False,
                        cls.ERR_PARENT_NOT_FOUND,
                        f"Parent not found: {new_parent_key}",
                        key=key,
                        parent_key=new_parent_key,
                    )

                if int(parent["task_id"]) != owner_task_id:
                    return WBSMutationResult(
                        False,
                        cls.ERR_CROSS_TASK,
                        "A subtask subtree cannot cross its owning main task.",
                        key=key,
                        parent_key=new_parent_key,
                    )

                # Cycle prevention:
                # Walk from proposed parent upward. If moving key appears,
                # proposed parent is inside moving subtree.
                current = int(parent["id"])

                while current is not None:
                    if current == int(key.entity_id):
                        return WBSMutationResult(
                            False,
                            cls.ERR_CYCLE,
                            "Cannot move an item beneath its own descendant.",
                            key=key,
                            parent_key=new_parent_key,
                        )

                    row = cls._subtask_row(
                        cur,
                        current,
                    )
                    if not row:
                        break

                    parent_id = row["parent_subtask_id"]
                    current = (
                        int(parent_id)
                        if parent_id is not None
                        else None
                    )

            else:
                return WBSMutationResult(
                    False,
                    cls.ERR_INVALID_ENTITY,
                    "Unsupported parent entity type.",
                    key=key,
                    parent_key=new_parent_key,
                )

            moving_project = cls._project_id_for_key(
                cur,
                key,
            )
            parent_project = cls._project_id_for_key(
                cur,
                new_parent_key,
            )

            if moving_project != parent_project:
                return WBSMutationResult(
                    False,
                    cls.ERR_CROSS_PROJECT,
                    "WBS hierarchy moves cannot cross projects.",
                    key=key,
                    parent_key=new_parent_key,
                )

        return WBSMutationResult(
            True,
            cls.OK,
            "Reparent request is structurally valid.",
            key=key,
            parent_key=new_parent_key,
        )

    # ------------------------------------------------------------
    # Professional WBS Indent / Outdent
    # ------------------------------------------------------------

    @classmethod
    def _ordered_subtask_scope(
        cls,
        cur,
        task_id: int,
        parent_subtask_id: Optional[int],
        exclude_id: Optional[int] = None,
    ) -> List[int]:
        """
        Canonical ordered IDs for one subtask sibling scope.
        """

        params = [int(task_id)]

        if parent_subtask_id is None:
            sql = """
                SELECT id
                FROM subtasks
                WHERE task_id = ?
                  AND parent_subtask_id IS NULL
            """
        else:
            sql = """
                SELECT id
                FROM subtasks
                WHERE task_id = ?
                  AND parent_subtask_id = ?
            """
            params.append(int(parent_subtask_id))

        if exclude_id is not None:
            sql += " AND id <> ?"
            params.append(int(exclude_id))

        sql += " ORDER BY position ASC, created_at ASC, id ASC"

        rows = cur.execute(
            sql,
            tuple(params),
        ).fetchall()

        return [int(r["id"]) for r in rows]

    @classmethod
    def _move_subtask_to_scope(
        cls,
        cur,
        subtask_id: int,
        task_id: int,
        old_parent_id: Optional[int],
        new_parent_id: Optional[int],
        target_index: int,
    ) -> int:
        """
        Internal transaction-local structural move.

        Removes the item from its old sibling scope, normalizes that scope,
        inserts it into the target scope at target_index, and normalizes the
        target scope.

        Caller owns transaction commit/rollback.
        """

        subtask_id = int(subtask_id)
        task_id = int(task_id)

        old_ids = cls._ordered_subtask_scope(
            cur,
            task_id,
            old_parent_id,
            exclude_id=subtask_id,
        )

        cls._write_positions(
            cur,
            "subtask",
            old_ids,
        )

        new_ids = cls._ordered_subtask_scope(
            cur,
            task_id,
            new_parent_id,
            exclude_id=subtask_id,
        )

        target_index = max(
            0,
            min(int(target_index), len(new_ids)),
        )

        new_ids.insert(
            target_index,
            subtask_id,
        )

        # Set parent first, then normalize final target scope.
        cur.execute(
            """
            UPDATE subtasks
            SET parent_subtask_id = ?
            WHERE id = ?
            """,
            (
                new_parent_id,
                subtask_id,
            ),
        )

        cls._write_positions(
            cur,
            "subtask",
            new_ids,
        )

        return target_index

    @classmethod
    def indent(
        cls,
        db_manager: Any,
        key: EntityRef,
    ) -> WBSMutationResult:
        """
        Indent a subtask beneath its immediately preceding sibling.

        Professional WBS rule:
            A
            B   <- selected

        becomes:

            A
                B

        B becomes the LAST CHILD of A.

        Main task roots cannot be indented because the canonical schema
        deliberately keeps task entities as project roots.
        """

        if key.entity_type == "task":
            return WBSMutationResult(
                False,
                cls.ERR_TASK_PARENT_FORBIDDEN,
                "Main tasks are WBS roots and cannot be indented.",
                key=key,
            )

        if key.entity_type != "subtask":
            return WBSMutationResult(
                False,
                cls.ERR_INVALID_ENTITY,
                "Only subtasks can be indented.",
                key=key,
            )

        with db_manager.get_connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.cursor()

                moving = cls._subtask_row(
                    cur,
                    key.entity_id,
                )

                if not moving:
                    conn.rollback()
                    return WBSMutationResult(
                        False,
                        cls.ERR_NODE_NOT_FOUND,
                        f"Node not found: {key}",
                        key=key,
                    )

                task_id = int(moving["task_id"])
                old_parent_id = moving["parent_subtask_id"]

                siblings = cls._ordered_subtask_scope(
                    cur,
                    task_id,
                    (
                        int(old_parent_id)
                        if old_parent_id is not None
                        else None
                    ),
                )

                try:
                    old_index = siblings.index(
                        int(key.entity_id)
                    )
                except ValueError:
                    conn.rollback()
                    return WBSMutationResult(
                        False,
                        cls.ERR_NODE_NOT_FOUND,
                        "Item was not found in its sibling scope.",
                        key=key,
                    )

                # First sibling has nothing before it to become its parent.
                if old_index <= 0:
                    conn.rollback()
                    return WBSMutationResult(
                        False,
                        cls.ERR_ALREADY_BOUNDARY,
                        "There is no previous sibling to indent under.",
                        key=key,
                        old_position=old_index,
                        new_position=old_index,
                    )

                new_parent_id = int(
                    siblings[old_index - 1]
                )

                # Defensive cycle validation.
                validation = cls.validate_reparent(
                    db_manager,
                    key,
                    EntityRef.subtask(new_parent_id),
                )

                if not validation.success:
                    conn.rollback()
                    return validation

                target_children = cls._ordered_subtask_scope(
                    cur,
                    task_id,
                    new_parent_id,
                    exclude_id=int(key.entity_id),
                )

                new_index = cls._move_subtask_to_scope(
                    cur,
                    int(key.entity_id),
                    task_id,
                    (
                        int(old_parent_id)
                        if old_parent_id is not None
                        else None
                    ),
                    new_parent_id,
                    len(target_children),
                )

                conn.commit()

                return WBSMutationResult(
                    True,
                    cls.OK,
                    "Item indented.",
                    key=key,
                    parent_key=EntityRef.subtask(new_parent_id),
                    old_position=old_index,
                    new_position=new_index,
                )

            except Exception:
                conn.rollback()
                raise

    @classmethod
    def outdent(
        cls,
        db_manager: Any,
        key: EntityRef,
    ) -> WBSMutationResult:
        """
        Move a subtask one hierarchy level upward.

        Professional WBS placement rule:
        the outdented item is inserted immediately AFTER its former parent.

        Example:

            A
                B   <- selected
                C
            D

        becomes:

            A
            B
            D

        B's own descendants remain attached to B.
        """

        if key.entity_type == "task":
            return WBSMutationResult(
                False,
                cls.ERR_ALREADY_BOUNDARY,
                "Main tasks are already at the WBS root level.",
                key=key,
            )

        if key.entity_type != "subtask":
            return WBSMutationResult(
                False,
                cls.ERR_INVALID_ENTITY,
                "Only subtasks can be outdented.",
                key=key,
            )

        with db_manager.get_connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.cursor()

                moving = cls._subtask_row(
                    cur,
                    key.entity_id,
                )

                if not moving:
                    conn.rollback()
                    return WBSMutationResult(
                        False,
                        cls.ERR_NODE_NOT_FOUND,
                        f"Node not found: {key}",
                        key=key,
                    )

                task_id = int(moving["task_id"])
                parent_id = moving["parent_subtask_id"]

                # Direct child of main task is already at the highest
                # representable subtask level.
                if parent_id is None:
                    conn.rollback()
                    return WBSMutationResult(
                        False,
                        cls.ERR_ALREADY_BOUNDARY,
                        "This item is already directly beneath its main task.",
                        key=key,
                    )

                parent_id = int(parent_id)

                parent = cls._subtask_row(
                    cur,
                    parent_id,
                )

                if not parent:
                    conn.rollback()
                    return WBSMutationResult(
                        False,
                        cls.ERR_PARENT_NOT_FOUND,
                        "Current WBS parent no longer exists.",
                        key=key,
                    )

                if int(parent["task_id"]) != task_id:
                    conn.rollback()
                    return WBSMutationResult(
                        False,
                        cls.ERR_CROSS_TASK,
                        "Parent belongs to a different main task.",
                        key=key,
                    )

                grandparent_id = parent[
                    "parent_subtask_id"
                ]

                grandparent_id = (
                    int(grandparent_id)
                    if grandparent_id is not None
                    else None
                )

                # Find former parent's index in the destination scope.
                destination = cls._ordered_subtask_scope(
                    cur,
                    task_id,
                    grandparent_id,
                    exclude_id=int(key.entity_id),
                )

                try:
                    parent_index = destination.index(
                        parent_id
                    )
                except ValueError:
                    conn.rollback()
                    return WBSMutationResult(
                        False,
                        cls.ERR_PARENT_NOT_FOUND,
                        "Former parent was not found in its sibling scope.",
                        key=key,
                    )

                old_siblings = cls._ordered_subtask_scope(
                    cur,
                    task_id,
                    parent_id,
                )

                try:
                    old_index = old_siblings.index(
                        int(key.entity_id)
                    )
                except ValueError:
                    old_index = int(
                        moving["position"] or 0
                    )

                # Insert immediately after former parent.
                target_index = parent_index + 1

                new_index = cls._move_subtask_to_scope(
                    cur,
                    int(key.entity_id),
                    task_id,
                    parent_id,
                    grandparent_id,
                    target_index,
                )

                conn.commit()

                parent_key = (
                    EntityRef.subtask(grandparent_id)
                    if grandparent_id is not None
                    else EntityRef.task(task_id)
                )

                return WBSMutationResult(
                    True,
                    cls.OK,
                    "Item outdented.",
                    key=key,
                    parent_key=parent_key,
                    old_position=old_index,
                    new_position=new_index,
                )

            except Exception:
                conn.rollback()
                raise

    # ------------------------------------------------------------
    # Safe drag/drop authority — Phase 1E.4
    # ------------------------------------------------------------

    @classmethod
    def drag_drop_move(
        cls,
        db_manager: Any,
        key: EntityRef,
        target_key: EntityRef,
        zone: str,
    ) -> WBSMutationResult:
        """
        Apply one typed WBS drag/drop intent atomically.

        zone:
            "before"
            "into"
            "after"

        This method performs validation and mutation inside the SAME
        BEGIN IMMEDIATE transaction. It does not rely on Qt model moves.
        """

        zone = str(zone or "").strip().lower()

        if zone not in ("before", "into", "after"):
            return WBSMutationResult(
                False,
                cls.ERR_INVALID_DROP,
                "Unsupported WBS drop position.",
                key=key,
                parent_key=target_key,
            )

        if key == target_key:
            return WBSMutationResult(
                False,
                cls.ERR_SELF_PARENT,
                "An item cannot be dropped onto itself.",
                key=key,
                parent_key=target_key,
            )

        with db_manager.get_connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.cursor()

                # ----------------------------------------------------
                # MAIN TASK ROOT REORDER
                # ----------------------------------------------------
                if key.entity_type == "task":
                    moving = cls._task_row(
                        cur,
                        key.entity_id,
                    )

                    if not moving:
                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            cls.ERR_NODE_NOT_FOUND,
                            f"Node not found: {key}",
                            key=key,
                        )

                    if (
                        target_key.entity_type != "task"
                        or zone == "into"
                    ):
                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            cls.ERR_TASK_PARENT_FORBIDDEN,
                            "Main tasks remain WBS roots. Drop them before or after another root task.",
                            key=key,
                            parent_key=target_key,
                        )

                    target = cls._task_row(
                        cur,
                        target_key.entity_id,
                    )

                    if not target:
                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            cls.ERR_PARENT_NOT_FOUND,
                            f"Drop target not found: {target_key}",
                            key=key,
                            parent_key=target_key,
                        )

                    if moving["project_id"] != target["project_id"]:
                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            cls.ERR_CROSS_PROJECT,
                            "Root tasks cannot be dragged between projects.",
                            key=key,
                            parent_key=target_key,
                        )

                    rows = cur.execute(
                        """
                        SELECT id
                        FROM tasks
                        WHERE project_id IS ?
                        ORDER BY position ASC, created_at ASC, id ASC
                        """,
                        (moving["project_id"],),
                    ).fetchall()

                    original = [
                        int(r["id"])
                        for r in rows
                    ]

                    moving_id = int(key.entity_id)
                    target_id = int(target_key.entity_id)

                    if (
                        moving_id not in original
                        or target_id not in original
                    ):
                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            cls.ERR_NODE_NOT_FOUND,
                            "Dragged task or target disappeared from its project.",
                            key=key,
                            parent_key=target_key,
                        )

                    old_position = original.index(
                        moving_id
                    )

                    reordered = [
                        entity_id
                        for entity_id in original
                        if entity_id != moving_id
                    ]

                    target_position = reordered.index(
                        target_id
                    )

                    insert_at = (
                        target_position
                        if zone == "before"
                        else target_position + 1
                    )

                    reordered.insert(
                        insert_at,
                        moving_id,
                    )

                    if reordered == original:
                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            cls.ERR_ALREADY_BOUNDARY,
                            "Task is already at that position.",
                            key=key,
                            old_position=old_position,
                            new_position=old_position,
                        )

                    cls._write_positions(
                        cur,
                        "task",
                        reordered,
                    )

                    conn.commit()

                    return WBSMutationResult(
                        True,
                        cls.OK,
                        "Root task reordered.",
                        key=key,
                        parent_key=None,
                        old_position=old_position,
                        new_position=reordered.index(
                            moving_id
                        ),
                    )

                # ----------------------------------------------------
                # SUBTASK STRUCTURAL MOVE
                # ----------------------------------------------------
                if key.entity_type != "subtask":
                    conn.rollback()
                    return WBSMutationResult(
                        False,
                        cls.ERR_INVALID_ENTITY,
                        "Unsupported dragged WBS entity.",
                        key=key,
                        parent_key=target_key,
                    )

                moving = cls._subtask_row(
                    cur,
                    key.entity_id,
                )

                if not moving:
                    conn.rollback()
                    return WBSMutationResult(
                        False,
                        cls.ERR_NODE_NOT_FOUND,
                        f"Node not found: {key}",
                        key=key,
                        parent_key=target_key,
                    )

                owner_task_id = int(
                    moving["task_id"]
                )

                old_parent_id = (
                    int(moving["parent_subtask_id"])
                    if moving["parent_subtask_id"] is not None
                    else None
                )

                old_scope = cls._ordered_subtask_scope(
                    cur,
                    owner_task_id,
                    old_parent_id,
                )

                try:
                    old_position = old_scope.index(
                        int(key.entity_id)
                    )
                except ValueError:
                    conn.rollback()
                    return WBSMutationResult(
                        False,
                        cls.ERR_NODE_NOT_FOUND,
                        "Dragged item was not found in its current sibling scope.",
                        key=key,
                        parent_key=target_key,
                    )

                # ------------------------------------------------
                # Resolve desired parent + target insertion index.
                # ------------------------------------------------

                if target_key.entity_type == "task":
                    target_task = cls._task_row(
                        cur,
                        target_key.entity_id,
                    )

                    if not target_task:
                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            cls.ERR_PARENT_NOT_FOUND,
                            f"Drop target not found: {target_key}",
                            key=key,
                            parent_key=target_key,
                        )

                    # A subtask may only return to its OWN main task.
                    if int(target_task["id"]) != owner_task_id:
                        moving_project = cls._project_id_for_key(
                            cur,
                            key,
                        )
                        target_project = target_task[
                            "project_id"
                        ]

                        reason = (
                            cls.ERR_CROSS_PROJECT
                            if moving_project != target_project
                            else cls.ERR_CROSS_TASK
                        )

                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            reason,
                            "A subtask subtree cannot be moved to another main task.",
                            key=key,
                            parent_key=target_key,
                        )

                    # before/after a TASK would imply promoting a subtask
                    # into the main-task root scope, which is forbidden.
                    if zone != "into":
                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            cls.ERR_TASK_PARENT_FORBIDDEN,
                            "Drop a subtask into its main task, not beside the main task.",
                            key=key,
                            parent_key=target_key,
                        )

                    new_parent_id = None

                    destination = cls._ordered_subtask_scope(
                        cur,
                        owner_task_id,
                        None,
                        exclude_id=int(key.entity_id),
                    )

                    # INTO always appends as the last child.
                    insert_at = len(destination)

                elif target_key.entity_type == "subtask":
                    target = cls._subtask_row(
                        cur,
                        target_key.entity_id,
                    )

                    if not target:
                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            cls.ERR_PARENT_NOT_FOUND,
                            f"Drop target not found: {target_key}",
                            key=key,
                            parent_key=target_key,
                        )

                    if int(target["task_id"]) != owner_task_id:
                        moving_project = cls._project_id_for_key(
                            cur,
                            key,
                        )
                        target_project = cls._project_id_for_key(
                            cur,
                            target_key,
                        )

                        reason = (
                            cls.ERR_CROSS_PROJECT
                            if moving_project != target_project
                            else cls.ERR_CROSS_TASK
                        )

                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            reason,
                            "A subtask subtree cannot cross its owning main task.",
                            key=key,
                            parent_key=target_key,
                        )

                    if zone == "into":
                        new_parent_id = int(
                            target_key.entity_id
                        )

                        destination = cls._ordered_subtask_scope(
                            cur,
                            owner_task_id,
                            new_parent_id,
                            exclude_id=int(key.entity_id),
                        )

                        insert_at = len(destination)

                    else:
                        new_parent_id = (
                            int(target["parent_subtask_id"])
                            if target["parent_subtask_id"] is not None
                            else None
                        )

                        destination = cls._ordered_subtask_scope(
                            cur,
                            owner_task_id,
                            new_parent_id,
                            exclude_id=int(key.entity_id),
                        )

                        target_id = int(
                            target_key.entity_id
                        )

                        if target_id not in destination:
                            conn.rollback()
                            return WBSMutationResult(
                                False,
                                cls.ERR_PARENT_NOT_FOUND,
                                "Drop target disappeared from its sibling scope.",
                                key=key,
                                parent_key=target_key,
                            )

                        target_position = destination.index(
                            target_id
                        )

                        insert_at = (
                            target_position
                            if zone == "before"
                            else target_position + 1
                        )

                else:
                    conn.rollback()
                    return WBSMutationResult(
                        False,
                        cls.ERR_INVALID_ENTITY,
                        "Unsupported WBS drop target.",
                        key=key,
                        parent_key=target_key,
                    )

                # ------------------------------------------------
                # Cycle protection INSIDE the write transaction.
                #
                # Only the proposed parent matters. For before/after,
                # target may be a descendant while its parent defines
                # the true destination scope.
                # ------------------------------------------------
                current = new_parent_id

                while current is not None:
                    if current == int(key.entity_id):
                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            cls.ERR_CYCLE,
                            "Cannot move an item beneath its own descendant.",
                            key=key,
                            parent_key=target_key,
                        )

                    row = cls._subtask_row(
                        cur,
                        current,
                    )

                    if not row:
                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            cls.ERR_PARENT_NOT_FOUND,
                            "A destination ancestor no longer exists.",
                            key=key,
                            parent_key=target_key,
                        )

                    parent_id = row[
                        "parent_subtask_id"
                    ]

                    current = (
                        int(parent_id)
                        if parent_id is not None
                        else None
                    )

                # ------------------------------------------------
                # Build expected order first to detect harmless no-op.
                # ------------------------------------------------
                expected_destination = list(
                    destination
                )

                insert_at = max(
                    0,
                    min(
                        int(insert_at),
                        len(expected_destination),
                    ),
                )

                expected_destination.insert(
                    insert_at,
                    int(key.entity_id),
                )

                if old_parent_id == new_parent_id:
                    if expected_destination == old_scope:
                        conn.rollback()
                        return WBSMutationResult(
                            False,
                            cls.ERR_ALREADY_BOUNDARY,
                            "Item is already at that position.",
                            key=key,
                            parent_key=(
                                EntityRef.subtask(new_parent_id)
                                if new_parent_id is not None
                                else EntityRef.task(owner_task_id)
                            ),
                            old_position=old_position,
                            new_position=old_position,
                        )

                new_position = cls._move_subtask_to_scope(
                    cur,
                    int(key.entity_id),
                    owner_task_id,
                    old_parent_id,
                    new_parent_id,
                    insert_at,
                )

                conn.commit()

                canonical_parent_key = (
                    EntityRef.subtask(
                        new_parent_id
                    )
                    if new_parent_id is not None
                    else EntityRef.task(
                        owner_task_id
                    )
                )

                return WBSMutationResult(
                    True,
                    cls.OK,
                    "WBS hierarchy updated.",
                    key=key,
                    parent_key=canonical_parent_key,
                    old_position=old_position,
                    new_position=new_position,
                )

            except Exception:
                conn.rollback()
                raise

    # ------------------------------------------------------------
    # Actual subtask reparent primitive
    # Used later by indent/outdent/drag-drop.
    # ------------------------------------------------------------

    @classmethod
    def reparent_subtask(
        cls,
        db_manager: Any,
        key: EntityRef,
        new_parent_key: EntityRef,
    ) -> WBSMutationResult:

        validation = cls.validate_reparent(
            db_manager,
            key,
            new_parent_key,
        )

        if not validation.success:
            return validation

        with db_manager.get_connection() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                cur = conn.cursor()

                moving = cls._subtask_row(
                    cur,
                    key.entity_id,
                )

                if not moving:
                    conn.rollback()
                    return WBSMutationResult(
                        False,
                        cls.ERR_NODE_NOT_FOUND,
                        f"Node not found: {key}",
                        key=key,
                        parent_key=new_parent_key,
                    )

                owner_task_id = int(
                    moving["task_id"]
                )
                old_parent_id = moving[
                    "parent_subtask_id"
                ]

                # Normalize old sibling scope after removal.
                if old_parent_id is None:
                    old_rows = cur.execute(
                        """
                        SELECT id
                        FROM subtasks
                        WHERE task_id = ?
                          AND parent_subtask_id IS NULL
                          AND id <> ?
                        ORDER BY position ASC, created_at ASC, id ASC
                        """,
                        (
                            owner_task_id,
                            key.entity_id,
                        ),
                    ).fetchall()
                else:
                    old_rows = cur.execute(
                        """
                        SELECT id
                        FROM subtasks
                        WHERE task_id = ?
                          AND parent_subtask_id = ?
                          AND id <> ?
                        ORDER BY position ASC, created_at ASC, id ASC
                        """,
                        (
                            owner_task_id,
                            int(old_parent_id),
                            key.entity_id,
                        ),
                    ).fetchall()

                cls._write_positions(
                    cur,
                    "subtask",
                    [int(r["id"]) for r in old_rows],
                )

                if new_parent_key.entity_type == "task":
                    new_parent_id = None
                else:
                    new_parent_id = int(
                        new_parent_key.entity_id
                    )

                if new_parent_id is None:
                    new_rows = cur.execute(
                        """
                        SELECT id
                        FROM subtasks
                        WHERE task_id = ?
                          AND parent_subtask_id IS NULL
                          AND id <> ?
                        ORDER BY position ASC, created_at ASC, id ASC
                        """,
                        (
                            owner_task_id,
                            key.entity_id,
                        ),
                    ).fetchall()
                else:
                    new_rows = cur.execute(
                        """
                        SELECT id
                        FROM subtasks
                        WHERE task_id = ?
                          AND parent_subtask_id = ?
                          AND id <> ?
                        ORDER BY position ASC, created_at ASC, id ASC
                        """,
                        (
                            owner_task_id,
                            new_parent_id,
                            key.entity_id,
                        ),
                    ).fetchall()

                new_position = len(new_rows)

                cur.execute(
                    """
                    UPDATE subtasks
                    SET parent_subtask_id = ?,
                        position = ?
                    WHERE id = ?
                    """,
                    (
                        new_parent_id,
                        new_position,
                        int(key.entity_id),
                    ),
                )

                conn.commit()

                return WBSMutationResult(
                    True,
                    cls.OK,
                    "Subtask hierarchy updated.",
                    key=key,
                    parent_key=new_parent_key,
                    old_position=int(
                        moving["position"] or 0
                    ),
                    new_position=new_position,
                )

            except Exception:
                conn.rollback()
                raise
