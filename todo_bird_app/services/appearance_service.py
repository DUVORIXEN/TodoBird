"""
Canonical Todo Bird appearance model and propagation helpers.

The application has Qt style sheets, QPalette, custom-painted widgets and
per-area typography. This module is the single place that resolves persisted
settings into effective semantic tokens; ThemeController remains the runtime
applier.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget


ACCENT_SCHEMES = {
    "professional_blue": ("Professional Blue", "#2563EB"),
    "adwaita_blue": ("Adwaita Blue", "#3584E4"),
    "indigo": ("Indigo", "#4F46E5"),
    "emerald": ("Emerald", "#059669"),
    "amber": ("Amber", "#D97706"),
    "rose": ("Rose", "#E11D48"),
    "graphite": ("Graphite / Neutral", "#475569"),
    "ubuntu_orange": ("Ubuntu Orange", "#E95420"),
}

BUTTON_STYLE_VALUES = {
    "flat",
    "3d_raised",
    "executive_soft",
    "neumorphic",
    "glow",
}

THEME_MODES = {
    "dark",
    "light",
    "system",
    "oled",
    "warm_paper",
    "nord",
}

THEME_ITEMS = [
    ("dark", "Dark Mode"),
    ("light", "Light Mode"),
    ("system", "System / Auto"),
    ("oled", "OLED Midnight Black"),
    ("warm_paper", "Warm Paper / Sepia"),
    ("nord", "Nord / Slate Blue"),
]


def is_system_dark(app: Optional[QApplication] = None) -> bool:
    """Detect OS dark mode via Qt styleHints or fallback to window luminance."""
    app = app or QApplication.instance()
    if app is not None:
        try:
            from PySide6.QtCore import Qt

            hints = app.styleHints()
            if hasattr(hints, "colorScheme"):
                scheme = hints.colorScheme()
                if scheme == Qt.ColorScheme.Dark:
                    return True
                if scheme == Qt.ColorScheme.Light:
                    return False
        except Exception:
            pass
        try:
            win_color = app.palette().color(QPalette.Window)
            return _relative_luminance(win_color) < 0.35
        except Exception:
            pass
    return True


DENSITY_VALUES = {
    "compact",
    "balanced",
    "spacious",
}

DENSITY_METRICS = {
    "compact": {
        "button_padding_v": 4,
        "button_padding_h": 9,
        "control_padding_v": 4,
        "control_padding_h": 9,
        "toolbar_padding_v": 5,
    },
    "balanced": {
        "button_padding_v": 5,
        "button_padding_h": 11,
        "control_padding_v": 5,
        "control_padding_h": 10,
        "toolbar_padding_v": 6,
    },
    "spacious": {
        "button_padding_v": 7,
        "button_padding_h": 14,
        "control_padding_v": 7,
        "control_padding_h": 12,
        "toolbar_padding_v": 8,
    },
}

TEXT_COLOR_ROLES = {
    "TEXT_PRIMARY",
    "TEXT_SECONDARY",
    "TEXT_MUTED",
    "TEXT_DISABLED",
    "HEADING_PRIMARY",
    "HEADING_SECONDARY",
    "TEXT_ON_ACCENT",
    "TEXT_ON_DANGER",
    "TEXT_ON_WARNING",
    "TEXT_ON_SUCCESS",
    "LINK",
    "LINK_HOVER",
    "PLACEHOLDER_TEXT",
    "TABLE_HEADER_TEXT",
    "SECTION_HEADER_TEXT",
    "SIDEBAR_TEXT",
    "SIDEBAR_SELECTED_TEXT",
}

_TEXT_COLOR_DECL_RE = re.compile(r"(?<![-\w])color\s*:\s*([^;{}]+)", re.IGNORECASE)


@dataclass(frozen=True)
class AppearanceSettings:
    theme: str
    is_dark: bool
    accent_scheme: str
    accent_color: str
    font_family: str
    font_size: int
    font_weight: str
    density: str
    button_style: str
    tokens: Dict[str, str]

    def font(self) -> QFont:
        font = QFont(self.font_family)
        font.setPointSize(self.font_size)
        font.setWeight(font_weight_to_qt(self.font_weight))
        return font

    @property
    def density_metrics(self) -> Dict[str, int]:
        return dict(DENSITY_METRICS.get(self.density, DENSITY_METRICS["balanced"]))


def _valid_color(value: Any, fallback: str) -> str:
    color = QColor(str(value or ""))
    return color.name().upper() if color.isValid() else fallback


def _coerce_int(value: Any, fallback: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = fallback
    return max(minimum, min(maximum, number))


def font_weight_to_qt(weight_name: str) -> QFont.Weight:
    value = str(weight_name or "normal").strip().lower()
    if value in {"bold", "700"}:
        return QFont.Weight.Bold
    if value in {"semibold", "semi bold", "demibold", "600"}:
        return QFont.Weight.DemiBold
    if value in {"medium", "500"}:
        return QFont.Weight.Medium
    return QFont.Weight.Normal


def _accent_scheme_for_color(color_hex: str) -> str:
    normalized = _valid_color(color_hex, "#2563EB")
    for key, (_label, scheme_color) in ACCENT_SCHEMES.items():
        if _valid_color(scheme_color, scheme_color) == normalized:
            return key
    return "custom"


def _resolve_density(settings_manager: Any) -> str:
    explicit = str(
        settings_manager.get("ui_density", "")
        if settings_manager is not None
        else ""
    ).lower().strip()
    if explicit in DENSITY_VALUES:
        return explicit

    experience = str(
        settings_manager.get("visual_experience_mode", "balanced")
        if settings_manager is not None
        else "balanced"
    ).lower().strip()
    if experience == "professional":
        return "compact"
    if experience == "personal":
        return "spacious"
    return "balanced"


def _lighten(hex_color: str, factor: int) -> str:
    color = QColor(hex_color)
    return color.lighter(factor).name().upper() if color.isValid() else hex_color


def _darken(hex_color: str, factor: int) -> str:
    color = QColor(hex_color)
    return color.darker(factor).name().upper() if color.isValid() else hex_color


def _alpha_rgba(hex_color: str, alpha: int) -> str:
    color = QColor(hex_color)
    if not color.isValid():
        color = QColor("#2563EB")
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {max(0, min(255, int(alpha)))})"


def _text_on(hex_color: str) -> str:
    """Pick white or near-black text for a filled surface by WCAG contrast.

    Fixed white text fails on light accents (amber, emerald, nord cyan);
    the winning contrast ratio decides instead.
    """
    probe = QColor(hex_color)
    if not probe.isValid():
        return "#FFFFFF"
    return "#FFFFFF" if contrast_ratio("#FFFFFF", hex_color) >= contrast_ratio("#111827", hex_color) else "#111827"


def text_color_on(hex_color: str) -> str:
    """Public wrapper: readable text color for an arbitrary filled surface."""
    return _text_on(hex_color)


def _semantic_tokens(
    is_dark: bool,
    accent_color: str,
    theme: Optional[str] = None,
) -> Dict[str, str]:
    chosen = (theme or ("dark" if is_dark else "light")).lower().strip()
    if chosen == "system":
        chosen = "dark" if is_dark else "light"

    if chosen == "oled":
        tokens = {
            "APP_BACKGROUND": "#000000",
            "SURFACE_1": "#090A0F",
            "SURFACE_2": "#13151F",
            "SURFACE_3": "#1D202F",
            "BORDER_SUBTLE": "#1A1D28",
            "BORDER_NORMAL": "#282D3E",
            "BORDER_STRONG": "#3F4660",
            "TEXT_PRIMARY": "#FFFFFF",
            "TEXT_SECONDARY": "#A0A8B8",
            "TEXT_MUTED": "#737B8C",
            "TEXT_DISABLED": "#505666",
            "HEADING_PRIMARY": "#FFFFFF",
            "HEADING_SECONDARY": "#E0E6F0",
            "LINK": _lighten(accent_color, 145),
            "LINK_HOVER": _lighten(accent_color, 165),
            "PLACEHOLDER_TEXT": "#737B8C",
            "TABLE_HEADER_TEXT": "#FFFFFF",
            "SECTION_HEADER_TEXT": "#FFFFFF",
            "SIDEBAR_TEXT": "#A0A8B8",
            "SIDEBAR_SELECTED_TEXT": "#FFFFFF",
        }
    elif chosen == "warm_paper":
        tokens = {
            "APP_BACKGROUND": "#F8F4EC",
            "SURFACE_1": "#FCFBF7",
            "SURFACE_2": "#F2EDE0",
            "SURFACE_3": "#E7E0D0",
            "BORDER_SUBTLE": "#E8E0D0",
            "BORDER_NORMAL": "#D5CBB8",
            "BORDER_STRONG": "#AFA38E",
            "TEXT_PRIMARY": "#2C241D",
            "TEXT_SECONDARY": "#64584C",
            "TEXT_MUTED": "#8E8172",
            "TEXT_DISABLED": "#B0A495",
            "HEADING_PRIMARY": "#1F1710",
            "HEADING_SECONDARY": "#4B3E32",
            "LINK": accent_color,
            "LINK_HOVER": _darken(accent_color, 118),
            "PLACEHOLDER_TEXT": "#8E8172",
            "TABLE_HEADER_TEXT": "#1F1710",
            "SECTION_HEADER_TEXT": "#1F1710",
            "SIDEBAR_TEXT": "#64584C",
            "SIDEBAR_SELECTED_TEXT": "#1F1710",
        }
    elif chosen == "nord":
        tokens = {
            "APP_BACKGROUND": "#242933",
            "SURFACE_1": "#2E3440",
            "SURFACE_2": "#3B4252",
            "SURFACE_3": "#434C5E",
            "BORDER_SUBTLE": "#3B4252",
            "BORDER_NORMAL": "#4C566A",
            "BORDER_STRONG": "#677693",
            "TEXT_PRIMARY": "#ECEFF4",
            "TEXT_SECONDARY": "#D8DEE9",
            "TEXT_MUTED": "#93A1B8",
            "TEXT_DISABLED": "#697790",
            "HEADING_PRIMARY": "#FFFFFF",
            "HEADING_SECONDARY": "#88C0D0",
            "LINK": _lighten(accent_color, 130),
            "LINK_HOVER": _lighten(accent_color, 150),
            "PLACEHOLDER_TEXT": "#93A1B8",
            "TABLE_HEADER_TEXT": "#ECEFF4",
            "SECTION_HEADER_TEXT": "#FFFFFF",
            "SIDEBAR_TEXT": "#D8DEE9",
            "SIDEBAR_SELECTED_TEXT": "#88C0D0",
        }
    elif is_dark:
        tokens = {
            "APP_BACKGROUND": "#161821",
            "SURFACE_1": "#242538",
            "SURFACE_2": "#2A2B3D",
            "SURFACE_3": "#34364A",
            "BORDER_SUBTLE": "#2D3345",
            "BORDER_NORMAL": "#40485F",
            "BORDER_STRONG": "#647084",
            "TEXT_PRIMARY": "#F4F7FB",
            "TEXT_SECONDARY": "#B7C0D1",
            "TEXT_MUTED": "#8792A6",
            "TEXT_DISABLED": "#8792A6",
            "HEADING_PRIMARY": "#FFFFFF",
            "HEADING_SECONDARY": "#DCE4F2",
            "LINK": _lighten(accent_color, 145),
            "LINK_HOVER": _lighten(accent_color, 165),
            "PLACEHOLDER_TEXT": "#8792A6",
            "TABLE_HEADER_TEXT": "#F4F7FB",
            "SECTION_HEADER_TEXT": "#FFFFFF",
            "SIDEBAR_TEXT": "#B7C0D1",
            "SIDEBAR_SELECTED_TEXT": "#FFFFFF",
        }
    else:
        tokens = {
            "APP_BACKGROUND": "#F5F7FB",
            "SURFACE_1": "#FFFFFF",
            "SURFACE_2": "#EEF2F7",
            "SURFACE_3": "#E2E8F0",
            "BORDER_SUBTLE": "#D9E1EC",
            "BORDER_NORMAL": "#CBD5E1",
            "BORDER_STRONG": "#94A3B8",
            "TEXT_PRIMARY": "#111827",
            "TEXT_SECONDARY": "#475569",
            "TEXT_MUTED": "#64748B",
            "TEXT_DISABLED": "#64748B",
            "HEADING_PRIMARY": "#0F172A",
            "HEADING_SECONDARY": "#334155",
            "LINK": accent_color,
            "LINK_HOVER": _darken(accent_color, 118),
            "PLACEHOLDER_TEXT": "#64748B",
            "TABLE_HEADER_TEXT": "#0F172A",
            "SECTION_HEADER_TEXT": "#0F172A",
            "SIDEBAR_TEXT": "#475569",
            "SIDEBAR_SELECTED_TEXT": "#FFFFFF",
        }

    tokens.update(
        {
            "ACCENT": accent_color,
            "ACCENT_HOVER": _lighten(accent_color, 113) if is_dark else _darken(accent_color, 112),
            "ACCENT_PRESSED": _darken(accent_color, 120),
            "ACCENT_SUBTLE": _alpha_rgba(accent_color, 42 if is_dark else 28),
            "TEXT_ON_ACCENT": _text_on(accent_color),
            "TEXT_ON_DANGER": "#FFFFFF",
            "TEXT_ON_WARNING": "#1F1710" if chosen == "warm_paper" else ("#000000" if chosen == "oled" else "#111827"),
            "TEXT_ON_SUCCESS": "#FFFFFF",
            "SUCCESS": "#10B981" if chosen == "oled" else ("#A3BE8C" if chosen == "nord" else "#047857"),
            "WARNING": "#F59E0B" if chosen != "nord" else "#EBCB8B",
            "DANGER": "#EF4444" if chosen == "oled" else ("#BF616A" if chosen == "nord" else "#DC2626"),
            "DANGER_HOVER": "#DC2626" if chosen == "oled" else ("#A64D56" if chosen == "nord" else "#B91C1C"),
            "INFO": "#38BDF8" if chosen == "oled" else ("#88C0D0" if chosen == "nord" else "#06B6D4"),
            "FOCUS_RING": accent_color,
            "GANTT_PLANNED": accent_color,
            "GANTT_ACTUAL": "#10B981" if chosen == "oled" else ("#A3BE8C" if chosen == "nord" else "#10B981"),
            "GANTT_BASELINE": "#A855F7" if chosen == "oled" else ("#B48EAD" if chosen == "nord" else "#8B5CF6"),
            "GANTT_GRID": "#282D3E" if chosen == "oled" else ("#4C566A" if chosen == "nord" else ("#D5CBB8" if chosen == "warm_paper" else ("#3A4254" if is_dark else "#D7DEE9"))),
            "GANTT_HEADER": "#050508" if chosen == "oled" else ("#1E222A" if chosen == "nord" else ("#F2EDE0" if chosen == "warm_paper" else ("#1A1D2A" if is_dark else "#EEF2F7"))),
            "GANTT_TEXT": "#FFFFFF" if chosen == "oled" else ("#ECEFF4" if chosen == "nord" else ("#2C241D" if chosen == "warm_paper" else ("#F4F7FB" if is_dark else "#111827"))),
            "GANTT_TEXT_MUTED": "#737B8C" if chosen == "oled" else ("#93A1B8" if chosen == "nord" else ("#8E8172" if chosen == "warm_paper" else ("#AAB4C5" if is_dark else "#64748B"))),
            # Sidebar selection paints the accent as its background, so the
            # selected label must carry the on-accent text color (nord cyan
            # on cyan was previously invisible).
            "SIDEBAR_SELECTED_TEXT": _text_on(accent_color),
        }
    )

    # Existing QSS files consume these lower-case names. Keep them as aliases
    # to make the old files readers of the new semantic model.
    sidebar_bg = "#000000" if chosen == "oled" else ("#1E222A" if chosen == "nord" else ("#F2EDE0" if chosen == "warm_paper" else ("#11131B" if is_dark else "#E9EEF6")))
    header_bg = "#050508" if chosen == "oled" else ("#1E222A" if chosen == "nord" else ("#F2EDE0" if chosen == "warm_paper" else ("#121520" if is_dark else "#E9EEF6")))

    tokens.update(
        {
            "bg_root": tokens["APP_BACKGROUND"],
            "bg_sidebar": sidebar_bg,
            "bg_card": tokens["SURFACE_1"],
            "bg_card_hover": tokens["SURFACE_2"],
            "bg_header": header_bg,
            "bg_input": tokens["SURFACE_1"],
            "text_primary": tokens["TEXT_PRIMARY"],
            "text_secondary": tokens["TEXT_SECONDARY"],
            "text_muted": tokens["TEXT_MUTED"],
            "heading_primary": tokens["HEADING_PRIMARY"],
            "heading_secondary": tokens["HEADING_SECONDARY"],
            "placeholder_text": tokens["PLACEHOLDER_TEXT"],
            "table_header_text": tokens["TABLE_HEADER_TEXT"],
            "section_header_text": tokens["SECTION_HEADER_TEXT"],
            "sidebar_text": tokens["SIDEBAR_TEXT"],
            "sidebar_selected_text": tokens["SIDEBAR_SELECTED_TEXT"],
            "border": tokens["BORDER_NORMAL"],
            "accent_default": tokens["ACCENT"],
            "accent_blue": tokens["ACCENT_HOVER"],
            "accent_green": tokens["SUCCESS"],
            "accent_purple": tokens["GANTT_BASELINE"],
            "accent_red": tokens["DANGER"],
        }
    )
    return tokens


def semantic_tokens_for(
    is_dark: bool,
    accent_color: str,
    theme: Optional[str] = None,
) -> Dict[str, str]:
    resolved_theme = theme or getattr(AppearanceService, "_CURRENT_THEME", "dark")
    if resolved_theme == "system":
        resolved_theme = "dark" if is_dark else "light"
    elif resolved_theme in {"oled", "nord"} and not is_dark:
        resolved_theme = "light"
    elif resolved_theme == "warm_paper" and is_dark:
        resolved_theme = "dark"
    return _semantic_tokens(
        is_dark,
        _valid_color(accent_color, "#2563EB"),
        theme=resolved_theme,
    )


def qpalette_from_tokens(tokens: Dict[str, str]) -> QPalette:
    palette = QPalette()
    colors = {
        "window": QColor(tokens["APP_BACKGROUND"]),
        "surface": QColor(tokens["SURFACE_1"]),
        "surface_alt": QColor(tokens["SURFACE_2"]),
        "text": QColor(tokens["TEXT_PRIMARY"]),
        "muted": QColor(tokens["TEXT_MUTED"]),
        "disabled": QColor(tokens["TEXT_DISABLED"]),
        "accent": QColor(tokens["ACCENT"]),
        "on_accent": QColor(tokens["TEXT_ON_ACCENT"]),
    }

    palette.setColor(QPalette.Window, colors["window"])
    palette.setColor(QPalette.WindowText, colors["text"])
    palette.setColor(QPalette.Base, colors["surface"])
    palette.setColor(QPalette.AlternateBase, colors["surface_alt"])
    palette.setColor(QPalette.ToolTipBase, colors["surface_alt"])
    palette.setColor(QPalette.ToolTipText, colors["text"])
    palette.setColor(QPalette.Text, colors["text"])
    palette.setColor(QPalette.Button, colors["surface_alt"])
    palette.setColor(QPalette.ButtonText, colors["text"])
    palette.setColor(QPalette.Highlight, colors["accent"])
    palette.setColor(QPalette.HighlightedText, colors["on_accent"])
    palette.setColor(QPalette.Link, QColor(tokens["LINK"]))
    palette.setColor(QPalette.LinkVisited, QColor(tokens["LINK_HOVER"]))
    palette.setColor(QPalette.BrightText, QColor(tokens["TEXT_ON_DANGER"]))

    try:
        palette.setColor(QPalette.PlaceholderText, QColor(tokens["PLACEHOLDER_TEXT"]))
    except Exception:
        pass

    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        palette.setColor(QPalette.Disabled, role, colors["disabled"])

    try:
        palette.setColor(QPalette.Disabled, QPalette.PlaceholderText, colors["disabled"])
    except Exception:
        pass

    return palette


def _relative_luminance(color: QColor) -> float:
    def channel(value: int) -> float:
        normalized = value / 255.0
        if normalized <= 0.03928:
            return normalized / 12.92
        return ((normalized + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.red())
        + 0.7152 * channel(color.green())
        + 0.0722 * channel(color.blue())
    )


def contrast_ratio(foreground: str, background: str) -> float:
    fg = QColor(str(foreground or ""))
    bg = QColor(str(background or ""))
    if not fg.isValid() or not bg.isValid():
        return 1.0
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _semantic_text_role_for_widget(widget: QWidget) -> str:
    role = str(widget.property("todoBirdTextRole") or "").strip().upper()
    if role in TEXT_COLOR_ROLES:
        return role

    if str(widget.property("secondary") or "").lower() == "true":
        return "TEXT_SECONDARY"
    if str(widget.property("muted") or "").lower() == "true":
        return "TEXT_MUTED"
    if str(widget.property("heading") or "").lower() == "true":
        return "HEADING_PRIMARY"

    name = str(widget.objectName() or "").lower()
    if "subtitle" in name:
        return "TEXT_SECONDARY"
    if "header" in name or "title" in name or "heading" in name:
        return "HEADING_PRIMARY"

    try:
        delta = int(widget.property("_todo_bird_font_delta_pt") or 0)
    except (TypeError, ValueError):
        delta = 0
    if delta >= 4:
        return "HEADING_PRIMARY"

    try:
        if widget.font().bold() and delta >= 2:
            return "HEADING_PRIMARY"
    except Exception:
        pass

    return "TEXT_PRIMARY"


def _fixed_text_color_is_unreadable(color: QColor, is_dark: bool) -> bool:
    luminance = _relative_luminance(color)
    if is_dark:
        return luminance < 0.22
    return luminance > 0.82


def _sanitize_widget_text_stylesheet(widget: QWidget, appearance: AppearanceSettings) -> None:
    stylesheet = ""
    try:
        stylesheet = widget.styleSheet()
    except Exception:
        return
    if not stylesheet or "color" not in stylesheet.lower():
        return

    try:
        from PySide6.QtWidgets import (
            QLabel,
            QGroupBox,
            QCheckBox,
            QRadioButton,
            QLineEdit,
            QTextEdit,
            QPlainTextEdit,
        )
    except Exception:
        return

    text_widget_types = (
        QLabel,
        QGroupBox,
        QCheckBox,
        QRadioButton,
        QLineEdit,
        QTextEdit,
        QPlainTextEdit,
    )
    if not isinstance(widget, text_widget_types):
        return
    if bool(widget.property("todoBirdAllowFixedTextColor")):
        return

    role = _semantic_text_role_for_widget(widget)
    replacement = appearance.tokens.get(role, appearance.tokens["TEXT_PRIMARY"])

    def replace_color(match: re.Match) -> str:
        raw_value = match.group(1).strip()
        if raw_value.lower() in {"inherit", "initial", "unset"}:
            return f"color: {replacement}"

        raw_color = QColor(raw_value)
        if not raw_color.isValid():
            return match.group(0)

        # Fully transparent text is a deliberate custom-paint contract
        # (e.g. ModernCheckBox hides styled text and paints its own).
        # Luminance of rgba(0,0,0,0) would otherwise classify it as
        # unreadable and re-paint visible text over the custom glyph.
        if raw_color.alpha() == 0:
            return match.group(0)

        # Preserve special semantic/status colors. They are not body text and
        # communicate state, schedule, selection, or brand accent.
        normalized = raw_color.name().upper()
        semantic_values = {
            appearance.tokens["ACCENT"].upper(),
            appearance.tokens["SUCCESS"].upper(),
            appearance.tokens["WARNING"].upper(),
            appearance.tokens["DANGER"].upper(),
            appearance.tokens["INFO"].upper(),
        }
        if normalized in semantic_values:
            return match.group(0)

        if _fixed_text_color_is_unreadable(raw_color, appearance.is_dark):
            return f"color: {replacement}"
        return match.group(0)

    sanitized = _TEXT_COLOR_DECL_RE.sub(replace_color, stylesheet)
    if sanitized != stylesheet:
        widget.setStyleSheet(sanitized)


def _ensure_font_safe_control_geometry(widget: QWidget, appearance: AppearanceSettings) -> None:
    try:
        from PySide6.QtWidgets import (
            QAbstractButton,
            QCheckBox,
            QComboBox,
            QDateEdit,
            QLineEdit,
            QPlainTextEdit,
            QSpinBox,
            QTabBar,
            QTextEdit,
            QTimeEdit,
        )
    except Exception:
        return

    control_types = (
        QAbstractButton,
        QComboBox,
        QDateEdit,
        QLineEdit,
        QPlainTextEdit,
        QSpinBox,
        QTabBar,
        QTextEdit,
        QTimeEdit,
    )
    if not isinstance(widget, control_types):
        return

    try:
        metrics = appearance.density_metrics
        if isinstance(widget, QTabBar):
            vertical_padding = 8
        elif isinstance(widget, QCheckBox):
            # Checkboxes are not buttons: button padding inflates them far
            # beyond their text (the "checkbox dominating text" artifact),
            # and raising their max height breaks deliberately compact rows.
            vertical_padding = metrics["control_padding_v"]
        elif isinstance(widget, QAbstractButton):
            vertical_padding = metrics["button_padding_v"]
        else:
            vertical_padding = metrics["control_padding_v"]
        min_height = widget.fontMetrics().height() + (vertical_padding * 2) + 2
        if widget.minimumHeight() < min_height:
            widget.setMinimumHeight(min_height)
        if not isinstance(widget, QCheckBox):
            max_height = widget.maximumHeight()
            if 0 < max_height < min_height:
                widget.setMaximumHeight(min_height)
    except Exception:
        return


class AppearanceService:
    """Resolve and propagate effective global appearance settings."""

    _CURRENT_THEME: str = "dark"

    @staticmethod
    def read(settings_manager: Any, app: Optional[QApplication] = None) -> AppearanceSettings:
        app = app or QApplication.instance()

        theme = str(
            settings_manager.get("theme", "dark")
            if settings_manager is not None
            else "dark"
        ).lower().strip()
        if theme not in THEME_MODES:
            theme = "dark"

        if theme == "system":
            is_dark = is_system_dark(app)
        elif theme in {"dark", "oled", "nord"}:
            is_dark = True
        elif theme in {"light", "warm_paper"}:
            is_dark = False
        else:
            is_dark = True

        AppearanceService._CURRENT_THEME = theme

        raw_accent = (
            settings_manager.get("accent_color", "#2563EB")
            if settings_manager is not None
            else "#2563EB"
        )
        accent_color = _valid_color(raw_accent, "#2563EB")
        accent_scheme = str(
            (
                settings_manager.get("accent_scheme", "")
                or settings_manager.get("color_scheme", "")
            )
            if settings_manager is not None
            else ""
        ).lower().strip()
        if accent_scheme not in ACCENT_SCHEMES:
            accent_scheme = _accent_scheme_for_color(accent_color)

        if accent_scheme in ACCENT_SCHEMES:
            accent_color = _valid_color(ACCENT_SCHEMES[accent_scheme][1], accent_color)

        fallback_family = app.font().family() if app is not None else "Inter"
        font_family = str(
            settings_manager.get("ui_font_family", fallback_family)
            if settings_manager is not None
            else fallback_family
        ).strip() or fallback_family
        font_size = _coerce_int(
            settings_manager.get("ui_font_size", 10)
            if settings_manager is not None
            else 10,
            10,
            8,
            20,
        )
        font_weight = str(
            settings_manager.get("ui_font_weight", "normal")
            if settings_manager is not None
            else "normal"
        ).lower().strip()
        if font_weight not in {"normal", "medium", "semibold", "bold"}:
            font_weight = "normal"

        density = _resolve_density(settings_manager)
        button_style = str(
            settings_manager.get("button_design_mode", "3d_raised")
            if settings_manager is not None
            else "3d_raised"
        ).lower().strip()
        if button_style not in BUTTON_STYLE_VALUES:
            button_style = "3d_raised"

        return AppearanceSettings(
            theme=theme,
            is_dark=is_dark,
            accent_scheme=accent_scheme,
            accent_color=accent_color,
            font_family=font_family,
            font_size=font_size,
            font_weight=font_weight,
            density=density,
            button_style=button_style,
            tokens=_semantic_tokens(is_dark, accent_color, theme=theme),
        )

    @staticmethod
    def set_accent_scheme(settings_manager: Any, scheme_key: str) -> str:
        key = str(scheme_key or "").lower().strip()
        if key not in ACCENT_SCHEMES:
            key = "professional_blue"
        color = ACCENT_SCHEMES[key][1]
        if settings_manager is not None:
            settings_manager.set("accent_scheme", key)
            settings_manager.set("color_scheme", key)
            settings_manager.set("accent_color", color)
        return color

    @staticmethod
    def apply_to_application(app: QApplication, appearance: AppearanceSettings) -> None:
        if app is None:
            return

        try:
            from todo_bird_app.ui.components.modern_button import (
                ButtonStyleDesign,
                ModernButton,
            )

            try:
                ModernButton.set_global_design_mode(
                    ButtonStyleDesign(appearance.button_style)
                )
            except Exception:
                ModernButton.set_global_design_mode(ButtonStyleDesign.RAISED_3D)
            ModernButton.set_global_density(appearance.density)
        except Exception:
            pass

        try:
            from todo_bird_app.ui.components.modern_combobox import ModernComboBox

            ModernComboBox.set_global_density(appearance.density)
        except Exception:
            pass

        for widget in list(app.allWidgets()):
            AppearanceService._apply_to_single_widget(widget, appearance)

    @staticmethod
    def _apply_to_single_widget(widget: QWidget, appearance: AppearanceSettings) -> None:
        if widget is None:
            return

        try:
            palette = qpalette_from_tokens(appearance.tokens)
            text_role = _semantic_text_role_for_widget(widget)
            text_color = QColor(
                appearance.tokens.get(text_role, appearance.tokens["TEXT_PRIMARY"])
            )
            for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
                palette.setColor(role, text_color)
            widget.setPalette(palette)
        except Exception:
            pass

        for key, value in (
            ("todoBirdTheme", appearance.theme),
            ("todoBirdAccent", appearance.accent_color),
            ("todoBirdDensity", appearance.density),
            ("todoBirdButtonStyle", appearance.button_style),
        ):
            widget.setProperty(key, value)

        set_theme = getattr(widget, "set_theme", None)
        if callable(set_theme):
            try:
                set_theme(appearance.is_dark, appearance.accent_color)
            except TypeError:
                try:
                    set_theme(appearance.is_dark)
                except TypeError:
                    pass

        _sanitize_widget_text_stylesheet(widget, appearance)
        _ensure_font_safe_control_geometry(widget, appearance)

        try:
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        except Exception:
            pass

    @staticmethod
    def apply_to_widget(widget: QWidget, appearance: AppearanceSettings) -> None:
        if widget is None:
            return

        widgets = [widget]
        try:
            widgets.extend(widget.findChildren(QWidget))
        except Exception:
            pass

        for target in widgets:
            AppearanceService._apply_to_single_widget(target, appearance)

        try:
            widget.updateGeometry()
            widget.update()
        except Exception:
            pass

    @staticmethod
    def qss_tokens(appearance: AppearanceSettings) -> Dict[str, str]:
        metrics = appearance.density_metrics
        tokens = dict(appearance.tokens)
        tokens.update(
            {
                "button_padding_v": str(metrics["button_padding_v"]),
                "button_padding_h": str(metrics["button_padding_h"]),
                "control_padding_v": str(metrics["control_padding_v"]),
                "control_padding_h": str(metrics["control_padding_h"]),
                "toolbar_padding_v": str(metrics["toolbar_padding_v"]),
                "button_padding_vpx": f"{metrics['button_padding_v']}px",
                "button_padding_hpx": f"{metrics['button_padding_h']}px",
                "control_padding_vpx": f"{metrics['control_padding_v']}px",
                "control_padding_hpx": f"{metrics['control_padding_h']}px",
                "toolbar_padding_vpx": f"{metrics['toolbar_padding_v']}px",
            }
        )
        icons_dir = Path(__file__).resolve().parent.parent / "assets" / "icons"
        on_accent = str(tokens.get("TEXT_ON_ACCENT", "#FFFFFF")).upper()
        tick_variant = "dark" if on_accent == "#111827" else "white"
        tokens.update(
            {
                # QSS url() treats backslashes as escape sequences and drops
                # the rule with "Could not parse application stylesheet" —
                # always hand Qt POSIX-style paths (valid on Windows too).
                "CHECKMARK_IMAGE": (icons_dir / f"cb_check_{tick_variant}.svg").as_posix(),
                "INDETERMINATE_IMAGE": (icons_dir / f"cb_dash_{tick_variant}.svg").as_posix(),
            }
        )
        return tokens

    @staticmethod
    def known_accent_items() -> Iterable[tuple[str, str]]:
        for key, (label, color) in ACCENT_SCHEMES.items():
            yield key, f"{label} ({color})"

    @staticmethod
    def known_theme_items() -> Iterable[tuple[str, str]]:
        return list(THEME_ITEMS)

    @staticmethod
    def known_text_color_roles() -> Iterable[str]:
        return tuple(sorted(TEXT_COLOR_ROLES))

    @staticmethod
    def text_color_for_role(appearance: AppearanceSettings, role: str) -> str:
        key = str(role or "TEXT_PRIMARY").strip().upper()
        return appearance.tokens.get(key, appearance.tokens["TEXT_PRIMARY"])
