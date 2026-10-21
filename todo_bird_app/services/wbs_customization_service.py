"""
TODO BIRD — WBS & CONTROL CUSTOMIZATION SERVICE
Manages centralized user interface preferences, WBS density profiles,
animation policies, and user-friendly error translations.
"""

from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass
from todo_bird_app.settings.settings_manager import SettingsManager


@dataclass(frozen=True)
class WBSDensityMetrics:
    mode: str
    row_height: int
    font_size: int
    indent_px: int
    padding_v: int


class WBSCustomizationService:
    """
    Central authority for WBS appearance configuration and user settings persistence.
    """

    # Density profiles
    DENSITY_PROFILES: Dict[str, WBSDensityMetrics] = {
        "professional": WBSDensityMetrics(
            mode="professional",
            row_height=28,
            font_size=12,
            indent_px=16,
            padding_v=2,
        ),
        "balanced": WBSDensityMetrics(
            mode="balanced",
            row_height=36,
            font_size=13,
            indent_px=20,
            padding_v=4,
        ),
        "personal": WBSDensityMetrics(
            mode="personal",
            row_height=44,
            font_size=14,
            indent_px=24,
            padding_v=6,
        ),
    }

    DEFAULT_SETTINGS = {
        "wbs_density": "balanced",
        "wbs_custom_row_height": 0,  # 0 = auto based on density
        "wbs_custom_indent": 0,      # 0 = auto based on density
        "wbs_show_code": True,
        "wbs_show_progress": True,
        "wbs_show_status": True,
        "wbs_show_icons": True,
        "wbs_show_guide_lines": True,
        "wbs_show_project_summary": True,
        "wbs_show_parent_rollup_progress": True,   # Show derived parent progress (rollup) vs leaf stored
        "wbs_show_parent_effort_summary": False,   # Show planned/actual effort summary on parent rows
        "wbs_show_parent_dates": False,            # Show planned start/finish dates on parent rows
        # Phase 2B Schedule Intelligence columns
        "wbs_show_critical": True,
        "wbs_show_total_float": True,
        "wbs_show_free_float": False,
        "wbs_show_es": False,
        "wbs_show_ef": False,
        "wbs_show_ls": False,
        "wbs_show_lf": False,
        "wbs_show_diagnostics": False,
        # Phase 2D Schedule Baseline & Variance columns
        "wbs_show_baseline_start": False,
        "wbs_show_baseline_finish": False,
        "wbs_show_start_variance": False,
        "wbs_show_finish_variance": True,
        "wbs_show_duration_variance": False,
        # Phase 2E Schedule Constraints & Deadlines columns
        "wbs_show_constraint_type": True,
        "wbs_show_constraint_date": True,
        "wbs_show_deadline": False,
        "wbs_show_deadline_variance": False,
        "wbs_show_constraint_status": True,
        "gantt_show_baseline": True,
        "wbs_surface_style": "clean",          # "clean" | "soft_panels" | "minimal"
        "wbs_summary_emphasis": "standard",    # "standard" | "subtle" | "strong"
        "wbs_guide_contrast": "low",           # "low" | "medium" | "high"
        "ui_animation_mode": "full",           # "full" | "reduced" | "off"
        "wbs_milestone_accent": "#8B5CF6",
    }

    def __init__(self, settings_manager: SettingsManager):
        self._settings = settings_manager

    def get_preference(self, key: str, default: Any = None) -> Any:
        def_val = default if default is not None else self.DEFAULT_SETTINGS.get(key)
        val = self._settings.get(key, def_val)
        # Type coercions
        if isinstance(def_val, bool):
            if isinstance(val, str):
                return val.lower() in ("true", "1", "yes")
            return bool(val)
        elif isinstance(def_val, int):
            try:
                return int(val)
            except (ValueError, TypeError):
                return def_val
        return val

    def set_preference(self, key: str, value: Any):
        self._settings.set(key, value)

    def get_all_preferences(self) -> Dict[str, Any]:
        return {
            key: self.get_preference(key, default)
            for key, default in self.DEFAULT_SETTINGS.items()
        }

    def save_preferences(self, prefs: Dict[str, Any]):
        for k, v in prefs.items():
            if k in self.DEFAULT_SETTINGS:
                self.set_preference(k, v)

    def reset_to_defaults(self):
        """Resets all WBS preferences to defaults."""
        for k, v in self.DEFAULT_SETTINGS.items():
            self.set_preference(k, v)

    def get_density_metrics(self) -> WBSDensityMetrics:
        """Returns the active density metrics with any custom overrides applied."""
        density_mode = str(self.get_preference("wbs_density", "balanced")).lower()
        base = self.DENSITY_PROFILES.get(density_mode, self.DENSITY_PROFILES["balanced"])

        custom_row_h = self.get_preference("wbs_custom_row_height", 0)
        custom_indent = self.get_preference("wbs_custom_indent", 0)

        row_h = custom_row_h if custom_row_h > 0 else base.row_height
        indent = custom_indent if custom_indent > 0 else base.indent_px

        return WBSDensityMetrics(
            mode=base.mode,
            row_height=row_h,
            font_size=base.font_size,
            indent_px=indent,
            padding_v=base.padding_v,
        )

    def is_animation_enabled(self) -> bool:
        mode = str(self.get_preference("ui_animation_mode", "full")).lower()
        return mode != "off"

    def is_reduced_motion(self) -> bool:
        mode = str(self.get_preference("ui_animation_mode", "full")).lower()
        return mode == "reduced"

    def get_surface_colors(self, is_dark: bool, accent_color: str) -> Dict[str, Any]:
        """Returns structured semantic surface colors based on active preferences."""
        style = str(self.get_preference("wbs_surface_style", "clean")).lower()
        emphasis = str(self.get_preference("wbs_summary_emphasis", "standard")).lower()
        contrast = str(self.get_preference("wbs_guide_contrast", "low")).lower()

        guide_alpha = 16 if contrast == "low" else (32 if contrast == "medium" else 50)
        summary_alpha = 8 if emphasis == "subtle" else (14 if emphasis == "standard" else 22)

        if is_dark:
            return {
                "bg_base": "#14141E",
                "bg_panel": "#1C1D2C" if style != "minimal" else "#14141E",
                "bg_toolbar": "#1E1F30" if style != "minimal" else "#14141E",
                "bg_header": "#181926",
                "border_panel": "#2E3045" if style != "minimal" else "transparent",
                "border_subtle": "#2E3045",
                "text_primary": "#CDD6F4",
                "text_secondary": "#A6ADC8",
                "text_muted": "#6C7086",
                "summary_alpha": summary_alpha,
                "hover_alpha": 18,
                "selected_alpha": 45,
                "guide_alpha": guide_alpha,
            }
        else:
            return {
                "bg_base": "#F1F5F9",
                "bg_panel": "#FFFFFF" if style != "minimal" else "#F1F5F9",
                "bg_toolbar": "#FFFFFF" if style != "minimal" else "#F1F5F9",
                "bg_header": "#F8FAFC",
                "border_panel": "#E2E8F0" if style != "minimal" else "transparent",
                "border_subtle": "#E2E8F0",
                "text_primary": "#0F172A",
                "text_secondary": "#475569",
                "text_muted": "#94A3B8",
                "summary_alpha": summary_alpha,
                "hover_alpha": 12,
                "selected_alpha": 25,
                "guide_alpha": guide_alpha,
            }

    @staticmethod
    def format_friendly_error(reason_code: str, entity_title: str = "This task") -> Tuple[str, str]:
        """
        Translates raw technical error codes into clear, helpful human messages.
        Returns (headline, explanation).
        """
        if reason_code in ("CYCLE_DETECTED", "ERR_CYCLE_DETECTED"):
            return (
                "Can't move task here",
                f"'{entity_title}' cannot be placed under one of its own subtasks.",
            )
        elif reason_code in ("SELF_PARENT", "ERR_SELF_PARENT"):
            return (
                "Invalid hierarchy change",
                f"'{entity_title}' cannot be parented to itself.",
            )
        elif reason_code in ("CROSS_PROJECT_MISMATCH", "ERR_CROSS_PROJECT_MISMATCH"):
            return (
                "Cross-project move not supported",
                "Tasks and subtasks can only be organized within the same project.",
            )
        elif reason_code in ("PARENT_NOT_FOUND", "ERR_PARENT_NOT_FOUND"):
            return (
                "Parent task not found",
                "The target parent task does not exist or has been deleted.",
            )
        else:
            return (
                "Hierarchy change rejected",
                "The requested tree structure change is invalid.",
            )
