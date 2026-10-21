
import sqlite3

import pytest

from todo_bird_app.services.wbs_service import EntityRef
from todo_bird_app.services.wbs_mutation_service import (
    WBSMutationService,
)


class TempDB:
    def __init__(self, path):
        self.path = str(path)

    def get_connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


@pytest.fixture
def db(tmp_path):
    mgr = TempDB(
        tmp_path / "phase1e.sqlite"
    )

    with mgr.get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                project_id INTEGER,
                position INTEGER DEFAULT 0,
                status TEXT DEFAULT 'Planned',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE subtasks (
                id INTEGER PRIMARY KEY,
                task_id INTEGER NOT NULL,
                parent_subtask_id INTEGER,
                title TEXT NOT NULL,
                position INTEGER DEFAULT 0,
                is_completed INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(task_id)
                    REFERENCES tasks(id)
                    ON DELETE CASCADE,
                FOREIGN KEY(parent_subtask_id)
                    REFERENCES subtasks(id)
                    ON DELETE CASCADE
            );
            """
        )

        # Project 10 roots
        conn.execute(
            "INSERT INTO tasks VALUES (1,'Root A',10,0,'Planned','2026-01-01')"
        )
        conn.execute(
            "INSERT INTO tasks VALUES (2,'Root B',10,1,'Planned','2026-01-02')"
        )
        conn.execute(
            "INSERT INTO tasks VALUES (3,'Root C',10,2,'Planned','2026-01-03')"
        )

        # Different project
        conn.execute(
            "INSERT INTO tasks VALUES (4,'Other Project',20,0,'Planned','2026-01-04')"
        )

        # Root A subtree:
        # 10 Alpha
        # 11 Beta
        #    12 Beta Child
        #       13 Beta Grandchild
        conn.execute(
            "INSERT INTO subtasks VALUES (10,1,NULL,'Alpha',0,0,'2026-01-05')"
        )
        conn.execute(
            "INSERT INTO subtasks VALUES (11,1,NULL,'Beta',1,0,'2026-01-06')"
        )
        conn.execute(
            "INSERT INTO subtasks VALUES (12,1,11,'Beta Child',0,0,'2026-01-07')"
        )
        conn.execute(
            "INSERT INTO subtasks VALUES (13,1,12,'Beta Grandchild',0,0,'2026-01-08')"
        )

        # Root B subtask
        conn.execute(
            "INSERT INTO subtasks VALUES (20,2,NULL,'B Child',0,0,'2026-01-09')"
        )

        conn.commit()

    return mgr


def rows(db, sql, params=()):
    with db.get_connection() as conn:
        return [
            tuple(r)
            for r in conn.execute(
                sql,
                params,
            ).fetchall()
        ]


def test_task_roots_move_down_transactionally(db):
    result = WBSMutationService.move_down(
        db,
        EntityRef.task(1),
    )

    assert result.success

    got = rows(
        db,
        """
        SELECT id, position
        FROM tasks
        WHERE project_id = 10
        ORDER BY position, id
        """,
    )

    assert got == [
        (2, 0),
        (1, 1),
        (3, 2),
    ]


def test_top_level_subtasks_move_up(db):
    result = WBSMutationService.move_up(
        db,
        EntityRef.subtask(11),
    )

    assert result.success

    got = rows(
        db,
        """
        SELECT id, position
        FROM subtasks
        WHERE task_id = 1
          AND parent_subtask_id IS NULL
        ORDER BY position, id
        """,
    )

    assert got == [
        (11, 0),
        (10, 1),
    ]


def test_boundary_move_is_safe_noop(db):
    result = WBSMutationService.move_up(
        db,
        EntityRef.task(1),
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_ALREADY_BOUNDARY
    )

    got = rows(
        db,
        """
        SELECT id, position
        FROM tasks
        WHERE project_id = 10
        ORDER BY position, id
        """,
    )

    assert got == [
        (1, 0),
        (2, 1),
        (3, 2),
    ]


def test_main_task_cannot_be_indented(db):
    result = WBSMutationService.validate_reparent(
        db,
        EntityRef.task(2),
        EntityRef.task(1),
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_TASK_PARENT_FORBIDDEN
    )


def test_subtask_cannot_parent_itself(db):
    result = WBSMutationService.validate_reparent(
        db,
        EntityRef.subtask(11),
        EntityRef.subtask(11),
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_SELF_PARENT
    )


def test_cycle_is_rejected(db):
    # 11 -> 12 -> 13 currently.
    # Moving 11 beneath 13 would create a cycle.
    result = WBSMutationService.validate_reparent(
        db,
        EntityRef.subtask(11),
        EntityRef.subtask(13),
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_CYCLE
    )


def test_cross_main_task_reparent_rejected(db):
    result = WBSMutationService.validate_reparent(
        db,
        EntityRef.subtask(10),
        EntityRef.task(2),
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_CROSS_TASK
    )


def test_nested_subtask_can_outdent_to_own_task(db):
    result = WBSMutationService.reparent_subtask(
        db,
        EntityRef.subtask(12),
        EntityRef.task(1),
    )

    assert result.success

    got = rows(
        db,
        """
        SELECT task_id, parent_subtask_id, position
        FROM subtasks
        WHERE id = 12
        """,
    )

    assert got == [
        (1, None, 2),
    ]


def test_subtask_can_indent_beneath_same_task_sibling(db):
    result = WBSMutationService.reparent_subtask(
        db,
        EntityRef.subtask(10),
        EntityRef.subtask(11),
    )

    assert result.success

    got = rows(
        db,
        """
        SELECT task_id, parent_subtask_id, position
        FROM subtasks
        WHERE id = 10
        """,
    )

    # Existing child 12 remains first; moved child appends.
    assert got == [
        (1, 11, 1),
    ]


def test_next_child_position_task_parent(db):
    assert (
        WBSMutationService.next_child_position(
            db,
            EntityRef.task(1),
        )
        == 2
    )


def test_next_child_position_nested_parent(db):
    assert (
        WBSMutationService.next_child_position(
            db,
            EntityRef.subtask(11),
        )
        == 1
    )


def test_typed_identity_collision_safe(db):
    # task:1 and subtask:1 are distinct semantic entities,
    # regardless of equal numeric IDs.
    assert EntityRef.task(1) != EntityRef.subtask(1)


def test_rebuild_wbs_after_reparent_has_valid_codes(db):
    result = WBSMutationService.reparent_subtask(
        db,
        EntityRef.subtask(10),
        EntityRef.subtask(11),
    )

    assert result.success

    from todo_bird_app.services.wbs_service import WBSService

    snap = WBSService.build_project_hierarchy(
        db,
        project_id=10,
    )

    assert not snap.orphaned_keys

    assert (
        snap.nodes_by_key[
            EntityRef.subtask(10)
        ].parent_key
        == EntityRef.subtask(11)
    )

    assert (
        snap.nodes_by_key[
            EntityRef.subtask(10)
        ].depth
        == 2
    )
