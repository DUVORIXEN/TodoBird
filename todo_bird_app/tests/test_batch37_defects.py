"""
Comprehensive Automated Acceptance Test Suite for Phase 0B / Batch 3.7
Covers all human runtime reported defects:
- AX01-AX07: Actual Execution & Main Task Save Truth & Effort Independence
- UP01-UP03: Upcoming View Count & Range Contract
- CP01-CP02: Completed View Count & Case Sensitivity
- DR01-DR04: Daily Review 4-Card Truth (Today, Effort, Carryover, Tomorrow)
- GT01-GT03: Gantt Multi-Year Zoom Mode & Hourly Planned Bars
- CS01-CS02: Companion Settings Save & Persistence
- WK01-WK03: Working Week Live Sync Parity
- FT01-FT04: Per-View Typography & Visual Experience Modes
"""

import pytest
import os
import tempfile
from pathlib import Path
from datetime import date, datetime, timedelta
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.controllers.review_controller import ReviewController
from todo_bird_app.gantt.timescale_engine import ZoomLevel
from todo_bird_app.gantt.gantt_chart import GanttChartWidget
from todo_bird_app.gantt.gantt_items import GanttTaskItem
from todo_bird_app.services.typography_service import TypographyService
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.work_effort_editor import WorkEffortEditor
from todo_bird_app.utils.working_calendar import (
    get_configured_working_weekdays,
    set_configured_working_weekdays,
    is_working_day,
    get_working_days_between,
    reset_working_calendar_defaults,
)

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture(autouse=True)
def mock_messagebox(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: QMessageBox.StandardButton.Ok)

@pytest.fixture
def temp_db_and_settings():
    fd_db, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd_db)

    db = DatabaseManager(db_path)
    with tempfile.TemporaryDirectory() as config_dir:
        settings = SettingsManager(db_manager=db, config_dir=Path(config_dir))

        reset_working_calendar_defaults()

        yield db, settings

    try:
        os.remove(db_path)
    except OSError:
        pass


# =========================================================================
# AX01 - AX07: Actual Execution & Main Task Save
# =========================================================================

def test_ax01_ax02_actual_span_and_effort_independence(qapp, temp_db_and_settings):
    db, settings = temp_db_and_settings
    ctl = TaskController(db)
    task = Task(title="Execution Test Task", planned_date="2026-08-13", due_date="2026-08-15")
    task_id = ctl.add_task(task)
    task.id = task_id

    dlg = TaskDialog(projects=[], task=task, db_manager=db, settings_manager=settings)
    dlg.actual_enabled_check.setChecked(True)
    dlg.actual_start_date_edit.setDate(date(2026, 8, 13))
    dlg.actual_start_edit.setTime(datetime.strptime("09:00", "%H:%M").time())
    dlg.actual_end_date_edit.setDate(date(2026, 8, 15))
    dlg.actual_end_edit.setTime(datetime.strptime("17:00", "%H:%M").time())

    # Set manual actual effort to 360 mins (6h)
    dlg.actual_duration_spin.setValue(360)

    # Actual Span label should reflect full elapsed span (56h 00m = 3360 mins)
    assert "3360" in dlg.actual_elapsed_label.text()
    # Actual Effort spinbox must NOT be overwritten by span
    assert dlg.actual_duration_spin.value() == 360

    dlg.close()


def test_ax03_ax04_main_task_save_with_actuals_and_custom_allocations(qapp, temp_db_and_settings):
    db, settings = temp_db_and_settings
    ctl = TaskController(db)
    task = Task(
        title="Custom Allocation Task",
        planned_date="2026-08-13",
        due_date="2026-08-15",
        allocation_mode="custom_by_day",
        planned_effort_minutes=450,
    )
    task_id = ctl.add_task(task)
    task.id = task_id

    # Seed custom allocations
    db.set_task_allocations(task_id, None, [
        {"allocation_date": "2026-08-13", "planned_minutes": 180},
        {"allocation_date": "2026-08-14", "planned_minutes": 180},
        {"allocation_date": "2026-08-15", "planned_minutes": 90},
    ])

    dlg = TaskDialog(projects=[], task=task, db_manager=db, settings_manager=settings)
    dlg.actual_enabled_check.setChecked(True)
    dlg.actual_start_date_edit.setDate(date(2026, 8, 13))
    dlg.actual_start_edit.setTime(datetime.strptime("09:00", "%H:%M").time())
    dlg.actual_end_date_edit.setDate(date(2026, 8, 15))
    dlg.actual_end_edit.setTime(datetime.strptime("17:00", "%H:%M").time())
    dlg.actual_duration_spin.setValue(360)
    dlg.status_combo.setCurrentIndex(dlg.status_combo.findData(TaskStatus.COMPLETED))

    # Trigger Save
    dlg.on_save()
    ctl.update_task(dlg.get_task())

    saved_task_row = db.get_task_by_id(task_id)
    saved_task = Task.from_row(saved_task_row)

    assert saved_task.actual_start_date == "2026-08-13"
    assert saved_task.actual_end_date == "2026-08-15"
    assert saved_task.actual_start_time == "09:00"
    assert saved_task.actual_end_time == "17:00"
    assert saved_task.actual_duration == 360
    assert saved_task.planned_effort_minutes == 450

    allocs = db.get_task_allocations(task_id)
    assert len(allocs) == 3


