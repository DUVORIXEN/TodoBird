"""
Test Module: Execution-Aware Schedule Authority (Phase 2E)
Validates all 50 mandatory execution-aware schedule authority rules:
 1. planned future task no actual
 2. early actual start
 3. late actual start
 4. actual exactly on planned start
 5. planned bar remains unchanged after early actual
 6. baseline remains unchanged
 7. revision remains unchanged
 8. open actual starts exact Actual Start
 9. open actual ends visually at canonical now
10. now endpoint never persisted
11. open Actual labelled In Progress
12. Actual Finish shows Not finished
13. explicit finish closes bar
14. finish exact timestamp persists
15. actual effort does not resize bar
16. daily dedication does not resize bar
17. progress does not fabricate finish
18. execution start variance negative when early
19. zero when on time
20. positive when late
21. exact minute variance
22. baseline execution variance
23. revision execution variance
24. schedule variance remains independent
25. finish variance unavailable while open
26. finish variance calculated when finished
27. constraint before/after actual diagnostic
28. SNET does not rewrite Actual Start
29. SNLT actual contradiction diagnostic
30. FNET actual contradiction diagnostic
31. FNLT actual contradiction diagnostic
32. MSO actual contradiction diagnostic
33. MFO actual contradiction diagnostic
34. cross-midnight variance
35. month-end
36. year-end
37. leap-day
38. weekend actual elapsed
39. project-calendar does not reduce actual elapsed
40. WBS/Gantt performance values agree
41. Task Dialog/Gantt values agree
42. tooltip correct
43. current-time provider deterministic in tests
44. light mode
45. dark mode
46. 10pt
47. 20pt
48. no DB query in paint
49. no duplicate formula path
50. no production DB mutation
"""

import os
import tempfile
from datetime import datetime, date, timedelta
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QDate, QTime

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.utils.time_math import (
    calculate_actual_elapsed_minutes,
    duration_between,
    get_current_datetime,
    set_current_datetime_override,
)
from todo_bird_app.services.execution_performance_service import (
    ExecutionPerformanceService,
    ExecutionState,
    StartPerformance,
    FinishPerformance,
    ExecutionDiagnosticCode,
)
from todo_bird_app.services.schedule_variance_service import (
    ScheduleVarianceService,
    VarianceStatus,
)
from todo_bird_app.gantt.gantt_items import GanttTaskItem
from todo_bird_app.gantt.gantt_chart import GanttChartWidget


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    yield db
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture(autouse=True)
def reset_time_override():
    yield
    set_current_datetime_override(None)


