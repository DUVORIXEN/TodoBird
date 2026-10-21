import pytest
import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from PySide6.QtWidgets import QApplication, QLabel, QPushButton
from PySide6.QtGui import QFont

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.services.typography_service import TypographyService
from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
from todo_bird_app.widgets.reminder_dialog import ReminderDialog

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
    db_path = os.path.join(temp_dir, "test_310d_rem.db")
    db = DatabaseManager(db_path)
    settings = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService.reset_session_state()
    yield db, settings, temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)

# REM01 Reminder modern widget opens
def test_rem01_modern_reminder_widget_opens(temp_env, qapp):
    db, settings, _ = temp_env
    t = Task(id=1, title="Review Q3 Deliverables", description="Check with team", startup_reminder=True)
    dlg = ReminderDialog(t, settings_manager=settings)
    assert dlg.title_label.text() == "Review Q3 Deliverables"
    assert dlg.desc_label.text() == "Check with team"
    assert dlg.btn_complete is not None
    assert dlg.btn_snooze is not None
    assert dlg.btn_open is not None
    assert dlg.btn_dismiss is not None

# REM02 Font family changes visibly
def test_rem02_font_family_changes(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_family_reminder", "Liberation Mono")

    t = Task(id=1, title="Sample Reminder", startup_reminder=True)
    dlg = ReminderDialog(t, settings_manager=settings)
    assert dlg.font().family() == "Liberation Mono"
    assert dlg.title_label.font().family() == "Liberation Mono"

# REM03 Font size changes
def test_rem03_font_size_changes(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_size_reminder", 16)

    t = Task(id=1, title="Sample Reminder", startup_reminder=True)
    dlg = ReminderDialog(t, settings_manager=settings)
    assert dlg.font().pointSize() == 16

# REM04 Font weight changes
def test_rem04_font_weight_changes(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_weight_reminder", "bold")

    t = Task(id=1, title="Sample Reminder", startup_reminder=True)
    dlg = ReminderDialog(t, settings_manager=settings)
    assert dlg.font().bold()

# REM05 Font color changes
def test_rem05_font_color_changes(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_color_reminder", "#E95420")

    t = Task(id=1, title="Sample Reminder", startup_reminder=True)
    dlg = ReminderDialog(t, settings_manager=settings)
    assert "#E95420" in dlg.title_label.styleSheet()

# REM06 Theme automatic color works
def test_rem06_theme_automatic_color_works(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_color_reminder", "auto")

    t = Task(id=1, title="Sample Reminder", startup_reminder=True)
    dlg = ReminderDialog(t, settings_manager=settings)
    color = TypographyService.get_font_color_for_area("reminder", settings)
    assert color is None # None indicates auto theme inheritance

# REM07 Reminder restart persists
def test_rem07_restart_persists(temp_env, qapp):
    db, settings, temp_dir = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_family_reminder", "Courier")
    settings.set("font_size_reminder", 15)
    settings.set("font_color_reminder", "#10B981")

    restarted = SettingsManager(db, config_dir=Path(temp_dir))
    t = Task(id=1, title="Sample Reminder", startup_reminder=True)
    dlg = ReminderDialog(t, settings_manager=restarted)
    assert dlg.font().family() == "Courier"
    assert dlg.font().pointSize() == 15
    assert "#10B981" in dlg.title_label.styleSheet()

# REM08 Computer-startup mode decision
def test_rem08_computer_startup_mode(temp_env):
    _, settings, _ = temp_env
    settings.set("reminder_trigger_mode", "computer_startup")
    # A manual launch that is the first launch of the local calendar day
    # counts as the user's session start (due launch reminders must fire)
    assert ReminderPolicyService.should_show_on_startup(settings, is_session_startup=False)
    # If launched with session startup flag, always returns True
    assert ReminderPolicyService.should_show_on_startup(settings, is_session_startup=True)
    # A manual launch later the same day is no longer the first opening
    from datetime import datetime as _dt
    settings.set("last_app_launch_date", _dt.now().strftime("%Y-%m-%d"))
    ReminderPolicyService.reset_session_state()
    assert not ReminderPolicyService.should_show_on_startup(settings, is_session_startup=False)
    assert ReminderPolicyService.should_show_on_startup(settings, is_session_startup=True)

# REM09 TodoBird-startup mode decision
def test_rem09_todobird_startup_mode(temp_env):
    _, settings, _ = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    assert ReminderPolicyService.should_show_on_startup(settings, is_session_startup=False)

# REM10 Scheduled-only mode suppresses startup popup
def test_rem10_scheduled_only_suppresses_startup_popup(temp_env):
    _, settings, _ = temp_env
    settings.set("reminder_trigger_mode", "scheduled_only")
    assert not ReminderPolicyService.should_show_on_startup(settings, is_session_startup=False)
    assert not ReminderPolicyService.should_show_on_startup(settings, is_session_startup=True)

# REM11 Disabled/manual suppresses popup
def test_rem11_disabled_suppresses_popup(temp_env):
    _, settings, _ = temp_env
    settings.set("reminder_trigger_mode", "disabled")
    assert not ReminderPolicyService.should_show_on_startup(settings, is_session_startup=False)
    assert not ReminderPolicyService.should_show_on_startup(settings, is_session_startup=True)

# REM12 Duplicate reminder popup prevented
def test_rem12_duplicate_suppression(temp_env):
    db, settings, _ = temp_env
    tc = TaskController(db)
    now = datetime.now()
    t = Task(
        title="Due Reminder Task",
        planned_date=now.strftime("%Y-%m-%d"),
        planned_start_time=now.strftime("%H:%M"),
    )
    tid = tc.add_task(t)
    t.id = tid
    ReminderPolicyService._session_start_time = now - timedelta(minutes=1)

    # First fetch returns the task
    due = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=now)
    assert len(due) == 1
    assert due[0].id == tid

    # Mark shown
    ReminderPolicyService.mark_shown(tid)

    # Second fetch suppresses it
    due_second = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=now)
    assert len(due_second) == 0

# REM13 Snooze updates next due state
def test_rem13_snooze_updates_due_state(temp_env):
    db, settings, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Snooze Target", startup_reminder=True)
    tid = tc.add_task(t)

    now = datetime(2026, 8, 17, 10, 0, 0)
    ReminderPolicyService.snooze_reminder(tid, minutes=30, from_dt=now)

    # At 10:15 (during snooze), should NOT be due
    check_1 = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=datetime(2026, 8, 17, 10, 15, 0))
    assert len(check_1) == 0

    # At 10:35 (after snooze expired), SHOULD be due again
    check_2 = ReminderPolicyService.get_due_reminders(tc, settings, current_dt=datetime(2026, 8, 17, 10, 35, 0))
    assert len(check_2) == 1
    assert check_2[0].id == tid

# REM14 Open Task works
def test_rem14_open_task_action(temp_env, qapp):
    db, settings, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Open Task Test", startup_reminder=True)
    tid = tc.add_task(t)
    t.id = tid

    dlg = ReminderDialog(t, task_controller=tc, settings_manager=settings)
    assert dlg.btn_open is not None

# REM15 Dismiss works
def test_rem15_dismiss_action(temp_env, qapp):
    db, settings, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Dismiss Test", startup_reminder=True)
    tid = tc.add_task(t)
    t.id = tid

    dlg = ReminderDialog(t, task_controller=tc, settings_manager=settings)
    dlg.btn_dismiss.click()

    # Verify task was dismissed for session
    due = ReminderPolicyService.get_due_reminders(tc, settings)
    assert len(due) == 0
