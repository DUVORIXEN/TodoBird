"""
Comprehensive Test Suite for Application Shutdown Lifecycle & Resource Cleanup
Validates deterministic clean exit, reentrancy safety, timer stoppage, companion cleanup,
WindowRegistry sweeping, and zero orphan Qt top-level windows.
"""

import gc
import pytest
from PySide6.QtWidgets import QApplication, QWidget, QDialog
from PySide6.QtCore import Qt

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import (
    TaskController,
    _GLOBAL_EVENT_BUS,
)
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.models.project import Project
from todo_bird_app.services.window_registry import WindowRegistry
from todo_bird_app.widgets.desktop_companion import DesktopCompanion
from todo_bird_app.widgets.pinned_tasks_window import PinnedTasksWindow
from todo_bird_app.widgets.reminder_dialog import ReminderDialog
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.project_dialog import ProjectDialog
from todo_bird_app.widgets.project_calendar_dialog import ProjectCalendarDialog
from todo_bird_app.widgets.justification_dialog import DelayJustificationDialog
from todo_bird_app.widgets.sidebar import SidebarWidget
from todo_bird_app.widgets.work_effort_editor import WorkEffortEditor
from todo_bird_app.views.main_window import MainWindow
from todo_bird_app.views.gantt_view import GanttView
from todo_bird_app.views.focus_view import FocusView
from todo_bird_app.views.settings_view import SettingsView


def _is_widget_alive_and_visible(w: QWidget) -> bool:
    try:
        return w.isWidgetType() and w.isVisible()
    except (RuntimeError, AttributeError):
        return False


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def temp_env(tmp_path):
    db_file = tmp_path / "test_shutdown_lifecycle.db"
    db = DatabaseManager(str(db_file))
    settings = SettingsManager(db)
    controller = TaskController(db)
    WindowRegistry.clear()
    yield db, settings, controller
    WindowRegistry.clear()


# ============================================================
# MANDATORY 20 SHUTDOWN LIFECYCLE TESTS
# ============================================================

def test_01_mainwindow_close_event_no_exceptions(temp_env, qapp):
    """TEST 01: Canonical MainWindow closeEvent executes without throwing exceptions."""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)
    main_win = MainWindow(db, settings, theme_ctrl)
    main_win.show()
    qapp.processEvents()

    # Trigger closeEvent
    assert main_win.close() is True
    qapp.processEvents()


def test_02_mainwindow_shutdown_in_progress_guard(temp_env, qapp):
    """TEST 02: MainWindow closeEvent sets _shutdown_in_progress reentrancy guard."""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)
    main_win = MainWindow(db, settings, theme_ctrl)
    main_win.show()

    assert not getattr(main_win, "_shutdown_in_progress", False)
    main_win.close()
    qapp.processEvents()
    assert getattr(main_win, "_shutdown_in_progress", False) is True


def test_03_mainwindow_close_event_reentrancy_safe(temp_env, qapp):
    """TEST 03: Calling MainWindow closeEvent a second time returns early (reentrancy safe)."""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)
    main_win = MainWindow(db, settings, theme_ctrl)
    main_win.show()

    main_win.close()
    qapp.processEvents()

    # Second call should return early without throwing error or duplicating cleanup
    res = main_win.close()
    assert res is True


def test_04_mainwindow_persists_geometry(temp_env, qapp):
    """TEST 04: MainWindow closeEvent persists geometry parameters."""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)
    main_win = MainWindow(db, settings, theme_ctrl)
    main_win.resize(1200, 800)
    main_win.move(100, 100)
    main_win.show()

    main_win.close()
    qapp.processEvents()

    assert settings.get("main_window_width") == 1200
    assert settings.get("main_window_height") == 800


def test_05_mainwindow_invokes_view_cleanup(temp_env, qapp):
    """TEST 05: MainWindow closeEvent invokes cleanup on view_stack_map views."""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)
    main_win = MainWindow(db, settings, theme_ctrl)
    main_win.show()

    cleaned_views = []
    # Mock a view with cleanup
    class MockView(QWidget):
        def cleanup(self):
            cleaned_views.append(self)

    mock_view = MockView()
    main_win.view_stack_map["mock_view"] = (0, mock_view)

    main_win.close()
    qapp.processEvents()

    assert mock_view in cleaned_views


def test_06_gantt_chart_widget_timer_stops(temp_env, qapp):
    """TEST 06: MainWindow closeEvent stops GanttChartWidget periodic update timer."""
    db, settings, controller = temp_env
    gantt_view = GanttView(controller)
    assert hasattr(gantt_view, "cleanup")
    assert gantt_view.gantt_chart.timer.isActive() is True

    gantt_view.cleanup()
    assert gantt_view.gantt_chart.timer.isActive() is False


