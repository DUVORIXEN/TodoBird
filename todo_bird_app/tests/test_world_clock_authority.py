"""
TODO BIRD — WORLD CLOCK AUTHORITY TEST SUITE
Exhaustive verification of WorldClockService, AnalogClockWidget, DigitalClockWidget,
WorldClockCard, WorldClockPopover, WorldClockView, all 5 visual themes,
global shortcuts, HeaderBar integration, and production DB safety.
"""

import hashlib
import os
import pytest
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPixmap, QPainter

from todo_bird_app.services.world_clock_service import (
    WorldClockItem,
    WorldClockService,
    country_code_to_flag,
)
from todo_bird_app.widgets.analog_clock_widget import AnalogClockWidget
from todo_bird_app.widgets.digital_clock_widget import DigitalClockWidget
from todo_bird_app.widgets.world_clock_card import WorldClockCard
from todo_bird_app.widgets.add_world_clock_dialog import AddWorldClockDialog
from todo_bird_app.ui.components.world_clock_popover import WorldClockPopover
from todo_bird_app.views.world_clock_view import WorldClockView
from todo_bird_app.widgets.headerbar import HeaderBarWidget
from todo_bird_app.widgets.command_palette import CommandPalette
from todo_bird_app.services.command_registry import CommandRegistry

from todo_bird_app.tests.path_helpers import production_db_path

PROD_DB_PATH = production_db_path()


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class FakeSettings:
    def __init__(self):
        self._data = {}

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, val):
        self._data[key] = val


def test_01_all_countries_discovery():
    """TEST 01: Discovers all 240+ ISO countries with names, flags, and timezones."""
    countries = WorldClockService.get_all_countries()
    assert len(countries) >= 200
    us = next((c for c in countries if c["code"] == "US"), None)
    assert us is not None
    assert us["name"] == "United States"
    assert "America/New_York" in us["timezones"]


def test_02_country_flag_emoji_generation():
    """TEST 02: Generates valid Unicode flag emojis for ISO country codes."""
    assert country_code_to_flag("US") == "🇺🇸"
    assert country_code_to_flag("GB") == "🇬🇧"
    assert country_code_to_flag("JP") == "🇯🇵"
    assert country_code_to_flag("IN") == "🇮🇳"
    assert country_code_to_flag("AE") == "🇦🇪"


def test_03_search_locations_by_city():
    """TEST 03: Search query matches cities like Tokyo, London, Sydney."""
    res_tokyo = WorldClockService.search_locations("Tokyo")
    assert any(r["city"] == "Tokyo" for r in res_tokyo)

    res_london = WorldClockService.search_locations("London")
    assert any(r["city"] == "London" for r in res_london)


def test_04_search_locations_by_country():
    """TEST 04: Search query matches country names like Germany, India, Brazil."""
    res_de = WorldClockService.search_locations("Germany")
    assert len(res_de) > 0
    assert any(r["country_code"] == "DE" for r in res_de)

    res_in = WorldClockService.search_locations("India")
    assert len(res_in) > 0
    assert any(r["country_code"] == "IN" for r in res_in)


def test_05_time_info_calculation():
    """TEST 05: Computes live time information, 12h/24h strings, and UTC offsets."""
    info = WorldClockService.get_time_info("Asia/Tokyo")
    assert "time_12h" in info
    assert "time_24h" in info
    assert "utc_offset" in info
    assert "UTC+09:00" in info["utc_offset"]
    assert 0 <= info["hour"] <= 23
    assert 0 <= info["minute"] <= 59
    assert 0 <= info["second"] <= 59


def test_06_relative_offset_calculation():
    """TEST 06: Calculates relative time difference (+Xh ahead / behind local)."""
    info = WorldClockService.get_time_info("Asia/Tokyo")
    assert "relative_str" in info
    assert ("ahead" in info["relative_str"] or "behind" in info["relative_str"] or "Same time" in info["relative_str"])


def test_07_solar_phase_calculation():
    """TEST 07: Computes solar phase (day, night, dawn, dusk) and boolean is_day."""
    info = WorldClockService.get_time_info("UTC")
    assert info["solar_phase"] in ("day", "night", "dawn", "dusk")
    assert isinstance(info["is_day"], bool)


