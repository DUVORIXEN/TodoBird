"""
Central Time-Math Authority for TODO BIRD.
Provides deterministic integer-minute arithmetic, day segmentation,
and coordinate conversion rules across Gantt, Focus, Calendar, and Dialogs.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional, Union, List, Any


DAY_MINUTES: int = 1440


@dataclass(frozen=True)
class DailySegment:
    """
    Represents an execution or scheduling segment within a single calendar day.
    Uses exclusive end-minute boundary [start_minute, end_minute_exclusive).
    """
    date: date
    start_minute: int
    end_minute_exclusive: int
    duration_minutes: int

    def __post_init__(self):
        if not (0 <= self.start_minute <= DAY_MINUTES):
            raise ValueError(f"Invalid start_minute: {self.start_minute}")
        if not (0 <= self.end_minute_exclusive <= DAY_MINUTES):
            raise ValueError(f"Invalid end_minute_exclusive: {self.end_minute_exclusive}")
        if self.end_minute_exclusive < self.start_minute:
            raise ValueError(f"End {self.end_minute_exclusive} < Start {self.start_minute}")
        if self.duration_minutes != (self.end_minute_exclusive - self.start_minute):
            raise ValueError(f"Duration mismatch: {self.duration_minutes} != {self.end_minute_exclusive - self.start_minute}")


def parse_hhmm(value: Union[str, time, int, None]) -> Optional[int]:
    """
    Parse an HH:MM string, time object, or integer minute into integer minutes (0..1439).
    Returns None if value is empty, invalid, or out of range.
    """
    if value is None:
        return None
    if isinstance(value, time):
        return value.hour * 60 + value.minute
    if isinstance(value, int):
        return value if 0 <= value < DAY_MINUTES else None
    
    val_str = str(value).strip()
    if not val_str:
        return None
    
    if ":" in val_str:
        parts = val_str.split(":")
        try:
            h = int(parts[0])
            m = int(parts[1]) if len(parts) > 1 else 0
            if 0 <= h < 24 and 0 <= m < 60:
                return h * 60 + m
        except (ValueError, TypeError):
            return None
    elif val_str.isdigit():
        try:
            h = int(val_str)
            if 0 <= h < 24:
                return h * 60
        except (ValueError, TypeError):
            return None

    return None


def format_hhmm(minutes: Optional[int]) -> str:
    """
    Format integer minutes (0..1439) into an 'HH:MM' string.
    Clamps within 0..1439.
    """
    if minutes is None:
        return "00:00"
    clamped = max(0, min(minutes, DAY_MINUTES - 1))
    h = clamped // 60
    m = clamped % 60
    return f"{h:02d}:{m:02d}"


def format_duration_display(duration_minutes: int) -> str:
    """
    Format integer duration into human-readable representation:
    < 60m: '7 min' or '45 min'
    >= 60m: '1h 24m' or '2h'
    """
    if duration_minutes <= 0:
        return "0 min"
    if duration_minutes < 60:
        return f"{duration_minutes} min"
    h = duration_minutes // 60
    m = duration_minutes % 60
    return f"{h}h {m}m" if m > 0 else f"{h}h"


def minutes_between_same_day(start_minute: int, end_minute: int) -> int:
    """
    Calculate duration between two minute timestamps on the same day.
    """
    return end_minute - start_minute


def parse_date(date_val: Union[date, str, None]) -> Optional[date]:
    """
    Convert a string (YYYY-MM-DD) or date object to a datetime.date.
    """
    if date_val is None:
        return None
    if isinstance(date_val, date):
        return date_val
    val_str = str(date_val).strip()
    if not val_str:
        return None
    try:
        return datetime.strptime(val_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def combine_date_time(date_val: Union[date, str, None], time_val: Union[time, str, int, None]) -> Optional[datetime]:
    """
    Safely combine date and time components into a native naive datetime.
    """
    d = parse_date(date_val)
    if d is None:
        return None
    m = parse_hhmm(time_val)
    if m is None:
        m = 0
    t = time(hour=m // 60, minute=m % 60)
    return datetime.combine(d, t)


def duration_between(
    start_date: Union[date, str, None],
    start_time: Union[time, str, int, None],
    end_date: Union[date, str, None],
    end_time: Union[time, str, int, None],
) -> int:
    """
    Calculate exact integer minutes between two datetime points.
    Returns integer duration in minutes (can be negative if end < start).
    """
    s_dt = combine_date_time(start_date, start_time)
    e_dt = combine_date_time(end_date, end_time)
    if s_dt is None or e_dt is None:
        return 0
    return int((e_dt - s_dt).total_seconds() // 60)


def segment_interval_by_day(
    start_date: Union[date, str],
    start_time: Union[time, str, int, None],
    end_date: Union[date, str, None] = None,
    end_time: Union[time, str, int, None] = None,
) -> List[DailySegment]:
    """
    Mathematically segment a datetime interval into per-calendar-day DailySegments.
    Uses exclusive 1440 (24:00) boundary for day-spanning intervals.
    
    Invariant: SUM(segment.duration_minutes for segment in segments) == total duration
    """
    s_d = parse_date(start_date)
    if s_d is None:
        return []
    
    e_d = parse_date(end_date) or s_d
    s_m = parse_hhmm(start_time) or 0
    e_m = None
    if end_time is not None:
        e_m = parse_hhmm(end_time)
    if e_m is None:
        # missing or unparseable end time — fall back instead of comparing None
        e_m = s_m if s_d == e_d else 0

    if s_d > e_d or (s_d == e_d and e_m < s_m):
        return []

    segments: List[DailySegment] = []

    if s_d == e_d:
        dur = e_m - s_m
        segments.append(DailySegment(
            date=s_d,
            start_minute=s_m,
            end_minute_exclusive=e_m,
            duration_minutes=dur,
        ))
        return segments

    # Multi-day interval:
    # 1. Start Day: [s_m, 1440)
    segments.append(DailySegment(
        date=s_d,
        start_minute=s_m,
        end_minute_exclusive=DAY_MINUTES,
        duration_minutes=DAY_MINUTES - s_m,
    ))

    # 2. Intermediate Days: [0, 1440)
    cur_d = s_d + timedelta(days=1)
    while cur_d < e_d:
        segments.append(DailySegment(
            date=cur_d,
            start_minute=0,
            end_minute_exclusive=DAY_MINUTES,
            duration_minutes=DAY_MINUTES,
        ))
        cur_d += timedelta(days=1)

    # 3. End Day: [0, e_m)
    if e_m > 0:
        segments.append(DailySegment(
            date=e_d,
            start_minute=0,
            end_minute_exclusive=e_m,
            duration_minutes=e_m,
        ))

    return segments


def clamp_minutes(value: int, minimum: int = 0, maximum: int = DAY_MINUTES) -> int:
    """
    Clamp an integer minute value to [minimum, maximum].
    """
    return max(minimum, min(value, maximum))


def minutes_to_x(minutes: int, pixels_per_hour: float) -> float:
    """
    Convert integer business minutes to presentation pixel X coordinate.
    """
    return (minutes / 60.0) * float(pixels_per_hour)


def duration_to_width(duration_minutes: int, pixels_per_hour: float) -> float:
    """
    Convert integer duration in minutes to presentation pixel width.
    """
    return (duration_minutes / 60.0) * float(pixels_per_hour)


def snap_minutes(minutes: int, snap: int = 15) -> int:
    """
    Explicit deterministic midpoint-up integer snap calculation.
    Avoids Python's built-in round() banker's rounding midpoint drift.
    """
    if snap <= 0:
        return minutes
    if minutes >= 0:
        return ((minutes + snap // 2) // snap) * snap
    else:
        return ((minutes - snap // 2) // snap) * snap


def utc_timestamp_to_local_date(value: Any) -> Optional[date]:
    """
    Maps a stored task timestamp to the LOCAL calendar date it represents.

    SQLite CURRENT_TIMESTAMP (the authority behind tasks.updated_at) is UTC.
    Comparing its raw date prefix against local date.today() mis-buckets every
    completion between local midnight and the UTC offset (e.g. 00:00-05:30 IST
    lands on the previous day). Full timestamps are treated as UTC and
    converted; bare date strings (e.g. planned_date fallbacks) are already
    local dates and pass through unchanged.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    from datetime import timezone as _tz

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            parsed = datetime.strptime(text[:19], fmt)
            return parsed.replace(tzinfo=_tz.utc).astimezone().date()
        except ValueError:
            continue
    return parse_date(text)


