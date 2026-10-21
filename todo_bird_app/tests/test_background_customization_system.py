import hashlib
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QPushButton, QWidget

from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.database import DatabaseManager, PRODUCTION_DB_PATH
from todo_bird_app.gantt.gantt_theme import DEFAULT_GANTT_COLORS
from todo_bird_app.services.background_service import (
    BACKGROUND_COLOR_PRESETS,
    BACKGROUND_MODE_IMAGE,
    BACKGROUND_MODE_SOLID,
    BACKGROUND_MODE_THEME_DEFAULT,
    BACKGROUND_MODE_TRANSPARENT,
    BACKGROUND_MODES,
    BackgroundService,
)
from todo_bird_app.services.media_service import MediaService
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.ui.background_overlay import BackgroundOverlayWidget
from todo_bird_app.views.main_window import MainWindow
from todo_bird_app.widgets.project_calendar_dialog import ProjectCalendarDialog
from todo_bird_app.widgets.project_dialog import ProjectDialog
from todo_bird_app.widgets.task_dialog import TaskDialog


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def temp_app_env(tmp_path, qapp):
    db_path = tmp_path / "background_customization.db"
    db = DatabaseManager.for_test(str(db_path))
    with db.get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, color) VALUES (1, 'Inbox', '#2563EB')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, color) VALUES (2, 'Build', '#059669')"
        )
        conn.commit()
    settings = SettingsManager(db, config_dir=tmp_path / "config")
    controller = ThemeController(settings)
    qapp.theme_controller = controller
    yield db, settings, controller, tmp_path


def _process_events(qapp, loops=3):
    for _ in range(loops):
        qapp.processEvents()


def _create_image(path: Path, color: QColor = QColor("#DB2777")) -> Path:
    image = QImage(48, 32, QImage.Format.Format_ARGB32)
    image.fill(color)
    assert image.save(str(path), "PNG")
    return path


def _render_widget(widget, qapp, width=240, height=160, seed="#000000") -> QImage:
    widget.resize(width, height)
    widget.show()
    _process_events(qapp)
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(seed))
    painter = QPainter(image)
    try:
        widget.render(painter, QPoint(0, 0))
    finally:
        painter.end()
    return image


def _sample_color(image: QImage, x=12, y=12) -> QColor:
    return QColor(image.pixel(x, y))


def _color_distance(left: QColor, right: QColor) -> int:
    return (
        abs(left.red() - right.red())
        + abs(left.green() - right.green())
        + abs(left.blue() - right.blue())
    )


def _production_hash() -> str:
    path = Path(PRODUCTION_DB_PATH)
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "mode",
    [
        BACKGROUND_MODE_THEME_DEFAULT,
        BACKGROUND_MODE_SOLID,
        BACKGROUND_MODE_IMAGE,
        BACKGROUND_MODE_TRANSPARENT,
    ],
)
def test_global_background_modes_are_canonical(temp_app_env, mode):
    _db, settings, _controller, _tmp = temp_app_env
    BackgroundService.write_global(settings, {"mode": mode, "opacity": 0.5})

    config = BackgroundService.global_config(settings)

    assert config.mode == mode
    assert config.mode in BACKGROUND_MODES


def test_settings_background_mode_combo_exposes_four_modes(temp_app_env):
    db, settings, _controller, _tmp = temp_app_env
    view = __import__("todo_bird_app.views.settings_view", fromlist=["SettingsView"]).SettingsView(
        db,
        settings,
    )

    labels = [view.bg_mode_combo.itemText(i) for i in range(view.bg_mode_combo.count())]
    values = [view.bg_mode_combo.itemData(i) for i in range(view.bg_mode_combo.count())]

    for mode, label in [
        (BACKGROUND_MODE_THEME_DEFAULT, "Theme Default"),
        (BACKGROUND_MODE_SOLID, "Solid Color"),
        (BACKGROUND_MODE_IMAGE, "Image"),
        (BACKGROUND_MODE_TRANSPARENT, "Transparent"),
    ]:
        assert label in labels
        assert mode in values


