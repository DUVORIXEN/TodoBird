"""
TODO BIRD — Dashboard Light-Mode Popup Theme Authority

Focused witness for the Phase 2E dashboard hover-tooltip defect:
native dashboard chart tooltips must resolve their palette from the current
semantic theme immediately before showing, including live theme switches.
"""

import hashlib
import inspect
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QMenu, QWidget, QToolTip

from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.database import DatabaseManager, PRODUCTION_DB_PATH
from todo_bird_app.services.appearance_service import (
    AppearanceService,
    contrast_ratio,
    qpalette_from_tokens,
    semantic_tokens_for,
)
from todo_bird_app.services.schedule_details_formatter import ScheduleDetailsModel
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.ui.components.schedule_details_popover import (
    ScheduleDetailsPopover,
)
from todo_bird_app.views.main_window import MainWindow
from todo_bird_app.widgets.dashboard_charts import (
    AdvancedCapacityChart,
    AdvancedStatusChart,
    AdvancedWeeklyActivityChart,
    AnimatedDashboardChart,
    ChartHitRegion,
    apply_dashboard_tooltip_theme,
    dashboard_tooltip_html,
    dashboard_tooltip_theme,
)
from todo_bird_app.widgets.sidebar import SidebarWidget


MIN_AA_CONTRAST = 4.5


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


def _set_widget_theme(widget: QWidget, *, is_dark: bool, accent: str = "#3584E4"):
    theme = "dark" if is_dark else "light"
    tokens = semantic_tokens_for(is_dark, accent)
    palette = qpalette_from_tokens(tokens)
    widget.setProperty("todoBirdTheme", theme)
    widget.setProperty("todoBirdAccent", accent)
    widget.setPalette(palette)
    app = QApplication.instance()
    if app is not None:
        app.setProperty("todoBirdTheme", theme)
        app.setProperty("todoBirdAccent", accent)
        app.setPalette(palette)
    return tokens


def _capacity_chart(qapp, *, is_dark: bool) -> AdvancedCapacityChart:
    chart = AdvancedCapacityChart()
    _set_widget_theme(chart, is_dark=is_dark)
    chart.set_animations_enabled(False)
    chart.set_values(actual_m=90, planned_m=180, capacity_m=480)
    chart.resize(420, 180)
    chart.show()
    qapp.processEvents()
    chart.grab()
    return chart


def _status_chart(qapp, *, is_dark: bool) -> AdvancedStatusChart:
    chart = AdvancedStatusChart()
    _set_widget_theme(chart, is_dark=is_dark)
    chart.set_animations_enabled(False)
    chart.set_counts(planned=4, in_progress=2, blocked=1, completed=5)
    chart.resize(360, 220)
    chart.show()
    qapp.processEvents()
    chart.grab()
    return chart


def _weekly_chart(qapp, *, is_dark: bool) -> AdvancedWeeklyActivityChart:
    chart = AdvancedWeeklyActivityChart()
    _set_widget_theme(chart, is_dark=is_dark)
    chart.set_animations_enabled(False)
    chart.set_daily_data(
        [
            ("Mon", 2, 3),
            ("Tue", 4, 3),
            ("Wed", 1, 2),
            ("Thu", 3, 4),
            ("Fri", 5, 6),
        ]
    )
    chart.resize(480, 240)
    chart.show()
    qapp.processEvents()
    chart.grab()
    return chart


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _first_region(chart: AnimatedDashboardChart) -> ChartHitRegion:
    assert chart._hit_regions, "chart render did not create hover regions"
    return chart._hit_regions[0]


def test_01_native_dashboard_tooltip_light_capacity_colors(qapp):
    chart = _capacity_chart(qapp, is_dark=False)
    theme = apply_dashboard_tooltip_theme(chart)
    assert theme.theme == "light"
    assert QColor(theme.background).lightness() > 180
    assert QColor(theme.text_primary).lightness() < 90
    assert QToolTip.palette().color(QPalette.ToolTipBase).name() == theme.background
    assert QToolTip.palette().color(QPalette.ToolTipText).name() == theme.text_primary
    chart.close()


