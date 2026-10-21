"""
Reminder Policy Service (Batch 3.10D / Phase 2C.2)
Central authority for reminder trigger modes, snooze tracking, duplicate suppression,
startup catch-up policy evaluation, daily first-open tracking, and acknowledgment persistence.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Set, Dict, Any

from todo_bird_app.models.task import (
    Task,
    TaskStatus,
    STARTUP_REMINDER_OFF,
    STARTUP_REMINDER_DAILY_FIRST,
    STARTUP_REMINDER_EVERY_APP,
)

logger = logging.getLogger(__name__)


class ReminderPolicyService:
    # Trigger Mode Constants
    MODE_COMPUTER_STARTUP = "computer_startup"
    MODE_APP_STARTUP = "app_startup"
    MODE_SCHEDULED_ONLY = "scheduled_only"
    MODE_DISABLED = "disabled"

    TRIGGER_MODES = [
        (MODE_SCHEDULED_ONLY, "Scheduled Time Only (Default — Never popup just on launch)"),
        (MODE_APP_STARTUP, "Todo Bird Startup + Due Reminders (Show due on every app open)"),
        (MODE_COMPUTER_STARTUP, "Computer Startup + Due Reminders (Show due on session login)"),
        (MODE_DISABLED, "Disabled / Manual (No automatic popups)"),
    ]

    # Task-level Startup Reminder Modes
    STARTUP_MODE_OFF = STARTUP_REMINDER_OFF
    STARTUP_MODE_DAILY_FIRST = STARTUP_REMINDER_DAILY_FIRST
    STARTUP_MODE_EVERY_APP = STARTUP_REMINDER_EVERY_APP

    # Session startup reference timestamp
    _session_start_time: datetime = datetime.now()

    # Runtime session state authorities
    _shown_in_session: Set[int] = set()
    _dismissed_in_session: Set[int] = set()
    _hidden_for_session: Set[int] = set()
    _snoozed_until: Dict[int, datetime] = {}
    _acknowledged_occurrences: Dict[int, str] = {}
    _daily_shown_dates: Dict[int, str] = {}
    _is_first_launch_today: Optional[bool] = None
    _startup_evaluated_in_session: bool = False

    @classmethod
    def get_occurrence_key(cls, task: Task) -> str:
        """Returns stable occurrence identity key for a task reminder."""
        p_date = str(getattr(task, "planned_date", "") or "").strip()[:10]
        p_time = str(getattr(task, "planned_start_time", "") or "").strip()[:5]
        if p_date or p_time:
            return f"{p_date}_{p_time}"
        return f"task_{task.id}"

    @classmethod
    def get_trigger_mode(cls, settings_manager: Optional[Any] = None) -> str:
        """Returns the configured reminder trigger mode, defaulting to scheduled_only."""
        if settings_manager is not None:
            mode = str(settings_manager.get("reminder_trigger_mode", cls.MODE_SCHEDULED_ONLY) or cls.MODE_SCHEDULED_ONLY).lower().strip()
            valid_modes = {cls.MODE_COMPUTER_STARTUP, cls.MODE_APP_STARTUP, cls.MODE_SCHEDULED_ONLY, cls.MODE_DISABLED}
            if mode in valid_modes:
                return mode
        return cls.MODE_SCHEDULED_ONLY

    @classmethod
    def ensure_startup_trigger_enabled_for_launch_reminder(
        cls,
        settings_manager: Optional[Any],
        startup_reminder_mode: Optional[str],
    ) -> bool:
        """
        Keeps task-level launch reminders from being hidden by the global trigger mode.

        Scheduled-only and disabled modes are still valid global choices, but once the
        user explicitly enables a task launch reminder, startup evaluation must be on.
        """
        if settings_manager is None:
            return False

        launch_mode = str(startup_reminder_mode or cls.STARTUP_MODE_OFF).strip()
        if launch_mode not in {cls.STARTUP_MODE_DAILY_FIRST, cls.STARTUP_MODE_EVERY_APP}:
            return False

        trigger_mode = cls.get_trigger_mode(settings_manager)
        if trigger_mode not in {cls.MODE_DISABLED, cls.MODE_SCHEDULED_ONLY}:
            return False

        settings_manager.set("reminder_trigger_mode", cls.MODE_APP_STARTUP)
        logger.info(
            "Reminder startup policy auto-enabled because task launch reminder mode is %s",
            launch_mode,
        )
        return True

    @classmethod
    def should_show_on_startup(cls, settings_manager: Optional[Any] = None, is_session_startup: bool = False) -> bool:
        """
        Determines whether reminders should be evaluated and presented at app launch.
        - app_startup mode: always True
        - computer_startup mode: True when launched via desktop session autostart,
          and also on a manual launch that is the first launch of the local calendar
          day (a user opening the app first thing in the morning IS their session
          start — due launch reminders must not be silently skipped then)
        - scheduled_only / disabled: always False
        """
        mode = cls.get_trigger_mode(settings_manager)
        if mode == cls.MODE_APP_STARTUP:
            return True
        if mode == cls.MODE_COMPUTER_STARTUP:
            if is_session_startup:
                return True
            return cls.check_and_update_first_launch_today(settings_manager)
        return False

    @classmethod
    def check_and_update_first_launch_today(cls, settings_manager: Optional[Any] = None) -> bool:
        """
        Determines if this session is the first launch of the local calendar day,
        and records the date.
        """
        if cls._is_first_launch_today is not None:
            return cls._is_first_launch_today

        today_str = datetime.now().strftime("%Y-%m-%d")
        if settings_manager is not None:
            last_launch = str(settings_manager.get("last_app_launch_date", "") or "").strip()
            is_first = (last_launch != today_str)
            settings_manager.set("last_app_launch_date", today_str)
            cls._is_first_launch_today = is_first
            return is_first

        cls._is_first_launch_today = True
        return True

    @classmethod
    def _sync_persisted_snoozes(cls, settings_manager: Optional[Any] = None):
        """Loads and syncs persisted snooze entries from settings_manager without overriding active RAM."""
        if settings_manager is None:
            return
        import json
        raw = settings_manager.get("persisted_snoozed_reminders", "")
        data = {}
        if isinstance(raw, str) and raw.strip():
            try:
                data = json.loads(raw)
            except Exception:
                data = {}
        elif isinstance(raw, dict):
            data = raw

        if isinstance(data, dict):
            for tid_str, dt_str in data.items():
                try:
                    tid = int(tid_str)
                    if tid not in cls._snoozed_until:
                        cls._snoozed_until[tid] = datetime.fromisoformat(str(dt_str))
                except Exception:
                    pass

    @classmethod
    def _save_persisted_snoozes(cls, settings_manager: Optional[Any] = None):
        """Saves active snooze entries to settings_manager."""
        if settings_manager is None:
            return
        import json
        try:
            data = {str(tid): dt.isoformat() for tid, dt in cls._snoozed_until.items()}
            settings_manager.set("persisted_snoozed_reminders", json.dumps(data))
        except Exception as e:
            logger.debug("Error saving persisted snoozes: %s", e)

    @classmethod
    def _sync_persisted_acknowledgments(cls, settings_manager: Optional[Any] = None):
        """Loads and syncs persisted acknowledged occurrences from settings_manager."""
        if settings_manager is None:
            return
        import json
        raw = settings_manager.get("persisted_acknowledged_reminders", "")
        data = {}
        if isinstance(raw, str) and raw.strip():
            try:
                data = json.loads(raw)
            except Exception:
                data = {}
        elif isinstance(raw, dict):
            data = raw

        if isinstance(data, dict):
            for tid_str, occ_key in data.items():
                try:
                    tid = int(tid_str)
                    if tid not in cls._acknowledged_occurrences:
                        cls._acknowledged_occurrences[tid] = str(occ_key)
                except Exception:
                    pass

    @classmethod
    def _save_persisted_acknowledgments(cls, settings_manager: Optional[Any] = None):
        """Saves active acknowledged occurrences to settings_manager."""
        if settings_manager is None:
            return
        import json
        try:
            data = {str(tid): str(occ_key) for tid, occ_key in cls._acknowledged_occurrences.items()}
            settings_manager.set("persisted_acknowledged_reminders", json.dumps(data))
        except Exception as e:
            logger.debug("Error saving persisted acknowledgments: %s", e)

    @classmethod
    def _sync_persisted_daily_startup(cls, settings_manager: Optional[Any] = None):
        """Loads and syncs persisted daily startup occurrences from settings_manager."""
        if settings_manager is None:
            return
        import json
        raw = settings_manager.get("persisted_daily_startup_reminders", "")
        data = {}
        if isinstance(raw, str) and raw.strip():
            try:
                data = json.loads(raw)
            except Exception:
                data = {}
        elif isinstance(raw, dict):
            data = raw

        if isinstance(data, dict):
            for tid_str, date_str in data.items():
                try:
                    tid = int(tid_str)
                    if tid not in cls._daily_shown_dates:
                        cls._daily_shown_dates[tid] = str(date_str)
                except Exception:
                    pass

    @classmethod
    def _save_persisted_daily_startup(cls, settings_manager: Optional[Any] = None):
        """Saves active daily startup dates to settings_manager."""
        if settings_manager is None:
            return
        import json
        try:
            data = {str(tid): str(d) for tid, d in cls._daily_shown_dates.items()}
            settings_manager.set("persisted_daily_startup_reminders", json.dumps(data))
        except Exception as e:
            logger.debug("Error saving daily startup dates: %s", e)

    @classmethod
    def get_startup_due_reminders(
        cls,
        task_controller: Any,
        settings_manager: Optional[Any] = None,
        current_dt: Optional[datetime] = None
    ) -> List[Task]:
        """
        Evaluates task-level startup reminder modes on fresh application start.
        Supports:
        - off: no startup reminder
        - daily_first_open: triggers on first launch of the local calendar day
        - every_app_open: triggers once per fresh application start
        """
        cls._sync_persisted_snoozes(settings_manager)
        cls._sync_persisted_acknowledgments(settings_manager)
        cls._sync_persisted_daily_startup(settings_manager)

        now = current_dt or datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        is_first_launch = cls.check_and_update_first_launch_today(settings_manager)

        all_tasks = task_controller.get_all_tasks()
        due_tasks = []

        for task in all_tasks:
            # Suppress terminal statuses
            if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
                continue

            task_id = task.id
            if task_id is None:
                continue

            if task_id in cls._dismissed_in_session or task_id in cls._hidden_for_session:
                continue

            if task_id in cls._shown_in_session:
                continue

            # Active snooze check
            if task_id in cls._snoozed_until:
                snooze_exp = cls._snoozed_until[task_id]
                if now < snooze_exp:
                    continue

            # Determine task startup mode
            mode = getattr(task, "startup_reminder_mode", None)
            if not mode:
                mode = cls.STARTUP_MODE_DAILY_FIRST if bool(getattr(task, "startup_reminder", False)) else cls.STARTUP_MODE_OFF

            if mode == cls.STARTUP_MODE_OFF:
                continue
            elif mode == cls.STARTUP_MODE_DAILY_FIRST:
                # Global authority: MUST be the first application launch of this local calendar day
                if not is_first_launch:
                    continue
                # Check if this task already triggered on this local calendar day
                if cls._daily_shown_dates.get(task_id) == today_str:
                    continue
                due_tasks.append(task)
            elif mode == cls.STARTUP_MODE_EVERY_APP:
                due_tasks.append(task)

        return due_tasks

    @classmethod
    def get_due_reminders(
        cls,
        task_controller: Any,
        settings_manager: Optional[Any] = None,
        current_dt: Optional[datetime] = None,
        ignore_duplicate_guard: bool = False
    ) -> List[Task]:
        """
        Returns active tasks whose scheduled reminders or snoozes become due during active runtime polling.
        """
        cls._sync_persisted_snoozes(settings_manager)
        cls._sync_persisted_acknowledgments(settings_manager)

        now = current_dt or datetime.now()
        all_tasks = task_controller.get_all_tasks()
        due_tasks = []
        snooze_changed = False

        for task in all_tasks:
            # Skip completed or cancelled tasks
            if task.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
                continue

            task_id = task.id
            if task_id is None:
                continue

            # Snooze check: highest priority. A live snooze expiration
            # must not be suppressed by stale shown/dismissed/ack state.
            if task_id in cls._snoozed_until:
                snooze_exp = cls._snoozed_until[task_id]
                if now < snooze_exp:
                    continue
                else:
                    # Snooze duration has elapsed -> trigger now and clear snooze
                    del cls._snoozed_until[task_id]
                    cls._shown_in_session.discard(task_id)
                    cls._dismissed_in_session.discard(task_id)
                    cls._hidden_for_session.discard(task_id)
                    cls._acknowledged_occurrences.pop(task_id, None)
                    snooze_changed = True
                    due_tasks.append(task)
                    continue

            # Dismissed or hidden in session check
            if task_id in cls._dismissed_in_session or task_id in cls._hidden_for_session:
                continue

            # Duplicate suppression check for active session
            if not ignore_duplicate_guard and task_id in cls._shown_in_session:
                continue

            occ_key = cls.get_occurrence_key(task)

            # Check if this exact occurrence was already acknowledged in persistent storage
            if cls._acknowledged_occurrences.get(task_id) == occ_key:
                continue

            # Determine scheduled datetime
            p_date = getattr(task, "planned_date", None)
            p_time = getattr(task, "planned_start_time", None)

            sched_dt = None
            if p_date:
                try:
                    p_date_str = str(p_date)[:10]
                    if p_time and str(p_time).strip():
                        t_str = str(p_time).strip()[:5]
                        sched_dt = datetime.strptime(f"{p_date_str} {t_str}", "%Y-%m-%d %H:%M")
                    else:
                        sched_dt = datetime.strptime(f"{p_date_str} 00:00", "%Y-%m-%d %H:%M")
                except Exception:
                    sched_dt = None

            if sched_dt is None:
                continue

            # If scheduled in future relative to now -> NOT due yet
            if sched_dt > now:
                continue

            # Scheduled datetime has arrived
            # Trigger if reached scheduled time during active running session
            if sched_dt >= cls._session_start_time:
                due_tasks.append(task)

        if snooze_changed:
            cls._save_persisted_snoozes(settings_manager)

        return due_tasks

    @classmethod
    def mark_shown(cls, task_id: int):
        """Marks a reminder as shown in the current session to suppress duplicates."""
        cls._shown_in_session.add(task_id)

    @classmethod
    def snooze_reminder(cls, task_id: int, minutes: int, from_dt: Optional[datetime] = None, settings_manager: Optional[Any] = None):
        """Snoozes a reminder for a given number of minutes and persists across restarts."""
        now = from_dt or datetime.now()
        cls._snoozed_until[task_id] = now + timedelta(minutes=minutes)
        cls._shown_in_session.discard(task_id)
        cls._dismissed_in_session.discard(task_id)
        cls._acknowledged_occurrences.pop(task_id, None)
        cls._save_persisted_snoozes(settings_manager)
        cls._save_persisted_acknowledgments(settings_manager)

    @classmethod
    def dismiss_reminder(cls, task_id: int, occurrence_key: Optional[str] = None, settings_manager: Optional[Any] = None):
        """Dismisses a reminder for the duration of this session and persists acknowledgment."""
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        cls._dismissed_in_session.add(task_id)
        cls._shown_in_session.add(task_id)
        cls._snoozed_until.pop(task_id, None)
        cls._daily_shown_dates[task_id] = today_str
        cls._acknowledged_occurrences[task_id] = occurrence_key or f"ack_{today_str}"
        cls._save_persisted_snoozes(settings_manager)
        cls._save_persisted_acknowledgments(settings_manager)
        cls._save_persisted_daily_startup(settings_manager)

    @classmethod
    def complete_reminder(cls, task: Task, task_controller: Any, settings_manager: Optional[Any] = None):
        """Marks a task as completed directly from the reminder dialog."""
        task.status = TaskStatus.COMPLETED
        task.progress = 100
        now = datetime.now()
        if not task.actual_end_date:
            task.actual_end_date = now.strftime("%Y-%m-%d")
        if not task.actual_end_time:
            task.actual_end_time = now.strftime("%H:%M")
        # Completing before a recorded (possibly future) actual start would
        # violate the execution-state invariant and crash the dialog's
        # Complete button — clamp the finish moment to the start moment.
        try:
            start_dt = end_dt = None
            if task.actual_start_date:
                start_dt = datetime.strptime(
                    f"{task.actual_start_date} {(task.actual_start_time or '00:00')[:5]}",
                    "%Y-%m-%d %H:%M",
                )
                end_dt = datetime.strptime(
                    f"{task.actual_end_date} {(task.actual_end_time or '00:00')[:5]}",
                    "%Y-%m-%d %H:%M",
                )
            if start_dt and end_dt and end_dt < start_dt:
                task.actual_end_date = task.actual_start_date
                task.actual_end_time = task.actual_start_time
        except (ValueError, TypeError):
            pass
        task_controller.update_task(task)
        if task.id is not None:
            occ_key = cls.get_occurrence_key(task)
            cls.dismiss_reminder(task.id, occurrence_key=occ_key, settings_manager=settings_manager)

    @classmethod
    def hide_for_session(cls, task_id: int):
        """Temporarily hides/closes a reminder for the current session without persisting acknowledgment."""
        cls._hidden_for_session.add(task_id)
        cls._shown_in_session.add(task_id)

    @classmethod
    def reset_session_state(cls, settings_manager: Optional[Any] = None):
        """Resets all runtime session state (useful for tests and restarts)."""
        cls._session_start_time = datetime.now()
        cls._shown_in_session.clear()
        cls._dismissed_in_session.clear()
        cls._hidden_for_session.clear()
        cls._snoozed_until.clear()
        cls._acknowledged_occurrences.clear()
        cls._daily_shown_dates.clear()
        cls._is_first_launch_today = None
        cls._startup_evaluated_in_session = False
        if settings_manager is not None:
            settings_manager.set("persisted_snoozed_reminders", "")
            settings_manager.set("persisted_acknowledged_reminders", "")
            settings_manager.set("persisted_daily_startup_reminders", "")
            settings_manager.set("last_app_launch_date", "")

    @classmethod
    def evaluate_startup_reminders(
        cls,
        main_window: Any,
        task_controller: Any,
        settings_manager: Optional[Any] = None,
        is_session_startup: bool = False
    ) -> List[Any]:
        """
        Evaluates startup policy and opens modern ReminderDialogs once per application session.
        """
        if cls._startup_evaluated_in_session:
            return []
        cls._startup_evaluated_in_session = True

        if not cls.should_show_on_startup(settings_manager, is_session_startup=is_session_startup):
            logger.info("Startup reminder skipped: policy is %s", cls.get_trigger_mode(settings_manager))
            return []

        cls.check_and_update_first_launch_today(settings_manager)
        due_tasks = cls.get_startup_due_reminders(task_controller, settings_manager)
        dialogs = []

        from todo_bird_app.services.reminder_presentation_service import ReminderPresentationService

        dialogs = ReminderPresentationService._present_desktop_reminders(due_tasks, main_window, task_controller, settings_manager)

        today_str = datetime.now().strftime("%Y-%m-%d")
        for task in due_tasks:
            if task.id is not None:
                mode = getattr(task, "startup_reminder_mode", None)
                if not mode:
                    mode = cls.STARTUP_MODE_DAILY_FIRST if bool(getattr(task, "startup_reminder", False)) else cls.STARTUP_MODE_OFF
                if mode == cls.STARTUP_MODE_DAILY_FIRST:
                    cls._daily_shown_dates[task.id] = today_str

        cls._save_persisted_daily_startup(settings_manager)
        return dialogs

    @classmethod
    def check_and_trigger_due_reminders(
        cls,
        main_window: Any,
        task_controller: Any,
        settings_manager: Optional[Any] = None
    ) -> List[Any]:
        """
        Periodically checks and triggers reminders when their scheduled time or snooze duration arrives.
        """
        mode = cls.get_trigger_mode(settings_manager)
        if mode == cls.MODE_DISABLED:
            return []

        due_tasks = cls.get_due_reminders(task_controller, settings_manager)
        from todo_bird_app.services.reminder_presentation_service import ReminderPresentationService
        dialogs = ReminderPresentationService._present_desktop_reminders(due_tasks, main_window, task_controller, settings_manager)

        return dialogs
