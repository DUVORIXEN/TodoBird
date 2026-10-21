"""
Professional CPM (Critical Path Method) Scheduling Service — Phase 2A.

Pure Python, Qt-independent, deterministic, non-destructive enterprise scheduling engine.

Calculates:
- Canonical schedule network graph
- Forward pass CPM dates (Earliest Start, Earliest Finish)
- Backward pass CPM dates (Latest Start, Latest Finish)
- Total Float (TF = LS - ES = LF - EF)
- Free Float (FF = min(ES(successors)) - EF)
- True Critical Path classification (TF == 0)
- Multiple critical paths support
- Cycle diagnostics (non-destructive, zero mutation)
- Scheduling diagnostics (unscheduled tasks, invalid durations, missing refs)

Authorities:
- Planned Elapsed Span (estimated_duration) = raw elapsed minutes without a project calendar,
  and working-calendar minutes when a project calendar is supplied.
- FS (Finish-to-Start) dependencies with optional lag
- O(V + E) iterative topological graph traversal (no recursion limit risk)
"""

from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta
from enum import Enum
from typing import Dict, List, Set, Tuple, Optional, Any, Sequence, Union

from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.services.schedule_constraint_service import (
    ConstraintType,
    parse_constraint_datetime,
    ProjectCalendarSpec,
)
from todo_bird_app.services.schedule_calendar_service import (
    ScheduleCalendar,
    add_working_days_preserve_time,
    add_working_minutes,
    next_working_datetime,
    previous_working_datetime,
    subtract_working_days_preserve_time,
    subtract_working_minutes,
    working_minutes_between,
)


class DiagnosticCode(str, Enum):
    DEPENDENCY_CYCLE = "DEPENDENCY_CYCLE"
    MISSING_TASK_REFERENCE = "MISSING_TASK_REFERENCE"
    CROSS_PROJECT_DEPENDENCY = "CROSS_PROJECT_DEPENDENCY"
    UNSCHEDULED_NO_START = "UNSCHEDULED_NO_START"
    UNSCHEDULED_NO_DURATION = "UNSCHEDULED_NO_DURATION"
    INVALID_DURATION = "INVALID_DURATION"
    NEGATIVE_FLOAT = "NEGATIVE_FLOAT"
    DISCONNECTED_COMPONENT = "DISCONNECTED_COMPONENT"
    SELF_REFERENCE = "SELF_REFERENCE"
    EARLIER_THAN_DEPENDENCY = "EARLIER_THAN_DEPENDENCY"
    INVALID_DEPENDENCY_TYPE = "INVALID_DEPENDENCY_TYPE"
    INVALID_LAG = "INVALID_LAG"
    DUPLICATE_DEPENDENCY = "DUPLICATE_DEPENDENCY"
    # Phase 2E Schedule Constraints, Deadlines & Calendar Diagnostics
    CONSTRAINT_CONFLICT = "CONSTRAINT_CONFLICT"
    CONSTRAINT_DATE_MISSING = "CONSTRAINT_DATE_MISSING"
    INVALID_CONSTRAINT_TYPE = "INVALID_CONSTRAINT_TYPE"
    DEADLINE_MISSED = "DEADLINE_MISSED"
    DEADLINE_AT_RISK = "DEADLINE_AT_RISK"
    CALENDAR_CONFLICT = "CALENDAR_CONFLICT"
    CALENDAR_UNAVAILABLE = "CALENDAR_UNAVAILABLE"


class DependencyType(str, Enum):
    FS = "FS"
    SS = "SS"
    FF = "FF"
    SF = "SF"


@dataclass(frozen=True)
class DependencySpec:
    predecessor_id: int
    successor_id: Optional[int] = None
    dependency_type: DependencyType = DependencyType.FS
    lag_minutes: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "predecessor_id": self.predecessor_id,
            "type": self.dependency_type.value,
            "lag_minutes": self.lag_minutes,
        }
        if self.successor_id is not None:
            d["successor_id"] = self.successor_id
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any], successor_id: Optional[int] = None) -> "DependencySpec":
        raw_pred = data.get("predecessor_id") if "predecessor_id" in data else (data.get("id") if "id" in data else data.get("task_id"))
        try:
            pred_id = int(raw_pred) if raw_pred is not None else -1
        except (TypeError, ValueError):
            pred_id = -1
        succ_id = int(data["successor_id"]) if data.get("successor_id") is not None else successor_id
        raw_type = str(data.get("type") or data.get("dependency_type") or "FS").upper().strip()
        try:
            dep_type = DependencyType(raw_type)
        except ValueError:
            dep_type = DependencyType.FS
        try:
            lag = int(data.get("lag_minutes", 0))
        except (TypeError, ValueError):
            lag = 0
        return cls(
            predecessor_id=pred_id,
            successor_id=succ_id,
            dependency_type=dep_type,
            lag_minutes=lag,
        )


