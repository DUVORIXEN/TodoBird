"""
Todo Bird Advanced Native Dashboard Chart Engine — Phase 1F.7.2.2

Pure PySide6 / QPainter implementation.
No browser, no embedded web charts.

Interactive Dashboard 2.0 chart architecture:
- Hit regions & geometric spatial indexing
- Hover inspection & visual point/segment highlight
- Rich native tooltips with current chart figures
- Mouse selection with distinct persistent visual state
- Full keyboard inspection (Tab focus, Left/Right/Up/Down navigation, Enter/Space select, Escape clear)
- Accessibility: AccessibleName, AccessibleDescription, outline/shape/opacity contrast
- Zero idle animation loops / zero CPU churn
- 7D / 14D / 30D / 90D range compatibility
- High-DPI and responsive reflow safe

The widgets intentionally preserve the existing Dashboard data contracts:
- capacity: actual minutes, planned minutes, capacity minutes
- task status: planned, in progress, blocked/delayed, completed
- activity: daily completed vs planned counts
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass, field
from math import cos, pi, sin
from typing import List, Tuple, Optional, Any, Dict

from PySide6.QtCore import (
    Qt,
    QEvent,
    QObject,
    QRectF,
    QPointF,
    QVariantAnimation,
    QEasingCurve,
    Signal,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QBrush,
    QPolygonF,
    QPalette,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QSizePolicy,
    QToolTip,
)

from todo_bird_app.services.appearance_service import semantic_tokens_for


def _format_m(minutes: int) -> str:
    """Format minutes into human-readable duration display (e.g. 90m -> 1h 30m)."""
    m = max(0, int(minutes))
    if m < 60:
        return f"{m}m"
    h = m // 60
    rem = m % 60
    return f"{h}h {rem}m" if rem > 0 else f"{h}h"


def _property_text(source, name: str) -> str:
    try:
        value = source.property(name) if source is not None else None
    except RuntimeError:
        value = None
    return str(value or "").strip()


def _dashboard_tooltip_is_dark(widget: Optional[QWidget]) -> bool:
    theme = _property_text(widget, "todoBirdTheme").lower()
    if theme in {"dark", "light"}:
        return theme == "dark"

    app = QApplication.instance()
    theme = _property_text(app, "todoBirdTheme").lower()
    if theme in {"dark", "light"}:
        return theme == "dark"

    try:
        palette = widget.palette() if widget is not None else app.palette()
        return palette.color(QPalette.Window).lightness() < 128
    except Exception:
        return True


def _dashboard_tooltip_accent(widget: Optional[QWidget]) -> str:
    for source in (widget, QApplication.instance()):
        accent = _property_text(source, "todoBirdAccent")
        if QColor(accent).isValid():
            return QColor(accent).name()
    try:
        return widget.palette().color(QPalette.Highlight).name()
    except Exception:
        return "#3584e4"


@dataclass(frozen=True)
class DashboardTooltipTheme:
    """Resolved dashboard hover-surface colors for the current runtime theme."""

    theme: str
    background: str
    text_primary: str
    text_secondary: str
    border: str
    accent: str

    @property
    def is_dark(self) -> bool:
        return self.theme == "dark"

    def qss(self) -> str:
        # Visual polish (M5 S5.1.3): card geometry snapped to the shared
        # spacing scale (radius 8 / padding 8x12); colors/fields unchanged.
        return (
            "QToolTip { "
            f"background-color: {self.background}; "
            f"color: {self.text_primary}; "
            f"border: 1px solid {self.border}; "
            "border-radius: 8px; "
            "padding: 8px 12px; "
            "font-size: 12px; "
            "font-weight: 500; "
            "}"
        )


def dashboard_tooltip_theme(widget: Optional[QWidget]) -> DashboardTooltipTheme:
    """Resolve native dashboard tooltip colors from the active semantic theme."""
    is_dark = _dashboard_tooltip_is_dark(widget)
    accent = _dashboard_tooltip_accent(widget)
    tokens = semantic_tokens_for(is_dark, accent)
    return DashboardTooltipTheme(
        theme="dark" if is_dark else "light",
        background=QColor(tokens["SURFACE_2"]).name(),
        text_primary=QColor(tokens["TEXT_PRIMARY"]).name(),
        text_secondary=QColor(tokens["TEXT_SECONDARY"]).name(),
        border=QColor(tokens["BORDER_STRONG"]).name(),
        accent=QColor(tokens["ACCENT"]).name(),
    )


def dashboard_tooltip_html(text: str, widget: Optional[QWidget]) -> str:
    """Return a rich tooltip body with explicit readable dashboard colors."""
    theme = dashboard_tooltip_theme(widget)
    lines = html.escape(str(text or "")).splitlines() or [""]
    title = lines[0]
    details = "<br>".join(lines[1:])
    if details:
        body = (
            f'<div style="color: {theme.text_primary}; font-weight: 700;">'
            f"{title}</div>"
            # Visual polish (M5 S5.1.3): 4px gap sits on the spacing scale.
            f'<div style="color: {theme.text_secondary}; margin-top: 4px;">'
            f"{details}</div>"
        )
    else:
        body = (
            f'<span style="color: {theme.text_primary}; font-weight: 600;">'
            f"{title}</span>"
        )

    # Visual polish (M5 S5.1.3): card geometry snapped to the shared scale
    # (radius 8 / padding 8x12); data fields and colors unchanged.
    return (
        '<div data-todo-bird-dashboard-tooltip="1" '
        'style="'
        f"background-color: {theme.background}; "
        f"color: {theme.text_primary}; "
        f"border: 1px solid {theme.border}; "
        "border-radius: 8px; "
        "padding: 8px 12px; "
        "white-space: nowrap; "
        "font-size: 12px; "
        '">'
        f"{body}</div>"
    )


def apply_dashboard_tooltip_theme(widget: Optional[QWidget]) -> DashboardTooltipTheme:
    """Synchronize Qt's static tooltip palette before a dashboard tooltip opens."""
    theme = dashboard_tooltip_theme(widget)
    palette = QToolTip.palette()
    palette.setColor(QPalette.ToolTipBase, QColor(theme.background))
    palette.setColor(QPalette.ToolTipText, QColor(theme.text_primary))
    QToolTip.setPalette(palette)

    app = QApplication.instance()
    if app is not None:
        app.setProperty("todoBirdDashboardTooltipTheme", theme.theme)
        app.setProperty("todoBirdDashboardTooltipQss", theme.qss())

    return theme


def _help_event_position(event) -> QPointF:
    try:
        return QPointF(event.pos())
    except Exception:
        return QPointF()


def _help_event_global_position(event, widget: QWidget):
    try:
        return event.globalPos()
    except Exception:
        return widget.mapToGlobal(_help_event_position(event).toPoint())


def show_dashboard_widget_tooltip(widget: QWidget, event, text: str) -> bool:
    """Show a dashboard-owned QWidget tooltip through the themed runtime path."""
    clean_text = str(text or "").strip()
    if not clean_text:
        QToolTip.hideText()
        widget._last_tooltip_text = ""
        try:
            event.ignore()
        except Exception:
            pass
        return True

    if getattr(widget, "_last_tooltip_text", None) == clean_text and QToolTip.isVisible():
        try:
            event.accept()
        except Exception:
            pass
        return True

    widget._last_tooltip_text = clean_text

    apply_dashboard_tooltip_theme(widget)
    QToolTip.showText(
        _help_event_global_position(event, widget),
        dashboard_tooltip_html(clean_text, widget),
        widget,
    )
    try:
        event.accept()
    except Exception:
        pass
    return True


class DashboardTooltipEventFilter(QObject):
    """Intercept ordinary QWidget tooltips inside DashboardView."""

    def eventFilter(self, watched, event):
        if (
            event.type() == QEvent.ToolTip
            and isinstance(watched, QWidget)
        ):
            return show_dashboard_widget_tooltip(
                watched,
                event,
                watched.toolTip(),
            )
        return super().eventFilter(watched, event)


def install_dashboard_tooltip_filter(widget: Optional[QWidget]) -> Optional[DashboardTooltipEventFilter]:
    """Attach the dashboard tooltip authority to a non-chart dashboard widget."""
    if widget is None:
        return None
    existing = getattr(widget, "_todo_bird_dashboard_tooltip_filter", None)
    if existing is not None:
        return existing

    tooltip_filter = DashboardTooltipEventFilter(widget)
    widget.installEventFilter(tooltip_filter)
    widget._todo_bird_dashboard_tooltip_filter = tooltip_filter
    return tooltip_filter


# ------------------------------------------------------------
# Interactive Hit Region Architecture
# ------------------------------------------------------------

@dataclass
class ChartHitRegion:
    """Lightweight interactive region for hit testing, tooltips, and accessibility."""
    key: Any
    label: str
    primary_value: Any
    secondary_value: Optional[Any] = None
    percentage: Optional[float] = None
    tooltip_text: str = ""
    accessible_text: str = ""
    rect: Optional[QRectF] = None
    path: Optional[QPainterPath] = None
    center: Optional[QPointF] = None
    radius: Optional[float] = None
    inner_radius: Optional[float] = None
    start_angle_deg: Optional[float] = None
    span_angle_deg: Optional[float] = None
    color: Optional[QColor] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def contains(self, point: QPointF) -> bool:
        """Determines if a given point lies within this hit region."""
        if self.path is not None:
            return self.path.contains(point)
        if self.rect is not None:
            return self.rect.contains(point)
        if self.center is not None and self.radius is not None:
            dx = point.x() - self.center.x()
            dy = point.y() - self.center.y()
            dist = math.hypot(dx, dy)
            if self.inner_radius is not None and dist < self.inner_radius:
                return False
            if dist > self.radius:
                return False
            if self.start_angle_deg is not None and self.span_angle_deg is not None:
                angle = math.degrees(math.atan2(-dy, dx)) % 360.0
                start = self.start_angle_deg % 360.0
                span = self.span_angle_deg
                if span < 0:
                    diff = (start - angle) % 360.0
                    return diff <= abs(span)
                else:
                    diff = (angle - start) % 360.0
                    return diff <= span
            return True
        return False

    def center_point(self) -> QPointF:
        """Returns the central coordinate of this hit region for tooltips and anchors."""
        if self.rect is not None:
            return self.rect.center()
        if self.center is not None:
            return self.center
        if self.path is not None:
            return self.path.boundingRect().center()
        return QPointF(0, 0)


# ------------------------------------------------------------
# Shared native animated interactive chart base
# ------------------------------------------------------------

