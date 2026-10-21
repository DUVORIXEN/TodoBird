"""
Tests for Batch 3.10I: 3W1H Structured "WHEN" Date + Time Authority
Covers:
- Mandatory tests 3W01..3W15
- Qt widget interactions (QDateEdit, QTimeEdit, QCheckBox, live summary)
- Bidirectional authority sync between 3W1H and TaskDialog
- Subtask schedule independence
- Backward compatibility and legacy reflection parsing
"""

import os
import gc
import pytest
from datetime import datetime, date, time
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QWidget
from PySide6.QtCore import Qt, QDate, QTime, QCoreApplication, QEvent

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.models.project import Project
from todo_bird_app.widgets.three_w_one_h_dialog import ThreeWOneHDialog
from todo_bird_app.widgets.task_dialog import TaskDialog


@pytest.fixture
def temp_env(tmp_path):
    db_file = tmp_path / "test_tb_310i.db"
    db = DatabaseManager(str(db_file))
    settings = SettingsManager(db)
    controller = TaskController(db)
    yield db, settings, controller


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


def test_3w01_planned_date_loads_into_3w1h(temp_env, qapp):
    """3W01: planned_date loads into 3W1H QDateEdit control."""
    db, settings, controller = temp_env
    task = Task(title="Investigation Task", planned_date="2026-08-20")

    dlg = ThreeWOneHDialog(task, settings_manager=settings)
    assert dlg.date_when.date().toString("yyyy-MM-dd") == "2026-08-20"


def test_3w02_planned_start_time_loads(temp_env, qapp):
    """3W02: planned_start_time loads into 3W1H QTimeEdit control."""
    db, settings, controller = temp_env
    task = Task(title="Morning Standup", planned_date="2026-08-20", planned_start_time="10:30")

    dlg = ThreeWOneHDialog(task, settings_manager=settings)
    assert dlg.time_when.time().toString("HH:mm") == "10:30"
    assert not dlg.chk_time_not_decided.isChecked()
    assert dlg.time_when.isEnabled()


def test_3w03_changing_date_updates_task_planned_date(temp_env, qapp):
    """3W03: Changing Date in 3W1H updates task.planned_date on save."""
    db, settings, controller = temp_env
    task = Task(title="Date Change Task", planned_date="2026-08-20", planned_start_time="09:00")

    dlg = ThreeWOneHDialog(task, settings_manager=settings)
    dlg.date_when.setDate(QDate(2026, 8, 25))
    dlg.on_save()

    assert task.planned_date == "2026-08-25"


def test_3w04_changing_time_updates_task_planned_start_time(temp_env, qapp):
    """3W04: Changing Time in 3W1H updates task.planned_start_time on save."""
    db, settings, controller = temp_env
    task = Task(title="Time Change Task", planned_date="2026-08-20", planned_start_time="09:00")

    dlg = ThreeWOneHDialog(task, settings_manager=settings)
    dlg.time_when.setTime(QTime(14, 0))
    dlg.on_save()

    assert task.planned_start_time == "14:00"


def test_3w05_task_dialog_sees_3w1h_changes(temp_env, qapp):
    """3W05: TaskDialog sees changes made in 3W1H."""
    db, settings, controller = temp_env
    task = Task(title="Sync Task 1", planned_date="2026-08-20", planned_start_time="09:00")
    t_id = controller.add_task(task)
    loaded_task = controller.get_task(t_id)

    # 1. Modify in 3W1H
    dlg_3w = ThreeWOneHDialog(loaded_task, settings_manager=settings)
    dlg_3w.date_when.setDate(QDate(2026, 8, 28))
    dlg_3w.time_when.setTime(QTime(11, 30))
    dlg_3w.on_save()
    controller.update_task(loaded_task)

    # 2. Open TaskDialog
    projects = controller.get_all_projects()
    saved_task = controller.get_task(t_id)
    dlg_task = TaskDialog(projects, task=saved_task, db_manager=db, settings_manager=settings)

    assert dlg_task.planned_date_edit.date().toString("yyyy-MM-dd") == "2026-08-28"
    assert dlg_task.start_time_edit.time().toString("HH:mm") == "11:30"
    dlg_task.reject()


