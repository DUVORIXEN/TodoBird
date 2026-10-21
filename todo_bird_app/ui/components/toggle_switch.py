"""
TODO BIRD — MODERN TOGGLE SWITCH COMPONENT
Provides an elegant, modern pill toggle switch for binary preferences (e.g. Show WBS, Auto-expand).
Features smooth sliding animation, tactile feedback, focus rings, and keyboard accessibility.
"""

from typing import Optional
from PySide6.QtCore import Qt, QRectF, QSize, Signal, Property, QVariantAnimation, QEasingCurve
from PySide6.QtWidgets import QAbstractButton, QWidget
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
from todo_bird_app.services.appearance_service import semantic_tokens_for, text_color_on


class ToggleSwitch(QAbstractButton):
    """
    Modern iOS / Linear-style sliding Toggle Switch.
    Dimensions: 40px width × 22px height.
    """

    toggledState = Signal(bool)

    def __init__(
        self,
        text: str = "",
        checked: bool = False,
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
        animate: bool = True,
    ):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.setChecked(checked)
        self._is_dark = is_dark
        self._accent_color = accent_color
        self._animate = animate
        self._thumb_pos = 1.0 if checked else 0.0
        self._is_hovered = False
        self._is_focused = False

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_step)

        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.toggled.connect(self._on_toggled)

    # -------------------------------------------------------------------------
    # Animation Property
    # -------------------------------------------------------------------------

    def get_thumb_pos(self) -> float:
        return self._thumb_pos

    def set_thumb_pos(self, val: float):
        self._thumb_pos = val
        self.update()

    thumbPosition = Property(float, get_thumb_pos, set_thumb_pos)

    def _on_anim_step(self, val):
        self.set_thumb_pos(float(val))

    def _on_toggled(self, is_checked: bool):
        target = 1.0 if is_checked else 0.0
        if self._animate and self.isVisible():
            self._anim.stop()
            self._anim.setStartValue(self._thumb_pos)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.set_thumb_pos(target)
        self.toggledState.emit(is_checked)

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self.text()) if self.text() else 0
        total_w = 42 + (8 + text_w if self.text() else 0)
        return QSize(total_w, 26)

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
        super().keyPressEvent(event)

    # -------------------------------------------------------------------------
    # Paint Engine
    # -------------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        track_w = 38.0
        track_h = 22.0
        track_y = (self.height() - track_h) / 2.0
        track_rect = QRectF(1.0, track_y, track_w, track_h)
        radius = track_h / 2.0

        is_disabled = not self.isEnabled()
        accent = QColor(self._accent_color)
        tokens = semantic_tokens_for(self._is_dark, self._accent_color)

        # Track Color Interpolation
        if is_disabled:
            track_bg = QColor(tokens["SURFACE_2"])
            thumb_col = QColor(tokens["TEXT_DISABLED"])
            text_col = QColor(tokens["TEXT_DISABLED"])
        else:
            off_bg = QColor(tokens["BORDER_NORMAL"])
            on_bg = accent.lighter(108) if self._is_hovered else accent

            r = int(off_bg.red() + (on_bg.red() - off_bg.red()) * self._thumb_pos)
            g = int(off_bg.green() + (on_bg.green() - off_bg.green()) * self._thumb_pos)
            b = int(off_bg.blue() + (on_bg.blue() - off_bg.blue()) * self._thumb_pos)
            track_bg = QColor(r, g, b)
            # The knob must contrast with the TRACK it currently sits on, not
            # with the accent: a dark-navy knob on the dark OFF track was
            # nearly invisible in dark mode.
            off_thumb = text_color_on(tokens["BORDER_NORMAL"])
            on_thumb = tokens["TEXT_ON_ACCENT"]
            thumb_col = QColor(off_thumb if self._thumb_pos < 0.5 else on_thumb)
            text_col = QColor(tokens["TEXT_PRIMARY"])

        # 1. Draw Track
        track_path = QPainterPath()
        track_path.addRoundedRect(track_rect, radius, radius)
        painter.fillPath(track_path, QBrush(track_bg))

        # Resting-state track outline (fades as thumb slides toward ON)
        if not is_disabled:
            outline_alpha = int(max(0, 200 * (1.0 - self._thumb_pos)))
            if outline_alpha > 0:
                outline_col = QColor(tokens["BORDER_STRONG"])
                outline_col.setAlpha(outline_alpha)
                painter.strokePath(track_path, QPen(outline_col, 1.6))

        # 2. Focus Ring
        if self._is_focused and not is_disabled:
            focus_path = QPainterPath()
            focus_path.addRoundedRect(track_rect.adjusted(-2, -2, 2, 2), radius + 2, radius + 2)
            painter.strokePath(focus_path, QPen(accent, 1.8))

        # 3. Draw Sliding Thumb
        thumb_size = 18.0
        thumb_margin = 2.0
        start_x = track_rect.x() + thumb_margin
        end_x = track_rect.right() - thumb_size - thumb_margin
        current_x = start_x + (end_x - start_x) * self._thumb_pos
        thumb_y = track_rect.y() + thumb_margin
        thumb_rect = QRectF(current_x, thumb_y, thumb_size, thumb_size)

        # Thumb drop shadow
        if not is_disabled:
            shadow_rect = thumb_rect.adjusted(0, 1, 0, 1)
            painter.setBrush(QBrush(QColor(0, 0, 0, 50)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(shadow_rect)

        # Thumb circle
        painter.setBrush(QBrush(thumb_col))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(thumb_rect)

        # 4. Text Label
        if self.text():
            painter.setFont(self.font())
            painter.setPen(text_col)
            text_rect = QRectF(track_w + 8, 0, self.width() - track_w - 8, self.height())
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())

        painter.end()