@pytest.mark.parametrize(
    "view_id,color",
    [
        ("dashboard", "#172554"),
        ("gantt", "#312E81"),
        ("wbs", "#334155"),
        ("calendar", "#F5E9D6"),
        ("settings", "#FFFFFF"),
    ],
)
def test_per_view_background_override_wins(temp_app_env, view_id, color):
    _db, settings, _controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#111827", "opacity": 1.0},
    )
    BackgroundService.write_view_override(
        settings,
        view_id,
        {"mode": BACKGROUND_MODE_SOLID, "color": color, "opacity": 1.0},
    )

    config = BackgroundService.effective_config(settings, view_id)

    assert config.source == "view"
    assert not config.inherited
    assert config.color == QColor(color).name().upper()


def test_view_override_inherits_when_cleared(temp_app_env):
    _db, settings, _controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#1F2937"},
    )
    BackgroundService.write_view_override(
        settings,
        "dashboard",
        {"mode": BACKGROUND_MODE_SOLID, "color": "#FFFFFF"},
    )
    BackgroundService.clear_view_override(settings, "dashboard")

    config = BackgroundService.effective_config(settings, "dashboard")

    assert config.inherited
    assert config.source == "global"
    assert config.color == "#1F2937"


@pytest.mark.parametrize("preset", list(BACKGROUND_COLOR_PRESETS.values()))
def test_solid_color_presets_are_normalized(temp_app_env, preset):
    _db, settings, _controller, _tmp = temp_app_env
    _label, color = preset
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": color},
    )

    assert BackgroundService.global_config(settings).color == QColor(color).name().upper()


def test_custom_color_persists_as_hex_value(temp_app_env):
    _db, settings, _controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#B4111827"},
    )

    color = BackgroundService.global_config(settings).color

    assert color.startswith("#")
    assert color == "#B4111827"


def test_invalid_color_falls_back_to_theme_surface(temp_app_env):
    _db, settings, _controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "definitely-not-a-color"},
    )

    assert BackgroundService.global_config(settings).color == "#161821"


def test_solid_color_persistence_survives_settings_restart(temp_app_env):
    db, settings, _controller, tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#E5E7EB", "opacity": 0.75},
    )

    reloaded = SettingsManager(db, config_dir=tmp / "config")
    config = BackgroundService.global_config(reloaded)

    assert config.mode == BACKGROUND_MODE_SOLID
    assert config.color == "#E5E7EB"
    assert config.opacity == pytest.approx(0.75)


def test_live_global_solid_update_repaints_main_window_overlay(temp_app_env, qapp):
    db, settings, controller, _tmp = temp_app_env
    window = MainWindow(db, settings, controller)
    window.resize(980, 680)
    window.show()
    _process_events(qapp, loops=4)

    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#FFFFFF", "opacity": 1.0},
    )
    window.update_background_overlay()
    image = _render_widget(window.bg_overlay, qapp, seed="#000000")

    assert _color_distance(_sample_color(image), QColor("#FFFFFF")) < 12


def test_legacy_image_background_is_preserved(temp_app_env):
    _db, settings, _controller, _tmp = temp_app_env
    settings.set("background_mode", "custom")
    settings.set("background_custom_image_path", "backgrounds/legacy.png")
    settings.set("background_fit_mode", "fit")
    settings.set("background_opacity", 0.42)

    config = BackgroundService.global_config(settings)

    assert config.mode == BACKGROUND_MODE_IMAGE
    assert config.image == "backgrounds/legacy.png"
    assert config.fit == "fit"
    assert config.opacity == pytest.approx(0.42)


def test_image_selection_uses_managed_media_path(temp_app_env):
    _db, settings, _controller, tmp = temp_app_env
    source = _create_image(tmp / "background.png")
    meta = MediaService.import_media(str(source), category="backgrounds")
    assert meta is not None

    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_IMAGE, "image": meta["relative_path"], "opacity": 0.6},
    )

    config = BackgroundService.global_config(settings)
    assert config.mode == BACKGROUND_MODE_IMAGE
    assert config.image.startswith("backgrounds/")
    assert settings.get("background_mode") == "custom"


