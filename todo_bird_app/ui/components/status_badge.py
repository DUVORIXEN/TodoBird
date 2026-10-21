"""
TODO BIRD — MODERN STATUS BADGE & MILESTONE COMPONENT
Provides semantic, restrained status badges/pills and vector milestone diamond rendering.
Supports: Planned, In Progress, Blocked, Completed, Delayed, Moved, Cancelled.
"""

from enum import Enum
from typing import Optional, Tuple
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QFont,
)

from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.services.icon_service import IconService


class BadgeStatus(Enum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    DELAYED = "delayed"
    MOVED = "moved"
    CANCELLED = "cancelled"
    MILESTONE = "milestone"


class StatusBadge(QWidget):
    """
    Compact semantic status badge / pill.
    Displays indicator dot/glyph and label with calibrated contrast in dark and light modes.
    """

    STATUS_CONFIG = {
        BadgeStatus.PLANNED: {
            "label": "Planned",
            "dark_bg": "#222334",
            "dark_fg": "#9BA3C0",
            "dark_border": "#2E3045",
            "light_bg": "#F1F5F9",
            "light_fg": "#475569",
            "light_border": "#CBD5E1",
            "dot": "#64748B",
        },
        BadgeStatus.IN_PROGRESS: {
            "label": "In Progress",
            "dark_bg": "#182538",
            "dark_fg": "#8CB8FF",
            "dark_border": "#243854",
            "light_bg": "#EBF4FF",
            "light_fg": "#1D4ED8",
            "light_border": "#BFDBFE",
            "dot": "#3B82F6",
        },
        BadgeStatus.COMPLETED: {
            "label": "Completed",
            "dark_bg": "#162B22",
            "dark_fg": "#6EE7B7",
            "dark_border": "#1E4033",
            "light_bg": "#ECFDF5",
            "light_fg": "#047857",
            "light_border": "#A7F3D0",
            "dot": "#10B981",
        },
        BadgeStatus.BLOCKED: {
            "label": "Blocked",
            "dark_bg": "#321C22",
            "dark_fg": "#FCA5A5",
            "dark_border": "#4D252E",
            "light_bg": "#FEF2F2",
            "light_fg": "#B91C1C",
            "light_border": "#FECACA",
            "dot": "#EF4444",
        },
        BadgeStatus.DELAYED: {
            "label": "Delayed",
            "dark_bg": "#2E2316",
            "dark_fg": "#FCD34D",
            "dark_border": "#45341E",
            "light_bg": "#FFFBEB",
            "light_fg": "#B45309",
            "light_border": "#FDE68A",
            "dot": "#F59E0B",
        },
        BadgeStatus.MOVED: {
            "label": "Moved",
            "dark_bg": "#261D36",
            "dark_fg": "#C4B5FD",
            "dark_border": "#3A2C52",
            "light_bg": "#F5F3FF",
            "light_fg": "#6D28D9",
            "light_border": "#DDD6FE",
            "dot": "#8B5CF6",
        },
        BadgeStatus.CANCELLED: {
            "label": "Cancelled",
            "dark_bg": "#222334",
            "dark_fg": "#6C7086",
            "dark_border": "#2A2B3D",
            "light_bg": "#F1F5F9",
            "light_fg": "#94A3B8",
            "light_border": "#E2E8F0",
            "dot": "#94A3B8",
        },
        BadgeStatus.MILESTONE: {
            "label": "Milestone",
            "dark_bg": "#2B1B3D",
            "dark_fg": "#E9D5FF",
            "dark_border": "#432860",
            "light_bg": "#FAF5FF",
            "light_fg": "#7E22CE",
            "light_border": "#E9D5FF",
            "dot": "#A855F7",
        },
    }

    def __init__(
        self,
        status: BadgeStatus = BadgeStatus.PLANNED,
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        custom_label: Optional[str] = None,
    ):
        super().__init__(parent)
        self._status = status
        self._is_dark = is_dark
        self._custom_label = custom_label
        self.setFixedHeight(22)

    @property
    def status(self) -> BadgeStatus:
        return self._status

    @status.setter
    def status(self, val: BadgeStatus):
        self._status = val
        self.update()

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark
        self.update()

    def sizeHint(self) -> QSize:
        cfg = self.STATUS_CONFIG.get(self._status, self.STATUS_CONFIG[BadgeStatus.PLANNED])
        label = self._custom_label or cfg["label"]
        fm = self.fontMetrics()
        w = fm.horizontalAdvance(label) + 24
        return QSize(w, 22)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        cfg = self.STATUS_CONFIG.get(self._status, self.STATUS_CONFIG[BadgeStatus.PLANNED])
        label = self._custom_label or cfg["label"]

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 5.0

        bg_col = QColor(cfg["dark_bg"] if self._is_dark else cfg["light_bg"])
        border_col = QColor(cfg["dark_border"] if self._is_dark else cfg["light_border"])
        text_col = QColor(cfg["dark_fg"] if self._is_dark else cfg["light_fg"])
        dot_col = QColor(cfg["dot"])

        # 1. Background Pill
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.fillPath(path, QBrush(bg_col))
        painter.strokePath(path, QPen(border_col, 1.0))

        # 2. Leading Dot or Diamond
        if self._status == BadgeStatus.MILESTONE:
            diamond_rect = QRectF(rect.x() + 6, rect.y() + (rect.height() - 9) / 2.0, 9, 9)
            IconService.render_vector_icon(painter, "milestone", diamond_rect, dot_col, filled=True)
        else:
            dot_cy = rect.y() + rect.height() / 2.0
            painter.setBrush(QBrush(dot_col))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(rect.x() + 7, dot_cy - 3, 6, 6))

        # 3. Label Text
        font = painter.font()
        font.setPointSize(11)
        font.setWeight(QFont.Medium)
        painter.setFont(font)
        painter.setPen(text_col)

        text_rect = QRectF(rect.x() + 18, 0, rect.width() - 22, rect.height())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, label)

        painter.end()


def render_milestone_diamond(
    painter: QPainter,
    rect: QRectF,
    color: QColor,
    filled: bool = True,
):
    """
    Renders a crisp vector milestone diamond gateway (◆) on any QPainter surface.
    """
    IconService.render_vector_icon(painter, "milestone", rect, color, stroke_width=1.8, filled=filled)
