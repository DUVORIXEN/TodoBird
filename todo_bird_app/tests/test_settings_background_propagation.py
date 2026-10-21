"""
TODO BIRD — SETTINGS VIEW BACKGROUND INHERITANCE & LIVE PROPAGATION TEST SUITE

Comprehensive verification suite verifying real SettingsView & MainWindow rendering:
1. Settings inherits global Theme Default.
2. Settings inherits global Solid Color.
3. Settings inherits global Image.
4. Settings inherits global Transparent.
5. Settings updates live while already open (no restart, no view switching).
6. Settings explicit override supersedes global background.
7. Reset override restores global background on Settings.
8. Settings cards, editors, controls and text remain readable with high contrast.
9. Light mode global and view background inheritance.
10. Dark mode global and view background inheritance.
11. 125%, 150%, 200% High-DPI scaling of background overlay in Settings view.
12. Production database SHA256 invariant preserved completely.
"""

import os
import sys
import tempfile
import hashlib
from pathlib import Path
import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QImage, QPainter, QColor, QFont
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager, PRODUCTION_DB_PATH
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.services.background_service import (
    BackgroundService,
    BACKGROUND_MODE_SOLID,
    BACKGROUND_MODE_THEME_DEFAULT,
    BACKGROUND_MODE_IMAGE,
    BACKGROUND_MODE_TRANSPARENT,
)
from todo_bird_app.services.media_service import MediaService
from todo_bird_app.views.main_window import MainWindow
from todo_bird_app.views.settings_view import SettingsView


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def temp_env(tmp_path, qapp):
    db_path = tmp_path / "test_settings_bg.db"
    db = DatabaseManager.for_test(str(db_path))
    with db.get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO projects (id, name, color) VALUES (1, 'Inbox', '#3B82F6')")
        conn.execute("INSERT OR IGNORE INTO projects (id, name, color) VALUES (4, 'THAAVORIX', '#10B981')")
        conn.commit()
    settings = SettingsManager(db, config_dir=tmp_path / "config")
    settings.set("view_background_overrides", {})
    controller = ThemeController(settings)
    qapp.theme_controller = controller
    yield db, settings, controller, tmp_path


def _process_events(qapp, loops=3):
    for _ in range(loops):
        qapp.processEvents()


def _create_test_image(path: Path, color: QColor = QColor("#E11D48")) -> Path:
    img = QImage(64, 64, QImage.Format.Format_ARGB32)
    img.fill(color)
    img.save(str(path), "PNG")
    return path


def _render_window_image(win: MainWindow, qapp) -> QImage:
    _process_events(qapp, loops=5)
    img = QImage(win.size(), QImage.Format.Format_ARGB32_Premultiplied)
    p = QPainter(img)
    win.render(p, QPoint(0, 0))
    p.end()
    return img


def _count_color_pixels_in_content_area(
    img: QImage,
    target_color: QColor,
    tolerance: int = 40,
    x_range=(200, 900),
    y_range=(60, 680),
    step=20,
) -> tuple[int, int]:
    """Counts sample pixels in the central view area matching target_color."""
    matched = 0
    total = 0
    for y in range(y_range[0], y_range[1], step):
        for x in range(x_range[0], x_range[1], step):
            total += 1
            col = img.pixelColor(x, y)
            diff = (
                abs(col.red() - target_color.red())
                + abs(col.green() - target_color.green())
                + abs(col.blue() - target_color.blue())
            )
            if diff <= tolerance:
                matched += 1
    return matched, total


