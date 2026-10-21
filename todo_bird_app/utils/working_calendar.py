"""
Working Calendar & Daily Workload Allocation Authority (Batch 3.3C)
Centralized Single Authority for working weekdays, capacity, overallocation,
effort distribution, and custom-day overrides.
"""

import json
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Optional, Any, Set, Union

logger = logging.getLogger(__name__)

# Monday=0, Tuesday=1, Wednesday=2, Thursday=3, Friday=4, Saturday=5, Sunday=6
DEFAULT_WORKING_WEEKDAYS: Set[int] = {0, 1, 2, 3, 4}  # Mon-Fri
DEFAULT_DAILY_CAPACITY_MINUTES: int = 480              # 8 hours / day

_GLOBAL_WORKING_WEEKDAYS: Set[int] = set(DEFAULT_WORKING_WEEKDAYS)
_GLOBAL_DAILY_CAPACITY_MINUTES: int = DEFAULT_DAILY_CAPACITY_MINUTES


def parse_date(val: Any) -> Optional[date]:
    if not val:
        return None
    if isinstance(val, date):
        return val
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def get_configured_working_weekdays(settings_manager: Optional[Any] = None) -> Set[int]:
    """
    Returns the currently active configured working weekdays set.
    """
    if settings_manager is not None:
        raw_work = settings_manager.get("working_weekdays")
        if raw_work is not None and isinstance(raw_work, list):
            return {int(d) for d in raw_work if 0 <= int(d) <= 6}
        raw_weekend = settings_manager.get("weekend_days")
        if raw_weekend is not None and isinstance(raw_weekend, list):
            weekends = {int(d) for d in raw_weekend if 0 <= int(d) <= 6}
            return {d for d in range(7) if d not in weekends}

    return set(_GLOBAL_WORKING_WEEKDAYS)


def set_configured_working_weekdays(weekdays: Union[Set[int], List[int]], settings_manager: Optional[Any] = None):
    """
    Sets and persists configured working weekdays.
    """
    global _GLOBAL_WORKING_WEEKDAYS
    valid_set = {int(d) for d in weekdays if 0 <= int(d) <= 6}
    _GLOBAL_WORKING_WEEKDAYS = valid_set

    if settings_manager is not None:
        settings_manager.set("working_weekdays", sorted(list(valid_set)))
        # Keep legacy weekend_days in sync for older views
        weekends = sorted(list({d for d in range(7) if d not in valid_set}))
        settings_manager.set("weekend_days", weekends)

    try:
        from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
        _GLOBAL_EVENT_BUS.working_calendar_changed.emit()
    except Exception:
        pass


def reset_working_calendar_defaults():
    """
    Resets global in-memory working calendar defaults to Mon-Fri and 480m.
    """
    global _GLOBAL_WORKING_WEEKDAYS, _GLOBAL_DAILY_CAPACITY_MINUTES
    _GLOBAL_WORKING_WEEKDAYS = set(DEFAULT_WORKING_WEEKDAYS)
    _GLOBAL_DAILY_CAPACITY_MINUTES = DEFAULT_DAILY_CAPACITY_MINUTES


def get_default_daily_capacity_minutes(settings_manager: Optional[Any] = None) -> int:
    """
    Returns default daily resource capacity in minutes (e.g. 480 for 8h).
    """
    if settings_manager is not None:
        raw = settings_manager.get("default_daily_capacity_minutes")
        if raw is not None:
            try:
                return max(0, int(raw))
            except Exception:
                pass
    return _GLOBAL_DAILY_CAPACITY_MINUTES


def set_default_daily_capacity_minutes(minutes: int, settings_manager: Optional[Any] = None):
    """
    Sets and persists default daily resource capacity.
    """
    global _GLOBAL_DAILY_CAPACITY_MINUTES
    _GLOBAL_DAILY_CAPACITY_MINUTES = max(0, int(minutes))
    if settings_manager is not None:
        settings_manager.set("default_daily_capacity_minutes", _GLOBAL_DAILY_CAPACITY_MINUTES)


