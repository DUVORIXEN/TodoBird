"""
Tests for DashboardDataService (Phase 2F Decision Cockpit).
"""

from datetime import date, datetime, timedelta
import pytest

from todo_bird_app.models.project import Project
from todo_bird_app.models.task import Task, TaskPriority, TaskStatus
from todo_bird_app.services.dashboard_data_service import (
    DashboardDataService,
    DashboardScope,
    DashboardModel,
)


class MockDBManager:
    def __init__(self, projects=None, tasks=None, allocations=None):
        self._projects = projects or []
        self._tasks = tasks or []
        self._allocations = allocations or []

    def get_all_projects(self):
        return [p.to_dict() if hasattr(p, "to_dict") else p for p in self._projects]

    def get_all_tasks(self):
        return [t.to_dict() if hasattr(t, "to_dict") else t for t in self._tasks]

    def get_tasks_by_project(self, project_id):
        return [
            t.to_dict() if hasattr(t, "to_dict") else t
            for t in self._tasks
            if (t.project_id if hasattr(t, "project_id") else t.get("project_id")) == project_id
        ]

    def get_task_allocations(self, task_id):
        return [
            a for a in self._allocations
            if a.get("task_id") == task_id
        ]


class MockSettingsManager:
    def __init__(self, capacity=480, working_days=None):
        self._capacity = capacity
        self._working_days = working_days or [0, 1, 2, 3, 4]

    def get(self, key, default=None):
        if key == "daily_capacity_minutes":
            return self._capacity
        if key == "working_weekdays":
            return self._working_days
        return default


def test_dashboard_data_service_portfolio_mode():
    today_str = date.today().strftime("%Y-%m-%d")
    yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_str = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

    projects = [
        {"id": 1, "name": "Project Alpha", "color": "#3584E4", "is_archived": 0},
        {"id": 2, "name": "Project Beta", "color": "#E95420", "is_archived": 0},
    ]
    tasks = [
        Task(
            id=1,
            project_id=1,
            title="Task 1 Today",
            status=TaskStatus.PLANNED,
            priority=TaskPriority.HIGH,
            planned_date=today_str,
            due_date=today_str,
            planned_effort_minutes=120,
        ),
        Task(
            id=2,
            project_id=1,
            title="Task 2 Overdue",
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.URGENT,
            planned_date=yesterday_str,
            due_date=yesterday_str,
            planned_effort_minutes=60,
        ),
        Task(
            id=3,
            project_id=2,
            title="Task 3 Blocked",
            status=TaskStatus.BLOCKED,
            priority=TaskPriority.MEDIUM,
            planned_date=today_str,
            due_date=tomorrow_str,
            planned_effort_minutes=90,
        ),
    ]
    t4 = Task(
        id=4,
        project_id=2,
        title="Task 4 Milestone",
        status=TaskStatus.PLANNED,
        priority=TaskPriority.MEDIUM,
        planned_date=tomorrow_str,
        due_date=tomorrow_str,
    )
    t4.is_milestone = True
    tasks.append(t4)

    db = MockDBManager(projects=projects, tasks=tasks)
    settings = MockSettingsManager(capacity=480)
    scope = DashboardScope(mode="portfolio", project_id=None, project_name="All Projects")

    model = DashboardDataService.build(db, settings, scope=scope)

    assert isinstance(model, DashboardModel)
    assert model.scope.is_portfolio is True
    # Executive Layer
    assert model.executive.active_tasks == 4
    assert model.executive.due_today >= 1
    assert model.executive.overdue == 1
    assert model.executive.daily_capacity_mins == 480
    assert model.executive.health_risk in ("yellow", "red")

    # Schedule Layer - Project Rankings
    assert len(model.schedule.project_rankings) == 2
    # Project Beta has blocked item -> ranked higher or equal risk
    assert model.schedule.project_rankings[0].project_id in (1, 2)

    # Execution Layer
    assert model.execution.focus_next_task is not None
    # Task 2 is overdue urgent -> must be focus next
    assert model.execution.focus_next_task.id == 2

    # Risk Layer
    assert model.risk.overdue_count == 1
    assert model.risk.blocked_count == 1

    # Needs Attention Queue
    assert len(model.actions.items) >= 1
    assert any("OVERDUE" in item.badge_text for item in model.actions.items)


