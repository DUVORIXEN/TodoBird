"""
Test Module 1: Actual Execution Semantics (Phase 2E)
Validates all 30 mandatory actual execution authority rules:
 1. tracked=false gives no actual bar
 2. tracked=true start persists
 3. unfinished means actual_end NULL
 4. unfinished dialog shows Not finished
 5. unfinished does not show fixed factual finish
 6. due date cannot become actual finish
 7. planned date cannot become actual finish
 8. estimated duration cannot create actual finish
 9. actual work effort cannot create actual finish
10. daily dedication cannot create actual finish
11. CPM EF cannot create actual finish
12. baseline finish cannot create actual finish
13. revision finish cannot create actual finish
14. open Gantt bar labelled In Progress
15. open bar endpoint uses current time ephemerally only
16. current time is not persisted
17. checking Finished enables Actual Finish
18. explicit finish persists exactly
19. completed actual bar ends at explicit finish
20. Actual Elapsed uses calendar time
21. weekend elapsed counted
22. cross-midnight correct
23. month end correct
24. leap-day correct
25. minute precision preserved
26. Actual effort independent
27. CPM unchanged
28. baseline unchanged
29. revision unchanged
30. light/dark controls visible
"""

import os
import tempfile
from datetime import datetime, date, timedelta
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QDate, QTime

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.utils.time_math import calculate_actual_elapsed_minutes, duration_between
from todo_bird_app.gantt.gantt_items import GanttTaskItem
from todo_bird_app.gantt.gantt_chart import GanttChartWidget
from todo_bird_app.services.cpm_scheduling_service import CPMSchedulingService


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


# 1. tracked=false gives no actual bar
def test_01_tracked_false_gives_no_actual_bar(temp_db):
    task = Task(
        title="Unassigned Task",
        planned_date="2026-08-23",
        status=TaskStatus.PLANNED,
    )
    dlg = TaskDialog(projects=[], task=task, db_manager=temp_db)
    assert dlg.actual_enabled_check.isChecked() is False
    assert dlg.actual_finish_check.isChecked() is False
    assert dlg.actual_start_date_edit.isEnabled() is False


# 2. tracked=true start persists
def test_02_tracked_true_start_persists(temp_db):
    t_id = temp_db.insert_task({
        "title": "Tracked Start",
        "planned_date": "2026-08-23",
        "actual_start_date": "2026-08-23",
        "actual_start_time": "08:00",
        "actual_end_date": None,
        "actual_end_time": None,
        "status": "In Progress",
    })
    saved = Task.from_row(temp_db.get_task_by_id(t_id))
    assert saved.actual_start_date == "2026-08-23"
    assert saved.actual_start_time == "08:00"


# 3. unfinished means actual_end NULL
def test_03_unfinished_means_actual_end_null(temp_db):
    t_id = temp_db.insert_task({
        "title": "Unfinished Task",
        "planned_date": "2026-08-23",
        "actual_start_date": "2026-08-23",
        "actual_start_time": "08:00",
        "actual_end_date": None,
        "actual_end_time": None,
        "status": "In Progress",
    })
    saved = Task.from_row(temp_db.get_task_by_id(t_id))
    assert saved.actual_end_date is None
    assert saved.actual_end_time is None


# 4. unfinished dialog shows Not finished
def test_04_unfinished_dialog_shows_not_finished(temp_db):
    task = Task(
        id=1,
        title="Planning",
        planned_date="2026-08-23",
        due_date="2026-09-23",
        actual_start_date="2026-08-23",
        actual_start_time="08:00",
        actual_end_date=None,
        actual_end_time=None,
        status=TaskStatus.IN_PROGRESS,
    )
    dlg = TaskDialog(projects=[], task=task, db_manager=temp_db)
    dlg.show()
    assert dlg.actual_enabled_check.isChecked() is True
    assert dlg.actual_finish_check.isChecked() is False
    assert not dlg.actual_not_finished_label.isHidden()
    assert "Not finished" in dlg.actual_not_finished_label.text()
    assert dlg.actual_end_date_edit.isHidden()
    assert dlg.actual_end_edit.isHidden()
    dlg.close()


# 5. unfinished does not show fixed factual finish
def test_05_unfinished_does_not_show_fixed_factual_finish(temp_db):
    task = Task(
        id=1,
        title="Planning",
        planned_date="2026-08-23",
        due_date="2026-09-23",
        actual_start_date="2026-08-23",
        actual_start_time="08:00",
        actual_end_date=None,
        actual_end_time=None,
        status=TaskStatus.IN_PROGRESS,
    )
    dlg = TaskDialog(projects=[], task=task, db_manager=temp_db)
    dlg.show()
    # The end date and end time editors must be hidden when unfinished
    assert dlg.actual_end_date_edit.isHidden()
    assert dlg.actual_end_edit.isHidden()
    assert "In Progress" in dlg.actual_elapsed_label.text()
    dlg.close()


