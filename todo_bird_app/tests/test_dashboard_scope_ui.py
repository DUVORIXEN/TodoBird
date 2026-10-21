"""
UI Integration Tests for Dashboard Scope Selector & Decision Cockpit (Phase 2F).
Verifies:
- Scope Selector initialization and project population
- Portfolio Mode vs. Project Mode panel visibility switching
- 3-Signal health display and transparent diagnostics
- Lookahead horizon switching (7D / 14D / 30D)
- Effort Variance chart integration and responsive behavior
- WBS summary rollup breakdown in Project mode
- Top-5 Attention Queue with count indicator and drill-down
"""

import pytest
from datetime import date, datetime, timedelta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.project import Project
from todo_bird_app.models.task import Task, TaskPriority, TaskStatus
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.views.dashboard_view import DashboardView
from todo_bird_app.services.dashboard_data_service import DashboardScope


@pytest.fixture
def app():
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "test_scope_ui.db"
    manager = DatabaseManager(str(db_file))
    return manager


@pytest.fixture
def settings(db, tmp_path):
    return SettingsManager(db_manager=db, config_dir=tmp_path)


def test_dashboard_scope_selector_initialization(app, db, settings):
    """Scope selector initializes with 'All Projects' and active projects sorted."""
    p1_id = db.insert_project({"name": "Project Bravo", "color": "#3584E4"})
    p2_id = db.insert_project({"name": "Project Alpha", "color": "#10B981"})
    # Archived project should be excluded
    p3_id = db.insert_project({"name": "Project Archived", "color": "#9CA3AF", "is_archived": 1})

    dashboard = DashboardView(db, settings)
    dashboard.refresh_data()

    combo = dashboard.scope_selector
    assert combo is not None
    assert combo.count() >= 3  # 1 All Projects + default Inbox + 2 active projects
    assert combo.itemText(0) == "All Projects"
    assert combo.itemData(0) is None

    # Check active projects are listed and archived is excluded
    texts = [combo.itemText(i) for i in range(combo.count())]
    assert any("Alpha" in t for t in texts)
    assert any("Bravo" in t for t in texts)
    assert not any("Archived" in t for t in texts)
    assert combo.currentIndex() == 0
    assert dashboard._current_scope.is_portfolio is True


def test_dashboard_scope_switching_behavior(app, db, settings):
    """Switching scope selector transitions DashboardScope and reflows deck."""
    p1_id = db.insert_project({"name": "Core Engine", "color": "#3584E4"})

    dashboard = DashboardView(db, settings)
    dashboard.refresh_data()

    # Initial state: Portfolio mode
    assert dashboard._current_scope.is_portfolio is True
    assert dashboard.portfolio_rankings_card.isHidden() is False
    assert dashboard.project_schedule_card.isHidden() is True

    # Switch to Project mode via programmatic selector
    dashboard._select_project_scope(p1_id)
    assert dashboard._current_scope.is_project is True
    assert dashboard._current_scope.project_id == p1_id
    assert "Core Engine" in dashboard._current_scope.project_name

    # Panel deck updates
    assert dashboard.portfolio_rankings_card.isHidden() is True
    assert dashboard.project_schedule_card.isHidden() is False

    # Switch back to Portfolio mode
    dashboard.scope_selector.setCurrentIndex(0)
    assert dashboard._current_scope.is_portfolio is True
    assert dashboard.portfolio_rankings_card.isHidden() is False
    assert dashboard.project_schedule_card.isHidden() is True


def test_dashboard_select_project_scope_helper(app, db, settings):
    """_select_project_scope programmatic selection updates dropdown."""
    p1_id = db.insert_project({"name": "Project 1", "color": "#3584E4"})
    p2_id = db.insert_project({"name": "Project 2", "color": "#E95420"})

    dashboard = DashboardView(db, settings)
    dashboard.refresh_data()

    dashboard._select_project_scope(p2_id)
    assert dashboard._current_scope.is_project is True
    assert dashboard._current_scope.project_id == p2_id


