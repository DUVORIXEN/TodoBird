"""
TODO BIRD — DASHBOARD DATA SERVICE (Phase 2F Decision Cockpit)

Canonical, single-pass data service for both Portfolio Mode (All Projects)
and Project Mode. Produces immutable frozen dataclass models for the
Dashboard View, integrating CPM Scheduling, Schedule Variance, Execution
Performance, and WBS Rollups.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from todo_bird_app.models.project import Project
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.services.cpm_scheduling_service import (
    CPMSchedulingService,
    DiagnosticCode,
    SchedulingResult,
)
from todo_bird_app.services.execution_performance_service import (
    ExecutionPerformanceService,
    FinishPerformance,
    StartPerformance,
)
from todo_bird_app.services.schedule_variance_service import (
    ScheduleVarianceService,
    VarianceStatus,
)
from todo_bird_app.utils.time_math import utc_timestamp_to_local_date
from todo_bird_app.utils.working_calendar import (
    get_configured_working_weekdays,
    get_default_daily_capacity_minutes,
    get_working_days_between,
    is_working_day,
)

logger = logging.getLogger(__name__)


# ==============================================================================
# SCOPE & DOMAIN MODELS
# ==============================================================================

@dataclass(frozen=True)
class DashboardScope:
    mode: str = "portfolio"  # "portfolio" or "project"
    project_id: Optional[int] = None
    project_name: str = "All Projects"

    @property
    def is_portfolio(self) -> bool:
        return self.mode == "portfolio" or self.project_id is None

    @property
    def is_project(self) -> bool:
        return self.mode == "project" and self.project_id is not None


@dataclass(frozen=True)
class ExecutiveLayerData:
    active_tasks: int
    due_today: int
    overdue: int
    completed_today: int
    completion_rate: float
    planned_effort_today_mins: int
    actual_effort_today_mins: int
    daily_capacity_mins: int
    headroom_mins: int
    health_schedule: str  # "green", "yellow", "red"
    health_execution: str
    health_risk: str
    overall_health: str
    deltas: Dict[str, Optional[int]]
    health_tooltip: str
    health_schedule_reasons: List[str] = field(default_factory=list)
    health_execution_reasons: List[str] = field(default_factory=list)
    health_risk_reasons: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ProjectRankingItem:
    project_id: int
    name: str
    color: str
    health_status: str  # "green", "yellow", "red"
    health_s: str
    health_x: str
    health_r: str
    progress_pct: int
    cpm_finish: Optional[str]
    finish_variance_days: Optional[float]
    critical_tasks_count: int
    overdue_count: int
    blocked_count: int
    total_tasks: int


@dataclass(frozen=True)
class MilestoneItem:
    task_id: int
    title: str
    project_name: str
    target_date: str
    forecast_cpm: Optional[str]
    variance_days: Optional[float]
    status: str  # "upcoming", "due_soon", "late", "completed"


@dataclass(frozen=True)
class ScheduleLayerData:
    is_baselined: bool
    baseline_name: Optional[str]
    baseline_created_at: Optional[str]
    planned_start: Optional[str]
    planned_finish: Optional[str]
    cpm_finish: Optional[str]
    start_variance_days: Optional[float]
    finish_variance_days: Optional[float]
    critical_tasks_count: int
    critical_remaining_mins: int
    next_critical_task_title: Optional[str]
    next_critical_task_date: Optional[str]
    longest_critical_chain_days: Optional[float]
    critical_blocked_count: int
    critical_delayed_count: int
    mean_float_days: Optional[float]
    near_critical_count: int
    at_risk_wbs_count: int
    milestones: List[MilestoneItem]
    project_rankings: List[ProjectRankingItem]


@dataclass(frozen=True)
class ExecutionLayerData:
    focus_next_task: Optional[Task]
    focus_next_reason: str
    started_early: int
    started_on_time: int
    started_late: int
    finished_early: int
    finished_on_time: int
    finished_late: int
    execution_anomalies: int
    horizon_7d_starting: int
    horizon_7d_finishing: int
    horizon_7d_milestones: int
    horizon_7d_critical: int
    horizon_14d_starting: int
    horizon_14d_finishing: int
    horizon_14d_milestones: int
    horizon_14d_critical: int
    horizon_30d_starting: int
    horizon_30d_finishing: int
    horizon_30d_milestones: int
    horizon_30d_critical: int
    horizon_90d_starting: int
    horizon_90d_finishing: int
    horizon_90d_milestones: int
    horizon_90d_critical: int
    horizon_180d_starting: int
    horizon_180d_finishing: int
    horizon_180d_milestones: int
    horizon_180d_critical: int


@dataclass(frozen=True)
class RiskLayerData:
    overdue_count: int
    blocked_count: int
    delayed_count: int
    unscheduled_count: int
    negative_float_count: int
    near_critical_count: int
    dependency_cycles_count: int
    avg_blocker_age_days: float
    critical_blockers_count: int
    blocked_tasks_sample: List[Dict[str, Any]]


@dataclass(frozen=True)
class DataQualityData:
    zero_duration_count: int
    dangling_tasks_count: int
    missing_deadlines_count: int
    unbaselined_count: int
    negative_float_count: int
    fidelity_score: int  # 0 to 100


@dataclass(frozen=True)
class AttentionItem:
    severity: str  # "critical", "high", "warning", "info"
    badge_text: str
    title: str
    detail: str
    action_label: str
    target_view: str
    entity_id: Optional[int] = None


@dataclass(frozen=True)
class ActionLayerData:
    items: List[AttentionItem]
    total_attention_count: int


@dataclass(frozen=True)
class ChartData:
    status_planned: int
    status_in_progress: int
    status_blocked_delayed: int
    status_completed: int
    activity_by_days: Dict[int, List[Tuple[str, int, int]]]  # {days: [(label, completed, planned)]}
    effort_variance_daily: List[Tuple[str, int, int]]  # (label, planned_mins, actual_mins)


@dataclass(frozen=True)
class DashboardModel:
    scope: DashboardScope
    executive: ExecutiveLayerData
    schedule: ScheduleLayerData
    execution: ExecutionLayerData
    risk: RiskLayerData
    data_quality: DataQualityData
    actions: ActionLayerData
    charts: ChartData


# ==============================================================================
# CANONICAL SERVICE ENGINE
# ==============================================================================

class DashboardDataService:
    """
    High-performance, single-pass canonical dashboard service.
    Accepts a database manager and settings manager, performs optimized batch queries,
    and constructs the complete multi-layer DashboardModel.
    """

    @classmethod
    def build(
        cls,
        db_manager: Any,
        settings_manager: Any,
        scope: Optional[DashboardScope] = None,
        now: Optional[datetime] = None,
    ) -> DashboardModel:
        if scope is None:
            scope = DashboardScope(mode="portfolio", project_id=None, project_name="All Projects")
        if now is None:
            now = datetime.now()

        today_str = now.strftime("%Y-%m-%d")
        active_working_days = get_configured_working_weekdays(settings_manager)
        daily_capacity = get_default_daily_capacity_minutes(settings_manager)

        # 1. Fetch raw projects and tasks
        all_projects_raw = db_manager.get_all_projects() if db_manager else []
        active_projects = [p for p in all_projects_raw if not p.get("is_archived")]
        project_dict = {p["id"]: p for p in active_projects}

        if scope.is_project and scope.project_id:
            raw_tasks = db_manager.get_tasks_by_project(scope.project_id) if db_manager else []
            selected_project_raw = project_dict.get(scope.project_id)
        else:
            raw_tasks = db_manager.get_all_tasks() if db_manager else []
            selected_project_raw = None

        tasks: List[Task] = []
        for r in raw_tasks:
            try:
                tasks.append(Task.from_row(r))
            except Exception:
                pass

        # 2. Executive layer calculations
        today_tasks: List[Task] = []
        active_tasks_count = 0
        overdue_tasks: List[Task] = []
        completed_today: List[Task] = []
        blocked_tasks: List[Task] = []
        delayed_tasks: List[Task] = []
        unscheduled_tasks: List[Task] = []
        milestone_tasks: List[Task] = []

        planned_effort_today = 0
        actual_effort_today = 0

        for t in tasks:
            is_completed = (t.status == TaskStatus.COMPLETED)
            is_cancelled = (t.status == TaskStatus.CANCELLED)

            if not is_completed and not is_cancelled:
                active_tasks_count += 1

            is_m = bool(getattr(t, "is_milestone", False) or ("milestone" in (getattr(t, "tags", []) or [])))
            if is_m:
                milestone_tasks.append(t)

            # Check today's commitments
            is_today = False
            if t.planned_date == today_str or t.due_date == today_str:
                is_today = True
            elif t.planned_date and t.due_date and t.planned_date <= today_str <= t.due_date:
                is_today = True

            if is_today and not is_cancelled:
                today_tasks.append(t)
                alloc_mode = getattr(t, "allocation_mode", "fixed_daily") or "fixed_daily"
                if alloc_mode == "fixed_daily":
                    if is_working_day(today_str, working_weekdays=active_working_days) or t.planned_date == today_str or t.due_date == today_str:
                        planned_effort_today += int(getattr(t, "daily_dedication_minutes", 0) or 0)
                elif alloc_mode == "total_effort":
                    p_span = 1
                    if t.planned_date and t.due_date and t.planned_date <= t.due_date:
                        w_days = get_working_days_between(t.planned_date, t.due_date, working_weekdays=active_working_days)
                        p_span = max(1, len(w_days))
                    planned_effort_today += int(getattr(t, "planned_effort_minutes", 0) or 0) // p_span
                elif alloc_mode == "custom_by_day":
                    if db_manager and t.id:
                        allocs = db_manager.get_task_allocations(task_id=t.id)
                        for a in allocs:
                            if a.get("allocation_date") == today_str:
                                planned_effort_today += int(a.get("planned_minutes", 0) or 0)
                                actual_effort_today += int(a.get("actual_minutes", 0) or 0)
                else:
                    planned_effort_today += int(getattr(t, "planned_effort_minutes", 0) or 0)

                if alloc_mode != "custom_by_day":
                    actual_effort_today += int(getattr(t, "actual_duration", 0) or 0)

            # Overdue
            if not is_completed and not is_cancelled and t.due_date and t.due_date < today_str:
                overdue_tasks.append(t)

            # Completed today. updated_at is a UTC SQLite timestamp — compare
            # its LOCAL calendar date, else completions between local midnight
            # and the UTC offset are counted on the wrong day.
            if is_completed and (
                getattr(t, "actual_end_date", None) == today_str
                or utc_timestamp_to_local_date(t.updated_at) == now.date()
            ):
                completed_today.append(t)

            # Blocked / Delayed / Unscheduled
            if t.status == TaskStatus.BLOCKED:
                blocked_tasks.append(t)
            elif t.status == TaskStatus.DELAYED:
                delayed_tasks.append(t)

            if not is_completed and not is_cancelled and not t.planned_date and not t.due_date:
                unscheduled_tasks.append(t)

        due_today_count = len(today_tasks)
        overdue_count = len(overdue_tasks)
        completed_count = len(completed_today)
        # Rate = how many of TODAY'S commitments are done. completed_count spans
        # a different population (any task finished today, incl. overdue from
        # earlier days), so dividing it by due_today_count could exceed 100%.
        today_completed_count = sum(
            1 for t in today_tasks
            if t.status == TaskStatus.COMPLETED
            or getattr(t, "actual_end_date", None) == today_str
        )
        completion_rate = (
            round((today_completed_count / due_today_count) * 100.0, 1)
            if due_today_count > 0
            else 0.0
        )
        headroom_mins = daily_capacity - planned_effort_today

        # 3. Schedule & CPM calculations
        cpm_result: Optional[SchedulingResult] = None
        finish_var_days: Optional[float] = None
        start_var_days: Optional[float] = None
        cpm_finish_str: Optional[str] = None
        planned_start_str: Optional[str] = None
        planned_finish_str: Optional[str] = None
        critical_count = 0
        critical_remaining_mins = 0
        longest_chain_days: Optional[float] = None
        next_critical_title: Optional[str] = None
        next_critical_date: Optional[str] = None
        critical_blocked_count = 0
        critical_delayed_count = 0
        mean_float_days: Optional[float] = None
        near_critical_count = 0
        negative_float_count = 0
        cycle_count = 0
        is_baselined = False
        baseline_name = None
        baseline_created_at = None

        if scope.is_project and scope.project_id:
            # Single Project Scope
            proj_obj = Project.from_row(selected_project_raw) if selected_project_raw else None
            is_baselined = bool(proj_obj and proj_obj.baseline_created_at)
            baseline_name = "Baseline Rev 1" if is_baselined else None
            baseline_created_at = proj_obj.baseline_created_at if proj_obj else None

            try:
                cpm_result = CPMSchedulingService.calculate_schedule(
                    tasks,
                    project_id=scope.project_id,
                )
            except Exception as e:
                logger.warning(f"CPM computation error in Project mode: {e}")
                cpm_result = None

            if cpm_result:
                critical_ids = set(cpm_result.critical_task_ids or ())
                critical_count = len(critical_ids)
                diag_codes = [d.code for d in (cpm_result.diagnostics or ())]
                cycle_count = diag_codes.count(DiagnosticCode.DEPENDENCY_CYCLE)

                # Float and CPM finish date
                all_floats = []
                earliest_finishes = []
                for tid, node in cpm_result.nodes.items():
                    if node.earliest_finish:
                        earliest_finishes.append(node.earliest_finish)
                    if node.total_float_minutes is not None:
                        all_floats.append(node.total_float_minutes)
                        if node.total_float_minutes < 0:
                            negative_float_count += 1
                        elif 0 < node.total_float_minutes <= 1440:  # <= 1 day
                            near_critical_count += 1

                if earliest_finishes:
                    max_ef = max(earliest_finishes)
                    cpm_finish_str = max_ef.strftime("%Y-%m-%d")

                if all_floats:
                    mean_float_days = round((sum(all_floats) / len(all_floats)) / 1440.0, 1)

                # Critical path tasks remaining work and next critical
                crit_tasks_uncompleted = [
                    t for t in tasks
                    if (t.id in critical_ids or (cpm_result and getattr(cpm_result.nodes.get(t.id), "is_critical", False)))
                    and t.status != TaskStatus.COMPLETED
                ]
                critical_remaining_mins = sum(
                    int(getattr(t, "planned_effort_minutes", 0) or 0)
                    for t in crit_tasks_uncompleted
                )
                critical_blocked_count = sum(1 for t in crit_tasks_uncompleted if t.status == TaskStatus.BLOCKED)
                critical_delayed_count = sum(1 for t in crit_tasks_uncompleted if t.status == TaskStatus.DELAYED)

                if crit_tasks_uncompleted:
                    sorted_crit = sorted(
                        crit_tasks_uncompleted,
                        key=lambda x: x.planned_date or x.due_date or "9999-99-99",
                    )
                    next_critical_title = sorted_crit[0].title
                    next_critical_date = sorted_crit[0].planned_date or sorted_crit[0].due_date

                if cpm_result.project_start and cpm_result.project_finish:
                    longest_chain_days = round((cpm_result.project_finish - cpm_result.project_start).total_seconds() / 86400.0, 1)

            # Variance computation
            try:
                task_vars, proj_var = ScheduleVarianceService.calculate_project_variance(
                    tasks,
                    cpm_result=cpm_result,
                    project=proj_obj,
                )
                if proj_var.has_baseline and proj_var.project_finish_variance_minutes is not None:
                    finish_var_days = round(proj_var.project_finish_variance_minutes / 1440.0, 1)
            except Exception as e:
                logger.warning(f"Variance computation error: {e}")

            # Planned start and finish from tasks
            valid_starts = [t.planned_date for t in tasks if t.planned_date]
            valid_finishes = [t.due_date for t in tasks if t.due_date]
            if valid_starts:
                planned_start_str = min(valid_starts)
            if valid_finishes:
                planned_finish_str = max(valid_finishes)

        # 4. Portfolio Rankings (For Portfolio Mode)
        project_rankings: List[ProjectRankingItem] = []
        worst_s = "green"
        worst_x = "green"
        worst_r = "green"

        for p in active_projects:
            pid = p["id"]
            p_name = p.get("name", f"Project {pid}")
            p_color = p.get("color", "#3584E4") or "#3584E4"
            p_tasks_raw = db_manager.get_tasks_by_project(pid) if db_manager else []
            p_tasks = [Task.from_row(r) for r in p_tasks_raw]

            p_total = len(p_tasks)
            p_done = sum(1 for t in p_tasks if t.status == TaskStatus.COMPLETED)
            p_overdue = sum(1 for t in p_tasks if t.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED) and t.due_date and t.due_date < today_str)
            p_blocked = sum(1 for t in p_tasks if t.status == TaskStatus.BLOCKED)
            p_prog = int((p_done / p_total) * 100) if p_total > 0 else 0

            # Schedule health for project
            p_crit_count = 0
            p_var_days: Optional[float] = None
            p_cpm_finish: Optional[str] = None
            p_proj = Project.from_row(p)
            try:
                p_cpm = CPMSchedulingService.calculate_schedule(p_tasks, project_id=pid)
                if p_cpm:
                    p_crit_count = len(p_cpm.critical_task_ids or ())
                    all_efs = [n.earliest_finish for n in p_cpm.nodes.values() if n.earliest_finish]
                    if all_efs:
                        p_cpm_finish = max(all_efs).strftime("%Y-%m-%d")
                _, p_var_sum = ScheduleVarianceService.calculate_project_variance(
                    p_tasks, cpm_result=p_cpm, project=p_proj
                )
                if p_var_sum.has_baseline and p_var_sum.project_finish_variance_minutes is not None:
                    p_var_days = round(p_var_sum.project_finish_variance_minutes / 1440.0, 1)
            except Exception:
                pass

            # 3-signal rules for this project
            # S: Schedule
            if p_var_days is None or p_var_days <= 0:
                p_s = "green"
            elif p_var_days <= 2.0:
                p_s = "yellow"
            else:
                p_s = "red"

            # X: Execution
            if p_overdue == 0:
                p_x = "green"
            elif p_overdue <= 2:
                p_x = "yellow"
            else:
                p_x = "red"

            # R: Risk
            if p_blocked == 0:
                p_r = "green"
            elif p_blocked <= 2:
                p_r = "yellow"
            else:
                p_r = "red"

            # Project composite
            p_worst = "red" if "red" in (p_s, p_x, p_r) else ("yellow" if "yellow" in (p_s, p_x, p_r) else "green")

            # Track portfolio worst
            if p_s == "red" or worst_s == "red":
                worst_s = "red"
            elif p_s == "yellow" and worst_s != "red":
                worst_s = "yellow"

            if p_x == "red" or worst_x == "red":
                worst_x = "red"
            elif p_x == "yellow" and worst_x != "red":
                worst_x = "yellow"

            if p_r == "red" or worst_r == "red":
                worst_r = "red"
            elif p_r == "yellow" and worst_r != "red":
                worst_r = "yellow"

            project_rankings.append(ProjectRankingItem(
                project_id=pid,
                name=p_name,
                color=p_color,
                health_status=p_worst,
                health_s=p_s,
                health_x=p_x,
                health_r=p_r,
                progress_pct=p_prog,
                cpm_finish=p_cpm_finish,
                finish_variance_days=p_var_days,
                critical_tasks_count=p_crit_count,
                overdue_count=p_overdue,
                blocked_count=p_blocked,
                total_tasks=p_total,
            ))

        # Sort project rankings: Risk-First (Red > Yellow > Green, then overdue desc)
        health_weight = {"red": 0, "yellow": 1, "green": 2}
        project_rankings.sort(
            key=lambda x: (health_weight.get(x.health_status, 3), -x.overdue_count, -x.critical_tasks_count)
        )

        # 9. Blocker Analytics & Data Quality (Moved before Health for variable availability)
        avg_blocker_age = 0.0
        if blocked_tasks:
            ages = []
            for bt in blocked_tasks:
                if bt.updated_at:
                    try:
                        u_dt = datetime.fromisoformat(str(bt.updated_at).replace("Z", "+00:00")).date()
                        ages.append(max(0, (now.date() - u_dt).days))
                    except Exception:
                        ages.append(1)
                else:
                    ages.append(1)
            avg_blocker_age = round(sum(ages) / len(ages), 1) if ages else 1.0

        # Data quality checks
        zero_dur_count = sum(1 for t in tasks if (getattr(t, "estimated_duration", 0) or 0) == 0 and not getattr(t, "is_milestone", False) and t.status != TaskStatus.COMPLETED)
        dangling_count = 0
        for t in tasks:
            if not getattr(t, "is_milestone", False) and t.status != TaskStatus.COMPLETED:
                raw_deps = getattr(t, "dependencies", None)
                if not raw_deps:
                    dangling_count += 1

        missing_deadlines = sum(1 for t in tasks if not t.planned_date and not t.due_date and t.status != TaskStatus.COMPLETED)
        unbaselined_count = sum(1 for t in tasks if getattr(t, "baseline_created_at", None) is None and t.status != TaskStatus.COMPLETED) if is_baselined else 0
        fidelity_score = max(0, min(100, 100 - (zero_dur_count * 2 + dangling_count + missing_deadlines * 2 + negative_float_count * 5)))

        # 5. Composite Health Indicators (Now after blocker analytics for avg_blocker_age)
        if scope.is_project:
            # Single Project Health
            # --- Schedule Health (S) ---
            s_reasons = []
            if finish_var_days is None or finish_var_days <= 0:
                h_s = "green"
                if finish_var_days is not None:
                    s_reasons.append(f"Forecast finish is {finish_var_days:+.1f} days vs baseline (on track)")
                else:
                    s_reasons.append("No baseline set — cannot evaluate schedule variance")
            elif finish_var_days <= 2.0:
                h_s = "yellow"
                s_reasons.append(f"Forecast finish is {finish_var_days:+.1f} days behind baseline (slip ≤2 days)")
            else:
                h_s = "red"
                s_reasons.append(f"Forecast finish is {finish_var_days:+.1f} days behind baseline (slip >2 days)")

            # --- Execution Health (X) ---
            x_reasons = []
            if overdue_count == 0:
                h_x = "green"
                x_reasons.append("No overdue commitments")
            elif overdue_count <= 2 and not any(t.priority.value.lower() == "urgent" for t in overdue_tasks):
                h_x = "yellow"
                x_reasons.append(f"{overdue_count} overdue task(s) — no urgent priority")
            else:
                h_x = "red"
                urgent_overdue = sum(1 for t in overdue_tasks if t.priority.value.lower() == "urgent")
                if urgent_overdue:
                    x_reasons.append(f"{overdue_count} overdue task(s) including {urgent_overdue} urgent")
                else:
                    x_reasons.append(f"{overdue_count} overdue task(s) — exceeds threshold")

            # --- Risk Health (R) - Comprehensive Forward-Looking Exposure ---
            r_reasons = []
            risk_triggers = []

            # Critical Risk Triggers (RED)
            if negative_float_count > 0:
                risk_triggers.append(("critical", f"{negative_float_count} task(s) with negative total float (schedule infeasible)"))
            if cycle_count > 0:
                risk_triggers.append(("critical", f"{cycle_count} dependency cycle(s) detected"))
            if critical_blocked_count > 0:
                risk_triggers.append(("critical", f"{critical_blocked_count} critical path task(s) blocked"))
            if critical_delayed_count > 0:
                risk_triggers.append(("critical", f"{critical_delayed_count} critical path task(s) delayed"))
            
            # Check for missed hard deadlines (overdue critical tasks)
            critical_overdue = [t for t in overdue_tasks if t.id in (cpm_result.critical_task_ids if cpm_result else ())]
            if critical_overdue:
                risk_triggers.append(("critical", f"{len(critical_overdue)} critical task(s) missed hard deadline"))

            # Warning Risk Triggers (AMBER)
            if len(blocked_tasks) > 0 and not risk_triggers:
                if len(blocked_tasks) <= 2:
                    risk_triggers.append(("warning", f"{len(blocked_tasks)} task(s) blocked (avg blocker age: {avg_blocker_age:.1f} days)"))
                else:
                    risk_triggers.append(("critical", f"{len(blocked_tasks)} task(s) blocked (avg blocker age: {avg_blocker_age:.1f} days)"))

            if len(delayed_tasks) > 0 and not any(t[0] == "critical" for t in risk_triggers):
                if len(delayed_tasks) <= 2:
                    risk_triggers.append(("warning", f"{len(delayed_tasks)} task(s) delayed"))
                else:
                    risk_triggers.append(("critical", f"{len(delayed_tasks)} task(s) delayed"))

            if near_critical_count > 0 and not any(t[0] == "critical" for t in risk_triggers):
                risk_triggers.append(("warning", f"{near_critical_count} near-critical task(s) (float ≤1 day)"))

            # Check for upcoming hard deadline with thin float (within 7 days, float < 2 days)
            if cpm_result and cpm_result.nodes:
                upcoming_critical_deadlines = 0
                for tid in (cpm_result.critical_task_ids or ()):
                    node = cpm_result.nodes.get(tid)
                    if node and node.earliest_finish:
                        days_to_finish = (node.earliest_finish.date() - now.date()).days
                        if 0 <= days_to_finish <= 7:
                            if node.total_float_minutes is not None and node.total_float_minutes < 2880:  # < 2 days
                                upcoming_critical_deadlines += 1
                if upcoming_critical_deadlines > 0 and not any(t[0] == "critical" for t in risk_triggers):
                    risk_triggers.append(("warning", f"{upcoming_critical_deadlines} critical deadline(s) within 7 days with float <2 days"))

            # High blocker ageing
            if avg_blocker_age > 5 and len(blocked_tasks) > 0 and not any(t[0] == "critical" for t in risk_triggers):
                risk_triggers.append(("warning", f"Blocker ageing high: {avg_blocker_age:.1f} days average"))

            # Determine final R color from triggers
            has_critical = any(t[0] == "critical" for t in risk_triggers)
            has_warning = any(t[0] == "warning" for t in risk_triggers)
            
            if has_critical:
                h_r = "red"
            elif has_warning:
                h_r = "yellow"
            else:
                h_r = "green"
                r_reasons.append("No blocked, delayed-critical, negative-float, cycle, deadline, or constraint risk currently detected")

            # Add trigger reasons
            for severity, reason in risk_triggers:
                r_reasons.append(f"[{severity.upper()}] {reason}")

            overall_h = "red" if "red" in (h_s, h_x, h_r) else ("yellow" if "yellow" in (h_s, h_x, h_r) else "green")
            
            # Build detailed tooltip with reasons
            h_tooltip = (
                f"Project Health: {overall_h.upper()}\n"
                f"• Schedule (S): {h_s.upper()} ({f'{finish_var_days:+.1f}d' if finish_var_days is not None else 'No Baseline'})\n"
                f"• Execution (X): {h_x.upper()} ({overdue_count} overdue)\n"
                f"• Risk (R): {h_r.upper()} "
            )
            if r_reasons:
                h_tooltip += "\n" + "\n".join(f"  - {r}" for r in r_reasons)
            else:
                h_tooltip += f"({len(blocked_tasks)} blocked, {negative_float_count} neg float)"
        else:
            # Portfolio Health (Worst of active projects)
            h_s = worst_s
            h_x = worst_x
            h_r = worst_r
            overall_h = "red" if "red" in (h_s, h_x, h_r) else ("yellow" if "yellow" in (h_s, h_x, h_r) else "green")
            
            # Collect portfolio-level risk reasons from worst projects
            portfolio_r_reasons = []
            # Find projects with RED risk
            red_risk_projects = [p for p in project_rankings if p.health_r == "red"]
            if red_risk_projects:
                portfolio_r_reasons.append(f"{len(red_risk_projects)} project(s) with critical schedule risk")
                for p in red_risk_projects[:3]:
                    portfolio_r_reasons.append(f"  - {p.name}: {p.blocked_count} blocked, {p.critical_tasks_count} critical")
            
            h_tooltip = (
                f"Portfolio Health: {overall_h.upper()}\n"
                f"• Schedule (S): {h_s.upper()}\n"
                f"• Execution (X): {h_x.upper()}\n"
                f"• Risk (R): {h_r.upper()}"
            )
            if portfolio_r_reasons:
                h_tooltip += "\n" + "\n".join(portfolio_r_reasons)

        # Create reason lists for UI
        s_reasons = locals().get('s_reasons', [])
        x_reasons = locals().get('x_reasons', [])
        r_reasons = locals().get('r_reasons', [])

        # 6. Milestone Watchlist items
        milestone_items: List[MilestoneItem] = []
        for mt in milestone_tasks:
            target_d = mt.due_date or mt.planned_date or "No Target"
            proj_name = project_dict.get(mt.project_id, {}).get("name", "Project") if mt.project_id else "General"
            m_stat = "upcoming"
            if mt.status == TaskStatus.COMPLETED:
                m_stat = "completed"
            elif target_d != "No Target" and target_d < today_str:
                m_stat = "late"
            elif target_d != "No Target" and target_d <= (now + timedelta(days=7)).strftime("%Y-%m-%d"):
                m_stat = "due_soon"

            milestone_items.append(MilestoneItem(
                task_id=int(mt.id or 0),
                title=mt.title,
                project_name=proj_name,
                target_date=target_d,
                forecast_cpm=target_d,  # CPM aligned or target
                variance_days=0.0,
                status=m_stat,
            ))

        # Sort milestones: Late first, then Due Soon, then Upcoming, Completed last
        m_order = {"late": 0, "due_soon": 1, "upcoming": 2, "completed": 3}
        milestone_items.sort(key=lambda m: (m_order.get(m.status, 4), m.target_date))

        # 7. Focus Next Selection (Deterministic Cascade)
        focus_task: Optional[Task] = None
        focus_reason = ""

        # Step 1: Overdue Urgent/High
        overdue_urgent = [t for t in overdue_tasks if t.priority.value.lower() in ("urgent", "high")]
        if overdue_urgent:
            focus_task = overdue_urgent[0]
            focus_reason = "Overdue high priority task requiring immediate resolution"
        # Step 2: In-Progress tasks
        if not focus_task:
            in_prog = [t for t in tasks if t.status == TaskStatus.IN_PROGRESS]
            if in_prog:
                focus_task = in_prog[0]
                focus_reason = "Currently in progress"
        # Step 3: Today's Urgent/High tasks
        if not focus_task:
            today_urgent = [t for t in today_tasks if t.priority.value.lower() in ("urgent", "high") and t.status != TaskStatus.COMPLETED]
            if today_urgent:
                focus_task = today_urgent[0]
                focus_reason = "High priority task scheduled for today"
        # Step 4: Today's scheduled tasks
        if not focus_task:
            today_pending = [t for t in today_tasks if t.status != TaskStatus.COMPLETED]
            if today_pending:
                focus_task = today_pending[0]
                focus_reason = "Scheduled commitment for today"
        # Step 5: First active task
        if not focus_task:
            active_list = [t for t in tasks if t.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)]
            if active_list:
                focus_task = active_list[0]
                focus_reason = "Next available active task"

        # 8. Upcoming Horizons (7D, 14D, 30D)
        def _horizon_metrics(days_ahead: int) -> Tuple[int, int, int, int]:
            h_end = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
            starting = sum(1 for t in tasks if t.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED) and t.planned_date and today_str <= t.planned_date <= h_end)
            finishing = sum(1 for t in tasks if t.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED) and t.due_date and today_str <= t.due_date <= h_end)
            m_count = sum(1 for t in milestone_tasks if t.status != TaskStatus.COMPLETED and (t.due_date or t.planned_date) and today_str <= (t.due_date or t.planned_date or "") <= h_end)
            crit_count = 0
            if cpm_result and cpm_result.critical_task_ids:
                crit_set = set(cpm_result.critical_task_ids)
                crit_count = sum(1 for t in tasks if t.id in crit_set and t.status != TaskStatus.COMPLETED and t.due_date and today_str <= t.due_date <= h_end)
            return starting, finishing, m_count, crit_count

        h7_s, h7_f, h7_m, h7_c = _horizon_metrics(7)
        h14_s, h14_f, h14_m, h14_c = _horizon_metrics(14)
        h30_s, h30_f, h30_m, h30_c = _horizon_metrics(30)
        h90_s, h90_f, h90_m, h90_c = _horizon_metrics(90)
        h180_s, h180_f, h180_m, h180_c = _horizon_metrics(180)

        # 9. Blocker Analytics & Data Quality
        avg_blocker_age = 0.0
        if blocked_tasks:
            ages = []
            for bt in blocked_tasks:
                if bt.updated_at:
                    try:
                        u_dt = datetime.fromisoformat(str(bt.updated_at).replace("Z", "+00:00")).date()
                        ages.append(max(0, (now.date() - u_dt).days))
                    except Exception:
                        ages.append(1)
                else:
                    ages.append(1)
            avg_blocker_age = round(sum(ages) / len(ages), 1) if ages else 1.0

        # Data quality checks
        zero_dur_count = sum(1 for t in tasks if (getattr(t, "estimated_duration", 0) or 0) == 0 and not getattr(t, "is_milestone", False) and t.status != TaskStatus.COMPLETED)
        dangling_count = 0
        for t in tasks:
            if not getattr(t, "is_milestone", False) and t.status != TaskStatus.COMPLETED:
                raw_deps = getattr(t, "dependencies", None)
                if not raw_deps:
                    dangling_count += 1

        missing_deadlines = sum(1 for t in tasks if not t.planned_date and not t.due_date and t.status != TaskStatus.COMPLETED)
        unbaselined_count = sum(1 for t in tasks if getattr(t, "baseline_created_at", None) is None and t.status != TaskStatus.COMPLETED) if is_baselined else 0
        fidelity_score = max(0, min(100, 100 - (zero_dur_count * 2 + dangling_count + missing_deadlines * 2 + negative_float_count * 5)))

        # 10. Prioritized Needs Attention Queue (Top 5 Display, True Total Count)
        all_attention_items: List[AttentionItem] = []
        seen_entity_ids = set()

        crit_blockers = [t for t in blocked_tasks if t.id in (cpm_result.critical_task_ids if cpm_result else ())]
        for cb in crit_blockers:
            seen_entity_ids.add(cb.id)
            all_attention_items.append(AttentionItem(
                severity="critical",
                badge_text="CRITICAL BLOCKER",
                title=cb.title,
                detail="Blocked on critical path; holding project delivery",
                action_label="Unblock",
                target_view="tasks",
                entity_id=cb.id,
            ))

        for ot in overdue_urgent:
            if ot.id not in seen_entity_ids:
                seen_entity_ids.add(ot.id)
                all_attention_items.append(AttentionItem(
                    severity="critical",
                    badge_text="OVERDUE URGENT",
                    title=ot.title,
                    detail=f"Overdue since {ot.due_date}",
                    action_label="Resolve",
                    target_view="tasks",
                    entity_id=ot.id,
                ))

        for bt in [t for t in blocked_tasks if t.id not in seen_entity_ids]:
            seen_entity_ids.add(bt.id)
            all_attention_items.append(AttentionItem(
                severity="high",
                badge_text="BLOCKED",
                title=bt.title,
                detail="Waiting on external dependency or blocker resolution",
                action_label="Inspect",
                target_view="tasks",
                entity_id=bt.id,
            ))

        for ot in overdue_tasks:
            if ot.id not in seen_entity_ids:
                seen_entity_ids.add(ot.id)
                all_attention_items.append(AttentionItem(
                    severity="warning",
                    badge_text="OVERDUE",
                    title=ot.title,
                    detail=f"Overdue since {ot.due_date}",
                    action_label="Reschedule",
                    target_view="tasks",
                    entity_id=ot.id,
                ))

        if headroom_mins < 0:
            all_attention_items.append(AttentionItem(
                severity="warning",
                badge_text="CAPACITY OVERLOAD",
                title="Daily Capacity Exceeded",
                detail=f"Planned effort exceeds daily limit by {abs(headroom_mins)//60}h {abs(headroom_mins)%60}m",
                action_label="Rebalance",
                target_view="calendar",
            ))

        if focus_task and focus_task.id not in seen_entity_ids:
            all_attention_items.append(AttentionItem(
                severity="info",
                badge_text="FOCUS NEXT",
                title=focus_task.title,
                detail=focus_reason,
                action_label="Start",
                target_view="tasks",
                entity_id=focus_task.id,
            ))

        # 11. Chart Data Aggregations (Single-Pass O(N))
        p_cnt = sum(1 for t in today_tasks if t.status in (TaskStatus.PLANNED, TaskStatus.INBOX))
        prog_cnt = sum(1 for t in today_tasks if t.status == TaskStatus.IN_PROGRESS)
        blk_cnt = sum(1 for t in today_tasks if t.status in (TaskStatus.BLOCKED, TaskStatus.DELAYED))
        done_cnt = sum(1 for t in today_tasks if t.status == TaskStatus.COMPLETED)

        # Pre-index completed tasks and planned tasks by date
        completed_by_date: Dict[str, int] = {}
        planned_by_date: Dict[str, int] = {}
        planned_effort_by_date: Dict[str, int] = {}
        actual_effort_by_date: Dict[str, int] = {}

        for t in tasks:
            if t.status == TaskStatus.COMPLETED:
                c_date = getattr(t, "actual_end_date", None) or (str(t.updated_at)[:10] if t.updated_at else None)
                if c_date:
                    completed_by_date[c_date] = completed_by_date.get(c_date, 0) + 1
                    actual_effort_by_date[c_date] = actual_effort_by_date.get(c_date, 0) + int(getattr(t, "actual_duration", 0) or 0)
            if t.planned_date:
                planned_by_date[t.planned_date] = planned_by_date.get(t.planned_date, 0) + 1
                planned_effort_by_date[t.planned_date] = planned_effort_by_date.get(t.planned_date, 0) + int(getattr(t, "planned_effort_minutes", 0) or 0)

        # Build activity sequences
        def _build_activity(days_count: int) -> List[Tuple[str, int, int]]:
            res = []
            for i in range(days_count - 1, -1, -1):
                d = (now.date() - timedelta(days=i)).strftime("%Y-%m-%d")
                d_label = (now.date() - timedelta(days=i)).strftime("%a" if days_count <= 7 else "%d %b")
                c_done = completed_by_date.get(d, 0)
                p_plan = planned_by_date.get(d, 0)
                res.append((d_label, c_done, p_plan))
            return res

        activity_by_days = {}
        for days in (7, 14, 30, 90):
            activity_by_days[days] = _build_activity(days)

        # Build effort variance daily
        effort_daily: List[Tuple[str, int, int]] = []
        for i in range(6, -1, -1):
            d = (now.date() - timedelta(days=i)).strftime("%Y-%m-%d")
            d_label = (now.date() - timedelta(days=i)).strftime("%a")
            p_eff = planned_effort_by_date.get(d, 0)
            a_eff = actual_effort_by_date.get(d, 0)
            effort_daily.append((d_label, p_eff, a_eff))

        # Assemble Model
        return DashboardModel(
            scope=scope,
            executive=ExecutiveLayerData(
                active_tasks=active_tasks_count,
                due_today=due_today_count,
                overdue=overdue_count,
                completed_today=completed_count,
                completion_rate=completion_rate,
                planned_effort_today_mins=planned_effort_today,
                actual_effort_today_mins=actual_effort_today,
                daily_capacity_mins=daily_capacity,
                headroom_mins=headroom_mins,
                health_schedule=h_s,
                health_execution=h_x,
                health_risk=h_r,
                overall_health=overall_h,
                deltas={"active": None, "overdue": None, "completed": None},
                health_tooltip=h_tooltip,
                health_schedule_reasons=s_reasons,
                health_execution_reasons=x_reasons,
                health_risk_reasons=r_reasons,
            ),
            schedule=ScheduleLayerData(
                is_baselined=is_baselined,
                baseline_name=baseline_name,
                baseline_created_at=baseline_created_at,
                planned_start=planned_start_str,
                planned_finish=planned_finish_str,
                cpm_finish=cpm_finish_str,
                start_variance_days=start_var_days,
                finish_variance_days=finish_var_days,
                critical_tasks_count=critical_count,
                critical_remaining_mins=critical_remaining_mins,
                next_critical_task_title=next_critical_title,
                next_critical_task_date=next_critical_date,
                longest_critical_chain_days=longest_chain_days,
                critical_blocked_count=critical_blocked_count,
                critical_delayed_count=critical_delayed_count,
                mean_float_days=mean_float_days,
                near_critical_count=near_critical_count,
                at_risk_wbs_count=0,
                milestones=milestone_items,
                project_rankings=project_rankings,
            ),
            execution=ExecutionLayerData(
                focus_next_task=focus_task,
                focus_next_reason=focus_reason,
                started_early=0,
                started_on_time=0,
                started_late=0,
                finished_early=0,
                finished_on_time=0,
                finished_late=0,
                execution_anomalies=0,
                horizon_7d_starting=h7_s,
                horizon_7d_finishing=h7_f,
                horizon_7d_milestones=h7_m,
                horizon_7d_critical=h7_c,
                horizon_14d_starting=h14_s,
                horizon_14d_finishing=h14_f,
                horizon_14d_milestones=h14_m,
                horizon_14d_critical=h14_c,
                horizon_30d_starting=h30_s,
                horizon_30d_finishing=h30_f,
                horizon_30d_milestones=h30_m,
                horizon_30d_critical=h30_c,
                horizon_90d_starting=h90_s,
                horizon_90d_finishing=h90_f,
                horizon_90d_milestones=h90_m,
                horizon_90d_critical=h90_c,
                horizon_180d_starting=h180_s,
                horizon_180d_finishing=h180_f,
                horizon_180d_milestones=h180_m,
                horizon_180d_critical=h180_c,
            ),
            risk=RiskLayerData(
                overdue_count=overdue_count,
                blocked_count=len(blocked_tasks),
                delayed_count=len(delayed_tasks),
                unscheduled_count=len(unscheduled_tasks),
                negative_float_count=negative_float_count,
                near_critical_count=near_critical_count,
                dependency_cycles_count=cycle_count,
                avg_blocker_age_days=avg_blocker_age,
                critical_blockers_count=critical_blocked_count,
                blocked_tasks_sample=[{"id": t.id, "title": t.title} for t in blocked_tasks[:5]],
            ),
            data_quality=DataQualityData(
                zero_duration_count=zero_dur_count,
                dangling_tasks_count=dangling_count,
                missing_deadlines_count=missing_deadlines,
                unbaselined_count=unbaselined_count,
                negative_float_count=negative_float_count,
                fidelity_score=fidelity_score,
            ),
            actions=ActionLayerData(
                items=all_attention_items[:5],
                total_attention_count=len(all_attention_items),
            ),
            charts=ChartData(
                status_planned=p_cnt,
                status_in_progress=prog_cnt,
                status_blocked_delayed=blk_cnt,
                status_completed=done_cnt,
                activity_by_days=activity_by_days,
                effort_variance_daily=effort_daily,
            ),
        )
