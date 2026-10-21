"""
Functional Verification of View WBS Navigation and Cross-View Workflows.
Tests:
- Direct NavigationController.set_active_section("wbs", project_id)
- DashboardView Project Schedule Card "📋 View WBS" button
- DashboardView Portfolio Rankings Card "📋" button
- DashboardView Work Breakdown Rollup Card "Open Full WBS Hierarchy →" button
- GanttView "📋 WBS" button
- WBSProjectView "📊 Gantt" button
- Task List ("tasks") fallback routing to "today"
"""

import pytest
from datetime import date
from PySide6.QtWidgets import QApplication, QPushButton

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.project import Project
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.views.main_window import MainWindow
from todo_bird_app.views.dashboard_view import DashboardView
from todo_bird_app.views.projects_view import ProjectsView
from todo_bird_app.views.gantt_view import GanttView


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def test_env(tmp_path):
    db_file = tmp_path / "test_wbs_nav.db"
    db = DatabaseManager(str(db_file))
    settings = SettingsManager(db_manager=db, config_dir=tmp_path)
    theme = ThemeController(settings)

    # Seed 2 distinct projects with tasks
    p1_id = db.insert_project({"name": "Project Alpha", "color": "#3584E4"})
    p2_id = db.insert_project({"name": "Project Beta", "color": "#10B981"})

    today_str = date.today().strftime("%Y-%m-%d")
    t1 = Task(
        title="Alpha Root Task",
        project_id=p1_id,
        planned_date=today_str,
        due_date=today_str,
        planned_effort_minutes=120,
        status=TaskStatus.IN_PROGRESS,
        actual_start_date=today_str,
        actual_start_time="09:00",
    )
    t2 = Task(
        title="Beta Root Task",
        project_id=p2_id,
        planned_date=today_str,
        due_date=today_str,
        planned_effort_minutes=240,
        status=TaskStatus.PLANNED,
    )
    db.insert_task(t1.to_dict())
    db.insert_task(t2.to_dict())

    return db, settings, theme, p1_id, p2_id


def test_navigation_controller_wbs_route(qapp, test_env):
    """Direct NavigationController.set_active_section('wbs', pid) switches to Projects WBS view."""
    db, settings, theme, p1_id, p2_id = test_env
    window = MainWindow(db, settings, theme)

    # Initial state is dashboard
    assert window.navigation_controller.current_section == "dashboard"

    # Navigate to WBS for Project Beta
    window.navigation_controller.set_active_section("wbs", p2_id)
    qapp.processEvents()

    # 1. Main stacked widget is showing ProjectsView
    proj_idx, proj_widget = window.view_stack_map["projects"]
    assert window.stacked_widget.currentIndex() == proj_idx
    assert isinstance(proj_widget, ProjectsView)

    # 2. ProjectsView mode is set to WBS (view_stack index 0, segmented control index 0)
    assert proj_widget.view_stack.currentIndex() == 0
    assert proj_widget.view_mode_control.selected_index == 0

    # 3. Selected project is Project Beta
    assert proj_widget.selected_project_id == p2_id
    assert "Project Beta" in proj_widget.proj_name_label.text()
    assert proj_widget.wbs_view.project_id == p2_id

    # 4. Header title reflects WBS
    assert window.headerbar.title_label.text() == "WBS Hierarchy"
    assert "rollups" in window.headerbar.subtitle_label.text().lower()

    # 5. Sidebar highlights "projects"
    assert window.sidebar._selected_key == "projects"


def test_dashboard_project_schedule_view_wbs_button(qapp, test_env):
    """Project Schedule Card '📋 View WBS' button triggers navigation to that project's WBS."""
    db, settings, theme, p1_id, p2_id = test_env
    window = MainWindow(db, settings, theme)

    dashboard = window.dashboard_view
    dashboard.refresh_data()

    # Select Project Alpha scope on Dashboard
    dashboard._select_project_scope(p1_id)
    qapp.processEvents()
    assert dashboard._current_scope.is_project is True
    assert dashboard._current_scope.project_id == p1_id
    assert dashboard.project_schedule_card.isHidden() is False

    # Find the View WBS button inside project_schedule_card
    wbs_buttons = [
        btn for btn in dashboard.project_schedule_card.findChildren(QPushButton)
        if "View WBS" in btn.text()
    ]
    assert len(wbs_buttons) >= 1
    wbs_btn = wbs_buttons[0]

    # Click View WBS
    wbs_btn.click()
    qapp.processEvents()

    # ProjectsView should now be visible in WBS mode with Project Alpha
    proj_idx, proj_widget = window.view_stack_map["projects"]
    assert window.stacked_widget.currentIndex() == proj_idx
    assert proj_widget.view_stack.currentIndex() == 0
    assert proj_widget.selected_project_id == p1_id
    assert "Project Alpha" in proj_widget.proj_name_label.text()
    assert proj_widget.wbs_view.project_id == p1_id