def test_02_native_dashboard_tooltip_light_status_colors(qapp):
    chart = _status_chart(qapp, is_dark=False)
    theme = apply_dashboard_tooltip_theme(chart)
    assert theme.theme == "light"
    assert contrast_ratio(theme.text_primary, theme.background) >= MIN_AA_CONTRAST
    assert contrast_ratio(theme.text_secondary, theme.background) >= MIN_AA_CONTRAST
    chart.close()


def test_03_native_dashboard_tooltip_light_weekly_colors(qapp):
    chart = _weekly_chart(qapp, is_dark=False)
    theme = apply_dashboard_tooltip_theme(chart)
    assert theme.theme == "light"
    assert theme.background == "#eef2f7"
    assert theme.text_primary == "#111827"
    chart.close()


def test_04_native_dashboard_tooltip_dark_capacity_colors(qapp):
    chart = _capacity_chart(qapp, is_dark=True)
    theme = apply_dashboard_tooltip_theme(chart)
    assert theme.theme == "dark"
    assert QColor(theme.background).lightness() < 90
    assert QColor(theme.text_primary).lightness() > 190
    assert QToolTip.palette().color(QPalette.ToolTipBase).name() == theme.background
    assert QToolTip.palette().color(QPalette.ToolTipText).name() == theme.text_primary
    chart.close()


def test_05_native_dashboard_tooltip_dark_status_colors(qapp):
    chart = _status_chart(qapp, is_dark=True)
    theme = apply_dashboard_tooltip_theme(chart)
    assert theme.theme == "dark"
    assert contrast_ratio(theme.text_primary, theme.background) >= MIN_AA_CONTRAST
    assert contrast_ratio(theme.text_secondary, theme.background) >= MIN_AA_CONTRAST
    chart.close()


def test_06_native_dashboard_tooltip_dark_weekly_colors(qapp):
    chart = _weekly_chart(qapp, is_dark=True)
    theme = apply_dashboard_tooltip_theme(chart)
    assert theme.theme == "dark"
    assert theme.background == "#2a2b3d"
    assert theme.text_primary == "#f4f7fb"
    chart.close()


def test_07_dashboard_custom_popup_markup_light(qapp):
    chart = _capacity_chart(qapp, is_dark=False)
    markup = dashboard_tooltip_html("Capacity\nRemaining headroom", chart)
    theme = dashboard_tooltip_theme(chart)
    assert 'data-todo-bird-dashboard-tooltip="1"' in markup
    assert f"background-color: {theme.background}" in markup
    assert f"color: {theme.text_primary}" in markup
    assert f"color: {theme.text_secondary}" in markup
    assert "Remaining headroom" in markup
    chart.close()


def test_08_dashboard_custom_popup_markup_dark(qapp):
    chart = _capacity_chart(qapp, is_dark=True)
    markup = dashboard_tooltip_html("Status\nBlocked: 1", chart)
    theme = dashboard_tooltip_theme(chart)
    assert 'data-todo-bird-dashboard-tooltip="1"' in markup
    assert f"background-color: {theme.background}" in markup
    assert f"border: 1px solid {theme.border}" in markup
    assert "Blocked: 1" in markup
    chart.close()


def test_09_primary_text_contrast_light(qapp):
    chart = _capacity_chart(qapp, is_dark=False)
    theme = dashboard_tooltip_theme(chart)
    assert contrast_ratio(theme.text_primary, theme.background) >= MIN_AA_CONTRAST
    chart.close()


def test_10_primary_text_contrast_dark(qapp):
    chart = _capacity_chart(qapp, is_dark=True)
    theme = dashboard_tooltip_theme(chart)
    assert contrast_ratio(theme.text_primary, theme.background) >= MIN_AA_CONTRAST
    chart.close()


def test_11_secondary_text_contrast_light(qapp):
    chart = _weekly_chart(qapp, is_dark=False)
    theme = dashboard_tooltip_theme(chart)
    assert contrast_ratio(theme.text_secondary, theme.background) >= MIN_AA_CONTRAST
    chart.close()


def test_12_secondary_text_contrast_dark(qapp):
    chart = _weekly_chart(qapp, is_dark=True)
    theme = dashboard_tooltip_theme(chart)
    assert contrast_ratio(theme.text_secondary, theme.background) >= MIN_AA_CONTRAST
    chart.close()