class AnimatedDashboardChart(QWidget):
    """Finite, lightweight native chart base with full interaction engine."""

    item_hovered = Signal(object)
    item_selected = Signal(object)
    selection_cleared = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._animation_progress = 1.0
        self._animations_enabled = True

        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Preferred,
        )

        self._animation = QVariantAnimation(self)
        self._animation.setDuration(520)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(
            QEasingCurve.OutCubic
        )
        self._animation.valueChanged.connect(
            self._on_animation_value
        )

        # Interaction infrastructure
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        self._hit_regions: List[ChartHitRegion] = []
        self._hovered_key: Optional[Any] = None
        self._hovered_region: Optional[ChartHitRegion] = None
        self._selected_key: Optional[Any] = None
        self._selected_region: Optional[ChartHitRegion] = None
        self._focused_index: Optional[int] = None
        self._interaction_enabled: bool = True

        # Tooltip hysteresis - prevents flicker and recreation storms
        self._tooltip_show_timer = QTimer(self)
        self._tooltip_show_timer.setSingleShot(True)
        self._tooltip_show_timer.setInterval(150)  # 150ms show delay
        self._tooltip_show_timer.timeout.connect(self._show_pending_tooltip)
        
        self._tooltip_hide_timer = QTimer(self)
        self._tooltip_hide_timer.setSingleShot(True)
        self._tooltip_hide_timer.setInterval(300)  # 300ms hide delay
        self._tooltip_hide_timer.timeout.connect(self._hide_pending_tooltip)
        
        self._pending_tooltip_region: Optional[ChartHitRegion] = None
        self._pending_tooltip_pos = QPointF()
        self._last_tooltip_key: Optional[Any] = None
        self._last_tooltip_global_pos = QPointF()
        self._tooltip_movement_tolerance = 8  # pixels - movement before tooltip updates

    def _on_animation_value(self, value):
        self._animation_progress = max(
            0.0,
            min(1.0, float(value)),
        )
        self.update()

    def set_animations_enabled(self, enabled: bool):
        self._animations_enabled = bool(enabled)

        if not self._animations_enabled:
            self._animation.stop()
            self._animation_progress = 1.0
            self.update()

    def animate_update(self):
        if not self._animations_enabled:
            self._animation_progress = 1.0
            self.update()
            return

        self._animation.stop()
        self._animation_progress = 0.0
        self._animation.start()

    # ------------------------------------------------------------
    # Interaction API & Helpers
    # ------------------------------------------------------------

    def set_interaction_enabled(self, enabled: bool):
        self._interaction_enabled = bool(enabled)
        if not self._interaction_enabled:
            self.clear_interaction_state()

    def hit_test(self, point: QPointF) -> Optional[ChartHitRegion]:
        """Finds the hit region containing the given coordinate."""
        if not self._interaction_enabled:
            return None
        for region in reversed(self._hit_regions):
            if region.contains(point):
                return region
        return None

    def selected_item(self) -> Optional[ChartHitRegion]:
        return self._selected_region

    def hovered_item(self) -> Optional[ChartHitRegion]:
        return self._hovered_region

    def select_key(self, key: Any):
        """Programmatically select a specific hit region by key."""
        self._selected_key = key
        self._selected_region = next((r for r in self._hit_regions if r.key == key), None)
        if self._selected_region:
            self.item_selected.emit(self._selected_region)
        else:
            self.selection_cleared.emit()
        self._update_accessible_state()
        self.update()

    def clear_selection(self):
        """Clears active selection."""
        if self._selected_key is not None or self._selected_region is not None:
            self._selected_key = None
            self._selected_region = None
            self.selection_cleared.emit()
            self._update_accessible_state()
            self.update()

    def clear_interaction_state(self):
        """Clears all hover, selection, and keyboard focus states."""
        self._hovered_key = None
        self._hovered_region = None
        self._selected_key = None
        self._selected_region = None
        self._focused_index = None
        self.unsetCursor()
        # Stop tooltip timers
        self._tooltip_show_timer.stop()
        self._tooltip_hide_timer.stop()
        self._pending_tooltip_region = None
        QToolTip.hideText()
        self.selection_cleared.emit()
        self._update_accessible_state()
        self.update()

    def _get_item_state(self, key: Any) -> Tuple[bool, bool, bool]:
        """Returns (is_hovered, is_selected, is_focused) for a given item key."""
        is_hovered = (self._hovered_key == key)
        is_selected = (self._selected_key == key)
        is_focused = (
            self._focused_index is not None
            and 0 <= self._focused_index < len(self._hit_regions)
            and self._hit_regions[self._focused_index].key == key
        )
        return is_hovered, is_selected, is_focused

    def _has_active_inspection(self) -> bool:
        """Returns True if any item is currently hovered, selected, or focused."""
        if self._hovered_key is not None or self._selected_key is not None:
            return True
        if self._focused_index is not None:
            return True
        return False

    def _resolve_item_color(self, base_color: QColor, key: Any) -> QColor:
        """Applies hover brightening or non-active item dimming."""
        is_h, is_s, is_f = self._get_item_state(key)
        if is_s:
            return base_color.lighter(118)
        elif is_h or is_f:
            return base_color.lighter(112)
        elif self._has_active_inspection():
            c = QColor(base_color)
            c.setAlpha(int(c.alpha() * 0.45))
            return c
        return base_color

    def _draw_focus_ring(self, painter: QPainter):
        """Draws subtle widget focus indicator when focused via keyboard."""
        if self.hasFocus():
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing, True)
            pen = QPen(self.accent_color(), 1.5, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            # Visual polish (M5 S5.1.2): radius snapped to CARD_RADIUS sm (8).
            painter.drawRoundedRect(
                QRectF(1.5, 1.5, self.width() - 3.0, self.height() - 3.0),
                8,
                8,
            )
            painter.restore()

    def _show_keyboard_tooltip(self, region: ChartHitRegion):
        if not region.tooltip_text:
            return
        pt = region.center_point()
        global_pt = self.mapToGlobal(pt.toPoint())
        self._show_dashboard_tooltip(global_pt, region)

    def _show_dashboard_tooltip(self, global_pos, region: ChartHitRegion):
        if not region.tooltip_text:
            return
        apply_dashboard_tooltip_theme(self)
        if hasattr(global_pos, "toPoint"):
            global_pos = global_pos.toPoint()
        QToolTip.showText(
            global_pos,
            dashboard_tooltip_html(region.tooltip_text, self),
            self,
        )

    # ------------------------------------------------------------
    # Tooltip Hysteresis - prevents flicker and recreation storms
    # ------------------------------------------------------------
    def _show_pending_tooltip(self):
        """Called after show delay - actually shows the tooltip."""
        if self._pending_tooltip_region and self._pending_tooltip_region.tooltip_text:
            self._show_dashboard_tooltip(self._pending_tooltip_pos, self._pending_tooltip_region)
            self._last_tooltip_key = self._pending_tooltip_region.key
            self._last_tooltip_global_pos = self._pending_tooltip_pos

    def _hide_pending_tooltip(self):
        """Called after hide delay - hides tooltip if not re-entered."""
        if self._hovered_key is None:
            QToolTip.hideText()
            self._pending_tooltip_region = None

    def _should_update_tooltip(self, new_region: Optional[ChartHitRegion], global_pos: QPointF) -> bool:
        """Determines if tooltip should update based on movement tolerance and key change."""
        if new_region is None:
            return True  # Always allow hide
        if new_region.key != self._last_tooltip_key:
            return True  # Different target - update
        # Same target - check movement tolerance
        dx = global_pos.x() - self._last_tooltip_global_pos.x()
        dy = global_pos.y() - self._last_tooltip_global_pos.y()
        distance = (dx * dx + dy * dy) ** 0.5
        return distance > self._tooltip_movement_tolerance

    def event(self, event):
        if event.type() == QEvent.ToolTip:
            region = self.hit_test(_help_event_position(event))
            tooltip_text = (
                region.tooltip_text
                if region is not None and region.tooltip_text
                else self.toolTip()
            )
            return show_dashboard_widget_tooltip(self, event, tooltip_text)
        return super().event(event)

    def _update_accessible_state(self):
        name = f"{getattr(self, 'chart_type', 'Dashboard')} Chart"
        self.setAccessibleName(name)

        current_item = self._selected_region or self._hovered_region
        if current_item is None and self._focused_index is not None and 0 <= self._focused_index < len(self._hit_regions):
            current_item = self._hit_regions[self._focused_index]

        desc_parts = [name]
        if current_item:
            desc_parts.append(f"Inspecting: {current_item.accessible_text or current_item.label}")
        desc_parts.append("Use Left/Right arrow keys to inspect data points, Enter to select, Escape to clear.")
        self.setAccessibleDescription(" | ".join(desc_parts))

    # ------------------------------------------------------------
    # Event Handlers
    # ------------------------------------------------------------

    def mouseMoveEvent(self, event):
        pos = event.position()
        region = self.hit_test(pos)
        new_key = region.key if region else None
        global_pos = event.globalPosition()

        if new_key != self._hovered_key:
            # Cancel any pending tooltip operations
            self._tooltip_show_timer.stop()
            self._tooltip_hide_timer.stop()

            self._hovered_key = new_key
            self._hovered_region = region

            if region is not None:
                self.setCursor(Qt.PointingHandCursor)
                if region.tooltip_text:
                    # Check if we should update tooltip (hysteresis)
                    if self._should_update_tooltip(region, global_pos):
                        # New target or significant movement - show after delay
                        self._pending_tooltip_region = region
                        self._pending_tooltip_pos = global_pos
                        self._tooltip_show_timer.start()
                    else:
                        # Same target, small movement - just update position
                        self._pending_tooltip_region = region
                        self._pending_tooltip_pos = global_pos
                self.item_hovered.emit(region)
            else:
                self.unsetCursor()
                # Hide after delay to prevent flicker
                self._tooltip_hide_timer.start()
                self.item_hovered.emit(None)

            self._update_accessible_state()
            self.update()

        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hovered_key is not None:
            self._hovered_key = None
            self._hovered_region = None
            self.unsetCursor()
            # Cancel show timer, start hide timer for hysteresis
            self._tooltip_show_timer.stop()
            self._tooltip_hide_timer.start()
            self.item_hovered.emit(None)
            self._update_accessible_state()
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position()
            region = self.hit_test(pos)

            if region is not None:
                if self._selected_key == region.key:
                    self._selected_key = None
                    self._selected_region = None
                    self.selection_cleared.emit()
                else:
                    self._selected_key = region.key
                    self._selected_region = region
                    if region in self._hit_regions:
                        self._focused_index = self._hit_regions.index(region)
                    self.item_selected.emit(region)
                self._update_accessible_state()
                self.update()
            else:
                if self._selected_key is not None:
                    self._selected_key = None
                    self._selected_region = None
                    self.selection_cleared.emit()
                    self._update_accessible_state()
                    self.update()

        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if not self._hit_regions:
            super().keyPressEvent(event)
            return

        if key in (Qt.Key_Left, Qt.Key_Up):
            if self._focused_index is None:
                self._focused_index = len(self._hit_regions) - 1
            else:
                self._focused_index = (self._focused_index - 1) % len(self._hit_regions)
            region = self._hit_regions[self._focused_index]
            self._hovered_key = region.key
            self._hovered_region = region
            self._show_keyboard_tooltip(region)
            self._update_accessible_state()
            self.update()
            event.accept()
        elif key in (Qt.Key_Right, Qt.Key_Down):
            if self._focused_index is None:
                self._focused_index = 0
            else:
                self._focused_index = (self._focused_index + 1) % len(self._hit_regions)
            region = self._hit_regions[self._focused_index]
            self._hovered_key = region.key
            self._hovered_region = region
            self._show_keyboard_tooltip(region)
            self._update_accessible_state()
            self.update()
            event.accept()
        elif key in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            if self._focused_index is not None and 0 <= self._focused_index < len(self._hit_regions):
                region = self._hit_regions[self._focused_index]
                if self._selected_key == region.key:
                    self._selected_key = None
                    self._selected_region = None
                    self.selection_cleared.emit()
                else:
                    self._selected_key = region.key
                    self._selected_region = region
                    self.item_selected.emit(region)
                self._update_accessible_state()
                self.update()
                event.accept()
        elif key == Qt.Key_Escape:
            if self._selected_key is not None or self._hovered_key is not None:
                self._selected_key = None
                self._selected_region = None
                self._hovered_key = None
                self._hovered_region = None
                QToolTip.hideText()
                self.selection_cleared.emit()
                self._update_accessible_state()
                self.update()
                event.accept()
        else:
            super().keyPressEvent(event)

    def focusInEvent(self, event):
        if self._focused_index is None and self._hit_regions:
            self._focused_index = 0
        if self._focused_index is not None and 0 <= self._focused_index < len(self._hit_regions):
            region = self._hit_regions[self._focused_index]
            self._show_keyboard_tooltip(region)
        self._update_accessible_state()
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        # Stop tooltip timers on focus out
        self._tooltip_show_timer.stop()
        self._tooltip_hide_timer.stop()
        self._pending_tooltip_region = None
        QToolTip.hideText()
        self._update_accessible_state()
        self.update()
        super().focusOutEvent(event)

    @staticmethod
    def semantic_colors():
        app = QApplication.instance()
        accent = app.palette().color(QPalette.Highlight) if app else QColor("#3584E4")
        win_text = app.palette().color(QPalette.WindowText) if app else QColor("#F4F7FB")
        muted = QColor(win_text)
        muted.setAlpha(200)
        grid = QColor(win_text)
        grid.setAlpha(46)  # ~18% alpha per M5 S5.1.1, theme-aware base
        track = QColor(win_text)
        track.setAlpha(26)
        return {
            "planned": accent,
            "actual": QColor("#10B981"),
            "blocked": QColor("#F59E0B"),
            "danger": QColor("#EF4444"),
            "completed": QColor("#059669"),
            "accent2": QColor("#8B5CF6"),
            "cyan": QColor("#06B6D4"),
            "muted": muted,
            "grid": grid,
            "track": track,
        }

    def accent_color(self):
        return self.palette().color(QPalette.Highlight)

    def foreground_color(self):
        pal = self.palette()
        return pal.color(
            pal.ColorRole.WindowText
        )

    def muted_color(self):
        c = self.foreground_color()
        c.setAlpha(155)
        return c

    @staticmethod
    def _lerp(a, b, t):
        return a + (b - a) * t


# ------------------------------------------------------------
# Capacity / Workload visualization
# ------------------------------------------------------------

class AdvancedCapacityChart(AnimatedDashboardChart):

    CHART_TYPES = (
        "Segmented Bar",
        "Stacked Bar",
        "Bullet",
        "Gauge",
        "Semi Gauge",
        "Donut",
        "Radial Progress",
    )

    def __init__(self, parent=None):
        super().__init__(parent)

        self.actual_m = 0
        self.planned_m = 0
        self.capacity_m = 480
        self.chart_type = "Segmented Bar"

        self.setMinimumHeight(72)

    def set_chart_type(self, chart_type: str, animate: bool = False):
        if chart_type not in self.CHART_TYPES:
            chart_type = "Segmented Bar"

        if chart_type == self.chart_type:
            if not animate and (self._animation_progress != 1.0 or self._animation.state() == QVariantAnimation.Running):
                self._animation.stop()
                self._animation_progress = 1.0
                self.update()
            return

        self.chart_type = chart_type

        if chart_type in (
            "Gauge",
            "Semi Gauge",
            "Donut",
            "Radial Progress",
        ):
            self.setMinimumHeight(155)
        else:
            self.setMinimumHeight(78)

        if animate and self._animations_enabled:
            self.animate_update()
        else:
            self._animation.stop()
            self._animation_progress = 1.0
            self.update()

        self._update_accessible_state()
        self.updateGeometry()

    def set_render_mode(self, chart_type: str):
        """Sets the presentation chart type/style immediately without restarting data animation."""
        self.set_chart_type(chart_type, animate=False)

    def set_values(
        self,
        actual_m: int,
        planned_m: int,
        capacity_m: int,
    ):
        values = (
            max(0, int(actual_m)),
            max(0, int(planned_m)),
            max(1, int(capacity_m)),
        )

        if values == (
            self.actual_m,
            self.planned_m,
            self.capacity_m,
        ):
            return

        (
            self.actual_m,
            self.planned_m,
            self.capacity_m,
        ) = values

        self.animate_update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.Antialiasing
        )

        # Clear and rebuild hit regions per paint pass
        self._hit_regions = []

        colors = self.semantic_colors()

        rect = QRectF(
            8,
            8,
            max(10, self.width() - 16),
            max(10, self.height() - 16),
        )

        max_value = max(
            self.capacity_m,
            self.actual_m + self.planned_m,
            1,
        )

        progress = self._animation_progress

        actual = self.actual_m * progress
        planned = self.planned_m * progress

        if self.chart_type == "Segmented Bar":
            self._draw_segmented_bar(
                painter,
                rect,
                actual,
                planned,
                max_value,
                colors,
            )

        elif self.chart_type == "Stacked Bar":
            self._draw_stacked_bar(
                painter,
                rect,
                actual,
                planned,
                max_value,
                colors,
            )

        elif self.chart_type == "Bullet":
            self._draw_bullet(
                painter,
                rect,
                actual,
                planned,
                colors,
            )

        elif self.chart_type == "Gauge":
            self._draw_gauge(
                painter,
                rect,
                actual,
                planned,
                full_circle=True,
                colors=colors,
            )

        elif self.chart_type == "Semi Gauge":
            self._draw_gauge(
                painter,
                rect,
                actual,
                planned,
                full_circle=False,
                colors=colors,
            )

        elif self.chart_type == "Donut":
            self._draw_donut(
                painter,
                rect,
                actual,
                planned,
                colors,
            )

        else:
            self._draw_radial_progress(
                painter,
                rect,
                actual,
                planned,
                colors,
            )

        self._draw_focus_ring(painter)

    def _register_capacity_regions(
        self,
        act_rect: Optional[QRectF] = None,
        plan_rect: Optional[QRectF] = None,
        cap_rect: Optional[QRectF] = None,
        act_path: Optional[QPainterPath] = None,
        plan_path: Optional[QPainterPath] = None,
        cap_path: Optional[QPainterPath] = None,
    ):
        act_util = round((self.actual_m / max(1, self.capacity_m)) * 100.0, 1)
        plan_util = round((self.planned_m / max(1, self.capacity_m)) * 100.0, 1)
        total_m = self.actual_m + self.planned_m
        tot_util = round((total_m / max(1, self.capacity_m)) * 100.0, 1)
        headroom = max(0, self.capacity_m - total_m)

        act_tt = (
            f"Actual Work Effort\n"
            f"• Effort Logged: {self.actual_m}m ({_format_m(self.actual_m)})\n"
            f"• Capacity Share: {act_util}%\n"
            f"• Target Capacity: {self.capacity_m}m ({_format_m(self.capacity_m)})"
        )
        plan_tt = (
            f"Planned Work Effort\n"
            f"• Planned Work: {self.planned_m}m ({_format_m(self.planned_m)})\n"
            f"• Capacity Share: {plan_util}%\n"
            f"• Target Capacity: {self.capacity_m}m ({_format_m(self.capacity_m)})"
        )
        cap_tt = (
            f" Daily Capacity & Headroom\n"
            f"• Capacity Target: {self.capacity_m}m ({_format_m(self.capacity_m)})\n"
            f"• Total Assigned: {total_m}m ({_format_m(total_m)}) ({tot_util}%)\n"
            f"• Available Headroom: {headroom}m ({_format_m(headroom)})"
        )

        self._hit_regions = [
            ChartHitRegion(
                key="actual",
                label="Actual Work Effort",
                primary_value=self.actual_m,
                percentage=act_util,
                tooltip_text=act_tt,
                accessible_text=f"Actual Work Effort: {self.actual_m} minutes, {act_util}% of capacity",
                rect=act_rect,
                path=act_path,
                color=self.semantic_colors()["actual"],
            ),
            ChartHitRegion(
                key="planned",
                label="Planned Work Effort",
                primary_value=self.planned_m,
                percentage=plan_util,
                tooltip_text=plan_tt,
                accessible_text=f"Planned Work Effort: {self.planned_m} minutes, {plan_util}% of capacity",
                rect=plan_rect,
                path=plan_path,
                color=self.semantic_colors()["planned"],
            ),
            ChartHitRegion(
                key="capacity",
                label="Daily Capacity",
                primary_value=self.capacity_m,
                secondary_value=headroom,
                percentage=tot_util,
                tooltip_text=cap_tt,
                accessible_text=f"Daily Capacity: {self.capacity_m} minutes, remaining headroom {headroom} minutes",
                rect=cap_rect,
                path=cap_path,
                color=self.foreground_color(),
            ),
        ]

    def _selection_pen(self, width: float = 2.0, alpha: int = 255) -> QPen:
        """Theme-aware selection ring: fixed white vanishes on light surfaces."""
        base = self.foreground_color()
        base.setAlpha(alpha)
        return QPen(base, width)

    def _draw_highlight_outline(self, painter: QPainter, rect: QRectF, is_selected: bool, radius: float = 6.0):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        if is_selected:
            painter.setPen(self._selection_pen(2.5))
        else:
            painter.setPen(self._selection_pen(1.8, 220))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)
        painter.restore()

    def _draw_segmented_bar(
        self,
        painter,
        rect,
        actual,
        planned,
        max_value,
        colors,
    ):
        bar_h = 20
        y = rect.center().y() - bar_h / 2
        track = QRectF(
            rect.left(),
            y,
            rect.width(),
            bar_h,
        )

        painter.setPen(Qt.NoPen)
        painter.setBrush(colors["track"])
        painter.drawRoundedRect(
            track,
            10,
            10,
        )

        full_act_w = min(
            rect.width(),
            rect.width() * self.actual_m / max_value,
        )
        full_plan_w = min(
            rect.width() - full_act_w,
            rect.width() * self.planned_m / max_value,
        )

        act_hit_rect = QRectF(rect.left(), y, max(1, full_act_w), bar_h)
        plan_hit_rect = QRectF(rect.left() + full_act_w, y, max(1, full_plan_w), bar_h)

        cap_x = (
            rect.left()
            + rect.width()
            * self.capacity_m
            / max_value
        )
        cap_rect = QRectF(cap_x - 8, y - 8, 16, bar_h + 16)

        self._register_capacity_regions(
            act_rect=act_hit_rect,
            plan_rect=plan_hit_rect,
            cap_rect=cap_rect,
        )

        act_w = min(
            rect.width(),
            rect.width() * actual / max_value,
        )
        plan_w = min(
            rect.width() - act_w,
            rect.width() * planned / max_value,
        )

        act_draw_rect = QRectF(rect.left(), y, max(0, act_w), bar_h)
        plan_draw_rect = QRectF(rect.left() + act_w, y, max(0, plan_w), bar_h)

        is_h_a, is_s_a, is_f_a = self._get_item_state("actual")
        is_h_p, is_s_p, is_f_p = self._get_item_state("planned")
        is_h_c, is_s_c, is_f_c = self._get_item_state("capacity")

        if act_w > 0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._resolve_item_color(colors["actual"], "actual"))
            painter.drawRoundedRect(
                act_draw_rect,
                10,
                10,
            )
            if is_h_a or is_s_a or is_f_a:
                self._draw_highlight_outline(painter, act_draw_rect, is_s_a, 10)

        if plan_w > 0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._resolve_item_color(colors["planned"], "planned"))
            painter.drawRect(
                plan_draw_rect
            )
            if is_h_p or is_s_p or is_f_p:
                self._draw_highlight_outline(painter, plan_draw_rect, is_s_p, 4)

        cap_col = colors["planned"] if (is_h_c or is_s_c or is_f_c) else self.foreground_color()
        painter.setPen(
            QPen(
                cap_col,
                3.5 if (is_h_c or is_s_c or is_f_c) else 2.0,
            )
        )
        painter.drawLine(
            QPointF(cap_x, y - 7),
            QPointF(cap_x, y + bar_h + 7),
        )

        self._draw_capacity_text(
            painter,
            rect,
        )

    def _draw_stacked_bar(
        self,
        painter,
        rect,
        actual,
        planned,
        max_value,
        colors,
    ):
        bar_h = 30
        y = rect.center().y() - bar_h / 2

        track = QRectF(
            rect.left(),
            y,
            rect.width(),
            bar_h,
        )

        painter.setPen(Qt.NoPen)
        painter.setBrush(colors["track"])
        painter.drawRoundedRect(
            track,
            9,
            9,
        )

        full_act_w = min(
            rect.width(),
            rect.width() * self.actual_m / max_value,
        )
        full_plan_w = min(
            max(0, rect.width() - full_act_w),
            rect.width() * self.planned_m / max_value,
        )

        act_hit_rect = QRectF(rect.left(), y, max(1, full_act_w), bar_h)
        plan_hit_rect = QRectF(rect.left() + full_act_w, y, max(1, full_plan_w), bar_h)
        cap_x = rect.left() + rect.width() * self.capacity_m / max_value
        cap_rect = QRectF(cap_x - 8, y - 8, 16, bar_h + 16)

        self._register_capacity_regions(
            act_rect=act_hit_rect,
            plan_rect=plan_hit_rect,
            cap_rect=cap_rect,
        )

        act_w = min(
            rect.width(),
            rect.width() * actual / max_value,
        )
        plan_w = min(
            max(0, rect.width() - act_w),
            rect.width() * planned / max_value,
        )

        act_draw_rect = QRectF(rect.left(), y, max(0, act_w), bar_h)
        plan_draw_rect = QRectF(rect.left() + act_w, y, max(0, plan_w), bar_h)

        is_h_a, is_s_a, is_f_a = self._get_item_state("actual")
        is_h_p, is_s_p, is_f_p = self._get_item_state("planned")

        if act_w > 0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._resolve_item_color(colors["actual"], "actual"))
            painter.drawRoundedRect(
                act_draw_rect,
                9,
                9,
            )
            if is_h_a or is_s_a or is_f_a:
                self._draw_highlight_outline(painter, act_draw_rect, is_s_a, 9)

        if plan_w > 0:
            painter.setPen(Qt.NoPen)
            painter.setBrush(self._resolve_item_color(colors["planned"], "planned"))
            painter.drawRect(
                plan_draw_rect
            )
            if is_h_p or is_s_p or is_f_p:
                self._draw_highlight_outline(painter, plan_draw_rect, is_s_p, 4)

        self._draw_capacity_text(
            painter,
            rect,
        )

    def _draw_bullet(
        self,
        painter,
        rect,
        actual,
        planned,
        colors,
    ):
        max_value = max(
            self.capacity_m,
            actual + planned,
            1,
        )

        center_y = rect.center().y()

        track_rect = QRectF(
            rect.left(),
            center_y - 15,
            rect.width(),
            30,
        )

        painter.setPen(Qt.NoPen)
        painter.setBrush(colors["track"])
        painter.drawRoundedRect(
            track_rect,
            8,
            8,
        )

        full_plan_w = rect.width() * min(max_value, self.actual_m + self.planned_m) / max_value
        full_act_w = rect.width() * self.actual_m / max_value

        plan_hit_rect = QRectF(rect.left(), center_y - 9, max(1, full_plan_w), 18)
        act_hit_rect = QRectF(rect.left(), center_y - 5, max(1, full_act_w), 10)

        cap_x = (
            rect.left()
            + rect.width()
            * self.capacity_m
            / max_value
        )
        cap_rect = QRectF(cap_x - 8, center_y - 25, 16, 50)

        self._register_capacity_regions(
            act_rect=act_hit_rect,
            plan_rect=plan_hit_rect,
            cap_rect=cap_rect,
        )

        planned_total = min(
            max_value,
            actual + planned,
        )

        plan_w = (
            rect.width()
            * planned_total
            / max_value
        )
        plan_rect = QRectF(rect.left(), center_y - 9, max(0, plan_w), 18)

        actual_w = (
            rect.width()
            * actual
            / max_value
        )
        act_rect = QRectF(rect.left(), center_y - 5, max(0, actual_w), 10)

        is_h_a, is_s_a, is_f_a = self._get_item_state("actual")
        is_h_p, is_s_p, is_f_p = self._get_item_state("planned")
        is_h_c, is_s_c, is_f_c = self._get_item_state("capacity")

        p_base = QColor(
            colors["planned"].red(),
            colors["planned"].green(),
            colors["planned"].blue(),
            115,
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._resolve_item_color(p_base, "planned"))
        painter.drawRoundedRect(
            plan_rect,
            6,
            6,
        )
        if is_h_p or is_s_p or is_f_p:
            self._draw_highlight_outline(painter, plan_rect, is_s_p, 6)

        painter.setPen(Qt.NoPen)
        painter.setBrush(self._resolve_item_color(colors["actual"], "actual"))
        painter.drawRoundedRect(
            act_rect,
            5,
            5,
        )
        if is_h_a or is_s_a or is_f_a:
            self._draw_highlight_outline(painter, act_rect, is_s_a, 5)

        cap_col = colors["planned"] if (is_h_c or is_s_c or is_f_c) else self.foreground_color()
        painter.setPen(
            QPen(
                cap_col,
                4 if (is_h_c or is_s_c or is_f_c) else 3,
            )
        )
        painter.drawLine(
            QPointF(cap_x, center_y - 21),
            QPointF(cap_x, center_y + 21),
        )

        self._draw_capacity_text(
            painter,
            rect,
        )

    def _draw_gauge(
        self,
        painter,
        rect,
        actual,
        planned,
        *,
        full_circle,
        colors,
    ):
        total = actual + planned
        pct = min(
            1.25,
            total / max(
                1,
                self.capacity_m,
            ),
        )

        size = min(
            rect.width(),
            rect.height(),
        ) - 18

        center = rect.center()

        gauge_rect = QRectF(
            center.x() - size / 2,
            center.y() - size / 2,
            size,
            size,
        )

        width = 15

        if full_circle:
            start = 90 * 16
            total_span = -360 * 16
        else:
            start = 180 * 16
            total_span = -180 * 16

        act_span = int(
            total_span
            * actual
            / max(1, self.capacity_m)
        )
        plan_span = int(
            total_span
            * planned
            / max(1, self.capacity_m)
        )

        self._register_capacity_regions(
            act_rect=QRectF(gauge_rect.left(), gauge_rect.top(), gauge_rect.width() / 2, gauge_rect.height()),
            plan_rect=QRectF(gauge_rect.center().x(), gauge_rect.top(), gauge_rect.width() / 2, gauge_rect.height()),
            cap_rect=gauge_rect,
        )

        is_h_a, is_s_a, is_f_a = self._get_item_state("actual")
        is_h_p, is_s_p, is_f_p = self._get_item_state("planned")

        painter.setBrush(Qt.NoBrush)
        painter.setPen(
            QPen(
                colors["track"],
                width,
                Qt.SolidLine,
                Qt.RoundCap,
            )
        )
        painter.drawArc(
            gauge_rect,
            start,
            total_span,
        )

        if act_span != 0:
            act_pen_w = width + 4 if (is_h_a or is_s_a or is_f_a) else width
            painter.setPen(
                QPen(
                    self._resolve_item_color(colors["actual"], "actual"),
                    act_pen_w,
                    Qt.SolidLine,
                    Qt.RoundCap,
                )
            )
            painter.drawArc(
                gauge_rect,
                start,
                act_span,
            )

        if plan_span != 0:
            plan_pen_w = width + 4 if (is_h_p or is_s_p or is_f_p) else width
            painter.setPen(
                QPen(
                    self._resolve_item_color(colors["planned"], "planned"),
                    plan_pen_w,
                    Qt.SolidLine,
                    Qt.RoundCap,
                )
            )
            painter.drawArc(
                gauge_rect,
                start + act_span,
                plan_span,
            )

        painter.setPen(
            self.foreground_color()
        )

        font = painter.font()
        font.setBold(True)
        font.setPointSize(16)
        painter.setFont(font)

        painter.drawText(
            gauge_rect,
            Qt.AlignCenter,
            f"{int(pct * 100)}%",
        )

    def _draw_donut(
        self,
        painter,
        rect,
        actual,
        planned,
        colors,
    ):
        size = min(
            rect.width(),
            rect.height(),
        ) - 16

        center = rect.center()

        donut_rect = QRectF(
            center.x() - size / 2,
            center.y() - size / 2,
            size,
            size,
        )

        width = 16

        painter.setBrush(Qt.NoBrush)
        painter.setPen(
            QPen(
                colors["track"],
                width,
                Qt.SolidLine,
                Qt.RoundCap,
            )
        )
        painter.drawEllipse(donut_rect)

        maximum = max(
            self.capacity_m,
            actual + planned,
            1,
        )

        act_span = int(
            -360
            * 16
            * actual
            / maximum
        )
        plan_span = int(
            -360
            * 16
            * planned
            / maximum
        )

        self._register_capacity_regions(
            act_rect=QRectF(donut_rect.left(), donut_rect.top(), donut_rect.width() / 2, donut_rect.height()),
            plan_rect=QRectF(donut_rect.center().x(), donut_rect.top(), donut_rect.width() / 2, donut_rect.height()),
            cap_rect=donut_rect,
        )

        is_h_a, is_s_a, is_f_a = self._get_item_state("actual")
        is_h_p, is_s_p, is_f_p = self._get_item_state("planned")

        if act_span != 0:
            act_w = width + 4 if (is_h_a or is_s_a or is_f_a) else width
            painter.setPen(
                QPen(
                    self._resolve_item_color(colors["actual"], "actual"),
                    act_w,
                    Qt.SolidLine,
                    Qt.RoundCap,
                )
            )
            painter.drawArc(
                donut_rect,
                90 * 16,
                act_span,
            )

        if plan_span != 0:
            plan_w = width + 4 if (is_h_p or is_s_p or is_f_p) else width
            painter.setPen(
                QPen(
                    self._resolve_item_color(colors["planned"], "planned"),
                    plan_w,
                    Qt.SolidLine,
                    Qt.RoundCap,
                )
            )
            painter.drawArc(
                donut_rect,
                90 * 16 + act_span,
                plan_span,
            )

        painter.setPen(
            self.foreground_color()
        )

        font = painter.font()
        font.setBold(True)
        font.setPointSize(15)
        painter.setFont(font)

        painter.drawText(
            donut_rect,
            Qt.AlignCenter,
            f"{int(actual + planned)}m",
        )

    def _draw_radial_progress(
        self,
        painter,
        rect,
        actual,
        planned,
        colors,
    ):
        center = rect.center()
        outer = min(
            rect.width(),
            rect.height(),
        ) - 16

        maximum = max(
            self.capacity_m,
            actual + planned,
            1,
        )

        self._register_capacity_regions(
            act_rect=QRectF(center.x() - outer / 2, center.y() - outer / 2, outer, outer),
            plan_rect=QRectF(center.x() - (outer - 24) / 2, center.y() - (outer - 24) / 2, outer - 24, outer - 24),
            cap_rect=rect,
        )

        is_h_a, is_s_a, is_f_a = self._get_item_state("actual")
        is_h_p, is_s_p, is_f_p = self._get_item_state("planned")

        for idx, (value, color, key, is_active) in enumerate(
            (
                (actual, colors["actual"], "actual", is_h_a or is_s_a or is_f_a),
                (planned, colors["planned"], "planned", is_h_p or is_s_p or is_f_p),
            )
        ):
            size = outer - idx * 24

            if size <= 16:
                break

            ring = QRectF(
                center.x() - size / 2,
                center.y() - size / 2,
                size,
                size,
            )

            painter.setBrush(Qt.NoBrush)
            painter.setPen(
                QPen(
                    colors["track"],
                    10,
                    Qt.SolidLine,
                    Qt.RoundCap,
                )
            )
            painter.drawEllipse(ring)

            stroke_w = 14 if is_active else 10
            painter.setPen(
                QPen(
                    self._resolve_item_color(color, key),
                    stroke_w,
                    Qt.SolidLine,
                    Qt.RoundCap,
                )
            )

            span = int(
                -360
                * 16
                * min(
                    1,
                    value / max(1, maximum),
                )
            )

            painter.drawArc(
                ring,
                90 * 16,
                span,
            )

        painter.setPen(
            self.foreground_color()
        )

        font = painter.font()
        font.setBold(True)
        font.setPointSize(13)
        painter.setFont(font)

        painter.drawText(
            rect,
            Qt.AlignCenter,
            "ACT / PLAN",
        )

    def _draw_capacity_text(
        self,
        painter,
        rect,
    ):
        painter.setPen(
            self.muted_color()
        )

        font = painter.font()
        font.setPointSize(9)
        painter.setFont(font)

        painter.drawText(
            QRectF(
                rect.left(),
                rect.bottom() - 16,
                rect.width(),
                16,
            ),
            Qt.AlignRight | Qt.AlignVCenter,
            "│ Capacity",
        )