def test_image_opacity_is_independent_setting(temp_app_env):
    _db, settings, _controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_IMAGE, "image": "backgrounds/test.png", "opacity": 0.37},
    )

    assert BackgroundService.global_config(settings).opacity == pytest.approx(0.37)


@pytest.mark.parametrize("fit", ["fill", "fit", "stretch", "center", "tile"])
def test_image_fit_modes_are_supported(temp_app_env, fit):
    _db, settings, _controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_IMAGE, "image": "backgrounds/test.png", "fit": fit},
    )

    assert BackgroundService.global_config(settings).fit == fit


def test_missing_image_falls_back_without_crash(temp_app_env, qapp):
    _db, settings, _controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_IMAGE, "image": "backgrounds/missing-file.png"},
    )
    overlay = BackgroundOverlayWidget(settings_manager=settings)
    image = _render_widget(overlay, qapp)

    assert _color_distance(_sample_color(image), QColor("#161821")) < 60


def test_corrupt_image_is_safe(temp_app_env, qapp, tmp_path):
    _db, settings, _controller, _tmp = temp_app_env
    corrupt = tmp_path / "not_image.png"
    corrupt.write_text("not an image", encoding="utf-8")
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_IMAGE, "image": str(corrupt)},
    )
    overlay = BackgroundOverlayWidget(settings_manager=settings)
    image = _render_widget(overlay, qapp)

    assert image.width() == 240
    assert image.height() == 160


@pytest.mark.parametrize("opacity", [0.0, 0.25, 0.5, 1.0])
def test_transparent_mode_opacity_levels(temp_app_env, qapp, opacity):
    _db, settings, _controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_TRANSPARENT, "opacity": opacity},
    )
    overlay = BackgroundOverlayWidget(settings_manager=settings)
    image = _render_widget(overlay, qapp, seed="#FF00FF")
    sample = _sample_color(image)

    if opacity == 0.0:
        assert _color_distance(sample, QColor("#FF00FF")) < 8
    else:
        assert _color_distance(sample, QColor("#FF00FF")) > 20


def test_transparent_mode_does_not_make_buttons_translucent(temp_app_env, qapp):
    _db, settings, controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_TRANSPARENT, "opacity": 0.25},
    )
    button = QPushButton("Readable")
    button.setObjectName("PrimaryButton")
    controller.apply_theme()
    _process_events(qapp)

    assert not button.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert str(settings.get("accent_color", "#E95420")).upper() in qapp.styleSheet()


def test_dashboard_cards_remain_readable_above_background(temp_app_env, qapp):
    db, settings, controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#FFFFFF", "opacity": 1.0},
    )
    window = MainWindow(db, settings, controller)
    window.resize(1040, 720)
    window.show()
    _process_events(qapp, loops=5)

    cards = window.dashboard_view.findChildren(QWidget, "CardWidget")

    assert cards
    assert any("background-color" in card.styleSheet() for card in cards)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_theme_default_tracks_light_and_dark(temp_app_env, theme):
    _db, settings, controller, _tmp = temp_app_env
    BackgroundService.write_global(settings, {"mode": BACKGROUND_MODE_THEME_DEFAULT})
    controller.apply_theme(mode=theme)

    config = BackgroundService.global_config(settings)

    assert config.mode == BACKGROUND_MODE_THEME_DEFAULT
    assert settings.get("theme") == theme


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_solid_color_survives_light_and_dark_theme_switch(temp_app_env, theme):
    _db, settings, controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#334155"},
    )
    controller.apply_theme(mode=theme)

    assert BackgroundService.global_config(settings).color == "#334155"


def test_theme_switch_preserves_custom_background_mode(temp_app_env):
    _db, settings, controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_TRANSPARENT, "opacity": 0.25},
    )
    controller.apply_theme(mode="light")
    controller.apply_theme(mode="dark")

    assert BackgroundService.global_config(settings).mode == BACKGROUND_MODE_TRANSPARENT
    assert BackgroundService.global_config(settings).opacity == pytest.approx(0.25)


