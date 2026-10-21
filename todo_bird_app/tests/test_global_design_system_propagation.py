import os
import shutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QWidget

from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.project import Project
from todo_bird_app.services.appearance_service import (
    ACCENT_SCHEMES,
    AppearanceService,
    semantic_tokens_for,
)
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.ui.components.modern_button import (
    ButtonStyleDesign,
    ButtonVariant,
    ModernButton,
)
from todo_bird_app.ui.components.modern_checkbox import ModernCheckBox
from todo_bird_app.ui.components.modern_combobox import ModernComboBox
from todo_bird_app.ui.components.search_field import SearchField
from todo_bird_app.ui.components.segmented_control import SegmentedControl
from todo_bird_app.ui.components.toggle_switch import ToggleSwitch
from todo_bird_app.views.main_window import MainWindow
from todo_bird_app.views.settings_view import SettingsView
from todo_bird_app.widgets.task_dialog import TaskDialog


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


BUTTON_STYLES = [
    "flat",
    "3d_raised",
    "executive_soft",
    "neumorphic",
    "glow",
]


def _combo_widget() -> ModernComboBox:
    combo = ModernComboBox()
    combo.addItems(["Ready", "Blocked", "Completed"])
    combo.setCurrentText("Ready")
    return combo


def _segmented_widget() -> SegmentedControl:
    return SegmentedControl(
        [("Compact", "compact"), ("Balanced", "balanced"), ("Spacious", "spacious")],
        animate=False,
    )


CONTROL_BUILDERS = [
    ("button", lambda: ModernButton("Control Probe", variant=ButtonVariant.PRIMARY)),
    ("combo", _combo_widget),
    ("checkbox", lambda: ModernCheckBox("Check Probe")),
    ("toggle", lambda: ToggleSwitch("Toggle Probe", checked=True, animate=False)),
    ("search", lambda: SearchField("Search probe")),
    ("segmented", _segmented_widget),
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
    db_path = tmp_path / "global_design.db"
    db = DatabaseManager.for_test(str(db_path))
    with db.get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, color) VALUES (1, 'Inbox', '#2563EB')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, color) VALUES (2, 'Design System', '#E11D48')"
        )
        conn.commit()
    settings = SettingsManager(db, config_dir=tmp_path / "config")
    controller = ThemeController(settings)
    qapp.theme_controller = controller
    controller.apply_theme(
        mode="dark",
        accent_scheme="professional_blue",
        density="balanced",
        button_style="3d_raised",
    )
    yield db, settings, controller
    db.close()
    shutil.rmtree(tmp_path, ignore_errors=True)


def _process_events(qapp, loops: int = 3) -> None:
    for _ in range(loops):
        qapp.processEvents()


def _render_widget(
    widget: QWidget,
    qapp,
    width: int = 360,
    height: int = 90,
) -> QImage:
    widget.resize(width, height)
    widget.show()
    _process_events(qapp)
    size = widget.size()
    image = QImage(size, QImage.Format_ARGB32_Premultiplied)
    image.fill(QColor("#000000"))
    painter = QPainter(image)
    try:
        widget.render(painter, QPoint(0, 0))
    finally:
        painter.end()
    return image


def _image_has_content(image: QImage) -> bool:
    first = QColor(image.pixel(0, 0))
    # Stride 4px: the previous width//8 grid sampled a 360x90 canvas at
    # 45x11px intervals and missed a 40x22 toggle track entirely, making the
    # verdict depend on background-blend luck (flipped when font metrics
    # changed under it).
    for y in range(0, image.height(), 4):
        for x in range(0, image.width(), 4):
            current = QColor(image.pixel(x, y))
            if (
                abs(first.red() - current.red())
                + abs(first.green() - current.green())
                + abs(first.blue() - current.blue())
            ) > 12:
                return True
    return False


def _sample_delta(left: QImage, right: QImage) -> int:
    width = min(left.width(), right.width())
    height = min(left.height(), right.height())
    changed = 0
    for y in range(0, height, 13):
        for x in range(0, width, 13):
            a = QColor(left.pixel(x, y))
            b = QColor(right.pixel(x, y))
            if (
                abs(a.red() - b.red())
                + abs(a.green() - b.green())
                + abs(a.blue() - b.blue())
            ) > 30:
                changed += 1
    return changed


@pytest.mark.parametrize("role", REQUIRED_SEMANTIC_ROLES)
def test_semantic_tokens_include_required_global_roles(role):
    for is_dark in (True, False):
        tokens = semantic_tokens_for(is_dark, "#E11D48")
        assert role in tokens
        if role != "ACCENT_SUBTLE":
            assert QColor(tokens[role]).isValid(), role


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("scheme", list(ACCENT_SCHEMES.keys()))
@pytest.mark.parametrize("density", ["compact", "balanced", "spacious"])
def test_theme_controller_replaces_all_qss_tokens(
    temp_app_env,
    qapp,
    theme,
    scheme,
    density,
):
    _db, settings, controller = temp_app_env
    controller.apply_theme(
        mode=theme,
        accent_scheme=scheme,
        density=density,
    )
    appearance = AppearanceService.read(settings, app=qapp)
    assert "@" not in qapp.styleSheet()
    assert appearance.accent_color in qapp.styleSheet()
    assert qapp.palette().highlight().color().name().upper() == appearance.accent_color


@pytest.mark.parametrize("style", BUTTON_STYLES)
def test_button_style_updates_existing_modern_button(temp_app_env, qapp, style):
    _db, _settings, controller = temp_app_env
    button = ModernButton("Style Probe", variant=ButtonVariant.PRIMARY)
    controller.apply_theme(button_style=style)
    _process_events(qapp)
    image = _render_widget(button, qapp)

    assert ModernButton.get_global_design_mode() == ButtonStyleDesign(style)
    assert button.property("todoBirdButtonStyle") == style
    assert _image_has_content(image)


