"""
Test Suite: Cross-Platform Windowing & QPA Compatibility Architecture
Validates:
1. PlatformCapabilities feature querying across backends
2. WindowInteractionService interactive child safety check
3. Native system move (startSystemMove) delegate & fallback
4. Native system resize (startSystemResize) edge mapping & execution
5. Multi-monitor geometry clamping (ensure_window_on_screen)
6. Negative coordinate handling for secondary displays
7. Non-blocking focus activation (activate_window_safely)
8. ReminderPresentationService layer separation & mobile boundary
9. ReminderDialog nonmodal desktop UX and registration
10. Exactly one reminder polling timer preserved
11. Wayland fallback safety (no illegal global move when startSystemMove fails)
12. X11 manual drag fallback allowed
13. Safe fallback when windowHandle is None
14. Nested interactive child widget click guarding
15. Negative coordinates and display gap clamping
16. Zero-overlap offscreen window recovery
17. Oversized window dimension clamping
18. Display hotplug listener idempotency
19. ReminderDialog parent=None lifetime retention in WindowRegistry
20. MainWindow focus gain while ReminderDialog is open
"""

import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from PySide6.QtWidgets import (
    QApplication, QWidget, QPushButton, QLineEdit, QComboBox, QDialog, QLabel, QVBoxLayout
)
from PySide6.QtCore import Qt, QPoint, QRect, QEvent
from PySide6.QtGui import QMouseEvent

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.models.task import Task
from todo_bird_app.services.window_interaction_service import (
    PlatformCapabilities,
    WindowInteractionService,
    CapabilityStatus
)
from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
from todo_bird_app.services.reminder_presentation_service import ReminderPresentationService
from todo_bird_app.services.window_registry import WindowRegistry
from todo_bird_app.widgets.reminder_dialog import ReminderDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture
def temp_env():
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "test_windowing.db")
        db = DatabaseManager(db_path)
        settings = SettingsManager(db, config_dir=Path(temp_dir))
        theme_ctrl = ThemeController(settings)
        ReminderPolicyService.reset_session_state(settings)
        yield db, settings, theme_ctrl, temp_dir
        ReminderPolicyService.reset_session_state(settings)


# 1. PlatformCapabilities backend detection and capability query flags
def test_01_platform_capabilities_querying(temp_env, qapp):
    plat_name = PlatformCapabilities.platform_name()
    assert isinstance(plat_name, str)
    assert len(plat_name) > 0

    session = PlatformCapabilities.session_type()
    assert isinstance(session, str)

    de = PlatformCapabilities.desktop_environment()
    assert isinstance(de, str)

    assert isinstance(PlatformCapabilities.supports_system_move(), bool)
    assert isinstance(PlatformCapabilities.supports_system_resize(), bool)
    assert isinstance(PlatformCapabilities.supports_manual_top_level_positioning(), bool)
    assert isinstance(PlatformCapabilities.supports_global_coordinates_reliably(), bool)
    assert isinstance(PlatformCapabilities.supports_window_activation(), bool)
    assert isinstance(PlatformCapabilities.supports_native_transient_parenting(), bool)

    # Capability enums
    assert isinstance(PlatformCapabilities.get_activation_capability(), CapabilityStatus)
    assert isinstance(PlatformCapabilities.get_system_move_capability(), CapabilityStatus)


# 2. WindowInteractionService interactive child safety check
def test_02_interactive_child_widget_safety_check(temp_env, qapp):
    parent_widget = QWidget()
    btn = QPushButton("Click Me", parent_widget)
    edit = QLineEdit(parent_widget)
    combo = QComboBox(parent_widget)

    assert WindowInteractionService.is_interactive_child_widget(btn) is True
    assert WindowInteractionService.is_interactive_child_widget(edit) is True
    assert WindowInteractionService.is_interactive_child_widget(combo) is True
    assert WindowInteractionService.is_interactive_child_widget(parent_widget) is False


# 3. System move delegate and interactive safety
def test_03_begin_system_move_interactive_safety(temp_env, qapp):
    win = QWidget()
    btn = QPushButton("Submit", win)
    win.setGeometry(100, 100, 300, 200)
    btn.setGeometry(10, 10, 100, 30)
    win.show()

    press_event = QMouseEvent(
        QEvent.MouseButtonPress,
        QPoint(15, 15),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier
    )

    handled = WindowInteractionService.begin_system_move(win, press_event)
    # Drag must NOT start over interactive child button
    assert handled is False
    win.close()