def test_background_color_is_independent_from_accent(temp_app_env):
    _db, settings, controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#1F2937"},
    )
    controller.apply_theme(accent_scheme="emerald")

    assert BackgroundService.global_config(settings).color == "#1F2937"
    assert settings.get("accent_color") == "#059669"


def test_accent_switch_does_not_overwrite_background(temp_app_env):
    _db, settings, controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_IMAGE, "image": "backgrounds/keep.png"},
    )
    controller.apply_theme(accent_scheme="rose")

    assert BackgroundService.global_config(settings).image == "backgrounds/keep.png"


def test_typography_change_does_not_reset_background(temp_app_env):
    _db, settings, controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#312E81"},
    )
    settings.set("ui_font_family", "Liberation Sans")
    settings.set("ui_font_size", 14)
    controller.apply_theme()

    config = BackgroundService.global_config(settings)
    assert config.mode == BACKGROUND_MODE_SOLID
    assert config.color == "#312E81"


def test_font_size_change_does_not_reset_background(temp_app_env):
    _db, settings, controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_TRANSPARENT, "opacity": 0.5},
    )
    settings.set("ui_font_size", 16)
    controller.apply_theme()

    assert BackgroundService.global_config(settings).mode == BACKGROUND_MODE_TRANSPARENT


def test_button_style_change_does_not_reset_background(temp_app_env):
    _db, settings, controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#172554"},
    )
    controller.apply_theme(button_style="glow")

    assert BackgroundService.global_config(settings).color == "#172554"


def test_per_view_live_update_reloads_overlay(temp_app_env, qapp):
    db, settings, controller, _tmp = temp_app_env
    window = MainWindow(db, settings, controller)
    window.resize(980, 680)
    window.show()
    window.navigation_controller.set_active_section("gantt")
    _process_events(qapp, loops=4)

    BackgroundService.write_view_override(
        settings,
        "gantt",
        {"mode": BACKGROUND_MODE_SOLID, "color": "#FFFFFF", "opacity": 1.0},
    )
    window.update_background_overlay()

    assert window.bg_overlay.view_id == "gantt"
    assert window.bg_overlay.config.source == "view"
    assert window.bg_overlay.bg_color == "#FFFFFF"


def test_background_update_requires_no_app_restart(temp_app_env, qapp):
    _db, settings, _controller, _tmp = temp_app_env
    overlay = BackgroundOverlayWidget(settings_manager=settings)
    before_id = id(overlay)
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#E5E7EB"},
    )
    overlay.reload_from_settings(settings)
    _process_events(qapp)

    assert id(overlay) == before_id
    assert overlay.config.color == "#E5E7EB"


def test_background_updates_do_not_create_duplicate_overlay_objects(temp_app_env):
    _db, settings, _controller, _tmp = temp_app_env
    overlay = BackgroundOverlayWidget(settings_manager=settings)

    for color in ("#111827", "#FFFFFF", "#334155"):
        BackgroundService.write_global(
            settings,
            {"mode": BACKGROUND_MODE_SOLID, "color": color},
        )
        overlay.reload_from_settings(settings)

    assert overlay.config.color == "#334155"


def test_gantt_background_customization_preserves_toolbar_and_readability(temp_app_env, qapp):
    db, settings, controller, _tmp = temp_app_env
    BackgroundService.write_view_override(
        settings,
        "gantt",
        {"mode": BACKGROUND_MODE_TRANSPARENT, "opacity": 0.5},
    )
    window = MainWindow(db, settings, controller)
    window.resize(1100, 760)
    window.show()
    window.navigation_controller.set_active_section("gantt")
    _process_events(qapp, loops=5)

    gantt = window.gantt_view
    refresh = gantt.refresh_btn

    assert window.bg_overlay.config.mode == BACKGROUND_MODE_TRANSPARENT
    assert refresh.isVisible()
    assert refresh.width() >= 70


