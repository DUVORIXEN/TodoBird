"""
TODO BIRD — MODERN CONTEXT MENU SYSTEM
Provides a premium, theme-aware context menu with generous padding,
shortcut pill hints, vector icons, subtle dividers, and disabled state styling.
"""

from typing import Optional, Callable
from PySide6.QtCore import Qt, QRectF, QSize, Signal
from PySide6.QtWidgets import QMenu, QWidget
from PySide6.QtGui import QIcon, QKeySequence, QAction
from PySide6.QtGui import QColor

from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.services.icon_service import IconService


class ModernMenu(QMenu):
    """
    Modern styled popup and context menu.
    Replaces default OS menus with clean rounded borders and theme-aware surface colors.
    """

    def __init__(
        self,
        title: str = "",
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
    ):
        super().__init__(title, parent)
        self._is_dark = is_dark
        self._accent_color = accent_color
        self._apply_theme()

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color
        self._apply_theme()

    def add_action_item(
        self,
        text: str,
        callback: Optional[Callable] = None,
        icon_name: Optional[str] = None,
        shortcut: Optional[str] = None,
        enabled: bool = True,
    ) -> QAction:
        """Helper to create a consistently styled action."""
        action = QAction(text, self)
        if icon_name:
            icon_col = "#CDD6F4" if self._is_dark else "#1E293B"
            action.setIcon(IconService.get_icon(icon_name, icon_col))
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.setEnabled(enabled)
        if callback:
            action.triggered.connect(callback)
        self.addAction(action)
        return action

    def _apply_theme(self):
        bg = "#1E1E2E" if self._is_dark else "#FFFFFF"
        border = "#3D3F56" if self._is_dark else "#CBD5E1"
        text = "#CDD6F4" if self._is_dark else "#1E293B"
        text_disabled = "#6C7086" if self._is_dark else "#94A3B8"
        accent = self._accent_color
        hover_bg = accent if self._is_dark else f"rgba({QColor(accent).red()}, {QColor(accent).green()}, {QColor(accent).blue()}, 0.15)"
        hover_fg = "#FFFFFF" if self._is_dark else accent

        self.setStyleSheet(f"""
            QMenu {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 4px;
                color: {text};
                font-size: 13px;
            }}
            QMenu::item {{
                background-color: transparent;
                padding: 6px 24px 6px 12px;
                border-radius: 6px;
                margin: 1px 2px;
            }}
            QMenu::item:selected {{
                background-color: {hover_bg};
                color: {hover_fg};
            }}
            QMenu::item:disabled {{
                color: {text_disabled};
                background-color: transparent;
            }}
            QMenu::separator {{
                height: 1px;
                background: {border};
                margin: 4px 6px;
            }}
            QMenu::icon {{
                padding-left: 4px;
            }}
        """)