def test_07_focus_view_timer_stops(temp_env, qapp):
    """TEST 07: MainWindow closeEvent stops FocusView periodic timer."""
    db, settings, controller = temp_env
    focus_view = FocusView(controller)
    assert hasattr(focus_view, "cleanup")
    assert focus_view.timer.isActive() is True

    focus_view.cleanup()
    assert focus_view.timer.isActive() is False


def test_08_reminder_poll_timer_stops(temp_env, qapp):
    """TEST 08: MainWindow closeEvent stops MainWindow _reminder_poll_timer."""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)
    main_win = MainWindow(db, settings, theme_ctrl)
    main_win.show()

    assert hasattr(main_win, "_reminder_poll_timer")
    assert main_win._reminder_poll_timer.isActive() is True

    main_win.close()
    qapp.processEvents()

    assert main_win._reminder_poll_timer.isActive() is False


def test_09_desktop_companion_cleaned_up(temp_env, qapp):
    """TEST 09: MainWindow closeEvent cleans up DesktopCompanion."""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)
    main_win = MainWindow(db, settings, theme_ctrl)
    main_win.show()

    companion = DesktopCompanion("Shutdown Companion Test")
    companion.show()
    main_win.desktop_companion = companion

    main_win.close()
    qapp.processEvents()
    qapp.processEvents()

    assert main_win.desktop_companion is None
    assert not _is_widget_alive_and_visible(companion)


def test_10_desktop_companion_cleanup_stops_animation(temp_env, qapp):
    """TEST 10: DesktopCompanion cleanup stops animation timer and marks _cleaning_up."""
    companion = DesktopCompanion("Test")
    companion.show()
    assert getattr(companion, "_cleaning_up", False) is False

    companion.cleanup()
    qapp.processEvents()

    assert getattr(companion, "_cleaning_up", False) is True
    assert companion.flight_timer.isActive() is False


def test_11_window_registry_tracking(temp_env, qapp):
    """TEST 11: WindowRegistry register/unregister tracks active windows correctly."""
    WindowRegistry.clear()
    w = QWidget()
    WindowRegistry.register(w)
    assert w in WindowRegistry.get_open_windows()

    WindowRegistry.unregister(w)
    assert w not in WindowRegistry.get_open_windows()


def test_12_window_registry_close_all_on_shutdown(temp_env, qapp):
    """TEST 12: WindowRegistry close_all_on_shutdown closes PinnedTasksWindow, DesktopCompanion, ReminderDialog."""
    db, settings, controller = temp_env
    pin_win = PinnedTasksWindow(db, settings)
    pin_win.show()

    t = Task(id=201, title="Test Registry Reminder")
    rem_dlg = ReminderDialog(t, settings_manager=settings)
    rem_dlg.show()

    companion = DesktopCompanion("Registry Companion")
    companion.show()

    qapp.processEvents()

    WindowRegistry.close_all_on_shutdown()
    qapp.processEvents()
    qapp.processEvents()

    assert len(WindowRegistry.get_open_windows()) == 0
    assert not _is_widget_alive_and_visible(pin_win)
    assert not _is_widget_alive_and_visible(rem_dlg)
    assert not _is_widget_alive_and_visible(companion)


def test_13_registered_dialogs_swept_on_shutdown(temp_env, qapp):
    """TEST 13: Top-level dialogs registered with WindowRegistry are swept and closed on shutdown."""
    db, settings, controller = temp_env
    projects = controller.get_all_projects()

    dlg1 = TaskDialog(projects, db_manager=db, settings_manager=settings)
    dlg1.show()

    dlg2 = ProjectDialog(settings_manager=settings)
    dlg2.show()

    qapp.processEvents()

    WindowRegistry.close_all_on_shutdown()
    qapp.processEvents()
    qapp.processEvents()

    assert not _is_widget_alive_and_visible(dlg1)
    assert not _is_widget_alive_and_visible(dlg2)


def test_14_unregistered_orphan_dialogs_swept(temp_env, qapp):
    """TEST 14: Unregistered orphan dialogs remaining in QApplication.topLevelWidgets() are swept and closed by close_all_on_shutdown."""
    orphan_dlg = QDialog()
    orphan_dlg.setWindowTitle("Unregistered Orphan Dialog")
    orphan_dlg.show()
    qapp.processEvents()

    assert orphan_dlg in QApplication.topLevelWidgets()

    WindowRegistry.close_all_on_shutdown()
    qapp.processEvents()
    qapp.processEvents()

    assert not _is_widget_alive_and_visible(orphan_dlg)


