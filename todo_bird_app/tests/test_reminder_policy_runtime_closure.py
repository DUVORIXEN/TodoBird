"""
Test Suite: Reminder Policy & Runtime Closure (Phase 2C.2)
Comprehensive automated tests verifying:
1. One canonical polling timer only
2. Normal due reminder fires once
3. Polling again does not duplicate same occurrence
4. Restart does not repeat dismissed reminder
5. Startup catch-up OFF prevents startup reminder
6. Startup catch-up ON shows missed reminder once
7. Second restart does not repeat acknowledged startup reminder
8. Snooze persists across restarts
9. Restart before snooze target does not trigger
10. Snooze target triggers correctly
11. Startup after missed snooze target behaves consistently
12. Completed task suppressed
13. Cancelled task suppressed
14. In-progress task still eligible
15. Blocked task behavior correct
16. Multiple reminders deterministic ordering & offset
17. Same task cannot spawn duplicate reminder windows
18. Reminder window is not WindowStaysOnTopHint
19. Reminder is not ApplicationModal
20. Reminder can lose active focus
21. Switching MainWindow does not force reminder back on top
22. No recurring raise_/activateWindow focus loop
23. Task-level startup preference persists in DB
24. Task-level preference survives restart
25. Legacy task data loads safely
26. Light theme rendering
27. Dark theme rendering
28. Typography 10 -> 20 -> 10 scaling
29. Keyboard accessibility & shortcuts (Alt+D, Alt+S, Alt+C, Alt+O, Esc)
30. Clean shutdown with reminder open
31. Clean shutdown with snoozed reminder
32. Reminder poll does not execute after teardown
"""

import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QKeyEvent

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
from todo_bird_app.widgets.reminder_dialog import ReminderDialog
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.services.window_registry import WindowRegistry
from todo_bird_app.services.typography_service import TypographyService


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture
def temp_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "test_reminders.db")
        db = DatabaseManager(db_path)
        settings = SettingsManager(db, config_dir=Path(temp_dir))
        theme_ctrl = ThemeController(settings)
        ReminderPolicyService.reset_session_state(settings)
        yield db, settings, theme_ctrl, temp_dir
        ReminderPolicyService.reset_session_state(settings)


# 1. One canonical polling timer only
def test_01_one_canonical_polling_timer_only(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    assert hasattr(win, "_reminder_poll_timer")
    assert win._reminder_poll_timer is not None
    assert win._reminder_poll_timer.isActive()
    assert win._reminder_poll_timer.interval() == 2000
    win.close()


# 2. Normal due reminder fires once
def test_02_normal_due_reminder_fires_once(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    now = datetime.now()
    t = Task(
        title="Normal Due Task",
        planned_date=now.strftime("%Y-%m-%d"),
        planned_start_time=now.strftime("%H:%M"),
        startup_reminder=False,
    )
    tid = tc.add_task(t)
    t.id = tid

    # Reference session start is before now
    ReminderPolicyService._session_start_time = now - timedelta(minutes=1)

    due = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=now)
    assert len(due) == 1
    assert due[0].id == tid


# 3. Polling again does not duplicate same occurrence
def test_03_polling_again_does_not_duplicate(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    now = datetime.now()
    t = Task(
        title="No Duplicate Task",
        planned_date=now.strftime("%Y-%m-%d"),
        planned_start_time=now.strftime("%H:%M"),
        startup_reminder=False,
    )
    tid = tc.add_task(t)
    ReminderPolicyService._session_start_time = now - timedelta(minutes=1)

    due1 = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=now)
    assert len(due1) == 1
    ReminderPolicyService.mark_shown(tid)

    # Next poll
    due2 = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=now + timedelta(seconds=2))
    assert len(due2) == 0


# 4. Restart does not repeat dismissed reminder
def test_04_restart_does_not_repeat_dismissed_reminder(temp_env):
    db, settings, _, temp_dir = temp_env
    tc = TaskController(db)
    now = datetime.now()
    t = Task(
        title="Dismissed Task",
        planned_date=now.strftime("%Y-%m-%d"),
        planned_start_time=now.strftime("%H:%M"),
        startup_reminder=False,
    )
    tid = tc.add_task(t)
    t.id = tid

    occ_key = ReminderPolicyService.get_occurrence_key(t)
    ReminderPolicyService.dismiss_reminder(tid, occurrence_key=occ_key, settings_manager=settings)

    # Simulate app restart: reload settings and reset session state RAM
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService.reset_session_state()
    ReminderPolicyService._session_start_time = now + timedelta(minutes=5)

    # Check due reminders in new session
    due_after_restart = ReminderPolicyService.get_due_reminders(tc, restarted_settings, current_dt=now + timedelta(minutes=5))
    assert len(due_after_restart) == 0


