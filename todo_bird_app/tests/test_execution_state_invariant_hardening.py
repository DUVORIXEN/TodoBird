"""
TODO BIRD — EXECUTION STATE INVARIANT HARDENING TEST SUITE

Tests the frozen execution authority invariants across:
1. ExecutionPerformanceService anomaly classification & validation
2. TaskDialog save-time rejection and form retention
3. DatabaseManager write-path invariant protection on insert and update
4. Compatibility: Permissive reading of existing records and preservation of valid states
"""

import os
import tempfile
from datetime import date, datetime
import pytest
from PySide6.QtWidgets import QMessageBox

from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.services.execution_performance_service import (
    ExecutionPerformanceService,
    ExecutionAnomalyCode,
    ExecutionStateInvariantError,
    HARD_INVARIANT_ANOMALIES,
)
from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.widgets.task_dialog import TaskDialog
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db", prefix="tb_test_invariant_")
    os.close(fd)
    db = DatabaseManager(path)
    yield db
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


@pytest.fixture
def temp_settings(temp_db):
    from pathlib import Path
    temp_dir = tempfile.mkdtemp(prefix="tb_test_settings_")
    settings = SettingsManager(db_manager=temp_db, config_dir=Path(temp_dir))
    yield settings


# =============================================================================
# PART A: ExecutionPerformanceService Canonical Anomaly Detection
# =============================================================================

def test_invariant_planned_no_actual_accepted():
    """Planned + no Actual = accepted."""
    task = Task(title="Planned Task", status=TaskStatus.PLANNED)
    violations = ExecutionPerformanceService.validate_execution_invariants(task)
    assert violations == []


def test_invariant_planned_with_actual_start_rejected():
    """Planned + Actual Start = rejected."""
    task = Task(
        title="Planned With Start",
        status=TaskStatus.PLANNED,
        actual_start_date="2026-08-15",
    )
    violations = ExecutionPerformanceService.validate_execution_invariants(task)
    assert len(violations) >= 1
    codes = [code for code, _ in violations]
    assert ExecutionAnomalyCode.STATUS_PLANNED_WITH_ACTUAL_START in codes


def test_invariant_planned_with_actual_finish_rejected():
    """Planned + Actual Finish = rejected."""
    task = Task(
        title="Planned With Finish",
        status=TaskStatus.PLANNED,
        actual_end_date="2026-08-15",
    )
    violations = ExecutionPerformanceService.validate_execution_invariants(task)
    assert len(violations) >= 1
    codes = [code for code, _ in violations]
    assert ExecutionAnomalyCode.STATUS_PLANNED_WITH_ACTUAL_FINISH in codes


def test_invariant_in_progress_with_actual_start_no_finish_accepted():
    """In Progress + Actual Start / no finish = accepted."""
    task = Task(
        title="Active In Progress",
        status=TaskStatus.IN_PROGRESS,
        actual_start_date="2026-08-15",
        actual_start_time="09:00",
    )
    violations = ExecutionPerformanceService.validate_execution_invariants(task)
    assert violations == []


def test_invariant_in_progress_without_actual_start_rejected():
    """In Progress without Actual Start = rejected."""
    task = Task(
        title="In Progress No Start",
        status=TaskStatus.IN_PROGRESS,
    )
    violations = ExecutionPerformanceService.validate_execution_invariants(task)
    assert len(violations) >= 1
    codes = [code for code, _ in violations]
    assert ExecutionAnomalyCode.STATUS_IN_PROGRESS_WITHOUT_ACTUAL_START in codes


def test_invariant_in_progress_with_actual_finish_rejected():
    """In Progress + Actual Finish = rejected."""
    task = Task(
        title="In Progress With Finish",
        status=TaskStatus.IN_PROGRESS,
        actual_start_date="2026-08-15",
        actual_end_date="2026-08-16",
    )
    violations = ExecutionPerformanceService.validate_execution_invariants(task)
    assert len(violations) >= 1
    codes = [code for code, _ in violations]
    assert ExecutionAnomalyCode.STATUS_IN_PROGRESS_BUT_FINISHED in codes


def test_invariant_actual_finish_without_actual_start_rejected():
    """Actual Finish without Actual Start = rejected."""
    task = Task(
        title="Finish Without Start",
        status=TaskStatus.COMPLETED,
        actual_end_date="2026-08-16",
    )
    violations = ExecutionPerformanceService.validate_execution_invariants(task)
    assert len(violations) >= 1
    codes = [code for code, _ in violations]
    assert ExecutionAnomalyCode.ACTUAL_FINISH_WITHOUT_START in codes


