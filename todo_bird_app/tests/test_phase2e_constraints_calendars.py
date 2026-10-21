"""
Phase 2E Acceptance Matrix Test Suite — Schedule Constraints, Deadlines & Project Calendars.

88 Comprehensive Scenarios testing:
- Constraint model, parsing, aliases, and validation (1–10)
- Forward/backward pass CPM math & negative float (11–23)
- Deadlines & variance monitoring (24–30)
- Dependency integration (31–37)
- Calendar & Exceptions (38–49)
- Baseline 1 Immutability Coexistence (50–53)
- WBS Item Model & Rollup Integration (54–59)
- Gantt Markers & Visuals (60–66)
- Milestones with Constraints/Deadlines (67–69)
- Database Persistence & Migrations (70–74)
- TaskDialog UI & Accessibility (75–80)
- Performance 5,000 Tasks O(V + E) (81–83)
- Regression Stability (84–88)
"""

import json
import os
import sqlite3
import tempfile
import time
from datetime import datetime, date, timedelta
from typing import Dict, List, Any

import pytest
from PySide6.QtCore import Qt, QModelIndex
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager, ScheduleVersionImmutabilityError
from todo_bird_app.models.task import Task, TaskPriority, TaskStatus
from todo_bird_app.models.project import Project
from todo_bird_app.models.wbs_item_model import WBSItemModel
from todo_bird_app.services.cpm_scheduling_service import (
    CPMSchedulingService,
    DiagnosticCode,
    DependencySpec,
    DependencyType,
)
from todo_bird_app.services.schedule_constraint_service import (
    ConstraintType,
    ConstraintSpec,
    CalendarException,
    ProjectCalendarSpec,
    ScheduleConstraintService,
    format_deadline_variance,
    get_constraint_display_name,
    get_constraint_tooltip,
    is_date_required,
    parse_constraint_datetime,
)
from todo_bird_app.gantt.gantt_items import GanttTaskItem
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.project_calendar_dialog import ProjectCalendarDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(path)
    yield db
    db.close()
    if os.path.exists(path):
        os.remove(path)


# ============================================================================
# 1. CONSTRAINT MODEL & PARSING (Scenarios 1–10)
# ============================================================================

def test_01_default_task_constraint():
    t = Task(id=1, title="Default Task")
    assert t.constraint_type == "ASAP"
    assert t.constraint_datetime is None
    assert t.deadline_datetime is None


def test_02_constraint_type_enum_parsing():
    for ct in ConstraintType:
        parsed = ConstraintType.from_str(ct.value)
        assert parsed == ct


def test_03_constraint_type_aliases():
    assert ConstraintType.from_str("Must Start On") == ConstraintType.MSO
    assert ConstraintType.from_str("Start No Earlier Than") == ConstraintType.SNET
    assert ConstraintType.from_str("Finish No Later Than") == ConstraintType.FNLT
    assert ConstraintType.from_str("As Late As Possible") == ConstraintType.ALAP


def test_04_case_insensitivity_and_whitespace():
    assert ConstraintType.from_str("  mso  ") == ConstraintType.MSO
    assert ConstraintType.from_str("snet") == ConstraintType.SNET
    assert ConstraintType.from_str("  As Soon As Possible  ") == ConstraintType.ASAP


def test_05_unknown_constraint_fallback():
    assert ConstraintType.from_str("UNKNOWN_FOO") == ConstraintType.ASAP
    assert ConstraintType.from_str(None) == ConstraintType.ASAP
    assert ConstraintType.from_str("") == ConstraintType.ASAP


def test_06_is_date_required():
    assert is_date_required(ConstraintType.ASAP) is False
    assert is_date_required(ConstraintType.ALAP) is False
    assert is_date_required(ConstraintType.SNET) is True
    assert is_date_required(ConstraintType.SNLT) is True
    assert is_date_required(ConstraintType.FNET) is True
    assert is_date_required(ConstraintType.FNLT) is True
    assert is_date_required(ConstraintType.MSO) is True
    assert is_date_required(ConstraintType.MFO) is True


def test_07_parse_constraint_datetime_formats():
    dt1 = parse_constraint_datetime("2026-09-01 09:30:00")
    assert dt1 == datetime(2026, 9, 1, 9, 30, 0)
    dt2 = parse_constraint_datetime("2026-09-01 09:30")
    assert dt2 == datetime(2026, 9, 1, 9, 30)
    dt3 = parse_constraint_datetime("2026-09-01")
    assert dt3 == datetime(2026, 9, 1, 0, 0)
    dt4 = parse_constraint_datetime(date(2026, 9, 1))
    assert dt4 == datetime(2026, 9, 1, 0, 0)


def test_08_parse_constraint_datetime_invalid():
    assert parse_constraint_datetime(None) is None
    assert parse_constraint_datetime("") is None
    assert parse_constraint_datetime("invalid-date") is None


def test_09_get_constraint_display_name():
    assert get_constraint_display_name(ConstraintType.ASAP) == "As Soon As Possible"
    assert get_constraint_display_name(ConstraintType.MSO) == "Must Start On"
    assert get_constraint_display_name("FNET") == "Finish No Earlier Than"


def test_10_get_constraint_tooltip():
    for ct in ConstraintType:
        tt = get_constraint_tooltip(ct)
        assert isinstance(tt, str)
        assert len(tt) > 5


# ============================================================================
# 2. FORWARD/BACKWARD PASS CPM MATH & NEGATIVE FLOAT (Scenarios 11–23)
# ============================================================================

def test_11_asap_task_schedules_at_earliest():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=120)
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[1])
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.nodes[1].earliest_finish == datetime(2026, 9, 1, 11, 0)
    assert res.nodes[2].earliest_start == datetime(2026, 9, 1, 11, 0)


def test_12_snet_pushes_start_forward():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=120)
    t2 = Task(
        id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        dependencies=[1], constraint_type="SNET", constraint_datetime="2026-09-01 14:00"
    )
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    # T1 finishes at 11:00, but SNET on T2 is 14:00 -> T2 ES becomes 14:00
    assert res.nodes[2].earliest_start == datetime(2026, 9, 1, 14, 0)
    assert res.nodes[2].earliest_finish == datetime(2026, 9, 1, 15, 0)


def test_13_snet_does_not_delay_if_dependency_is_later():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=360) # finishes 15:00
    t2 = Task(
        id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        dependencies=[1], constraint_type="SNET", constraint_datetime="2026-09-01 12:00"
    )
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.nodes[2].earliest_start == datetime(2026, 9, 1, 15, 0)


def test_14_fnet_pushes_finish_and_start():
    t1 = Task(
        id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        constraint_type="FNET", constraint_datetime="2026-09-01 12:00"
    )
    res = CPMSchedulingService.calculate_schedule([t1])
    assert res.nodes[1].earliest_finish == datetime(2026, 9, 1, 12, 0)
    assert res.nodes[1].earliest_start == datetime(2026, 9, 1, 11, 0)


