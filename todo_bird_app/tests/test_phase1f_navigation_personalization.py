
from PySide6.QtWidgets import QApplication

from todo_bird_app.widgets.sidebar import (
    SidebarWidget,
)


class FakeSettings:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


def _app():
    return QApplication.instance() or QApplication([])


def _nav(values=None):
    _app()
    return SidebarWidget(
        FakeSettings(values)
    )


def test_default_order_contains_every_destination_once():
    nav = _nav()

    canonical = nav.canonical_navigation_keys()

    assert nav.navigation_order == canonical
    assert len(set(nav.navigation_order)) == len(canonical)

    nav.close()


def test_old_saved_order_forward_fills_new_destinations():
    nav = _nav({
        "navigation_order": [
            "today",
            "dashboard",
        ],
    })

    assert nav.navigation_order[:2] == [
        "today",
        "dashboard",
    ]

    assert set(nav.navigation_order) == set(
        nav.canonical_navigation_keys()
    )

    nav.close()


def test_favorite_persists():
    settings = FakeSettings()
    nav = SidebarWidget(settings)

    nav.set_navigation_favorite(
        "projects",
        True,
    )

    assert "projects" in nav.navigation_favorites
    assert "projects" in settings.values[
        "navigation_favorites"
    ]

    nav.set_navigation_favorite(
        "projects",
        False,
    )

    assert "projects" not in nav.navigation_favorites

    nav.close()


def test_move_navigation_item_persists_order():
    settings = FakeSettings()
    nav = SidebarWidget(settings)

    original = list(nav.navigation_order)

    key = original[2]

    nav.move_navigation_item(
        key,
        -1,
    )

    assert nav.navigation_order[1] == key
    assert settings.values[
        "navigation_order"
    ][1] == key

    nav.close()


def test_hide_and_restore_destination():
    settings = FakeSettings()
    nav = SidebarWidget(settings)

    nav.set_navigation_hidden(
        "analytics",
        True,
    )

    assert "analytics" in nav.navigation_hidden
    assert "analytics" not in nav.visible_navigation_keys()
    assert nav.vertical_items[
        "analytics"
    ].isHidden()

    nav.set_navigation_hidden(
        "analytics",
        False,
    )

    assert "analytics" not in nav.navigation_hidden
    assert "analytics" in nav.visible_navigation_keys()

    nav.close()


def test_active_destination_cannot_be_hidden():
    nav = _nav()

    nav.select_item(
        "projects",
        emit=False,
    )

    nav.set_navigation_hidden(
        "projects",
        True,
    )

    assert "projects" not in nav.navigation_hidden

    nav.close()


def test_restore_all_navigation_items():
    nav = _nav()

    nav.set_navigation_hidden("analytics", True)
    nav.set_navigation_hidden("feedback", True)

    assert nav.navigation_hidden

    nav.restore_all_navigation_items()

    assert nav.navigation_hidden == []

    nav.close()


def test_priority_places_selected_then_favorites():
    nav = _nav()

    nav.select_item(
        "gantt",
        emit=False,
    )

    nav.set_navigation_favorite(
        "projects",
        True,
    )
    nav.set_navigation_favorite(
        "calendar",
        True,
    )

    priority = nav._navigation_priority_keys()

    assert priority[0] == "gantt"
    assert priority[1:3] == [
        "projects",
        "calendar",
    ]

    nav.close()


def test_more_menu_recovers_hidden_destinations():
    app = _app()

    nav = SidebarWidget(FakeSettings())
    nav.apply_navigation_preferences(
        "bottom",
        "glass",
        "right",
        persist=False,
        emit_change=False,
    )

    nav.set_navigation_hidden(
        "analytics",
        True,
    )

    nav.show()
    app.processEvents()

    nav._rebuild_more_menu()

    assert not nav.more_button.isHidden()

    texts = [
        action.text()
        for action in nav.more_menu.actions()
    ]

    assert "Show Hidden Destination" in texts

    nav.close()


def test_horizontal_overflow_never_loses_destinations():
    app = _app()

    nav = SidebarWidget(FakeSettings())

    nav.apply_navigation_preferences(
        "bottom",
        "glass",
        "center",
        persist=False,
        emit_change=False,
    )

    nav.resize(620, 62)
    nav.show()
    app.processEvents()

    nav._apply_horizontal_fit()
    app.processEvents()

    visible = set(
        key
        for key, item in nav.horizontal_items.items()
        if not item.isHidden()
    )

    overflow = set(
        nav._horizontal_overflow_keys
    )

    intended = set(
        nav.visible_navigation_keys()
    )

    assert visible | overflow == intended
    assert visible & overflow == set()

    nav.close()


def test_reset_personalization_restores_default_authority():
    nav = _nav()

    nav.set_navigation_favorite(
        "projects",
        True,
    )
    nav.set_navigation_hidden(
        "analytics",
        True,
    )
    nav.move_navigation_item(
        "today",
        3,
    )

    nav.reset_navigation_personalization()

    assert nav.navigation_favorites == []
    assert nav.navigation_hidden == []
    assert (
        nav.navigation_order
        == nav.canonical_navigation_keys()
    )

    nav.close()
