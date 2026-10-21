"""
Comprehensive Hierarchy Execution & Effort Truth Test Suite (Batch 3.4)
Validates Five-Authority Contract across Main Task, Subtask, and Sub-Subtask:
1. Planned Elapsed Span
2. Planned Work Effort
3. Daily Dedication / Allocation Mode (Fixed Daily, Total Effort, Custom by Day)
4. Actual Work Effort
5. Actual Elapsed Span
"""

import os
import tempfile
import pytest
from datetime import date, datetime
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QDate, QTime

from todo_bird_app.models.task import Task, TaskPriority, TaskStatus
from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.utils.time_math import (
    duration_between,
    calculate_actual_elapsed_minutes,
    format_duration_display,
)
from todo_bird_app.utils.working_calendar import (
    calculate_planned_effort,
    get_working_days_between,
    is_working_day,
    set_configured_working_weekdays,
    set_default_daily_capacity_minutes,
)
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.work_effort_editor import WorkEffortEditor


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_db():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_batch34.db")
    db = DatabaseManager(db_path=db_path)
    # Ensure default Mon-Fri working calendar
    set_configured_working_weekdays([0, 1, 2, 3, 4])
    set_default_daily_capacity_minutes(480)
    yield db


# =========================================================================
# HA01 to HA06: Actual Span vs Actual Effort Authority Tests
# =========================================================================

def test_ha01_multi_day_actual_span_calendar_independent():
    """HA01: Actual Elapsed Span calculation is calendar-independent and NOT reduced by working calendar."""
    # 13 Aug 2026 (Thu) 09:00 -> 15 Aug 2026 (Sat) 17:00 = 56 hours = 3360 minutes
    span = calculate_actual_elapsed_minutes("2026-08-13", "09:00", "2026-08-15", "17:00")
    assert span == 3360
    assert format_duration_display(span) == "56h"


def test_ha02_actual_work_effort_independent_from_actual_span():
    """HA02: Actual Work Effort is stored independently from Actual Elapsed Span in Task model."""
    t = Task(
        title="Main Task Actual",
        actual_start_date="2026-08-13",
        actual_start_time="09:00",
        actual_end_date="2026-08-15",
        actual_end_time="17:00",
        actual_duration=360,  # 6h logged active work effort
    )
    assert t.actual_elapsed_minutes == 3360  # 56h calendar span
    assert t.actual_duration == 360          # 6h work effort


def test_ha03_task_dialog_actual_span_and_effort_separation(qapp):
    """HA03: TaskDialog UI displays both Actual Elapsed Span and Actual Effort."""
    t = Task(
        title="Dialog Actual Test",
        actual_start_date="2026-08-13",
        actual_start_time="09:00",
        actual_end_date="2026-08-15",
        actual_end_time="17:00",
        actual_duration=360,
    )
    dialog = TaskDialog(projects=[], task=t)
    assert dialog.actual_enabled_check.isChecked()
    assert "56h" in dialog.actual_elapsed_label.text()
    assert dialog.actual_duration_spin.value() == 360


def test_ha04_subtask_actual_span_calculation():
    """HA04: Subtask Actual Span calculation across days without working-calendar reduction."""
    # 14 Aug 2026 (Fri) 10:00 -> 16 Aug 2026 (Sun) 17:00 = 55h = 3300 mins
    span = calculate_actual_elapsed_minutes("2026-08-14", "10:00", "2026-08-16", "17:00")
    assert span == 3300


def test_ha05_subtask_actual_effort_decoupled_from_span(temp_db):
    """HA05: Subtask Actual Effort (e.g. 120 mins) is decoupled from Subtask Actual Span (3300 mins)."""
    t_id = temp_db.insert_task(Task(title="Parent Task"))
    sub_id = temp_db.insert_subtask(
        task_id=t_id,
        title="Subtask Testing",
        actual_start_date="2026-08-14",
        actual_start_time="10:00",
        actual_end_date="2026-08-16",
        actual_end_time="17:00",
        actual_duration=120,
    )
    tree = temp_db.get_subtask_tree(t_id)
    assert len(tree) == 1
    sub = tree[0]
    assert sub["actual_duration"] == 120
    span = calculate_actual_elapsed_minutes(
        sub["actual_start_date"], sub["actual_start_time"],
        sub["actual_end_date"], sub["actual_end_time"]
    )
    assert span == 3300


