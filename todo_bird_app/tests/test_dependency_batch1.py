import json
from pathlib import Path

import pytest

from todo_bird_app.database import DatabaseManager
from todo_bird_app.gantt.gantt_dependency_engine import GanttDependencyEngine
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task, TaskPriority, TaskCategory, TaskStatus


def _make_task(task_id, title="Task", dependencies=None, project_id=1):
    return Task(
        id=task_id,
        title=title,
        project_id=project_id,
        priority=TaskPriority.MEDIUM,
        category=TaskCategory.WORK,
        planned_date="2026-08-10",
        due_date="2026-08-10",
        estimated_duration=60,
        progress=0,
        status=TaskStatus.PLANNED,
        dependencies=list(dependencies or []),
    )


def test_d00_existing_prod_db_can_be_read_without_mutation(tmp_path):
    db_path = tmp_path / "read_only.db"
    db = DatabaseManager(str(db_path))
    rows = db.get_all_tasks()
    assert isinstance(rows, list)
    assert db.get_connection() is not None


def test_d01_valid_direct_dependency_is_accepted():
    task_a = _make_task(1, "A")
    task_b = _make_task(2, "B", dependencies=[1])
    result = GanttDependencyEngine.validate_proposed_dependencies(
        task_id=task_b.id,
        candidate_ids=task_b.dependencies,
        tasks=[task_a, task_b],
    )
    assert result["valid"] is True
    assert result["normalized_dependencies"] == [1]
    assert result["missing_ids"] == []
    assert result["cycle_nodes"] == []


def test_d02_self_dependency_is_rejected():
    task = _make_task(4, "A")
    result = GanttDependencyEngine.validate_proposed_dependencies(
        task_id=task.id,
        candidate_ids=[task.id],
        tasks=[task],
    )
    assert result["valid"] is False
    assert result["self_reference"] is True
    assert "self" in result["message"].lower()


def test_d03_two_node_cycle_is_rejected():
    task_a = _make_task(1, "A", dependencies=[2])
    task_b = _make_task(2, "B", dependencies=[1])
    result = GanttDependencyEngine.validate_proposed_dependencies(
        task_id=2,
        candidate_ids=[1],
        tasks=[task_a, task_b],
    )
    assert result["valid"] is False
    assert set(result["cycle_nodes"]) == {1, 2}
    assert "circular dependency" in result["message"].lower()


def test_d04_three_node_cycle_is_rejected():
    task_a = _make_task(1, "A", dependencies=[3])
    task_b = _make_task(2, "B", dependencies=[1])
    task_c = _make_task(3, "C", dependencies=[2])
    result = GanttDependencyEngine.validate_proposed_dependencies(
        task_id=3,
        candidate_ids=[2],
        tasks=[task_a, task_b, task_c],
    )
    assert result["valid"] is False
    assert set(result["cycle_nodes"]) == {1, 2, 3}


def test_d05_duplicate_dependencies_normalize_safely():
    result = GanttDependencyEngine.validate_proposed_dependencies(
        task_id=10,
        candidate_ids=[2, 2, 2, 3],
        tasks=[_make_task(2, "A"), _make_task(3, "B"), _make_task(10, "C")],
    )
    assert result["normalized_dependencies"] == [2, 3]
    assert result["valid"] is True


def test_d06_missing_dependency_id_is_detected():
    result = GanttDependencyEngine.validate_proposed_dependencies(
        task_id=10,
        candidate_ids=[999999],
        tasks=[_make_task(10, "C")],
    )
    assert result["valid"] is False
    assert result["missing_ids"] == [999999]
    assert "no longer exists" in result["message"].lower()


def test_d07_legacy_cycle_detection_is_read_only():
    task_a = _make_task(7, "A", dependencies=[8])
    task_b = _make_task(8, "B", dependencies=[7])
    cycle_nodes = GanttDependencyEngine.find_cycle_nodes(
        {task.id: task for task in [task_a, task_b]},
        {task.id: set(task.dependencies) for task in [task_a, task_b]},
    )
    assert set(cycle_nodes) == {7, 8}
    assert task_a.dependencies == [8]
    assert task_b.dependencies == [7]


def test_d08_cycle_safe_auto_shift_analysis_never_mutates_cycle_members():
    task_a = _make_task(7, "A", dependencies=[8])
    task_b = _make_task(8, "B", dependencies=[7])
    legacy = GanttDependencyEngine.legacy_dependency_issues([task_a, task_b])
    assert legacy[0]["task_id"] == 7
    assert task_a.dependencies == [8]
    assert task_b.dependencies == [7]


def test_d09_critical_path_analysis_does_not_crash_on_legacy_cycle():
    task_a = _make_task(7, "A", dependencies=[8])
    task_b = _make_task(8, "B", dependencies=[7])
    result = GanttDependencyEngine.annotate([task_a, task_b])
    assert "cycle_nodes" in result
    assert set(result["cycle_nodes"]) == {7, 8}


def test_t01_task_id_stable_after_update(tmp_path):
    db = DatabaseManager(str(tmp_path / "task_update.db"))
    ctrl = TaskController(db)
    task = _make_task(200, "Keep id")
    task_id = ctrl.add_task(task)
    fresh = ctrl.get_task(task_id)
    assert fresh.id == task_id

    fresh.title = "Updated title"
    assert ctrl.update_task(fresh) is True
    reloaded = ctrl.get_task(task_id)
    assert reloaded.id == task_id
    assert reloaded.title == "Updated title"