def test_invariant_actual_finish_before_actual_start_rejected():
    """Actual Finish before Actual Start = rejected."""
    task = Task(
        title="Finish Before Start",
        status=TaskStatus.COMPLETED,
        actual_start_date="2026-08-16",
        actual_start_time="10:00",
        actual_end_date="2026-08-15",
        actual_end_time="10:00",
    )
    violations = ExecutionPerformanceService.validate_execution_invariants(task)
    assert len(violations) >= 1
    codes = [code for code, _ in violations]
    assert ExecutionAnomalyCode.ACTUAL_FINISH_BEFORE_START in codes


def test_invariant_completed_with_valid_actuals_accepted():
    """Completed with valid Actual Start + Finish = accepted."""
    task = Task(
        title="Valid Completed",
        status=TaskStatus.COMPLETED,
        actual_start_date="2026-08-15",
        actual_start_time="09:00",
        actual_end_date="2026-08-15",
        actual_end_time="17:00",
    )
    violations = ExecutionPerformanceService.validate_execution_invariants(task)
    assert violations == []


def test_invariant_valid_delayed_active_state_accepted():
    """Valid Delayed active state (Actual Start, no Actual Finish) remains accepted."""
    task = Task(
        title="Active Delayed Task",
        status=TaskStatus.DELAYED,
        actual_start_date="2026-08-13",
        actual_start_time="09:00",
        progress=60,
    )
    violations = ExecutionPerformanceService.validate_execution_invariants(task)
    assert violations == []


def test_invariant_delayed_with_actual_finish_rejected():
    """Delayed with Actual Finish = rejected (Delayed tasks are active, not finished)."""
    task = Task(
        title="Delayed With Finish",
        status=TaskStatus.DELAYED,
        actual_start_date="2026-08-13",
        actual_end_date="2026-08-14",
    )
    violations = ExecutionPerformanceService.validate_execution_invariants(task)
    assert len(violations) >= 1
    codes = [code for code, _ in violations]
    assert ExecutionAnomalyCode.STATUS_DELAYED_WITH_ACTUAL_FINISH in codes


def test_invariant_valid_blocked_active_state_accepted():
    """Valid Blocked state (both unstarted and active with start but no finish) accepted."""
    # 1. Blocked before start
    task_unstarted = Task(title="Blocked Unstarted", status=TaskStatus.BLOCKED)
    assert ExecutionPerformanceService.validate_execution_invariants(task_unstarted) == []

    # 2. Blocked after start
    task_active = Task(
        title="Blocked Active",
        status=TaskStatus.BLOCKED,
        actual_start_date="2026-08-14",
        actual_start_time="10:00",
    )
    assert ExecutionPerformanceService.validate_execution_invariants(task_active) == []

    # 3. Blocked with finish is rejected
    task_finished = Task(
        title="Blocked Finished",
        status=TaskStatus.BLOCKED,
        actual_start_date="2026-08-14",
        actual_end_date="2026-08-15",
    )
    violations = ExecutionPerformanceService.validate_execution_invariants(task_finished)
    codes = [code for code, _ in violations]
    assert ExecutionAnomalyCode.STATUS_BLOCKED_WITH_ACTUAL_FINISH in codes


# =============================================================================
# PART B: TaskDialog Save Validation and Form Field Retention
# =============================================================================

def test_task_dialog_prevents_invalid_save(qapp, temp_db, temp_settings, monkeypatch):
    """TaskDialog prevents saving invalid combinations and displays warning."""
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, msg, *args, **kwargs: warnings.append((title, msg)),
    )

    task = Task(title="Dialog Test Task", status=TaskStatus.PLANNED)
    dlg = TaskDialog(projects=[], task=task, db_manager=temp_db, settings_manager=temp_settings)

    # Set status to In Progress, but don't check actual_enabled_check (no Actual Start)
    idx = dlg.status_combo.findData(TaskStatus.IN_PROGRESS)
    dlg.status_combo.setCurrentIndex(idx)
    assert dlg.actual_enabled_check.isChecked() is False

    dlg.on_save()

    # Rejection should occur
    assert len(warnings) == 1
    title, msg = warnings[0]
    assert title == "Invalid Execution State"
    assert "In Progress" in msg
    assert "Actual Start" in msg

    # Task was not saved to DB
    all_tasks = temp_db.get_all_tasks()
    assert len(all_tasks) == 0


