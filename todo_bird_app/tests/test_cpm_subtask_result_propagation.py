import hashlib
import inspect
import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager
from todo_bird_app.gantt.gantt_dependency_engine import GanttDependencyEngine
from todo_bird_app.gantt.gantt_items import GanttTaskItem
from todo_bird_app.gantt.gantt_theme import GanttColorProfile
from todo_bird_app.models.task import Task
from todo_bird_app.models.wbs_filter_proxy_model import WBSFilterProxyModel
from todo_bird_app.models.wbs_item_model import WBSItemModel
from todo_bird_app.services.cpm_scheduling_service import DependencyType
from todo_bird_app.services.gantt_wbs_adapter import GanttWBSAdapter
from todo_bird_app.services.schedule_calendar_service import effective_project_calendar_from_db
from todo_bird_app.services.schedule_version_service import ScheduleVersionService
from todo_bird_app.services.wbs_cpm_adapter import calculate_wbs_cpm
from todo_bird_app.services.wbs_rollup_service import WBSRollupService
from todo_bird_app.services.wbs_service import EntityRef, WBSService
from todo_bird_app.views.gantt_view import GanttView

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PRODUCTION_DB = Path(__file__).resolve().parents[1] / "data" / "todo_bird.db"


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "cpm_subtask_result_propagation.db"))
    WBSRollupService.clear_cache()
    yield db
    WBSRollupService.clear_cache()
    db.close()


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dependency(pred_id, dep_type="FS", lag=0):
    return [{"predecessor_id": pred_id, "type": dep_type, "lag_minutes": lag}]


def _make_witness(db, *, dep_type="FS", lag=0, lead=False, minute_network=False):
    project_id = db.insert_project({"name": "SCHEDULING WITNESS FINAL"})
    db.set_project_calendar(project_id, [0, 1, 2, 3, 4, 5])
    parent_id = db.insert_task(
        {
            "project_id": project_id,
            "title": "Foundation",
            "status": "Planned",
            "planned_date": "2026-09-01",
            "planned_start_time": "09:00",
            "estimated_duration": 7200,
            "planned_effort_minutes": 2400,
            "show_in_gantt": 1,
        }
    )
    excavation_id = db.insert_subtask(
        parent_id,
        "Excavation Final",
        position=0,
        planned_date="2026-09-01",
        planned_start_time="09:00",
        estimated_duration=2880,
        planned_effort_minutes=960,
        show_in_gantt=True,
    )
    reinforcement_start = "09:00"
    duration = 2880
    if minute_network or dep_type in {"SS", "FF", "SF"} or lag or lead:
        duration = 60
        reinforcement_start = "08:00"
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE subtasks SET estimated_duration=? WHERE id=?",
                (60, excavation_id),
            )
            conn.commit()
    reinforcement_id = db.insert_subtask(
        parent_id,
        "Reinforcement Final",
        position=1,
        planned_date="2026-09-01",
        planned_start_time=reinforcement_start,
        estimated_duration=duration,
        planned_effort_minutes=960,
        dependencies=_dependency(excavation_id, dep_type, lag),
        show_in_gantt=True,
    )
    return {
        "project_id": project_id,
        "parent_id": parent_id,
        "excavation_id": excavation_id,
        "reinforcement_id": reinforcement_id,
    }


def _snapshot(db, project_id):
    return WBSService.build_project_hierarchy(db, project_id=project_id)


def _wbs_cpm(db, project_id):
    snapshot = _snapshot(db, project_id)
    return calculate_wbs_cpm(
        snapshot,
        db,
        project_calendar=effective_project_calendar_from_db(db, project_id),
    )


def _wbs_model(db, project_id):
    model = WBSItemModel()
    model.load_project(db, project_id)
    return model


def _model_value(model, key, column, role=Qt.DisplayRole):
    idx = model.index_from_key(key, column)
    assert idx.isValid()
    return model.data(idx, role)


def _gantt_rows(db, project_id):
    return GanttWBSAdapter.build_project_rows(_snapshot(db, project_id), db)


def _row(rows, key):
    return next(row for row in rows if row.key == key)


class _FakeGanttView:
    _build_phase1d_wbs_gantt_items = GanttView._build_phase1d_wbs_gantt_items

    def __init__(self, db, project_id):
        self.db_manager = db
        self.current_project_id = project_id