@pytest.mark.parametrize("name,builder", CONTROL_BUILDERS)
@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("scheme", ["rose", "emerald"])
def test_existing_custom_controls_receive_live_theme_and_accent(
    temp_app_env,
    qapp,
    name,
    builder,
    theme,
    scheme,
):
    _db, _settings, controller = temp_app_env
    control = builder()
    controller.apply_theme(mode=theme, accent_scheme=scheme)
    _process_events(qapp)
    image = _render_widget(control, qapp)
    expected_accent = ACCENT_SCHEMES[scheme][1]

    assert control.property("todoBirdTheme") == theme
    assert control.property("todoBirdAccent") == expected_accent
    if hasattr(control, "_accent_color"):
        assert getattr(control, "_accent_color").upper() == expected_accent
    assert _image_has_content(image), name


@pytest.mark.parametrize("density", ["compact", "balanced", "spacious"])
def test_density_sets_measured_button_and_combo_heights(temp_app_env, qapp, density):
    _db, _settings, controller = temp_app_env
    button = ModernButton("Density Probe", variant=ButtonVariant.SECONDARY)
    combo = _combo_widget()
    controller.apply_theme(density=density)
    _process_events(qapp)

    assert button.property("todoBirdDensity") == density
    assert combo.property("todoBirdDensity") == density
    assert 24 <= button.sizeHint().height() <= 56
    assert 28 <= combo.sizeHint().height() <= 56
    assert button.minimumWidth() >= button.sizeHint().width()


def test_main_window_real_render_changes_theme_accent_font_and_density(
    temp_app_env,
    qapp,
):
    db, settings, controller = temp_app_env
    window = MainWindow(db, settings, controller)
    window.resize(1180, 780)
    window.show()
    _process_events(qapp)
    before = _render_widget(window, qapp, width=1180, height=780)

    settings.set("ui_font_family", "Liberation Mono")
    settings.set("ui_font_size", 14)
    settings.set("ui_font_weight", "bold")
    controller.apply_theme(
        mode="light",
        accent_scheme="rose",
        density="spacious",
        button_style="glow",
    )
    _process_events(qapp, loops=5)
    after = _render_widget(window, qapp, width=1180, height=780)

    assert window.property("todoBirdTheme") == "light"
    assert qapp.font().pointSize() == 14
    assert qapp.palette().highlight().color().name().upper() == "#E11D48"
    assert _sample_delta(before, after) > 40


def test_gantt_refresh_button_visible_in_real_main_window_toolbar(
    temp_app_env,
    qapp,
):
    db, settings, controller = temp_app_env
    window = MainWindow(db, settings, controller)
    window.resize(1100, 760)
    window.show()
    window.navigation_controller.set_active_section("gantt")
    _process_events(qapp, loops=5)

    gantt = window.gantt_view
    refresh = gantt.refresh_btn
    viewport = gantt._gantt_toolbar_scroll.viewport()
    refresh_rect = QRect(refresh.mapTo(viewport, QPoint(0, 0)), refresh.size())

    assert refresh.isVisible()
    assert refresh.width() >= 70
    assert refresh.height() >= 28
    assert refresh_rect.intersects(viewport.rect())
    assert gantt._gantt_toolbar.width() >= gantt._gantt_toolbar.sizeHint().width()
    assert hasattr(gantt, "appearance_menu")
    assert hasattr(gantt, "layers_menu")


def test_settings_view_real_render_drives_canonical_controller(
    temp_app_env,
    qapp,
):
    db, settings, controller = temp_app_env
    view = SettingsView(db, settings)
    view.theme_controller = controller
    view.resize(900, 700)
    view.show()
    _process_events(qapp)
    before = _render_widget(view, qapp, width=900, height=700)

    view.theme_combo.setCurrentText("Light Mode")
    view.accent_combo.setCurrentIndex(view.accent_combo.findData("amber"))
    view.density_combo.setCurrentIndex(view.density_combo.findData("spacious"))
    view.btn_design_combo.setCurrentIndex(view.btn_design_combo.findData("flat"))
    _process_events(qapp, loops=5)
    after = _render_widget(view, qapp, width=900, height=700)

    appearance = AppearanceService.read(settings, app=qapp)
    assert appearance.theme == "light"
    assert appearance.accent_scheme == "amber"
    assert appearance.density == "spacious"
    assert appearance.button_style == "flat"
    assert _sample_delta(before, after) > 20


def test_task_dialog_real_render_inherits_application_appearance(
    temp_app_env,
    qapp,
):
    db, settings, controller = temp_app_env
    dialog = TaskDialog(
        [Project(id=1, name="Inbox", color="#2563EB")],
        db_manager=db,
        settings_manager=settings,
    )
    dialog.resize(620, 720)
    dialog.show()
    _process_events(qapp)
    before = _render_widget(dialog, qapp, width=620, height=720)

    settings.set("ui_font_family", "Liberation Serif")
    settings.set("ui_font_size", 13)
    controller.apply_theme(
        mode="light",
        accent_scheme="indigo",
        density="compact",
        button_style="executive_soft",
    )
    _process_events(qapp, loops=5)
    after = _render_widget(dialog, qapp, width=620, height=720)

    assert qapp.font().family() == "Liberation Serif"
    assert dialog.palette().highlight().color().name().upper() == "#4F46E5"
    assert _sample_delta(before, after) > 20
