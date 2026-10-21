
import sqlite3

import pytest

from todo_bird_app.services.wbs_service import (
    EntityRef,
    WBSService,
)
from todo_bird_app.services.wbs_mutation_service import (
    WBSMutationService,
)


class TempDB:
    def __init__(self, path):
        self.path = str(path)

    def get_connection(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            "PRAGMA foreign_keys = ON"
        )
        return conn


@pytest.fixture
def db(tmp_path):
    mgr = TempDB(
        tmp_path / "phase1e_drag_drop.sqlite"
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

        # Project 10
        conn.execute(
            "INSERT INTO tasks VALUES "
            "(1,'Root A',10,0,'Planned','2026-01-01')"
        )
        conn.execute(
            "INSERT INTO tasks VALUES "
            "(2,'Root B',10,1,'Planned','2026-01-02')"
        )
        conn.execute(
            "INSERT INTO tasks VALUES "
            "(3,'Root C',10,2,'Planned','2026-01-03')"
        )

        # Project 20
        conn.execute(
            "INSERT INTO tasks VALUES "
            "(9,'Other Project',20,0,'Planned','2026-01-04')"
        )

        # Root A:
        #
        # 10 Alpha
        #   12 AlphaChild
        #     15 DeepChild
        # 11 Beta
        #   13 BetaChild
        # 14 Gamma
        #
        conn.execute(
            "INSERT INTO subtasks VALUES "
            "(10,1,NULL,'Alpha',0,0,'2026-01-05')"
        )
        conn.execute(
            "INSERT INTO subtasks VALUES "
            "(11,1,NULL,'Beta',1,0,'2026-01-06')"
        )
        conn.execute(
            "INSERT INTO subtasks VALUES "
            "(14,1,NULL,'Gamma',2,0,'2026-01-07')"
        )
        conn.execute(
            "INSERT INTO subtasks VALUES "
            "(12,1,10,'AlphaChild',0,0,'2026-01-08')"
        )
        conn.execute(
            "INSERT INTO subtasks VALUES "
            "(15,1,12,'DeepChild',0,0,'2026-01-09')"
        )
        conn.execute(
            "INSERT INTO subtasks VALUES "
            "(13,1,11,'BetaChild',0,0,'2026-01-10')"
        )

        # Root B child for cross-main-task rejection.
        conn.execute(
            "INSERT INTO subtasks VALUES "
            "(20,2,NULL,'RootB Child',0,0,'2026-01-11')"
        )

        # Other project child.
        conn.execute(
            "INSERT INTO subtasks VALUES "
            "(90,9,NULL,'Other Child',0,0,'2026-01-12')"
        )

        conn.commit()

    return mgr


def rows(db, sql, params=()):
    with db.get_connection() as conn:
        return [
            tuple(row)
            for row in conn.execute(
                sql,
                params,
            ).fetchall()
        ]


def test_root_task_drag_reorders_before(db):
    result = WBSMutationService.drag_drop_move(
        db,
        EntityRef.task(3),
        EntityRef.task(1),
        "before",
    )

    assert result.success

    assert rows(
        db,
        """
        SELECT id, position
        FROM tasks
        WHERE project_id = 10
        ORDER BY position, id
        """,
    ) == [
        (3, 0),
        (1, 1),
        (2, 2),
    ]


def test_root_task_cannot_drop_into_task(db):
    result = WBSMutationService.drag_drop_move(
        db,
        EntityRef.task(2),
        EntityRef.task(1),
        "into",
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_TASK_PARENT_FORBIDDEN
    )


def test_root_task_cross_project_rejected(db):
    result = WBSMutationService.drag_drop_move(
        db,
        EntityRef.task(1),
        EntityRef.task(9),
        "after",
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_CROSS_PROJECT
    )


def test_subtask_drop_into_sibling_becomes_last_child(db):
    result = WBSMutationService.drag_drop_move(
        db,
        EntityRef.subtask(14),
        EntityRef.subtask(10),
        "into",
    )

    assert result.success

    assert rows(
        db,
        """
        SELECT id, parent_subtask_id, position
        FROM subtasks
        WHERE id IN (12,14)
        ORDER BY position, id
        """,
    ) == [
        (12, 10, 0),
        (14, 10, 1),
    ]


def test_subtask_before_target_reparents_to_target_scope(db):
    result = WBSMutationService.drag_drop_move(
        db,
        EntityRef.subtask(13),
        EntityRef.subtask(14),
        "before",
    )

    assert result.success

    assert rows(
        db,
        """
        SELECT id, parent_subtask_id, position
        FROM subtasks
        WHERE task_id = 1
          AND parent_subtask_id IS NULL
        ORDER BY position, id
        """,
    ) == [
        (10, None, 0),
        (11, None, 1),
        (13, None, 2),
        (14, None, 3),
    ]


def test_subtask_after_target_reorders_same_scope(db):
    result = WBSMutationService.drag_drop_move(
        db,
        EntityRef.subtask(10),
        EntityRef.subtask(11),
        "after",
    )

    assert result.success

    assert rows(
        db,
        """
        SELECT id, position
        FROM subtasks
        WHERE task_id = 1
          AND parent_subtask_id IS NULL
        ORDER BY position, id
        """,
    ) == [
        (11, 0),
        (10, 1),
        (14, 2),
    ]


def test_drop_into_owner_task_outdents_to_direct_child(db):
    result = WBSMutationService.drag_drop_move(
        db,
        EntityRef.subtask(12),
        EntityRef.task(1),
        "into",
    )

    assert result.success
    assert result.parent_key == EntityRef.task(1)

    row = rows(
        db,
        """
        SELECT parent_subtask_id, position
        FROM subtasks
        WHERE id = 12
        """,
    )[0]

    assert row[0] is None


def test_cross_main_task_subtask_move_rejected(db):
    result = WBSMutationService.drag_drop_move(
        db,
        EntityRef.subtask(10),
        EntityRef.subtask(20),
        "into",
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_CROSS_TASK
    )


def test_cross_project_subtask_move_rejected(db):
    result = WBSMutationService.drag_drop_move(
        db,
        EntityRef.subtask(10),
        EntityRef.subtask(90),
        "into",
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_CROSS_PROJECT
    )


def test_self_drop_rejected(db):
    result = WBSMutationService.drag_drop_move(
        db,
        EntityRef.subtask(10),
        EntityRef.subtask(10),
        "into",
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_SELF_PARENT
    )


def test_descendant_cycle_rejected(db):
    # Alpha(10) -> AlphaChild(12) -> DeepChild(15)
    # Moving Alpha into DeepChild must be rejected.
    result = WBSMutationService.drag_drop_move(
        db,
        EntityRef.subtask(10),
        EntityRef.subtask(15),
        "into",
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_CYCLE
    )


def test_descendants_stay_attached_when_parent_moves(db):
    result = WBSMutationService.drag_drop_move(
        db,
        EntityRef.subtask(10),
        EntityRef.subtask(11),
        "into",
    )

    assert result.success

    # AlphaChild remains child of Alpha.
    assert rows(
        db,
        """
        SELECT parent_subtask_id
        FROM subtasks
        WHERE id = 12
        """,
    ) == [(10,)]

    # Deep child still remains below AlphaChild.
    assert rows(
        db,
        """
        SELECT parent_subtask_id
        FROM subtasks
        WHERE id = 15
        """,
    ) == [(12,)]


def test_invalid_zone_rejected_without_mutation(db):
    before = rows(
        db,
        """
        SELECT id, parent_subtask_id, position
        FROM subtasks
        ORDER BY id
        """,
    )

    result = WBSMutationService.drag_drop_move(
        db,
        EntityRef.subtask(10),
        EntityRef.subtask(11),
        "sideways",
    )

    after = rows(
        db,
        """
        SELECT id, parent_subtask_id, position
        FROM subtasks
        ORDER BY id
        """,
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_INVALID_DROP
    )
    assert after == before


def test_snapshot_remains_valid_after_complex_drop(db):
    result = WBSMutationService.drag_drop_move(
        db,
        EntityRef.subtask(14),
        EntityRef.subtask(12),
        "into",
    )

    assert result.success

    snapshot = WBSService.build_project_hierarchy(
        db,
        project_id=10,
    )

    assert not snapshot.orphaned_keys

    gamma = snapshot.nodes_by_key[
        EntityRef.subtask(14)
    ]

    assert gamma.parent_key == EntityRef.subtask(12)
