
from pathlib import Path


WBS = Path(
    "todo_bird_app/views/"
    "wbs_project_view.py"
).read_text()

PROJECTS = Path(
    "todo_bird_app/views/"
    "projects_view.py"
).read_text()

SEARCH = Path(
    "todo_bird_app/ui/components/"
    "search_field.py"
).read_text()


def test_wbs_toolbar_no_longer_uses_rigid_widths():
    assert (
        "self.search_field.setFixedWidth(240)"
        not in WBS
    )
    assert (
        "self.status_combo.setFixedWidth(130)"
        not in WBS
    )
    assert (
        "self.density_control.setFixedWidth(160)"
        not in WBS
    )


def test_wbs_search_is_bounded_and_expanding():
    assert (
        "self.search_field.setMinimumWidth(160)"
        in WBS
    )
    assert (
        "self.search_field.setMaximumWidth(300)"
        in WBS
    )
    assert (
        "QSizePolicy.Expanding"
        in WBS
    )


def test_wbs_status_and_density_keep_readable_bounds():
    assert (
        "self.status_combo.setMinimumWidth(110)"
        in WBS
    )
    assert (
        "self.status_combo.setMaximumWidth(145)"
        in WBS
    )
    assert (
        "self.density_control.setMinimumWidth(145)"
        in WBS
    )
    assert (
        "self.density_control.setMaximumWidth(175)"
        in WBS
    )


def test_project_sidebar_is_bounded_not_fixed():
    assert (
        "left_panel.setFixedWidth(240)"
        not in PROJECTS
    )
    assert (
        "left_panel.setMinimumWidth(180)"
        in PROJECTS
    )
    assert (
        "left_panel.setMaximumWidth(240)"
        in PROJECTS
    )


def test_project_view_switcher_is_responsive():
    assert (
        "self.view_mode_control.setFixedWidth(240)"
        not in PROJECTS
    )
    assert (
        "self.view_mode_control.setMinimumWidth(190)"
        in PROJECTS
    )
    assert (
        "self.view_mode_control.setMaximumWidth(240)"
        in PROJECTS
    )


def test_project_heading_can_yield_horizontal_space():
    assert (
        "self.proj_name_label.setMinimumWidth(80)"
        in PROJECTS
    )
    assert (
        "QSizePolicy.Ignored"
        in PROJECTS
    )


def test_responsive_phase_preserves_accessibility_semantics():
    expected_wbs = (
        "Search work breakdown structure",
        "WBS status filter",
        "WBS display density",
        "Expand all WBS branches",
        "Collapse all WBS branches",
        "Create new project task",
    )

    for text in expected_wbs:
        assert text in WBS

    expected_projects = (
        "Create new project",
        "Project list",
        "Selected project",
        "Project view mode",
    )

    for text in expected_projects:
        assert text in PROJECTS


def test_search_field_uses_measured_height_not_fixed_height():
    assert "self.setFixedHeight(34)" not in SEARCH
    assert "self._update_geometry()" in SEARCH
    assert "fm.height()" in SEARCH

    # Width remains owned by parent/layout, which is the desired
    # responsive architecture.
    assert "self.setFixedWidth(" not in SEARCH
