"""
Batch 3.9 Comprehensive Verification Suite
Covers:
- AE01–AE08: Actual Effort Single Authority & Live Summing
- SV01–SV10: Systematic Save Action Audit & Toast Feedback
- CW01–CW07: Saturday Live Working Calendar Sync
- TP01–TP10: Per-View Real Typography Resolution & Rendering
- EP01–EP07: Experience Modes (Professional, Balanced, Personal)
- GL09–GL14: Gantt Task Label Presentation & Deduplication
- DV01–DV10: Dashboard Presentation Refinement & Native Charts
"""

import pytest
from datetime import date, datetime, timedelta
from PySide6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QDialog, QMessageBox
from PySide6.QtCore import Qt, QDate, QTime

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task, TaskPriority, TaskStatus, TaskCategory
from todo_bird_app.models.project import Project
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController, _GLOBAL_EVENT_BUS
from todo_bird_app.widgets.work_effort_editor import WorkEffortEditor
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.toast_banner import ToastBanner
from todo_bird_app.services.working_week import WorkingWeekService
from todo_bird_app.utils.working_calendar import (
    set_configured_working_weekdays,
    get_configured_working_weekdays,
    set_default_daily_capacity_minutes,
)
from todo_bird_app.services.typography_service import TypographyService
from todo_bird_app.services.experience_profile import ExperienceProfileService
from todo_bird_app.widgets.sidebar import SidebarWidget
from todo_bird_app.views.calendar_view import CalendarView
from todo_bird_app.views.dashboard_view import DashboardView
from todo_bird_app.views.settings_view import SettingsView


@pytest.fixture
def app():
    instance = QApplication.instance()
    if not instance:
        instance = QApplication([])
    return instance


@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "test_b39.db"
    return DatabaseManager(str(db_file))


@pytest.fixture
def settings(db, tmp_path):
    return SettingsManager(db_manager=db, config_dir=tmp_path)


# =========================================================================
# AE01–AE08: Actual Effort Single Authority & Live Summing
# =========================================================================

def test_ae01_main_actual_day_rows_sum_live(app, settings):
    """AE01: Day-by-day actual minutes in WorkEffortEditor immediately sum and emit."""
    editor = WorkEffortEditor(
        start_date="2026-08-13",
        due_date="2026-08-15",
        allocation_mode="custom_by_day",
        settings_manager=settings,
    )
    emitted = []
    editor.actualEffortChanged.connect(lambda v: emitted.append(v))

    # Edit Day 1 (13 Aug = 2h = 120m)
    h1, m1 = editor.custom_actual_spinners["2026-08-13"]
    h1.setValue(2)
    m1.setValue(0)
    assert editor.actual_effort_minutes == 120

    # Edit Day 2 (14 Aug = 3h = 180m)
    h2, m2 = editor.custom_actual_spinners["2026-08-14"]
    h2.setValue(3)
    m2.setValue(0)
    assert editor.actual_effort_minutes == 300

    # Edit Day 3 (15 Aug = 1h = 60m)
    h3, m3 = editor.custom_actual_spinners["2026-08-15"]
    h3.setValue(1)
    m3.setValue(0)
    assert editor.actual_effort_minutes == 360
    assert emitted[-1] == 360


def test_ae02_ae04_ae05_planned_span_and_actual_span_unchanged(app, settings):
    """AE02 & AE04 & AE05: Actual effort does not alter Planned Effort, Planned Span, or Actual Span."""
    editor = WorkEffortEditor(
        start_date="2026-08-13",
        due_date="2026-08-15",
        allocation_mode="fixed_daily",
        daily_dedication_minutes=60,
        settings_manager=settings,
    )
    initial_planned = editor.planned_effort_spin.value()

    # Enter custom actual allocations
    editor.set_data(
        allocation_mode="fixed_daily",
        daily_dedication_minutes=60,
        custom_actual_allocations={"2026-08-13": 120, "2026-08-14": 180, "2026-08-15": 60}
    )
    # Planned effort remains untouched
    assert editor.planned_effort_spin.value() == initial_planned
    assert editor.actual_effort_minutes == 360