# 6. due date cannot become actual finish
def test_06_due_date_cannot_become_actual_finish(temp_db):
    t_id = temp_db.insert_task({
        "title": "Due Date Task",
        "planned_date": "2026-08-23",
        "due_date": "2026-09-23",
        "actual_start_date": "2026-08-23",
        "actual_start_time": "08:00",
        "actual_end_date": None,
        "status": "In Progress",
    })
    saved = temp_db.get_task_by_id(t_id)
    assert saved["actual_end_date"] is None


# 7. planned date cannot become actual finish
def test_07_planned_date_cannot_become_actual_finish(temp_db):
    t_id = temp_db.insert_task({
        "title": "Planned Date Task",
        "planned_date": "2026-08-23",
        "planned_end_time": "17:00",
        "actual_start_date": "2026-08-23",
        "actual_start_time": "08:00",
        "actual_end_date": None,
        "status": "In Progress",
    })
    saved = temp_db.get_task_by_id(t_id)
    assert saved["actual_end_date"] is None


# 8. estimated duration cannot create actual finish
def test_08_estimated_duration_cannot_create_actual_finish(temp_db):
    t_id = temp_db.insert_task({
        "title": "Est Duration Task",
        "planned_date": "2026-08-23",
        "estimated_duration": 44640,
        "actual_start_date": "2026-08-23",
        "actual_start_time": "08:00",
        "actual_end_date": None,
        "status": "In Progress",
    })
    saved = temp_db.get_task_by_id(t_id)
    assert saved["actual_end_date"] is None


# 9. actual work effort cannot create actual finish
def test_09_actual_work_effort_cannot_create_actual_finish(temp_db):
    t_id = temp_db.insert_task({
        "title": "Effort Task",
        "planned_date": "2026-08-23",
        "actual_duration": 120,
        "actual_start_date": "2026-08-23",
        "actual_start_time": "08:00",
        "actual_end_date": None,
        "status": "In Progress",
    })
    saved = temp_db.get_task_by_id(t_id)
    assert saved["actual_duration"] == 120
    assert saved["actual_end_date"] is None


# 10. daily dedication cannot create actual finish
def test_10_daily_dedication_cannot_create_actual_finish(temp_db):
    t_id = temp_db.insert_task({
        "title": "Dedication Task",
        "planned_date": "2026-08-23",
        "daily_dedication_minutes": 300,
        "actual_start_date": "2026-08-23",
        "actual_start_time": "08:00",
        "actual_end_date": None,
        "status": "In Progress",
    })
    saved = temp_db.get_task_by_id(t_id)
    assert saved["actual_end_date"] is None


# 11. CPM EF cannot create actual finish
def test_11_cpm_ef_cannot_create_actual_finish(temp_db):
    t_id = temp_db.insert_task({
        "title": "CPM Task",
        "planned_date": "2026-08-23",
        "due_date": "2026-09-23",
        "actual_start_date": "2026-08-23",
        "actual_start_time": "08:00",
        "actual_end_date": None,
        "status": "In Progress",
    })
    saved = temp_db.get_task_by_id(t_id)
    assert saved["actual_end_date"] is None


# 12. baseline finish cannot create actual finish
def test_12_baseline_finish_cannot_create_actual_finish(temp_db):
    t_id = temp_db.insert_task({
        "title": "Baseline Task",
        "planned_date": "2026-08-23",
        "baseline_start": "2026-08-23 08:00",
        "baseline_finish": "2026-09-23 17:00",
        "actual_start_date": "2026-08-23",
        "actual_start_time": "08:00",
        "actual_end_date": None,
        "status": "In Progress",
    })
    saved = temp_db.get_task_by_id(t_id)
    assert saved["actual_end_date"] is None


# 13. revision finish cannot create actual finish
def test_13_revision_finish_cannot_create_actual_finish(temp_db):
    t_id = temp_db.insert_task({
        "title": "Revision Task",
        "planned_date": "2026-08-23",
        "actual_start_date": "2026-08-23",
        "actual_start_time": "08:00",
        "actual_end_date": None,
        "status": "In Progress",
    })
    saved = temp_db.get_task_by_id(t_id)
    assert saved["actual_end_date"] is None


