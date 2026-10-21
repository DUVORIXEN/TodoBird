"""
TODO BIRD — EXECUTION PERFORMANCE SERVICE (Phase 2E)

Pure Python, Qt-independent, deterministic canonical authority for:
1. Deriving and validating Execution States (NOT_TRACKED, IN_PROGRESS, FINISHED).
2. Detecting, classifying, and diagnosing Execution State Anomalies.
3. Calculating full calendar-time Actual Elapsed minutes.
4. Calculating Execution Start & Finish Variances (Actual vs Reference).
5. Detecting constraint-vs-actual schedule-control exceptions.

Sign Convention (Project Controls Standard):
    Variance = Actual - Reference
    - negative start variance = started EARLIER than reference (ahead)
    - zero start variance = started ON reference
    - positive start variance = started LATER than reference (behind)
    - negative finish variance = finished EARLIER than reference (ahead)
    - positive finish variance = finished LATER than reference (behind)

Integer minutes are the internal calculation authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Sequence, Tuple, Union

from todo_bird_app.utils.time_math import (
    combine_date_time,
    parse_date,
    parse_hhmm,
    duration_between,
    calculate_actual_elapsed_minutes,
    get_current_datetime,
)


class ExecutionState(str, Enum):
    NOT_TRACKED = "not_started"
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    FINISHED = "completed"
    COMPLETED = "completed"


class StartPerformance(str, Enum):
    NOT_STARTED = "not_started"
    STARTED_EARLY = "started_early"
    STARTED_ON_TIME = "started_on_time"
    STARTED_LATE = "started_late"


class FinishPerformance(str, Enum):
    UNAVAILABLE = "unavailable"
    IN_PROGRESS = "in_progress"
    FINISHED_EARLY = "finished_early"
    FINISHED_ON_TIME = "finished_on_time"
    FINISHED_LATE = "finished_late"


class ExecutionDiagnosticCode(str, Enum):
    ACTUAL_START_BEFORE_PLAN = "ACTUAL_START_BEFORE_PLAN"
    ACTUAL_START_AFTER_PLAN = "ACTUAL_START_AFTER_PLAN"
    ACTUAL_START_BEFORE_SNET = "ACTUAL_START_BEFORE_SNET"
    ACTUAL_START_AFTER_SNLT = "ACTUAL_START_AFTER_SNLT"
    ACTUAL_FINISH_BEFORE_FNET = "ACTUAL_FINISH_BEFORE_FNET"
    ACTUAL_FINISH_AFTER_FNLT = "ACTUAL_FINISH_AFTER_FNLT"
    ACTUAL_START_DIFFERS_FROM_MSO = "ACTUAL_START_DIFFERS_FROM_MSO"
    ACTUAL_FINISH_DIFFERS_FROM_MFO = "ACTUAL_FINISH_DIFFERS_FROM_MFO"


class ExecutionAnomalyCode(str, Enum):
    TRACKING_DISABLED_WITH_ACTUALS = "TRACKING_DISABLED_WITH_ACTUALS"
    ACTUAL_FINISH_WITHOUT_START = "ACTUAL_FINISH_WITHOUT_START"
    ACTUAL_FINISH_BEFORE_START = "ACTUAL_FINISH_BEFORE_START"
    ACTUAL_END_TIME_WITHOUT_DATE = "ACTUAL_END_TIME_WITHOUT_DATE"
    ACTUAL_START_TIME_WITHOUT_DATE = "ACTUAL_START_TIME_WITHOUT_DATE"
    STATUS_IN_PROGRESS_BUT_FINISHED = "STATUS_IN_PROGRESS_BUT_FINISHED"
    STATUS_IN_PROGRESS_WITHOUT_ACTUAL_START = "STATUS_IN_PROGRESS_WITHOUT_ACTUAL_START"
    STATUS_PLANNED_WITH_ACTUAL_START = "STATUS_PLANNED_WITH_ACTUAL_START"
    STATUS_PLANNED_WITH_ACTUAL_FINISH = "STATUS_PLANNED_WITH_ACTUAL_FINISH"
    STATUS_DELAYED_WITH_ACTUAL_FINISH = "STATUS_DELAYED_WITH_ACTUAL_FINISH"
    STATUS_BLOCKED_WITH_ACTUAL_FINISH = "STATUS_BLOCKED_WITH_ACTUAL_FINISH"
    STATUS_MOVED_WITH_ACTUAL_FINISH = "STATUS_MOVED_WITH_ACTUAL_FINISH"
    STATUS_COMPLETED_BUT_UNFINISHED = "STATUS_COMPLETED_BUT_UNFINISHED"
    CANCELLED_WITH_ACTUAL_FINISH = "CANCELLED_WITH_ACTUAL_FINISH"
    PROGRESS_100_WITHOUT_FINISH = "PROGRESS_100_WITHOUT_FINISH"


class ExecutionStateInvariantError(ValueError):
    """Raised when an execution state invariant is violated during persistence."""

    def __init__(self, message: str, anomaly_code: Optional[ExecutionAnomalyCode] = None):
        super().__init__(message)
        self.anomaly_code = anomaly_code


HARD_INVARIANT_ANOMALIES = frozenset({
    ExecutionAnomalyCode.ACTUAL_FINISH_WITHOUT_START,
    ExecutionAnomalyCode.ACTUAL_FINISH_BEFORE_START,
    ExecutionAnomalyCode.ACTUAL_END_TIME_WITHOUT_DATE,
    ExecutionAnomalyCode.ACTUAL_START_TIME_WITHOUT_DATE,
    ExecutionAnomalyCode.STATUS_IN_PROGRESS_BUT_FINISHED,
    ExecutionAnomalyCode.STATUS_IN_PROGRESS_WITHOUT_ACTUAL_START,
    ExecutionAnomalyCode.STATUS_PLANNED_WITH_ACTUAL_START,
    ExecutionAnomalyCode.STATUS_PLANNED_WITH_ACTUAL_FINISH,
    ExecutionAnomalyCode.STATUS_DELAYED_WITH_ACTUAL_FINISH,
    ExecutionAnomalyCode.STATUS_BLOCKED_WITH_ACTUAL_FINISH,
    ExecutionAnomalyCode.STATUS_MOVED_WITH_ACTUAL_FINISH,
    ExecutionAnomalyCode.CANCELLED_WITH_ACTUAL_FINISH,
    ExecutionAnomalyCode.STATUS_COMPLETED_BUT_UNFINISHED,
})


@dataclass(frozen=True)
class ExecutionPerformanceResult:
    task_id: Optional[int]
    execution_state: ExecutionState
    actual_start: Optional[datetime]
    actual_finish: Optional[datetime]
    actual_elapsed_minutes: int
    actual_work_effort_minutes: int
    reference_start: Optional[datetime]
    reference_finish: Optional[datetime]
    start_variance_minutes: Optional[int]
    finish_variance_minutes: Optional[int]
    start_performance: StartPerformance
    finish_performance: FinishPerformance
    start_variance_display: str
    finish_variance_display: str
    diagnostics: List[str] = field(default_factory=list)
    diagnostic_codes: List[ExecutionDiagnosticCode] = field(default_factory=list)
    anomalies: List[Tuple[ExecutionAnomalyCode, str]] = field(default_factory=list)


def format_duration_human(minutes: int) -> str:
    """Format absolute integer minutes into user-friendly representation."""
    abs_m = abs(minutes)
    if abs_m == 0:
        return "0m"
    days = abs_m // 1440
    rem_m = abs_m % 1440
    hours = rem_m // 60
    mins = rem_m % 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if mins > 0:
        parts.append(f"{mins}m")

    return " ".join(parts) if parts else f"{abs_m}m"


def format_variance_display(
    variance_minutes: Optional[int],
    is_start: bool = True,
    state: ExecutionState = ExecutionState.NOT_TRACKED,
) -> str:
    """Format variance integer minutes into executive display text."""
    if variance_minutes is None:
        if state == ExecutionState.IN_PROGRESS and not is_start:
            return "In progress / Not finished"
        return "Not available"

    action = "Started" if is_start else "Finished"

    if variance_minutes == 0:
        return f"{action} on time"

    dur_str = format_duration_human(variance_minutes)
    days = abs(variance_minutes) // 1440
    if abs(variance_minutes) % 1440 == 0 and days > 0:
        day_str = f"{days} day" if days == 1 else f"{days} days"
    else:
        day_str = dur_str

    if variance_minutes < 0:
        return f"{action} {day_str} early"
    else:
        return f"{action} {day_str} late"


class ExecutionPerformanceService:
    """
    Pure Python canonical domain authority for Actual Execution State & Performance.
    """

    @classmethod
    def derive_execution_state(cls, task: Any) -> ExecutionState:
        """
        Derives canonical execution state from task data.
        Never infers state from progress %, duration, dedication, or schedule dates.
        """
        act_s_d = getattr(task, "actual_start_date", None) if not isinstance(task, dict) else task.get("actual_start_date")
        act_e_d = getattr(task, "actual_end_date", None) if not isinstance(task, dict) else task.get("actual_end_date")

        if not act_s_d:
            return ExecutionState.NOT_TRACKED
        if not act_e_d:
            return ExecutionState.IN_PROGRESS
        return ExecutionState.FINISHED

    @classmethod
    def validate_execution_state(cls, task: Any) -> List[Tuple[ExecutionAnomalyCode, str]]:
        """
        Validates persisted execution fields and classifies invalid states or contradictions.
        """
        anomalies: List[Tuple[ExecutionAnomalyCode, str]] = []

        act_s_d = getattr(task, "actual_start_date", None) if not isinstance(task, dict) else task.get("actual_start_date")
        act_s_t = getattr(task, "actual_start_time", None) if not isinstance(task, dict) else task.get("actual_start_time")
        act_e_d = getattr(task, "actual_end_date", None) if not isinstance(task, dict) else task.get("actual_end_date")
        act_e_t = getattr(task, "actual_end_time", None) if not isinstance(task, dict) else task.get("actual_end_time")

        # Normalize empty strings to None
        act_s_d = str(act_s_d).strip() if act_s_d else None
        act_s_t = str(act_s_t).strip() if act_s_t else None
        act_e_d = str(act_e_d).strip() if act_e_d else None
        act_e_t = str(act_e_t).strip() if act_e_t else None

        status_val = getattr(task, "status", None) if not isinstance(task, dict) else task.get("status")
        if hasattr(status_val, "value"):
            status_val = status_val.value
        status_str = str(status_val).strip().lower() if status_val is not None else ""
        progress = int(getattr(task, "progress", 0) or 0) if not isinstance(task, dict) else int(task.get("progress", 0) or 0)

        act_start = combine_date_time(act_s_d, act_s_t or "00:00") if act_s_d else None
        act_finish = combine_date_time(act_e_d, act_e_t or "23:59") if act_e_d else None

        # 1. Actual Start Time without Date
        if act_s_t and not act_s_d:
            anomalies.append((
                ExecutionAnomalyCode.ACTUAL_START_TIME_WITHOUT_DATE,
                "Actual Start Time is specified without an Actual Start Date.",
            ))

        # 2. Actual End Time without Date
        if act_e_t and not act_e_d:
            anomalies.append((
                ExecutionAnomalyCode.ACTUAL_END_TIME_WITHOUT_DATE,
                "Actual End Time is specified without an Actual End Date.",
            ))

        # 3. Actual Finish without Actual Start
        if act_e_d and not act_s_d:
            anomalies.append((
                ExecutionAnomalyCode.ACTUAL_FINISH_WITHOUT_START,
                "Actual Finish is recorded without an Actual Start Date.",
            ))

        # 4. Actual Finish earlier than Actual Start
        if act_start and act_finish and act_finish < act_start:
            anomalies.append((
                ExecutionAnomalyCode.ACTUAL_FINISH_BEFORE_START,
                f"Actual Finish ({act_finish}) is earlier than Actual Start ({act_start}).",
            ))

        # 5. Status Planned contradictions
        if status_str == "planned":
            if act_s_d:
                anomalies.append((
                    ExecutionAnomalyCode.STATUS_PLANNED_WITH_ACTUAL_START,
                    "Task status is 'Planned' but an Actual Start date is populated. Planned tasks cannot carry actual execution history. Clear Actual tracking or change task status to In Progress.",
                ))
            if act_e_d:
                anomalies.append((
                    ExecutionAnomalyCode.STATUS_PLANNED_WITH_ACTUAL_FINISH,
                    "Task status is 'Planned' but an Actual Finish date is populated. Planned tasks cannot carry actual execution history.",
                ))

        # 6. Status In Progress contradictions
        if status_str in ("in progress", "in_progress"):
            if not act_s_d:
                anomalies.append((
                    ExecutionAnomalyCode.STATUS_IN_PROGRESS_WITHOUT_ACTUAL_START,
                    "Task status is 'In Progress' but Actual Start date is missing. An In Progress task requires an explicit factual Actual Start date.",
                ))
            if act_e_d:
                anomalies.append((
                    ExecutionAnomalyCode.STATUS_IN_PROGRESS_BUT_FINISHED,
                    "Task status is 'In Progress' but an Actual Finish date is persisted. In Progress tasks cannot have an Actual Finish date.",
                ))

        # 8. Status Delayed contradiction
        if status_str == "delayed" and act_e_d:
            anomalies.append((
                ExecutionAnomalyCode.STATUS_DELAYED_WITH_ACTUAL_FINISH,
                "Task status is 'Delayed' but an Actual Finish date is persisted. An active Delayed task cannot have an Actual Finish date.",
            ))

        # 9. Status Blocked contradiction
        if status_str == "blocked" and act_e_d:
            anomalies.append((
                ExecutionAnomalyCode.STATUS_BLOCKED_WITH_ACTUAL_FINISH,
                "Task status is 'Blocked' but an Actual Finish date is persisted. An active Blocked task cannot have an Actual Finish date.",
            ))

        # 10. Status Moved contradiction
        if status_str == "moved" and act_e_d:
            anomalies.append((
                ExecutionAnomalyCode.STATUS_MOVED_WITH_ACTUAL_FINISH,
                "Task status is 'Moved' but an Actual Finish date is persisted. A Moved task cannot have an Actual Finish date.",
            ))

        # 11. Status Cancelled with actual finish
        if status_str == "cancelled" and act_e_d:
            anomalies.append((
                ExecutionAnomalyCode.CANCELLED_WITH_ACTUAL_FINISH,
                "Task status is 'Cancelled' but carries a persisted Actual Finish date.",
            ))

        # 12. Status Completed but unfinished (if tracked)
        if status_str == "completed" and act_s_d and not act_e_d:
            anomalies.append((
                ExecutionAnomalyCode.STATUS_COMPLETED_BUT_UNFINISHED,
                "Task status is 'Completed' but Actual Execution is still open (no Actual Finish date).",
            ))

        # 13. Progress = 100% without actual finish (operational advisory)
        if progress == 100 and act_s_d and not act_e_d:
            anomalies.append((
                ExecutionAnomalyCode.PROGRESS_100_WITHOUT_FINISH,
                "Progress is 100% but Actual Execution has not been explicitly finished.",
            ))

        return anomalies

    @classmethod
    def validate_execution_invariants(cls, task: Any) -> List[Tuple[ExecutionAnomalyCode, str]]:
        """
        Validates execution invariants that must not be violated on database write.
        Returns a list of (ExecutionAnomalyCode, message) for any hard invariant violations.
        """
        all_anomalies = cls.validate_execution_state(task)
        return [(code, msg) for code, msg in all_anomalies if code in HARD_INVARIANT_ANOMALIES]

    @classmethod
    def assert_valid_execution_state(cls, task: Any) -> None:
        """
        Asserts that task obeys execution state invariants.
        Raises ExecutionStateInvariantError if any hard invariant is violated.
        """
        violations = cls.validate_execution_invariants(task)
        if violations:
            code, msg = violations[0]
            raise ExecutionStateInvariantError(
                f"Execution state invariant violation [{code.value}]: {msg}",
                anomaly_code=code,
            )

    @classmethod
    def calculate_actual_elapsed(cls, task: Any, now: Optional[datetime] = None) -> int:
        """
        Calculates full calendar-time actual elapsed minutes.
        Never reduced by project working calendar.
        """
        if now is None:
            now = get_current_datetime()

        act_s_d = getattr(task, "actual_start_date", None) if not isinstance(task, dict) else task.get("actual_start_date")
        act_s_t = getattr(task, "actual_start_time", None) if not isinstance(task, dict) else task.get("actual_start_time")
        act_e_d = getattr(task, "actual_end_date", None) if not isinstance(task, dict) else task.get("actual_end_date")
        act_e_t = getattr(task, "actual_end_time", None) if not isinstance(task, dict) else task.get("actual_end_time")

        if not act_s_d:
            return 0

        act_start = combine_date_time(act_s_d, act_s_t or "08:00")
        if not act_start:
            return 0

        if act_e_d:
            act_finish = combine_date_time(act_e_d, act_e_t or "17:00")
            if act_finish:
                return max(0, int((act_finish - act_start).total_seconds() // 60))

        # In progress: calendar elapsed from actual start to canonical now
        return max(0, int((now - act_start).total_seconds() // 60))

    @classmethod
    def calculate_start_variance(
        cls,
        actual_start: Optional[datetime],
        reference_start: Optional[datetime],
    ) -> Optional[int]:
        """
        Execution Start Variance = Actual Start - Reference Start (in integer minutes).
        """
        if actual_start is None or reference_start is None:
            return None
        return int((actual_start - reference_start).total_seconds() // 60)

    @classmethod
    def calculate_finish_variance(
        cls,
        actual_finish: Optional[datetime],
        reference_finish: Optional[datetime],
    ) -> Optional[int]:
        """
        Execution Finish Variance = Actual Finish - Reference Finish (in integer minutes).
        Returns None while execution is in progress.
        """
        if actual_finish is None or reference_finish is None:
            return None
        return int((actual_finish - reference_finish).total_seconds() // 60)

    @classmethod
    def analyze_task_execution(
        cls,
        task: Any,
        reference_start: Optional[Union[datetime, date, str]] = None,
        reference_finish: Optional[Union[datetime, date, str]] = None,
        now: Optional[datetime] = None,
    ) -> ExecutionPerformanceResult:
        """
        Comprehensive pure-Python analysis of task execution against reference schedule.
        """
        if now is None:
            now = get_current_datetime()

        task_id = getattr(task, "id", None) if not isinstance(task, dict) else task.get("id")

        # 1. State derivation and validation
        exec_state = cls.derive_execution_state(task)
        anomalies = cls.validate_execution_state(task)

        # 2. Extract actual timestamps
        act_s_d = getattr(task, "actual_start_date", None) if not isinstance(task, dict) else task.get("actual_start_date")
        act_s_t = getattr(task, "actual_start_time", None) if not isinstance(task, dict) else task.get("actual_start_time")
        act_e_d = getattr(task, "actual_end_date", None) if not isinstance(task, dict) else task.get("actual_end_date")
        act_e_t = getattr(task, "actual_end_time", None) if not isinstance(task, dict) else task.get("actual_end_time")
        act_dur = int(getattr(task, "actual_duration", 0) or 0) if not isinstance(task, dict) else int(task.get("actual_duration", 0) or 0)

        actual_start_dt = combine_date_time(act_s_d, act_s_t or "08:00") if act_s_d else None
        actual_finish_dt = combine_date_time(act_e_d, act_e_t or "17:00") if act_e_d else None

        # 3. Extract reference dates (default to planned / CPM start and finish)
        ref_s_dt = cls._parse_dt(reference_start)
        if ref_s_dt is None:
            cpm_es = getattr(task, "cpm_earliest_start", None) if not isinstance(task, dict) else task.get("cpm_earliest_start")
            p_date = getattr(task, "planned_date", None) if not isinstance(task, dict) else task.get("planned_date")
            p_time = getattr(task, "planned_start_time", None) if not isinstance(task, dict) else task.get("planned_start_time")
            ref_s_dt = cls._parse_dt(cpm_es) or combine_date_time(p_date, p_time or "08:00")

        ref_e_dt = cls._parse_dt(reference_finish)
        if ref_e_dt is None:
            cpm_ef = getattr(task, "cpm_earliest_finish", None) if not isinstance(task, dict) else task.get("cpm_earliest_finish")
            d_date = getattr(task, "due_date", None) if not isinstance(task, dict) else task.get("due_date")
            p_e_time = getattr(task, "planned_end_time", None) if not isinstance(task, dict) else task.get("planned_end_time")
            ref_e_dt = cls._parse_dt(cpm_ef) or combine_date_time(d_date, p_e_time or "17:00")

        # 4. Calculate actual elapsed
        elapsed_minutes = cls.calculate_actual_elapsed(task, now=now)

        # 5. Calculate Execution Start Variance
        start_var_minutes = cls.calculate_start_variance(actual_start_dt, ref_s_dt)
        start_perf = StartPerformance.NOT_STARTED
        if start_var_minutes is not None:
            if start_var_minutes < 0:
                start_perf = StartPerformance.STARTED_EARLY
            elif start_var_minutes == 0:
                start_perf = StartPerformance.STARTED_ON_TIME
            else:
                start_perf = StartPerformance.STARTED_LATE

        start_var_disp = format_variance_display(start_var_minutes, is_start=True, state=exec_state)

        # 6. Calculate Execution Finish Variance
        finish_var_minutes = cls.calculate_finish_variance(actual_finish_dt, ref_e_dt)
        finish_perf = FinishPerformance.UNAVAILABLE
        if exec_state == ExecutionState.IN_PROGRESS:
            finish_perf = FinishPerformance.IN_PROGRESS
        elif exec_state == ExecutionState.FINISHED and finish_var_minutes is not None:
            if finish_var_minutes < 0:
                finish_perf = FinishPerformance.FINISHED_EARLY
            elif finish_var_minutes == 0:
                finish_perf = FinishPerformance.FINISHED_ON_TIME
            else:
                finish_perf = FinishPerformance.FINISHED_LATE

        finish_var_disp = format_variance_display(finish_var_minutes, is_start=False, state=exec_state)

        # 7. Check constraint contradictions & compile diagnostics
        diagnostics: List[str] = []
        diag_codes: List[ExecutionDiagnosticCode] = []

        if actual_start_dt is not None:
            c_diag = cls.check_constraint_actual_contradictions(task, actual_start_dt, actual_finish_dt)
            for code, msg in c_diag:
                diag_codes.append(code)
                diagnostics.append(msg)

            if start_perf == StartPerformance.STARTED_EARLY:
                diag_codes.append(ExecutionDiagnosticCode.ACTUAL_START_BEFORE_PLAN)
                diagnostics.append(f"Actual execution started before current planned start ({start_var_disp}).")
            elif start_perf == StartPerformance.STARTED_LATE:
                diag_codes.append(ExecutionDiagnosticCode.ACTUAL_START_AFTER_PLAN)
                diagnostics.append(f"Actual execution started after current planned start ({start_var_disp}).")

        return ExecutionPerformanceResult(
            task_id=task_id,
            execution_state=exec_state,
            actual_start=actual_start_dt,
            actual_finish=actual_finish_dt,
            actual_elapsed_minutes=elapsed_minutes,
            actual_work_effort_minutes=act_dur,
            reference_start=ref_s_dt,
            reference_finish=ref_e_dt,
            start_variance_minutes=start_var_minutes,
            finish_variance_minutes=finish_var_minutes,
            start_performance=start_perf,
            finish_performance=finish_perf,
            start_variance_display=start_var_disp,
            finish_variance_display=finish_var_disp,
            diagnostics=diagnostics,
            diagnostic_codes=diag_codes,
            anomalies=anomalies,
        )

    @classmethod
    def check_constraint_actual_contradictions(
        cls,
        task: Any,
        actual_start: Optional[datetime],
        actual_finish: Optional[datetime],
    ) -> List[Tuple[ExecutionDiagnosticCode, str]]:
        """
        Detects schedule-control contradictions where historical execution contradicts
        forecast scheduling constraints without altering Actual dates.
        """
        results: List[Tuple[ExecutionDiagnosticCode, str]] = []
        if actual_start is None:
            return results

        c_type = getattr(task, "constraint_type", None) if not isinstance(task, dict) else task.get("constraint_type")
        c_dt_raw = getattr(task, "constraint_date", None) or getattr(task, "constraint_datetime", None) if not isinstance(task, dict) else (task.get("constraint_date") or task.get("constraint_datetime"))
        if hasattr(c_type, "value"):
            c_type = c_type.value
        c_type_str = str(c_type).upper() if c_type else ""
        c_dt = cls._parse_dt(c_dt_raw)

        if not c_type_str or c_dt is None:
            return results

        c_d = c_dt.date()
        act_s_d = actual_start.date()
        act_f_d = actual_finish.date() if actual_finish else None

        # SNET: Start No Earlier Than
        if c_type_str in ("SNET", "START_NO_EARLIER_THAN"):
            if act_s_d < c_d:
                results.append((
                    ExecutionDiagnosticCode.ACTUAL_START_BEFORE_SNET,
                    f"Actual execution started ({act_s_d}) before the Start No Earlier Than constraint ({c_d}).",
                ))

        # SNLT: Start No Later Than
        elif c_type_str in ("SNLT", "START_NO_LATER_THAN"):
            if act_s_d > c_d:
                results.append((
                    ExecutionDiagnosticCode.ACTUAL_START_AFTER_SNLT,
                    f"Actual execution started ({act_s_d}) after the Start No Later Than constraint ({c_d}).",
                ))

        # MSO: Must Start On
        elif c_type_str in ("MSO", "MUST_START_ON"):
            if act_s_d != c_d:
                results.append((
                    ExecutionDiagnosticCode.ACTUAL_START_DIFFERS_FROM_MSO,
                    f"Actual execution started ({act_s_d}) on a different date than Must Start On constraint ({c_d}).",
                ))

        # FNET: Finish No Earlier Than
        elif c_type_str in ("FNET", "FINISH_NO_EARLIER_THAN"):
            if act_f_d and act_f_d < c_d:
                results.append((
                    ExecutionDiagnosticCode.ACTUAL_FINISH_BEFORE_FNET,
                    f"Actual execution finished ({act_f_d}) before Finish No Earlier Than constraint ({c_d}).",
                ))

        # FNLT: Finish No Later Than
        elif c_type_str in ("FNLT", "FINISH_NO_LATER_THAN"):
            if act_f_d and act_f_d > c_d:
                results.append((
                    ExecutionDiagnosticCode.ACTUAL_FINISH_AFTER_FNLT,
                    f"Actual execution finished ({act_f_d}) after Finish No Later Than constraint ({c_d}).",
                ))

        # MFO: Must Finish On
        elif c_type_str in ("MFO", "MUST_FINISH_ON"):
            if act_f_d and act_f_d != c_d:
                results.append((
                    ExecutionDiagnosticCode.ACTUAL_FINISH_DIFFERS_FROM_MFO,
                    f"Actual execution finished ({act_f_d}) on a different date than Must Finish On constraint ({c_d}).",
                ))

        return results

    @classmethod
    def _parse_dt(cls, val: Any) -> Optional[datetime]:
        if val is None:
            return None
        if isinstance(val, datetime):
            return val
        if isinstance(val, date):
            return datetime.combine(val, time(8, 0))
        val_str = str(val).strip()
        if not val_str:
            return None
        try:
            return datetime.fromisoformat(val_str)
        except Exception:
            try:
                return datetime.strptime(val_str[:10], "%Y-%m-%d")
            except Exception:
                return None
