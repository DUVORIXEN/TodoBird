import logging
from datetime import date, timedelta
from typing import Dict, Any, List, Optional
from todo_bird_app.models.task import Task, TaskStatus

logger = logging.getLogger(__name__)

class ReviewController:
    """
    Controller calculating Daily Review and Plan vs Actual metrics.
    """
    def __init__(self, db_manager, settings_manager: Optional[Any] = None):
        self.db_manager = db_manager
        self.settings_manager = settings_manager

    def get_daily_review_summary(self, target_date: str = None) -> Dict[str, Any]:
        if target_date is None:
            target_date = date.today().strftime("%Y-%m-%d")

        t_date = date.fromisoformat(target_date)
        tomorrow_str = (t_date + timedelta(days=1)).strftime("%Y-%m-%d")

        rows = self.db_manager.get_all_tasks()
        all_tasks = [Task.from_row(r) for r in rows]

        # 1. Planned for today (or multi-day span intersecting today)
        planned_tasks = [
            t for t in all_tasks
            if t.planned_date == target_date
            or (t.planned_date and t.due_date and t.planned_date <= target_date <= t.due_date)
        ]

        # 2. Completed today
        completed_today = [
            t for t in all_tasks
            if (t.actual_end_date == target_date or (t.planned_date == target_date and t.status == TaskStatus.COMPLETED))
        ]

        # 3. Overdue active tasks
        overdue_tasks = [
            t for t in all_tasks
            if t.due_date and t.due_date < target_date and t.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
        ]

        # 4. Carryover (started/planned before today, still active)
        carryover_tasks = [
            t for t in all_tasks
            if t.planned_date and t.planned_date < target_date and t.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
        ]

        # 5. Tomorrow commitments
        tomorrow_tasks = [
            t for t in all_tasks
            if (t.planned_date == tomorrow_str or t.due_date == tomorrow_str) and t.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
        ]

        completed = [t for t in planned_tasks if t.status == TaskStatus.COMPLETED]
        delayed = [t for t in planned_tasks if t.status == TaskStatus.DELAYED]
        moved = [t for t in planned_tasks if t.status == TaskStatus.MOVED]
        cancelled = [t for t in planned_tasks if t.status == TaskStatus.CANCELLED]
        in_progress = [t for t in planned_tasks if t.status == TaskStatus.IN_PROGRESS]
        pending = [t for t in planned_tasks if t.status in (TaskStatus.PLANNED, TaskStatus.INBOX)]

        total_planned = len(planned_tasks)
        completed_count = len(completed_today) if completed_today else len(completed)

        # Productivity Score Calculation
        if total_planned > 0:
            productivity_score = round(((len(completed) + 0.5 * len(in_progress)) / total_planned) * 100, 1)
        else:
            productivity_score = 100.0 if completed_count > 0 else 0.0

        # Effort calculations
        planned_effort_total = sum(
            t.daily_dedication_minutes if t.daily_dedication_minutes > 0
            else (t.planned_effort_minutes if t.planned_effort_minutes > 0 else t.estimated_duration)
            for t in planned_tasks
        )
        # A task both planned today and completed today appears in BOTH lists;
        # dedupe so "Actual Effort Logged" is not double-counted.
        seen_ids = set()
        effort_tasks = []
        for t in list(planned_tasks) + list(completed_today):
            tid = getattr(t, "id", None)
            if tid is not None:
                if tid in seen_ids:
                    continue
                seen_ids.add(tid)
            effort_tasks.append(t)
        actual_effort_total = sum(int(t.actual_duration or 0) for t in effort_tasks)

        daily_capacity = 480
        if self.settings_manager:
            daily_capacity = int(self.settings_manager.get("default_daily_capacity_minutes", 480) or 480)

        remaining_capacity = max(0, daily_capacity - planned_effort_total)

        return {
            "date": target_date,
            "tomorrow_date": tomorrow_str,
            "total_planned": total_planned,
            "completed_count": completed_count,
            "delayed_count": len(delayed),
            "moved_count": len(moved),
            "cancelled_count": len(cancelled),
            "in_progress_count": len(in_progress),
            "pending_count": len(pending),
            "overdue_count": len(overdue_tasks),
            "carryover_count": len(carryover_tasks),
            "tomorrow_count": len(tomorrow_tasks),
            "productivity_score": productivity_score,
            "est_duration_total": sum(t.estimated_duration for t in planned_tasks),
            "act_duration_total": actual_effort_total,
            "planned_effort_total": planned_effort_total,
            "daily_capacity": daily_capacity,
            "remaining_capacity": remaining_capacity,
            "planned_tasks": planned_tasks,
            "completed_tasks": completed_today or completed,
            "overdue_tasks": overdue_tasks,
            "carryover_tasks": carryover_tasks,
            "tomorrow_tasks": tomorrow_tasks,
            "pending_tasks": pending + in_progress,
        }
