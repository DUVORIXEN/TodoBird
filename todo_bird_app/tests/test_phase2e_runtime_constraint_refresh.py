"""
Phase 2E Runtime Constraint Refresh & Display Authority Integration Test Suite
"""

import json
from datetime import datetime
import pytest
from PySide6.QtCore import Qt

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task
from todo_bird_app.models.wbs_item_model import WBSItemModel
from todo_bird_app.services.cpm_scheduling_service import CPMSchedulingService, DiagnosticCode
from todo_bird_app.services.gantt_wbs_adapter import GanttWBSAdapter


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_todo_bird.db")
    db = DatabaseManager(db_file)
    yield db
    db.close()


def test_01_save_snet_persists(temp_db):
    pid = temp_db.insert_project({"name": "THAAVORIX"})
    tid = temp_db.insert_task({
        "project_id": pid, "title": "Planning", "planned_date": "2026-08-23", "planned_start_time": "00:00",
        "estimated_duration": 1440, "constraint_type": "SNET", "constraint_datetime": "2026-09-15 09:00"
    })
    row = temp_db.get_task_by_id(tid)
    assert row["constraint_type"] == "SNET"
    assert row["constraint_datetime"] == "2026-09-15 09:00"


def test_02_cpm_es_moves_to_constraint_date(temp_db):
    pid = temp_db.insert_project({"name": "THAAVORIX"})
    tid = temp_db.insert_task({
        "project_id": pid, "title": "Planning", "planned_date": "2026-08-23", "planned_start_time": "00:00",
        "estimated_duration": 1440, "constraint_type": "SNET", "constraint_datetime": "2026-09-15 09:00"
    })
    tasks = [Task.from_row(r) for r in temp_db.get_tasks_by_project(pid)]
    res = CPMSchedulingService.calculate_schedule(tasks, project_id=pid)
    assert res.nodes[tid].earliest_start == datetime(2026, 9, 15, 9, 0)


def test_03_wbs_displays_constrained_current_start(temp_db):
    pid = temp_db.insert_project({"name": "THAAVORIX"})
    tid = temp_db.insert_task({
        "project_id": pid, "title": "Planning", "planned_date": "2026-08-23", "planned_start_time": "00:00",
        "estimated_duration": 1440, "constraint_type": "SNET", "constraint_datetime": "2026-09-15 09:00"
    })
    model = WBSItemModel()
    model.load_project(temp_db, pid)
    idx_es = model.index(0, WBSItemModel.COL_ES)
    assert "2026-09-15 09:00" in str(model.data(idx_es, Qt.DisplayRole))
    assert model.data(model.index(0, 0), WBSItemModel.RollupPlannedStartRole) == "2026-09-15T09:00:00"


def test_04_gantt_bar_uses_constrained_current_start(temp_db):
    pid = temp_db.insert_project({"name": "THAAVORIX"})
    tid = temp_db.insert_task({
        "project_id": pid, "title": "Planning", "planned_date": "2026-08-23", "planned_start_time": "00:00",
        "estimated_duration": 1440, "constraint_type": "SNET", "constraint_datetime": "2026-09-15 09:00"
    })
    model = WBSItemModel()
    model.load_project(temp_db, pid)
    snap = model.snapshot
    payloads = {k: temp_db.get_task_by_id(k.entity_id) for k in snap.nodes_by_key}
    rows = GanttWBSAdapter.build_rows(snap, payloads, model.get_all_rollups())
    assert rows[0].planned_start == datetime(2026, 9, 15, 9, 0)


def test_05_baseline_remains_frozen(temp_db):
    pid = temp_db.insert_project({"name": "THAAVORIX"})
    tid = temp_db.insert_task({
        "project_id": pid, "title": "Planning", "planned_date": "2026-08-23", "planned_start_time": "00:00",
        "estimated_duration": 1440, "baseline_start": "2026-08-23 00:00", "baseline_finish": "2026-08-24 00:00",
        "constraint_type": "SNET", "constraint_datetime": "2026-09-15 09:00"
    })
    row = temp_db.get_task_by_id(tid)
    assert row["baseline_start"] == "2026-08-23 00:00"
    assert row["baseline_finish"] == "2026-08-24 00:00"


def test_06_reopening_task_shows_saved_snet(temp_db):
    pid = temp_db.insert_project({"name": "THAAVORIX"})
    tid = temp_db.insert_task({
        "project_id": pid, "title": "Planning", "planned_date": "2026-08-23", "planned_start_time": "00:00",
        "estimated_duration": 1440, "constraint_type": "SNET", "constraint_datetime": "2026-09-15 09:00"
    })
    t_obj = Task.from_row(temp_db.get_task_by_id(tid))
    assert t_obj.constraint_type == "SNET"
    assert t_obj.constraint_datetime == "2026-09-15 09:00"


def test_07_editing_constraint_again_refreshes_wbs(temp_db):
    pid = temp_db.insert_project({"name": "THAAVORIX"})
    tid = temp_db.insert_task({
        "project_id": pid, "title": "Planning", "planned_date": "2026-08-23", "planned_start_time": "00:00",
        "estimated_duration": 1440, "constraint_type": "SNET", "constraint_datetime": "2026-09-15 09:00"
    })
    model = WBSItemModel()
    model.load_project(temp_db, pid)
    assert "2026-09-15 09:00" in str(model.data(model.index(0, WBSItemModel.COL_ES), Qt.DisplayRole))

    # Edit constraint date to 2026-10-01
    temp_db.update_task(tid, {"constraint_datetime": "2026-10-01 09:00"})
    model.load_project(temp_db, pid)
    assert "2026-10-01 09:00" in str(model.data(model.index(0, WBSItemModel.COL_ES), Qt.DisplayRole))


