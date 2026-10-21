"""
Window Registry Service (Batch 3.10H)
Central lifecycle and ownership manager for Todo Bird application windows and dialogs.
Ensures single-instance window roles, prevents orphaned zombie widgets, and guarantees
deterministic clean application shutdown.
"""

import logging
import weakref
from typing import Optional, Dict, Set, List, Any
from PySide6.QtWidgets import QWidget, QDialog, QApplication
from PySide6.QtCore import QObject

try:
    import shiboken6
except Exception:
    shiboken6 = None

logger = logging.getLogger(__name__)


class WindowRegistry:
    """
    Lightweight central registry managing top-level and modeless windows.
    Uses weak references to prevent keeping dead PySide6 wrappers alive.
    """
    _registered_windows: Dict[int, Any] = {}  # maps id(window) -> weakref.ref(window)
    _role_map: Dict[str, int] = {}  # maps role -> id(window)

    @classmethod
    def _is_valid_widget(cls, window: Optional[QWidget]) -> bool:
        if window is None:
            return False
        try:
            if shiboken6 is not None and not shiboken6.isValid(window):
                return False
            return bool(window.isWidgetType())
        except RuntimeError:
            return False

    @classmethod
    def _unregister_id(cls, win_id: int):
        cls._registered_windows.pop(win_id, None)
        for role, wid in list(cls._role_map.items()):
            if wid == win_id:
                del cls._role_map[role]

    @classmethod
    def clear(cls):
        """Resets registry state (used for test isolation)."""
        cls._registered_windows.clear()
        cls._role_map.clear()

    @classmethod
    def register(cls, window: QWidget, role: Optional[str] = None):
        """Registers a window with optional role."""
        if not window:
            return
        win_id = id(window)
        cls._registered_windows[win_id] = weakref.ref(window)
        if role:
            cls._role_map[role] = win_id
        try:
            window.destroyed.connect(
                lambda _obj=None, wid=win_id: cls._unregister_id(wid)
            )
        except Exception:
            pass

    @classmethod
    def unregister(cls, window: QWidget):
        """Explicitly unregisters a window."""
        if not window:
            return
        win_id = id(window)
        cls._registered_windows.pop(win_id, None)
        for role, wid in list(cls._role_map.items()):
            if wid == win_id:
                del cls._role_map[role]

    @classmethod
    def get_window(cls, role: str) -> Optional[QWidget]:
        """Returns the registered window for a given role if still alive and valid."""
        win_id = cls._role_map.get(role)
        if win_id is not None:
            ref = cls._registered_windows.get(win_id)
            if ref is not None:
                w = ref()
                if cls._is_valid_widget(w):
                    return w
            cls._unregister_id(win_id)
        return None

    @classmethod
    def get_open_windows(cls) -> List[QWidget]:
        """Returns list of all currently active registered windows."""
        alive = []
        for win_id, ref in list(cls._registered_windows.items()):
            w = ref()
            if cls._is_valid_widget(w):
                alive.append(w)
                continue
            cls._unregister_id(win_id)
        return alive

    @classmethod
    def close_all_transient(cls):
        """Closes all transient dialogs."""
        for win_id, ref in list(cls._registered_windows.items()):
            w = ref()
            if cls._is_valid_widget(w):
                try:
                    if isinstance(w, QDialog) and w.isVisible():
                        w.reject() if hasattr(w, "reject") else w.close()
                except RuntimeError:
                    pass
            cls._registered_windows.pop(win_id, None)

    @classmethod
    def close_all_on_shutdown(cls):
        """
        Closes all registered modeless, companion, floating windows and dialogs on app shutdown.
        Also sweeps any remaining top-level QWidget/QDialog objects (excluding MainWindow)
        to guarantee no orphan windows prevent QApplication exit.
        """
        logger.info("WindowRegistry: Closing all registered windows on shutdown...")
        for win_id, ref in list(cls._registered_windows.items()):
            w = ref()
            if cls._is_valid_widget(w):
                try:
                    if hasattr(w, "cleanup"):
                        w.cleanup()
                    w.close()
                    w.deleteLater()
                except Exception as e:
                    logger.debug(
                        "WindowRegistry: Error closing registered window "
                        f"id={win_id}: {e}"
                    )
            else:
                cls._unregister_id(win_id)

        cls._registered_windows.clear()
        cls._role_map.clear()

        # Sweep all remaining top-level widgets in QApplication
        app = QApplication.instance()
        if app:
            for w in list(app.topLevelWidgets()):
                if (
                    cls._is_valid_widget(w)
                    and w.__class__.__name__ != "MainWindow"
                ):
                    try:
                        if hasattr(w, "cleanup"):
                            w.cleanup()
                        if hasattr(w, "reject"):
                            w.reject()
                        w.close()
                        w.deleteLater()
                    except Exception as e:
                        logger.debug(f"WindowRegistry: Error closing top-level widget: {e}")
        cls._role_map.clear()

    _reminder_resize_listeners: Set[Any] = set()

    @classmethod
    def register_reminder_resize_listener(cls, callback):
        """Registers a callback to receive live (w, h) resize events from active reminder dialogs."""
        cls._reminder_resize_listeners.add(callback)

    @classmethod
    def unregister_reminder_resize_listener(cls, callback):
        """Unregisters a reminder resize listener callback."""
        cls._reminder_resize_listeners.discard(callback)

    @classmethod
    def notify_reminder_resized(cls, w: int, h: int):
        """Notifies all registered listeners when a reminder dialog is resized via dragging."""
        for cb in list(cls._reminder_resize_listeners):
            try:
                cb(w, h)
            except Exception as e:
                logger.debug(f"WindowRegistry: Error in reminder resize listener: {e}")

    @classmethod
    def notify_reminder_settings_changed(cls):
        """Notifies all active ReminderDialog instances that settings have been updated."""
        for win_id, ref in list(cls._registered_windows.items()):
            w = ref()
            if w is not None:
                try:
                    if hasattr(w, "update_from_settings"):
                        w.update_from_settings()
                except Exception as e:
                    logger.debug(f"WindowRegistry: Error updating reminder window: {e}")

    @classmethod
    def clear(cls):
        """Clears registry state (useful for tests)."""
        cls._registered_windows.clear()
        cls._role_map.clear()
        cls._reminder_resize_listeners.clear()