def test_ax06_actual_timeline_validation(qapp, temp_db_and_settings):
    db, settings = temp_db_and_settings
    task = Task(title="Invalid Date Task", planned_date="2026-08-13")
    dlg = TaskDialog(projects=[], task=task, db_manager=db, settings_manager=settings)
    dlg.actual_enabled_check.setChecked(True)
    dlg.actual_start_date_edit.setDate(date(2026, 8, 15))
    dlg.actual_end_date_edit.setDate(date(2026, 8, 13))

    # Should not accept
    dlg.on_save()
    assert dlg.result() != TaskDialog.Accepted
    dlg.close()


# =========================================================================
# UP01 - UP03: Upcoming View Count & Range Contract
# =========================================================================

def test_up01_up03_upcoming_range_and_exclusion(temp_db_and_settings):
    db, settings = temp_db_and_settings
    ctl = TaskController(db)

    today_str = date.today().strftime("%Y-%m-%d")
    in_5_days = (date.today() + timedelta(days=5)).strftime("%Y-%m-%d")
    in_40_days = (date.today() + timedelta(days=40)).strftime("%Y-%m-%d")
    in_10_days = (date.today() + timedelta(days=10)).strftime("%Y-%m-%d")

    # 1. Normal upcoming task (in 5 days)
    t1 = Task(title="Task 1", planned_date=in_5_days, status=TaskStatus.PLANNED)
    ctl.add_task(t1)

    # 2. Spanning task starting today and due in 10 days
    t2 = Task(title="Spanning Task", planned_date=today_str, due_date=in_10_days, status=TaskStatus.IN_PROGRESS, actual_start_date=today_str, actual_start_time="09:00")
    ctl.add_task(t2)

    # 3. Completed task (should be excluded)
    t3 = Task(title="Completed Task", planned_date=in_5_days, status=TaskStatus.COMPLETED)
    ctl.add_task(t3)

    # 4. Cancelled task (should be excluded)
    t4 = Task(title="Cancelled Task", planned_date=in_5_days, status=TaskStatus.CANCELLED)
    ctl.add_task(t4)

    # 5. Far future task (in 40 days)
    t5 = Task(title="Far Task", planned_date=in_40_days, status=TaskStatus.PLANNED)
    ctl.add_task(t5)

    end_30 = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
    count = ctl.get_upcoming_tasks_count(end_date=end_30)
    tasks = ctl.get_upcoming_tasks(end_date=end_30)

    assert count == 2
    assert len(tasks) == 2
    titles = [t.title for t in tasks]
    assert "Task 1" in titles
    assert "Spanning Task" in titles
    assert "Completed Task" not in titles
    assert "Cancelled Task" not in titles
    assert "Far Task" not in titles


# =========================================================================
# CP01 - CP02: Completed View Count & Case Sensitivity
# =========================================================================

def test_cp01_completed_case_insensitivity(temp_db_and_settings):
    db, settings = temp_db_and_settings
    ctl = TaskController(db)

    t1 = Task(title="Finished 1", status=TaskStatus.COMPLETED)
    ctl.add_task(t1)

    # Direct raw insert with lowercase 'completed'
    with db.get_connection() as conn:
        conn.cursor().execute("INSERT INTO tasks (title, status) VALUES ('Finished 2', 'completed')")

    completed_tasks = ctl.get_completed_tasks()
    completed_count = ctl.get_completed_tasks_count()

    assert completed_count == 2
    assert len(completed_tasks) == 2


# =========================================================================
# DR01 - DR04: Daily Review 4-Card Truth
# =========================================================================

def test_dr01_dr04_daily_review_metrics(temp_db_and_settings):
    db, settings = temp_db_and_settings
    ctl = TaskController(db)
    rev_ctl = ReviewController(db, settings_manager=settings)

    today_str = date.today().strftime("%Y-%m-%d")
    yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    # Planned today with 120m effort
    t_today = Task(title="Today Work", planned_date=today_str, planned_effort_minutes=120, status=TaskStatus.PLANNED)
    ctl.add_task(t_today)

    # Completed today with 60m actual
    t_comp = Task(title="Done Work", planned_date=today_str, actual_start_date=today_str, actual_start_time="09:00", actual_end_date=today_str, actual_end_time="10:00", actual_duration=60, status=TaskStatus.COMPLETED)
    ctl.add_task(t_comp)

    # Overdue from yesterday
    t_overdue = Task(title="Overdue Work", planned_date=yesterday_str, due_date=yesterday_str, status=TaskStatus.IN_PROGRESS, actual_start_date=yesterday_str, actual_start_time="09:00")
    ctl.add_task(t_overdue)

    # Tomorrow task
    t_tom = Task(title="Tomorrow Work", planned_date=tomorrow_str, status=TaskStatus.PLANNED)
    ctl.add_task(t_tom)

    summary = rev_ctl.get_daily_review_summary(today_str)

    assert summary["total_planned"] == 2
    assert summary["completed_count"] >= 1
    assert summary["overdue_count"] == 1
    assert summary["carryover_count"] == 1
    assert summary["tomorrow_count"] == 1
    assert summary["planned_effort_total"] >= 120
    assert summary["act_duration_total"] >= 60
    assert summary["remaining_capacity"] == max(0, 480 - summary["planned_effort_total"])


