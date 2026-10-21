
from types import SimpleNamespace

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.views.gantt_view import GanttView


def _task(tid, pid, title, show=True):
    return Task(
        id=tid,
        title=title,
        project_id=pid,
        priority=TaskPriority.MEDIUM,
        status=TaskStatus.PLANNED,
        show_in_gantt=show,
        planned_date=None,
        due_date=None,
        estimated_duration=0,
        progress=0,
    )


def test_live_project_rows_use_wbs_rollup_and_are_read_only():
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
                (id, title, project_id, position, status,
                 show_in_gantt, planned_effort_minutes, progress)
            VALUES
                (1, 'A', ?, 0, 'Planned', 1, 9999, 5)
            """,
            (pid,),
        )

        cur.execute(
            """
            INSERT INTO subtasks
                (task_id, parent_subtask_id, title, position,
                 is_completed, show_in_gantt,
                 planned_effort_minutes, progress)
            VALUES
                (1, NULL, 'B', 0, 0, 0, 9999, 1)
            """
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
                (1, ?, 'D', 0, 0, 1,
                 '2026-08-18', '08:00', '16:00', 480, 50)
            """,
            (bid,),
        )

        cur.execute(
            """
            INSERT INTO subtasks
                (task_id, parent_subtask_id, title, position,
                 is_completed, show_in_gantt,
                 planned_date, planned_start_time, planned_end_time,
                 planned_effort_minutes, progress)
            VALUES
                (1, ?, 'E', 1, 1, 1,
                 '2026-08-19', '10:00', '14:00', 240, 100)
            """,
            (bid,),
        )

        conn.commit()

    real_a = _task(1, pid, "A")

    fake_view = SimpleNamespace(
        db_manager=db,
    )

    rows = GanttView._build_phase1d_wbs_gantt_items(
        fake_view,
        [real_a],
    )

    assert [x.title for x in rows] == [
        "A",
        "B",
        "D",
        "E",
    ]

    a, b, d, e = rows

    assert a.gantt_is_summary is True
    assert b.gantt_is_summary is True
    assert a.gantt_read_only is True
    assert b.gantt_read_only is True

    assert d.gantt_is_summary is False
    assert d.gantt_read_only is False

    assert [x.gantt_depth for x in rows] == [0, 1, 2, 2]

    # Parent stored 9999 values remain raw Task fields.
    # Derived WBS summary values are exposed only through gantt_* metadata.
    assert a.planned_effort_minutes == 9999
    assert b.planned_effort_minutes == 9999
    assert a.gantt_rollup_planned_effort == 720
    assert b.gantt_rollup_planned_effort == 720

    assert a.progress == 5
    assert b.progress == 1
    assert a.gantt_rollup_progress == 67
    assert b.gantt_rollup_progress == 67

    assert a.planned_date is None
    assert a.planned_start_time is None
    assert a.due_date is None
    assert a.planned_end_time is None
    assert a.gantt_summary_planned_start.strftime("%Y-%m-%d %H:%M") == "2026-08-18 08:00"
    assert a.gantt_summary_planned_finish.strftime("%Y-%m-%d %H:%M") == "2026-08-19 14:00"

    # Critical invariant: Actual Effort is not reused as Actual Elapsed Span.
    assert a.actual_duration == 0
    assert a.actual_start_date is None
    assert a.actual_end_date is None

    # Stable nested identity for existing edit/open receiver.
    assert d.id < 0
    assert d.source_subtask_id > 0

    db.close()


def test_inbox_main_task_behavior_preserved():
    db = DatabaseManager(":memory:")

    inbox = _task(
        91,
        None,
        "Inbox Gantt",
        show=True,
    )

    fake_view = SimpleNamespace(
        db_manager=db,
    )

    rows = GanttView._build_phase1d_wbs_gantt_items(
        fake_view,
        [inbox],
    )

    assert rows == [inbox]
    assert inbox.gantt_is_summary is False
    assert inbox.gantt_read_only is False

    db.close()


def test_summary_actual_lane_is_explicitly_disabled():
    source = open(
        "todo_bird_app/gantt/gantt_items.py",
        "r",
    ).read()

    assert "show_execution_lane = (" in source
    assert "(not is_summary)" in source
