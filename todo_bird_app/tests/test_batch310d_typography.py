import pytest
import os
import shutil
import tempfile
from pathlib import Path
from datetime import date, datetime

from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from PySide6.QtGui import QFont

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.models.project import Project
from todo_bird_app.services.typography_service import TypographyService
from todo_bird_app.widgets.sidebar import SidebarWidget
from todo_bird_app.widgets.task_item_widget import TaskItemWidget
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.project_dialog import ProjectDialog
from todo_bird_app.widgets.three_w_one_h_dialog import ThreeWOneHDialog
from todo_bird_app.views.daily_review_view import DailyReviewView
from todo_bird_app.views.today_view import TodayView
from todo_bird_app.views.calendar_view import CalendarView

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
    db_path = os.path.join(temp_dir, "test_310d_typo.db")
    db = DatabaseManager(db_path)
    settings = SettingsManager(db, config_dir=Path(temp_dir))
    yield db, settings, temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)

# FONT-D01 Daily Review remains unchanged / reference pass
def test_font_d01_daily_review_reference_pass(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_review", True)
    settings.set("font_family_review", "Courier")
    settings.set("font_size_review", 14)
    settings.set("font_weight_review", "bold")

    view = DailyReviewView(db, settings)
    font = TypographyService.get_font_for_area("review", settings)

    assert font.family() == "Courier"
    assert font.pointSize() == 14
    assert font.bold()
    assert view.font().family() == "Courier"

# FONT-S01 Sidebar family changes
def test_font_s01_sidebar_family(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("sidebar_font_override", True)
    settings.set("sidebar_font_family", "Liberation Mono")

    sidebar = SidebarWidget(settings_manager=settings)
    resolved = TypographyService.get_font_for_area("sidebar", settings)
    assert resolved.family() == "Liberation Mono"
    assert sidebar.font().family() == "Liberation Mono"
    assert sidebar.item_widgets["dashboard"].text_label.font().family() == "Liberation Mono"

# FONT-S02 Sidebar size changes
def test_font_s02_sidebar_size(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_sidebar", True)
    settings.set("font_size_sidebar", 18)

    sidebar = SidebarWidget(settings_manager=settings)
    resolved = TypographyService.get_font_for_area("sidebar", settings)
    assert resolved.pointSize() == 18
    assert sidebar.font().pointSize() == 18
    assert sidebar.item_widgets["today"].text_label.font().pointSize() == 18

# FONT-S03 Sidebar works with global base unchanged
def test_font_s03_sidebar_independence_from_global(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("ui_font_family", "DejaVu Sans")
    settings.set("ui_font_size", 10)
    settings.set("font_override_sidebar", True)
    settings.set("font_family_sidebar", "Liberation Serif")
    settings.set("font_size_sidebar", 16)

    sidebar = SidebarWidget(settings_manager=settings)
    # Global unchanged
    assert TypographyService.get_font_for_area("review", settings).family() == "DejaVu Sans"
    # Sidebar overridden
    assert sidebar.font().family() == "Liberation Serif"
    assert sidebar.font().pointSize() == 16

# FONT-S04 Sidebar persists restart
def test_font_s04_sidebar_restart_persistence(temp_env, qapp):
    db, settings, temp_dir = temp_env
    settings.set("font_override_sidebar", True)
    settings.set("font_family_sidebar", "Courier")
    settings.set("font_size_sidebar", 15)

    # Restart
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    sidebar = SidebarWidget(settings_manager=restarted_settings)
    assert sidebar.font().family() == "Courier"
    assert sidebar.font().pointSize() == 15

# FONT-T01 Task-list family
def test_font_t01_task_list_family(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_tasklist", True)
    settings.set("font_family_tasklist", "Liberation Mono")

    t = Task(id=1, title="Sample Task", planned_date="2026-08-17")
    card = TaskItemWidget(t, settings_manager=settings)
    TypographyService.apply_to_widget(card, "tasklist", settings)

    assert card.font().family() == "Liberation Mono"
    assert card.title_label.font().family() == "Liberation Mono"

# FONT-T02 Task-list size
def test_font_t02_task_list_size(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_tasklist", True)
    settings.set("font_size_tasklist", 16)

    t = Task(id=1, title="Sample Task", planned_date="2026-08-17")
    card = TaskItemWidget(t, settings_manager=settings)
    TypographyService.apply_to_widget(card, "tasklist", settings)

    assert card.font().pointSize() == 16
    assert card.title_label.font().pointSize() == 16

# FONT-T03 Task-list persists
def test_font_t03_task_list_persists(temp_env, qapp):
    db, settings, temp_dir = temp_env
    settings.set("font_override_tasklist", True)
    settings.set("font_family_tasklist", "Liberation Serif")
    settings.set("font_size_tasklist", 14)

    restarted = SettingsManager(db, config_dir=Path(temp_dir))
    view = TodayView(db, restarted)
    assert view.font().family() == "Liberation Serif"
    assert view.font().pointSize() == 14

# FONT-C01 Calendar family
def test_font_c01_calendar_family(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_calendar", True)
    settings.set("font_family_calendar", "Liberation Mono")

    cal_view = CalendarView(db, settings)
    assert cal_view.font().family() == "Liberation Mono"
    assert cal_view.calendar.font().family() == "Liberation Mono"

# FONT-C02 Calendar size
def test_font_c02_calendar_size(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_calendar", True)
    settings.set("font_size_calendar", 15)

    cal_view = CalendarView(db, settings)
    assert cal_view.font().pointSize() == 15
    assert cal_view.calendar.font().pointSize() == 15

# FONT-C03 Calendar painted dates & table
def test_font_c03_calendar_table(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_calendar", True)
    settings.set("font_family_calendar", "Liberation Sans")
    settings.set("font_size_calendar", 13)

    cal_view = CalendarView(db, settings)
    from PySide6.QtWidgets import QTableView
    table = cal_view.calendar.findChild(QTableView)
    assert table is not None
    assert table.font().family() == "Liberation Sans"
    assert table.font().pointSize() == 13

# FONT-C04 Calendar task labels
def test_font_c04_calendar_task_labels(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_calendar", True)
    settings.set("font_family_calendar", "Courier")

    cal_view = CalendarView(db, settings)
    assert cal_view.date_title.font().family() == "Courier"
    assert cal_view.date_subtitle.font().family() == "Courier"

# FONT-C05 Calendar restart
def test_font_c05_calendar_restart(temp_env, qapp):
    db, settings, temp_dir = temp_env
    settings.set("font_override_calendar", True)
    settings.set("font_family_calendar", "Liberation Serif")
    settings.set("font_size_calendar", 16)

    restarted = SettingsManager(db, config_dir=Path(temp_dir))
    cal_view = CalendarView(db, restarted)
    assert cal_view.font().family() == "Liberation Serif"
    assert cal_view.font().pointSize() == 16

# FONT-F01 Dialog family
def test_font_f01_dialog_family(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_dialogs", True)
    settings.set("font_family_dialogs", "Liberation Mono")

    t = Task(title="Test Dialog")
    dlg = TaskDialog([], t, db_manager=db, settings_manager=settings)
    assert dlg.font().family() == "Liberation Mono"

# FONT-F02 Dialog size
def test_font_f02_dialog_size(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_dialogs", True)
    settings.set("font_size_dialogs", 16)

    t = Task(title="Test Dialog")
    dlg = TaskDialog([], t, db_manager=db, settings_manager=settings)
    assert dlg.font().pointSize() == 16

# FONT-F03 Subtask dialog
def test_font_f03_subtask_dialog(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_dialogs", True)
    settings.set("font_family_dialogs", "Liberation Sans")
    settings.set("font_size_dialogs", 14)

    t = Task(title="Main", id=1)
    dlg = TaskDialog([], t, db_manager=db, settings_manager=settings)
    resolved = TypographyService.get_font_for_area("dialogs", settings)
    assert resolved.family() == "Liberation Sans"
    assert resolved.pointSize() == 14

# FONT-F04 Project dialog
def test_font_f04_project_dialog(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_dialogs", True)
    settings.set("font_family_dialogs", "Courier")
    settings.set("font_size_dialogs", 15)

    proj = Project(name="Test Proj")
    dlg = ProjectDialog(proj, settings_manager=settings)
    assert dlg.font().family() == "Courier"
    assert dlg.font().pointSize() == 15

# FONT-F05 Dialog restart
def test_font_f05_dialog_restart(temp_env, qapp):
    db, settings, temp_dir = temp_env
    settings.set("font_override_dialogs", True)
    settings.set("font_family_dialogs", "Liberation Serif")
    settings.set("font_size_dialogs", 14)

    restarted = SettingsManager(db, config_dir=Path(temp_dir))
    t = Task(title="Restarted")
    dlg = TaskDialog([], t, db_manager=db, settings_manager=restarted)
    assert dlg.font().family() == "Liberation Serif"
    assert dlg.font().pointSize() == 14
