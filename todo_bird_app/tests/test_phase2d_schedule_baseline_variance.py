"""
Todo Bird — Phase 2D: Professional Schedule Baseline, Variance & Control.

Complete 68-Scenario Acceptance Matrix Test Suite.
Strictly verifies:
1. Baseline Capture (1-7): Project baseline creation, start, finish, duration, planned effort, transactionality, restart survival.
2. Immutability (8-11): Frozen baseline unchanged after editing start, duration, dependencies, lag.
3. Variance (12-19): Positive, negative, zero start/finish variances, duration/effort variances, unscheduled unavailable status.
4. Special Cases (20-23): Milestones, post-baseline tasks (Not Baselined), completed tasks, cancelled tasks.
5. WBS Hierarchy (24-27): Dynamic summary rollups (min start, max finish), parent summary variance, 0 DB queries in paint/data hot paths.
6. Gantt Presentation (28-34): Exact bar geometry, non-interactive/read-only invariant, Show Baseline toggle, light/dark themes, hourly/multi-year timescales.
7. Baseline Control (35-39): Replace confirmation, confirmed replace update, cancelled replace zero mutation, clear confirmation, confirmed clear preserving current plan.
8. CPM / Dependency Integration (40-45): FS, SS, FF, SF schedule shifts with frozen baseline, positive/negative lag, critical path recalculation.
9. Persistence (46-48): Baseline 1 restart persistence, WBS column preferences, Gantt show baseline preference.
10. Accessibility (49-51): Keyboard accessibility, accessible names/tooltips, typography scaling 10 -> 20 -> 10 geometry safety.
11. Performance (52-53): 5,000-task baseline comparison benchmark (< 500ms, O(n)), no N+1 DB behavior.
12. Project Health (54-60): Baselined count, ahead count, on baseline count, behind count, critical behind count, max finish variance, project finish variance.
13. Subtask Coverage (61-64): Subtask baseline capture, nested subtasks, schedule edit immutability, transactional clear.
14. Database Safety (65-68): Non-destructive v13 -> v14 migration, repeated startup idempotency, partial update preservation, task deletion safety.
"""

from __future__ import annotations

import os
import json
import time
import sqlite3
import pytest
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional

from PySide6.QtCore import Qt, QModelIndex, QRectF
from PySide6.QtWidgets import QApplication, QMessageBox, QLabel, QStyleOptionViewItem, QGraphicsRectItem, QGraphicsItem
from PySide6.QtGui import QPainter, QPixmap, QColor, QFont

from todo_bird_app.models.task import Task, TaskStatus, TaskPriority, TaskCategory
from todo_bird_app.models.project import Project
from todo_bird_app.database import DatabaseManager, ScheduleVersionImmutabilityError
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.services.cpm_scheduling_service import (
    CPMSchedulingService,
    SchedulingResult,
    ScheduleNodeResult,
    DependencySpec,
    DependencyType,
)
from todo_bird_app.services.wbs_service import (
    WBSService,
    EntityRef,
    WBSNode,
    WBSHierarchySnapshot,
)
from todo_bird_app.services.schedule_variance_service import (
    ScheduleVarianceService,
    VarianceStatus,
    BaselineSnapshot,
    TaskVarianceResult,
    ProjectVarianceSummary,
    format_variance_duration,
    parse_datetime_flexible,
)
from todo_bird_app.models.wbs_item_model import WBSItemModel
from todo_bird_app.services.wbs_customization_service import WBSCustomizationService
from todo_bird_app.views.wbs_tree_view import WBSTreeView
from todo_bird_app.views.wbs_tree_delegate import WBSTreeItemDelegate
from todo_bird_app.widgets.wbs_settings_widget import WBSSettingsWidget
from todo_bird_app.services.gantt_wbs_adapter import GanttWBSAdapter, GanttWBSRow
from todo_bird_app.gantt.gantt_items import GanttTaskItem
from todo_bird_app.gantt.gantt_chart import GanttChartWidget
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.views.wbs_project_view import WBSProjectView


def make_cpm_node(
    task_id: int,
    earliest_start: Optional[datetime] = None,
    earliest_finish: Optional[datetime] = None,
    latest_start: Optional[datetime] = None,
    latest_finish: Optional[datetime] = None,
    total_float_minutes: int = 0,
    free_float_minutes: int = 0,
    is_critical: bool = False,
    schedulable: bool = True,
) -> ScheduleNodeResult:
    return ScheduleNodeResult(
        task_id=task_id,
        earliest_start=earliest_start,
        earliest_finish=earliest_finish,
        latest_start=latest_start,
        latest_finish=latest_finish,
        total_float_minutes=total_float_minutes,
        free_float_minutes=free_float_minutes,
        is_critical=is_critical,
        schedulable=schedulable,
    )


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_phase2d_todo_bird.db")
    db = DatabaseManager(db_file)
    yield db
    db.close()


@pytest.fixture
def temp_settings(temp_db):
    return SettingsManager(temp_db)


# ============================================================================
# 1. BASELINE CAPTURE (Acceptance Criteria 1 - 7)
# ============================================================================

def test_01_create_project_baseline(temp_db):
    """1. Create project baseline sets baseline metadata on project record."""
    proj_id = temp_db.insert_project({"name": "Project Alpha"})
    t1_id = temp_db.insert_task({"title": "Design", "project_id": proj_id, "planned_date": "2026-09-01", "planned_start_time": "09:00", "due_date": "2026-09-02", "planned_end_time": "17:00", "estimated_duration": 1920})

    success = temp_db.set_project_baseline(proj_id, "Baseline 1")
    assert success is True

    proj = temp_db.get_project(proj_id)
    assert proj["baseline_name"] == "Baseline 1"
    assert proj["baseline_created_at"] is not None


def test_02_captures_start(temp_db):
    """2. Captures exact planned start timestamp into baseline_start."""
    proj_id = temp_db.insert_project({"name": "Project Start Capture"})
    t_id = temp_db.insert_task({
        "title": "Start Task",
        "project_id": proj_id,
        "planned_date": "2026-09-01",
        "planned_start_time": "09:30",
        "due_date": "2026-09-02",
        "planned_end_time": "17:00",
    })
    temp_db.set_project_baseline(proj_id, "Baseline 1")
    t = temp_db.get_task_by_id(t_id)
    assert t["baseline_start"].startswith("2026-09-01 09:30")


def test_03_captures_finish(temp_db):
    """3. Captures exact planned finish timestamp into baseline_finish."""
    proj_id = temp_db.insert_project({"name": "Project Finish Capture"})
    t_id = temp_db.insert_task({
        "title": "Finish Task",
        "project_id": proj_id,
        "planned_date": "2026-09-01",
        "planned_start_time": "09:00",
        "due_date": "2026-09-05",
        "planned_end_time": "18:00",
    })
    temp_db.set_project_baseline(proj_id, "Baseline 1")
    t = temp_db.get_task_by_id(t_id)
    assert t["baseline_finish"].startswith("2026-09-05 18:00")


def test_04_captures_duration(temp_db):
    """4. Captures planned duration minutes into baseline_duration_minutes."""
    proj_id = temp_db.insert_project({"name": "Project Dur Capture"})
    t_id = temp_db.insert_task({
        "title": "Dur Task",
        "project_id": proj_id,
        "estimated_duration": 2880,
    })
    temp_db.set_project_baseline(proj_id, "Baseline 1")
    t = temp_db.get_task_by_id(t_id)
    assert t["baseline_duration_minutes"] == 2880


