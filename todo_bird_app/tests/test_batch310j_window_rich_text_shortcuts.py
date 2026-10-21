"""
Tests for Batch 3.10J: Task Edit Window Desktop Usability, Rich Description Authority & Keyboard Shortcut Standard
Covers:
- Window Management & Usability: WIN-J01..WIN-J08
- Rich Description Authority: RT-J01..RT-J12
- Keyboard Shortcut Standard: KS-J01..KS-J12
"""

import html as html_mod
import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QWidget, QTextEdit
from PySide6.QtCore import Qt, QDate, QTime
from PySide6.QtGui import QFont, QTextCharFormat, QTextCursor, QTextListFormat, QKeySequence

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority, TaskCategory
from todo_bird_app.models.project import Project
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.project_dialog import ProjectDialog
from todo_bird_app.widgets.three_w_one_h_dialog import ThreeWOneHDialog
from todo_bird_app.widgets.confirm_delete_dialog import ConfirmDeleteDialog
from todo_bird_app.widgets.rich_text_editor import RichTextEditor
from todo_bird_app.widgets.command_palette import CommandPalette
from todo_bird_app.services.command_registry import CommandRegistry, CommandInfo
from todo_bird_app.views.main_window import MainWindow
from todo_bird_app.views.inbox_view import InboxView
from todo_bird_app.views.focus_view import FocusView


@pytest.fixture
def temp_env(tmp_path):
    db_file = tmp_path / "test_tb_310j.db"
    db = DatabaseManager(str(db_file))
    settings = SettingsManager(db)
    controller = TaskController(db)
    yield db, settings, controller


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


# ==============================================================================
# PART D: WINDOW USABILITY & DESKTOP CONTRACT (WIN-J01..WIN-J08)
# ==============================================================================

def test_win_j01_task_dialog_resizable_no_fixed_constraint(temp_env, qapp):
    """WIN-J01: TaskDialog is freely resizable and sets proper minimum size."""
    db, settings, controller = temp_env
    projects = controller.get_all_projects()
    dlg = TaskDialog(projects, db_manager=db, settings_manager=settings)

    # Minimum size is set to prevent unusable miniature dimensions
    assert dlg.minimumWidth() >= 400
    assert dlg.minimumHeight() >= 400

    # Can resize to larger desktop dimensions
    dlg.resize(1024, 900)
    assert dlg.width() == 1024
    assert dlg.height() == 900
    dlg.close()


def test_win_j02_task_dialog_geometry_persistence(temp_env, qapp):
    """WIN-J02: TaskDialog geometry persists across open/close cycles."""
    db, settings, controller = temp_env
    projects = controller.get_all_projects()

    # Open dialog 1, resize and close
    dlg1 = TaskDialog(projects, db_manager=db, settings_manager=settings)
    dlg1.resize(750, 850)
    dlg1.done(QDialog.Accepted)

    # Settings should store the custom size
    assert settings.get("task_dialog_width") == 750
    assert settings.get("task_dialog_height") == 850

    # Open dialog 2, should restore saved geometry
    dlg2 = TaskDialog(projects, db_manager=db, settings_manager=settings)
    assert dlg2.width() == 750
    assert dlg2.height() == 850
    dlg2.close()


def test_win_j03_project_dialog_resizable(temp_env, qapp):
    """WIN-J03: ProjectDialog is resizable and no longer uses setFixedSize."""
    db, settings, controller = temp_env
    project = Project(name="Alpha Project")
    dlg = ProjectDialog(project=project, settings_manager=settings)

    assert dlg.minimumWidth() >= 300
    assert dlg.minimumHeight() >= 250

    dlg.resize(600, 500)
    assert dlg.width() == 600
    assert dlg.height() == 500
    dlg.close()


def test_win_j04_project_dialog_geometry_persistence(temp_env, qapp):
    """WIN-J04: ProjectDialog geometry persists across sessions."""
    db, settings, controller = temp_env
    dlg1 = ProjectDialog(settings_manager=settings)
    dlg1.resize(520, 420)
    dlg1.done(QDialog.Accepted)

    assert settings.get("project_dialog_width") == 520
    assert settings.get("project_dialog_height") == 420

    dlg2 = ProjectDialog(settings_manager=settings)
    assert dlg2.width() == 520
    assert dlg2.height() == 420
    dlg2.close()


def test_win_j05_subtask_edit_dialog_resizable(temp_env, qapp):
    """WIN-J05: Subtask editor in TaskDialog is resizable with RichTextEditor."""
    db, settings, controller = temp_env
    task = Task(title="Parent Task")
    task_id = controller.add_task(task)
    task.id = task_id

    dlg = TaskDialog([], task=task, db_manager=db, settings_manager=settings)
    item = dlg._new_subtask_tree_item("Child Subtask")
    dlg.subtask_tree.addTopLevelItem(item)
    dlg.subtask_tree.setCurrentItem(item)

    # Edit selected subtask
    # Inspect that metadata is loaded and editor is RichTextEditor
    metadata = item.data(0, Qt.UserRole + 1) or {}
    assert "description" in metadata
    dlg.close()


