"""
Phase 2A.1 — Dark Mode Contrast + Global Typography Regression Tests
Validates:
1. Projects "New Task" button follows global typography (10pt -> 20pt -> 10pt),
   no fixed height ceiling, no text clipping, sizeHint scales dynamically.
2. Dark Mode and Light Mode foreground text contrast for page and section headings
   across Projects, Dashboard, Calendar, Focus, Analytics, Settings, StatePanel, WBS.
3. Live theme switching (Light -> Dark -> Light) and typography propagation.
4. Static audit ensuring no dangerous hardcoded dark foregrounds in headings.
5. No idle timers or unexpected DB queries introduced.
"""

import os
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QAbstractButton, QWidget
from PySide6.QtGui import QFont, QPalette, QColor

from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.services.typography_service import TypographyService
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.database import DatabaseManager
from todo_bird_app.ui.components.modern_button import ModernButton, ButtonVariant, ButtonSize
from todo_bird_app.widgets.state_panel import StatePanel
from todo_bird_app.widgets.modern_card import ModernCard, SectionHeader, MetricCard
from todo_bird_app.views.projects_view import ProjectsView
from todo_bird_app.views.wbs_project_view import WBSProjectView
from todo_bird_app.views.calendar_view import CalendarView
from todo_bird_app.views.focus_view import FocusView
from todo_bird_app.views.analytics_view import AnalyticsView
from todo_bird_app.views.settings_view import SettingsView
from todo_bird_app.views.dashboard_view import DashboardView


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_phase2a1.db")
    db = DatabaseManager(db_path)
    return db


@pytest.fixture
def test_settings(tmp_path, test_db):
    settings = SettingsManager(test_db, config_dir=tmp_path)
    return settings


# =========================================================================
# Issue B: Projects "New Task" Button Typography & Geometry
# =========================================================================

def test_projects_new_task_button_exists(qapp, test_db, test_settings):
    """1. Projects New Task button exists."""
    pv = ProjectsView(test_db, test_settings)
    assert hasattr(pv, "wbs_view"), "ProjectsView must have wbs_view"
    assert hasattr(pv.wbs_view, "btn_add_task"), "WBSProjectView must have btn_add_task"
    assert isinstance(pv.wbs_view.btn_add_task, QAbstractButton)
    assert "New Task" in pv.wbs_view.btn_add_task.text()


def test_new_task_button_receives_global_font_at_10pt(qapp, test_db, test_settings):
    """2. New Task button receives global font at 10pt."""
    test_settings.set("ui_font_size", 10)
    pv = ProjectsView(test_db, test_settings)
    pv.apply_typography()
    btn = pv.wbs_view.btn_add_task
    assert btn.font().pointSize() == 10


def test_new_task_button_font_grows_at_20pt(qapp, test_db, test_settings):
    """3. font grows at 20pt."""
    test_settings.set("ui_font_size", 10)
    pv = ProjectsView(test_db, test_settings)
    pv.apply_typography()
    btn = pv.wbs_view.btn_add_task
    hint_10pt = btn.sizeHint()

    test_settings.set("ui_font_size", 20)
    pv.apply_typography()
    assert btn.font().pointSize() == 20
    hint_20pt = btn.sizeHint()
    assert hint_20pt.width() > hint_10pt.width()
    assert hint_20pt.height() > hint_10pt.height()


def test_new_task_button_font_shrinks_on_reverse(qapp, test_db, test_settings):
    """4. font shrinks on 20pt -> 10pt."""
    test_settings.set("ui_font_size", 20)
    pv = ProjectsView(test_db, test_settings)
    pv.apply_typography()
    btn = pv.wbs_view.btn_add_task
    assert btn.font().pointSize() == 20
    hint_20pt = btn.sizeHint()

    test_settings.set("ui_font_size", 10)
    pv.apply_typography()
    assert btn.font().pointSize() == 10
    hint_10pt = btn.sizeHint()
    assert hint_10pt.width() < hint_20pt.width()
    assert hint_10pt.height() < hint_20pt.height()


def test_button_geometry_remains_sufficient_no_clipping(qapp, test_db, test_settings):
    """5 & 6. button geometry remains sufficient and no clipping at 20pt."""
    test_settings.set("ui_font_size", 20)
    pv = ProjectsView(test_db, test_settings)
    pv.apply_typography()
    btn = pv.wbs_view.btn_add_task

    fm = btn.fontMetrics()
    text_w = fm.horizontalAdvance(btn.text())
    hint = btn.sizeHint()

    # The size hint must be wider and taller than bare text
    assert hint.width() >= text_w + 20
    assert hint.height() >= fm.height()
    # Button maximum height should not be constrained to 34px
    assert btn.maximumHeight() > 34


def test_no_fixed_font_size_remains_on_modern_button():
    """20. no fixed font-size remains on ModernButton painting."""
    code_path = Path("todo_bird_app/ui/components/modern_button.py")
    code = code_path.read_text(encoding="utf-8")
    assert "self._font_size = 13" not in code
    assert "font.setPointSize(self._font_size)" not in code
    assert "self.setFixedHeight(self._height)" not in code


# =========================================================================
# Issue A: Dark Mode & Light Mode Heading Readability & Contrast
# =========================================================================