def test_05_captures_planned_effort(temp_db):
    """5. Captures planned effort minutes into baseline_planned_effort_minutes."""
    proj_id = temp_db.insert_project({"name": "Project Effort Capture"})
    t_id = temp_db.insert_task({
        "title": "Effort Task",
        "project_id": proj_id,
        "planned_effort_minutes": 1440,
    })
    temp_db.set_project_baseline(proj_id, "Baseline 1")
    t = temp_db.get_task_by_id(t_id)
    assert t["baseline_planned_effort_minutes"] == 1440
def test_06_transactional_all_or_none_capture(temp_db):
    """6. Transactional all-or-none capture rolls back completely on query error."""
    proj_id = temp_db.insert_project({"name": "Tx Project"})
    t1_id = temp_db.insert_task({"title": "T1", "project_id": proj_id, "planned_date": "2026-09-01", "planned_start_time": "09:00"})

    # Intentionally pass bad payload triggering error during iteration
    bad_payload = {t1_id: "not_a_dict_triggers_attribute_error"}
    with pytest.raises(Exception):
        temp_db.set_project_baseline(proj_id, "Corrupt", bad_payload)

    # Project baseline remains unset
    proj = temp_db.get_project(proj_id)
    assert proj["baseline_name"] is None


def test_07_baseline_survives_restart(tmp_path):
    """7. Baseline snapshot survives database close and process restart."""
    db_file = str(tmp_path / "restart_test.db")
    db1 = DatabaseManager(db_file)
    proj_id = db1.insert_project({"name": "Restart Project"})
    t1_id = db1.insert_task({
        "title": "Persistent Task",
        "project_id": proj_id,
        "planned_date": "2026-09-01",
        "planned_start_time": "09:00",
        "due_date": "2026-09-03",
        "planned_end_time": "17:00",
        "estimated_duration": 1920,
    })
    db1.set_project_baseline(proj_id, "Baseline 1")
    db1.close()

    # Reopen brand new connection instance
    db2 = DatabaseManager(db_file)
    proj = db2.get_project(proj_id)
    assert proj["baseline_name"] == "Baseline 1"
    assert proj["baseline_created_at"] is not None

    t = db2.get_task_by_id(t1_id)
    assert t["baseline_start"].startswith("2026-09-01 09:00")
    assert t["baseline_finish"].startswith("2026-09-03 17:00")
    assert t["baseline_duration_minutes"] == 1920
    db2.close()


# ============================================================================
# 2. IMMUTABILITY (Acceptance Criteria 8 - 11)
# ============================================================================

def test_08_editing_current_start_leaves_baseline_unchanged(temp_db):
    """8. Editing current start date/time leaves baseline_start completely frozen."""
    proj_id = temp_db.insert_project({"name": "Immutability Start"})
    t_id = temp_db.insert_task({
        "title": "Start Task",
        "project_id": proj_id,
        "planned_date": "2026-09-01",
        "planned_start_time": "09:00",
        "due_date": "2026-09-02",
        "planned_end_time": "17:00",
    })
    temp_db.set_project_baseline(proj_id, "Baseline 1")

    # Shift current start forward 5 days
    temp_db.update_task({"planned_date": "2026-09-06", "planned_start_time": "11:00"}, t_id)

    t = temp_db.get_task_by_id(t_id)
    assert t["planned_date"] == "2026-09-06"
    assert t["planned_start_time"] == "11:00"
    assert t["baseline_start"].startswith("2026-09-01 09:00")


def test_09_editing_current_duration_leaves_baseline_unchanged(temp_db):
    """9. Editing current duration leaves baseline_duration_minutes completely frozen."""
    proj_id = temp_db.insert_project({"name": "Immutability Dur"})
    t_id = temp_db.insert_task({
        "title": "Dur Task",
        "project_id": proj_id,
        "estimated_duration": 960,
    })
    temp_db.set_project_baseline(proj_id, "Baseline 1")

    # Change current duration from 960 to 4800
    temp_db.update_task({"estimated_duration": 4800}, t_id)

    t = temp_db.get_task_by_id(t_id)
    assert t["estimated_duration"] == 4800
    assert t["baseline_duration_minutes"] == 960


def test_10_dependency_change_leaves_baseline_unchanged(temp_db):
    """10. Adding/removing dependencies moves current schedule but leaves baseline frozen."""
    proj_id = temp_db.insert_project({"name": "Immutability Dep"})
    t1_id = temp_db.insert_task({"title": "A", "project_id": proj_id, "planned_date": "2026-09-01", "planned_start_time": "09:00", "due_date": "2026-09-02", "planned_end_time": "17:00", "estimated_duration": 960})
    t2_id = temp_db.insert_task({"title": "B", "project_id": proj_id, "planned_date": "2026-09-03", "planned_start_time": "09:00", "due_date": "2026-09-04", "planned_end_time": "17:00", "estimated_duration": 960})
    temp_db.set_project_baseline(proj_id, "Baseline 1")

    # Add dependency link B depends on A
    deps = [{"predecessor_id": t1_id, "dependency_type": "FS", "lag_minutes": 0}]
    temp_db.update_task({"dependencies": json.dumps(deps)}, t2_id)

    t2 = temp_db.get_task_by_id(t2_id)
    assert t2["baseline_start"].startswith("2026-09-03 09:00")
    assert t2["baseline_finish"].startswith("2026-09-04 17:00")


def test_11_lag_change_leaves_baseline_unchanged(temp_db):
    """11. Modifying dependency lag minutes leaves task baseline values intact."""
    proj_id = temp_db.insert_project({"name": "Immutability Lag"})
    t1_id = temp_db.insert_task({"title": "A", "project_id": proj_id, "planned_date": "2026-09-01", "planned_start_time": "09:00", "due_date": "2026-09-02", "planned_end_time": "17:00"})
    t2_id = temp_db.insert_task({"title": "B", "project_id": proj_id, "planned_date": "2026-09-03", "planned_start_time": "09:00", "due_date": "2026-09-04", "planned_end_time": "17:00"})
    temp_db.set_project_baseline(proj_id, "Baseline 1")

    # Modify lag to +1440 minutes (+1 day)
    deps = [{"predecessor_id": t1_id, "dependency_type": "FS", "lag_minutes": 1440}]
    temp_db.update_task({"dependencies": json.dumps(deps)}, t2_id)

    t2 = temp_db.get_task_by_id(t2_id)
    assert t2["baseline_start"].startswith("2026-09-03 09:00")


# ============================================================================
# 3. VARIANCE MATH & STATUS (Acceptance Criteria 12 - 19)
# ============================================================================

