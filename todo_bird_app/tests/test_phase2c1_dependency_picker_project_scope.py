import pytest
from PySide6.QtWidgets import QApplication, QTreeWidget, QComboBox, QLineEdit
from PySide6.QtCore import Qt

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.models.project import Project
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.gantt.gantt_dependency_engine import GanttDependencyEngine
from todo_bird_app.services.cpm_scheduling_service import (
    CPMSchedulingService,
    DiagnosticCode,
    DependencySpec,
    DependencyType,
    parse_dependency_specs,
)
from todo_bird_app.widgets.task_dialog import TaskDialog


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_p2c1.db")
    db = DatabaseManager(db_file)
    
    # Project 1: THAAVORIX (id=1)
    db.insert_project({"name": "THAAVORIX", "color": "#3B82F6", "icon": "", "description": "", "is_archived": 0})
    # Project 2: External Project (id=2)
    db.insert_project({"name": "Other Project", "color": "#10B981", "icon": "", "description": "", "is_archived": 0})

    return db


def test_01_dependency_picker_only_lists_same_project_tasks(app, test_db):
    """1. Dependency picker only lists tasks belonging to the same project."""
    # Tasks in Project 1
    t1_id = test_db.insert_task(Task(title="Start", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())
    t2_id = test_db.insert_task(Task(title="Planning", project_id=1, planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60).to_dict())
    
    # Task in Project 2
    t_ext_id = test_db.insert_task(Task(title="External Task", project_id=2, planned_date="2026-09-01", planned_start_time="10:00", estimated_duration=60).to_dict())

    target_task = Task.from_row(test_db.get_task_by_id(t1_id))
    dialog = TaskDialog(projects=[], task=target_task, db_manager=test_db)

    tree = dialog.dependency_tree
    offered_ids = [tree.topLevelItem(i).data(0, Qt.UserRole) for i in range(tree.topLevelItemCount())]

    assert t2_id in offered_ids
    assert t_ext_id not in offered_ids


def test_02_current_task_excluded(app, test_db):
    """2. The task currently being edited is excluded from its own dependency picker."""
    t1_id = test_db.insert_task(Task(title="Start", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())
    t2_id = test_db.insert_task(Task(title="Planning", project_id=1, planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60).to_dict())

    target_task = Task.from_row(test_db.get_task_by_id(t1_id))
    dialog = TaskDialog(projects=[], task=target_task, db_manager=test_db)

    tree = dialog.dependency_tree
    offered_ids = [tree.topLevelItem(i).data(0, Qt.UserRole) for i in range(tree.topLevelItemCount())]

    assert t1_id not in offered_ids
    assert t2_id in offered_ids


def test_03_identical_title_in_another_project_not_visible(app, test_db):
    """3. An identically-named task in another project is not shown in the picker."""
    # Project 1: Success
    t_p1_id = test_db.insert_task(Task(title="Success", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())
    # Project 2: Success
    t_p2_id = test_db.insert_task(Task(title="Success", project_id=2, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())
    # Target task in Project 1: Start
    t_start_id = test_db.insert_task(Task(title="Start", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())

    target_task = Task.from_row(test_db.get_task_by_id(t_start_id))
    dialog = TaskDialog(projects=[], task=target_task, db_manager=test_db)

    tree = dialog.dependency_tree
    offered_ids = [tree.topLevelItem(i).data(0, Qt.UserRole) for i in range(tree.topLevelItemCount())]

    assert t_p1_id in offered_ids
    assert t_p2_id not in offered_ids


def test_04_identical_title_in_same_project_distinguishable(app, test_db):
    """4. Multiple tasks with identical titles in the same project display ID disambiguation."""
    t1_id = test_db.insert_task(Task(title="Review", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())
    t2_id = test_db.insert_task(Task(title="Review", project_id=1, planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60).to_dict())
    t3_id = test_db.insert_task(Task(title="Execute", project_id=1, planned_date="2026-09-01", planned_start_time="10:00", estimated_duration=60).to_dict())

    target_task = Task.from_row(test_db.get_task_by_id(t3_id))
    dialog = TaskDialog(projects=[], task=target_task, db_manager=test_db)

    tree = dialog.dependency_tree
    item_texts = [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]

    # Duplicate titles should display with ID disambiguation
    assert f"Review — #{t1_id}" in item_texts
    assert f"Review — #{t2_id}" in item_texts


def test_05_unprojected_task_behavior_deterministic(app, test_db):
    """5. Unprojected tasks (project_id=None) only offer other unprojected tasks."""
    t_un1 = test_db.insert_task(Task(title="Unproj 1", project_id=None, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())
    t_un2 = test_db.insert_task(Task(title="Unproj 2", project_id=None, planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60).to_dict())
    t_proj = test_db.insert_task(Task(title="Project Task", project_id=1, planned_date="2026-09-01", planned_start_time="10:00", estimated_duration=60).to_dict())

    target_task = Task.from_row(test_db.get_task_by_id(t_un1))
    dialog = TaskDialog(projects=[], task=target_task, db_manager=test_db)

    tree = dialog.dependency_tree
    offered_ids = [tree.topLevelItem(i).data(0, Qt.UserRole) for i in range(tree.topLevelItemCount())]

    assert t_un2 in offered_ids
    assert t_proj not in offered_ids


def test_06_ui_cannot_create_cross_project_dependency(app, test_db):
    """6. UI TaskDialog does not present cross-project candidates to select."""
    t_p1 = test_db.insert_task(Task(title="Start", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())
    t_p2 = test_db.insert_task(Task(title="Other Project Task", project_id=2, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())

    target_task = Task.from_row(test_db.get_task_by_id(t_p1))
    dialog = TaskDialog(projects=[], task=target_task, db_manager=test_db)

    tree = dialog.dependency_tree
    items = [tree.topLevelItem(i) for i in range(tree.topLevelItemCount())]
    assert not any(item.data(0, Qt.UserRole) == t_p2 for item in items)


def test_07_controller_service_rejects_cross_project_dependency(test_db):
    """7. TaskController rejects cross-project dependency update."""
    ctrl = TaskController(test_db)
    t_p1 = test_db.insert_task(Task(title="Start", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())
    t_p2 = test_db.insert_task(Task(title="Other Task", project_id=2, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())

    updated = Task.from_row(test_db.get_task_by_id(t_p1))
    updated.dependencies = [{"predecessor_id": t_p2, "type": "FS", "lag_minutes": 0}]

    ok = ctrl.update_task(updated)
    assert ok is False


def test_08_validation_returns_cross_project_dependency(test_db):
    """8. GanttDependencyEngine returns error_code CROSS_PROJECT_DEPENDENCY."""
    all_tasks = [
        Task(id=1, title="Task 1", project_id=1),
        Task(id=2, title="Task 2", project_id=2),
    ]
    res = GanttDependencyEngine.validate_proposed_dependencies(
        task_id=1,
        candidate_ids=[{"predecessor_id": 2, "type": "FS", "lag_minutes": 0}],
        tasks=all_tasks,
    )
    assert res["valid"] is False
    assert res.get("error_code") == "CROSS_PROJECT_DEPENDENCY"
    assert "same project" in res["message"]


def test_09_failed_cross_project_validation_causes_zero_db_mutation(test_db):
    """9. Rejected cross-project update leaves the database unmutated."""
    ctrl = TaskController(test_db)
    t_p1 = test_db.insert_task(Task(title="Start", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60, dependencies=[]).to_dict())
    t_p2 = test_db.insert_task(Task(title="Other Task", project_id=2, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())

    updated = Task.from_row(test_db.get_task_by_id(t_p1))
    updated.dependencies = [{"predecessor_id": t_p2, "type": "FS", "lag_minutes": 0}]
    ctrl.update_task(updated)

    persisted = Task.from_row(test_db.get_task_by_id(t_p1))
    assert parse_dependency_specs(persisted.dependencies) == []


def test_10_legacy_cross_project_stored_edge_is_not_silently_deleted(app, test_db):
    """10. Existing cross-project edge is not wiped on opening TaskDialog."""
    # Pre-existing cross-project dependency stored in DB
    t_p2 = test_db.insert_task(Task(title="Legacy External", project_id=2, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())
    t_p1 = test_db.insert_task(Task(
        title="Start",
        project_id=1,
        planned_date="2026-09-01",
        planned_start_time="08:00",
        estimated_duration=60,
        dependencies=[{"predecessor_id": t_p2, "type": "FS", "lag_minutes": 0}]
    ).to_dict())

    target_task = Task.from_row(test_db.get_task_by_id(t_p1))
    dialog = TaskDialog(projects=[], task=target_task, db_manager=test_db)

    # Verify dialog task dependencies remain intact upon opening
    assert len(parse_dependency_specs(dialog.task.dependencies)) == 1
    assert parse_dependency_specs(dialog.task.dependencies)[0].predecessor_id == t_p2


def test_11_task_dialog_can_open_safely_with_legacy_external_edge(app, test_db):
    """11. TaskDialog opens safely and renders legacy external dependency with warning."""
    t_p2 = test_db.insert_task(Task(title="Legacy External", project_id=2, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())
    t_p1 = test_db.insert_task(Task(
        title="Start",
        project_id=1,
        planned_date="2026-09-01",
        planned_start_time="08:00",
        estimated_duration=60,
        dependencies=[{"predecessor_id": t_p2, "type": "FS", "lag_minutes": 0}]
    ).to_dict())

    target_task = Task.from_row(test_db.get_task_by_id(t_p1))
    dialog = TaskDialog(projects=[], task=target_task, db_manager=test_db)

    tree = dialog.dependency_tree
    assert tree.topLevelItemCount() == 1
    item = tree.topLevelItem(0)
    assert item.data(0, Qt.UserRole) == t_p2
    assert "External Project" in item.text(0)
    assert item.checkState(0) == Qt.Checked


def test_12_legacy_external_edge_receives_diagnostic_warning():
    """12. CPMSchedulingService diagnoses cross-project dependency."""
    t1 = Task(id=1, title="Task 1", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[{"predecessor_id": 2, "type": "FS", "lag_minutes": 0}])
    t2 = Task(id=2, title="Task 2", project_id=2, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60)

    res = CPMSchedulingService.calculate_schedule([t1, t2])
    n1 = res.get_node(1)
    assert DiagnosticCode.CROSS_PROJECT_DEPENDENCY in n1.diagnostic_codes


def test_13_normal_same_project_fs_saves(test_db):
    """13. Normal same-project FS dependency validates and saves."""
    ctrl = TaskController(test_db)
    t1 = test_db.insert_task(Task(title="A", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())
    t2 = test_db.insert_task(Task(title="B", project_id=1, planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60).to_dict())

    t2_obj = Task.from_row(test_db.get_task_by_id(t2))
    t2_obj.dependencies = [{"predecessor_id": t1, "type": "FS", "lag_minutes": 60}]
    ok = ctrl.update_task(t2_obj)
    assert ok is True

    persisted = Task.from_row(test_db.get_task_by_id(t2))
    specs = parse_dependency_specs(persisted.dependencies)
    assert len(specs) == 1
    assert specs[0].dependency_type == DependencyType.FS
    assert specs[0].lag_minutes == 60


def test_14_normal_same_project_ss_saves(test_db):
    """14. Normal same-project SS dependency validates and saves."""
    ctrl = TaskController(test_db)
    t1 = test_db.insert_task(Task(title="A", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())
    t2 = test_db.insert_task(Task(title="B", project_id=1, planned_date="2026-09-01", planned_start_time="08:30", estimated_duration=60).to_dict())

    t2_obj = Task.from_row(test_db.get_task_by_id(t2))
    t2_obj.dependencies = [{"predecessor_id": t1, "type": "SS", "lag_minutes": 30}]
    ok = ctrl.update_task(t2_obj)
    assert ok is True

    persisted = Task.from_row(test_db.get_task_by_id(t2))
    specs = parse_dependency_specs(persisted.dependencies)
    assert len(specs) == 1
    assert specs[0].dependency_type == DependencyType.SS
    assert specs[0].lag_minutes == 30


def test_15_normal_same_project_ff_saves(test_db):
    """15. Normal same-project FF dependency validates and saves."""
    ctrl = TaskController(test_db)
    t1 = test_db.insert_task(Task(title="A", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())
    t2 = test_db.insert_task(Task(title="B", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())

    t2_obj = Task.from_row(test_db.get_task_by_id(t2))
    t2_obj.dependencies = [{"predecessor_id": t1, "type": "FF", "lag_minutes": 120}]
    ok = ctrl.update_task(t2_obj)
    assert ok is True

    persisted = Task.from_row(test_db.get_task_by_id(t2))
    specs = parse_dependency_specs(persisted.dependencies)
    assert len(specs) == 1
    assert specs[0].dependency_type == DependencyType.FF
    assert specs[0].lag_minutes == 120


def test_16_normal_same_project_sf_saves(test_db):
    """16. Normal same-project SF dependency validates and saves."""
    ctrl = TaskController(test_db)
    t1 = test_db.insert_task(Task(title="A", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())
    t2 = test_db.insert_task(Task(title="B", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())

    t2_obj = Task.from_row(test_db.get_task_by_id(t2))
    t2_obj.dependencies = [{"predecessor_id": t1, "type": "SF", "lag_minutes": -30}]
    ok = ctrl.update_task(t2_obj)
    assert ok is True

    persisted = Task.from_row(test_db.get_task_by_id(t2))
    specs = parse_dependency_specs(persisted.dependencies)
    assert len(specs) == 1
    assert specs[0].dependency_type == DependencyType.SF
    assert specs[0].lag_minutes == -30


def test_17_same_project_cycle_still_rejected(test_db):
    """17. Cycles within the same project remain strictly rejected."""
    ctrl = TaskController(test_db)
    t1 = test_db.insert_task(Task(title="A", project_id=1, planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict())
    t2 = test_db.insert_task(Task(title="B", project_id=1, planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
                                  dependencies=[{"predecessor_id": t1, "type": "FS", "lag_minutes": 0}]).to_dict())

    # Attempt cycle: A depends on B
    t1_obj = Task.from_row(test_db.get_task_by_id(t1))
    t1_obj.dependencies = [{"predecessor_id": t2, "type": "FS", "lag_minutes": 0}]
    ok = ctrl.update_task(t1_obj)
    assert ok is False


def test_18_task12_to_task9_thaavorix_scenario_rejected():
    """18. Exact THAAVORIX 4-task network cycle is rejected when Task 12 is chosen for Task 9."""
    # Tasks 9, 10, 11, 12 in project 4
    tasks = [
        Task(id=9, title="Start", project_id=4, planned_date="2026-08-23", planned_start_time="04:00", estimated_duration=19020, dependencies=[]),
        Task(id=10, title="Planning", project_id=4, planned_date="2026-08-23", planned_start_time="00:00", estimated_duration=44640,
             dependencies=[{"predecessor_id": 9, "type": "FS", "lag_minutes": 1440}]),
        Task(id=11, title="Progress", project_id=4, planned_date="2026-08-24", planned_start_time="04:00", estimated_duration=15900,
             dependencies=[{"predecessor_id": 9, "type": "SS", "lag_minutes": 120}]),
        Task(id=12, title="Success", project_id=4, planned_date="2026-08-25", planned_start_time="00:00", estimated_duration=14400,
             dependencies=[
                 {"predecessor_id": 10, "type": "FF", "lag_minutes": 1440},
                 {"predecessor_id": 11, "type": "SF", "lag_minutes": -120},
             ]),
    ]

    # Propose candidate dependency: Task 9 depends on Task 12
    val = GanttDependencyEngine.validate_proposed_dependencies(
        task_id=9,
        candidate_ids=[{"predecessor_id": 12, "type": "FS", "lag_minutes": 0}],
        tasks=tasks,
    )
    assert val["valid"] is False
    assert 9 in val["cycle_nodes"]
    assert 12 in val["cycle_nodes"]
    assert "Circular dependency detected" in val["message"]
