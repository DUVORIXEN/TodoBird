"""
ToastBanner — Reusable lightweight animated feedback banner for Todo Bird.
Provides visual confirmation for Save/Update actions and visible validation warnings.
"""

from typing import Optional
from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QColor

class ToastBanner(QLabel):
    """
    Floating animated toast banner attached to a parent widget.
    """
    _active_toast: Optional["ToastBanner"] = None

    def __init__(self, parent: QWidget, message: str, status: str = "success", duration_ms: int = 2500):
        super().__init__(parent)
        self.duration_ms = duration_ms
        self.setText(message)
        self.setAlignment(Qt.AlignCenter)

        # Style based on status
        if status == "success":
            bg_color = "rgba(16, 185, 129, 0.95)"  # Emerald green
            text_color = "#FFFFFF"
            border_color = "#059669"
        elif status == "warning":
            bg_color = "rgba(245, 158, 11, 0.95)"  # Amber
            text_color = "#FFFFFF"
            border_color = "#D97706"
        elif status == "error":
            bg_color = "rgba(239, 68, 68, 0.95)"   # Red
            text_color = "#FFFFFF"
            border_color = "#DC2626"
        else:
            bg_color = "rgba(53, 132, 228, 0.95)"  # Brand blue
            text_color = "#FFFFFF"
            border_color = "#1D4ED8"

        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: 600;
            }}
        """)
        self.adjustSize()

        # Position at top-center of parent
        self._reposition()

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(200)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)

        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self._fade_out)

    def _reposition(self):
        if self.parentWidget():
            p_w = self.parentWidget().width()
            my_w = self.width()
            x = max(10, (p_w - my_w) // 2)
            y = 20
            self.move(x, y)

    def show_toast(self):
        self.show()
        self.raise_()
        self.anim.start()
        self.hide_timer.start(self.duration_ms)

    def _fade_out(self):
        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(300)
        self.fade_anim.setStartValue(1.0)
        self.fade_anim.setEndValue(0.0)
        self.fade_anim.setEasingCurve(QEasingCurve.InCubic)
        self.fade_anim.finished.connect(self.deleteLater)
        self.fade_anim.start()

    @classmethod
    def show_message(cls, parent: QWidget, message: str, status: str = "success", duration_ms: int = 2500):
        if not parent:
            return None
        if cls._active_toast:
            try:
                cls._active_toast.deleteLater()
            except Exception:
                pass
        toast = cls(parent, message, status=status, duration_ms=duration_ms)
        cls._active_toast = toast
        toast.show_toast()
        return toast
