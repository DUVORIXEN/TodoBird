"""
TODO BIRD — MODERN SECTION CARD COMPONENT
Provides a clean container card with subtle glass borders, optional collapsible header, and header action slots.
"""

from typing import Optional
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtGui import QPainter, QPainterPath, QColor, QPen, QBrush

from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.ui.components.modern_chevron import ModernChevron


class SectionCard(QWidget):
    """
    Modern container card for grouping form sections or settings categories.
    """

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        collapsible: bool = False,
        initially_expanded: bool = True,
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
    ):
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self._collapsible = collapsible
        self._is_dark = is_dark
        self._accent_color = accent_color

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(16, 14, 16, 16)
        self._main_layout.setSpacing(12)

        # Header Row
        self._header_layout = QHBoxLayout()
        self._header_layout.setContentsMargins(0, 0, 0, 0)
        self._header_layout.setSpacing(8)

        if collapsible:
            self._chevron = ModernChevron(expanded=initially_expanded, is_dark=is_dark, accent_color=accent_color)
            self._chevron.toggledState.connect(self._on_chevron_toggled)
            self._header_layout.addWidget(self._chevron)

        # Titles VBox
        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(2)
        self._title_label = QLabel(title)
        self._title_label.setStyleSheet("font-weight: 600; font-size: 14px; color: #CDD6F4;")
        title_vbox.addWidget(self._title_label)

        if subtitle:
            self._subtitle_label = QLabel(subtitle)
            self._subtitle_label.setStyleSheet("font-size: 12px; color: #A6ADC8;")
            title_vbox.addWidget(self._subtitle_label)

        self._header_layout.addLayout(title_vbox)
        self._header_layout.addStretch()
        self._main_layout.addLayout(self._header_layout)

        # Content Container
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(8)
        self._main_layout.addWidget(self._content_widget)

        if collapsible and not initially_expanded:
            self._content_widget.setVisible(False)

        self._update_styles()

    def get_content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def add_header_widget(self, widget: QWidget):
        self._header_layout.addWidget(widget)

    def _on_chevron_toggled(self, is_expanded: bool):
        self._content_widget.setVisible(is_expanded)

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color
        if self._collapsible and hasattr(self, "_chevron"):
            self._chevron.set_theme(is_dark, accent_color)
        self._update_styles()
        self.update()

    def _update_styles(self):
        title_col = "#CDD6F4" if self._is_dark else "#1E293B"
        sub_col = "#A6ADC8" if self._is_dark else "#64748B"
        self._title_label.setStyleSheet(f"font-weight: 600; font-size: 14px; color: {title_col};")
        if hasattr(self, "_subtitle_label"):
            self._subtitle_label.setStyleSheet(f"font-size: 12px; color: {sub_col};")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 10.0

        bg = QColor("#1E1E2E") if self._is_dark else QColor("#FFFFFF")
        border = QColor("#313244") if self._is_dark else QColor("#E2E8F0")

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, QBrush(bg))
        painter.strokePath(path, QPen(border, 1.0))

        painter.end()
