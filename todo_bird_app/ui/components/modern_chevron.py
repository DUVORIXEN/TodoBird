"""
TODO BIRD — MODERN CHEVRON & ARROW COMPONENT
Provides a crisp, theme-aware vector chevron for tree expand/collapse and dropdowns.
Features an interactive hit target of 28px for a 14px visible chevron,
smooth 90° rotation animation, high-DPI crispness, and keyboard accessibility.
"""

from typing import Optional
from PySide6.QtCore import Qt, QRectF, QSize, Signal, Property, QVariantAnimation, QEasingCurve
from PySide6.QtWidgets import QAbstractButton, QWidget, QSizePolicy
from PySide6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QMouseEvent,
    QKeyEvent,
)

from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.services.icon_service import IconService


class ModernChevron(QAbstractButton):
    """
    Modern Expand / Collapse Vector Chevron Button.
    Collapsed: Angle 0° (pointing right ▶)
    Expanded: Angle 90° (pointing down ▼)
    Hit Region: 28px square; Visible chevron: 12-14px.
    """

    toggledState = Signal(bool)  # Emits True when expanded, False when collapsed

    def __init__(
        self,
        expanded: bool = False,
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
        animate: bool = True,
    ):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(expanded)
        self._is_dark = is_dark
        self._accent_color = accent_color
        self._animate = animate
        self._rotation_angle = 90.0 if expanded else 0.0
        self._is_hovered = False
        self._is_focused = False

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(140)  # ~120-180ms
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_step)

        self.setFixedSize(28, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.toggled.connect(self._on_toggled)

    # -------------------------------------------------------------------------
    # Rotation Property for Animation
    # -------------------------------------------------------------------------

    def get_rotation(self) -> float:
        return self._rotation_angle

    def set_rotation(self, val: float):
        self._rotation_angle = val
        self.update()

    rotationAngle = Property(float, get_rotation, set_rotation)

    def _on_anim_step(self, val):
        self.set_rotation(float(val))

    def _on_toggled(self, is_checked: bool):
        target_angle = 90.0 if is_checked else 0.0
        if self._animate and self.isVisible():
            self._anim.stop()
            self._anim.setStartValue(self._rotation_angle)
            self._anim.setEndValue(target_angle)
            self._anim.start()
        else:
            self.set_rotation(target_angle)
        self.toggledState.emit(is_checked)

    def set_expanded(self, expanded: bool, animate: bool = True):
        self._animate = animate
        self.setChecked(expanded)

    def is_expanded(self) -> bool:
        return self.isChecked()

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color
        self.update()

    # -------------------------------------------------------------------------
    # Events
    # -------------------------------------------------------------------------

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

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.toggle()
            event.accept()
            return
        elif event.key() == Qt.Key_Right and not self.isChecked():
            self.setChecked(True)
            event.accept()
            return
        elif event.key() == Qt.Key_Left and self.isChecked():
            self.setChecked(False)
            event.accept()
            return
        super().keyPressEvent(event)

    # -------------------------------------------------------------------------
    # Paint Engine
    # -------------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h / 2.0

        # Hover circular highlight background
        if self._is_hovered and self.isEnabled():
            bg_highlight = QColor(255, 255, 255, 20) if self._is_dark else QColor(0, 0, 0, 16)
            painter.setBrush(QBrush(bg_highlight))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), 6, 6)

        # Focus ring
        if self._is_focused and self.isEnabled():
            focus_pen = QPen(QColor(self._accent_color), 1.5)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(focus_pen)
            painter.drawRoundedRect(QRectF(2, 2, w - 4, h - 4), 6, 6)

        # Icon stroke color
        if not self.isEnabled():
            col = QColor("#6C7086") if self._is_dark else QColor("#94A3B8")
        elif self._is_hovered or self.isChecked():
            col = QColor(self._accent_color) if self.isChecked() else (QColor("#CDD6F4") if self._is_dark else QColor("#1E293B"))
        else:
            col = QColor("#A6ADC8") if self._is_dark else QColor("#64748B")

        # Save coordinate space and rotate around center
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self._rotation_angle)

        # Draw centered right-pointing chevron: (x1, y1) -> (x2, y2) -> (x3, y3)
        icon_span = 5.0
        path = QPainterPath()
        path.moveTo(-icon_span * 0.5, -icon_span)
        path.lineTo(icon_span * 0.6, 0.0)
        path.lineTo(-icon_span * 0.5, icon_span)

        pen = QPen(col, 1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        painter.restore()
        painter.end()
