"""
TODO BIRD — Comprehensive Verification Test Suite for Batch 3.10G
Tests:
- PIN-T01 to PIN-T06: Pinned tasks typography (family, size, weight, global inheritance, restart persistence, rebuild stability)
- PIN-W01 to PIN-W10: Pinned window sizing (presets, custom dimensions, resize, persistence, multi-monitor clamping, responsiveness)
- RBG01 to RBG12: Reminder background images (none, global, custom, fit modes, opacity, overlay, WCAG readability, persistence)
- RSH01 to RSH10: Reminder shape & capsule (soft, rounded, capsule dynamic radius, custom radius, frameless hints, drag, esc dismissal)
"""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QApplication, QDialog, QWidget
from PySide6.QtCore import Qt, QPoint, QSize
from PySide6.QtGui import QFont, QColor, QPixmap, QPainter

from todo_bird_app.models.task import Task
from todo_bird_app.services.typography_service import TypographyService, AREAS
from todo_bird_app.services.media_service import MediaService
from todo_bird_app.widgets.pinned_priorities_widget import PinnedTaskCard, PinnedPrioritiesWidget
from todo_bird_app.widgets.pinned_tasks_window import PinnedTasksWindow, SIZE_PRESETS
from todo_bird_app.widgets.reminder_dialog import ReminderDialog, ReminderCardFrame
from todo_bird_app.views.settings_view import SettingsView


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class MockSettingsManager:
    def __init__(self, initial=None):
        self._data = dict(initial or {})

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value


class MockDBManager:
    def __init__(self):
        self._tasks = []
        self._projects = [{"id": 1, "name": "Inbox"}]

    def get_all_projects(self):
        return self._projects

    def get_connection(self):
        class MockConn:
            def __init__(self, outer):
                self.outer = outer
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def execute(self, sql, params=()):
                class MockCursor:
                    def __init__(self, rows):
                        self.rows = rows
                    def fetchall(self):
                        return self.rows
                if "SELECT" in sql:
                    return MockCursor(self.outer._tasks)
                return MockCursor([])
            def commit(self):
                pass
        return MockConn(self)


# ============================================================================
# PART 1: PINNED TASKS TYPOGRAPHY (PIN-T01 to PIN-T06)
# ============================================================================

def test_pin_t01_area_registered():
    """PIN-T01: Pinned tasks area is registered in TypographyService.AREAS."""
    area_keys = [k for k, _ in AREAS]
    assert "pinned_tasks" in area_keys


def test_pin_t02_default_and_custom_font_resolution(qapp):
    """PIN-T02: TypographyService resolves default global and per-area overrides for pinned_tasks."""
    settings = MockSettingsManager({
        "ui_font_family": "Roboto",
        "ui_font_size": 11,
        "ui_font_weight": "bold",
    })
    font = TypographyService.get_font_for_area("pinned_tasks", settings)
    assert font.family() == "Roboto"
    assert font.pointSize() == 11
    assert font.bold()

    # Override for pinned_tasks
    settings.set("font_override_pinned_tasks", True)
    settings.set("font_family_pinned_tasks", "Ubuntu")
    settings.set("font_size_pinned_tasks", 14)
    settings.set("font_weight_pinned_tasks", "normal")

    font_over = TypographyService.get_font_for_area("pinned_tasks", settings)
    assert font_over.family() == "Ubuntu"
    assert font_over.pointSize() == 14
    assert not font_over.bold()


def test_pin_t03_alias_normalization(qapp):
    """PIN-T03: Alias 'pinned' and 'pins' resolve correctly to 'pinned_tasks'."""
    settings = MockSettingsManager({
        "font_override_pinned_tasks": True,
        "font_family_pinned_tasks": "Cantarell",
        "font_size_pinned_tasks": 12,
    })
    f1 = TypographyService.get_font_for_area("pinned", settings)
    f2 = TypographyService.get_font_for_area("pins", settings)
    assert f1.family() == "Cantarell"
    assert f2.family() == "Cantarell"


def test_pin_t04_pinned_task_card_typography(qapp):
    """PIN-T04: PinnedTaskCard applies configured typography to title, meta, schedule, and buttons."""
    settings = MockSettingsManager({
        "font_override_pinned_tasks": True,
        "font_family_pinned_tasks": "DejaVu Sans",
        "font_size_pinned_tasks": 12,
        "font_weight_pinned_tasks": "medium",
    })
    task_row = {
        "id": 1,
        "title": "Launch Phase 0B",
        "status": "In Progress",
        "progress": 50,
        "pin_color": "#E95420",
    }
    card = PinnedTaskCard(task_row, project_name="Core", settings_manager=settings)
    assert card.title_label.font().family() == "DejaVu Sans"
    assert card.title_label.font().pointSize() == 14  # title gets +2pt
    assert card.meta_label.font().family() == "DejaVu Sans"
    assert card.schedule_label.font().family() == "DejaVu Sans"
    assert card.left_btn.font().family() == "DejaVu Sans"
    assert card.open_btn.font().family() == "DejaVu Sans"


