
from pathlib import Path

from PySide6.QtWidgets import QApplication

from todo_bird_app.ui.components.segmented_control import (
    SegmentedControl,
)


def _app():
    return QApplication.instance() or QApplication([])


def test_segmented_control_exposes_selected_state():
    _app()

    control = SegmentedControl(
        segments=[
            ("Professional", "professional"),
            ("Balanced", "balanced"),
            ("Personal", "personal"),
        ],
        selected_index=1,
        animate=False,
    )

    assert control.accessibleName() == "Segmented control"

    description = control.accessibleDescription()

    assert "Selected: Balanced" in description
    assert "Professional" in description
    assert "Personal" in description
    assert "Left and Right arrow keys" in description


def test_segmented_control_accessible_state_updates():
    _app()

    control = SegmentedControl(
        segments=[
            ("WBS Hierarchy", "wbs"),
            ("Task List", "list"),
        ],
        selected_index=0,
        animate=False,
    )

    assert (
        "Selected: WBS Hierarchy"
        in control.accessibleDescription()
    )

    control.set_selected_index(
        1,
        notify=False,
    )

    assert (
        "Selected: Task List"
        in control.accessibleDescription()
    )


def test_wbs_tree_has_semantic_identity():
    src = Path(
        "todo_bird_app/views/"
        "wbs_tree_view.py"
    ).read_text()

    assert (
        'setAccessibleName("Work breakdown structure")'
        in src
    )

    assert "Alt+Up or Alt+Down" in src


def test_wbs_toolbar_controls_are_named():
    src = Path(
        "todo_bird_app/views/"
        "wbs_project_view.py"
    ).read_text()

    expected = (
        "Search work breakdown structure",
        "WBS status filter",
        "WBS display density",
        "Expand all WBS branches",
        "Collapse all WBS branches",
        "Create new project task",
    )

    for text in expected:
        assert text in src


def test_projects_controls_are_named():
    src = Path(
        "todo_bird_app/views/"
        "projects_view.py"
    ).read_text()

    expected = (
        "Create new project",
        "Project list",
        "Selected project",
        "Project view mode",
    )

    for text in expected:
        assert text in src


def test_phase1f4_does_not_modify_visual_geometry_contracts():
    segmented = Path(
        "todo_bird_app/ui/components/"
        "segmented_control.py"
    ).read_text()

    tree = Path(
        "todo_bird_app/views/"
        "wbs_tree_view.py"
    ).read_text()

    # Existing accessibility/interaction contract remains, while
    # the global design system owns a typography-safe measured baseline.
    assert "self.setFixedHeight(34)" not in segmented
    assert "self.setMinimumHeight(34)" not in segmented
    assert "self._update_geometry()" in segmented
    assert "max(28, int(fm.height()) + 10)" in segmented
    assert "def minimumSizeHint(" in segmented
    assert "QEvent.FontChange" in segmented
    assert "self.setFocusPolicy(Qt.StrongFocus)" in segmented
    assert "Qt.Key_Right" in segmented
    assert "Qt.Key_Left" in segmented

    assert "self.setUniformRowHeights(True)" in tree
    assert "self.setSelectionMode(QAbstractItemView.SingleSelection)" in tree
    assert "self.setAnimated(True)" in tree
    assert "self.setFocusPolicy(Qt.StrongFocus)" in tree