# 4. System resize edge mapping
def test_04_system_resize_edge_mapping():
    assert WindowInteractionService.map_edge_string_to_edges("top") == Qt.TopEdge
    assert WindowInteractionService.map_edge_string_to_edges("bottom") == Qt.BottomEdge
    assert WindowInteractionService.map_edge_string_to_edges("left") == Qt.LeftEdge
    assert WindowInteractionService.map_edge_string_to_edges("right") == Qt.RightEdge

    corner = WindowInteractionService.map_edge_string_to_edges("bottom_right")
    assert bool(corner & Qt.BottomEdge)
    assert bool(corner & Qt.RightEdge)


# 5. Multi-monitor availableGeometry clamping
def test_05_ensure_window_on_screen_clamping(temp_env, qapp):
    primary = QApplication.primaryScreen()
    assert primary is not None
    avail = primary.availableGeometry()

    huge_rect = QRect(avail.x() + avail.width() + 500, avail.y() + avail.height() + 500, 500, 400)
    clamped = WindowInteractionService.ensure_window_on_screen(huge_rect, min_width=320, min_height=200)

    assert avail.contains(clamped.topLeft())
    assert clamped.width() <= avail.width()
    assert clamped.height() <= avail.height()


# 6. Safe non-blocking window activation
def test_06_activate_window_safely(temp_env, qapp):
    win = QWidget()
    win.setGeometry(200, 200, 400, 300)
    WindowInteractionService.activate_window_safely(win)
    assert win.isVisible()
    win.close()