def test_08_editing_constraint_again_refreshes_gantt(temp_db):
    pid = temp_db.insert_project({"name": "THAAVORIX"})
    tid = temp_db.insert_task({
        "project_id": pid, "title": "Planning", "planned_date": "2026-08-23", "planned_start_time": "00:00",
        "estimated_duration": 1440, "constraint_type": "SNET", "constraint_datetime": "2026-09-15 09:00"
    })
    temp_db.update_task(tid, {"constraint_datetime": "2026-10-01 09:00"})
    model = WBSItemModel()
    model.load_project(temp_db, pid)
    snap = model.snapshot
    payloads = {k: temp_db.get_task_by_id(k.entity_id) for k in snap.nodes_by_key}
    rows = GanttWBSAdapter.build_rows(snap, payloads, model.get_all_rollups())
    assert rows[0].planned_start == datetime(2026, 10, 1, 9, 0)


def test_09_removing_constraint_returns_schedule_to_planned(temp_db):
    pid = temp_db.insert_project({"name": "THAAVORIX"})
    tid = temp_db.insert_task({
        "project_id": pid, "title": "Planning", "planned_date": "2026-08-24", "planned_start_time": "09:00",
        "estimated_duration": 1440, "constraint_type": "SNET", "constraint_datetime": "2026-09-15 09:00"
    })
    temp_db.update_task(tid, {"constraint_type": "ASAP", "constraint_datetime": None})
    model = WBSItemModel()
    model.load_project(temp_db, pid)
    assert "2026-08-24 09:00" in str(model.data(model.index(0, WBSItemModel.COL_ES), Qt.DisplayRole))


def test_10_deadline_only_edit_does_not_move_schedule(temp_db):
    pid = temp_db.insert_project({"name": "THAAVORIX"})
    tid = temp_db.insert_task({
        "project_id": pid, "title": "Planning", "planned_date": "2026-08-24", "planned_start_time": "09:00",
        "estimated_duration": 1440, "constraint_type": "ASAP"
    })
    model1 = WBSItemModel()
    model1.load_project(temp_db, pid)
    es1 = model1.data(model1.index(0, WBSItemModel.COL_ES), Qt.DisplayRole)

    temp_db.update_task(tid, {"deadline_datetime": "2026-08-20 17:00"})
    model2 = WBSItemModel()
    model2.load_project(temp_db, pid)
    es2 = model2.data(model2.index(0, WBSItemModel.COL_ES), Qt.DisplayRole)
    assert es1 == es2


def test_11_fnlt_conflict_appears_in_wbs_diagnostics(temp_db):
    pid = temp_db.insert_project({"name": "THAAVORIX"})
    t1 = temp_db.insert_task({
        "project_id": pid, "title": "A", "planned_date": "2026-08-24", "planned_start_time": "09:00",
        "estimated_duration": 2880
    })
    t2 = temp_db.insert_task({
        "project_id": pid, "title": "B", "planned_date": "2026-08-24", "planned_start_time": "09:00",
        "estimated_duration": 1440, "dependencies": json.dumps([{"predecessor_id": t1, "type": "FS", "lag_minutes": 0}]),
        "constraint_type": "FNLT", "constraint_datetime": "2026-08-25 08:00"
    })
    model = WBSItemModel()
    model.load_project(temp_db, pid)
    idx_diag = model.index(1, WBSItemModel.COL_DIAGNOSTICS)
    assert "Constraint Conflict" in str(model.data(idx_diag, Qt.DisplayRole))


def test_12_mso_conflict_appears_without_breaking_dependency(temp_db):
    pid = temp_db.insert_project({"name": "THAAVORIX"})
    t1 = temp_db.insert_task({
        "project_id": pid, "title": "A", "planned_date": "2026-08-24", "planned_start_time": "09:00",
        "estimated_duration": 2880
    })
    t2 = temp_db.insert_task({
        "project_id": pid, "title": "B", "planned_date": "2026-08-24", "planned_start_time": "09:00",
        "estimated_duration": 1440, "dependencies": json.dumps([{"predecessor_id": t1, "type": "FS", "lag_minutes": 0}]),
        "constraint_type": "MSO", "constraint_datetime": "2026-08-24 09:00"
    })
    model = WBSItemModel()
    model.load_project(temp_db, pid)
    idx_es = model.index(1, WBSItemModel.COL_ES)
    # Earliest start remains at 2026-08-25 09:00 (predecessor A finish bound preserved!)
    assert "2026-08-25 09:00" in str(model.data(idx_es, Qt.DisplayRole))


def test_13_no_db_query_in_paint_path(temp_db, monkeypatch):
    pid = temp_db.insert_project({"name": "THAAVORIX"})
    temp_db.insert_task({
        "project_id": pid, "title": "Planning", "planned_date": "2026-08-23", "planned_start_time": "00:00",
        "estimated_duration": 1440, "constraint_type": "SNET", "constraint_datetime": "2026-09-15 09:00"
    })
    model = WBSItemModel()
    model.load_project(temp_db, pid)

    db_queries = 0
    orig_get_tasks = temp_db.get_tasks_by_project

    def fail_if_queried(*args, **kwargs):
        nonlocal db_queries
        db_queries += 1
        return orig_get_tasks(*args, **kwargs)

    monkeypatch.setattr(temp_db, "get_tasks_by_project", fail_if_queried)

    for c in range(WBSItemModel.COLUMN_COUNT):
        model.data(model.index(0, c), Qt.DisplayRole)
        model.data(model.index(0, c), WBSItemModel.RollupPlannedStartRole)
        model.data(model.index(0, c), WBSItemModel.CPMEarliestStartRole)

    assert db_queries == 0
