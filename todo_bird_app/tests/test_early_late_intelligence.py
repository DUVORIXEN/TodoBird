import os
import tempfile
from datetime import date, datetime, time
import pytest

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.controllers.delay_engine import DelayEngine, TimingStatus
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.gantt.gantt_items import GanttTaskItem
from todo_bird_app.widgets.three_w_one_h_dialog import ThreeWOneHDialog
from todo_bird_app.views.focus_view import FocusView

_APP = QApplication.instance() or QApplication([])


def _temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(path)
    return db, path


def test_early_start_hourly_detection():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        engine = DelayEngine(settings)

        # Planned for 09:00, started early at 07:00 (120 min ahead)
        task = Task(
            title="Early Bird Milestone",
            planned_date="2026-08-20",
            planned_start_time="09:00",
            actual_start_time="07:00",
            status=TaskStatus.IN_PROGRESS,
        )

        status, diff_mins = engine.evaluate_start_timing(task)
        assert status == TimingStatus.EARLY_START
        assert diff_mins == 120
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_delayed_start_hourly_detection():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        engine = DelayEngine(settings)

        # Planned for 09:00, started late at 11:30 (150 min delayed)
        task = Task(
            title="Delayed Kickoff",
            planned_date="2026-08-20",
            planned_start_time="09:00",
            actual_start_time="11:30",
            status=TaskStatus.IN_PROGRESS,
        )

        status, diff_mins = engine.evaluate_start_timing(task)
        assert status == TimingStatus.DELAYED_START
        assert diff_mins == 150
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_on_time_tolerance():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        engine = DelayEngine(settings)

        # Planned for 09:00, started at 09:05 (within 15 min tolerance)
        task = Task(
            title="On Time Milestone",
            planned_date="2026-08-20",
            planned_start_time="09:00",
            actual_start_time="09:05",
            status=TaskStatus.IN_PROGRESS,
        )

        status, _ = engine.evaluate_start_timing(task)
        assert status == TimingStatus.ON_TRACK
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_gantt_item_renders_early_start_velocity():
    task = Task(
        title="Speedy Task",
        planned_date="2026-08-20",
        planned_start_time="09:00",
        actual_start_time="07:00",
        status=TaskStatus.IN_PROGRESS,
    )
    colors = {"actual_color": "#10B981"}
    item = GanttTaskItem(
        task=task,
        row=0,
        col_start=0.0,
        duration_cols=2.0,
        col_width=60,
        color_profile=colors,
        timing_status=TimingStatus.EARLY_START,
        zoom_mode="hourly",
    )
    assert item.timing_status == TimingStatus.EARLY_START
    assert "Early Start" in item.toolTip() or "Ahead of Schedule" in item.toolTip() or "Velocity" in item.toolTip()


def test_three_w_one_h_dialog_reflection_structure():
    task = Task(title="Slip Investigation", planned_date="2026-08-20")
    dlg = ThreeWOneHDialog(task, delay_minutes=60)
    dlg.txt_what.setText("Database lock during integration test")
    dlg.combo_why.setCurrentIndex(0)
    dlg.txt_how.setText("Refactor transaction isolation level")

    reflection = dlg.get_reflection_text()
    assert "3W1H Reflection" in reflection
    assert "Database lock" in reflection
    assert "External Blocker" in reflection or "Waiting on Dependency" in reflection
    assert "Refactor transaction" in reflection


def test_focus_view_displays_start_velocity_banners():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)

        # 1. Early task
        t_early = Task(
            title="Early Feature",
            planned_date=date.today().strftime("%Y-%m-%d"),
            planned_start_time="23:00",  # Later tonight, but start now
            actual_start_date=date.today().strftime("%Y-%m-%d"),
            actual_start_time="08:00",
            status=TaskStatus.IN_PROGRESS,
        )
        eid = tc.add_task(t_early)

        focus_view = FocusView(db, settings)
        focus_view.select_task_by_id(eid)

        assert not focus_view.lbl_velocity_banner.isHidden()
        assert "Early Start" in focus_view.lbl_velocity_banner.text()
    finally:
        if os.path.exists(path):
            os.remove(path)
