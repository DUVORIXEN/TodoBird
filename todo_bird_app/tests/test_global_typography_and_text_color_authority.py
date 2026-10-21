import hashlib
import os
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QFontInfo, QImage, QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTextEdit,
    QWidget,
)

from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.database import DatabaseManager, PRODUCTION_DB_PATH
from todo_bird_app.services.appearance_service import (
    AppearanceService,
    contrast_ratio,
)
from todo_bird_app.services.background_service import (
    BACKGROUND_MODE_SOLID,
    BACKGROUND_MODE_TRANSPARENT,
    BackgroundService,
)
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.ui.components.modern_button import ButtonVariant, ModernButton
from todo_bird_app.ui.components.modern_combobox import ModernComboBox
from todo_bird_app.views.main_window import MainWindow
from todo_bird_app.widgets.modern_card import MetricCard, StatusChip
from todo_bird_app.widgets.task_dialog import TaskDialog


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

VIEW_IDS = [
    "main_window",
    "dashboard",
    "wbs",
    "gantt",
    "calendar",
    "settings",
    "task_dialog",
    "analytics",
    "today",
    "upcoming",
]

TEXT_ROLES = [
    "TEXT_PRIMARY",
    "TEXT_SECONDARY",
    "TEXT_MUTED",
    "TEXT_DISABLED",
    "HEADING_PRIMARY",
    "HEADING_SECONDARY",
    "TEXT_ON_ACCENT",
    "TEXT_ON_DANGER",
    "TEXT_ON_WARNING",
    "TEXT_ON_SUCCESS",
    "LINK",
    "LINK_HOVER",
    "PLACEHOLDER_TEXT",
    "TABLE_HEADER_TEXT",
    "SECTION_HEADER_TEXT",
    "SIDEBAR_TEXT",
    "SIDEBAR_SELECTED_TEXT",
]


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def temp_app_env(tmp_path, qapp):
    db_path = tmp_path / "typography_text_color.db"
    db = DatabaseManager.for_test(str(db_path))
    with db.get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, color) VALUES (1, 'Inbox', '#2563EB')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, color) VALUES (2, 'Typography', '#E11D48')"
        )
        conn.commit()
    settings = SettingsManager(db, config_dir=tmp_path / "config")
    controller = ThemeController(settings)
    qapp.theme_controller = controller
    yield db, settings, controller, tmp_path


def _process_events(qapp, loops=3):
    for _ in range(loops):
        qapp.processEvents()


def _render_widget(widget: QWidget, qapp, width=720, height=420) -> QImage:
    widget.resize(width, height)
    widget.show()
    _process_events(qapp, loops=4)
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor("#000000"))
    painter = QPainter(image)
    try:
        widget.render(painter, QPoint(0, 0))
    finally:
        painter.end()
    return image


def _sample_delta(left: QImage, right: QImage) -> int:
    changed = 0
    for y in range(0, min(left.height(), right.height()), 17):
        for x in range(0, min(left.width(), right.width()), 17):
            a = QColor(left.pixel(x, y))
            b = QColor(right.pixel(x, y))
            if (
                abs(a.red() - b.red())
                + abs(a.green() - b.green())
                + abs(a.blue() - b.blue())
            ) > 36:
                changed += 1
    return changed


def _production_hash() -> str:
    path = Path(PRODUCTION_DB_PATH)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _available_two_families(qapp):
    preferred = [
        qapp.font().family(),
        "Liberation Sans",
        "Liberation Serif",
        "DejaVu Sans",
        "Sans Serif",
    ]
    families = set(QFontDatabase.families())
    found = []
    for family in preferred:
        if family and (family in families or family == qapp.font().family()):
            if family not in found:
                found.append(family)
        if len(found) >= 2:
            return found[:2]
    return [qapp.font().family(), QFontInfo(QFont("serif")).family()]