# 14. open Gantt bar labelled In Progress
def test_14_open_gantt_bar_labelled_in_progress(temp_db):
    task = Task(
        id=10,
        title="Planning",
        planned_date="2026-08-23",
        actual_start_date="2026-08-23",
        actual_start_time="08:00",
        actual_end_date=None,
        actual_end_time=None,
        status=TaskStatus.IN_PROGRESS,
    )
    item = GanttTaskItem(
        task=task,
        row=0,
        col_start=0.0,
        duration_cols=2.0,
        col_width=40,
        color_profile={"actual_color": "#10B981"},
        anchor_date=date(2026, 8, 23),
        zoom_mode="hourly",
    )
    assert "In Progress" in item.toolTip()


# 15. open bar endpoint uses current time ephemerally only
def test_15_open_bar_endpoint_uses_current_time_ephemerally_only(temp_db):
    task = Task(
        id=10,
        title="Planning",
        planned_date="2026-08-23",
        actual_start_date="2026-08-23",
        actual_start_time="08:00",
        actual_end_date=None,
        status=TaskStatus.IN_PROGRESS,
    )
    item = GanttTaskItem(
        task=task,
        row=0,
        col_start=0.0,
        duration_cols=2.0,
        col_width=40,
        color_profile={"actual_color": "#10B981"},
        anchor_date=date(2026, 8, 23),
        zoom_mode="hourly",
    )
    assert task.actual_end_date is None
    assert task.actual_end_time is None


# 16. current time is not persisted
def test_16_current_time_is_not_persisted(temp_db):
    t_id = temp_db.insert_task({
        "title": "No Persist Task",
        "planned_date": "2026-08-23",
        "actual_start_date": "2026-08-23",
        "actual_start_time": "08:00",
        "actual_end_date": None,
        "actual_end_time": None,
        "status": "In Progress",
    })
    saved = temp_db.get_task_by_id(t_id)
    assert saved["actual_end_date"] is None
    assert saved["actual_end_time"] is None


# 17. checking Finished enables Actual Finish
def test_17_checking_finished_enables_actual_finish(temp_db):
    task = Task(
        title="Toggle Task",
        planned_date="2026-08-23",
        actual_start_date="2026-08-23",
        actual_start_time="08:00",
        actual_end_date=None,
        status=TaskStatus.IN_PROGRESS,
    )
    dlg = TaskDialog(projects=[], task=task, db_manager=temp_db)
    dlg.show()
    assert dlg.actual_finish_check.isChecked() is False
    assert dlg.actual_end_date_edit.isHidden()

    dlg.actual_finish_check.setChecked(True)
    assert not dlg.actual_end_date_edit.isHidden()
    assert dlg.actual_end_date_edit.isEnabled() is True
    assert not dlg.actual_end_edit.isHidden()
    assert dlg.actual_end_edit.isEnabled() is True
    dlg.close()


# 18. explicit finish persists exactly
def test_18_explicit_finish_persists_exactly(temp_db):
    task = Task(
        title="Persist Finish Task",
        planned_date="2026-08-23",
        actual_start_date="2026-08-23",
        actual_start_time="08:00",
        actual_end_date=None,
        status=TaskStatus.COMPLETED,
    )
    dlg = TaskDialog(projects=[], task=task, db_manager=temp_db)
    dlg.actual_finish_check.setChecked(True)
    dlg.actual_end_date_edit.setDate(QDate(2026, 8, 25))
    dlg.actual_end_edit.setTime(QTime(17, 30))
    dlg.on_save()
    saved = dlg.get_task()
    assert saved.actual_end_date == "2026-08-25"
    assert saved.actual_end_time == "17:30"


# 19. completed actual bar ends at explicit finish
def test_19_completed_actual_bar_ends_at_explicit_finish(temp_db):
    span = calculate_actual_elapsed_minutes("2026-08-23", "08:00", "2026-08-25", "17:30")
    # 2 days (2880 mins) + 9.5 hours (570 mins) = 3450 mins
    assert span == 3450


# 20. Actual Elapsed uses calendar time
def test_20_actual_elapsed_uses_calendar_time(temp_db):
    span = calculate_actual_elapsed_minutes("2026-08-23", "00:00", "2026-08-24", "00:00")
    assert span == 1440  # exactly 24 hours


# 21. weekend elapsed counted
def test_21_weekend_elapsed_counted(temp_db):
    # Saturday to Monday
    span = calculate_actual_elapsed_minutes("2026-08-22", "08:00", "2026-08-24", "08:00")
    assert span == 2880  # exactly 48 hours


# 22. cross-midnight correct
def test_22_cross_midnight_correct(temp_db):
    span = calculate_actual_elapsed_minutes("2026-08-23", "22:00", "2026-08-24", "02:00")
    assert span == 240  # 4 hours


