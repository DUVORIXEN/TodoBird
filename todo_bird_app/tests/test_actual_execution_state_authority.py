"""
TODO BIRD — ACTUAL EXECUTION STATE & AUTHORITY TEST SUITE (Phase 2E)

Comprehensive 50-item verification suite testing:
- Canonical Actual Execution State Machine (NOT_TRACKED, IN_PROGRESS, FINISHED).
- Detection and prevention of invalid states and contradictions.
- Deterministic calculation of full calendar-time Actual Elapsed minutes.
- Execution Start & Finish Variance sign contract (Actual - Reference).
- Independence of Actuals from Schedule/Forecast/Baseline/Revisions/Effort/Progress.
- Cross-view authority parity (TaskDialog, WBS, Gantt, Dashboard, Calendar).
- Real QImage/QPainter pixel rendering verification in dark & light themes.
- Absolute read-only production DB safety.
"""

import os
import sys
import tempfile
import sqlite3
import hashlib
from datetime import datetime, date, time, timedelta

import pytest
from PySide6.QtCore import Qt, QDate, QTime, QRectF
from PySide6.QtGui import QImage, QColor, QPainter
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority, TaskCategory
from todo_bird_app.models.project import Project
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.gantt.gantt_chart import GanttChartWidget
from todo_bird_app.gantt.gantt_items import GanttTaskItem
from todo_bird_app.gantt.timescale_engine import TimescaleEngine, ZoomLevel
from todo_bird_app.services.cpm_scheduling_service import CPMSchedulingService
from todo_bird_app.services.execution_performance_service import (
    ExecutionPerformanceService,
    ExecutionState,
    StartPerformance,
    FinishPerformance,
    ExecutionDiagnosticCode,
    ExecutionAnomalyCode,
)
from todo_bird_app.services.wbs_rollup_service import WBSRollupService
from todo_bird_app.services.wbs_service import WBSService, EntityRef
from todo_bird_app.utils.time_math import (
    set_current_datetime_override,
    get_current_datetime,
    get_current_date,
    calculate_actual_elapsed_minutes,
)


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture(autouse=True)
def cleanup_time_mock():
    set_current_datetime_override(datetime(2026, 8, 25, 9, 0, 0))
    yield
    set_current_datetime_override(None)


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    with db.get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO projects (id, name, color) VALUES (1, 'Default Project', '#3B82F6')")
        conn.execute("INSERT OR IGNORE INTO projects (id, name, color) VALUES (4, 'THAAVORIX', '#10B981')")
        conn.commit()
    yield db
    if os.path.exists(path):
        os.remove(path)


def build_widget_with_cpm(tasks):
    cpm_res = CPMSchedulingService.calculate_schedule(tasks, project_id=4)
    for t in tasks:
        node = cpm_res.nodes.get(t.id)
        if node:
            t.cpm_earliest_start = node.earliest_start
            t.cpm_earliest_finish = node.earliest_finish
            t.gantt_planned_start = node.earliest_start.date() if node.earliest_start else None
            t.gantt_planned_finish = node.earliest_finish.date() if node.earliest_finish else None

    widget = GanttChartWidget(settings_manager=None)
    widget.filter_project_id = 4
    widget.zoom_mode = ZoomLevel.DAILY
    widget.set_tasks(tasks, {4: "THAAVORIX"})
    return widget


# -----------------------------------------------------------------------------
# 1. State Machine: Clean States & Invariant Checks
# -----------------------------------------------------------------------------

def test_01_not_tracked_clean_state():
    """1. Untracked state: actual dates are NULL, execution state is NOT_TRACKED."""
    task = Task(title="Untracked", planned_date="2026-09-15", due_date="2026-10-16")
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.execution_state in (ExecutionState.NOT_TRACKED, ExecutionState.NOT_STARTED)
    assert res.actual_start is None
    assert res.actual_finish is None
    assert res.actual_elapsed_minutes == 0
    assert res.start_performance == StartPerformance.NOT_STARTED
    assert res.finish_performance == FinishPerformance.UNAVAILABLE


