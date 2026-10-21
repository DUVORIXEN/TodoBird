
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
        conn.execute("PRAGMA foreign_keys = ON")
        return conn


@pytest.fixture
def db(tmp_path):
    mgr = TempDB(
        tmp_path / "phase1e_indent.sqlite"
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

        conn.execute(
            "INSERT INTO tasks VALUES "
            "(1,'Root A',10,0,'Planned','2026-01-01')"
        )
        conn.execute(
            "INSERT INTO tasks VALUES "
            "(2,'Root B',10,1,'Planned','2026-01-02')"
        )

        # Root A
        #
        # 10 A
        # 11 B
        #    12 B1
        #    13 B2
        # 14 C
        #
        conn.execute(
            "INSERT INTO subtasks VALUES "
            "(10,1,NULL,'A',0,0,'2026-01-03')"
        )
        conn.execute(
            "INSERT INTO subtasks VALUES "
            "(11,1,NULL,'B',1,0,'2026-01-04')"
        )
        conn.execute(
            "INSERT INTO subtasks VALUES "
            "(12,1,11,'B1',0,0,'2026-01-05')"
        )
        conn.execute(
            "INSERT INTO subtasks VALUES "
            "(13,1,11,'B2',1,0,'2026-01-06')"
        )
        conn.execute(
            "INSERT INTO subtasks VALUES "
            "(14,1,NULL,'C',2,0,'2026-01-07')"
        )

        conn.commit()

    return mgr


def fetch(db, sql, params=()):
    with db.get_connection() as conn:
        return [
            tuple(r)
            for r in conn.execute(
                sql,
                params,
            ).fetchall()
        ]


def test_indent_places_item_under_previous_sibling(db):
    result = WBSMutationService.indent(
        db,
        EntityRef.subtask(14),
    )

    assert result.success
    assert result.parent_key == EntityRef.subtask(11)

    row = fetch(
        db,
        """
        SELECT task_id, parent_subtask_id, position
        FROM subtasks
        WHERE id = 14
        """,
    )

    # Existing B1/B2 remain first; C appends.
    assert row == [
        (1, 11, 2),
    ]


def test_indent_normalizes_old_scope(db):
    result = WBSMutationService.indent(
        db,
        EntityRef.subtask(11),
    )

    assert result.success
    assert result.parent_key == EntityRef.subtask(10)

    roots = fetch(
        db,
        """
        SELECT id, position
        FROM subtasks
        WHERE task_id = 1
          AND parent_subtask_id IS NULL
        ORDER BY position, id
        """,
    )

    assert roots == [
        (10, 0),
        (14, 1),
    ]


def test_first_sibling_cannot_indent(db):
    result = WBSMutationService.indent(
        db,
        EntityRef.subtask(10),
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_ALREADY_BOUNDARY
    )


def test_main_task_cannot_indent(db):
    result = WBSMutationService.indent(
        db,
        EntityRef.task(2),
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_TASK_PARENT_FORBIDDEN
    )


def test_outdent_moves_one_level_up_after_parent(db):
    result = WBSMutationService.outdent(
        db,
        EntityRef.subtask(12),
    )

    assert result.success
    assert result.parent_key == EntityRef.task(1)

    roots = fetch(
        db,
        """
        SELECT id, parent_subtask_id, position
        FROM subtasks
        WHERE task_id = 1
          AND parent_subtask_id IS NULL
        ORDER BY position, id
        """,
    )

    # B1 moves immediately after B.
    assert roots == [
        (10, None, 0),
        (11, None, 1),
        (12, None, 2),
        (14, None, 3),
    ]


def test_outdent_preserves_remaining_old_sibling_order(db):
    result = WBSMutationService.outdent(
        db,
        EntityRef.subtask(12),
    )

    assert result.success

    children = fetch(
        db,
        """
        SELECT id, position
        FROM subtasks
        WHERE task_id = 1
          AND parent_subtask_id = 11
        ORDER BY position, id
        """,
    )

    assert children == [
        (13, 0),
    ]


def test_direct_child_cannot_outdent_above_main_task(db):
    result = WBSMutationService.outdent(
        db,
        EntityRef.subtask(10),
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_ALREADY_BOUNDARY
    )


def test_main_task_outdent_is_boundary_noop(db):
    result = WBSMutationService.outdent(
        db,
        EntityRef.task(1),
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_ALREADY_BOUNDARY
    )


def test_indent_then_outdent_round_trip_structure(db):
    before = fetch(
        db,
        """
        SELECT id, parent_subtask_id, position
        FROM subtasks
        WHERE task_id = 1
        ORDER BY id
        """,
    )

    r1 = WBSMutationService.indent(
        db,
        EntityRef.subtask(14),
    )
    assert r1.success

    r2 = WBSMutationService.outdent(
        db,
        EntityRef.subtask(14),
    )
    assert r2.success

    after = fetch(
        db,
        """
        SELECT id, parent_subtask_id, position
        FROM subtasks
        WHERE task_id = 1
        ORDER BY id
        """,
    )

    assert after == before


def test_descendants_move_with_indented_parent(db):
    # Indent B under A. B1/B2 must remain children of B.
    result = WBSMutationService.indent(
        db,
        EntityRef.subtask(11),
    )

    assert result.success

    rows = fetch(
        db,
        """
        SELECT id, parent_subtask_id
        FROM subtasks
        WHERE id IN (11,12,13)
        ORDER BY id
        """,
    )

    assert rows == [
        (11, 10),
        (12, 11),
        (13, 11),
    ]


def test_wbs_snapshot_codes_rederive_after_indent(db):
    result = WBSMutationService.indent(
        db,
        EntityRef.subtask(11),
    )

    assert result.success

    snap = WBSService.build_project_hierarchy(
        db,
        project_id=10,
    )

    assert not snap.orphaned_keys

    b = snap.nodes_by_key[
        EntityRef.subtask(11)
    ]

    assert b.parent_key == EntityRef.subtask(10)
    assert b.depth == 2


def test_wbs_snapshot_codes_rederive_after_outdent(db):
    result = WBSMutationService.outdent(
        db,
        EntityRef.subtask(12),
    )

    assert result.success

    snap = WBSService.build_project_hierarchy(
        db,
        project_id=10,
    )

    assert not snap.orphaned_keys

    b1 = snap.nodes_by_key[
        EntityRef.subtask(12)
    ]

    assert b1.parent_key == EntityRef.task(1)
    assert b1.depth == 1
