import pytest
import os
import shutil
import tempfile
from pathlib import Path
from datetime import date, datetime, timedelta

from PySide6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QComboBox, QListView, QFrame
from PySide6.QtCore import Qt, QDate, QRectF, QPointF
from PySide6.QtGui import QFont, QColor, QPainter, QPixmap

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.services.typography_service import TypographyService
from todo_bird_app.widgets.work_effort_editor import WorkEffortEditor
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.sidebar import SidebarWidget
from todo_bird_app.views.dashboard_view import DashboardView
from todo_bird_app.widgets.dashboard_charts import (
    AdvancedCapacityChart, AdvancedStatusChart, AdvancedWeeklyActivityChart
)
from todo_bird_app.views.daily_review_view import DailyReviewView
from todo_bird_app.views.calendar_view import CalendarView
from todo_bird_app.views.gantt_view import GanttView
from todo_bird_app.gantt.gantt_theme import GanttColorProfile, DEFAULT_GANTT_COLORS, LIGHT_GANTT_COLORS
from todo_bird_app.gantt.gantt_left_pane import GanttLeftPaneDelegate, GanttLeftPaneModel

@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app

@pytest.fixture
def temp_env():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_310c.db")
    db = DatabaseManager(db_path)
    settings = SettingsManager(db, config_dir=Path(temp_dir))
    yield db, settings, temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)

# ==============================================================================
# 1. EFFORT MODE VISIBILITY TESTS (F02 / F10 REGRESSION)
# ==============================================================================

def test_effort_mode_visibility_fixed_daily_hides_table(temp_env, qapp):
    db, settings, _ = temp_env
    editor = WorkEffortEditor(
        start_date="2026-08-13",
        due_date="2026-08-15",
        allocation_mode="fixed_daily",
        daily_dedication_minutes=120,
        settings_manager=settings
    )
    editor.show()
    # Fixed daily MUST hide custom alloc frame
    assert editor.custom_alloc_frame.isHidden()

def test_effort_mode_visibility_custom_by_day_shows_table(temp_env, qapp):
    db, settings, _ = temp_env
    editor = WorkEffortEditor(
        start_date="2026-08-13",
        due_date="2026-08-15",
        allocation_mode="custom_by_day",
        custom_allocations={"2026-08-13": 60, "2026-08-14": 120},
        settings_manager=settings
    )
    editor.show()
    # Custom by day MUST show custom alloc frame
    assert not editor.custom_alloc_frame.isHidden()

def test_effort_mode_visibility_total_effort_hides_table(temp_env, qapp):
    db, settings, _ = temp_env
    editor = WorkEffortEditor(
        start_date="2026-08-13",
        due_date="2026-08-15",
        allocation_mode="total_effort",
        planned_effort_minutes=300,
        settings_manager=settings
    )
    editor.show()
    # Total effort MUST hide custom alloc frame
    assert editor.custom_alloc_frame.isHidden()

def test_effort_mode_switching_live_visibility_toggle(temp_env, qapp):
    db, settings, _ = temp_env
    editor = WorkEffortEditor(
        start_date="2026-08-13",
        due_date="2026-08-15",
        allocation_mode="fixed_daily",
        settings_manager=settings
    )
    editor.show()
    assert editor.custom_alloc_frame.isHidden()

    # Switch to Custom by Day
    idx_custom = editor.allocation_mode_combo.findData("custom_by_day")
    editor.allocation_mode_combo.setCurrentIndex(idx_custom)
    assert not editor.custom_alloc_frame.isHidden()

    # Switch to Total Effort
    idx_total = editor.allocation_mode_combo.findData("total_effort")
    editor.allocation_mode_combo.setCurrentIndex(idx_total)
    assert editor.custom_alloc_frame.isHidden()

    # Switch back to Fixed Daily
    idx_fixed = editor.allocation_mode_combo.findData("fixed_daily")
    editor.allocation_mode_combo.setCurrentIndex(idx_fixed)
    assert editor.custom_alloc_frame.isHidden()

# ==============================================================================
# 2. TYPOGRAPHY AUTHORITY TESTS
# ==============================================================================

def test_typography_authority_sidebar_independence(temp_env, qapp):
    db, settings, _ = temp_env
    theme_ctl = ThemeController(settings)
    theme_ctl.apply_theme()

    # Configure global font
    settings.set("ui_font_family", "DejaVu Sans")
    settings.set("ui_font_size", 12)
    settings.set("ui_font_weight", "normal")

    # Configure sidebar override
    settings.set("font_override_sidebar", True)
    settings.set("font_family_sidebar", "Liberation Mono")
    settings.set("font_size_sidebar", 16)
    settings.set("font_weight_sidebar", "bold")

    sidebar = SidebarWidget(settings_manager=settings)
    resolved_font = TypographyService.get_font_for_area("sidebar", settings)

    assert resolved_font.family() == "Liberation Mono"
    assert resolved_font.pointSize() == 16
    assert resolved_font.bold()

    # Verify widget font matches resolved area font
    assert sidebar.font().family() == "Liberation Mono"

def test_typography_authority_daily_review_and_dashboard(temp_env, qapp):
    db, settings, _ = temp_env
    theme_ctl = ThemeController(settings)
    theme_ctl.apply_theme()

    settings.set("font_override_review", True)
    settings.set("font_family_review", "Courier")
    settings.set("font_size_review", 14)
    settings.set("font_weight_review", "bold")

    review_view = DailyReviewView(db, settings)
    resolved_review_font = TypographyService.get_font_for_area("review", settings)

    assert resolved_review_font.family() == "Courier"
    assert resolved_review_font.pointSize() == 14
    assert resolved_review_font.bold()
    assert review_view.font().family() == "Courier"