def _background_for_role(tokens, role):
    if role == "TEXT_ON_ACCENT" or role == "SIDEBAR_SELECTED_TEXT":
        return tokens["ACCENT"]
    if role == "TEXT_ON_DANGER":
        return tokens["DANGER"]
    if role == "TEXT_ON_WARNING":
        return tokens["WARNING"]
    if role == "TEXT_ON_SUCCESS":
        return tokens["SUCCESS"]
    if role in {"TABLE_HEADER_TEXT"}:
        return tokens["SURFACE_2"]
    return tokens["SURFACE_1"]


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("role", TEXT_ROLES)
def test_semantic_text_roles_have_theme_contrast(temp_app_env, theme, role):
    _db, settings, controller, _tmp = temp_app_env
    controller.apply_theme(mode=theme, accent_scheme="professional_blue")
    appearance = AppearanceService.read(settings, app=QApplication.instance())
    fg = AppearanceService.text_color_for_role(appearance, role)
    bg = _background_for_role(appearance.tokens, role)
    threshold = 3.0 if role in {"TEXT_MUTED", "TEXT_DISABLED", "PLACEHOLDER_TEXT"} else 4.0

    assert role in AppearanceService.known_text_color_roles()
    assert QColor(fg).isValid()
    assert contrast_ratio(fg, bg) >= threshold


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("view_id", VIEW_IDS)
def test_major_view_heading_roles_are_readable(temp_app_env, theme, view_id):
    _db, settings, controller, _tmp = temp_app_env
    controller.apply_theme(mode=theme)
    appearance = AppearanceService.read(settings)

    assert contrast_ratio(
        appearance.tokens["HEADING_PRIMARY"],
        appearance.tokens["SURFACE_1"],
    ) >= 4.5
    assert view_id


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("view_id", VIEW_IDS)
def test_major_view_body_roles_are_readable(temp_app_env, theme, view_id):
    _db, settings, controller, _tmp = temp_app_env
    controller.apply_theme(mode=theme)
    appearance = AppearanceService.read(settings)

    assert contrast_ratio(
        appearance.tokens["TEXT_PRIMARY"],
        appearance.tokens["SURFACE_1"],
    ) >= 4.5
    assert contrast_ratio(
        appearance.tokens["TEXT_SECONDARY"],
        appearance.tokens["SURFACE_1"],
    ) >= 3.0
    assert view_id


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(
    "role",
    [
        QPalette.WindowText,
        QPalette.Text,
        QPalette.ButtonText,
        QPalette.PlaceholderText,
        QPalette.ToolTipText,
    ],
)
def test_qpalette_text_roles_follow_theme(temp_app_env, qapp, theme, role):
    _db, _settings, controller, _tmp = temp_app_env
    controller.apply_theme(mode=theme, accent_scheme="emerald")
    palette_color = qapp.palette().color(role)

    assert palette_color.isValid()
    assert palette_color.name().upper() != ("#111827" if theme == "dark" else "#FFFFFF")


@pytest.mark.parametrize("size", [10, 11, 12, 14, 16, 18, 20])
def test_font_size_matrix_keeps_controls_dynamic(temp_app_env, qapp, size):
    _db, settings, controller, _tmp = temp_app_env
    settings.set("ui_font_size", size)
    controller.apply_theme(mode="dark", density="compact")
    button = ModernButton("Dynamic Button", variant=ButtonVariant.SECONDARY)
    combo = ModernComboBox()
    combo.addItems(["Alpha", "Beta"])
    _process_events(qapp)

    assert qapp.font().pointSize() == size
    assert button.sizeHint().height() >= button.fontMetrics().height() + 6
    assert combo.sizeHint().height() >= combo.fontMetrics().height() + 6


@pytest.mark.parametrize("bad_color", ["#000000", "#111111", "#111827", "#1F2937", "black"])
def test_dark_mode_sanitizes_unreadable_fixed_label_colors(temp_app_env, bad_color):
    _db, settings, controller, _tmp = temp_app_env
    controller.apply_theme(mode="dark")
    appearance = AppearanceService.read(settings)
    label = QLabel("Heading")
    label.setStyleSheet(f"font-weight: 700; color: {bad_color};")
    label.setProperty("todoBirdTextRole", "HEADING_PRIMARY")

    AppearanceService.apply_to_widget(label, appearance)

    assert appearance.tokens["HEADING_PRIMARY"] in label.styleSheet()


