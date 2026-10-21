import json

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QPushButton, QTreeWidget

from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.project import Project
from todo_bird_app.models.task import Task
from todo_bird_app.services.cpm_scheduling_service import DependencyType
from todo_bird_app.services.dependency_authoring_service import (
    DependencyAuthoringService,
    parse_authoring_dependency_specs,
    storage_dependency,
)
from todo_bird_app.services.gantt_wbs_adapter import GanttWBSAdapter
from todo_bird_app.services.wbs_cpm_adapter import calculate_wbs_cpm, cpm_node_for_key
from todo_bird_app.services.wbs_service import EntityRef, WBSService
from todo_bird_app.widgets.task_dialog import TaskDialog


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def dep_db(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "dependency_authoring.db"))
    with db.get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, color) VALUES (1, 'Interaction Project', '#2563EB')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, color) VALUES (2, 'External Project', '#DC2626')"
        )
        conn.commit()
    return db


def _project():
    return Project(id=1, name="Interaction Project", color="#2563EB")


def _insert_task(db, title, project_id=1, **overrides):
    task = Task(
        title=title,
        project_id=project_id,
        planned_date=overrides.pop("planned_date", "2026-09-01"),
        planned_start_time=overrides.pop("planned_start_time", "09:00"),
        estimated_duration=overrides.pop("estimated_duration", 1440),
        show_in_gantt=overrides.pop("show_in_gantt", True),
        **overrides,
    )
    return db.insert_task(task.to_dict())


def _insert_subtask(db, task_id, title, **overrides):
    return db.insert_subtask(
        task_id=task_id,
        title=title,
        planned_date=overrides.pop("planned_date", "2026-09-01"),
        planned_start_time=overrides.pop("planned_start_time", "09:00"),
        estimated_duration=overrides.pop("estimated_duration", 1440),
        show_in_gantt=overrides.pop("show_in_gantt", True),
        dependencies=overrides.pop("dependencies", []),
        parent_subtask_id=overrides.pop("parent_subtask_id", None),
        **overrides,
    )


def _fixture_ids(db):
    leaf_task = _insert_task(db, "Leaf Task")
    successor_task = _insert_task(db, "Successor Task")
    parent = _insert_task(db, "Foundation")
    excavation = _insert_subtask(db, parent, "Excavation Final")
    reinforcement = _insert_subtask(db, parent, "Reinforcement Final")
    nested = _insert_subtask(db, parent, "Nested Detail", parent_subtask_id=excavation)
    external = _insert_task(db, "External", project_id=2)
    return {
        "leaf_task": leaf_task,
        "successor_task": successor_task,
        "parent": parent,
        "excavation": excavation,
        "reinforcement": reinforcement,
        "nested": nested,
        "external": external,
    }


def _task_dialog(db, task_id):
    return TaskDialog(
        projects=[_project()],
        task=Task.from_row(db.get_task_by_id(task_id)),
        db_manager=db,
    )


def _item_by_key(tree: QTreeWidget, key_text: str):
    for index in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(index)
        if item.data(0, Qt.UserRole + 3) == key_text:
            return item
    return None


def _checked_key_texts(tree: QTreeWidget):
    return [
        tree.topLevelItem(index).data(0, Qt.UserRole + 3)
        for index in range(tree.topLevelItemCount())
        if tree.topLevelItem(index).checkState(0) == Qt.Checked
    ]


EDGE_CASES = [
    (pred_kind, succ_kind, dep_type, lag)
    for pred_kind in ("task", "subtask")
    for succ_kind in ("task", "subtask")
    for dep_type in ("FS", "SS", "FF", "SF")
    for lag in (-1440, 0, 120)
]


@pytest.mark.parametrize("pred_kind,succ_kind,dep_type,lag", EDGE_CASES)
def test_typed_dependency_authoring_service_accepts_leaf_edges(
    dep_db, pred_kind, succ_kind, dep_type, lag
):
    ids = _fixture_ids(dep_db)
    pred_key = (
        EntityRef.task(ids["leaf_task"])
        if pred_kind == "task"
        else EntityRef.subtask(ids["nested"])
    )
    succ_key = (
        EntityRef.task(ids["successor_task"])
        if succ_kind == "task"
        else EntityRef.subtask(ids["reinforcement"])
    )
    raw = [storage_dependency(pred_key, dep_type, lag, typed=True)]

    result = DependencyAuthoringService.validate_dependencies(
        dep_db,
        successor_key=succ_key,
        raw_dependencies=raw,
        project_id=1,
    )

    assert result.valid is True
    assert result.normalized_dependencies[0].predecessor_key == pred_key
    assert result.normalized_dependencies[0].dependency_type == DependencyType(dep_type)
    assert result.normalized_dependencies[0].lag_minutes == lag


