import logging
from datetime import date, datetime, timedelta
from typing import List, Union

logger = logging.getLogger(__name__)

# Weekday convention: Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6
WEEKDAY_NAMES = [
    (0, "Monday"),
    (1, "Tuesday"),
    (2, "Wednesday"),
    (3, "Thursday"),
    (4, "Friday"),
    (5, "Saturday"),
    (6, "Sunday"),
]

DEFAULT_WEEKEND_DAYS = [5, 6]  # Saturday & Sunday

class WorkingWeekService:
    """
    Central service for user-defined working week and weekend day preferences.
    Used consistently across Gantt chart, Calendar view, Analytics, and Daily Review.
    """
    def __init__(self, settings_manager):
        self.settings_manager = settings_manager

    def get_working_weekdays(self) -> List[int]:
        from todo_bird_app.utils.working_calendar import get_configured_working_weekdays
        return sorted(list(get_configured_working_weekdays(self.settings_manager)))

    def set_working_weekdays(self, days: List[int]):
        from todo_bird_app.utils.working_calendar import set_configured_working_weekdays
        set_configured_working_weekdays(set(days), self.settings_manager)

    def get_weekend_days(self) -> List[int]:
        work_days = set(self.get_working_weekdays())
        return sorted(list({d for d in range(7) if d not in work_days}))

    def set_weekend_days(self, days: List[int]):
        valid_weekends = {int(d) for d in days if 0 <= int(d) <= 6}
        work_days = [d for d in range(7) if d not in valid_weekends]
        self.set_working_weekdays(work_days)

    def is_weekend(self, target: Union[date, datetime, int]) -> bool:
        if isinstance(target, (date, datetime)):
            w = target.weekday()
        else:
            w = int(target)
        return w in self.get_weekend_days()

    def get_working_days_count(self, start: date, end: date) -> int:
        from todo_bird_app.utils.working_calendar import get_working_days_between
        return len(get_working_days_between(start, end, set(self.get_working_weekdays())))