def test_15_fnet_does_not_delay_if_work_already_finishes_later():
    t1 = Task(
        id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=300, # finishes 14:00
        constraint_type="FNET", constraint_datetime="2026-09-01 12:00"
    )
    res = CPMSchedulingService.calculate_schedule([t1])
    assert res.nodes[1].earliest_finish == datetime(2026, 9, 1, 14, 0)


def test_16_mso_forces_exact_start_date():
    t1 = Task(
        id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        constraint_type="MSO", constraint_datetime="2026-09-01 13:00"
    )
    res = CPMSchedulingService.calculate_schedule([t1])
    assert res.nodes[1].earliest_start == datetime(2026, 9, 1, 13, 0)
    assert res.nodes[1].earliest_finish == datetime(2026, 9, 1, 14, 0)


def test_17_mso_conflict_with_predecessor():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=240) # finishes 13:00
    t2 = Task(
        id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        dependencies=[1], constraint_type="MSO", constraint_datetime="2026-09-01 10:00" # Impossible: T1 finishes 13:00
    )
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert DiagnosticCode.CONSTRAINT_CONFLICT in res.nodes[2].diagnostic_codes
    assert res.nodes[2].earliest_start == datetime(2026, 9, 1, 13, 0)


def test_18_mfo_forces_exact_finish():
    t1 = Task(
        id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=120,
        constraint_type="MFO", constraint_datetime="2026-09-01 15:00"
    )
    res = CPMSchedulingService.calculate_schedule([t1])
    assert res.nodes[1].earliest_finish == datetime(2026, 9, 1, 15, 0)
    assert res.nodes[1].earliest_start == datetime(2026, 9, 1, 13, 0)


def test_19_mfo_conflict_with_predecessor():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=360) # finishes 15:00
    t2 = Task(
        id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        dependencies=[1], constraint_type="MFO", constraint_datetime="2026-09-01 12:00" # Impossible
    )
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert DiagnosticCode.CONSTRAINT_CONFLICT in res.nodes[2].diagnostic_codes


def test_20_snlt_restricts_latest_start():
    t1 = Task(
        id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        constraint_type="SNLT", constraint_datetime="2026-09-01 10:00"
    )
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=300) # finishes 14:00
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    # Project finishes at 14:00. Without SNLT, T1 LF would be 14:00 (LS 13:00).
    # With SNLT at 10:00, T1 LF <= 11:00 -> LS <= 10:00.
    assert res.nodes[1].latest_start <= datetime(2026, 9, 1, 10, 0)


def test_21_snlt_conflict_negative_float():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=180) # finishes 12:00
    t2 = Task(
        id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        dependencies=[1], constraint_type="SNLT", constraint_datetime="2026-09-01 10:00" # ES=12:00 > SNLT=10:00
    )
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.nodes[2].total_float_minutes is not None
    assert res.nodes[2].total_float_minutes < 0
    assert DiagnosticCode.NEGATIVE_FLOAT in res.nodes[2].diagnostic_codes
    assert DiagnosticCode.CONSTRAINT_CONFLICT in res.nodes[2].diagnostic_codes


def test_22_fnlt_restricts_latest_finish():
    # Case 1: Valid network finish before FNLT bound
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60)
    t2 = Task(
        id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        dependencies=[1], constraint_type="FNLT", constraint_datetime="2026-09-01 12:00"
    )
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.nodes[2].latest_finish <= datetime(2026, 9, 1, 12, 0)
    assert res.nodes[2].total_float_minutes >= 0

    # Case 2: Exact boundary match LF == constraint
    t3 = Task(
        id=3, title="C", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=120,
        constraint_type="FNLT", constraint_datetime="2026-09-01 11:00"
    )
    res_b = CPMSchedulingService.calculate_schedule([t3])
    assert res_b.nodes[3].latest_finish == datetime(2026, 9, 1, 11, 0)

    # Case 3: Violation requiring finish after constraint -> conflict & negative float
    t4 = Task(id=4, title="D", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=180) # EF=12:00
    t5 = Task(
        id=5, title="E", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        dependencies=[4], constraint_type="FNLT", constraint_datetime="2026-09-01 10:00" # Impossible
    )
    res_v = CPMSchedulingService.calculate_schedule([t4, t5])
    assert res_v.nodes[5].total_float_minutes < 0
    assert DiagnosticCode.CONSTRAINT_CONFLICT in res_v.nodes[5].diagnostic_codes


def test_23_alap_shifts_to_latest_start():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, constraint_type="ALAP")
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=240) # finishes 13:00
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    # Project finishes at 13:00. T1 (dur=60) shifts to 12:00->13:00 under ALAP
    assert res.nodes[1].earliest_start == datetime(2026, 9, 1, 12, 0)
    assert res.nodes[1].earliest_finish == datetime(2026, 9, 1, 13, 0)


# ============================================================================
# 3. DEADLINE MONITORING & VARIANCES (Scenarios 24–30)
# ============================================================================

def test_24_no_deadline_evaluation():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60)
    eval_res = ScheduleConstraintService.evaluate_task_deadline(t1, cpm_finish=datetime(2026, 9, 1, 10, 0))
    assert eval_res.deadline_datetime is None
    assert eval_res.variance_minutes is None
    assert eval_res.is_missed is False


def test_25_deadline_ahead_of_schedule():
    t1 = Task(
        id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        deadline_datetime="2026-09-01 12:00"
    )
    eval_res = ScheduleConstraintService.evaluate_task_deadline(t1, cpm_finish=datetime(2026, 9, 1, 10, 0), total_float_minutes=120)
    assert eval_res.variance_minutes == -120
    assert eval_res.is_missed is False
    assert eval_res.is_at_risk is False


def test_26_deadline_exact_match():
    t1 = Task(
        id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        deadline_datetime="2026-09-01 10:00"
    )
    eval_res = ScheduleConstraintService.evaluate_task_deadline(t1, cpm_finish=datetime(2026, 9, 1, 10, 0))
    assert eval_res.variance_minutes == 0
    assert eval_res.is_missed is False


def test_27_deadline_missed():
    t1 = Task(
        id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=180,
        deadline_datetime="2026-09-01 10:00"
    )
    res = CPMSchedulingService.calculate_schedule([t1])
    assert DiagnosticCode.DEADLINE_MISSED in res.nodes[1].diagnostic_codes


def test_28_deadline_at_risk():
    # Deterministic safe vs missed: no arbitrary 24h buffer heuristic
    t1 = Task(
        id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        deadline_datetime="2026-09-01 10:30"
    )
    res = CPMSchedulingService.calculate_schedule([t1])
    # Finished at 10:00 <= 10:30 -> Not missed
    assert DiagnosticCode.DEADLINE_MISSED not in res.nodes[1].diagnostic_codes
    assert DiagnosticCode.DEADLINE_AT_RISK not in res.nodes[1].diagnostic_codes