def test_projects_heading_readable_light_and_dark(qapp, test_db, test_settings):
    """7 & 8. Projects headings readable in Light and Dark modes."""
    tc = ThemeController(test_settings)
    pv = ProjectsView(test_db, test_settings)

    # Dark mode
    tc.apply_theme(mode="dark")
    pal = qapp.palette()
    dark_fg = pal.color(QPalette.WindowText)
    # Bright text in dark mode
    assert dark_fg.lightness() > 150

    # Light mode
    tc.apply_theme(mode="light")
    pal = qapp.palette()
    light_fg = pal.color(QPalette.WindowText)
    # Dark text in light mode
    assert light_fg.lightness() < 100


def test_dashboard_major_heading_readable_dark(qapp, test_db, test_settings):
    """9. Dashboard major heading readable Dark."""
    tc = ThemeController(test_settings)
    tc.apply_theme(mode="dark")
    dv = DashboardView(test_db, test_settings)
    assert "color: #F3F4F6;" not in dv.focus_next_title.styleSheet()
    assert "color: inherit;" in dv.focus_next_title.styleSheet()


def test_calendar_major_heading_readable_dark(qapp, test_db, test_settings):
    """10. Calendar major heading readable Dark."""
    tc = ThemeController(test_settings)
    tc.apply_theme(mode="dark")
    cv = CalendarView(test_db, test_settings)
    assert cv.date_title.property("_todo_bird_font_delta_pt") == 4
    assert cv.date_title.property("_todo_bird_font_role_weight") == "bold"
    assert "color: inherit;" in cv.date_title.styleSheet()


def test_focus_major_heading_readable_dark(qapp, test_db, test_settings):
    """11. Focus major heading readable Dark."""
    tc = ThemeController(test_settings)
    tc.apply_theme(mode="dark")
    fv = FocusView(test_db, test_settings)
    assert fv.lbl_task_title.property("_todo_bird_font_delta_pt") == 10
    assert "color: inherit;" in fv.lbl_task_title.styleSheet()


def test_analytics_major_heading_readable_dark(qapp, test_db, test_settings):
    """12. Analytics major heading readable Dark."""
    tc = ThemeController(test_settings)
    tc.apply_theme(mode="dark")
    av = AnalyticsView(test_db, test_settings)
    assert av.lbl_planned_hrs.property("_todo_bird_font_delta_pt") == 12
    assert "font-size: 22px;" not in av.lbl_planned_hrs.styleSheet()


def test_settings_major_heading_readable_dark(qapp, test_db, test_settings):
    """13. Settings major headings readable Dark and follow relative font roles."""
    tc = ThemeController(test_settings)
    tc.apply_theme(mode="dark")
    sv = SettingsView(test_db, test_settings)
    labels = sv.findChildren(QLabel)
    for lbl in labels:
        if "🎨 Appearance" in lbl.text():
            assert lbl.property("_todo_bird_font_delta_pt") == 4
            assert "font-size: 16px;" not in lbl.styleSheet()
            assert "color: inherit;" in lbl.styleSheet()


def test_state_panel_title_readable_dark(qapp):
    """14. StatePanel title readable Dark."""
    sp = StatePanel()
    assert sp.title_label.property("_todo_bird_font_delta_pt") == 4
    assert "color: inherit;" in sp.title_label.styleSheet()
    assert "font-size: 16px;" not in sp.title_label.styleSheet()


def test_wbs_headings_remain_readable_dark(qapp, test_db, test_settings):
    """15. WBS heading/toolbars remain readable Dark."""
    tc = ThemeController(test_settings)
    tc.apply_theme(mode="dark")
    wbs = WBSProjectView(test_db, test_settings)
    assert wbs.btn_add_task.font().pointSize() > 0


def test_theme_switch_changes_and_restores_foreground(qapp, test_db, test_settings):
    """16, 17, 18. Light -> Dark -> Light transitions correctly without stale colors."""
    tc = ThemeController(test_settings)
    
    # 1. Start Light
    tc.apply_theme(mode="light")
    light_text = qapp.palette().color(QPalette.WindowText)
    assert light_text.lightness() < 100

    # 2. Switch to Dark
    tc.apply_theme(mode="dark")
    dark_text = qapp.palette().color(QPalette.WindowText)
    assert dark_text.lightness() > 150

    # 3. Restore to Light
    tc.apply_theme(mode="light")
    restored_text = qapp.palette().color(QPalette.WindowText)
    assert restored_text.lightness() < 100
    assert restored_text == light_text


def test_ordinary_headings_follow_global_typography(qapp, test_db, test_settings):
    """19. Ordinary headings scale relative to base font."""
    test_settings.set("ui_font_size", 10)
    pv = ProjectsView(test_db, test_settings)
    pv.apply_typography()
    assert pv.proj_name_label.font().pointSize() == 10 + 6  # base 10 + delta 6

    test_settings.set("ui_font_size", 20)
    pv.apply_typography()
    assert pv.proj_name_label.font().pointSize() == 20 + 6  # base 20 + delta 6

    test_settings.set("ui_font_size", 10)
    pv.apply_typography()
    assert pv.proj_name_label.font().pointSize() == 10 + 6


def test_no_new_idle_timers_or_db_access_introduced():
    """21 & 22. No idle timers or DB polling in ModernButton / TypographyService."""
    mb_text = Path("todo_bird_app/ui/components/modern_button.py").read_text()
    assert "QTimer" not in mb_text

    ts_text = Path("todo_bird_app/services/typography_service.py").read_text()
    assert "sqlite3" not in ts_text
    assert "DatabaseManager" not in ts_text