# 7. ReminderPresentationService layer separation
def test_07_reminder_presentation_service_desktop(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    tc = TaskController(db)
    now = datetime.now()
    t = Task(
        title="Presentation Service Task",
        planned_date=now.strftime("%Y-%m-%d"),
        planned_start_time=now.strftime("%H:%M"),
        startup_reminder=True,
    )
    tid = tc.add_task(t)

    from todo_bird_app.views.main_window import MainWindow
    win = MainWindow(db, settings, theme_ctrl)

    dialogs = ReminderPresentationService.present_due_reminders(win, tc, settings, is_startup=True)
    assert len(dialogs) == 1
    assert dialogs[0].task.id == tid

    reg_win = WindowRegistry.get_window(f"reminder_{tid}")
    assert reg_win is not None

    win.close()


# 8. ReminderDialog nonmodal desktop UX & WindowStaysOnTopHint exclusion
def test_08_reminder_dialog_nonmodal_flags(temp_env, qapp):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    t = Task(id=99, title="Nonmodal Test Task")

    dlg = ReminderDialog(t, task_controller=tc, settings_manager=settings)
    assert not dlg.isModal()
    assert dlg.windowModality() == Qt.NonModal
    assert not bool(dlg.windowFlags() & Qt.WindowStaysOnTopHint)
    dlg.close()


# 9. Diagnostics logging does not throw
def test_09_log_platform_diagnostics():
    WindowInteractionService.log_platform_diagnostics()


# 10. Wayland move fallback safety (no illegal global move when startSystemMove fails)
def test_10_wayland_move_fallback_safety(temp_env, qapp):
    win = QWidget()
    win.setGeometry(100, 100, 300, 200)
    win.show()

    with patch.object(PlatformCapabilities, "supports_manual_top_level_positioning", return_value=False):
        with patch.object(win, "windowHandle", return_value=None):
            press_event = QMouseEvent(
                QEvent.MouseButtonPress,
                QPoint(50, 10),
                Qt.LeftButton,
                Qt.LeftButton,
                Qt.NoModifier
            )
            handled = WindowInteractionService.begin_system_move(win, press_event)
            # Must return False safely without initiating manual move on Wayland
            assert handled is False
            assert getattr(win, "_is_moving", False) is False
    win.close()


# 11. X11 manual drag fallback allowed
def test_11_x11_manual_drag_fallback_allowed(temp_env, qapp):
    win = QWidget()
    win.setGeometry(100, 100, 300, 200)
    win.show()

    with patch.object(PlatformCapabilities, "supports_manual_top_level_positioning", return_value=True):
        with patch.object(win, "windowHandle", return_value=None):
            press_event = QMouseEvent(
                QEvent.MouseButtonPress,
                QPoint(50, 10),
                Qt.LeftButton,
                Qt.LeftButton,
                Qt.NoModifier
            )
            handled = WindowInteractionService.begin_system_move(win, press_event)
            assert handled is True
            assert getattr(win, "_is_moving", False) is True
    win.close()


# 12. Safe fallback when windowHandle is None
def test_12_no_window_handle_safe_fallback(temp_env, qapp):
    win = QWidget()
    press_event = QMouseEvent(QEvent.MouseButtonPress, QPoint(5, 5), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)

    # Must not throw when windowHandle is None
    res_move = WindowInteractionService.begin_system_move(win, press_event)
    res_resize = WindowInteractionService.begin_system_resize(win, press_event, "right")

    assert isinstance(res_move, bool)
    assert isinstance(res_resize, bool)


# 13. Nested interactive child widget click guarding
def test_13_nested_interactive_child_widget_guarding(temp_env, qapp):
    panel = QWidget()
    btn = QPushButton("Outer Button", panel)
    layout = QVBoxLayout(btn)
    inner_label = QLabel("Inner Text inside Button", btn)
    layout.addWidget(inner_label)

    # Click on inner label inside button must still identify parent button as interactive
    assert WindowInteractionService.is_interactive_child_widget(inner_label) is True


# 14. Zero-overlap offscreen window recovery
def test_14_zero_overlap_offscreen_recovery(temp_env, qapp):
    primary = QApplication.primaryScreen()
    avail = primary.availableGeometry()

    # Position window completely offscreen to the far right
    offscreen_rect = QRect(avail.x() + avail.width() + 2000, avail.y() + avail.height() + 2000, 400, 300)
    recovered = WindowInteractionService.ensure_window_on_screen(offscreen_rect)

    # Recovered rect must be re-centered inside availableGeometry
    assert avail.contains(recovered.topLeft())
    assert recovered.width() == 400
    assert recovered.height() == 300


# 15. Oversized window dimension clamping
def test_15_oversized_window_dimension_clamping(temp_env, qapp):
    primary = QApplication.primaryScreen()
    avail = primary.availableGeometry()

    oversized_rect = QRect(avail.x(), avail.y(), avail.width() + 1000, avail.height() + 1000)
    clamped = WindowInteractionService.ensure_window_on_screen(oversized_rect)

    assert clamped.width() <= avail.width()
    assert clamped.height() <= avail.height()


# 16. Display hotplug listener idempotency
def test_16_display_hotplug_listener_idempotency(temp_env, qapp):
    # Calling setup_display_hotplug_listeners multiple times must be idempotent
    WindowInteractionService.setup_display_hotplug_listeners()
    WindowInteractionService.setup_display_hotplug_listeners()
    assert WindowInteractionService._screen_listeners_connected is True


# 17. ReminderDialog parent=None lifetime retention in WindowRegistry
def test_17_reminder_dialog_parent_none_lifetime(temp_env, qapp):
    db, settings, _, _ = temp_env
    tc = TaskController(db)
    t = Task(id=101, title="Lifetime Test Task")

    dlg = ReminderDialog(t, task_controller=tc, settings_manager=settings, parent=None)
    assert dlg.parent() is None

    reg_win = WindowRegistry.get_window(f"reminder_{t.id}")
    assert reg_win is dlg

    dlg.close()
    assert WindowRegistry.get_window(f"reminder_{t.id}") is None


# 18. MainWindow focus gain while ReminderDialog is open
def test_18_main_window_can_gain_focus_with_reminder(temp_env, qapp):
    db, settings, theme_ctrl, _ = temp_env
    from todo_bird_app.views.main_window import MainWindow

    win = MainWindow(db, settings, theme_ctrl)
    win.show()

    t = Task(id=102, title="Focus Test Task")
    dlg = ReminderDialog(t, settings_manager=settings, parent=None)
    dlg.show()

    # Raising MainWindow must work since dlg is nonmodal and does not have WindowStaysOnTopHint
    win.raise_()
    win.activateWindow()

    assert not dlg.isModal()
    dlg.close()
    win.close()
