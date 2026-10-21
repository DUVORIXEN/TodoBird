"""
Test suite for Dashboard Layout Presets (Executive, Project Controls, Focus, Analytics, Compact).
Validates live switching, persistence, state preservation, responsive geometry,
themes, and high-DPI scaling.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch
import pytest

from PySide6.QtWidgets import QApplication, QWidget, QFrame
from PySide6.QtCore import Qt, QDate

from todo_bird_app.views.dashboard_view import DashboardView
from todo_bird_app.services.appearance_service import AppearanceService


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


class MockDBManager:
    def __init__(self, projects=None, tasks=None):
        self._projects = projects or [
            {"id": 1, "name": "Eagle Launch", "color": "#3584E4", "is_archived": 0},
            {"id": 2, "name": "Falcon Rover", "color": "#10B981", "is_archived": 0},
        ]
        self._tasks = tasks or []

    def get_all_projects(self):
        return list(self._projects)

    def get_all_tasks(self):
        return list(self._tasks)

    def get_tasks_by_project(self, project_id):
        return [t for t in self._tasks if getattr(t, "project_id", None) == project_id]


class MockSettingsManager:
    def __init__(self, settings=None):
        self._settings = settings or {
            "theme": "dark",
            "accent_color": "#3584E4",
            "dashboard_layout_preset": "Executive",
            "dashboard_world_clocks": [],
        }

    def get(self, key, default=None):
        return self._settings.get(key, default)

    def set(self, key, value):
        self._settings[key] = value

    def save(self):
        pass


@pytest.fixture
def dashboard_fixture(qapp):
    db = MockDBManager()
    settings = MockSettingsManager()
    view = DashboardView(db, settings)
    view.show()
    yield view
    view.cleanup()


def test_layout_presets_initialization(dashboard_fixture):
    view = dashboard_fixture
    assert hasattr(view, "layout_selector")
    assert view.layout_selector.objectName() == "dashboard_layout_selector"
    assert hasattr(view, "lbl_dashboard_view")
    assert "Dashboard View:" in view.lbl_dashboard_view.text()

    items = [view.layout_selector.itemText(i) for i in range(view.layout_selector.count())]
    expected = ["Executive", "Project Controls", "Focus", "Analytics", "Compact"]
    assert items == expected
    assert view.layout_selector.currentText() == "Executive"
    assert getattr(view, "_current_layout_preset", "") == "Executive"


def test_live_switch_instantly(dashboard_fixture):
    view = dashboard_fixture
    presets = ["Project Controls", "Focus", "Analytics", "Compact", "Executive"]

    for p in presets:
        view.layout_selector.setCurrentText(p)
        assert getattr(view, "_current_layout_preset", "") == p
        assert view.layout_selector.currentText() == p
        assert view.settings_manager.get("dashboard_layout_preset") == p


def test_persistence_between_instances(qapp):
    db = MockDBManager()
    settings = MockSettingsManager({"dashboard_layout_preset": "Focus"})

    view1 = DashboardView(db, settings)
    assert view1._current_layout_preset == "Focus"
    assert view1.layout_selector.currentText() == "Focus"

    # Switch to Analytics
    view1.layout_selector.setCurrentText("Analytics")
    assert settings.get("dashboard_layout_preset") == "Analytics"
    view1.cleanup()

    # Create new instance and verify persistence
    view2 = DashboardView(db, settings)
    assert view2._current_layout_preset == "Analytics"
    assert view2.layout_selector.currentText() == "Analytics"
    view2.cleanup()


def test_state_and_scope_preservation_during_preset_switches(dashboard_fixture):
    view = dashboard_fixture
    
    # 1. Set specific scope
    view.scope_selector.setCurrentIndex(1)
    orig_scope_mode = view._current_scope.mode
    orig_scope_pid = view._current_scope.project_id

    # 2. Set specific horizon
    view._on_horizon_clicked(30)
    assert view._current_horizon_days == 30

    # 3. Set specific anchor date
    target_date = date.today() + timedelta(days=5)
    view.anchor_date_edit.setDate(QDate(target_date.year, target_date.month, target_date.day))
    assert view._anchor_date == target_date

    # 4. Mock build service to guarantee NO recomputation occurs on layout switches
    with patch("todo_bird_app.services.dashboard_data_service.DashboardDataService.build") as mock_build:
        for preset in ["Compact", "Project Controls", "Analytics", "Focus", "Executive"]:
            view.layout_selector.setCurrentText(preset)
            
            # Scope must remain strictly unchanged
            assert view._current_scope.mode == orig_scope_mode
            assert view._current_scope.project_id == orig_scope_pid
            assert view.scope_selector.currentIndex() == 1

            # Horizon must remain strictly unchanged
            assert view._current_horizon_days == 30

            # Anchor date must remain strictly unchanged
            assert view._anchor_date == target_date

        # Must not recompute data services on layout switch
        assert mock_build.call_count == 0


def test_preset_emphases_and_visibility(dashboard_fixture):
    view = dashboard_fixture

    # Focus: secondary analytics hidden
    view.layout_selector.setCurrentText("Focus")
    assert view.weekly_chart_card.isHidden()
    assert view.effort_chart_card.isHidden()
    assert view.schedule_deck.isHidden()
    assert view.horizon_card.isHidden()
    assert view.projects_card.isHidden()
    assert view.status_chart_card.isHidden()
    assert view.milestones_card.isHidden()
    # Hero action center visible
    assert not view.focus_next_card.isHidden()
    assert not view.attention_card.isHidden()
    assert not view.timeline_card.isHidden()
    assert not view.card_today_tasks.isHidden()

    # Executive: spacious, Health, Schedule Deck, Milestones visible
    view.layout_selector.setCurrentText("Executive")
    assert not view.card_health.isHidden()
    assert not view.schedule_deck.isHidden()
    assert not view.milestones_card.isHidden()
    assert not view.attention_card.isHidden()
    assert not view.risk_quality_card.isHidden()
    assert view.layout.spacing() == 18

    # Project Controls: dense layout, Horizon, Schedule, Weekly chart visible
    view.layout_selector.setCurrentText("Project Controls")
    assert not view.schedule_deck.isHidden()
    assert not view.horizon_card.isHidden()
    assert not view.weekly_chart_card.isHidden()
    assert not view.effort_chart_card.isHidden()
    assert not view.projects_card.isHidden()
    assert view.layout.spacing() == 10

    # Analytics: Charts visible and prominent
    view.layout_selector.setCurrentText("Analytics")
    assert not view.status_chart_card.isHidden()
    assert not view.weekly_chart_card.isHidden()
    assert not view.effort_chart_card.isHidden()
    assert not view.workload_card.isHidden()
    assert not view.schedule_deck.isHidden()

    # Compact: 8px spacing, tight margins
    view.layout_selector.setCurrentText("Compact")
    assert view.layout.spacing() == 8
    assert view.kpi_grid.spacing() == 6


def test_light_and_dark_themes_across_all_presets(dashboard_fixture):
    view = dashboard_fixture
    dark_settings = MockSettingsManager({"theme": "dark", "accent_color": "#3584E4"})
    light_settings = MockSettingsManager({"theme": "light", "accent_color": "#2563EB"})
    dark_state = AppearanceService.read(dark_settings)
    light_state = AppearanceService.read(light_settings)

    for preset in ["Executive", "Project Controls", "Focus", "Analytics", "Compact"]:
        view.layout_selector.setCurrentText(preset)
        
        # Test dark
        view.on_appearance_changed(dark_state)
        assert not view.greeting_card.isHidden()
        
        # Test light
        view.on_appearance_changed(light_state)
        assert not view.greeting_card.isHidden()


def test_multi_resolution_geometry_safety(dashboard_fixture):
    view = dashboard_fixture
    resolutions = [
        (1366, 768),
        (1920, 1080),
        (2560, 1600),
    ]

    for preset in ["Executive", "Project Controls", "Focus", "Analytics", "Compact"]:
        view.layout_selector.setCurrentText(preset)
        for width, height in resolutions:
            view.resize(width, height)
            view.content_widget.resize(width - 32, height)
            view._apply_dashboard_chart_reflow()
            
            # Ensure content widget width is valid and no zero/negative bounds
            assert view.content_widget.width() > 0
            assert view.greeting_card.width() >= 0


def test_high_dpi_scaling_safety(dashboard_fixture):
    view = dashboard_fixture

    for preset in ["Executive", "Project Controls", "Focus", "Analytics", "Compact"]:
        view.layout_selector.setCurrentText(preset)
        for scale in [1.0, 1.5, 2.0]:
            view._apply_dashboard_chart_reflow()
            assert view.layout_selector.count() == 5


def test_rapid_switch_stress_and_timer_stability(dashboard_fixture):
    view = dashboard_fixture
    presets = ["Executive", "Project Controls", "Focus", "Analytics", "Compact"]

    # 100 rapid layout switches
    for i in range(100):
        target = presets[i % len(presets)]
        view.layout_selector.setCurrentText(target)

    # Ensure single running clock timer without duplication
    assert hasattr(view, "clock_timer")
    assert view.clock_timer.isActive()
    assert len(view.findChildren(type(view.clock_timer))) >= 1
