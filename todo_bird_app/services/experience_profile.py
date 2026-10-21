"""
Experience Profile Service (Batch 3.9)
Centralized profile tokens for Visual Experience Modes:
- professional: compact spacing, high information density, data-first cards, quieter backgrounds
- balanced: standard balanced spacing and imagery
- personal: generous spacing, prominent companion/imagery, warmer card surfaces
"""

from typing import Dict, Any, Optional

EXPERIENCE_PROFILES: Dict[str, Dict[str, Any]] = {
    "professional": {
        "mode": "professional",
        "card_radius": 6,
        "card_padding": 8,
        "section_spacing": 8,
        "thumbnail_size": 24,
        "thumbnail_visible": False,
        "background_opacity_multiplier": 0.3,
        "companion_prominence": "minimal",
        "dashboard_density": "compact",
        "task_row_height": 28,
        "chart_scale": 0.85,
        "accent_muted": True,
    },
    "balanced": {
        "mode": "balanced",
        "card_radius": 10,
        "card_padding": 12,
        "section_spacing": 14,
        "thumbnail_size": 48,
        "thumbnail_visible": True,
        "background_opacity_multiplier": 1.0,
        "companion_prominence": "standard",
        "dashboard_density": "balanced",
        "task_row_height": 36,
        "chart_scale": 1.0,
        "accent_muted": False,
    },
    "personal": {
        "mode": "personal",
        "card_radius": 14,
        "card_padding": 16,
        "section_spacing": 20,
        "thumbnail_size": 80,
        "thumbnail_visible": True,
        "background_opacity_multiplier": 1.5,
        "companion_prominence": "prominent",
        "dashboard_density": "relaxed",
        "task_row_height": 44,
        "chart_scale": 1.15,
        "accent_muted": False,
    },
}

class ExperienceProfileService:
    """
    Central service providing design tokens based on the current experience mode.
    """
    @staticmethod
    def get_profile(mode: Optional[str] = "balanced") -> Dict[str, Any]:
        key = (mode or "balanced").lower().strip()
        return EXPERIENCE_PROFILES.get(key, EXPERIENCE_PROFILES["balanced"])

    @staticmethod
    def get_active_profile(settings_manager=None) -> Dict[str, Any]:
        if settings_manager is not None:
            mode = settings_manager.get("visual_experience_mode", "balanced")
            return ExperienceProfileService.get_profile(mode)
        return EXPERIENCE_PROFILES["balanced"]
