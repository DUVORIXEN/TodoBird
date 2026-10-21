from enum import Enum
from datetime import datetime, date, time, timezone
from typing import Dict, Any, Tuple, Optional
import logging

from todo_bird_app.models.task import Task, TaskStatus

logger = logging.getLogger(__name__)

class TimingStatus(Enum):
    # Live schedule health
    ON_TRACK = "On Track"
    AT_RISK = "At Risk"
    OVERDUE = "Overdue"

    # Start timing classifications
    EARLY_START = "Early Start"
    DELAYED_START = "Delayed Start"

    # Completion / execution performance
    COMPLETED_BEFORE_TIME = "Completed Before Time"
    COMPLETED_ON_TIME = "Completed On Time"
    SLIGHT_DELAY = "Slight Delay"
    MODERATE_DELAY = "Moderate Delay"
    SEVERE_DELAY = "Severe Delay"
    VERY_SEVERE_DELAY = "Very Severe Delay"

class DelayEngine:
    """
    Plan vs Actual delay analysis engine.
    Calculates delay metrics, completion timing status, and justification requirements.
    """
    def __init__(self, settings_manager):
        self.settings_manager = settings_manager
        self._threshold_warning_emitted = False

    def get_thresholds(self) -> Dict[str, Any]:
        """
        Return normalized delay thresholds.

        Invalid user settings must never create contradictory timing
        classifications or flood the application log.

        Commercial defaults:
            on-time tolerance : 5 minutes
            slight delay      : 15 minutes
            moderate delay    : 30 minutes
            severe delay      : 60 minutes
        """
        defaults = {
            "on_time_tolerance": 5,
            "slight_delay": 15,
            "moderate_delay": 30,
            "severe_delay": 60,
            "very_severe_percentage": 50.0,
        }

        def safe_int(key, default):
            try:
                return max(
                    0,
                    int(
                        self.settings_manager.get(
                            key,
                            default,
                        )
                    ),
                )
            except Exception:
                return default

        def safe_float(key, default):
            try:
                return max(
                    0.0,
                    float(
                        self.settings_manager.get(
                            key,
                            default,
                        )
                    ),
                )
            except Exception:
                return default

        tol = safe_int(
            "on_time_tolerance_minutes",
            defaults["on_time_tolerance"],
        )

        slight = safe_int(
            "slight_delay_minutes",
            defaults["slight_delay"],
        )

        moderate = safe_int(
            "moderate_delay_minutes",
            defaults["moderate_delay"],
        )

        severe = safe_int(
            "severe_delay_minutes",
            defaults["severe_delay"],
        )

        valid_order = (
            tol <= slight <= moderate <= severe
        )

        if not valid_order:
            tol = defaults["on_time_tolerance"]
            slight = defaults["slight_delay"]
            moderate = defaults["moderate_delay"]
            severe = defaults["severe_delay"]

            if not self._threshold_warning_emitted:
                logger.warning(
                    "Invalid delay threshold ordering detected. "
                    "Using safe defaults: 5/15/30/60 minutes."
                )
                self._threshold_warning_emitted = True

        return {
            "on_time_tolerance": tol,
            "slight_delay": slight,
            "moderate_delay": moderate,
            "severe_delay": severe,
            "very_severe_percentage":
                safe_float(
                    "very_severe_delay_percentage",
                    defaults[
                        "very_severe_percentage"
                    ],
                ),
            "require_justification_moderate":
                bool(
                    self.settings_manager.get(
                        "require_justification_moderate",
                        False,
                    )
                ),
            "require_justification_severe":
                bool(
                    self.settings_manager.get(
                        "require_justification_severe",
                        True,
                    )
                ),
        }

    def _planned_deadline(self, task: Task):
        """
        Resolve the real operational deadline.

        Authority order:
          1. due_date + planned_end_time
          2. planned_date + planned_end_time
          3. planned_date + planned_start_time + estimated_duration
          4. due_date end-of-day
          5. planned_date end-of-day

        This makes hour/minute work usable even when Due Date was
        not separately entered.
        """

        def parse_day(value):
            if not value:
                return None

            try:
                return datetime.strptime(
                    str(value),
                    "%Y-%m-%d",
                ).date()
            except Exception:
                return None

        def parse_clock(value):
            if not value:
                return None

            try:
                return datetime.strptime(
                    str(value),
                    "%H:%M",
                ).time()
            except Exception:
                return None

        due_day = parse_day(task.due_date)
        planned_day = parse_day(task.planned_date)

        end_clock = parse_clock(
            task.planned_end_time
        )

        start_clock = parse_clock(
            task.planned_start_time
        )

        # Explicit Due Date + End Time is strongest authority.
        if due_day and end_clock:
            return datetime.combine(
                due_day,
                end_clock,
            )

        # Planned Date + End Time.
        if planned_day and end_clock:
            return datetime.combine(
                planned_day,
                end_clock,
            )

        # Planned start + estimated work duration.
        if (
            planned_day
            and start_clock
            and int(task.estimated_duration or 0) > 0
        ):
            planned_start = datetime.combine(
                planned_day,
                start_clock,
            )

            from datetime import timedelta

            return (
                planned_start
                + timedelta(
                    minutes=int(
                        task.estimated_duration
                    )
                )
            )

        # Date-only work is due by end-of-day.
        if due_day:
            return datetime.combine(
                due_day,
                time(23, 59),
            )

        if planned_day:
            return datetime.combine(
                planned_day,
                time(23, 59),
            )

        return None


    def _completion_datetime(self, task: Task):
        """
        Best available completion timestamp.

        updated_at is useful because completing a task updates the
        task row. Fall back to planned/due date + actual_end_time.

        updated_at is stored by SQLite CURRENT_TIMESTAMP in UTC; it is
        converted to local time before comparison with local deadlines,
        else every delay/early verdict is skewed by the UTC offset
        (e.g. -5:30 for India).
        """
        if task.updated_at:
            value = str(task.updated_at)

            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d %H:%M",
            ):
                try:
                    parsed_utc = datetime.strptime(
                        value[:19],
                        fmt,
                    ).replace(tzinfo=timezone.utc)
                    return parsed_utc.astimezone().replace(tzinfo=None)
                except Exception:
                    pass

        if task.actual_end_time:
            date_text = (
                task.due_date
                or task.planned_date
                or date.today().strftime(
                    "%Y-%m-%d"
                )
            )

            try:
                d = datetime.strptime(
                    date_text,
                    "%Y-%m-%d",
                ).date()

                t = datetime.strptime(
                    task.actual_end_time,
                    "%H:%M",
                ).time()

                return datetime.combine(d, t)
            except Exception:
                pass

        return None

    def analyze_task_timing(self, task: Task) -> Tuple[TimingStatus, int, float]:
        """
        Unified Plan-vs-Actual and live deadline intelligence.

        Unfinished:
          ON_TRACK / AT_RISK / OVERDUE

        Completed:
          COMPLETED_BEFORE_TIME / COMPLETED_ON_TIME /
          delay severity.
        """
        thresholds = self.get_thresholds()

        planned_dur = (
            task.estimated_duration
            if task.estimated_duration > 0
            else 30
        )

        deadline = self._planned_deadline(task)
        now = datetime.now()

        completed = (
            task.status == TaskStatus.COMPLETED
            or int(task.progress or 0) >= 100
        )

        # --------------------------------------------------
        # LIVE / UNFINISHED TASK
        # --------------------------------------------------
        if not completed:
            if deadline is None:
                return (
                    TimingStatus.ON_TRACK,
                    0,
                    0.0,
                )

            remaining_minutes = int(
                (deadline - now).total_seconds()
                // 60
            )

            if remaining_minutes < 0:
                overdue_minutes = abs(
                    remaining_minutes
                )

                overdue_pct = (
                    overdue_minutes
                    / planned_dur
                    * 100.0
                    if planned_dur > 0
                    else 0.0
                )

                return (
                    TimingStatus.OVERDUE,
                    overdue_minutes,
                    overdue_pct,
                )

            # --------------------------------------------------
            # AT-RISK WINDOW
            #
            # Default commercial warning horizon = 60 minutes.
            # For long tasks use 20% of planned effort if larger.
            # This can later become a Settings preference.
            # --------------------------------------------------
            risk_window = max(
                60,
                int(planned_dur * 0.20),
            )

            if remaining_minutes <= risk_window:
                return (
                    TimingStatus.AT_RISK,
                    0,
                    0.0,
                )

            return (
                TimingStatus.ON_TRACK,
                0,
                0.0,
            )

        # --------------------------------------------------
        # COMPLETED TASK
        # --------------------------------------------------
        completed_at = self._completion_datetime(
            task
        )

        if deadline is not None and completed_at is not None:
            delay_mins = int(
                (
                    completed_at - deadline
                ).total_seconds()
                // 60
            )
        else:
            actual_dur = (
                task.actual_duration
                if task.actual_duration > 0
                else planned_dur
            )

            delay_mins = (
                actual_dur - planned_dur
            )

        delay_pct = (
            delay_mins
            / planned_dur
            * 100.0
            if planned_dur > 0
            else 0.0
        )

        if delay_mins < -thresholds[
            "on_time_tolerance"
        ]:
            status = (
                TimingStatus.COMPLETED_BEFORE_TIME
            )

        elif delay_mins <= thresholds[
            "on_time_tolerance"
        ]:
            status = (
                TimingStatus.COMPLETED_ON_TIME
            )

        elif delay_mins <= thresholds[
            "slight_delay"
        ]:
            status = TimingStatus.SLIGHT_DELAY

        elif delay_mins <= thresholds[
            "moderate_delay"
        ]:
            status = TimingStatus.MODERATE_DELAY

        elif (
            delay_mins
            <= thresholds["severe_delay"]
            and delay_pct
            < thresholds[
                "very_severe_percentage"
            ]
        ):
            status = TimingStatus.SEVERE_DELAY

        else:
            status = (
                TimingStatus.VERY_SEVERE_DELAY
            )

        return (
            status,
            delay_mins,
            delay_pct,
        )

    def requires_justification(self, timing_status: TimingStatus) -> bool:
        t = self.get_thresholds()
        if timing_status in (TimingStatus.SEVERE_DELAY, TimingStatus.VERY_SEVERE_DELAY) and t["require_justification_severe"]:
            return True
        if timing_status == TimingStatus.MODERATE_DELAY and t["require_justification_moderate"]:
            return True
        return False

    @staticmethod
    def _parse_date(value) -> Optional[date]:
        if not value:
            return None
        if isinstance(value, date):
            return value
        try:
            return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
        except Exception:
            return None

    @staticmethod
    def _parse_clock(value) -> Optional[time]:
        if not value:
            return None
        if isinstance(value, time):
            return value
        try:
            val_s = str(value).strip()
            if ":" in val_s:
                parts = val_s.split(":")
                return time(int(parts[0]), int(parts[1]))
            elif val_s.isdigit():
                return time(int(val_s), 0)
        except Exception:
            return None
        return None

    def evaluate_start_timing(self, task: Task, now_dt: Optional[datetime] = None) -> Tuple[TimingStatus, int]:
        """
        Evaluate whether task started early or late relative to planned schedule.

        Returns (TimingStatus, delta_minutes):
        - delta_minutes > 0: minutes early (for EARLY_START) or minutes delayed (for DELAYED_START).
        - (TimingStatus.ON_TRACK, delta_minutes): within tolerance.
        """
        if now_dt is None:
            now_dt = datetime.now()

        p_day = self._parse_date(task.planned_date)
        if not p_day:
            return (TimingStatus.ON_TRACK, 0)

        p_time = self._parse_clock(task.planned_start_time) or time(9, 0)
        planned_start_dt = datetime.combine(p_day, p_time)

        # 1. Check if an actual start time/date is recorded
        a_day = getattr(task, "actual_start_date", None)
        a_day = self._parse_date(a_day) if a_day else None
        a_time = self._parse_clock(task.actual_start_time) if task.actual_start_time else None

        if a_time:
            actual_day = a_day or p_day
            actual_start_dt = datetime.combine(actual_day, a_time)
            diff_mins = int((actual_start_dt - planned_start_dt).total_seconds() / 60)

            if diff_mins < -15:
                return (TimingStatus.EARLY_START, abs(diff_mins))
            elif diff_mins > 15:
                return (TimingStatus.DELAYED_START, diff_mins)
            else:
                return (TimingStatus.ON_TRACK, diff_mins)

        # 2. If task has started via progress/status without explicit actual_start_time
        if task.status in (TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED) or int(task.progress or 0) > 0:
            return (TimingStatus.ON_TRACK, 0)

        # 3. Unstarted task: compare current time vs planned start
        if now_dt > planned_start_dt:
            slip_mins = int((now_dt - planned_start_dt).total_seconds() / 60)
            if slip_mins > 15:
                return (TimingStatus.DELAYED_START, slip_mins)

        return (TimingStatus.ON_TRACK, 0)
