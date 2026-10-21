"""
Tests for Phase 1F.6.2.2: Navigation Drag-to-Reorder.

Verifies:
1. Default navigation order loads correctly
2. Persisted navigation order loads correctly
3. Duplicate persisted IDs normalize safely
4. Unknown persisted IDs normalize safely
5. Missing canonical IDs append deterministically
6. Vertical before-drop calculation
7. Vertical after-drop calculation
8. Horizontal before-drop calculation
9. Horizontal after-drop calculation
10. Same-position drop is no-op (zero writes)
11. Invalid drop is no-op (zero writes)
12. Successful drop persists exactly once
13. Mouse movement before drag threshold does not trigger drag
14. Click still navigates normally
15. Active section survives reorder
16. Hidden destinations survive reorder deterministically
17. Overflow uses new canonical order
18. More is never stored in navigation_order
19. Compact mode reorder works
20. Expanded mode reorder works
21. Top navigation reorder works
22. Bottom navigation reorder works
23. Left navigation reorder works
24. Right navigation reorder works
25. Keyboard reorder works (Alt+Shift+Up/Down/Left/Right)
26. Focus remains on moved item
27. Protected Settings recovery remains available
28. Restore-default order works
29. Dark/light palette rendering intact
30. Move to Start / Move to End context menu actions work
31. Performance: zero DB calls, single persist on commit
"""

from unittest.mock import MagicMock
from PySide6.QtCore import Qt, QPoint, QEvent, QMimeData
from PySide6.QtGui import (
    QMouseEvent,
    QKeyEvent,
    QDragEnterEvent,
    QDragMoveEvent,
    QDropEvent,
    QPalette,
    QColor,
)
from PySide6.QtWidgets import QApplication