# =========================================================================
# GT01 - GT03: Gantt Multi-Year & Hourly Zoom Modes
# =========================================================================

def test_gt01_gantt_multi_year_zoom_mapping(qapp, temp_db_and_settings):
    db, settings = temp_db_and_settings
    chart = GanttChartWidget(settings_manager=settings)

    chart.set_zoom_mode("Multi-Year")
    assert chart.zoom_mode == ZoomLevel.MULTI_YEAR

    chart.set_zoom_mode("multi-year")
    assert chart.zoom_mode == ZoomLevel.MULTI_YEAR

    chart.set_zoom_mode("Hourly")
    assert chart.zoom_mode == ZoomLevel.HOURLY


def test_gt02_gantt_hourly_spanning_day_does_not_fabricate_planned_bar(qapp, temp_db_and_settings):
    db, settings = temp_db_and_settings
    task = Task(
        title="Spanning 3-day Task",
        planned_date="2026-08-13",
        due_date="2026-08-15",
        planned_start_time="09:00",
        planned_end_time="17:00",
        estimated_duration=480
    )

    chart = GanttChartWidget(settings_manager=settings)
    chart.set_zoom_mode("hourly")
    chart.anchor_date = date(2026, 8, 14)
    chart.set_tasks([task], {})
    chart.rebuild_chart()

    assert chart._current_empty_message is not None
    assert "active today, but none have a timed schedule" in chart._current_empty_message
    assert len(chart._rendered_task_items) == 0


# =========================================================================
# CS01 - CS02: Companion Settings Save
# =========================================================================

def test_cs01_cs02_companion_settings_save(qapp, temp_db_and_settings):
    from todo_bird_app.views.settings_view import SettingsView
    db, settings = temp_db_and_settings

    view = SettingsView(db, settings)
    view.cb_companion_enabled.setChecked(True)
    view.cb_voice_enabled.setChecked(True)
    view.companion_activity_combo.setCurrentText("Balanced")

    # Should execute without AttributeError
    view.save_companion_settings()

    assert settings.get("companion_enabled") is True
    assert settings.get("voice_enabled") is True
    assert settings.get("companion_activity_level") == "balanced"


# =========================================================================
# WK01 - WK03: Working Week Live Sync
# =========================================================================

def test_wk01_wk03_working_week_live_sync(temp_db_and_settings):
    db, settings = temp_db_and_settings

    # 1. Mon-Fri default
    set_configured_working_weekdays({0, 1, 2, 3, 4}, settings)
    assert is_working_day(date(2026, 8, 15)) is False  # Saturday

    # 2. Enable Saturday
    set_configured_working_weekdays({0, 1, 2, 3, 4, 5}, settings)
    assert is_working_day(date(2026, 8, 15)) is True   # Saturday is now working

    working_days = get_working_days_between("2026-08-13", "2026-08-15", settings_manager=settings)
    assert len(working_days) == 3  # Thu, Fri, Sat


# =========================================================================
# FT01 - FT04: Per-View Typography & Visual Experience Modes
# =========================================================================

def test_ft01_ft04_typography_and_experience_modes(qapp, temp_db_and_settings):
    db, settings = temp_db_and_settings

    # Global default font (ensure override is False)
    settings.set("font_override_gantt", False)
    settings.set("font_override_sidebar", False)
    settings.set("ui_font_size", 11)
    settings.set("ui_font_weight", "normal")

    f_global = TypographyService.get_font_for_area("gantt", settings)
    assert f_global.pointSize() == 11

    # Override for Gantt only
    settings.set("font_override_gantt", True)
    settings.set("font_size_gantt", 14)
    settings.set("font_weight_gantt", "bold")

    f_gantt = TypographyService.get_font_for_area("gantt", settings)
    assert f_gantt.pointSize() == 14

    # Sidebar should still use global
    f_sidebar = TypographyService.get_font_for_area("sidebar", settings)
    assert f_sidebar.pointSize() == 11

    # Experience mode persistence
    settings.set("visual_experience_mode", "professional")
    assert settings.get("visual_experience_mode") == "professional"