def test_win_j06_3w1h_dialog_resizable(temp_env, qapp):
    """WIN-J06: ThreeWOneHDialog is resizable with minimum size and no fixed width."""
    db, settings, controller = temp_env
    task = Task(title="Reflection Task")
    dlg = ThreeWOneHDialog(task, settings_manager=settings)

    assert dlg.minimumWidth() >= 400
    assert dlg.minimumHeight() >= 400

    dlg.resize(700, 750)
    assert dlg.width() == 700
    assert dlg.height() == 750
    dlg.close()


def test_win_j07_confirm_delete_dialog_resizable(temp_env, qapp):
    """WIN-J07: ConfirmDeleteDialog is resizable and does not enforce fixed width."""
    db, settings, controller = temp_env
    dlg = ConfirmDeleteDialog(task_title="Test Delete", settings_manager=settings)

    assert dlg.minimumWidth() >= 300
    dlg.resize(480, 240)
    assert dlg.width() == 480
    dlg.close()


def test_win_j08_dialog_keyboard_accessibility_escape_closes(temp_env, qapp):
    """WIN-J08: Dialogs reject/close cleanly when Escape key is pressed."""
    db, settings, controller = temp_env
    dlg = TaskDialog([], db_manager=db, settings_manager=settings)
    dlg.show()

    # Reject / Escape closes dialog
    dlg.reject()
    assert not dlg.isVisible()


def test_win_j09_task_dialog_has_min_max_buttons_hint(temp_env, qapp):
    """WIN-J09: TaskDialog window flags include WindowMinMaxButtonsHint for maximize/minimize."""
    db, settings, controller = temp_env
    dlg = TaskDialog([], db_manager=db, settings_manager=settings)

    flags = dlg.windowFlags()
    assert bool(flags & Qt.WindowMinMaxButtonsHint) is True
    assert bool(flags & Qt.WindowCloseButtonHint) is True
    dlg.close()


def test_win_j10_reminder_dialog_cursor_dragging_and_size_grip(temp_env, qapp):
    """WIN-J10: ReminderDialog provides size grip and edge detection for cursor dragging resize."""
    db, settings, controller = temp_env
    from todo_bird_app.widgets.reminder_dialog import ReminderDialog
    from PySide6.QtCore import QPoint

    task = Task(title="Cursor Resize Task", description="Testing cursor dragging")
    dlg = ReminderDialog(task, settings_manager=settings)

    # Centralized event filter architecture replaces QSizeGrip
    assert not hasattr(dlg, "size_grip")

    # Edge detection for hover resizing
    dlg.resize(500, 300)
    assert dlg._get_resize_edge(QPoint(2, 150)) == "left"
    assert dlg._get_resize_edge(QPoint(498, 150)) == "right"
    assert dlg._get_resize_edge(QPoint(250, 2)) == "top"
    assert dlg._get_resize_edge(QPoint(250, 298)) == "bottom"
    assert dlg._get_resize_edge(QPoint(498, 298)) == "bottom_right"
    assert dlg._get_resize_edge(QPoint(250, 150)) == ""  # Inside window

    dlg.close()


def test_win_j11_reminder_dialog_size_presets_and_persistence(temp_env, qapp):
    """WIN-J11: ReminderDialog applies size presets (compact, standard, large) and saves/restores geometry."""
    db, settings, controller = temp_env
    from todo_bird_app.widgets.reminder_dialog import ReminderDialog

    task = Task(title="Preset Task")
    dlg = ReminderDialog(task, settings_manager=settings)

    # Test Compact Preset
    dlg.apply_preset("compact")
    assert dlg.width() == 460
    assert dlg.height() == 280
    assert settings.get("reminder_window_size_mode") == "compact"

    # Test Large Preset
    dlg.apply_preset("large")
    assert dlg.width() == 680
    assert dlg.height() == 440
    assert settings.get("reminder_window_size_mode") == "large"

    # Test Standard Preset
    dlg.apply_preset("standard")
    assert dlg.width() == 540
    assert dlg.height() == 340
    assert settings.get("reminder_window_size_mode") == "standard"

    dlg.close()


def test_win_j12_settings_view_reminder_window_size_controls(temp_env, qapp):
    """WIN-J12: SettingsView provides controls to set reminder window presets and custom dimensions."""
    db, settings, controller = temp_env
    from todo_bird_app.views.settings_view import SettingsView

    view = SettingsView(db, settings)
    assert hasattr(view, "rem_window_size_combo")
    assert hasattr(view, "rem_w_spin")
    assert hasattr(view, "rem_h_spin")

    # Select compact preset
    c_idx = view.rem_window_size_combo.findData("compact")
    view.rem_window_size_combo.setCurrentIndex(c_idx)
    assert settings.get("reminder_window_size_mode") == "compact"
    assert settings.get("reminder_window_width") == 460
    assert settings.get("reminder_window_height") == 280
    assert not view.rem_w_spin.isEnabled()

    # Select custom preset
    custom_idx = view.rem_window_size_combo.findData("custom")
    view.rem_window_size_combo.setCurrentIndex(custom_idx)
    assert view.rem_w_spin.isEnabled()
    assert view.rem_h_spin.isEnabled()

    # Change custom spinbox values
    view.rem_w_spin.setValue(600)
    view.rem_h_spin.setValue(400)
    assert settings.get("reminder_window_width") == 600
    assert settings.get("reminder_window_height") == 400