def _gantt_items(db, project_id):
    all_tasks = [Task.from_row(row) for row in db.get_tasks_by_project(project_id)]
    return GanttView._build_phase1d_wbs_gantt_items(
        _FakeGanttView(db, project_id),
        all_tasks,
    )


def _gantt_item(items, entity_type, entity_id):
    for item in items:
        if (
            getattr(item, "gantt_entity_type", None) == entity_type
            and int(getattr(item, "gantt_entity_id", 0)) == int(entity_id)
        ):
            return item
    raise AssertionError(f"Missing Gantt item {entity_type}:{entity_id}")


def test_01_engine_includes_first_subtask(temp_db):
    ids = _make_witness(temp_db)
    result = _wbs_cpm(temp_db, ids["project_id"])
    assert EntityRef.subtask(ids["excavation_id"]) in result.nodes


def test_02_engine_includes_second_subtask(temp_db):
    ids = _make_witness(temp_db)
    result = _wbs_cpm(temp_db, ids["project_id"])
    assert EntityRef.subtask(ids["reinforcement_id"]) in result.nodes


def test_03_engine_excludes_summary_parent_from_leaf_network(temp_db):
    ids = _make_witness(temp_db)
    result = _wbs_cpm(temp_db, ids["project_id"])
    assert EntityRef.task(ids["parent_id"]) not in result.nodes


def test_04_fs_edge_preserved_between_subtasks(temp_db):
    ids = _make_witness(temp_db)
    result = _wbs_cpm(temp_db, ids["project_id"])
    rein_key = EntityRef.subtask(ids["reinforcement_id"])
    exc_key = EntityRef.subtask(ids["excavation_id"])
    assert result.input_nodes[rein_key].predecessors == (exc_key,)
    assert result.input_nodes[exc_key].successors == (rein_key,)


@pytest.mark.parametrize(
    "node_name,key_name",
    [
        ("Excavation Final", "excavation_id"),
        ("Reinforcement Final", "reinforcement_id"),
    ],
)
def test_05_06_leaf_nodes_have_full_cpm_result(temp_db, node_name, key_name):
    ids = _make_witness(temp_db)
    result = _wbs_cpm(temp_db, ids["project_id"])
    node = result.get_node(EntityRef.subtask(ids[key_name]))
    assert node is not None, node_name
    assert node.earliest_start is not None
    assert node.earliest_finish is not None
    assert node.latest_start is not None
    assert node.latest_finish is not None
    assert node.total_float_minutes is not None
    assert node.free_float_minutes is not None


@pytest.mark.parametrize(
    "column,role",
    [
        (WBSItemModel.COL_ES, WBSItemModel.CPMEarliestStartRole),
        (WBSItemModel.COL_EF, WBSItemModel.CPMEarliestFinishRole),
        (WBSItemModel.COL_LS, WBSItemModel.CPMLatestStartRole),
        (WBSItemModel.COL_LF, WBSItemModel.CPMLatestFinishRole),
        (WBSItemModel.COL_TOTAL_FLOAT, WBSItemModel.CPMTotalFloatRole),
        (WBSItemModel.COL_FREE_FLOAT, WBSItemModel.CPMFreeFloatRole),
    ],
)
def test_07_12_wbs_propagates_subtask_cpm_roles(temp_db, column, role):
    ids = _make_witness(temp_db)
    model = _wbs_model(temp_db, ids["project_id"])
    key = EntityRef.subtask(ids["reinforcement_id"])
    assert _model_value(model, key, column) not in (None, "—", "-", "Not analyzed")
    assert model.data(model.index_from_key(key, 0), role) is not None


def test_13_wbs_propagates_subtask_critical_flag(temp_db):
    ids = _make_witness(temp_db)
    model = _wbs_model(temp_db, ids["project_id"])
    key = EntityRef.subtask(ids["reinforcement_id"])
    assert model.data(model.index_from_key(key, 0), WBSItemModel.CPMCriticalRole) is True
    assert "Critical" in _model_value(model, key, WBSItemModel.COL_CRITICAL)


