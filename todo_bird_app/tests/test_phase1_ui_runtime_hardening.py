"""
Phase 1 UI Runtime Hardening Test Suite
Verifies:
1. SettingsView instantiates and tab count remains 7.
2. Dashboard settings tab is not blank and controls are created once.
3. _populate_dashboard_settings exists exactly once on SettingsView (and not GreetingEditDialog).
4. Dashboard settings reorder controls instantiate without NameError.
5. Dashboard clock timer starts correctly.
6. Dashboard cleanup stops the timer and clears widget references.
7. _update_clock_times_only() safely skips an invalid/deleted clock widget without RuntimeError.
8. No duplicate clock timer is created on repeated refresh.
9. CalendarView layout clearing runs cleanly via canonical clear_layout.
10. ProjectsView layout clearing runs cleanly via canonical clear_layout.
11. WorkEffortEditor custom table layout clearing runs cleanly via canonical clear_layout.
12. Clean shutdown lifecycle of MainWindow.
"""

from unittest.mock import MagicMock
import pytest
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QTabWidget,
    QListWidget,
    QPushButton,
    QVBoxLayout,
)
from PySide6.QtCore import Qt

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.views.settings_view import SettingsView, GreetingEditDialog
from todo_bird_app.views.dashboard_view import DashboardView
from todo_bird_app.views.calendar_view import CalendarView
from todo_bird_app.views.projects_view import ProjectsView
from todo_bird_app.widgets.work_effort_editor import WorkEffortEditor
from todo_bird_app.services.world_clock_service import WorldClockService


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_db():
    db = DatabaseManager(":memory:")
    return db


@pytest.fixture
def test_sm(test_db):
    sm = SettingsManager(test_db)
    return sm


def test_01_settings_view_instantiates_and_tab_count(qapp, test_db, test_sm):
    view = SettingsView(test_db, test_sm)
    qapp.processEvents()

    tabs = view.findChild(QTabWidget, "SettingsTabs")
    assert tabs is not None
    assert tabs.count() == 7
    tab_names = [tabs.tabText(i) for i in range(tabs.count())]
    assert "Dashboard" in tab_names
    assert tab_names[6] == "Dashboard"
    view.cleanup()


def test_02_settings_dashboard_tab_populated_not_blank(qapp, test_db, test_sm):
    view = SettingsView(test_db, test_sm)
    qapp.processEvents()

    assert hasattr(view, "clocks_list_widget")
    assert isinstance(view.clocks_list_widget, QListWidget)
    assert view.clocks_list_widget.count() > 0

    # Ensure Dashboard tab page has widgets
    dashboard_page = view.settings_tabs.widget(6)
    assert dashboard_page is not None
    assert len(dashboard_page.findChildren(QWidget)) > 0
    assert len(dashboard_page.findChildren(QPushButton)) >= 4  # Add, Del, Up, Down
    view.cleanup()


def test_03_populate_dashboard_settings_exists_exactly_once():
    # Must exist on SettingsView
    assert hasattr(SettingsView, "_populate_dashboard_settings")
    # Must NOT exist on GreetingEditDialog
    assert not hasattr(GreetingEditDialog, "_populate_dashboard_settings")


def test_04_dashboard_settings_reorder_controls_function_without_error(qapp, test_db, test_sm):
    view = SettingsView(test_db, test_sm)
    qapp.processEvents()

    initial_count = view.clocks_list_widget.count()
    assert initial_count > 1

    # Select second item and move up
    view.clocks_list_widget.setCurrentRow(1)
    view._on_clocks_reordered()
    qapp.processEvents()

    assert view.clocks_list_widget.count() == initial_count
    view.cleanup()


def test_05_dashboard_clock_timer_starts_correctly(qapp, test_db, test_sm):
    view = DashboardView(test_db, test_sm)
    qapp.processEvents()

    assert hasattr(view, "clock_timer")
    assert view.clock_timer is not None
    assert view.clock_timer.isActive()
    assert view.clock_timer.interval() in (1000, 60000)
    view.cleanup()


def test_06_dashboard_cleanup_stops_clock_timer_and_clears_widgets(qapp, test_db, test_sm):
    view = DashboardView(test_db, test_sm)
    qapp.processEvents()

    timer = view.clock_timer
    assert timer.isActive()

    view.cleanup()
    assert not timer.isActive()
    assert len(view._clock_widgets) == 0


def test_07_dashboard_clock_update_skips_invalid_or_deleted_widget(qapp, test_db, test_sm):
    view = DashboardView(test_db, test_sm)
    qapp.processEvents()

    class DeadClockWidget(QWidget):
        def update_time(self, info):
            raise RuntimeError("Internal C++ object (DigitalClockWidget) already deleted.")

    dead_widget = DeadClockWidget()
    view._clock_widgets.append((dead_widget, "Asia/Tokyo"))

    # Must NOT raise RuntimeError
    view._update_clock_times_only()

    # The dead widget should have been pruned from _clock_widgets
    assert dead_widget not in [w for w, _ in view._clock_widgets]
    view.cleanup()


def test_08_no_duplicate_clock_timer_created(qapp, test_db, test_sm):
    view = DashboardView(test_db, test_sm)
    qapp.processEvents()

    orig_timer = view.clock_timer
    view.refresh_data()
    view._rebuild_clock_strip()

    assert view.clock_timer is orig_timer
    view.cleanup()


def test_09_calendar_view_rebuilds_layout_cleanly(qapp, test_db, test_sm):
    view = CalendarView(test_db, test_sm)
    qapp.processEvents()

    # Trigger task list rebuild
    view.refresh_data()
    qapp.processEvents()

    assert view.task_list_layout is not None
    view.cleanup()


def test_10_projects_view_rebuilds_layout_cleanly(qapp, test_db, test_sm):
    view = ProjectsView(test_db, test_sm)
    qapp.processEvents()

    view.load_project_tasks()
    qapp.processEvents()

    assert view.task_list_layout is not None
    view.cleanup()


def test_11_work_effort_editor_rebuilds_custom_table_cleanly(qapp):
    editor = WorkEffortEditor(start_date="2026-09-01", due_date="2026-09-05")
    qapp.processEvents()

    editor.set_data(allocation_mode="custom")
    qapp.processEvents()

    # Rebuild custom table
    editor._rebuild_custom_table()
    qapp.processEvents()

    assert editor.custom_alloc_layout is not None
    editor.deleteLater()


def test_12_clean_shutdown(qapp, test_db, test_sm):
    from todo_bird_app.controllers.theme_controller import ThemeController
    from todo_bird_app.views.main_window import MainWindow

    tc = ThemeController(test_sm)
    mw = MainWindow(test_db, test_sm, tc)
    qapp.processEvents()

    mw.show()
    qapp.processEvents()

    # Close and verify clean shutdown
    mw.close()
    qapp.processEvents()
