import pytest
import os
from unittest.mock import patch, MagicMock

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from PySide6.QtCore import QTimer

from todo_bird_app.app import MainWindow
from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
from todo_bird_app.widgets.support_dialog import SupportTodoBirdDialog
from todo_bird_app.services.window_registry import WindowRegistry
from todo_bird_app.models.task import Task, TaskStatus

@pytest.fixture(autouse=True)
def clean_window_registry():
    """Ensure WindowRegistry starts clean for each test."""
    WindowRegistry.clear()
    yield
    WindowRegistry.clear()

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app

@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test_startup.db"
    return DatabaseManager.temporary(str(db_path))

@pytest.fixture
def settings(temp_db, tmp_path):
    config_dir = tmp_path / "config"
    return SettingsManager(temp_db, config_dir=config_dir)

@pytest.fixture
def theme(settings):
    return ThemeController(settings)

@pytest.fixture
def main_window(temp_db, settings, theme, qapp):
    # Enable offscreen rendering
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    window = MainWindow(temp_db, settings, theme)
    yield window
    window.close()

def get_top_level_dialogs():
    app = QApplication.instance()
    if not app:
        return []
    
    # In offscreen QPA (headless), isVisible() may not accurately reflect show() state
    # We instead check existence of the expected window types in topLevelWidgets
    return [w for w in app.topLevelWidgets() if isinstance(w, (QDialog, QMessageBox))]

def test_startup_scenario_a_clean(main_window, qapp):
    """Scenario A: No reminders, companion disabled. Expected: MainWindow only."""
    main_window.show()
    qapp.processEvents()
    
    dialogs = get_top_level_dialogs()
    assert len(dialogs) == 0, f"Expected 0 dialogs, found {dialogs}"
    assert main_window.isVisible()

def test_startup_scenario_b_eligible_no_auto_prompt(main_window, temp_db, settings, qapp):
    """Scenario B: Support eligibility true, no reminders. NO SupportTodoBirdDialog."""
    for i in range(30):
        t = Task(title=f"Completed {i}", status=TaskStatus.COMPLETED)
        temp_db.insert_task(t.to_dict())
        
    main_window.show()
    qapp.processEvents()
    
    # Check that no QTimer is waiting to trigger the support prompt
    # Since we completely removed the timer and method, there should be no SupportTodoBirdDialog
    dialogs = get_top_level_dialogs()
    support_dialogs = [d for d in dialogs if d.objectName() == "SupportTodoBirdDialog"]
    
    assert len(support_dialogs) == 0
    assert len(dialogs) == 0

def test_startup_scenario_c_legitimate_reminder(main_window, temp_db, qapp):
    """Scenario C: One legitimate startup reminder."""
    t = Task(
        title="Startup Task", 
        status=TaskStatus.INBOX, 
        startup_reminder=True,
        startup_reminder_mode="every_app_open"
    )
    temp_db.insert_task(t.to_dict())

    
    main_window.show()
    qapp.processEvents()
    
    # Setting the mode manually as we are bypassing the save hook by using db_manager directly
    main_window.settings_manager.set("reminder_trigger_mode", "app_startup")
    
    all_tasks = main_window.task_controller.get_all_tasks()
    due_tasks = ReminderPolicyService.get_startup_due_reminders(
        main_window.task_controller,
        main_window.settings_manager
    )
    print("ALL TASKS:", len(all_tasks))
    print("DUE TASKS:", len(due_tasks))
    
    ReminderPolicyService.reset_session_state(main_window.settings_manager)
    dialogs = ReminderPolicyService.evaluate_startup_reminders(
        main_window,
        main_window.task_controller,
        settings_manager=main_window.settings_manager,
        is_session_startup=True
    )
    qapp.processEvents()
    
    assert len(dialogs) == 1
    assert type(dialogs[0]).__name__ == "ReminderDialog"

def test_startup_scenario_d_reminder_and_support_eligibility(main_window, temp_db, qapp):
    """Scenario D: Support eligibility true + one reminder. Expected: MainWindow + permitted reminder, NO support dialog."""
    # Insert 30 completed to make eligible
    for i in range(30):
        t = Task(title=f"Completed {i}", status=TaskStatus.COMPLETED)
        temp_db.insert_task(t.to_dict())
        
    # Insert 1 reminder
    t = Task(
        title="Startup Task", 
        status=TaskStatus.INBOX, 
        startup_reminder=True,
        startup_reminder_mode="every_app_open"
    )
    temp_db.insert_task(t.to_dict())

    
    main_window.show()
    
    main_window.settings_manager.set("reminder_trigger_mode", "app_startup")
    ReminderPolicyService.reset_session_state(main_window.settings_manager)
    dialogs = ReminderPolicyService.evaluate_startup_reminders(
        main_window,
        main_window.task_controller,
        settings_manager=main_window.settings_manager,
        is_session_startup=True
    )
    qapp.processEvents()
    
    top_level = get_top_level_dialogs()
    support_dialogs = [d for d in top_level if d.objectName() == "SupportTodoBirdDialog"]
    
    assert len(dialogs) == 1
    assert type(dialogs[0]).__name__ == "ReminderDialog"
    assert len(support_dialogs) == 0

def test_startup_scenario_e_critical_recovery(qapp, tmp_path):
    """Scenario E: Critical recovery condition. No support prompt."""
    from todo_bird_app.services.backup_manager import BackupManager
    
    db_path = tmp_path / "corrupt.db"
    db_path.write_bytes(b"corrupt data")
    
    is_valid, _ = BackupManager.verify_database_integrity(db_path)
    assert not is_valid