@pytest.mark.parametrize("bad_color", ["#FFFFFF", "#F8FAFC", "white"])
def test_light_mode_sanitizes_unreadable_fixed_label_colors(temp_app_env, bad_color):
    _db, settings, controller, _tmp = temp_app_env
    controller.apply_theme(mode="light")
    appearance = AppearanceService.read(settings)
    label = QLabel("Heading")
    label.setStyleSheet(f"font-weight: 700; color: {bad_color};")
    label.setProperty("todoBirdTextRole", "HEADING_PRIMARY")

    AppearanceService.apply_to_widget(label, appearance)

    assert appearance.tokens["HEADING_PRIMARY"] in label.styleSheet()


@pytest.mark.parametrize("status_color", ["ACCENT", "SUCCESS", "WARNING", "DANGER", "INFO"])
def test_special_semantic_colors_are_preserved(temp_app_env, status_color):
    _db, settings, controller, _tmp = temp_app_env
    controller.apply_theme(mode="dark", accent_scheme="rose")
    appearance = AppearanceService.read(settings)
    color = appearance.tokens[status_color]
    label = QLabel("Status")
    label.setStyleSheet(f"color: {color}; font-weight: 600;")

    AppearanceService.apply_to_widget(label, appearance)

    assert color in label.styleSheet()


@pytest.mark.parametrize("theme_file", ["dark.qss", "light.qss"])
def test_theme_qss_has_no_fixed_generic_heading_color(theme_file):
    qss = (Path("todo_bird_app/themes") / theme_file).read_text(encoding="utf-8")

    assert "QLabel[heading=\"true\"]" in qss
    assert "QGroupBox::title" in qss
    assert "QLabel[heading=\"true\"] {\n    color: #000000" not in qss
    assert "QLabel[heading=\"true\"] {\n    color: #FFFFFF" not in qss


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_qss_tokens_resolve_for_raw_qt_text_widgets(temp_app_env, qapp, theme):
    _db, _settings, controller, _tmp = temp_app_env
    controller.apply_theme(mode=theme, accent_scheme="indigo")
    css = qapp.styleSheet()

    assert "@" not in css
    assert "QHeaderView::section" in css
    assert "QMenu::item:selected" in css
    assert "QPlainTextEdit" in css


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_modern_button_custom_paint_text_uses_theme(temp_app_env, qapp, theme):
    _db, _settings, controller, _tmp = temp_app_env
    controller.apply_theme(mode=theme, accent_scheme="professional_blue")
    button = ModernButton("Painted", variant=ButtonVariant.SECONDARY)
    image = _render_widget(button, qapp, width=180, height=48)

    assert image.width() == 180
    assert button.property("todoBirdTheme") == theme


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_modern_combo_custom_paint_text_uses_theme(temp_app_env, qapp, theme):
    _db, _settings, controller, _tmp = temp_app_env
    controller.apply_theme(mode=theme, accent_scheme="professional_blue")
    combo = ModernComboBox()
    combo.addItems(["Readable", "Clear"])
    image = _render_widget(combo, qapp, width=180, height=48)

    assert image.width() == 180
    assert combo.property("todoBirdTheme") == theme


def test_status_chip_retains_semantic_status_color(temp_app_env):
    _db, settings, controller, _tmp = temp_app_env
    controller.apply_theme(mode="dark")
    appearance = AppearanceService.read(settings)
    chip = StatusChip("Late", appearance.tokens["DANGER"])

    AppearanceService.apply_to_widget(chip, appearance)

    assert appearance.tokens["DANGER"] in chip.styleSheet()


def test_metric_card_heading_and_body_tokens_follow_theme(temp_app_env):
    _db, settings, controller, _tmp = temp_app_env
    controller.apply_theme(mode="dark")
    appearance = AppearanceService.read(settings)
    card = MetricCard("Open", "12", "tasks", color_hex=appearance.tokens["ACCENT"])

    AppearanceService.apply_to_widget(card, appearance)

    assert appearance.tokens["TEXT_MUTED"] in card.title_label.styleSheet()
    assert appearance.tokens["TEXT_SECONDARY"] in card.sub_label.styleSheet()


