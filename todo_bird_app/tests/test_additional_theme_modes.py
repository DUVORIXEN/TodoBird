"""
Automated unit and integration test suite for the 4 additional theme modes:
- System / Auto
- OLED Midnight Black
- Warm Paper / Sepia
- Nord / Slate Blue
plus existing Dark Mode and Light Mode.
"""

import os
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.database import DatabaseManager
from todo_bird_app.services.appearance_service import (
    AppearanceService,
    THEME_ITEMS,
    THEME_MODES,
    contrast_ratio,
    is_system_dark,
    semantic_tokens_for,
)
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.themes.tokens import (
    DARK_PALETTE,
    LIGHT_PALETTE,
    NORD_PALETTE,
    OLED_PALETTE,
    THEME_PALETTES,
    WARM_PAPER_PALETTE,
)
from todo_bird_app.views.settings_view import SettingsView

REQUIRED_SEMANTIC_ROLES = [
    "APP_BACKGROUND",
    "SURFACE_1",
    "SURFACE_2",
    "SURFACE_3",
    "BORDER_SUBTLE",
    "BORDER_NORMAL",
    "BORDER_STRONG",
    "TEXT_PRIMARY",
    "TEXT_SECONDARY",
    "TEXT_MUTED",
    "TEXT_DISABLED",
    "ACCENT",
    "ACCENT_HOVER",
    "ACCENT_PRESSED",
    "ACCENT_SUBTLE",
    "TEXT_ON_ACCENT",
    "SUCCESS",
    "WARNING",
    "DANGER",
    "INFO",
    "FOCUS_RING",
    "GANTT_PLANNED",
    "GANTT_ACTUAL",
    "GANTT_BASELINE",
    "GANTT_GRID",
    "GANTT_HEADER",
    "GANTT_TEXT",
    "GANTT_TEXT_MUTED",
]


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def test_all_theme_modes_registered():
    expected_modes = {"dark", "light", "system", "oled", "warm_paper", "nord"}
    assert THEME_MODES == expected_modes
    assert len(THEME_ITEMS) == 6
    registered_keys = {code for code, _label in THEME_ITEMS}
    assert registered_keys == expected_modes


def test_theme_palettes_export():
    assert "dark" in THEME_PALETTES
    assert "light" in THEME_PALETTES
    assert "oled" in THEME_PALETTES
    assert "warm_paper" in THEME_PALETTES
    assert "nord" in THEME_PALETTES
    for name, palette in THEME_PALETTES.items():
        assert "bg_root" in palette, f"Missing bg_root in {name}"
        assert "bg_card" in palette, f"Missing bg_card in {name}"
        assert "text_primary" in palette, f"Missing text_primary in {name}"


@pytest.mark.parametrize("theme_mode", ["dark", "light", "system", "oled", "warm_paper", "nord"])
def test_appearance_service_resolves_each_theme(qapp, theme_mode):
    settings = SettingsManager()
    settings.set("theme", theme_mode)
    settings.set("accent_color", "#2563EB")

    appearance = AppearanceService.read(settings, app=qapp)
    assert appearance.theme == theme_mode

    if theme_mode in {"dark", "oled", "nord"}:
        assert appearance.is_dark is True
    elif theme_mode in {"light", "warm_paper"}:
        assert appearance.is_dark is False
    elif theme_mode == "system":
        assert appearance.is_dark == is_system_dark(qapp)

    # Every required semantic role must be present and valid
    for role in REQUIRED_SEMANTIC_ROLES:
        assert role in appearance.tokens, f"Role {role} missing from {theme_mode}"
        if role != "ACCENT_SUBTLE":
            assert QColor(appearance.tokens[role]).isValid(), f"Invalid color for {role} in {theme_mode}"


def test_oled_palette_characteristics(qapp):
    settings = SettingsManager()
    settings.set("theme", "oled")
    appearance = AppearanceService.read(settings, app=qapp)

    tokens = appearance.tokens
    assert tokens["APP_BACKGROUND"] == "#000000"
    assert tokens["SURFACE_1"] == "#090A0F"
    assert tokens["TEXT_PRIMARY"] == "#FFFFFF"
    assert tokens["bg_root"] == "#000000"
    assert tokens["bg_sidebar"] == "#000000"

    # WCAG Contrast verification: Pure white on black is 21:1 AAA
    ratio_primary = contrast_ratio(tokens["TEXT_PRIMARY"], tokens["APP_BACKGROUND"])
    assert ratio_primary >= 20.0
    ratio_card = contrast_ratio(tokens["TEXT_PRIMARY"], tokens["SURFACE_1"])
    assert ratio_card >= 18.0


def test_warm_paper_palette_characteristics(qapp):
    settings = SettingsManager()
    settings.set("theme", "warm_paper")
    appearance = AppearanceService.read(settings, app=qapp)

    tokens = appearance.tokens
    assert tokens["APP_BACKGROUND"] == "#F8F4EC"
    assert tokens["SURFACE_1"] == "#FCFBF7"
    assert tokens["TEXT_PRIMARY"] == "#2C241D"
    assert tokens["bg_root"] == "#F8F4EC"

    # WCAG Contrast verification: roasted espresso on warm ivory > 10:1 AAA
    ratio_card = contrast_ratio(tokens["TEXT_PRIMARY"], tokens["SURFACE_1"])
    assert ratio_card >= 10.0
    ratio_secondary = contrast_ratio(tokens["TEXT_SECONDARY"], tokens["SURFACE_1"])
    assert ratio_secondary >= 4.5


def test_nord_palette_characteristics(qapp):
    settings = SettingsManager()
    settings.set("theme", "nord")
    appearance = AppearanceService.read(settings, app=qapp)

    tokens = appearance.tokens
    assert tokens["APP_BACKGROUND"] == "#242933"
    assert tokens["SURFACE_1"] == "#2E3440"
    assert tokens["TEXT_PRIMARY"] == "#ECEFF4"
    assert tokens["HEADING_SECONDARY"] == "#88C0D0"

    # WCAG Contrast verification
    ratio_card = contrast_ratio(tokens["TEXT_PRIMARY"], tokens["SURFACE_1"])
    assert ratio_card >= 9.0


@pytest.mark.parametrize("theme_mode", ["dark", "light", "system", "oled", "warm_paper", "nord"])
def test_theme_controller_applies_all_modes(qapp, theme_mode):
    settings = SettingsManager()
    controller = ThemeController(settings)

    controller.apply_theme(mode=theme_mode, accent_color="#2563EB")
    appearance = AppearanceService.read(settings, app=qapp)

    assert controller.current_mode == theme_mode
    assert "@" not in qapp.styleSheet()
    assert len(qapp.styleSheet()) > 5000


def test_settings_view_theme_combo_roundtrip(qapp):
    settings = SettingsManager()
    db = DatabaseManager.for_test(":memory:")
    view = SettingsView(db, settings_manager=settings)

    combo = view.theme_combo
    data_items = [combo.itemData(i) for i in range(combo.count())]
    assert data_items == ["dark", "light", "system", "oled", "warm_paper", "nord"]

    # Test selecting each option updates settings_manager
    for mode in ["oled", "warm_paper", "nord", "system", "light", "dark"]:
        idx = combo.findData(mode)
        assert idx >= 0
        combo.setCurrentIndex(idx)
        assert settings.get("theme") == mode

    # Test refresh_data restores combo index
    settings.set("theme", "warm_paper")
    view.refresh_data()
    assert combo.currentData() == "warm_paper"