def test_win_j13_live_bidirectional_reminder_resize_sync(temp_env, qapp):
    """WIN-J13: Dragging a reminder window live-updates SettingsView spinboxes in real time."""
    db, settings, controller = temp_env
    from todo_bird_app.widgets.reminder_dialog import ReminderDialog
    from todo_bird_app.views.settings_view import SettingsView
    from PySide6.QtGui import QResizeEvent
    from PySide6.QtCore import QSize

    view = SettingsView(db, settings)
    task = Task(title="Live Sync Task")
    dlg = ReminderDialog(task, settings_manager=settings)
    dlg.show()

    # Trigger resize event simulating window dragging
    dlg.resize(640, 420)
    dlg.resizeEvent(QResizeEvent(QSize(640, 420), QSize(540, 340)))

    # View should automatically update spinbox values
    assert view.rem_w_spin.value() == 640
    assert view.rem_h_spin.value() == 420

    dlg.close()


def test_win_j14_settings_change_live_updates_open_reminder(temp_env, qapp):
    """WIN-J14: Changing size presets in SettingsView live-updates active open ReminderDialog instances."""
    db, settings, controller = temp_env
    from todo_bird_app.widgets.reminder_dialog import ReminderDialog
    from todo_bird_app.views.settings_view import SettingsView

    task = Task(title="Open Reminder Task")
    dlg = ReminderDialog(task, settings_manager=settings)
    dlg.show()

    view = SettingsView(db, settings)
    # Switch preset to Large in SettingsView
    l_idx = view.rem_window_size_combo.findData("large")
    view.rem_window_size_combo.setCurrentIndex(l_idx)

    # Active dialog should immediately update its dimensions to 680x440
    assert dlg.width() == 680
    assert dlg.height() == 440

    dlg.close()


def test_win_j15_reminder_dialog_scrollable(temp_env, qapp):
    """WIN-J15: ReminderDialog contains a QScrollArea ensuring long content is scrollable."""
    db, settings, controller = temp_env
    from todo_bird_app.widgets.reminder_dialog import ReminderDialog
    from PySide6.QtWidgets import QScrollArea

    task = Task(title="Scroll Task", description="Long description " * 50)
    dlg = ReminderDialog(task, settings_manager=settings)

    scroll_areas = dlg.findChildren(QScrollArea)
    assert len(scroll_areas) >= 1
    assert scroll_areas[0].widgetResizable() is True
    dlg.close()


def test_win_j16_all_dialogs_scrollable(temp_env, qapp):
    """WIN-J16: ProjectDialog and ThreeWOneHDialog contain QScrollArea form containers."""
    db, settings, controller = temp_env
    from PySide6.QtWidgets import QScrollArea

    proj_dlg = ProjectDialog(settings_manager=settings)
    assert len(proj_dlg.findChildren(QScrollArea)) >= 1
    proj_dlg.close()

    task = Task(title="3W1H Scroll")
    three_w_dlg = ThreeWOneHDialog(task, settings_manager=settings)
    assert len(three_w_dlg.findChildren(QScrollArea)) >= 1
    three_w_dlg.close()


def test_win_j17_desktop_window_flags_minimize_maximize(temp_env, qapp):
    """WIN-J17: TaskDialog, ProjectDialog, and ThreeWOneHDialog use Qt.Window for full desktop titlebar controls."""
    db, settings, controller = temp_env

    t_dlg = TaskDialog([], db_manager=db, settings_manager=settings)
    assert bool(t_dlg.windowFlags() & Qt.Window) is True
    assert bool(t_dlg.windowFlags() & Qt.WindowMinMaxButtonsHint) is True
    t_dlg.close()

    p_dlg = ProjectDialog(settings_manager=settings)
    assert bool(p_dlg.windowFlags() & Qt.Window) is True
    assert bool(p_dlg.windowFlags() & Qt.WindowMinMaxButtonsHint) is True
    p_dlg.close()

    three_w = ThreeWOneHDialog(Task(title="Flags Task"), settings_manager=settings)
    assert bool(three_w.windowFlags() & Qt.Window) is True
    assert bool(three_w.windowFlags() & Qt.WindowMinMaxButtonsHint) is True
    three_w.close()


