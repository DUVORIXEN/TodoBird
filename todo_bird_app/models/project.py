from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import json

@dataclass
class Project:
    id: Optional[int] = None
    name: str = ""
    color: str = "#E95420"  # Ubuntu accent default
    icon: str = "folder"
    description: str = ""
    is_archived: bool = False
    created_at: Optional[str] = None
    # Migration v14 Schedule Baseline 1 (Phase 2D)
    baseline_created_at: Optional[str] = None
    baseline_name: Optional[str] = None
    # Migration v15 Project Calendar & Exceptions (Phase 2E)
    working_weekdays: Optional[List[int]] = None
    calendar_exceptions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "icon": self.icon,
            "description": self.description,
            "is_archived": 1 if self.is_archived else 0,
            "created_at": self.created_at,
            "baseline_created_at": self.baseline_created_at,
            "baseline_name": self.baseline_name,
            "working_weekdays": json.dumps(self.working_weekdays) if self.working_weekdays is not None else None,
            "calendar_exceptions": json.dumps(self.calendar_exceptions) if self.calendar_exceptions else "[]",
        }

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "Project":
        raw_work = row.get("working_weekdays")
        work_days = None
        if raw_work:
            if isinstance(raw_work, (list, tuple)):
                work_days = list(raw_work)
            elif isinstance(raw_work, str):
                try:
                    work_days = json.loads(raw_work)
                except Exception:
                    work_days = None

        raw_ex = row.get("calendar_exceptions")
        exceptions = []
        if raw_ex:
            if isinstance(raw_ex, list):
                exceptions = list(raw_ex)
            elif isinstance(raw_ex, str):
                try:
                    exceptions = json.loads(raw_ex)
                except Exception:
                    exceptions = []

        return cls(
            id=row.get("id"),
            name=row.get("name", ""),
            color=row.get("color", "#E95420"),
            icon=row.get("icon", "folder"),
            description=row.get("description", ""),
            is_archived=bool(row.get("is_archived", 0)),
            created_at=row.get("created_at"),
            baseline_created_at=row.get("baseline_created_at"),
            baseline_name=row.get("baseline_name"),
            working_weekdays=work_days,
            calendar_exceptions=exceptions,
        )