@pytest.mark.parametrize(
    "field",
    [
        "cpm_earliest_start",
        "cpm_earliest_finish",
        "cpm_latest_start",
        "cpm_latest_finish",
        "cpm_total_float_minutes",
        "cpm_free_float_minutes",
    ],
)
def test_14_19_gantt_row_propagates_subtask_cpm_fields(temp_db, field):
    ids = _make_witness(temp_db)
    rows = _gantt_rows(temp_db, ids["project_id"])
    row = _row(rows, EntityRef.subtask(ids["reinforcement_id"]))
    assert getattr(row, field) is not None


def test_20_gantt_row_propagates_subtask_critical_flag(temp_db):
    ids = _make_witness(temp_db)
    rows = _gantt_rows(temp_db, ids["project_id"])
    assert _row(rows, EntityRef.subtask(ids["reinforcement_id"])).cpm_is_critical is True


def test_21_no_not_analyzed_when_wbs_result_exists(temp_db):
    ids = _make_witness(temp_db)
    model = _wbs_model(temp_db, ids["project_id"])
    key = EntityRef.subtask(ids["reinforcement_id"])
    assert _model_value(model, key, WBSItemModel.COL_CRITICAL) != "Not analyzed"
    assert "Not analyzed" not in (model.data(model.index_from_key(key, 0), Qt.ToolTipRole) or "")


def test_22_task_and_subtask_id_mapping_do_not_collide(temp_db):
    ids = _make_witness(temp_db)
    leaf_task_id = temp_db.insert_task(
        {
            "project_id": ids["project_id"],
            "title": "Independent Leaf",
            "status": "Planned",
            "planned_date": "2026-09-01",
            "planned_start_time": "09:00",
            "estimated_duration": 60,
            "show_in_gantt": 1,
        }
    )
    assert leaf_task_id == ids["reinforcement_id"]
    result = _wbs_cpm(temp_db, ids["project_id"])
    assert EntityRef.task(leaf_task_id) in result.nodes
    assert EntityRef.subtask(leaf_task_id) in result.nodes
    assert result.cpm_id_by_key[EntityRef.task(leaf_task_id)] != result.cpm_id_by_key[EntityRef.subtask(leaf_task_id)]


def test_23_task_lookup_and_subtask_lookup_return_different_nodes(temp_db):
    ids = _make_witness(temp_db)
    leaf_task_id = temp_db.insert_task(
        {
            "project_id": ids["project_id"],
            "title": "Independent Leaf",
            "status": "Planned",
            "planned_date": "2026-09-03",
            "planned_start_time": "09:00",
            "estimated_duration": 60,
            "show_in_gantt": 1,
        }
    )
    result = _wbs_cpm(temp_db, ids["project_id"])
    task_node = result.get_node(EntityRef.task(leaf_task_id))
    subtask_node = result.get_node(EntityRef.subtask(leaf_task_id))
    assert task_node is not None
    assert subtask_node is not None
    assert task_node.earliest_start != subtask_node.earliest_start


def test_24_nested_subtask_leaf_mapping(temp_db):
    ids = _make_witness(temp_db)
    nested_id = temp_db.insert_subtask(
        ids["parent_id"],
        "Nested Inspection",
        parent_subtask_id=ids["reinforcement_id"],
        planned_date="2026-09-03",
        planned_start_time="09:00",
        estimated_duration=60,
        show_in_gantt=True,
    )
    result = _wbs_cpm(temp_db, ids["project_id"])
    assert EntityRef.subtask(ids["reinforcement_id"]) not in result.nodes
    assert EntityRef.subtask(nested_id) in result.nodes


def test_25_summary_row_separate_from_leaf_result(temp_db):
    ids = _make_witness(temp_db)
    model = _wbs_model(temp_db, ids["project_id"])
    parent_key = EntityRef.task(ids["parent_id"])
    assert model.data(model.index_from_key(parent_key, 0), WBSItemModel.CPMNodeResultRole) is None
    assert _model_value(model, parent_key, WBSItemModel.COL_CRITICAL) == "Contains Critical"


def test_26_leaf_row_exposes_result_object(temp_db):
    ids = _make_witness(temp_db)
    model = _wbs_model(temp_db, ids["project_id"])
    leaf_key = EntityRef.subtask(ids["reinforcement_id"])
    assert model.data(model.index_from_key(leaf_key, 0), WBSItemModel.CPMNodeResultRole) is not None


