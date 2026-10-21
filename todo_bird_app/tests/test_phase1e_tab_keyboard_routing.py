
import os

os.environ.setdefault(
    "QT_QPA_PLATFORM",
    "offscreen",
)

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from todo_bird_app.views.wbs_tree_view import WBSTreeView


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class FakeIndex:
    def isValid(self):
        return True


def test_tree_has_early_event_override():
    assert "event" in WBSTreeView.__dict__


def test_tab_is_consumed_and_emits_indent(monkeypatch):
    _app()

    tree = WBSTreeView(
        custom_service=None,
        is_dark=False,
    )

    calls = []

    monkeypatch.setattr(
        tree,
        "currentIndex",
        lambda: FakeIndex(),
    )

    monkeypatch.setattr(
        tree,
        "get_source_key",
        lambda index: "subtask:42",
    )

    tree.hierarchyIndentRequested.connect(
        lambda key: calls.append(
            ("indent", key)
        )
    )

    ev = QKeyEvent(
        QEvent.KeyPress,
        Qt.Key_Tab,
        Qt.NoModifier,
    )

    handled = tree.event(ev)

    assert handled is True
    assert ev.isAccepted()
    assert calls == [
        ("indent", "subtask:42"),
    ]


def test_backtab_is_consumed_and_emits_outdent(monkeypatch):
    _app()

    tree = WBSTreeView(
        custom_service=None,
        is_dark=False,
    )

    calls = []

    monkeypatch.setattr(
        tree,
        "currentIndex",
        lambda: FakeIndex(),
    )

    monkeypatch.setattr(
        tree,
        "get_source_key",
        lambda index: "subtask:42",
    )

    tree.hierarchyOutdentRequested.connect(
        lambda key: calls.append(
            ("outdent", key)
        )
    )

    ev = QKeyEvent(
        QEvent.KeyPress,
        Qt.Key_Backtab,
        Qt.ShiftModifier,
    )

    handled = tree.event(ev)

    assert handled is True
    assert ev.isAccepted()
    assert calls == [
        ("outdent", "subtask:42"),
    ]


def test_normal_key_not_intercepted_as_hierarchy_command():
    _app()

    tree = WBSTreeView(
        custom_service=None,
        is_dark=False,
    )

    ev = QKeyEvent(
        QEvent.KeyPress,
        Qt.Key_Down,
        Qt.NoModifier,
    )

    assert ev.key() not in (
        Qt.Key_Tab,
        Qt.Key_Backtab,
    )
