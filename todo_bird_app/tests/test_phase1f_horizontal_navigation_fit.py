
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


def _nav(style="expanded"):
    app = _app()

    nav = SidebarWidget(FakeSettings())

    nav.apply_navigation_preferences(
        "bottom",
        style,
        "center",
        persist=False,
        emit_change=False,
    )

    nav.show()
    app.processEvents()

    return app, nav


def test_horizontal_full_width_is_content_aware():
    _app()

    nav = SidebarWidget(FakeSettings())

    nav.apply_navigation_preferences(
        "bottom",
        "expanded",
        "left",
        persist=False,
        emit_change=False,
    )

    dashboard = nav.horizontal_items["dashboard"]
    feedback = nav.horizontal_items["feedback"]

    assert dashboard.horizontal_full_width() > 45
    assert feedback.horizontal_full_width() > dashboard.horizontal_full_width()

    nav.close()


def test_compact_fit_never_displays_partial_text():
    app, nav = _nav("expanded")

    nav.resize(650, 62)
    app.processEvents()

    nav._apply_horizontal_fit()
    app.processEvents()

    visible_keys = [
        key
        for key, item in nav.horizontal_items.items()
        if not item.isHidden()
    ]

    # Phase 1F.6.2.1 priority behavior:
    # the selected destination may intentionally retain its complete label.
    assert nav._selected_key in visible_keys

    for key in visible_keys:
        item = nav.horizontal_items[key]
        canonical_title = nav._title_for_key(key)

        # Canonical text is never abbreviated/mutated.
        assert item.text_label.text() == canonical_title
        assert item.toolTip() == canonical_title

        if item.text_label.isHidden():
            # Compact destinations are intentionally icon-only.
            assert item.minimumWidth() >= 46
        else:
            # Protected destinations may remain fully labeled,
            # but their width must be content-aware rather than ~45px.
            assert item.minimumWidth() > 45

    # Anything not visible must remain recoverable through overflow.
    visible_set = set(visible_keys)
    overflow_set = set(nav._horizontal_overflow_keys)

    assert (
        visible_set | overflow_set
        == set(nav.visible_navigation_keys())
    )
    assert visible_set.isdisjoint(overflow_set)

    nav.close()


def test_full_fit_restores_complete_labels():
    app, nav = _nav("expanded")

    item = nav.horizontal_items["dashboard"]

    # First prove compact mode hides the complete label instead of
    # allowing Qt to clip it into fragments such as "Da".
    item.set_horizontal_fit_mode(True)
    app.processEvents()

    assert item.text_label.isHidden()
    assert item.toolTip() == "Dashboard"

    # Then prove full mode restores the complete destination name and
    # assigns content-aware width rather than the old generic ~45 px.
    item.set_horizontal_fit_mode(False)
    app.processEvents()

    assert not item.text_label.isHidden()
    assert item.text_label.text() == "Dashboard"
    assert item.minimumWidth() > 45

    nav.close()


def test_rail_remains_icon_only():
    app, nav = _nav("rail")

    nav.resize(2400, 54)
    app.processEvents()

    nav._apply_horizontal_fit()
    app.processEvents()

    for item in nav.horizontal_items.values():
        assert item.text_label.isHidden()
        assert item.toolTip()

    nav.close()


def test_all_horizontal_destinations_remain_present():
    app, nav = _nav("glass")

    nav.resize(600, 62)
    app.processEvents()

    nav._apply_horizontal_fit()

    assert set(nav.horizontal_items) == {
        key
        for key, _title, _icon
        in nav.NAV_ITEMS
    }

    nav.close()


def test_vertical_navigation_is_not_forced_into_horizontal_fit():
    _app()

    nav = SidebarWidget(FakeSettings())

    nav.apply_navigation_preferences(
        "left",
        "expanded",
        "left",
        persist=False,
        emit_change=False,
    )

    item = nav.vertical_items["dashboard"]

    assert not item.text_label.isHidden()
    assert item.text_label.text() == "Dashboard"

    nav.close()


def test_horizontal_fit_contract_never_uses_abbreviated_label_text():
    _app()
    nav = SidebarWidget(FakeSettings())

    nav.apply_navigation_preferences(
        "bottom",
        "expanded",
        "right",
        persist=False,
        emit_change=False,
    )

    for key, title, _icon in nav.NAV_ITEMS:
        item = nav.horizontal_items[key]

        # Todo Bird always keeps the canonical destination label intact.
        assert item.text_label.text() == title

        item.set_horizontal_fit_mode(True)

        # Narrow presentation hides the label completely; it never mutates
        # canonical text into arbitrary fragments/abbreviations.
        assert item.text_label.isHidden()
        assert item.text_label.text() == title
        assert item.toolTip() == title

        item.set_horizontal_fit_mode(False)

        if nav.navigation_style != "rail":
            assert not item.text_label.isHidden()
            assert item.text_label.text() == title

    nav.close()
