import pytest
import sqlite3
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QDate, QTime

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task
from todo_bird_app.widgets.task_dialog import TaskDialog

_APP = QApplication.instance() or QApplication([])


def test_schema_v9_migration_creates_actual_columns(tmp_path):
    """Verify v9 migration adds actual execution columns to tasks and subtasks."""
    db_file = str(tmp_path / "test_v9.db")
    db = DatabaseManager(db_path=db_file)

    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Verify tasks table columns
        cursor.execute("PRAGMA table_info(tasks);")
        task_cols = {row["name"] for row in cursor.fetchall()}
        assert "actual_start_date" in task_cols
        assert "actual_end_date" in task_cols
        assert "actual_start_time" in task_cols
        assert "actual_end_time" in task_cols
        assert "actual_duration" in task_cols

        # Verify subtasks table columns
        cursor.execute("PRAGMA table_info(subtasks);")
        subtask_cols = {row["name"] for row in cursor.fetchall()}
        assert "actual_start_date" in subtask_cols
        assert "actual_end_date" in subtask_cols
        assert "actual_start_time" in subtask_cols
        assert "actual_end_time" in subtask_cols
        assert "actual_duration" in subtask_cols


def test_subtask_actual_execution_crud(tmp_path):
    """Verify insert, update, and get_subtask_tree with actual execution timing fields."""
    db_file = str(tmp_path / "test_subtask_actual.db")
    db = DatabaseManager(db_path=db_file)

    task_id = db.insert_task({
        "title": "Parent Master Task",
        "planned_date": "2026-08-15",
        "due_date": "2026-08-17",
        "status": "in_progress",
        "actual_start_date": "2026-08-15",
        "actual_start_time": "09:00",
    })

    # Insert subtask with actual timing
    sub_id = db.insert_subtask(
        task_id=task_id,
        title="Subtask 1 with Actuals",
        planned_date="2026-08-15",
        due_date="2026-08-15",
        planned_start_time="09:00",
        planned_end_time="10:00",
        actual_start_date="2026-08-15",
        actual_end_date="2026-08-15",
        actual_start_time="08:45",
        actual_end_time="09:30",
        actual_duration=45,
        progress=100,
        is_completed=True,
    )
    assert sub_id > 0

    # Retrieve subtask tree
    tree = db.get_subtask_tree(task_id)
    assert len(tree) == 1
    node = tree[0]
    assert node["title"] == "Subtask 1 with Actuals"
    assert node["actual_start_date"] == "2026-08-15"
    assert node["actual_start_time"] == "08:45"
    assert node["actual_end_time"] == "09:30"
    assert node["actual_duration"] == 45

    # Update subtask with new actuals
    db.update_subtask(
        subtask_id=sub_id,
        title="Subtask 1 Updated",
        is_completed=True,
        actual_start_date="2026-08-16",
        actual_start_time="07:30",
        actual_end_time="09:00",
        actual_duration=90,
    )

    flat = db.get_all_subtasks_flat(task_id)
    assert flat[0]["actual_start_date"] == "2026-08-16"
    assert flat[0]["actual_start_time"] == "07:30"
    assert flat[0]["actual_end_time"] == "09:00"
    assert flat[0]["actual_duration"] == 90


def test_task_dialog_subtask_actual_execution_ui(tmp_path):
    """Verify TaskDialog tree captures and saves subtask actual timing."""
    db_file = str(tmp_path / "test_dialog_subtasks.db")
    db = DatabaseManager(db_path=db_file)

    task_id = db.insert_task({
        "title": "Main Project",
        "planned_date": "2026-08-15",
        "due_date": "2026-08-18",
        "status": "in_progress",
        "actual_start_date": "2026-08-15",
        "actual_start_time": "09:00",
    })

    db.insert_subtask(
        task_id=task_id,
        title="Feature Implementation",
        planned_date="2026-08-15",
        actual_start_date="2026-08-15",
        actual_start_time="10:00",
        actual_end_time="11:30",
        actual_duration=90,
        progress=50,
    )

    task_row = db.get_task_by_id(task_id)
    t = Task.from_row(task_row)
    dialog = TaskDialog(projects=[], task=t, db_manager=db)

    # Verify existing subtask loaded into tree with actuals
    top_item = dialog.subtask_tree.topLevelItem(0)
    assert top_item is not None
    meta = top_item.data(0, Qt.UserRole + 1)
    assert meta["actual_start_time"] == "10:00"
    assert meta["actual_end_time"] == "11:30"
    assert meta["actual_duration"] == 90

    # Save dialog and verify DB persisted correctly
    dialog.on_save()

    updated_tree = db.get_subtask_tree(task_id)
    assert updated_tree[0]["actual_start_time"] == "10:00"
    assert updated_tree[0]["actual_duration"] == 90