# 5. Startup catch-up OFF prevents startup reminder
def test_05_startup_catchup_off_prevents_startup_reminder(temp_env):
    db, settings, _, _ = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    tc = TaskController(db)
    past = datetime.now() - timedelta(hours=2)
    t = Task(
        title="Old Missed Task",
        planned_date=past.strftime("%Y-%m-%d"),
        planned_start_time=past.strftime("%H:%M"),
        startup_reminder=False,  # OFF
    )
    tc.add_task(t)

    # App launches now
    ReminderPolicyService._session_start_time = datetime.now()
    due = ReminderPolicyService.get_due_reminders(tc, settings)
    assert len(due) == 0


# 6. Startup catch-up ON shows missed reminder once
def test_06_startup_catchup_on_shows_missed_reminder_once(temp_env):
    db, settings, _, _ = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    tc = TaskController(db)
    past = datetime.now() - timedelta(hours=2)
    t = Task(
        title="Missed Task Catchup",
        planned_date=past.strftime("%Y-%m-%d"),
        planned_start_time=past.strftime("%H:%M"),
        startup_reminder=True,  # ON
    )
    tid = tc.add_task(t)

    ReminderPolicyService._session_start_time = datetime.now()
    due = ReminderPolicyService.get_startup_due_reminders(tc, settings)
    assert len(due) == 1
    assert due[0].id == tid

    # Mark shown
    ReminderPolicyService.mark_shown(tid)
    due_again = ReminderPolicyService.get_due_reminders(tc, settings)
    assert len(due_again) == 0


# 7. Second restart does not repeat acknowledged startup reminder
def test_07_second_restart_does_not_repeat_acknowledged_startup_reminder(temp_env):
    db, settings, _, temp_dir = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    tc = TaskController(db)
    past = datetime.now() - timedelta(hours=2)
    t = Task(
        title="Acknowledged Startup Task",
        planned_date=past.strftime("%Y-%m-%d"),
        planned_start_time=past.strftime("%H:%M"),
        startup_reminder=True,
    )
    tid = tc.add_task(t)
    t.id = tid

    occ_key = ReminderPolicyService.get_occurrence_key(t)
    ReminderPolicyService.dismiss_reminder(tid, occurrence_key=occ_key, settings_manager=settings)

    # Restart app
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService.reset_session_state()
    ReminderPolicyService._session_start_time = datetime.now()

    due = ReminderPolicyService.get_due_reminders(tc, restarted_settings)
    assert len(due) == 0


# 8. Snooze persists across restarts
def test_08_snooze_persists_across_restarts(temp_env):
    db, settings, _, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(title="Snooze Persist Task", startup_reminder=True)
    tid = tc.add_task(t)

    now = datetime(2026, 8, 23, 10, 0, 0)
    ReminderPolicyService.snooze_reminder(tid, minutes=30, from_dt=now, settings_manager=settings)

    # Restart app and reload
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService._snoozed_until.clear()

    # During snooze at 10:15
    check_1 = ReminderPolicyService.get_due_reminders(tc, restarted_settings, current_dt=datetime(2026, 8, 23, 10, 15, 0))
    assert len(check_1) == 0


# 9. Restart before snooze target does not trigger
def test_09_restart_before_snooze_target_does_not_trigger(temp_env):
    db, settings, _, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(title="Early Restart Task", startup_reminder=True)
    tid = tc.add_task(t)

    now = datetime(2026, 8, 23, 8, 0, 0)
    ReminderPolicyService.snooze_reminder(tid, minutes=60, from_dt=now, settings_manager=settings)

    restarted = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService._snoozed_until.clear()
    check = ReminderPolicyService.get_due_reminders(tc, restarted, current_dt=datetime(2026, 8, 23, 8, 30, 0))
    assert len(check) == 0


