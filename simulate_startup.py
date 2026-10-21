import sys
import os
import json
from datetime import datetime, timedelta
from PySide6.QtWidgets import QApplication

# Set up environment
os.environ["TODO_BIRD_ENV"] = "test"
os.environ["XDG_RUNTIME_DIR"] = "/tmp/runtime-dir"

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task
from todo_bird_app.services.reminder_policy_service import ReminderPolicyService

def run():
    app = QApplication.instance() or QApplication(sys.argv)
    db = DatabaseManager(":memory:")
    sm = SettingsManager(db)
    tc = TaskController(db)
    
    # Create a task due 5 minutes ago
    past_dt = datetime.now() - timedelta(minutes=5)
    t = Task(
        title="Missed Morning Reminder",
        planned_date=past_dt.strftime("%Y-%m-%d"),
        planned_start_time=past_dt.strftime("%H:%M"),
        # The crucial user configuration!
        # if they just set a date/time but don't explicitly enable "startup_reminder" or "startup_reminder_mode":
        startup_reminder=False,
        startup_reminder_mode=ReminderPolicyService.STARTUP_MODE_OFF
    )
    tc.add_task(t)
    
    # Simulate app startup (app.py)
    # ReminderPolicyService.evaluate_startup_reminders uses the settings mode:
    ReminderPolicyService.reset_session_state()
    # Let's say user has default settings (scheduled_only)
    
    # 1. Start up evaluates:
    dlgs = ReminderPolicyService.evaluate_startup_reminders(
        None, tc, settings_manager=sm, is_session_startup=False
    )
    print(f"Startup dialogs (startup_reminder=False, default global mode): {len(dlgs)}")
    
    # 2. Poller evaluates 2 seconds later:
    dlgs2 = ReminderPolicyService.check_and_trigger_due_reminders(None, tc, settings_manager=sm)
    print(f"Poller dialogs (startup_reminder=False, default global mode): {len(dlgs2)}")

    print("\n--- Now enabling startup_reminder on task ---")
    t.startup_reminder = True
    t.startup_reminder_mode = ReminderPolicyService.STARTUP_MODE_DAILY_FIRST
    tc.update_task(t)
    
    ReminderPolicyService.reset_session_state()
    
    # 1. Start up evaluates:
    dlgs3 = ReminderPolicyService.evaluate_startup_reminders(
        None, tc, settings_manager=sm, is_session_startup=False
    )
    print(f"Startup dialogs (startup_reminder=True, default global mode): {len(dlgs3)}")
    
    # 2. Poller evaluates 2 seconds later:
    dlgs4 = ReminderPolicyService.check_and_trigger_due_reminders(None, tc, settings_manager=sm)
    print(f"Poller dialogs (startup_reminder=True, default global mode): {len(dlgs4)}")


if __name__ == "__main__":
    run()