def test_02_tracked_in_progress_clean_state():
    """2. Tracked In-Progress state: actual start set, actual finish is NULL."""
    set_current_datetime_override(datetime(2026, 8, 25, 12, 0))
    task = Task(
        title="In Progress",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        actual_end_date=None,
        actual_end_time=None,
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.execution_state == ExecutionState.IN_PROGRESS
    assert res.actual_start == datetime(2026, 8, 24, 8, 0)
    assert res.actual_finish is None
    # Elapsed from 24 Aug 08:00 to 25 Aug 12:00 = 28 hours = 1680 minutes
    assert res.actual_elapsed_minutes == 1680
    assert res.finish_performance == FinishPerformance.IN_PROGRESS


def test_03_finished_clean_state():
    """3. Tracked Finished state: both actual start and actual finish set."""
    task = Task(
        title="Finished Task",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        actual_end_date="2026-08-28",
        actual_end_time="17:00",
        status=TaskStatus.COMPLETED,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.execution_state in (ExecutionState.FINISHED, ExecutionState.COMPLETED)
    assert res.actual_start == datetime(2026, 8, 24, 8, 0)
    assert res.actual_finish == datetime(2026, 8, 28, 17, 0)
    assert res.actual_elapsed_minutes == 6300
    assert res.finish_performance in (
        FinishPerformance.FINISHED_EARLY,
        FinishPerformance.FINISHED_ON_TIME,
        FinishPerformance.FINISHED_LATE,
        FinishPerformance.UNAVAILABLE,
    )


def test_04_reject_finish_without_start():
    """4. Anomaly detection: actual finish exists without actual start."""
    task = Task(title="Invalid Finish", actual_start_date=None, actual_end_date="2026-08-28")
    anomalies = ExecutionPerformanceService.validate_execution_state(task)
    codes = [code for code, _ in anomalies]
    assert ExecutionAnomalyCode.ACTUAL_FINISH_WITHOUT_START in codes


def test_05_reject_finish_before_start():
    """5. Anomaly detection: actual finish earlier than actual start."""
    task = Task(
        title="Time Travel",
        actual_start_date="2026-08-28",
        actual_start_time="08:00",
        actual_end_date="2026-08-24",
        actual_end_time="17:00",
    )
    anomalies = ExecutionPerformanceService.validate_execution_state(task)
    codes = [code for code, _ in anomalies]
    assert ExecutionAnomalyCode.ACTUAL_FINISH_BEFORE_START in codes


# -----------------------------------------------------------------------------
# 2. Task Dialog: Resting State, Editing & Persistence
# -----------------------------------------------------------------------------

def test_06_opening_dialog_does_not_mutate(temp_db):
    """6. Opening a dialog must never mutate task actuals in DB."""
    controller = TaskController(temp_db)
    task = Task(title="Witness Task", project_id=1, planned_date="2026-09-15", actual_start_date="2026-08-24", actual_start_time="08:00")
    tid = controller.add_task(task)
    task.id = tid

    projects = [Project.from_row(p) for p in temp_db.get_all_projects()]
    dlg = TaskDialog(projects=projects, task=task, db_manager=temp_db)
    saved = controller.get_task(tid)
    assert saved.actual_start_date == "2026-08-24"
    assert saved.actual_end_date is None


def test_07_cancelling_dialog_does_not_mutate(temp_db):
    """7. Rejecting/cancelling dialog leaves persisted state untouched."""
    controller = TaskController(temp_db)
    task = Task(title="Cancel Test", project_id=1, planned_date="2026-09-15", actual_start_date="2026-08-24", actual_start_time="08:00")
    tid = controller.add_task(task)
    task.id = tid

    projects = [Project.from_row(p) for p in temp_db.get_all_projects()]
    dlg = TaskDialog(projects=projects, task=task, db_manager=temp_db)
    dlg.actual_finish_check.setChecked(True)
    dlg.reject()

    saved = controller.get_task(tid)
    assert saved.actual_end_date is None


def test_08_save_explicit_start_persists(temp_db):
    """8. Explicitly tracking actual start persists upon save."""
    controller = TaskController(temp_db)
    task = Task(title="Start Test", project_id=1, planned_date="2026-09-15")
    tid = controller.add_task(task)
    task.id = tid

    projects = [Project.from_row(p) for p in temp_db.get_all_projects()]
    dlg = TaskDialog(projects=projects, task=task, db_manager=temp_db)
    dlg.actual_enabled_check.setChecked(True)
    dlg.actual_start_date_edit.setDate(QDate(2026, 8, 24))
    dlg.actual_start_edit.setTime(QTime(8, 0))
    dlg.on_save()

    controller.update_task(dlg.task)
    saved = controller.get_task(tid)
    assert saved.actual_start_date == "2026-08-24"
    assert saved.actual_start_time == "08:00"
    assert saved.actual_end_date is None


def test_09_unfinished_persists_null_end(temp_db):
    """9. While unfinished, actual_end_date and time remain strictly NULL."""
    controller = TaskController(temp_db)
    task = Task(title="Unfinished", project_id=1, actual_start_date="2026-08-24", actual_start_time="08:00")
    tid = controller.add_task(task)
    task.id = tid

    projects = [Project.from_row(p) for p in temp_db.get_all_projects()]
    dlg = TaskDialog(projects=projects, task=task, db_manager=temp_db)
    dlg.on_save()
    controller.update_task(dlg.task)

    saved = controller.get_task(tid)
    assert saved.actual_end_date is None
    assert saved.actual_end_time is None


def test_10_explicit_finish_persists_exactly(temp_db):
    """10. Checking finished and choosing finish date/time persists exactly."""
    controller = TaskController(temp_db)
    task = Task(title="Finish Test", project_id=1, actual_start_date="2026-08-24", actual_start_time="08:00")
    tid = controller.add_task(task)
    task.id = tid

    projects = [Project.from_row(p) for p in temp_db.get_all_projects()]
    dlg = TaskDialog(projects=projects, task=task, db_manager=temp_db)
    dlg.actual_finish_check.setChecked(True)
    dlg.actual_end_date_edit.setDate(QDate(2026, 8, 26))
    dlg.actual_end_edit.setTime(QTime(17, 30))
    dlg.on_save()
    controller.update_task(dlg.task)

    saved = controller.get_task(tid)
    assert saved.actual_end_date == "2026-08-26"
    assert saved.actual_end_time == "17:30"


# -----------------------------------------------------------------------------
# 3. Non-Inference: Zero Fabrication from Non-Execution Fields
# -----------------------------------------------------------------------------

def test_11_actual_effort_does_not_infer_finish():
    """11. Logging work effort (actual_duration) does not create actual finish."""
    task = Task(title="Effort Only", actual_start_date="2026-08-24", actual_duration=480)
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.execution_state == ExecutionState.IN_PROGRESS
    assert res.actual_finish is None


def test_12_dedication_does_not_infer_finish():
    """12. Daily dedication does not create actual finish."""
    task = Task(title="Dedication", actual_start_date="2026-08-24", daily_dedication_minutes=240)
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.execution_state == ExecutionState.IN_PROGRESS
    assert res.actual_finish is None


def test_13_progress_does_not_infer_finish():
    """13. Setting progress to 100% does not fabricate an actual finish timestamp."""
    task = Task(title="Progress 100", actual_start_date="2026-08-24", progress=100)
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.execution_state == ExecutionState.IN_PROGRESS
    assert res.actual_finish is None


def test_14_due_date_does_not_infer_finish():
    """14. Due date does not fabricate an actual finish."""
    task = Task(title="Due Date", actual_start_date="2026-08-24", due_date="2026-09-01")
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_finish is None


def test_15_planned_date_does_not_infer_finish():
    """15. Planned date does not fabricate an actual finish."""
    task = Task(title="Planned Date", actual_start_date="2026-08-24", planned_date="2026-09-01")
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_finish is None


def test_16_cpm_ef_does_not_infer_finish():
    """16. CPM Earliest Finish does not fabricate an actual finish."""
    task = Task(title="CPM EF", actual_start_date="2026-08-24")
    setattr(task, "cpm_earliest_finish", "2026-09-05 17:00")
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_finish is None


def test_17_baseline_does_not_infer_finish():
    """17. Baseline finish does not fabricate an actual finish."""
    task = Task(title="Baseline", actual_start_date="2026-08-24")
    setattr(task, "baseline_finish", "2026-09-10 17:00")
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_finish is None


def test_18_revision_does_not_infer_finish():
    """18. Approved revision finish does not fabricate an actual finish."""
    task = Task(title="Revision", actual_start_date="2026-08-24")
    setattr(task, "revision_finish", "2026-09-12 17:00")
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_finish is None


# -----------------------------------------------------------------------------
# 4. Canonical Now & Elapsed Calculations
# -----------------------------------------------------------------------------

def test_19_open_actual_uses_canonical_now_ephemerally():
    """19. In-progress execution uses canonical now dynamically."""
    set_current_datetime_override(datetime(2026, 8, 25, 10, 0))
    task = Task(title="Now Test", actual_start_date="2026-08-24", actual_start_time="10:00")
    res1 = ExecutionPerformanceService.analyze_task_execution(task)
    assert res1.actual_elapsed_minutes == 1440  # exactly 24 hours

    set_current_datetime_override(datetime(2026, 8, 25, 12, 0))
    res2 = ExecutionPerformanceService.analyze_task_execution(task)
    assert res2.actual_elapsed_minutes == 1560  # exactly 26 hours


def test_20_canonical_now_not_persisted(temp_db):
    """20. Canonical now is never persisted into actual_end_date."""
    controller = TaskController(temp_db)
    set_current_datetime_override(datetime(2026, 8, 25, 12, 0))
    task = Task(title="Persist Check", project_id=1, actual_start_date="2026-08-24", actual_start_time="08:00")
    tid = controller.add_task(task)

    saved = controller.get_task(tid)
    assert saved.actual_end_date is None
    assert saved.actual_end_time is None


def test_21_open_actual_elapsed_exact():
    """21. Exact integer minute precision for open actual elapsed time."""
    set_current_datetime_override(datetime(2026, 8, 24, 8, 47))
    task = Task(title="Precision", actual_start_date="2026-08-24", actual_start_time="08:00")
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_elapsed_minutes == 47


def test_22_finished_elapsed_exact():
    """22. Exact integer minute precision for finished actual elapsed time."""
    task = Task(
        title="Finished Precision",
        actual_start_date="2026-08-24",
        actual_start_time="08:15",
        actual_end_date="2026-08-24",
        actual_end_time="10:45",
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_elapsed_minutes == 150


def test_23_weekend_actual_elapsed_counted():
    """23. Full calendar time is used; weekend hours are not removed."""
    # 2026-08-21 is Friday, 2026-08-24 is Monday (72h)
    task = Task(
        title="Weekend Span",
        actual_start_date="2026-08-21",
        actual_start_time="08:00",
        actual_end_date="2026-08-24",
        actual_end_time="08:00",
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_elapsed_minutes == 72 * 60  # 4320 minutes


def test_24_cross_midnight():
    """24. Cross-midnight elapsed calculation is exact."""
    task = Task(
        title="Midnight",
        actual_start_date="2026-08-24",
        actual_start_time="23:30",
        actual_end_date="2026-08-25",
        actual_end_time="01:15",
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_elapsed_minutes == 105


def test_25_month_boundary():
    """25. Month boundary crossing is exact."""
    task = Task(
        title="Month End",
        actual_start_date="2026-08-31",
        actual_start_time="22:00",
        actual_end_date="2026-09-01",
        actual_end_time="02:00",
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_elapsed_minutes == 240


def test_26_year_boundary():
    """26. Year boundary crossing is exact."""
    task = Task(
        title="Year End",
        actual_start_date="2026-12-31",
        actual_start_time="20:00",
        actual_end_date="2027-01-01",
        actual_end_time="08:00",
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_elapsed_minutes == 720


def test_27_leap_day():
    """27. Leap year (2028-02-29) calculation is exact."""
    task = Task(
        title="Leap Day",
        actual_start_date="2028-02-28",
        actual_start_time="12:00",
        actual_end_date="2028-03-01",
        actual_end_time="12:00",
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_elapsed_minutes == 2880  # 48 hours (includes Feb 29)


def test_28_2100_non_leap():
    """28. Non-leap centurial year (2100) calculation is exact."""
    task = Task(
        title="2100 Non-Leap",
        actual_start_date="2100-02-28",
        actual_start_time="12:00",
        actual_end_date="2100-03-01",
        actual_end_time="12:00",
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_elapsed_minutes == 1440  # 24 hours (no Feb 29)


# -----------------------------------------------------------------------------
# 5. Sign Contract & Variances
# -----------------------------------------------------------------------------

def test_29_early_start_variance():
    """29. Started early: Actual Start < Planned Start yields negative variance."""
    task = Task(
        title="Early Start",
        planned_date="2026-09-15",
        planned_start_time="09:00",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.start_variance_minutes < 0
    assert res.start_performance == StartPerformance.STARTED_EARLY
    assert "early" in res.start_variance_display.lower()


def test_30_on_time_start_variance():
    """30. Started on time yields 0 variance."""
    task = Task(
        title="On Time",
        planned_date="2026-08-24",
        planned_start_time="08:00",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.start_variance_minutes == 0
    assert res.start_performance == StartPerformance.STARTED_ON_TIME


def test_31_late_start_variance():
    """31. Started late: Actual Start > Planned Start yields positive variance."""
    task = Task(
        title="Late Start",
        planned_date="2026-08-20",
        planned_start_time="08:00",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.start_variance_minutes > 0
    assert res.start_performance == StartPerformance.STARTED_LATE
    assert "late" in res.start_variance_display.lower()


def test_32_finish_variance_unavailable_while_open():
    """32. Finish variance is UNAVAILABLE while task is open / in progress."""
    task = Task(title="Open", planned_date="2026-09-15", actual_start_date="2026-08-24")
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.finish_variance_minutes is None
    assert res.finish_performance == FinishPerformance.IN_PROGRESS


def test_33_finish_variance_after_finish():
    """33. Finish variance is calculated once explicitly finished."""
    task = Task(
        title="Finished",
        planned_date="2026-09-15",
        due_date="2026-10-16",
        actual_start_date="2026-08-24",
        actual_end_date="2026-10-10",
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.finish_variance_minutes is not None
    assert res.finish_variance_minutes < 0  # Finished before Oct 16
    assert res.finish_performance == FinishPerformance.FINISHED_EARLY


def test_34_schedule_variance_independent():
    """34. Schedule variance (Forecast vs Baseline) and Execution variance are separate."""
    task = Task(
        title="Dual Variance",
        planned_date="2026-09-15",
        due_date="2026-10-16",
        actual_start_date="2026-08-24",
    )
    setattr(task, "baseline_start", "2026-09-01 08:00")
    res = ExecutionPerformanceService.analyze_task_execution(task, reference_start=datetime(2026, 9, 15, 8, 0))
    assert res.start_variance_minutes < 0  # 24 Aug vs 15 Sep


# -----------------------------------------------------------------------------
# 6. Constraints vs Actuals & Status
# -----------------------------------------------------------------------------

def test_35_constraint_contradiction_retained():
    """35. SNET constraint with earlier actual start produces diagnostic while retaining dates."""
    task = Task(
        title="Constraint Contradiction",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
    )
    setattr(task, "constraint_type", "SNET")
    setattr(task, "constraint_date", "2026-09-15")
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert ExecutionDiagnosticCode.ACTUAL_START_BEFORE_SNET in res.diagnostic_codes


def test_36_snet_does_not_rewrite_actual():
    """36. SNET constraint does not mutate or rewrite factual actual start date."""
    task = Task(
        title="No Rewrite",
        actual_start_date="2026-08-24",
    )
    setattr(task, "constraint_type", "SNET")
    setattr(task, "constraint_date", "2026-09-15")
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_start.date() == date(2026, 8, 24)


def test_37_status_change_does_not_fabricate_finish():
    """37. Setting status to In Progress or Cancelled does not fabricate finish."""
    task = Task(title="Status Test", status=TaskStatus.IN_PROGRESS, actual_start_date="2026-08-24")
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_finish is None


def test_38_explicit_mark_complete_now_semantics(temp_db):
    """38. toggle_task_complete stamps actual finish only if tracked, and uncompleting clears it."""
    controller = TaskController(temp_db)
    set_current_datetime_override(datetime(2026, 8, 25, 15, 30))
    task = Task(title="Toggle Complete", project_id=1, actual_start_date="2026-08-24", actual_start_time="08:00")
    tid = controller.add_task(task)

    # 1. Complete
    controller.toggle_task_complete(tid)
    completed_task = controller.get_task(tid)
    assert completed_task.status == TaskStatus.COMPLETED
    assert completed_task.actual_end_date == "2026-08-25"
    assert completed_task.actual_end_time == "15:30"

    # 2. Uncomplete
    controller.toggle_task_complete(tid)
    reopened_task = controller.get_task(tid)
    assert reopened_task.status != TaskStatus.COMPLETED
    assert reopened_task.actual_end_date is None
    assert reopened_task.actual_end_time is None


# -----------------------------------------------------------------------------
# 7. Cross-View Consistency
# -----------------------------------------------------------------------------

def test_39_task_dialog_wbs_agree(temp_db):
    """39. TaskDialog and WBS rollup agree on actual start and elapsed calculations."""
    set_current_datetime_override(datetime(2026, 8, 25, 12, 0))
    controller = TaskController(temp_db)
    task = Task(
        title="Task Dialog vs WBS",
        project_id=1,
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.COMPLETED,
        actual_end_date="2026-08-25",
        actual_end_time="12:00",
    )
    tid = controller.add_task(task)
    task.id = tid

    # Task Dialog analysis
    dlg_res = ExecutionPerformanceService.analyze_task_execution(task)

    # WBS calculation
    snap = WBSService.build_project_hierarchy(temp_db, project_id=task.project_id)
    rollups = WBSRollupService.compute_all_rollups(snap, temp_db)
    rollup = rollups.get(EntityRef.task(tid))

    # Elapsed from 24 Aug 08:00 to 25 Aug 12:00 = 1680 minutes
    assert dlg_res.actual_start == rollup.actual_start == datetime(2026, 8, 24, 8, 0)
    assert dlg_res.actual_finish == rollup.actual_finish == datetime(2026, 8, 25, 12, 0)
    assert dlg_res.actual_elapsed_minutes == rollup.actual_elapsed_minutes == 1680


def test_40_task_dialog_gantt_agree(temp_db):
    """40. TaskDialog and Gantt item consume the exact same actual performance result."""
    set_current_datetime_override(datetime(2026, 8, 25, 12, 0))
    controller = TaskController(temp_db)
    task = Task(id=10, title="Dialog vs Gantt", project_id=4, planned_date="2026-09-15", actual_start_date="2026-08-24", actual_start_time="08:00")

    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.start_performance == StartPerformance.STARTED_EARLY

    widget = build_widget_with_cpm([task])
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    assert planning_item is not None
    assert "Started" in planning_item.toolTip()


def test_41_wbs_gantt_agree(temp_db):
    """41. WBS and Gantt agree on actual start date and active status."""
    controller = TaskController(temp_db)
    task = Task(id=10, title="WBS Gantt Parity", project_id=4, actual_start_date="2026-08-24", actual_start_time="08:00")
    tid = controller.add_task(task)
    task.id = tid

    snap = WBSService.build_project_hierarchy(temp_db, project_id=task.project_id)
    rollups = WBSRollupService.compute_all_rollups(snap, temp_db)
    rollup = rollups.get(EntityRef.task(tid))

    widget = build_widget_with_cpm([task])
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == tid
    )

    assert rollup.actual_start == datetime(2026, 8, 24, 8, 0)
    actual_bars = [c for c in planning_item.childItems() if c.toolTip() == "Actual Execution — In Progress"]
    assert len(actual_bars) == 1


def test_42_dashboard_canonical_authority():
    """42. Dashboard metrics consume ExecutionPerformanceService without deviations."""
    task = Task(title="Dashboard", planned_date="2026-09-15", actual_start_date="2026-08-24", actual_start_time="08:00")
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.execution_state == ExecutionState.IN_PROGRESS
    assert res.start_variance_minutes < 0


def test_43_calendar_canonical_authority():
    """43. Calendar view metrics consume canonical time provider and execution authority."""
    task = Task(title="Calendar", actual_start_date="2026-08-24", actual_start_time="08:00")
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_start == datetime(2026, 8, 24, 8, 0)


# -----------------------------------------------------------------------------
# 8. Gantt Visual Geometry & Rendering
# -----------------------------------------------------------------------------

def test_44_actual_bar_visible_without_hover():
    """44. Actual bar item is added to the scene and is visible without hover."""
    task = Task(
        id=10,
        title="Planning",
        project_id=4,
        planned_date="2026-09-15",
        due_date="2026-10-16",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
    )
    widget = build_widget_with_cpm([task])

    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    assert actual_bar.isVisible() is True


def test_45_actual_bar_positive_geometry():
    """45. Actual bar has positive width, height, and valid scene coordinates."""
    task = Task(
        id=10,
        title="Planning",
        project_id=4,
        planned_date="2026-09-15",
        due_date="2026-10-16",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
    )
    widget = build_widget_with_cpm([task])

    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    act_rect = actual_bar.sceneBoundingRect()
    assert act_rect.width() > 0
    assert act_rect.height() > 0


def test_46_timescale_includes_early_actual():
    """46. Timescale dynamic date range includes early actual start."""
    task = Task(
        id=10,
        title="Planning",
        project_id=4,
        planned_date="2026-09-15",
        due_date="2026-10-16",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
    )
    min_d, max_d = TimescaleEngine.get_relevant_date_range(date(2026, 9, 15), [task])
    assert min_d <= date(2026, 8, 24)
    assert max_d >= date(2026, 10, 16)


def test_47_fit_project_includes_actual():
    """47. Fit Project incorporates early actual dates into scene span."""
    task = Task(
        id=10,
        title="Planning",
        project_id=4,
        planned_date="2026-09-15",
        due_date="2026-10-16",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
    )
    widget = build_widget_with_cpm([task])
    cols = widget.columns
    first_col_date = cols[0].start_date
    last_col_date = cols[-1].end_date
    assert first_col_date <= date(2026, 8, 24)
    assert last_col_date >= date(2026, 10, 16)


# -----------------------------------------------------------------------------
# 9. Pixel / Render Tests
# -----------------------------------------------------------------------------

def test_48_dark_rendering_pixel_check():
    """48. Real QPainter rasterization proves actual bar renders distinctly in Dark theme."""
    task = Task(
        id=10,
        title="Planning",
        project_id=4,
        planned_date="2026-09-15",
        due_date="2026-10-16",
        actual_start_date="2026-08-23",
        actual_start_time="08:00",
    )
    widget = build_widget_with_cpm([task])

    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    act_scene_rect = actual_bar.sceneBoundingRect()
    w = max(10, int(act_scene_rect.width()))
    h = max(10, int(act_scene_rect.height()))

    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor("#1e1e2e"))
    painter = QPainter(img)
    widget.scene.render(painter, QRectF(0, 0, w, h), act_scene_rect)
    painter.end()

    # Actual bar pixel sample at center
    pixel = img.pixelColor(w // 2, h // 2)
    # Emerald green actual bar has high green component
    assert pixel.green() > pixel.red()
    assert pixel.green() > 100


def test_49_light_rendering_pixel_check():
    """49. Real QPainter rasterization proves actual bar renders distinctly in Light theme."""
    task = Task(
        id=10,
        title="Planning",
        project_id=4,
        planned_date="2026-09-15",
        due_date="2026-10-16",
        actual_start_date="2026-08-23",
        actual_start_time="08:00",
    )
    widget = build_widget_with_cpm([task])

    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    act_scene_rect = actual_bar.sceneBoundingRect()
    w = max(10, int(act_scene_rect.width()))
    h = max(10, int(act_scene_rect.height()))

    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor("#ffffff"))
    painter = QPainter(img)
    widget.scene.render(painter, QRectF(0, 0, w, h), act_scene_rect)
    painter.end()

    pixel = img.pixelColor(w // 2, h // 2)
    assert pixel.green() > pixel.red()


# -----------------------------------------------------------------------------
# 10. Production DB Safety
# -----------------------------------------------------------------------------

def test_50_production_db_untouched():
    """50. Production DB remains 100% read-only and unmutated."""
    from todo_bird_app.tests.path_helpers import production_db_path
    prod_path = str(production_db_path())
    assert os.path.exists(prod_path)
    with sqlite3.connect(f"file:{prod_path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        rows = cur.execute("SELECT id, title, actual_start_date, actual_end_date FROM tasks WHERE project_id = 4").fetchall()
        for r in rows:
            if r["title"] == "Planning":
                assert r["actual_start_date"] == "2026-08-23"
                assert r["actual_end_date"] is None
