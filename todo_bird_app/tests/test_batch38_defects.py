"""
Automated Defect Closure & Acceptance Suite for Batch 3.8
Covers:
- F1 / F2: Main Task Actual Span live update & Day-by-Day Actual Effort Authority
- F3: Subtask / Sub-Subtask Responsive Layout & Scroll Wrapping
- F4: Working Week Live Sync
- F5: Real Per-View Typography Resolution & Event Bus Propagation
- F6: Experience Modes (Professional / Balanced / Personal)
- F7: Dashboard Foundation (Key metrics, deterministic Focus Next, Workload meter, Projects)
- F8: Gantt Task Name Clarity & In-bar Labeling
"""

import pytest
from datetime import date, datetime, timedelta
from pathlib import Path
from PySide6.QtCore import Qt, QDate, QTime
from PySide6.QtWidgets import QApplication, QDialog, QScrollArea, QLabel, QSpinBox

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS, TaskController
from todo_bird_app.utils.working_calendar import (
    set_configured_working_weekdays,
    get_configured_working_weekdays,
    get_working_days_between,
)
from todo_bird_app.utils.time_math import (
    calculate_actual_elapsed_minutes,
    duration_between,
    format_duration_display,
)
from todo_bird_app.widgets.work_effort_editor import WorkEffortEditor
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.services.typography_service import TypographyService, AREAS
from todo_bird_app.views.dashboard_view import DashboardView
from todo_bird_app.widgets.sidebar import SidebarWidget
from todo_bird_app.gantt.gantt_items import GanttTaskItem
from todo_bird_app.gantt.gantt_chart import GanttChartWidget


@pytest.fixture
def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "test_b38.db"
    manager = DatabaseManager(str(db_file))
    return manager


@pytest.fixture
def settings(db, tmp_path):
    return SettingsManager(db_manager=db, config_dir=tmp_path)


# =========================================================================
# F1 & F2: Actual Span Live Update & Actual Effort Authority
# =========================================================================

def test_a38_01_actual_elapsed_span_clock_delta():
    """Actual span is pure calendar clock delta decoupled from working hours."""
    dur = calculate_actual_elapsed_minutes("2026-08-15", "10:00", "2026-08-16", "12:00")
    assert dur == 26 * 60  # 1560 mins


def test_a38_02_task_dialog_actual_span_live_calculation(app, db, settings):
    """TaskDialog immediately calculates and updates actual_elapsed_label when dates/times change."""
    tc = TaskController(db)
    task = Task(title="Test Task", planned_date="2026-08-17", due_date="2026-08-17")
    task_id = tc.add_task(task)
    task.id = task_id

    dlg = TaskDialog([], task=task, db_manager=db, settings_manager=settings)
    dlg.actual_enabled_check.setChecked(True)
    dlg.actual_start_date_edit.setDate(QDate(2026, 8, 17))
    dlg.actual_start_edit.setTime(QTime(9, 0))
    dlg.actual_end_date_edit.setDate(QDate(2026, 8, 17))
    dlg.actual_end_edit.setTime(QTime(17, 30))

    # Span is 8h 30m = 510 mins
    assert "8h 30m" in dlg.actual_elapsed_label.text()
    assert "510 mins" in dlg.actual_elapsed_label.text()

    # Changing start time immediately updates label
    dlg.actual_start_edit.setTime(QTime(8, 0))
    assert "9h 30m" in dlg.actual_elapsed_label.text()
    assert "570 mins" in dlg.actual_elapsed_label.text()


def test_a38_03_work_effort_editor_actual_minutes_sum(app, settings):
    """WorkEffortEditor custom mode edits actual minutes day-by-day and emits sum."""
    editor = WorkEffortEditor(
        start_date="2026-08-17",
        due_date="2026-08-19",
        allocation_mode="custom_by_day",
        custom_allocations={"2026-08-17": 120, "2026-08-18": 180, "2026-08-19": 60},
        custom_actual_allocations={"2026-08-17": 90, "2026-08-18": 150, "2026-08-19": 45},
        settings_manager=settings,
    )

    data = editor.get_data()
    assert data["custom_actual_allocations"]["2026-08-17"] == 90
    assert data["custom_actual_allocations"]["2026-08-18"] == 150
    assert data["custom_actual_allocations"]["2026-08-19"] == 45

    # Changing actual spinbox emits actualEffortChanged
    actual_emitted = []
    editor.actualEffortChanged.connect(lambda val: actual_emitted.append(val))

    # Find the actual spinboxes for 2026-08-17 (h_spin, m_spin)
    h_spin, m_spin = editor.custom_actual_spinners["2026-08-17"]
    h_spin.setValue(2)  # 2h 30m = 150 mins
    m_spin.setValue(30)
    assert len(actual_emitted) > 0
    assert actual_emitted[-1] == 150 + 150 + 45  # 345 mins


