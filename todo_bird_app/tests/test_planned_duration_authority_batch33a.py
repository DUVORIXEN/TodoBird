"""
Tests for TODO BIRD Batch 3.3A Planned Multi-Day Duration Authority Repair.
Covers PD01..PD15.
"""

import os
import tempfile
from datetime import date, datetime, time
import pytest
from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import QApplication

from todo_bird_app.utils.time_math import (
    duration_between,
    format_duration_display,
    parse_hhmm,
    format_hhmm,
)
from todo_bird_app.database import DatabaseManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.widgets.task_dialog import TaskDialog


def _temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    return db, path


@pytest.fixture(autouse=True)
def _ensure_app():
    import sys
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    yield app


# ==============================================================================
# PLANNED DURATION MATHEMATICAL AUTHORITY (PD01 .. PD07)
# ==============================================================================

def test_pd01_multi_day_planned_duration():
    """PD01: 13 Aug 07:00 -> 15 Aug 13:40 = 3280m (54h 40m)."""
    dur = duration_between("2026-08-13", "07:00", "2026-08-15", "13:40")
    assert dur == 3280
    assert format_duration_display(dur) == "54h 40m"


def test_pd02_same_day_planned_duration():
    """PD02: 13 Aug 07:00 -> 13 Aug 13:40 = 400m (6h 40m)."""
    dur = duration_between("2026-08-13", "07:00", "2026-08-13", "13:40")
    assert dur == 400
    assert format_duration_display(dur) == "6h 40m"


def test_pd03_cross_midnight_next_day():
    """PD03: 13 Aug 23:30 -> 14 Aug 00:45 = 75m."""
    dur = duration_between("2026-08-13", "23:30", "2026-08-14", "00:45")
    assert dur == 75
    assert format_duration_display(dur) == "1h 15m"


def test_pd04_same_day_long_span():
    """PD04: 13 Aug 08:23 -> 13 Aug 21:45 = 802m (13h 22m)."""
    dur = duration_between("2026-08-13", "08:23", "2026-08-13", "21:45")
    assert dur == 802
    assert format_duration_display(dur) == "13h 22m"


def test_pd05_exact_24_hour_span():
    """PD05: 13 Aug 08:00 -> 14 Aug 08:00 = 1440m (24h)."""
    dur = duration_between("2026-08-13", "08:00", "2026-08-14", "08:00")
    assert dur == 1440
    assert format_duration_display(dur) == "24h"


def test_pd06_exact_48_hour_span():
    """PD06: 13 Aug 08:00 -> 15 Aug 08:00 = 2880m (48h)."""
    dur = duration_between("2026-08-13", "08:00", "2026-08-15", "08:00")
    assert dur == 2880
    assert format_duration_display(dur) == "48h"


def test_pd07_exact_49_hour_span():
    """PD07: 13 Aug 08:00 -> 15 Aug 09:00 = 2940m (49h)."""
    dur = duration_between("2026-08-13", "08:00", "2026-08-15", "09:00")
    assert dur == 2940
    assert format_duration_display(dur) == "49h"


# ==============================================================================
# TASK DIALOG SIGNAL WIRING TESTS (PD08 .. PD11)
# ==============================================================================

def test_pd08_changing_due_date_updates_duration_immediately():
    """PD08: changing due_date updates duration immediately in TaskDialog."""
    task = Task(
        title="Signal Test",
        planned_date="2026-08-13",
        due_date="2026-08-13",
        planned_start_time="07:00",
        planned_end_time="13:40",
    )
    dialog = TaskDialog(projects=[], task=task)
    assert dialog.duration_spin.value() == 400

    # Change due_date to 2026-08-15
    dialog.due_date_edit.setDate(QDate(2026, 8, 15))
    assert dialog.duration_spin.value() == 3280
    assert "54h 40m" in dialog.duration_spin.toolTip()


def test_pd09_changing_planned_date_updates_immediately():
    """PD09: changing planned_date preserves duration and moves target finish."""
    task = Task(
        title="Signal Test",
        planned_date="2026-08-15",
        due_date="2026-08-15",
        planned_start_time="07:00",
        planned_end_time="13:40",
    )
    dialog = TaskDialog(projects=[], task=task)
    assert dialog.duration_spin.value() == 400

    # Changing the start anchor must not rewrite the estimated duration.
    dialog.planned_date_edit.setDate(QDate(2026, 8, 13))
    assert dialog.duration_spin.value() == 400
    assert dialog.due_date_edit.date().toString("yyyy-MM-dd") == "2026-08-13"
    assert dialog.end_time_edit.time().toString("HH:mm") == "13:40"


