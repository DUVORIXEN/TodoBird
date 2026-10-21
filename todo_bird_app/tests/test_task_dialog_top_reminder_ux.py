import pytest
from PySide6.QtWidgets import QApplication
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.models.task import Task
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.database import DatabaseManager
from unittest.mock import MagicMock

@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.fixture
def temp_tc(tmp_path):
    db_file = tmp_path / "test_ux.db"
    db = DatabaseManager(str(db_file))
    return TaskController(db_manager=db)

def test_01_top_reminder_unchecked_means_off(temp_tc, qapp):
    t = Task()
    dlg = TaskDialog([], t, db_manager=temp_tc.db_manager)
    
    dlg.facade_reminder_checkbox.setChecked(False)
    
    assert not dlg.facade_reminder_combo.isEnabled()
    assert dlg.startup_reminder_combo.currentData() == "off"

def test_02_top_reminder_checked_daily_syncs_to_daily_first_open(temp_tc, qapp):
    t = Task()
    dlg = TaskDialog([], t, db_manager=temp_tc.db_manager)
    
    dlg.facade_reminder_checkbox.setChecked(True)
    idx = dlg.facade_reminder_combo.findData("daily_first_open")
    dlg.facade_reminder_combo.setCurrentIndex(idx)
    
    assert dlg.startup_reminder_combo.currentData() == "daily_first_open"

def test_03_top_reminder_checked_every_syncs_to_every_app_open(temp_tc, qapp):
    t = Task()
    dlg = TaskDialog([], t, db_manager=temp_tc.db_manager)
    
    dlg.facade_reminder_checkbox.setChecked(True)
    idx = dlg.facade_reminder_combo.findData("every_app_open")
    dlg.facade_reminder_combo.setCurrentIndex(idx)
    
    assert dlg.startup_reminder_combo.currentData() == "every_app_open"

def test_04_edit_daily_task_restores_top_checkbox_and_dropdown(temp_tc, qapp):
    t = Task(title="Test", startup_reminder=True, startup_reminder_mode="daily_first_open")
    dlg = TaskDialog([], t, db_manager=temp_tc.db_manager)
    
    assert dlg.facade_reminder_checkbox.isChecked()
    assert dlg.facade_reminder_combo.isEnabled()
    assert dlg.facade_reminder_combo.currentData() == "daily_first_open"

def test_05_edit_every_task_restores_top_checkbox_and_dropdown(temp_tc, qapp):
    t = Task(title="Test", startup_reminder=True, startup_reminder_mode="every_app_open")
    dlg = TaskDialog([], t, db_manager=temp_tc.db_manager)
    
    assert dlg.facade_reminder_checkbox.isChecked()
    assert dlg.facade_reminder_combo.isEnabled()
    assert dlg.facade_reminder_combo.currentData() == "every_app_open"

def test_06_edit_off_task_restores_unchecked(temp_tc, qapp):
    t = Task(title="Test", startup_reminder=False, startup_reminder_mode="off")
    dlg = TaskDialog([], t, db_manager=temp_tc.db_manager)
    
    assert not dlg.facade_reminder_checkbox.isChecked()
    assert not dlg.facade_reminder_combo.isEnabled()

def test_07_top_and_legacy_controls_stay_synchronized(temp_tc, qapp):
    t = Task()
    dlg = TaskDialog([], t, db_manager=temp_tc.db_manager)
    
    # Check top
    dlg.facade_reminder_checkbox.setChecked(True)
    assert dlg.startup_reminder_combo.currentData() == "daily_first_open"
    
    # Change inner
    idx = dlg.startup_reminder_combo.findData("every_app_open")
    dlg.startup_reminder_combo.setCurrentIndex(idx)
    assert dlg.facade_reminder_checkbox.isChecked()
    assert dlg.facade_reminder_combo.currentData() == "every_app_open"
    
    # Disable inner
    idx = dlg.startup_reminder_combo.findData("off")
    dlg.startup_reminder_combo.setCurrentIndex(idx)
    assert not dlg.facade_reminder_checkbox.isChecked()
    assert not dlg.facade_reminder_combo.isEnabled()