def test_t02_title_edit_does_not_change_dependencies(tmp_path):
    db = DatabaseManager(str(tmp_path / "title_dep.db"))
    ctrl = TaskController(db)
    task = _make_task(10, "Base", dependencies=[11])
    dep = _make_task(11, "Dep")
    ctrl.add_task(dep)
    ctrl.add_task(task)

    task.title = "Renamed"
    assert ctrl.update_task(task) is True
    reloaded = ctrl.get_task(task.id)
    assert reloaded.title == "Renamed"
    assert reloaded.dependencies == [11]


def test_t03_schedule_edit_does_not_change_dependency_list(tmp_path):
    db = DatabaseManager(str(tmp_path / "schedule.db"))
    ctrl = TaskController(db)
    task = _make_task(20, "Schedule", dependencies=[21])
    dep = _make_task(21, "Dep")
    ctrl.add_task(dep)
    ctrl.add_task(task)

    task.planned_date = "2026-08-12"
    task.due_date = "2026-08-14"
    task.estimated_duration = 180
    assert ctrl.update_task(task) is True
    reloaded = ctrl.get_task(task.id)
    assert reloaded.dependencies == [21]
    assert reloaded.planned_date == "2026-08-12"
    assert reloaded.due_date == "2026-08-14"


def test_t04_dependency_edit_does_not_alter_timing_fields(tmp_path):
    db = DatabaseManager(str(tmp_path / "dep_timing.db"))
    ctrl = TaskController(db)
    dep_a = _make_task(30, "A")
    dep_b = _make_task(31, "B")
    task = _make_task(32, "Task", dependencies=[30], project_id=1)
    ctrl.add_task(dep_a)
    ctrl.add_task(dep_b)
    ctrl.add_task(task)

    task.dependencies = [31]
    task.planned_date = "2026-08-22"
    task.due_date = "2026-08-23"
    task.estimated_duration = 90
    assert ctrl.update_task(task) is True
    reloaded = ctrl.get_task(task.id)
    assert reloaded.dependencies == [31]
    assert reloaded.planned_date == "2026-08-22"
    assert reloaded.due_date == "2026-08-23"
    assert reloaded.estimated_duration == 90


def test_t05_progress_remains_0_to_100(tmp_path):
    db = DatabaseManager(str(tmp_path / "progress.db"))
    ctrl = TaskController(db)
    task = _make_task(40, "Progress")
    task.progress = 150
    assert ctrl.add_task(task) > 0
    reloaded = ctrl.get_task(task.id)
    assert 0 <= reloaded.progress <= 100


def test_t06_planned_date_leq_due_date_is_deterministic(tmp_path):
    db = DatabaseManager(str(tmp_path / "dates.db"))
    ctrl = TaskController(db)
    task = _make_task(50, "Date check")
    task.planned_date = "2026-08-15"
    task.due_date = "2026-08-14"
    assert ctrl.add_task(task) > 0
    reloaded = ctrl.get_task(task.id)
    assert reloaded.planned_date == "2026-08-15"
    assert reloaded.due_date == "2026-08-14"


def test_t07_completed_task_persistence_remains_valid(tmp_path):
    db = DatabaseManager(str(tmp_path / "completed.db"))
    ctrl = TaskController(db)
    task = _make_task(60, "Complete")
    task.status = TaskStatus.COMPLETED
    task.progress = 100
    assert ctrl.add_task(task) > 0
    saved = ctrl.get_task(task.id)
    assert saved.status == TaskStatus.COMPLETED
    assert saved.progress == 100


def test_t08_cancelled_task_remains_persisted_and_retrievable(tmp_path):
    db = DatabaseManager(str(tmp_path / "cancelled.db"))
    ctrl = TaskController(db)
    task = _make_task(70, "Cancelled")
    task.status = TaskStatus.CANCELLED
    assert ctrl.add_task(task) > 0
    saved = ctrl.get_task(task.id)
    assert saved.status == TaskStatus.CANCELLED


def test_t09_nested_subtasks_untouched_when_editing_main_task_dependencies(tmp_path):
    db = DatabaseManager(str(tmp_path / "subtasks.db"))
    ctrl = TaskController(db)
    task = _make_task(80, "Parent", dependencies=[81])
    task_id = ctrl.add_task(task)
    db.insert_subtask(task_id, "Child", parent_subtask_id=None, position=0)
    assert db.get_subtasks(task_id)

    task.dependencies = [81]
    assert ctrl.update_task(task) is True
    assert len(db.get_subtasks(task_id)) == 1


def test_x00_views_begin_from_same_database_truth(tmp_path):
    db = DatabaseManager(str(tmp_path / "cross_view.db"))
    ctrl = TaskController(db)
    task = _make_task(90, "Shared Task", dependencies=[91])
    dep = _make_task(91, "Shared Dependency")
    ctrl.add_task(dep)
    task_id = ctrl.add_task(task)

    by_id = ctrl.get_task(task_id)
    assert by_id is not None
    assert by_id.dependencies == [91]
    rows = db.get_all_tasks()
    row_map = {row["id"]: row for row in rows}
    assert row_map[task_id]["title"] == "Shared Task"
    assert json.loads(row_map[task_id]["dependencies"]) == [91]
