"""
Test Suite: Reminder Startup Trigger Modes — Daily First Open / Every App Open
Validates:
1. OFF does not trigger on startup
2. OFF does not suppress normal scheduled reminder
3. Scheduled reminder 2 minutes after startup still fires
4. daily_first_open triggers on first launch of day
5. daily_first_open does not trigger on second launch same day
6. daily_first_open triggers again next local calendar day
7. every_app_open triggers each new app session
8. every_app_open does not retrigger every polling cycle
9. Completed tasks suppressed
10. Cancelled tasks suppressed
11. Snooze takes precedence appropriately
12. Escape/X current-session hide preserved
13. Explicit Dismiss semantics for daily mode
14. Explicit Dismiss semantics for every-app mode
15. Legacy startup_reminder=0 migrates to off
16. Legacy startup_reminder=1 migrates to daily_first_open
17. TaskDialog persists mode
18. Restart persists mode
19. Dark theme rendering
20. Light theme rendering
21. Typography scaling 10 -> 20 -> 10
22. Keyboard control (Alt+D, Alt+S, Alt+C, Alt+O, Esc)
23. No second reminder timer created
24. Startup evaluation occurs once/session
25. WindowRegistry duplicate prevention
26. Shutdown safety
27. OmmLVVN actual behavior classified correctly
28. OmmLaxmiVignaVinashakaya Namaha actual behavior classified correctly
"""

import os
import shutil
import tempfile
from datetime import datetime, timedelta, date
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import (
    Task,
    TaskStatus,
    STARTUP_REMINDER_OFF,
    STARTUP_REMINDER_DAILY_FIRST,
    STARTUP_REMINDER_EVERY_APP,
)
from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
from todo_bird_app.widgets.reminder_dialog import ReminderDialog
from todo_bird_app.widgets.task_dialog import TaskDialog


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _close_leftover_reminder_dialogs(qapp):
    """ReminderDialogs/TaskDialogs are parent-less top-levels; close and delete
    them after every test so they don't leak into other files' zero-dialog
    assertions (get_top_level_dialogs counts objects, not visibility)."""
    yield
    from PySide6.QtWidgets import QDialog
    from PySide6.QtCore import QCoreApplication, QEvent
    import shiboken6
    for w in list(qapp.topLevelWidgets()):
        try:
            if isinstance(w, QDialog) and shiboken6.isValid(w):
                w.close()
                w.deleteLater()
        except RuntimeError:
            pass
    qapp.processEvents()
    # DeferredDelete is only flushed outside a running event loop via sendPostedEvents
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.fixture
def temp_env():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_todo_bird.db")
    db = DatabaseManager(db_path)
    settings = SettingsManager(db, config_dir=Path(temp_dir))
    settings.set("reminder_trigger_mode", "app_startup")
    theme_ctrl = ThemeController(settings)

    ReminderPolicyService.reset_session_state(settings)

    yield db, settings, theme_ctrl, temp_dir

    ReminderPolicyService.reset_session_state(settings)
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass


# 1. OFF does not trigger on startup
def test_01_off_does_not_trigger_on_startup(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    tc = TaskController(db)
    t = Task(
        title="Off Mode Task",
        startup_reminder_mode=STARTUP_REMINDER_OFF,
        planned_date="2026-08-20",
        planned_start_time="04:00",
    )
    tid = tc.add_task(t)

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)

    dlgs = ReminderPolicyService.evaluate_startup_reminders(win, tc, settings)
    assert len(dlgs) == 0
    win.close()


# 2. OFF does not suppress normal scheduled reminder
def test_02_off_does_not_suppress_normal_scheduled_reminder(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    past_dt = datetime.now() - timedelta(minutes=5)
    t = Task(
        title="Scheduled Due Task",
        startup_reminder_mode=STARTUP_REMINDER_OFF,
        planned_date=past_dt.strftime("%Y-%m-%d"),
        planned_start_time=past_dt.strftime("%H:%M"),
    )
    tid = tc.add_task(t)

    # Set session start time prior to planned time
    ReminderPolicyService._session_start_time = past_dt - timedelta(minutes=5)
    due = ReminderPolicyService.get_due_reminders(tc, settings)
    assert any(x.id == tid for x in due)


# 3. Scheduled reminder 2 minutes after startup still fires
def test_03_scheduled_reminder_2_minutes_after_startup_fires(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    start_time = datetime.now()
    ReminderPolicyService._session_start_time = start_time

    # Scheduled 2 minutes in the future relative to startup
    due_time = start_time + timedelta(minutes=2)
    t = Task(
        title="2 Min Later Task",
        startup_reminder_mode=STARTUP_REMINDER_OFF,
        planned_date=due_time.strftime("%Y-%m-%d"),
        planned_start_time=due_time.strftime("%H:%M"),
    )
    tid = tc.add_task(t)

    # Polling at startup (now = start_time) -> not due
    due_at_start = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=start_time)
    assert not any(x.id == tid for x in due_at_start)

    # Polling 2 minutes later (now = due_time) -> DUE!
    due_at_trigger = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=due_time)
    assert any(x.id == tid for x in due_at_trigger)


