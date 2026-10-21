
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


def _nav(style="glass"):
    app = _app()

    nav = SidebarWidget(FakeSettings())

    nav.apply_navigation_preferences(
        "bottom",
        style,
        "center",
        persist=False,
        emit_change=False,
    )

    return app, nav


def test_visible_non_rail_items_keep_complete_labels():
    app, nav = _nav("glass")

    nav.resize(700, 62)
    nav.show()
    app.processEvents()

    nav._apply_horizontal_fit()
    app.processEvents()

    for key, item in nav.horizontal_items.items():
        if item.isHidden():
            continue

        assert not item.text_label.isHidden()
        assert (
            item.text_label.text()
            == nav._title_for_key(key)
        )
        assert item.minimumWidth() > 45

    nav.close()


def test_non_visible_items_are_in_more_overflow():
    app, nav = _nav("expanded")

    nav.resize(650, 62)
    nav.show()
    app.processEvents()

    nav._apply_horizontal_fit()
    app.processEvents()

    direct = {
        key
        for key, item
        in nav.horizontal_items.items()
        if not item.isHidden()
    }

    overflow = set(
        nav._horizontal_overflow_keys
    )

    intended = set(
        nav.visible_navigation_keys()
    )

    assert direct | overflow == intended
    assert direct.isdisjoint(overflow)

    nav.close()


def test_badged_direct_item_keeps_badge_visible():
    app, nav = _nav("glass")

    nav.set_badge_count(
        "dashboard",
        8,
    )

    nav.resize(850, 62)
    nav.show()
    app.processEvents()

    nav._apply_horizontal_fit()
    app.processEvents()

    item = nav.horizontal_items["dashboard"]

    assert not item.isHidden()
    assert not item.text_label.isHidden()
    assert item.badge_label.text() == "8"
    assert not item.badge_label.isHidden()

    nav.close()


def test_favorite_keeps_full_label_when_directly_visible():
    app, nav = _nav("slim")

    nav.set_navigation_favorite(
        "projects",
        True,
    )

    nav.resize(800, 62)
    nav.show()
    app.processEvents()

    nav._apply_horizontal_fit()
    app.processEvents()

    item = nav.horizontal_items["projects"]

    if not item.isHidden():
        assert not item.text_label.isHidden()
        assert item.text_label.text() == "Projects"

    nav.close()


def test_rail_remains_intentionally_icon_only():
    app, nav = _nav("rail")

    nav.resize(800, 54)
    nav.show()
    app.processEvents()

    nav._apply_horizontal_fit()
    app.processEvents()

    for item in nav.horizontal_items.values():
        if not item.isHidden():
            assert item.text_label.isHidden()
            assert item.toolTip()

    nav.close()


def test_canonical_text_is_never_abbreviated():
    app, nav = _nav("minimal")

    nav.resize(620, 54)
    nav.show()
    app.processEvents()

    nav._apply_horizontal_fit()

    for key, item in nav.horizontal_items.items():
        assert (
            item.text_label.text()
            == nav._title_for_key(key)
        )

    nav.close()
