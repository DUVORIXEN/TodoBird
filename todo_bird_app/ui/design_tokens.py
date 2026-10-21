"""
TODO BIRD — Centralized Design Tokens (Batch 3.5)
Establishes the modern, premium visual design system for Todo Bird:
- Consistent spacing scales
- Harmonious corner radii
- Adaptive elevation & shadows
- Elegant typography hierarchy
- Semantic color palette (Light & Dark mode aware)
- Motion timing constants
"""
from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class DesignTokens:
    # -------------------------------------------------------------------------
    # Spacing Scale (in pixels: 4, 8, 12, 16, 20, 24, 32, 40)
    # -------------------------------------------------------------------------
    SPACING_XS: int = 4
    SPACING_SM: int = 8
    SPACING_MD: int = 12
    SPACING_LG: int = 16
    SPACING_XL: int = 20
    SPACING_2XL: int = 24
    SPACING_3XL: int = 32
    SPACING_4XL: int = 40

    # -------------------------------------------------------------------------
    # Corner Radii (in pixels)
    # -------------------------------------------------------------------------
    RADIUS_SM: int = 6
    RADIUS_MD: int = 10
    RADIUS_LG: int = 14
    RADIUS_XL: int = 20
    RADIUS_FULL: int = 9999

    # -------------------------------------------------------------------------
    # Typography Scale (in points / px)
    # -------------------------------------------------------------------------
    FONT_SIZE_CAPTION: int = 11
    FONT_SIZE_BODY: int = 13
    FONT_SIZE_SUBTITLE: int = 15
    FONT_SIZE_TITLE: int = 18
    FONT_SIZE_HERO: int = 24
    FONT_SIZE_DISPLAY: int = 32

    FONT_WEIGHT_NORMAL: str = "400"
    FONT_WEIGHT_MEDIUM: str = "500"
    FONT_WEIGHT_SEMIBOLD: str = "600"
    FONT_WEIGHT_BOLD: str = "700"


    # -------------------------------------------------------------------------
    # Elevation & Shadows
    # -------------------------------------------------------------------------
    SHADOW_SM: str = "0 1px 3px rgba(0, 0, 0, 0.08)"
    SHADOW_MD: str = "0 4px 12px rgba(0, 0, 0, 0.12)"
    SHADOW_LG: str = "0 8px 24px rgba(0, 0, 0, 0.16)"

    # -------------------------------------------------------------------------
    # Animation Durations (in milliseconds)
    # -------------------------------------------------------------------------
    ANIMATION_FAST: int = 120
    ANIMATION_NORMAL: int = 180
    ANIMATION_SLOW: int = 240

    # -------------------------------------------------------------------------
    # Core Semantic Colors
    # -------------------------------------------------------------------------
    COLOR_ACCENT: str = "#3584E4"
    COLOR_ACCENT_HOVER: str = "#1D72D6"
    COLOR_ACCENT_LIGHT: str = "#EBF4FF"
    COLOR_ACCENT_DARK: str = "#183863"

    COLOR_SUCCESS: str = "#047857"
    COLOR_SUCCESS_BG: str = "#ECFDF5"
    COLOR_SUCCESS_TEXT: str = "#065F46"

    COLOR_WARNING: str = "#F59E0B"
    COLOR_WARNING_BG: str = "#FFFBEB"
    COLOR_WARNING_TEXT: str = "#92400E"

    COLOR_DANGER: str = "#DC2626"
    COLOR_DANGER_BG: str = "#FEF2F2"
    COLOR_DANGER_TEXT: str = "#991B1B"

    # Dark Mode Surfaces & Borders
    DARK_SURFACE: str = "#1E1E2E"
    DARK_SURFACE_ALT: str = "#252538"
    DARK_PANEL: str = "#181825"
    DARK_BORDER: str = "#313244"
    DARK_BORDER_SUBTLE: str = "#2A2B3D"
    DARK_TEXT_PRIMARY: str = "#CDD6F4"
    DARK_TEXT_SECONDARY: str = "#A6ADC8"
    DARK_TEXT_MUTED: str = "#8792A6"
    DARK_HEADING_PRIMARY: str = "#FFFFFF"
    DARK_HEADING_SECONDARY: str = "#DCE4F2"
    DARK_PLACEHOLDER_TEXT: str = "#8792A6"
    DARK_TABLE_HEADER_TEXT: str = "#F4F7FB"

    # Light Mode Surfaces & Borders
    LIGHT_SURFACE: str = "#FFFFFF"
    LIGHT_SURFACE_ALT: str = "#F8FAFC"
    LIGHT_PANEL: str = "#F1F5F9"
    LIGHT_BORDER: str = "#E2E8F0"
    LIGHT_BORDER_SUBTLE: str = "#EDF2F7"
    LIGHT_TEXT_PRIMARY: str = "#0F172A"
    LIGHT_TEXT_SECONDARY: str = "#475569"
    LIGHT_TEXT_MUTED: str = "#64748B"
    LIGHT_HEADING_PRIMARY: str = "#0F172A"
    LIGHT_HEADING_SECONDARY: str = "#334155"
    LIGHT_PLACEHOLDER_TEXT: str = "#64748B"
    LIGHT_TABLE_HEADER_TEXT: str = "#0F172A"

    # WBS Layered Semantic Surfaces (Dark)
    WBS_DARK_BG_BASE: str = "#14141E"
    WBS_DARK_PANEL: str = "#1C1D2C"
    WBS_DARK_TOOLBAR: str = "#1E1F30"
    WBS_DARK_HEADER: str = "#181926"
    WBS_DARK_ROW_NORMAL: str = "transparent"
    WBS_DARK_ROW_SUMMARY_ALPHA: int = 12  # rgba(255, 255, 255, 12)
    WBS_DARK_ROW_HOVER_ALPHA: int = 16    # rgba(255, 255, 255, 16)
    WBS_DARK_ROW_SELECTED_ALPHA: int = 45 # rgba(accent, 45)
    WBS_DARK_BORDER: str = "#2E3045"
    WBS_DARK_GUIDE_ALPHA: int = 22        # rgba(255, 255, 255, 22)

    # WBS Layered Semantic Surfaces (Light)
    WBS_LIGHT_BG_BASE: str = "#F1F5F9"
    WBS_LIGHT_PANEL: str = "#FFFFFF"
    WBS_LIGHT_TOOLBAR: str = "#FFFFFF"
    WBS_LIGHT_HEADER: str = "#F8FAFC"
    WBS_LIGHT_ROW_NORMAL: str = "transparent"
    WBS_LIGHT_ROW_SUMMARY_ALPHA: int = 10 # rgba(0, 0, 0, 10)
    WBS_LIGHT_ROW_HOVER_ALPHA: int = 12   # rgba(0, 0, 0, 12)
    WBS_LIGHT_ROW_SELECTED_ALPHA: int = 25# rgba(accent, 25)
    WBS_LIGHT_BORDER: str = "#E2E8F0"
    WBS_LIGHT_GUIDE_ALPHA: int = 24       # rgba(0, 0, 0, 24)

    @classmethod
    def get_card_stylesheet(cls, is_dark: bool = False, elevated: bool = True) -> str:
        """Returns modern, soft-surface rounded card stylesheet."""
        if is_dark:
            bg = cls.DARK_SURFACE if elevated else cls.DARK_PANEL
            border = cls.DARK_BORDER
            text = cls.DARK_TEXT_PRIMARY
        else:
            bg = cls.LIGHT_SURFACE if elevated else cls.LIGHT_PANEL
            border = cls.LIGHT_BORDER
            text = cls.LIGHT_TEXT_PRIMARY

        return f"""
            QFrame#CardWidget, QWidget#CardWidget {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: {cls.RADIUS_MD}px;
                color: {text};
            }}
        """

    @classmethod
    def get_badge_stylesheet(cls, variant: str = "default", is_dark: bool = False) -> str:
        """Returns modern chip / badge stylesheet with accessible contrast."""
        if variant == "success":
            bg = "#064E3B" if is_dark else cls.COLOR_SUCCESS_BG
            text = "#6EE7B7" if is_dark else cls.COLOR_SUCCESS_TEXT
            border = "#059669" if is_dark else "#A7F3D0"
        elif variant == "warning":
            bg = "#78350F" if is_dark else cls.COLOR_WARNING_BG
            text = "#FCD34D" if is_dark else cls.COLOR_WARNING_TEXT
            border = "#D97706" if is_dark else "#FDE68A"
        elif variant == "danger":
            bg = "#7F1D1D" if is_dark else cls.COLOR_DANGER_BG
            text = "#FCA5A5" if is_dark else cls.COLOR_DANGER_TEXT
            border = "#DC2626" if is_dark else "#FECACA"
        elif variant == "accent":
            bg = cls.DARK_SURFACE_ALT if is_dark else cls.COLOR_ACCENT_LIGHT
            text = "#93C5FD" if is_dark else "#1E40AF"
            border = "#3B82F6" if is_dark else "#BFDBFE"
        else:
            bg = cls.DARK_SURFACE_ALT if is_dark else cls.LIGHT_SURFACE_ALT
            text = cls.DARK_TEXT_SECONDARY if is_dark else cls.LIGHT_TEXT_SECONDARY
            border = cls.DARK_BORDER if is_dark else cls.LIGHT_BORDER

        return f"""
            QLabel {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: {cls.RADIUS_SM}px;
                padding: 3px 8px;
                font-size: {cls.FONT_SIZE_CAPTION}pt;
                font-weight: 600;
            }}
        """

    @classmethod
    def get_primary_button_stylesheet(cls, accent_color: str = None) -> str:
        """Returns a premium, modern primary button stylesheet."""
        accent = accent_color or cls.COLOR_ACCENT
        return f"""
            QPushButton {{
                background-color: {accent};
                color: #FFFFFF;
                border: none;
                border-radius: {cls.RADIUS_SM}px;
                padding: 8px 16px;
                font-weight: 600;
                font-size: {cls.FONT_SIZE_BODY}pt;
            }}
            QPushButton:hover {{
                background-color: {cls.COLOR_ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {cls.COLOR_ACCENT_DARK};
            }}
            QPushButton:disabled {{
                background-color: #64748B;
                color: #94A3B8;
            }}
        """

    @classmethod
    def get_secondary_button_stylesheet(cls, is_dark: bool = False) -> str:
        """Returns a modern secondary button stylesheet."""
        bg = cls.DARK_SURFACE_ALT if is_dark else cls.LIGHT_SURFACE
        border = cls.DARK_BORDER if is_dark else cls.LIGHT_BORDER
        text = cls.DARK_TEXT_PRIMARY if is_dark else cls.LIGHT_TEXT_PRIMARY
        hover_bg = cls.DARK_BORDER if is_dark else cls.LIGHT_PANEL

        return f"""
            QPushButton {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: {cls.RADIUS_SM}px;
                padding: 8px 16px;
                font-weight: 500;
                font-size: {cls.FONT_SIZE_BODY}pt;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
            }}
            QPushButton:pressed {{
                background-color: {border};
            }}
        """