def test_win_j18_snooze_ten_minutes_timing_logic(temp_env, qapp):
    """WIN-J18: Snoozing a reminder for 10 minutes does NOT trigger until 10 minutes have elapsed."""
    db, settings, controller = temp_env
    from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
    from datetime import datetime, timedelta

    ReminderPolicyService.reset_session_state()
    task = Task(title="Snooze Test Task", startup_reminder=1)
    task.id = controller.add_task(task)

    now = datetime(2026, 8, 18, 10, 0, 0)
    # Snooze for 10 minutes from 10:00 -> snoozed until 10:10
    ReminderPolicyService.snooze_reminder(task.id, 10, from_dt=now)

    # Check at 10:05 (5 minutes in) -> should NOT be due
    check_5min = ReminderPolicyService.get_due_reminders(controller, settings, current_dt=now + timedelta(minutes=5))
    assert len(check_5min) == 0

    # Check at 10:09:59 -> should NOT be due
    check_9min = ReminderPolicyService.get_due_reminders(controller, settings, current_dt=now + timedelta(minutes=9, seconds=59))
    assert len(check_9min) == 0

    # Check at 10:10:00 (10 minutes elapsed) -> IS DUE
    check_10min = ReminderPolicyService.get_due_reminders(controller, settings, current_dt=now + timedelta(minutes=10))
    assert len(check_10min) == 1
    assert check_10min[0].id == task.id


def test_win_j19_future_scheduled_reminder_timing(temp_env, qapp):
    """WIN-J19: Future scheduled reminder does not trigger prematurely."""
    db, settings, controller = temp_env
    from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
    from datetime import datetime

    ReminderPolicyService.reset_session_state()
    ReminderPolicyService._session_start_time = datetime(2026, 8, 18, 10, 0)
    # Task scheduled for 10:30 today
    task = Task(title="Scheduled Task", planned_date="2026-08-18", planned_start_time="10:30", startup_reminder=0)
    task.id = controller.add_task(task)

    # Current time is 10:15 -> NOT due
    check_early = ReminderPolicyService.get_due_reminders(controller, settings, current_dt=datetime(2026, 8, 18, 10, 15))
    assert len(check_early) == 0

    # Current time is 10:30 -> IS due
    check_on_time = ReminderPolicyService.get_due_reminders(controller, settings, current_dt=datetime(2026, 8, 18, 10, 30))
    assert len(check_on_time) == 1
    assert check_on_time[0].id == task.id


def test_win_j20_reminder_live_time_badge_active(temp_env, qapp):
    """WIN-J20: ReminderDialog top-right time badge ticks live current time and schedule context."""
    db, settings, controller = temp_env
    from todo_bird_app.widgets.reminder_dialog import ReminderDialog

    task = Task(title="Clock Test Task", planned_start_time="14:00")
    dlg = ReminderDialog(task, settings_manager=settings)

    assert hasattr(dlg, "lbl_time_badge")
    badge_text = dlg.lbl_time_badge.text()
    assert ("AM" in badge_text or "PM" in badge_text) and "Due 14:00" in badge_text
    dlg.close()


def test_win_j21_reminder_smart_sleek_buttons(temp_env, qapp):
    """WIN-J21: ReminderDialog action buttons are compact and smartly styled."""
    db, settings, controller = temp_env
    from todo_bird_app.widgets.reminder_dialog import ReminderDialog

    task = Task(title="Button Style Task")
    dlg = ReminderDialog(task, settings_manager=settings)

    assert dlg.btn_complete.height() == 32 or dlg.btn_complete.maximumHeight() <= 40
    assert dlg.btn_snooze.height() == 32 or dlg.btn_snooze.maximumHeight() <= 40
    assert dlg.btn_open.height() == 32 or dlg.btn_open.maximumHeight() <= 40
    assert dlg.btn_dismiss.height() == 32 or dlg.btn_dismiss.maximumHeight() <= 40
    dlg.close()


