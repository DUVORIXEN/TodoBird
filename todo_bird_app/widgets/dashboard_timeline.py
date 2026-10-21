
"""
Dashboard Horizontal Scrollable Lookahead Timeline Widget
"""
from datetime import date, timedelta, datetime
from typing import Dict, List, Any, Optional

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QScrollArea, 
    QFrame, QSizePolicy, QToolTip
)
from PySide6.QtCore import Qt, QRect, QRectF, QPoint, QPointF, Signal, QDate
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QPalette, QPainterPath, QPolygonF

from todo_bird_app.themes.tokens import (
    SEMANTIC_COLORS,
    TYPOGRAPHY_HIERARCHY,
    SPACING_SCALE,
    CARD_RADIUS,
)

# Visual-only constants (spacing scale / radius / typography roles).
# Date, horizon and layout math below is untouched.
_BAR_RADIUS = 4  # == SPACING_SCALE["xs"]; bars are 20px tall so sm/8 is too round.
_BAR_ALPHA = 200  # bumped 180→200 for bar readability (S4.1.2).
_MILESTONE_MIN_WIDTH = 5.0
_TICK_LABEL_SIZE = TYPOGRAPHY_HIERARCHY["caption"]["size"]  # 11px ~= 8pt header
_TICK_DATE_SIZE = 7  # sub-label stays compact under the D-label
_ANCHOR_LABEL_SIZE = TYPOGRAPHY_HIERARCHY["caption"]["size"]
_TASK_NAME_LEFT_PAD = SPACING_SCALE["md"] - 2  # 10px, was hardcoded 10


def _timeline_is_dark(widget) -> bool:
    """Resolve light/dark from theme properties, falling back to palette."""
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        for source in (widget, app):
            try:
                value = source.property("todoBirdTheme") if source is not None else None
            except RuntimeError:
                value = None
            if isinstance(value, str) and value.lower() in {"dark", "light"}:
                return value.lower() == "dark"
        palette = widget.palette() if widget is not None else app.palette()
        return palette.color(QPalette.Window).lightness() < 128
    except Exception:
        return True

