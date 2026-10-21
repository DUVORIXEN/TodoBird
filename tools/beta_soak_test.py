#!/usr/bin/env python3
import sys
import os
from pathlib import Path
import time
import argparse
import logging
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).parent.parent))

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.views.main_window import MainWindow

def setup_logger():
    logger = logging.getLogger("beta_soak_test")
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(ch)
    return logger

def generate_mock_tasks(db_manager, count: int):
    logger = logging.getLogger("beta_soak_test")
    logger.info(f"Generating {count} mock tasks...")
    
    # Bulk insert is faster but we will use the standard service for realistic behavior
    from todo_bird_app.models.task import Task
    for i in range(count):
        t = Task(
            title=f"Soak Test Task {i}",
            planned_effort_minutes=30,
            status="IN_PROGRESS" if i % 2 == 0 else "TODO"
        )
        db_manager.insert_task(t.to_dict())

def run_soak_test(dataset_size: int, cycles: int):
    logger = setup_logger()
    logger.info("=========================================")
    logger.info(f"Starting Beta Soak Test - {dataset_size} tasks, {cycles} cycles")
    logger.info("=========================================")
    
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    
    db_path = Path(__file__).parent.parent / "todo_bird_app" / "data" / "soak_test.db"
    if db_path.exists():
        db_path.unlink()
        
    db_manager = DatabaseManager.temporary(str(db_path))
    generate_mock_tasks(db_manager, dataset_size)
    
    app = QApplication.instance() or QApplication(sys.argv)
    settings_manager = SettingsManager(db_manager)
    theme_controller = ThemeController(settings_manager)
    
    start_time = time.time()
    
    # Measure Cold Startup
    window = MainWindow(db_manager, settings_manager, theme_controller)
    window.show()
    app.processEvents()
    cold_time = time.time() - start_time
    logger.info(f"Cold startup time (including UI render): {cold_time:.2f}s")
    
    # Simulate View Switching
    for i in range(cycles):
        logger.info(f"Cycle {i+1}/{cycles}")
        # Switch to Inbox
        window.stacked_widget.setCurrentIndex(0)
        app.processEvents()
        
        # Open Task Dialog for a task
        tasks = db_manager.get_all_tasks(limit=10)
        if tasks:
            window.task_controller.open_task_dialog(tasks[0]['id'], parent=window)
            app.processEvents()
            # Find the active dialog and close it
            active_dialogs = window.findChildren(QApplication.activeModalWidget().__class__) if QApplication.activeModalWidget() else []
            for d in active_dialogs:
                d.close()
            app.processEvents()
            
    logger.info("Soak test completed successfully.")
    window.close()
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", type=int, default=1000, help="Number of mock tasks")
    parser.add_argument("--cycles", type=int, default=10, help="Number of UI interaction cycles")
    args = parser.parse_args()
    run_soak_test(args.size, args.cycles)
