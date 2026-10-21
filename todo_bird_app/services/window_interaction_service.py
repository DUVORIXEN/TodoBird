"""
Window Interaction Service & Platform Capabilities (Phase C & D)
Centralized QPA platform abstraction, window movement/resize, focus activation,
multi-monitor geometry safety, and DPI scaling authority for Todo Bird.
"""

import os
import sys
import logging
from enum import Enum
from typing import Optional, Dict, Any, Tuple, List
from PySide6.QtWidgets import (
    QWidget, QDialog, QApplication, QAbstractButton, QComboBox,
    QAbstractSpinBox, QLineEdit, QTextEdit, QPlainTextEdit, QScrollBar,
    QSizeGrip, QSlider
)
from PySide6.QtCore import Qt, QPoint, QRect, QSize
from PySide6.QtGui import QGuiApplication, QScreen, QWindow

logger = logging.getLogger(__name__)


class CapabilityStatus(Enum):
    """Explicit evidence-backed capability status classifications."""
    SUPPORTED = "supported"
    SUPPORTED_WITH_LIMITATIONS = "supported_with_limitations"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class PlatformCapabilities:
    """
    Centralized query service for QPA platform backend capabilities and environment features.
    Prefers API feature detection over fragile hardcoded OS checks.
    """

    @classmethod
    def platform_name(cls) -> str:
        """Returns the active Qt QPA platform backend name (e.g., 'wayland', 'xcb', 'windows', 'cocoa', 'ios')."""
        app = QGuiApplication.instance()
        if app:
            try:
                name = str(app.platformName() or "").lower().strip()
                if name:
                    return name
            except Exception:
                pass

        if sys.platform == "win32":
            return "windows"
        elif sys.platform == "darwin":
            return "cocoa"
        elif sys.platform.startswith("linux"):
            session_type = str(os.environ.get("XDG_SESSION_TYPE", "")).lower()
            return "wayland" if "wayland" in session_type else "xcb"
        return "unknown"

    @classmethod
    def session_type(cls) -> str:
        """Returns diagnostic session type ('wayland', 'x11', 'win32', 'cocoa', 'ios')."""
        if sys.platform == "win32":
            return "win32"
        elif sys.platform == "darwin":
            return "cocoa"

        session = str(os.environ.get("XDG_SESSION_TYPE", "")).lower().strip()
        if session:
            return session
        if os.environ.get("WAYLAND_DISPLAY"):
            return "wayland"
        if os.environ.get("DISPLAY"):
            return "x11"
        return cls.platform_name()

    @classmethod
    def desktop_environment(cls) -> str:
        """Returns diagnostic desktop environment name ('gnome', 'kde', 'xfce', 'cinnamon', 'windows', 'macos')."""
        if sys.platform == "win32":
            return "windows"
        elif sys.platform == "darwin":
            return "macos"

        desktop = str(os.environ.get("XDG_CURRENT_DESKTOP", "") or os.environ.get("DESKTOP_SESSION", "")).lower().strip()
        if "gnome" in desktop:
            return "gnome"
        elif "kde" in desktop or "plasma" in desktop:
            return "kde"
        elif "xfce" in desktop:
            return "xfce"
        elif "cinnamon" in desktop:
            return "cinnamon"
        return desktop or "generic_linux"

    @classmethod
    def get_system_move_capability(cls) -> CapabilityStatus:
        plat = cls.platform_name()
        if plat in {"wayland", "xcb", "windows", "cocoa", "qxcb", "qwayland", "qwindows", "qcocoa"}:
            return CapabilityStatus.SUPPORTED
        if plat == "ios":
            return CapabilityStatus.UNSUPPORTED
        return CapabilityStatus.UNKNOWN

    @classmethod
    def get_system_resize_capability(cls) -> CapabilityStatus:
        plat = cls.platform_name()
        if plat in {"wayland", "xcb", "windows", "cocoa", "qxcb", "qwayland", "qwindows", "qcocoa"}:
            return CapabilityStatus.SUPPORTED
        if plat == "ios":
            return CapabilityStatus.UNSUPPORTED
        return CapabilityStatus.UNKNOWN

    @classmethod
    def get_activation_capability(cls) -> CapabilityStatus:
        plat = cls.platform_name()
        if plat == "ios":
            return CapabilityStatus.UNSUPPORTED
        # On Wayland, Windows, macOS, activation can be requested, but OS compositor enforces focus-stealing rules
        return CapabilityStatus.SUPPORTED_WITH_LIMITATIONS

    @classmethod
    def get_autostart_capability(cls) -> CapabilityStatus:
        if sys.platform == "linux":
            return CapabilityStatus.SUPPORTED_WITH_LIMITATIONS  # XDG desktop autostart implemented
        if sys.platform in ("win32", "darwin"):
            return CapabilityStatus.SUPPORTED_WITH_LIMITATIONS  # Requires OS registry / launch agent configuration
        return CapabilityStatus.UNSUPPORTED

    @classmethod
    def get_system_tray_capability(cls) -> CapabilityStatus:
        from PySide6.QtWidgets import QSystemTrayIcon
        try:
            if QSystemTrayIcon.isSystemTrayAvailable():
                return CapabilityStatus.SUPPORTED_WITH_LIMITATIONS
            return CapabilityStatus.UNSUPPORTED
        except Exception:
            return CapabilityStatus.UNSUPPORTED

    @classmethod
    def supports_system_move(cls) -> bool:
        return cls.get_system_move_capability() in (CapabilityStatus.SUPPORTED, CapabilityStatus.SUPPORTED_WITH_LIMITATIONS)

    @classmethod
    def supports_system_resize(cls) -> bool:
        return cls.get_system_resize_capability() in (CapabilityStatus.SUPPORTED, CapabilityStatus.SUPPORTED_WITH_LIMITATIONS)

    @classmethod
    def supports_manual_top_level_positioning(cls) -> bool:
        """
        True if client application move()/setGeometry() on top-level windows is honored by the OS.
        On Wayland and iOS, top-level manual positioning is ignored or prohibited by the compositor.
        """
        plat = cls.platform_name()
        if "wayland" in plat or plat == "ios":
            return False
        return True

    @classmethod
    def supports_global_coordinates_reliably(cls) -> bool:
        """True if global mouse cursor coordinates are accessible to client applications."""
        plat = cls.platform_name()
        if "wayland" in plat or plat == "ios":
            return False
        return True

    @classmethod
    def supports_window_activation(cls) -> bool:
        return cls.get_activation_capability() != CapabilityStatus.UNSUPPORTED

    @classmethod
    def supports_native_transient_parenting(cls) -> bool:
        return cls.platform_name() != "ios"

    @classmethod
    def supports_fractional_scaling(cls) -> bool:
        return True

    @classmethod
    def supports_desktop_autostart(cls) -> bool:
        return cls.get_autostart_capability() != CapabilityStatus.UNSUPPORTED

    @classmethod
    def supports_system_tray(cls) -> bool:
        return cls.get_system_tray_capability() != CapabilityStatus.UNSUPPORTED

    @classmethod
    def supports_native_notifications(cls) -> bool:
        return True

    @classmethod
    def supports_always_on_top(cls) -> bool:
        return cls.platform_name() != "ios"

    @classmethod
    def supports_window_minimize(cls) -> bool:
        return cls.platform_name() != "ios"

    @classmethod
    def supports_window_maximize(cls) -> bool:
        return cls.platform_name() != "ios"

    @classmethod
    def supports_multi_monitor_positioning(cls) -> bool:
        return cls.supports_manual_top_level_positioning()

    @classmethod
    def supports_pointer_hover(cls) -> bool:
        return cls.platform_name() != "ios"

    @classmethod
    def supports_touch_primary_input(cls) -> bool:
        return cls.platform_name() == "ios"