def test_13_border_is_distinct_light(qapp):
    chart = _status_chart(qapp, is_dark=False)
    theme = dashboard_tooltip_theme(chart)
    assert QColor(theme.border).isValid()
    assert theme.border != theme.background
    assert QColor(theme.border).lightness() < QColor(theme.background).lightness()
    chart.close()


def test_14_border_is_distinct_dark(qapp):
    chart = _status_chart(qapp, is_dark=True)
    theme = dashboard_tooltip_theme(chart)
    assert QColor(theme.border).isValid()
    assert theme.border != theme.background
    assert QColor(theme.border).lightness() > QColor(theme.background).lightness()
    chart.close()


def test_15_live_switch_light_to_dark_existing_dashboard_chart(qapp):
    chart = _capacity_chart(qapp, is_dark=False)
    light_theme = apply_dashboard_tooltip_theme(chart)
    _set_widget_theme(chart, is_dark=True)
    dark_theme = apply_dashboard_tooltip_theme(chart)
    assert light_theme.theme == "light"
    assert dark_theme.theme == "dark"
    assert light_theme.background != dark_theme.background
    assert QToolTip.palette().color(QPalette.ToolTipBase).name() == dark_theme.background
    chart.close()


def test_16_live_switch_dark_to_light_existing_dashboard_chart(qapp):
    chart = _capacity_chart(qapp, is_dark=True)
    dark_theme = apply_dashboard_tooltip_theme(chart)
    _set_widget_theme(chart, is_dark=False)
    light_theme = apply_dashboard_tooltip_theme(chart)
    assert dark_theme.theme == "dark"
    assert light_theme.theme == "light"
    assert QColor(light_theme.background).lightness() > QColor(dark_theme.background).lightness()
    assert QToolTip.palette().color(QPalette.ToolTipText).name() == light_theme.text_primary
    chart.close()


def test_17_chart_created_before_theme_switch_uses_current_app_theme(qapp):
    chart = AdvancedCapacityChart()
    _set_widget_theme(chart, is_dark=True)
    chart.setProperty("todoBirdTheme", "")
    _set_widget_theme(QWidget(), is_dark=False)
    theme = apply_dashboard_tooltip_theme(chart)
    assert theme.theme == "light"
    chart.close()


def test_18_chart_created_after_theme_switch_inherits_app_theme(qapp):
    _set_widget_theme(QWidget(), is_dark=False)
    chart = AdvancedCapacityChart()
    chart.setPalette(qapp.palette())
    theme = apply_dashboard_tooltip_theme(chart)
    assert theme.theme == "light"
    assert theme.background == "#eef2f7"
    chart.close()


def test_19_dashboard_tooltip_call_sites_are_centralized():
    source = inspect.getsource(AnimatedDashboardChart)
    assert "QToolTip.showText" in source
    assert source.count("QToolTip.showText") == 1
    assert "dashboard_tooltip_html(" in source
    assert "apply_dashboard_tooltip_theme(" in source


def test_20_no_hardcoded_unreadable_light_dashboard_tooltip_colors():
    module_source = Path("todo_bird_app/widgets/dashboard_charts.py").read_text()
    forbidden = [
        "background-color: #1e1e2e",
        "background-color: #181825",
        "background-color: #2a2b3d",
        "color: #cdd6f4",
        "color: #ffffff",
    ]
    lowered = module_source.lower()
    for token in forbidden:
        assert token not in lowered


def test_21_settings_menu_qss_still_theme_tokenized():
    light = Path("todo_bird_app/themes/light.qss").read_text()
    dark = Path("todo_bird_app/themes/dark.qss").read_text()
    assert "QMenu {" in light and "@bg_card" in light and "@text_primary" in light
    assert "QMenu {" in dark and "@bg_card" in dark and "@text_primary" in dark


def test_22_sidebar_tooltip_palette_not_regressed(qapp, tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "sidebar_tooltip.db"))
    settings = SettingsManager(db, config_dir=tmp_path / "config")
    settings.set("theme", "light")
    controller = ThemeController(settings)
    controller.apply_theme("light")
    sidebar = SidebarWidget(settings_manager=settings)
    AppearanceService.apply_to_widget(sidebar, AppearanceService.read(settings, app=qapp))
    tooltip_theme = apply_dashboard_tooltip_theme(sidebar)
    assert tooltip_theme.theme == "light"
    assert contrast_ratio(tooltip_theme.text_primary, tooltip_theme.background) >= MIN_AA_CONTRAST
    sidebar.close()


