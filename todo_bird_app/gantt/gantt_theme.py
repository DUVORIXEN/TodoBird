from dataclasses import dataclass, field
from typing import Dict, Any

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from todo_bird_app.services.appearance_service import semantic_tokens_for

DEFAULT_GANTT_COLORS = {
    # UI Elements
    "bg_color": "#1E1E2E",
    "grid_color": "rgba(255, 255, 255, 0.08)",
    "header_color": "#181825",
    "text_color": "#F3F4F6",
    "weekend_shade": "rgba(0, 0, 0, 0.15)",
    "today_marker_color": "#E95420",
    "current_time_marker_color": "#EF4444",
    "milestone_color": "#E95420",
    "dependency_line_color": "#3584E4",

    # Left Pane semantic tokens
    "panel_bg": "#1E293B",
    "panel_header_bg": "#1E293B",
    "panel_grid_color": "#374151",
    "panel_text_color": "#F3F4F6",
    "panel_secondary_text": "#9CA3AF",

    # Task Status & Timing Colors
    "planned_color": "#3584E4",          # Adwaita Blue
    "actual_color": "#10B981",           # Default Actual Green
    "completed_early_color": "#065F46",  # Dark Green
    "completed_ontime_color": "#10B981", # Light Green / Emerald
    "slight_delay_color": "#F59E0B",     # Amber / Yellow
    "moderate_delay_color": "#F97316",   # Orange
    "severe_delay_color": "#EF4444",     # Red
    "very_severe_delay_color": "#991B1B",# Deep Red
    "cancelled_color": "#6B7280",        # Muted Gray
    "paused_color": "#8B5CF6",           # Purple
    "critical_color": "#DC2626",         # Bright Red Border
    "selected_color": "#FBBF24",         # Gold Highlight
    "hovered_color": "#60A5FA",          # Bright Blue Highlight
}

LIGHT_GANTT_COLORS = {
    "bg_color": "#FFFFFF",
    "grid_color": "rgba(0, 0, 0, 0.08)",
    "header_color": "#EBECEF",
    "text_color": "#1F2937",
    "weekend_shade": "rgba(0, 0, 0, 0.04)",
    "today_marker_color": "#E95420",
    "current_time_marker_color": "#EF4444",
    "milestone_color": "#E95420",
    "dependency_line_color": "#3584E4",

    # Left Pane semantic tokens
    "panel_bg": "#F0F1F5",
    "panel_header_bg": "#EBECEF",
    "panel_grid_color": "#E5E7EB",
    "panel_text_color": "#1F2937",
    "panel_secondary_text": "#6B7280",

    "planned_color": "#2563EB",
    "actual_color": "#059669",
    "completed_early_color": "#047857",
    "completed_ontime_color": "#10B981",
    "slight_delay_color": "#D97706",
    "moderate_delay_color": "#EA580C",
    "severe_delay_color": "#DC2626",
    "very_severe_delay_color": "#991B1B",
    "cancelled_color": "#9CA3AF",
    "paused_color": "#7C3AED",
    "critical_color": "#B91C1C",
    "selected_color": "#D97706",
    "hovered_color": "#3B82F6",
}

HIGH_CONTRAST_GANTT_COLORS = {
    "bg_color": "#000000",
    "grid_color": "#FFFFFF",
    "header_color": "#111111",
    "text_color": "#FFFFFF",
    "weekend_shade": "#222222",
    "today_marker_color": "#FFFF00",
    "current_time_marker_color": "#FF0000",
    "milestone_color": "#FF00FF",
    "dependency_line_color": "#00FFFF",

    # Left Pane semantic tokens
    "panel_bg": "#000000",
    "panel_header_bg": "#111111",
    "panel_grid_color": "#FFFFFF",
    "panel_text_color": "#FFFFFF",
    "panel_secondary_text": "#CCCCCC",

    "planned_color": "#0000FF",
    "actual_color": "#00FF00",
    "completed_early_color": "#008000",
    "completed_ontime_color": "#00FF00",
    "slight_delay_color": "#FFFF00",
    "moderate_delay_color": "#FF8000",
    "severe_delay_color": "#FF0000",
    "very_severe_delay_color": "#800000",
    "cancelled_color": "#808080",
    "paused_color": "#800080",
    "critical_color": "#FF0000",
    "selected_color": "#FFFF00",
    "hovered_color": "#00FFFF",
}

@dataclass
class GanttColorProfile:
    mode: str = "follow_app"  # follow_app, light, dark, high_contrast, custom
    colors: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_GANTT_COLORS))

    def get_effective_colors(
        self,
        current_app_theme: str = "dark",
        accent_color: str = None,
    ) -> Dict[str, str]:
        def _follow_app_colors() -> Dict[str, str]:
            app = QApplication.instance()
            if accent_color is None and app is not None:
                accent = app.palette().color(QPalette.Highlight).name()
            else:
                accent = accent_color or "#3584E4"

            is_dark = str(current_app_theme).lower() == "dark"
            tokens = semantic_tokens_for(is_dark, accent)
            return {
                **(DEFAULT_GANTT_COLORS if is_dark else LIGHT_GANTT_COLORS),
                "bg_color": tokens["APP_BACKGROUND"],
                "grid_color": tokens["GANTT_GRID"],
                "header_color": tokens["GANTT_HEADER"],
                "text_color": tokens["GANTT_TEXT"],
                "text_primary": tokens["GANTT_TEXT"],
                "text_secondary": tokens["GANTT_TEXT_MUTED"],
                "today_marker_color": tokens["ACCENT"],
                "milestone_color": tokens["ACCENT"],
                "dependency_line_color": tokens["ACCENT"],
                "panel_bg": tokens["SURFACE_1"],
                "panel_header_bg": tokens["SURFACE_2"],
                "panel_grid_color": tokens["BORDER_NORMAL"],
                "panel_text_color": tokens["TEXT_PRIMARY"],
                "panel_secondary_text": tokens["TEXT_SECONDARY"],
                "planned_color": tokens["ACCENT"],
                "hovered_color": QColor(tokens["ACCENT"]).lighter(125).name(),
                "selected_color": QColor(tokens["ACCENT"]).lighter(135).name(),
            }

        if self.mode == "follow_app":
            return _follow_app_colors()
        elif self.mode == "light":
            return dict(LIGHT_GANTT_COLORS)
        elif self.mode == "dark":
            return dict(DEFAULT_GANTT_COLORS)
        elif self.mode == "high_contrast":
            return dict(HIGH_CONTRAST_GANTT_COLORS)
        else:  # custom
            profile = dict(DEFAULT_GANTT_COLORS)
            profile.update(self.colors)
            return profile

    def restore_defaults(self):
        self.mode = "follow_app"
        self.colors = dict(DEFAULT_GANTT_COLORS)