# ------------------------------------------------------------
# Task status visualization
# ------------------------------------------------------------

class AdvancedStatusChart(AnimatedDashboardChart):

    CHART_TYPES = (
        "Executive Ring",
        "Donut",
        "Pie",
        "Waffle",
        "Stacked Bar",
        "Radial Rings",
    )

    def __init__(self, parent=None):
        super().__init__(parent)

        self.chart_type = "Executive Ring"

        self.counts = {
            "planned": 0,
            "in_progress": 0,
            "blocked": 0,
            "completed": 0,
        }

        self.setMinimumHeight(165)

    def set_chart_type(self, chart_type: str, animate: bool = False):
        if chart_type not in self.CHART_TYPES:
            chart_type = "Executive Ring"

        if chart_type == self.chart_type:
            if not animate and (self._animation_progress != 1.0 or self._animation.state() == QVariantAnimation.Running):
                self._animation.stop()
                self._animation_progress = 1.0
                self.update()
            return

        self.chart_type = chart_type

        if chart_type == "Stacked Bar":
            self.setMinimumHeight(95)
        else:
            self.setMinimumHeight(165)

        if animate and self._animations_enabled:
            self.animate_update()
        else:
            self._animation.stop()
            self._animation_progress = 1.0
            self.update()

        self._update_accessible_state()
        self.updateGeometry()

    def set_render_mode(self, chart_type: str):
        """Sets the presentation chart type/style immediately without restarting data animation."""
        self.set_chart_type(chart_type, animate=False)

    def set_counts(
        self,
        planned,
        in_progress,
        blocked,
        completed,
    ):
        new_counts = {
            "planned": max(0, int(planned)),
            "in_progress": max(
                0,
                int(in_progress),
            ),
            "blocked": max(0, int(blocked)),
            "completed": max(
                0,
                int(completed),
            ),
        }

        if new_counts == self.counts:
            return

        self.counts = new_counts
        self.animate_update()

    def _segments(self):
        colors = self.semantic_colors()

        return [
            (
                "Planned",
                self.counts["planned"],
                colors["planned"],
                "planned",
            ),
            (
                "In Progress",
                self.counts["in_progress"],
                colors["actual"],
                "in_progress",
            ),
            (
                "Blocked",
                self.counts["blocked"],
                colors["blocked"],
                "blocked",
            ),
            (
                "Completed",
                self.counts["completed"],
                colors["completed"],
                "completed",
            ),
        ]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.Antialiasing
        )

        # Clear hit regions per paint pass
        self._hit_regions = []

        rect = QRectF(
            10,
            8,
            max(10, self.width() - 20),
            max(10, self.height() - 16),
        )

        if self.chart_type == "Executive Ring":
            self._draw_ring(
                painter,
                rect,
                executive=True,
            )

        elif self.chart_type == "Donut":
            self._draw_ring(
                painter,
                rect,
                executive=False,
            )

        elif self.chart_type == "Pie":
            self._draw_pie(
                painter,
                rect,
            )

        elif self.chart_type == "Waffle":
            self._draw_waffle(
                painter,
                rect,
            )

        elif self.chart_type == "Stacked Bar":
            self._draw_stacked_bar(
                painter,
                rect,
            )

        else:
            self._draw_radial_rings(
                painter,
                rect,
            )

        self._draw_focus_ring(painter)

    def _draw_ring(
        self,
        painter,
        rect,
        *,
        executive,
    ):
        segments = self._segments()
        total = sum(v for _, v, _, _ in segments)

        size = min(
            rect.width(),
            rect.height(),
        ) - 12

        center = rect.center()

        ring = QRectF(
            center.x() - size / 2,
            center.y() - size / 2,
            size,
            size,
        )

        width = 18 if executive else 13
        outer_r = size / 2 + width / 2
        inner_r = max(0, size / 2 - width / 2)

        colors = self.semantic_colors()

        painter.setBrush(Qt.NoBrush)
        painter.setPen(
            QPen(
                colors["track"],
                width,
                Qt.SolidLine,
                Qt.RoundCap,
            )
        )
        painter.drawEllipse(ring)

        active_label = None
        active_count = None
        active_pct = None

        if total > 0:
            start = 90 * 16

            for name, count, color, key in segments:
                if count <= 0:
                    continue

                full_span = int(
                    -360
                    * 16
                    * count
                    / total
                )

                span = int(
                    full_span
                    * self._animation_progress
                )

                pct = round((count / total) * 100.0, 1)
                tt = (
                    f"{name} Tasks\n"
                    f"• Count: {count} {'task' if count == 1 else 'tasks'}\n"
                    f"• Share: {pct}% of tracked tasks ({total} total)"
                )

                # Register angular hit region based on full angles
                self._hit_regions.append(
                    ChartHitRegion(
                        key=key,
                        label=name,
                        primary_value=count,
                        percentage=pct,
                        tooltip_text=tt,
                        accessible_text=f"{name} Tasks: {count} tasks, {pct}% of tracked tasks",
                        center=center,
                        radius=outer_r + 4,
                        inner_radius=inner_r - 4,
                        start_angle_deg=start / 16.0,
                        span_angle_deg=full_span / 16.0,
                        color=color,
                    )
                )

                is_h, is_s, is_f = self._get_item_state(key)
                if is_h or is_s or is_f:
                    active_label = name
                    active_count = count
                    active_pct = pct

                stroke_w = width + 5 if (is_h or is_s or is_f) else width
                painter.setPen(
                    QPen(
                        self._resolve_item_color(color, key),
                        stroke_w,
                        Qt.SolidLine,
                        Qt.RoundCap,
                    )
                )

                painter.drawArc(
                    ring,
                    start,
                    span,
                )

                start += full_span

        painter.setPen(
            self.foreground_color()
        )

        font = painter.font()
        font.setBold(True)
        font.setPointSize(
            20 if executive else 15
        )
        painter.setFont(font)

        center_display_text = str(active_count if active_count is not None else total)
        painter.drawText(
            ring,
            Qt.AlignCenter,
            center_display_text,
        )

        small = painter.font()
        small.setBold(False)
        small.setPointSize(8)
        painter.setFont(small)

        sub_rect = QRectF(
            ring.left(),
            ring.center().y() + (18 if executive else 14),
            ring.width(),
            20,
        )

        painter.setPen(
            self.muted_color()
        )

        sub_label = f"{active_label.upper()} ({active_pct}%)" if active_label else ("TODAY" if executive else "TOTAL")
        painter.drawText(
            sub_rect,
            Qt.AlignCenter,
            sub_label,
        )

    def _draw_pie(
        self,
        painter,
        rect,
    ):
        segments = self._segments()
        total = sum(v for _, v, _, _ in segments)

        if total <= 0:
            self._draw_empty(
                painter,
                rect,
            )
            return

        size = min(
            rect.width(),
            rect.height(),
        ) - 12

        center = rect.center()

        pie_rect = QRectF(
            center.x() - size / 2,
            center.y() - size / 2,
            size,
            size,
        )

        start = 90 * 16

        for name, count, color, key in segments:
            if count <= 0:
                continue

            full_span = int(
                -360
                * 16
                * count
                / total
            )

            span = int(
                full_span
                * self._animation_progress
            )

            pct = round((count / total) * 100.0, 1)
            tt = (
                f"{name} Tasks\n"
                f"• Count: {count} {'task' if count == 1 else 'tasks'}\n"
                f"• Share: {pct}% of tracked tasks ({total} total)"
            )

            self._hit_regions.append(
                ChartHitRegion(
                    key=key,
                    label=name,
                    primary_value=count,
                    percentage=pct,
                    tooltip_text=tt,
                    accessible_text=f"{name} Tasks: {count} tasks, {pct}% of tracked tasks",
                    center=center,
                    radius=size / 2,
                    inner_radius=0,
                    start_angle_deg=start / 16.0,
                    span_angle_deg=full_span / 16.0,
                    color=color,
                )
            )

            is_h, is_s, is_f = self._get_item_state(key)

            if is_s:
                painter.setPen(self._selection_pen(2.5))
            elif is_h or is_f:
                painter.setPen(self._selection_pen(1.8, 220))
            else:
                painter.setPen(Qt.NoPen)

            painter.setBrush(self._resolve_item_color(color, key))

            painter.drawPie(
                pie_rect,
                start,
                span,
            )

            start += full_span

    def _draw_waffle(
        self,
        painter,
        rect,
    ):
        segments = self._segments()
        total = sum(v for _, v, _, _ in segments)

        if total <= 0:
            self._draw_empty(
                painter,
                rect,
            )
            return

        cols = 10
        rows = 5
        cells = cols * rows

        cell_values = []
        cell_keys = []
        # Per-segment metadata for the per-cell hit regions registered below.
        # (The old code registered the WHOLE chart rect once per segment, so
        # hit-testing always landed on the last-appended segment.)
        segment_meta = {}

        for name, count, color, key in segments:
            pct = round((count / total) * 100.0, 1)
            tt = (
                f"{name} Tasks\n"
                f"• Count: {count} {'task' if count == 1 else 'tasks'}\n"
                f"• Share: {pct}% of tracked tasks ({total} total)"
            )
            segment_meta[key] = {
                "label": name,
                "value": count,
                "pct": pct,
                "tooltip": tt,
                "accessible": f"{name} Tasks: {count} tasks, {pct}% of tracked tasks",
                "color": color,
            }

            n = round(
                cells
                * count
                / total
                * self._animation_progress
            )
            cell_values.extend([color] * n)
            cell_keys.extend([key] * n)

        cell_values = cell_values[:cells]
        cell_keys = cell_keys[:cells]

        cell_w = rect.width() / cols
        cell_h = rect.height() / rows

        for idx in range(cells):
            row = idx // cols
            col = idx % cols

            x = rect.left() + col * cell_w
            y = rect.top() + row * cell_h

            cell_rect = QRectF(
                x + 3,
                y + 3,
                max(2, cell_w - 6),
                max(2, cell_h - 6),
            )

            k = cell_keys[idx] if idx < len(cell_keys) else None
            if k and k in segment_meta:
                meta = segment_meta[k]
                self._hit_regions.append(
                    ChartHitRegion(
                        key=k,
                        label=meta["label"],
                        primary_value=meta["value"],
                        percentage=meta["pct"],
                        tooltip_text=meta["tooltip"],
                        accessible_text=meta["accessible"],
                        rect=cell_rect,
                        color=meta["color"],
                    )
                )
            is_h, is_s, is_f = self._get_item_state(k) if k else (False, False, False)

            if is_s:
                painter.setPen(self._selection_pen(1.8))
            elif is_h or is_f:
                painter.setPen(self._selection_pen(1.2, 200))
            else:
                painter.setPen(Qt.NoPen)

            painter.setBrush(
                self._resolve_item_color(cell_values[idx], k)
                if idx < len(cell_values)
                else self.semantic_colors()["track"]
            )

            painter.drawRoundedRect(
                cell_rect,
                4,
                4,
            )

    def _draw_stacked_bar(
        self,
        painter,
        rect,
    ):
        segments = self._segments()
        total = sum(v for _, v, _, _ in segments)

        if total <= 0:
            self._draw_empty(
                painter,
                rect,
            )
            return

        bar = QRectF(
            rect.left(),
            rect.center().y() - 16,
            rect.width(),
            32,
        )

        painter.setPen(Qt.NoPen)
        painter.setBrush(
            self.semantic_colors()["track"]
        )
        painter.drawRoundedRect(
            bar,
            9,
            9,
        )

        x = bar.left()

        for name, count, color, key in segments:
            if count <= 0:
                continue

            width = (
                bar.width()
                * count
                / total
                * self._animation_progress
            )

            seg_rect = QRectF(
                x,
                bar.top(),
                width,
                bar.height(),
            )

            pct = round((count / total) * 100.0, 1)
            tt = (
                f"{name} Tasks\n"
                f"• Count: {count} {'task' if count == 1 else 'tasks'}\n"
                f"• Share: {pct}% of tracked tasks ({total} total)"
            )

            self._hit_regions.append(
                ChartHitRegion(
                    key=key,
                    label=name,
                    primary_value=count,
                    percentage=pct,
                    tooltip_text=tt,
                    accessible_text=f"{name} Tasks: {count} tasks, {pct}% of tracked tasks",
                    rect=seg_rect,
                    color=color,
                )
            )

            is_h, is_s, is_f = self._get_item_state(key)

            if is_s:
                painter.setPen(self._selection_pen(2.0))
            elif is_h or is_f:
                painter.setPen(self._selection_pen(1.5, 220))
            else:
                painter.setPen(Qt.NoPen)

            painter.setBrush(self._resolve_item_color(color, key))
            painter.drawRect(
                seg_rect
            )

            x += width

    def _draw_radial_rings(
        self,
        painter,
        rect,
    ):
        segments = self._segments()

        maximum = max(
            1,
            max(v for _, v, _, _ in segments),
        )

        center = rect.center()
        outer = min(
            rect.width(),
            rect.height(),
        ) - 14

        total = sum(v for _, v, _, _ in segments)

        for idx, (name, value, color, key) in enumerate(
            segments
        ):
            size = outer - idx * 24

            if size <= 18:
                break

            ring = QRectF(
                center.x() - size / 2,
                center.y() - size / 2,
                size,
                size,
            )

            pct = round((value / max(1, total)) * 100.0, 1)
            tt = (
                f"{name} Tasks\n"
                f"• Count: {value} {'task' if value == 1 else 'tasks'}\n"
                f"• Share: {pct}% of tracked tasks ({total} total)"
            )

            self._hit_regions.append(
                ChartHitRegion(
                    key=key,
                    label=name,
                    primary_value=value,
                    percentage=pct,
                    tooltip_text=tt,
                    accessible_text=f"{name} Tasks: {value} tasks, {pct}% of tracked tasks",
                    center=center,
                    radius=size / 2 + 5,
                    inner_radius=max(0, size / 2 - 5),
                    color=color,
                )
            )

            is_h, is_s, is_f = self._get_item_state(key)

            painter.setBrush(Qt.NoBrush)
            painter.setPen(
                QPen(
                    self.semantic_colors()["track"],
                    8,
                    Qt.SolidLine,
                    Qt.RoundCap,
                )
            )
            painter.drawEllipse(ring)

            stroke_w = 12 if (is_h or is_s or is_f) else 8
            painter.setPen(
                QPen(
                    self._resolve_item_color(color, key),
                    stroke_w,
                    Qt.SolidLine,
                    Qt.RoundCap,
                )
            )

            span = int(
                -360
                * 16
                * value
                / maximum
                * self._animation_progress
            )

            painter.drawArc(
                ring,
                90 * 16,
                span,
            )

    def _draw_empty(
        self,
        painter,
        rect,
    ):
        # Visual polish (M5 S5.1.2): explicit caption typography (11pt,
        # muted) so the empty state holds hierarchy in both themes.
        painter.save()
        caption = painter.font()
        caption.setPointSize(11)
        painter.setFont(caption)
        painter.setPen(
            self.muted_color()
        )

        painter.drawText(
            rect,
            Qt.AlignCenter,
            "No task activity",
        )
        painter.restore()