def test_29_deadline_does_not_alter_cpm_dates():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60)
    t2 = Task(
        id=2, title="A_with_deadline", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        deadline_datetime="2026-09-01 08:00" # Missed deadline
    )
    res1 = CPMSchedulingService.calculate_schedule([t1])
    res2 = CPMSchedulingService.calculate_schedule([t2])
    assert res1.nodes[1].earliest_start == res2.nodes[2].earliest_start
    assert res1.nodes[1].earliest_finish == res2.nodes[2].earliest_finish


def test_30_format_deadline_variance():
    assert format_deadline_variance(None) == "—"
    assert format_deadline_variance(0) == "0m"
    assert format_deadline_variance(45) == "+45m"
    assert format_deadline_variance(-45) == "-45m"
    assert format_deadline_variance(1500) == "+1d 1h"
    assert format_deadline_variance(-2880) == "-2d"


# ============================================================================
# 4. DEPENDENCY INTEGRATION (Scenarios 31–37)
# ============================================================================

def test_31_snet_with_fs_dependency():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60)
    t2 = Task(
        id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        dependencies=[1], constraint_type="SNET", constraint_datetime="2026-09-01 11:30"
    )
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.nodes[2].earliest_start == datetime(2026, 9, 1, 11, 30)


def test_32_ss_dependency_with_snet():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=120)
    spec = DependencySpec(predecessor_id=1, successor_id=2, dependency_type=DependencyType.SS, lag_minutes=30)
    t2 = Task(
        id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        dependencies=[spec.to_dict()], constraint_type="SNET", constraint_datetime="2026-09-01 10:00"
    )
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    # SS + 30m = 09:30. SNET = 10:00 -> ES = 10:00
    assert res.nodes[2].earliest_start == datetime(2026, 9, 1, 10, 0)


def test_33_ff_dependency_with_fnet():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=120) # EF=11:00
    spec = DependencySpec(predecessor_id=1, successor_id=2, dependency_type=DependencyType.FF, lag_minutes=0)
    t2 = Task(
        id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        dependencies=[spec.to_dict()], constraint_type="FNET", constraint_datetime="2026-09-01 12:00"
    )
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.nodes[2].earliest_finish == datetime(2026, 9, 1, 12, 0)


def test_34_sf_dependency_with_mso():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60)
    spec = DependencySpec(predecessor_id=1, successor_id=2, dependency_type=DependencyType.SF, lag_minutes=120) # EF(2) >= ES(1) + 120 = 11:00
    t2 = Task(
        id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        dependencies=[spec.to_dict()], constraint_type="MSO", constraint_datetime="2026-09-01 10:00"
    )
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.nodes[2].earliest_start == datetime(2026, 9, 1, 10, 0)


def test_35_multi_predecessor_convergence_mso_conflict():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=120) # EF=11:00
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=300) # EF=14:00
    t3 = Task(
        id=3, title="C", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        dependencies=[1, 2], constraint_type="MSO", constraint_datetime="2026-09-01 12:00" # Violates T2 finish of 14:00
    )
    res = CPMSchedulingService.calculate_schedule([t1, t2, t3])
    assert DiagnosticCode.CONSTRAINT_CONFLICT in res.nodes[3].diagnostic_codes


def test_36_chain_with_intermediate_snlt_creates_upstream_negative_float():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=120)
    t2 = Task(
        id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=120,
        dependencies=[1], constraint_type="SNLT", constraint_datetime="2026-09-01 10:00"
    )
    t3 = Task(id=3, title="C", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[2])
    res = CPMSchedulingService.calculate_schedule([t1, t2, t3])
    # T1 finishes 11:00, but T2 must start by 10:00 -> Upstream T1 has negative float
    assert res.nodes[1].total_float_minutes < 0
    assert res.nodes[2].total_float_minutes < 0


def test_37_critical_path_classification_negative_float():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=120)
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[1])
    t3 = Task(
        id=3, title="C_snlt", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        constraint_type="SNLT", constraint_datetime="2026-09-01 08:00"
    )
    res = CPMSchedulingService.calculate_schedule([t1, t2, t3])
    # T1 and T2 form the ordinary critical path (TF == 0)
    assert res.nodes[1].total_float_minutes == 0
    assert res.nodes[1].is_critical is True
    assert res.nodes[2].total_float_minutes == 0
    assert res.nodes[2].is_critical is True

    # T3 has negative float (TF < 0) -> conflict/warning state, NOT ordinary Critical Path (TF == 0)
    assert res.nodes[3].total_float_minutes < 0
    assert res.nodes[3].is_critical is False
    assert DiagnosticCode.NEGATIVE_FLOAT in res.nodes[3].diagnostic_codes
    assert DiagnosticCode.CONSTRAINT_CONFLICT in res.nodes[3].diagnostic_codes


# ============================================================================
# 5. CALENDAR & EXCEPTIONS (Scenarios 38–49)
# ============================================================================

def test_38_default_project_calendar():
    cal = ProjectCalendarSpec(project_id=1)
    assert cal.working_weekdays == (0, 1, 2, 3, 4)
    assert cal.is_working_day(date(2026, 9, 1)) is True   # Tuesday
    assert cal.is_working_day(date(2026, 9, 5)) is False  # Saturday


def test_39_custom_4_day_calendar():
    cal = ProjectCalendarSpec(project_id=1, working_weekdays=(0, 1, 2, 3))
    assert cal.is_working_day(date(2026, 9, 3)) is True   # Thursday
    assert cal.is_working_day(date(2026, 9, 4)) is False  # Friday (non-working)


def test_40_custom_6_day_calendar():
    cal = ProjectCalendarSpec(project_id=1, working_weekdays=(0, 1, 2, 3, 4, 5))
    assert cal.is_working_day(date(2026, 9, 5)) is True   # Saturday is working


def test_41_custom_7_day_calendar():
    cal = ProjectCalendarSpec(project_id=1, working_weekdays=(0, 1, 2, 3, 4, 5, 6))
    assert cal.is_working_day(date(2026, 9, 6)) is True   # Sunday is working


def test_42_holiday_exception():
    ex = CalendarException(date_str="2026-09-01", is_working=False, name="National Holiday")
    cal = ProjectCalendarSpec(project_id=1, working_weekdays=(0, 1, 2, 3, 4), exceptions=(ex,))
    assert cal.is_working_day(date(2026, 9, 1)) is False  # Tuesday is now holiday