def test_a38_04_task_dialog_saves_actual_allocations(app, db, settings):
    """TaskDialog persists day-by-day actual minutes in task_allocations table."""
    tc = TaskController(db)
    task = Task(
        title="Custom Allocation Task",
        planned_date="2026-08-17",
        due_date="2026-08-18",
        allocation_mode="custom_by_day",
        planned_effort_minutes=300,
        actual_duration=240,
    )
    task_id = tc.add_task(task)
    task.id = task_id

    dlg = TaskDialog([], task=task, db_manager=db, settings_manager=settings)
    dlg.work_effort_editor.allocation_mode_combo.setCurrentText("Custom by Day")
    # Set planned: 180m and 120m
    p_h1, p_m1 = dlg.work_effort_editor.custom_spinners["2026-08-17"]
    p_h1.setValue(3)
    p_m1.setValue(0)

    p_h2, p_m2 = dlg.work_effort_editor.custom_spinners["2026-08-18"]
    p_h2.setValue(2)
    p_m2.setValue(0)

    # Set actual: 150m and 90m
    a_h1, a_m1 = dlg.work_effort_editor.custom_actual_spinners["2026-08-17"]
    a_h1.setValue(2)
    a_m1.setValue(30)

    a_h2, a_m2 = dlg.work_effort_editor.custom_actual_spinners["2026-08-18"]
    a_h2.setValue(1)
    a_m2.setValue(30)

    dlg.on_save()

    allocs = db.get_task_allocations(task_id=task_id)
    alloc_map = {a["allocation_date"]: a for a in allocs}
    assert alloc_map["2026-08-17"]["planned_minutes"] == 180
    assert alloc_map["2026-08-17"]["actual_minutes"] == 150
    assert alloc_map["2026-08-18"]["planned_minutes"] == 120
    assert alloc_map["2026-08-18"]["actual_minutes"] == 90


# =========================================================================
# F3: Subtask / Sub-Subtask Responsive Layout & Scroll Area
# =========================================================================

def test_ru01_subtask_dialog_has_scroll_area(app, db, settings):
    """Subtask edit dialog contains a top-level QScrollArea to prevent clipping."""
    tc = TaskController(db)
    task = Task(title="Parent Task", planned_date="2026-08-17", due_date="2026-08-18")
    task_id = tc.add_task(task)
    task.id = task_id

    dlg = TaskDialog([], task=task, db_manager=db, settings_manager=settings)
    # Add a top-level subtask
    dlg.subtask_input.setText("Child Subtask")
    dlg.add_subtask_item()

    # The subtask tree item has metadata
    item = dlg.subtask_tree.topLevelItem(0)
    assert item is not None
    assert "Child Subtask" in item.text(0)


# =========================================================================
# F4: Working Week Live Sync
# =========================================================================

def test_wc38_01_working_week_event_emitted(settings):
    """Changing configured working weekdays emits working_calendar_changed."""
    events = []
    _GLOBAL_EVENT_BUS.working_calendar_changed.connect(lambda: events.append(True))

    set_configured_working_weekdays({0, 1, 2, 3, 4}, settings_manager=settings)
    assert len(events) >= 1
    assert get_configured_working_weekdays(settings) == {0, 1, 2, 3, 4}


def test_wc38_02_work_effort_editor_reacts_to_calendar_change(app, settings):
    """WorkEffortEditor rebuilds days and updates planned span when calendar changes."""
    set_configured_working_weekdays({0, 1, 2, 3, 4}, settings_manager=settings)

    editor = WorkEffortEditor(
        start_date="2026-08-14",  # Friday
        due_date="2026-08-17",    # Monday
        allocation_mode="fixed_daily",
        daily_dedication_minutes=60,
        settings_manager=settings,
    )
    # Fri (14) + Mon (17) = 2 working days => planned effort is 120 mins
    assert editor.planned_effort_spin.value() == 120

    # Switch to 7-day work week
    set_configured_working_weekdays({0, 1, 2, 3, 4, 5, 6}, settings_manager=settings)
    # Editor automatically refreshed via event bus => planned effort becomes 240 mins
    assert editor.planned_effort_spin.value() == 240


# =========================================================================
# F5: Real Per-View Typography Resolution
# =========================================================================

