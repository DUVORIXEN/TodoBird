"""
TODO BIRD — MODERN TOAST NOTIFICATION SYSTEM
Provides non-blocking, elegant toast notifications for user actions (Task moved, View saved, etc.).
Supports success, warning, error, and info types, optional action buttons, and auto-dismissal.
"""

from typing import Optional, Callable
from PySide6.QtCore import Qt, QRectF, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QPushButton, QGraphicsOpacityEffect
from PySide6.QtGui import QPainter, QPainterPath, QColor, QBrush, QPen, QFont

from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.services.icon_service import IconService


class Toast(QWidget):
    """
    Individual floating toast notification with entrance animation and vector icons.
    """

    def __init__(
        self,
        message: str,
        status: str = "success",  # "success" | "warning" | "error" | "info"
        duration_ms: int = 3500,
        action_label: Optional[str] = None,
        action_callback: Optional[Callable] = None,
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
    ):
        super().__init__(parent)
        self._message = message
        self._status = status
        self._is_dark = is_dark
        self._action_callback = action_callback

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)

        # Message Label
        self.msg_label = QLabel(message)
        self.msg_label.setStyleSheet("color: #FFFFFF; font-size: 13px; font-weight: 500;")
        layout.addWidget(self.msg_label)

        # Action Button if provided
        if action_label and action_callback:
            self.action_btn = QPushButton(action_label)
            self.action_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.2);
                    color: #FFFFFF;
                    border: none;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-weight: 600;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.35);
                }
            """)
            self.action_btn.clicked.connect(self._on_action_clicked)
            layout.addWidget(self.action_btn)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)

        # Auto-dismiss timer
        if duration_ms > 0:
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.setInterval(duration_ms)
            self._timer.timeout.connect(self.fade_out)
            self._timer.start()

    def _on_action_clicked(self):
        if self._action_callback:
            self._action_callback()
        self.fade_out()

    def show_animated(self):
        self.show()
        anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        anim.setDuration(180)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()

    def fade_out(self):
        anim = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.InCubic)
        anim.finished.connect(self.close)
        anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 8.0

        if self._status == "error":
            bg = QColor("#991B1B") if self._is_dark else QColor("#EF4444")
            icon_name = "close"
        elif self._status == "warning":
            bg = QColor("#92400E") if self._is_dark else QColor("#F59E0B")
            icon_name = "filter"
        elif self._status == "info":
            bg = QColor("#1E3A8A") if self._is_dark else QColor("#3B82F6")
            icon_name = "task"
        else:  # success
            bg = QColor("#065F46") if self._is_dark else QColor("#10B981")
            icon_name = "checkmark"

        # Background Path
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, QBrush(bg))
        painter.strokePath(path, QPen(QColor(255, 255, 255, 40), 1.0))

        painter.end()


class ToastManager:
    """Manages toast positioning and presentation on top of parent windows."""

    @staticmethod
    def show_toast(
        parent: QWidget,
        message: str,
        status: str = "success",
        duration_ms: int = 3500,
        action_label: Optional[str] = None,
        action_callback: Optional[Callable] = None,
        is_dark: bool = True,
    ):
        toast = Toast(
            message=message,
            status=status,
            duration_ms=duration_ms,
            action_label=action_label,
            action_callback=action_callback,
            parent=parent,
            is_dark=is_dark,
        )
        toast.adjustSize()
        # Position centered at bottom of parent widget
        parent_rect = parent.rect()
        toast_x = (parent_rect.width() - toast.width()) // 2
        toast_y = parent_rect.height() - toast.height() - 24
        toast.move(toast_x, toast_y)
        toast.show_animated()
        return toast