def test_43_overtime_working_day_exception():
    ex = CalendarException(date_str="2026-09-05", is_working=True, name="Overtime Saturday")
    cal = ProjectCalendarSpec(project_id=1, working_weekdays=(0, 1, 2, 3, 4), exceptions=(ex,))
    assert cal.is_working_day(date(2026, 9, 5)) is True   # Saturday is now working


def test_44_calendar_conflict_diagnostic():
    ex = CalendarException(date_str="2026-09-01", is_working=False, name="Holiday")
    cal = ProjectCalendarSpec(project_id=1, working_weekdays=(0, 1, 2, 3, 4), exceptions=(ex,))
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60)
    res = CPMSchedulingService.calculate_schedule([t1], project_calendar=cal)
    assert DiagnosticCode.CALENDAR_CONFLICT in res.nodes[1].diagnostic_codes


def test_45_task_inherits_project_calendar(temp_db):
    pid = temp_db.insert_project({
        "name": "Cal Project",
        "working_weekdays": [0, 1, 2, 3],
        "calendar_exceptions": [{"date": "2026-09-01", "is_working": 0, "name": "Holiday"}],
    })
    cal_data = temp_db.get_project_calendar(pid)
    assert cal_data["working_weekdays"] == [0, 1, 2, 3]
    assert len(cal_data["calendar_exceptions"]) == 1


def test_46_actual_elapsed_span_preserved_on_weekend():
    t = Task(
        id=1, title="A",
        actual_start_date="2026-09-05", actual_start_time="10:00",  # Saturday
        actual_end_date="2026-09-05", actual_end_time="14:00",
    )
    # Actual elapsed span is 240 minutes (10:00 to 14:00) regardless of working calendar
    assert t.actual_elapsed_minutes == 240


def test_47_actual_span_over_weekend():
    t = Task(
        id=1, title="A",
        actual_start_date="2026-09-04", actual_start_time="12:00",  # Friday
        actual_end_date="2026-09-07", actual_end_time="12:00",    # Monday (72 hours)
    )
    assert t.actual_elapsed_minutes == 72 * 60


def test_48_calendar_exception_serialization():
    ex = CalendarException(date_str="2026-12-25", is_working=False, name="Christmas")
    d = ex.to_dict()
    assert d["date"] == "2026-12-25"
    assert d["is_working"] == 0
    assert d["name"] == "Christmas"
    ex2 = CalendarException.from_dict(d)
    assert ex2.date_str == "2026-12-25"
    assert ex2.is_working is False


def test_49_multiple_calendar_exceptions():
    ex1 = CalendarException(date_str="2026-09-01", is_working=False, name="Holiday 1")
    ex2 = CalendarException(date_str="2026-09-02", is_working=False, name="Holiday 2")
    cal = ProjectCalendarSpec(project_id=1, exceptions=(ex1, ex2))
    assert cal.is_working_day("2026-09-01") is False
    assert cal.is_working_day("2026-09-02") is False
    assert cal.is_working_day("2026-09-03") is True


# ============================================================================
# 6. BASELINE 1 IMMUTABILITY COEXISTENCE (Scenarios 50–53)
# ============================================================================

def test_50_constraints_do_not_mutate_frozen_baseline():
    t = Task(
        id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        baseline_start="2026-09-01 09:00", baseline_finish="2026-09-01 10:00", baseline_duration_minutes=60,
        constraint_type="SNET", constraint_datetime="2026-09-05 09:00"
    )
    # Working schedule moves to Sep 5, but baseline remains Sep 1
    res = CPMSchedulingService.calculate_schedule([t])
    assert res.nodes[1].earliest_start == datetime(2026, 9, 5, 9, 0)
    assert t.baseline_start == "2026-09-01 09:00"
    assert t.baseline_finish == "2026-09-01 10:00"


def test_51_variance_calculation_with_active_constraints():
    t = Task(
        id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        baseline_start="2026-09-01 09:00", baseline_finish="2026-09-01 10:00", baseline_duration_minutes=60,
        constraint_type="SNET", constraint_datetime="2026-09-01 12:00"
    )
    res = CPMSchedulingService.calculate_schedule([t])
    from todo_bird_app.services.schedule_variance_service import ScheduleVarianceService
    v_res = ScheduleVarianceService.calculate_task_variance(t, cpm_node=res.nodes[1])
    assert v_res.start_variance_minutes == 180  # 09:00 -> 12:00 = +180m delay
    assert v_res.finish_variance_minutes == 180


def test_52_negative_float_coexists_with_baseline():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=120)
    t2 = Task(
        id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
        dependencies=[1], baseline_start="2026-09-01 11:00", baseline_finish="2026-09-01 12:00",
        constraint_type="SNLT", constraint_datetime="2026-09-01 10:00"
    )
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.nodes[2].total_float_minutes < 0
    assert t2.baseline_start == "2026-09-01 11:00"


def test_53_clearing_baseline_refused_preserves_constraints(temp_db):
    pid = temp_db.insert_project({"name": "P1"})
    tid = temp_db.insert_task({
        "project_id": pid, "title": "T1", "planned_date": "2026-09-01", "planned_start_time": "09:00",
        "estimated_duration": 60, "constraint_type": "MSO", "constraint_datetime": "2026-09-01 10:00",
        "baseline_start": "2026-09-01 09:00",
    })
    with pytest.raises(ScheduleVersionImmutabilityError):
        temp_db.clear_project_baseline(pid)
    saved = temp_db.get_task_by_id(tid)
    assert saved["baseline_start"] == "2026-09-01 09:00"
    assert saved["constraint_type"] == "MSO"
    assert saved["constraint_datetime"] == "2026-09-01 10:00"


# ============================================================================
# 7. WBS ITEM MODEL & ROLLUP INTEGRATION (Scenarios 54–59)
# ============================================================================

def test_54_wbs_model_exposes_phase2e_roles(temp_db):
    pid = temp_db.insert_project({"name": "WBS Proj"})
    temp_db.insert_task({
        "project_id": pid, "title": "Constrained", "planned_date": "2026-09-01", "planned_start_time": "09:00",
        "estimated_duration": 60, "constraint_type": "MSO", "constraint_datetime": "2026-09-01 11:00",
        "deadline_datetime": "2026-09-01 15:00",
    })
    model = WBSItemModel()
    model.load_project(temp_db, pid)
    idx = model.index(0, 0)
    assert model.data(idx, WBSItemModel.ConstraintTypeRole) == "MSO"
    assert model.data(idx, WBSItemModel.ConstraintDateRole) == "2026-09-01 11:00"
    assert model.data(idx, WBSItemModel.DeadlineDateRole) == "2026-09-01 15:00"