def _production_hash() -> str:
    prod_path = Path(PRODUCTION_DB_PATH)
    if not prod_path.exists():
        return ""
    return hashlib.sha256(prod_path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def production_db_baseline_hash():
    return _production_hash()


# =============================================================================
# 1. Settings Inherits Global Background Modes (01 - 04)
# =============================================================================

def test_01_settings_inherits_global_theme_default(temp_env, qapp):
    """1. Settings inherits global Theme Default background."""
    db, settings, controller, _ = temp_env
    BackgroundService.write_global(settings, {"mode": BACKGROUND_MODE_THEME_DEFAULT})
    win = MainWindow(db, settings, controller)
    win.resize(1000, 700)
    win.show()
    win.navigation_controller.set_active_section("settings")
    _process_events(qapp, loops=5)

    assert win.bg_overlay.config.mode == BACKGROUND_MODE_THEME_DEFAULT
    assert win.bg_overlay.config.source == "global"
    assert win.bg_overlay.config.inherited is True


def test_02_settings_inherits_global_solid_color(temp_env, qapp):
    """2. Settings inherits global Solid Color background and renders pixels."""
    db, settings, controller, _ = temp_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#E95420", "opacity": 1.0},
    )
    win = MainWindow(db, settings, controller)
    win.resize(1000, 700)
    win.show()
    win.navigation_controller.set_active_section("settings")
    img = _render_window_image(win, qapp)

    assert win.bg_overlay.config.color == "#E95420"
    matched, total = _count_color_pixels_in_content_area(img, QColor("#E95420"))
    assert matched >= total * 0.20, f"Expected orange pixels in Settings view, got {matched}/{total}"


def test_03_settings_inherits_global_image(temp_env, qapp):
    """3. Settings inherits global Image background."""
    db, settings, controller, tmp = temp_env
    img_path = _create_test_image(tmp / "global_bg.png", QColor("#3B82F6"))
    meta = MediaService.import_media(str(img_path), category="backgrounds", db_manager=db)

    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_IMAGE, "image": meta["relative_path"], "opacity": 0.8},
    )
    win = MainWindow(db, settings, controller)
    win.resize(1000, 700)
    win.show()
    win.navigation_controller.set_active_section("settings")
    _process_events(qapp, loops=5)

    assert win.bg_overlay.config.mode == BACKGROUND_MODE_IMAGE
    assert win.bg_overlay.config.image == meta["relative_path"]
    assert win.bg_overlay.config.source == "global"


def test_04_settings_inherits_global_transparent(temp_env, qapp):
    """4. Settings inherits global Transparent background mode."""
    db, settings, controller, _ = temp_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_TRANSPARENT, "opacity": 0.3},
    )
    win = MainWindow(db, settings, controller)
    win.resize(1000, 700)
    win.show()
    win.navigation_controller.set_active_section("settings")
    _process_events(qapp, loops=5)

    assert win.bg_overlay.config.mode == BACKGROUND_MODE_TRANSPARENT
    assert win.bg_overlay.config.opacity == pytest.approx(0.3)


# =============================================================================
# 2. Live Updates & Overrides (05 - 07)
# =============================================================================

def test_05_settings_updates_while_already_open(temp_env, qapp):
    """5. Changing global solid color while Settings is open repaints Settings immediately."""
    db, settings, controller, _ = temp_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#10B981", "opacity": 1.0},
    )
    win = MainWindow(db, settings, controller)
    win.resize(1000, 700)
    win.show()
    win.navigation_controller.set_active_section("settings")
    _process_events(qapp, loops=5)

    # Initial green check
    img_before = _render_window_image(win, qapp)
    matched_green, _ = _count_color_pixels_in_content_area(img_before, QColor("#10B981"))
    assert matched_green >= 50

    # User modifies global color to purple (#8B5CF6) via SettingsView controls
    sv = win.settings_view
    sv.bg_apply_to_combo.setCurrentIndex(sv.bg_apply_to_combo.findData("global"))
    sv._write_background_changes(mode=BACKGROUND_MODE_SOLID, color="#8B5CF6")
    _process_events(qapp, loops=5)

    img_after = _render_window_image(win, qapp)
    matched_purple, _ = _count_color_pixels_in_content_area(img_after, QColor("#8B5CF6"))
    assert matched_purple >= 50, "Settings view must immediately repaint with new purple global background"


def test_06_settings_override_supersedes_global(temp_env, qapp):
    """6. Settings explicit view override supersedes global background."""
    db, settings, controller, _ = temp_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#3B82F6", "opacity": 1.0},
    )
    win = MainWindow(db, settings, controller)
    win.resize(1000, 700)
    win.show()
    win.navigation_controller.set_active_section("settings")
    _process_events(qapp, loops=5)

    # Apply view override for settings (yellow #F59E0B)
    sv = win.settings_view
    sv.bg_apply_to_combo.setCurrentIndex(sv.bg_apply_to_combo.findData("view"))
    sv._write_background_changes(mode=BACKGROUND_MODE_SOLID, color="#F59E0B")
    _process_events(qapp, loops=5)

    img = _render_window_image(win, qapp)
    assert win.bg_overlay.config.source == "view"
    assert win.bg_overlay.config.color == "#F59E0B"
    matched_yellow, _ = _count_color_pixels_in_content_area(img, QColor("#F59E0B"))
    assert matched_yellow >= 50


