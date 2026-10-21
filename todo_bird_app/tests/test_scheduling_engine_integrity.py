from __future__ import annotations

import time
from datetime import datetime

import pytest

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task
from todo_bird_app.services.cpm_scheduling_service import (
    CPMSchedulingService,
    DependencyType,
    DiagnosticCode,
)
from todo_bird_app.services.execution_performance_service import (
    ExecutionPerformanceService,
    ExecutionState,
)
from todo_bird_app.services.schedule_constraint_service import (
    ProjectCalendarSpec,
    ScheduleConstraintService,
)
from todo_bird_app.services.schedule_version_service import ScheduleVersionService


MON_FRI = ProjectCalendarSpec(project_id=1, working_weekdays=(0, 1, 2, 3, 4))


def dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def task(
    task_id: int,
    *,
    day: str = "2026-09-07",
    clock: str = "09:00",
    duration: int = 60,
    deps=None,
    **extra,
) -> Task:
    return Task(
        id=task_id,
        title=f"Task {task_id}",
        project_id=extra.pop("project_id", 1),
        planned_date=day,
        planned_start_time=clock,
        estimated_duration=duration,
        dependencies=list(deps or []),
        **extra,
    )


def dep(pred: int, dtype: DependencyType = DependencyType.FS, lag: int = 0) -> dict:
    return {
        "predecessor_id": pred,
        "type": dtype.value,
        "lag_minutes": lag,
    }


@pytest.fixture
def temp_db(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "scheduling_integrity.db"))
    yield db
    db.close()


def test_negative_free_float_value_is_not_silently_clamped():
    predecessor = task(1, duration=60, constraint_type="ALAP")
    successor = task(2, day="2026-09-07", clock="09:00", duration=60, deps=[dep(1)])
    independent_tail = task(3, day="2026-09-07", clock="16:00", duration=60)

    result = CPMSchedulingService.calculate_schedule(
        [predecessor, successor, independent_tail],
        project_calendar=MON_FRI,
    )

    n1 = result.nodes[1]
    n2 = result.nodes[2]
    assert n1.earliest_start == dt("2026-09-07 15:00")
    assert n1.earliest_finish == dt("2026-09-07 16:00")
    assert n2.earliest_start == dt("2026-09-07 10:00")
    assert n1.total_float_minutes == 0
    assert n1.is_critical is True
    assert n1.free_float_minutes == -360
    assert DiagnosticCode.NEGATIVE_FLOAT in n1.diagnostic_codes


def test_snapshot_from_cpm_object_uses_estimated_duration_not_calendar_wall_span():
    source_task = task(
        1,
        day="2026-09-11",
        clock="09:00",
        duration=1440,
        planned_effort_minutes=480,
    )
    cpm_node = CPMSchedulingService.calculate_schedule(
        [source_task],
        project_calendar=MON_FRI,
    ).nodes[1]

    item = ScheduleVersionService._snapshot_from_record(
        source_task.to_dict(),
        entity_type="task",
        entity_id=1,
        task_id=1,
        parent_subtask_id=None,
        wbs_path="task:1",
        cpm_node=cpm_node,
    )

    assert item["start"] == "2026-09-11 09:00"
    assert item["finish"] == "2026-09-11 09:00"
    assert item["duration_minutes"] == 1440
    assert item["planned_effort_minutes"] == 480


def test_version_snapshot_internal_cpm_uses_project_calendar_from_database(temp_db):
    project_id = temp_db.insert_project({"name": "Calendar Snapshot"})
    temp_db.set_project_calendar(project_id, working_weekdays=[0, 1, 2, 3, 4])
    task_id = temp_db.insert_task(
        {
            "project_id": project_id,
            "title": "Calendar Task",
            "planned_date": "2026-09-11",
            "planned_start_time": "09:00",
            "estimated_duration": 1440,
            "planned_effort_minutes": 480,
        }
    )

    version_id = ScheduleVersionService.create_approved_revision(
        temp_db,
        project_id,
        name="Calendar Revision",
        approved_at="2026-09-12T08:00:00",
    )
    items = {
        (item["entity_type"], item["entity_id"]): item
        for item in temp_db.get_schedule_version_items(version_id)
    }

    item = items[("task", task_id)]
    assert item["start"] == "2026-09-11 09:00"
    assert item["finish"] == "2026-09-11 09:00"
    assert item["duration_minutes"] == 1440
    assert item["planned_effort_minutes"] == 480


def test_early_actual_start_does_not_rewrite_current_forecast():
    planned = task(
        1,
        day="2026-09-07",
        clock="09:00",
        duration=120,
        actual_start_date="2026-09-01",
        actual_start_time="06:00",
    )

    result = CPMSchedulingService.calculate_schedule([planned], project_calendar=MON_FRI)

    assert result.nodes[1].earliest_start == dt("2026-09-07 09:00")
    assert result.nodes[1].earliest_finish == dt("2026-09-07 11:00")


def test_actual_elapsed_is_full_calendar_time_and_effort_remains_separate():
    executed = task(
        1,
        actual_start_date="2026-09-11",
        actual_start_time="12:00",
        actual_end_date="2026-09-14",
        actual_end_time="12:00",
        actual_duration=90,
    )

    result = ExecutionPerformanceService.analyze_task_execution(executed)

    assert result.execution_state == ExecutionState.FINISHED
    assert result.actual_elapsed_minutes == 4320
    assert result.actual_work_effort_minutes == 90


def test_open_actual_uses_now_for_analysis_without_persisted_finish():
    open_task = task(
        1,
        actual_start_date="2026-09-11",
        actual_start_time="12:00",
        actual_end_date=None,
        actual_end_time=None,
        actual_duration=120,
    )

    result = ExecutionPerformanceService.analyze_task_execution(
        open_task,
        now=dt("2026-09-14 12:00"),
    )

    assert result.execution_state == ExecutionState.IN_PROGRESS
    assert result.actual_finish is None
    assert result.finish_variance_minutes is None
    assert result.actual_elapsed_minutes == 4320
    assert open_task.actual_end_date is None
    assert open_task.actual_end_time is None


def test_deadline_authority_is_safe_or_missed_without_risk_window():
    deadline_task = task(1, deadline_datetime="2026-09-07 10:00")

    safe = ScheduleConstraintService.evaluate_task_deadline(
        deadline_task,
        cpm_finish=dt("2026-09-07 10:00"),
        total_float_minutes=0,
    )
    missed = ScheduleConstraintService.evaluate_task_deadline(
        deadline_task,
        cpm_finish=dt("2026-09-07 10:01"),
        total_float_minutes=999,
    )

    assert safe.variance_minutes == 0
    assert safe.is_missed is False
    assert safe.is_at_risk is False
    assert missed.variance_minutes == 1
    assert missed.is_missed is True
    assert missed.is_at_risk is False


def test_5000_node_chain_cpm_is_iterative_and_complete():
    tasks = [
        task(i, day="2026-09-07", clock="00:00", duration=1, deps=[dep(i - 1)] if i > 1 else [])
        for i in range(1, 5001)
    ]

    started = time.perf_counter()
    result = CPMSchedulingService.calculate_schedule(tasks)
    elapsed = time.perf_counter() - started

    assert elapsed < 10.0
    assert result.total_tasks == 5000
    assert result.schedulable_tasks == 5000
    assert result.has_cycles is False
    assert result.nodes[1].is_critical is True
    assert result.nodes[5000].is_critical is True
    assert result.nodes[5000].earliest_finish == dt("2026-09-10 11:20")
