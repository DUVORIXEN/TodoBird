import sys
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from todo_bird_app.views.wbs_project_view import (
    WBSProjectView,
)


class FakeSettings:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


def _app():
    return QApplication.instance() or QApplication([])


def _view():
    _app()

    return WBSProjectView(
        db_manager=None,
        settings_manager=FakeSettings(),
        project_id=None,
    )


def test_responsive_toolbar_has_two_managed_rows():
    src = Path(
        "todo_bird_app/views/"
        "wbs_project_view.py"
    ).read_text()

    assert "toolbar_primary_layout" in src
    assert "toolbar_secondary_layout" in src
    assert "_apply_toolbar_responsive_layout" in src


def test_narrow_toolbar_uses_second_row():
    app = _app()
    view = _view()

    view.setFixedSize(600, 500)
    view.show()
    app.processEvents()
    
    view._apply_toolbar_responsive_layout()
    app.processEvents()

    assert view._toolbar_compact_mode is True
    assert not view.toolbar_secondary_row.isHidden()

    # Search and Status remain in row 1.
    assert (
        view.toolbar_primary_layout.indexOf(
            view.search_field
        )
        >= 0
    )
    assert (
        view.toolbar_primary_layout.indexOf(
            view.status_combo
        )
        >= 0
    )

    # Density and New Task move to row 2.
    assert (
        view.toolbar_secondary_layout.indexOf(
            view.density_control
        )
        >= 0
    )
    assert (
        view.toolbar_secondary_layout.indexOf(
            view.btn_add_task
        )
        >= 0
    )

    view.close()


def test_wide_toolbar_returns_to_single_row():
    app = _app()
    view = _view()

    view.resize(1000, 600)
    view.show()
    app.processEvents()

    view._apply_toolbar_responsive_layout()
    app.processEvents()

    assert view._toolbar_compact_mode is False
    assert view.toolbar_secondary_row.isHidden()

    for widget in (
        view.search_field,
        view.status_combo,
        view.density_control,
        view.btn_expand_all,
        view.btn_collapse_all,
        view.btn_add_task,
    ):
        assert (
            view.toolbar_primary_layout.indexOf(
                widget
            )
            >= 0
        )

    view.close()


def test_reflow_preserves_accessibility_authority():
    src = Path(
        "todo_bird_app/views/"
        "wbs_project_view.py"
    ).read_text()

    for text in (
        "Search work breakdown structure",
        "WBS status filter",
        "WBS display density",
        "Expand all WBS branches",
        "Collapse all WBS branches",
        "Create new project task",
    ):
        assert text in src


def test_reflow_never_hides_function_controls():
    src = Path(
        "todo_bird_app/views/"
        "wbs_project_view.py"
    ).read_text()

    # Only the secondary ROW itself is responsive.
    # Functional controls are moved, never hidden.
    forbidden = (
        "self.search_field.hide()",
        "self.status_combo.hide()",
        "self.density_control.hide()",
        "self.btn_expand_all.hide()",
        "self.btn_collapse_all.hide()",
        "self.btn_add_task.hide()",
    )

    for text in forbidden:
        assert text not in src
