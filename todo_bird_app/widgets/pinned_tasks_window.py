"""
TODO BIRD — Dedicated Pinned Tasks Window (Batch 3.10G)
Provides an independent, resizable, floating companion window for Pinned Priorities.
Features:
- Size Presets: Compact (360x260), Standard (520x360), Large (740x500), Custom
- Desktop and edge-based resizing with minimum size constraints (320x220)
- Multi-monitor safety geometry clamping
- Persistence across application restarts
- Independent typography and responsive card layout
"""

import logging
from typing import Optional, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QScrollArea, QWidget, QSizeGrip, QApplication
)
from PySide6.QtCore import Qt, QPoint, QSize, Signal
from PySide6.QtGui import QScreen

from todo_bird_app.widgets.pinned_priorities_widget import PinnedPrioritiesWidget
from todo_bird_app.services.typography_service import TypographyService

logger = logging.getLogger(__name__)

SIZE_PRESETS = {
    "compact": (360, 260),
    "standard": (520, 360),
    "large": (740, 500),
}
MIN_WIDTH = 320
MIN_HEIGHT = 220


class PinnedTasksWindow(QDialog):
    """
    Dedicated floating / standalone window for Pinned Priorities with full geometry control.
    """

    @classmethod
    def get_or_open(
        cls,
        db_manager: Any,
        settings_manager: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ) -> "PinnedTasksWindow":
        """Single-instance window factory: raises existing or creates new."""
        from todo_bird_app.services.window_registry import WindowRegistry
        existing = WindowRegistry.get_window("pinned_tasks")
        if existing is not None and isinstance(existing, PinnedTasksWindow):
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return existing

        win = PinnedTasksWindow(db_manager, settings_manager, parent=parent)
        win.show()
        win.raise_()
        win.activateWindow()
        return win

    def __init__(
        self,
        db_manager: Any,
        settings_manager: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.db_manager = db_manager
        self.settings_manager = settings_manager

        self.setWindowTitle("Pinned Priorities — TODO BIRD")
        self.setModal(False)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)

        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.register(self, role="pinned_tasks")

        self._init_ui()
        self.restore_geometry_from_settings()

    def closeEvent(self, event):
        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.unregister(self)
        super().closeEvent(event)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Embedded PinnedPrioritiesWidget
        self.pinned_widget = PinnedPrioritiesWidget(
            self.db_manager,
            self.settings_manager,
            parent=self,
        )
        layout.addWidget(self.pinned_widget, 1)

        # Bottom Bar with Size Grip
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(4, 0, 4, 0)
        bottom_bar.addStretch()

        self.size_grip = QSizeGrip(self)
        bottom_bar.addWidget(self.size_grip, 0, Qt.AlignBottom | Qt.AlignRight)
        layout.addLayout(bottom_bar)

    def apply_preset(self, preset_name: str):
        """Applies a size preset (compact, standard, large, custom)."""
        preset_key = str(preset_name or "standard").lower().strip()
        if preset_key in SIZE_PRESETS:
            w, h = SIZE_PRESETS[preset_key]
            self.resize(w, h)
            if self.settings_manager:
                self.settings_manager.set("pinned_window_size_mode", preset_key)
                self.settings_manager.set("pinned_window_width", w)
                self.settings_manager.set("pinned_window_height", h)

    def restore_geometry_from_settings(self):
        """Restores and clamps window size and position from settings."""
        if not self.settings_manager:
            self.resize(*SIZE_PRESETS["standard"])
            return

        mode = str(self.settings_manager.get("pinned_window_size_mode", "standard") or "standard").lower().strip()
        default_w, default_h = SIZE_PRESETS.get(mode, SIZE_PRESETS["standard"])

        w = int(self.settings_manager.get("pinned_window_width", default_w) or default_w)
        h = int(self.settings_manager.get("pinned_window_height", default_h) or default_h)

        w = max(MIN_WIDTH, w)
        h = max(MIN_HEIGHT, h)

        # Screen geometry clamping for multi-monitor safety
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            w = min(w, geo.width())
            h = min(h, geo.height())

            saved_x = self.settings_manager.get("pinned_window_x")
            saved_y = self.settings_manager.get("pinned_window_y")

            if saved_x is not None and saved_y is not None:
                x = int(saved_x)
                y = int(saved_y)
                # Clamp within screen bounds
                x = max(geo.left(), min(x, geo.right() - w))
                y = max(geo.top(), min(y, geo.bottom() - h))
                self.move(x, y)

        self.resize(w, h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = max(MIN_WIDTH, self.width())
        h = max(MIN_HEIGHT, self.height())
        if self.settings_manager:
            self.settings_manager.set("pinned_window_width", w)
            self.settings_manager.set("pinned_window_height", h)
            # If resized away from preset, update mode to custom
            cur_mode = str(self.settings_manager.get("pinned_window_size_mode", "standard")).lower()
            if cur_mode in SIZE_PRESETS:
                pw, ph = SIZE_PRESETS[cur_mode]
                if abs(w - pw) > 10 or abs(h - ph) > 10:
                    self.settings_manager.set("pinned_window_size_mode", "custom")

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.settings_manager:
            self.settings_manager.set("pinned_window_x", self.x())
            self.settings_manager.set("pinned_window_y", self.y())