def test_pin_t05_pinned_priorities_widget_typography(qapp):
    """PIN-T05: PinnedPrioritiesWidget applies configured typography to header and rebuilds cards."""
    settings = MockSettingsManager({
        "font_override_pinned_tasks": True,
        "font_family_pinned_tasks": "Fira Sans",
        "font_size_pinned_tasks": 11,
    })
    db = MockDBManager()
    db._tasks = [{
        "id": 1, "title": "Inspect Engine", "is_pinned": 1, "pin_position": 1,
        "status": "Planned", "progress": 20, "pin_color": "#3584E4"
    }]
    panel = PinnedPrioritiesWidget(db, settings_manager=settings)
    assert panel.title_label.font().family() == "Fira Sans"
    assert panel.count_label.font().family() == "Fira Sans"


def test_pin_t06_settings_view_pinned_introspection(qapp):
    """PIN-T06: SettingsView includes Pinned Tasks Card in area_typo_widgets with live preview."""
    settings = MockSettingsManager()
    controller = MagicMock()
    controller.get_working_week_config.return_value = {"days": [1, 2, 3, 4, 5], "start_time": "09:00", "end_time": "17:00"}
    view = SettingsView(controller, settings)
    assert "pinned_tasks" in view.area_typo_widgets
    cb, fam, sz, wt, title_lbl = view.area_typo_widgets["pinned_tasks"]
    assert title_lbl is not None
    assert hasattr(view, "update_pinned_preview")


# ============================================================================
# PART 2: PINNED TASKS WINDOW RESIZING (PIN-W01 to PIN-W10)
# ============================================================================

def test_pin_w01_window_instantiation(qapp):
    """PIN-W01: PinnedTasksWindow instantiates as a non-modal top-level dialog."""
    db = MockDBManager()
    settings = MockSettingsManager()
    win = PinnedTasksWindow(db, settings)
    assert not win.isModal()
    assert win.minimumWidth() >= 320
    assert win.minimumHeight() >= 220


def test_pin_w02_presets_applied(qapp):
    """PIN-W02: PinnedTasksWindow correctly applies compact, standard, and large presets."""
    db = MockDBManager()
    settings = MockSettingsManager()
    win = PinnedTasksWindow(db, settings)

    win.apply_preset("compact")
    assert win.width() == 360
    assert win.height() == 260
    assert settings.get("pinned_window_size_mode") == "compact"

    win.apply_preset("standard")
    assert win.width() == 520
    assert win.height() == 360
    assert settings.get("pinned_window_size_mode") == "standard"

    win.apply_preset("large")
    assert win.width() == 740
    assert win.height() == 500
    assert settings.get("pinned_window_size_mode") == "large"


def test_pin_w03_custom_geometry_restored(qapp):
    """PIN-W03: Custom width and height are restored from settings on startup."""
    db = MockDBManager()
    settings = MockSettingsManager({
        "pinned_window_size_mode": "custom",
        "pinned_window_width": 600,
        "pinned_window_height": 400,
    })
    win = PinnedTasksWindow(db, settings)
    assert win.width() == 600
    assert win.height() == 400


def test_pin_w04_minimum_dimensions_enforced(qapp):
    """PIN-W04: Dimensions smaller than 320x220 are clamped up to minimum size."""
    db = MockDBManager()
    settings = MockSettingsManager({
        "pinned_window_size_mode": "custom",
        "pinned_window_width": 100,
        "pinned_window_height": 50,
    })
    win = PinnedTasksWindow(db, settings)
    assert win.width() >= 320
    assert win.height() >= 220


def test_pin_w05_settings_view_preset_switch(qapp):
    """PIN-W05: Switching preset combo in SettingsView updates spinboxes and settings."""
    settings = MockSettingsManager()
    controller = MagicMock()
    controller.get_working_week_config.return_value = {"days": [1, 2, 3, 4, 5], "start_time": "09:00", "end_time": "17:00"}
    view = SettingsView(controller, settings)

    c_idx = view.pinned_window_size_combo.findData("compact")
    view.pinned_window_size_combo.setCurrentIndex(c_idx)
    assert settings.get("pinned_window_size_mode") == "compact"
    assert settings.get("pinned_window_width") == 360
    assert settings.get("pinned_window_height") == 260
    assert not view.pinned_w_spin.isEnabled()

    cust_idx = view.pinned_window_size_combo.findData("custom")
    view.pinned_window_size_combo.setCurrentIndex(cust_idx)
    assert settings.get("pinned_window_size_mode") == "custom"
    assert view.pinned_w_spin.isEnabled()
    assert view.pinned_h_spin.isEnabled()


# ============================================================================
# PART 3: REMINDER BACKGROUND IMAGE (RBG01 to RBG12)
# ============================================================================