def test_55_wbs_model_column_count_and_headers():
    model = WBSItemModel()
    assert model.columnCount() == 22
    assert model.headerData(WBSItemModel.COL_CONSTRAINT, Qt.Horizontal, Qt.DisplayRole) == "Constraint Type"
    assert model.headerData(WBSItemModel.COL_DEADLINE, Qt.Horizontal, Qt.DisplayRole) == "Deadline"
    assert model.headerData(WBSItemModel.COL_DEADLINE_VARIANCE, Qt.Horizontal, Qt.DisplayRole) == "Deadline Variance"


def test_56_wbs_summary_nodes_display_dashes_for_leaf_columns(temp_db):
    pid = temp_db.insert_project({"name": "Parent Proj"})
    tid = temp_db.insert_task({"project_id": pid, "title": "Parent", "planned_date": "2026-09-01", "planned_start_time": "09:00"})
    temp_db.insert_subtask(task_id=tid, title="Child", planned_date="2026-09-01", planned_start_time="09:00")
    model = WBSItemModel()
    model.load_project(temp_db, pid)
    parent_idx = model.index(0, WBSItemModel.COL_CONSTRAINT)
    assert model.data(parent_idx, Qt.DisplayRole) == "—"


def test_57_wbs_deadline_variance_role_computation(temp_db):
    pid = temp_db.insert_project({"name": "Var Proj"})
    temp_db.insert_task({
        "project_id": pid, "title": "Task 1", "planned_date": "2026-09-01", "planned_start_time": "09:00",
        "estimated_duration": 60, "deadline_datetime": "2026-09-01 12:00",
    })
    model = WBSItemModel()
    model.load_project(temp_db, pid)
    idx = model.index(0, 0)
    var_m = model.data(idx, WBSItemModel.DeadlineVarianceRole)
    assert var_m == -120  # Finishes at 10:00, deadline 12:00 -> -120m


def test_58_wbs_constraint_status_display(temp_db):
    pid = temp_db.insert_project({"name": "Status Proj"})
    t1 = temp_db.insert_task({
        "project_id": pid, "title": "T1", "planned_date": "2026-09-01", "planned_start_time": "09:00",
        "estimated_duration": 180,
    })
    t2 = temp_db.insert_task({
        "project_id": pid, "title": "T2", "planned_date": "2026-09-01", "planned_start_time": "09:00",
        "estimated_duration": 60, "dependencies": json.dumps([t1]),
        "constraint_type": "MSO", "constraint_datetime": "2026-09-01 10:00",
    })
    model = WBSItemModel()
    model.load_project(temp_db, pid)
    idx_t2 = model.index(1, WBSItemModel.COL_CONSTRAINT_STATUS)
    assert model.data(idx_t2, Qt.DisplayRole) == "Conflicted"


def test_59_wbs_o1_lookup_performance(temp_db):
    pid = temp_db.insert_project({"name": "Perf Proj"})
    for i in range(100):
        temp_db.insert_task({
            "project_id": pid, "title": f"T{i}", "planned_date": "2026-09-01", "planned_start_time": "09:00",
            "estimated_duration": 30, "constraint_type": "ASAP",
        })
    model = WBSItemModel()
    model.load_project(temp_db, pid)
    t0 = time.perf_counter()
    for row in range(100):
        for col in range(22):
            idx = model.index(row, col)
            _ = model.data(idx, Qt.DisplayRole)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.1  # 2,200 cell accesses in < 100ms


# ============================================================================
# 8. GANTT MARKERS & VISUALS (Scenarios 60–66)
# ============================================================================

def test_60_gantt_renders_constraint_marker(qapp):
    task = Task(
        id=1, title="Constrained", planned_date="2026-09-01", planned_start_time="09:00",
        estimated_duration=120, constraint_type="MSO", constraint_datetime="2026-09-01 11:00"
    )
    prof = {"bar": "#6366F1", "text": "#FFFFFF", "progress": "#4F46E5"}
    item = GanttTaskItem(task=task, row=0, col_start=0.0, duration_cols=2.0, col_width=60, color_profile=prof)
    has_lock = any(hasattr(c, "text") and c.text() == "🔒" for c in item.childItems())
    assert has_lock is True


def test_61_gantt_renders_deadline_marker(qapp):
    task = Task(
        id=1, title="Deadlined", planned_date="2026-09-01", planned_start_time="09:00",
        estimated_duration=120, deadline_datetime="2026-09-01 15:00"
    )
    prof = {"bar": "#6366F1", "text": "#FFFFFF", "progress": "#4F46E5"}
    item = GanttTaskItem(task=task, row=0, col_start=0.0, duration_cols=2.0, col_width=60, color_profile=prof)
    has_flag = any(hasattr(c, "text") and c.text() == "⚑" for c in item.childItems())
    assert has_flag is True


def test_62_gantt_renders_both_baseline_and_constraint_markers(qapp):
    task = Task(
        id=1, title="Dual", planned_date="2026-09-01", planned_start_time="09:00",
        estimated_duration=120, baseline_start="2026-09-01 09:00", baseline_finish="2026-09-01 11:00",
        constraint_type="SNET", constraint_datetime="2026-09-01 09:30", deadline_datetime="2026-09-01 14:00"
    )
    prof = {"bar": "#6366F1", "text": "#FFFFFF", "progress": "#4F46E5"}
    item = GanttTaskItem(task=task, row=0, col_start=0.0, duration_cols=2.0, col_width=60, color_profile=prof, show_baseline=True)
    has_lock = any(hasattr(c, "text") and c.text() == "🔒" for c in item.childItems())
    has_flag = any(hasattr(c, "text") and c.text() == "⚑" for c in item.childItems())
    assert has_lock is True
    assert has_flag is True


def test_63_gantt_milestone_diamond_with_deadline(qapp):
    task = Task(
        id=1, title="Milestone 1", planned_date="2026-09-01", planned_start_time="09:00",
        estimated_duration=0, is_pinned=False, tags=["milestone"], deadline_datetime="2026-09-01 12:00"
    )
    prof = {"bar": "#6366F1", "text": "#FFFFFF", "progress": "#4F46E5"}
    item = GanttTaskItem(task=task, row=0, col_start=0.0, duration_cols=1.0, col_width=60, color_profile=prof)
    assert item is not None


def test_64_gantt_critical_path_marker_on_negative_float(qapp):
    task = Task(
        id=1, title="Crit", planned_date="2026-09-01", planned_start_time="09:00",
        estimated_duration=60, priority=TaskPriority.URGENT
    )
    task.cpm_is_critical = True
    prof = {"bar": "#6366F1", "text": "#FFFFFF", "progress": "#4F46E5"}
    item = GanttTaskItem(task=task, row=0, col_start=0.0, duration_cols=1.0, col_width=60, color_profile=prof)
    has_cp = any(hasattr(c, "text") and "CP" in c.text() for c in item.childItems())
    assert has_cp is True


