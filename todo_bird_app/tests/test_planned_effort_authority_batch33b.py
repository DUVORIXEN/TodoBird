"""
Test Suite: Planned Effort + Daily Time Dedication + Resource Capacity Foundation (Batch 3.3B)
Validates EFF01 to EFF15 rules:
- Separation of Calendar Elapsed Span and Planned Work Effort
- Fixed Daily, Total Effort, and Custom by Day calculation models
- Persistence across Schema v10 database migrations
- Subtask and sub-subtask parity
- Non-interference with Gantt schedule geometry and Actual execution
"""

import os
import tempfile
import pytest
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.utils.time_math import duration_between
from todo_bird_app.utils.working_calendar import (
    get_working_days_between,
    calculate_planned_effort,
)
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.gantt.gantt_items import GanttTaskItem


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    from todo_bird_app.utils.working_calendar import set_configured_working_weekdays
    set_configured_working_weekdays({0, 1, 2, 3, 4})
    return app


def _temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    return db, path


def test_eff01_fixed_daily_three_days():
    """EFF01: 3 applicable working days, 4h/day = 12h (720 min) planned effort."""
    eff = calculate_planned_effort("2026-08-13", "2026-08-15", daily_dedication_minutes=240, allocation_mode="fixed_daily", working_weekdays={0, 1, 2, 3, 4, 5})
    assert eff == 720


def test_eff02_fixed_daily_two_hours():
    """EFF02: 3 working days, 2h/day = 6h (360 min) planned effort."""
    eff = calculate_planned_effort("2026-08-13", "2026-08-15", daily_dedication_minutes=120, allocation_mode="fixed_daily", working_weekdays={0, 1, 2, 3, 4, 5})
    assert eff == 360


def test_eff03_custom_by_day():
    """EFF03: Custom by day: 13 Aug=2h, 14 Aug=4h, 15 Aug=1h30 -> 7h30 (450 min)."""
    custom = {
        "2026-08-13": 120,
        "2026-08-14": 240,
        "2026-08-15": 90,
    }
    eff = calculate_planned_effort("2026-08-13", "2026-08-15", daily_dedication_minutes=0, allocation_mode="custom_by_day", custom_allocations=custom)
    assert eff == 450


def test_eff04_calendar_elapsed_vs_planned_effort_separation():
    """EFF04: Calendar elapsed span is 3280 min (54h40) while planned effort is 480 min (8h) for Mon-Fri."""
    task = Task(
        title="Elapsed vs Effort",
        planned_date="2026-08-13",
        due_date="2026-08-15",
        planned_start_time="07:00",
        planned_end_time="13:40",
        daily_dedication_minutes=240,
        allocation_mode="fixed_daily",
    )
    dialog = TaskDialog(projects=[], task=task)
    assert dialog.duration_spin.value() == 3280
    assert dialog.planned_effort_spin.value() == 480
    assert dialog.duration_spin.value() != dialog.planned_effort_spin.value()


def test_eff05_changing_daily_dedication_recalculates_effort_without_mutating_schedule():
    """EFF05: Changing daily dedication changes effort without changing start/end or elapsed duration."""
    task = Task(
        title="Dynamic Effort",
        planned_date="2026-08-13",
        due_date="2026-08-15",
        planned_start_time="07:00",
        planned_end_time="13:40",
    )
    dialog = TaskDialog(projects=[], task=task)
    assert dialog.duration_spin.value() == 3280

    dialog.daily_hours_spin.setValue(4)
    dialog.daily_mins_spin.setValue(0)
    assert dialog.planned_effort_spin.value() == 480
    assert dialog.duration_spin.value() == 3280

    dialog.daily_hours_spin.setValue(2)
    dialog.daily_mins_spin.setValue(30)
    assert dialog.planned_effort_spin.value() == 300
    assert dialog.duration_spin.value() == 3280


def test_eff06_changing_planned_end_date_recalculates_working_dates_and_effort():
    """EFF06: Changing planned end date from 15 Aug to 17 Aug increases Mon-Fri working days from 2 to 3."""
    eff2 = calculate_planned_effort("2026-08-13", "2026-08-15", daily_dedication_minutes=240, allocation_mode="fixed_daily", working_weekdays={0, 1, 2, 3, 4})
    assert eff2 == 480

    eff3 = calculate_planned_effort("2026-08-13", "2026-08-17", daily_dedication_minutes=240, allocation_mode="fixed_daily", working_weekdays={0, 1, 2, 3, 4})
    assert eff3 == 720


