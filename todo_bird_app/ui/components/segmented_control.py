"""
TODO BIRD — MODERN SEGMENTED CONTROL COMPONENT
Provides a sleek segmented pill control for mutually exclusive options (e.g. Professional | Balanced | Personal).
Features smooth animated selection indicator pill, tactile hover, and full keyboard navigation.
"""

from typing import List, Optional, Tuple, Any
from PySide6.QtCore import (
    Qt,
    QRectF,
    QSize,
    Signal,
    Property,
    QVariantAnimation,
    QEasingCurve,
    QEvent,
)
from PySide6.QtWidgets import QWidget, QSizePolicy
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
from todo_bird_app.services.appearance_service import semantic_tokens_for


class SegmentedControl(QWidget):
    """
    Modern Segmented Switch / Tab Pill Group.
    Displays items horizontally with a sliding background pill indicator.
    """

    valueChanged = Signal(int, str, object)  # (index, label, data)

    def __init__(
        self,
        segments: Optional[List[Tuple[str, Any]]] = None,
        selected_index: int = 0,
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
        animate: bool = True,
    ):
        super().__init__(parent)
        self._segments: List[Tuple[str, Any]] = segments or [("Option 1", 0), ("Option 2", 1)]
        self._selected_index = max(0, min(selected_index, len(self._segments) - 1))
        self._is_dark = is_dark
        self._accent_color = accent_color
        self._animate = animate
        self._indicator_pos = float(self._selected_index)
        self._hover_index = -1
        self._is_focused = False

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_step)

        self._update_geometry()
        self.setMaximumHeight(16777215)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Fixed,
        )

        # Phase 1F.4 — accessibility foundation.
        #
        # SegmentedControl is custom-painted, so expose a useful semantic
        # description explicitly rather than relying only on pixels.
        self.setAccessibleName("Segmented control")
        self._refresh_accessibility_description()

    # -------------------------------------------------------------------------
    # Animation Property
    # -------------------------------------------------------------------------

    def get_indicator_pos(self) -> float:
        return self._indicator_pos

    def set_indicator_pos(self, val: float):
        self._indicator_pos = val
        self.update()

    indicatorPosition = Property(float, get_indicator_pos, set_indicator_pos)

    def _on_anim_step(self, val):
        self.set_indicator_pos(float(val))

    def _refresh_accessibility_description(self) -> None:
        """
        Keep assistive-technology state synchronized with the currently
        selected custom-painted segment.

        Visual appearance and keyboard routing remain unchanged.
        """
        if not self._segments:
            self.setAccessibleDescription(
                "No options available."
            )
            return

        selected = max(
            0,
            min(
                self._selected_index,
                len(self._segments) - 1,
            ),
        )

        selected_label = str(
            self._segments[selected][0]
        )

        option_labels = ", ".join(
            str(label)
            for label, _ in self._segments
        )

        self.setAccessibleDescription(
            f"Selected: {selected_label}. "
            f"Options: {option_labels}. "
            "Use Left and Right arrow keys to change selection."
        )

    # -------------------------------------------------------------------------
    # Public APIs
    # -------------------------------------------------------------------------

    @property
    def selected_index(self) -> int:
        return self._selected_index

    @selected_index.setter
    def selected_index(self, index: int):
        self.set_selected_index(index)

    def set_selected_index(self, index: int, notify: bool = True):
        if not (0 <= index < len(self._segments)):
            return
        if self._selected_index == index and self._indicator_pos == float(index):
            return

        self._selected_index = index
        self._refresh_accessibility_description()
        target = float(index)

        if self._animate and self.isVisible():
            self._anim.stop()
            self._anim.setStartValue(self._indicator_pos)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.set_indicator_pos(target)

        if notify:
            label, data = self._segments[index]
            self.valueChanged.emit(index, label, data)

    def set_segments(self, segments: List[Tuple[str, Any]], selected_index: int = 0):
        self._segments = list(segments)
        self._selected_index = max(0, min(selected_index, len(self._segments) - 1))
        self._indicator_pos = float(self._selected_index)
        self._refresh_accessibility_description()
        self._update_geometry()
        self.update()

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color
        self._update_geometry()
        self.update()

    def _update_geometry(self):
        self.setMinimumHeight(self.sizeHint().height())
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        """
        Geometry authority for the custom-painted control.

        Measurement must use exactly the same font that paintEvent()
        uses. This prevents 20pt -> 10pt reverse-scaling clipping.
        """
        fm = self.fontMetrics()

        total_w = 0

        for label, _ in self._segments:
            total_w += (
                fm.horizontalAdvance(
                    str(label)
                )
                + 28
            )

        required_h = max(28, int(fm.height()) + 10)

        return QSize(
            max(total_w, 160),
            required_h,
        )

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def changeEvent(self, event):
        """
        A custom-painted widget must invalidate its geometry whenever
        its font changes; Qt cannot infer this from our painter.
        """
        super().changeEvent(event)

        if (
            event is not None
            and event.type() == QEvent.FontChange
        ):
            self._update_geometry()
            self.update()

    # -------------------------------------------------------------------------
    # Events
    # -------------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and len(self._segments) > 0:
            seg_w = self.width() / float(len(self._segments))
            clicked_idx = int(event.position().x() / seg_w)
            clicked_idx = max(0, min(clicked_idx, len(self._segments) - 1))
            self.set_selected_index(clicked_idx)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if len(self._segments) > 0:
            seg_w = self.width() / float(len(self._segments))
            idx = int(event.position().x() / seg_w)
            self._hover_index = max(0, min(idx, len(self._segments) - 1))
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_index = -1
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
        if event.key() == Qt.Key_Right:
            self.set_selected_index(min(self._selected_index + 1, len(self._segments) - 1))
            event.accept()
            return
        elif event.key() == Qt.Key_Left:
            self.set_selected_index(max(self._selected_index - 1, 0))
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

        num_segs = len(self._segments)
        if num_segs == 0:
            return

        w = self.width()
        h = self.height()
        outer_rect = QRectF(1, 1, w - 2, h - 2)
        outer_radius = 8.0
        accent = QColor(self._accent_color)
        tokens = semantic_tokens_for(self._is_dark, self._accent_color)

        # 1. Outer Container Background
        bg_col = QColor(tokens["SURFACE_2"])
        border_col = QColor(tokens["BORDER_NORMAL"])

        outer_path = QPainterPath()
        outer_path.addRoundedRect(outer_rect, outer_radius, outer_radius)
        painter.fillPath(outer_path, QBrush(bg_col))
        painter.strokePath(outer_path, QPen(border_col, 1.0))

        # Focus ring
        if self._is_focused:
            focus_path = QPainterPath()
            focus_path.addRoundedRect(outer_rect.adjusted(-1, -1, 1, 1), outer_radius + 1, outer_radius + 1)
            painter.strokePath(focus_path, QPen(accent, 1.5))

        # 2. Sliding Active Indicator Pill
        seg_w = (w - 4) / float(num_segs)
        ind_x = 2 + self._indicator_pos * seg_w
        ind_rect = QRectF(ind_x, 2, seg_w, h - 4)
        ind_radius = outer_radius - 2.0

        if self._is_dark:
            ind_bg = accent
            ind_border = ind_bg
        else:
            ind_bg = QColor(tokens["SURFACE_1"])
            ind_border = QColor(tokens["BORDER_NORMAL"])

        ind_path = QPainterPath()
        ind_path.addRoundedRect(ind_rect, ind_radius, ind_radius)
        painter.fillPath(ind_path, QBrush(ind_bg))
        if not self._is_dark:
            painter.strokePath(ind_path, QPen(ind_border, 1.0))

        # 3. Draw Segment Labels
        #
        # IMPORTANT:
        # Use the widget's configured font. sizeHint() measures this
        # same font, keeping layout and painting in one authority.
        font = QFont(self.font())
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)

        for i, (label, _) in enumerate(self._segments):
            seg_rect = QRectF(2 + i * seg_w, 0, seg_w, h)
            is_active = (i == self._selected_index)

            if is_active:
                text_col = QColor(tokens["TEXT_ON_ACCENT"]) if self._is_dark else accent.darker(140)
            elif i == self._hover_index:
                text_col = QColor(tokens["TEXT_PRIMARY"])
            else:
                text_col = QColor(tokens["TEXT_SECONDARY"])

            painter.setPen(text_col)
            painter.drawText(seg_rect, Qt.AlignCenter, label)

        painter.end()