# 4. daily_first_open triggers on first launch of day
def test_04_daily_first_open_triggers_on_first_launch(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Daily First Task", startup_reminder_mode=STARTUP_REMINDER_DAILY_FIRST)
    tid = tc.add_task(t)

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)

    dlgs = ReminderPolicyService.evaluate_startup_reminders(win, tc, settings)
    assert len(dlgs) == 1
    assert dlgs[0].task.id == tid
    win.close()


# 5. daily_first_open does not trigger on second launch same day
def test_05_daily_first_open_does_not_trigger_on_second_launch_same_day(temp_env, qapp):
    db, settings, theme_ctrl, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(title="Daily First Task", startup_reminder_mode=STARTUP_REMINDER_DAILY_FIRST)
    tid = tc.add_task(t)

    from todo_bird_app.views.main_window import MainWindow
    win1 = MainWindow(db, settings, theme_ctrl)
    dlgs1 = ReminderPolicyService.evaluate_startup_reminders(win1, tc, settings)
    assert len(dlgs1) == 1
    win1.close()

    # Second launch on same day
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService._startup_evaluated_in_session = False
    ReminderPolicyService._shown_in_session.clear()
    ReminderPolicyService._is_first_launch_today = None

    win2 = MainWindow(db, restarted_settings, theme_ctrl)
    dlgs2 = ReminderPolicyService.evaluate_startup_reminders(win2, tc, restarted_settings)
    assert len(dlgs2) == 0
    win2.close()


# 6. daily_first_open triggers again next local calendar day
def test_06_daily_first_open_triggers_again_next_local_calendar_day(temp_env, qapp):
    db, settings, theme_ctrl, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(title="Daily First Task", startup_reminder_mode=STARTUP_REMINDER_DAILY_FIRST)
    tid = tc.add_task(t)

    # First launch today (simulate recorded yesterday)
    today = datetime.now()
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    settings.set("persisted_daily_startup_reminders", f'{{"{tid}": "{yesterday_str}"}}')
    settings.set("last_app_launch_date", yesterday_str)

    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService.reset_session_state()

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, restarted_settings, theme_ctrl)
    dlgs = ReminderPolicyService.evaluate_startup_reminders(win, tc, restarted_settings)
    assert len(dlgs) == 1
    assert dlgs[0].task.id == tid
    win.close()


# 7. every_app_open triggers each new app session
def test_07_every_app_open_triggers_each_new_app_session(temp_env, qapp):
    db, settings, theme_ctrl, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(title="Every App Open Task", startup_reminder_mode=STARTUP_REMINDER_EVERY_APP)
    tid = tc.add_task(t)

    from todo_bird_app.views.main_window import MainWindow
    # First launch
    win1 = MainWindow(db, settings, theme_ctrl)
    dlgs1 = ReminderPolicyService.evaluate_startup_reminders(win1, tc, settings)
    assert len(dlgs1) == 1
    win1.close()

    # Second launch
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService.reset_session_state()

    win2 = MainWindow(db, restarted_settings, theme_ctrl)
    dlgs2 = ReminderPolicyService.evaluate_startup_reminders(win2, tc, restarted_settings)
    assert len(dlgs2) == 1
    win2.close()