class WindowInteractionService:
    """
    Centralized Platform Window Adapter managing native system move, system resize,
    multi-monitor availableGeometry clamping, negative screen coordinates, and activation.
    """

    _screen_listeners_connected = False

    @classmethod
    def setup_display_hotplug_listeners(cls):
        """Connects screenAdded/screenRemoved signals once idempotently."""
        if cls._screen_listeners_connected:
            return
        app = QGuiApplication.instance()
        if app:
            try:
                app.screenAdded.connect(cls._handle_screen_added)
                app.screenRemoved.connect(cls._handle_screen_removed)
                cls._screen_listeners_connected = True
                logger.debug("Display hotplug signal listeners connected.")
            except Exception as e:
                logger.debug("Failed to connect screen change listeners: %s", e)

    @classmethod
    def _handle_screen_added(cls, screen: QScreen):
        logger.info("Display connected: %s (Geometry=%s)", screen.name() if screen else "unknown", screen.geometry() if screen else "")

    @classmethod
    def _handle_screen_removed(cls, screen: QScreen):
        logger.info("Display disconnected: %s. Auditing open windows...", screen.name() if screen else "unknown")
        from todo_bird_app.services.window_registry import WindowRegistry
        for win in WindowRegistry.get_all_windows():
            if hasattr(win, "geometry") and hasattr(win, "setGeometry"):
                try:
                    rect = win.geometry()
                    clamped = cls.ensure_window_on_screen(rect, target_widget=win)
                    if clamped != rect and PlatformCapabilities.supports_manual_top_level_positioning():
                        win.setGeometry(clamped)
                except Exception as e:
                    logger.debug("Error adjusting window geometry on screen removal: %s", e)

    @classmethod
    def is_interactive_child_widget(cls, child: Optional[QWidget]) -> bool:
        """
        Returns True if the widget or its immediate container is an interactive control
        where header drag must NOT start.
        """
        if not child:
            return False

        curr = child
        while curr is not None:
            if isinstance(curr, (QAbstractButton, QComboBox, QAbstractSpinBox, QLineEdit, QTextEdit, QPlainTextEdit, QScrollBar, QSizeGrip, QSlider)):
                return True
            if hasattr(curr, "objectName") and curr.objectName() in {"CancelButton", "SaveButton", "HeaderClockBadge", "SizeGrip"}:
                return True
            curr = curr.parentWidget()
        return False

    @classmethod
    def get_target_screen(cls, pos_or_widget: Optional[Any] = None) -> QScreen:
        """Determines the appropriate QScreen for a given position or widget."""
        app = QGuiApplication.instance()
        if not app:
            return None

        if isinstance(pos_or_widget, QWidget):
            win = pos_or_widget.windowHandle()
            if win and win.screen():
                return win.screen()
            if pos_or_widget.isVisible():
                g_pos = pos_or_widget.mapToGlobal(QPoint(0, 0))
                scr = QGuiApplication.screenAt(g_pos)
                if scr:
                    return scr

        if isinstance(pos_or_widget, QPoint):
            scr = QGuiApplication.screenAt(pos_or_widget)
            if scr:
                return scr

        return QGuiApplication.primaryScreen()

    @classmethod
    def ensure_window_on_screen(
        cls,
        rect: QRect,
        target_widget: Optional[QWidget] = None,
        min_width: int = 320,
        min_height: int = 200
    ) -> QRect:
        """
        Clamps window geometry to the available geometry (accounting for docks, panels, taskbars)
        of the appropriate QScreen. Supports negative origin coordinates for secondary monitors and monitor gaps.
        """
        scr = cls.get_target_screen(target_widget or rect.topLeft())
        if not scr:
            return rect

        avail = scr.availableGeometry()

        w = max(min_width, min(rect.width(), avail.width()))
        h = max(min_height, min(rect.height(), avail.height()))

        x = rect.x()
        y = rect.y()

        clamped_rect = QRect(x, y, w, h)
        intersect = clamped_rect.intersected(avail)

        if intersect.isEmpty() or intersect.width() < w * 0.4 or intersect.height() < h * 0.4:
            x = avail.x() + (avail.width() - w) // 2
            y = avail.y() + (avail.height() - h) // 2
        else:
            if x + w > avail.x() + avail.width():
                x = avail.x() + avail.width() - w
            if x < avail.x():
                x = avail.x()

            if y + h > avail.y() + avail.height():
                y = avail.y() + avail.height() - h
            if y < avail.y():
                y = avail.y()

        return QRect(x, y, w, h)

    @classmethod
    def begin_system_move(cls, widget: QWidget, event: Any) -> bool:
        """
        Initiates native system window movement via QWindow.startSystemMove().
        Safely checks interactive child controls and falls back to manual positioning if needed.
        On Wayland, if startSystemMove fails, manual global position manipulation is NOT performed.
        """
        if not widget:
            return False

        child = widget.childAt(event.position().toPoint() if hasattr(event, "position") else event.pos())
        if cls.is_interactive_child_widget(child):
            return False

        win = widget.windowHandle()
        if not win and hasattr(widget, "window"):
            top_level = widget.window()
            if top_level:
                win = top_level.windowHandle()

        if win and hasattr(win, "startSystemMove"):
            try:
                if win.startSystemMove():
                    logger.debug("Native QWindow.startSystemMove succeeded.")
                    return True
            except Exception as e:
                logger.debug("Native startSystemMove failed or unhandled: %s", e)

        # Fallback Path for platforms supporting manual top-level positioning (X11, Windows, macOS)
        if PlatformCapabilities.supports_manual_top_level_positioning():
            g_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            frame_top_left = widget.window().frameGeometry().topLeft() if widget.window() else widget.frameGeometry().topLeft()
            widget._drag_pos = g_pos - frame_top_left
            widget._is_moving = True
            return True

        # On Wayland/iOS, manual global move is unsupported; return False safely
        return False

    @classmethod
    def map_edge_string_to_edges(cls, edge_str: str) -> Qt.Edges:
        edges = Qt.Edges()
        edge_lower = str(edge_str or "").lower().strip()
        if "top" in edge_lower:
            edges |= Qt.TopEdge
        if "bottom" in edge_lower:
            edges |= Qt.BottomEdge
        if "left" in edge_lower:
            edges |= Qt.LeftEdge
        if "right" in edge_lower:
            edges |= Qt.RightEdge
        return edges

    @classmethod
    def begin_system_resize(cls, widget: QWidget, event: Any, edge_str: str) -> bool:
        """
        Initiates native system window resizing via QWindow.startSystemResize(edges).
        """
        if not widget or not edge_str:
            return False

        edges = cls.map_edge_string_to_edges(edge_str)
        if not edges:
            return False

        win = widget.windowHandle()
        if not win and hasattr(widget, "window"):
            top_level = widget.window()
            if top_level:
                win = top_level.windowHandle()

        if win and hasattr(win, "startSystemResize"):
            try:
                if win.startSystemResize(edges):
                    logger.debug("Native QWindow.startSystemResize succeeded for edges %s", edge_str)
                    return True
            except Exception as e:
                logger.debug("Native startSystemResize failed: %s", e)

        if PlatformCapabilities.supports_manual_top_level_positioning():
            widget._is_resizing = True
            widget._resize_edge = edge_str
            widget._drag_start_geo = widget.geometry()
            widget._drag_start_pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            return True

        return False

    @classmethod
    def activate_window_safely(cls, widget: QWidget):
        """Activates and presents a window safely without focus-stealing loops or modal trapping."""
        if not widget:
            return
        try:
            widget.show()
            if PlatformCapabilities.supports_window_activation():
                widget.raise_()
                widget.activateWindow()
        except Exception as e:
            logger.debug("Error during safe window activation: %s", e)

    @classmethod
    def log_platform_diagnostics(cls):
        """Provides diagnostic platform log summary at application startup."""
        try:
            logger.info("==================================================")
            logger.info("TODO BIRD PLATFORM DIAGNOSTICS")
            logger.info("QPA Backend: %s", cls.platform_name())
            logger.info("Session Type: %s", cls.session_type())
            logger.info("Desktop Environment: %s", cls.desktop_environment())
            logger.info("System Move Supported: %s", cls.supports_system_move())
            logger.info("System Resize Supported: %s", cls.supports_system_resize())
            logger.info("Manual Positioning Supported: %s", cls.supports_manual_top_level_positioning())
            logger.info("Activation Capability: %s", cls.get_activation_capability().value)

            app = QGuiApplication.instance()
            if app:
                screens = app.screens()
                logger.info("Connected Displays: %d", len(screens))
                for i, scr in enumerate(screens):
                    logger.info(
                        "  Display #%d '%s': Geometry=%s, Available=%s, DPI=%.1f, DPR=%.2f",
                        i + 1, scr.name(), scr.geometry(), scr.availableGeometry(),
                        scr.logicalDotsPerInch(), scr.devicePixelRatio()
                    )
            logger.info("==================================================")
        except Exception as e:
            logger.debug("Error logging platform diagnostics: %s", e)