def calculate_actual_elapsed_minutes(
    start_date: Any,
    start_time: Any,
    end_date: Any,
    end_time: Any,
) -> int:
    """
    Calculates full calendar elapsed time between actual start and actual end in integer minutes.
    ABSOLUTELY NEVER applies working calendar or weekend reduction.
    """
    dur = duration_between(start_date, start_time, end_date, end_time)
    return max(0, int(dur or 0))


_CURRENT_DATETIME_OVERRIDE: Optional[datetime] = None


def get_current_datetime() -> datetime:
    """
    Single canonical authority for current datetime across TODO BIRD.
    Supports deterministic override in test environments.
    """
    global _CURRENT_DATETIME_OVERRIDE
    if _CURRENT_DATETIME_OVERRIDE is not None:
        return _CURRENT_DATETIME_OVERRIDE
    return datetime.now()


def get_current_date() -> date:
    """
    Single canonical authority for current date across TODO BIRD.
    """
    return get_current_datetime().date()


def set_current_datetime_override(dt: Optional[datetime]) -> None:
    """
    Set or clear the deterministic datetime override for testing.
    """
    global _CURRENT_DATETIME_OVERRIDE
    _CURRENT_DATETIME_OVERRIDE = dt


def set_mock_current_datetime(dt: Optional[datetime]) -> None:
    set_current_datetime_override(dt)


def clear_mock_current_datetime() -> None:
    set_current_datetime_override(None)