def test_ha06_sub_subtask_actual_span_and_effort(temp_db):
    """HA06: Sub-subtask Actual Span and Actual Effort are decoupled and independently preserved."""
    t_id = temp_db.insert_task(Task(title="Parent Task"))
    parent_sub_id = temp_db.insert_subtask(task_id=t_id, title="Parent Subtask")
    child_sub_id = temp_db.insert_subtask(
        task_id=t_id,
        title="Sub-subtask Deep Execution",
        parent_subtask_id=parent_sub_id,
        actual_start_date="2026-08-13",
        actual_start_time="08:00",
        actual_end_date="2026-08-14",
        actual_end_time="12:00",
        actual_duration=180,  # 3h work effort
    )
    tree = temp_db.get_subtask_tree(t_id)
    child = tree[0]["children"][0]
    assert child["id"] == child_sub_id
    assert child["actual_duration"] == 180
    span = calculate_actual_elapsed_minutes(
        child["actual_start_date"], child["actual_start_time"],
        child["actual_end_date"], child["actual_end_time"]
    )
    assert span == 1680  # 28 hours


# =========================================================================
# HS01 to HS10: Subtask Five-Authority Parity Tests
# =========================================================================

def test_hs01_subtask_planned_elapsed_span():
    """HS01: Subtask Planned Elapsed Span is full calendar span."""
    # 13 Aug 07:00 -> 15 Aug 13:40 = 54h 40m = 3280 mins
    span = duration_between("2026-08-13", "07:00", "2026-08-15", "13:40")
    assert span == 3280


def test_hs02_subtask_fixed_daily_effort():
    """HS02: Subtask Fixed Daily effort calculation across Mon-Fri working days."""
    set_configured_working_weekdays([0, 1, 2, 3, 4])
    # 13 Aug (Thu) to 15 Aug (Sat) with 4h/day (240m) = 2 working days (Thu, Fri) * 240 = 480m (8h)
    effort = calculate_planned_effort("2026-08-13", "2026-08-15", 240, allocation_mode="fixed_daily")
    assert effort == 480


def test_hs03_subtask_total_effort_distribution():
    """HS03: Subtask Total Effort mode returns exact total effort."""
    effort = calculate_planned_effort("2026-08-13", "2026-08-15", 0, allocation_mode="total_effort", total_effort_minutes=601)
    assert effort == 601


def test_hs04_subtask_custom_by_day_effort_and_overrides():
    """HS04: Subtask Custom by Day sums per-day minutes with working days and non-working overrides."""
    set_configured_working_weekdays([0, 1, 2, 3, 4])  # Mon-Fri
    custom_map = {
        "2026-08-13": 180,  # Thu (working): 3h
        "2026-08-14": 180,  # Fri (working): 3h
        "2026-08-15": 90,   # Sat (non-working override): 1h30
    }
    effort = calculate_planned_effort("2026-08-13", "2026-08-15", 0, allocation_mode="custom_by_day", custom_allocations=custom_map)
    assert effort == 450  # 7h 30m