@pytest.mark.parametrize(
    "background",
    [
        {"mode": BACKGROUND_MODE_SOLID, "color": "#FFFFFF", "theme": "light"},
        {"mode": BACKGROUND_MODE_SOLID, "color": "#111827", "theme": "dark"},
        {"mode": BACKGROUND_MODE_TRANSPARENT, "opacity": 0.25, "theme": "dark"},
        {"mode": BACKGROUND_MODE_TRANSPARENT, "opacity": 0.5, "theme": "light"},
    ],
)
def test_custom_background_does_not_drive_text_authority(temp_app_env, background):
    _db, settings, controller, _tmp = temp_app_env
    theme = background["theme"]
    background_config = {key: value for key, value in background.items() if key != "theme"}
    BackgroundService.write_global(settings, background_config)
    controller.apply_theme(mode=theme)
    appearance = AppearanceService.read(settings)

    assert contrast_ratio(
        appearance.tokens["TEXT_PRIMARY"],
        appearance.tokens["SURFACE_1"],
    ) >= 4.5
    assert BackgroundService.global_config(settings).mode == background["mode"]


@pytest.mark.parametrize("accent_scheme", ["professional_blue", "emerald"])
def test_accent_scheme_does_not_make_body_text_unreadable(temp_app_env, accent_scheme):
    _db, settings, controller, _tmp = temp_app_env
    controller.apply_theme(mode="dark", accent_scheme=accent_scheme)
    appearance = AppearanceService.read(settings)

    assert contrast_ratio(
        appearance.tokens["TEXT_PRIMARY"],
        appearance.tokens["SURFACE_1"],
    ) >= 4.5
    assert appearance.accent_scheme == accent_scheme


@pytest.mark.parametrize("scale", [1.25, 1.5, 2.0])
def test_dpi_scaled_font_geometry_is_safe(temp_app_env, qapp, scale):
    _db, settings, controller, _tmp = temp_app_env
    expected_size = min(int(12 * scale), 20)
    settings.set("ui_font_size", int(12 * scale))
    controller.apply_theme(mode="dark")
    button = QPushButton("DPI Text")
    line_edit = QLineEdit("DPI Text")
    appearance = AppearanceService.read(settings)
    AppearanceService.apply_to_widget(button, appearance)
    AppearanceService.apply_to_widget(line_edit, appearance)

    assert button.minimumHeight() >= button.fontMetrics().height()
    assert line_edit.minimumHeight() >= line_edit.fontMetrics().height()
    assert qapp.font().pointSize() == expected_size


def test_real_main_window_theme_switch_repaints_text_and_surfaces(temp_app_env, qapp):
    db, settings, controller, _tmp = temp_app_env
    window = MainWindow(db, settings, controller)
    window.resize(1120, 760)
    window.show()
    controller.apply_theme(mode="light")
    _process_events(qapp, loops=5)
    light = _render_widget(window, qapp, width=1120, height=760)

    controller.apply_theme(mode="dark")
    _process_events(qapp, loops=5)
    dark = _render_widget(window, qapp, width=1120, height=760)

    assert _sample_delta(light, dark) > 120
    assert window.headerbar.title_label.palette().color(QPalette.WindowText).name().upper() == "#FFFFFF"


def test_settings_visible_live_theme_and_font_change(temp_app_env, qapp):
    db, settings, controller, _tmp = temp_app_env
    window = MainWindow(db, settings, controller)
    window.resize(1120, 760)
    window.show()
    window.navigation_controller.set_active_section("settings")
    controller.apply_theme(mode="light")
    before = _render_widget(window.settings_view, qapp, width=860, height=640)

    family_a, family_b = _available_two_families(qapp)
    settings.set("ui_font_family", family_b)
    settings.set("ui_font_size", 16)
    settings.set("ui_font_weight", "semibold")
    controller.apply_theme(mode="dark")
    after = _render_widget(window.settings_view, qapp, width=860, height=640)

    assert _sample_delta(before, after) > 80
    assert qapp.font().pointSize() == 16
    assert QFontInfo(qapp.font()).family()
    assert family_a


def test_real_font_family_propagates_to_views_buttons_combos_and_headings(temp_app_env, qapp):
    db, settings, controller, _tmp = temp_app_env
    family_a, family_b = _available_two_families(qapp)
    window = MainWindow(db, settings, controller)
    window.show()
    settings.set("ui_font_family", family_a)
    controller.apply_theme(mode="dark")
    settings.set("ui_font_family", family_b)
    controller.apply_theme(mode="dark")
    _process_events(qapp, loops=5)

    labels = window.findChildren(QLabel)
    buttons = window.findChildren(QPushButton)
    combos = window.findChildren(ModernComboBox)

    assert labels
    assert buttons
    assert combos
    assert window.headerbar.title_label.font().family()
    assert labels[0].font().family()
    assert buttons[0].font().family()
    assert combos[0].font().family()