def test_dependency_candidates_include_subtask_leaf_with_parent_context(dep_db):
    ids = _fixture_ids(dep_db)
    candidates = DependencyAuthoringService.build_candidates(
        dep_db,
        project_id=1,
        successor_key=EntityRef.subtask(ids["reinforcement"]),
    )
    by_key = {candidate.key: candidate for candidate in candidates}

    assert EntityRef.subtask(ids["excavation"]) not in by_key
    assert EntityRef.subtask(ids["nested"]) in by_key
    assert "Foundation > Excavation Final > Nested Detail" in by_key[
        EntityRef.subtask(ids["nested"])
    ].display_title


def test_dependency_candidates_exclude_summary_parent_and_self(dep_db):
    ids = _fixture_ids(dep_db)
    candidates = DependencyAuthoringService.build_candidates(
        dep_db,
        project_id=1,
        successor_key=EntityRef.subtask(ids["reinforcement"]),
    )
    keys = {candidate.key for candidate in candidates}

    assert EntityRef.task(ids["parent"]) not in keys
    assert EntityRef.subtask(ids["reinforcement"]) not in keys


def test_dependency_candidates_exclude_cross_project_rows(dep_db):
    ids = _fixture_ids(dep_db)
    candidates = DependencyAuthoringService.build_candidates(
        dep_db,
        project_id=1,
        successor_key=EntityRef.task(ids["successor_task"]),
    )
    assert EntityRef.task(ids["external"]) not in {candidate.key for candidate in candidates}


def test_dependency_candidates_exclude_completed_subtasks(dep_db):
    parent = _insert_task(dep_db, "Foundation")
    done = _insert_subtask(dep_db, parent, "Done", is_completed=True)
    todo = _insert_subtask(dep_db, parent, "Todo")
    candidates = DependencyAuthoringService.build_candidates(
        dep_db,
        project_id=1,
        successor_key=EntityRef.subtask(todo),
    )

    assert EntityRef.subtask(done) not in {candidate.key for candidate in candidates}


def test_dependency_validation_rejects_self_dependency(dep_db):
    ids = _fixture_ids(dep_db)
    key = EntityRef.subtask(ids["reinforcement"])
    result = DependencyAuthoringService.validate_dependencies(
        dep_db,
        successor_key=key,
        raw_dependencies=[storage_dependency(key, "FS", 0, typed=True)],
        project_id=1,
    )

    assert result.valid is False
    assert result.error_code == "SELF_REFERENCE"


def test_dependency_validation_rejects_duplicate_dependency(dep_db):
    ids = _fixture_ids(dep_db)
    pred_key = EntityRef.task(ids["leaf_task"])
    result = DependencyAuthoringService.validate_dependencies(
        dep_db,
        successor_key=EntityRef.task(ids["successor_task"]),
        raw_dependencies=[
            storage_dependency(pred_key, "FS", 0, typed=True),
            storage_dependency(pred_key, "SS", 60, typed=True),
        ],
        project_id=1,
    )

    assert result.valid is False
    assert result.error_code == "DUPLICATE_DEPENDENCY"


def test_dependency_validation_rejects_cross_project_dependency(dep_db):
    ids = _fixture_ids(dep_db)
    result = DependencyAuthoringService.validate_dependencies(
        dep_db,
        successor_key=EntityRef.task(ids["successor_task"]),
        raw_dependencies=[
            storage_dependency(EntityRef.task(ids["external"]), "FS", 0, typed=True)
        ],
        project_id=1,
    )

    assert result.valid is False
    assert result.error_code == "CROSS_PROJECT_DEPENDENCY"


def test_dependency_validation_rejects_cycle_across_subtasks(dep_db):
    ids = _fixture_ids(dep_db)
    dep_db.update_subtask(
        subtask_id=ids["nested"],
        title="Nested Detail",
        is_completed=False,
        dependencies=[
            storage_dependency(EntityRef.subtask(ids["reinforcement"]), "FS", 0, typed=True)
        ],
    )

    result = DependencyAuthoringService.validate_dependencies(
        dep_db,
        successor_key=EntityRef.subtask(ids["reinforcement"]),
        raw_dependencies=[
            storage_dependency(EntityRef.subtask(ids["nested"]), "FS", 0, typed=True)
        ],
        project_id=1,
    )

    assert result.valid is False
    assert result.error_code == "DEPENDENCY_CYCLE"