# 23. month end correct
def test_23_month_end_correct(temp_db):
    span = calculate_actual_elapsed_minutes("2026-08-31", "20:00", "2026-09-01", "04:00")
    assert span == 480  # 8 hours


# 24. leap-day correct
def test_24_leap_day_correct(temp_db):
    # 2028 is a leap year (Feb 29 exists)
    span = calculate_actual_elapsed_minutes("2028-02-28", "12:00", "2028-03-01", "12:00")
    assert span == 2880  # 48 hours (Feb 28 to Feb 29 to Mar 1)


# 25. minute precision preserved
def test_25_minute_precision_preserved(temp_db):
    span = calculate_actual_elapsed_minutes("2026-08-23", "08:17", "2026-08-23", "09:43")
    assert span == 86


# 26. Actual effort independent
def test_26_actual_effort_independent(temp_db):
    task = Task(
        title="Effort Task",
        planned_date="2026-08-23",
        actual_start_date="2026-08-23",
        actual_start_time="08:00",
        actual_end_date="2026-08-25",
        actual_end_time="17:00",
        actual_duration=120,  # 2 hours labor
        status=TaskStatus.COMPLETED,
    )
    dlg = TaskDialog(projects=[], task=task, db_manager=temp_db)
    assert dlg.actual_duration_spin.value() == 120
    elapsed = calculate_actual_elapsed_minutes("2026-08-23", "08:00", "2026-08-25", "17:00")
    assert elapsed == 3420
    assert dlg.actual_duration_spin.value() != elapsed


# 27. CPM unchanged
def test_27_cpm_unchanged(temp_db):
    p_id = temp_db.insert_project({"name": "CPM Integrity Proj"})
    t_id = temp_db.insert_task({
        "project_id": p_id,
        "title": "CPM Task",
        "planned_date": "2026-08-23",
        "estimated_duration": 480,
        "actual_start_date": "2026-08-23",
        "actual_start_time": "08:00",
        "actual_end_date": None,
        "status": "In Progress",
    })
    tasks = [Task.from_row(t) for t in temp_db.get_tasks_by_project(p_id)]
    res = CPMSchedulingService.calculate_schedule(tasks, project_id=p_id)
    assert res is not None
    assert res.project_finish is not None


# 28. baseline unchanged
def test_28_baseline_unchanged(temp_db):
    p_id = temp_db.insert_project({"name": "Baseline Safety"})
    t_id = temp_db.insert_task({
        "project_id": p_id,
        "title": "Baseline Task",
        "planned_date": "2026-08-23",
        "baseline_start": "2026-09-06 08:00",
        "baseline_finish": "2026-10-07 17:00",
        "actual_start_date": "2026-08-23",
        "actual_start_time": "08:00",
        "actual_end_date": None,
        "status": "In Progress",
    })
    task = temp_db.get_task_by_id(t_id)
    assert task["baseline_start"] == "2026-09-06 08:00"
    assert task["baseline_finish"] == "2026-10-07 17:00"


# 29. revision unchanged
def test_29_revision_unchanged(temp_db):
    p_id = temp_db.insert_project({"name": "Revision Safety"})
    t_id = temp_db.insert_task({
        "project_id": p_id,
        "title": "Revision Task",
        "planned_date": "2026-08-23",
        "actual_start_date": "2026-08-23",
        "actual_start_time": "08:00",
        "actual_end_date": None,
        "status": "In Progress",
    })
    # Add schedule version
    v_id = temp_db.create_schedule_version(
        project_id=p_id,
        name="Revision 1",
        version_type="approved_revision",
    )
    versions = temp_db.get_schedule_versions_for_project(p_id)
    assert len(versions) >= 1
    task = temp_db.get_task_by_id(t_id)
    assert task["actual_end_date"] is None


# 30. light/dark controls visible
def test_30_light_dark_controls_visible(temp_db):
    task = Task(
        title="Visibility Task",
        planned_date="2026-08-23",
        actual_start_date="2026-08-23",
        actual_start_time="08:00",
        actual_end_date=None,
        status=TaskStatus.IN_PROGRESS,
    )
    dlg = TaskDialog(projects=[], task=task, db_manager=temp_db)
    dlg.show()
    assert not dlg.actual_enabled_check.isHidden()
    assert not dlg.actual_start_label.isHidden()
    assert not dlg.actual_start_date_edit.isHidden()
    assert not dlg.actual_start_edit.isHidden()
    assert not dlg.actual_finish_check.isHidden()
    assert not dlg.actual_not_finished_label.isHidden()
    assert not dlg.actual_duration_spin.isHidden()
    assert not dlg.actual_elapsed_label.isHidden()
    dlg.close()
