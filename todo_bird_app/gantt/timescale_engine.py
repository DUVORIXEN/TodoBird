import calendar
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

class ZoomLevel(Enum):
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    MULTI_YEAR = "multi_year"

@dataclass
class TimelineColumn:
    index: int
    start_date: date
    end_date: date
    primary_header: str      # e.g., "2026"
    secondary_header: str    # e.g., "W31", "Aug", "Jan", "2026"
    sub_label: str           # e.g., "27 Jul–02 Aug", "Q3"
    is_today_period: bool
    x_offset: float
    width: float

def add_months(start_date: date, months: int) -> date:
    """
    Calendar-safe month arithmetic handling leap years and varying month lengths.
    """
    month = start_date.month - 1 + months
    year = start_date.year + month // 12
    month = month % 12 + 1
    day = min(start_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)

class TimescaleEngine:
    """
    Single authority for multi-year Gantt timescale rendering, ISO week calculations,
    calendar-safe month arithmetic, and dynamic project range expansion.
    """
    COLUMN_WIDTHS = {
        ZoomLevel.HOURLY: 60.0,
        ZoomLevel.DAILY: 60.0,
        ZoomLevel.WEEKLY: 100.0,
        ZoomLevel.MONTHLY: 110.0,
        ZoomLevel.YEARLY: 80.0,
        ZoomLevel.MULTI_YEAR: 140.0,
    }

    @staticmethod
    def get_quarter_label(month: int) -> str:
        if month in (1, 2, 3):
            return "Q1"
        elif month in (4, 5, 6):
            return "Q2"
        elif month in (7, 8, 9):
            return "Q3"
        else:
            return "Q4"

    @classmethod
    def get_relevant_date_range(cls, anchor_date: date, tasks: List = None) -> Tuple[date, date]:
        """
        Extracts min start and max finish dates across all task authorities:
        - planned_date / due_date / planned_start / planned_finish
        - CPM earliest_start / earliest_finish
        - baseline_start / baseline_finish
        - constraint_datetime
        - deadline_datetime
        """
        all_dates = [anchor_date]
        if tasks:
            for t in tasks:
                def extract_d(val):
                    if not val:
                        return
                    if isinstance(val, datetime):
                        all_dates.append(val.date())
                    elif isinstance(val, date):
                        all_dates.append(val)
                    elif isinstance(val, str):
                        try:
                            d_str = val.strip()[:10]
                            all_dates.append(datetime.strptime(d_str, "%Y-%m-%d").date())
                        except Exception:
                            pass

                if isinstance(t, dict):
                    extract_d(t.get("planned_date"))
                    extract_d(t.get("due_date"))
                    extract_d(t.get("planned_start"))
                    extract_d(t.get("planned_finish"))
                    extract_d(t.get("cpm_earliest_start"))
                    extract_d(t.get("cpm_earliest_finish"))
                    extract_d(t.get("baseline_start"))
                    extract_d(t.get("baseline_finish"))
                    extract_d(t.get("constraint_datetime"))
                    extract_d(t.get("deadline_datetime"))
                    extract_d(t.get("actual_start_date"))
                    extract_d(t.get("actual_end_date"))
                    extract_d(t.get("actual_start"))
                    extract_d(t.get("actual_finish"))
                    if t.get("actual_start_date") and not t.get("actual_end_date"):
                        from todo_bird_app.utils.time_math import get_current_date
                        all_dates.append(get_current_date())
                else:
                    extract_d(getattr(t, "planned_date", None))
                    extract_d(getattr(t, "due_date", None))
                    extract_d(getattr(t, "planned_start", None))
                    extract_d(getattr(t, "planned_finish", None))
                    extract_d(getattr(t, "cpm_earliest_start", None))
                    extract_d(getattr(t, "cpm_earliest_finish", None))
                    extract_d(getattr(t, "baseline_start", None))
                    extract_d(getattr(t, "baseline_finish", None))
                    extract_d(getattr(t, "constraint_datetime", None))
                    extract_d(getattr(t, "deadline_datetime", None))
                    extract_d(getattr(t, "actual_start_date", None))
                    extract_d(getattr(t, "actual_end_date", None))
                    extract_d(getattr(t, "actual_start", None))
                    extract_d(getattr(t, "actual_finish", None))
                    if getattr(t, "actual_start_date", None) and not getattr(t, "actual_end_date", None):
                        from todo_bird_app.utils.time_math import get_current_date
                        all_dates.append(get_current_date())
                    if hasattr(t, "source_payload") and isinstance(t.source_payload, dict):
                        extract_d(t.source_payload.get("constraint_datetime"))
                        extract_d(t.source_payload.get("deadline_datetime"))
                        extract_d(t.source_payload.get("baseline_start"))
                        extract_d(t.source_payload.get("baseline_finish"))
                        extract_d(t.source_payload.get("actual_start_date"))
                        extract_d(t.source_payload.get("actual_end_date"))

        min_d = min(all_dates)
        max_d = max(all_dates)
        return min_d, max_d

    @classmethod
    def calculate_timescale_range(
        cls,
        anchor_date: date,
        zoom_level: ZoomLevel,
        tasks: List = None,
        projects: List = None,
        past_years: int = 5,
        future_years: int = 5
    ) -> Tuple[date, date]:
        """
        Calculates visible start and end dates. Dynamically expands future/past bounds
        to encompass all task and project dates.
        """
        curr_year = anchor_date.year
        min_start = date(curr_year - past_years, 1, 1)
        max_end = date(curr_year + future_years, 12, 31)

        min_d, max_d = cls.get_relevant_date_range(anchor_date, tasks)
        if min_d < min_start:
            min_start = date(max(1970, min_d.year - 1), 1, 1)
        if max_d > max_end:
            max_end = date(min(2099, max_d.year + 1), 12, 31)

        return min_start, max_end

    @classmethod
    def generate_columns(
        cls,
        zoom_level: ZoomLevel,
        anchor_date: date,
        tasks: List = None,
        projects: List = None
    ) -> List[TimelineColumn]:
        """
        Generates unique, non-repeating timeline columns for the selected zoom level.
        """
        today = date.today()
        col_width = cls.COLUMN_WIDTHS.get(zoom_level, 80.0)
        columns: List[TimelineColumn] = []

        if zoom_level == ZoomLevel.HOURLY:
            # 24 hour columns for anchor_date
            date_str = anchor_date.strftime("%d %b %Y")
            for hr in range(24):
                col = TimelineColumn(
                    index=hr,
                    start_date=anchor_date,
                    end_date=anchor_date,
                    primary_header=date_str if hr == 0 else "",
                    secondary_header=f"{hr:02d}:00",
                    sub_label=f"{hr+1:02d}:00" if hr < 23 else "23:59",
                    is_today_period=(anchor_date == today),
                    x_offset=hr * col_width,
                    width=col_width
                )
                columns.append(col)
        elif zoom_level == ZoomLevel.DAILY:
            min_d, max_d = cls.get_relevant_date_range(anchor_date, tasks)
            start_d = min(anchor_date - timedelta(days=14), min_d - timedelta(days=7))
            end_d = max(anchor_date + timedelta(days=21), max_d + timedelta(days=14))
            days_count = (end_d - start_d).days + 1
            for i in range(days_count):
                c_date = start_d + timedelta(days=i)
                col = TimelineColumn(
                    index=i,
                    start_date=c_date,
                    end_date=c_date,
                    primary_header=c_date.strftime("%B %Y"),
                    secondary_header=c_date.strftime("%d"),
                    sub_label=c_date.strftime("%a"),
                    is_today_period=(c_date == today),
                    x_offset=i * col_width,
                    width=col_width
                )
                columns.append(col)

        elif zoom_level == ZoomLevel.WEEKLY:
            min_d, max_d = cls.get_relevant_date_range(anchor_date, tasks)
            anchor_monday = anchor_date - timedelta(days=anchor_date.weekday())
            range_monday = min_d - timedelta(days=min_d.weekday())
            range_sunday = max_d + timedelta(days=(6 - max_d.weekday()))
            start_monday = min(
                anchor_monday - timedelta(weeks=8),
                range_monday - timedelta(weeks=1),
            )
            end_sunday = max(
                anchor_monday + timedelta(weeks=11, days=6),
                range_sunday + timedelta(weeks=1),
            )
            weeks_count = ((end_sunday - start_monday).days // 7) + 1

            for i in range(weeks_count):
                w_monday = start_monday + timedelta(weeks=i)
                w_sunday = w_monday + timedelta(days=6)
                iso_year, iso_week, _ = w_monday.isocalendar()

                col = TimelineColumn(
                    index=i,
                    start_date=w_monday,
                    end_date=w_sunday,
                    primary_header=str(iso_year),
                    secondary_header=f"W{iso_week:02d}",
                    sub_label=f"{w_monday.strftime('%d %b')}–{w_sunday.strftime('%d %b')}",
                    is_today_period=(w_monday <= today <= w_sunday),
                    x_offset=i * col_width,
                    width=col_width
                )
                columns.append(col)

        elif zoom_level == ZoomLevel.MONTHLY:
            min_d, max_d = cls.get_relevant_date_range(anchor_date, tasks)
            anchor_month = date(anchor_date.year, anchor_date.month, 1)
            range_month = date(min_d.year, min_d.month, 1)
            start_month = min(
                add_months(anchor_month, -6),
                add_months(range_month, -1),
            )
            end_month = max(
                add_months(anchor_month, 11),
                add_months(date(max_d.year, max_d.month, 1), 1),
            )
            months_count = (
                (end_month.year - start_month.year) * 12
                + (end_month.month - start_month.month)
                + 1
            )
            for i in range(months_count):
                m_start = add_months(start_month, i)
                m_end = add_months(m_start, 1) - timedelta(days=1)

                col = TimelineColumn(
                    index=i,
                    start_date=m_start,
                    end_date=m_end,
                    primary_header=str(m_start.year),
                    secondary_header=m_start.strftime("%b"),
                    sub_label=cls.get_quarter_label(m_start.month),
                    is_today_period=(m_start <= today <= m_end),
                    x_offset=i * col_width,
                    width=col_width
                )
                columns.append(col)

        elif zoom_level == ZoomLevel.YEARLY:
            min_d, max_d = cls.get_relevant_date_range(anchor_date, tasks)
            start_year = min(anchor_date.year, min_d.year)
            end_year = max(anchor_date.year, max_d.year)
            month_index = 0

            for year in range(start_year, end_year + 1):
                for month in range(1, 13):
                    m_start = date(year, month, 1)
                    m_end = add_months(m_start, 1) - timedelta(days=1)

                    col = TimelineColumn(
                        index=month_index,
                        start_date=m_start,
                        end_date=m_end,
                        primary_header=str(year),
                        secondary_header=m_start.strftime("%b"),
                        sub_label=cls.get_quarter_label(month),
                        is_today_period=(m_start <= today <= m_end),
                        x_offset=month_index * col_width,
                        width=col_width
                    )
                    columns.append(col)
                    month_index += 1

        elif zoom_level == ZoomLevel.MULTI_YEAR:
            # Multi-Year columns (current_year - 5 to current_year + 5, or expanded)
            min_start, max_end = cls.calculate_timescale_range(anchor_date, zoom_level, tasks, projects)
            start_yr = min_start.year
            end_yr = max_end.year
            years_count = end_yr - start_yr + 1

            for i in range(years_count):
                yr = start_yr + i
                y_start = date(yr, 1, 1)
                y_end = date(yr, 12, 31)

                col = TimelineColumn(
                    index=i,
                    start_date=y_start,
                    end_date=y_end,
                    primary_header="Multi-Year Plan",
                    secondary_header=str(yr),
                    sub_label="12 Months",
                    is_today_period=(yr == today.year),
                    x_offset=i * col_width,
                    width=col_width
                )
                columns.append(col)

        return columns

    @classmethod
    def date_to_x(cls, target_date: date, columns: List[TimelineColumn]) -> float:
        """
        Maps a date to exact pixel X coordinate within visible columns.
        """
        if not columns:
            return 0.0

        if target_date <= columns[0].start_date:
            return columns[0].x_offset

        if target_date >= columns[-1].end_date:
            return columns[-1].x_offset + columns[-1].width

        for col in columns:
            if col.start_date <= target_date <= col.end_date:
                total_days = (col.end_date - col.start_date).days + 1
                offset_days = (target_date - col.start_date).days
                fraction = offset_days / float(max(1, total_days))
                return col.x_offset + (fraction * col.width)

        return columns[0].x_offset

    @classmethod
    def time_to_x(cls, hour: int, minute: int, col_width: float = 60.0) -> float:
        """
        Maps an hour (0..23) and minute (0..59) to exact pixel X coordinate on the 24-hour timeline.
        """
        return (float(hour) + (float(minute) / 60.0)) * float(col_width)

    @staticmethod
    def intersects_visible_range(task_start: date, task_end: date, visible_start: date, visible_end: date) -> bool:
        """
        Returns True if task date interval intersects the visible timeline range.
        """
        return task_start <= visible_end and task_end >= visible_start