def test_dashboard_portfolio_rankings_wbs_button(qapp, test_env):
    """Portfolio Rankings Card row '📋' button triggers navigation to chosen project's WBS."""
    db, settings, theme, p1_id, p2_id = test_env
    window = MainWindow(db, settings, theme)

    dashboard = window.dashboard_view
    dashboard.refresh_data()
    qapp.processEvents()

    # Portfolio mode: rankings card visible
    assert dashboard._current_scope.is_portfolio is True
    assert dashboard.portfolio_rankings_card.isHidden() is False

    # Find all WBS buttons in rankings
    wbs_buttons = [
        btn for btn in dashboard.rankings_vbox.parentWidget().findChildren(QPushButton)
        if btn.toolTip() == "View WBS"
    ]
    assert len(wbs_buttons) >= 2

    # Click the first ranking row's WBS button
    wbs_buttons[0].click()
    qapp.processEvents()

    # Should have navigated to ProjectsView in WBS mode
    proj_idx, proj_widget = window.view_stack_map["projects"]
    assert window.stacked_widget.currentIndex() == proj_idx
    assert proj_widget.view_stack.currentIndex() == 0
    assert proj_widget.wbs_view.project_id is not None


def test_dashboard_wbs_rollup_card_link(qapp, test_env):
    """Work Breakdown Rollup Card direct link navigates to WBS."""
    db, settings, theme, p1_id, p2_id = test_env
    window = MainWindow(db, settings, theme)

    dashboard = window.dashboard_view
    dashboard.refresh_data()
    dashboard._select_project_scope(p2_id)
    qapp.processEvents()

    # Find open WBS link in projects card
    links = [
        btn for btn in dashboard.projects_card.findChildren(QPushButton)
        if "WBS Hierarchy" in btn.text()
    ]
    assert len(links) >= 1
    links[0].click()
    qapp.processEvents()

    proj_idx, proj_widget = window.view_stack_map["projects"]
    assert window.stacked_widget.currentIndex() == proj_idx
    assert proj_widget.view_stack.currentIndex() == 0
    assert proj_widget.selected_project_id == p2_id


def test_gantt_to_wbs_cross_navigation(qapp, test_env):
    """GanttView '📋 WBS' button switches smoothly to WBS view for the active project."""
    db, settings, theme, p1_id, p2_id = test_env
    window = MainWindow(db, settings, theme)

    # Navigate to Gantt for Project Beta
    window.navigation_controller.set_active_section("gantt", p2_id)
    qapp.processEvents()

    gantt_idx, gantt_widget = window.view_stack_map["gantt"]
    assert window.stacked_widget.currentIndex() == gantt_idx
    assert gantt_widget.current_project_id == p2_id

    # Click WBS button in Gantt
    assert hasattr(gantt_widget, "wbs_nav_btn")
    gantt_widget.wbs_nav_btn.click()
    qapp.processEvents()

    # Should now be on ProjectsView in WBS mode with Project Beta
    proj_idx, proj_widget = window.view_stack_map["projects"]
    assert window.stacked_widget.currentIndex() == proj_idx
    assert proj_widget.view_stack.currentIndex() == 0
    assert proj_widget.selected_project_id == p2_id


def test_wbs_to_gantt_cross_navigation(qapp, test_env):
    """WBSProjectView '📊 Gantt' button switches smoothly to Gantt view for the active project."""
    db, settings, theme, p1_id, p2_id = test_env
    window = MainWindow(db, settings, theme)

    # Navigate to WBS for Project Alpha
    window.navigation_controller.set_active_section("wbs", p1_id)
    qapp.processEvents()

    proj_idx, proj_widget = window.view_stack_map["projects"]
    assert window.stacked_widget.currentIndex() == proj_idx
    assert proj_widget.wbs_view.project_id == p1_id

    # Click Gantt button in WBS
    assert hasattr(proj_widget.wbs_view, "btn_gantt")
    proj_widget.wbs_view.btn_gantt.click()
    qapp.processEvents()

    # Should now be on GanttView with Project Alpha
    gantt_idx, gantt_widget = window.view_stack_map["gantt"]
    assert window.stacked_widget.currentIndex() == gantt_idx
    assert gantt_widget.current_project_id == p1_id


def test_tasks_alias_navigation_routes_to_today(qapp, test_env):
    """Navigation to 'tasks' alias routes cleanly to 'today' view without error."""
    db, settings, theme, p1_id, p2_id = test_env
    window = MainWindow(db, settings, theme)

    window.navigation_controller.set_active_section("tasks")
    qapp.processEvents()

    today_idx, today_widget = window.view_stack_map["today"]
    assert window.stacked_widget.currentIndex() == today_idx
    assert window.sidebar._selected_key == "today"