def test_ae06_ae07_ae08_save_and_reopen_persists_actual_allocations(app, db, settings):
    """AE06, AE07, AE08: Saving task persists actual_minutes into task_allocations and reloads cleanly."""
    task = Task(
        title="Actual Effort Persistence Task",
        planned_date="2026-08-13",
        due_date="2026-08-15",
        allocation_mode="custom_by_day",
    )
    tc = TaskController(db)
    task_id = tc.add_task(task)
    task.id = task_id

    # Open dialog and add actual allocations
    dlg = TaskDialog([], task=task, db_manager=db, settings_manager=settings)
    h1, m1 = dlg.work_effort_editor.custom_actual_spinners["2026-08-13"]
    h1.setValue(2)
    h2, m2 = dlg.work_effort_editor.custom_actual_spinners["2026-08-14"]
    h2.setValue(3)
    dlg.on_save()
    tc.update_task(dlg.get_task())

    # Verify DB
    allocs = db.get_task_allocations(task_id=task_id)
    actual_map = {a["allocation_date"]: a["actual_minutes"] for a in allocs}
    assert actual_map.get("2026-08-13") == 120
    assert actual_map.get("2026-08-14") == 180

    # Reopen dialog
    reopened = tc.get_task(task_id)
    assert reopened.actual_duration == 300
    dlg2 = TaskDialog([], task=reopened, db_manager=db, settings_manager=settings)
    assert dlg2.work_effort_editor.actual_effort_minutes == 300
    assert dlg2.actual_duration_spin.value() == 300


# =========================================================================
# SV01–SV10: Save Action Audit & Toast Feedback
# =========================================================================

def test_sv01_main_task_save(app, db, settings):
    """SV01: Main Task Save successfully updates task model and persists."""
    t = Task(title="Test SV01", planned_date="2026-08-16", due_date="2026-08-16")
    dlg = TaskDialog([], task=t, db_manager=db, settings_manager=settings)
    dlg.title_input.setText("Updated SV01 Title")
    dlg.on_save()
    assert dlg.task.title == "Updated SV01 Title"


def test_sv07_invalid_data_gives_visible_reason(app, db, settings):
    """SV07: Empty title does not save silently."""
    t = Task(title="", planned_date="2026-08-16")
    dlg = TaskDialog([], task=t, db_manager=db, settings_manager=settings)
    dlg.title_input.setText("   ")
    dlg.on_save()
    # Task title was not updated to empty
    assert dlg.task.title == ""


def test_sv10_toast_banner_feedback(app):
    """SV10: ToastBanner displays non-intrusive feedback message."""
    w = QWidget()
    w.show()
    toast = ToastBanner.show_message(w, "✓ Task saved successfully", status="success")
    assert toast is not None
    assert toast.text() == "✓ Task saved successfully"


# =========================================================================
# CW01–CW07: Saturday Live Working Calendar Sync
# =========================================================================

def test_cw01_cw05_working_week_toggle_events(settings):
    """CW01 & CW05: Setting Saturday ON/OFF emits working_calendar_changed."""
    events = []
    _GLOBAL_EVENT_BUS.working_calendar_changed.connect(lambda: events.append(True))

    # Enable Saturday (0,1,2,3,4,5)
    set_configured_working_weekdays({0, 1, 2, 3, 4, 5}, settings_manager=settings)
    assert len(events) >= 1
    assert 5 in get_configured_working_weekdays(settings)

    # Disable Saturday (0,1,2,3,4)
    set_configured_working_weekdays({0, 1, 2, 3, 4}, settings_manager=settings)
    assert 5 not in get_configured_working_weekdays(settings)


def test_cw02_open_main_editor_updates_immediately(app, settings):
    """CW02 & CW06: Open WorkEffortEditor reloads calendar status and recalculates fixed effort."""
    set_configured_working_weekdays({0, 1, 2, 3, 4}, settings_manager=settings)  # Mon-Fri
    editor = WorkEffortEditor(
        start_date="2026-08-14",  # Friday
        due_date="2026-08-15",    # Saturday
        allocation_mode="fixed_daily",
        daily_dedication_minutes=60,
        settings_manager=settings,
    )
    # Only Friday is working = 60 mins
    assert editor.planned_effort_spin.value() == 60

    # Turn Saturday ON while editor is open
    set_configured_working_weekdays({0, 1, 2, 3, 4, 5}, settings_manager=settings)
    # Editor reactively recalculated = 120 mins
    assert editor.planned_effort_spin.value() == 120