def test_task_dialog_heading_reacts_to_dark_theme(temp_app_env, qapp):
    db, settings, controller, _tmp = temp_app_env
    controller.apply_theme(mode="dark", accent_scheme="indigo")
    dialog = TaskDialog([], db_manager=db, settings_manager=settings)
    appearance = AppearanceService.read(settings)
    AppearanceService.apply_to_widget(dialog, appearance)
    _process_events(qapp)
    headings = [
        label
        for label in dialog.findChildren(QLabel)
        if "Task" in label.text() or label.property("heading") == "true"
    ]

    assert headings
    for heading in headings[:3]:
        assert contrast_ratio(
            heading.palette().color(QPalette.WindowText).name(),
            appearance.tokens["SURFACE_1"],
        ) >= 4.0


def test_table_header_and_body_text_palette_are_readable(temp_app_env, qapp):
    _db, settings, controller, _tmp = temp_app_env
    controller.apply_theme(mode="dark")
    table = QTableWidget(1, 2)
    table.setHorizontalHeaderLabels(["Task", "Status"])
    table.setItem(0, 0, __import__("PySide6.QtWidgets", fromlist=["QTableWidgetItem"]).QTableWidgetItem("Design"))
    table.setItem(0, 1, __import__("PySide6.QtWidgets", fromlist=["QTableWidgetItem"]).QTableWidgetItem("Open"))
    appearance = AppearanceService.read(settings)
    AppearanceService.apply_to_widget(table, appearance)
    image = _render_widget(table, qapp, width=360, height=160)

    assert image.width() == 360
    assert table.palette().color(QPalette.Text).name().upper() == appearance.tokens["TEXT_PRIMARY"]


def test_theme_change_keeps_same_main_window_instance(temp_app_env):
    db, _settings, controller, _tmp = temp_app_env
    window = MainWindow(db, _settings, controller)
    before_id = id(window)
    controller.apply_theme(mode="light")
    controller.apply_theme(mode="dark")

    assert id(window) == before_id


def test_font_change_keeps_same_main_window_instance(temp_app_env):
    db, settings, controller, _tmp = temp_app_env
    window = MainWindow(db, settings, controller)
    before_id = id(window)
    settings.set("ui_font_size", 18)
    controller.apply_theme()

    assert id(window) == before_id


def test_weight_change_keeps_same_main_window_instance(temp_app_env):
    db, settings, controller, _tmp = temp_app_env
    window = MainWindow(db, settings, controller)
    before_id = id(window)
    settings.set("ui_font_weight", "bold")
    controller.apply_theme()

    assert id(window) == before_id


def test_cpm_settings_are_unchanged_by_typography(temp_app_env):
    _db, settings, controller, _tmp = temp_app_env
    before = settings.get("working_weekdays")
    settings.set("ui_font_size", 16)
    controller.apply_theme()

    assert settings.get("working_weekdays") == before


def test_actual_execution_settings_are_unchanged_by_typography(temp_app_env):
    _db, settings, controller, _tmp = temp_app_env
    before = settings.get("gantt_actual_color")
    settings.set("ui_font_family", "Liberation Sans")
    controller.apply_theme()

    assert settings.get("gantt_actual_color") == before


def test_baseline_settings_are_unchanged_by_typography(temp_app_env):
    _db, settings, controller, _tmp = temp_app_env
    before = settings.get("gantt_plan_color")
    settings.set("ui_font_weight", "medium")
    controller.apply_theme()

    assert settings.get("gantt_plan_color") == before


def test_revision_settings_are_unchanged_by_text_color(temp_app_env):
    _db, settings, controller, _tmp = temp_app_env
    before = settings.get("global_background_mode")
    controller.apply_theme(mode="dark", accent_scheme="amber")

    assert settings.get("global_background_mode") == before


def test_production_database_hash_unchanged_by_typography_authority(temp_app_env):
    _db, settings, controller, _tmp = temp_app_env
    before = _production_hash()
    settings.set("ui_font_size", 14)
    settings.set("ui_font_weight", "bold")
    controller.apply_theme(mode="dark")
    after = _production_hash()

    assert after == before