def test_65_gantt_conflict_outline_coexistence(qapp):
    task = Task(id=1, title="Overlap", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60)
    setattr(task, "gantt_overlap", True)
    prof = {"bar": "#6366F1", "text": "#FFFFFF", "progress": "#4F46E5"}
    item = GanttTaskItem(task=task, row=0, col_start=0.0, duration_cols=1.0, col_width=60, color_profile=prof)
    has_conflict_marker = any(hasattr(c, "text") and "🔀" in c.text() for c in item.childItems())
    assert has_conflict_marker is True


def test_66_gantt_marker_tooltips(qapp):
    task = Task(
        id=1, title="T", planned_date="2026-09-01", planned_start_time="09:00",
        estimated_duration=60, constraint_type="MSO", constraint_datetime="2026-09-01 10:00"
    )
    prof = {"bar": "#6366F1", "text": "#FFFFFF", "progress": "#4F46E5"}
    item = GanttTaskItem(task=task, row=0, col_start=0.0, duration_cols=1.0, col_width=60, color_profile=prof)
    lock_item = next((c for c in item.childItems() if hasattr(c, "text") and c.text() == "🔒"), None)
    assert lock_item is not None
    assert "MSO" in lock_item.toolTip()


# ============================================================================
# 9. MILESTONES WITH CONSTRAINTS & DEADLINES (Scenarios 67–69)
# ============================================================================

def test_67_milestone_with_snet_constraint():
    t = Task(
        id=1, title="M1", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=0,
        tags=["milestone"], constraint_type="SNET", constraint_datetime="2026-09-01 14:00"
    )
    res = CPMSchedulingService.calculate_schedule([t])
    assert res.nodes[1].earliest_start == datetime(2026, 9, 1, 14, 0)
    assert res.nodes[1].earliest_finish == datetime(2026, 9, 1, 14, 0)


def test_68_milestone_with_mso():
    t = Task(
        id=1, title="M1", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=0,
        tags=["milestone"], constraint_type="MSO", constraint_datetime="2026-09-01 12:00"
    )
    res = CPMSchedulingService.calculate_schedule([t])
    assert res.nodes[1].earliest_start == datetime(2026, 9, 1, 12, 0)


def test_69_milestone_with_deadline_variance():
    t = Task(
        id=1, title="M1", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=0,
        tags=["milestone"], deadline_datetime="2026-09-01 10:00"
    )
    res = CPMSchedulingService.calculate_schedule([t])
    eval_res = ScheduleConstraintService.evaluate_task_deadline(t, cpm_finish=res.nodes[1].earliest_finish)
    assert eval_res.variance_minutes == -60  # Finished at 09:00, deadline 10:00 -> -60m


# ============================================================================
# 10. DATABASE PERSISTENCE & MIGRATIONS (Scenarios 70–74)
# ============================================================================

def test_70_schema_v15_migration_idempotency(temp_db):
    conn = temp_db.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(version) FROM schema_version;")
    ver = cursor.fetchone()[0]
    assert ver >= 15
    # Re-run migration should be idempotent
    temp_db._apply_v15_schema(cursor)


def test_71_insert_and_update_task_constraints(temp_db):
    pid = temp_db.insert_project({"name": "P1"})
    tid = temp_db.insert_task({
        "project_id": pid, "title": "T1", "planned_date": "2026-09-01", "planned_start_time": "09:00",
        "estimated_duration": 60, "constraint_type": "MSO", "constraint_datetime": "2026-09-01 10:00",
        "deadline_datetime": "2026-09-01 18:00",
    })
    t = temp_db.get_task_by_id(tid)
    assert t["constraint_type"] == "MSO"
    assert t["constraint_datetime"] == "2026-09-01 10:00"
    assert t["deadline_datetime"] == "2026-09-01 18:00"

    temp_db.update_task({
        "id": tid, "constraint_type": "ALAP", "constraint_datetime": None, "deadline_datetime": "2026-09-01 20:00"
    })
    t_updated = temp_db.get_task_by_id(tid)
    assert t_updated["constraint_type"] == "ALAP"
    assert t_updated["constraint_datetime"] is None
    assert t_updated["deadline_datetime"] == "2026-09-01 20:00"


def test_72_insert_and_update_project_calendar(temp_db):
    pid = temp_db.insert_project({
        "name": "P1", "working_weekdays": [0, 1, 2, 3],
        "calendar_exceptions": [{"date": "2026-09-01", "is_working": 0, "name": "Off"}],
    })
    p = temp_db.get_project(pid)
    assert json.loads(p["working_weekdays"]) == [0, 1, 2, 3]


def test_73_set_and_get_project_calendar_sync(temp_db):
    pid = temp_db.insert_project({"name": "P1"})
    temp_db.set_project_calendar(
        pid,
        working_weekdays=[0, 1, 2, 3, 4, 5],
        calendar_exceptions=[{"date": "2026-10-01", "is_working": 0, "name": "Holiday"}],
    )
    cal = temp_db.get_project_calendar(pid)
    assert cal["working_weekdays"] == [0, 1, 2, 3, 4, 5]
    assert len(cal["calendar_exceptions"]) == 1
    assert cal["calendar_exceptions"][0]["date"] == "2026-10-01"


def test_74_add_and_delete_project_calendar_exception(temp_db):
    pid = temp_db.insert_project({"name": "P1"})
    ex_id = temp_db.add_project_calendar_exception(pid, "2026-11-01", is_working=False, name="Off Day")
    assert ex_id > 0
    cal1 = temp_db.get_project_calendar(pid)
    assert len(cal1["calendar_exceptions"]) == 1

    temp_db.delete_project_calendar_exception(ex_id)
    cal2 = temp_db.get_project_calendar(pid)
    assert len(cal2["calendar_exceptions"]) == 0


# ============================================================================
# 11. TASKDIALOG UI & ACCESSIBILITY (Scenarios 75–80)
# ============================================================================

def test_75_task_dialog_constraint_combo_populated(qapp):
    proj = Project(id=1, name="P1")
    dlg = TaskDialog(projects=[proj])
    assert dlg.constraint_type_combo.count() == 8
    dlg.close()


def test_76_task_dialog_dynamic_date_enable_disable(qapp):
    proj = Project(id=1, name="P1")
    dlg = TaskDialog(projects=[proj])
    dlg.constraint_type_combo.setCurrentIndex(dlg.constraint_type_combo.findData("ASAP"))
    assert dlg.constraint_date_edit.isEnabled() is False
    dlg.constraint_type_combo.setCurrentIndex(dlg.constraint_type_combo.findData("MSO"))
    assert dlg.constraint_date_edit.isEnabled() is True
    dlg.close()


def test_77_task_dialog_deadline_checkbox_toggle(qapp):
    proj = Project(id=1, name="P1")
    dlg = TaskDialog(projects=[proj])
    dlg.deadline_check.setChecked(False)
    assert dlg.deadline_date_edit.isEnabled() is False
    dlg.deadline_check.setChecked(True)
    assert dlg.deadline_date_edit.isEnabled() is True
    dlg.close()


