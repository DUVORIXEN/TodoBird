from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Dict, Any
import json
from datetime import datetime, date, time

class TaskPriority(Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    URGENT = "Urgent"

class TaskStatus(Enum):
    INBOX = "Inbox"
    PLANNED = "Planned"
    IN_PROGRESS = "In Progress"
    BLOCKED = "Blocked"
    COMPLETED = "Completed"
    DELAYED = "Delayed"
    MOVED = "Moved"
    CANCELLED = "Cancelled"

class TaskCategory(Enum):
    WORK = "Work"
    PERSONAL = "Personal"
    HEALTH = "Health"
    FINANCE = "Finance"
    LEARNING = "Learning"
    OTHER = "Other"

STARTUP_REMINDER_OFF = "off"
STARTUP_REMINDER_DAILY_FIRST = "daily_first_open"
STARTUP_REMINDER_EVERY_APP = "every_app_open"

@dataclass
class Task:
    id: Optional[int] = None
    title: str = ""
    project_id: Optional[int] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    tags: List[str] = field(default_factory=list)
    category: TaskCategory = TaskCategory.WORK
    description: str = ""
    planned_date: Optional[str] = None  # YYYY-MM-DD
    due_date: Optional[str] = None      # YYYY-MM-DD
    planned_start_time: Optional[str] = None  # HH:MM
    planned_end_time: Optional[str] = None    # HH:MM
    actual_start_time: Optional[str] = None   # HH:MM
    actual_end_time: Optional[str] = None     # HH:MM
    actual_start_date: Optional[str] = None   # YYYY-MM-DD
    actual_end_date: Optional[str] = None     # YYYY-MM-DD
    estimated_duration: int = 0         # In minutes
    actual_duration: int = 0            # In minutes
    progress: int = 0                   # 0 to 100
    notes: str = ""
    recurring: Optional[str] = None     # e.g., 'daily', 'weekly', or JSON config
    dependencies: List[int] = field(default_factory=list)  # List of Task IDs
    status: TaskStatus = TaskStatus.INBOX
    # Migration v2 delay tracking fields
    delay_minutes: int = 0
    delay_percentage: float = 0.0
    delay_category: str = ""
    delay_reason: str = ""
    delay_notes: str = ""
    delay_recorded_at: Optional[str] = None
    completion_rating: int = 5
    completed_before_plan: bool = False
    show_in_gantt: bool = True
    startup_reminder: bool = False
    startup_reminder_mode: str = "off"

    # Migration v8 persistent colored pinning
    is_pinned: bool = False
    pin_color: str = "#E95420"
    pin_position: int = 0

    # Migration v12 Canonical position / WBS sibling order authority
    position: int = 0

    def __post_init__(self):
        if self.startup_reminder_mode == "off" and self.startup_reminder:
            self.startup_reminder_mode = "daily_first_open"
        elif self.startup_reminder_mode != "off":
            self.startup_reminder = True

    # Migration v10 Planned effort and daily dedication
    planned_effort_minutes: int = 0
    daily_dedication_minutes: int = 0
    allocation_mode: str = "fixed_daily"

    # Migration v11 Cover / Media image
    image_path: str = ""

    # Migration v14 Schedule Baseline 1 (Phase 2D)
    baseline_start: Optional[str] = None
    baseline_finish: Optional[str] = None
    baseline_duration_minutes: Optional[int] = None
    baseline_planned_effort_minutes: Optional[int] = None

    # Migration v15 Schedule Constraints & Deadlines (Phase 2E)
    constraint_type: str = "ASAP"
    constraint_datetime: Optional[str] = None
    deadline_datetime: Optional[str] = None

    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @property
    def planned_elapsed_minutes(self) -> int:
        return int(self.estimated_duration or 0)

    @property
    def actual_elapsed_minutes(self) -> int:
        from todo_bird_app.utils.time_math import calculate_actual_elapsed_minutes
        if not self.actual_start_date or not self.actual_start_time:
            return 0
        ed = self.actual_end_date or self.actual_start_date
        et = self.actual_end_time or "23:59"
        return calculate_actual_elapsed_minutes(self.actual_start_date, self.actual_start_time, ed, et)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "project_id": self.project_id,
            "priority": self.priority.value,
            "tags": json.dumps(self.tags),
            "category": self.category.value,
            "description": self.description,
            "planned_date": self.planned_date,
            "due_date": self.due_date,
            "planned_start_time": self.planned_start_time,
            "planned_end_time": self.planned_end_time,
            "actual_start_time": self.actual_start_time,
            "actual_end_time": self.actual_end_time,
            "actual_start_date": self.actual_start_date,
            "actual_end_date": self.actual_end_date,
            "estimated_duration": self.estimated_duration,
            "actual_duration": self.actual_duration,
            "progress": self.progress,
            "notes": self.notes,
            "recurring": self.recurring,
            "dependencies": json.dumps([d.to_dict() if hasattr(d, "to_dict") else d for d in self.dependencies]) if isinstance(self.dependencies, (list, tuple)) else (self.dependencies or "[]"),
            "status": self.status.value,
            "delay_minutes": self.delay_minutes,
            "delay_percentage": self.delay_percentage,
            "delay_category": self.delay_category,
            "delay_reason": self.delay_reason,
            "delay_notes": self.delay_notes,
            "delay_recorded_at": self.delay_recorded_at,
            "completion_rating": self.completion_rating,
            "completed_before_plan": 1 if self.completed_before_plan else 0,
            "show_in_gantt": 1 if self.show_in_gantt else 0,
            "startup_reminder": 1 if self.startup_reminder else 0,
            "startup_reminder_mode": self.startup_reminder_mode,
            "is_pinned": 1 if self.is_pinned else 0,
            "pin_color": self.pin_color,
            "pin_position": self.pin_position,
            "position": self.position,
            "planned_effort_minutes": self.planned_effort_minutes,
            "daily_dedication_minutes": self.daily_dedication_minutes,
            "allocation_mode": self.allocation_mode,
            "image_path": self.image_path,
            "baseline_start": self.baseline_start,
            "baseline_finish": self.baseline_finish,
            "baseline_duration_minutes": self.baseline_duration_minutes,
            "baseline_planned_effort_minutes": self.baseline_planned_effort_minutes,
            "constraint_type": self.constraint_type,
            "constraint_datetime": self.constraint_datetime,
            "deadline_datetime": self.deadline_datetime,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Task":
        tags = []
        if "tags" in row and row["tags"]:
            try:
                tags = json.loads(row["tags"])
            except Exception:
                tags = [t.strip() for t in str(row["tags"]).split(",") if t.strip()]

        dependencies = []
        if "dependencies" in row and row["dependencies"]:
            if isinstance(row["dependencies"], (list, tuple)):
                dependencies = list(row["dependencies"])
            elif isinstance(row["dependencies"], str):
                try:
                    dependencies = json.loads(row["dependencies"])
                except Exception:
                    dependencies = []

        raw_prio = row.get("priority", "Medium")
        try:
            priority = TaskPriority(raw_prio)
        except ValueError:
            priority = TaskPriority.MEDIUM

        raw_cat = row.get("category", "Work")
        try:
            category = TaskCategory(raw_cat)
        except ValueError:
            category = TaskCategory.WORK

        raw_status = row.get("status", "Inbox")
        try:
            status = TaskStatus(raw_status)
        except (ValueError, TypeError):
            status = TaskStatus.INBOX

        raw_mode = row.get("startup_reminder_mode")
        if raw_mode:
            startup_reminder_mode = str(raw_mode).lower().strip()
        elif bool(row.get("startup_reminder", False)):
            startup_reminder_mode = STARTUP_REMINDER_DAILY_FIRST
        else:
            startup_reminder_mode = STARTUP_REMINDER_OFF
        startup_reminder = (startup_reminder_mode != STARTUP_REMINDER_OFF)

        raw_bdur = row.get("baseline_duration_minutes")
        baseline_duration_minutes = int(raw_bdur) if raw_bdur is not None else None

        raw_beff = row.get("baseline_planned_effort_minutes")
        baseline_planned_effort_minutes = int(raw_beff) if raw_beff is not None else None

        return cls(
            id=row.get("id"),
            title=row.get("title", ""),
            project_id=row.get("project_id"),
            priority=priority,
            tags=tags,
            category=category,
            description=row.get("description", ""),
            planned_date=row.get("planned_date"),
            due_date=row.get("due_date"),
            planned_start_time=row.get("planned_start_time"),
            planned_end_time=row.get("planned_end_time"),
            actual_start_time=row.get("actual_start_time"),
            actual_end_time=row.get("actual_end_time"),
            actual_start_date=row.get("actual_start_date"),
            actual_end_date=row.get("actual_end_date"),
            estimated_duration=row.get("estimated_duration", 0),
            actual_duration=row.get("actual_duration", 0),
            progress=row.get("progress", 0),
            notes=row.get("notes", ""),
            recurring=row.get("recurring"),
            dependencies=dependencies,
            status=status,
            delay_minutes=row.get("delay_minutes", 0),
            delay_percentage=float(row.get("delay_percentage", 0.0)),
            delay_category=row.get("delay_category", ""),
            delay_reason=row.get("delay_reason", ""),
            delay_notes=row.get("delay_notes", ""),
            delay_recorded_at=row.get("delay_recorded_at"),
            completion_rating=row.get("completion_rating", 5),
            completed_before_plan=bool(row.get("completed_before_plan", False)),
            show_in_gantt=bool(row.get("show_in_gantt", True)),
            startup_reminder=startup_reminder,
            startup_reminder_mode=startup_reminder_mode,
            is_pinned=bool(row.get("is_pinned", False)),
            pin_color=row.get("pin_color", "#E95420"),
            pin_position=int(row.get("pin_position", 0) or 0),
            position=int(row.get("position", 0) or 0),
            planned_effort_minutes=int(row.get("planned_effort_minutes", 0) or 0),
            daily_dedication_minutes=int(row.get("daily_dedication_minutes", 0) or 0),
            allocation_mode=row.get("allocation_mode", "fixed_daily"),
            image_path=row.get("image_path", "") or "",
            baseline_start=row.get("baseline_start"),
            baseline_finish=row.get("baseline_finish"),
            baseline_duration_minutes=baseline_duration_minutes,
            baseline_planned_effort_minutes=baseline_planned_effort_minutes,
            constraint_type=row.get("constraint_type") or "ASAP",
            constraint_datetime=row.get("constraint_datetime"),
            deadline_datetime=row.get("deadline_datetime"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