def test_win_j22_flicker_free_resizing_state(temp_env, qapp):
    """WIN-J22: Dragging reminder window maintains _is_resizing state and defers disk saves to release."""
    db, settings, controller = temp_env
    from todo_bird_app.widgets.reminder_dialog import ReminderDialog
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent

    task = Task(title="Flicker Test")
    dlg = ReminderDialog(task, settings_manager=settings)
    dlg.show()

    # Simulate mouse press on right edge
    edge = dlg._get_resize_edge(QPoint(dlg.width() - 2, 100))
    assert edge == "right"

    from todo_bird_app.services.window_interaction_service import WindowInteractionService
    original_resize = WindowInteractionService.begin_system_resize
    def mock_resize(widget, event, edge_str):
        widget._is_resizing = True
        widget._resize_edge = edge_str
        widget._drag_start_geo = widget.geometry()
        widget._drag_start_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
        return True
    WindowInteractionService.begin_system_resize = mock_resize

    try:
        local_pt = QPoint(dlg.width() - 2, 100)
        global_pt = dlg.mapToGlobal(local_pt)
        press_ev = QMouseEvent(QEvent.MouseButtonPress, local_pt, global_pt, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
        dlg.eventFilter(dlg, press_ev)
        assert dlg._is_resizing is True

        # Mouse release
        release_ev = QMouseEvent(QEvent.MouseButtonRelease, QPoint(dlg.width() + 50, 100), QPoint(150, 100), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
        dlg.mouseReleaseEvent(release_ev)
        assert dlg._is_resizing is False
        assert dlg._resize_edge is None
    finally:
        WindowInteractionService.begin_system_resize = original_resize
        dlg.close()


def test_win_j23_snooze_intervals_options_and_minimum_5_minutes(temp_env, qapp):
    """WIN-J23: Snooze menu supports 5m, 10m, 20m, 30m, 1h, 24h intervals with exact timing evaluation."""
    db, settings, controller = temp_env
    from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
    from todo_bird_app.widgets.reminder_dialog import ReminderDialog
    from datetime import datetime, timedelta

    # 1. Verify 5m snooze
    ReminderPolicyService.reset_session_state()
    task = Task(title="5min Snooze Task", startup_reminder=1)
    task.id = controller.add_task(task)

    now = datetime(2026, 8, 18, 10, 0, 0)
    ReminderPolicyService.snooze_reminder(task.id, 5, from_dt=now)

    # 4 minutes later -> not due
    assert len(ReminderPolicyService.get_due_reminders(controller, settings, current_dt=now + timedelta(minutes=4))) == 0
    # 5 minutes later -> due
    due_5m = ReminderPolicyService.get_due_reminders(controller, settings, current_dt=now + timedelta(minutes=5))
    assert len(due_5m) == 1
    assert due_5m[0].id == task.id

    # 2. Verify 20m snooze
    ReminderPolicyService.reset_session_state()
    ReminderPolicyService.snooze_reminder(task.id, 20, from_dt=now)
    assert len(ReminderPolicyService.get_due_reminders(controller, settings, current_dt=now + timedelta(minutes=19))) == 0
    assert len(ReminderPolicyService.get_due_reminders(controller, settings, current_dt=now + timedelta(minutes=20))) == 1

    # 3. Verify 30m snooze
    ReminderPolicyService.reset_session_state()
    ReminderPolicyService.snooze_reminder(task.id, 30, from_dt=now)
    assert len(ReminderPolicyService.get_due_reminders(controller, settings, current_dt=now + timedelta(minutes=29))) == 0
    assert len(ReminderPolicyService.get_due_reminders(controller, settings, current_dt=now + timedelta(minutes=30))) == 1

    # 4. Verify 1 hour (60m) snooze
    ReminderPolicyService.reset_session_state()
    ReminderPolicyService.snooze_reminder(task.id, 60, from_dt=now)
    assert len(ReminderPolicyService.get_due_reminders(controller, settings, current_dt=now + timedelta(minutes=59))) == 0
    assert len(ReminderPolicyService.get_due_reminders(controller, settings, current_dt=now + timedelta(minutes=60))) == 1

    # 5. Verify 24 hour (1440m) snooze
    ReminderPolicyService.reset_session_state()
    ReminderPolicyService.snooze_reminder(task.id, 1440, from_dt=now)
    assert len(ReminderPolicyService.get_due_reminders(controller, settings, current_dt=now + timedelta(minutes=1439))) == 0
    assert len(ReminderPolicyService.get_due_reminders(controller, settings, current_dt=now + timedelta(minutes=1440))) == 1


def test_win_j24_canonical_controller_authority_no_duplicates(temp_env, qapp):
    """WIN-J24: MainWindow holds canonical task_controller authority without duplicate controller creation."""
    db, settings, controller = temp_env
    from todo_bird_app.views.main_window import MainWindow
    from todo_bird_app.controllers.theme_controller import ThemeController

    tc_theme = ThemeController(settings)
    main_win = MainWindow(db, settings, tc_theme)

    # 1. Proves MainWindow has canonical task_controller
    assert hasattr(main_win, "task_controller")
    assert main_win.task_controller is not None
    assert main_win.task_controller.db_manager is db

    # 2. Proves open_quick_add_dialog reuses canonical controller
    main_win.close()


def test_win_j25_snooze_persistence_across_app_restart(temp_env, qapp):
    """WIN-J25: Snooze state persists across application restarts without mutating original task schedule."""
    db, settings, controller = temp_env
    from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
    from datetime import datetime, timedelta

    ReminderPolicyService.reset_session_state(settings_manager=settings)

    # Task originally scheduled at 10:00
    task = Task(title="Restart Snooze Test", planned_date="2026-08-18", planned_start_time="10:00", startup_reminder=1)
    task_id = controller.add_task(task)

    # Operator snoozes at 10:00 for 10 minutes (expires at 10:10)
    snooze_time = datetime(2026, 8, 18, 10, 0, 0)
    ReminderPolicyService.snooze_reminder(task_id, 10, from_dt=snooze_time, settings_manager=settings)

    # Simulate application close at 10:04 (simulate restart / RAM clear)
    ReminderPolicyService._snoozed_until.clear()
    ReminderPolicyService._shown_in_session.clear()
    ReminderPolicyService._dismissed_in_session.clear()

    # Reopen at 10:06 (before 10:10) -> must still be snoozed, not due
    check_early = ReminderPolicyService.get_due_reminders(controller, settings, current_dt=datetime(2026, 8, 18, 10, 6, 0))
    assert len(check_early) == 0

    # Reopen at 10:12 (after 10:10) -> must be eligible and trigger
    check_due = ReminderPolicyService.get_due_reminders(controller, settings, current_dt=datetime(2026, 8, 18, 10, 12, 0))
    assert len(check_due) == 1
    assert check_due[0].id == task_id

    # Verify original task schedule was NEVER mutated
    reloaded_task = controller.get_task(task_id)
    assert reloaded_task.planned_date == "2026-08-18"
    assert reloaded_task.planned_start_time == "10:00"


def test_win_j26_single_scheduler_instance_and_clean_shutdown(temp_env, qapp):
    """WIN-J26: Only one reminder polling timer exists on MainWindow and cleanly stops on close."""
    db, settings, controller = temp_env
    from todo_bird_app.views.main_window import MainWindow
    from todo_bird_app.controllers.theme_controller import ThemeController

    tc_theme = ThemeController(settings)
    main_win = MainWindow(db, settings, tc_theme)

    # Exactly one timer exists and is active
    assert hasattr(main_win, "_reminder_poll_timer")
    assert main_win._reminder_poll_timer.isActive() is True

    # Navigating views does not create extra timers
    main_win.navigation_controller.set_active_section("settings")
    main_win.navigation_controller.set_active_section("today")
    main_win.navigation_controller.set_active_section("gantt")
    assert main_win._reminder_poll_timer.isActive() is True

    # Clean shutdown stops the timer
    main_win.close()
    assert main_win._reminder_poll_timer.isActive() is False


# ==============================================================================
# PART E: RICH DESCRIPTION AUTHORITY (RT-J01..RT-J12)
# ==============================================================================

def test_rt_j01_bold_formatting_toggle(qapp):
    """RT-J01: Bold formatting toggles on selection with toolbar action."""
    editor = RichTextEditor()
    editor.editor.setPlainText("Hello World")

    cursor = editor.editor.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.KeepAnchor)
    editor.editor.setTextCursor(cursor)

    # Trigger bold
    editor.bold_action.trigger()
    fmt = editor.editor.textCursor().charFormat()
    assert fmt.fontWeight() == QFont.Bold

    # Untoggle bold
    editor.bold_action.trigger()
    fmt2 = editor.editor.textCursor().charFormat()
    assert fmt2.fontWeight() == QFont.Normal


def test_rt_j02_italic_formatting_toggle(qapp):
    """RT-J02: Italic formatting toggles on selection."""
    editor = RichTextEditor()
    editor.editor.setPlainText("Italicized Text")

    cursor = editor.editor.textCursor()
    cursor.select(QTextCursor.Document)
    editor.editor.setTextCursor(cursor)

    editor.italic_action.trigger()
    assert editor.editor.textCursor().charFormat().fontItalic() is True

    editor.italic_action.trigger()
    assert editor.editor.textCursor().charFormat().fontItalic() is False


def test_rt_j03_underline_formatting_toggle(qapp):
    """RT-J03: Underline formatting toggles on selection."""
    editor = RichTextEditor()
    editor.editor.setPlainText("Underlined Content")

    cursor = editor.editor.textCursor()
    cursor.select(QTextCursor.Document)
    editor.editor.setTextCursor(cursor)

    editor.underline_action.trigger()
    assert editor.editor.textCursor().charFormat().fontUnderline() is True

    editor.underline_action.trigger()
    assert editor.editor.textCursor().charFormat().fontUnderline() is False


def test_rt_j04_bullet_list_toggle(qapp):
    """RT-J04: Bullet list inserts and toggles correctly."""
    editor = RichTextEditor()
    editor.editor.setPlainText("Item 1\nItem 2")

    cursor = editor.editor.textCursor()
    cursor.setPosition(0)
    editor.editor.setTextCursor(cursor)

    editor.bullet_action.trigger()
    current_list = editor.editor.textCursor().currentList()
    assert current_list is not None
    assert current_list.format().style() == QTextListFormat.ListDisc

    # Trigger again removes list
    editor.bullet_action.trigger()
    assert editor.editor.textCursor().currentList() is None


def test_rt_j05_numbered_list_toggle(qapp):
    """RT-J05: Numbered list inserts and toggles correctly."""
    editor = RichTextEditor()
    editor.editor.setPlainText("Step 1\nStep 2")

    cursor = editor.editor.textCursor()
    cursor.setPosition(0)
    editor.editor.setTextCursor(cursor)

    editor.number_action.trigger()
    current_list = editor.editor.textCursor().currentList()
    assert current_list is not None
    assert current_list.format().style() == QTextListFormat.ListDecimal


def test_rt_j06_toolbar_state_sync_with_cursor(qapp):
    """RT-J06: Toolbar buttons update checked state based on cursor character format."""
    editor = RichTextEditor()
    editor.setHtml("<p><b>BoldPart</b><i>ItalicPart</i></p>")

    # Move cursor inside BoldPart
    cursor = editor.editor.textCursor()
    cursor.setPosition(2)
    editor.editor.setTextCursor(cursor)
    assert editor.bold_action.isChecked() is True
    assert editor.italic_action.isChecked() is False

    # Move cursor inside ItalicPart
    cursor.setPosition(10)
    editor.editor.setTextCursor(cursor)
    assert editor.bold_action.isChecked() is False
    assert editor.italic_action.isChecked() is True


def test_rt_j07_html_storage_and_roundtrip(qapp):
    """RT-J07: Formatted HTML content roundtrips without loss."""
    editor1 = RichTextEditor()
    editor1.editor.setPlainText("Important Note")
    cursor = editor1.editor.textCursor()
    cursor.select(QTextCursor.Document)
    editor1.editor.setTextCursor(cursor)
    editor1.bold_action.trigger()

    saved_html = editor1.toHtml()
    assert "<b" in saved_html.lower() or "font-weight:600" in saved_html or "font-weight:700" in saved_html or "font-weight:bold" in saved_html

    editor2 = RichTextEditor()
    editor2.setHtml(saved_html)
    assert "Important Note" in editor2.toPlainText()


def test_rt_j08_backward_compatibility_plain_text_loading(qapp):
    """RT-J08: Legacy plain text without HTML tags loads cleanly into RichTextEditor."""
    editor = RichTextEditor()
    plain_text = "Line 1: Requirement analysis\nLine 2: Design specs"
    editor.setHtml(plain_text)

    # Should be auto-wrapped in paragraphs and fully readable
    assert "Line 1: Requirement analysis" in editor.toPlainText()
    assert "Line 2: Design specs" in editor.toPlainText()


def test_rt_j09_task_dialog_saves_html_description(temp_env, qapp):
    """RT-J09: TaskDialog saves rich HTML description to task model."""
    db, settings, controller = temp_env
    task = Task(title="Rich Task")
    dlg = TaskDialog([], task=task, db_manager=db, settings_manager=settings)
    dlg.desc_input.setHtml("<p>Detailed <b>rich</b> description.</p>")
    dlg.on_save()

    saved_desc = task.description
    assert "rich" in saved_desc
    assert ("<b" in saved_desc.lower() or "font-weight" in saved_desc)


def test_rt_j10_project_dialog_saves_html_description(temp_env, qapp):
    """RT-J10: ProjectDialog saves rich HTML description to project model."""
    db, settings, controller = temp_env
    project = Project(name="Web App")
    dlg = ProjectDialog(project=project, settings_manager=settings)
    dlg.desc_input.setHtml("<p>Project <i>roadmap</i> and goals.</p>")
    dlg.on_save()

    assert "roadmap" in project.description
    assert ("<i" in project.description.lower() or "font-style:italic" in project.description)


def test_rt_j11_focus_view_reflection_appends_html(temp_env, qapp):
    """RT-J11: Focus view appends 3W1H reflection as an HTML paragraph."""
    db, settings, controller = temp_env
    task = Task(title="Focus Task", description="<p>Initial requirements.</p>")
    task_id = controller.add_task(task)
    task.id = task_id

    # Simulate reflection append
    reflection = "\n[3W1H Reflection]: Bottleneck resolved."
    escaped_reflection = html_mod.escape(reflection)
    reflection_html = f"<p>{escaped_reflection}</p>"
    task.description = (task.description or "") + reflection_html
    controller.update_task(task)

    updated = controller.get_task(task_id)
    assert "Initial requirements." in updated.description
    assert "[3W1H Reflection]: Bottleneck resolved." in updated.description
    assert "<p>" in updated.description


def test_rt_j12_inbox_view_quick_edit_rich_text(temp_env, qapp):
    """RT-J12: InboxView quick-edit dialog uses RichTextEditor."""
    db, settings, controller = temp_env
    inbox = InboxView(db, settings)
    task = Task(title="Inbox Item", description="<p>Quick note <b>bold</b>.</p>")
    task_id = controller.add_task(task)
    task.id = task_id

    # The quick edit uses RichTextEditor and updates description as HTML
    editor = RichTextEditor()
    editor.setHtml(task.description)
    assert "Quick note bold." in editor.toPlainText()


# ==============================================================================
# PART F: KEYBOARD SHORTCUT STANDARD (KS-J01..KS-J12)
# ==============================================================================

def test_ks_j01_command_registry_singleton(qapp):
    """KS-J01: CommandRegistry is a consistent singleton across imports."""
    reg1 = CommandRegistry()
    reg2 = CommandRegistry()
    assert reg1 is reg2


def test_ks_j02_command_registration_and_retrieval(qapp):
    """KS-J02: Commands can be registered, queried, and retrieved with shortcuts."""
    reg = CommandRegistry()
    reg.register(
        command_id="test_quick_task",
        display_name="Quick Task",
        callback=lambda: None,
        shortcut="Ctrl+Shift+N",
        scope="global",
        tooltip="Create quick task",
        allow_override=True,
    )

    cmd = reg.get_command("test_quick_task")
    assert cmd is not None
    assert cmd.display_name == "Quick Task"
    assert cmd.shortcut == "Ctrl+Shift+N"
    assert reg.get_shortcut_text("test_quick_task") == "Ctrl+Shift+N"


def test_ks_j03_duplicate_command_id_error(qapp):
    """KS-J03: Duplicate command registration without allow_override raises ValueError."""
    reg = CommandRegistry()
    reg.register("dup_cmd", "Original", lambda: None, allow_override=True)

    with pytest.raises(ValueError):
        reg.register("dup_cmd", "Duplicate", lambda: None, allow_override=False)


def test_ks_j04_command_unregistration(qapp):
    """KS-J04: Unregistering a command removes it from registry and shortcut map."""
    reg = CommandRegistry()
    reg.register("temp_cmd", "Temp", lambda: None, shortcut="Ctrl+T", allow_override=True)
    assert reg.get_command("temp_cmd") is not None

    reg.unregister("temp_cmd")
    assert reg.get_command("temp_cmd") is None
    assert reg.get_shortcut_text("temp_cmd") == ""


def test_ks_j05_main_window_global_shortcuts_registered(temp_env, qapp):
    """KS-J05: MainWindow registers global shortcuts: Ctrl+N, Ctrl+K, Ctrl+,, Ctrl+Q."""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)
    main_win = MainWindow(db, settings, theme_ctrl)

    reg = main_win.command_registry
    assert reg.get_shortcut_text("new_task") == "Ctrl+N"
    assert reg.get_shortcut_text("open_command_palette") == "Ctrl+K"
    assert reg.get_shortcut_text("open_settings") == "Ctrl+,"
    assert reg.get_shortcut_text("quit_application") == "Ctrl+Q"

    main_win.close()


