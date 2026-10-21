"""
TODO BIRD - SCHEDULE CALENDAR AUTHORITY (Phase 2E)

Pure working-calendar arithmetic for CPM. The Phase 2E scope is day-level
working calendars, not shift calendars: a working date contributes all 1,440
minutes, while a non-working date contributes zero minutes.

Precedence:
1. Project date exception/override.
2. Explicit project weekday rule, or DB-resolved global working-week fallback.
3. Default Mon-Fri calendar when no project/global calendar is configured.

Actual execution remains full elapsed calendar time and must not use this
service.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Mapping, Optional, Set

MINUTES_PER_DAY = 24 * 60
DEFAULT_WORKING_WEEKDAYS = (0, 1, 2, 3, 4)
_MAX_DAY_STEPS = 20000


def _calendar_value(project_calendar: Any, key: str, default: Any = None) -> Any:
    if isinstance(project_calendar, Mapping):
        return project_calendar.get(key, default)
    return getattr(project_calendar, key, default)


def _coerce_weekdays(raw_weekdays: Any) -> tuple[int, ...]:
    if raw_weekdays is None:
        return DEFAULT_WORKING_WEEKDAYS
    if isinstance(raw_weekdays, str):
        try:
            raw_weekdays = json.loads(raw_weekdays)
        except Exception:
            return DEFAULT_WORKING_WEEKDAYS
    if isinstance(raw_weekdays, int):
        raw_weekdays = (raw_weekdays,)

    try:
        weekdays = tuple(
            sorted(
                {
                    int(day)
                    for day in raw_weekdays
                    if 0 <= int(day) <= 6
                }
            )
        )
    except Exception:
        weekdays = ()
    return weekdays or DEFAULT_WORKING_WEEKDAYS


def _coerce_exception_items(raw_exceptions: Any) -> tuple[Any, ...]:
    if raw_exceptions is None:
        return ()
    if isinstance(raw_exceptions, str):
        try:
            raw_exceptions = json.loads(raw_exceptions)
        except Exception:
            return ()
    if isinstance(raw_exceptions, Mapping):
        raw_exceptions = (raw_exceptions,)
    try:
        return tuple(raw_exceptions or ())
    except Exception:
        return ()


def _calendar_exception_items(project_calendar: Any) -> tuple[Any, ...]:
    if isinstance(project_calendar, ScheduleCalendar):
        items = [
            {"date": iso, "is_working": True, "name": "Working override"}
            for iso in sorted(project_calendar.working_overrides)
        ]
        items.extend(
            {"date": iso, "is_working": False, "name": "Holiday"}
            for iso in sorted(project_calendar.holidays)
        )
        return tuple(items)

    raw = _calendar_value(project_calendar, "exceptions", None)
    if raw is None:
        raw = _calendar_value(project_calendar, "calendar_exceptions", None)
    return _coerce_exception_items(raw)


def _exception_value(exception: Any, key: str, default: Any = None) -> Any:
    if isinstance(exception, Mapping):
        return exception.get(key, default)
    return getattr(exception, key, default)


def _exception_date_str(exception: Any) -> str:
    raw = (
        _exception_value(exception, "date_str", None)
        or _exception_value(exception, "date", None)
        or _exception_value(exception, "exception_date", "")
    )
    return str(raw or "")[:10]


def _exception_is_working(exception: Any) -> bool:
    raw = _exception_value(exception, "is_working", False)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return int(raw) == 1
    return str(raw).strip().lower() in {"1", "true", "yes", "working"}


def _exception_name(exception: Any) -> str:
    return str(_exception_value(exception, "name", "") or "")


@dataclass(frozen=True)
class CalendarDateStatus:
    date_str: str
    is_working: bool
    label: str
    source: str
    reason: str = ""
    exception_name: str = ""


@dataclass(frozen=True)
class ScheduleCalendar:
    working_weekdays: tuple[int, ...] = DEFAULT_WORKING_WEEKDAYS
    holidays: frozenset[str] = frozenset()
    working_overrides: frozenset[str] = frozenset()

    @classmethod
    def from_project_calendar(cls, project_calendar: Optional[Any]) -> Optional["ScheduleCalendar"]:
        if project_calendar is None:
            return None
        if isinstance(project_calendar, cls):
            return project_calendar

        raw_weekdays = _calendar_value(
            project_calendar,
            "working_weekdays",
            DEFAULT_WORKING_WEEKDAYS,
        )
        weekdays = _coerce_weekdays(raw_weekdays)

        holidays: Set[str] = set()
        overrides: Set[str] = set()
        exceptions = _calendar_exception_items(project_calendar)
        for exc in exceptions:
            date_str = _exception_date_str(exc)
            if not date_str:
                continue
            is_working = _exception_is_working(exc)
            if is_working:
                overrides.add(date_str)
                holidays.discard(date_str)
            else:
                holidays.add(date_str)
                overrides.discard(date_str)

        return cls(
            working_weekdays=weekdays,
            holidays=frozenset(holidays),
            working_overrides=frozenset(overrides),
        )

    def is_working_day(self, target: Any) -> bool:
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
        if iso in self.working_overrides:
            return True
        if iso in self.holidays:
            return False
        return d.weekday() in self.working_weekdays

    def next_working_datetime(self, value: datetime) -> datetime:
        if self.is_working_day(value):
            return value
        target_day = value.date()
        for _ in range(_MAX_DAY_STEPS):
            target_day += timedelta(days=1)
            if self.is_working_day(target_day):
                return datetime.combine(target_day, value.time())
        raise OverflowError("No next working day found within schedule calendar bound.")

    def previous_working_datetime(self, value: datetime) -> datetime:
        if self.is_working_day(value):
            return value
        target_day = value.date()
        for _ in range(_MAX_DAY_STEPS):
            target_day -= timedelta(days=1)
            if self.is_working_day(target_day):
                return datetime.combine(target_day, value.time())
        raise OverflowError("No previous working day found within schedule calendar bound.")

    def previous_working_day(self, before_or_on: date) -> date:
        target_day = before_or_on
        for _ in range(_MAX_DAY_STEPS):
            if self.is_working_day(target_day):
                return target_day
            target_day -= timedelta(days=1)
        raise OverflowError("No previous working day found within schedule calendar bound.")

    def next_working_day(self, after_or_on: date) -> date:
        target_day = after_or_on
        for _ in range(_MAX_DAY_STEPS):
            if self.is_working_day(target_day):
                return target_day
            target_day += timedelta(days=1)
        raise OverflowError("No next working day found within schedule calendar bound.")


def classify_calendar_date(project_calendar: Optional[Any], target: Any) -> CalendarDateStatus:
    if isinstance(target, datetime):
        d = target.date()
    elif isinstance(target, date):
        d = target
    else:
        try:
            d = datetime.strptime(str(target)[:10], "%Y-%m-%d").date()
        except Exception:
            return CalendarDateStatus(
                date_str=str(target or ""),
                is_working=False,
                label="Invalid date",
                source="invalid_date",
            )

    iso = d.strftime("%Y-%m-%d")
    matched_exception = None
    for exc in _calendar_exception_items(project_calendar):
        if _exception_date_str(exc) != iso:
            continue
        matched_exception = exc

    if matched_exception is not None:
        is_working = _exception_is_working(matched_exception)
        name = _exception_name(matched_exception)
        if is_working:
            return CalendarDateStatus(
                date_str=iso,
                is_working=True,
                label="Working override",
                source="calendar_exception",
                reason="Explicit working-date exception overrides weekday rule.",
                exception_name=name,
            )
        label = "Holiday" if "holiday" in name.lower() else "Non-working exception"
        return CalendarDateStatus(
            date_str=iso,
            is_working=False,
            label=label,
            source="calendar_exception",
            reason="Explicit non-working date exception overrides weekday rule.",
            exception_name=name,
        )

    calendar = calendar_from_project(project_calendar)
    if calendar is None:
        calendar = ScheduleCalendar()

    if d.weekday() in calendar.working_weekdays:
        return CalendarDateStatus(
            date_str=iso,
            is_working=True,
            label="Working",
            source="weekday_rule",
            reason="Date weekday is enabled in the project working weekdays.",
        )
    return CalendarDateStatus(
        date_str=iso,
        is_working=False,
        label="Non-working",
        source="weekday_rule",
        reason="Date weekday is not enabled in the project working weekdays.",
    )


def project_calendar_spec_from_source(
    project_calendar: Optional[Any],
    project_id: Optional[int] = None,
) -> Optional[Any]:
    if project_calendar is None:
        return None

    from todo_bird_app.services.schedule_constraint_service import (
        CalendarException,
        ProjectCalendarSpec,
    )

    if isinstance(project_calendar, ProjectCalendarSpec):
        if project_id is None or project_calendar.project_id == project_id:
            return project_calendar
        return ProjectCalendarSpec(
            project_id=project_id,
            working_weekdays=project_calendar.working_weekdays,
            exceptions=project_calendar.exceptions,
        )

    resolved_project_id = project_id
    if resolved_project_id is None:
        raw_project_id = _calendar_value(project_calendar, "project_id", None)
        try:
            resolved_project_id = int(raw_project_id) if raw_project_id is not None else None
        except (TypeError, ValueError):
            resolved_project_id = None

    exceptions = tuple(
        CalendarException(
            date_str=_exception_date_str(exc),
            is_working=_exception_is_working(exc),
            name=_exception_name(exc),
        )
        for exc in _calendar_exception_items(project_calendar)
        if _exception_date_str(exc)
    )
    return ProjectCalendarSpec(
        project_id=resolved_project_id,
        working_weekdays=_coerce_weekdays(
            _calendar_value(project_calendar, "working_weekdays", DEFAULT_WORKING_WEEKDAYS)
        ),
        exceptions=exceptions,
    )


def effective_project_calendar_from_db(
    db_manager: Optional[Any],
    project_id: Optional[int],
) -> Optional[Any]:
    if (
        project_id is None
        or db_manager is None
        or not hasattr(db_manager, "get_project_calendar")
    ):
        return None
    try:
        clean_project_id = int(project_id)
    except (TypeError, ValueError):
        return None
    try:
        return project_calendar_spec_from_source(
            db_manager.get_project_calendar(clean_project_id),
            project_id=clean_project_id,
        )
    except Exception:
        return None


def calendar_from_project(project_calendar: Optional[Any]) -> Optional[ScheduleCalendar]:
    return ScheduleCalendar.from_project_calendar(project_calendar)


def is_working_day(project_calendar: Optional[Any], target: Any) -> bool:
    calendar = calendar_from_project(project_calendar)
    if calendar is None:
        calendar = ScheduleCalendar()
    return calendar.is_working_day(target)


def next_working_datetime(value: datetime, project_calendar: Optional[Any]) -> datetime:
    calendar = calendar_from_project(project_calendar)
    if calendar is None:
        return value
    return calendar.next_working_datetime(value)


def previous_working_datetime(value: datetime, project_calendar: Optional[Any]) -> datetime:
    calendar = calendar_from_project(project_calendar)
    if calendar is None:
        return value
    return calendar.previous_working_datetime(value)


def add_working_days_preserve_time(
    start: datetime,
    day_count: int,
    project_calendar: Optional[Any],
) -> datetime:
    """
    Place a nominal working-day duration on the project calendar.

    This is intentionally separate from add_working_minutes: Todo Bird stores
    one scheduled day as 1,440 nominal minutes, but whole-day placement uses
    the working-date sequence. Day 1 is the first effective working date at the
    original clock time, so Tue + 5 working days on a Mon-Sat calendar lands
    on Saturday at the same clock time.
    """
    clean_days = max(0, int(day_count or 0))
    calendar = calendar_from_project(project_calendar)

    if calendar is None:
        if clean_days <= 0:
            return start
        return start + timedelta(days=clean_days - 1)

    current = calendar.next_working_datetime(start)
    if clean_days <= 1:
        return current

    current_day = current.date()
    remaining = clean_days - 1
    for _ in range(_MAX_DAY_STEPS):
        current_day += timedelta(days=1)
        if calendar.is_working_day(current_day):
            remaining -= 1
            if remaining <= 0:
                return datetime.combine(current_day, current.time())

    raise OverflowError("Working-day placement exceeded schedule calendar bound.")


def subtract_working_days_preserve_time(
    finish: datetime,
    day_count: int,
    project_calendar: Optional[Any],
) -> datetime:
    """
    Reverse of add_working_days_preserve_time for backward CPM placement.

    Day 1 is the finish date itself when it is working. For example, subtracting
    5 working days from Sat 2026-09-05 09:00 on a Mon-Sat calendar returns
    Tue 2026-09-01 09:00.
    """
    clean_days = max(0, int(day_count or 0))
    calendar = calendar_from_project(project_calendar)

    if calendar is None:
        if clean_days <= 0:
            return finish
        return finish - timedelta(days=clean_days - 1)

    current = calendar.previous_working_datetime(finish)
    if clean_days <= 1:
        return current

    current_day = current.date()
    remaining = clean_days - 1
    for _ in range(_MAX_DAY_STEPS):
        current_day -= timedelta(days=1)
        if calendar.is_working_day(current_day):
            remaining -= 1
            if remaining <= 0:
                return datetime.combine(current_day, current.time())

    raise OverflowError("Working-day reverse placement exceeded schedule calendar bound.")


def add_working_minutes(
    start: datetime,
    minutes: int,
    project_calendar: Optional[Any],
) -> datetime:
    calendar = calendar_from_project(project_calendar)
    delta_minutes = int(minutes or 0)
    if calendar is None:
        return start + timedelta(minutes=delta_minutes)
    if delta_minutes == 0:
        return calendar.next_working_datetime(start)
    if delta_minutes < 0:
        return subtract_working_minutes(start, -delta_minutes, project_calendar)

    current = calendar.next_working_datetime(start)
    remaining = delta_minutes
    for _ in range(_MAX_DAY_STEPS):
        if not calendar.is_working_day(current.date()):
            current = calendar.next_working_datetime(current)
            continue

        end_of_day = datetime.combine(current.date() + timedelta(days=1), time(0, 0))
        available = max(0, int((end_of_day - current).total_seconds() // 60))
        if remaining <= available:
            return current + timedelta(minutes=remaining)

        remaining -= available
        current = end_of_day

    raise OverflowError("Working-minute addition exceeded schedule calendar bound.")


def subtract_working_minutes(
    finish: datetime,
    minutes: int,
    project_calendar: Optional[Any],
) -> datetime:
    calendar = calendar_from_project(project_calendar)
    delta_minutes = int(minutes or 0)
    if calendar is None:
        return finish - timedelta(minutes=delta_minutes)
    if delta_minutes == 0:
        return finish if calendar.is_working_day(finish) else calendar.next_working_datetime(finish)
    if delta_minutes < 0:
        return add_working_minutes(finish, -delta_minutes, project_calendar)

    current = finish
    remaining = delta_minutes
    for _ in range(_MAX_DAY_STEPS):
        if calendar.is_working_day(current.date()) and current.time() != time(0, 0):
            start_of_day = datetime.combine(current.date(), time(0, 0))
            available = max(0, int((current - start_of_day).total_seconds() // 60))
            if remaining <= available:
                return current - timedelta(minutes=remaining)

            remaining -= available
            current = start_of_day
            continue

        search_day = current.date()
        if current.time() == time(0, 0):
            search_day -= timedelta(days=1)
        while not calendar.is_working_day(search_day):
            search_day -= timedelta(days=1)

        day_end = datetime.combine(search_day + timedelta(days=1), time(0, 0))
        if remaining <= MINUTES_PER_DAY:
            return day_end - timedelta(minutes=remaining)

        remaining -= MINUTES_PER_DAY
        current = datetime.combine(search_day, time(0, 0))

    raise OverflowError("Working-minute subtraction exceeded schedule calendar bound.")


def working_minutes_between(
    start: datetime,
    finish: datetime,
    project_calendar: Optional[Any],
) -> int:
    calendar = calendar_from_project(project_calendar)
    if calendar is None:
        return int((finish - start).total_seconds() // 60)
    if finish < start:
        return -working_minutes_between(finish, start, project_calendar)
    if finish == start:
        return 0

    total = 0
    current_day = start.date()
    final_day = finish.date()
    for _ in range((final_day - current_day).days + 1):
        if calendar.is_working_day(current_day):
            interval_start = max(start, datetime.combine(current_day, time(0, 0)))
            interval_finish = min(finish, datetime.combine(current_day + timedelta(days=1), time(0, 0)))
            if interval_finish > interval_start:
                total += int((interval_finish - interval_start).total_seconds() // 60)
        if current_day >= final_day:
            break
        current_day += timedelta(days=1)
    return total