@dataclass(frozen=True)
class ScheduleNode:
    task_id: int
    title: str = ""
    project_id: Optional[int] = None
    planned_start: Optional[datetime] = None
    planned_finish: Optional[datetime] = None
    duration_minutes: int = 0
    status: Optional[str] = None
    is_milestone: bool = False
    is_completed: bool = False
    is_cancelled: bool = False
    predecessors: Tuple[int, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScheduleEdge:
    predecessor_id: int
    successor_id: int
    dependency_type: DependencyType = DependencyType.FS
    lag_minutes: int = 0


@dataclass(frozen=True)
class ScheduleDiagnostic:
    code: DiagnosticCode
    task_id: Optional[int]
    message: str
    related_task_ids: Tuple[int, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ScheduleNodeResult:
    task_id: int
    earliest_start: Optional[datetime]
    earliest_finish: Optional[datetime]
    latest_start: Optional[datetime]
    latest_finish: Optional[datetime]
    total_float_minutes: Optional[int]
    free_float_minutes: Optional[int]
    is_critical: bool
    schedulable: bool
    diagnostic_codes: Tuple[DiagnosticCode, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SchedulingResult:
    project_id: Optional[int]
    project_start: Optional[datetime]
    project_finish: Optional[datetime]
    nodes: Dict[int, ScheduleNodeResult]
    critical_task_ids: Tuple[int, ...]
    critical_paths: Tuple[Tuple[int, ...], ...]
    diagnostics: Tuple[ScheduleDiagnostic, ...]
    has_cycles: bool
    cycle_task_ids: Tuple[int, ...]
    is_complete: bool

    def get_node(self, task_id: int) -> Optional[ScheduleNodeResult]:
        return self.nodes.get(task_id)

    @property
    def total_tasks(self) -> int:
        return len(self.nodes)

    @property
    def schedulable_tasks(self) -> int:
        return sum(1 for n in self.nodes.values() if n.schedulable)


def parse_lag_duration(text: Any) -> Optional[int]:
    """
    Parses project manager lag/lead expressions into minutes.
    Bounded range: -525600 to +525600 minutes (approx ±1 year).
    Supported units:
        d / day / days (1d = 1440m)
        h / hr / hrs / hour / hours (1h = 60m)
        m / min / mins / minute / minutes (1m)
    Examples:
        0 -> 0
        "30m" -> 30
        "2h" -> 120
        "1d" -> 1440
        "1d 2h" -> 1560
        "-2h" -> -120
        "-1d" -> -1440
        "+1d 4h 30m" -> 1710
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        val = int(text)
        if -525600 <= val <= 525600:
            return val
        return None

    raw = str(text).strip()
    if not raw:
        return 0
    if raw in ("0", "+0", "-0", "0m", "0h", "0d"):
        return 0

    is_negative = raw.startswith("-")
    if raw.startswith("+") or raw.startswith("-"):
        raw = raw[1:].strip()

    tokens = re.findall(r"(\d+(?:\.\d+)?)\s*([a-zA-Z]*)", raw)
    if not tokens:
        return None

    total_minutes = 0.0
    for num_str, unit in tokens:
        try:
            val = float(num_str)
        except ValueError:
            return None
        unit = unit.lower().strip()
        if unit in ("d", "day", "days"):
            total_minutes += val * 1440
        elif unit in ("h", "hr", "hrs", "hour", "hours"):
            total_minutes += val * 60
        elif unit in ("m", "min", "mins", "minute", "minutes", ""):
            total_minutes += val
        else:
            return None

    result = int(round(-total_minutes if is_negative else total_minutes))
    if -525600 <= result <= 525600:
        return result
    return None


def format_lag_duration(minutes: Optional[int]) -> str:
    """
    Formats lag/lead minutes into signed PM friendly format.
    0 -> "0m"
    120 -> "+2h"
    -120 -> "-2h"
    1440 -> "+1d"
    1560 -> "+1d 2h"
    """
    if minutes is None or minutes == 0:
        return "0m"
    sign = "-" if minutes < 0 else "+"
    abs_m = abs(int(minutes))
    if abs_m < 60:
        return f"{sign}{abs_m}m"
    if abs_m < 1440:
        h = abs_m // 60
        rem = abs_m % 60
        return f"{sign}{h}h {rem}m" if rem else f"{sign}{h}h"
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


def format_concise_dependency(spec: Union[DependencySpec, Dict[str, Any], int]) -> str:
    """
    Formats concise dependency string e.g. '12FS+1d', '5SS', '8FF-2h', '3SF'.
    """
    if isinstance(spec, int):
        return f"{spec}FS"
    if isinstance(spec, dict):
        pred_id = spec.get("predecessor_id") or spec.get("id") or 0
        dep_type = str(spec.get("type") or "FS").upper()
        lag = int(spec.get("lag_minutes", 0))
    elif isinstance(spec, DependencySpec):
        pred_id = spec.predecessor_id
        dep_type = spec.dependency_type.value
        lag = spec.lag_minutes
    else:
        return str(spec)

    lag_str = format_lag_duration(lag) if lag != 0 else ""
    return f"{pred_id}{dep_type}{lag_str}"


def parse_dependency_specs(raw: Any, successor_id: Optional[int] = None) -> List[DependencySpec]:
    """
    Decodes raw dependency data into canonical DependencySpec list.
    Supports:
        - List of ints [1, 2, 3] (legacy FS/0)
        - List of dicts [{'predecessor_id': 1, 'type': 'SS', 'lag_minutes': 60}]
        - JSON string containing list of ints or dicts
        - List of DependencySpec objects
    Deduplicates predecessor_id deterministically (last spec wins).
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if not isinstance(raw, (list, tuple, set)):
        raw = [raw]

    seen: Dict[int, DependencySpec] = {}

    for item in raw:
        if isinstance(item, DependencySpec):
            spec = item
            if successor_id is not None and spec.successor_id is None:
                spec = DependencySpec(
                    predecessor_id=spec.predecessor_id,
                    successor_id=successor_id,
                    dependency_type=spec.dependency_type,
                    lag_minutes=spec.lag_minutes,
                )
        elif isinstance(item, dict):
            spec = DependencySpec.from_dict(item, successor_id=successor_id)
        elif isinstance(item, (int, str)):
            try:
                pid = int(item)
                spec = DependencySpec(
                    predecessor_id=pid,
                    successor_id=successor_id,
                    dependency_type=DependencyType.FS,
                    lag_minutes=0,
                )
            except (TypeError, ValueError):
                continue
        else:
            continue

        if spec.predecessor_id is None or spec.predecessor_id < 0:
            continue
        if successor_id is not None and spec.predecessor_id == successor_id:
            continue

        seen[spec.predecessor_id] = spec

    return list(seen.values())


def serialize_dependency_specs(specs: Sequence[Union[DependencySpec, Dict[str, Any], int]]) -> str:
    """
    Serializes a sequence of DependencySpecs to JSON string.
    [{"predecessor_id": 1, "type": "FS", "lag_minutes": 0}, ...]
    """
    out: List[Dict[str, Any]] = []
    seen: Set[int] = set()
    for s in specs:
        if isinstance(s, DependencySpec):
            if s.predecessor_id is not None and s.predecessor_id >= 0 and s.predecessor_id not in seen:
                seen.add(s.predecessor_id)
                out.append({"predecessor_id": s.predecessor_id, "type": s.dependency_type.value, "lag_minutes": s.lag_minutes})
        elif isinstance(s, dict):
            raw_pid = s.get("predecessor_id") if "predecessor_id" in s else (s.get("id") if "id" in s else s.get("task_id"))
            if raw_pid is not None:
                try:
                    pid = int(raw_pid)
                    if pid >= 0 and pid not in seen:
                        seen.add(pid)
                        raw_type = str(s.get("type") or "FS").upper()
                        try:
                            dep_type = DependencyType(raw_type).value
                        except ValueError:
                            dep_type = "FS"
                        lag = int(s.get("lag_minutes") or 0)
                        out.append({"predecessor_id": pid, "type": dep_type, "lag_minutes": lag})
                except (TypeError, ValueError):
                    continue
        elif isinstance(s, (int, str)):
            try:
                pid = int(s)
                if pid >= 0 and pid not in seen:
                    seen.add(pid)
                    out.append({"predecessor_id": pid, "type": "FS", "lag_minutes": 0})
            except (TypeError, ValueError):
                continue
    return json.dumps(out)


def format_float_duration(minutes: Optional[int]) -> str:
    """
    Project-manager-friendly calendar elapsed float formatting.
    Authority: full calendar elapsed minutes (1440m = 1d).
    """
    if minutes is None:
        return "—"
    if minutes == 0:
        return "0m"

    sign = "-" if minutes < 0 else ""
    abs_m = abs(int(minutes))

    if abs_m < 60:
        return f"{sign}{abs_m}m"

    if abs_m < 1440:
        h = abs_m // 60
        rem_m = abs_m % 60
        if rem_m == 0:
            return f"{sign}{h}h"
        return f"{sign}{h}h {rem_m}m"

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


def format_cpm_datetime(dt: Optional[Union[datetime, str]]) -> str:
    """Format datetime consistently for schedule intelligence display."""
    if dt is None:
        return "—"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            try:
                dt = datetime.strptime(dt[:16], "%Y-%m-%d %H:%M")
            except Exception:
                return str(dt)
    if not isinstance(dt, datetime):
        return str(dt)
    if dt.time() == time(0, 0):
        return dt.strftime("%Y-%m-%d")
    return dt.strftime("%Y-%m-%d %H:%M")


class CPMSchedulingService:
    """
    Enterprise CPM scheduling calculation engine.
    UI-independent, read-only analytical authority.
    Supports FS, SS, FF, SF and positive/negative lag.
    """

    @staticmethod
    def _parse_date(value: Any) -> Optional[date]:
        if not value:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        try:
            return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
        except Exception:
            return None

    @staticmethod
    def _parse_time(value: Any) -> Optional[time]:
        if not value:
            return None
        if isinstance(value, time):
            return value
        try:
            return datetime.strptime(str(value).strip()[:5], "%H:%M").time()
        except Exception:
            return None

    @classmethod
    def planned_start_datetime(cls, task: Task) -> Optional[datetime]:
        day = cls._parse_date(task.planned_date)
        if day is None:
            return None
        clock = cls._parse_time(task.planned_start_time) or time(0, 0)
        return datetime.combine(day, clock)

    @classmethod
    def planned_finish_datetime(cls, task: Task) -> Optional[datetime]:
        start = cls.planned_start_datetime(task)
        duration_m = max(0, int(task.estimated_duration or 0))
        if start is not None and duration_m > 0:
            return start + timedelta(minutes=duration_m)
        due = cls._parse_date(task.due_date)
        if due is not None:
            due_clock = cls._parse_time(task.planned_end_time) or time(23, 59)
            return datetime.combine(due, due_clock)
        if start is not None:
            return start
        return None

    @classmethod
    def normalize_dependencies(cls, raw_dependencies: Any, task_id: Optional[int] = None) -> List[int]:
        specs = parse_dependency_specs(raw_dependencies, successor_id=task_id)
        return [s.predecessor_id for s in specs]

    @classmethod
    def calculate_schedule(
        cls,
        tasks: Sequence[Union[Task, Dict[str, Any]]],
        project_id: Optional[int] = None,
        anchor_date: Optional[datetime] = None,
        project_calendar: Optional[ProjectCalendarSpec] = None,
    ) -> SchedulingResult:
        """
        Calculates full forward pass, backward pass, float, and critical path
        for the given tasks across all 4 dependency types (FS, SS, FF, SF), lag/lead,
        professional schedule constraints, deadlines, and calendar availability.
        Operates non-destructively in O(V + E) complexity.
        """
        # Resolve any dict items into Task objects
        resolved_tasks: List[Task] = []
        for item in tasks:
            if isinstance(item, Task):
                resolved_tasks.append(item)
            elif isinstance(item, dict):
                try:
                    resolved_tasks.append(Task.from_row(item))
                except Exception:
                    resolved_tasks.append(Task(
                        id=item.get("id"),
                        project_id=item.get("project_id"),
                        title=item.get("title", ""),
                        status=item.get("status", "Planned"),
                        planned_date=item.get("planned_date"),
                        planned_start_time=item.get("planned_start_time"),
                        planned_end_time=item.get("planned_end_time"),
                        estimated_duration=item.get("estimated_duration", 0),
                        dependencies=item.get("dependencies", []),
                        constraint_type=item.get("constraint_type", "ASAP"),
                        constraint_datetime=item.get("constraint_datetime"),
                        deadline_datetime=item.get("deadline_datetime"),
                    ))

        # Filter tasks if project_id is explicitly specified
        scoped_tasks: List[Task] = []
        for t in resolved_tasks:
            if t.id is None:
                continue
            # Filter non-task synthetic types if any
            if getattr(t, "gantt_item_type", "task") != "task":
                continue
            if project_id is not None and t.project_id != project_id:
                continue
            scoped_tasks.append(t)

        if not scoped_tasks:
            return SchedulingResult(
                project_id=project_id,
                project_start=None,
                project_finish=None,
                nodes={},
                critical_task_ids=(),
                critical_paths=(),
                diagnostics=(),
                has_cycles=False,
                cycle_task_ids=(),
                is_complete=True,
            )

        task_map: Dict[int, Task] = {int(t.id): t for t in scoped_tasks if t.id is not None}
        diagnostics: List[ScheduleDiagnostic] = []
        node_diagnostic_codes: Dict[int, List[DiagnosticCode]] = {tid: [] for tid in task_map}
        calendar_authority = ScheduleCalendar.from_project_calendar(project_calendar)
        calendar_enabled = calendar_authority is not None

        def cal_start(value: datetime) -> datetime:
            return next_working_datetime(value, calendar_authority)

        def cal_upper_start(value: datetime) -> datetime:
            return previous_working_datetime(value, calendar_authority)

        def clean_minutes(value: int) -> int:
            return int(value or 0)

        def is_nominal_whole_day_duration(minutes: int) -> bool:
            clean = clean_minutes(minutes)
            return clean > 0 and clean % 1440 == 0

        def cal_add(value: datetime, minutes: int) -> datetime:
            return add_working_minutes(value, clean_minutes(minutes), calendar_authority)

        def cal_subtract(value: datetime, minutes: int) -> datetime:
            return subtract_working_minutes(value, clean_minutes(minutes), calendar_authority)

        def cal_add_duration(value: datetime, minutes: int) -> datetime:
            clean = max(0, clean_minutes(minutes))
            if calendar_enabled and is_nominal_whole_day_duration(clean):
                return add_working_days_preserve_time(
                    value,
                    clean // 1440,
                    calendar_authority,
                )
            return add_working_minutes(value, clean, calendar_authority)

        def cal_subtract_duration(value: datetime, minutes: int) -> datetime:
            clean = max(0, clean_minutes(minutes))
            if calendar_enabled and is_nominal_whole_day_duration(clean):
                return subtract_working_days_preserve_time(
                    value,
                    clean // 1440,
                    calendar_authority,
                )
            return subtract_working_minutes(value, clean, calendar_authority)

        def cal_between(start: datetime, finish: datetime) -> int:
            return working_minutes_between(start, finish, calendar_authority)

        # 1. Parse and validate inputs per task
        parsed_starts: Dict[int, Optional[datetime]] = {}
        durations: Dict[int, int] = {}
        task_constraints: Dict[int, Tuple[ConstraintType, Optional[datetime]]] = {}
        task_deadlines: Dict[int, Optional[datetime]] = {}
        incoming_edges: Dict[int, List[DependencySpec]] = {tid: [] for tid in task_map}
        outgoing_edges: Dict[int, List[DependencySpec]] = {tid: [] for tid in task_map}
        successors_map: Dict[int, List[int]] = {tid: [] for tid in task_map}
        schedulable_flags: Dict[int, bool] = {tid: True for tid in task_map}

        for tid, task in task_map.items():
            # Check planned start
            p_start = cls.planned_start_datetime(task)
            parsed_starts[tid] = p_start
            if p_start is None:
                schedulable_flags[tid] = False
                node_diagnostic_codes[tid].append(DiagnosticCode.UNSCHEDULED_NO_START)
                diagnostics.append(
                    ScheduleDiagnostic(
                        code=DiagnosticCode.UNSCHEDULED_NO_START,
                        task_id=tid,
                        message=f"Task {tid} ('{task.title}') has no planned start date.",
                    )
                )

            # Check duration
            is_ms = bool(getattr(task, "is_milestone", False) or getattr(task, "gantt_is_milestone", False))
            raw_dur = int(task.estimated_duration or 0)
            if is_ms or raw_dur == 0:
                durations[tid] = 0
            elif raw_dur < 0:
                durations[tid] = 0
                schedulable_flags[tid] = False
                node_diagnostic_codes[tid].append(DiagnosticCode.INVALID_DURATION)
                diagnostics.append(
                    ScheduleDiagnostic(
                        code=DiagnosticCode.INVALID_DURATION,
                        task_id=tid,
                        message=f"Task {tid} ('{task.title}') has negative estimated duration ({raw_dur}m).",
                    )
                )
            else:
                durations[tid] = raw_dur

            if calendar_enabled and p_start is not None and durations[tid] > 0:
                if not calendar_authority.is_working_day(p_start.date()):
                    node_diagnostic_codes[tid].append(DiagnosticCode.CALENDAR_CONFLICT)
                    diagnostics.append(
                        ScheduleDiagnostic(
                            code=DiagnosticCode.CALENDAR_CONFLICT,
                            task_id=tid,
                            message=f"Task {tid} planned start falls on non-working calendar date ({p_start.strftime('%Y-%m-%d')}).",
                        )
                    )

            # Parse constraints and deadlines
            raw_ctype = getattr(task, "constraint_type", "ASAP")
            ctype = ConstraintType.from_str(raw_ctype)
            c_dt = parse_constraint_datetime(getattr(task, "constraint_datetime", None))
            d_dt = parse_constraint_datetime(getattr(task, "deadline_datetime", None))
            task_constraints[tid] = (ctype, c_dt)
            task_deadlines[tid] = d_dt

            if ctype not in (ConstraintType.ASAP, ConstraintType.ALAP) and c_dt is None:
                node_diagnostic_codes[tid].append(DiagnosticCode.CONSTRAINT_DATE_MISSING)
                diagnostics.append(
                    ScheduleDiagnostic(
                        code=DiagnosticCode.CONSTRAINT_DATE_MISSING,
                        task_id=tid,
                        message=f"Task {tid} has constraint '{ctype.value}' but no constraint date/time.",
                    )
                )

            # Validate dependencies
            raw_deps = task.dependencies or []
            if isinstance(raw_deps, str):
                try:
                    raw_deps = json.loads(raw_deps)
                except Exception:
                    raw_deps = []
            if not isinstance(raw_deps, (list, tuple, set)):
                raw_deps = [raw_deps]

            seen_preds_in_task: Set[int] = set()

            for dep_item in raw_deps:
                if isinstance(dep_item, DependencySpec):
                    spec = dep_item
                elif isinstance(dep_item, dict):
                    # Check invalid type in dict
                    raw_type = str(dep_item.get("type") or dep_item.get("dependency_type") or "FS").upper().strip()
                    try:
                        dep_type = DependencyType(raw_type)
                    except ValueError:
                        node_diagnostic_codes[tid].append(DiagnosticCode.INVALID_DEPENDENCY_TYPE)
                        diagnostics.append(
                            ScheduleDiagnostic(
                                code=DiagnosticCode.INVALID_DEPENDENCY_TYPE,
                                task_id=tid,
                                message=f"Task {tid} has invalid dependency type '{raw_type}'.",
                            )
                        )
                        dep_type = DependencyType.FS

                    # Check lag bounds
                    raw_lag = dep_item.get("lag_minutes", 0)
                    lag_val = parse_lag_duration(raw_lag)
                    if lag_val is None:
                        node_diagnostic_codes[tid].append(DiagnosticCode.INVALID_LAG)
                        diagnostics.append(
                            ScheduleDiagnostic(
                                code=DiagnosticCode.INVALID_LAG,
                                task_id=tid,
                                message=f"Task {tid} has out-of-bounds or invalid lag value '{raw_lag}'.",
                            )
                        )
                        lag_val = 0

                    pid = int(dep_item.get("predecessor_id") or dep_item.get("id") or dep_item.get("task_id") or 0)
                    spec = DependencySpec(
                        predecessor_id=pid,
                        successor_id=tid,
                        dependency_type=dep_type,
                        lag_minutes=lag_val,
                    )
                elif isinstance(dep_item, (int, str)):
                    try:
                        pid = int(dep_item)
                        spec = DependencySpec(
                            predecessor_id=pid,
                            successor_id=tid,
                            dependency_type=DependencyType.FS,
                            lag_minutes=0,
                        )
                    except (TypeError, ValueError):
                        continue
                else:
                    continue

                dep_id = spec.predecessor_id
                if dep_id is None or dep_id < 0:
                    continue

                # Check duplicate
                if dep_id in seen_preds_in_task:
                    node_diagnostic_codes[tid].append(DiagnosticCode.DUPLICATE_DEPENDENCY)
                    diagnostics.append(
                        ScheduleDiagnostic(
                            code=DiagnosticCode.DUPLICATE_DEPENDENCY,
                            task_id=tid,
                            message=f"Task {tid} has duplicate dependency on predecessor {dep_id}.",
                            related_task_ids=(dep_id,),
                        )
                    )
                    continue
                seen_preds_in_task.add(dep_id)

                # Check self reference
                if dep_id == tid:
                    node_diagnostic_codes[tid].append(DiagnosticCode.SELF_REFERENCE)
                    diagnostics.append(
                        ScheduleDiagnostic(
                            code=DiagnosticCode.SELF_REFERENCE,
                            task_id=tid,
                            message=f"Task {tid} ('{task.title}') has a self-referencing dependency.",
                        )
                    )
                    continue

                # Check missing reference
                if dep_id not in task_map:
                    node_diagnostic_codes[tid].append(DiagnosticCode.MISSING_TASK_REFERENCE)
                    diagnostics.append(
                        ScheduleDiagnostic(
                            code=DiagnosticCode.MISSING_TASK_REFERENCE,
                            task_id=tid,
                            message=f"Task {tid} references missing predecessor task ID {dep_id}.",
                            related_task_ids=(dep_id,),
                        )
                    )
                    continue

                # Check cross-project reference
                pred_task = task_map[dep_id]
                if getattr(pred_task, "project_id", None) != getattr(task, "project_id", None):
                    node_diagnostic_codes[tid].append(DiagnosticCode.CROSS_PROJECT_DEPENDENCY)
                    diagnostics.append(
                        ScheduleDiagnostic(
                            code=DiagnosticCode.CROSS_PROJECT_DEPENDENCY,
                            task_id=tid,
                            message=f"Task {tid} ('{task.title}') references cross-project predecessor task {dep_id} ('{pred_task.title}').",
                            related_task_ids=(dep_id,),
                        )
                    )

                incoming_edges[tid].append(spec)
                outgoing_edges[dep_id].append(spec)
                if tid not in successors_map[dep_id]:
                    successors_map[dep_id].append(tid)

        # 2. Cycle Detection using iterative DFS with explicit stack
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[int, int] = {tid: WHITE for tid in task_map}
        cycle_nodes: Set[int] = set()

        for root in task_map:
            if color[root] != WHITE:
                continue
            stack: List[Tuple[int, Any]] = [(root, iter(successors_map.get(root, [])))]
            color[root] = GRAY
            path: List[int] = [root]

            while stack:
                u, it = stack[-1]
                try:
                    v = next(it)
                    if color[v] == GRAY:
                        # Found cycle
                        try:
                            idx = path.index(v)
                            cycle_nodes.update(path[idx:])
                        except ValueError:
                            cycle_nodes.add(v)
                            cycle_nodes.add(u)
                    elif color[v] == WHITE:
                        color[v] = GRAY
                        path.append(v)
                        stack.append((v, iter(successors_map.get(v, []))))
                except StopIteration:
                    color[u] = BLACK
                    path.pop()
                    stack.pop()

        has_cycles = len(cycle_nodes) > 0
        if has_cycles:
            sorted_cycles = tuple(sorted(cycle_nodes))
            for c_id in sorted_cycles:
                schedulable_flags[c_id] = False
                if DiagnosticCode.DEPENDENCY_CYCLE not in node_diagnostic_codes[c_id]:
                    node_diagnostic_codes[c_id].append(DiagnosticCode.DEPENDENCY_CYCLE)
            diagnostics.append(
                ScheduleDiagnostic(
                    code=DiagnosticCode.DEPENDENCY_CYCLE,
                    task_id=None,
                    message=f"Dependency cycle detected involving {len(cycle_nodes)} task(s): {list(sorted_cycles)}",
                    related_task_ids=sorted_cycles,
                )
            )

        # 3. Determine Schedulable Subset (Acyclic & valid inputs)
        tainted_by_cycle: Set[int] = set(cycle_nodes)
        taint_queue = deque(cycle_nodes)
        while taint_queue:
            curr = taint_queue.popleft()
            for succ in successors_map.get(curr, []):
                if succ not in tainted_by_cycle:
                    tainted_by_cycle.add(succ)
                    taint_queue.append(succ)

        for tid in tainted_by_cycle:
            schedulable_flags[tid] = False

        schedulable_ids = {tid for tid in task_map if schedulable_flags[tid]}

        if not schedulable_ids:
            nodes_result: Dict[int, ScheduleNodeResult] = {}
            for tid in task_map:
                nodes_result[tid] = ScheduleNodeResult(
                    task_id=tid,
                    earliest_start=None,
                    earliest_finish=None,
                    latest_start=None,
                    latest_finish=None,
                    total_float_minutes=None,
                    free_float_minutes=None,
                    is_critical=False,
                    schedulable=False,
                    diagnostic_codes=tuple(node_diagnostic_codes[tid]),
                )
            return SchedulingResult(
                project_id=project_id,
                project_start=None,
                project_finish=None,
                nodes=nodes_result,
                critical_task_ids=(),
                critical_paths=(),
                diagnostics=tuple(diagnostics),
                has_cycles=has_cycles,
                cycle_task_ids=tuple(sorted(cycle_nodes)),
                is_complete=False,
            )

        # 4. Topological Sort of Schedulable Nodes (Kahn's Algorithm - O(V + E))
        in_degree: Dict[int, int] = {}
        sched_successors: Dict[int, List[int]] = {tid: [] for tid in schedulable_ids}
        sched_incoming_edges: Dict[int, List[DependencySpec]] = {tid: [] for tid in schedulable_ids}
        sched_outgoing_edges: Dict[int, List[DependencySpec]] = {tid: [] for tid in schedulable_ids}

        for tid in schedulable_ids:
            valid_inc = [e for e in incoming_edges[tid] if e.predecessor_id in schedulable_ids]
            sched_incoming_edges[tid] = valid_inc
            preds_set = {e.predecessor_id for e in valid_inc}
            in_degree[tid] = len(preds_set)

            for e in valid_inc:
                sched_outgoing_edges[e.predecessor_id].append(e)
                if tid not in sched_successors[e.predecessor_id]:
                    sched_successors[e.predecessor_id].append(tid)

        queue = deque(sorted([tid for tid, deg in in_degree.items() if deg == 0]))
        topo_order: List[int] = []

        while queue:
            curr = queue.popleft()
            topo_order.append(curr)
            for succ in sched_successors.get(curr, []):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        # Determine project anchor datetime
        earliest_root_start = None
        for tid in topo_order:
            if not sched_incoming_edges[tid] and parsed_starts[tid] is not None:
                if earliest_root_start is None or parsed_starts[tid] < earliest_root_start:
                    earliest_root_start = parsed_starts[tid]

        if earliest_root_start is None:
            earliest_root_start = anchor_date or datetime.combine(date.today(), time(0, 0))

        # 5. Forward Pass (ES and EF) with all 4 edge types, lag/lead & constraints
        earliest_start: Dict[int, datetime] = {}
        earliest_finish: Dict[int, datetime] = {}

        for tid in topo_order:
            inc_edges = sched_incoming_edges[tid]
            dur = durations[tid]
            ctype, c_dt = task_constraints[tid]

            if not inc_edges:
                dep_es = parsed_starts[tid] or earliest_root_start
                dep_es = cal_start(dep_es)
            else:
                bounds: List[datetime] = []
                for e in inc_edges:
                    p = e.predecessor_id
                    lag_m = int(e.lag_minutes or 0)
                    dtype = e.dependency_type

                    if dtype == DependencyType.FS:
                        bound = cal_add(earliest_finish[p], lag_m)
                    elif dtype == DependencyType.SS:
                        bound = cal_add(earliest_start[p], lag_m)
                    elif dtype == DependencyType.FF:
                        finish_bound = cal_add(earliest_finish[p], lag_m)
                        bound = cal_subtract_duration(finish_bound, dur)
                    elif dtype == DependencyType.SF:
                        finish_bound = cal_add(earliest_start[p], lag_m)
                        bound = cal_subtract_duration(finish_bound, dur)
                    else:
                        bound = cal_add(earliest_finish[p], lag_m)

                    bounds.append(bound)

                max_dep_es = max(bounds)
                own_planned_start = parsed_starts[tid]
                if own_planned_start is not None:
                    own_planned_start = cal_start(own_planned_start)
                    dep_es = max(own_planned_start, max_dep_es)
                else:
                    dep_es = max_dep_es

            # Apply forward constraints
            if ctype == ConstraintType.SNET and c_dt is not None:
                es = max(dep_es, cal_start(c_dt))
            elif ctype == ConstraintType.FNET and c_dt is not None:
                finish_bound = cal_start(c_dt)
                es = max(dep_es, cal_subtract_duration(finish_bound, dur))
            elif ctype == ConstraintType.MSO and c_dt is not None:
                must_start = cal_start(c_dt)
                if must_start < dep_es:
                    if DiagnosticCode.CONSTRAINT_CONFLICT not in node_diagnostic_codes[tid]:
                        node_diagnostic_codes[tid].append(DiagnosticCode.CONSTRAINT_CONFLICT)
                        diagnostics.append(
                            ScheduleDiagnostic(
                                code=DiagnosticCode.CONSTRAINT_CONFLICT,
                                task_id=tid,
                                message=f"Task {tid} predecessor dependencies require start at {dep_es}, violating Must Start On ({must_start}).",
                            )
                        )
                    es = dep_es
                else:
                    es = must_start
            elif ctype == ConstraintType.MFO and c_dt is not None:
                must_finish = c_dt
                req_start = cal_subtract_duration(must_finish, dur)
                if req_start < dep_es:
                    if DiagnosticCode.CONSTRAINT_CONFLICT not in node_diagnostic_codes[tid]:
                        node_diagnostic_codes[tid].append(DiagnosticCode.CONSTRAINT_CONFLICT)
                        diagnostics.append(
                            ScheduleDiagnostic(
                                code=DiagnosticCode.CONSTRAINT_CONFLICT,
                                task_id=tid,
                                message=f"Task {tid} predecessor dependencies require finish at {cal_add_duration(dep_es, dur)}, violating Must Finish On ({must_finish}).",
                            )
                        )
                    es = dep_es
                else:
                    es = req_start
            else:
                es = dep_es

            ef = cal_add_duration(es, dur)
            earliest_start[tid] = es
            earliest_finish[tid] = ef

        # Project finish authority: max(EF) across all schedulable nodes
        project_start_dt = min(earliest_start[tid] for tid in topo_order)
        project_finish_dt = max(earliest_finish[tid] for tid in topo_order)

        # 6. Backward Pass (LS and LF) with all 4 edge types, lag/lead & constraints
        latest_start: Dict[int, datetime] = {}
        latest_finish: Dict[int, datetime] = {}

        for tid in reversed(topo_order):
            out_edges = sched_outgoing_edges[tid]
            dur = durations[tid]
            ctype, c_dt = task_constraints[tid]

            if not out_edges:
                lf = project_finish_dt
            else:
                req_lfs: List[datetime] = []
                for e in out_edges:
                    s = e.successor_id
                    lag_m = int(e.lag_minutes or 0)
                    dtype = e.dependency_type

                    if dtype == DependencyType.FS:
                        req_lf = cal_add(latest_start[s], -lag_m)
                    elif dtype == DependencyType.SS:
                        pred_start_limit = cal_add(latest_start[s], -lag_m)
                        req_lf = cal_add_duration(pred_start_limit, dur)
                    elif dtype == DependencyType.FF:
                        req_lf = cal_add(latest_finish[s], -lag_m)
                    elif dtype == DependencyType.SF:
                        pred_start_limit = cal_add(latest_finish[s], -lag_m)
                        req_lf = cal_add_duration(pred_start_limit, dur)
                    else:
                        req_lf = cal_add(latest_start[s], -lag_m)

                    req_lfs.append(req_lf)

                lf = min(req_lfs)

            # Apply backward constraints
            if ctype == ConstraintType.SNLT and c_dt is not None:
                start_limit = cal_upper_start(c_dt)
                if start_limit < earliest_start[tid]:
                    if DiagnosticCode.CONSTRAINT_CONFLICT not in node_diagnostic_codes[tid]:
                        node_diagnostic_codes[tid].append(DiagnosticCode.CONSTRAINT_CONFLICT)
                        diagnostics.append(
                            ScheduleDiagnostic(
                                code=DiagnosticCode.CONSTRAINT_CONFLICT,
                                task_id=tid,
                                message=f"Task {tid} earliest start ({earliest_start[tid]}) exceeds Start No Later Than bound ({start_limit}).",
                            )
                        )
                lf = min(lf, cal_add_duration(start_limit, dur))
            elif ctype == ConstraintType.FNLT and c_dt is not None:
                if c_dt < earliest_finish[tid]:
                    if DiagnosticCode.CONSTRAINT_CONFLICT not in node_diagnostic_codes[tid]:
                        node_diagnostic_codes[tid].append(DiagnosticCode.CONSTRAINT_CONFLICT)
                        diagnostics.append(
                            ScheduleDiagnostic(
                                code=DiagnosticCode.CONSTRAINT_CONFLICT,
                                task_id=tid,
                                message=f"Task {tid} earliest finish ({earliest_finish[tid]}) exceeds Finish No Later Than bound ({c_dt}).",
                            )
                        )
                lf = min(lf, c_dt)
            elif ctype == ConstraintType.MSO and c_dt is not None:
                lf = min(lf, cal_add_duration(cal_start(c_dt), dur))
            elif ctype == ConstraintType.MFO and c_dt is not None:
                lf = min(lf, c_dt)

            ls = cal_subtract_duration(lf, dur)
            latest_start[tid] = ls
            latest_finish[tid] = lf

        # 6b. ALAP Post-Processing: shift planned dates to latest start without delaying project
        for tid in topo_order:
            ctype, c_dt = task_constraints[tid]
            dur = durations[tid]
            if ctype == ConstraintType.ALAP:
                alap_es = min(latest_start[tid], cal_subtract_duration(project_finish_dt, dur))
                earliest_start[tid] = alap_es
                earliest_finish[tid] = cal_add_duration(alap_es, dur)

        # 7. Float Calculations & Critical Path Classification
        total_float: Dict[int, int] = {}
        free_float: Dict[int, int] = {}
        is_critical_map: Dict[int, bool] = {}

        for tid in topo_order:
            es = earliest_start[tid]
            ef = earliest_finish[tid]
            ls = latest_start[tid]
            lf = latest_finish[tid]

            # Total Float = LS - ES (in minutes) — preserve negative float
            tf_minutes = cal_between(es, ls)
            total_float[tid] = tf_minutes
            if tf_minutes < 0:
                if DiagnosticCode.NEGATIVE_FLOAT not in node_diagnostic_codes[tid]:
                    node_diagnostic_codes[tid].append(DiagnosticCode.NEGATIVE_FLOAT)
                    diagnostics.append(
                        ScheduleDiagnostic(
                            code=DiagnosticCode.NEGATIVE_FLOAT,
                            task_id=tid,
                            message=f"Negative total float ({tf_minutes}m) on task {tid}.",
                        )
                    )

            # Edge-specific Free Float derivation
            out_edges = sched_outgoing_edges[tid]
            if out_edges:
                edge_ffs: List[int] = []
                for e in out_edges:
                    s = e.successor_id
                    lag_m = e.lag_minutes
                    dtype = e.dependency_type

                    if dtype == DependencyType.FS:
                        slack_dt = cal_between(cal_add(earliest_finish[tid], lag_m), earliest_start[s])
                    elif dtype == DependencyType.SS:
                        slack_dt = cal_between(cal_add(earliest_start[tid], lag_m), earliest_start[s])
                    elif dtype == DependencyType.FF:
                        slack_dt = cal_between(cal_add(earliest_finish[tid], lag_m), earliest_finish[s])
                    elif dtype == DependencyType.SF:
                        slack_dt = cal_between(cal_add(earliest_start[tid], lag_m), earliest_finish[s])
                    else:
                        slack_dt = cal_between(cal_add(earliest_finish[tid], lag_m), earliest_start[s])

                    edge_ffs.append(int(slack_dt))

                ff_minutes = min(edge_ffs)
            else:
                ff_minutes = cal_between(ef, project_finish_dt)

            # Free Float is an independent CPM value, not a display-only
            # badge. Preserve negative values so ALAP/constraint conflicts
            # remain mathematically visible to downstream diagnostics.
            free_float[tid] = int(ff_minutes)
            if ff_minutes < 0:
                if DiagnosticCode.NEGATIVE_FLOAT not in node_diagnostic_codes[tid]:
                    node_diagnostic_codes[tid].append(DiagnosticCode.NEGATIVE_FLOAT)
                    diagnostics.append(
                        ScheduleDiagnostic(
                            code=DiagnosticCode.NEGATIVE_FLOAT,
                            task_id=tid,
                            message=f"Negative free float ({ff_minutes}m) on task {tid}.",
                        )
                    )

            # Critical path classification: Total Float == 0 (Canonical Phase 2A rule)
            is_crit = (tf_minutes == 0)
            is_critical_map[tid] = is_crit

            # Deadline evaluation (Deterministic MISSED vs SAFE)
            d_dt = task_deadlines[tid]
            if d_dt is not None:
                if ef > d_dt:
                    if DiagnosticCode.DEADLINE_MISSED not in node_diagnostic_codes[tid]:
                        node_diagnostic_codes[tid].append(DiagnosticCode.DEADLINE_MISSED)
                        diagnostics.append(
                            ScheduleDiagnostic(
                                code=DiagnosticCode.DEADLINE_MISSED,
                                task_id=tid,
                                message=f"Task {tid} forecast finish ({ef}) misses deadline ({d_dt}).",
                            )
                        )

            # Project Calendar availability check
            if calendar_enabled and durations[tid] > 0:
                if not calendar_authority.is_working_day(es.date()):
                    if DiagnosticCode.CALENDAR_CONFLICT not in node_diagnostic_codes[tid]:
                        node_diagnostic_codes[tid].append(DiagnosticCode.CALENDAR_CONFLICT)
                        diagnostics.append(
                            ScheduleDiagnostic(
                                code=DiagnosticCode.CALENDAR_CONFLICT,
                                task_id=tid,
                                message=f"Task {tid} planned start falls on non-working calendar date ({es.strftime('%Y-%m-%d')}).",
                            )
                        )

        # 8. Multiple Critical Paths Enumeration (Iterative, zero recursion)
        critical_task_ids = tuple(sorted([tid for tid in schedulable_ids if is_critical_map[tid]]))

        def is_tight_critical_edge(e: DependencySpec) -> bool:
            p = e.predecessor_id
            s = e.successor_id
            if not is_critical_map.get(p, False) or not is_critical_map.get(s, False):
                return False
            lag_m = int(e.lag_minutes or 0)
            dtype = e.dependency_type
            if dtype == DependencyType.FS:
                return cal_add(earliest_finish[p], lag_m) == earliest_start[s]
            elif dtype == DependencyType.SS:
                return cal_add(earliest_start[p], lag_m) == earliest_start[s]
            elif dtype == DependencyType.FF:
                return cal_add(earliest_finish[p], lag_m) == earliest_finish[s]
            elif dtype == DependencyType.SF:
                return cal_add(earliest_start[p], lag_m) == earliest_finish[s]
            return False

        critical_paths_list: List[Tuple[int, ...]] = []
        critical_roots = [
            tid for tid in topo_order
            if is_critical_map[tid] and not any(is_tight_critical_edge(e) for e in sched_incoming_edges[tid])
        ]

        def get_critical_succs(u: int) -> List[int]:
            return [
                e.successor_id for e in sched_outgoing_edges[u]
                if is_tight_critical_edge(e)
            ]

        for c_root in critical_roots:
            if len(critical_paths_list) >= 100:
                break
            stack: List[Tuple[int, Any]] = [(c_root, iter(get_critical_succs(c_root)))]
            curr_path: List[int] = [c_root]

            while stack and len(critical_paths_list) < 100:
                u, it = stack[-1]
                try:
                    v = next(it)
                    curr_path.append(v)
                    stack.append((v, iter(get_critical_succs(v))))
                except StopIteration:
                    if not get_critical_succs(u):
                        critical_paths_list.append(tuple(curr_path))
                    curr_path.pop()
                    stack.pop()

        critical_paths = tuple(critical_paths_list)

        # 9. Build Immutable Result Objects
        final_nodes: Dict[int, ScheduleNodeResult] = {}
        for tid in task_map:
            if tid in schedulable_ids:
                final_nodes[tid] = ScheduleNodeResult(
                    task_id=tid,
                    earliest_start=earliest_start[tid],
                    earliest_finish=earliest_finish[tid],
                    latest_start=latest_start[tid],
                    latest_finish=latest_finish[tid],
                    total_float_minutes=total_float[tid],
                    free_float_minutes=free_float[tid],
                    is_critical=is_critical_map[tid],
                    schedulable=True,
                    diagnostic_codes=tuple(node_diagnostic_codes[tid]),
                )
            else:
                final_nodes[tid] = ScheduleNodeResult(
                    task_id=tid,
                    earliest_start=None,
                    earliest_finish=None,
                    latest_start=None,
                    latest_finish=None,
                    total_float_minutes=None,
                    free_float_minutes=None,
                    is_critical=False,
                    schedulable=False,
                    diagnostic_codes=tuple(node_diagnostic_codes[tid]),
                )

        return SchedulingResult(
            project_id=project_id,
            project_start=project_start_dt,
            project_finish=project_finish_dt,
            nodes=final_nodes,
            critical_task_ids=critical_task_ids,
            critical_paths=critical_paths,
            diagnostics=tuple(diagnostics),
            has_cycles=has_cycles,
            cycle_task_ids=tuple(sorted(cycle_nodes)),
            is_complete=True,
        )
