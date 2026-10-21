"""
TODO BIRD — MODERN CHECKBOX COMPONENT
Provides a compact, modern rounded-square checkbox with crisp vector checkmarks,
indeterminate dash support, focus rings, hover transitions, and keyboard accessibility.
"""

from typing import Optional
from PySide6.QtCore import Qt, QRectF, QSize, Signal
from PySide6.QtWidgets import QCheckBox, QWidget
from PySide6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QFont,
    QKeyEvent,
    QMouseEvent,
)

from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.services.icon_service import IconService
from todo_bird_app.services.appearance_service import semantic_tokens_for


class ModernCheckBox(QCheckBox):
    """
    Modern custom-painted vector checkbox.
    Supports unchecked, checked, and partially checked (indeterminate) states.
    """

    def __init__(
        self,
        text: str = "",
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
    ):
        super().__init__(text, parent)
        self._is_dark = is_dark
        self._accent_color = accent_color
        self._is_hovered = False
        self._is_focused = False

        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setStyleSheet("QCheckBox { spacing: 8px; color: transparent; }")

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self.text()) if self.text() else 0
        box_size = max(18.0, round(fm.height() * 0.90))
        total_w = int(box_size + (8 + text_w if self.text() else 0) + 4)
        total_h = max(24, int(fm.height() + 6))
        return QSize(total_w, total_h)

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self._is_focused = True
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._is_focused = False
        self.update()
        super().focusOutEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        fm = self.fontMetrics()
        box_size = max(18.0, round(fm.height() * 0.90))
        box_y = (self.height() - box_size) / 2.0
        box_rect = QRectF(1.0, box_y, box_size, box_size)
        radius = max(4.0, round(box_size * 0.26))

        is_checked = self.isChecked()
        is_partially_checked = (self.checkState() == Qt.PartiallyChecked)
        is_disabled = not self.isEnabled()
        accent = QColor(self._accent_color)

        tokens = semantic_tokens_for(self._is_dark, self._accent_color)

        # 1. Colors Computation
        if is_disabled:
            bg_col = QColor(tokens["SURFACE_2"])
            border_col = QColor(tokens["BORDER_SUBTLE"])
            icon_col = QColor(tokens["TEXT_DISABLED"])
            text_col = QColor(tokens["TEXT_DISABLED"])
        elif is_checked or is_partially_checked:
            bg_col = accent.lighter(110) if self._is_hovered else accent
            border_col = bg_col
            icon_col = QColor(tokens["TEXT_ON_ACCENT"])
            text_col = QColor(tokens["TEXT_PRIMARY"])
        else:
            # Unchecked resting state - high contrast & clear box outline
            bg_col = QColor(tokens["SURFACE_1"])
            border_col = accent if self._is_hovered else QColor(tokens["BORDER_STRONG"])
            icon_col = QColor(0, 0, 0, 0)
            text_col = QColor(tokens["TEXT_PRIMARY"])

        # 2. Draw Checkbox Box
        path = QPainterPath()
        path.addRoundedRect(box_rect, radius, radius)
        painter.fillPath(path, QBrush(bg_col))
        painter.strokePath(path, QPen(border_col, 1.6))

        # 3. Focus Ring
        if self._is_focused and not is_disabled:
            focus_path = QPainterPath()
            focus_path.addRoundedRect(box_rect.adjusted(-2, -2, 2, 2), radius + 2, radius + 2)
            painter.strokePath(focus_path, QPen(accent, 1.8))

        # 4. Checkmark or Indeterminate Dash
        if is_checked and not is_partially_checked:
            stroke_w = max(2.2, round(box_size * 0.12))
            IconService.render_vector_icon(painter, "checkmark", box_rect, icon_col, stroke_width=stroke_w)
        elif is_partially_checked:
            stroke_w = max(2.4, round(box_size * 0.14))
            IconService.render_vector_icon(painter, "dash", box_rect, icon_col, stroke_width=stroke_w)

        # 5. Text Label
        if self.text():
            painter.setFont(self.font())
            painter.setPen(text_col)
            text_rect = QRectF(box_size + 8, 0, self.width() - box_size - 8, self.height())
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())

        painter.end()