def test_hs05_subtask_custom_allocations_db_persistence(temp_db):
    """HS05: Subtask Custom by Day allocations persist to task_allocations with subtask_id."""
    t_id = temp_db.insert_task(Task(title="Main Task"))
    sub_id = temp_db.insert_subtask(task_id=t_id, title="Subtask A", allocation_mode="custom_by_day")

    allocs = [
        {"allocation_date": "2026-08-13", "planned_minutes": 180},
        {"allocation_date": "2026-08-14", "planned_minutes": 180},
        {"allocation_date": "2026-08-15", "planned_minutes": 90},
    ]
    temp_db.set_task_allocations(task_id=t_id, subtask_id=sub_id, allocations=allocs)

    saved_allocs = temp_db.get_task_allocations(task_id=t_id, subtask_id=sub_id)
    assert len(saved_allocs) == 3
    assert saved_allocs[0]["allocation_date"] == "2026-08-13"
    assert saved_allocs[0]["planned_minutes"] == 180
    assert saved_allocs[2]["allocation_date"] == "2026-08-15"
    assert saved_allocs[2]["planned_minutes"] == 90


def test_hs06_subtask_custom_allocations_loaded_in_tree(temp_db):
    """HS06: Subtask tree loads custom allocations attached to subtask dict."""
    t_id = temp_db.insert_task(Task(title="Main Task"))
    sub_id = temp_db.insert_subtask(task_id=t_id, title="Subtask A", allocation_mode="custom_by_day")

    temp_db.set_task_allocations(
        task_id=t_id,
        subtask_id=sub_id,
        allocations=[
            {"allocation_date": "2026-08-13", "planned_minutes": 180},
            {"allocation_date": "2026-08-14", "planned_minutes": 180},
        ]
    )

    tree = temp_db.get_subtask_tree(t_id)
    assert len(tree) == 1
    assert tree[0]["custom_allocations"] == {
        "2026-08-13": 180,
        "2026-08-14": 180,
    }


def test_hs07_subtask_allocations_idempotent_save(temp_db):
    """HS07: Repeated saves in task_allocations for subtask are idempotent (no duplicates)."""
    t_id = temp_db.insert_task(Task(title="Main Task"))
    sub_id = temp_db.insert_subtask(task_id=t_id, title="Subtask A")

    allocs1 = [{"allocation_date": "2026-08-13", "planned_minutes": 120}]
    temp_db.set_task_allocations(task_id=t_id, subtask_id=sub_id, allocations=allocs1)
    temp_db.set_task_allocations(task_id=t_id, subtask_id=sub_id, allocations=allocs1)
    temp_db.set_task_allocations(task_id=t_id, subtask_id=sub_id, allocations=allocs1)

    rows = temp_db.get_task_allocations(task_id=t_id, subtask_id=sub_id)
    assert len(rows) == 1
    assert rows[0]["planned_minutes"] == 120


def test_hs08_work_effort_editor_date_change(qapp):
    """HS08: WorkEffortEditor handles date change while preserving existing custom allocations."""
    editor = WorkEffortEditor(
        start_date="2026-08-13",
        due_date="2026-08-14",
        allocation_mode="custom_by_day",
        custom_allocations={"2026-08-13": 120, "2026-08-14": 120},
    )
    assert editor.get_data()["planned_effort_minutes"] == 240

    # Extend date range to 15 Aug
    editor.set_dates("2026-08-13", "2026-08-15")
    # Existing allocations for 13 and 14 are preserved
    assert editor._custom_allocations.get("2026-08-13") == 120
    assert editor._custom_allocations.get("2026-08-14") == 120


def test_hs09_subtask_actual_execution_saved_in_dialog(qapp, temp_db):
    """HS09: Subtask Actual execution tracking is preserved on save/load in TaskDialog."""
    t = Task(id=1, title="Main Task")
    temp_db.insert_task(t)
    sub_id = temp_db.insert_subtask(
        task_id=1,
        title="Sub 1",
        actual_start_date="2026-08-14",
        actual_start_time="10:00",
        actual_end_date="2026-08-16",
        actual_end_time="17:00",
        actual_duration=120,
    )

    dialog = TaskDialog(projects=[], task=t, db_manager=temp_db)
    pending = dialog._collect_subtask_tree()
    assert len(pending) == 1
    sub = pending[0]
    assert sub["actual_start_date"] == "2026-08-14"
    assert sub["actual_end_date"] == "2026-08-16"
    assert sub["actual_duration"] == 120