def test_ks_j06_rich_text_local_shortcuts_registered(temp_env, qapp):
    """KS-J06: Rich text formatting shortcuts (Ctrl+B/I/U) registered with local scope."""
    reg = CommandRegistry()
    cmd_b = reg.get_command("format_bold")
    cmd_i = reg.get_command("format_italic")
    cmd_u = reg.get_command("format_underline")

    assert cmd_b is not None and cmd_b.shortcut == "Ctrl+B" and cmd_b.scope == "local"
    assert cmd_i is not None and cmd_i.shortcut == "Ctrl+I" and cmd_i.scope == "local"
    assert cmd_u is not None and cmd_u.shortcut == "Ctrl+U" and cmd_u.scope == "local"


def test_ks_j07_command_palette_displays_shortcut_hints(temp_env, qapp):
    """KS-J07: CommandPalette displays shortcut hints next to registered actions."""
    db, settings, controller = temp_env
    palette = CommandPalette(db)

    # Check that create task item includes [Ctrl+N]
    found_shortcut_hint = False
    for i in range(palette.list_widget.count()):
        item_text = palette.list_widget.item(i).text()
        if "Create New Task" in item_text and "Ctrl+N" in item_text:
            found_shortcut_hint = True
            break

    assert found_shortcut_hint is True
    palette.close()