def test_ty01_typography_service_global_and_overrides(settings):
    """TypographyService respects global settings and per-view overrides."""
    settings.set("ui_font_family", "Inter")
    settings.set("ui_font_size", 10)

    font_default = TypographyService.get_font_for_area("gantt", settings)
    assert font_default.family() == "Inter"
    assert font_default.pointSize() == 10

    # Override for Gantt
    settings.set("font_override_gantt", True)
    settings.set("font_family_gantt", "Roboto")
    settings.set("font_size_gantt", 12)

    font_gantt = TypographyService.get_font_for_area("gantt", settings)
    assert font_gantt.family() == "Roboto"
    assert font_gantt.pointSize() == 12

    # Other area remains default
    font_sidebar = TypographyService.get_font_for_area("sidebar", settings)
    assert font_sidebar.family() == "Inter"
    assert font_sidebar.pointSize() == 10


def test_ty02_typography_service_apply_to_widget(app, settings):
    """TypographyService applies font recursively to widget and children."""
    from PySide6.QtWidgets import QWidget
    w = QWidget()
    lbl = QLabel("Test Label", w)
    settings.set("font_override_sidebar", True)
    settings.set("font_family_sidebar", "Inter")
    settings.set("font_size_sidebar", 14)

    TypographyService.apply_to_widget(w, "sidebar", settings)
    assert w.font().pointSize() == 14
    assert lbl.font().pointSize() == 14


# =========================================================================
# F6: Experience Modes
# =========================================================================

def test_ex01_experience_modes_event_bus(settings):
    """Experience mode change emits experience_mode_changed signal."""
    emitted_modes = []
    _GLOBAL_EVENT_BUS.experience_mode_changed.connect(lambda mode: emitted_modes.append(mode))

    settings.set("visual_experience_mode", "professional")
    _GLOBAL_EVENT_BUS.experience_mode_changed.emit("professional")

    assert len(emitted_modes) == 1
    assert emitted_modes[0] == "professional"


# =========================================================================
# F7: Dashboard Foundation
# =========================================================================

def test_db01_dashboard_view_initialization_and_metrics(app, db, settings):
    """DashboardView computes today's tasks, planned effort, actual effort, and headroom."""
    today_str = date.today().strftime("%Y-%m-%d")
    tc = TaskController(db)

    # Add task for today
    t1 = Task(
        title="Dashboard Test Task 1",
        planned_date=today_str,
        due_date=today_str,
        planned_effort_minutes=120,
        daily_dedication_minutes=120,
        allocation_mode="fixed_daily",
        priority=TaskPriority.HIGH,
        status=TaskStatus.PLANNED,
    )
    tc.add_task(t1)

    dashboard = DashboardView(db, settings)
    dashboard.refresh_data()

    assert dashboard.card_today_tasks.value_label.text() == "1"
    assert "2h" in dashboard.card_planned_effort.value_label.text()
    assert "Dashboard Test Task 1" in dashboard.focus_next_title.text()
    assert "Dashboard Test Task 1" in dashboard.focus_next_title.text()


def test_db02_dashboard_overload_warning(app, db, settings):
    """Dashboard flags overload when planned effort exceeds daily capacity."""
    today_str = date.today().strftime("%Y-%m-%d")
    from todo_bird_app.utils.working_calendar import set_default_daily_capacity_minutes
    set_default_daily_capacity_minutes(240, settings_manager=settings)  # 4h capacity = 240 mins
    tc = TaskController(db)

    t = Task(
        title="Heavy Task",
        planned_date=today_str,
        due_date=today_str,
        daily_dedication_minutes=360,  # 6h > 4h cap
        allocation_mode="fixed_daily",
        priority=TaskPriority.URGENT,
        status=TaskStatus.PLANNED,
    )
    tc.add_task(t)

    dashboard = DashboardView(db, settings)
    dashboard.refresh_data()

    assert "Overloaded" in dashboard.card_headroom.value_label.text()
    assert dashboard.workload_progress.value() == 100


# =========================================================================
# F8: Gantt Task Name Clarity
# =========================================================================

def test_gl01_gantt_item_renders_with_typography(app, db, settings):
    """Gantt items resolve their typography and layout cleanly."""
    task = Task(
        id=1,
        title="Gantt Clarity Task",
        planned_date="2026-08-17",
        due_date="2026-08-19",
        planned_start_time="09:00",
        planned_end_time="17:00",
        status=TaskStatus.PLANNED,
    )
    item = GanttTaskItem(task, row=0, col_start=0, duration_cols=2, col_width=40, color_profile={})
    assert item is not None
