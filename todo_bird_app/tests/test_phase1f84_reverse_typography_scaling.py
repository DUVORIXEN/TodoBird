
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

from todo_bird_app.ui.components.segmented_control import (
    SegmentedControl,
)


ROOT = Path("todo_bird_app")


def _app():
    return QApplication.instance() or QApplication([])


def test_segmented_control_has_no_absolute_12pt_painter():
    text = (
        ROOT
        / "ui"
        / "components"
        / "segmented_control.py"
    ).read_text()

    assert "font.setPointSize(12)" not in text
    assert "font = QFont(self.font())" in text


def test_segmented_size_hint_tracks_current_font():
    _app()

    control = SegmentedControl(
        segments=[
            ("WBS Hierarchy", "wbs"),
            ("Task List", "list"),
        ],
        animate=False,
    )

    small = QFont(control.font())
    small.setPointSize(10)
    control.setFont(small)

    small_hint = control.sizeHint()

    large = QFont(control.font())
    large.setPointSize(20)
    control.setFont(large)

    large_hint = control.sizeHint()

    assert large_hint.width() > small_hint.width()
    assert large_hint.height() > small_hint.height()


def test_segmented_reverse_scaling_returns_smaller_hint():
    _app()

    control = SegmentedControl(
        segments=[
            ("WBS Hierarchy", "wbs"),
            ("Task List", "list"),
        ],
        animate=False,
    )

    large = QFont(control.font())
    large.setPointSize(20)
    control.setFont(large)
    large_hint = control.sizeHint()

    small = QFont(control.font())
    small.setPointSize(10)
    control.setFont(small)
    small_hint = control.sizeHint()

    assert small_hint.width() < large_hint.width()
    assert small_hint.height() < large_hint.height()


def test_segmented_34px_is_minimum_not_fixed_ceiling():
    text = (
        ROOT
        / "ui"
        / "components"
        / "segmented_control.py"
    ).read_text()

    assert "self.setFixedHeight(34)" not in text
    assert "self.setMinimumHeight(34)" not in text
    assert "self._update_geometry()" in text
    assert "max(28, int(fm.height()) + 10)" in text


def test_segmented_font_change_updates_geometry():
    text = (
        ROOT
        / "ui"
        / "components"
        / "segmented_control.py"
    ).read_text()

    assert "QEvent.FontChange" in text
    assert "self.updateGeometry()" in text


def test_wbs_typography_uses_safe_existing_refresh():
    text = (
        ROOT
        / "views"
        / "wbs_project_view.py"
    ).read_text()

    assert (
        "_GLOBAL_EVENT_BUS.typography_changed.connect"
        in text
    )

    assert (
        "self.refresh_wbs_appearance"
        in text
    )

    assert "tree.scheduleDelayedItemsLayout()" in text
    assert "tree.doItemsLayout()" in text


def test_wbs_typography_refresh_does_not_emit_model_layout_changed():
    text = (
        ROOT
        / "views"
        / "wbs_project_view.py"
    ).read_text()

    refresh_start = text.index(
        "def _apply_wbs_appearance_refresh"
    )

    refresh_end = text.index(
        "def on_wbs_preferences_changed",
        refresh_start,
    )

    block = text[
        refresh_start:refresh_end
    ]

    assert ".layoutChanged.emit" not in block
    assert "beginResetModel" not in block
    assert "endResetModel" not in block