def test_15_task_dialog_clean_deletion(temp_env, qapp):
    """TEST 15: TaskDialog closeEvent / deleteLater removes window from topLevelWidgets without leaking."""
    db, settings, controller = temp_env
    projects = controller.get_all_projects()

    initial_top_levels = len(QApplication.topLevelWidgets())
    dlg = TaskDialog(projects, db_manager=db, settings_manager=settings)
    dlg.show()
    qapp.processEvents()

    dlg.reject()
    dlg.deleteLater()
    qapp.processEvents()
    qapp.processEvents()
    gc.collect()

    final_top_levels = len(QApplication.topLevelWidgets())
    assert final_top_levels <= initial_top_levels


def test_16_project_dialog_clean_deletion(temp_env, qapp):
    """TEST 16: ProjectDialog closeEvent / deleteLater removes window from topLevelWidgets without leaking."""
    db, settings, controller = temp_env

    initial_top_levels = len(QApplication.topLevelWidgets())
    dlg = ProjectDialog(settings_manager=settings)
    dlg.show()
    qapp.processEvents()

    dlg.reject()
    dlg.deleteLater()
    qapp.processEvents()
    qapp.processEvents()
    gc.collect()

    final_top_levels = len(QApplication.topLevelWidgets())
    assert final_top_levels <= initial_top_levels


def test_17_project_calendar_dialog_clean_deletion(temp_env, qapp):
    """TEST 17: ProjectCalendarDialog closeEvent / deleteLater removes window from topLevelWidgets without leaking."""
    db, settings, controller = temp_env

    initial_top_levels = len(QApplication.topLevelWidgets())
    dlg = ProjectCalendarDialog(db_manager=db)
    dlg.show()
    qapp.processEvents()

    dlg.reject()
    dlg.deleteLater()
    qapp.processEvents()
    qapp.processEvents()
    gc.collect()

    final_top_levels = len(QApplication.topLevelWidgets())
    assert final_top_levels <= initial_top_levels


def test_18_delay_justification_dialog_clean_deletion(temp_env, qapp):
    """TEST 18: DelayJustificationDialog closeEvent / deleteLater removes window from topLevelWidgets without leaking."""
    t = Task(id=301, title="Delayed Task Test", status=TaskStatus.DELAYED)
    initial_top_levels = len(QApplication.topLevelWidgets())

    dlg = DelayJustificationDialog(t)
    dlg.show()
    qapp.processEvents()

    dlg.reject()
    dlg.deleteLater()
    qapp.processEvents()
    qapp.processEvents()
    gc.collect()

    final_top_levels = len(QApplication.topLevelWidgets())
    assert final_top_levels <= initial_top_levels


def test_19_full_simulated_lifecycle_zero_orphan_windows(temp_env, qapp):
    """TEST 19: Full simulated lifecycle leaves ZERO orphan non-main windows in QApplication.topLevelWidgets()."""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)

    main_win = MainWindow(db, settings, theme_ctrl)
    main_win.show()

    companion = DesktopCompanion("Lifecycle Companion")
    companion.show()

    pin_win = PinnedTasksWindow.get_or_open(db, settings, parent=main_win)
    pin_win.show()

    projects = controller.get_all_projects()
    dlg = TaskDialog(projects, db_manager=db, settings_manager=settings)
    dlg.show()

    qapp.processEvents()

    # Close task dialog first
    dlg.reject()
    dlg.deleteLater()

    # Now close MainWindow
    main_win.close()
    qapp.processEvents()
    qapp.processEvents()
    gc.collect()

    # Filter topLevelWidgets to only visible top-level widgets
    remaining_visible_windows = [w for w in QApplication.topLevelWidgets() if w.isWindow() and w.isVisible()]
    assert len(remaining_visible_windows) == 0, f"Expected 0 visible orphan windows, found: {remaining_visible_windows}"


def test_20_full_simulated_lifecycle_no_active_timers(temp_env, qapp):
    """TEST 20: Full simulated lifecycle leaves no active application timers or running worker threads."""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)

    main_win = MainWindow(db, settings, theme_ctrl)
    main_win.show()

    # Verify timers are active initially
    assert main_win._reminder_poll_timer.isActive() is True
    assert main_win.gantt_view.gantt_chart.timer.isActive() is True
    assert main_win.focus_view.timer.isActive() is True

    # Close MainWindow
    main_win.close()
    qapp.processEvents()

    # Verify timers are stopped after shutdown
    assert main_win._reminder_poll_timer.isActive() is False
    assert main_win.gantt_view.gantt_chart.timer.isActive() is False
    assert main_win.focus_view.timer.isActive() is False