def test_task_dialog_main_task_lists_subtask_predecessor_candidates(qapp, dep_db):
    ids = _fixture_ids(dep_db)
    dialog = _task_dialog(dep_db, ids["successor_task"])

    combo_values = [
        dialog.dependency_predecessor_combo.itemData(i)
        for i in range(dialog.dependency_predecessor_combo.count())
    ]

    assert f"task:{ids['leaf_task']}" in combo_values
    assert f"subtask:{ids['nested']}" in combo_values
    assert f"task:{ids['parent']}" not in combo_values


def test_task_dialog_add_button_checks_typed_subtask_dependency(qapp, dep_db):
    ids = _fixture_ids(dep_db)
    dialog = _task_dialog(dep_db, ids["successor_task"])
    target_key = f"subtask:{ids['nested']}"

    idx = dialog.dependency_predecessor_combo.findData(target_key)
    dialog.dependency_predecessor_combo.setCurrentIndex(idx)
    dialog.dependency_type_combo.setCurrentIndex(dialog.dependency_type_combo.findData("SS"))
    dialog.dependency_lag_edit.setText("+2h")
    QTest.mouseClick(dialog.dependency_add_button, Qt.LeftButton)

    item = _item_by_key(dialog.dependency_tree, target_key)
    assert item is not None
    assert item.checkState(0) == Qt.Checked
    assert target_key in _checked_key_texts(dialog.dependency_tree)


def test_task_dialog_save_preserves_typed_subtask_dependency(qapp, dep_db):
    ids = _fixture_ids(dep_db)
    dialog = _task_dialog(dep_db, ids["successor_task"])
    target_key = f"subtask:{ids['nested']}"

    dialog.dependency_predecessor_combo.setCurrentIndex(
        dialog.dependency_predecessor_combo.findData(target_key)
    )
    QTest.mouseClick(dialog.dependency_add_button, Qt.LeftButton)
    dialog.on_save()

    assert dialog.result() == TaskDialog.Accepted
    assert dialog.task.dependencies[0]["predecessor_key"] == target_key
    assert dialog.task.dependencies[0]["predecessor_entity_type"] == "subtask"


def test_task_controller_accepts_typed_task_to_subtask_dependency(qapp, dep_db):
    ids = _fixture_ids(dep_db)
    controller = TaskController(dep_db)
    task = Task.from_row(dep_db.get_task_by_id(ids["successor_task"]))
    task.dependencies = [
        storage_dependency(EntityRef.subtask(ids["nested"]), "FS", 0, typed=True)
    ]

    assert controller.update_task(task) is True
    reloaded = Task.from_row(dep_db.get_task_by_id(ids["successor_task"]))
    assert json.loads(reloaded.to_dict()["dependencies"])[0]["predecessor_key"] == f"subtask:{ids['nested']}"


def test_subtask_dialog_can_add_and_persist_subtask_dependency(qapp, dep_db):
    ids = _fixture_ids(dep_db)
    dialog = _task_dialog(dep_db, ids["parent"])
    target_item = None
    for row in range(dialog.subtask_tree.topLevelItemCount()):
        item = dialog.subtask_tree.topLevelItem(row)
        if item.data(0, Qt.UserRole) == ids["reinforcement"]:
            target_item = item
            break
    dialog.subtask_tree.setCurrentItem(target_item)

    def drive_modal():
        modal = QApplication.activeModalWidget()
        tree = modal.findChild(QTreeWidget, "subtask_dependency_tree")
        combo = modal.findChild(QComboBox, "subtask_dependency_predecessor_combo")
        dep_type = modal.findChild(QComboBox, "subtask_dependency_type_combo")
        lag = modal.findChild(QLineEdit, "subtask_dependency_lag_edit")
        add_button = modal.findChild(QPushButton, "subtask_dependency_add_button")
        save_button = next(
            button
            for button in modal.findChildren(QPushButton)
            if "Save Details" in button.text()
        )
        combo.setCurrentIndex(combo.findData(f"subtask:{ids['nested']}"))
        dep_type.setCurrentIndex(dep_type.findData("FS"))
        lag.setText("0m")
        QTest.mouseClick(add_button, Qt.LeftButton)
        assert _item_by_key(tree, f"subtask:{ids['nested']}").checkState(0) == Qt.Checked
        QTest.mouseClick(save_button, Qt.LeftButton)

    QTimer.singleShot(0, drive_modal)
    dialog.edit_selected_subtask_details()
    dialog.on_save()

    rows = {
        row["id"]: row
        for row in dep_db.get_all_subtasks_flat(ids["parent"])
    }
    saved = json.loads(rows[ids["reinforcement"]]["dependencies"])
    assert saved[0]["predecessor_key"] == f"subtask:{ids['nested']}"
    assert saved[0]["type"] == "FS"