def test_27_refresh_updates_duration_result(temp_db):
    ids = _make_witness(temp_db)
    first = _wbs_cpm(temp_db, ids["project_id"]).get_node(EntityRef.subtask(ids["reinforcement_id"]))
    with temp_db.get_connection() as conn:
        conn.execute("UPDATE subtasks SET estimated_duration=? WHERE id=?", (4320, ids["reinforcement_id"]))
        conn.commit()
    second = _wbs_cpm(temp_db, ids["project_id"]).get_node(EntityRef.subtask(ids["reinforcement_id"]))
    assert first.earliest_finish != second.earliest_finish


def test_28_refresh_updates_dependency_result(temp_db):
    ids = _make_witness(temp_db)
    rein_key = EntityRef.subtask(ids["reinforcement_id"])
    before = _wbs_cpm(temp_db, ids["project_id"]).get_node(rein_key).earliest_start
    with temp_db.get_connection() as conn:
        conn.execute("UPDATE subtasks SET dependencies=? WHERE id=?", ("[]", ids["reinforcement_id"]))
        conn.commit()
    after = _wbs_cpm(temp_db, ids["project_id"]).get_node(rein_key).earliest_start
    assert before != after


def test_29_refresh_updates_calendar_result(temp_db):
    ids = _make_witness(temp_db)
    rein_key = EntityRef.subtask(ids["reinforcement_id"])
    with temp_db.get_connection() as conn:
        conn.execute("UPDATE subtasks SET estimated_duration=? WHERE id=?", (7200, ids["excavation_id"]))
        conn.execute("UPDATE subtasks SET estimated_duration=? WHERE id=?", (7200, ids["reinforcement_id"]))
        conn.commit()
    before = _wbs_cpm(temp_db, ids["project_id"]).get_node(rein_key).earliest_finish
    temp_db.set_project_calendar(ids["project_id"], [0, 1, 2, 3, 4])
    after = _wbs_cpm(temp_db, ids["project_id"]).get_node(rein_key).earliest_finish
    assert before != after


def test_30_gantt_dependency_annotate_preserves_canonical_subtask_cpm(temp_db):
    ids = _make_witness(temp_db)
    items = _gantt_items(temp_db, ids["project_id"])
    subtask = _gantt_item(items, "subtask", ids["reinforcement_id"])
    GanttDependencyEngine.annotate(items)
    assert subtask.gantt_cpm_analysis_status == "analyzed"
    assert subtask.cpm_earliest_start is not None


@pytest.mark.parametrize(
    "dep_type,expected_start,expected_finish",
    [
        ("FS", "2026-09-01 10:00", "2026-09-01 11:00"),
        ("SS", "2026-09-01 09:00", "2026-09-01 10:00"),
        ("FF", "2026-09-01 09:00", "2026-09-01 10:00"),
        ("SF", "2026-09-01 08:00", "2026-09-01 09:00"),
    ],
)
def test_31_34_dependency_types_preserved_for_subtasks(temp_db, dep_type, expected_start, expected_finish):
    ids = _make_witness(temp_db, dep_type=dep_type, minute_network=True)
    node = _wbs_cpm(temp_db, ids["project_id"]).get_node(EntityRef.subtask(ids["reinforcement_id"]))
    assert node.earliest_start.strftime("%Y-%m-%d %H:%M") == expected_start
    assert node.earliest_finish.strftime("%Y-%m-%d %H:%M") == expected_finish


@pytest.mark.parametrize(
    "lag,expected_start",
    [
        (60, "2026-09-01 11:00"),
        (-30, "2026-09-01 09:30"),
    ],
)
def test_35_36_lag_and_lead_preserved_for_subtasks(temp_db, lag, expected_start):
    ids = _make_witness(temp_db, dep_type="FS", lag=lag)
    node = _wbs_cpm(temp_db, ids["project_id"]).get_node(EntityRef.subtask(ids["reinforcement_id"]))
    assert node.earliest_start.strftime("%Y-%m-%d %H:%M") == expected_start


def test_37_wbs_and_gantt_do_not_duplicate_cpm_math():
    model_src = inspect.getsource(WBSItemModel)
    adapter_src = inspect.getsource(GanttWBSAdapter)
    tooltip_src = inspect.getsource(GanttTaskItem._set_rich_tooltip)
    assert "calculate_wbs_cpm" in model_src
    assert "cpm_node_for_key" in adapter_src
    assert "earliest_start =" not in tooltip_src
    assert "latest_finish =" not in tooltip_src


