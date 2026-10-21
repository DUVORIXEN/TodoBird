"""
TODO BIRD — UI Language Service (i18n layer)

Design contract:
- The canonical source strings are the English UI strings already in the
  codebase. Translation packs map English source -> translated text.
- `t(text)` is a total function: unknown strings and unknown languages
  always fall back to the English source, so the app can never render a
  blank label and default (English) behavior is byte-identical to before.
- Chrome surfaces (navigation, header bar, menus, settings tabs) retranslate
  live; deep content (dialogs, forms, data-driven views) picks the new
  language on restart. The UI tells the user this on change.
- Packs live in todo_bird_app/i18n/<code>.json as data, so languages can be
  added or crowd-corrected without touching code.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import QObject, Qt, Signal

logger = logging.getLogger(__name__)

I18N_DIR = Path(__file__).resolve().parent.parent / "i18n"

# (code, native name, english name, flag, rtl)
LANGUAGES = [
    ("en", "English", "English", "🇺🇸", False),
    ("es", "Español", "Spanish", "🇪🇸", False),
    ("fr", "Français", "French", "🇫🇷", False),
    ("de", "Deutsch", "German", "🇩🇪", False),
    ("pt", "Português (Brasil)", "Portuguese (Brazil)", "🇧🇷", False),
    ("hi", "हिन्दी", "Hindi", "🇮🇳", False),
    ("te", "తెలుగు", "Telugu", "🇮🇳", False),
    ("ar", "العربية", "Arabic", "🇸🇦", True),
    ("zh_cn", "简体中文", "Chinese (Simplified)", "🇨🇳", False),
    ("ja", "日本語", "Japanese", "🇯🇵", False),
    ("ru", "Русский", "Russian", "🇷🇺", False),
]

RTL_LANGUAGES = {code for code, _n, _e, _f, rtl in LANGUAGES if rtl}

_LANGUAGE_MAP = {code: (native, english, flag, rtl) for code, native, english, flag, rtl in LANGUAGES}


class LanguageService(QObject):
    """Resolves UI strings for the active language and retranslates chrome."""

    language_changed = Signal(str)

    _instance: Optional["LanguageService"] = None

    def __init__(self, settings_manager=None):
        super().__init__()
        self.settings_manager = settings_manager
        self._packs: Dict[str, Dict[str, str]] = {}
        self._current = "en"

    # ------------------------------------------------------------------
    # Registration / lookup
    # ------------------------------------------------------------------

    @classmethod
    def instance(cls, settings_manager=None) -> "LanguageService":
        if cls._instance is None:
            cls._instance = cls(settings_manager)
        elif settings_manager is not None and cls._instance.settings_manager is None:
            cls._instance.settings_manager = settings_manager
        return cls._instance

    @staticmethod
    def available_languages():
        return tuple(LANGUAGES)

    @staticmethod
    def native_name(code: str) -> str:
        return _LANGUAGE_MAP.get(code, ("English",))[0]

    @staticmethod
    def is_rtl(code: str) -> bool:
        return code in RTL_LANGUAGES

    def current_language(self) -> str:
        return self._current

    def _load_pack(self, code: str) -> Dict[str, str]:
        if code in self._packs:
            return self._packs[code]
        pack: Dict[str, str] = {}
        if code and code != "en":
            pack_path = I18N_DIR / f"{code}.json"
            try:
                if pack_path.exists():
                    raw = json.loads(pack_path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        pack = {
                            str(k): str(v)
                            for k, v in raw.items()
                            if isinstance(v, str) and v.strip()
                        }
            except (OSError, ValueError) as exc:
                logger.warning("Language pack %s unreadable: %s", code, exc)
        self._packs[code] = pack
        return pack

    def t(self, text: str) -> str:
        """Translate an English source string; always returns usable text."""
        if not text:
            return text
        if self._current == "en":
            return text
        translated = self._load_pack(self._current).get(text)
        return translated if translated else text

    def coverage(self) -> float:
        """Fraction of the reference string set covered by the active pack."""
        if self._current == "en":
            return 1.0
        pack = self._load_pack(self._current)
        if not REFERENCE_STRINGS:
            return 0.0
        return sum(1 for s in REFERENCE_STRINGS if s in pack) / len(REFERENCE_STRINGS)

    # ------------------------------------------------------------------
    # Apply / retranslate
    # ------------------------------------------------------------------

    def initialize(self, settings_manager=None) -> str:
        """Read the persisted language and apply it without retranslation
        (call once at startup, before chrome is built)."""
        manager = settings_manager or self.settings_manager
        code = "en"
        if manager is not None:
            try:
                code = str(manager.get("ui_language", "en") or "en").lower().strip()
            except Exception:
                code = "en"
        if code not in _LANGUAGE_MAP:
            code = "en"
        self._current = code
        self._apply_layout_direction()
        return code

    def set_language(self, code: str) -> str:
        """Switch UI language, persist it, apply RTL direction, retranslate
        the live chrome, and notify the rest of the app."""
        code = str(code or "en").lower().strip()
        if code not in _LANGUAGE_MAP:
            return self._current
        if code == self._current:
            return code
        self._current = code
        if self.settings_manager is not None:
            try:
                self.settings_manager.set("ui_language", code)
            except Exception:
                pass
        self._apply_layout_direction()
        self.language_changed.emit(code)
        return code

    def _apply_layout_direction(self):
        app = None
        try:
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
        except Exception:
            app = None
        if app is None:
            return
        try:
            direction = Qt.RightToLeft if self.is_rtl(self._current) else Qt.LeftToRight
            app.setLayoutDirection(direction)
        except Exception:
            pass


def t(text: str) -> str:
    """Module-level convenience used by chrome widgets."""
    return LanguageService.instance().t(text)


def retranslate_available_widgets() -> None:
    """Ask registered chrome widgets to retranslate (language switch)."""
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return
        for widget in list(app.topLevelWidgets()):
            hook = getattr(widget, "retranslate_ui", None)
            if callable(hook):
                try:
                    hook()
                except Exception:
                    logger.exception("retranslate_ui failed on %s", type(widget).__name__)
    except Exception:
        pass


# ----------------------------------------------------------------------
# Reference string set — the chrome strings shipped in every pack.
# English source text is the key; packs map it to the translation.
# ----------------------------------------------------------------------

REFERENCE_STRINGS = (
    # Navigation
    "Dashboard", "Inbox", "Today", "Focus Mode", "Upcoming", "Projects",
    "Completed", "Calendar", "Gantt Chart", "Analytics", "Daily Review",
    "Pilot Feedback", "World Clock", "Settings",
    # Header bar
    "+  New Task", "World Clock", "Mode", "Light", "Dark", "? Help",
    "Support Todo Bird", "Diagnostics", "About",
    # Menus
    "&File", "&Edit", "&View", "&Help", "Toggle &Theme Mode",
    "Select &All", "E&xit",
    # Settings tabs
    "Appearance", "Typography", "Reminders", "Companion", "Planning",
    "System", "Dashboard",
    # Settings sections
    "Language & Region", "UI Language", "Country / Region",
    "Apply Region Defaults", "UI Language changes apply instantly to the "
    "navigation, header bar and menus. Restart Todo Bird to translate "
    "every window.",
    "Region defaults set the working week and 12/24-hour clock for the "
    "selected country.",
    # Common actions
    "Save", "Cancel", "Delete", "Edit", "Add Task", "Complete", "Snooze",
    "Dismiss", "Search…", "Quick Backup",
    # Toasts / notes
    "Language updated", "Restart for full effect",
)