def test_typed_subtask_dependency_recomputes_wbs_cpm(dep_db):
    ids = _fixture_ids(dep_db)
    dep_db.update_subtask(
        subtask_id=ids["reinforcement"],
        title="Reinforcement Final",
        is_completed=False,
        planned_date="2026-09-01",
        planned_start_time="09:00",
        estimated_duration=1440,
        show_in_gantt=True,
        dependencies=[
            storage_dependency(EntityRef.subtask(ids["nested"]), "FS", 0, typed=True)
        ],
    )
    dep_db.update_subtask(
        subtask_id=ids["nested"],
        title="Nested Detail",
        is_completed=False,
        planned_date="2026-09-01",
        planned_start_time="09:00",
        estimated_duration=1440,
        show_in_gantt=True,
    )
    snapshot = WBSService.build_project_hierarchy(dep_db, project_id=1)

    result = calculate_wbs_cpm(snapshot, dep_db)
    nested_node = cpm_node_for_key(result, EntityRef.subtask(ids["nested"]))
    reinf_node = cpm_node_for_key(result, EntityRef.subtask(ids["reinforcement"]))

    assert nested_node is not None
    assert reinf_node is not None
    assert reinf_node.earliest_start == nested_node.earliest_finish


def test_gantt_rows_receive_dependency_authoring_refresh_data(dep_db):
    ids = _fixture_ids(dep_db)
    dep_db.update_subtask(
        subtask_id=ids["reinforcement"],
        title="Reinforcement Final",
        is_completed=False,
        planned_date="2026-09-01",
        planned_start_time="09:00",
        estimated_duration=1440,
        show_in_gantt=True,
        dependencies=[
            storage_dependency(EntityRef.subtask(ids["nested"]), "FS", 0, typed=True)
        ],
    )

    snapshot = WBSService.build_project_hierarchy(dep_db, project_id=1)
    rows = GanttWBSAdapter.build_project_rows(snapshot, dep_db)
    row_by_key = {str(row.key): row for row in rows}

    assert row_by_key[f"subtask:{ids['reinforcement']}"].cpm_analysis_status == "analyzed"
    assert "predecessor" in row_by_key[f"subtask:{ids['reinforcement']}"].dependency_summary


def test_remove_selected_dependency_unchecks_row(qapp, dep_db):
    ids = _fixture_ids(dep_db)
    dialog = _task_dialog(dep_db, ids["successor_task"])
    target_key = f"task:{ids['leaf_task']}"
    dialog.dependency_predecessor_combo.setCurrentIndex(
        dialog.dependency_predecessor_combo.findData(target_key)
    )
    QTest.mouseClick(dialog.dependency_add_button, Qt.LeftButton)
    item = _item_by_key(dialog.dependency_tree, target_key)
    dialog.dependency_tree.setCurrentItem(item)
    QTest.mouseClick(dialog.dependency_remove_button, Qt.LeftButton)

    assert item.checkState(0) == Qt.Unchecked


def test_invalid_lag_shows_inline_feedback_in_add_row(qapp, dep_db):
    ids = _fixture_ids(dep_db)
    dialog = _task_dialog(dep_db, ids["successor_task"])
    dialog.dependency_lag_edit.setText("not-a-duration")

    QTest.mouseClick(dialog.dependency_add_button, Qt.LeftButton)

    assert "lag/lead" in dialog.dependency_status_label.text()


def test_parse_authoring_dependencies_preserves_task_legacy_identity(dep_db):
    ids = _fixture_ids(dep_db)
    specs = parse_authoring_dependency_specs(
        [{"predecessor_id": ids["leaf_task"], "type": "FS", "lag_minutes": 0}],
        fallback_entity_type="task",
    )

    assert specs[0].predecessor_key == EntityRef.task(ids["leaf_task"])


def test_parse_authoring_dependencies_preserves_explicit_subtask_identity(dep_db):
    ids = _fixture_ids(dep_db)
    specs = parse_authoring_dependency_specs(
        [
            {
                "predecessor_id": ids["nested"],
                "predecessor_entity_type": "subtask",
                "type": "FF",
                "lag_minutes": -60,
            }
        ],
        fallback_entity_type="task",
    )

    assert specs[0].predecessor_key == EntityRef.subtask(ids["nested"])
    assert specs[0].dependency_type == DependencyType.FF
    assert specs[0].lag_minutes == -60