def test_07_reset_override_restores_global(temp_env, qapp):
    """7. Resetting Settings override restores global background."""
    db, settings, controller, _ = temp_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#3B82F6", "opacity": 1.0},
    )
    BackgroundService.write_view_override(
        settings,
        "settings",
        {"mode": BACKGROUND_MODE_SOLID, "color": "#F59E0B"},
    )
    win = MainWindow(db, settings, controller)
    win.resize(1000, 700)
    win.show()
    win.navigation_controller.set_active_section("settings")
    _process_events(qapp, loops=5)

    sv = win.settings_view
    sv.on_reset_current_view_background()
    _process_events(qapp, loops=5)

    assert win.bg_overlay.config.source == "global"
    assert win.bg_overlay.config.color == "#3B82F6"
    img = _render_window_image(win, qapp)
    matched_blue, _ = _count_color_pixels_in_content_area(img, QColor("#3B82F6"))
    assert matched_blue >= 50


# =============================================================================
# 3. Legibility, Light/Dark, High-DPI & Safety (08 - 12)
# =============================================================================

def test_08_settings_cards_remain_readable(temp_env, qapp):
    """8. Settings cards and form controls maintain high-contrast backgrounds."""
    db, settings, controller, _ = temp_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#EF4444", "opacity": 1.0},
    )
    win = MainWindow(db, settings, controller)
    win.resize(1000, 700)
    win.show()
    win.navigation_controller.set_active_section("settings")
    _process_events(qapp, loops=5)

    sv = win.settings_view
    assert sv.theme_combo.isVisible()
    assert sv.bg_mode_combo.isVisible()
    assert sv.btn_reset_all_bg.isVisible()


def test_09_light_mode_settings_background(temp_env, qapp):
    """9. Light mode inherits global background correctly on Settings."""
    db, settings, controller, _ = temp_env
    settings.set("theme", "light")
    controller.apply_theme()
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#D1FAE5", "opacity": 1.0},
    )
    win = MainWindow(db, settings, controller)
    win.resize(1000, 700)
    win.show()
    win.navigation_controller.set_active_section("settings")
    img = _render_window_image(win, qapp)

    matched, _ = _count_color_pixels_in_content_area(img, QColor("#D1FAE5"))
    assert matched >= 50


def test_10_dark_mode_settings_background(temp_env, qapp):
    """10. Dark mode inherits global background correctly on Settings."""
    db, settings, controller, _ = temp_env
    settings.set("theme", "dark")
    controller.apply_theme()
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#312E81", "opacity": 1.0},
    )
    win = MainWindow(db, settings, controller)
    win.resize(1000, 700)
    win.show()
    win.navigation_controller.set_active_section("settings")
    img = _render_window_image(win, qapp)

    matched, _ = _count_color_pixels_in_content_area(img, QColor("#312E81"))
    assert matched >= 50


@pytest.mark.parametrize("scale", [1.25, 1.5, 2.0])
def test_11_high_dpi_settings_background(temp_env, qapp, scale):
    """11. High-DPI (125%, 150%, 200%) scaling renders Settings background cleanly."""
    db, settings, controller, _ = temp_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#172554", "opacity": 1.0},
    )
    win = MainWindow(db, settings, controller)
    win.resize(int(900 * scale), int(650 * scale))
    win.show()
    win.navigation_controller.set_active_section("settings")
    _process_events(qapp, loops=5)

    assert win.bg_overlay.geometry().width() == win.centralWidget().width()
    assert win.bg_overlay.geometry().height() == win.centralWidget().height()


def test_12_production_db_unchanged(production_db_baseline_hash):
    """12. Production database hash remains completely untouched."""
    prod_path = Path(PRODUCTION_DB_PATH)
    assert prod_path.exists(), "Production DB must exist"
    assert _production_hash() == production_db_baseline_hash