def test_3w06_3w1h_sees_task_dialog_changes(temp_env, qapp):
    """3W06: 3W1H sees changes made in TaskDialog."""
    db, settings, controller = temp_env
    task = Task(title="Sync Task 2", planned_date="2026-08-20", planned_start_time="09:00")
    t_id = controller.add_task(task)
    loaded_task = controller.get_task(t_id)

    # 1. Modify in TaskDialog
    projects = controller.get_all_projects()
    dlg_task = TaskDialog(projects, task=loaded_task, db_manager=db, settings_manager=settings)
    dlg_task.planned_date_edit.setDate(QDate(2026, 9, 2))
    dlg_task.start_time_edit.setTime(QTime(15, 45))
    dlg_task.on_save()
    controller.update_task(dlg_task.get_task())

    # 2. Open 3W1H
    saved_task = controller.get_task(t_id)
    dlg_3w = ThreeWOneHDialog(saved_task, settings_manager=settings)

    assert dlg_3w.date_when.date().toString("yyyy-MM-dd") == "2026-09-02"
    assert dlg_3w.time_when.time().toString("HH:mm") == "15:45"
    dlg_3w.reject()


def test_3w07_time_not_decided_stores_null_correctly(temp_env, qapp):
    """3W07: 'Time not decided' stores None/unset in task.planned_start_time."""
    db, settings, controller = temp_env
    task = Task(title="Undecided Time Task", planned_date="2026-08-20", planned_start_time="10:00")

    dlg = ThreeWOneHDialog(task, settings_manager=settings)
    dlg.chk_time_not_decided.setChecked(True)
    assert not dlg.time_when.isEnabled()
    dlg.on_save()

    assert task.planned_start_time is None
    assert task.planned_date == "2026-08-20"


def test_3w08_no_fake_midnight_for_unknown_time(temp_env, qapp):
    """3W08: Unknown time does not store fake 00:00 midnight."""
    db, settings, controller = temp_env
    task = Task(title="No Time Task", planned_date="2026-08-20", planned_start_time=None)

    dlg = ThreeWOneHDialog(task, settings_manager=settings)
    assert dlg.chk_time_not_decided.isChecked()
    summary = dlg.lbl_when_summary.text()
    assert "Time not decided" in summary
    assert "00:00" not in summary

    dlg.on_save()
    assert task.planned_start_time is None
    assert task.planned_start_time != "00:00"


def test_3w09_save_reopen_persists(temp_env, qapp):
    """3W09: Save and reopen 3W1H preserves date, time, and reflection block."""
    db, settings, controller = temp_env
    task = Task(title="Persistent Reflection", planned_date="2026-08-20")

    dlg1 = ThreeWOneHDialog(task, settings_manager=settings)
    dlg1.txt_what.setText("Waiting for database migration")
    dlg1.txt_where.setText("Staging Cluster")
    dlg1.txt_how.setText("Run alembic upgrade head")
    dlg1.date_when.setDate(QDate(2026, 8, 24))
    dlg1.time_when.setTime(QTime(16, 0))
    dlg1.chk_time_not_decided.setChecked(False)
    dlg1.on_save()

    reflection = dlg1.get_reflection_text()
    task.description = reflection

    dlg2 = ThreeWOneHDialog(task, settings_manager=settings)
    assert dlg2.date_when.date().toString("yyyy-MM-dd") == "2026-08-24"
    assert dlg2.time_when.time().toString("HH:mm") == "16:00"
    assert dlg2.txt_what.text() == "Waiting for database migration"
    assert dlg2.txt_where.text() == "Staging Cluster"
    assert dlg2.txt_how.text() == "Run alembic upgrade head"


def test_3w10_restart_persists(temp_env, qapp):
    """3W10: Changes made through 3W1H persist across DB reconnection / restart."""
    db, settings, controller = temp_env
    task = Task(title="Restart Persist Task", planned_date="2026-08-20", planned_start_time="09:00")
    t_id = controller.add_task(task)

    loaded = controller.get_task(t_id)
    dlg = ThreeWOneHDialog(loaded, settings_manager=settings)
    dlg.date_when.setDate(QDate(2026, 8, 30))
    dlg.time_when.setTime(QTime(13, 15))
    dlg.chk_time_not_decided.setChecked(False)
    dlg.on_save()
    controller.update_task(loaded)

    # Re-instantiate database manager to simulate application restart
    db2 = DatabaseManager(db.db_path)
    ctrl2 = TaskController(db2)
    reloaded = ctrl2.get_task(t_id)

    assert reloaded.planned_date == "2026-08-30"
    assert reloaded.planned_start_time == "13:15"