def test_pd10_changing_start_time_updates_immediately():
    """PD10: changing start time preserves duration and moves target finish."""
    task = Task(
        title="Signal Test",
        planned_date="2026-08-13",
        due_date="2026-08-15",
        planned_start_time="07:00",
        planned_end_time="13:40",
    )
    dialog = TaskDialog(projects=[], task=task)
    assert dialog.duration_spin.value() == 3280

    # Changing the start anchor must not rewrite the estimated duration.
    dialog.start_time_edit.setTime(QTime(8, 0))
    assert dialog.duration_spin.value() == 3280
    assert dialog.due_date_edit.date().toString("yyyy-MM-dd") == "2026-08-15"
    assert dialog.end_time_edit.time().toString("HH:mm") == "14:40"


def test_pd11_changing_end_time_updates_immediately():
    """PD11: changing end time updates duration immediately in TaskDialog."""
    task = Task(
        title="Signal Test",
        planned_date="2026-08-13",
        due_date="2026-08-15",
        planned_start_time="07:00",
        planned_end_time="13:40",
    )
    dialog = TaskDialog(projects=[], task=task)
    assert dialog.duration_spin.value() == 3280

    # Change end time to 14:40 (+60m -> 3340m)
    dialog.end_time_edit.setTime(QTime(14, 40))
    assert dialog.duration_spin.value() == 3340


# ==============================================================================
# ACTUAL DURATION & HIERARCHY PARITY TESTS (PD12 .. PD15)
# ==============================================================================

def test_pd12_actual_duration_unchanged_and_correct():
    """PD12: Actual duration still unchanged and exact (14 Aug 10:00 -> 16 Aug 17:00 = 3300m)."""
    dur = duration_between("2026-08-14", "10:00", "2026-08-16", "17:00")
    assert dur == 3300
    assert format_duration_display(dur) == "55h"


def test_pd13_main_task_parity():
    """PD13: Main task dialog produces exact 3280 mins on save."""
    task = Task(
        title="Main Parity",
        planned_date="2026-08-13",
        due_date="2026-08-15",
        planned_start_time="07:00",
        planned_end_time="13:40",
    )
    dialog = TaskDialog(projects=[], task=task)
    assert dialog.duration_spin.value() == 3280
    dialog.on_save()
    saved = dialog.get_task()
    assert saved.estimated_duration == 3280


def test_pd14_subtask_parity():
    """PD14: Subtask editing uses same 3280 min multi-day duration authority."""
    db, path = _temp_db()
    try:
        tc = TaskController(db)
        tid = tc.add_task(Task(title="Parent Task"))
        sid = db.insert_subtask(
            task_id=tid,
            title="Sub Multi-Day",
            planned_date="2026-08-13",
            due_date="2026-08-15",
            planned_start_time="07:00",
            planned_end_time="13:40",
            estimated_duration=3280,
        )
        subs = db.get_all_subtasks_flat(tid)
        sub_row = next(s for s in subs if s["id"] == sid)
        dur = duration_between(
            sub_row["planned_date"],
            sub_row["planned_start_time"],
            sub_row["due_date"],
            sub_row["planned_end_time"],
        )
        assert dur == 3280
        assert sub_row["estimated_duration"] == 3280
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_pd15_sub_subtask_parity():
    """PD15: Sub-subtask editing uses same multi-day duration authority."""
    db, path = _temp_db()
    try:
        tc = TaskController(db)
        tid = tc.add_task(Task(title="Parent Task"))
        sid = db.insert_subtask(task_id=tid, title="Sub 1")
        ssid = db.insert_subtask(
            task_id=tid,
            parent_subtask_id=sid,
            title="Sub-Sub Multi-Day",
            planned_date="2026-08-13",
            due_date="2026-08-15",
            planned_start_time="07:00",
            planned_end_time="13:40",
            estimated_duration=3280,
        )
        subs = db.get_all_subtasks_flat(tid)
        sub_row = next(s for s in subs if s["id"] == ssid)
        dur = duration_between(
            sub_row["planned_date"],
            sub_row["planned_start_time"],
            sub_row["due_date"],
            sub_row["planned_end_time"],
        )
        assert dur == 3280
        assert sub_row["estimated_duration"] == 3280
    finally:
        if os.path.exists(path):
            os.remove(path)
