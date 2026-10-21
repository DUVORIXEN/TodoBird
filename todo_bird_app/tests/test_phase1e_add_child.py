
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
        conn = sqlite3.connect(
            self.path
        )
        conn.row_factory = sqlite3.Row
        conn.execute(
            "PRAGMA foreign_keys = ON"
        )
        return conn


@pytest.fixture
def db(tmp_path):
    mgr = TempDB(
        tmp_path
        / "phase1e_add_child.sqlite"
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                parent_subtask_id INTEGER,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                is_completed INTEGER DEFAULT 0,
                position INTEGER DEFAULT 0,
                planned_date TEXT,
                due_date TEXT,
                planned_start_time TEXT,
                planned_end_time TEXT,
                estimated_duration INTEGER DEFAULT 0,
                priority TEXT DEFAULT 'Medium',
                progress INTEGER DEFAULT 0,
                show_in_gantt INTEGER DEFAULT 0,
                dependencies TEXT DEFAULT '[]',
                icon TEXT DEFAULT '',
                image_path TEXT DEFAULT '',
                is_pinned INTEGER DEFAULT 0,
                pin_color TEXT DEFAULT '#E95420',
                pin_position INTEGER DEFAULT 0,
                actual_start_date TEXT,
                actual_end_date TEXT,
                actual_start_time TEXT,
                actual_end_time TEXT,
                actual_duration INTEGER DEFAULT 0,
                planned_effort_minutes INTEGER DEFAULT 0,
                daily_dedication_minutes INTEGER DEFAULT 0,
                allocation_mode TEXT DEFAULT 'fixed_daily',
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
            """
            INSERT INTO tasks
                (id,title,project_id,position,status,created_at)
            VALUES
                (1,'Root',10,0,'Planned','2026-01-01')
            """
        )

        conn.execute(
            """
            INSERT INTO subtasks
                (
                    id,task_id,parent_subtask_id,
                    title,position,created_at
                )
            VALUES
                (10,1,NULL,'Existing A',0,'2026-01-02')
            """
        )

        conn.execute(
            """
            INSERT INTO subtasks
                (
                    id,task_id,parent_subtask_id,
                    title,position,created_at
                )
            VALUES
                (11,1,NULL,'Existing B',1,'2026-01-03')
            """
        )

        conn.execute(
            """
            INSERT INTO subtasks
                (
                    id,task_id,parent_subtask_id,
                    title,position,created_at
                )
            VALUES
                (12,1,10,'Nested A1',0,'2026-01-04')
            """
        )

        conn.commit()

    return mgr


def query(db, sql, params=()):
    with db.get_connection() as conn:
        return [
            tuple(row)
            for row in conn.execute(
                sql,
                params,
            ).fetchall()
        ]


def test_task_parent_creates_direct_subtask(db):
    result = WBSMutationService.create_child(
        db,
        EntityRef.task(1),
        "New Direct Child",
    )

    assert result.success
    assert result.key.entity_type == "subtask"
    assert result.parent_key == EntityRef.task(1)

    row = query(
        db,
        """
        SELECT task_id,parent_subtask_id,title,position
        FROM subtasks
        WHERE id = ?
        """,
        (result.key.entity_id,),
    )

    assert row == [
        (1, None, "New Direct Child", 2)
    ]


def test_subtask_parent_creates_nested_child(db):
    result = WBSMutationService.create_child(
        db,
        EntityRef.subtask(10),
        "New Nested Child",
    )

    assert result.success
    assert (
        result.parent_key
        == EntityRef.subtask(10)
    )

    row = query(
        db,
        """
        SELECT task_id,parent_subtask_id,title,position
        FROM subtasks
        WHERE id = ?
        """,
        (result.key.entity_id,),
    )

    assert row == [
        (1, 10, "New Nested Child", 1)
    ]


def test_child_position_appends_deterministically(db):
    r1 = WBSMutationService.create_child(
        db,
        EntityRef.task(1),
        "C",
    )

    r2 = WBSMutationService.create_child(
        db,
        EntityRef.task(1),
        "D",
    )

    assert r1.success
    assert r2.success

    rows = query(
        db,
        """
        SELECT title,position
        FROM subtasks
        WHERE task_id = 1
          AND parent_subtask_id IS NULL
        ORDER BY position,id
        """,
    )

    assert rows == [
        ("Existing A", 0),
        ("Existing B", 1),
        ("C", 2),
        ("D", 3),
    ]


def test_empty_title_rejected_without_insert(db):
    before = query(
        db,
        "SELECT COUNT(*) FROM subtasks",
    )[0][0]

    result = WBSMutationService.create_child(
        db,
        EntityRef.task(1),
        "   ",
    )

    after = query(
        db,
        "SELECT COUNT(*) FROM subtasks",
    )[0][0]

    assert not result.success
    assert after == before


def test_missing_parent_rejected(db):
    result = WBSMutationService.create_child(
        db,
        EntityRef.task(999),
        "Should Not Exist",
    )

    assert not result.success
    assert (
        result.reason_code
        == WBSMutationService.ERR_PARENT_NOT_FOUND
    )


def test_snapshot_is_valid_after_nested_creation(db):
    result = WBSMutationService.create_child(
        db,
        EntityRef.subtask(12),
        "Deep Child",
    )

    assert result.success

    snapshot = WBSService.build_project_hierarchy(
        db,
        project_id=10,
    )

    assert not snapshot.orphaned_keys

    node = snapshot.nodes_by_key[
        result.key
    ]

    assert (
        node.parent_key
        == EntityRef.subtask(12)
    )
    assert node.depth == 3