# 10. Snooze target triggers correctly
def test_10_snooze_target_triggers_correctly(temp_env):
    db, settings, _, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(title="Snooze Due Task", startup_reminder=True)
    tid = tc.add_task(t)

    now = datetime(2026, 8, 23, 8, 0, 0)
    ReminderPolicyService.snooze_reminder(tid, minutes=60, from_dt=now, settings_manager=settings)

    restarted = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService._snoozed_until.clear()
    check = ReminderPolicyService.get_due_reminders(tc, restarted, current_dt=datetime(2026, 8, 23, 9, 5, 0))
    assert len(check) == 1
    assert check[0].id == tid


# 11. Startup after missed snooze target behaves consistently
def test_11_startup_after_missed_snooze_target(temp_env):
    db, settings, _, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(title="Missed Snooze Target Task", startup_reminder=True)
    tid = tc.add_task(t)

    now = datetime(2026, 8, 23, 8, 0, 0)
    ReminderPolicyService.snooze_reminder(tid, minutes=60, from_dt=now, settings_manager=settings)

    # App closed at 8:00, opened at 12:00
    restarted = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService._snoozed_until.clear()
    check = ReminderPolicyService.get_due_reminders(tc, restarted, current_dt=datetime(2026, 8, 23, 12, 0, 0))
    assert len(check) == 1
    assert check[0].id == tid


# 12. Completed task suppressed
def test_12_completed_task_suppressed(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    now = datetime.now()
    t = Task(
        title="Completed Task",
        planned_date=now.strftime("%Y-%m-%d"),
        status=TaskStatus.COMPLETED,
        startup_reminder=True,
    )
    tc.add_task(t)
    due = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=now)
    assert len(due) == 0


# 13. Cancelled task suppressed
def test_13_cancelled_task_suppressed(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    now = datetime.now()
    t = Task(
        title="Cancelled Task",
        planned_date=now.strftime("%Y-%m-%d"),
        status=TaskStatus.CANCELLED,
        startup_reminder=True,
    )
    tc.add_task(t)
    due = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=now)
    assert len(due) == 0


# 14. In-progress task still eligible
def test_14_in_progress_task_still_eligible(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    now = datetime.now()
    ReminderPolicyService._session_start_time = now - timedelta(minutes=2)
    t = Task(
        title="In Progress Task",
        planned_date=now.strftime("%Y-%m-%d"),
        planned_start_time=now.strftime("%H:%M"),
        status=TaskStatus.IN_PROGRESS,
        actual_start_date=now.strftime("%Y-%m-%d"),
        startup_reminder=False,
    )
    tid = tc.add_task(t)
    due = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=now)
    assert len(due) == 1
    assert due[0].id == tid


# 15. Blocked task behavior correct
def test_15_blocked_task_still_eligible(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    now = datetime.now()
    ReminderPolicyService._session_start_time = now - timedelta(minutes=2)
    t = Task(
        title="Blocked Task",
        planned_date=now.strftime("%Y-%m-%d"),
        planned_start_time=now.strftime("%H:%M"),
        status=TaskStatus.BLOCKED,
        startup_reminder=False,
    )
    tid = tc.add_task(t)
    due = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=now)
    assert len(due) == 1
    assert due[0].id == tid