def test_typography_no_override_falls_back_to_global(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("ui_font_family", "DejaVu Sans")
    settings.set("ui_font_size", 13)
    settings.set("ui_font_weight", "semibold")
    settings.set("font_override_calendar", False)

    cal_font = TypographyService.get_font_for_area("calendar", settings)
    assert cal_font.family() == "DejaVu Sans"
    assert cal_font.pointSize() == 13
    assert cal_font.weight() == QFont.Weight.DemiBold

# ==============================================================================
# 3. GANTT DARK MODE & LEFT PANE THEME AUTHORITY TESTS
# ==============================================================================

def test_gantt_color_profile_tokens():
    from todo_bird_app.services.appearance_service import semantic_tokens_for

    profile = GanttColorProfile()
    dark_tokens = semantic_tokens_for(True, "#E11D48")
    light_tokens = semantic_tokens_for(False, "#E11D48")
    dark_colors = profile.get_effective_colors("dark", accent_color="#E11D48")
    light_colors = profile.get_effective_colors("light", accent_color="#E11D48")

    assert "panel_bg" in dark_colors
    assert "panel_header_bg" in dark_colors
    assert "panel_grid_color" in dark_colors
    assert "panel_text_color" in dark_colors

    assert dark_colors["panel_bg"] == dark_tokens["SURFACE_1"]
    assert light_colors["panel_bg"] == light_tokens["SURFACE_1"]
    assert dark_colors["panel_text_color"] == dark_tokens["TEXT_PRIMARY"]
    assert light_colors["panel_text_color"] == light_tokens["TEXT_PRIMARY"]
    assert dark_colors["planned_color"] == dark_tokens["ACCENT"]
    assert light_colors["planned_color"] == light_tokens["ACCENT"]

def test_gantt_view_startup_theme_awareness(temp_env, qapp):
    from todo_bird_app.services.appearance_service import semantic_tokens_for

    db, settings, _ = temp_env
    settings.set("theme", "light")
    g_view = GanttView(db, settings)

    # In light theme, left pane delegate must have light effective colors
    light_surface = semantic_tokens_for(False, "#2563EB")["SURFACE_1"]
    assert g_view.left_pane_delegate.color_profile["panel_bg"] == light_surface
    assert light_surface in g_view.left_pane_list.styleSheet()

def test_gantt_view_theme_toggle_updates_left_pane(temp_env, qapp):
    from todo_bird_app.services.appearance_service import semantic_tokens_for

    db, settings, _ = temp_env
    settings.set("theme", "dark")
    g_view = GanttView(db, settings)
    assert g_view.left_pane_delegate.color_profile["panel_bg"] == semantic_tokens_for(True, "#2563EB")["SURFACE_1"]

    # Switch theme to Light via theme handler
    g_view.on_gantt_theme_changed("Light")
    light_surface = GanttColorProfile(mode="light").get_effective_colors("light")["panel_bg"]
    assert g_view.left_pane_delegate.color_profile["panel_bg"] == light_surface
    assert light_surface in g_view.left_pane_list.styleSheet()

# ==============================================================================
# 4. DASHBOARD CHART PERSISTENCE & RENDERING TESTS
# ==============================================================================

def test_dashboard_chart_type_persistence_across_restart(temp_env, qapp):
    db, settings, temp_dir = temp_env

    # 1. Create initial dashboard view and change chart types
    dash1 = DashboardView(db, settings)
    dash1.capacity_chart_type.setCurrentText("Donut")
    dash1.status_chart_type.setCurrentText("Stacked Bar")
    dash1.weekly_chart_type.setCurrentText("Area")

    # Verify settings manager was updated
    assert settings.get("dashboard_capacity_chart_type") == "Donut"
    assert settings.get("dashboard_status_chart_type") == "Stacked Bar"
    assert settings.get("dashboard_week_chart_type") == "Area"

    # 2. Simulate App Restart: Create new settings manager and new DashboardView instance
    settings_restarted = SettingsManager(db, config_dir=Path(temp_dir))
    dash2 = DashboardView(db, settings_restarted)

    # 3. Assert chart types persisted and initialized widgets correctly
    assert dash2.capacity_chart_type.currentText() == "Donut"
    assert dash2.capacity_stacked_bar.chart_type == "Donut"

    assert dash2.status_chart_type.currentText() == "Stacked Bar"
    assert dash2.status_donut.chart_type == "Stacked Bar"

    assert dash2.weekly_chart_type.currentText() == "Area"
    assert dash2.weekly_chart.chart_type == "Area"

def test_weekly_chart_area_and_line_render_without_exception(qapp):
    chart = AdvancedWeeklyActivityChart()
    chart.resize(300, 100)
    chart.set_daily_data([
        ("Mon", 2, 4),
        ("Tue", 3, 3),
        ("Wed", 5, 2),
        ("Thu", 1, 4),
        ("Fri", 4, 4),
        ("Sat", 0, 0),
        ("Sun", 0, 0),
    ])

    pixmap = QPixmap(300, 100)

    # Test Bar mode
    chart.set_chart_type("Bar")
    chart.render(pixmap)

    # Test Line mode
    chart.set_chart_type("Line")
    chart.render(pixmap)

    # Test Area mode (previously crashed due to missing QPolygonF / QPainterPath bug)
    chart.set_chart_type("Area")
    chart.render(pixmap)

    assert not pixmap.isNull()