def test_21_widget_cleanup_disconnects_global_event_bus_slots(temp_env, qapp):
    """TEST 21: Closed widgets no longer receive global theme/calendar refresh signals."""
    db, settings, controller = temp_env

    class ProbeSidebar(SidebarWidget):
        def __init__(self, *args, **kwargs):
            self.typography_calls = 0
            super().__init__(*args, **kwargs)

        def _apply_typography(self):
            self.typography_calls += 1
            return super()._apply_typography()

    class ProbeFocusView(FocusView):
        def __init__(self, *args, **kwargs):
            self.typography_calls = 0
            super().__init__(*args, **kwargs)

        def apply_typography(self):
            self.typography_calls += 1
            return super().apply_typography()

    class ProbeWorkEffortEditor(WorkEffortEditor):
        def __init__(self, *args, **kwargs):
            self.calendar_calls = 0
            super().__init__(*args, **kwargs)

        def _on_global_working_calendar_changed(self):
            self.calendar_calls += 1
            return super()._on_global_working_calendar_changed()

    class ProbeGanttView(GanttView):
        def __init__(self, *args, **kwargs):
            self.toolbar_typography_calls = 0
            super().__init__(*args, **kwargs)

        def _sync_gantt_toolbar_typography_height(self):
            self.toolbar_typography_calls += 1
            return super()._sync_gantt_toolbar_typography_height()

    sidebar = ProbeSidebar(settings)
    focus_view = ProbeFocusView(controller)
    effort_editor = ProbeWorkEffortEditor(
        start_date="2026-09-15",
        due_date="2026-09-16",
        settings_manager=settings,
    )
    gantt_view = ProbeGanttView(controller)

    sidebar_typography_before = sidebar.typography_calls
    focus_typography_before = focus_view.typography_calls
    gantt_toolbar_before = gantt_view.toolbar_typography_calls
    calendar_before = effort_editor.calendar_calls

    _GLOBAL_EVENT_BUS.typography_changed.emit()
    _GLOBAL_EVENT_BUS.working_calendar_changed.emit()
    qapp.processEvents()

    assert sidebar.typography_calls == sidebar_typography_before + 1
    assert focus_view.typography_calls == focus_typography_before + 1
    assert gantt_view.toolbar_typography_calls == gantt_toolbar_before + 1
    assert effort_editor.calendar_calls == calendar_before + 1

    sidebar.cleanup()
    focus_view.cleanup()
    effort_editor.cleanup()
    gantt_view.cleanup()

    sidebar_typography_after = sidebar.typography_calls
    focus_typography_after = focus_view.typography_calls
    gantt_toolbar_after = gantt_view.toolbar_typography_calls
    calendar_after = effort_editor.calendar_calls

    _GLOBAL_EVENT_BUS.typography_changed.emit()
    _GLOBAL_EVENT_BUS.working_calendar_changed.emit()
    qapp.processEvents()

    assert sidebar.typography_calls == sidebar_typography_after
    assert focus_view.typography_calls == focus_typography_after
    assert gantt_view.toolbar_typography_calls == gantt_toolbar_after
    assert effort_editor.calendar_calls == calendar_after

    sidebar.deleteLater()
    focus_view.deleteLater()
    effort_editor.deleteLater()
    gantt_view.deleteLater()
    qapp.processEvents()


def test_22_cleanup_preserves_external_task_controller_global_bridge(temp_env, qapp):
    """TEST 22: Cleaning a view does not dismantle a TaskController it does not own."""
    db, settings, controller = temp_env
    observed = []
    controller.tasks_changed.connect(lambda: observed.append("changed"))

    _GLOBAL_EVENT_BUS.tasks_changed.emit()
    qapp.processEvents()
    assert observed == ["changed"]

    gantt_view = GanttView(controller)
    gantt_view.cleanup()
    observed.clear()

    _GLOBAL_EVENT_BUS.tasks_changed.emit()
    qapp.processEvents()

    assert observed == ["changed"]

    gantt_view.deleteLater()
    qapp.processEvents()


def test_23_settings_view_unregisters_reminder_resize_listener(temp_env, qapp):
    """TEST 23: SettingsView does not retain reminder resize callbacks after cleanup."""
    db, settings, controller = temp_env
    settings_view = SettingsView(db, settings)

    listener = getattr(settings_view, "_reminder_resize_listener", None)
    assert listener is not None
    assert listener in WindowRegistry._reminder_resize_listeners

    settings_view.cleanup()

    assert listener not in WindowRegistry._reminder_resize_listeners
    assert getattr(settings_view, "_reminder_resize_listener", None) is None

    settings_view.deleteLater()
    qapp.processEvents()