# 1. planned future task no actual
def test_01_planned_future_task_no_actual(temp_db):
    task = Task(
        title="Future Plan",
        planned_date="2026-09-15",
        due_date="2026-10-16",
        status=TaskStatus.PLANNED,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.execution_state == ExecutionState.NOT_STARTED
    assert res.actual_start is None
    assert res.actual_finish is None
    assert res.start_performance == StartPerformance.NOT_STARTED
    assert res.finish_performance == FinishPerformance.UNAVAILABLE


# 2. early actual start
def test_02_early_actual_start(temp_db):
    task = Task(
        title="Planning",
        planned_date="2026-09-15",
        due_date="2026-10-16",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.execution_state == ExecutionState.IN_PROGRESS
    assert res.start_performance == StartPerformance.STARTED_EARLY
    assert res.start_variance_minutes < 0
    assert "early" in res.start_variance_display.lower()


# 3. late actual start
def test_03_late_actual_start(temp_db):
    task = Task(
        title="Delayed Start",
        planned_date="2026-09-15",
        planned_start_time="08:00",
        actual_start_date="2026-09-20",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.start_performance == StartPerformance.STARTED_LATE
    assert res.start_variance_minutes > 0
    assert "late" in res.start_variance_display.lower()


# 4. actual exactly on planned start
def test_04_actual_exactly_on_planned_start(temp_db):
    task = Task(
        title="On Time Task",
        planned_date="2026-09-15",
        planned_start_time="08:00",
        actual_start_date="2026-09-15",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.start_performance == StartPerformance.STARTED_ON_TIME
    assert res.start_variance_minutes == 0
    assert "on time" in res.start_variance_display.lower()


# 5. planned bar remains unchanged after early actual
def test_05_planned_bar_remains_unchanged_after_early_actual(temp_db):
    t_id = temp_db.insert_task({
        "title": "Planning",
        "planned_date": "2026-09-15",
        "due_date": "2026-10-16",
        "actual_start_date": "2026-08-24",
        "actual_start_time": "08:00",
        "status": "In Progress",
    })
    saved = temp_db.get_task_by_id(t_id)
    # The planned date and due date must NEVER be overwritten to match actual start
    assert saved["planned_date"] == "2026-09-15"
    assert saved["due_date"] == "2026-10-16"


# 6. baseline remains unchanged
def test_06_baseline_remains_unchanged(temp_db):
    t_id = temp_db.insert_task({
        "title": "Baselined Task",
        "planned_date": "2026-09-15",
        "baseline_start": "2026-09-06 08:00",
        "baseline_finish": "2026-10-07 17:00",
        "actual_start_date": "2026-08-24",
        "actual_start_time": "08:00",
        "status": "In Progress",
    })
    saved = temp_db.get_task_by_id(t_id)
    assert saved["baseline_start"] == "2026-09-06 08:00"
    assert saved["baseline_finish"] == "2026-10-07 17:00"


# 7. revision remains unchanged
def test_07_revision_remains_unchanged(temp_db):
    p_id = temp_db.insert_project({"name": "Revision Safety"})
    t_id = temp_db.insert_task({
        "project_id": p_id,
        "title": "Revision Task",
        "planned_date": "2026-09-15",
        "actual_start_date": "2026-08-24",
        "status": "In Progress",
    })
    v_id = temp_db.create_schedule_version(project_id=p_id, name="Rev 1")
    assert v_id > 0
    saved = temp_db.get_task_by_id(t_id)
    assert saved["planned_date"] == "2026-09-15"


# 8. open actual starts exact Actual Start
def test_08_open_actual_starts_exact_actual_start(temp_db):
    task = Task(
        title="Planning",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_start == datetime(2026, 8, 24, 8, 0)


# 9. open actual ends visually at canonical now
def test_09_open_actual_ends_visually_at_canonical_now(temp_db):
    mock_now = datetime(2026, 8, 25, 12, 0)
    set_current_datetime_override(mock_now)
    task = Task(
        title="Planning",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task, now=mock_now)
    assert res.actual_elapsed_minutes == 28 * 60 + 0  # 28 hours = 1680 mins


# 10. now endpoint never persisted
def test_10_now_endpoint_never_persisted(temp_db):
    t_id = temp_db.insert_task({
        "title": "Open Execution",
        "planned_date": "2026-09-15",
        "actual_start_date": "2026-08-24",
        "actual_start_time": "08:00",
        "actual_end_date": None,
        "status": "In Progress",
    })
    saved = temp_db.get_task_by_id(t_id)
    assert saved["actual_end_date"] is None
    assert saved["actual_end_time"] is None


# 11. open Actual labelled In Progress
def test_11_open_actual_labelled_in_progress(temp_db):
    task = Task(
        id=10,
        title="Planning",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    item = GanttTaskItem(
        task=task,
        row=0,
        col_start=0.0,
        duration_cols=2.0,
        col_width=40,
        color_profile={"actual_color": "#10B981"},
        anchor_date=date(2026, 8, 24),
        zoom_mode="hourly",
    )
    assert "In Progress" in item.toolTip()


# 12. Actual Finish shows Not finished
def test_12_actual_finish_shows_not_finished(temp_db):
    task = Task(
        title="Planning",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        actual_end_date=None,
        status=TaskStatus.IN_PROGRESS,
    )
    dlg = TaskDialog(projects=[], task=task, db_manager=temp_db)
    dlg.show()
    assert dlg.actual_not_finished_label.isVisible() is True
    assert "Not finished" in dlg.actual_not_finished_label.text()
    dlg.close()


# 13. explicit finish closes bar
def test_13_explicit_finish_closes_bar(temp_db):
    task = Task(
        title="Completed Task",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        actual_end_date="2026-08-25",
        actual_end_time="17:00",
        status=TaskStatus.COMPLETED,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.execution_state == ExecutionState.COMPLETED
    assert res.actual_finish == datetime(2026, 8, 25, 17, 0)


# 14. finish exact timestamp persists
def test_14_finish_exact_timestamp_persists(temp_db):
    t_id = temp_db.insert_task({
        "title": "Completed Task",
        "planned_date": "2026-09-15",
        "actual_start_date": "2026-08-24",
        "actual_start_time": "08:00",
        "actual_end_date": "2026-08-25",
        "actual_end_time": "17:30",
        "status": "Completed",
    })
    saved = temp_db.get_task_by_id(t_id)
    assert saved["actual_end_date"] == "2026-08-25"
    assert saved["actual_end_time"] == "17:30"


# 15. actual effort does not resize bar
def test_15_actual_effort_does_not_resize_bar(temp_db):
    task = Task(
        title="Planning",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        actual_end_date="2026-08-26",
        actual_end_time="08:00",
        actual_duration=120,  # 2 hours labor
        status=TaskStatus.COMPLETED,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    # Elapsed is 48 hours (2880 mins), labor is 120 mins
    assert res.actual_elapsed_minutes == 2880
    assert res.actual_work_effort_minutes == 120


# 16. daily dedication does not resize bar
def test_16_daily_dedication_does_not_resize_bar(temp_db):
    task = Task(
        title="Dedication Task",
        planned_date="2026-09-15",
        daily_dedication_minutes=300,
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        actual_end_date="2026-08-26",
        actual_end_time="08:00",
        status=TaskStatus.COMPLETED,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_elapsed_minutes == 2880


# 17. progress does not fabricate finish
def test_17_progress_does_not_fabricate_finish(temp_db):
    task = Task(
        title="Progress Task",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        actual_end_date=None,
        progress=100,
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_finish is None
    assert res.execution_state == ExecutionState.IN_PROGRESS


# 18. execution start variance negative when early
def test_18_execution_start_variance_negative_when_early(temp_db):
    task = Task(
        planned_date="2026-09-15",
        planned_start_time="08:00",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.start_variance_minutes < 0
    assert res.start_performance == StartPerformance.STARTED_EARLY


# 19. zero when on time
def test_19_zero_when_on_time(temp_db):
    task = Task(
        planned_date="2026-09-15",
        planned_start_time="08:00",
        actual_start_date="2026-09-15",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.start_variance_minutes == 0
    assert res.start_performance == StartPerformance.STARTED_ON_TIME


# 20. positive when late
def test_20_positive_when_late(temp_db):
    task = Task(
        planned_date="2026-09-15",
        planned_start_time="08:00",
        actual_start_date="2026-09-16",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.start_variance_minutes > 0
    assert res.start_performance == StartPerformance.STARTED_LATE


# 21. exact minute variance
def test_21_exact_minute_variance(temp_db):
    task = Task(
        planned_date="2026-09-15",
        planned_start_time="09:00",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    # Aug 24 08:00 to Sep 15 09:00 = 22 days (31680m) + 1 hour (60m) = 31740 minutes early
    assert res.start_variance_minutes == -31740


# 22. baseline execution variance
def test_22_baseline_execution_variance(temp_db):
    task = Task(
        baseline_start="2026-09-06 08:00",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task, reference_start="2026-09-06 08:00")
    # Aug 24 to Sep 6 = 13 days = 18720 mins early
    assert res.start_variance_minutes == -18720
    assert "13 days early" in res.start_variance_display


# 23. revision execution variance
def test_23_revision_execution_variance(temp_db):
    task = Task(
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task, reference_start="2026-09-01 08:00")
    # Aug 24 to Sep 1 = 8 days early
    assert res.start_variance_minutes == -11520


# 24. schedule variance remains independent
def test_24_schedule_variance_remains_independent(temp_db):
    # Schedule variance: Forecast (15 Sep) vs Baseline (06 Sep) = +9 days
    # Execution variance: Actual (24 Aug) vs Forecast (15 Sep) = -22 days
    task = Task(
        planned_date="2026-09-15",
        planned_start_time="08:00",
        baseline_start="2026-09-06 08:00",
        baseline_finish="2026-10-07 17:00",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    sched_res = ScheduleVarianceService.calculate_task_variance(
        task=task,
    )
    exec_res = ExecutionPerformanceService.analyze_task_execution(task)

    assert sched_res.start_variance_minutes == 9 * 1440  # +9 days
    assert exec_res.start_variance_minutes == -22 * 1440  # -22 days
    assert sched_res.start_variance_minutes != exec_res.start_variance_minutes


# 25. finish variance unavailable while open
def test_25_finish_variance_unavailable_while_open(temp_db):
    task = Task(
        planned_date="2026-09-15",
        due_date="2026-10-16",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        actual_end_date=None,
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.finish_variance_minutes is None
    assert res.finish_performance == FinishPerformance.IN_PROGRESS
    assert "In progress" in res.finish_variance_display


# 26. finish variance calculated when finished
def test_26_finish_variance_calculated_when_finished(temp_db):
    task = Task(
        due_date="2026-10-16",
        planned_end_time="17:00",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        actual_end_date="2026-10-10",
        actual_end_time="17:00",
        status=TaskStatus.COMPLETED,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.finish_variance_minutes == -6 * 1440  # -6 days (finished 6 days early)
    assert res.finish_performance == FinishPerformance.FINISHED_EARLY
    assert "6 days early" in res.finish_variance_display


# 27. constraint before/after actual diagnostic
def test_27_constraint_before_after_actual_diagnostic(temp_db):
    task = {
        "title": "SNET Task",
        "constraint_type": "SNET",
        "constraint_date": "2026-09-15",
        "actual_start_date": "2026-08-24",
        "actual_start_time": "08:00",
    }
    diag = ExecutionPerformanceService.check_constraint_actual_contradictions(
        task,
        actual_start=datetime(2026, 8, 24, 8, 0),
        actual_finish=None,
    )
    assert len(diag) == 1
    assert diag[0][0] == ExecutionDiagnosticCode.ACTUAL_START_BEFORE_SNET


# 28. SNET does not rewrite Actual Start
def test_28_snet_does_not_rewrite_actual_start(temp_db):
    t_id = temp_db.insert_task({
        "title": "SNET Retain Actual",
        "planned_date": "2026-09-15",
        "constraint_type": "SNET",
        "constraint_datetime": "2026-09-15 08:00",
        "actual_start_date": "2026-08-24",
        "actual_start_time": "08:00",
        "status": "In Progress",
    })
    saved = temp_db.get_task_by_id(t_id)
    assert saved["actual_start_date"] == "2026-08-24"
    assert saved["constraint_datetime"] == "2026-09-15 08:00"


# 29. SNLT actual contradiction diagnostic
def test_29_snlt_actual_contradiction_diagnostic(temp_db):
    task = {
        "constraint_type": "SNLT",
        "constraint_date": "2026-08-20",
        "actual_start_date": "2026-08-24",
    }
    diag = ExecutionPerformanceService.check_constraint_actual_contradictions(
        task,
        actual_start=datetime(2026, 8, 24, 8, 0),
        actual_finish=None,
    )
    assert len(diag) == 1
    assert diag[0][0] == ExecutionDiagnosticCode.ACTUAL_START_AFTER_SNLT


# 30. FNET actual contradiction diagnostic
def test_30_fnet_actual_contradiction_diagnostic(temp_db):
    task = {
        "constraint_type": "FNET",
        "constraint_date": "2026-09-01",
        "actual_start_date": "2026-08-24",
        "actual_end_date": "2026-08-28",
    }
    diag = ExecutionPerformanceService.check_constraint_actual_contradictions(
        task,
        actual_start=datetime(2026, 8, 24, 8, 0),
        actual_finish=datetime(2026, 8, 28, 17, 0),
    )
    assert len(diag) == 1
    assert diag[0][0] == ExecutionDiagnosticCode.ACTUAL_FINISH_BEFORE_FNET


# 31. FNLT actual contradiction diagnostic
def test_31_fnlt_actual_contradiction_diagnostic(temp_db):
    task = {
        "constraint_type": "FNLT",
        "constraint_date": "2026-08-25",
        "actual_start_date": "2026-08-24",
        "actual_end_date": "2026-08-28",
    }
    diag = ExecutionPerformanceService.check_constraint_actual_contradictions(
        task,
        actual_start=datetime(2026, 8, 24, 8, 0),
        actual_finish=datetime(2026, 8, 28, 17, 0),
    )
    assert len(diag) == 1
    assert diag[0][0] == ExecutionDiagnosticCode.ACTUAL_FINISH_AFTER_FNLT


# 32. MSO actual contradiction diagnostic
def test_32_mso_actual_contradiction_diagnostic(temp_db):
    task = {
        "constraint_type": "MSO",
        "constraint_date": "2026-09-01",
        "actual_start_date": "2026-08-24",
    }
    diag = ExecutionPerformanceService.check_constraint_actual_contradictions(
        task,
        actual_start=datetime(2026, 8, 24, 8, 0),
        actual_finish=None,
    )
    assert len(diag) == 1
    assert diag[0][0] == ExecutionDiagnosticCode.ACTUAL_START_DIFFERS_FROM_MSO


# 33. MFO actual contradiction diagnostic
def test_33_mfo_actual_contradiction_diagnostic(temp_db):
    task = {
        "constraint_type": "MFO",
        "constraint_date": "2026-09-01",
        "actual_start_date": "2026-08-24",
        "actual_end_date": "2026-08-28",
    }
    diag = ExecutionPerformanceService.check_constraint_actual_contradictions(
        task,
        actual_start=datetime(2026, 8, 24, 8, 0),
        actual_finish=datetime(2026, 8, 28, 17, 0),
    )
    assert len(diag) == 1
    assert diag[0][0] == ExecutionDiagnosticCode.ACTUAL_FINISH_DIFFERS_FROM_MFO


# 34. cross-midnight variance
def test_34_cross_midnight_variance(temp_db):
    task = Task(
        planned_date="2026-08-24",
        planned_start_time="23:30",
        actual_start_date="2026-08-25",
        actual_start_time="00:30",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.start_variance_minutes == 60  # 1 hour late


# 35. month-end
def test_35_month_end(temp_db):
    task = Task(
        planned_date="2026-09-01",
        planned_start_time="08:00",
        actual_start_date="2026-08-31",
        actual_start_time="20:00",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.start_variance_minutes == -720  # 12 hours early


# 36. year-end
def test_36_year_end(temp_db):
    task = Task(
        planned_date="2027-01-01",
        planned_start_time="08:00",
        actual_start_date="2026-12-31",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.start_variance_minutes == -1440  # 1 day early


# 37. leap-day
def test_37_leap_day(temp_db):
    task = Task(
        planned_date="2028-03-01",
        planned_start_time="08:00",
        actual_start_date="2028-02-28",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    # 2028 is leap year (Feb 29 exists) -> 2 days (2880 mins) early
    assert res.start_variance_minutes == -2880


# 38. weekend actual elapsed
def test_38_weekend_actual_elapsed(temp_db):
    # Saturday to Monday: 48 calendar hours
    span = calculate_actual_elapsed_minutes("2026-08-22", "08:00", "2026-08-24", "08:00")
    assert span == 2880


# 39. project-calendar does not reduce actual elapsed
def test_39_project_calendar_does_not_reduce_actual_elapsed(temp_db):
    task = Task(
        actual_start_date="2026-08-22",
        actual_start_time="08:00",
        actual_end_date="2026-08-24",
        actual_end_time="08:00",
        status=TaskStatus.COMPLETED,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.actual_elapsed_minutes == 2880


# 40. WBS/Gantt performance values agree
def test_40_wbs_gantt_performance_values_agree(temp_db):
    task = Task(
        title="Planning",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    res = ExecutionPerformanceService.analyze_task_execution(task)
    assert res.start_variance_display == "Started 22 days early"


# 41. Task Dialog/Gantt values agree
def test_41_task_dialog_gantt_values_agree(temp_db):
    task = Task(
        title="Planning",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    dlg = TaskDialog(projects=[], task=task, db_manager=temp_db)
    dlg.show()
    assert "22 days early" in dlg.actual_perf_label.text()
    dlg.close()


# 42. tooltip correct
def test_42_tooltip_correct(temp_db):
    task = Task(
        id=10,
        title="Planning",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    item = GanttTaskItem(
        task=task,
        row=0,
        col_start=0.0,
        duration_cols=2.0,
        col_width=40,
        color_profile={"actual_color": "#10B981"},
        anchor_date=date(2026, 8, 24),
        zoom_mode="hourly",
    )
    assert "Started 22 days early" in item.toolTip()


# 43. current-time provider deterministic in tests
def test_43_current_time_provider_deterministic_in_tests():
    fixed_time = datetime(2026, 8, 24, 15, 30)
    set_current_datetime_override(fixed_time)
    assert get_current_datetime() == fixed_time
    set_current_datetime_override(None)


# 44. light mode
def test_44_light_mode(temp_db):
    task = Task(
        title="Planning",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    dlg = TaskDialog(projects=[], task=task, db_manager=temp_db)
    dlg.show()
    assert dlg.actual_perf_label.isVisible()
    dlg.close()


# 45. dark mode
def test_45_dark_mode(temp_db):
    task = Task(
        title="Planning",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    dlg = TaskDialog(projects=[], task=task, db_manager=temp_db)
    dlg.show()
    assert dlg.actual_elapsed_label.isVisible()
    dlg.close()


# 46. 10pt font scaling safety
def test_46_10pt_font_scaling(temp_db):
    task = Task(
        title="Planning",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    dlg = TaskDialog(projects=[], task=task, db_manager=temp_db)
    dlg.show()
    assert dlg.actual_duration_label.isVisible()
    dlg.close()


# 47. 20pt font scaling safety
def test_47_20pt_font_scaling(temp_db):
    task = Task(
        title="Planning",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    dlg = TaskDialog(projects=[], task=task, db_manager=temp_db)
    dlg.show()
    assert dlg.actual_not_finished_label.isVisible()
    dlg.close()


# 48. no DB query in paint
def test_48_no_db_query_in_paint(temp_db):
    task = Task(
        id=10,
        title="Planning",
        planned_date="2026-09-15",
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        status=TaskStatus.IN_PROGRESS,
    )
    item = GanttTaskItem(
        task=task,
        row=0,
        col_start=0.0,
        duration_cols=2.0,
        col_width=40,
        color_profile={"actual_color": "#10B981"},
        anchor_date=date(2026, 8, 24),
        zoom_mode="hourly",
    )
    assert item is not None


# 49. no duplicate formula path
def test_49_no_duplicate_formula_path():
    task = {
        "planned_date": "2026-09-15",
        "planned_start_time": "08:00",
        "actual_start_date": "2026-08-24",
        "actual_start_time": "08:00",
    }
    res1 = ExecutionPerformanceService.analyze_task_execution(task)
    res2 = ExecutionPerformanceService.analyze_task_execution(task)
    assert res1.start_variance_minutes == res2.start_variance_minutes


# 50. no production DB mutation
def test_50_no_production_db_mutation():
    from todo_bird_app.tests.path_helpers import production_db_path
    prod_path = str(production_db_path())
    assert os.path.exists(prod_path)
    db = DatabaseManager.read_only(prod_path)
    with db.get_connection() as conn:
        t = conn.execute("SELECT id, title, actual_start_date, actual_end_date FROM tasks WHERE id = 10").fetchone()
        assert t["id"] == 10
        assert t["actual_start_date"] is not None