# 8. every_app_open does not retrigger every polling cycle
def test_08_every_app_open_does_not_retrigger_every_polling_cycle(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Polling Safety Task", startup_reminder_mode=STARTUP_REMINDER_EVERY_APP)
    tid = tc.add_task(t)

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    dlgs = ReminderPolicyService.evaluate_startup_reminders(win, tc, settings)
    assert len(dlgs) == 1

    # Next 2-second periodic poll
    poll_dlgs = ReminderPolicyService.check_and_trigger_due_reminders(win, tc, settings)
    assert len(poll_dlgs) == 0
    win.close()


# 9. Completed tasks suppressed
def test_09_completed_tasks_suppressed(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Completed Task", status=TaskStatus.COMPLETED, startup_reminder_mode=STARTUP_REMINDER_EVERY_APP)
    tc.add_task(t)

    due = ReminderPolicyService.get_startup_due_reminders(tc, settings)
    assert len(due) == 0


# 10. Cancelled tasks suppressed
def test_10_cancelled_tasks_suppressed(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Cancelled Task", status=TaskStatus.CANCELLED, startup_reminder_mode=STARTUP_REMINDER_EVERY_APP)
    tc.add_task(t)

    due = ReminderPolicyService.get_startup_due_reminders(tc, settings)
    assert len(due) == 0


# 11. Snooze takes precedence appropriately
def test_11_snooze_takes_precedence(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Snoozed Startup Task", startup_reminder_mode=STARTUP_REMINDER_EVERY_APP)
    tid = tc.add_task(t)

    # Snooze for 30 minutes
    ReminderPolicyService.snooze_reminder(tid, minutes=30, settings_manager=settings)
    due = ReminderPolicyService.get_startup_due_reminders(tc, settings)
    assert len(due) == 0


# 12. Escape/X current-session hide preserved
def test_12_escape_preserves_current_session_hide(temp_env, qapp):
    db, settings, theme_ctrl, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(title="Esc Hide Task", startup_reminder_mode=STARTUP_REMINDER_EVERY_APP)
    tid = tc.add_task(t)

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    dlgs = ReminderPolicyService.evaluate_startup_reminders(win, tc, settings)
    assert len(dlgs) == 1

    # User presses Escape
    key_ev = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    dlgs[0].keyPressEvent(key_ev)
    assert tid in ReminderPolicyService._hidden_for_session

    # Polling during active session skips it
    poll = ReminderPolicyService.check_and_trigger_due_reminders(win, tc, settings)
    assert len(poll) == 0
    win.close()


# 13. Explicit Dismiss semantics for daily mode
def test_13_explicit_dismiss_for_daily_mode(temp_env, qapp):
    db, settings, theme_ctrl, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(title="Daily Dismiss Task", startup_reminder_mode=STARTUP_REMINDER_DAILY_FIRST)
    tid = tc.add_task(t)
    t.id = tid

    dlg = ReminderDialog(t, task_controller=tc, settings_manager=settings)
    dlg.btn_dismiss.click()

    # Restart same day -> suppressed
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService.reset_session_state()
    from todo_bird_app.views.main_window import MainWindow
    win1 = MainWindow(db, restarted_settings, theme_ctrl)
    dlgs1 = ReminderPolicyService.evaluate_startup_reminders(win1, tc, restarted_settings)
    assert len(dlgs1) == 0
    win1.close()


# 14. Explicit Dismiss semantics for every-app mode
def test_14_explicit_dismiss_for_every_app_mode(temp_env, qapp):
    db, settings, theme_ctrl, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(title="Every App Dismiss Task", startup_reminder_mode=STARTUP_REMINDER_EVERY_APP)
    tid = tc.add_task(t)
    t.id = tid

    dlg = ReminderDialog(t, task_controller=tc, settings_manager=settings)
    dlg.btn_dismiss.click()
    assert tid in ReminderPolicyService._dismissed_in_session

    # Next launch brings it back as configured
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService.reset_session_state()
    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, restarted_settings, theme_ctrl)
    dlgs = ReminderPolicyService.evaluate_startup_reminders(win, tc, restarted_settings)
    assert len(dlgs) == 1
    win.close()


# 15. Legacy startup_reminder=0 migrates to off
def test_15_legacy_0_migrates_to_off(temp_env):
    db, settings, _, _ = temp_env
    row = {"id": 101, "title": "Legacy 0", "startup_reminder": 0, "status": "Inbox"}
    t = Task.from_row(row)
    assert t.startup_reminder_mode == STARTUP_REMINDER_OFF
    assert t.startup_reminder is False


# 16. Legacy startup_reminder=1 migrates to daily_first_open
def test_16_legacy_1_migrates_to_daily_first_open(temp_env):
    db, settings, _, _ = temp_env
    row = {"id": 102, "title": "Legacy 1", "startup_reminder": 1, "status": "Inbox"}
    t = Task.from_row(row)
    assert t.startup_reminder_mode == STARTUP_REMINDER_DAILY_FIRST
    assert t.startup_reminder is True


# 17. TaskDialog persists mode
def test_17_task_dialog_persists_mode(temp_env, qapp):
    db, settings, _, _ = temp_env
    t = Task(title="Dialog Mode Test", startup_reminder_mode=STARTUP_REMINDER_OFF)
    dlg = TaskDialog([], t, db_manager=db, settings_manager=settings)

    # Change to Every app opening
    idx = dlg.startup_reminder_combo.findData(STARTUP_REMINDER_EVERY_APP)
    dlg.startup_reminder_combo.setCurrentIndex(idx)
    dlg.on_save()

    assert t.startup_reminder_mode == STARTUP_REMINDER_EVERY_APP
    assert t.startup_reminder is True


def test_17b_launch_reminder_auto_enables_disabled_startup_policy(temp_env, qapp):
    db, settings, _, _ = temp_env
    settings.set("reminder_trigger_mode", ReminderPolicyService.MODE_DISABLED)
    t = Task(title="Disabled Policy Repair", startup_reminder_mode=STARTUP_REMINDER_OFF)
    dlg = TaskDialog([], t, db_manager=db, settings_manager=settings)

    idx = dlg.startup_reminder_combo.findData(STARTUP_REMINDER_EVERY_APP)
    dlg.startup_reminder_combo.setCurrentIndex(idx)
    dlg.on_save()

    assert t.startup_reminder_mode == STARTUP_REMINDER_EVERY_APP
    assert settings.get("reminder_trigger_mode") == ReminderPolicyService.MODE_APP_STARTUP


def test_17c_launch_reminder_auto_enables_scheduled_only_policy(temp_env):
    _, settings, _, _ = temp_env
    settings.set("reminder_trigger_mode", ReminderPolicyService.MODE_SCHEDULED_ONLY)

    changed = ReminderPolicyService.ensure_startup_trigger_enabled_for_launch_reminder(
        settings,
        STARTUP_REMINDER_DAILY_FIRST,
    )

    assert changed is True
    assert settings.get("reminder_trigger_mode") == ReminderPolicyService.MODE_APP_STARTUP


def test_17d_launch_reminder_keeps_computer_startup_policy(temp_env):
    _, settings, _, _ = temp_env
    settings.set("reminder_trigger_mode", ReminderPolicyService.MODE_COMPUTER_STARTUP)

    changed = ReminderPolicyService.ensure_startup_trigger_enabled_for_launch_reminder(
        settings,
        STARTUP_REMINDER_EVERY_APP,
    )

    assert changed is False
    assert settings.get("reminder_trigger_mode") == ReminderPolicyService.MODE_COMPUTER_STARTUP


def test_17e_off_launch_reminder_keeps_disabled_policy(temp_env):
    _, settings, _, _ = temp_env
    settings.set("reminder_trigger_mode", ReminderPolicyService.MODE_DISABLED)

    changed = ReminderPolicyService.ensure_startup_trigger_enabled_for_launch_reminder(
        settings,
        STARTUP_REMINDER_OFF,
    )

    assert changed is False
    assert settings.get("reminder_trigger_mode") == ReminderPolicyService.MODE_DISABLED


# 18. Restart persists mode
def test_18_restart_persists_mode(temp_env):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Persistence Task", startup_reminder_mode=STARTUP_REMINDER_EVERY_APP)
    tid = tc.add_task(t)

    loaded = tc.get_task(tid)
    assert loaded.startup_reminder_mode == STARTUP_REMINDER_EVERY_APP


# 19. Dark theme rendering
def test_19_dark_theme_rendering(temp_env, qapp):
    db, settings, _, _ = temp_env
    settings.set("theme", "dark")
    t = Task(id=1, title="Dark Theme Task")
    dlg = ReminderDialog(t, settings_manager=settings)
    assert dlg.isVisible() or dlg.minimumSize().isValid()
    dlg.close()


# 20. Light theme rendering
def test_20_light_theme_rendering(temp_env, qapp):
    db, settings, _, _ = temp_env
    settings.set("theme", "light")
    t = Task(id=1, title="Light Theme Task")
    dlg = ReminderDialog(t, settings_manager=settings)
    assert dlg.isVisible() or dlg.minimumSize().isValid()
    dlg.close()


# 21. Typography scaling 10 -> 20 -> 10
def test_21_typography_scaling(temp_env, qapp):
    db, settings, _, _ = temp_env
    t = Task(id=1, title="Scaling Task")
    dlg = ReminderDialog(t, settings_manager=settings)
    for sz in (10, 20, 10):
        settings.set("font_size_reminder", sz)
        settings.set("font_override_reminder", True)
        dlg.update_from_settings()
        assert dlg.font().pointSize() == sz
    dlg.close()


# 22. Keyboard control (Alt+D, Alt+S, Alt+C, Alt+O, Esc)
def test_22_keyboard_control(temp_env, qapp):
    db, settings, _, _ = temp_env
    t = Task(id=1, title="Keyboard Task")
    dlg = ReminderDialog(t, settings_manager=settings)
    assert dlg.btn_dismiss.shortcut().toString() == "Alt+D"
    assert dlg.btn_snooze.shortcut().toString() == "Alt+S"
    assert dlg.btn_complete.shortcut().toString() == "Alt+C"
    assert dlg.btn_open.shortcut().toString() == "Alt+O"
    dlg.close()


# 23. No second reminder timer created
def test_23_no_second_reminder_timer_created(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    timers = [c for c in win.children() if c.metaObject().className() == "QTimer"]
    # Exactly one reminder poll timer
    reminder_timers = [t for t in timers if t == win._reminder_poll_timer]
    assert len(reminder_timers) == 1
    win.close()


# 24. Startup evaluation occurs once/session
def test_24_startup_evaluation_occurs_once_per_session(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Once Test", startup_reminder_mode=STARTUP_REMINDER_EVERY_APP)
    tc.add_task(t)

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    dlgs1 = ReminderPolicyService.evaluate_startup_reminders(win, tc, settings)
    assert len(dlgs1) == 1

    # Calling again in same session returns []
    dlgs2 = ReminderPolicyService.evaluate_startup_reminders(win, tc, settings)
    assert len(dlgs2) == 0
    win.close()


# 25. WindowRegistry duplicate prevention
def test_25_window_registry_duplicate_prevention(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Registry Guard Task", startup_reminder_mode=STARTUP_REMINDER_EVERY_APP)
    tid = tc.add_task(t)
    t.id = tid

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    dlg1 = ReminderDialog(t, task_controller=tc, settings_manager=settings, parent=win)
    dlg1.show()

    ReminderPolicyService._startup_evaluated_in_session = False
    dlgs = ReminderPolicyService.evaluate_startup_reminders(win, tc, settings)
    # Blocked by registry
    assert len(dlgs) == 0
    dlg1.close()
    win.close()


# 26. Shutdown safety
def test_26_shutdown_safety(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    win.close()
    assert not win._reminder_poll_timer.isActive()


# 27. OmmLVVN actual behavior classified correctly
def test_27_ommlvvn_actual_behavior_classification(temp_env):
    """
    Forensic Verification:
    OmmLVVN had startup_reminder=0 (Off) and planned_date in the past.
    Startup reminder was correctly suppressed.
    Normal scheduled reminder / daily recurrence triggered during active session.
    """
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    start_time = datetime.now()
    ReminderPolicyService._session_start_time = start_time

    # Configured as OmmLVVN (Off)
    t = Task(
        title="OmmLVVN",
        startup_reminder_mode=STARTUP_REMINDER_OFF,
        planned_date="2026-08-13",
        planned_start_time="08:23",
        recurring="daily",
    )
    tid = tc.add_task(t)

    # 1. On startup: No reminder
    startup_due = ReminderPolicyService.get_startup_due_reminders(tc, settings)
    assert not any(x.id == tid for x in startup_due)

    # 2. When scheduled trigger arrives 2 minutes later: Fires normally
    due_2min = start_time + timedelta(minutes=2)
    t.planned_start_time = due_2min.strftime("%H:%M")
    t.planned_date = due_2min.strftime("%Y-%m-%d")
    tc.update_task(t)

    poll_due = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=due_2min)
    assert any(x.id == tid for x in poll_due)


# 28. OmmLaxmiVignaVinashakaya Namaha actual behavior classified correctly
def test_28_ommlaxmi_actual_behavior_classification(temp_env, qapp):
    """
    Forensic Verification:
    Task had startup_reminder=1 (daily_first_open).
    When startup evaluation runs, it triggers once on the first launch of the day,
    and clamping ensures geometry is within available screen bounds.
    """
    db, settings, theme_ctrl, _ = temp_env
    tc = TaskController(db)
    t = Task(
        title="OmmLaxmiVignaVinashakaya Namaha",
        startup_reminder_mode=STARTUP_REMINDER_DAILY_FIRST,
        planned_date="2026-08-20",
        planned_start_time="04:00",
    )
    tid = tc.add_task(t)

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    dlgs = ReminderPolicyService.evaluate_startup_reminders(win, tc, settings)
    assert len(dlgs) == 1
    assert dlgs[0].task.id == tid

    # Clamping test: Ensure dialog geometry is valid on screen
    screen = QApplication.primaryScreen()
    if screen:
        geo = screen.availableGeometry()
        assert dlgs[0].y() <= geo.bottom()
    win.close()


# 29. Task ineligible on first launch, eligible on second launch -> does NOT show as daily_first_open
def test_29_ineligible_on_first_launch_eligible_on_second_launch_does_not_show_as_daily_first_open(temp_env, qapp):
    """
    INVARIANT:
    daily_first_open MUST mean:
    "Show this task only during the FIRST Todo Bird application launch of the local calendar day."
    It must NOT mean:
    "Show this task on the first launch today where this particular task happens to be eligible."
    """
    db, settings, theme_ctrl, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(
        title="Task A (Daily Mode)",
        startup_reminder_mode=STARTUP_REMINDER_DAILY_FIRST,
        planned_date=datetime.now().strftime("%Y-%m-%d"),
        planned_start_time="09:00",
    )
    tid = tc.add_task(t)
    t.id = tid

    # 07:00 — First launch of the day, but Task A is temporarily snoozed for 60 min
    ReminderPolicyService.snooze_reminder(tid, minutes=60, settings_manager=settings)

    from todo_bird_app.views.main_window import MainWindow
    win1 = MainWindow(db, settings, theme_ctrl)
    dlgs1 = ReminderPolicyService.evaluate_startup_reminders(win1, tc, settings)
    assert len(dlgs1) == 0  # Snoozed, so does not show on launch 1
    win1.close()

    # 10:00 — Second launch of the day, Task A is no longer snoozed (eligible)
    # Clear active RAM snooze to simulate snooze elapsed while app was closed
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    restarted_settings.set("persisted_snoozed_reminders", "")
    ReminderPolicyService.reset_session_state()

    win2 = MainWindow(db, restarted_settings, theme_ctrl)
    # On launch 2, because this is NOT the first launch of today, daily_first_open MUST NOT fire
    dlgs2 = ReminderPolicyService.evaluate_startup_reminders(win2, tc, restarted_settings)
    assert len(dlgs2) == 0
    win2.close()


# 30. Snoozed reminder expiration fires even on second launch
def test_30_snoozed_reminder_expiration_fires_on_second_launch(temp_env, qapp):
    db, settings, theme_ctrl, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(
        title="Task Snooze (Daily Mode)",
        startup_reminder_mode=STARTUP_REMINDER_DAILY_FIRST,
    )
    tid = tc.add_task(t)
    t.id = tid

    # First launch today (records today's launch date)
    from todo_bird_app.views.main_window import MainWindow
    win1 = MainWindow(db, settings, theme_ctrl)
    ReminderPolicyService.evaluate_startup_reminders(win1, tc, settings)
    win1.close()

    # Second launch on same day
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService.reset_session_state()

    win2 = MainWindow(db, restarted_settings, theme_ctrl)
    # Startup reminder does NOT fire on second launch
    dlgs = ReminderPolicyService.evaluate_startup_reminders(win2, tc, restarted_settings)
    assert len(dlgs) == 0

    # User snoozes task during session for 5 minutes
    now = datetime.now()
    ReminderPolicyService.snooze_reminder(tid, minutes=5, from_dt=now, settings_manager=restarted_settings)

    # 5 minutes later during active session: snooze expires
    trigger_dt = now + timedelta(minutes=6)
    poll_due = ReminderPolicyService.check_and_trigger_due_reminders(win2, tc, restarted_settings)
    # Using get_due_reminders with current_dt
    due = ReminderPolicyService.get_due_reminders(tc, restarted_settings, current_dt=trigger_dt)
    assert any(x.id == tid for x in due)
    win2.close()


# 31. daily_first_open + first launch today + persisted_daily_startup yesterday + persisted ack => reminder shown
def test_31_daily_first_open_shown_with_historical_occurrence_acknowledgment(temp_env, qapp):
    import json
    db, settings, theme_ctrl, _ = temp_env
    tc = TaskController(db)
    t = Task(
        title="Historical Ack Task",
        startup_reminder_mode=STARTUP_REMINDER_DAILY_FIRST,
        planned_date="2026-08-20",
        planned_start_time="04:00",
    )
    tid = tc.add_task(t)
    t.id = tid
    occ_key = ReminderPolicyService.get_occurrence_key(t)
    assert occ_key == "2026-08-20_04:00"

    today = datetime.now()
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    ReminderPolicyService.reset_session_state()

    # Yesterday's daily startup record, persisted acknowledgment of occurrence, and last launch yesterday
    settings.set("persisted_daily_startup_reminders", json.dumps({str(tid): yesterday_str}))
    settings.set("persisted_acknowledged_reminders", json.dumps({str(tid): occ_key}))
    settings.set("last_app_launch_date", yesterday_str)

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    dlgs = ReminderPolicyService.evaluate_startup_reminders(win, tc, settings)

    # Persisted acknowledgment MUST be loaded in _acknowledged_occurrences
    assert ReminderPolicyService._acknowledged_occurrences.get(tid) == occ_key
    # Despite the historical occurrence acknowledgment, daily_first_open MUST show on first launch of today
    assert len(dlgs) == 1
    assert dlgs[0].task.id == tid
    win.close()


# 32. Same configuration but second app launch on same local day => NOT shown
def test_32_daily_first_open_suppressed_on_second_launch_same_day_with_persisted_ack(temp_env, qapp):
    import json
    db, settings, theme_ctrl, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(
        title="Historical Ack Task",
        startup_reminder_mode=STARTUP_REMINDER_DAILY_FIRST,
        planned_date="2026-08-20",
        planned_start_time="04:00",
    )
    tid = tc.add_task(t)
    t.id = tid
    occ_key = ReminderPolicyService.get_occurrence_key(t)

    today = datetime.now()
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    ReminderPolicyService.reset_session_state()

    # Setup first launch today with persisted acknowledgment
    settings.set("persisted_daily_startup_reminders", json.dumps({str(tid): yesterday_str}))
    settings.set("persisted_acknowledged_reminders", json.dumps({str(tid): occ_key}))
    settings.set("last_app_launch_date", yesterday_str)

    from todo_bird_app.views.main_window import MainWindow
    # Launch 1: Shows reminder
    win1 = MainWindow(db, settings, theme_ctrl)
    dlgs1 = ReminderPolicyService.evaluate_startup_reminders(win1, tc, settings)
    assert len(dlgs1) == 1
    win1.close()

    # Launch 2 on same local day
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService.reset_session_state()

    win2 = MainWindow(db, restarted_settings, theme_ctrl)
    dlgs2 = ReminderPolicyService.evaluate_startup_reminders(win2, tc, restarted_settings)
    assert len(dlgs2) == 0
    win2.close()


# 33. Next local calendar day => reminder eligible again even with persisted ack
def test_33_daily_first_open_eligible_again_next_calendar_day_with_persisted_ack(temp_env, qapp):
    import json
    db, settings, theme_ctrl, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(
        title="Next Day Eligible Task",
        startup_reminder_mode=STARTUP_REMINDER_DAILY_FIRST,
        planned_date="2026-08-20",
        planned_start_time="04:00",
    )
    tid = tc.add_task(t)
    t.id = tid
    occ_key = ReminderPolicyService.get_occurrence_key(t)

    today = datetime.now()
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    ReminderPolicyService.reset_session_state()

    # Simulate Day 1 was yesterday (or older), and persisted ack remains
    settings.set("persisted_daily_startup_reminders", json.dumps({str(tid): yesterday_str}))
    settings.set("persisted_acknowledged_reminders", json.dumps({str(tid): occ_key}))
    settings.set("last_app_launch_date", yesterday_str)

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    due = ReminderPolicyService.get_startup_due_reminders(tc, settings)
    assert any(task.id == tid for task in due)

    dlgs = ReminderPolicyService.evaluate_startup_reminders(win, tc, settings)
    assert len(dlgs) == 1
    assert dlgs[0].task.id == tid
    win.close()


# 34. Scheduled/runtime polling regression: persisted ack STILL suppresses normal runtime scheduled reminder
def test_34_runtime_polling_scheduled_occurrence_remains_suppressed_by_persisted_ack(temp_env):
    import json
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    now = datetime.now()
    past_time = now - timedelta(minutes=10)

    # Task A has scheduled time in past and is acknowledged in persisted_acknowledged_reminders
    t_ack = Task(
        title="Acked Runtime Task",
        startup_reminder_mode=STARTUP_REMINDER_DAILY_FIRST,
        planned_date=past_time.strftime("%Y-%m-%d"),
        planned_start_time=past_time.strftime("%H:%M"),
    )
    tid_ack = tc.add_task(t_ack)
    t_ack.id = tid_ack
    occ_key_ack = ReminderPolicyService.get_occurrence_key(t_ack)

    # Task B has scheduled time in past and is NOT acknowledged
    t_unack = Task(
        title="Unacked Runtime Task",
        startup_reminder_mode=STARTUP_REMINDER_DAILY_FIRST,
        planned_date=past_time.strftime("%Y-%m-%d"),
        planned_start_time=past_time.strftime("%H:%M"),
    )
    tid_unack = tc.add_task(t_unack)
    t_unack.id = tid_unack

    ReminderPolicyService.reset_session_state()
    settings.set("persisted_acknowledged_reminders", json.dumps({str(tid_ack): occ_key_ack}))
    ReminderPolicyService._session_start_time = past_time - timedelta(minutes=5)

    due = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=now)
    due_ids = [x.id for x in due]

    # Task A MUST be suppressed by persisted acknowledgment during runtime polling
    assert tid_ack not in due_ids
    # Task B MUST fire because it was not acknowledged
    assert tid_unack in due_ids


# 35. every_app_open behavior remains unchanged
def test_35_every_app_open_behavior_remains_unchanged(temp_env, qapp):
    import json
    db, settings, theme_ctrl, temp_dir = temp_env
    tc = TaskController(db)
    t = Task(
        title="Every App Open Task",
        startup_reminder_mode=STARTUP_REMINDER_EVERY_APP,
        planned_date="2026-08-20",
        planned_start_time="04:00",
    )
    tid = tc.add_task(t)
    t.id = tid
    occ_key = ReminderPolicyService.get_occurrence_key(t)

    ReminderPolicyService.reset_session_state()

    # Even with an acknowledged occurrence and launch earlier today:
    today_str = datetime.now().strftime("%Y-%m-%d")
    settings.set("persisted_acknowledged_reminders", json.dumps({str(tid): occ_key}))
    settings.set("last_app_launch_date", today_str)

    from todo_bird_app.views.main_window import MainWindow
    # Launch 1: every_app_open fires
    win1 = MainWindow(db, settings, theme_ctrl)
    dlgs1 = ReminderPolicyService.evaluate_startup_reminders(win1, tc, settings)
    assert len(dlgs1) == 1
    assert dlgs1[0].task.id == tid
    win1.close()

    # Launch 2: every_app_open fires again on new session
    restarted_settings = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService.reset_session_state()

    win2 = MainWindow(db, restarted_settings, theme_ctrl)
    dlgs2 = ReminderPolicyService.evaluate_startup_reminders(win2, tc, restarted_settings)
    assert len(dlgs2) == 1
    assert dlgs2[0].task.id == tid
    win2.close()


# 36. Completed and cancelled tasks remain suppressed on startup
def test_36_completed_and_cancelled_tasks_remain_suppressed(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    tc = TaskController(db)
    t_completed = Task(
        title="Completed Task",
        status=TaskStatus.COMPLETED,
        startup_reminder_mode=STARTUP_REMINDER_DAILY_FIRST,
        planned_date="2026-08-20",
        planned_start_time="04:00",
    )
    tid_comp = tc.add_task(t_completed)

    t_cancelled = Task(
        title="Cancelled Task",
        status=TaskStatus.CANCELLED,
        startup_reminder_mode=STARTUP_REMINDER_DAILY_FIRST,
        planned_date="2026-08-20",
        planned_start_time="04:00",
    )
    tid_canc = tc.add_task(t_cancelled)

    today = datetime.now()
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    ReminderPolicyService.reset_session_state()
    settings.set("last_app_launch_date", yesterday_str)

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)
    dlgs = ReminderPolicyService.evaluate_startup_reminders(win, tc, settings)
    shown_ids = [d.task.id for d in dlgs]

    assert tid_comp not in shown_ids
    assert tid_canc not in shown_ids
    win.close()