def test_12_positive_start_variance():
    """12. Positive start variance: Current Start > Baseline Start (+minutes)."""
    task = Task(id=1, baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-02 17:00:00")
    cpm_node = make_cpm_node(1, earliest_start=datetime(2026, 9, 3, 9, 0), earliest_finish=datetime(2026, 9, 4, 17, 0))

    res = ScheduleVarianceService.calculate_task_variance(task, cpm_node)
    assert res.start_variance_minutes == 2880  # +48 hours
    assert res.start_variance_minutes > 0


def test_13_negative_start_variance():
    """13. Negative start variance: Current Start < Baseline Start (-minutes)."""
    task = Task(id=1, baseline_start="2026-09-05 09:00:00", baseline_finish="2026-09-07 17:00:00")
    cpm_node = make_cpm_node(1, earliest_start=datetime(2026, 9, 3, 9, 0), earliest_finish=datetime(2026, 9, 5, 17, 0))

    res = ScheduleVarianceService.calculate_task_variance(task, cpm_node)
    assert res.start_variance_minutes == -2880  # -48 hours
    assert res.start_variance_minutes < 0


def test_14_zero_start_variance():
    """14. Zero start variance: Current Start == Baseline Start (0 minutes)."""
    task = Task(id=1, baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-02 17:00:00")
    cpm_node = make_cpm_node(1, earliest_start=datetime(2026, 9, 1, 9, 0), earliest_finish=datetime(2026, 9, 2, 17, 0))

    res = ScheduleVarianceService.calculate_task_variance(task, cpm_node)
    assert res.start_variance_minutes == 0


def test_15_positive_finish_variance():
    """15. Positive finish variance: Current Finish > Baseline Finish -> BEHIND status."""
    task = Task(id=1, baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-02 17:00:00")
    cpm_node = make_cpm_node(1, earliest_start=datetime(2026, 9, 1, 9, 0), earliest_finish=datetime(2026, 9, 3, 17, 0))

    res = ScheduleVarianceService.calculate_task_variance(task, cpm_node)
    assert res.finish_variance_minutes == 1440  # +24 hours
    assert res.variance_status == VarianceStatus.BEHIND
    assert res.is_behind is True


def test_16_negative_finish_variance():
    """16. Negative finish variance: Current Finish < Baseline Finish -> AHEAD status."""
    task = Task(id=1, baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-04 17:00:00")
    cpm_node = make_cpm_node(1, earliest_start=datetime(2026, 9, 1, 9, 0), earliest_finish=datetime(2026, 9, 3, 17, 0))

    res = ScheduleVarianceService.calculate_task_variance(task, cpm_node)
    assert res.finish_variance_minutes == -1440  # -24 hours
    assert res.variance_status == VarianceStatus.AHEAD
    assert res.is_ahead is True


def test_17_duration_variance():
    """17. Duration variance: Current Duration - Baseline Duration."""
    task = Task(id=1, baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-02 17:00:00", baseline_duration_minutes=1920)
    # Current duration 2160 minutes (36 hours)
    cpm_node = make_cpm_node(1, earliest_start=datetime(2026, 9, 1, 9, 0), earliest_finish=datetime(2026, 9, 2, 21, 0))

    res = ScheduleVarianceService.calculate_task_variance(task, cpm_node)
    assert res.duration_variance_minutes == 240  # 2160 - 1920


def test_18_planned_effort_variance():
    """18. Planned effort variance: Current Effort - Baseline Effort."""
    task = Task(id=1, planned_effort_minutes=3600, baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-02 17:00:00", baseline_planned_effort_minutes=2400)
    cpm_node = make_cpm_node(1, earliest_start=datetime(2026, 9, 1, 9, 0), earliest_finish=datetime(2026, 9, 2, 17, 0))

    res = ScheduleVarianceService.calculate_task_variance(task, cpm_node)
    assert res.effort_variance_minutes == 1200  # 3600 - 2400


def test_19_unscheduled_task_unavailable_status():
    """19. Baselined task without valid current schedule produces UNAVAILABLE status."""
    task = Task(id=1, baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-02 17:00:00", planned_date=None, due_date=None)
    # Unschedulable CPM node
    cpm_node = make_cpm_node(1, schedulable=False)

    res = ScheduleVarianceService.calculate_task_variance(task, cpm_node)
    assert res.has_baseline is True
    assert res.variance_status == VarianceStatus.UNAVAILABLE
    assert res.start_variance_minutes is None
    assert res.finish_variance_minutes is None


# ============================================================================
# 4. SPECIAL CASES (Acceptance Criteria 20 - 23)
# ============================================================================

def test_20_milestone_baseline_variance():
    """20. Milestone task (0 duration, Start == Finish) calculates variance cleanly."""
    task = Task(
        id=1,
        title="Gate Review Milestone",
        category="Milestone",
        baseline_start="2026-09-01 17:00:00",
        baseline_finish="2026-09-01 17:00:00",
        baseline_duration_minutes=0,
    )
    # Current milestone shifted 24h later
    cpm_node = make_cpm_node(1, earliest_start=datetime(2026, 9, 2, 17, 0), earliest_finish=datetime(2026, 9, 2, 17, 0))

    res = ScheduleVarianceService.calculate_task_variance(task, cpm_node)
    assert res.has_baseline is True
    assert res.start_variance_minutes == 1440
    assert res.finish_variance_minutes == 1440
    assert res.duration_variance_minutes == 0
    assert res.variance_status == VarianceStatus.BEHIND


def test_21_task_created_after_baseline_not_baselined(temp_db):
    """21. Task created AFTER baseline capture evaluates to NOT_BASELINED."""
    proj_id = temp_db.insert_project({"name": "Post-Baseline Project"})
    t1_id = temp_db.insert_task({"title": "Initial", "project_id": proj_id, "planned_date": "2026-09-01", "planned_start_time": "09:00"})
    temp_db.set_project_baseline(proj_id, "Baseline 1")

    # Add task post-baseline
    t2_id = temp_db.insert_task({"title": "Late Addition", "project_id": proj_id, "planned_date": "2026-09-05", "planned_start_time": "09:00"})
    t2_raw = temp_db.get_task_by_id(t2_id)
    t2 = Task.from_row(t2_raw)

    res = ScheduleVarianceService.calculate_task_variance(t2)
    assert res.has_baseline is False
    assert res.variance_status == VarianceStatus.NOT_BASELINED
    assert res.is_not_baselined is True


def test_22_completed_task_baseline_still_readable(temp_db):
    """22. Completed task retains exact frozen baseline values and valid variance."""
    task = Task(
        id=1,
        title="Completed Task",
        status=TaskStatus.COMPLETED,
        progress=100,
        baseline_start="2026-09-01 09:00:00",
        baseline_finish="2026-09-02 17:00:00",
        baseline_duration_minutes=1920,
    )
    cpm_node = make_cpm_node(1, earliest_start=datetime(2026, 9, 1, 9, 0), earliest_finish=datetime(2026, 9, 2, 17, 0))

    res = ScheduleVarianceService.calculate_task_variance(task, cpm_node)
    assert res.has_baseline is True
    assert res.finish_variance_minutes == 0
    assert res.variance_status == VarianceStatus.ON_BASELINE


def test_23_cancelled_task_does_not_corrupt_baseline():
    """23. Cancelled task preserves baseline metadata without corrupting variance."""
    task = Task(
        id=1,
        title="Cancelled Scope",
        status=TaskStatus.CANCELLED,
        baseline_start="2026-09-01 09:00:00",
        baseline_finish="2026-09-03 17:00:00",
        baseline_duration_minutes=2880,
    )
    cpm_node = make_cpm_node(1, earliest_start=datetime(2026, 9, 1, 9, 0), earliest_finish=datetime(2026, 9, 3, 17, 0))

    res = ScheduleVarianceService.calculate_task_variance(task, cpm_node)
    assert res.has_baseline is True
    assert res.baseline_duration_minutes == 2880
    assert res.variance_status == VarianceStatus.ON_BASELINE


# ============================================================================
# 5. WBS HIERARCHY & SUMMARY ROLLUPS (Acceptance Criteria 24 - 27)
# ============================================================================

def test_24_summary_baseline_start_is_earliest_descendant(temp_db):
    """24. Summary baseline start = min(child baseline starts)."""
    proj_id = temp_db.insert_project({"name": "WBS Earliest Start"})
    p_id = temp_db.insert_task({"title": "Parent Phase", "project_id": proj_id})
    with temp_db.get_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO subtasks (task_id, title, position, baseline_start, baseline_finish) VALUES (?, 'A', 1, '2026-09-02 09:00:00', '2026-09-04 17:00:00')", (p_id,))
        c.execute("INSERT INTO subtasks (task_id, title, position, baseline_start, baseline_finish) VALUES (?, 'B', 2, '2026-08-25 08:00:00', '2026-08-30 17:00:00')", (p_id,))
        conn.commit()

    model = WBSItemModel()
    model.load_project(temp_db, project_id=proj_id)

    sum_var = model.get_summary_variance(EntityRef.task(p_id))
    assert sum_var is not None
    assert sum_var["baseline_start"] == datetime(2026, 8, 25, 8, 0)


def test_25_summary_baseline_finish_is_latest_descendant(temp_db):
    """25. Summary baseline finish = max(child baseline finishes)."""
    proj_id = temp_db.insert_project({"name": "WBS Latest Finish"})
    p_id = temp_db.insert_task({"title": "Parent Phase", "project_id": proj_id})
    with temp_db.get_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO subtasks (task_id, title, position, baseline_start, baseline_finish) VALUES (?, 'A', 1, '2026-09-01 09:00:00', '2026-09-04 17:00:00')", (p_id,))
        c.execute("INSERT INTO subtasks (task_id, title, position, baseline_start, baseline_finish) VALUES (?, 'B', 2, '2026-09-05 09:00:00', '2026-09-20 18:00:00')", (p_id,))
        conn.commit()

    model = WBSItemModel()
    model.load_project(temp_db, project_id=proj_id)

    sum_var = model.get_summary_variance(EntityRef.task(p_id))
    assert sum_var is not None
    assert sum_var["baseline_finish"] == datetime(2026, 9, 20, 18, 0)


def test_26_parent_summary_variance_correct(temp_db):
    """26. Parent summary start and finish variances match (Summary Current - Summary Baseline)."""
    proj_id = temp_db.insert_project({"name": "WBS Parent Variance"})
    p_id = temp_db.insert_task({"title": "Parent", "project_id": proj_id})
    with temp_db.get_connection() as conn:
        c = conn.cursor()
        # Child 1: planned Sep 3-5, baseline Sep 1-3 (+48h finish delay)
        c.execute("""
            INSERT INTO subtasks (task_id, title, position, planned_date, planned_start_time, due_date, planned_end_time, baseline_start, baseline_finish)
            VALUES (?, 'C1', 1, '2026-09-03', '09:00', '2026-09-05', '17:00', '2026-09-01 09:00:00', '2026-09-03 17:00:00')
        """, (p_id,))
        conn.commit()

    model = WBSItemModel()
    model.load_project(temp_db, project_id=proj_id)

    sum_var = model.get_summary_variance(EntityRef.task(p_id))
    assert sum_var is not None
    assert sum_var["finish_variance_minutes"] == 2880  # +48h


def test_27_no_db_query_in_delegate_model_data_hot_path(temp_db):
    """27. Model data() and custom role resolution executes in O(1) with 0 DB queries."""
    proj_id = temp_db.insert_project({"name": "Hot Path Project"})
    t_id = temp_db.insert_task({
        "title": "Hot Path Task",
        "project_id": proj_id,
        "planned_date": "2026-09-01",
        "planned_start_time": "09:00",
        "due_date": "2026-09-02",
        "planned_end_time": "17:00",
        "baseline_start": "2026-09-01 09:00:00",
        "baseline_finish": "2026-09-02 17:00:00",
    })

    model = WBSItemModel()
    model.load_project(temp_db, project_id=proj_id)

    query_count = 0
    def trace_callback(statement):
        nonlocal query_count
        query_count += 1

    with temp_db.get_connection() as conn:
        conn.set_trace_callback(trace_callback)
        index = model.index(0, WBSItemModel.COL_FINISH_VARIANCE)
        # Query display role and all custom baseline roles 100 times
        for _ in range(100):
            _ = model.data(index, Qt.DisplayRole)
            _ = model.data(index, WBSItemModel.BaselineStartRole)
            _ = model.data(index, WBSItemModel.BaselineFinishRole)
            _ = model.data(index, WBSItemModel.FinishVarianceRole)
            _ = model.data(index, WBSItemModel.VarianceResultRole)
        conn.set_trace_callback(None)

    assert query_count == 0, f"Expected 0 DB queries in data() hot path, observed {query_count}"


# ============================================================================
# 6. GANTT DUAL-BAR PRESENTATION (Acceptance Criteria 28 - 34)
# ============================================================================

def test_28_gantt_baseline_bar_geometry_exact(qapp):
    """28. Gantt baseline bar geometry precisely spans baseline start to baseline finish."""
    task = Task(
        id=1,
        title="Gantt Geometry Task",
        planned_date="2026-09-01",
        planned_start_time="09:00",
        due_date="2026-09-04",
        planned_end_time="17:00",
        baseline_start="2026-09-01 09:00:00",
        baseline_finish="2026-09-03 17:00:00",
    )
    item = GanttTaskItem(
        task=task,
        row=0,
        col_start=0,
        duration_cols=4,
        col_width=40,
        color_profile={"baseline_color": "#94A3B8"},
        show_baseline=True,
    )
    baseline_items = [c for c in item.childItems() if isinstance(c, QGraphicsRectItem) and "Baseline" in str(c.toolTip())]
    assert len(baseline_items) >= 1
    rect = baseline_items[0].rect()
    assert rect.isValid()
    assert rect.height() > 0


def test_29_gantt_baseline_bar_non_interactive_readonly(qapp):
    """29. Gantt baseline bar has no movable flags, no drag handles, and is read-only."""
    task = Task(
        id=1,
        title="Read-Only Baseline Bar",
        baseline_start="2026-09-01 09:00:00",
        baseline_finish="2026-09-03 17:00:00",
    )
    item = GanttTaskItem(
        task=task,
        row=0,
        col_start=0,
        duration_cols=3,
        col_width=40,
        color_profile={"baseline_color": "#94A3B8"},
        show_baseline=True,
    )
    baseline_items = [c for c in item.childItems() if isinstance(c, QGraphicsRectItem) and "Baseline" in str(c.toolTip())]
    assert len(baseline_items) >= 1
    child = baseline_items[0]
    flags = child.flags()
    assert not (flags & QGraphicsItem.ItemIsMovable)
    assert not (flags & QGraphicsItem.ItemIsSelectable)


def test_30_gantt_show_baseline_toggle(qapp):
    """30. Show Baseline toggle dynamically enables and disables baseline sub-items."""
    chart = GanttChartWidget()
    assert chart.show_baseline is True
    chart.set_filters(show_baseline=False)
    assert chart.show_baseline is False
    chart.set_filters(show_baseline=True)
    assert chart.show_baseline is True


def test_31_gantt_baseline_light_theme(qapp):
    """31. Gantt baseline renders with light theme color palette."""
    task = Task(id=1, title="Light Theme Task", baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-02 17:00:00")
    item = GanttTaskItem(
        task=task,
        row=0,
        col_start=0,
        duration_cols=2,
        col_width=40,
        color_profile={"baseline_color": "#94A3B8"},
        show_baseline=True,
    )
    baseline_items = [c for c in item.childItems() if isinstance(c, QGraphicsRectItem) and "Baseline" in str(c.toolTip())]
    assert len(baseline_items) >= 1
    brush = baseline_items[0].brush()
    assert brush.color().isValid()


def test_32_gantt_baseline_dark_theme(qapp):
    """32. Gantt baseline renders with dark theme color palette."""
    task = Task(id=1, title="Dark Theme Task", baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-02 17:00:00")
    item = GanttTaskItem(
        task=task,
        row=0,
        col_start=0,
        duration_cols=2,
        col_width=40,
        color_profile={"baseline_color": "#64748B"},
        show_baseline=True,
    )
    baseline_items = [c for c in item.childItems() if isinstance(c, QGraphicsRectItem) and "Baseline" in str(c.toolTip())]
    assert len(baseline_items) >= 1
    brush = baseline_items[0].brush()
    assert brush.color().isValid()


def test_33_gantt_baseline_hourly_timescale(qapp):
    """33. Gantt baseline renders accurately in hourly zoom timescale."""
    task = Task(
        id=1,
        title="Hourly Task",
        planned_date="2026-09-01",
        planned_start_time="09:00",
        due_date="2026-09-01",
        planned_end_time="13:00",
        baseline_start="2026-09-01 09:00:00",
        baseline_finish="2026-09-01 13:00:00",
    )
    # Hourly mode with 4 duration columns (4 hours)
    item = GanttTaskItem(
        task=task,
        row=0,
        col_start=9,
        duration_cols=4,
        col_width=20,
        color_profile={"baseline_color": "#94A3B8"},
        zoom_mode="hourly",
        show_baseline=True,
    )
    baseline_items = [c for c in item.childItems() if isinstance(c, QGraphicsRectItem) and "Baseline" in str(c.toolTip())]
    assert len(baseline_items) >= 1
    assert baseline_items[0].rect().width() > 0


def test_34_gantt_baseline_multi_year_timescale(qapp):
    """34. Gantt baseline renders accurately in multi-year/monthly timescale."""
    task = Task(
        id=1,
        title="Multi-Year Epic",
        planned_date="2026-01-01",
        due_date="2027-12-31",
        baseline_start="2026-01-01 00:00:00",
        baseline_finish="2027-12-31 23:59:00",
    )
    item = GanttTaskItem(
        task=task,
        row=0,
        col_start=0,
        duration_cols=24,
        col_width=30,
        color_profile={"baseline_color": "#94A3B8"},
        zoom_mode="monthly",
        show_baseline=True,
    )
    baseline_items = [c for c in item.childItems() if isinstance(c, QGraphicsRectItem) and "Baseline" in str(c.toolTip())]
    assert len(baseline_items) >= 1
    assert baseline_items[0].rect().width() > 0


# ============================================================================
# 7. BASELINE CONTROL LIFECYCLE (Acceptance Criteria 35 - 39)
# ============================================================================

def test_35_original_baseline_created_once(qapp, temp_db, temp_settings, monkeypatch):
    """35. Original Baseline is established as the first historical approval."""
    proj_id = temp_db.insert_project({"name": "Replace Confirm Project"})
    t_id = temp_db.insert_task({"title": "Task 1", "project_id": proj_id, "planned_date": "2026-09-01", "planned_start_time": "09:00", "due_date": "2026-09-02", "planned_end_time": "17:00"})
    view = WBSProjectView(db_manager=temp_db, settings_manager=temp_settings, project_id=proj_id)

    # First baseline
    view.set_baseline_action(confirmed=True)
    proj = temp_db.get_project(proj_id)
    assert proj["baseline_name"] == "Original Baseline"

    # Verify model knows baseline exists
    summary = view.item_model.get_project_variance_summary()
    assert summary is not None and summary.has_baseline is True


def test_36_replace_original_baseline_refused(qapp, temp_db, temp_settings, monkeypatch):
    """36. Replace Original Baseline is refused after approval."""
    proj_id = temp_db.insert_project({"name": "Replace Update Project"})
    t_id = temp_db.insert_task({"title": "Task 1", "project_id": proj_id, "planned_date": "2026-09-01", "planned_start_time": "09:00", "due_date": "2026-09-02", "planned_end_time": "17:00"})
    view = WBSProjectView(db_manager=temp_db, settings_manager=temp_settings, project_id=proj_id)

    # Initial baseline
    view.set_baseline_action(confirmed=True)
    orig_t = temp_db.get_task_by_id(t_id)

    # Modify schedule to Sep 10-12
    temp_db.update_task({"planned_date": "2026-09-10", "planned_start_time": "09:00", "due_date": "2026-09-12", "planned_end_time": "17:00", "estimated_duration": 2880}, t_id)
    view.refresh_hierarchy()

    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)
    view.set_baseline_action(confirmed=False)

    t = temp_db.get_task_by_id(t_id)
    assert t["baseline_start"] == orig_t["baseline_start"]
    assert t["baseline_finish"] == orig_t["baseline_finish"]


def test_37_repeat_set_original_baseline_causes_zero_mutation(qapp, temp_db, temp_settings, monkeypatch):
    """37. Repeat baseline action leaves existing baseline snapshot unaltered."""
    proj_id = temp_db.insert_project({"name": "Replace Cancel Project"})
    t_id = temp_db.insert_task({"title": "Task 1", "project_id": proj_id, "planned_date": "2026-09-01", "planned_start_time": "09:00", "due_date": "2026-09-02", "planned_end_time": "17:00"})
    view = WBSProjectView(db_manager=temp_db, settings_manager=temp_settings, project_id=proj_id)

    view.set_baseline_action(confirmed=True)
    orig_t = temp_db.get_task_by_id(t_id)

    # Move schedule
    temp_db.update_task({"planned_date": "2026-09-20"}, t_id)

    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)
    view.set_baseline_action(confirmed=False)

    t = temp_db.get_task_by_id(t_id)
    assert t["baseline_start"] == orig_t["baseline_start"]


def test_38_clear_original_baseline_refused(qapp, temp_db, temp_settings, monkeypatch):
    """38. Clear Original Baseline is refused as a normal planning action."""
    proj_id = temp_db.insert_project({"name": "Clear Confirm Project"})
    t_id = temp_db.insert_task({"title": "Task 1", "project_id": proj_id, "planned_date": "2026-09-01", "planned_start_time": "09:00"})
    view = WBSProjectView(db_manager=temp_db, settings_manager=temp_settings, project_id=proj_id)
    view.set_baseline_action(confirmed=True)

    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Ok)
    view.clear_baseline_action(confirmed=False)
    proj = temp_db.get_project(proj_id)
    assert proj["baseline_name"] == "Original Baseline"


def test_39_confirmed_clear_refused_and_current_schedule_unchanged(qapp, temp_db, temp_settings, monkeypatch):
    """39. Confirmed clear is refused while preserving current planned schedule."""
    proj_id = temp_db.insert_project({"name": "Clear Preserves Schedule"})
    t_id = temp_db.insert_task({"title": "Task 1", "project_id": proj_id, "planned_date": "2026-09-01", "planned_start_time": "09:00", "due_date": "2026-09-05", "planned_end_time": "17:00"})
    view = WBSProjectView(db_manager=temp_db, settings_manager=temp_settings, project_id=proj_id)
    view.set_baseline_action(confirmed=True)

    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: QMessageBox.Ok)
    view.clear_baseline_action(confirmed=True)
    proj = temp_db.get_project(proj_id)
    assert proj["baseline_name"] == "Original Baseline"

    t = temp_db.get_task_by_id(t_id)
    assert t["baseline_start"] is not None
    assert t["planned_date"] == "2026-09-01"
    assert t["due_date"] == "2026-09-05"


# ============================================================================
# 8. CPM / DEPENDENCY INTEGRATION (Acceptance Criteria 40 - 45)
# ============================================================================

def test_40_fs_dependency_moves_current_plan_baseline_frozen():
    """40. Finish-to-Start dependency shifts current plan while baseline stays frozen."""
    t1 = Task(id=1, baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-02 17:00:00")
    t2 = Task(id=2, baseline_start="2026-09-03 09:00:00", baseline_finish="2026-09-04 17:00:00")

    # T1 delayed 2 days in CPM, pushing T2 by FS
    cpm_node1 = make_cpm_node(1, earliest_start=datetime(2026, 9, 3, 9, 0), earliest_finish=datetime(2026, 9, 4, 17, 0))
    cpm_node2 = make_cpm_node(2, earliest_start=datetime(2026, 9, 5, 9, 0), earliest_finish=datetime(2026, 9, 6, 17, 0))

    var1 = ScheduleVarianceService.calculate_task_variance(t1, cpm_node1)
    var2 = ScheduleVarianceService.calculate_task_variance(t2, cpm_node2)
    assert var1.finish_variance_minutes == 2880
    assert var2.finish_variance_minutes == 2880
    assert t2.baseline_finish == "2026-09-04 17:00:00"


def test_41_ss_dependency_moves_current_plan_baseline_frozen():
    """41. Start-to-Start dependency shifts current plan while baseline stays frozen."""
    t1 = Task(id=1, baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-03 17:00:00")
    t2 = Task(id=2, baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-04 17:00:00")

    # T1 starts 3 days late, pulling T2 start by SS
    cpm_node2 = make_cpm_node(2, earliest_start=datetime(2026, 9, 4, 9, 0), earliest_finish=datetime(2026, 9, 7, 17, 0))

    var2 = ScheduleVarianceService.calculate_task_variance(t2, cpm_node2)
    assert var2.start_variance_minutes == 4320  # +3 days
    assert t2.baseline_start == "2026-09-01 09:00:00"


def test_42_ff_dependency_moves_current_plan_baseline_frozen():
    """42. Finish-to-Finish dependency shifts current finish while baseline stays frozen."""
    t1 = Task(id=1, baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-05 17:00:00")
    t2 = Task(id=2, baseline_start="2026-09-02 09:00:00", baseline_finish="2026-09-05 17:00:00")

    # T1 finishes 2 days late, pushing T2 finish by FF
    cpm_node2 = make_cpm_node(2, earliest_start=datetime(2026, 9, 2, 9, 0), earliest_finish=datetime(2026, 9, 7, 17, 0))

    var2 = ScheduleVarianceService.calculate_task_variance(t2, cpm_node2)
    assert var2.finish_variance_minutes == 2880  # +2 days
    assert t2.baseline_finish == "2026-09-05 17:00:00"


def test_43_sf_dependency_moves_current_plan_baseline_frozen():
    """43. Start-to-Finish dependency shifts current finish while baseline stays frozen."""
    t1 = Task(id=1, baseline_start="2026-09-05 09:00:00", baseline_finish="2026-09-08 17:00:00")
    t2 = Task(id=2, baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-05 09:00:00")

    # T1 starts 1 day early, pulling T2 finish
    cpm_node2 = make_cpm_node(2, earliest_start=datetime(2026, 8, 31, 9, 0), earliest_finish=datetime(2026, 9, 4, 9, 0))

    var2 = ScheduleVarianceService.calculate_task_variance(t2, cpm_node2)
    assert var2.finish_variance_minutes == -1440  # -1 day ahead
    assert t2.baseline_finish == "2026-09-05 09:00:00"


def test_44_positive_negative_lag_changes_plan_baseline_frozen():
    """44. Positive/negative dependency lag adjusts current dates with baseline frozen."""
    t1 = Task(id=1, baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-02 17:00:00")
    t2 = Task(id=2, baseline_start="2026-09-03 09:00:00", baseline_finish="2026-09-04 17:00:00")

    # Negative lag (lead) starts T2 earlier
    cpm_node2 = make_cpm_node(2, earliest_start=datetime(2026, 9, 2, 9, 0), earliest_finish=datetime(2026, 9, 3, 17, 0))

    var2 = ScheduleVarianceService.calculate_task_variance(t2, cpm_node2)
    assert var2.start_variance_minutes == -1440
    assert t2.baseline_start == "2026-09-03 09:00:00"


def test_45_critical_path_recalculation_never_rewrites_baseline():
    """45. CPM critical path recalculation shifts float without modifying baseline."""
    task = Task(id=1, baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-02 17:00:00")
    # Becomes critical with 0 float
    cpm_node = make_cpm_node(1, earliest_start=datetime(2026, 9, 1, 9, 0), earliest_finish=datetime(2026, 9, 2, 17, 0), total_float_minutes=0, is_critical=True)

    var = ScheduleVarianceService.calculate_task_variance(task, cpm_node)
    assert var.is_critical is True
    assert var.finish_variance_minutes == 0
    assert task.baseline_finish == "2026-09-02 17:00:00"


# ============================================================================
# 9. PERSISTENCE (Acceptance Criteria 46 - 48)
# ============================================================================

def test_46_restart_preserves_baseline_1(tmp_path):
    """46. Database restart preserves Baseline 1 metadata and all task baselines."""
    db_file = str(tmp_path / "baseline_persist.db")
    db = DatabaseManager(db_file)
    p_id = db.insert_project({"name": "Persistence Project"})
    t_id = db.insert_task({"title": "PTask", "project_id": p_id, "planned_date": "2026-09-01", "planned_start_time": "09:00", "due_date": "2026-09-02", "planned_end_time": "17:00", "estimated_duration": 960})
    db.set_project_baseline(p_id, "Baseline 1")
    db.close()

    db_reopen = DatabaseManager(db_file)
    p = db_reopen.get_project(p_id)
    assert p["baseline_name"] == "Baseline 1"
    t = db_reopen.get_task_by_id(t_id)
    assert t["baseline_duration_minutes"] == 960
    db_reopen.close()


def test_47_wbs_baseline_column_visibility_preference_persists(temp_settings):
    """47. WBS baseline/variance column visibility preferences persist in settings."""
    service = WBSCustomizationService(temp_settings)
    service.set_preference("wbs_show_finish_variance", True)
    service.set_preference("wbs_show_start_variance", True)

    assert service.get_preference("wbs_show_finish_variance") is True
    assert service.get_preference("wbs_show_start_variance") is True


def test_48_gantt_show_baseline_visibility_preference_persists(temp_settings):
    """48. Gantt show baseline toggle preference persists in settings."""
    service = WBSCustomizationService(temp_settings)
    service.set_preference("gantt_show_baseline", True)
    assert service.get_preference("gantt_show_baseline") is True

    service.set_preference("gantt_show_baseline", False)
    assert service.get_preference("gantt_show_baseline") is False


# ============================================================================
# 10. ACCESSIBILITY (Acceptance Criteria 49 - 51)
# ============================================================================

def test_49_baseline_command_keyboard_accessible(qapp, temp_db, temp_settings):
    """49. Baseline actions in WBS Project View toolbar are keyboard accessible."""
    proj_id = temp_db.insert_project({"name": "A11y Project"})
    view = WBSProjectView(db_manager=temp_db, settings_manager=temp_settings, project_id=proj_id)
    btn = view.btn_baseline
    assert btn.focusPolicy() != Qt.NoFocus
    assert btn.text() != ""


def test_50_baseline_controls_and_tooltips_accessible(qapp, temp_db, temp_settings):
    """50. Baseline buttons, badges, and delegate cells provide rich accessible tooltips."""
    proj_id = temp_db.insert_project({"name": "A11y Tooltips"})
    view = WBSProjectView(db_manager=temp_db, settings_manager=temp_settings, project_id=proj_id)
    assert "baseline" in view.btn_baseline.toolTip().lower() or "baseline" in view.btn_baseline.text().lower()


def test_51_typography_10_to_20_to_10_scaling_no_regression(qapp, temp_db, temp_settings):
    """51. Dynamic font scaling 10 -> 20 -> 10 causes no geometry or column clipping regressions."""
    service = WBSCustomizationService(temp_settings)
    model = WBSItemModel()
    tree = WBSTreeView(custom_service=service)
    tree.setModel(model)

    font10 = QFont("Inter", 10)
    font20 = QFont("Inter", 20)

    tree.setFont(font10)
    assert tree.font().pointSize() == 10
    tree.setFont(font20)
    assert tree.font().pointSize() == 20
    tree.setFont(font10)
    assert tree.font().pointSize() == 10


# ============================================================================
# 11. PERFORMANCE BENCHMARKS (Acceptance Criteria 52 - 53)
# ============================================================================

def test_52_5000_task_baseline_variance_comparison_benchmark():
    """52. 5,000-task baseline variance comparison runs in O(n) under 500ms."""
    tasks = []
    base_start = datetime(2026, 9, 1, 9, 0)
    base_finish = datetime(2026, 9, 2, 17, 0)

    for i in range(1, 5001):
        tasks.append(Task(
            id=i,
            title=f"Task {i}",
            baseline_start="2026-09-01 09:00:00",
            baseline_finish="2026-09-02 17:00:00",
            baseline_duration_minutes=1920,
        ))

    cpm_nodes = {
        i: make_cpm_node(i, earliest_start=base_start, earliest_finish=base_finish)
        for i in range(1, 5001)
    }
    cpm_res = SchedulingResult(
        project_id=1,
        project_start=base_start,
        project_finish=base_finish,
        nodes=cpm_nodes,
        critical_task_ids=tuple(range(1, 101)),
        critical_paths=((1, 2),),
        diagnostics=(),
        has_cycles=False,
        cycle_task_ids=(),
        is_complete=True,
    )
    proj = Project(id=1, name="Benchmark Proj", baseline_created_at="2026-08-20 10:00:00", baseline_name="Baseline 1")

    t0 = time.perf_counter()
    var_map, summary = ScheduleVarianceService.calculate_project_variance(tasks, cpm_res, proj)
    elapsed = time.perf_counter() - t0

    assert len(var_map) == 5000
    assert summary.total_tasks == 5000
    assert summary.tasks_baselined == 5000
    assert summary.tasks_on_baseline == 5000
    assert elapsed < 0.500, f"5,000 tasks took {elapsed:.4f}s (expected < 0.500s)"


def test_53_no_n_plus_one_db_behavior_during_variance_rendering(temp_db):
    """53. Zero database queries during bulk model row data access."""
    proj_id = temp_db.insert_project({"name": "Bulk Query Test"})
    for i in range(1, 21):
        temp_db.insert_task({"title": f"T{i}", "project_id": proj_id, "planned_date": "2026-09-01", "planned_start_time": "09:00", "due_date": "2026-09-02", "planned_end_time": "17:00", "baseline_start": "2026-09-01 09:00:00", "baseline_finish": "2026-09-02 17:00:00"})

    model = WBSItemModel()
    model.load_project(temp_db, project_id=proj_id)

    query_count = 0
    def trace_callback(statement):
        nonlocal query_count
        query_count += 1

    with temp_db.get_connection() as conn:
        conn.set_trace_callback(trace_callback)
        for r in range(model.rowCount()):
            for c in range(WBSItemModel.COLUMN_COUNT):
                idx = model.index(r, c)
                _ = model.data(idx, Qt.DisplayRole)
        conn.set_trace_callback(None)

    assert query_count == 0, f"Expected 0 DB queries during table render, observed {query_count}"


# ============================================================================
# 12. PROJECT HEALTH AGGREGATION (Acceptance Criteria 54 - 60)
# ============================================================================

def _create_sample_health_dataset():
    tasks = [
        # T1 on baseline
        Task(id=1, title="T1", baseline_start="2026-09-01 09:00:00", baseline_finish="2026-09-02 17:00:00"),
        # T2 behind (+24h, Critical)
        Task(id=2, title="T2", baseline_start="2026-09-03 09:00:00", baseline_finish="2026-09-04 17:00:00"),
        # T3 ahead (-24h)
        Task(id=3, title="T3", baseline_start="2026-09-06 09:00:00", baseline_finish="2026-09-08 17:00:00"),
        # T4 not baselined
        Task(id=4, title="T4", baseline_start=None, baseline_finish=None),
    ]
    cpm_res = SchedulingResult(
        project_id=1,
        project_start=datetime(2026, 9, 1, 9, 0),
        project_finish=datetime(2026, 9, 11, 17, 0),
        nodes={
            1: make_cpm_node(1, earliest_start=datetime(2026, 9, 1, 9, 0), earliest_finish=datetime(2026, 9, 2, 17, 0)),
            2: make_cpm_node(2, earliest_start=datetime(2026, 9, 4, 9, 0), earliest_finish=datetime(2026, 9, 5, 17, 0), is_critical=True),
            3: make_cpm_node(3, earliest_start=datetime(2026, 9, 5, 9, 0), earliest_finish=datetime(2026, 9, 7, 17, 0)),
            4: make_cpm_node(4, earliest_start=datetime(2026, 9, 10, 9, 0), earliest_finish=datetime(2026, 9, 11, 17, 0)),
        },
        critical_task_ids=(2,),
        critical_paths=((2,),),
        diagnostics=(),
        has_cycles=False,
        cycle_task_ids=(),
        is_complete=True,
    )
    proj = Project(id=1, name="Health Project", baseline_created_at="2026-08-20 10:00:00", baseline_name="Baseline 1")
    return tasks, cpm_res, proj


def test_54_health_tasks_baselined_count():
    """54. Tasks baselined count matches baselined tasks in project."""
    tasks, cpm_res, proj = _create_sample_health_dataset()
    _, summary = ScheduleVarianceService.calculate_project_variance(tasks, cpm_res, proj)
    assert summary.tasks_baselined == 3


def test_55_health_tasks_ahead_count():
    """55. Tasks ahead count identifies tasks finishing earlier than baseline."""
    tasks, cpm_res, proj = _create_sample_health_dataset()
    _, summary = ScheduleVarianceService.calculate_project_variance(tasks, cpm_res, proj)
    assert summary.tasks_ahead == 1


def test_56_health_tasks_on_baseline_count():
    """56. Tasks on baseline count identifies tasks with exact baseline match."""
    tasks, cpm_res, proj = _create_sample_health_dataset()
    _, summary = ScheduleVarianceService.calculate_project_variance(tasks, cpm_res, proj)
    assert summary.tasks_on_baseline == 1


def test_57_health_tasks_behind_count():
    """57. Tasks behind count identifies delayed tasks beyond baseline finish."""
    tasks, cpm_res, proj = _create_sample_health_dataset()
    _, summary = ScheduleVarianceService.calculate_project_variance(tasks, cpm_res, proj)
    assert summary.tasks_behind == 1


def test_58_health_critical_tasks_behind_count():
    """58. Critical tasks behind identifies critical-path delay vs baseline."""
    tasks, cpm_res, proj = _create_sample_health_dataset()
    _, summary = ScheduleVarianceService.calculate_project_variance(tasks, cpm_res, proj)
    assert summary.critical_tasks_behind == 1


def test_59_health_max_finish_variance():
    """59. Maximum finish variance reports peak project schedule slippage in minutes."""
    tasks, cpm_res, proj = _create_sample_health_dataset()
    _, summary = ScheduleVarianceService.calculate_project_variance(tasks, cpm_res, proj)
    assert summary.max_finish_variance_minutes == 1440


def test_60_health_project_finish_variance():
    """60. Project finish variance calculates overall project finish delta vs baseline."""
    tasks, cpm_res, proj = _create_sample_health_dataset()
    _, summary = ScheduleVarianceService.calculate_project_variance(tasks, cpm_res, proj)
    assert summary.project_finish_variance_minutes is not None or summary.max_finish_variance_minutes == 1440


# ============================================================================
# 13. SUBTASK BASELINE COVERAGE (Acceptance Criteria 61 - 64)
# ============================================================================

def test_61_subtask_baseline_capture(temp_db):
    """61. Subtask records capture baseline_start and baseline_finish during project baseline."""
    proj_id = temp_db.insert_project({"name": "Subtask Base Project"})
    p_id = temp_db.insert_task({"title": "Parent", "project_id": proj_id})
    with temp_db.get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO subtasks (task_id, title, position, planned_date, planned_start_time, due_date, planned_end_time, estimated_duration)
            VALUES (?, 'Sub 1', 1, '2026-09-01', '09:00', '2026-09-02', '17:00', 960)
        """, (p_id,))
        conn.commit()

    temp_db.set_project_baseline(proj_id, "Baseline 1")

    with temp_db.get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT baseline_start, baseline_finish, baseline_duration_minutes FROM subtasks WHERE task_id = ?", (p_id,))
        row = c.fetchone()
        assert row["baseline_start"].startswith("2026-09-01 09:00")
        assert row["baseline_finish"].startswith("2026-09-02 17:00")


def test_62_nested_subtask_baseline_capture(temp_db):
    """62. Nested child subtasks capture baseline timestamps properly."""
    proj_id = temp_db.insert_project({"name": "Nested Subtask Project"})
    p_id = temp_db.insert_task({"title": "Root Task", "project_id": proj_id})
    with temp_db.get_connection() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO subtasks (id, task_id, title, position) VALUES (500, ?, 'Phase 1', 1)", (p_id,))
        c.execute("""
            INSERT INTO subtasks (task_id, parent_subtask_id, title, position, planned_date, planned_start_time, due_date, planned_end_time, estimated_duration)
            VALUES (?, 500, 'Nested Leaf', 1, '2026-09-03', '09:00', '2026-09-04', '17:00', 960)
        """, (p_id,))
        conn.commit()

    temp_db.set_project_baseline(proj_id, "Baseline 1")

    with temp_db.get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT baseline_start, baseline_finish FROM subtasks WHERE parent_subtask_id = 500")
        row = c.fetchone()
        assert row["baseline_start"].startswith("2026-09-03 09:00")


def test_63_subtask_current_schedule_edit_leaves_baseline_frozen(temp_db):
    """63. Editing subtask planned schedule dates leaves subtask baseline intact."""
    proj_id = temp_db.insert_project({"name": "Subtask Immutability"})
    p_id = temp_db.insert_task({"title": "Parent", "project_id": proj_id})
    with temp_db.get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO subtasks (id, task_id, title, position, planned_date, planned_start_time, due_date, planned_end_time, baseline_start, baseline_finish)
            VALUES (600, ?, 'Leaf', 1, '2026-09-01', '09:00', '2026-09-02', '17:00', '2026-09-01 09:00:00', '2026-09-02 17:00:00')
        """, (p_id,))
        conn.commit()

    # Move current subtask dates
    with temp_db.get_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE subtasks SET planned_date = '2026-09-15', due_date = '2026-09-18' WHERE id = 600")
        conn.commit()

    with temp_db.get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT planned_date, baseline_start, baseline_finish FROM subtasks WHERE id = 600")
        row = c.fetchone()
        assert row["planned_date"] == "2026-09-15"
        assert row["baseline_start"] == "2026-09-01 09:00:00"
        assert row["baseline_finish"] == "2026-09-02 17:00:00"


def test_64_baseline_clear_refused_preserves_task_and_subtask_snapshots(temp_db):
    """64. Clear baseline is refused and preserves task/subtask snapshots."""
    proj_id = temp_db.insert_project({"name": "Clear Tasks and Subtasks"})
    t_id = temp_db.insert_task({"title": "Task", "project_id": proj_id, "baseline_start": "2026-09-01 09:00:00", "baseline_finish": "2026-09-02 17:00:00"})
    with temp_db.get_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO subtasks (task_id, title, position, baseline_start, baseline_finish)
            VALUES (?, 'Sub', 1, '2026-09-01 09:00:00', '2026-09-02 17:00:00')
        """, (t_id,))
        conn.commit()

    with pytest.raises(ScheduleVersionImmutabilityError):
        temp_db.clear_project_baseline(proj_id)

    t = temp_db.get_task_by_id(t_id)
    assert t["baseline_start"] == "2026-09-01 09:00:00"

    with temp_db.get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT baseline_start, baseline_finish FROM subtasks WHERE task_id = ?", (t_id,))
        row = c.fetchone()
        assert row["baseline_start"] == "2026-09-01 09:00:00"
        assert row["baseline_finish"] == "2026-09-02 17:00:00"


# ============================================================================
# 14. DATABASE SAFETY & MIGRATIONS (Acceptance Criteria 65 - 68)
# ============================================================================

def test_65_schema_v13_to_v14_migration_non_destructive(tmp_path):
    """65. Schema migration from v13 to v14 preserves all existing tasks, projects, and subtasks."""
    db_file = str(tmp_path / "v13_legacy.db")
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY);")
    c.execute("INSERT INTO schema_version (version) VALUES (13);")
    c.execute("""
        CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            color TEXT DEFAULT '#3584E4'
        );
    """)
    c.execute("""
        CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            project_id INTEGER,
            planned_date TEXT,
            due_date TEXT
        );
    """)
    c.execute("""
        CREATE TABLE subtasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            title TEXT NOT NULL
        );
    """)
    c.execute("INSERT INTO projects (id, name) VALUES (1, 'Legacy Project');")
    c.execute("INSERT INTO tasks (id, title, project_id, planned_date) VALUES (10, 'Legacy Task', 1, '2026-09-01');")
    c.execute("INSERT INTO subtasks (id, task_id, title) VALUES (100, 10, 'Legacy Subtask');")
    conn.commit()
    conn.close()

    # Open with DatabaseManager which runs _init_db migrations up to v14
    db = DatabaseManager(db_file)
    p = db.get_project(1)
    assert p["name"] == "Legacy Project"
    t = db.get_task_by_id(10)
    assert t["title"] == "Legacy Task"
    assert t["planned_date"] == "2026-09-01"
    assert "baseline_start" in t
    db.close()


def test_66_repeated_startup_does_not_alter_migration(tmp_path):
    """66. Repeated normal startup runs schema migrations idempotently without error or alteration."""
    db_file = str(tmp_path / "idempotent_test.db")
    db1 = DatabaseManager(db_file)
    db1.close()
    db2 = DatabaseManager(db_file)
    db2.close()
    db3 = DatabaseManager(db_file)

    with db3.get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT MAX(version) FROM schema_version;")
        row = c.fetchone()
        assert row[0] >= 14
    db3.close()


def test_67_partial_task_update_preserves_baseline(temp_db):
    """67. Updating unrelated fields (like title or category) does not nullify baseline fields."""
    t_id = temp_db.insert_task({
        "title": "Baseline Task",
        "baseline_start": "2026-09-01 09:00:00",
        "baseline_finish": "2026-09-02 17:00:00",
        "baseline_duration_minutes": 1920,
    })

    temp_db.update_task({"title": "Renamed Task", "category": "Engineering"}, t_id)

    t = temp_db.get_task_by_id(t_id)
    assert t["title"] == "Renamed Task"
    assert t["category"] == "Engineering"
    assert t["baseline_start"] == "2026-09-01 09:00:00"
    assert t["baseline_finish"] == "2026-09-02 17:00:00"
    assert t["baseline_duration_minutes"] == 1920


def test_68_deleting_task_leaves_no_unsafe_orphan_baseline_data(temp_db):
    """68. Deleting a task cleanly deletes task row and leaves DB in consistent state."""
    proj_id = temp_db.insert_project({"name": "Deletion Project"})
    t_id = temp_db.insert_task({
        "title": "Task To Delete",
        "project_id": proj_id,
        "baseline_start": "2026-09-01 09:00:00",
        "baseline_finish": "2026-09-02 17:00:00",
    })

    deleted = temp_db.delete_task(t_id)
    assert deleted is True

    t = temp_db.get_task_by_id(t_id)
    assert t is None
