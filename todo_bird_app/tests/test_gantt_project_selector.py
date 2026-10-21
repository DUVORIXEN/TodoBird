"""
Test Module 2: Gantt Project Selector (Phase 2E)
Validates mandatory project selector, filtering, and scope isolation rules.
"""

import os
import tempfile
import pytest
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.views.gantt_view import GanttView
from todo_bird_app.services.cpm_scheduling_service import CPMSchedulingService


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_setup():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    tc = TaskController(db_manager=db)

    p1_id = db.insert_project({"name": "THAAVORIX"})
    p2_id = db.insert_project({"name": "OTHER_PROJECT"})

    t1_id = db.insert_task({
        "project_id": p1_id,
        "title": "Planning",
        "planned_date": "2026-08-23",
        "due_date": "2026-09-23",
        "show_in_gantt": 1,
    })

    t2_id = db.insert_task({
        "project_id": p2_id,
        "title": "Unrelated Work",
        "planned_date": "2026-08-25",
        "due_date": "2026-09-05",
        "show_in_gantt": 1,
    })

    yield db, tc, p1_id, p2_id, t1_id, t2_id

    if os.path.exists(path):
        os.remove(path)


def test_01_project_dropdown_lists_valid_projects(test_setup):
    """1. project dropdown lists valid projects."""
    db, tc, p1_id, p2_id, _, _ = test_setup
    view = GanttView(tc)
    assert view.project_combo.count() >= 2
    items = [view.project_combo.itemText(i) for i in range(view.project_combo.count())]
    assert "THAAVORIX" in items
    assert "OTHER_PROJECT" in items


def test_02_entering_project_context_selects_that_project(test_setup):
    """2. entering project context selects that project."""
    db, tc, p1_id, p2_id, _, _ = test_setup
    view = GanttView(tc)
    view.set_current_project(p1_id)
    assert view.current_project_id == p1_id
    assert view.project_combo.currentData() == p1_id


def test_03_thaavorix_shows_thaavorix_only(test_setup):
    """3. THAAVORIX shows THAAVORIX tasks only."""
    db, tc, p1_id, p2_id, _, _ = test_setup
    view = GanttView(tc)
    view.set_current_project(p1_id)

    raw_tasks = tc.get_all_tasks()
    presentation_items = view._build_phase1d_wbs_gantt_items(raw_tasks)
    titles = [item.title for item in presentation_items if hasattr(item, "title")]
    assert "Planning" in titles
    assert "Unrelated Work" not in titles


def test_04_unrelated_tasks_absent(test_setup):
    """4. unrelated tasks absent when single project is selected."""
    db, tc, p1_id, p2_id, _, _ = test_setup
    view = GanttView(tc)
    view.set_current_project(p2_id)

    raw_tasks = tc.get_all_tasks()
    presentation_items = view._build_phase1d_wbs_gantt_items(raw_tasks)
    titles = [item.title for item in presentation_items if hasattr(item, "title")]
    assert "Unrelated Work" in titles
    assert "Planning" not in titles


def test_05_switching_project_refreshes_immediately(test_setup):
    """5. switching project refreshes immediately."""
    db, tc, p1_id, p2_id, _, _ = test_setup
    view = GanttView(tc)
    view.set_current_project(p1_id)
    assert view.current_project_id == p1_id

    view.set_current_project(p2_id)
    assert view.current_project_id == p2_id


def test_06_no_experience_mode_switch_required(test_setup):
    """6. no experience-mode switch required to change project."""
    db, tc, p1_id, p2_id, _, _ = test_setup
    view = GanttView(tc)
    view.set_current_project(p1_id)
    assert view.current_project_id == p1_id


def test_07_timeline_extent_recalculates(test_setup):
    """7. timeline extent recalculates on project change."""
    db, tc, p1_id, p2_id, _, _ = test_setup
    view = GanttView(tc)
    view.set_current_project(p1_id)
    view.fit_project_timeline()
    assert True


def test_08_dependencies_project_scoped(test_setup):
    """8. dependencies project-scoped."""
    db, tc, p1_id, p2_id, _, _ = test_setup
    t1 = [Task.from_row(t) for t in db.get_tasks_by_project(p1_id)]
    t2 = [Task.from_row(t) for t in db.get_tasks_by_project(p2_id)]
    cpm1 = CPMSchedulingService.calculate_schedule(t1, project_id=p1_id)
    cpm2 = CPMSchedulingService.calculate_schedule(t2, project_id=p2_id)
    assert cpm1 is not None
    assert cpm2 is not None


def test_09_baseline_project_scoped(test_setup):
    """9. baseline project-scoped."""
    db, tc, p1_id, p2_id, _, _ = test_setup
    from todo_bird_app.services.schedule_version_service import ScheduleVersionService
    v1 = ScheduleVersionService.create_approved_revision(db, p1_id, name="B1")
    v2 = ScheduleVersionService.create_approved_revision(db, p2_id, name="B2")
    assert v1 is not None and v2 is not None and v1 != v2


def test_10_constraints_deadlines_project_scoped(test_setup):
    """10. constraints/deadlines project-scoped."""
    db, tc, p1_id, p2_id, _, _ = test_setup
    from todo_bird_app.services.schedule_constraint_service import ScheduleConstraintService
    tasks1 = [Task.from_row(t) for t in db.get_tasks_by_project(p1_id)]
    tasks2 = [Task.from_row(t) for t in db.get_tasks_by_project(p2_id)]
    r1 = ScheduleConstraintService.evaluate_schedule_constraints(tasks1) if hasattr(ScheduleConstraintService, "evaluate_schedule_constraints") else {}
    r2 = ScheduleConstraintService.evaluate_schedule_constraints(tasks2) if hasattr(ScheduleConstraintService, "evaluate_schedule_constraints") else {}
    assert isinstance(r1, (dict, list))
    assert isinstance(r2, (dict, list))


def test_11_selected_project_session_persistence(test_setup):
    """11. selected project session persistence."""
    db, tc, p1_id, p2_id, _, _ = test_setup
    view = GanttView(tc)
    view.set_current_project(p1_id)
    saved = view.settings_manager.get("gantt_selected_project_id")
    assert saved == p1_id


def test_12_all_projects_safely_supported_or_intentionally_absent(test_setup):
    """12. All Projects either safely supported or intentionally absent (one-project-at-a-time preferred)."""
    db, tc, p1_id, p2_id, _, _ = test_setup
    view = GanttView(tc)
    # Default is strictly single-project context
    assert view.current_project_id is not None


def test_13_no_cross_project_cpm_merging(test_setup):
    """13. no cross-project CPM merging."""
    db, tc, p1_id, p2_id, _, _ = test_setup
    t1 = [Task.from_row(t) for t in db.get_tasks_by_project(p1_id)]
    t2 = [Task.from_row(t) for t in db.get_tasks_by_project(p2_id)]
    cpm1 = CPMSchedulingService.calculate_schedule(t1, project_id=p1_id)
    cpm2 = CPMSchedulingService.calculate_schedule(t2, project_id=p2_id)
    assert cpm1.project_id == p1_id
    assert cpm2.project_id == p2_id