def test_dashboard_3_signal_health_display(app, db, settings):
    """Health card renders 3 independent signals (S X R) without single score compression."""
    dashboard = DashboardView(db, settings)
    dashboard.refresh_data()

    health_text = dashboard.card_health.value_label.text()
    # Expect 3 dots separated by spaces
    assert any(sym in health_text for sym in ("●", "🟢", "🟡", "🔴"))
    assert len(health_text.split()) == 3

    sub_text = dashboard.card_health.sub_label.text()
    assert "S:" in sub_text
    assert "X:" in sub_text
    assert "R:" in sub_text

    # Tooltip must contain transparent diagnostics
    assert len(dashboard.card_health.toolTip()) > 10


def test_dashboard_lookahead_horizon_buttons(app, db, settings):
    """Clicking 7D, 14D, and 30D buttons switches lookahead horizon."""
    dashboard = DashboardView(db, settings)
    dashboard.refresh_data()

    assert dashboard._current_horizon_days == 7
    assert dashboard.btn_h7.isChecked() is True

    dashboard.btn_h14.click()
    assert dashboard._current_horizon_days == 14
    assert dashboard.btn_h14.isChecked() is True
    assert dashboard.btn_h7.isChecked() is False

    dashboard.btn_h30.click()
    assert dashboard._current_horizon_days == 30
    assert dashboard.btn_h30.isChecked() is True


def test_dashboard_effort_variance_chart_integrated(app, db, settings):
    """Effort variance chart is constructed, configured, and accepts daily data."""
    dashboard = DashboardView(db, settings)
    dashboard.refresh_data()

    assert hasattr(dashboard, "effort_chart")
    assert dashboard.effort_chart is not None
    assert hasattr(dashboard, "effort_chart_type")

    # Change chart type
    dashboard._on_effort_chart_changed("Stacked Bar")
    assert dashboard.effort_chart.chart_type == "Stacked Bar"


def test_dashboard_bottom_wbs_rollup_in_project_mode(app, db, settings):
    """Bottom area displays WBS rollup in Project mode and Project Progress in Portfolio mode."""
    pid = db.insert_project({"name": "Phoenix Project", "color": "#10B981"})

    tc = TaskController(db)
    t1 = Task(
        title="Architecture Package",
        project_id=pid,
        planned_date=date.today().strftime("%Y-%m-%d"),
        due_date=date.today().strftime("%Y-%m-%d"),
        planned_effort_minutes=180,
        status=TaskStatus.IN_PROGRESS,
        actual_start_date=date.today().strftime("%Y-%m-%d"),
    )
    tc.add_task(t1)

    dashboard = DashboardView(db, settings)
    dashboard.refresh_data()

    # In Portfolio mode:
    assert "Active Projects Progress" in dashboard.projects_card.header_label.text()

    # Switch to Project mode:
    dashboard._select_project_scope(pid)
    assert "Work Breakdown Rollup" in dashboard.projects_card.header_label.text()
    assert dashboard.projects_vbox.count() >= 1


def test_dashboard_attention_queue_limit_and_counter(app, db, settings):
    """Attention queue limits display to top 5 items and provides explicit counter."""
    yesterday_str = (date.today() - timedelta(days=2)).strftime("%Y-%m-%d")

    tc = TaskController(db)
    # Add multiple overdue tasks
    for i in range(7):
        t = Task(
            title=f"Overdue Task {i}",
            planned_date=yesterday_str,
            due_date=yesterday_str,
            priority=TaskPriority.HIGH,
            status=TaskStatus.PLANNED,
        )
        tc.add_task(t)

    dashboard = DashboardView(db, settings)
    dashboard.refresh_data()

    # Count of attention items in vbox: up to 5 items + 1 counter row
    assert dashboard.attention_vbox.count() >= 2
    # Check that model has total attention count reflecting all overdue tasks
    assert dashboard._current_model.actions.total_attention_count >= 7
    # But displayed items in action layer is capped at 5
    assert len(dashboard._current_model.actions.items) <= 5
