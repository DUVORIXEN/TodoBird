
from pathlib import Path

from PySide6.QtWidgets import QApplication

from todo_bird_app.widgets.sidebar import SidebarWidget


class FakeSettings:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


def _app():
    return QApplication.instance() or QApplication([])


def test_default_navigation_is_backward_compatible():
    _app()
    settings = FakeSettings()

    nav = SidebarWidget(settings)

    assert nav.navigation_position == "left"
    assert nav.navigation_style == "expanded"
    assert nav.navigation_alignment == "left"
    assert nav.pages.currentWidget() is nav.vertical_page

    nav.close()


def test_all_navigation_positions_are_supported():
    _app()
    nav = SidebarWidget(FakeSettings())

    for position in (
        "left",
        "right",
        "top",
        "bottom",
    ):
        nav.apply_navigation_preferences(
            position,
            "expanded",
            "left",
            persist=False,
            emit_change=False,
        )

        assert nav.navigation_position == position

        if position in ("top", "bottom"):
            assert nav.pages.currentWidget() is nav.horizontal_page
        else:
            assert nav.pages.currentWidget() is nav.vertical_page

    nav.close()


def test_all_navigation_styles_are_supported():
    _app()
    nav = SidebarWidget(FakeSettings())

    for style in (
        "expanded",
        "rail",
        "slim",
        "tiles",
        "glass",
        "minimal",
    ):
        nav.apply_navigation_preferences(
            "left",
            style,
            "left",
            persist=False,
            emit_change=False,
        )

        assert nav.navigation_style == style

    nav.close()


def test_navigation_preferences_persist():
    _app()
    settings = FakeSettings()
    nav = SidebarWidget(settings)

    nav.apply_navigation_preferences(
        "bottom",
        "glass",
        "right",
        persist=True,
        emit_change=False,
    )

    assert settings.values["navigation_position"] == "bottom"
    assert settings.values["navigation_style"] == "glass"
    assert settings.values["navigation_alignment"] == "right"

    nav.close()


def test_selection_is_synchronized_across_orientations():
    _app()
    nav = SidebarWidget(FakeSettings())

    nav.select_item(
        "projects",
        emit=False,
    )

    assert nav.vertical_items["projects"].isChecked()
    assert nav.horizontal_items["projects"].isChecked()

    assert not nav.vertical_items["today"].isChecked()
    assert not nav.horizontal_items["today"].isChecked()

    nav.close()


def test_badges_are_synchronized_across_orientations():
    _app()
    nav = SidebarWidget(FakeSettings())

    nav.set_badge_count(
        "today",
        7,
    )

    assert nav.vertical_items["today"].count == 7
    assert nav.horizontal_items["today"].count == 7

    nav.close()


def test_compact_rail_hides_labels_but_keeps_tooltips():
    _app()
    nav = SidebarWidget(FakeSettings())

    nav.apply_navigation_preferences(
        "left",
        "rail",
        "left",
        persist=False,
        emit_change=False,
    )

    item = nav.vertical_items["projects"]

    assert item.text_label.isHidden()
    assert item.toolTip() == "Projects"

    nav.close()


def test_main_window_has_four_navigation_hosts():
    src = Path(
        "todo_bird_app/views/main_window.py"
    ).read_text()

    for text in (
        "top_navigation_host",
        "left_navigation_host",
        "right_navigation_host",
        "bottom_navigation_host",
        "apply_navigation_preferences",
    ):
        assert text in src


def test_settings_expose_navigation_personalization():
    src = Path(
        "todo_bird_app/views/settings_view.py"
    ).read_text()

    for text in (
        "Navigation & Workspace Dock",
        "navigation_position_combo",
        "navigation_style_combo",
        "navigation_alignment_combo",
        "Bottom Navigation Dock",
        "Glass Dock",
        "Compact Rail",
    ):
        assert text in src


def test_theme_files_support_navigation_positions_and_styles():
    for name in (
        "dark.qss",
        "light.qss",
    ):
        src = Path(
            "todo_bird_app/themes"
        ) / name

        text = src.read_text()

        assert 'navPosition="right"' in text
        assert 'navPosition="top"' in text
        assert 'navPosition="bottom"' in text
        assert 'navStyle="glass"' in text
        assert 'navStyle="tiles"' in text
        assert 'navStyle="minimal"' in text
