import logging
from enum import Enum
from typing import List, Tuple
from todo_bird_app.models.task import Task, TaskPriority, TaskStatus

logger = logging.getLogger(__name__)

class WorkloadState(Enum):
    UNDER_CAPACITY = "Under capacity"
    BALANCED = "Balanced"
    SLIGHTLY_OVERLOADED = "Slightly overloaded"
    SEVERELY_OVERLOADED = "Severely overloaded"

class WorkloadEngine:
    """
    Calculates daily workload confidence and overload metrics based on planned durations
    and available working hours.
    """
    def __init__(self, settings_manager):
        self.settings_manager = settings_manager

    def evaluate_day_workload(self, tasks: List[Task], available_hours: float = 8.0) -> Tuple[WorkloadState, float, float, str]:
        planned_minutes = sum(t.estimated_duration for t in tasks if t.status != TaskStatus.COMPLETED)
        planned_hours = planned_minutes / 60.0
        available_minutes = available_hours * 60.0

        if available_minutes <= 0:
            ratio = 1.0
        else:
            ratio = planned_minutes / available_minutes

        if ratio <= 0.6:
            state = WorkloadState.UNDER_CAPACITY
            advice = "✨ You have plenty of available capacity. Great time to focus on complex or creative tasks!"
        elif ratio <= 1.0:
            state = WorkloadState.BALANCED
            advice = "🎯 Your workload is balanced and achievable within your target working hours."
        elif ratio <= 1.25:
            state = WorkloadState.SLIGHTLY_OVERLOADED
            advice = "⚠️ Slightly overloaded. Consider moving 1 lower-priority task to tomorrow or reducing durations."
        else:
            state = WorkloadState.SEVERELY_OVERLOADED
            advice = "🚨 Severely overloaded! Move non-essential tasks to upcoming days to protect your focus and energy."

        return state, planned_hours, available_hours, advice