@pytest.mark.parametrize(
    "color_value",
    [
        DEFAULT_GANTT_COLORS["planned_color"],
        DEFAULT_GANTT_COLORS["actual_color"],
        "#8B5CF6",
    ],
)
def test_gantt_forecast_actual_and_baseline_colors_remain_visible(temp_app_env, color_value):
    _db, _settings, _controller, _tmp = temp_app_env
    color = QColor(color_value)

    assert color.isValid()
    assert color.alpha() == 255


def test_gantt_refresh_remains_visible_after_background_override(temp_app_env, qapp):
    db, settings, controller, _tmp = temp_app_env
    BackgroundService.write_view_override(
        settings,
        "gantt",
        {"mode": BACKGROUND_MODE_SOLID, "color": "#F5E9D6"},
    )
    window = MainWindow(db, settings, controller)
    window.resize(1100, 760)
    window.show()
    window.navigation_controller.set_active_section("gantt")
    _process_events(qapp, loops=5)

    refresh = window.gantt_view.refresh_btn

    assert refresh.isVisible()
    assert refresh.width() >= 70


def test_wbs_rows_remain_readable_with_transparent_background(temp_app_env):
    _db, settings, _controller, _tmp = temp_app_env
    BackgroundService.write_view_override(
        settings,
        "wbs",
        {"mode": BACKGROUND_MODE_TRANSPARENT, "opacity": 0.25},
    )
    config = BackgroundService.effective_config(settings, "wbs")

    assert config.mode == BACKGROUND_MODE_TRANSPARENT
    assert config.opacity == pytest.approx(0.25)


def test_wbs_headers_remain_on_semantic_surfaces(temp_app_env, qapp):
    db, settings, controller, _tmp = temp_app_env
    window = MainWindow(db, settings, controller)
    window.resize(1000, 700)
    window.show()
    window.navigation_controller.set_active_section("projects")
    _process_events(qapp, loops=5)

    tree = window.projects_view.wbs_view.tree_view
    assert tree.header() is not None
    assert not tree.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def test_settings_current_view_override_updates_ui_state(temp_app_env):
    db, settings, _controller, _tmp = temp_app_env
    view = __import__("todo_bird_app.views.settings_view", fromlist=["SettingsView"]).SettingsView(
        db,
        settings,
    )
    view.bg_apply_to_combo.setCurrentIndex(view.bg_apply_to_combo.findData("view"))
    view._write_background_changes(mode=BACKGROUND_MODE_SOLID, color="#FFFFFF")

    assert BackgroundService.effective_config(settings, "settings").source == "view"
    assert view.btn_reset_bg_view.isEnabled()


@pytest.mark.parametrize("scale", [1.0, 1.25, 1.5, 2.0])
def test_overlay_renders_without_dpi_dependent_crash(temp_app_env, qapp, scale):
    _db, settings, _controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#334155"},
    )
    overlay = BackgroundOverlayWidget(settings_manager=settings)
    width = int(240 * scale)
    height = int(160 * scale)
    image = _render_widget(overlay, qapp, width=width, height=height)

    assert image.width() == width
    assert image.height() == height


def test_reset_current_view_background_restores_global(temp_app_env):
    _db, settings, _controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#111827"},
    )
    BackgroundService.write_view_override(
        settings,
        "dashboard",
        {"mode": BACKGROUND_MODE_SOLID, "color": "#FFFFFF"},
    )
    BackgroundService.clear_view_override(settings, "dashboard")

    assert BackgroundService.effective_config(settings, "dashboard").color == "#111827"


def test_reset_all_backgrounds_clears_global_and_view_overrides(temp_app_env):
    _db, settings, _controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#FFFFFF"},
    )
    BackgroundService.write_view_override(
        settings,
        "gantt",
        {"mode": BACKGROUND_MODE_SOLID, "color": "#111827"},
    )
    BackgroundService.reset_all(settings)

    assert BackgroundService.global_config(settings).mode == BACKGROUND_MODE_THEME_DEFAULT
    assert BackgroundService.view_overrides(settings) == {}


