"""
TODO BIRD — MODERN EMPTY STATE COMPONENT
Provides a welcoming, high-polish empty state placeholder with vector icons,
explanatory text, and a primary call-to-action button.
"""

from typing import Optional, Callable
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtGui import QPainter, QPainterPath, QColor

from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.ui.components.modern_button import ModernButton, ButtonVariant, ButtonSize
from todo_bird_app.services.icon_service import IconService


class EmptyState(QWidget):
    """
    Polished visual placeholder for empty lists, search results, or projects.
    """

    def __init__(
        self,
        icon_name: str = "task",
        title: str = "No tasks found",
        description: str = "Create your first task or adjust your active filters.",
        action_label: Optional[str] = None,
        action_callback: Optional[Callable] = None,
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
    ):
        super().__init__(parent)
        self._icon_name = icon_name
        self._title = title
        self._description = description
        self._is_dark = is_dark
        self._accent_color = accent_color

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)
        layout.setContentsMargins(32, 48, 32, 48)

        # Icon Container Widget
        self._icon_widget = _EmptyStateIconWidget(icon_name, is_dark, accent_color)
        layout.addWidget(self._icon_widget, 0, Qt.AlignCenter)

        # Title Label
        self._title_label = QLabel(title)
        self._title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title_label)

        # Description Label
        self._desc_label = QLabel(description)
        self._desc_label.setAlignment(Qt.AlignCenter)
        self._desc_label.setWordWrap(True)
        self._desc_label.setMaximumWidth(360)
        layout.addWidget(self._desc_label)

        # Action Button if provided
        if action_label and action_callback:
            self._action_btn = ModernButton(
                text=action_label,
                variant=ButtonVariant.PRIMARY,
                size=ButtonSize.STANDARD,
                icon_name="add",
                is_dark=is_dark,
                accent_color=accent_color,
            )
            self._action_btn.clicked.connect(action_callback)
            layout.addWidget(self._action_btn, 0, Qt.AlignCenter)

        self._update_styles()

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color
        self._icon_widget.set_theme(is_dark, accent_color)
        if hasattr(self, "_action_btn"):
            self._action_btn.set_theme(is_dark, accent_color)
        self._update_styles()

    def _update_styles(self):
        title_col = "#CDD6F4" if self._is_dark else "#1E293B"
        desc_col = "#A6ADC8" if self._is_dark else "#64748B"
        self._title_label.setStyleSheet(f"font-weight: 600; font-size: 16px; color: {title_col};")
        self._desc_label.setStyleSheet(f"font-size: 13px; color: {desc_col};")


class _EmptyStateIconWidget(QWidget):
    """Circular backdrop container with vector icon."""

    def __init__(self, icon_name: str, is_dark: bool, accent_color: str):
        super().__init__()
        self._icon_name = icon_name
        self._is_dark = is_dark
        self._accent_color = accent_color
        self.setFixedSize(56, 56)

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(self.rect())
        accent = QColor(self._accent_color)
        bg = QColor(accent.red(), accent.green(), accent.blue(), 35 if self._is_dark else 20)

        # Circular backdrop
        painter.setBrush(bg)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(rect)

        # Centered Icon
        icon_box = QRectF(16, 16, 24, 24)
        IconService.render_vector_icon(painter, self._icon_name, icon_box, accent, stroke_width=2.0)

        painter.end()