def test_dashboard_data_service_project_mode():
    today_str = date.today().strftime("%Y-%m-%d")

    projects = [
        {"id": 42, "name": "Deep Project", "color": "#10B981", "is_archived": 0, "baseline_created_at": "2026-08-01T00:00:00"},
    ]
    tasks = [
        Task(
            id=10,
            project_id=42,
            title="Critical Task",
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.HIGH,
            planned_date=today_str,
            due_date=today_str,
            estimated_duration=120,
            planned_effort_minutes=120,
        ),
        Task(
            id=11,
            project_id=42,
            title="Completed Task",
            status=TaskStatus.COMPLETED,
            priority=TaskPriority.MEDIUM,
            planned_date=today_str,
            due_date=today_str,
            actual_end_date=today_str,
            actual_duration=120,
        ),
    ]

    db = MockDBManager(projects=projects, tasks=tasks)
    settings = MockSettingsManager(capacity=480)
    scope = DashboardScope(mode="project", project_id=42, project_name="Deep Project")

    model = DashboardDataService.build(db, settings, scope=scope)

    assert model.scope.is_project is True
    assert model.scope.project_id == 42
    assert model.executive.active_tasks == 1
    assert model.executive.completed_today == 1
    assert model.schedule.is_baselined is True
    assert model.executive.health_execution == "green"
    assert model.executive.health_risk == "yellow"
    assert "DEEP PROJECT" in model.executive.health_tooltip or "Project Health" in model.executive.health_tooltip


def test_dashboard_data_service_health_rules_and_data_quality():
    today_str = date.today().strftime("%Y-%m-%d")
    yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    projects = [{"id": 100, "name": "Risk Project", "color": "#EF4444", "is_archived": 0}]
    # 4 overdue tasks -> Execution health RED
    # 3 blocked tasks -> Risk health RED
    tasks = [
        Task(id=i, project_id=100, title=f"Overdue {i}", status=TaskStatus.PLANNED, priority=TaskPriority.HIGH, planned_date=yesterday_str, due_date=yesterday_str)
        for i in range(1, 5)
    ]
    tasks.extend([
        Task(id=i, project_id=100, title=f"Blocked {i}", status=TaskStatus.BLOCKED, priority=TaskPriority.MEDIUM, planned_date=today_str, due_date=today_str)
        for i in range(5, 8)
    ])
    # 1 zero-duration non-milestone task
    tasks.append(Task(id=9, project_id=100, title="Zero Dur", status=TaskStatus.PLANNED, priority=TaskPriority.LOW, estimated_duration=0))

    db = MockDBManager(projects=projects, tasks=tasks)
    settings = MockSettingsManager()
    scope = DashboardScope(mode="project", project_id=100, project_name="Risk Project")

    model = DashboardDataService.build(db, settings, scope=scope)

    assert model.executive.overdue == 4
    assert model.executive.health_execution == "red"
    assert model.risk.blocked_count == 3
    assert model.executive.health_risk == "red"
    assert model.executive.overall_health == "red"
    assert model.data_quality.zero_duration_count >= 1
    assert model.data_quality.fidelity_score < 100


def test_dashboard_data_service_empty_state():
    db = MockDBManager(projects=[], tasks=[])
    settings = MockSettingsManager()
    scope = DashboardScope(mode="portfolio")

    model = DashboardDataService.build(db, settings, scope=scope)

    assert model.executive.active_tasks == 0
    assert model.executive.due_today == 0
    assert model.executive.overdue == 0
    assert model.executive.completed_today == 0
    assert model.executive.overall_health == "green"
    assert len(model.schedule.project_rankings) == 0
    assert len(model.schedule.milestones) == 0
    assert len(model.actions.items) == 0

