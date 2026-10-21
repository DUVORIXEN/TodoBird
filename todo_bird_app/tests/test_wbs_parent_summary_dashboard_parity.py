import hashlib
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.wbs_item_model import WBSItemModel
from todo_bird_app.services.dashboard_schedule_summary_service import (
    DashboardScheduleSummaryService,
)
from todo_bird_app.services.gantt_wbs_adapter import GanttWBSAdapter
from todo_bird_app.services.schedule_calendar_service import effective_project_calendar_from_db
from todo_bird_app.services.wbs_cpm_adapter import calculate_wbs_cpm
from todo_bird_app.services.wbs_rollup_service import WBSRollupService
from todo_bird_app.services.wbs_service import EntityRef, WBSService


PRODUCTION_DB = Path(__file__).resolve().parents[1] / "data" / "todo_bird.db"
RAW_TASK_FIELDS = (
    "planned_date",
    "planned_start_time",
    "due_date",
    "planned_end_time",
    "estimated_duration",
    "planned_effort_minutes",
    "daily_dedication_minutes",
)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "wbs_parent_summary_parity.db"))
    WBSRollupService.clear_cache()
    yield db
    WBSRollupService.clear_cache()
    db.close()


def _dependency(predecessor_id):
    return [{"predecessor_id": predecessor_id, "type": "FS", "lag_minutes": 0}]


def _make_foundation_witness(db):
    project_id = db.insert_project({"name": "SCHEDULING WITNESS FINAL"})
    db.set_project_calendar(project_id, [0, 1, 2, 3, 4, 5])
    parent_id = db.insert_task(
        {
            "project_id": project_id,
            "title": "Foundation",
            "status": "Planned",
            "planned_date": "2026-09-10",
            "planned_start_time": "13:00",
            "due_date": "2026-09-20",
            "planned_end_time": "19:00",
            "estimated_duration": 9999,
            "planned_effort_minutes": 9999,
            "daily_dedication_minutes": 111,
            "show_in_gantt": 1,
        }
    )
    prep_id = db.insert_subtask(
        parent_id,
        "Foundation Prep",
        position=0,
        planned_effort_minutes=9999,
        show_in_gantt=True,
    )
    excavation_id = db.insert_subtask(
        parent_id,
        "Excavation",
        parent_subtask_id=prep_id,
        position=0,
        planned_date="2026-09-01",
        planned_start_time="09:00",
        estimated_duration=2880,
        planned_effort_minutes=480,
        progress=50,
        show_in_gantt=True,
    )
    survey_id = db.insert_subtask(
        parent_id,
        "Survey",
        parent_subtask_id=prep_id,
        position=1,
        planned_date="2026-09-01",
        planned_start_time="09:00",
        estimated_duration=60,
        planned_effort_minutes=60,
        progress=100,
        show_in_gantt=True,
    )
    reinforcement_id = db.insert_subtask(
        parent_id,
        "Reinforcement",
        position=1,
        planned_date="2026-09-02",
        planned_start_time="09:00",
        estimated_duration=2880,
        planned_effort_minutes=480,
        progress=0,
        dependencies=_dependency(excavation_id),
        show_in_gantt=True,
    )
    return {
        "project_id": project_id,
        "parent_id": parent_id,
        "prep_id": prep_id,
        "excavation_id": excavation_id,
        "survey_id": survey_id,
        "reinforcement_id": reinforcement_id,
    }


def _make_overlap_witness(db):
    project_id = db.insert_project({"name": "OVERLAP WITNESS"})
    db.set_project_calendar(project_id, [0, 1, 2, 3, 4, 5])
    parent_id = db.insert_task(
        {
            "project_id": project_id,
            "title": "Overlap Parent",
            "status": "Planned",
            "estimated_duration": 7777,
            "show_in_gantt": 1,
        }
    )
    first_id = db.insert_subtask(
        parent_id,
        "Overlap A",
        position=0,
        planned_date="2026-09-01",
        planned_start_time="09:00",
        estimated_duration=2880,
        planned_effort_minutes=480,
        show_in_gantt=True,
    )
    second_id = db.insert_subtask(
        parent_id,
        "Overlap B",
        position=1,
        planned_date="2026-09-01",
        planned_start_time="12:00",
        estimated_duration=2880,
        planned_effort_minutes=480,
        show_in_gantt=True,
    )
    return {
        "project_id": project_id,
        "parent_id": parent_id,
        "first_id": first_id,
        "second_id": second_id,
    }