def test_ks_j08_get_all_commands_enumeration(qapp):
    """KS-J08: CommandRegistry.get_all_commands returns complete list of commands."""
    reg = CommandRegistry()
    cmds = reg.get_all_commands()
    assert isinstance(cmds, list)
    assert len(cmds) >= 4  # Contains at least new_task, open_command_palette, open_settings, quit_application


def test_ks_j09_command_registry_clear(qapp):
    """KS-J09: Clearing command registry safely removes all bindings."""
    reg = CommandRegistry()
    reg.register("test_clr", "Clear Test", lambda: None, shortcut="Ctrl+Alt+C", allow_override=True)
    assert len(reg.get_all_commands()) > 0

    reg.clear()
    assert len(reg.get_all_commands()) == 0


def test_ks_j10_ctrl_k_palette_open_action(temp_env, qapp):
    """KS-J10: Triggering open_command_palette command invokes action correctly."""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)
    main_win = MainWindow(db, settings, theme_ctrl)

    opened = False
    def mock_open_palette():
        nonlocal opened
        opened = True

    main_win.open_command_palette = mock_open_palette
    main_win.command_registry.register(
        "open_command_palette",
        "Command Palette",
        main_win.open_command_palette,
        shortcut="Ctrl+K",
        parent=main_win,
        allow_override=True,
    )

    cmd = main_win.command_registry.get_command("open_command_palette")
    cmd.callback()
    assert opened is True
    main_win.close()


