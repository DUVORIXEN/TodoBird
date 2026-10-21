"""
TODO BIRD — Companion & 30-Day Greeting Service (Batch 3.5)
Manages:
- Companion personalization (Default Bird, Custom Image, Disabled)
- Activity levels (Off, Minimal, Balanced, Expressive)
- 30-Day Greeting Planner repository & schedule resolution
- Contextual motivational and milestone reflections
- Session-aware greeting trigger management
"""
import os
import logging
from datetime import date, datetime
from typing import Dict, Any, List, Optional
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QIcon

from todo_bird_app.services.media_service import MediaService
from todo_bird_app.settings.settings_manager import SettingsManager

logger = logging.getLogger(__name__)


class CompanionService:
    """Manages the Todo Bird personal companion and 30-day greeting schedule."""

    _session_greeting_shown: bool = False

    def __init__(self, db_manager: Any = None, settings_manager: Optional[SettingsManager] = None):
        self.db_manager = db_manager
        self.settings = settings_manager or SettingsManager()

    # -------------------------------------------------------------------------
    # Companion Avatar & State
    # -------------------------------------------------------------------------
    @property
    def avatar_mode(self) -> str:
        """'default', 'custom', or 'disabled'"""
        return str(self.settings.get("companion_avatar_mode", "default")).lower()

    @property
    def custom_avatar_path(self) -> str:
        return str(self.settings.get("companion_custom_avatar_path", ""))

    @property
    def activity_level(self) -> str:
        """'off', 'minimal', 'balanced', or 'expressive'"""
        return str(self.settings.get("companion_activity_level", "balanced")).lower()

    @property
    def greeting_frequency(self) -> str:
        """'once_per_day', 'once_per_session', or 'never'"""
        return str(self.settings.get("companion_greeting_frequency", "once_per_day")).lower()

    @property
    def greeting_schedule_mode(self) -> str:
        """'same_every_day', 'day_by_day', or 'date_specific'"""
        return str(self.settings.get("companion_greeting_schedule_mode", "day_by_day")).lower()

    def set_avatar_mode(self, mode: str, custom_path: Optional[str] = None):
        self.settings.set("companion_avatar_mode", mode)
        if custom_path is not None:
            self.settings.set("companion_custom_avatar_path", custom_path)

    def set_activity_level(self, level: str):
        self.settings.set("companion_activity_level", level)

    def set_greeting_preferences(self, frequency: str, schedule_mode: str):
        self.settings.set("companion_greeting_frequency", frequency)
        self.settings.set("companion_greeting_schedule_mode", schedule_mode)

    def get_companion_pixmap(self, max_size: int = 64) -> Optional[QPixmap]:
        """Returns the current companion pixmap according to avatar mode."""
        if self.avatar_mode == "disabled":
            return None

        if self.avatar_mode == "custom" and self.custom_avatar_path:
            pixmap = MediaService.load_pixmap(self.custom_avatar_path, max_width=max_size, max_height=max_size)
            if pixmap and not pixmap.isNull():
                return pixmap

        # Default bird fallback
        built_in_candidates = [
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons", "bird.png"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons", "app_icon.png"),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "icons", "bird.svg"),
        ]
        for cand in built_in_candidates:
            if os.path.exists(cand):
                pm = QPixmap(cand)
                if not pm.isNull():
                    return pm.scaled(max_size, max_size)

        # Fallback in-memory pixmap
        pm = QPixmap(max_size, max_size)
        pm.fill(Qt.transparent)
        return pm

    # -------------------------------------------------------------------------
    # 30-Day Greeting Planner & Lookup
    # -------------------------------------------------------------------------
    def get_all_greetings(self) -> List[Dict[str, Any]]:
        """Returns all 30 greeting configurations from database."""
        if not self.db_manager:
            return self._get_fallback_greetings()
        try:
            items = self.db_manager.get_all_greetings()
            return items if items else self._get_fallback_greetings()
        except Exception as e:
            logger.warning("Error fetching greetings from DB: %s", e)
            return self._get_fallback_greetings()

    def get_greeting_for_date(self, target_date: Optional[date] = None) -> Dict[str, Any]:
        """Determines the appropriate greeting according to configured schedule mode."""
        d = target_date or date.today()
        mode = self.greeting_schedule_mode

        if mode == "same_every_day":
            # Return Day 1
            if self.db_manager:
                g = self.db_manager.get_greeting_by_day(1)
                if g:
                    return g
            return self._get_fallback_greetings()[0]

        elif mode == "date_specific":
            # Look up by exact date YYYY-MM-DD
            d_str = d.strftime("%Y-%m-%d")
            if self.db_manager:
                g = self.db_manager.get_greeting_by_date(d_str)
                if g and g.get("enabled", 1):
                    return g
            # Fall back to cycle day if specific date not configured
            cycle_day = min(30, max(1, d.day))
            if self.db_manager:
                g = self.db_manager.get_greeting_by_day(cycle_day)
                if g:
                    return g
            return self._get_fallback_greetings()[cycle_day - 1]

        else:  # 'day_by_day' 30-day planner
            cycle_day = min(30, max(1, d.day))
            if self.db_manager:
                g = self.db_manager.get_greeting_by_day(cycle_day)
                if g:
                    return g
            return self._get_fallback_greetings()[cycle_day - 1]

    def update_greeting(
        self,
        cycle_day: Optional[int] = None,
        schedule_date: Optional[str] = None,
        title: str = "",
        message: str = "",
        image_path: str = "",
        enabled: bool = True,
    ) -> int:
        if not self.db_manager:
            return 0
        return self.db_manager.upsert_greeting(
            cycle_day=cycle_day,
            schedule_date=schedule_date,
            title=title,
            message=message,
            image_path=image_path,
            enabled=enabled,
        )

    def apply_greeting_to_days(self, source_day: int, target_days: List[int]) -> bool:
        """Applies title, message, and image from source_day to target_days."""
        if not self.db_manager:
            return False
        src = self.db_manager.get_greeting_by_day(source_day)
        if not src:
            return False
        for t_day in target_days:
            if 1 <= t_day <= 30 and t_day != source_day:
                self.db_manager.upsert_greeting(
                    cycle_day=t_day,
                    title=src.get("title", ""),
                    message=src.get("message", ""),
                    image_path=src.get("image_path", ""),
                    enabled=bool(src.get("enabled", 1)),
                )
        return True

    def duplicate_greeting_to_all(self, source_day: int) -> bool:
        """Copies source_day greeting across all 30 days."""
        return self.apply_greeting_to_days(source_day, list(range(1, 31)))

    @classmethod
    def get_effective_greeting(cls, db_manager: Any, settings_manager: Optional[SettingsManager] = None, current_date_str: Optional[str] = None) -> Dict[str, Any]:
        svc = cls(db_manager, settings_manager)
        target_d = None
        if current_date_str:
            try:
                target_d = datetime.strptime(current_date_str, "%Y-%m-%d").date()
            except Exception:
                target_d = date.today()
        return svc.get_greeting_for_date(target_d)

    @classmethod
    def get_companion_avatar_pixmap(cls, settings_manager: Optional[SettingsManager] = None, max_dim: int = 64) -> Optional[QPixmap]:
        svc = cls(None, settings_manager)
        return svc.get_companion_pixmap(max_dim)

    # -------------------------------------------------------------------------
    # Display Trigger Decision
    # -------------------------------------------------------------------------
    @classmethod
    def should_show_greeting(cls, settings_or_self: Any = None) -> bool:
        """Evaluates whether startup/first-open greeting banner should display."""
        if isinstance(settings_or_self, CompanionService):
            svc = settings_or_self
        elif isinstance(settings_or_self, SettingsManager):
            svc = cls(None, settings_or_self)
        else:
            svc = cls(None, None)

        if not svc.settings.get("companion_enabled", True):
            return False

        if svc.avatar_mode == "disabled" or svc.activity_level == "off":
            return False

        freq = svc.greeting_frequency
        if freq == "never":
            return False

        if freq == "once_per_session":
            if cls._session_greeting_shown:
                return False
            return True

        if freq == "once_per_day":
            last_shown_date = svc.settings.get("companion_last_greeting_date", "")
            today_str = date.today().strftime("%Y-%m-%d")
            if last_shown_date == today_str:
                return False
            return True

        return True

    @classmethod
    def mark_greeting_shown(cls, settings_or_self: Any = None):
        """Records that greeting was displayed."""
        cls._session_greeting_shown = True
        if isinstance(settings_or_self, CompanionService):
            settings_or_self.settings.set("companion_last_greeting_date", date.today().strftime("%Y-%m-%d"))
        elif isinstance(settings_or_self, SettingsManager):
            settings_or_self.set("companion_last_greeting_date", date.today().strftime("%Y-%m-%d"))

    # -------------------------------------------------------------------------
    # Contextual Activity Messages
    # -------------------------------------------------------------------------
    def get_contextual_message(self, event_type: str, **kwargs) -> Optional[str]:
        """Returns subtle, motivating companion reactions."""
        if self.activity_level in ("off", "minimal") and event_type not in ("focus_completed", "milestone"):
            return None

        if event_type == "task_completed":
            task_title = kwargs.get("task_title", "Task")
            return f"Well done on '{task_title}'! Another milestone checked off."

        elif event_type == "milestone":
            return "Project milestone achieved! Outstanding dedication and focus."

        elif event_type == "focus_started":
            return "Focus session active. Distractions muted — let's make it count."

        elif event_type == "focus_completed":
            duration_mins = kwargs.get("duration_minutes", 25)
            return f"Outstanding — {duration_mins} minutes of deep, uninterrupted work completed."

        elif event_type == "task_overdue":
            return "Notice: this task is past its due plan. Let's adjust dedication or conquer it."

        return None

    def _get_fallback_greetings(self) -> List[Dict[str, Any]]:
        """Provides in-memory 30-day defaults if database is not attached."""
        return [
            {"id": i, "cycle_day": i, "title": f"Day {i} Focus", "message": "Execute with clarity and purpose.", "image_path": "", "enabled": 1}
            for i in range(1, 31)
        ]