class DashboardTimelineContent(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.anchor_date = date.today()
        self.horizon_days = 7
        self.data = []  # List of dicts (name, start, finish, status, critical)
        self.today = date.today()
        self.px_per_day = 80
        self.left_margin = 150  # Space for task names
        self.top_margin = 40
        self.row_height = 40
        self.days_before = 30
        self.setMinimumHeight(200)
        # Visual-only hover affordance (row highlight + tooltip). No data impact.
        self._hover_row = -1

    def update_data(self, anchor_date, horizon_days, data, today):
        self.anchor_date = anchor_date
        self.horizon_days = horizon_days
        if isinstance(data, dict):
            if "tasks" in data and isinstance(data["tasks"], list):
                self.data = data["tasks"]
            else:
                items = []
                for m_date_str, count in data.get("milestones", {}).items():
                    try:
                        m_d = datetime.strptime(m_date_str, "%Y-%m-%d").date() if isinstance(m_date_str, str) else m_date_str
                        items.append({"name": f"Milestones ({count})", "start": m_d, "finish": m_d, "status": "planned", "critical": False})
                    except Exception:
                        pass
                for c_date_str, count in data.get("critical", {}).items():
                    try:
                        c_d = datetime.strptime(c_date_str, "%Y-%m-%d").date() if isinstance(c_date_str, str) else c_date_str
                        items.append({"name": f"Critical ({count})", "start": c_d, "finish": c_d, "status": "in_progress", "critical": True})
                    except Exception:
                        pass
                self.data = items
        elif isinstance(data, list):
            self.data = data
        else:
            self.data = []
        self.today = today

        # Adaptive tick contract
        if horizon_days <= 7:
            self.px_per_day = 80
        elif horizon_days <= 14:
            self.px_per_day = 50
        elif horizon_days <= 30:
            self.px_per_day = 35
        elif horizon_days <= 90:
            self.px_per_day = 15
        else:
            self.px_per_day = 10
        
        total_width = self.left_margin + (self.days_before + self.horizon_days) * self.px_per_day + 40
        self.setMinimumWidth(total_width)
        
        total_height = self.top_margin + len(self.data) * self.row_height + 20
        self.setMinimumHeight(total_height)
        
        self.update()

    def _get_x_for_date(self, d: date) -> float:
        delta = (d - self.anchor_date).days
        return self.left_margin + (self.days_before + delta) * self.px_per_day

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        is_dark = _timeline_is_dark(self)
        grid_pen = QPen(QColor(255, 255, 255, 18) if is_dark else QColor(0, 0, 0, 18), 1)
        text_pen = QPen(QColor("#9CA3AF") if is_dark else QColor("#64748B"), 1)
        date_sub_pen = QPen(QColor("#6B7280") if is_dark else QColor("#94A3B8"), 1)
        task_pen = QPen(QColor("#F3F4F6") if is_dark else QColor("#0F172A"), 1)
        font = painter.font()
        # 8pt tick label ≈ 11px caption role (TYPOGRAPHY_HIERARCHY["caption"]).
        font.setPointSize(8)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)

        # Draw anchor line: subtle glow pass (wide translucent accent, alpha
        # 50) under the 2px solid accent core. Paint-only; x math untouched.
        anchor_x = self._get_x_for_date(self.anchor_date)
        accent = QColor(SEMANTIC_COLORS["accent"])  # #E95420 token
        glow_pen = QPen(QColor(accent.red(), accent.green(), accent.blue(), 40), 6)
        painter.setPen(glow_pen)
        painter.drawLine(int(anchor_x), 0, int(anchor_x), self.height())
        anchor_pen = QPen(accent, 2)  # ACCENT token
        painter.setPen(anchor_pen)
        painter.drawLine(int(anchor_x), 0, int(anchor_x), self.height())
        # Anchor label chip: accent-tinted rounded background behind the text
        # so it reads on light and dark surfaces alike.
        anchor_font = painter.font()
        anchor_font.setPointSize(8)
        anchor_font.setBold(True)
        painter.setFont(anchor_font)
        chip_text = "◆ D · Anchor"
        chip_w, chip_h = 94, 18
        chip_rect = QRectF(int(anchor_x) - chip_w / 2.0, 5, chip_w, chip_h)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 230))
        painter.drawRoundedRect(chip_rect, 4, 4)
        painter.setPen(QPen(QColor("#FFFFFF"), 1))
        painter.drawText(chip_rect, Qt.AlignCenter, chip_text)
        painter.setFont(font)

        # Subtle today marker (dashed, muted) — distinct from the solid anchor.
        try:
            today_x = self._get_x_for_date(self.today)
            if int(today_x) != int(anchor_x):
                today_pen = QPen(
                    QColor(148, 163, 184, 160) if is_dark else QColor(100, 116, 139, 170),
                    1, Qt.DashLine,
                )
                painter.setPen(today_pen)
                painter.drawLine(int(today_x), self.top_margin, int(today_x), self.height())
        except Exception:
            pass

        # Decide tick interval
        tick_interval = 1
        if self.horizon_days >= 30:
            tick_interval = 2
        if self.horizon_days >= 90:
            tick_interval = 7

        # Draw ticks from D-30 to D+horizon
        for i in range(-self.days_before, self.horizon_days + 1):
            if i % tick_interval != 0:
                continue
                
            d = self.anchor_date + timedelta(days=i)
            x = self._get_x_for_date(d)
            
            painter.setPen(grid_pen)
            painter.drawLine(int(x), self.top_margin, int(x), self.height())
            
            painter.setPen(text_pen)
            label = "D" if i == 0 else (f"D+{i}" if i > 0 else f"D{i}")
            date_str = d.strftime("%d %b")
            painter.drawText(int(x) - 20, 25, 40, 15, Qt.AlignCenter, label)
            
            painter.setPen(date_sub_pen)
            font.setPointSize(_TICK_DATE_SIZE)
            painter.setFont(font)
            painter.drawText(int(x) - 20, self.top_margin - 5, 40, 15, Qt.AlignCenter, date_str)
            font.setPointSize(8)
            font.setWeight(QFont.DemiBold)
            painter.setFont(font)

        # S4.1.3 — empty state: muted centered hint (visual only, no data).
        if not self.data:
            empty_pen = QPen(QColor(150, 150, 150) if is_dark else QColor(100, 116, 139), 1)
            painter.setPen(empty_pen)
            empty_font = painter.font()
            empty_font.setPointSize(8)
            painter.setFont(empty_font)
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "No tasks in this horizon — adjust scope or horizon.")
            return

        # Draw Gantt Bars
        y = self.top_margin + 10
        for row_idx, task in enumerate(self.data):
            if not isinstance(task, dict) or "name" not in task or "start" not in task or "finish" not in task:
                continue
            if row_idx == self._hover_row:
                painter.fillRect(0, y, self.width(), self.row_height,
                                 QColor(255, 255, 255, 14) if is_dark else QColor(15, 23, 42, 10))
            painter.setPen(task_pen)
            painter.drawText(_TASK_NAME_LEFT_PAD, y, self.left_margin - 20, self.row_height, Qt.AlignVCenter | Qt.AlignLeft, task["name"])

            start_x = self._get_x_for_date(task["start"])
            finish_x = self._get_x_for_date(task["finish"])

            bar_width = max(finish_x - start_x, _MILESTONE_MIN_WIDTH)

            if task.get("critical"):
                bar_color = QColor(QColor(SEMANTIC_COLORS["red"]).red(),
                                   QColor(SEMANTIC_COLORS["red"]).green(),
                                   QColor(SEMANTIC_COLORS["red"]).blue(), _BAR_ALPHA)
            elif task.get("status") == "in_progress":
                bar_color = QColor(QColor(SEMANTIC_COLORS["green"]).red(),
                                   QColor(SEMANTIC_COLORS["green"]).green(),
                                   QColor(SEMANTIC_COLORS["green"]).blue(), _BAR_ALPHA)
            else:
                bar_color = QColor(QColor(SEMANTIC_COLORS["blue"]).red(),
                                   QColor(SEMANTIC_COLORS["blue"]).green(),
                                   QColor(SEMANTIC_COLORS["blue"]).blue(), _BAR_ALPHA)

            painter.setBrush(bar_color)
            painter.setPen(Qt.NoPen)

            rect = QRectF(start_x, y + 10, bar_width, self.row_height - 20)
            painter.drawRoundedRect(rect, _BAR_RADIUS, _BAR_RADIUS)

            # S4.1.2 — milestone diamond for zero-duration tasks (visual only;
            # position reuses the same _get_x_for_date math as the bar).
            try:
                is_milestone = task.get("start") == task.get("finish")
            except Exception:
                is_milestone = False
            if is_milestone:
                cy = y + 10 + (self.row_height - 20) / 2.0
                half = (self.row_height - 20) / 2.0
                diamond = QPolygonF([
                    QPointF(start_x, cy - half),
                    QPointF(start_x + half, cy),
                    QPointF(start_x, cy + half),
                    QPointF(start_x - half, cy),
                ])
                # White border so the diamond reads on any bar color/theme.
                painter.setPen(QPen(QColor("#FFFFFF"), 1))
                painter.drawPolygon(diamond)
                painter.setPen(Qt.NoPen)

            # S4.1.3 — hovered-bar accent outline (visual affordance only).
            if row_idx == self._hover_row:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(SEMANTIC_COLORS["accent"]), 1))
                painter.drawRoundedRect(rect.adjusted(-0.5, -0.5, 0.5, 0.5),
                                         _BAR_RADIUS, _BAR_RADIUS)
                painter.setPen(Qt.NoPen)

            y += self.row_height

    def mouseMoveEvent(self, event):
        # Visual-only hover affordance: highlight row + tooltip. No data impact.
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        rel_y = pos.y() - (self.top_margin + 10)
        row = int(rel_y // self.row_height) if self.row_height else -1
        if row < 0 or row >= len(self.data):
            row = -1
        if row != self._hover_row:
            self._hover_row = row
            self.update()
        if row >= 0:
            task = self.data[row]
            tip = f"{task.get('name', '')}\n{task.get('start', '')} → {task.get('finish', '')}"
            QToolTip.showText(event.globalPos(), tip, self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_row = -1
        QToolTip.hideText()
        self.update()
        super().leaveEvent(event)


class DashboardTimelineWidget(QWidget):
    """Horizontal scrollable timeline for lookahead horizons."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(280)
        
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setFrameShape(QFrame.NoFrame)
        # S4.1.3 — thin (8px) rounded horizontal scrollbar. Translucent gray
        # handle + transparent track read correctly on light AND dark themes
        # via palette-independent alpha (no hardcoded dark/light background).
        self.scroll_area.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:horizontal { height: 8px; background: transparent;"
            " margin: 0px 8px 0px 8px; }"
            "QScrollBar::handle:horizontal { background: rgba(128, 128, 128, 110);"
            " border-radius: 4px; min-width: 20px; }"
            "QScrollBar::handle:horizontal:hover { background: rgba(128, 128, 128, 170); }"
            "QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {"
            " width: 0px; background: transparent; }"
            "QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {"
            " background: transparent; }"
        )
        
        self.content = DashboardTimelineContent(self.scroll_area)
        self.scroll_area.setWidget(self.content)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll_area)
        
    def set_data(self, anchor_date: date, horizon_days: int, data: Dict[str, Any], today: date):
        self.content.update_data(anchor_date, horizon_days, data, today)
        
    def wheelEvent(self, event):
        if event.modifiers() & Qt.ShiftModifier:
            self.scroll_area.horizontalScrollBar().event(event)
        else:
            super().wheelEvent(event)

# Convenience function to create timeline data from dashboard model
def build_timeline_data(model: Any, anchor: date, horizon_days: int) -> Dict[str, Any]:
    return {}