def test_23_schedule_details_popover_not_regressed(qapp):
    model = ScheduleDetailsModel(title="Tooltip Theme Guard", project_name="Theme")
    popover = ScheduleDetailsPopover(model, is_dark=False)
    style = popover.styleSheet()
    assert "#FFFFFF" in style or "#F8FAFC" in style
    assert "#0F172A" in style or "#111827" in style
    popover.close()


def test_24_production_database_unchanged_by_dashboard_popup_theme_checks(qapp):
    assert PRODUCTION_DB_PATH.exists(), f"Production DB missing at {PRODUCTION_DB_PATH}"
    before = _sha256(PRODUCTION_DB_PATH)
    chart = AdvancedCapacityChart()
    _set_widget_theme(chart, is_dark=False)
    theme = apply_dashboard_tooltip_theme(chart)
    html = dashboard_tooltip_html("DB Safety\nNo write path", chart)
    assert theme.theme == "light"
    assert "No write path" in html
    chart.close()
    after = _sha256(PRODUCTION_DB_PATH)
    assert after == before


def test_25_real_main_window_temp_db_dashboard_hover_light_dark(qapp, tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "dashboard_tooltip_main.db"))
    settings = SettingsManager(db, config_dir=tmp_path / "config")
    controller = ThemeController(settings)
    window = MainWindow(db, settings, controller)
    window.show()
    controller.apply_theme("light")
    qapp.processEvents()

    chart = window.dashboard_view.capacity_stacked_bar
    chart.set_animations_enabled(False)
    chart.set_values(actual_m=120, planned_m=240, capacity_m=480)
    chart.resize(420, 180)
    qapp.processEvents()
    chart.grab()
    region = _first_region(chart)
    chart._show_dashboard_tooltip(chart.mapToGlobal(region.center_point().toPoint()), region)
    light_theme = dashboard_tooltip_theme(chart)
    assert light_theme.theme == "light"
    assert QToolTip.palette().color(QPalette.ToolTipBase).name() == light_theme.background

    controller.apply_theme("dark")
    qapp.processEvents()
    chart._show_dashboard_tooltip(chart.mapToGlobal(region.center_point().toPoint()), region)
    dark_theme = dashboard_tooltip_theme(chart)
    assert dark_theme.theme == "dark"
    assert QToolTip.palette().color(QPalette.ToolTipBase).name() == dark_theme.background

    window.close()


def test_26_real_main_window_temp_db_dashboard_created_after_switch(qapp, tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "dashboard_tooltip_created_after.db"))
    settings = SettingsManager(db, config_dir=tmp_path / "config2")
    controller = ThemeController(settings)
    controller.apply_theme("light")
    window = MainWindow(db, settings, controller)
    window.show()
    qapp.processEvents()
    chart = window.dashboard_view.status_donut
    theme = apply_dashboard_tooltip_theme(chart)
    assert theme.theme == "light"
    assert contrast_ratio(theme.text_primary, theme.background) >= MIN_AA_CONTRAST
    window.close()


def test_27_qtooltip_global_qss_tokens_remain_in_light_and_dark():
    light = Path("todo_bird_app/themes/light.qss").read_text()
    dark = Path("todo_bird_app/themes/dark.qss").read_text()
    for content in (light, dark):
        assert "QToolTip {" in content
        assert "background-color: @SURFACE_2;" in content
        assert "color: @TEXT_PRIMARY;" in content
        assert "border: 1px solid @BORDER_STRONG;" in content


def test_28_qmenu_runtime_palette_still_readable(qapp):
    menu = QMenu()
    _set_widget_theme(menu, is_dark=False)
    menu.addAction("Settings")
    theme = apply_dashboard_tooltip_theme(menu)
    assert theme.theme == "light"
    assert contrast_ratio(theme.text_primary, theme.background) >= MIN_AA_CONTRAST
    menu.close()
