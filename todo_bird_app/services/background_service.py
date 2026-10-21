"""
Canonical Todo Bird background appearance model.

This service preserves the older image-background settings while adding the
Phase 2E global/per-view background hierarchy:

global settings -> optional view override -> BackgroundOverlayWidget.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, Mapping, Optional

from PySide6.QtGui import QColor


BACKGROUND_MODE_THEME_DEFAULT = "theme_default"
BACKGROUND_MODE_SOLID = "solid"
BACKGROUND_MODE_IMAGE = "image"
BACKGROUND_MODE_TRANSPARENT = "transparent"

BACKGROUND_MODES = {
    BACKGROUND_MODE_THEME_DEFAULT,
    BACKGROUND_MODE_SOLID,
    BACKGROUND_MODE_IMAGE,
    BACKGROUND_MODE_TRANSPARENT,
}

BACKGROUND_FIT_MODES = {"fill", "fit", "stretch", "center", "tile"}

BACKGROUND_COLOR_PRESETS = {
    "theme_surface": ("Theme Surface", "#242538"),
    "graphite": ("Graphite", "#1F2937"),
    "slate": ("Slate", "#334155"),
    "midnight": ("Midnight", "#111827"),
    "navy": ("Navy", "#172554"),
    "indigo": ("Indigo", "#312E81"),
    "emerald_tint": ("Emerald Tint", "#D1FAE5"),
    "warm_sand": ("Warm Sand", "#F5E9D6"),
    "soft_grey": ("Soft Grey", "#E5E7EB"),
    "pure_white": ("Pure White", "#FFFFFF"),
}

VIEW_LABELS = {
    "dashboard": "Dashboard",
    "inbox": "Inbox",
    "today": "Today",
    "upcoming": "Upcoming",
    "completed": "Completed",
    "projects": "Projects",
    "wbs": "WBS",
    "gantt": "Gantt",
    "calendar": "Calendar",
    "focus": "Focus",
    "daily_review": "Daily Review",
    "analytics": "Analytics",
    "settings": "Settings",
    "feedback": "Pilot Feedback",
}


@dataclass(frozen=True)
class BackgroundConfig:
    mode: str = BACKGROUND_MODE_THEME_DEFAULT
    color: str = "#161821"
    image: str = ""
    opacity: float = 1.0
    fit: str = "fill"
    overlay_mode: str = "auto"
    view_id: Optional[str] = None
    inherited: bool = False
    source: str = "global"

    def with_changes(self, **changes: Any) -> "BackgroundConfig":
        return replace(self, **changes)

    def to_settings_dict(self) -> Dict[str, Any]:
        return {
            "override_enabled": True,
            "mode": self.mode,
            "color": self.color,
            "image": self.image,
            "opacity": self.opacity,
            "fit": self.fit,
            "overlay_mode": self.overlay_mode,
        }


class BackgroundService:
    """Resolve, persist and reset Todo Bird background settings."""

    @staticmethod
    def normalize_mode(value: Any) -> str:
        mode = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if mode in {"", "none", "default", "theme", "theme_default"}:
            return BACKGROUND_MODE_THEME_DEFAULT
        if mode in {"custom", "custom_image", "image", "background_image"}:
            return BACKGROUND_MODE_IMAGE
        if mode in {"solid", "solid_color", "color"}:
            return BACKGROUND_MODE_SOLID
        if mode in {"transparent", "translucent", "alpha"}:
            return BACKGROUND_MODE_TRANSPARENT
        return BACKGROUND_MODE_THEME_DEFAULT

    @staticmethod
    def normalize_fit(value: Any) -> str:
        fit = str(value or "fill").strip().lower()
        return fit if fit in BACKGROUND_FIT_MODES else "fill"

    @staticmethod
    def normalize_opacity(value: Any, fallback: float = 1.0) -> float:
        try:
            opacity = float(value)
        except (TypeError, ValueError):
            opacity = fallback
        return max(0.0, min(1.0, opacity))

    @staticmethod
    def normalize_color(value: Any, fallback: str = "#161821") -> str:
        color = QColor(str(value or ""))
        if not color.isValid():
            color = QColor(fallback)
        if not color.isValid():
            color = QColor("#161821")
        fmt = QColor.NameFormat.HexArgb if color.alpha() < 255 else QColor.NameFormat.HexRgb
        return color.name(fmt).upper()

    @staticmethod
    def color_preset_items() -> Iterable[tuple[str, str, str]]:
        for key, (label, color) in BACKGROUND_COLOR_PRESETS.items():
            yield key, label, color

    @staticmethod
    def view_label(view_id: Optional[str]) -> str:
        key = str(view_id or "settings").strip().lower()
        return VIEW_LABELS.get(key, key.replace("_", " ").title())

    @staticmethod
    def _settings_get(settings_manager: Any, key: str, default: Any = None) -> Any:
        if settings_manager is None:
            return default
        try:
            return settings_manager.get(key, default)
        except Exception:
            return default

    @staticmethod
    def _theme_surface_color(settings_manager: Any, tokens: Optional[Mapping[str, str]]) -> str:
        if tokens and tokens.get("APP_BACKGROUND"):
            return BackgroundService.normalize_color(tokens["APP_BACKGROUND"], "#161821")
        theme = str(BackgroundService._settings_get(settings_manager, "theme", "dark")).lower()
        return "#F5F7FB" if theme == "light" else "#161821"

    @staticmethod
    def global_config(settings_manager: Any, tokens: Optional[Mapping[str, str]] = None) -> BackgroundConfig:
        theme_surface = BackgroundService._theme_surface_color(settings_manager, tokens)
        raw_global_mode = BackgroundService._settings_get(
            settings_manager,
            "global_background_mode",
            None,
        )
        mode = BackgroundService.normalize_mode(raw_global_mode)

        legacy_mode = BackgroundService.normalize_mode(
            BackgroundService._settings_get(settings_manager, "background_mode", "none")
        )
        legacy_image = str(
            BackgroundService._settings_get(
                settings_manager,
                "background_custom_image_path",
                "",
            )
            or ""
        )
        global_image = str(
            BackgroundService._settings_get(settings_manager, "global_background_image", "")
            or ""
        )

        # Preserve existing image-background users when their config predates
        # the new global_* authority keys.
        using_legacy_image = (
            (raw_global_mode in (None, "", BACKGROUND_MODE_THEME_DEFAULT))
            and legacy_mode == BACKGROUND_MODE_IMAGE
            and legacy_image
            and not global_image
        )
        if using_legacy_image:
            mode = BACKGROUND_MODE_IMAGE
            global_image = legacy_image

        default_opacity = 0.22 if mode == BACKGROUND_MODE_TRANSPARENT else 1.0
        if using_legacy_image:
            default_opacity = BackgroundService.normalize_opacity(
                BackgroundService._settings_get(settings_manager, "background_opacity", 0.35),
                0.35,
            )
        opacity_value = (
            BackgroundService._settings_get(settings_manager, "background_opacity", default_opacity)
            if using_legacy_image
            else BackgroundService._settings_get(
                settings_manager,
                "global_background_opacity",
                default_opacity,
            )
        )
        fit_value = (
            BackgroundService._settings_get(settings_manager, "background_fit_mode", "fill")
            if using_legacy_image
            else BackgroundService._settings_get(
                settings_manager,
                "global_background_fit",
                BackgroundService._settings_get(settings_manager, "background_fit_mode", "fill"),
            )
        )
        overlay_value = (
            BackgroundService._settings_get(settings_manager, "background_overlay_mode", "auto")
            if using_legacy_image
            else BackgroundService._settings_get(
                settings_manager,
                "global_background_overlay_mode",
                BackgroundService._settings_get(settings_manager, "background_overlay_mode", "auto"),
            )
        )

        return BackgroundConfig(
            mode=mode,
            color=BackgroundService.normalize_color(
                BackgroundService._settings_get(
                    settings_manager,
                    "global_background_color",
                    theme_surface,
                ),
                theme_surface,
            ),
            image=global_image,
            opacity=BackgroundService.normalize_opacity(opacity_value, default_opacity),
            fit=BackgroundService.normalize_fit(fit_value),
            overlay_mode=str(overlay_value or "auto").lower(),
            source="global",
        )

    @staticmethod
    def view_overrides(settings_manager: Any) -> Dict[str, Dict[str, Any]]:
        raw = BackgroundService._settings_get(settings_manager, "view_background_overrides", {})
        return dict(raw) if isinstance(raw, dict) else {}

    @staticmethod
    def has_view_override(settings_manager: Any, view_id: Optional[str]) -> bool:
        key = str(view_id or "").strip().lower()
        entry = BackgroundService.view_overrides(settings_manager).get(key, {})
        return bool(isinstance(entry, dict) and entry.get("override_enabled"))

    @staticmethod
    def effective_config(
        settings_manager: Any,
        view_id: Optional[str] = None,
        tokens: Optional[Mapping[str, str]] = None,
    ) -> BackgroundConfig:
        global_config = BackgroundService.global_config(settings_manager, tokens)
        key = str(view_id or "").strip().lower()
        if not key:
            return global_config

        entry = BackgroundService.view_overrides(settings_manager).get(key, {})
        if not isinstance(entry, dict) or not entry.get("override_enabled"):
            return global_config.with_changes(view_id=key, inherited=True, source="global")

        mode = BackgroundService.normalize_mode(entry.get("mode", global_config.mode))
        default_opacity = 0.22 if mode == BACKGROUND_MODE_TRANSPARENT else global_config.opacity
        return BackgroundConfig(
            mode=mode,
            color=BackgroundService.normalize_color(entry.get("color", global_config.color), global_config.color),
            image=str(entry.get("image", global_config.image) or ""),
            opacity=BackgroundService.normalize_opacity(entry.get("opacity", default_opacity), default_opacity),
            fit=BackgroundService.normalize_fit(entry.get("fit", global_config.fit)),
            overlay_mode=str(entry.get("overlay_mode", global_config.overlay_mode) or "auto").lower(),
            view_id=key,
            inherited=False,
            source="view",
        )

    @staticmethod
    def _set_many(settings_manager: Any, values: Mapping[str, Any]) -> None:
        if settings_manager is None:
            return
        for key, value in values.items():
            settings_manager.set(key, value)

    @staticmethod
    def write_global(settings_manager: Any, config: BackgroundConfig | Mapping[str, Any]) -> BackgroundConfig:
        if isinstance(config, BackgroundConfig):
            cfg = config
        else:
            current = BackgroundService.global_config(settings_manager)
            cfg = current.with_changes(**dict(config))

        cfg = cfg.with_changes(
            mode=BackgroundService.normalize_mode(cfg.mode),
            color=BackgroundService.normalize_color(cfg.color),
            opacity=BackgroundService.normalize_opacity(
                cfg.opacity,
                0.22 if cfg.mode == BACKGROUND_MODE_TRANSPARENT else 1.0,
            ),
            fit=BackgroundService.normalize_fit(cfg.fit),
            image=str(cfg.image or ""),
            source="global",
            inherited=False,
            view_id=None,
        )

        legacy_mode = "custom" if cfg.mode == BACKGROUND_MODE_IMAGE and cfg.image else "none"
        BackgroundService._set_many(
            settings_manager,
            {
                "global_background_mode": cfg.mode,
                "global_background_color": cfg.color,
                "global_background_image": cfg.image,
                "global_background_opacity": cfg.opacity,
                "global_background_fit": cfg.fit,
                "global_background_overlay_mode": cfg.overlay_mode,
                "background_mode": legacy_mode,
                "background_custom_image_path": cfg.image if legacy_mode == "custom" else "",
                "background_fit_mode": cfg.fit,
                "background_opacity": cfg.opacity,
                "background_overlay_mode": cfg.overlay_mode,
            },
        )
        return cfg

    @staticmethod
    def write_view_override(
        settings_manager: Any,
        view_id: str,
        config: BackgroundConfig | Mapping[str, Any],
    ) -> BackgroundConfig:
        key = str(view_id or "").strip().lower()
        if not key:
            raise ValueError("view_id is required for a background override")

        if isinstance(config, BackgroundConfig):
            cfg = config
        else:
            current = BackgroundService.effective_config(settings_manager, key)
            cfg = current.with_changes(**dict(config))

        cfg = cfg.with_changes(
            mode=BackgroundService.normalize_mode(cfg.mode),
            color=BackgroundService.normalize_color(cfg.color),
            opacity=BackgroundService.normalize_opacity(
                cfg.opacity,
                0.22 if cfg.mode == BACKGROUND_MODE_TRANSPARENT else 1.0,
            ),
            fit=BackgroundService.normalize_fit(cfg.fit),
            image=str(cfg.image or ""),
            view_id=key,
            inherited=False,
            source="view",
        )

        overrides = BackgroundService.view_overrides(settings_manager)
        overrides[key] = cfg.to_settings_dict()
        if settings_manager is not None:
            settings_manager.set("view_background_overrides", overrides)
        return cfg

    @staticmethod
    def clear_view_override(settings_manager: Any, view_id: str) -> None:
        key = str(view_id or "").strip().lower()
        overrides = BackgroundService.view_overrides(settings_manager)
        if key in overrides:
            overrides.pop(key, None)
            if settings_manager is not None:
                settings_manager.set("view_background_overrides", overrides)

    @staticmethod
    def reset_all(settings_manager: Any) -> BackgroundConfig:
        cfg = BackgroundConfig()
        BackgroundService._set_many(
            settings_manager,
            {
                "view_background_overrides": {},
            },
        )
        return BackgroundService.write_global(settings_manager, cfg)