# ------------------------------------------------------------
# Activity / Trend visualization
# ------------------------------------------------------------

class AdvancedWeeklyActivityChart(
    AnimatedDashboardChart
):

    CHART_TYPES = (
        "Grouped Bar",
        "Stacked Bar",
        "Line",
        "Smooth Line",
        "Area",
        "Lollipop",
        "Step Line",
        "Combo",
    )

    def __init__(self, parent=None):
        super().__init__(parent)

        self.chart_type = "Grouped Bar"
        self.daily_data: List[
            Tuple[str, int, int]
        ] = []

        self.setMinimumHeight(190)

    def set_chart_type(self, chart_type: str, animate: bool = False):
        if chart_type not in self.CHART_TYPES:
            chart_type = "Grouped Bar"

        if chart_type == self.chart_type:
            if not animate and (self._animation_progress != 1.0 or self._animation.state() == QVariantAnimation.Running):
                self._animation.stop()
                self._animation_progress = 1.0
                self.update()
            return

        self.chart_type = chart_type

        if animate and self._animations_enabled:
            self.animate_update()
        else:
            self._animation.stop()
            self._animation_progress = 1.0
            self.update()

        self._update_accessible_state()
        self.updateGeometry()

    def set_render_mode(self, chart_type: str):
        """Sets the presentation chart type/style immediately without restarting data animation."""
        self.set_chart_type(chart_type, animate=False)

    def set_daily_data(
        self,
        data: List[Tuple[str, int, int]],
    ):
        data = list(data)

        if data == self.daily_data:
            return

        self.daily_data = data
        if self._selected_key is not None and (not isinstance(self._selected_key, int) or self._selected_key >= len(data)):
            self.clear_selection()

        self.animate_update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.Antialiasing
        )

        # Clear hit regions per paint pass
        self._hit_regions = []

        if not self.daily_data:
            # Visual polish (M5 S5.1.2): explicit caption typography (11pt,
            # muted) so the empty state holds hierarchy in both themes.
            painter.save()
            caption = painter.font()
            caption.setPointSize(11)
            painter.setFont(caption)
            painter.setPen(
                self.muted_color()
            )
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "No execution history",
            )
            painter.restore()
            return

        # Visual polish (M5 S5.1.1): chart insets snapped to the shared
        # spacing scale (32/12/12/32); data mapping unchanged.
        left = 32
        right = 12
        top = 12
        bottom = 32

        chart = QRectF(
            left,
            top,
            max(10, self.width() - left - right),
            max(10, self.height() - top - bottom),
        )

        max_value = max(
            1,
            max(
                max(completed, planned)
                for _, completed, planned
                in self.daily_data
            ),
        )

        # Register column hit regions for all days
        count = len(self.daily_data)
        col_w = chart.width() / max(1, count)

        for idx, (day, completed, planned) in enumerate(self.daily_data):
            col_x = self._x_for(chart, idx)
            col_rect = QRectF(col_x - col_w / 2, chart.top(), col_w, chart.height())

            variance = completed - planned
            var_str = f"+{variance}" if variance > 0 else f"{variance}"
            rate_str = f"{round((completed / planned) * 100.0, 1)}%" if planned > 0 else ("100%" if completed > 0 else "0%")

            tt = (
                f"{day}\n"
                f"• Completed: {completed} tasks\n"
                f"• Planned: {planned} tasks\n"
                f"• Variance: {var_str}\n"
                f"• Completion Rate: {rate_str}"
            )

            self._hit_regions.append(
                ChartHitRegion(
                    key=idx,
                    label=day,
                    primary_value=completed,
                    secondary_value=planned,
                    percentage=round((completed / planned) * 100.0, 1) if planned > 0 else 0.0,
                    tooltip_text=tt,
                    accessible_text=f"{day}: {completed} completed, {planned} planned, variance {var_str}",
                    rect=col_rect,
                    metadata={"day": day, "completed": completed, "planned": planned, "variance": variance},
                )
            )

        self._draw_grid(
            painter,
            chart,
            max_value,
        )

        # Draw inspection highlight column behind data
        if self._has_active_inspection():
            active_idx = self._selected_key if self._selected_key is not None else self._hovered_key
            if active_idx is None and self._focused_index is not None and 0 <= self._focused_index < len(self._hit_regions):
                active_idx = self._hit_regions[self._focused_index].key

            if isinstance(active_idx, int) and 0 <= active_idx < len(self.daily_data):
                col_x = self._x_for(chart, active_idx)
                band_rect = QRectF(col_x - col_w / 2 + 1, chart.top(), col_w - 2, chart.height())
                painter.save()
                painter.setPen(Qt.NoPen)
                pal = self.palette()
                is_dark = pal.color(pal.ColorRole.Window).lightness() < 128
                highlight_bg = QColor(255, 255, 255, 22) if is_dark else QColor(0, 0, 0, 14)
                painter.setBrush(highlight_bg)
                painter.drawRoundedRect(band_rect, 4, 4)
                painter.restore()

        if self.chart_type == "Grouped Bar":
            self._draw_grouped_bars(
                painter,
                chart,
                max_value,
            )

        elif self.chart_type == "Stacked Bar":
            self._draw_stacked_bars(
                painter,
                chart,
                max_value,
            )

        elif self.chart_type in (
            "Line",
            "Smooth Line",
            "Area",
            "Step Line",
        ):
            self._draw_lines(
                painter,
                chart,
                max_value,
            )

        elif self.chart_type == "Lollipop":
            self._draw_lollipop(
                painter,
                chart,
                max_value,
            )

        else:
            self._draw_combo(
                painter,
                chart,
                max_value,
            )

        self._draw_day_labels(
            painter,
            chart,
        )

        self._draw_focus_ring(painter)

    def _x_for(
        self,
        chart,
        index,
    ):
        count = max(
            1,
            len(self.daily_data),
        )

        return (
            chart.left()
            + chart.width()
            * (index + 0.5)
            / count
        )

    def _y_for(
        self,
        chart,
        value,
        maximum,
    ):
        return (
            chart.bottom()
            - chart.height()
            * value
            / max(1, maximum)
            * self._animation_progress
        )

    def _draw_grid(
        self,
        painter,
        chart,
        maximum,
    ):
        colors = self.semantic_colors()
        painter.setPen(
            QPen(
                colors["grid"],
                1,
                Qt.DotLine,
            )
        )

        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        ticks = 4
        for i in range(ticks + 1):
            y = (
                chart.bottom()
                - chart.height() * i / ticks
            )
            painter.drawLine(
                QPointF(chart.left(), y),
                QPointF(chart.right(), y),
            )

            val = int(maximum * i / ticks)
            painter.setPen(
                self.muted_color()
            )
            painter.drawText(
                QRectF(
                    0,
                    y - 8,
                    max(24.0, chart.left() - 6),
                    16,
                ),
                Qt.AlignRight,
                str(val),
            )
            painter.setPen(
                QPen(
                    colors["grid"],
                    1,
                    Qt.DotLine,
                )
            )



    def _draw_grouped_bars(
        self,
        painter,
        chart,
        maximum,
    ):
        colors = self.semantic_colors()
        count = len(self.daily_data)

        group_w = chart.width() / max(1, count)
        bar_w = min(
            16,
            group_w * 0.28,
        )

        for idx, (
            _day,
            completed,
            planned,
        ) in enumerate(self.daily_data):
            center_x = self._x_for(
                chart,
                idx,
            )

            p_h = (
                chart.height()
                * planned
                / maximum
                * self._animation_progress
            )

            c_h = (
                chart.height()
                * completed
                / maximum
                * self._animation_progress
            )

            p_rect = QRectF(
                center_x - bar_w - 2,
                chart.bottom() - p_h,
                bar_w,
                p_h,
            )
            c_rect = QRectF(
                center_x + 2,
                chart.bottom() - c_h,
                bar_w,
                c_h,
            )

            is_h, is_s, is_f = self._get_item_state(idx)

            painter.setPen(Qt.NoPen)
            painter.setBrush(self._resolve_item_color(colors["planned"], idx))
            painter.drawRoundedRect(
                p_rect,
                4,
                4,
            )
            if is_s:
                painter.setPen(self._selection_pen(2.0))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(p_rect, 4, 4)
            elif is_h or is_f:
                painter.setPen(self._selection_pen(1.5, 200))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(p_rect, 4, 4)

            painter.setPen(Qt.NoPen)
            painter.setBrush(self._resolve_item_color(colors["actual"], idx))
            painter.drawRoundedRect(
                c_rect,
                4,
                4,
            )
            if is_s:
                painter.setPen(self._selection_pen(2.0))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(c_rect, 4, 4)
            elif is_h or is_f:
                painter.setPen(self._selection_pen(1.5, 200))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(c_rect, 4, 4)

    def _draw_stacked_bars(
        self,
        painter,
        chart,
        maximum,
    ):
        colors = self.semantic_colors()

        stack_max = max(
            1,
            max(
                completed + planned
                for _day, completed, planned
                in self.daily_data
            ),
        )

        count = len(self.daily_data)
        group_w = chart.width() / max(1, count)
        bar_w = min(
            24,
            group_w * 0.48,
        )

        for idx, (
            _day,
            completed,
            planned,
        ) in enumerate(self.daily_data):
            center_x = self._x_for(
                chart,
                idx,
            )

            c_h = (
                chart.height()
                * completed
                / stack_max
                * self._animation_progress
            )

            p_h = (
                chart.height()
                * planned
                / stack_max
                * self._animation_progress
            )

            c_rect = QRectF(
                center_x - bar_w / 2,
                chart.bottom() - c_h,
                bar_w,
                c_h,
            )
            p_rect = QRectF(
                center_x - bar_w / 2,
                chart.bottom() - c_h - p_h,
                bar_w,
                p_h,
            )

            is_h, is_s, is_f = self._get_item_state(idx)

            painter.setPen(Qt.NoPen)
            painter.setBrush(self._resolve_item_color(colors["actual"], idx))
            painter.drawRoundedRect(
                c_rect,
                5,
                5,
            )

            painter.setBrush(self._resolve_item_color(colors["planned"], idx))
            painter.drawRect(
                p_rect
            )

            if is_s:
                painter.setPen(self._selection_pen(2.0))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(
                    QRectF(center_x - bar_w / 2, chart.bottom() - c_h - p_h, bar_w, c_h + p_h),
                    5,
                    5,
                )
            elif is_h or is_f:
                painter.setPen(self._selection_pen(1.5, 200))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(
                    QRectF(center_x - bar_w / 2, chart.bottom() - c_h - p_h, bar_w, c_h + p_h),
                    5,
                    5,
                )

    def _series_points(
        self,
        chart,
        maximum,
        completed,
    ):
        points = []

        for idx, row in enumerate(
            self.daily_data
        ):
            value = row[1] if completed else row[2]

            points.append(
                QPointF(
                    self._x_for(chart, idx),
                    self._y_for(
                        chart,
                        value,
                        maximum,
                    ),
                )
            )

        return points

    def _smooth_path(
        self,
        points,
    ):
        path = QPainterPath()

        if not points:
            return path

        path.moveTo(points[0])

        if len(points) == 1:
            return path

        for idx in range(
            1,
            len(points),
        ):
            prev = points[idx - 1]
            cur = points[idx]

            mid_x = (
                prev.x() + cur.x()
            ) / 2

            path.cubicTo(
                QPointF(mid_x, prev.y()),
                QPointF(mid_x, cur.y()),
                cur,
            )

        return path

    def _plain_path(
        self,
        points,
        step=False,
    ):
        path = QPainterPath()

        if not points:
            return path

        path.moveTo(points[0])

        for point in points[1:]:
            if step:
                path.lineTo(
                    QPointF(
                        point.x(),
                        path.currentPosition().y(),
                    )
                )

            path.lineTo(point)

        return path

    def _draw_lines(
        self,
        painter,
        chart,
        maximum,
    ):
        colors = self.semantic_colors()

        completed = self._series_points(
            chart,
            maximum,
            True,
        )
        planned = self._series_points(
            chart,
            maximum,
            False,
        )

        smooth = (
            self.chart_type == "Smooth Line"
        )

        step = (
            self.chart_type == "Step Line"
        )

        p_path = (
            self._smooth_path(planned)
            if smooth
            else self._plain_path(
                planned,
                step=step,
            )
        )

        c_path = (
            self._smooth_path(completed)
            if smooth
            else self._plain_path(
                completed,
                step=step,
            )
        )

        if self.chart_type == "Area":
            for points, color in (
                (planned, colors["planned"]),
                (completed, colors["actual"]),
            ):
                if not points:
                    continue

                area = QPainterPath()
                area.moveTo(
                    points[0].x(),
                    chart.bottom(),
                )

                for point in points:
                    area.lineTo(point)

                area.lineTo(
                    points[-1].x(),
                    chart.bottom(),
                )
                area.closeSubpath()

                fill = QColor(color)
                fill.setAlpha(48)

                painter.fillPath(
                    area,
                    fill,
                )

        painter.setBrush(Qt.NoBrush)

        painter.setPen(
            QPen(
                colors["planned"],
                2.5,
                Qt.SolidLine,
                Qt.RoundCap,
                Qt.RoundJoin,
            )
        )
        painter.drawPath(p_path)

        painter.setPen(
            QPen(
                colors["actual"],
                2.5,
                Qt.SolidLine,
                Qt.RoundCap,
                Qt.RoundJoin,
            )
        )
        painter.drawPath(c_path)

        # Draw inspection vertical guide line
        active_idx = self._selected_key if self._selected_key is not None else self._hovered_key
        if active_idx is None and self._focused_index is not None and 0 <= self._focused_index < len(self._hit_regions):
            active_idx = self._hit_regions[self._focused_index].key

        if isinstance(active_idx, int) and 0 <= active_idx < len(self.daily_data):
            guide_x = self._x_for(chart, active_idx)
            painter.save()
            painter.setPen(QPen(colors["planned"], 1.5, Qt.DashLine))
            painter.drawLine(QPointF(guide_x, chart.top()), QPointF(guide_x, chart.bottom()))
            painter.restore()

        for points, color, is_comp in (
            (planned, colors["planned"], False),
            (completed, colors["actual"], True),
        ):
            for idx, point in enumerate(points):
                is_h, is_s, is_f = self._get_item_state(idx)
                is_active = is_h or is_s or is_f

                painter.setPen(Qt.NoPen)
                painter.setBrush(color)

                if is_active:
                    # Enlarge active dot with outer ring
                    painter.save()
                    painter.setPen(self._selection_pen(2.0))
                    painter.setBrush(color.lighter(120))
                    painter.drawEllipse(point, 6.0, 6.0)
                    painter.restore()
                else:
                    painter.drawEllipse(
                        point,
                        3.5,
                        3.5,
                    )

    def _draw_lollipop(
        self,
        painter,
        chart,
        maximum,
    ):
        colors = self.semantic_colors()

        for idx, (
            _day,
            completed,
            planned,
        ) in enumerate(self.daily_data):
            x = self._x_for(chart, idx)
            is_h, is_s, is_f = self._get_item_state(idx)
            is_active = is_h or is_s or is_f

            for value, color, offset in (
                (
                    planned,
                    colors["planned"],
                    -5,
                ),
                (
                    completed,
                    colors["actual"],
                    5,
                ),
            ):
                y = self._y_for(
                    chart,
                    value,
                    maximum,
                )

                stem_w = 3.5 if is_active else 2.0
                painter.setPen(
                    QPen(
                        self._resolve_item_color(color, idx),
                        stem_w,
                    )
                )

                painter.drawLine(
                    QPointF(
                        x + offset,
                        chart.bottom(),
                    ),
                    QPointF(
                        x + offset,
                        y,
                    ),
                )

                painter.setBrush(self._resolve_item_color(color, idx))

                if is_active:
                    painter.setPen(self._selection_pen(2.0))
                    painter.drawEllipse(
                        QPointF(
                            x + offset,
                            y,
                        ),
                        7.0,
                        7.0,
                    )
                else:
                    painter.setPen(Qt.NoPen)
                    painter.drawEllipse(
                        QPointF(
                            x + offset,
                            y,
                        ),
                        5,
                        5,
                    )

    def _draw_combo(
        self,
        painter,
        chart,
        maximum,
    ):
        colors = self.semantic_colors()

        count = len(self.daily_data)
        group_w = chart.width() / max(1, count)
        bar_w = min(
            20,
            group_w * 0.38,
        )

        completed_points = []

        for idx, (
            _day,
            completed,
            planned,
        ) in enumerate(self.daily_data):
            x = self._x_for(
                chart,
                idx,
            )

            p_h = (
                chart.height()
                * planned
                / maximum
                * self._animation_progress
            )

            bar_rect = QRectF(
                x - bar_w / 2,
                chart.bottom() - p_h,
                bar_w,
                p_h,
            )

            is_h, is_s, is_f = self._get_item_state(idx)

            painter.setPen(Qt.NoPen)
            painter.setBrush(self._resolve_item_color(colors["planned"], idx))
            painter.drawRoundedRect(
                bar_rect,
                4,
                4,
            )

            if is_s:
                painter.setPen(self._selection_pen(2.0))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(bar_rect, 4, 4)
            elif is_h or is_f:
                painter.setPen(self._selection_pen(1.5, 200))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(bar_rect, 4, 4)

            completed_points.append(
                QPointF(
                    x,
                    self._y_for(
                        chart,
                        completed,
                        maximum,
                    ),
                )
            )

        path = self._smooth_path(
            completed_points
        )

        painter.setPen(
            QPen(
                colors["actual"],
                3,
                Qt.SolidLine,
                Qt.RoundCap,
                Qt.RoundJoin,
            )
        )
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        for idx, point in enumerate(completed_points):
            is_h, is_s, is_f = self._get_item_state(idx)
            if is_h or is_s or is_f:
                painter.setPen(self._selection_pen(2.0))
                painter.setBrush(colors["actual"].lighter(120))
                painter.drawEllipse(
                    point,
                    6.5,
                    6.5,
                )
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(colors["actual"])
                painter.drawEllipse(
                    point,
                    4,
                    4,
                )

    def _draw_day_labels(
        self,
        painter,
        chart,
    ):
        painter.setPen(
            self.muted_color()
        )

        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        count = len(self.daily_data)

        if count <= 0:
            return

        group_w = chart.width() / count

        target_label_width = 48.0
        max_visible_labels = max(
            2,
            int(
                chart.width()
                / target_label_width
            ),
        )

        step = max(
            1,
            (count + max_visible_labels - 1)
            // max_visible_labels,
        )

        shown_idxs = [
            idx
            for idx in range(count)
            if idx == 0 or idx == count - 1 or idx % step == 0
        ]
        # The final label sits (count-1) % step groups after the previous
        # shown one; drop that crowded predecessor so the two can't collide.
        if (
            count - 1 in shown_idxs
            and (count - 1) % step != 0
            and len(shown_idxs) > 1
        ):
            shown_idxs.remove(shown_idxs[-2])

        for idx in shown_idxs:
            day = self.daily_data[idx][0]

            label_width = max(
                group_w,
                min(
                    74.0,
                    chart.width()
                    / max(
                        2,
                        max_visible_labels,
                    ),
                ),
            )

            center_x = self._x_for(
                chart,
                idx,
            )

            is_h, is_s, is_f = self._get_item_state(idx)
            if is_s:
                painter.setPen(self.accent_color())
                f_bold = QFont(painter.font())
                f_bold.setBold(True)
                painter.setFont(f_bold)
            elif is_h or is_f:
                painter.setPen(self.foreground_color())
                painter.setFont(font)
            else:
                painter.setPen(self.muted_color())
                painter.setFont(font)

            # Visual polish (M5 S5.1.2): 4px label gap sits on the spacing
            # scale. Each label is elided to its true slot (spacing between
            # shown labels), so adjacent labels can never overlap.
            slot_w = min(label_width, group_w * max(1, step))
            elided_day = painter.fontMetrics().elidedText(
                day, Qt.ElideMiddle, int(slot_w)
            )
            painter.drawText(
                QRectF(
                    center_x - slot_w / 2,
                    chart.bottom() + 4,
                    slot_w,
                    20,
                ),
                Qt.AlignCenter,
                elided_day,
            )