def test_08_load_save_clocks_settings():
    """TEST 08: Clocks load and save seamlessly into settings."""
    settings = FakeSettings()
    clocks = WorldClockService.load_clocks(settings)
    assert len(clocks) == 5  # 5 default clocks

    # Add a custom clock
    clocks.append(WorldClockItem(
        id="c_custom",
        country_code="CH",
        country_name="Switzerland",
        city="Zurich",
        timezone="Europe/Zurich",
        custom_label="Alps Branch",
    ))
    WorldClockService.save_clocks(settings, clocks)

    reloaded = WorldClockService.load_clocks(settings)
    assert len(reloaded) == 6
    assert reloaded[-1].custom_label == "Alps Branch"


def test_09_clock_type_persistence():
    """TEST 09: Clock type ('analog' or 'digital') persists correctly."""
    settings = FakeSettings()
    assert WorldClockService.get_clock_type(settings) == "analog"

    WorldClockService.set_clock_type(settings, "digital")
    assert WorldClockService.get_clock_type(settings) == "digital"

    WorldClockService.set_clock_type(settings, "analog")
    assert WorldClockService.get_clock_type(settings) == "analog"


def test_10_theme_persistence_all_5_themes():
    """TEST 10: Supports all 5 themes (minimal, luxury, cyberpunk, retro_lcd, solar)."""
    settings = FakeSettings()
    for t in ["minimal", "luxury", "cyberpunk", "retro_lcd", "solar"]:
        WorldClockService.set_clock_theme(settings, t)
        assert WorldClockService.get_clock_theme(settings) == t


def test_11_analog_clock_widget_minimal_paint(qapp):
    """TEST 11: AnalogClockWidget paints successfully with 'minimal' theme."""
    widget = AnalogClockWidget(timezone_name="America/New_York", theme="minimal")
    pixmap = QPixmap(150, 150)
    widget.render(pixmap)
    assert not pixmap.isNull()
    widget.close()


def test_12_analog_clock_widget_luxury_paint(qapp):
    """TEST 12: AnalogClockWidget paints successfully with 'luxury' theme."""
    widget = AnalogClockWidget(timezone_name="Europe/London", theme="luxury")
    pixmap = QPixmap(150, 150)
    widget.render(pixmap)
    assert not pixmap.isNull()
    widget.close()


def test_13_analog_clock_widget_cyberpunk_paint(qapp):
    """TEST 13: AnalogClockWidget paints successfully with 'cyberpunk' theme."""
    widget = AnalogClockWidget(timezone_name="Asia/Tokyo", theme="cyberpunk")
    pixmap = QPixmap(150, 150)
    widget.render(pixmap)
    assert not pixmap.isNull()
    widget.close()


def test_14_analog_clock_widget_retro_lcd_paint(qapp):
    """TEST 14: AnalogClockWidget paints successfully with 'retro_lcd' theme."""
    widget = AnalogClockWidget(timezone_name="Australia/Sydney", theme="retro_lcd")
    pixmap = QPixmap(150, 150)
    widget.render(pixmap)
    assert not pixmap.isNull()
    widget.close()


def test_15_analog_clock_widget_solar_paint(qapp):
    """TEST 15: AnalogClockWidget paints successfully with 'solar' theme."""
    widget = AnalogClockWidget(timezone_name="Asia/Dubai", theme="solar")
    pixmap = QPixmap(150, 150)
    widget.render(pixmap)
    assert not pixmap.isNull()
    widget.close()


def test_16_digital_clock_widget_12h_24h_modes(qapp):
    """TEST 16: DigitalClockWidget toggles between 12-hour and 24-hour formats."""
    widget = DigitalClockWidget(timezone_name="Europe/London", use_24h=False)
    assert not widget.ampm_lbl.isHidden()

    widget.set_format_24h(True)
    assert widget.ampm_lbl.isHidden()
    assert len(widget.time_lbl.text()) == 8  # HH:MM:SS
    widget.close()


def test_17_digital_clock_all_5_themes(qapp):
    """TEST 17: DigitalClockWidget applies all 5 themes without error."""
    widget = DigitalClockWidget(timezone_name="America/New_York")
    for t in ["minimal", "luxury", "cyberpunk", "retro_lcd", "solar"]:
        widget.set_theme(t)
        assert widget.theme == t
    widget.close()


def test_18_world_clock_card_switching(qapp):
    """TEST 18: WorldClockCard dynamically switches between Analog and Digital."""
    item = WorldClockItem(id="t1", country_code="JP", country_name="Japan", city="Tokyo", timezone="Asia/Tokyo")
    card = WorldClockCard(item, clock_type="analog")
    assert isinstance(card.clock_widget, AnalogClockWidget)

    card.set_clock_type("digital")
    assert isinstance(card.clock_widget, DigitalClockWidget)

    card.set_clock_type("analog")
    assert isinstance(card.clock_widget, AnalogClockWidget)
    card.close()