def test_hs10_work_effort_editor_mode_switching(qapp):
    """HS10: Switching allocation mode dynamically updates planned effort and UI state."""
    editor = WorkEffortEditor(
        start_date="2026-08-13",
        due_date="2026-08-15",
        allocation_mode="fixed_daily",
        daily_dedication_minutes=240,
    )
    # Fixed daily: 2 working days (Thu, Fri) * 240 = 480
    assert editor.get_data()["planned_effort_minutes"] == 480
    assert editor.custom_alloc_frame.isHidden()

    # Switch to total effort
    editor.allocation_mode_combo.setCurrentIndex(1)
    editor.planned_effort_spin.setValue(600)
    assert editor.get_data()["planned_effort_minutes"] == 600
    assert editor.custom_alloc_frame.isHidden()

    # Switch to custom by day
    editor.allocation_mode_combo.setCurrentIndex(2)
    assert not editor.custom_alloc_frame.isHidden()


# =========================================================================
# HSS01 to HSS10: Sub-subtask Five-Authority Parity Tests
# =========================================================================

def test_hss01_sub_subtask_planned_elapsed_span():
    """HSS01: Sub-subtask Planned Elapsed Span calculation."""
    span = duration_between("2026-08-13", "08:00", "2026-08-14", "18:00")
    assert span == 2040  # 34 hours


def test_hss02_sub_subtask_fixed_daily_effort():
    """HSS02: Sub-subtask Fixed Daily effort calculation."""
    set_configured_working_weekdays([0, 1, 2, 3, 4])
    effort = calculate_planned_effort("2026-08-13", "2026-08-14", 120, allocation_mode="fixed_daily")
    assert effort == 240  # 2 days * 2h = 4h


def test_hss03_sub_subtask_total_effort_distribution():
    """HSS03: Sub-subtask Total Effort distribution."""
    effort = calculate_planned_effort("2026-08-13", "2026-08-14", 0, allocation_mode="total_effort", total_effort_minutes=350)
    assert effort == 350


def test_hss04_sub_subtask_custom_by_day_effort_and_overrides():
    """HSS04: Sub-subtask Custom by Day allocation table and override tracking."""
    custom_map = {
        "2026-08-13": 60,
        "2026-08-14": 90,
        "2026-08-15": 30,  # Non-working override
    }
    effort = calculate_planned_effort("2026-08-13", "2026-08-15", 0, allocation_mode="custom_by_day", custom_allocations=custom_map)
    assert effort == 180


def test_hss05_sub_subtask_allocations_db_persistence(temp_db):
    """HSS05: Sub-subtask allocations persist to task_allocations with unique sub-subtask id."""
    t_id = temp_db.insert_task(Task(title="Main Task"))
    parent_sub_id = temp_db.insert_subtask(task_id=t_id, title="Subtask")
    child_sub_id = temp_db.insert_subtask(
        task_id=t_id,
        title="Sub-subtask",
        parent_subtask_id=parent_sub_id,
        allocation_mode="custom_by_day",
    )

    allocs = [
        {"allocation_date": "2026-08-13", "planned_minutes": 60},
        {"allocation_date": "2026-08-14", "planned_minutes": 60},
    ]
    temp_db.set_task_allocations(task_id=t_id, subtask_id=child_sub_id, allocations=allocs)

    saved = temp_db.get_task_allocations(task_id=t_id, subtask_id=child_sub_id)
    assert len(saved) == 2
    assert saved[0]["planned_minutes"] == 60


def test_hss06_sub_subtask_allocations_reloaded_in_tree(temp_db):
    """HSS06: Sub-subtask allocations are reloaded into get_subtask_tree."""
    t_id = temp_db.insert_task(Task(title="Main Task"))
    p_id = temp_db.insert_subtask(task_id=t_id, title="Parent")
    c_id = temp_db.insert_subtask(task_id=t_id, title="Child", parent_subtask_id=p_id)

    temp_db.set_task_allocations(
        task_id=t_id,
        subtask_id=c_id,
        allocations=[{"allocation_date": "2026-08-13", "planned_minutes": 45}]
    )

    tree = temp_db.get_subtask_tree(t_id)
    child = tree[0]["children"][0]
    assert child["custom_allocations"] == {"2026-08-13": 45}