def is_working_day(
    target_date: Any,
    working_weekdays: Optional[Set[int]] = None,
    holidays: Optional[Set[str]] = None,
    custom_overrides: Optional[Dict[str, int]] = None,
    settings_manager: Optional[Any] = None,
) -> bool:
    """
    Determines if target_date is a working day.
    - Explicit custom_overrides with minutes > 0 count as working overrides.
    - Explicit holidays count as non-working.
    - Otherwise checked against configured working weekdays.
    """
    td = parse_date(target_date)
    if not td:
        return False

    iso = td.strftime("%Y-%m-%d")

    if custom_overrides and iso in custom_overrides:
        return int(custom_overrides[iso] or 0) > 0

    if holidays and iso in holidays:
        return False

    if working_weekdays is None:
        working_weekdays = get_configured_working_weekdays(settings_manager)

    return td.weekday() in working_weekdays


def get_working_days_between(
    start_date: Any,
    end_date: Any,
    working_weekdays: Optional[Set[int]] = None,
    holidays: Optional[Set[str]] = None,
    custom_overrides: Optional[Dict[str, int]] = None,
    settings_manager: Optional[Any] = None,
) -> List[date]:
    """
    Returns list of working dates between start_date and end_date (inclusive).
    """
    sd = parse_date(start_date)
    ed = parse_date(end_date)
    if not sd:
        return []
    if not ed or ed < sd:
        ed = sd

    if working_weekdays is None:
        working_weekdays = get_configured_working_weekdays(settings_manager)

    days = []
    curr = sd
    while curr <= ed:
        if is_working_day(curr, working_weekdays, holidays, custom_overrides, settings_manager):
            days.append(curr)
        curr += timedelta(days=1)
    return days


def distribute_total_effort_minutes(
    total_effort_minutes: int,
    working_days: List[date],
) -> Dict[str, int]:
    """
    Distributes total_effort_minutes across working_days using exact integer remainder math.
    Zero floating point loss. Guaranteed sum(result.values()) == total_effort_minutes.
    """
    total = max(0, int(total_effort_minutes or 0))
    if not working_days or total == 0:
        return {}

    n = len(working_days)
    base_mins = total // n
    remainder = total % n

    result: Dict[str, int] = {}
    for i, d in enumerate(working_days):
        iso = d.strftime("%Y-%m-%d")
        extra = 1 if i < remainder else 0
        result[iso] = base_mins + extra

    return result


def calculate_overallocation(
    daily_capacity_minutes: int,
    allocated_minutes: int,
) -> Dict[str, int]:
    """
    Calculates resource workload utilization, remaining capacity, and overload in exact integer minutes.
    """
    capacity = max(0, int(daily_capacity_minutes or 0))
    allocated = max(0, int(allocated_minutes or 0))
    remaining = max(0, capacity - allocated)
    overload = max(0, allocated - capacity)

    return {
        "capacity_minutes": capacity,
        "allocated_minutes": allocated,
        "remaining_minutes": remaining,
        "overload_minutes": overload,
        "is_overloaded": overload > 0,
    }


def calculate_planned_effort(
    start_date: Any,
    end_date: Any,
    daily_dedication_minutes: int,
    allocation_mode: str = "fixed_daily",
    total_effort_minutes: int = 0,
    custom_allocations: Optional[Dict[str, int]] = None,
    working_weekdays: Optional[Set[int]] = None,
    holidays: Optional[Set[str]] = None,
) -> int:
    """
    Calculates total planned effort in integer minutes.
    - fixed_daily: daily_dedication_minutes * number of applicable working days
    - total_effort: returns specified total_effort_minutes
    - custom_by_day: sum of all custom allocations for the range
    """
    if working_weekdays is None:
        working_weekdays = get_configured_working_weekdays()

    mode = (allocation_mode or "fixed_daily").lower()

    if mode == "fixed_daily":
        applicable_days = get_working_days_between(start_date, end_date, working_weekdays, holidays)
        daily_m = max(0, int(daily_dedication_minutes or 0))
        return len(applicable_days) * daily_m

    elif mode == "total_effort":
        return max(0, int(total_effort_minutes or 0))

    elif mode == "custom_by_day":
        if custom_allocations:
            return sum(max(0, int(v or 0)) for v in custom_allocations.values())
        applicable_days = get_working_days_between(start_date, end_date, working_weekdays, holidays)
        daily_m = max(0, int(daily_dedication_minutes or 0))
        return len(applicable_days) * daily_m

    applicable_days = get_working_days_between(start_date, end_date, working_weekdays, holidays)
    return max(0, int(daily_dedication_minutes or 0)) * len(applicable_days)