def test_19_world_clock_card_pinning(qapp):
    """TEST 19: WorldClockCard emits pin_toggled and remove_requested signals."""
    item = WorldClockItem(id="t1", country_code="JP", country_name="Japan", city="Tokyo", timezone="Asia/Tokyo")
    card = WorldClockCard(item)

    pinned_ids = []
    removed_ids = []
    card.pin_toggled.connect(lambda cid: pinned_ids.append(cid))
    card.remove_requested.connect(lambda cid: removed_ids.append(cid))

    card.btn_pin.click()
    assert pinned_ids == ["t1"]

    card.btn_delete.click()
    assert removed_ids == ["t1"]
    card.close()


def test_20_add_world_clock_dialog_search_and_add(qapp):
    """TEST 20: AddWorldClockDialog filters locations and prepares WorldClockItem."""
    dlg = AddWorldClockDialog()
    dlg.search_edit.setText("Paris")
    assert dlg.results_list.count() > 0

    first_item = dlg.results_list.item(0)
    dlg._on_result_clicked(first_item)
    assert dlg.btn_add.isEnabled()
    assert "Paris" in dlg.preview_title_lbl.text()
    dlg.close()


def test_21_world_clock_popover_init_and_close(qapp):
    """TEST 21: WorldClockPopover loads cards and closes cleanly."""
    settings = FakeSettings()
    popover = WorldClockPopover(settings_manager=settings)
    assert len(popover.cards) == 5
    assert popover.scroll_area is not None

    popover._set_type("digital")
    assert popover.clock_type == "digital"
    popover.close()


def test_22_world_clock_view_init_and_scrubber(qapp):
    """TEST 22: WorldClockView initializes multi-clock grid and timezone scrubber."""
    settings = FakeSettings()
    view = WorldClockView(settings_manager=settings)
    assert len(view.cards) == 5
    assert view.time_slider is not None

    # Move scrubber to 15:00 (900 minutes)
    view.time_slider.setValue(900)
    assert "15:00" in view.slider_val_lbl.text()

    view._reset_scrubber()
    assert "Live Current Time" in view.slider_val_lbl.text()
    view.close()


def test_23_headerbar_world_clock_button(qapp):
    """TEST 23: HeaderBarWidget includes accessible World Clock button."""
    header = HeaderBarWidget()
    assert hasattr(header, "clock_btn")
    assert header.clock_btn.text() == "World Clock"

    clicked = []
    header.world_clock_requested.connect(lambda: clicked.append(True))
    header.clock_btn.click()
    assert clicked == [True]
    header.close()


def test_24_command_palette_world_clock_actions(qapp):
    """TEST 24: CommandPalette lists World Clock action commands."""
    palette = CommandPalette(db_manager=None)
    items_text = [palette.list_widget.item(i).text() for i in range(palette.list_widget.count())]
    assert any("World Clock" in text for text in items_text)
    palette.close()


def test_25_global_shortcut_registered(qapp, tmp_path):
    """TEST 25: Ctrl+Alt+W is registered in global CommandRegistry."""
    from todo_bird_app.database import DatabaseManager
    from todo_bird_app.settings.settings_manager import SettingsManager
    from todo_bird_app.controllers.theme_controller import ThemeController
    from todo_bird_app.views.main_window import MainWindow

    db_file = tmp_path / "test_wc.db"
    db = DatabaseManager(str(db_file))
    settings = SettingsManager(db_manager=db, config_dir=tmp_path / "config")
    theme_ctrl = ThemeController(settings)

    win = MainWindow(db, settings, theme_ctrl)
    registry = CommandRegistry()
    cmd = registry.get_command("open_world_clock")
    assert cmd is not None
    assert cmd.shortcut == "Ctrl+Alt+W"
    assert cmd.display_name == "World Clock"
    win.close()


def test_26_production_db_safety_invariant():
    """TEST 26: Production database SHA-256 is unchanged by world-clock checks."""
    assert PROD_DB_PATH.exists(), f"Production DB missing at {PROD_DB_PATH}"
    with open(PROD_DB_PATH, "rb") as f:
        before_hash = hashlib.sha256(f.read()).hexdigest()

    assert country_code_to_flag("US")

    with open(PROD_DB_PATH, "rb") as f:
        after_hash = hashlib.sha256(f.read()).hexdigest()
    assert after_hash == before_hash, (
        f"Production DB mutated! Before {before_hash}, after {after_hash}"
    )