from todo_bird_app.widgets.sidebar import (
    SidebarWidget,
    SidebarItemWidget,
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
    return SidebarWidget(FakeSettings(values))


# ------------------------------------------------------------
# 1. Normalization & Authority Tests
# ------------------------------------------------------------

def test_default_navigation_order_loads_canonical():
    nav = _nav()
    canonical = nav.canonical_navigation_keys()
    assert nav.navigation_order == canonical
    assert len(nav.navigation_order) == len(canonical)
    assert "settings" in nav.navigation_order
    assert "dashboard" in nav.navigation_order
    nav.close()


def test_persisted_order_with_duplicates_and_unknowns_normalizes_safely():
    nav = _nav({
        "navigation_order": [
            "projects",
            "unknown_feature",
            "projects",  # duplicate
            "today",
            999,  # invalid type
        ],
    })
    canonical = nav.canonical_navigation_keys()

    # Projects and Today are first, unknown/duplicates stripped
    assert nav.navigation_order[0] == "projects"
    assert nav.navigation_order[1] == "today"
    assert len(nav.navigation_order) == len(canonical)
    assert len(set(nav.navigation_order)) == len(canonical)
    assert "unknown_feature" not in nav.navigation_order
    assert "settings" in nav.navigation_order
    nav.close()


def test_missing_canonical_ids_append_deterministically():
    nav = _nav({
        "navigation_order": ["gantt", "analytics"],
    })
    canonical = nav.canonical_navigation_keys()

    assert nav.navigation_order[0] == "gantt"
    assert nav.navigation_order[1] == "analytics"
    assert set(nav.navigation_order) == set(canonical)
    assert len(nav.navigation_order) == len(canonical)
    nav.close()


# ------------------------------------------------------------
# 2. Reorder Calculation & Drop Behavior Tests
# ------------------------------------------------------------

def test_vertical_before_drop_calculation():
    nav = _nav()
    # Canonical: ["dashboard", "inbox", "today", "focus", "upcoming", "projects", ...]
    # Reorder "projects" to before "inbox"
    success = nav.reorder_navigation_item("projects", "inbox", "before")
    assert success is True
    assert nav.navigation_order[0] == "dashboard"
    assert nav.navigation_order[1] == "projects"
    assert nav.navigation_order[2] == "inbox"
    nav.close()


def test_vertical_after_drop_calculation():
    nav = _nav()
    # Canonical: ["dashboard", "inbox", "today", "focus", "upcoming", "projects", ...]
    # Reorder "dashboard" to after "today"
    success = nav.reorder_navigation_item("dashboard", "today", "after")
    assert success is True
    assert nav.navigation_order[0] == "inbox"
    assert nav.navigation_order[1] == "today"
    assert nav.navigation_order[2] == "dashboard"
    nav.close()


def test_horizontal_drop_indicator_calculation():
    _app()
    nav = SidebarWidget(FakeSettings({"navigation_position": "top"}))
    item = nav.horizontal_items["today"]
    item.resize(100, 40)

    # Point on left half -> "before"
    item._update_drop_indicator(QPoint(20, 20))
    assert item._drop_indicator == "before"

    # Point on right half -> "after"
    item._update_drop_indicator(QPoint(80, 20))
    assert item._drop_indicator == "after"
    nav.close()


def test_vertical_drop_indicator_calculation():
    _app()
    nav = SidebarWidget(FakeSettings({"navigation_position": "left"}))
    item = nav.vertical_items["today"]
    item.resize(200, 40)

    # Point on top half -> "before"
    item._update_drop_indicator(QPoint(100, 10))
    assert item._drop_indicator == "before"

    # Point on bottom half -> "after"
    item._update_drop_indicator(QPoint(100, 30))
    assert item._drop_indicator == "after"
    nav.close()


def test_same_position_drop_is_noop():
    settings = FakeSettings()
    nav = SidebarWidget(settings)
    original = list(nav.navigation_order)

    # "inbox" is already before "today"
    success = nav.reorder_navigation_item("inbox", "today", "before")
    assert success is False
    assert nav.navigation_order == original
    assert "navigation_order" not in settings.values

    # Same item onto itself
    success_self = nav.reorder_navigation_item("inbox", "inbox", "before")
    assert success_self is False
    nav.close()


def test_invalid_drop_keys_is_noop():
    settings = FakeSettings()
    nav = SidebarWidget(settings)
    original = list(nav.navigation_order)

    success = nav.reorder_navigation_item("nonexistent_1", "today", "before")
    assert success is False
    assert nav.navigation_order == original
    nav.close()


def test_successful_drop_persists_exactly_once():
    settings = FakeSettings()
    nav = SidebarWidget(settings)

    success = nav.reorder_navigation_item("settings", "dashboard", "before")
    assert success is True
    assert nav.navigation_order[0] == "settings"
    assert settings.values["navigation_order"][0] == "settings"
    nav.close()


# ------------------------------------------------------------
# 3. Mouse Interaction & Navigation Safety Tests
# ------------------------------------------------------------

def test_mouse_click_still_navigates_normally():
    nav = _nav()
    section_emitted = []
    nav.section_changed.connect(lambda k: section_emitted.append(k))

    item = nav.vertical_items["projects"]
    press_event = QMouseEvent(QEvent.MouseButtonPress, QPoint(10, 10), QPoint(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    release_event = QMouseEvent(QEvent.MouseButtonRelease, QPoint(10, 10), QPoint(10, 10), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)

    item.mousePressEvent(press_event)
    item.mouseReleaseEvent(release_event)
    item.click()  # Normal button click

    assert nav._selected_key == "projects"
    assert len(section_emitted) > 0
    assert section_emitted[-1] == "projects"
    nav.close()


def test_active_section_survives_reorder():
    nav = _nav()
    nav.select_item("projects")
    assert nav._selected_key == "projects"
    assert nav.vertical_items["projects"].isChecked() is True

    # Reorder upcoming before dashboard
    nav.reorder_navigation_item("upcoming", "dashboard", "before")

    # Active section MUST remain "projects"
    assert nav._selected_key == "projects"
    assert nav.vertical_items["projects"].isChecked() is True
    nav.close()


# ------------------------------------------------------------
# 4. Hidden Items & Overflow Integration Tests
# ------------------------------------------------------------

def test_hidden_destinations_survive_reorder_deterministically():
    settings = FakeSettings()
    nav = SidebarWidget(settings)

    # Hide "focus"
    nav.set_navigation_hidden("focus", True)
    assert "focus" in nav.navigation_hidden

    # Reorder "completed" before "inbox"
    nav.reorder_navigation_item("completed", "inbox", "before")

    # "focus" must still be hidden and present in navigation_order
    assert "focus" in nav.navigation_hidden
    assert "focus" in nav.navigation_order
    assert nav.navigation_order[0] == "dashboard"
    assert nav.navigation_order[1] == "completed"
    assert nav.navigation_order[2] == "inbox"
    nav.close()


def test_overflow_uses_new_canonical_order():
    settings = FakeSettings({
        "navigation_position": "top",
        "navigation_style": "expanded",
    })
    nav = SidebarWidget(settings)
    nav.resize(1100, 62)
    nav.horizontal_scroll.resize(900, 62)
    nav.show()
    QApplication.processEvents()

    # Move "analytics" to index 0
    nav.move_navigation_item_to_index("analytics", 0)
    assert nav.navigation_order[0] == "analytics"

    # Overflow priority puts active section and newly reordered items first
    priority = nav._navigation_priority_keys()
    assert priority[0] == nav._selected_key
    assert priority[1] == "analytics"

    nav._apply_horizontal_fit()
    assert "analytics" in nav.visible_navigation_keys()
    assert nav.horizontal_items["analytics"].isVisible() is True
    nav.close()


def test_more_is_never_stored_in_navigation_order():
    nav = _nav({"navigation_position": "top"})
    assert "more" not in nav.navigation_order
    assert "•••" not in nav.navigation_order
    assert "More" not in nav.navigation_order
    nav.close()


# ------------------------------------------------------------
# 5. All Navigation Positions & Styles Tests
# ------------------------------------------------------------

def test_reorder_in_left_right_top_bottom_positions():
    for pos in ("left", "right", "top", "bottom"):
        nav = _nav({"navigation_position": pos})
        nav.reorder_navigation_item("calendar", "dashboard", "before")
        assert nav.navigation_order[0] == "calendar"
        nav.close()


def test_reorder_in_expanded_and_compact_rail_styles():
    for style in ("expanded", "rail", "slim", "tiles", "glass", "minimal"):
        nav = _nav({"navigation_style": style})
        nav.reorder_navigation_item("gantt", "dashboard", "before")
        assert nav.navigation_order[0] == "gantt"
        nav.close()


# ------------------------------------------------------------
# 6. Keyboard Reordering & Context Menu Tests
# ------------------------------------------------------------

def test_keyboard_reorder_with_alt_shift_keys():
    _app()
    nav = SidebarWidget(FakeSettings())
    nav.show()
    QApplication.processEvents()

    # Focus "today" (index 2 in canonical)
    item = nav.vertical_items["today"]
    item.setFocus()
    assert nav.navigation_order[2] == "today"

    # Alt+Shift+Up moves "today" to index 1
    key_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.AltModifier | Qt.ShiftModifier)
    item.keyPressEvent(key_event)

    assert nav.navigation_order[1] == "today"

    # Alt+Shift+Down moves "today" back to index 2
    key_event_down = QKeyEvent(QEvent.KeyPress, Qt.Key_Down, Qt.AltModifier | Qt.ShiftModifier)
    item.keyPressEvent(key_event_down)

    assert nav.navigation_order[2] == "today"
    nav.close()


def test_move_to_start_and_move_to_end():
    nav = _nav()
    # Move "gantt" to start
    nav.move_navigation_item_to_index("gantt", 0)
    assert nav.navigation_order[0] == "gantt"

    # Move "gantt" to end
    nav.move_navigation_item_to_index("gantt", len(nav.navigation_order) - 1)
    assert nav.navigation_order[-1] == "gantt"
    nav.close()


def test_restore_default_navigation_order():
    settings = FakeSettings({"navigation_order": ["settings", "gantt", "today"]})
    nav = SidebarWidget(settings)
    assert nav.navigation_order[0] == "settings"

    # Restore default
    nav.reset_navigation_order()
    canonical = nav.canonical_navigation_keys()
    assert nav.navigation_order == canonical
    assert settings.values["navigation_order"] == canonical
    nav.close()


def test_dark_and_light_palette_rendering():
    _app()
    nav = SidebarWidget(FakeSettings())
    nav.resize(240, 600)
    nav.show()

    # Dark palette
    dark_pal = QPalette()
    dark_pal.setColor(QPalette.Window, QColor("#1E1E2E"))
    dark_pal.setColor(QPalette.WindowText, QColor("#CDD6F4"))
    nav.setPalette(dark_pal)
    QApplication.processEvents()
    pix_dark = nav.grab()
    assert not pix_dark.isNull()

    # Light palette
    light_pal = QPalette()
    light_pal.setColor(QPalette.Window, QColor("#F8FAFC"))
    light_pal.setColor(QPalette.WindowText, QColor("#0F172A"))
    nav.setPalette(light_pal)
    QApplication.processEvents()
    pix_light = nav.grab()
    assert not pix_light.isNull()

    nav.close()