def test_hss07_sub_subtask_repeated_save_idempotence(temp_db):
    """HSS07: Sub-subtask repeated saves are idempotent in SQLite."""
    t_id = temp_db.insert_task(Task(title="Main Task"))
    p_id = temp_db.insert_subtask(task_id=t_id, title="Parent")
    c_id = temp_db.insert_subtask(task_id=t_id, title="Child", parent_subtask_id=p_id)

    allocs = [{"allocation_date": "2026-08-13", "planned_minutes": 75}]
    temp_db.set_task_allocations(task_id=t_id, subtask_id=c_id, allocations=allocs)
    temp_db.set_task_allocations(task_id=t_id, subtask_id=c_id, allocations=allocs)

    rows = temp_db.get_task_allocations(task_id=t_id, subtask_id=c_id)
    assert len(rows) == 1
    assert rows[0]["planned_minutes"] == 75


def test_hss08_sub_subtask_actual_elapsed_span_vs_effort():
    """HSS08: Sub-subtask Actual Elapsed Span vs Actual Effort."""
    span = calculate_actual_elapsed_minutes("2026-08-13", "10:00", "2026-08-14", "12:00")
    assert span == 1560  # 26h
    actual_effort = 120  # 2h logged
    assert span != actual_effort


def test_hss09_sub_subtask_progress_independence(temp_db):
    """HSS09: Sub-subtask progress is independent of parent task progress."""
    t_id = temp_db.insert_task(Task(title="Main Task", progress=10))
    p_id = temp_db.insert_subtask(task_id=t_id, title="Parent", progress=20)
    c_id = temp_db.insert_subtask(task_id=t_id, title="Child", parent_subtask_id=p_id, progress=80)

    tree = temp_db.get_subtask_tree(t_id)
    assert tree[0]["progress"] == 20
    assert tree[0]["children"][0]["progress"] == 80


def test_hss10_sub_subtask_deep_hierarchy_persistence(temp_db):
    """HSS10: Deep hierarchy with effort & allocations persists cleanly."""
    t_id = temp_db.insert_task(Task(title="Main Project Task"))
    p_id = temp_db.insert_subtask(task_id=t_id, title="Phase 1", planned_effort_minutes=480)
    c_id = temp_db.insert_subtask(
        task_id=t_id,
        title="Module 1.1",
        parent_subtask_id=p_id,
        planned_effort_minutes=240,
        daily_dedication_minutes=120,
    )

    tree = temp_db.get_subtask_tree(t_id)
    assert len(tree) == 1
    assert tree[0]["title"] == "Phase 1"
    assert tree[0]["planned_effort_minutes"] == 480
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["title"] == "Module 1.1"
    assert tree[0]["children"][0]["planned_effort_minutes"] == 240
    assert tree[0]["children"][0]["daily_dedication_minutes"] == 120


# =========================================================================
# HI01 to HI04: Parent/Sibling Hierarchy Isolation Tests
# =========================================================================

def test_hi01_subtask_edit_does_not_mutate_parent(temp_db):
    """HI01: Editing a subtask does not overwrite parent task Planned Span, Planned Effort, or Actual Effort."""
    parent_task = Task(
        title="Parent Task",
        estimated_duration=3280,
        planned_effort_minutes=480,
        actual_duration=360,
    )
    t_id = temp_db.insert_task(parent_task)
    sub_id = temp_db.insert_subtask(
        task_id=t_id,
        title="Child Subtask",
        estimated_duration=120,
        planned_effort_minutes=120,
        actual_duration=60,
    )

    # Re-fetch parent task
    parent_loaded = temp_db.get_task_by_id(t_id)
    assert parent_loaded["estimated_duration"] == 3280
    assert parent_loaded["planned_effort_minutes"] == 480
    assert parent_loaded["actual_duration"] == 360


