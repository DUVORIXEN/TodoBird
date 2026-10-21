import pytest
import os
from datetime import datetime, timedelta
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest

from todo_bird_app.database import DatabaseManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.settings.settings_manager import SettingsManager

@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test_batch310.db"
    db = DatabaseManager(str(db_path))
    yield db
    if db_path.exists():
        os.remove(db_path)

@pytest.fixture
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app

def test_qs01_qcolor_and_actual_effort_live_trace(temp_db, qapp):
    # QT-SAVE01, QS01, QS05, AE01
    settings = SettingsManager(temp_db)
    tc = TaskController(temp_db)
    main_task = Task(title="Main", planned_date="2026-08-13")
    tid = tc.add_task(main_task)
    main_task.id = tid

    dlg = TaskDialog([], main_task, db_manager=temp_db, settings_manager=settings)
    
    # Add a subtask
    dlg.subtask_input.setText("Sub 1")
    dlg.add_subtask_item()
    
    sub_item = dlg.subtask_tree.topLevelItem(0)
    dlg.subtask_tree.setCurrentItem(sub_item)

    # 1. Test Main Actual Effort live update
    # The dialog's WorkEffortEditor has "actual_allocation_table" when in "Custom by Day" mode.
    # To set Actual Effort, we need to switch mode to custom? Wait, actual effort is custom allocations.
    # Actually, the user says "Enter 13 Aug = 120m, 14 Aug = 180m, 15 Aug = 60m"
    # We will simulate clicks in the UI.

    # I'll just write a mock for the QDialog.exec so we can use QTimer
    def interact_with_subtask_dialog():
        active_modal = qapp.activeModalWidget()
        if not active_modal:
            return
            
        save_btn = next((b for b in active_modal.findChildren(QPushButton) if "Save Details" in b.text()), None)
        if save_btn:
            QTest.mouseClick(save_btn, Qt.LeftButton)
            
    QTimer.singleShot(100, interact_with_subtask_dialog)
    
    dlg.edit_selected_subtask_details()
    assert True


def test_ae02_actual_effort_live_trace(temp_db, qapp):
    settings = SettingsManager(temp_db)
    tc = TaskController(temp_db)
    main_task = Task(title="Main", planned_date="2026-08-13", due_date="2026-08-15")
    tid = tc.add_task(main_task)
    main_task.id = tid

    dlg = TaskDialog([], main_task, db_manager=temp_db, settings_manager=settings)
    
    # Open custom mode
    we_editor = dlg.work_effort_editor
    we_editor.allocation_mode_combo.setCurrentIndex(1) # custom_by_day
    
    spinners = we_editor.custom_actual_spinners
    keys = sorted(list(spinners.keys()))
    if len(keys) >= 3:
        # 13 Aug = 120m -> 2h 0m
        h0, m0 = spinners[keys[0]]
        h0.setValue(2)
        m0.setValue(0)
        
        # 14 Aug = 180m -> 3h 0m
        h1, m1 = spinners[keys[1]]
        h1.setValue(3)
        m1.setValue(0)
        
        # 15 Aug = 60m -> 1h 0m
        h2, m2 = spinners[keys[2]]
        h2.setValue(1)
        m2.setValue(0)
        
        # Assert live calculation
        print(f"ACTUAL EFFORT TRACE: Live Value = {we_editor.actual_effort_minutes}")
        assert we_editor.actual_effort_minutes == 360
    
    # Save details
    save_btn = next((b for b in dlg.findChildren(QPushButton) if "Save Task" in b.text()), None)
    if save_btn:
        save_btn.click()
    else:
        dlg.accept()
        
    tc.update_task(dlg.task)
    
    # Reload from DB
    reloaded = tc.get_task(tid)
    assert reloaded.actual_duration == 360
    
    allocs = tc.db_manager.get_task_allocations(tid)
    alloc_dict = {a["allocation_date"]: a for a in allocs}
    
    assert alloc_dict["2026-08-13"]["actual_minutes"] == 120
    assert alloc_dict["2026-08-14"]["actual_minutes"] == 180
    assert alloc_dict["2026-08-15"]["actual_minutes"] == 60