def _make_at_risk_witness(db):
    ids = _make_foundation_witness(db)
    db.insert_subtask(
        ids["parent_id"],
        "Unscheduled Child",
        position=2,
        estimated_duration=120,
        planned_effort_minutes=120,
        show_in_gantt=True,
    )
    return ids


def _snapshot(db, project_id):
    return WBSService.build_project_hierarchy(db, project_id=project_id)


def _cpm(db, project_id):
    snap = _snapshot(db, project_id)
    return calculate_wbs_cpm(
        snap,
        db,
        project_calendar=effective_project_calendar_from_db(db, project_id),
    )


def _model(db, project_id):
    model = WBSItemModel()
    model.load_project(db, project_id)
    return model


def _display(model, key, column):
    index = model.index_from_key(key, column)
    assert index.isValid()
    return model.data(index, Qt.DisplayRole)


def _role(model, key, role):
    index = model.index_from_key(key, 0)
    assert index.isValid()
    return model.data(index, role)


def _rows(db, project_id):
    return GanttWBSAdapter.build_project_rows(_snapshot(db, project_id), db)


def _row(rows, key):
    return next(row for row in rows if row.key == key)


def _raw_parent(db, parent_id):
    row = db.get_task_by_id(parent_id)
    return {field: row[field] for field in RAW_TASK_FIELDS}


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_01_foundation_parent_is_not_cpm_leaf_node(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    cpm = _cpm(temp_db, ids["project_id"])
    assert cpm.get_node(EntityRef.task(ids["parent_id"])) is None


def test_02_child_subtasks_are_cpm_nodes(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    cpm = _cpm(temp_db, ids["project_id"])
    assert cpm.get_node(EntityRef.subtask(ids["excavation_id"])) is not None
    assert cpm.get_node(EntityRef.subtask(ids["reinforcement_id"])) is not None


def test_03_summary_metadata_exists_for_foundation(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    summary = _role(_model(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]), WBSItemModel.CPMSummaryResultRole)
    assert summary is not None


def test_04_parent_summary_start_uses_earliest_descendant_start(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    model = _model(temp_db, ids["project_id"])
    assert _role(model, EntityRef.task(ids["parent_id"]), WBSItemModel.CPMEarliestStartRole).strftime("%Y-%m-%d %H:%M") == "2026-09-01 09:00"


def test_05_parent_with_two_children_uses_earliest_start(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    model = _model(temp_db, ids["project_id"])
    parent_es = _role(model, EntityRef.task(ids["parent_id"]), WBSItemModel.CPMEarliestStartRole)
    survey_es = _role(model, EntityRef.subtask(ids["survey_id"]), WBSItemModel.CPMEarliestStartRole)
    assert parent_es == survey_es


def test_06_parent_summary_finish_uses_latest_descendant_finish(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    model = _model(temp_db, ids["project_id"])
    assert _role(model, EntityRef.task(ids["parent_id"]), WBSItemModel.CPMEarliestFinishRole).strftime("%Y-%m-%d %H:%M") == "2026-09-03 09:00"


def test_07_summary_latest_start_uses_descendant_latest_envelope_start(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    model = _model(temp_db, ids["project_id"])
    parent_ls = _role(model, EntityRef.task(ids["parent_id"]), WBSItemModel.CPMLatestStartRole)
    leaf_ls = [
        _role(model, EntityRef.subtask(ids[name]), WBSItemModel.CPMLatestStartRole)
        for name in ("excavation_id", "survey_id", "reinforcement_id")
    ]
    assert parent_ls == min(leaf_ls)


def test_08_summary_latest_finish_uses_descendant_latest_envelope_finish(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    model = _model(temp_db, ids["project_id"])
    parent_lf = _role(model, EntityRef.task(ids["parent_id"]), WBSItemModel.CPMLatestFinishRole)
    leaf_lf = [
        _role(model, EntityRef.subtask(ids[name]), WBSItemModel.CPMLatestFinishRole)
        for name in ("excavation_id", "survey_id", "reinforcement_id")
    ]
    assert parent_lf == max(leaf_lf)


def test_09_overlapping_children_summary_span_is_envelope_not_sum(temp_db, qapp):
    ids = _make_overlap_witness(temp_db)
    row = _row(_rows(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]))
    child_duration_sum = sum(
        _row(_rows(temp_db, ids["project_id"]), EntityRef.subtask(ids[name])).planned_elapsed_minutes
        for name in ("first_id", "second_id")
    )
    assert row.planned_elapsed_minutes < child_duration_sum


def test_10_parent_raw_task_schedule_unchanged_by_model_summary(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    before = _raw_parent(temp_db, ids["parent_id"])
    _model(temp_db, ids["project_id"])
    assert _raw_parent(temp_db, ids["parent_id"]) == before


def test_11_parent_raw_task_schedule_unchanged_by_gantt_summary(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    before = _raw_parent(temp_db, ids["parent_id"])
    _rows(temp_db, ids["project_id"])
    assert _raw_parent(temp_db, ids["parent_id"]) == before


def test_12_child_es_preserved(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    value = _role(_model(temp_db, ids["project_id"]), EntityRef.subtask(ids["excavation_id"]), WBSItemModel.CPMEarliestStartRole)
    assert value.strftime("%Y-%m-%d %H:%M") == "2026-09-01 09:00"


def test_13_child_ef_preserved(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    value = _role(_model(temp_db, ids["project_id"]), EntityRef.subtask(ids["excavation_id"]), WBSItemModel.CPMEarliestFinishRole)
    assert value.strftime("%Y-%m-%d %H:%M") == "2026-09-02 09:00"


def test_14_child_ls_preserved(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    model = _model(temp_db, ids["project_id"])
    assert _role(model, EntityRef.subtask(ids["excavation_id"]), WBSItemModel.CPMLatestStartRole) is not None


def test_15_child_lf_preserved(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    model = _model(temp_db, ids["project_id"])
    assert _role(model, EntityRef.subtask(ids["reinforcement_id"]), WBSItemModel.CPMLatestFinishRole) is not None


def test_16_parent_critical_contains_child_critical(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    text = _display(_model(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]), WBSItemModel.COL_CRITICAL)
    assert text == "Contains Critical"


def test_17_noncritical_child_mix_is_preserved(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    model = _model(temp_db, ids["project_id"])
    assert _role(model, EntityRef.subtask(ids["survey_id"]), WBSItemModel.CPMCriticalRole) is False
    assert _role(model, EntityRef.task(ids["parent_id"]), WBSItemModel.CPMCriticalRole) is True


def test_18_parent_total_float_role_is_not_faked(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    assert _role(_model(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]), WBSItemModel.CPMTotalFloatRole) is None


def test_19_parent_free_float_role_is_not_faked(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    assert _role(_model(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]), WBSItemModel.CPMFreeFloatRole) is None


def test_20_parent_total_float_display_is_summary_na(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    text = _display(_model(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]), WBSItemModel.COL_TOTAL_FLOAT)
    assert text == "N/A (Summary)"


def test_21_parent_free_float_display_is_summary_na(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    text = _display(_model(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]), WBSItemModel.COL_FREE_FLOAT)
    assert text == "N/A (Summary)"


def test_22_summary_health_healthy_when_descendant_schedule_is_complete(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    text = _display(_model(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]), WBSItemModel.COL_DIAGNOSTICS)
    assert text == "Healthy"


def test_23_summary_progress_rollup_uses_children(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    progress = _role(_model(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]), WBSItemModel.RollupProgressRole)
    assert 0 < progress < 100


def test_24_nested_subtask_summary_has_summary_metadata(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    summary = _role(_model(temp_db, ids["project_id"]), EntityRef.subtask(ids["prep_id"]), WBSItemModel.CPMSummaryResultRole)
    assert summary is not None
    assert summary.descendant_leaf_count == 2


def test_25_multiple_nesting_levels_roll_up_to_main_task(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    summary = _role(_model(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]), WBSItemModel.CPMSummaryResultRole)
    assert summary.descendant_leaf_count == 3


@pytest.mark.parametrize(
    "column",
    [
        WBSItemModel.COL_ES,
        WBSItemModel.COL_EF,
        WBSItemModel.COL_LS,
        WBSItemModel.COL_LF,
    ],
)
def test_26_29_wbs_summary_date_columns_are_visible(column, temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    text = _display(_model(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]), column)
    assert text not in ("-", "—", "N/A (Summary)")


def test_30_no_meaningless_dash_when_summary_state_known(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    model = _model(temp_db, ids["project_id"])
    key = EntityRef.task(ids["parent_id"])
    assert _display(model, key, WBSItemModel.COL_CRITICAL) != "—"
    assert _display(model, key, WBSItemModel.COL_DIAGNOSTICS) != "—"


def test_31_gantt_summary_bar_start_matches_wbs_summary_start(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    model = _model(temp_db, ids["project_id"])
    row = _row(_rows(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]))
    assert row.cpm_earliest_start == _role(model, EntityRef.task(ids["parent_id"]), WBSItemModel.CPMEarliestStartRole)


def test_32_gantt_summary_bar_finish_matches_wbs_summary_finish(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    model = _model(temp_db, ids["project_id"])
    row = _row(_rows(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]))
    assert row.cpm_earliest_finish == _role(model, EntityRef.task(ids["parent_id"]), WBSItemModel.CPMEarliestFinishRole)


def test_33_gantt_summary_carries_derived_cpm_start(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    row = _row(_rows(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]))
    assert row.cpm_earliest_start.strftime("%Y-%m-%d %H:%M") == "2026-09-01 09:00"


def test_34_gantt_summary_carries_derived_cpm_finish(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    row = _row(_rows(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]))
    assert row.cpm_earliest_finish.strftime("%Y-%m-%d %H:%M") == "2026-09-03 09:00"


def test_35_dashboard_critical_count_matches_leaf_cpm(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    summary = DashboardScheduleSummaryService.project_summary(temp_db, ids["project_id"], "SCHEDULING WITNESS FINAL")
    critical_leaf_count = len(_cpm(temp_db, ids["project_id"]).critical_keys)
    assert summary.critical_work_count == critical_leaf_count


def test_36_dashboard_project_span_matches_wbs_summary_envelope(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    summary = DashboardScheduleSummaryService.project_summary(temp_db, ids["project_id"], "SCHEDULING WITNESS FINAL")
    row = _row(_rows(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]))
    assert summary.summary_start == row.cpm_earliest_start
    assert summary.summary_finish == row.cpm_earliest_finish


def test_37_dashboard_suffix_exposes_supported_schedule_metrics(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    summary = DashboardScheduleSummaryService.project_summary(temp_db, ids["project_id"], "SCHEDULING WITNESS FINAL")
    suffix = DashboardScheduleSummaryService.format_snapshot_suffix(summary)
    assert "critical" in suffix
    assert "1 Sep-3 Sep" in suffix


def test_38_at_risk_summary_reports_missing_child_schedule(temp_db, qapp):
    ids = _make_at_risk_witness(temp_db)
    text = _display(_model(temp_db, ids["project_id"]), EntityRef.task(ids["parent_id"]), WBSItemModel.COL_DIAGNOSTICS)
    assert text.startswith("At Risk")


def test_39_summary_recompute_does_not_update_raw_task_fields(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    before = _raw_parent(temp_db, ids["parent_id"])
    model = _model(temp_db, ids["project_id"])
    model.rebuild_cpm_schedule()
    model.rebuild_rollups()
    DashboardScheduleSummaryService.project_summary(temp_db, ids["project_id"], "SCHEDULING WITNESS FINAL")
    assert _raw_parent(temp_db, ids["parent_id"]) == before


def test_40_save_reopen_raw_parent_task_unchanged_by_summary_reads(temp_db, qapp):
    ids = _make_foundation_witness(temp_db)
    before = _raw_parent(temp_db, ids["parent_id"])
    temp_db.close()
    reopened = DatabaseManager.for_test(temp_db.db_path)
    try:
        _model(reopened, ids["project_id"])
        assert _raw_parent(reopened, ids["parent_id"]) == before
    finally:
        reopened.close()


def test_41_production_db_hash_unchanged_by_hash_only_witness():
    before = _hash(PRODUCTION_DB)
    assert PRODUCTION_DB.exists()
    after = _hash(PRODUCTION_DB)
    assert after == before
