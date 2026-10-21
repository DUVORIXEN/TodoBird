import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = {
    "theme": "dark",                   # dark, light, system
    "accent_scheme": "ubuntu_orange",  # named accent scheme
    "accent_color": "#E95420",         # resolved accent color
    "color_scheme": "neutral",         # structural surface scheme
    "ui_font_family": "Inter",
    "ui_font_size": 10,
    "ui_font_weight": "normal",
    "ui_density": "balanced",          # compact, balanced, spacious
    "button_design_mode": "3d_raised",
    "global_background_mode": "theme_default",
    "global_background_color": "#161821",
    "global_background_image": "",
    "global_background_opacity": 1.0,
    "global_background_fit": "fill",
    "global_background_overlay_mode": "auto",
    "view_background_overrides": {},
    # Legacy Batch 3.5 image keys. Keep as compatibility aliases so existing
    # image backgrounds and reminder-global backgrounds continue to work.
    "background_mode": "none",
    "background_custom_image_path": "",
    "background_fit_mode": "fill",
    "background_opacity": 0.35,
    "background_overlay_mode": "auto",
    "active_companion": "avocet",       # avocet, yoga_ganapathy, lakshmi_ganapathy, male_lion
    "greeting_setting": "every_startup", # every_startup, morning_only, morning_evening, never
    "animations_enabled": True,
    "voice_enabled": True,
    "voice_rate": 160,
    "companion_enabled": True,
    "companion_visible_seconds": 24,
    "greeting_mode": "once_daily",      # once_daily, every_startup, never
    "greeting_morning_enabled": True,
    "greeting_afternoon_enabled": True,
    "greeting_evening_enabled": True,
    "greeting_night_enabled": True,
    "devotional_intro": True,
    "devotional_intro_text": "Om Gam Ganapataye Namaha.",
    "ui_language": "en",
    "region_country": "",
    "region_use_24h": True,
    "region_date_style": "dmy",
    "assistant_name": "Durga",
    "user_salutation": "friend",
    "active_voice_profile": "durga",
    "active_tone_style": "custom",
    "audio_output_device": "auto",      # auto, system_default, or a concrete PipeWire/Pulse sink
    "dashboard_world_clocks": [],
    "dashboard_layout_preset": "Executive",
    "custom_greeting_morning": (
        "Hi {salutation}, I am {assistant}. Good morning. "
        "Wishing you a peaceful, confident and successful day. "
        "Let us begin with clarity, positivity and focus."
    ),
    "custom_greeting_afternoon": (
        "Hi {salutation}, I am {assistant}. Good afternoon. "
        "Wishing you a focused and productive rest of the day."
    ),
    "custom_greeting_evening": (
        "Hi {salutation}, I am {assistant}. Good evening. Welcome back. "
        "Let us close the day calmly and with clarity."
    ),
    "custom_greeting_night": (
        "Hi {salutation}, I am {assistant}. Good evening. Welcome back. "
        "Let us close the day calmly and with clarity."
    ),
    "last_greeting_morning_date": "",
    "last_greeting_afternoon_date": "",
    "last_greeting_evening_date": "",
    "last_greeting_night_date": "",
    "shutdown_guard_enabled": True,
    "gantt_plan_color": "#3584E4",     # Adwaita Blue
    "gantt_actual_color": "#10B981",   # Emerald Green
    "gantt_delayed_color": "#EF4444",   # Red
    "working_weekdays": [0, 1, 2, 3, 4], # Mon-Fri default
    "weekend_days": [5, 6],             # Sat-Sun default
    "default_daily_capacity_minutes": 480, # 8h / day

    # Description Editor customer defaults.
    # These are presentation defaults only; inline rich-text HTML remains authoritative.
    "description_font_use_app_default": True,
    "description_font_family": "",
    "description_font_size": 13,
    "description_font_color_mode": "auto",   # auto | custom
    "description_font_color": "#0F172A",
}

class SettingsManager:
    """
    Manages application settings stored in SQLite with JSON file backup.
    """
    def __init__(self, db_manager=None, config_dir: Optional[Path] = None):
        self.db_manager = db_manager
        
        if config_dir is not None:
            config_dir = Path(config_dir)
        else:
            from todo_bird_app.services.path_resolver import PathResolver
            config_dir = PathResolver.get_config_dir()
                
        config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = config_dir / "config.json"
        self._settings = dict(DEFAULT_CONFIG)
        self.load_settings()

    def load_settings(self):
        # 1. Load from config.json if exists
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    file_settings = json.load(f)
                    self._settings.update(file_settings)
            except Exception as e:
                logger.error(f"Error reading config.json: {e}")

        # 2. Sync with database if available
        if self.db_manager:
            try:
                with self.db_manager.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT key, value FROM settings;")
                    for row in cursor.fetchall():
                        k, db_val = row[0], row[1]
                        if db_val is not None:
                            try:
                                self._settings[k] = json.loads(db_val)
                            except Exception:
                                self._settings[k] = db_val
            except Exception as e:
                logger.error(f"Error loading settings from DB: {e}")

        # 3. Synchronize with working_calendar authority
        self._sync_working_calendar()

    def _sync_working_calendar(self):
        try:
            from todo_bird_app.utils.working_calendar import (
                set_configured_working_weekdays,
                set_default_daily_capacity_minutes,
            )
            raw_work = self._settings.get("working_weekdays")
            if raw_work is not None and isinstance(raw_work, list):
                set_configured_working_weekdays(set(raw_work))
            elif "weekend_days" in self._settings and isinstance(self._settings["weekend_days"], list):
                weekends = set(self._settings["weekend_days"])
                work_days = [d for d in range(7) if d not in weekends]
                set_configured_working_weekdays(set(work_days))

            if "default_daily_capacity_minutes" in self._settings:
                set_default_daily_capacity_minutes(self._settings["default_daily_capacity_minutes"])
        except Exception as e:
            logger.error(f"Error syncing working calendar from settings: {e}")

    def save_settings(self):
        # 1. Write to JSON
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2)
        except Exception as e:
            logger.error(f"Error writing config.json: {e}")

        # 2. Write to DB if available
        if self.db_manager:
            try:
                for k, v in self._settings.items():
                    val_str = json.dumps(v) if isinstance(v, (dict, list, bool)) else str(v)
                    self.db_manager.set_setting(k, val_str)
            except Exception as e:
                logger.error(f"Error saving setting to DB: {e}")

        # 3. Keep working calendar in sync
        self._sync_working_calendar()

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default if default is not None else DEFAULT_CONFIG.get(key))

    def set(self, key: str, value: Any):
        self._settings[key] = value
        self.save_settings()

    def all_settings(self) -> Dict[str, Any]:
        return dict(self._settings)