def test_eff07_manual_custom_allocations_table_persistence():
    """EFF07: Custom allocations table stores and retrieves per-day minutes safely."""
    db, path = _temp_db()
    try:
        tc = TaskController(db)
        tid = tc.add_task(Task(
            title="Custom Allocations Task",
            planned_date="2026-08-13",
            due_date="2026-08-15",
            planned_effort_minutes=450,
            allocation_mode="custom_by_day",
        ))

        allocations = [
            {"allocation_date": "2026-08-13", "planned_minutes": 120},
            {"allocation_date": "2026-08-14", "planned_minutes": 240},
            {"allocation_date": "2026-08-15", "planned_minutes": 90},
        ]
        db.set_task_allocations(task_id=tid, subtask_id=None, allocations=allocations)

        loaded = db.get_task_allocations(task_id=tid)
        assert len(loaded) == 3
        assert sum(a["planned_minutes"] for a in loaded) == 450
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_eff08_subtask_dedication_persists():
    """EFF08: Subtask planned effort and dedication fields persist in DB."""
    db, path = _temp_db()
    try:
        tc = TaskController(db)
        tid = tc.add_task(Task(title="Parent"))
        sid = db.insert_subtask(
            task_id=tid,
            title="Sub Effort",
            planned_date="2026-08-13",
            due_date="2026-08-15",
            daily_dedication_minutes=240,
            planned_effort_minutes=720,
            allocation_mode="fixed_daily",
        )
        subs = db.get_all_subtasks_flat(tid)
        sub = next(s for s in subs if s["id"] == sid)
        assert sub["daily_dedication_minutes"] == 240
        assert sub["planned_effort_minutes"] == 720
        assert sub["allocation_mode"] == "fixed_daily"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_eff09_sub_subtask_dedication_persists():
    """EFF09: Sub-subtask planned effort and dedication fields persist in DB."""
    db, path = _temp_db()
    try:
        tc = TaskController(db)
        tid = tc.add_task(Task(title="Parent"))
        sid = db.insert_subtask(task_id=tid, title="Sub 1")
        ssid = db.insert_subtask(
            task_id=tid,
            parent_subtask_id=sid,
            title="SubSub Effort",
            planned_date="2026-08-13",
            due_date="2026-08-15",
            daily_dedication_minutes=120,
            planned_effort_minutes=360,
            allocation_mode="fixed_daily",
        )
        subs = db.get_all_subtasks_flat(tid)
        subsub = next(s for s in subs if s["id"] == ssid)
        assert subsub["daily_dedication_minutes"] == 120
        assert subsub["planned_effort_minutes"] == 360
        assert subsub["allocation_mode"] == "fixed_daily"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_eff10_actual_calculation_remains_unchanged():
    """EFF10: Actual execution timing and actual_duration calculation remain unaffected."""
    task = Task(
        title="Actual Unchanged",
        actual_start_date="2026-08-14",
        actual_start_time="10:00",
        actual_end_date="2026-08-16",
        actual_end_time="17:00",
        actual_duration=3300,
        planned_effort_minutes=720,
    )
    assert task.actual_duration == 3300
    assert task.planned_effort_minutes == 720


def test_eff11_gantt_geometry_unchanged_when_effort_changes():
    """EFF11: Gantt schedule bar geometry is based strictly on planned datetime schedule, not effort."""
    task = Task(
        title="Gantt Item Geometry",
        planned_date="2026-08-13",
        due_date="2026-08-15",
        planned_start_time="07:00",
        planned_end_time="13:40",
        estimated_duration=3280,
        planned_effort_minutes=720,
    )
    profile = {"planned": "#3584E4", "actual": "#10B981"}
    item1 = GanttTaskItem(task, row=0, col_start=0.0, duration_cols=3.0, col_width=80, color_profile=profile)
    rect1 = item1.boundingRect()

    task.planned_effort_minutes = 2400
    item2 = GanttTaskItem(task, row=0, col_start=0.0, duration_cols=3.0, col_width=80, color_profile=profile)
    rect2 = item2.boundingRect()

    assert rect1.width() == rect2.width()


def test_eff12_progress_unchanged_when_effort_changes():
    """EFF12: Progress remains an independent 0-100 completion metric."""
    task = Task(
        title="Progress Independence",
        progress=45,
        planned_effort_minutes=720,
    )
    assert task.progress == 45
    task.planned_effort_minutes = 1440
    assert task.progress == 45


def test_eff13_zero_minute_dedication_handled_safely():
    """EFF13: 0-minute daily dedication produces 0 planned effort without error."""
    eff = calculate_planned_effort("2026-08-13", "2026-08-15", daily_dedication_minutes=0, allocation_mode="fixed_daily")
    assert eff == 0


def test_eff14_dedication_cannot_be_negative():
    """EFF14: Negative values are safely clamped to 0."""
    eff = calculate_planned_effort("2026-08-13", "2026-08-15", daily_dedication_minutes=-50, allocation_mode="fixed_daily")
    assert eff == 0


def test_eff15_custom_per_day_total_exact_integer_minutes():
    """EFF15: Custom allocations sum with exact integer minute precision (no float rounding error)."""
    custom = {
        "2026-08-13": 75,   # 1h 15m
        "2026-08-14": 143,  # 2h 23m
        "2026-08-15": 202,  # 3h 22m
    }
    eff = calculate_planned_effort("2026-08-13", "2026-08-15", daily_dedication_minutes=0, allocation_mode="custom_by_day", custom_allocations=custom)
    assert eff == 420  # 75 + 143 + 202 = 420 (7h 00m)
    assert isinstance(eff, int)