def test_real_main_window_overlay_renders_background_modes(temp_app_env, qapp):
    db, settings, controller, tmp = temp_app_env
    window = MainWindow(db, settings, controller)
    window.resize(980, 680)
    window.show()
    _process_events(qapp, loops=5)

    mode_configs = [
        {"mode": BACKGROUND_MODE_THEME_DEFAULT},
        {"mode": BACKGROUND_MODE_SOLID, "color": "#111827", "opacity": 1.0},
        {"mode": BACKGROUND_MODE_SOLID, "color": "#FFFFFF", "opacity": 1.0},
        {"mode": BACKGROUND_MODE_IMAGE, "image_color": "#DB2777", "opacity": 0.8},
        {"mode": BACKGROUND_MODE_TRANSPARENT, "opacity": 0.25},
        {"mode": BACKGROUND_MODE_TRANSPARENT, "opacity": 0.5},
    ]

    samples = []
    for idx, mode_config in enumerate(mode_configs):
        config = dict(mode_config)
        if config.get("mode") == BACKGROUND_MODE_IMAGE:
            source = _create_image(tmp / f"render_bg_{idx}.png", QColor(config.pop("image_color")))
            meta = MediaService.import_media(str(source), category="backgrounds")
            config["image"] = meta["relative_path"]
        BackgroundService.write_global(settings, config)
        window.update_background_overlay()
        overlay_image = _render_widget(window.bg_overlay, qapp, seed="#FF00FF")
        samples.append(_sample_color(overlay_image))

    assert any(_color_distance(samples[0], sample) > 20 for sample in samples[1:])


def test_dialogs_keep_readable_semantic_surfaces(temp_app_env):
    db, settings, _controller, _tmp = temp_app_env
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_TRANSPARENT, "opacity": 0.25},
    )
    task_dialog = TaskDialog([], db_manager=db, settings_manager=settings)
    project_dialog = ProjectDialog(settings_manager=settings)
    calendar_dialog = ProjectCalendarDialog(
        project_id=1,
        project_name="Build",
        db_manager=db,
    )

    for dialog in (task_dialog, project_dialog, calendar_dialog):
        assert not dialog.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        assert dialog.palette().window().color().isValid()


def test_restart_persistence_for_view_override(temp_app_env):
    db, settings, _controller, tmp = temp_app_env
    BackgroundService.write_view_override(
        settings,
        "calendar",
        {"mode": BACKGROUND_MODE_SOLID, "color": "#F5E9D6", "opacity": 0.7},
    )

    reloaded = SettingsManager(db, config_dir=tmp / "config")
    config = BackgroundService.effective_config(reloaded, "calendar")

    assert config.source == "view"
    assert config.color == "#F5E9D6"
    assert config.opacity == pytest.approx(0.7)


def test_cpm_settings_are_unchanged_by_background(temp_app_env):
    _db, settings, _controller, _tmp = temp_app_env
    before = settings.get("working_weekdays")
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#FFFFFF"},
    )

    assert settings.get("working_weekdays") == before


def test_baseline_revision_settings_are_unchanged_by_background(temp_app_env):
    _db, settings, _controller, _tmp = temp_app_env
    before = settings.get("gantt_plan_color")
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_TRANSPARENT, "opacity": 0.25},
    )

    assert settings.get("gantt_plan_color") == before


def test_actual_execution_settings_are_unchanged_by_background(temp_app_env):
    _db, settings, _controller, _tmp = temp_app_env
    before = settings.get("gantt_actual_color")
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_IMAGE, "image": "backgrounds/test.png"},
    )

    assert settings.get("gantt_actual_color") == before


def test_production_database_hash_unchanged_by_background_service(temp_app_env):
    _db, settings, _controller, _tmp = temp_app_env
    before = _production_hash()
    BackgroundService.write_global(
        settings,
        {"mode": BACKGROUND_MODE_SOLID, "color": "#334155"},
    )
    after = _production_hash()

    assert after == before