def test_task_dialog_preserves_fields_after_validation_failure(qapp, temp_db, temp_settings, monkeypatch):
    """TaskDialog preserves all user-entered fields after validation failure."""
    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda parent, title, msg, *args, **kwargs: warnings.append((title, msg)),
    )

    task = Task(title="Initial Title", status=TaskStatus.PLANNED)
    dlg = TaskDialog(projects=[], task=task, db_manager=temp_db, settings_manager=temp_settings)

    # Enter custom fields
    dlg.title_input.setText("Modified Title Not Saved")
    dlg.tags_input.setText("urgent, critical")
    idx = dlg.status_combo.findData(TaskStatus.IN_PROGRESS)
    dlg.status_combo.setCurrentIndex(idx)

    # Trigger save which fails
    dlg.on_save()
    assert len(warnings) == 1

    # Dialog state is preserved and not closed
    assert dlg.title_input.text() == "Modified Title Not Saved"
    assert dlg.tags_input.text() == "urgent, critical"
    assert dlg.status_combo.currentData() == TaskStatus.IN_PROGRESS


# =============================================================================
# PART C: Database Write-Path Invariant Protection
# =============================================================================

def test_db_insert_rejects_invalid_execution_state(temp_db):
    """DB insert rejects invalid execution states with ExecutionStateInvariantError."""
    # 1. Planned with actual start
    with pytest.raises(ExecutionStateInvariantError) as exc_info:
        temp_db.insert_task({
            "title": "Invalid Planned",
            "status": "planned",
            "actual_start_date": "2026-08-15",
        })
    assert exc_info.value.anomaly_code == ExecutionAnomalyCode.STATUS_PLANNED_WITH_ACTUAL_START

    # 2. In Progress without actual start
    with pytest.raises(ExecutionStateInvariantError) as exc_info:
        temp_db.insert_task({
            "title": "Invalid In Progress",
            "status": "in_progress",
        })
    assert exc_info.value.anomaly_code == ExecutionAnomalyCode.STATUS_IN_PROGRESS_WITHOUT_ACTUAL_START

    # 3. Finish without start
    with pytest.raises(ExecutionStateInvariantError) as exc_info:
        temp_db.insert_task({
            "title": "Invalid Finish",
            "status": "completed",
            "actual_end_date": "2026-08-15",
        })
    assert exc_info.value.anomaly_code == ExecutionAnomalyCode.ACTUAL_FINISH_WITHOUT_START


def test_db_update_rejects_invalid_execution_state(temp_db):
    """DB update rejects mutations resulting in invalid execution state."""
    # Insert a valid planned task
    task_id = temp_db.insert_task({
        "title": "Valid Planned Task",
        "status": "planned",
    })
    assert task_id is not None

    # Attempt updating to In Progress without setting actual_start_date
    with pytest.raises(ExecutionStateInvariantError) as exc_info:
        temp_db.update_task({
            "id": task_id,
            "title": "Valid Planned Task",
            "status": "in_progress",
        })
    assert exc_info.value.anomaly_code == ExecutionAnomalyCode.STATUS_IN_PROGRESS_WITHOUT_ACTUAL_START

    # Task remains intact with planned status in DB
    row = temp_db.get_task_by_id(task_id)
    assert row["status"] == "planned"


def test_valid_existing_operations_pass(temp_db):
    """Valid tasks insert, update, and persist without errors."""
    # Insert planned task
    t1_id = temp_db.insert_task({"title": "Task 1", "status": "planned"})
    assert t1_id is not None

    # Transition to In Progress with actual start
    temp_db.update_task({
        "id": t1_id,
        "status": "in_progress",
        "actual_start_date": "2026-08-15",
        "actual_start_time": "09:00",
    })
    row = temp_db.get_task_by_id(t1_id)
    assert row["status"] == "in_progress"
    assert row["actual_start_date"] == "2026-08-15"

    # Transition to Completed with actual finish
    temp_db.update_task({
        "id": t1_id,
        "status": "completed",
        "actual_start_date": "2026-08-15",
        "actual_start_time": "09:00",
        "actual_end_date": "2026-08-15",
        "actual_end_time": "17:00",
    })
    row = temp_db.get_task_by_id(t1_id)
    assert row["status"] == "completed"
    assert row["actual_end_date"] == "2026-08-15"


def test_db_reading_existing_tasks_remains_permissive(temp_db):
    """Loading/reading existing tasks remains permissive without throwing."""
    # Directly inject an old invalid row using raw SQL to simulate legacy DB state
    with temp_db.get_connection() as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, title, status, actual_start_date)
            VALUES (999, 'Legacy Bad Task', 'planned', '2026-08-10')
            """
        )

    # Reading must NOT raise ExecutionStateInvariantError
    row = temp_db.get_task_by_id(999)
    assert row is not None
    assert row["title"] == "Legacy Bad Task"
    assert row["actual_start_date"] == "2026-08-10"

    tasks = temp_db.get_all_tasks()
    legacy = [t for t in tasks if t["id"] == 999]
    assert len(legacy) == 1
