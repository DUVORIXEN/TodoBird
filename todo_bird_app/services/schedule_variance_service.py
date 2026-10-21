"""
TODO BIRD — PROFESSIONAL SCHEDULE VARIANCE SERVICE (Phase 2D)

Pure Python, Qt-independent, deterministic enterprise schedule baseline & variance engine.

Core Concept:
1. ORIGINAL APPROVED PLAN = BASELINE 1 (historical snapshot)
2. CURRENT WORKING PLAN = CURRENT SCHEDULE (CPM forward/backward pass or planned schedule)
3. ACTUAL EXECUTION = ACTUALS (progress, actual start/finish dates)

Variance Sign Convention (Project Controls Standard):
    Variance = Current - Baseline
    - positive Start Variance = current starts later than baseline
    - negative Start Variance = current starts earlier
    - positive Finish Variance = current finishes later (behind baseline)
    - negative Finish Variance = current finishes earlier (ahead of baseline)
    - positive Duration Variance = current duration is longer
    - negative Duration Variance = current duration is shorter
    - positive Effort Variance = current planned effort is higher
    - negative Effort Variance = current planned effort is lower
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date, time, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Sequence, Tuple, Union

from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.models.project import Project


class VarianceStatus(str, Enum):
    AHEAD = "ahead"
    ON_BASELINE = "on_baseline"
    BEHIND = "behind"
    NOT_BASELINED = "not_baselined"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class BaselineSnapshot:
    task_id: int
    baseline_start: Optional[datetime]
    baseline_finish: Optional[datetime]
    baseline_duration_minutes: Optional[int]
    baseline_planned_effort_minutes: Optional[int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "baseline_start": self.baseline_start.isoformat() if self.baseline_start else None,
            "baseline_finish": self.baseline_finish.isoformat() if self.baseline_finish else None,
            "baseline_duration_minutes": self.baseline_duration_minutes,
            "baseline_planned_effort_minutes": self.baseline_planned_effort_minutes,
        }


@dataclass(frozen=True)
class TaskVarianceResult:
    task_id: int
    has_baseline: bool
    baseline_start: Optional[datetime]
    baseline_finish: Optional[datetime]
    baseline_duration_minutes: Optional[int]
    baseline_planned_effort_minutes: Optional[int]

    current_start: Optional[datetime]
    current_finish: Optional[datetime]
    current_duration_minutes: Optional[int]
    current_planned_effort_minutes: int

    start_variance_minutes: Optional[int]
    finish_variance_minutes: Optional[int]
    duration_variance_minutes: Optional[int]
    effort_variance_minutes: Optional[int]

    variance_status: VarianceStatus
    is_critical: bool = False

    @property
    def status(self) -> VarianceStatus:
        return self.variance_status

    @property
    def is_ahead(self) -> bool:
        return self.variance_status == VarianceStatus.AHEAD

    @property
    def is_on_baseline(self) -> bool:
        return self.variance_status == VarianceStatus.ON_BASELINE

    @property
    def is_behind(self) -> bool:
        return self.variance_status == VarianceStatus.BEHIND

    @property
    def is_not_baselined(self) -> bool:
        return self.variance_status == VarianceStatus.NOT_BASELINED

    @property
    def is_unavailable(self) -> bool:
        return self.variance_status == VarianceStatus.UNAVAILABLE


@dataclass(frozen=True)
class ProjectVarianceSummary:
    project_id: Optional[int]
    has_baseline: bool
    baseline_created_at: Optional[str]
    baseline_name: Optional[str]
    total_tasks: int
    tasks_baselined: int
    tasks_not_baselined: int
    tasks_ahead: int
    tasks_on_baseline: int
    tasks_behind: int
    critical_tasks_behind: int
    max_finish_variance_minutes: Optional[int]
    project_finish_variance_minutes: Optional[int]

    @property
    def tasks_unbaselined(self) -> int:
        return self.tasks_not_baselined


def parse_datetime_flexible(date_val: Any, time_val: Any = None) -> Optional[datetime]:
    """Parses date/time strings or objects into a canonical datetime."""
    if not date_val:
        return None
    if isinstance(date_val, datetime):
        return date_val
    if isinstance(date_val, date):
        t = time(0, 0)
        if time_val:
            if isinstance(time_val, time):
                t = time_val
            elif isinstance(time_val, str) and ":" in time_val:
                try:
                    parts = time_val.strip().split(":")
                    t = time(int(parts[0]), int(parts[1]))
                except Exception:
                    pass
        return datetime.combine(date_val, t)

    d_str = str(date_val).strip()
    if not d_str:
        return None

    # Try ISO formats
    try:
        if "T" in d_str:
            return datetime.fromisoformat(d_str)
        if " " in d_str:
            parts = d_str.split(" ")
            d_part = parts[0][:10]
            t_part = parts[1][:5]
            return datetime.strptime(f"{d_part} {t_part}", "%Y-%m-%d %H:%M")
        # Date only with separate time_val
        t_str = str(time_val).strip()[:5] if time_val and ":" in str(time_val) else "00:00"
        return datetime.strptime(f"{d_str[:10]} {t_str}", "%Y-%m-%d %H:%M")
    except Exception:
        pass

    try:
        return datetime.strptime(d_str[:10], "%Y-%m-%d")
    except Exception:
        return None


def format_variance_duration(minutes: Optional[int], zero_as_zero: bool = True) -> str:
    """
    Formats a signed variance duration in minutes into a clean project-controls string.
    Examples:
        +2d, -4h, 0, +1d 3h, -15m
    """
    if minutes is None:
        return "—"
    if minutes == 0:
        return "0" if zero_as_zero else "+0m"

    sign = "+" if minutes > 0 else "-"
    abs_m = abs(minutes)

    days = abs_m // 1440
    rem_m = abs_m % 1440
    hours = rem_m // 60
    mins = rem_m % 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if mins > 0 and (days == 0 or hours == 0):
        parts.append(f"{mins}m")

    if not parts:
        return "0"

    return f"{sign}{' '.join(parts)}"


class ScheduleVarianceService:
    """
    Canonical authority for schedule baseline comparison, variance calculation,
    and project health aggregation.
    """

    @classmethod
    def calculate_task_variance(
        cls,
        task: Task,
        cpm_node: Optional[Any] = None,
        is_critical: bool = False
    ) -> TaskVarianceResult:
        """
        Compares a task's current schedule against its baseline snapshot.
        """
        task_id = int(task.id or 0)
        b_start_raw = getattr(task, "baseline_start", None)
        b_finish_raw = getattr(task, "baseline_finish", None)
        b_dur_raw = getattr(task, "baseline_duration_minutes", None)
        b_eff_raw = getattr(task, "baseline_planned_effort_minutes", None)

        has_baseline = bool(b_start_raw and str(b_start_raw).strip())
        b_start = parse_datetime_flexible(b_start_raw) if has_baseline else None
        b_finish = parse_datetime_flexible(b_finish_raw) if has_baseline else None
        b_dur = int(b_dur_raw) if b_dur_raw is not None else None
        b_eff = int(b_eff_raw) if b_eff_raw is not None else None

        # Determine current schedule start and finish
        curr_start: Optional[datetime] = None
        curr_finish: Optional[datetime] = None
        curr_dur: Optional[int] = None
        curr_eff: int = int(getattr(task, "planned_effort_minutes", 0) or 0)

        # Check CPM schedule node first
        if cpm_node is not None and getattr(cpm_node, "schedulable", False):
            curr_start = getattr(cpm_node, "earliest_start", None)
            curr_finish = getattr(cpm_node, "earliest_finish", None)
            if curr_start and curr_finish:
                curr_dur = int((curr_finish - curr_start).total_seconds() / 60)
            if hasattr(cpm_node, "is_critical"):
                is_critical = bool(cpm_node.is_critical)
        else:
            p_date = getattr(task, "planned_date", None)
            p_time = getattr(task, "planned_start_time", None)
            d_date = getattr(task, "due_date", None) or p_date
            d_time = getattr(task, "planned_end_time", None)
            curr_start = parse_datetime_flexible(p_date, p_time)
            if d_time:
                curr_finish = parse_datetime_flexible(d_date, d_time)
            elif curr_start and getattr(task, "estimated_duration", 0):
                curr_finish = curr_start + timedelta(minutes=int(task.estimated_duration or 0))
            else:
                curr_finish = parse_datetime_flexible(d_date, None)
            if curr_start and curr_finish:
                curr_dur = int((curr_finish - curr_start).total_seconds() / 60)
            else:
                curr_dur = int(getattr(task, "estimated_duration", 0) or 0)

        if not has_baseline:
            return TaskVarianceResult(
                task_id=task_id,
                has_baseline=False,
                baseline_start=None,
                baseline_finish=None,
                baseline_duration_minutes=None,
                baseline_planned_effort_minutes=None,
                current_start=curr_start,
                current_finish=curr_finish,
                current_duration_minutes=curr_dur,
                current_planned_effort_minutes=curr_eff,
                start_variance_minutes=None,
                finish_variance_minutes=None,
                duration_variance_minutes=None,
                effort_variance_minutes=None,
                variance_status=VarianceStatus.NOT_BASELINED,
                is_critical=is_critical,
            )

        if curr_start is None or curr_finish is None or b_start is None or b_finish is None:
            return TaskVarianceResult(
                task_id=task_id,
                has_baseline=True,
                baseline_start=b_start,
                baseline_finish=b_finish,
                baseline_duration_minutes=b_dur,
                baseline_planned_effort_minutes=b_eff,
                current_start=curr_start,
                current_finish=curr_finish,
                current_duration_minutes=curr_dur,
                current_planned_effort_minutes=curr_eff,
                start_variance_minutes=None,
                finish_variance_minutes=None,
                duration_variance_minutes=None,
                effort_variance_minutes=None,
                variance_status=VarianceStatus.UNAVAILABLE,
                is_critical=is_critical,
            )

        # Calculate variances (Current - Baseline)
        start_var = int((curr_start - b_start).total_seconds() / 60)
        finish_var = int((curr_finish - b_finish).total_seconds() / 60)
        dur_var = (curr_dur - b_dur) if (curr_dur is not None and b_dur is not None) else None
        eff_var = (curr_eff - b_eff) if b_eff is not None else None

        if finish_var < 0:
            status = VarianceStatus.AHEAD
        elif finish_var == 0:
            status = VarianceStatus.ON_BASELINE
        else:
            status = VarianceStatus.BEHIND

        return TaskVarianceResult(
            task_id=task_id,
            has_baseline=True,
            baseline_start=b_start,
            baseline_finish=b_finish,
            baseline_duration_minutes=b_dur,
            baseline_planned_effort_minutes=b_eff,
            current_start=curr_start,
            current_finish=curr_finish,
            current_duration_minutes=curr_dur,
            current_planned_effort_minutes=curr_eff,
            start_variance_minutes=start_var,
            finish_variance_minutes=finish_var,
            duration_variance_minutes=dur_var,
            effort_variance_minutes=eff_var,
            variance_status=status,
            is_critical=is_critical,
        )

    @classmethod
    def calculate_project_variance(
        cls,
        tasks: Sequence[Task],
        cpm_result: Optional[Any] = None,
        project: Optional[Project] = None
    ) -> Tuple[Dict[int, TaskVarianceResult], ProjectVarianceSummary]:
        """
        Calculates all task variances and aggregates project-level summary metrics.
        Runs in O(n) time.
        """
        cpm_nodes = getattr(cpm_result, "nodes", {}) if cpm_result else {}
        critical_ids = set(getattr(cpm_result, "critical_task_ids", ()) or ())
        critical_keys = set(getattr(cpm_result, "critical_keys", ()) or ())
        try:
            from todo_bird_app.services.wbs_cpm_adapter import cpm_node_for_key
            from todo_bird_app.services.wbs_service import EntityRef
        except Exception:  # pragma: no cover
            cpm_node_for_key = None  # type: ignore
            EntityRef = None  # type: ignore

        results: Dict[int, TaskVarianceResult] = {}
        total = len(tasks)
        baselined = 0
        not_baselined = 0
        ahead = 0
        on_baseline = 0
        behind = 0
        critical_behind = 0
        max_finish_var: Optional[int] = None
        has_baseline_project = bool(project and project.baseline_created_at)

        for task in tasks:
            tid = int(task.id or 0)
            cpm_node = cpm_nodes.get(tid)
            task_key = None
            if EntityRef is not None:
                try:
                    task_key = EntityRef.task(tid)
                except Exception:
                    task_key = None
            if cpm_node is None and cpm_node_for_key is not None and task_key is not None:
                cpm_node = cpm_node_for_key(cpm_result, task_key)
            is_crit = (
                (tid in critical_ids)
                or (task_key in critical_keys if task_key is not None else False)
                or (task.priority.value.lower() == "urgent")
            )
            res = cls.calculate_task_variance(task, cpm_node, is_critical=is_crit)
            results[tid] = res

            if res.has_baseline:
                baselined += 1
                has_baseline_project = True
                if res.variance_status == VarianceStatus.AHEAD:
                    ahead += 1
                elif res.variance_status == VarianceStatus.ON_BASELINE:
                    on_baseline += 1
                elif res.variance_status == VarianceStatus.BEHIND:
                    behind += 1
                    if res.is_critical:
                        critical_behind += 1

                if res.finish_variance_minutes is not None:
                    if max_finish_var is None or res.finish_variance_minutes > max_finish_var:
                        max_finish_var = res.finish_variance_minutes
            else:
                not_baselined += 1

        # Project finish variance: comparison of overall project finish date vs baseline
        proj_finish_var: Optional[int] = None
        if has_baseline_project and baselined > 0:
            earliest_curr_start = None
            latest_curr_finish = None
            earliest_base_start = None
            latest_base_finish = None

            for res in results.values():
                if res.has_baseline and res.baseline_start and res.baseline_finish:
                    if earliest_base_start is None or res.baseline_start < earliest_base_start:
                        earliest_base_start = res.baseline_start
                    if latest_base_finish is None or res.baseline_finish > latest_base_finish:
                        latest_base_finish = res.baseline_finish

                if res.current_start and res.current_finish:
                    if earliest_curr_start is None or res.current_start < earliest_curr_start:
                        earliest_curr_start = res.current_start
                    if latest_curr_finish is None or res.current_finish > latest_curr_finish:
                        latest_curr_finish = res.current_finish

            if latest_curr_finish and latest_base_finish:
                proj_finish_var = int((latest_curr_finish - latest_base_finish).total_seconds() / 60)

        proj_id = project.id if project else (tasks[0].project_id if tasks else None)
        b_created = project.baseline_created_at if project else None
        b_name = project.baseline_name if project else ("Baseline 1" if has_baseline_project else None)

        summary = ProjectVarianceSummary(
            project_id=proj_id,
            has_baseline=has_baseline_project,
            baseline_created_at=b_created,
            baseline_name=b_name,
            total_tasks=total,
            tasks_baselined=baselined,
            tasks_not_baselined=not_baselined,
            tasks_ahead=ahead,
            tasks_on_baseline=on_baseline,
            tasks_behind=behind,
            critical_tasks_behind=critical_behind,
            max_finish_variance_minutes=max_finish_var,
            project_finish_variance_minutes=proj_finish_var,
        )

        return results, summary

    @classmethod
    def capture_project_baseline_payload(
        cls,
        tasks: Sequence[Task],
        cpm_result: Optional[Any] = None
    ) -> Dict[int, Dict[str, Any]]:
        """
        Creates the snapshot payload for Baseline 1 based on current CPM/planned schedule truth.
        """
        cpm_nodes = getattr(cpm_result, "nodes", {}) if cpm_result else {}
        payload: Dict[int, Dict[str, Any]] = {}

        for task in tasks:
            tid = int(task.id or 0)
            if tid == 0:
                continue

            cpm_node = cpm_nodes.get(tid)
            b_start_dt: Optional[datetime] = None
            b_finish_dt: Optional[datetime] = None
            b_dur: int = 0
            b_eff: int = int(getattr(task, "planned_effort_minutes", 0) or 0)

            if cpm_node is not None and getattr(cpm_node, "schedulable", False) and getattr(cpm_node, "earliest_start", None) is not None:
                b_start_dt = cpm_node.earliest_start
                b_finish_dt = cpm_node.earliest_finish
                if b_start_dt and b_finish_dt:
                    b_dur = max(0, int((b_finish_dt - b_start_dt).total_seconds() / 60))
            else:
                p_date = getattr(task, "planned_date", None)
                p_time = getattr(task, "planned_start_time", None)
                d_date = getattr(task, "due_date", None) or p_date
                d_time = getattr(task, "planned_end_time", None)
                b_start_dt = parse_datetime_flexible(p_date, p_time)
                b_finish_dt = parse_datetime_flexible(d_date, d_time)
                if b_start_dt and b_finish_dt:
                    b_dur = max(0, int((b_finish_dt - b_start_dt).total_seconds() / 60))
                else:
                    b_dur = int(getattr(task, "estimated_duration", 0) or 0)

            payload[tid] = {
                "baseline_start": b_start_dt.strftime("%Y-%m-%d %H:%M") if b_start_dt else None,
                "baseline_finish": b_finish_dt.strftime("%Y-%m-%d %H:%M") if b_finish_dt else None,
                "baseline_duration_minutes": b_dur if b_start_dt else None,
                "baseline_planned_effort_minutes": b_eff,
            }

        return payload