# ------------------------------------------------------------
# Effort Variance visualization (Phase 2F Decision Cockpit)
# ------------------------------------------------------------

class AdvancedEffortVarianceChart(AnimatedDashboardChart):
    """
    Effort Variance Chart (Phase 2F Decision Cockpit).
    Visualizes Planned Effort vs. Actual Effort over time (7D / 14D / 30D / 90D).
    Supports Grouped Bar, Stacked Bar, Line, and Area visual presentations.
    """

    CHART_TYPES = (
        "Grouped Bar",
        "Stacked Bar",
        "Line",
        "Area",
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.chart_type = "Grouped Bar"
        self.daily_data: List[Tuple[str, int, int]] = []  # (label, planned_mins, actual_mins)
        self.setMinimumHeight(190)

    def set_chart_type(self, chart_type: str, animate: bool = False):
        if chart_type not in self.CHART_TYPES:
            chart_type = "Grouped Bar"

        if chart_type == self.chart_type:
            if not animate and (self._animation_progress != 1.0 or self._animation.state() == QVariantAnimation.Running):
                self._animation.stop()
                self._animation_progress = 1.0
                self.update()
            return

        self.chart_type = chart_type

        if animate and self._animations_enabled:
            self.animate_update()
        else:
            self._animation.stop()
            self._animation_progress = 1.0
            self.update()

        self._update_accessible_state()
        self.updateGeometry()

    def set_render_mode(self, chart_type: str):
        self.set_chart_type(chart_type, animate=False)

    def set_daily_data(self, data: List[Tuple[str, int, int]]):
        data = list(data)
        if data == self.daily_data:
            return

        self.daily_data = data
        if self._selected_key is not None and (not isinstance(self._selected_key, int) or self._selected_key >= len(data)):
            self.clear_selection()

        self.animate_update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        self._hit_regions = []

        if not self.daily_data:
            # Visual polish (M5 S5.1.2): explicit caption typography (11pt,
            # muted) so the empty state holds hierarchy in both themes.
            painter.save()
            caption = painter.font()
            caption.setPointSize(11)
            painter.setFont(caption)
            painter.setPen(self.muted_color())
            painter.drawText(self.rect(), Qt.AlignCenter, "No effort history")
            painter.restore()
            return

        # Visual polish (M5 S5.1.1): chart insets snapped to the shared
        # spacing scale (40/12/12/32); data mapping unchanged.
        left = 40
        right = 12
        top = 12
        bottom = 32

        chart = QRectF(
            left,
            top,
            max(10, self.width() - left - right),
            max(10, self.height() - top - bottom),
        )

        max_value = max(
            60,
            max(
                max(planned, actual)
                for _, planned, actual in self.daily_data
            )
        )

        count = len(self.daily_data)
        col_w = chart.width() / max(1, count)

        for idx, (day, planned, actual) in enumerate(self.daily_data):
            col_x = self._x_for(chart, idx)
            col_rect = QRectF(col_x - col_w / 2, chart.top(), col_w, chart.height())

            diff = actual - planned
            diff_str = f"+{_format_m(diff)}" if diff > 0 else (f"-{_format_m(abs(diff))}" if diff < 0 else "0m")
            status_text = "Over Plan" if diff > 0 else ("Under Plan" if diff < 0 else "On Plan")

            tt = (
                f"{day}\n"
                f"• Planned Effort: {_format_m(planned)}\n"
                f"• Actual Logged: {_format_m(actual)}\n"
                f"• Variance: {diff_str} ({status_text})"
            )

            self._hit_regions.append(
                ChartHitRegion(
                    key=idx,
                    label=day,
                    primary_value=actual,
                    secondary_value=planned,
                    percentage=round((actual / max(1, planned)) * 100.0, 1) if planned > 0 else 0.0,
                    tooltip_text=tt,
                    accessible_text=f"{day}: planned {_format_m(planned)}, actual {_format_m(actual)}, variance {diff_str}",
                    rect=col_rect,
                    metadata={"day": day, "planned": planned, "actual": actual, "variance": diff},
                )
            )

        self._draw_grid(painter, chart, max_value)

        # Inspection highlight band
        if self._has_active_inspection():
            active_idx = self._selected_key if self._selected_key is not None else self._hovered_key
            if active_idx is None and self._focused_index is not None and 0 <= self._focused_index < len(self._hit_regions):
                active_idx = self._hit_regions[self._focused_index].key

            if isinstance(active_idx, int) and 0 <= active_idx < len(self.daily_data):
                col_x = self._x_for(chart, active_idx)
                band_rect = QRectF(col_x - col_w / 2 + 1, chart.top(), col_w - 2, chart.height())
                painter.save()
                painter.setPen(Qt.NoPen)
                pal = self.palette()
                is_dark = pal.color(pal.ColorRole.Window).lightness() < 128
                highlight_bg = QColor(255, 255, 255, 22) if is_dark else QColor(0, 0, 0, 14)
                painter.setBrush(highlight_bg)
                painter.drawRoundedRect(band_rect, 4, 4)
                painter.restore()

        if self.chart_type == "Grouped Bar":
            self._draw_grouped_bars(painter, chart, max_value)
        elif self.chart_type == "Stacked Bar":
            self._draw_stacked_bars(painter, chart, max_value)
        elif self.chart_type == "Area":
            self._draw_area(painter, chart, max_value)
        else:
            self._draw_lines(painter, chart, max_value)

        self._draw_day_labels(painter, chart)
        self._draw_focus_ring(painter)

    def _x_for(self, chart: QRectF, index: int) -> float:
        count = max(1, len(self.daily_data))
        return chart.left() + chart.width() * (index + 0.5) / count

    def _y_for(self, chart: QRectF, value: int, maximum: int) -> float:
        return chart.bottom() - chart.height() * value / max(1, maximum) * self._animation_progress

    def _draw_grid(self, painter: QPainter, chart: QRectF, maximum: int):
        colors = self.semantic_colors()
        painter.setPen(QPen(colors["grid"], 1, Qt.DotLine))

        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        ticks = 4
        for i in range(ticks + 1):
            y = chart.bottom() - chart.height() * i / ticks
            painter.drawLine(QPointF(chart.left(), y), QPointF(chart.right(), y))

            val_mins = int(maximum * i / ticks)
            painter.setPen(self.muted_color())
            label = _format_m(val_mins)
            painter.drawText(QRectF(0, y - 8, chart.left() - 4, 16), Qt.AlignRight | Qt.AlignVCenter, label)
            painter.setPen(QPen(colors["grid"], 1, Qt.DotLine))

    def _draw_grouped_bars(self, painter: QPainter, chart: QRectF, maximum: int):
        colors = self.semantic_colors()
        count = len(self.daily_data)
        group_w = chart.width() / max(1, count)
        bar_w = min(16, group_w * 0.28)

        for idx, (_day, planned, actual) in enumerate(self.daily_data):
            center_x = self._x_for(chart, idx)
            p_h = chart.height() * planned / maximum * self._animation_progress
            a_h = chart.height() * actual / maximum * self._animation_progress

            p_rect = QRectF(center_x - bar_w - 2, chart.bottom() - p_h, bar_w, p_h)
            a_rect = QRectF(center_x + 2, chart.bottom() - a_h, bar_w, a_h)

            is_h, is_s, is_f = self._get_item_state(idx)

            painter.setPen(Qt.NoPen)
            painter.setBrush(self._resolve_item_color(colors["accent2"], idx))
            painter.drawRoundedRect(p_rect, 4, 4)

            painter.setBrush(self._resolve_item_color(colors["actual"], idx))
            painter.drawRoundedRect(a_rect, 4, 4)

            if is_s:
                painter.setPen(self._selection_pen(2.0))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(p_rect, 4, 4)
                painter.drawRoundedRect(a_rect, 4, 4)
            elif is_h or is_f:
                painter.setPen(self._selection_pen(1.5, 200))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(p_rect, 4, 4)
                painter.drawRoundedRect(a_rect, 4, 4)

    def _draw_stacked_bars(self, painter: QPainter, chart: QRectF, maximum: int):
        colors = self.semantic_colors()
        stack_max = max(60, max(planned + actual for _day, planned, actual in self.daily_data))
        count = len(self.daily_data)
        group_w = chart.width() / max(1, count)
        bar_w = min(24, group_w * 0.48)

        for idx, (_day, planned, actual) in enumerate(self.daily_data):
            center_x = self._x_for(chart, idx)
            a_h = chart.height() * actual / stack_max * self._animation_progress
            p_h = chart.height() * planned / stack_max * self._animation_progress

            a_rect = QRectF(center_x - bar_w / 2, chart.bottom() - a_h, bar_w, a_h)
            p_rect = QRectF(center_x - bar_w / 2, chart.bottom() - a_h - p_h, bar_w, p_h)

            is_h, is_s, is_f = self._get_item_state(idx)

            painter.setPen(Qt.NoPen)
            painter.setBrush(self._resolve_item_color(colors["actual"], idx))
            painter.drawRoundedRect(a_rect, 4, 4)

            painter.setBrush(self._resolve_item_color(colors["accent2"], idx))
            painter.drawRect(p_rect)

            if is_s:
                painter.setPen(self._selection_pen(2.0))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(QRectF(center_x - bar_w / 2, chart.bottom() - a_h - p_h, bar_w, a_h + p_h), 4, 4)
            elif is_h or is_f:
                painter.setPen(self._selection_pen(1.5, 200))
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(QRectF(center_x - bar_w / 2, chart.bottom() - a_h - p_h, bar_w, a_h + p_h), 4, 4)

    def _series_points(self, chart: QRectF, maximum: int, is_actual: bool) -> List[QPointF]:
        points = []
        for idx, row in enumerate(self.daily_data):
            value = row[2] if is_actual else row[1]
            points.append(QPointF(self._x_for(chart, idx), self._y_for(chart, value, maximum)))
        return points

    def _plain_path(self, points: List[QPointF]) -> QPainterPath:
        path = QPainterPath()
        if not points:
            return path
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        return path

    def _draw_lines(self, painter: QPainter, chart: QRectF, maximum: int):
        colors = self.semantic_colors()
        actual_pts = self._series_points(chart, maximum, True)
        planned_pts = self._series_points(chart, maximum, False)

        p_path = self._plain_path(planned_pts)
        a_path = self._plain_path(actual_pts)

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(colors["accent2"], 2.2))
        painter.drawPath(p_path)

        painter.setPen(QPen(colors["actual"], 2.4))
        painter.drawPath(a_path)

        # Draw points
        for points, col in ((planned_pts, colors["accent2"]), (actual_pts, colors["actual"])):
            for idx, pt in enumerate(points):
                is_h, is_s, is_f = self._get_item_state(idx)
                r = 5.0 if is_s else (4.0 if (is_h or is_f) else 3.0)
                painter.setPen(self._selection_pen(1.5))
                painter.setBrush(col)
                painter.drawEllipse(pt, r, r)

    def _draw_area(self, painter: QPainter, chart: QRectF, maximum: int):
        colors = self.semantic_colors()
        actual_pts = self._series_points(chart, maximum, True)
        planned_pts = self._series_points(chart, maximum, False)

        for points, col in ((planned_pts, colors["accent2"]), (actual_pts, colors["actual"])):
            if not points:
                continue
            fill_path = self._plain_path(points)
            fill_path.lineTo(points[-1].x(), chart.bottom())
            fill_path.lineTo(points[0].x(), chart.bottom())
            fill_path.closeSubpath()

            fill_c = QColor(col)
            fill_c.setAlpha(45)
            painter.setPen(Qt.NoPen)
            painter.setBrush(fill_c)
            painter.drawPath(fill_path)

            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(col, 2.0))
            painter.drawPath(self._plain_path(points))

    def _draw_day_labels(self, painter: QPainter, chart: QRectF):
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        count = len(self.daily_data)
        if count == 0:
            return

        group_w = chart.width() / max(1, count)
        max_visible_labels = max(2, int(chart.width() / 48))
        step = max(1, (count + max_visible_labels - 1) // max_visible_labels)

        shown_idxs = [
            idx
            for idx in range(count)
            if idx == 0 or idx == count - 1 or idx % step == 0
        ]
        if (
            count - 1 in shown_idxs
            and (count - 1) % step != 0
            and len(shown_idxs) > 1
        ):
            shown_idxs.remove(shown_idxs[-2])

        for idx in shown_idxs:
            day = self.daily_data[idx][0]

            label_width = max(group_w, min(74.0, chart.width() / max(2, max_visible_labels)))
            center_x = self._x_for(chart, idx)

            is_h, is_s, is_f = self._get_item_state(idx)
            if is_s:
                painter.setPen(self.accent_color())
                f_bold = QFont(painter.font())
                f_bold.setBold(True)
                painter.setFont(f_bold)
            elif is_h or is_f:
                painter.setPen(self.foreground_color())
                painter.setFont(font)
            else:
                painter.setPen(self.muted_color())
                painter.setFont(font)

            # Visual polish (M5 S5.1.2): 4px label gap sits on the spacing
            # scale. Each label is elided to its true slot (spacing between
            # shown labels), so adjacent labels can never overlap.
            slot_w = min(label_width, group_w * max(1, step))
            elided_day = painter.fontMetrics().elidedText(
                day, Qt.ElideMiddle, int(slot_w)
            )
            painter.drawText(
                QRectF(center_x - slot_w / 2, chart.bottom() + 4, slot_w, 20),
                Qt.AlignCenter,
                elided_day,
            )