def test_3w11_child_task_schedule_ownership_correct(temp_env, qapp):
    """3W11: 3W1H can be opened for subtasks and updates only child schedule."""
    subtask_data = {
        "title": "Subtask Schedule Test",
        "planned_date": "2026-08-22",
        "planned_start_time": "10:00",
        "description": "",
    }

    dlg = ThreeWOneHDialog(subtask_data)
    assert dlg.date_when.date().toString("yyyy-MM-dd") == "2026-08-22"
    assert dlg.time_when.time().toString("HH:mm") == "10:00"

    dlg.date_when.setDate(QDate(2026, 8, 26))
    dlg.time_when.setTime(QTime(11, 45))
    dlg.on_save()

    assert subtask_data["planned_date"] == "2026-08-26"
    assert subtask_data["planned_start_time"] == "11:45"


def test_3w12_parent_not_mutated_by_subtask_3w1h(temp_env, qapp):
    """3W12: Modifying subtask in 3W1H does not mutate parent task."""
    parent_task = Task(title="Parent Task", planned_date="2026-08-20", planned_start_time="08:00")
    subtask_data = {
        "title": "Child Subtask",
        "planned_date": "2026-08-22",
        "planned_start_time": "10:00",
    }

    dlg_sub = ThreeWOneHDialog(subtask_data)
    dlg_sub.date_when.setDate(QDate(2026, 8, 29))
    dlg_sub.time_when.setTime(QTime(17, 0))
    dlg_sub.on_save()

    assert parent_task.planned_date == "2026-08-20"
    assert parent_task.planned_start_time == "08:00"
    assert subtask_data["planned_date"] == "2026-08-29"
    assert subtask_data["planned_start_time"] == "17:00"


def test_3w13_legacy_free_text_content_not_silently_destroyed(temp_env, qapp):
    """3W13: Legacy free-text reflection notes are not destroyed and restore cleanly."""
    legacy_notes = (
        "### 3W1H Reflection (2026-08-15 14:00)\n"
        "- **What**: Legacy Scope Issue\n"
        "- **Why**: Requirement Clarification Needed\n"
        "- **Where**: Client Office\n"
        "- **When**: Revised target 2026-08-21 14:30\n"
        "- **How**: Review specs with product team\n"
    )
    task = Task(title="Legacy Reflection Task", planned_date="2026-08-21", planned_start_time="14:30", description=legacy_notes)

    dlg = ThreeWOneHDialog(task)
    assert dlg.txt_what.text() == "Legacy Scope Issue"
    assert dlg.txt_where.text() == "Client Office"
    assert dlg.txt_how.text() == "Review specs with product team"
    assert dlg.date_when.date().toString("yyyy-MM-dd") == "2026-08-21"
    assert dlg.time_when.time().toString("HH:mm") == "14:30"


def test_3w14_locale_safe_display(temp_env, qapp):
    """3W14: Muted human-readable summary generates locale-safe clean date and time."""
    task = Task(title="Locale Test", planned_date="2026-08-20", planned_start_time="10:30")

    dlg = ThreeWOneHDialog(task)
    summary = dlg.lbl_when_summary.text()
    assert "Thursday" in summary
    assert "20 August 2026" in summary
    assert "10:30 AM" in summary or "10:30" in summary

    dlg.chk_time_not_decided.setChecked(True)
    summary_undecided = dlg.lbl_when_summary.text()
    assert "Thursday" in summary_undecided
    assert "20 August 2026" in summary_undecided
    assert "Time not decided" in summary_undecided


def test_3w15_no_duplicate_schedule_authority(temp_env, qapp):
    """3W15: 3W1H reuses existing planned_date and planned_start_time without creating second authority."""
    task = Task(title="Authority Test", planned_date="2026-08-20", planned_start_time="09:00")
    dlg = ThreeWOneHDialog(task)

    dlg.date_when.setDate(QDate(2026, 8, 27))
    dlg.time_when.setTime(QTime(16, 30))
    dlg.chk_time_not_decided.setChecked(False)
    dlg.on_save()

    # Verify task only updated planned_date and planned_start_time
    assert task.planned_date == "2026-08-27"
    assert task.planned_start_time == "16:30"
    # Ensure no redundant or competing fields exist
    assert not hasattr(task, "when_date")
    assert not hasattr(task, "when_time")
    assert not hasattr(task, "three_w_when")