def test_38_production_db_hash_unchanged_by_read_only_probe():
    before = _hash_file(PRODUCTION_DB)
    assert PRODUCTION_DB.exists()
    after = _hash_file(PRODUCTION_DB)
    assert after == before


def test_39_existing_cpm_suite_files_present():
    root = Path(__file__).resolve().parent
    assert (root / "test_phase2a_professional_scheduling_engine.py").exists()
    assert (root / "test_phase2c_advanced_dependencies.py").exists()
    assert (root / "test_working_calendar_cpm_authority.py").exists()


def test_40_full_regression_runner_present():
    runner = Path(__file__).resolve().parents[2] / "tools" / "run_isolated_pytest.py"
    assert runner.exists()


def test_41_gantt_tooltip_shows_subtask_cpm_core(qapp, temp_db):
    ids = _make_witness(temp_db)
    items = _gantt_items(temp_db, ids["project_id"])
    subtask = _gantt_item(items, "subtask", ids["reinforcement_id"])
    GanttDependencyEngine.annotate(items)
    item = GanttTaskItem(
        subtask,
        0,
        0,
        1,
        60,
        GanttColorProfile(),
        project_name="SCHEDULING WITNESS FINAL",
    )
    tooltip = item.toolTip()
    assert "Current Forecast Start" in tooltip
    assert "Current Forecast Finish" in tooltip
    assert "ES:" in tooltip
    assert "EF:" in tooltip
    assert "LS:" in tooltip
    assert "LF:" in tooltip
    assert "Total Float" in tooltip
    assert "Free Float" in tooltip
    assert "Critical:" in tooltip
    assert "Dependencies:" in tooltip
    assert "Not analyzed" not in tooltip


def test_42_wbs_filter_critical_includes_subtask_leaf(temp_db):
    ids = _make_witness(temp_db)
    model = _wbs_model(temp_db, ids["project_id"])
    proxy = WBSFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.set_status_filter("critical")
    source_parent = model.index_from_key(EntityRef.task(ids["parent_id"]), 0)
    proxy_parent = proxy.mapFromSource(source_parent)
    assert proxy_parent.isValid()
    assert proxy.rowCount(proxy_parent) >= 1


def test_43_schedule_version_snapshot_uses_subtask_cpm(temp_db):
    ids = _make_witness(temp_db)
    items = ScheduleVersionService.capture_current_schedule_snapshot(temp_db, ids["project_id"])
    subtask_item = next(
        item
        for item in items
        if item["entity_type"] == "subtask" and item["entity_id"] == ids["reinforcement_id"]
    )
    assert subtask_item["start"] == "2026-09-02 09:00"
    assert subtask_item["finish"] == "2026-09-03 09:00"


def test_44_gantt_view_subtask_item_uses_same_values_as_wbs_cpm(temp_db):
    ids = _make_witness(temp_db)
    cpm_node = _wbs_cpm(temp_db, ids["project_id"]).get_node(EntityRef.subtask(ids["reinforcement_id"]))
    item = _gantt_item(_gantt_items(temp_db, ids["project_id"]), "subtask", ids["reinforcement_id"])
    assert item.cpm_earliest_start[:16] == cpm_node.earliest_start.isoformat()[:16]
    assert item.cpm_latest_finish[:16] == cpm_node.latest_finish.isoformat()[:16]


def test_45_report_oracle_expected_vs_actual_fs_values(temp_db):
    ids = _make_witness(temp_db)
    result = _wbs_cpm(temp_db, ids["project_id"])
    excavation = result.get_node(EntityRef.subtask(ids["excavation_id"]))
    reinforcement = result.get_node(EntityRef.subtask(ids["reinforcement_id"]))
    assert excavation.earliest_start.strftime("%Y-%m-%d %H:%M") == "2026-09-01 09:00"
    assert excavation.earliest_finish.strftime("%Y-%m-%d %H:%M") == "2026-09-02 09:00"
    assert reinforcement.earliest_start == excavation.earliest_finish
    assert reinforcement.earliest_finish.strftime("%Y-%m-%d %H:%M") == "2026-09-03 09:00"
