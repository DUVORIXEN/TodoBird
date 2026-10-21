"""
ISOLATED Unit Test for wbs_item_model.py
Target: todo_bird_app/models/wbs_item_model.py
Session: ses_wbs_model_1
WARNING: THIS FILE WILL BE DELETED AFTER TEST PASSES
Test code preserved in: .opencode/unit-tests/
"""
import sys
from PySide6.QtWidgets import QApplication

# Need QApplication before Qt model
app = QApplication.instance() or QApplication(sys.argv)

from todo_bird_app.services.wbs_service import EntityRef, WBSService
from todo_bird_app.models.wbs_item_model import WBSItemModel
from todo_bird_app.database import DatabaseManager

def test_roles_consecutive():
    assert WBSItemModel.NodeKeyRole == 257
    assert WBSItemModel.RollupProgressRole == 273
    assert WBSItemModel.RollupDataRole == 282
    print("roles consecutive pass")

def test_progress_for_summary_uses_rollup():
    db = DatabaseManager(db_path=":memory:")
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO projects (name, color, icon, description) VALUES ('P','c','i','')")
        pid = cur.lastrowid
        cur.execute("INSERT INTO tasks (title, project_id, position, status, created_at) VALUES ('A', ?, 0, 'Planned', '2026-08-18 00:00:00')", (pid,))
        tid = cur.lastrowid
        cur.execute("INSERT INTO subtasks (task_id, parent_subtask_id, title, position, is_completed, created_at, planned_effort_minutes, progress) VALUES (?, NULL, 'B', 0, 0, '2026-08-18 00:00:01', 0, 0)", (tid,))
        cur.execute("SELECT id FROM subtasks WHERE title='B'")
        bid = cur.fetchone()[0]
        cur.execute("INSERT INTO subtasks (task_id, parent_subtask_id, title, position, is_completed, created_at, planned_effort_minutes, progress, planned_date, planned_start_time, planned_end_time) VALUES (?, ?, 'D', 0, 0, '2026-08-18 00:00:02', 480, 50, '2026-08-18', '09:00', '17:00')", (tid, bid))
        cur.execute("INSERT INTO subtasks (task_id, parent_subtask_id, title, position, is_completed, created_at, planned_effort_minutes, progress, planned_date, planned_start_time, planned_end_time) VALUES (?, ?, 'E', 1, 0, '2026-08-18 00:00:03', 240, 100, '2026-08-18', '13:00', '17:00')", (tid, bid))
        conn.commit()
    snap = WBSService.build_project_hierarchy(db, project_id=pid)
    model = WBSItemModel(snap)
    model.set_snapshot(snap, db_manager=db)
    # B is summary with leaves D,E -> progress should be 67 (weighted)
    b_key = [k for k,n in snap.nodes_by_key.items() if n.title=="B"][0]
    idx = model.index_from_key(b_key)
    prog = model.data(idx, WBSItemModel.ProgressRole)
    rprog = model.data(idx, WBSItemModel.RollupProgressRole)
    assert prog == 67, f"expected 67 got {prog}"
    assert rprog == 67
    print("summary progress pass", prog)
    # leaf D should retain naive progress 0 (child untouched) but rollup data 50
    d_key = [k for k,n in snap.nodes_by_key.items() if n.title=="D"][0]
    idx_d = model.index_from_key(d_key)
    leaf_prog = model.data(idx_d, WBSItemModel.ProgressRole)
    assert leaf_prog == 0, f"leaf naive {leaf_prog}"
    rleaf = model.data(idx_d, WBSItemModel.RollupProgressRole)
    assert rleaf == 50
    print("leaf unchanged pass")

def test_planned_roles_wired():
    db = DatabaseManager(db_path=":memory:")
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO projects (name, color, icon, description) VALUES ('P2','c','i','')")
        pid = cur.lastrowid
        cur.execute("INSERT INTO tasks (title, project_id, position, status, created_at) VALUES ('A', ?, 0, 'Planned', '2026-08-18 00:00:00')", (pid,))
        tid = cur.lastrowid
        cur.execute("INSERT INTO subtasks (task_id, parent_subtask_id, title, position, is_completed, created_at, planned_date, planned_start_time, planned_end_time, planned_effort_minutes) VALUES (?, NULL, 'X', 0, 0, '2026-08-18 00:00:01', '2026-08-18', '08:00', '12:00', 240)", (tid,))
        cur.execute("INSERT INTO subtasks (task_id, parent_subtask_id, title, position, is_completed, created_at, planned_date, planned_start_time, planned_end_time, planned_effort_minutes) VALUES (?, NULL, 'Y', 1, 0, '2026-08-18 00:00:02', '2026-08-19', '10:00', '14:00', 240)", (tid,))
        conn.commit()
    snap = WBSService.build_project_hierarchy(db, project_id=pid)
    model = WBSItemModel(snap)
    model.set_snapshot(snap, db_manager=db)
    task_key = snap.root_keys[0]
    idx = model.index_from_key(task_key)
    ps = model.data(idx, WBSItemModel.PlannedStartRole)
    pf = model.data(idx, WBSItemModel.PlannedFinishRole)
    assert ps is not None and pf is not None
    assert ps < pf
    pe = model.data(idx, WBSItemModel.PlannedEffortRole)
    assert pe == 480
    print("planned roles pass", ps, pf, pe)
    # no DB per data: ensure repeated calls no error
    for _ in range(10):
        model.data(idx, WBSItemModel.RollupDataRole)

def test_setData_no_mutation():
    snap = WBSService.build_from_raw([], project_id=None)
    model = WBSItemModel(snap)
    idx = model.index(0,0)
    assert model.setData(idx, "x") is False
    print("setData pass")

if __name__ == "__main__":
    test_roles_consecutive()
    test_progress_for_summary_uses_rollup()
    test_planned_roles_wired()
    test_setData_no_mutation()
    print("ALL ISOLATED PASS")
    app.quit()