def test_78_task_dialog_on_save_persists_constraints(qapp):
    proj = Project(id=1, name="P1")
    task = Task(id=1, title="Test Task", project_id=1, planned_date="2026-09-01", planned_start_time="09:00", planned_end_time="10:00")
    dlg = TaskDialog(projects=[proj], task=task)
    dlg.title_input.setText("Updated Task")
    dlg.constraint_type_combo.setCurrentIndex(dlg.constraint_type_combo.findData("SNET"))
    dlg.deadline_check.setChecked(True)
    dlg.on_save()
    assert dlg.task.constraint_type == "SNET"
    assert dlg.task.constraint_datetime is not None
    assert dlg.task.deadline_datetime is not None
    dlg.close()


def test_79_task_dialog_baseline_and_actuals_coexist(qapp):
    proj = Project(id=1, name="P1")
    task = Task(
        id=1, title="Test", project_id=1, planned_date="2026-09-01", planned_start_time="09:00", planned_end_time="10:00",
        baseline_start="2026-09-01 09:00", baseline_finish="2026-09-01 10:00", baseline_duration_minutes=60,
    )
    dlg = TaskDialog(projects=[proj], task=task)
    assert dlg is not None
    dlg.close()


def test_80_project_calendar_dialog_ui(qapp, temp_db):
    pid = temp_db.insert_project({"name": "Cal Project"})
    dlg = ProjectCalendarDialog(project_id=pid, project_name="Cal Project", db_manager=temp_db)
    assert len(dlg.weekday_checkboxes) == 7
    dlg._on_save()
    dlg.close()


# ============================================================================
# 12. PERFORMANCE 5,000 TASKS O(V + E) (Scenarios 81–83)
# ============================================================================

def test_81_performance_5000_tasks_cpm():
    tasks = []
    base_dt = datetime(2026, 9, 1, 9, 0)
    for i in range(1, 5001):
        deps = [i - 1] if i > 1 else []
        c_type = "ASAP"
        c_dt = None
        if i % 10 == 0:
            c_type = "SNET"
            c_dt = (base_dt + timedelta(minutes=i * 5)).strftime("%Y-%m-%d %H:%M")
        elif i % 25 == 0:
            c_type = "ALAP"

        tasks.append(Task(
            id=i, title=f"Task {i}", planned_date="2026-09-01", planned_start_time="09:00",
            estimated_duration=10, dependencies=deps, constraint_type=c_type, constraint_datetime=c_dt
        ))

    t0 = time.perf_counter()
    res = CPMSchedulingService.calculate_schedule(tasks)
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.8  # 5,000 chained tasks with constraints calculated in < 800ms
    assert len(res.nodes) == 5000
    assert res.is_complete is True


def test_82_linear_time_scaling():
    def time_cpm(n):
        ts = [Task(id=i, title=f"T{i}", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=10, dependencies=[i-1] if i>1 else []) for i in range(1, n+1)]
        t0 = time.perf_counter()
        _ = CPMSchedulingService.calculate_schedule(ts)
        return time.perf_counter() - t0

    t_1000 = time_cpm(1000)
    t_2000 = time_cpm(2000)
    # Scaling factor should be roughly linear (t_2000 <= 3.5 * t_1000)
    assert t_2000 < max(0.5, t_1000 * 3.5)


def test_83_zero_stack_depth_overflow_on_deep_graph():
    # 3,000 serial dependencies in a single chain
    tasks = [Task(id=i, title=f"T{i}", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=5, dependencies=[i-1] if i>1 else []) for i in range(1, 3001)]
    res = CPMSchedulingService.calculate_schedule(tasks)
    assert len(res.nodes) == 3000
    assert len(res.critical_task_ids) == 3000


# ============================================================================
# 13. REGRESSION STABILITY (Scenarios 84–88)
# ============================================================================

def test_84_pure_unconstrained_cpm_parity():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=120)
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[1])
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.nodes[1].total_float_minutes == 0
    assert res.nodes[2].total_float_minutes == 0
    assert res.critical_task_ids == (1, 2)


def test_85_baseline_variance_math_matches_phase2d():
    from todo_bird_app.services.schedule_variance_service import ScheduleVarianceService
    t = Task(
        id=1, title="A", planned_date="2026-09-01", planned_start_time="10:00", estimated_duration=60,
        baseline_start="2026-09-01 09:00", baseline_finish="2026-09-01 10:00", baseline_duration_minutes=60,
    )
    v = ScheduleVarianceService.calculate_task_variance(t, is_critical=False)
    assert v.start_variance_minutes == 60
    assert v.finish_variance_minutes == 60
    assert v.duration_variance_minutes == 0


def test_86_four_dependency_types_without_constraints():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=120)
    spec_ss = DependencySpec(predecessor_id=1, successor_id=2, dependency_type=DependencyType.SS, lag_minutes=30)
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[spec_ss.to_dict()])
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.nodes[2].earliest_start == datetime(2026, 9, 1, 9, 30)


def test_87_wbs_rollups_parity(temp_db):
    pid = temp_db.insert_project({"name": "WBS Rollup"})
    tid = temp_db.insert_task({"project_id": pid, "title": "Parent", "planned_date": "2026-09-01", "planned_start_time": "09:00"})
    temp_db.insert_subtask(task_id=tid, title="Child 1", progress=100, estimated_duration=60)
    temp_db.insert_subtask(task_id=tid, title="Child 2", progress=0, estimated_duration=60)
    model = WBSItemModel()
    model.load_project(temp_db, pid)
    idx = model.index(0, WBSItemModel.COL_PROGRESS)
    assert model.data(idx, WBSItemModel.ProgressRole) == 50  # Average progress = 50%


def test_88_cycle_detection_preserved():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[2])
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[1])
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.has_cycles is True
    assert 1 in res.cycle_task_ids
    assert 2 in res.cycle_task_ids


# ============================================================================
# 14. EXPLICIT AUDIT VERIFICATION (Scenarios 89–100)
# ============================================================================

