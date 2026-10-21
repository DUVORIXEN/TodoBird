
import os

os.environ.setdefault(
    "QT_QPA_PLATFORM",
    "offscreen",
)

from PySide6.QtWidgets import QApplication

from todo_bird_app.ui.components.modern_menu import ModernMenu


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_modern_menu_constructs_in_light_theme():
    _app()

    menu = ModernMenu(
        "Task Actions",
        parent=None,
        is_dark=False,
        accent_color="#3584E4",
    )

    assert menu is not None
    menu.deleteLater()


def test_modern_menu_constructs_in_dark_theme():
    _app()

    menu = ModernMenu(
        "Task Actions",
        parent=None,
        is_dark=True,
        accent_color="#3584E4",
    )

    assert menu is not None
    menu.deleteLater()


def test_modern_menu_light_theme_can_add_action():
    _app()

    menu = ModernMenu(
        "Task Actions",
        parent=None,
        is_dark=False,
        accent_color="#3584E4",
    )

    menu.add_action_item(
        "Move Up",
        lambda: None,
        icon_name="chevron_up",
        shortcut="Alt+Up",
    )

    assert len(menu.actions()) >= 1
    menu.deleteLater()
