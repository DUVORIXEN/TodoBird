import logging
from datetime import datetime, date, timedelta
from typing import Tuple

logger = logging.getLogger(__name__)

class ShutdownGuardManager:
    """
    Systemd User Service & Night Shutdown Guard Manager.
    Intercepts Ubuntu 24.04 shutdowns after configured night time (default 9 PM)
    to present the tomorrow planning workflow.
    """
    def __init__(self, db_manager, settings_manager):
        self.db_manager = db_manager
        self.settings_manager = settings_manager

    def should_intercept_shutdown(self) -> Tuple[bool, str]:
        """
        Determines whether system shutdown should be intercepted.
        Returns (intercept_bool, reason_string).
        """
        if not self.settings_manager.get("shutdown_guard_enabled", True):
            return False, "Shutdown guard disabled in settings"

        # Check current time against configured night threshold
        night_time_str = self.settings_manager.get("night_planning_time", "21:00")
        try:
            night_hour, night_minute = map(int, night_time_str.split(":"))
        except Exception:
            night_hour, night_minute = 21, 0

        now = datetime.now()
        threshold_time = now.replace(hour=night_hour, minute=night_minute, second=0, microsecond=0)

        # 1. Never interrupt daytime shutdown (before threshold time)
        if now < threshold_time:
            return False, f"Daytime shutdown before {night_time_str}"

        # 2. Night hours: Check if tomorrow already has planned tasks
        tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        tomorrow_tasks = self.db_manager.get_all_tasks(planned_date=tomorrow_str)

        if len(tomorrow_tasks) > 0:
            # Tomorrow is already planned — do NOT ask again
            return False, "Tomorrow work is already planned"

        # Tomorrow not planned yet — intercept shutdown for evening planning workflow!
        return True, "Night shutdown intercepted: Tomorrow work not yet planned"