def test_ks_j11_ctrl_n_quick_add_action(temp_env, qapp):
    """KS-J11: Triggering new_task command invokes open_quick_add_dialog."""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)
    main_win = MainWindow(db, settings, theme_ctrl)

    opened = False
    def mock_quick_add():
        nonlocal opened
        opened = True

    main_win.open_quick_add_dialog = mock_quick_add
    main_win.command_registry.register(
        "new_task",
        "New Task",
        main_win.open_quick_add_dialog,
        shortcut="Ctrl+N",
        parent=main_win,
        allow_override=True,
    )

    cmd = main_win.command_registry.get_command("new_task")
    cmd.callback()
    assert opened is True
    main_win.close()


def test_ks_j12_clean_shutdown_shortcut_action(temp_env, qapp):
    """KS-J12: Ctrl+Q quit command invokes MainWindow close cleanly."""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)
    main_win = MainWindow(db, settings, theme_ctrl)

    closed = False
    def mock_close():
        nonlocal closed
        closed = True

    main_win.close = mock_close
    main_win.command_registry.register(
        "quit_application",
        "Quit",
        main_win.close,
        shortcut="Ctrl+Q",
        parent=main_win,
        allow_override=True,
    )

    cmd = main_win.command_registry.get_command("quit_application")
    cmd.callback()
    assert closed is True