def test_hi02_sub_subtask_edit_does_not_mutate_parent_subtask(temp_db):
    """HI02: Editing a sub-subtask does not overwrite parent subtask Planned Span, Planned Effort, or Actual Effort."""
    t_id = temp_db.insert_task(Task(title="Main Task"))
    p_id = temp_db.insert_subtask(
        task_id=t_id,
        title="Parent Subtask",
        estimated_duration=600,
        planned_effort_minutes=300,
        actual_duration=150,
    )
    c_id = temp_db.insert_subtask(
        task_id=t_id,
        title="Child Subtask",
        parent_subtask_id=p_id,
        estimated_duration=120,
        planned_effort_minutes=60,
        actual_duration=30,
    )

    tree = temp_db.get_subtask_tree(t_id)
    parent_sub = tree[0]
    assert parent_sub["estimated_duration"] == 600
    assert parent_sub["planned_effort_minutes"] == 300
    assert parent_sub["actual_duration"] == 150


def test_hi03_sibling_subtask_isolation(temp_db):
    """HI03: Sibling subtasks maintain strict data isolation in allocations."""
    t_id = temp_db.insert_task(Task(title="Main Task"))
    sub_a = temp_db.insert_subtask(task_id=t_id, title="Subtask A")
    sub_b = temp_db.insert_subtask(task_id=t_id, title="Subtask B")

    temp_db.set_task_allocations(
        task_id=t_id,
        subtask_id=sub_a,
        allocations=[{"allocation_date": "2026-08-13", "planned_minutes": 100}]
    )
    temp_db.set_task_allocations(
        task_id=t_id,
        subtask_id=sub_b,
        allocations=[{"allocation_date": "2026-08-13", "planned_minutes": 200}]
    )

    allocs_a = temp_db.get_task_allocations(task_id=t_id, subtask_id=sub_a)
    allocs_b = temp_db.get_task_allocations(task_id=t_id, subtask_id=sub_b)

    assert len(allocs_a) == 1
    assert allocs_a[0]["planned_minutes"] == 100
    assert len(allocs_b) == 1
    assert allocs_b[0]["planned_minutes"] == 200


def test_hi04_subtask_deletion_isolates_allocations(temp_db):
    """HI04: Deleting a subtask removes its allocations without touching parent or sibling allocations."""
    t_id = temp_db.insert_task(Task(title="Main Task"))
    temp_db.set_task_allocations(
        task_id=t_id,
        subtask_id=None,
        allocations=[{"allocation_date": "2026-08-13", "planned_minutes": 480}]
    )
    sub_a = temp_db.insert_subtask(task_id=t_id, title="Subtask A")
    sub_b = temp_db.insert_subtask(task_id=t_id, title="Subtask B")

    temp_db.set_task_allocations(
        task_id=t_id,
        subtask_id=sub_a,
        allocations=[{"allocation_date": "2026-08-13", "planned_minutes": 100}]
    )
    temp_db.set_task_allocations(
        task_id=t_id,
        subtask_id=sub_b,
        allocations=[{"allocation_date": "2026-08-13", "planned_minutes": 200}]
    )

    # Delete subtask A
    temp_db.delete_subtask(sub_a)
    # Also clean up its allocations
    temp_db.set_task_allocations(task_id=t_id, subtask_id=sub_a, allocations=[])

    # Check main task allocations intact
    main_allocs = temp_db.get_task_allocations(task_id=t_id, subtask_id=None)
    assert len(main_allocs) == 1
    assert main_allocs[0]["planned_minutes"] == 480

    # Check subtask B allocations intact
    b_allocs = temp_db.get_task_allocations(task_id=t_id, subtask_id=sub_b)
    assert len(b_allocs) == 1
    assert b_allocs[0]["planned_minutes"] == 200