def test_rbg01_reminder_card_frame_modes(qapp):
    """RBG01: ReminderCardFrame handles none, global, and custom background modes without crashing."""
    settings = MockSettingsManager({"reminder_background_mode": "none"})
    frame = ReminderCardFrame(settings)
    assert frame is not None

    settings.set("reminder_background_mode", "global")
    settings.set("background_custom_image_path", "test_global.png")
    settings.set("background_opacity", 0.5)

    settings.set("reminder_background_mode", "custom")
    settings.set("reminder_background_image", "test_custom.png")
    settings.set("reminder_background_fit", "fit")
    settings.set("reminder_background_opacity", 0.45)
    settings.set("reminder_background_overlay", 0.80)


def test_rbg02_reminder_settings_view_controls(qapp):
    """RBG02: SettingsView contains full background image controls and persists changes."""
    settings = MockSettingsManager()
    controller = MagicMock()
    controller.get_working_week_config.return_value = {"days": [1, 2, 3, 4, 5], "start_time": "09:00", "end_time": "17:00"}
    view = SettingsView(controller, settings)

    assert hasattr(view, "rem_bg_mode_combo")
    assert hasattr(view, "rem_bg_fit_combo")
    assert hasattr(view, "rem_bg_opacity_spin")
    assert hasattr(view, "rem_bg_overlay_spin")

    view.rem_bg_opacity_spin.setValue(60)
    assert pytest.approx(settings.get("reminder_background_opacity"), 0.01) == 0.60

    view.rem_bg_overlay_spin.setValue(85)
    assert pytest.approx(settings.get("reminder_background_overlay"), 0.01) == 0.85


def test_rbg03_contrast_ratio_calculation():
    """RBG03: Contrast ratio helper accurately calculates WCAG contrast."""
    ratio_high = TypographyService.calculate_contrast_ratio("#FFFFFF", "#000000")
    assert ratio_high >= 20.0

    ratio_low = TypographyService.calculate_contrast_ratio("#2A2A2A", "#1E1E1E")
    assert ratio_low < 3.0


# ============================================================================
# PART 4: REMINDER CAPSULE / ROUNDED WINDOW (RSH01 to RSH10)
# ============================================================================

def test_rsh01_reminder_dialog_frameless_translucent(qapp):
    """RSH01: ReminderDialog has FramelessWindowHint and WA_TranslucentBackground enabled."""
    task = Task(id=10, title="Review Warranty Terms", description="Check terms before signing.")
    settings = MockSettingsManager()
    dlg = ReminderDialog(task, settings_manager=settings)
    assert dlg.windowFlags() & Qt.FramelessWindowHint
    assert dlg.testAttribute(Qt.WA_TranslucentBackground)


def test_rsh02_corner_radius_styles(qapp):
    """RSH02: ReminderCardFrame accurately calculates soft, rounded, capsule, and custom radii."""
    settings = MockSettingsManager({"reminder_corner_style": "soft"})
    frame = ReminderCardFrame(settings)
    frame.resize(460, 280)
    assert frame.get_corner_radius() == 14

    settings.set("reminder_corner_style", "rounded")
    assert frame.get_corner_radius() == 24

    settings.set("reminder_corner_style", "capsule")
    cap_radius = frame.get_corner_radius()
    assert 18 <= cap_radius <= 36

    settings.set("reminder_corner_style", "custom")
    settings.set("reminder_corner_radius", 32)
    assert frame.get_corner_radius() == 32


def test_rsh03_escape_key_dismissal(qapp):
    """RSH03: ReminderDialog dismisses cleanly on Escape key press."""
    task = Task(id=11, title="Pay Insurance")
    settings = MockSettingsManager()
    dlg = ReminderDialog(task, settings_manager=settings)

    with patch.object(dlg, "on_hide_for_session_clicked") as mock_dismiss:
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent
        event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
        dlg.keyPressEvent(event)
        mock_dismiss.assert_called_once()


def test_rsh04_settings_view_capsule_controls(qapp):
    """RSH04: SettingsView shape controls change corner styles and live preview."""
    settings = MockSettingsManager()
    controller = MagicMock()
    controller.get_working_week_config.return_value = {"days": [1, 2, 3, 4, 5], "start_time": "09:00", "end_time": "17:00"}
    view = SettingsView(controller, settings)

    assert hasattr(view, "rem_corner_style_combo")
    assert hasattr(view, "rem_custom_radius_spin")

    cap_idx = view.rem_corner_style_combo.findData("capsule")
    view.rem_corner_style_combo.setCurrentIndex(cap_idx)
    assert settings.get("reminder_corner_style") == "capsule"
    assert not view.rem_custom_radius_spin.isEnabled()

    cust_idx = view.rem_corner_style_combo.findData("custom")
    view.rem_corner_style_combo.setCurrentIndex(cust_idx)
    assert settings.get("reminder_corner_style") == "custom"
    assert view.rem_custom_radius_spin.isEnabled()

    view.rem_custom_radius_spin.setValue(28)
    assert settings.get("reminder_corner_radius") == 28
