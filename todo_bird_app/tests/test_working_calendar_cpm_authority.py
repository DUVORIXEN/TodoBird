"""
Phase 2E S1 blocker 4 oracle tests: working-calendar CPM authority.

These tests intentionally avoid Qt widgets. They exercise the pure calendar
arithmetic service, CPM forward/backward equations, temp DB schedule-version
immutability, and read-only production witness behavior.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

import pytest

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task
from todo_bird_app.services.cpm_scheduling_service import (
    CPMSchedulingService,
    DependencyType,
    DiagnosticCode,
)
from todo_bird_app.services.schedule_calendar_service import (
    add_working_minutes,
    subtract_working_minutes,
    working_minutes_between,
)
from todo_bird_app.services.schedule_constraint_service import (
    CalendarException,
    ProjectCalendarSpec,
)
from todo_bird_app.services.schedule_version_service import ScheduleVersionService


APP_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DB = APP_ROOT / "data" / "todo_bird.db"
MON_FRI = ProjectCalendarSpec(project_id=1, working_weekdays=(0, 1, 2, 3, 4))
MON_SAT = ProjectCalendarSpec(project_id=1, working_weekdays=(0, 1, 2, 3, 4, 5))
SEVEN_DAY = ProjectCalendarSpec(project_id=1, working_weekdays=(0, 1, 2, 3, 4, 5, 6))
HOLIDAY_TUE = ProjectCalendarSpec(
    project_id=1,
    working_weekdays=(0, 1, 2, 3, 4),
    exceptions=(CalendarException("2026-09-15", False, "Holiday Tuesday"),),
)
SUNDAY_OVERRIDE = ProjectCalendarSpec(
    project_id=1,
    working_weekdays=(0, 1, 2, 3, 4),
    exceptions=(CalendarException("2026-09-13", True, "Sunday work"),),
)


def dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def make_task(
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
        planned_date=day,
        planned_start_time=clock,
        estimated_duration=duration,
        dependencies=list(deps or []),
        **extra,
    )


def dep(pred: int, dtype: DependencyType | str = DependencyType.FS, lag: int = 0) -> dict:
    return {
        "predecessor_id": pred,
        "type": dtype.value if isinstance(dtype, DependencyType) else str(dtype),
        "lag_minutes": lag,
    }


def schedule(tasks, calendar=MON_FRI):
    return CPMSchedulingService.calculate_schedule(tasks, project_calendar=calendar)


def node(result, task_id: int):
    n = result.nodes[task_id]
    assert n.schedulable is True
    return n


def version_items_hash(db: DatabaseManager, version_id: int) -> str:
    rows = sorted(
        db.get_schedule_version_items(version_id),
        key=lambda row: (
            str(row.get("entity_type")),
            int(row.get("entity_id") or 0),
            str(row.get("wbs_path") or ""),
        ),
    )
    payload = json.dumps(rows, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize(
    ("calendar", "start", "minutes", "expected"),
    [
        (None, "2026-09-12 09:00", 60, "2026-09-12 10:00"),
        (MON_FRI, "2026-09-07 09:00", 1, "2026-09-07 09:01"),
        (MON_FRI, "2026-09-07 09:00", 59, "2026-09-07 09:59"),
        (MON_FRI, "2026-09-07 09:00", 60, "2026-09-07 10:00"),
        (MON_FRI, "2026-09-07 09:00", 61, "2026-09-07 10:01"),
        (MON_FRI, "2026-09-07 23:30", 60, "2026-09-08 00:30"),
        (MON_FRI, "2026-09-11 23:00", 120, "2026-09-14 01:00"),
        (MON_FRI, "2026-09-11 09:00", 1440, "2026-09-14 09:00"),
        (MON_FRI, "2026-09-07 09:00", 1440, "2026-09-08 09:00"),
        (MON_SAT, "2026-09-12 09:00", 60, "2026-09-12 10:00"),
        (SEVEN_DAY, "2026-09-13 09:00", 60, "2026-09-13 10:00"),
        (HOLIDAY_TUE, "2026-09-14 23:00", 120, "2026-09-16 01:00"),
        (SUNDAY_OVERRIDE, "2026-09-13 10:00", 60, "2026-09-13 11:00"),
        (ProjectCalendarSpec(working_weekdays=(0, 1, 2, 3)), "2026-09-10 23:00", 120, "2026-09-14 01:00"),
        (MON_FRI, "2026-12-31 23:00", 120, "2027-01-01 01:00"),
        (MON_FRI, "2026-01-30 23:00", 120, "2026-02-02 01:00"),
        (MON_FRI, "2028-02-28 23:00", 120, "2028-02-29 01:00"),
        (MON_FRI, "2100-02-26 23:00", 120, "2100-03-01 01:00"),
    ],
)
def test_01_add_working_minutes_matrix(calendar, start, minutes, expected):
    assert add_working_minutes(dt(start), minutes, calendar) == dt(expected)


@pytest.mark.parametrize(
    ("calendar", "finish", "minutes", "expected"),
    [
        (None, "2026-09-12 10:00", 60, "2026-09-12 09:00"),
        (MON_FRI, "2026-09-07 10:00", 60, "2026-09-07 09:00"),
        (MON_FRI, "2026-09-14 00:30", 60, "2026-09-11 23:30"),
        (HOLIDAY_TUE, "2026-09-16 01:00", 120, "2026-09-14 23:00"),
        (MON_FRI, "2026-09-14 09:00", 1440, "2026-09-11 09:00"),
        (SUNDAY_OVERRIDE, "2026-09-13 11:00", 60, "2026-09-13 10:00"),
        (MON_FRI, "2026-09-08 09:00", 1440, "2026-09-07 09:00"),
        (MON_FRI, "2026-09-14 00:00", 1, "2026-09-11 23:59"),
    ],
)
def test_02_subtract_working_minutes_matrix(calendar, finish, minutes, expected):
    assert subtract_working_minutes(dt(finish), minutes, calendar) == dt(expected)


@pytest.mark.parametrize(
    ("calendar", "start", "finish", "expected"),
    [
        (None, "2026-09-11 23:00", "2026-09-14 01:00", 3000),
        (MON_FRI, "2026-09-11 23:00", "2026-09-14 01:00", 120),
        (MON_FRI, "2026-09-07 09:00", "2026-09-07 10:00", 60),
        (HOLIDAY_TUE, "2026-09-14 23:00", "2026-09-16 01:00", 120),
        (HOLIDAY_TUE, "2026-09-16 01:00", "2026-09-14 23:00", -120),
        (MON_FRI, "2026-09-12 00:00", "2026-09-13 23:00", 0),
    ],
)
def test_03_working_minutes_between_matrix(calendar, start, finish, expected):
    assert working_minutes_between(dt(start), dt(finish), calendar) == expected


def test_04_project_calendar_weekday_and_duplicate_exception_precedence():
    assert MON_FRI.is_working_day("2026-09-07") is True
    assert MON_FRI.is_working_day("2026-09-12") is False
    assert MON_SAT.is_working_day("2026-09-12") is True
    holiday_then_work = ProjectCalendarSpec(
        exceptions=(
            CalendarException("2026-09-12", False, "holiday"),
            CalendarException("2026-09-12", True, "override"),
        )
    )
    work_then_holiday = ProjectCalendarSpec(
        exceptions=(
            CalendarException("2026-09-12", True, "override"),
            CalendarException("2026-09-12", False, "holiday"),
        )
    )
    assert holiday_then_work.is_working_day("2026-09-12") is True
    assert work_then_holiday.is_working_day("2026-09-12") is False


def test_05_root_start_on_nonworking_date_is_normalized_and_diagnosed():
    result = schedule([make_task(1, day="2026-09-12", clock="09:00", duration=60)])
    n = node(result, 1)
    assert n.earliest_start == dt("2026-09-14 09:00")
    assert n.earliest_finish == dt("2026-09-14 10:00")
    assert DiagnosticCode.CALENDAR_CONFLICT in n.diagnostic_codes


def test_06_milestone_zero_duration_has_no_plus_one_day():
    milestone = make_task(1, day="2026-09-12", clock="09:00", duration=0)
    result = schedule([milestone])
    n = node(result, 1)
    assert n.earliest_start == dt("2026-09-14 09:00")
    assert n.earliest_finish == dt("2026-09-14 09:00")
    assert n.latest_start == n.latest_finish


def test_07_one_day_task_duration_preserves_same_working_date_endpoint():
    result = schedule([make_task(1, day="2026-09-07", clock="09:00", duration=1440)])
    n = node(result, 1)
    assert n.earliest_start == dt("2026-09-07 09:00")
    assert n.earliest_finish == dt("2026-09-07 09:00")


def test_08_two_day_task_duration_skips_weekend_without_starting_successor_there():
    t1 = make_task(1, day="2026-09-11", clock="00:00", duration=2880)
    t2 = make_task(2, day="2026-09-11", clock="00:00", duration=60, deps=[dep(1)])
    result = schedule([t1, t2])
    assert node(result, 1).earliest_finish == dt("2026-09-14 00:00")
    assert node(result, 2).earliest_start == dt("2026-09-14 00:00")


@pytest.mark.parametrize(
    ("dtype", "lag", "expected_start", "expected_finish"),
    [
        (DependencyType.FS, 0, "2026-09-07 11:00", "2026-09-07 12:00"),
        (DependencyType.FS, 60, "2026-09-07 12:00", "2026-09-07 13:00"),
        (DependencyType.FS, -30, "2026-09-07 10:30", "2026-09-07 11:30"),
        (DependencyType.FS, 1440, "2026-09-08 11:00", "2026-09-08 12:00"),
        (DependencyType.SS, 0, "2026-09-07 09:00", "2026-09-07 10:00"),
        (DependencyType.SS, 60, "2026-09-07 10:00", "2026-09-07 11:00"),
        (DependencyType.SS, -30, "2026-09-07 08:30", "2026-09-07 09:30"),
        (DependencyType.SS, 1440, "2026-09-08 09:00", "2026-09-08 10:00"),
        (DependencyType.FF, 0, "2026-09-07 10:00", "2026-09-07 11:00"),
        (DependencyType.FF, 60, "2026-09-07 11:00", "2026-09-07 12:00"),
        (DependencyType.FF, -30, "2026-09-07 09:30", "2026-09-07 10:30"),
        (DependencyType.FF, 1440, "2026-09-08 10:00", "2026-09-08 11:00"),
        (DependencyType.SF, 0, "2026-09-07 08:00", "2026-09-07 09:00"),
        (DependencyType.SF, 60, "2026-09-07 09:00", "2026-09-07 10:00"),
        (DependencyType.SF, -30, "2026-09-07 07:30", "2026-09-07 08:30"),
        (DependencyType.SF, 1440, "2026-09-08 08:00", "2026-09-08 09:00"),
    ],
)
def test_09_dependency_equations_obey_calendar(dtype, lag, expected_start, expected_finish):
    pred = make_task(1, day="2026-09-07", clock="09:00", duration=120)
    succ = make_task(2, day="2026-09-07", clock="00:00", duration=60, deps=[dep(1, dtype, lag)])
    result = schedule([pred, succ])
    n = node(result, 2)
    assert n.earliest_start == dt(expected_start)
    assert n.earliest_finish == dt(expected_finish)


@pytest.mark.parametrize(
    ("dtype", "lag", "expected_ls", "expected_lf"),
    [
        (DependencyType.FS, 60, "2026-09-07 09:00", "2026-09-07 11:00"),
        (DependencyType.SS, 60, "2026-09-07 09:00", "2026-09-07 11:00"),
        (DependencyType.FF, 60, "2026-09-07 09:00", "2026-09-07 11:00"),
        (DependencyType.SF, 60, "2026-09-07 10:00", "2026-09-07 12:00"),
    ],
)
def test_10_backward_dependency_equations_obey_calendar(dtype, lag, expected_ls, expected_lf):
    pred = make_task(1, day="2026-09-07", clock="09:00", duration=120)
    succ = make_task(2, day="2026-09-07", clock="00:00", duration=60, deps=[dep(1, dtype, lag)])
    result = schedule([pred, succ])
    n = node(result, 1)
    assert n.latest_start == dt(expected_ls)
    assert n.latest_finish == dt(expected_lf)


def test_11_backward_pass_skips_weekend_when_successor_starts_monday():
    pred = make_task(1, day="2026-09-11", clock="23:00", duration=60)
    succ = make_task(2, day="2026-09-14", clock="00:00", duration=60, deps=[dep(1)])
    result = schedule([pred, succ])
    n = node(result, 1)
    assert n.latest_start == dt("2026-09-11 23:00")
    assert n.total_float_minutes == 0


@pytest.mark.parametrize(
    ("task", "expected_es", "expected_ef"),
    [
        (make_task(1, constraint_type="ASAP"), "2026-09-07 09:00", "2026-09-07 10:00"),
        (make_task(1, constraint_type="SNET", constraint_datetime="2026-09-12 09:00"), "2026-09-14 09:00", "2026-09-14 10:00"),
        (make_task(1, constraint_type="FNET", constraint_datetime="2026-09-12 09:00"), "2026-09-14 08:00", "2026-09-14 09:00"),
        (make_task(1, constraint_type="MSO", constraint_datetime="2026-09-07 13:00"), "2026-09-07 13:00", "2026-09-07 14:00"),
        (make_task(1, duration=120, constraint_type="MFO", constraint_datetime="2026-09-07 15:00"), "2026-09-07 13:00", "2026-09-07 15:00"),
    ],
)
def test_12_forward_constraints_obey_calendar(task, expected_es, expected_ef):
    result = schedule([task])
    n = node(result, 1)
    assert n.earliest_start == dt(expected_es)
    assert n.earliest_finish == dt(expected_ef)


def test_13_snlt_restricts_latest_start_with_calendar():
    constrained = make_task(1, constraint_type="SNLT", constraint_datetime="2026-09-07 10:00")
    tail = make_task(2, duration=300)
    result = schedule([constrained, tail])
    assert node(result, 1).latest_start <= dt("2026-09-07 10:00")


def test_14_fnlt_restricts_latest_finish_without_reversing_meaning():
    task = make_task(1, duration=120, constraint_type="FNLT", constraint_datetime="2026-09-07 11:00")
    result = schedule([task])
    assert node(result, 1).latest_finish <= dt("2026-09-07 11:00")


def test_15_fnlt_cross_weekend_creates_negative_float_when_finish_is_too_late():
    task = make_task(
        1,
        day="2026-09-11",
        clock="23:00",
        duration=120,
        constraint_type="FNLT",
        constraint_datetime="2026-09-14 00:00",
    )
    result = schedule([task])
    n = node(result, 1)
    assert n.earliest_finish == dt("2026-09-14 01:00")
    assert n.latest_finish <= dt("2026-09-14 00:00")
    assert n.total_float_minutes < 0
    assert n.is_critical is False


def test_16_deadline_monitoring_does_not_move_calendar_schedule():
    plain = make_task(1)
    deadlined = make_task(2, deadline_datetime="2026-09-07 08:00")
    r1 = schedule([plain])
    r2 = schedule([deadlined])
    assert node(r1, 1).earliest_start == node(r2, 2).earliest_start
    assert node(r1, 1).earliest_finish == node(r2, 2).earliest_finish
    assert DiagnosticCode.DEADLINE_MISSED in node(r2, 2).diagnostic_codes


def test_17_alap_shifts_to_latest_calendar_start():
    alap = make_task(1, day="2026-09-11", clock="09:00", duration=60, constraint_type="ALAP")
    tail = make_task(2, day="2026-09-11", clock="23:00", duration=120)
    result = schedule([alap, tail])
    assert node(result, 1).earliest_start == dt("2026-09-14 00:00")
    assert node(result, 1).earliest_finish == dt("2026-09-14 01:00")


def test_18_multiple_predecessor_forward_pass_uses_max_calendar_bound():
    a = make_task(1, day="2026-09-11", clock="23:00", duration=120)
    b = make_task(2, day="2026-09-14", clock="00:00", duration=60)
    c = make_task(3, day="2026-09-07", clock="00:00", duration=60, deps=[dep(1, lag=60), dep(2)])
    result = schedule([a, b, c])
    assert node(result, 3).earliest_start == dt("2026-09-14 02:00")


def test_19_multiple_critical_paths_are_preserved():
    a = make_task(1, duration=60)
    b = make_task(2, duration=60)
    c = make_task(3, day="2026-09-07", clock="00:00", duration=60, deps=[dep(1), dep(2)])
    result = schedule([a, b, c])
    assert result.critical_task_ids == (1, 2, 3)
    assert set(result.critical_paths) == {(1, 3), (2, 3)}


def test_20_positive_total_and_free_float_are_working_minutes():
    short = make_task(1, duration=60)
    long_tail = make_task(2, duration=180)
    result = schedule([short, long_tail])
    n = node(result, 1)
    assert n.total_float_minutes == 120
    assert n.free_float_minutes == 120
    assert n.is_critical is False


def test_21_negative_float_is_not_classified_as_normal_critical_path():
    pred = make_task(1, duration=180)
    succ = make_task(2, duration=60, deps=[dep(1)], constraint_type="SNLT", constraint_datetime="2026-09-07 10:00")
    result = schedule([pred, succ])
    assert node(result, 1).total_float_minutes < 0
    assert node(result, 2).total_float_minutes < 0
    assert node(result, 1).is_critical is False
    assert node(result, 2).is_critical is False


def test_22_cycle_detection_remains_non_destructive():
    a = make_task(1, deps=[dep(2)])
    b = make_task(2, deps=[dep(1)])
    result = schedule([a, b])
    assert result.has_cycles is True
    assert result.cycle_task_ids == (1, 2)
    assert result.schedulable_tasks == 0


def test_23_disconnected_networks_share_project_finish_float_authority():
    a = make_task(1, duration=60)
    b = make_task(2, duration=60, deps=[dep(1)])
    c = make_task(3, duration=240)
    result = schedule([a, b, c])
    assert node(result, 1).is_critical is False
    assert node(result, 2).is_critical is False
    assert node(result, 3).is_critical is True
    assert result.project_finish == dt("2026-09-07 13:00")


def test_24_total_float_start_and_finish_forms_are_equivalent():
    a = make_task(1, duration=180)
    b = make_task(2, duration=60)
    c = make_task(3, day="2026-09-07", clock="00:00", duration=60, deps=[dep(1), dep(2)])
    result = schedule([a, b, c])
    for task_id in (1, 2, 3):
        n = node(result, task_id)
        start_form = working_minutes_between(n.earliest_start, n.latest_start, MON_FRI)
        finish_form = working_minutes_between(n.earliest_finish, n.latest_finish, MON_FRI)
        assert n.total_float_minutes == start_form
        assert n.total_float_minutes == finish_form


def test_25_no_calendar_path_preserves_raw_elapsed_legacy_behavior():
    pred = make_task(1, day="2026-09-11", clock="23:00", duration=120)
    succ = make_task(2, day="2026-09-11", clock="00:00", duration=60, deps=[dep(1)])
    result = CPMSchedulingService.calculate_schedule([pred, succ])
    assert node(result, 1).earliest_finish == dt("2026-09-12 01:00")
    assert node(result, 2).earliest_start == dt("2026-09-12 01:00")


def test_26_project_calendar_isolation_for_same_planned_sunday():
    task = make_task(1, day="2026-09-13", clock="09:00", duration=60)
    mon_fri_result = schedule([task], MON_FRI)
    seven_day_result = schedule([task], SEVEN_DAY)
    assert node(mon_fri_result, 1).earliest_start == dt("2026-09-14 09:00")
    assert node(seven_day_result, 1).earliest_start == dt("2026-09-13 09:00")


def test_27_date_only_planned_start_is_midnight_authority():
    task = Task(id=1, title="Date only", planned_date="2026-09-07", estimated_duration=60)
    result = schedule([task])
    assert node(result, 1).earliest_start == dt("2026-09-07 00:00")


def test_28_datetime_start_time_is_preserved():
    task = make_task(1, day="2026-09-07", clock="12:34", duration=61)
    result = schedule([task])
    assert node(result, 1).earliest_start == dt("2026-09-07 12:34")
    assert node(result, 1).earliest_finish == dt("2026-09-07 13:35")


def test_29_working_minute_round_trip_has_no_rounding_drift():
    start = dt("2026-09-11 23:59")
    finish = add_working_minutes(start, 61, MON_FRI)
    assert finish == dt("2026-09-14 01:00")
    assert working_minutes_between(start, finish, MON_FRI) == 61
    assert subtract_working_minutes(finish, 61, MON_FRI) == start


def test_30_actual_execution_elapsed_remains_full_calendar_time():
    task = Task(
        id=1,
        title="Actual",
        actual_start_date="2026-09-11",
        actual_start_time="12:00",
        actual_end_date="2026-09-14",
        actual_end_time="12:00",
    )
    assert task.actual_elapsed_minutes == 72 * 60


def test_31_original_baseline_snapshot_is_unchanged_by_calendar_cpm(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "original_baseline.db"))
    try:
        project_id = db.insert_project({"name": "Calendar baseline"})
        task_id = db.insert_task({
            "project_id": project_id,
            "title": "Baseline task",
            "planned_date": "2026-09-11",
            "planned_start_time": "23:00",
            "estimated_duration": 120,
            "status": "Planned",
        })
        version_id = ScheduleVersionService.create_original_baseline(
            db,
            project_id,
            approved_at="2026-09-07T00:00:00",
        )
        before = version_items_hash(db, version_id)
        task = Task.from_row(db.get_task_by_id(task_id))
        CPMSchedulingService.calculate_schedule([task], project_id=project_id, project_calendar=MON_FRI)
        after = version_items_hash(db, version_id)
        assert before == after
    finally:
        db.close()


def test_32_approved_revision_snapshot_is_unchanged_by_calendar_cpm(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "approved_revision.db"))
    try:
        project_id = db.insert_project({"name": "Calendar revision"})
        task_id = db.insert_task({
            "project_id": project_id,
            "title": "Revision task",
            "planned_date": "2026-09-11",
            "planned_start_time": "23:00",
            "estimated_duration": 120,
            "status": "Planned",
        })
        ScheduleVersionService.create_original_baseline(
            db,
            project_id,
            approved_at="2026-09-07T00:00:00",
        )
        revision_id = ScheduleVersionService.create_approved_revision(
            db,
            project_id,
            name="Calendar Revision",
            approved_at="2026-09-08T00:00:00",
        )
        before = version_items_hash(db, revision_id)
        task = Task.from_row(db.get_task_by_id(task_id))
        CPMSchedulingService.calculate_schedule([task], project_id=project_id, project_calendar=MON_FRI)
        after = version_items_hash(db, revision_id)
        assert before == after
    finally:
        db.close()


def test_33_wbs_item_model_uses_cpm_with_project_calendar():
    source = (APP_ROOT / "models" / "wbs_item_model.py").read_text(encoding="utf-8")
    assert "CPMSchedulingService.calculate_schedule" in source
    assert "project_calendar=proj_cal" in source
    assert "get_project_calendar" in source


def test_34_gantt_view_refresh_delegates_to_wbs_rollup_cpm_route():
    source = (APP_ROOT / "views" / "gantt_view.py").read_text(encoding="utf-8")
    assert "refresh_project_schedule" in source
    assert "recalculates CPM schedule via WBSRollupService / CPMSchedulingService" in source
    assert "_build_phase1d_wbs_gantt_items" in source


def test_35_schedule_calendar_service_is_the_named_cpm_arithmetic_authority():
    source = (APP_ROOT / "services" / "cpm_scheduling_service.py").read_text(encoding="utf-8")
    assert "from todo_bird_app.services.schedule_calendar_service import" in source
    assert "add_working_minutes" in source
    assert "subtract_working_minutes" in source
    assert "working_minutes_between" in source


def test_36_5000_node_calendar_cpm_performance_is_bounded():
    tasks = [make_task(1, duration=1)]
    for task_id in range(2, 5001):
        tasks.append(make_task(task_id, day="2026-09-07", clock="00:00", duration=1, deps=[dep(task_id - 1)]))
    start = time.perf_counter()
    result = schedule(tasks)
    elapsed = time.perf_counter() - start
    assert result.schedulable_tasks == 5000
    assert node(result, 5000).earliest_finish == dt("2026-09-10 20:20")
    assert elapsed < 5.0


def test_37_production_db_read_only_witness_does_not_change_hash():
    if not PRODUCTION_DB.exists():
        pytest.skip("production DB not present")
    before = hashlib.sha256(PRODUCTION_DB.read_bytes()).hexdigest()
    db = DatabaseManager.read_only(str(PRODUCTION_DB))
    try:
        with db.get_connection() as conn:
            conn.execute("SELECT COUNT(*) FROM projects;").fetchone()
            conn.execute("SELECT COUNT(*) FROM tasks;").fetchone()
            conn.execute("SELECT COUNT(*) FROM schedule_versions;").fetchone()
    finally:
        db.close()
    after = hashlib.sha256(PRODUCTION_DB.read_bytes()).hexdigest()
    assert after == before