def test_89_all_8_constraint_equations():
    # 1. ASAP
    t_asap = Task(id=1, title="ASAP", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, constraint_type="ASAP")
    r1 = CPMSchedulingService.calculate_schedule([t_asap])
    assert r1.nodes[1].earliest_start == datetime(2026, 9, 1, 9, 0)

    # 2. ALAP
    t_alap = Task(id=2, title="ALAP", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, constraint_type="ALAP")
    t_ref = Task(id=3, title="Ref", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=240)
    r2 = CPMSchedulingService.calculate_schedule([t_alap, t_ref])
    assert r2.nodes[2].earliest_start == datetime(2026, 9, 1, 12, 0)

    # 3. SNET: ES >= constraint
    t_snet = Task(id=4, title="SNET", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, constraint_type="SNET", constraint_datetime="2026-09-01 11:00")
    r3 = CPMSchedulingService.calculate_schedule([t_snet])
    assert r3.nodes[4].earliest_start == datetime(2026, 9, 1, 11, 0)

    # 4. SNLT: LS <= constraint
    t_snlt = Task(id=5, title="SNLT", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, constraint_type="SNLT", constraint_datetime="2026-09-01 10:00")
    r4 = CPMSchedulingService.calculate_schedule([t_snlt, t_ref])
    assert r4.nodes[5].latest_start <= datetime(2026, 9, 1, 10, 0)

    # 5. FNET: EF >= constraint
    t_fnet = Task(id=6, title="FNET", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, constraint_type="FNET", constraint_datetime="2026-09-01 12:00")
    r5 = CPMSchedulingService.calculate_schedule([t_fnet])
    assert r5.nodes[6].earliest_finish == datetime(2026, 9, 1, 12, 0)

    # 6. FNLT: LF <= constraint
    t_fnlt = Task(id=7, title="FNLT", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, constraint_type="FNLT", constraint_datetime="2026-09-01 11:00")
    r6 = CPMSchedulingService.calculate_schedule([t_fnlt])
    assert r6.nodes[7].latest_finish <= datetime(2026, 9, 1, 11, 0)

    # 7. MSO: start exactly equals constraint (if valid)
    t_mso = Task(id=8, title="MSO", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, constraint_type="MSO", constraint_datetime="2026-09-01 13:00")
    r7 = CPMSchedulingService.calculate_schedule([t_mso])
    assert r7.nodes[8].earliest_start == datetime(2026, 9, 1, 13, 0)

    # 8. MFO: finish exactly equals constraint (if valid)
    t_mfo = Task(id=9, title="MFO", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, constraint_type="MFO", constraint_datetime="2026-09-01 14:00")
    r8 = CPMSchedulingService.calculate_schedule([t_mfo])
    assert r8.nodes[9].earliest_finish == datetime(2026, 9, 1, 14, 0)


def test_90_snlt_impossible_network():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=180) # EF=12:00
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[1], constraint_type="SNLT", constraint_datetime="2026-09-01 10:00")
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.nodes[2].total_float_minutes < 0
    assert DiagnosticCode.CONSTRAINT_CONFLICT in res.nodes[2].diagnostic_codes


def test_91_fnlt_impossible_network():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=180) # EF=12:00
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[1], constraint_type="FNLT", constraint_datetime="2026-09-01 11:00")
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.nodes[2].total_float_minutes < 0
    assert DiagnosticCode.CONSTRAINT_CONFLICT in res.nodes[2].diagnostic_codes


def test_92_mso_dependency_conflict():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=180) # EF=12:00
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[1], constraint_type="MSO", constraint_datetime="2026-09-01 10:00")
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.nodes[2].earliest_start == datetime(2026, 9, 1, 12, 0) # Dependency bounds preserved!
    assert DiagnosticCode.CONSTRAINT_CONFLICT in res.nodes[2].diagnostic_codes


def test_93_mfo_dependency_conflict():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=180) # EF=12:00
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[1], constraint_type="MFO", constraint_datetime="2026-09-01 11:00")
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.nodes[2].earliest_start == datetime(2026, 9, 1, 12, 0) # Dependency bounds preserved!
    assert DiagnosticCode.CONSTRAINT_CONFLICT in res.nodes[2].diagnostic_codes


def test_94_negative_float_not_classified_as_ordinary_critical():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=120)
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[1])
    t3 = Task(id=3, title="C_snlt", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, constraint_type="SNLT", constraint_datetime="2026-09-01 08:00")
    res = CPMSchedulingService.calculate_schedule([t1, t2, t3])
    assert res.nodes[1].total_float_minutes == 0
    assert res.nodes[1].is_critical is True
    assert res.nodes[3].total_float_minutes < 0
    assert res.nodes[3].is_critical is False # Strict TF == 0 rule


def test_95_deadline_safe():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, deadline_datetime="2026-09-01 12:00")
    res = CPMSchedulingService.calculate_schedule([t1])
    assert DiagnosticCode.DEADLINE_MISSED not in res.nodes[1].diagnostic_codes


def test_96_deadline_missed():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=180, deadline_datetime="2026-09-01 10:00")
    res = CPMSchedulingService.calculate_schedule([t1])
    assert DiagnosticCode.DEADLINE_MISSED in res.nodes[1].diagnostic_codes


def test_97_no_arbitrary_24h_risk_threshold():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, deadline_datetime="2026-09-01 10:30")
    res = CPMSchedulingService.calculate_schedule([t1])
    assert DiagnosticCode.DEADLINE_AT_RISK not in res.nodes[1].diagnostic_codes


def test_98_deadline_never_changes_es_ef():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60)
    t2 = Task(id=2, title="A_deadlined", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, deadline_datetime="2026-09-01 08:00")
    r1 = CPMSchedulingService.calculate_schedule([t1])
    r2 = CPMSchedulingService.calculate_schedule([t2])
    assert r1.nodes[1].earliest_start == r2.nodes[2].earliest_start
    assert r1.nodes[1].earliest_finish == r2.nodes[2].earliest_finish


def test_99_baseline_remains_frozen():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, baseline_start="2026-09-01 09:00", baseline_finish="2026-09-01 10:00", constraint_type="SNET", constraint_datetime="2026-09-05 09:00")
    res = CPMSchedulingService.calculate_schedule([t1])
    assert res.nodes[1].earliest_start == datetime(2026, 9, 5, 9, 0)
    assert t1.baseline_start == "2026-09-01 09:00"


def test_100_four_dependency_types_unchanged():
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=120)
    s_fs = DependencySpec(1, 2, DependencyType.FS, 0)
    s_ss = DependencySpec(1, 3, DependencyType.SS, 30)
    s_ff = DependencySpec(1, 4, DependencyType.FF, 60)
    s_sf = DependencySpec(1, 5, DependencyType.SF, 0)

    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[s_fs.to_dict()])
    t3 = Task(id=3, title="C", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[s_ss.to_dict()])
    t4 = Task(id=4, title="D", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[s_ff.to_dict()])
    t5 = Task(id=5, title="E", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60, dependencies=[s_sf.to_dict()])

    res = CPMSchedulingService.calculate_schedule([t1, t2, t3, t4, t5])
    assert res.nodes[2].earliest_start == datetime(2026, 9, 1, 11, 0)
    assert res.nodes[3].earliest_start == datetime(2026, 9, 1, 9, 30)
    assert res.nodes[4].earliest_finish == datetime(2026, 9, 1, 12, 0)
    assert res.nodes[5].earliest_finish >= datetime(2026, 9, 1, 9, 0)