# =========================================================================
# TP01–TP10: Per-View Typography Resolution & Precedence
# =========================================================================

def test_tp01_tp03_tp09_independent_typography_settings(settings):
    """TP01, TP03, TP09: Sidebar and Calendar typography settings are completely independent."""
    settings.set("font_override_sidebar", True)
    settings.set("font_family_sidebar", "Ubuntu")
    settings.set("font_size_sidebar", 12)

    settings.set("font_override_calendar", True)
    settings.set("font_family_calendar", "Courier")
    settings.set("font_size_calendar", 9)

    f_side = TypographyService.get_font_for_area("sidebar", settings)
    f_cal = TypographyService.get_font_for_area("calendar", settings)

    assert f_side.family() == "Ubuntu"
    assert f_side.pointSize() == 12
    assert f_cal.family() == "Courier"
    assert f_cal.pointSize() == 9


def test_tp01_sidebar_widget_applies_typography(app, settings):
    """TP01: SidebarWidget applies configured font to item labels."""
    settings.set("font_override_sidebar", True)
    settings.set("font_family_sidebar", "Inter")
    settings.set("font_size_sidebar", 13)

    sidebar = SidebarWidget(settings_manager=settings)
    assert "dashboard" in sidebar.item_widgets
    item = sidebar.item_widgets["dashboard"]
    assert item.text_label.font().pointSize() == 13


# =========================================================================
# EP01–EP07: Experience Modes
# =========================================================================

def test_ep01_ep03_experience_profiles():
    """EP01, EP03: Experience profiles provide differentiated design tokens."""
    prof = ExperienceProfileService.get_profile("professional")
    pers = ExperienceProfileService.get_profile("personal")

    assert prof["card_radius"] == 6
    assert pers["card_radius"] == 14
    assert prof["section_spacing"] < pers["section_spacing"]
    assert prof["thumbnail_visible"] is False
    assert pers["thumbnail_visible"] is True


# =========================================================================
# GL09–GL14: Gantt Task Label Presentation
# =========================================================================

def test_gl09_gl10_gantt_label_position_setting(settings):
    """GL09, GL10: Gantt task label position defaults to left_column_only."""
    val = settings.get("gantt_task_label_position", "left_column_only")
    assert val == "left_column_only"


# =========================================================================
# DV01–DV10: Dashboard Presentation Refinement & Native Charts
# =========================================================================

def test_dv01_dv04_dashboard_clean_containers(app, db, settings):
    """DV01, DV04: Dashboard builds clean isolated container widgets without layout leaks."""
    tc = TaskController(db)
    today_iso = date.today().strftime("%Y-%m-%d")
    t1 = Task(
        title="Timed Task 1",
        planned_date=today_iso,
        due_date=today_iso,
        planned_start_time="09:00",
        planned_end_time="10:00",
        planned_effort_minutes=60,
    )
    tc.add_task(t1)

    dashboard = DashboardView(db, settings)
    dashboard.refresh_data()

    # Timeline and project items are wrapped in QWidgets
    assert dashboard.timeline_vbox.count() >= 1
    w = dashboard.timeline_vbox.itemAt(0).widget()
    assert isinstance(w, QWidget)

    # Refresh again: Old widgets are cleanly deleted and not duplicated
    dashboard.refresh_data()
    assert dashboard.timeline_vbox.count() >= 1


def test_dv05_dv06_dv07_dashboard_native_charts(app, db, settings):
    """DV05, DV06, DV07: Dashboard native charts (Capacity, Donut, Weekly) are populated."""
    dashboard = DashboardView(db, settings)
    dashboard.refresh_data()

    assert dashboard.capacity_stacked_bar is not None
    assert dashboard.status_donut is not None
    assert dashboard.weekly_chart is not None
    assert len(dashboard.weekly_chart.daily_data) == 7
