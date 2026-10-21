
from todo_bird_app.database import DatabaseManager
from todo_bird_app.services.wbs_service import (
    EntityRef,
    WBSService,
)
from todo_bird_app.services.gantt_wbs_adapter import (
    GanttWBSAdapter,
)


def test_wbs_adapter_summary_order_visibility_and_rollup():
    db = DatabaseManager(":memory:")

    with db.get_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO projects (name, color) VALUES ('P', '#3584E4')"
        )
        pid = cur.lastrowid

        cur.execute(
            """
            INSERT INTO tasks
                (title, project_id, position, status, show_in_gantt,
                 planned_effort_minutes, progress)
            VALUES
                ('A', ?, 0, 'Planned', 1, 9999, 5)
            """,
            (pid,),
        )
        tid = cur.lastrowid

        cur.execute(
            """
            INSERT INTO subtasks
                (task_id, parent_subtask_id, title, position,
                 is_completed, show_in_gantt,
                 planned_date, planned_start_time, planned_end_time,
                 planned_effort_minutes, progress)
            VALUES
                (?, NULL, 'B', 0, 0, 0,
                 NULL, NULL, NULL, 9999, 1)
            """,
            (tid,),
        )
        bid = cur.lastrowid

        cur.execute(
            """
            INSERT INTO subtasks
                (task_id, parent_subtask_id, title, position,
                 is_completed, show_in_gantt,
                 planned_date, planned_start_time, planned_end_time,
                 planned_effort_minutes, progress)
            VALUES
                (?, ?, 'D', 0, 0, 1,
                 '2026-08-18', '08:00', '16:00', 480, 50)
            """,
            (tid, bid),
        )

        cur.execute(
            """
            INSERT INTO subtasks
                (task_id, parent_subtask_id, title, position,
                 is_completed, show_in_gantt,
                 planned_date, planned_start_time, planned_end_time,
                 planned_effort_minutes, progress)
            VALUES
                (?, ?, 'E', 1, 1, 1,
                 '2026-08-19', '10:00', '14:00', 240, 100)
            """,
            (tid, bid),
        )

        conn.commit()

    snap = WBSService.build_project_hierarchy(
        db,
        project_id=pid,
    )

    rows = GanttWBSAdapter.build_project_rows(
        snap,
        db,
    )

    assert [r.title for r in rows] == [
        "A",
        "B",
        "D",
        "E",
    ]

    a, b, d, e = rows

    # Canonical hierarchy
    assert a.depth == 0
    assert b.depth == 1
    assert d.depth == 2
    assert e.depth == 2

    # B is visible even though its own show_in_gantt=0 because
    # descendants D/E are visible.
    assert b.show_in_gantt is True

    # Summary rows are derived/read-only.
    assert a.is_summary is True
    assert b.is_summary is True
    assert a.is_read_only is True
    assert b.is_read_only is True

    # Leaf rows remain editable candidates.
    assert d.is_summary is False
    assert d.is_read_only is False

    # Parent stored 9999 effort is ignored; only descendant leaves count.
    assert a.planned_effort_minutes == 720
    assert b.planned_effort_minutes == 720

    # Weighted progress: (480*50 + 240*100)/720 = 67%.
    assert a.progress_percent == 67
    assert b.progress_percent == 67

    # Summary schedule envelope.
    assert a.planned_start.strftime("%Y-%m-%d %H:%M") == "2026-08-18 08:00"
    assert a.planned_finish.strftime("%Y-%m-%d %H:%M") == "2026-08-19 14:00"

    assert a.leaf_count == 2
    assert b.leaf_count == 2

    db.close()