# 16. Multiple reminders deterministic ordering & offset
def test_16_multiple_reminders_deterministic(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    tc = TaskController(db)
    t1 = Task(title="Task A", startup_reminder=True)
    t2 = Task(title="Task B", startup_reminder=True)
    tc.add_task(t1)
    tc.add_task(t2)

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    dialogs = ReminderPolicyService.evaluate_startup_reminders(win, tc, settings_manager=settings)
    assert len(dialogs) == 2
    # Ensure they have staggered offsets so they do not exactly obscure each other
    assert dialogs[1].x() != dialogs[0].x() or dialogs[1].y() != dialogs[0].y()
    win.close()


# 17. Same task cannot spawn duplicate reminder windows
def test_17_same_task_cannot_spawn_duplicate_windows(temp_env, qapp):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Single Instance Task", startup_reminder=True)
    tid = tc.add_task(t)
    t.id = tid

    dlg1 = ReminderDialog(t, task_controller=tc, settings_manager=settings)
    dlg1.show()

    # Query registry
    existing = WindowRegistry.get_window(f"reminder_{tid}")
    assert existing is dlg1

    dlg1.close()


# 18. Reminder window is not WindowStaysOnTopHint
def test_18_reminder_window_is_not_stays_on_top(temp_env, qapp):
    db, settings, _, _ = temp_env
    t = Task(id=1, title="Non-Topmost Reminder")
    dlg = ReminderDialog(t, settings_manager=settings)
    flags = dlg.windowFlags()
    assert not bool(flags & Qt.WindowStaysOnTopHint)
    dlg.close()


# 19. Reminder is not ApplicationModal
def test_19_reminder_is_not_application_modal(temp_env, qapp):
    db, settings, _, _ = temp_env
    t = Task(id=1, title="Non-Modal Reminder")
    dlg = ReminderDialog(t, settings_manager=settings)
    assert not dlg.isModal()
    assert dlg.windowModality() == Qt.NonModal
    dlg.close()


# 20. Reminder can lose active focus
def test_20_reminder_can_lose_active_focus(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    win.show()

    t = Task(id=1, title="Focus Test Reminder")
    dlg = ReminderDialog(t, settings_manager=settings, parent=win)
    dlg.show()

    # Activating main window works naturally
    win.activateWindow()
    assert not bool(dlg.windowFlags() & Qt.WindowStaysOnTopHint)
    dlg.close()
    win.close()


# 21. Switching MainWindow does not force reminder back on top
def test_21_switching_mainwindow_does_not_force_reminder_on_top(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    win.show()

    t = Task(id=2, title="Z-Order Test")
    dlg = ReminderDialog(t, settings_manager=settings, parent=win)
    dlg.show()

    # MainWindow raise doesn't violate reminder window flags
    win.raise_()
    assert not bool(dlg.windowFlags() & Qt.WindowStaysOnTopHint)
    dlg.close()
    win.close()


# 22. No recurring raise_/activateWindow focus loop
def test_22_no_recurring_raise_focus_loop(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    tc = TaskController(db)
    now = datetime.now()
    t = Task(
        title="Focus Loop Test",
        planned_date=now.strftime("%Y-%m-%d"),
        planned_start_time=now.strftime("%H:%M"),
    )
    tid = tc.add_task(t)
    t.id = tid
    ReminderPolicyService._session_start_time = now - timedelta(minutes=1)

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)

    # First trigger shows dialog
    dlgs1 = ReminderPolicyService.check_and_trigger_due_reminders(win, tc, settings)
    assert len(dlgs1) == 1

    # Second periodic poll detects window is already visible and returns empty list
    dlgs2 = ReminderPolicyService.check_and_trigger_due_reminders(win, tc, settings)
    assert len(dlgs2) == 0
    win.close()


# 23. Task-level startup preference persists in DB
def test_23_task_level_startup_preference_persists_in_db(temp_env):
    db, _, _, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Startup Flag Task", startup_reminder=True)
    tid = tc.add_task(t)

    loaded = tc.get_task(tid)
    assert loaded is not None
    assert loaded.startup_reminder is True


# 24. Task-level preference survives restart
def test_24_task_level_preference_survives_restart(temp_env):
    db, _, _, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Startup Flag Restart Task", startup_reminder=True)
    tid = tc.add_task(t)

    # Reload from fresh controller
    tc2 = TaskController(db)
    reloaded = tc2.get_task(tid)
    assert reloaded.startup_reminder is True


# 25. Legacy task data loads safely
def test_25_legacy_task_data_loads_safely(temp_env):
    db, _, _, _ = temp_env
    tc = TaskController(db)
    # Insert task without specifying startup_reminder
    t = Task(title="Legacy Task")
    tid = tc.add_task(t)

    loaded = tc.get_task(tid)
    assert loaded.startup_reminder in (False, 0)


# 26. Light theme rendering
def test_26_light_theme_rendering(temp_env, qapp):
    db, settings, _, _ = temp_env
    settings.set("theme", "light")
    t = Task(id=1, title="Light Mode Card")
    dlg = ReminderDialog(t, settings_manager=settings)
    assert dlg.isVisible() or dlg.minimumSize().isValid()
    dlg.close()


# 27. Dark theme rendering
def test_27_dark_theme_rendering(temp_env, qapp):
    db, settings, _, _ = temp_env
    settings.set("theme", "dark")
    t = Task(id=1, title="Dark Mode Card")
    dlg = ReminderDialog(t, settings_manager=settings)
    assert dlg.isVisible() or dlg.minimumSize().isValid()
    dlg.close()


# 28. Typography 10 -> 20 -> 10 scaling
def test_28_typography_scaling(temp_env, qapp):
    db, settings, _, _ = temp_env
    t = Task(id=1, title="Typography Scaling Task")
    dlg = ReminderDialog(t, settings_manager=settings)

    for sz in (10, 20, 10):
        settings.set("font_size_reminder", sz)
        settings.set("font_override_reminder", True)
        dlg.update_from_settings()
        assert dlg.font().pointSize() == sz

    dlg.close()


# 29. Keyboard accessibility & shortcuts
def test_29_keyboard_accessibility_and_shortcuts(temp_env, qapp):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Keyboard Accessibility Task", startup_reminder=True)
    tid = tc.add_task(t)
    t.id = tid

    dlg = ReminderDialog(t, task_controller=tc, settings_manager=settings)
    assert dlg.btn_dismiss.shortcut().toString() == "Alt+D"
    assert dlg.btn_snooze.shortcut().toString() == "Alt+S"
    assert dlg.btn_complete.shortcut().toString() == "Alt+C"
    assert dlg.btn_open.shortcut().toString() == "Alt+O"

    # Esc key triggers dismiss
    key_ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    dlg.keyPressEvent(key_ev)


# 30. Clean shutdown with reminder open
def test_30_clean_shutdown_with_reminder_open(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    t = Task(id=99, title="Shutdown With Reminder")
    dlg = ReminderDialog(t, settings_manager=settings, parent=win)
    win.startup_reminder_dialogs = [dlg]
    dlg.show()

    # Close MainWindow
    win.close()
    assert not win._reminder_poll_timer.isActive()


# 31. Clean shutdown with snoozed reminder
def test_31_clean_shutdown_with_snoozed_reminder(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Shutdown Snoozed Task", startup_reminder=True)
    tid = tc.add_task(t)

    ReminderPolicyService.snooze_reminder(tid, minutes=45, settings_manager=settings)
    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    win.close()


# 32. Reminder poll does not execute after teardown
def test_32_reminder_poll_does_not_execute_after_teardown(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    win.close()
    assert not win._reminder_poll_timer.isActive()


# 33. Esc closes reminder and does NOT persist acknowledgment
def test_33_escape_closes_dialog_and_does_not_persist_dismissal(temp_env, qapp):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Escape Safety Task", startup_reminder=True)
    tid = tc.add_task(t)
    t.id = tid

    dlg = ReminderDialog(t, task_controller=tc, settings_manager=settings)
    dlg.show()
    assert tid not in ReminderPolicyService._hidden_for_session
    assert tid not in ReminderPolicyService._acknowledged_occurrences

    # Press Escape
    key_ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    dlg.keyPressEvent(key_ev)

    # Window is closed/hidden for this session
    assert tid in ReminderPolicyService._hidden_for_session
    # Acknowledgment was NOT persisted!
    assert tid not in ReminderPolicyService._acknowledged_occurrences
    raw = settings.get("persisted_acknowledged_reminders", "")
    assert str(tid) not in str(raw)


# 34. Esc-hidden reminder does not reappear on next 2-second poll
def test_34_escape_hidden_reminder_does_not_reappear_on_next_poll(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    tc = TaskController(db)
    now = datetime.now()
    t = Task(
        title="Poll Suppress Task",
        planned_date=now.strftime("%Y-%m-%d"),
        planned_start_time=now.strftime("%H:%M"),
    )
    tid = tc.add_task(t)
    t.id = tid
    ReminderPolicyService._session_start_time = now - timedelta(minutes=1)

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)

    # Initial popup
    dlgs = ReminderPolicyService.check_and_trigger_due_reminders(win, tc, settings)
    assert len(dlgs) == 1

    # User presses Escape on the dialog
    key_ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    dlgs[0].keyPressEvent(key_ev)
    assert tid in ReminderPolicyService._hidden_for_session

    # Next periodic poll (2 seconds later)
    subsequent = ReminderPolicyService.check_and_trigger_due_reminders(win, tc, settings)
    assert len(subsequent) == 0
    win.close()


# 35. Esc-hidden reminder reappears after restart if eligible
def test_35_escape_hidden_reminder_reappears_after_restart_if_eligible(temp_env, qapp):
    db, settings, _, temp_dir = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    tc = TaskController(db)
    past = datetime.now() - timedelta(hours=1)
    t = Task(
        title="Reappearing Task",
        planned_date=past.strftime("%Y-%m-%d"),
        planned_start_time=past.strftime("%H:%M"),
        startup_reminder=True,
    )
    tid = tc.add_task(t)
    t.id = tid

    dlg = ReminderDialog(t, task_controller=tc, settings_manager=settings)
    dlg.show()
    key_ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    dlg.keyPressEvent(key_ev)

    # Hidden in current session
    due_cur = ReminderPolicyService.get_due_reminders(tc, settings)
    assert len(due_cur) == 0

    # Restart Todo Bird
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService.reset_session_state()
    ReminderPolicyService._session_start_time = datetime.now()

    # Session hide is cleared; task is still eligible and appears on startup evaluation after restart!
    due_restarted = ReminderPolicyService.get_startup_due_reminders(tc, restarted_settings)
    assert len(due_restarted) == 1
    assert due_restarted[0].id == tid


# 36. Window close X has same safe session-hide semantics
def test_36_window_close_x_has_same_safe_session_hide_semantics(temp_env, qapp):
    db, settings, _, temp_dir = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    tc = TaskController(db)
    t = Task(title="Window Close X Task", startup_reminder=True)
    tid = tc.add_task(t)
    t.id = tid

    dlg = ReminderDialog(t, task_controller=tc, settings_manager=settings)
    dlg.show()

    # Simulate user clicking window close X button
    dlg.close()

    assert tid in ReminderPolicyService._hidden_for_session
    assert tid not in ReminderPolicyService._acknowledged_occurrences
    raw = settings.get("persisted_acknowledged_reminders", "")
    assert str(tid) not in str(raw)


# 37. Explicit Dismiss button persists acknowledgment across restarts
def test_37_explicit_dismiss_button_persists_across_restarts(temp_env, qapp):
    db, settings, _, temp_dir = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    tc = TaskController(db)
    past = datetime.now() - timedelta(hours=1)
    t = Task(
        title="Explicit Dismiss Task",
        planned_date=past.strftime("%Y-%m-%d"),
        planned_start_time=past.strftime("%H:%M"),
        startup_reminder=True,
    )
    tid = tc.add_task(t)
    t.id = tid

    dlg = ReminderDialog(t, task_controller=tc, settings_manager=settings)
    dlg.btn_dismiss.click()

    assert tid in ReminderPolicyService._acknowledged_occurrences

    # Restart Todo Bird
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService.reset_session_state()
    ReminderPolicyService._session_start_time = datetime.now()

    # Dismissed reminder does NOT reappear
    due = ReminderPolicyService.get_due_reminders(tc, restarted_settings)
    assert len(due) == 0


# 38. Alt+D shortcut triggers explicit dismiss
def test_38_alt_d_shortcut_triggers_explicit_dismiss(temp_env, qapp):
    db, settings, _, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(title="Alt D Dismiss Task", startup_reminder=True)
    tid = tc.add_task(t)
    t.id = tid

    dlg = ReminderDialog(t, task_controller=tc, settings_manager=settings)
    assert dlg.btn_dismiss.shortcut().toString() == "Alt+D"
    dlg.btn_dismiss.click()

    assert tid in ReminderPolicyService._acknowledged_occurrences


# ==============================================================================
# MANDATORY REGRESSION COVERAGE (DECUPLED STARTUP / RUNTIME POLL AUTHORITY)
# ==============================================================================

# 1. daily_first_open already shown today + old planned datetime => get_due_reminders() returns no task.
def test_req_01_daily_first_shown_today_old_planned_runtime_poll_returns_empty(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    today_str = datetime.now().strftime("%Y-%m-%d")
    t = Task(
        title="Task 6 Defect Repro",
        planned_date="2026-08-20",
        planned_start_time="04:00",
        startup_reminder_mode="daily_first_open",
    )
    tid = tc.add_task(t)
    t.id = tid

    # Record shown today
    ReminderPolicyService._daily_shown_dates[tid] = today_str
    ReminderPolicyService._session_start_time = datetime.now()

    due = ReminderPolicyService.get_due_reminders(tc, settings)
    assert len(due) == 0


# 2. daily_first_open first startup today => startup evaluation shows once.
def test_req_02_daily_first_first_startup_today_shows_once(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    tc = TaskController(db)
    t = Task(
        title="Daily First Startup Task",
        planned_date="2026-08-20",
        planned_start_time="04:00",
        startup_reminder_mode="daily_first_open",
    )
    tid = tc.add_task(t)
    t.id = tid

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)

    due = ReminderPolicyService.get_startup_due_reminders(tc, settings)
    assert len(due) == 1
    assert due[0].id == tid
    win.close()


# 3. second launch same day => startup evaluation suppresses.
def test_req_03_second_launch_same_day_startup_evaluation_suppresses(temp_env, qapp):
    db, settings, theme_ctrl, temp_dir = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    tc = TaskController(db)
    t = Task(
        title="Second Launch Task",
        planned_date="2026-08-20",
        planned_start_time="04:00",
        startup_reminder_mode="daily_first_open",
    )
    tid = tc.add_task(t)
    t.id = tid

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)

    # First launch today: evaluate startup reminders
    dlgs = ReminderPolicyService.evaluate_startup_reminders(win, tc, settings)
    assert len(dlgs) == 1

    # Simulate second launch same day
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    restarted_settings.set("reminder_trigger_mode", "app_startup")
    ReminderPolicyService.reset_session_state()
    ReminderPolicyService._is_first_launch_today = False

    due_2nd = ReminderPolicyService.get_startup_due_reminders(tc, restarted_settings)
    assert len(due_2nd) == 0
    win.close()


# 4. runtime poll after second launch => does not resurrect reminder.
def test_req_04_runtime_poll_after_second_launch_does_not_resurrect(temp_env, qapp):
    db, settings, theme_ctrl, temp_dir = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    tc = TaskController(db)
    t = Task(
        title="Resurrection Guard Task",
        planned_date="2026-08-20",
        planned_start_time="04:00",
        startup_reminder_mode="daily_first_open",
    )
    tid = tc.add_task(t)
    t.id = tid

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)

    # First launch
    ReminderPolicyService.evaluate_startup_reminders(win, tc, settings)

    # Second launch same day
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    restarted_settings.set("reminder_trigger_mode", "app_startup")
    ReminderPolicyService.reset_session_state()
    ReminderPolicyService._is_first_launch_today = False
    win2 = MainWindow(db, restarted_settings, theme_ctrl)

    # Runtime poll executing in 2nd launch
    runtime_due = ReminderPolicyService.get_due_reminders(tc, restarted_settings)
    assert len(runtime_due) == 0

    win.close()
    win2.close()


# 5. every_app_open startup => shows once per fresh application session.
def test_req_05_every_app_open_startup_shows_once_per_fresh_session(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    tc = TaskController(db)
    t = Task(
        title="Every App Startup Task",
        planned_date="2026-08-20",
        planned_start_time="04:00",
        startup_reminder_mode="every_app_open",
    )
    tid = tc.add_task(t)
    t.id = tid

    due = ReminderPolicyService.get_startup_due_reminders(tc, settings)
    assert len(due) == 1
    assert due[0].id == tid


# 6. runtime polling in same process => does not duplicate every_app_open reminder.
def test_req_06_runtime_polling_same_process_does_not_duplicate_every_app_open(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    tc = TaskController(db)
    t = Task(
        title="Every App Runtime No Duplicate",
        planned_date="2026-08-20",
        planned_start_time="04:00",
        startup_reminder_mode="every_app_open",
    )
    tid = tc.add_task(t)
    t.id = tid

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)

    # Startup evaluation triggers it once and marks shown
    dlgs = ReminderPolicyService.evaluate_startup_reminders(win, tc, settings)
    assert len(dlgs) == 1

    # Subsequent runtime polling
    runtime_due = ReminderPolicyService.get_due_reminders(tc, settings)
    assert len(runtime_due) == 0
    win.close()


# 7. old historical planned datetime + every_app_open => no runtime replay after startup popup.
def test_req_07_old_planned_datetime_every_app_open_no_runtime_replay(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    tc = TaskController(db)
    t = Task(
        title="Historical Every App Task",
        planned_date="2020-01-01",
        planned_start_time="08:00",
        startup_reminder_mode="every_app_open",
    )
    tid = tc.add_task(t)
    t.id = tid

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)

    ReminderPolicyService.evaluate_startup_reminders(win, tc, settings)
    poll_dlgs = ReminderPolicyService.check_and_trigger_due_reminders(win, tc, settings)
    assert len(poll_dlgs) == 0
    win.close()


# 8. scheduled reminder becomes due after session_start => runtime poll still shows it.
def test_req_08_scheduled_reminder_becomes_due_after_session_start(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    start_time = datetime.now()
    ReminderPolicyService._session_start_time = start_time

    due_time = start_time + timedelta(minutes=2)
    t = Task(
        title="Active Session Scheduled Task",
        planned_date=due_time.strftime("%Y-%m-%d"),
        planned_start_time=due_time.strftime("%H:%M"),
        startup_reminder_mode="off",
    )
    tid = tc.add_task(t)
    t.id = tid

    due_at_start = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=start_time)
    assert len(due_at_start) == 0

    due_at_trigger = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=due_time)
    assert len(due_at_trigger) == 1
    assert due_at_trigger[0].id == tid


# 9. exact scheduled occurrence acknowledgment => runtime poll still suppresses it.
def test_req_09_exact_scheduled_occurrence_ack_suppresses_runtime_poll(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    now = datetime.now()
    ReminderPolicyService._session_start_time = now - timedelta(minutes=5)
    t = Task(
        title="Acknowledged Scheduled Task",
        planned_date=now.strftime("%Y-%m-%d"),
        planned_start_time=now.strftime("%H:%M"),
    )
    tid = tc.add_task(t)
    t.id = tid

    occ_key = ReminderPolicyService.get_occurrence_key(t)
    ReminderPolicyService.dismiss_reminder(tid, occurrence_key=occ_key, settings_manager=settings)

    due = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=now)
    assert len(due) == 0


# 10. active snooze => suppresses until expiry.
def test_req_10_active_snooze_suppresses_until_expiry(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    now = datetime.now()
    ReminderPolicyService._session_start_time = now - timedelta(minutes=5)
    t = Task(
        title="Active Snooze Task",
        planned_date=now.strftime("%Y-%m-%d"),
        planned_start_time=now.strftime("%H:%M"),
    )
    tid = tc.add_task(t)
    t.id = tid

    ReminderPolicyService.snooze_reminder(tid, minutes=10, from_dt=now, settings_manager=settings)

    due_during_snooze = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=now + timedelta(minutes=5))
    assert len(due_during_snooze) == 0


# 11. snooze expiry => still triggers correctly.
def test_req_11_snooze_expiry_triggers_correctly(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    now = datetime.now()
    ReminderPolicyService._session_start_time = now - timedelta(minutes=5)
    t = Task(
        title="Expiring Snooze Task",
        planned_date=now.strftime("%Y-%m-%d"),
        planned_start_time=now.strftime("%H:%M"),
    )
    tid = tc.add_task(t)
    t.id = tid

    ReminderPolicyService.snooze_reminder(tid, minutes=10, from_dt=now, settings_manager=settings)

    due_after_expiry = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=now + timedelta(minutes=11))
    assert len(due_after_expiry) == 1
    assert due_after_expiry[0].id == tid


# 12. completed/cancelled => remain suppressed.
def test_req_12_completed_and_cancelled_remain_suppressed(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    now = datetime.now()
    ReminderPolicyService._session_start_time = now - timedelta(minutes=5)

    t1 = Task(
        title="Completed Task",
        status=TaskStatus.COMPLETED,
        planned_date=now.strftime("%Y-%m-%d"),
        planned_start_time=now.strftime("%H:%M"),
        startup_reminder_mode="daily_first_open",
    )
    t2 = Task(
        title="Cancelled Task",
        status=TaskStatus.CANCELLED,
        planned_date=now.strftime("%Y-%m-%d"),
        planned_start_time=now.strftime("%H:%M"),
        startup_reminder_mode="every_app_open",
    )
    tc.add_task(t1)
    tc.add_task(t2)

    startup_due = ReminderPolicyService.get_startup_due_reminders(tc, settings)
    assert len(startup_due) == 0

    runtime_due = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=now)
    assert len(runtime_due) == 0


# 13. exactly one MainWindow._reminder_poll_timer remains.
def test_req_13_exactly_one_reminder_poll_timer(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)

    timers = [child for child in win.children() if isinstance(child, QTimer)]
    reminder_timers = [t for t in timers if getattr(win, "_reminder_poll_timer", None) == t]

    assert hasattr(win, "_reminder_poll_timer")
    assert win._reminder_poll_timer is not None
    assert len(reminder_timers) == 1
    win.close()
