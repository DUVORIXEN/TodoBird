"""
Schedule Constraint, Deadline & Project Calendar Service — Phase 2E.

Pure Python, Qt-independent, deterministic, enterprise analytical authority.
Supports:
- Constraint types: ASAP, ALAP, SNET, SNLT, FNET, FNLT, MSO, MFO
- Deadlines (monitoring commitment, separate from constraints)
- Project calendars (working weekdays Mon-Sun, holiday/overtime exceptions)
- Structured diagnostic evaluation
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta
from enum import Enum
from typing import Dict, List, Set, Tuple, Optional, Any, Sequence, Union

from todo_bird_app.models.task import Task


class ConstraintType(str, Enum):
    ASAP = "ASAP"   # As Soon As Possible (Default)
    ALAP = "ALAP"   # As Late As Possible
    SNET = "SNET"   # Start No Earlier Than
    SNLT = "SNLT"   # Start No Later Than
    FNET = "FNET"   # Finish No Earlier Than
    FNLT = "FNLT"   # Finish No Later Than
    MSO = "MSO"     # Must Start On
    MFO = "MFO"     # Must Finish On

    @classmethod
    def from_str(cls, val: Any) -> "ConstraintType":
        if isinstance(val, cls):
            return val
        if not val:
            return cls.ASAP
        raw = str(val).strip().upper()
        aliases = {
            "AS SOON AS POSSIBLE": cls.ASAP,
            "AS LATE AS POSSIBLE": cls.ALAP,
            "START NO EARLIER THAN": cls.SNET,
            "START NO LATER THAN": cls.SNLT,
            "FINISH NO EARLIER THAN": cls.FNET,
            "FINISH NO LATER THAN": cls.FNLT,
            "MUST START ON": cls.MSO,
            "MUST FINISH ON": cls.MFO,
        }
        if raw in aliases:
            return aliases[raw]
        try:
            return cls(raw)
        except ValueError:
            return cls.ASAP


CONSTRAINT_DISPLAY_NAMES: Dict[ConstraintType, str] = {
    ConstraintType.ASAP: "As Soon As Possible",
    ConstraintType.ALAP: "As Late As Possible",
    ConstraintType.SNET: "Start No Earlier Than",
    ConstraintType.SNLT: "Start No Later Than",
    ConstraintType.FNET: "Finish No Earlier Than",
    ConstraintType.FNLT: "Finish No Later Than",
    ConstraintType.MSO: "Must Start On",
    ConstraintType.MFO: "Must Finish On",
}

CONSTRAINT_TOOLTIPS: Dict[ConstraintType, str] = {
    ConstraintType.ASAP: "Schedule as early as dependencies allow.",
    ConstraintType.ALAP: "Schedule as late as possible without delaying successors.",
    ConstraintType.SNET: "Do not schedule this task before this date.",
    ConstraintType.SNLT: "Task should start no later than this date.",
    ConstraintType.FNET: "Task should not finish before this date.",
    ConstraintType.FNLT: "Task should finish no later than this date.",
    ConstraintType.MSO: "Task must start exactly on this date.",
    ConstraintType.MFO: "Task must finish exactly on this date.",
}


def get_constraint_display_name(ctype: Union[ConstraintType, str]) -> str:
    ct = ConstraintType.from_str(ctype) if not isinstance(ctype, ConstraintType) else ctype
    return CONSTRAINT_DISPLAY_NAMES.get(ct, str(ct.value))


def get_constraint_tooltip(ctype: Union[ConstraintType, str]) -> str:
    ct = ConstraintType.from_str(ctype) if not isinstance(ctype, ConstraintType) else ctype
    return CONSTRAINT_TOOLTIPS.get(ct, "")


def is_date_required(ctype: Union[ConstraintType, str]) -> bool:
    ct = ConstraintType.from_str(ctype) if not isinstance(ctype, ConstraintType) else ctype
    return ct not in (ConstraintType.ASAP, ConstraintType.ALAP)


def parse_constraint_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time(0, 0))
    val_str = str(value).strip()
    if not val_str:
        return None
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(val_str[:len(datetime.now().strftime(fmt))], fmt)
        except Exception:
            try:
                return datetime.strptime(val_str, fmt)
            except Exception:
                continue
    return None


@dataclass(frozen=True)
class ConstraintSpec:
    task_id: int
    constraint_type: ConstraintType = ConstraintType.ASAP
    constraint_datetime: Optional[datetime] = None
    deadline_datetime: Optional[datetime] = None


@dataclass(frozen=True)
class CalendarException:
    date_str: str                # YYYY-MM-DD
    is_working: bool = False     # False = Non-working holiday, True = Special working day
    name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date_str,
            "is_working": 1 if self.is_working else 0,
            "name": self.name,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalendarException":
        d_str = str(data.get("date") or data.get("exception_date") or "")[:10]
        raw_w = data.get("is_working", 0)
        is_w = bool(raw_w is True or raw_w == 1 or str(raw_w).lower() in ("true", "1"))
        name = str(data.get("name", ""))
        return cls(date_str=d_str, is_working=is_w, name=name)


@dataclass(frozen=True)
class ProjectCalendarSpec:
    project_id: Optional[int] = None
    working_weekdays: Tuple[int, ...] = (0, 1, 2, 3, 4)  # Mon-Fri
    exceptions: Tuple[CalendarException, ...] = field(default_factory=tuple)

    @property
    def working_weekdays_set(self) -> Set[int]:
        return set(self.working_weekdays)

    @property
    def holidays_set(self) -> Set[str]:
        return {e.date_str for e in self.exceptions if not e.is_working}

    @property
    def working_overrides_set(self) -> Set[str]:
        return {e.date_str for e in self.exceptions if e.is_working}

    def is_working_day(self, target: Union[date, datetime, str]) -> bool:
        if isinstance(target, datetime):
            d = target.date()
        elif isinstance(target, date):
            d = target
        else:
            try:
                d = datetime.strptime(str(target)[:10], "%Y-%m-%d").date()
            except Exception:
                return False

        iso = d.strftime("%Y-%m-%d")
        exception_decision = None
        for exc in self.exceptions:
            if exc.date_str == iso:
                exception_decision = bool(exc.is_working)
        if exception_decision is not None:
            return exception_decision
        return d.weekday() in self.working_weekdays_set


@dataclass(frozen=True)
class ConstraintEvaluation:
    task_id: int
    constraint_type: ConstraintType
    constraint_datetime: Optional[datetime]
    is_satisfied: bool
    is_conflicted: bool
    conflict_message: Optional[str] = None


@dataclass(frozen=True)
class DeadlineEvaluation:
    task_id: int
    deadline_datetime: Optional[datetime]
    forecast_finish: Optional[datetime]
    variance_minutes: Optional[int]    # Forecast Finish - Deadline (Positive = Late/Missed)
    is_missed: bool
    is_at_risk: bool


@dataclass(frozen=True)
class ProjectConstraintSummary:
    total_tasks: int
    constrained_tasks: int
    constraint_conflicts_count: int
    deadline_missed_count: int
    deadline_at_risk_count: int
    unconstrained_critical_count: int


def format_deadline_variance(minutes: Optional[int]) -> str:
    """
    Format deadline variance:
    Positive -> '+1d 2h' (Missed/Late)
    Negative -> '-3d' (Ahead of deadline)
    Zero -> '0m' (Exact on deadline)
    None -> '—'
    """
    if minutes is None:
        return "—"
    if minutes == 0:
        return "0m"

    sign = "+" if minutes > 0 else "-"
    abs_m = abs(int(minutes))

    if abs_m < 60:
        return f"{sign}{abs_m}m"
    if abs_m < 1440:
        h = abs_m // 60
        rem_m = abs_m % 60
        return f"{sign}{h}h {rem_m}m" if rem_m else f"{sign}{h}h"

    d = abs_m // 1440
    rem = abs_m % 1440
    h = rem // 60
    m = rem % 60

    parts = [f"{d}d"]
    if h > 0:
        parts.append(f"{h}h")
    if m > 0:
        parts.append(f"{m}m")
    return f"{sign}{' '.join(parts)}"


class ScheduleConstraintService:
    """
    Central analytical service for schedule constraints, deadlines, and project calendar.
    """

    @classmethod
    def evaluate_task_deadline(
        cls,
        task: Task,
        cpm_finish: Optional[datetime] = None,
        total_float_minutes: Optional[int] = None,
    ) -> DeadlineEvaluation:
        tid = int(task.id or 0)
        raw_deadline = getattr(task, "deadline_datetime", None)
        d_dt = parse_constraint_datetime(raw_deadline)

        if d_dt is None or cpm_finish is None:
            return DeadlineEvaluation(
                task_id=tid,
                deadline_datetime=d_dt,
                forecast_finish=cpm_finish,
                variance_minutes=None,
                is_missed=False,
                is_at_risk=False,
            )

        # Variance = Forecast Finish - Deadline (in minutes)
        var_minutes = int((cpm_finish - d_dt).total_seconds() // 60)
        is_missed = (var_minutes > 0)
        is_at_risk = False  # Defer arbitrary business thresholds; deterministic SAFE vs MISSED

        return DeadlineEvaluation(
            task_id=tid,
            deadline_datetime=d_dt,
            forecast_finish=cpm_finish,
            variance_minutes=var_minutes,
            is_missed=is_missed,
            is_at_risk=is_at_risk,
        )

    @classmethod
    def evaluate_task_constraint(
        cls,
        task: Task,
        cpm_start: Optional[datetime] = None,
        cpm_finish: Optional[datetime] = None,
        dep_bound_start: Optional[datetime] = None,
        dep_bound_finish: Optional[datetime] = None,
    ) -> ConstraintEvaluation:
        tid = int(task.id or 0)
        raw_type = getattr(task, "constraint_type", "ASAP")
        ctype = ConstraintType.from_str(raw_type)
        c_dt = parse_constraint_datetime(getattr(task, "constraint_datetime", None))

        if ctype in (ConstraintType.ASAP, ConstraintType.ALAP):
            return ConstraintEvaluation(
                task_id=tid,
                constraint_type=ctype,
                constraint_datetime=None,
                is_satisfied=True,
                is_conflicted=False,
            )

        if c_dt is None:
            return ConstraintEvaluation(
                task_id=tid,
                constraint_type=ctype,
                constraint_datetime=None,
                is_satisfied=False,
                is_conflicted=True,
                conflict_message=f"Constraint {ctype.value} requires a valid constraint date/time.",
            )

        if cpm_start is None or cpm_finish is None:
            return ConstraintEvaluation(
                task_id=tid,
                constraint_type=ctype,
                constraint_datetime=c_dt,
                is_satisfied=False,
                is_conflicted=False,
            )

        # Evaluate specific constraint bounds
        is_conflicted = False
        msg = None

        if ctype == ConstraintType.SNET:
            # SNET: ES >= c_dt
            pass

        elif ctype == ConstraintType.SNLT:
            # SNLT: ES <= c_dt. Conflict if dependencies force ES > c_dt
            if dep_bound_start is not None and dep_bound_start > c_dt:
                is_conflicted = True
                msg = f"Dependency predecessor logic forces start ({dep_bound_start}) after SNLT bound ({c_dt})."

        elif ctype == ConstraintType.FNET:
            # FNET: EF >= c_dt
            pass

        elif ctype == ConstraintType.FNLT:
            # FNLT: EF <= c_dt. Conflict if dependencies force EF > c_dt
            if dep_bound_finish is not None and dep_bound_finish > c_dt:
                is_conflicted = True
                msg = f"Dependency predecessor logic forces finish ({dep_bound_finish}) after FNLT bound ({c_dt})."

        elif ctype == ConstraintType.MSO:
            # MSO: ES = c_dt. Conflict if dep_bound_start > c_dt
            if dep_bound_start is not None and dep_bound_start > c_dt:
                is_conflicted = True
                msg = f"Predecessor dependencies require start no earlier than {dep_bound_start}, violating Must Start On {c_dt}."

        elif ctype == ConstraintType.MFO:
            # MFO: EF = c_dt. Conflict if dep_bound_finish > c_dt
            if dep_bound_finish is not None and dep_bound_finish > c_dt:
                is_conflicted = True
                msg = f"Predecessor dependencies require finish no earlier than {dep_bound_finish}, violating Must Finish On {c_dt}."

        return ConstraintEvaluation(
            task_id=tid,
            constraint_type=ctype,
            constraint_datetime=c_dt,
            is_satisfied=not is_conflicted,
            is_conflicted=is_conflicted,
            conflict_message=msg,
        )
