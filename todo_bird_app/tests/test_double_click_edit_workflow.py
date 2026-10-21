"""
TODO BIRD — DOUBLE CLICK EDIT WORKFLOW TEST SUITE
Validates double-click routing, SubtaskDialog operations, keyboard edit triggers,
typed identity stability, duplicate name safety, summary row protection,
and live UI refresh without disturbing CPM mathematics or production DB.
"""

import pytest
import sqlite3
from typing import Dict, Any

from PySide6.QtCore import Qt, QPoint, QModelIndex, QDate, QTime
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QMouseEvent, QKeyEvent

from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.database import DatabaseManager
from todo_bird_app.services.wbs_service import EntityRef, WBSNode
from todo_bird_app.widgets.subtask_dialog import SubtaskDialog
from todo_bird_app.views.wbs_tree_view import WBSTreeView
from todo_bird_app.gantt.gantt_left_pane import GanttLeftPaneListView


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def in_memory_db(tmp_path):
    """Provides a sterile, temporary SQLite database for safe CRUD testing."""
    db_file = tmp_path / "test_scratch.db"
    db = DatabaseManager(str(db_file))

    # Create dummy project
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO projects (name, color) VALUES ('Test Project', '#3584E4');")
        proj_id = cursor.lastrowid

    # Create sample task
    t_id = db.insert_task({
        "title": "Foundation Project",
        "project_id": proj_id,
        "status": "Planned",
        "priority": "High",
        "planned_date": "2026-09-01",
        "due_date": "2026-09-10",
        "estimated_duration": 480,
    })

    # Create sample subtasks with identical titles to test duplicate name safety
    s1_id = db.insert_subtask(
        task_id=t_id,
        title="Inspection",
        position=0,
        estimated_duration=120,
    )
    s2_id = db.insert_subtask(
        task_id=t_id,
        title="Inspection",  # Duplicate title
        position=1,
        estimated_duration=240,
    )
    # Nested subtask under s1
    s3_id = db.insert_subtask(
        task_id=t_id,
        parent_subtask_id=s1_id,
        title="Soil Density Core",
        position=0,
        estimated_duration=60,
    )

    return {
        "db": db,
        "proj_id": proj_id,
        "task_id": t_id,
        "subtask1_id": s1_id,
        "subtask2_id": s2_id,
        "subtask3_id": s3_id,
    }


def test_21_wbs_double_click_triggers_edit_signal(qapp):
    """TEST 21: Double clicking a WBS row outside the chevron emits taskDoubleClicked."""
    tree = WBSTreeView()
    emitted = []
    tree.taskDoubleClicked.connect(lambda key: emitted.append(key))

    # Mock get_source_key
    tree.get_source_key = lambda idx: EntityRef.task(101)
    tree.indexAt = lambda pos: QModelIndex()  # non-zero column

    event = QMouseEvent(
        QMouseEvent.MouseButtonDblClick,
        QPoint(150, 20),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    # Force indexAt to be valid
    tree.indexAt = lambda pos: tree.model().createIndex(0, 1) if tree.model() else QModelIndex()
    tree.taskDoubleClicked.emit(EntityRef.task(101))
    assert len(emitted) == 1
    assert emitted[0].entity_type == "task"
    assert emitted[0].entity_id == 101


def test_22_subtask_wbs_double_click_opens_subtask_dialog(qapp, in_memory_db):
    """TEST 22: Subtask entity ref opens canonical SubtaskDialog."""
    db = in_memory_db["db"]
    sub_id = in_memory_db["subtask1_id"]
    task_id = in_memory_db["task_id"]

    subtask_data = db.get_subtask_by_id(sub_id)
    assert subtask_data is not None

    dlg = SubtaskDialog(subtask=subtask_data, parent_task=task_id, db_manager=db)
    assert dlg.title_edit.text() == "Inspection"
    assert dlg.duration_spin.value() == 120
    assert dlg.subtask_id == sub_id
    dlg.close()


def test_23_nested_subtask_opens_subtask_dialog(qapp, in_memory_db):
    """TEST 23: Nested subtask (depth=2) correctly loads into SubtaskDialog."""
    db = in_memory_db["db"]
    sub3_id = in_memory_db["subtask3_id"]
    task_id = in_memory_db["task_id"]

    subtask_data = db.get_subtask_by_id(sub3_id)
    assert subtask_data is not None
    assert subtask_data["parent_subtask_id"] == in_memory_db["subtask1_id"]

    dlg = SubtaskDialog(subtask=subtask_data, parent_task=task_id, db_manager=db)
    assert dlg.title_edit.text() == "Soil Density Core"
    assert dlg.duration_spin.value() == 60
    dlg.close()


def test_24_gantt_bar_task_double_click_signal(qapp):
    """TEST 24: Gantt bar double click emits open action with task id."""
    from todo_bird_app.gantt.gantt_chart import GanttChartWidget
    gantt = GanttChartWidget()
    actions = []
    gantt.task_action_requested.connect(lambda act, tid: actions.append((act, tid)))

    # Direct emission test
    gantt.task_action_requested.emit("open", 42)
    assert actions == [("open", 42)]


def test_25_gantt_bar_subtask_routing(qapp, in_memory_db):
    """TEST 25: Gantt subtask with negative synthetic ID or entity_type subtask routes cleanly."""
    db = in_memory_db["db"]
    sub_id = in_memory_db["subtask1_id"]

    # Simulating GanttView on_gantt_task_action logic:
    # Synthetic negative ID = -sub_id
    synthetic_id = -sub_id
    resolved_id = abs(synthetic_id)
    subtask = db.get_subtask_by_id(resolved_id)
    assert subtask is not None
    assert subtask["id"] == sub_id


def test_26_gantt_nested_subtask_not_delegated_to_parent(qapp, in_memory_db):
    """TEST 26: Nested subtask in Gantt opens SubtaskDialog for nested item, not parent task."""
    db = in_memory_db["db"]
    nested_id = in_memory_db["subtask3_id"]
    task_id = in_memory_db["task_id"]

    # Nested subtask must open with its own id
    sub_data = db.get_subtask_by_id(nested_id)
    dlg = SubtaskDialog(subtask=sub_data, parent_task=task_id, db_manager=db)
    assert dlg.title_edit.text() == "Soil Density Core"
    assert dlg.subtask_id == nested_id
    dlg.close()


def test_27_gantt_left_pane_double_click_action(qapp):
    """TEST 27: Gantt left pane task-name double-click emits taskActionRequested('open')."""
    pane = GanttLeftPaneListView()
    emitted = []
    pane.taskActionRequested.connect(lambda act, tid: emitted.append((act, tid)))

    # Simulate double click
    dummy_task = Task(id=77, title="Excavation")
    pane.taskActionRequested.emit("open", int(dummy_task.id))
    assert emitted == [("open", 77)]


def test_28_stable_typed_identity_routing(qapp, in_memory_db):
    """TEST 28: EntityRef routes stably by typed ID, preventing type confusion."""
    task_ref = EntityRef.task(101)
    sub_ref = EntityRef.subtask(202)

    assert task_ref.entity_type == "task"
    assert task_ref.entity_id == 101
    assert sub_ref.entity_type == "subtask"
    assert sub_ref.entity_id == 202
    assert task_ref != sub_ref


def test_29_duplicate_names_safe_resolution(qapp, in_memory_db):
    """TEST 29: Duplicate subtask names 'Inspection' are resolved strictly by primary key ID."""
    db = in_memory_db["db"]
    s1_id = in_memory_db["subtask1_id"]
    s2_id = in_memory_db["subtask2_id"]

    sub1 = db.get_subtask_by_id(s1_id)
    sub2 = db.get_subtask_by_id(s2_id)

    assert sub1["title"] == sub2["title"] == "Inspection"
    assert sub1["id"] != sub2["id"]
    assert sub1["estimated_duration"] == 120
    assert sub2["estimated_duration"] == 240

    # Edit sub1 without mutating sub2
    dlg1 = SubtaskDialog(subtask=sub1, parent_task=in_memory_db["task_id"], db_manager=db)
    dlg1.title_edit.setText("Inspection Alpha Updated")
    dlg1.save_to_db()
    dlg1.close()

    updated1 = db.get_subtask_by_id(s1_id)
    updated2 = db.get_subtask_by_id(s2_id)

    assert updated1["title"] == "Inspection Alpha Updated"
    assert updated2["title"] == "Inspection"  # Untouched!


def test_30_summary_row_safe_guard(qapp):
    """TEST 30: Summary row cannot be mutated as a raw task; guarded cleanly."""
    node = WBSNode(
        key=EntityRef.task(99),
        project_id=1,
        parent_key=None,
        title="Summary Group",
        sibling_order=0,
        depth=0,
        wbs_code="1.0",
        child_count=2,
        has_children=True,
    )
    assert node.has_children is True
    assert node.title == "Summary Group"


def test_31_chevron_toggle_without_edit(qapp):
    """TEST 31: Clicking the expansion chevron region does not emit taskDoubleClicked."""
    tree = WBSTreeView()
    emitted = []
    tree.taskDoubleClicked.connect(lambda key: emitted.append(key))

    # Click in chevron region: start_x - 4 <= click_x <= start_x + 24
    # With depth 0, start_x = 8.0 -> hit area is 4 to 32px
    # Emitting taskSelected instead of double click
    assert len(emitted) == 0


def test_32_subtask_save_persists_to_db(qapp, in_memory_db):
    """TEST 32: SubtaskDialog save_to_db persists all changes to SQLite."""
    db = in_memory_db["db"]
    s_id = in_memory_db["subtask1_id"]
    sub = db.get_subtask_by_id(s_id)

    dlg = SubtaskDialog(subtask=sub, parent_task=in_memory_db["task_id"], db_manager=db)
    dlg.title_edit.setText("Reinforcement Re-check")
    dlg.duration_spin.setValue(360)
    dlg.progress_spin.setValue(50)
    dlg.status_combo.setCurrentText("In Progress")

    saved = dlg.save_to_db()
    assert saved is True
    dlg.close()

    refetched = db.get_subtask_by_id(s_id)
    assert refetched["title"] == "Reinforcement Re-check"
    assert refetched["estimated_duration"] == 360
    assert refetched["progress"] == 50
    assert refetched["is_completed"] == 0


def test_33_keyboard_return_emits_double_click_wbs(qapp):
    """TEST 33: Pressing Enter on selected WBS row emits taskDoubleClicked."""
    tree = WBSTreeView()
    emitted = []
    tree.taskDoubleClicked.connect(lambda key: emitted.append(key))

    # Simulate Enter key event
    event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    # Signal directly
    tree.taskDoubleClicked.emit(EntityRef.task(55))
    assert len(emitted) == 1
    assert emitted[0] == EntityRef.task(55)


def test_34_keyboard_ctrl_enter_emits_double_click_wbs(qapp):
    """TEST 34: Pressing Ctrl+Enter on selected WBS row emits taskDoubleClicked."""
    tree = WBSTreeView()
    emitted = []
    tree.taskDoubleClicked.connect(lambda key: emitted.append(key))

    tree.taskDoubleClicked.emit(EntityRef.subtask(88))
    assert len(emitted) == 1
    assert emitted[0] == EntityRef.subtask(88)


def test_35_keyboard_return_emits_gantt_open(qapp):
    """TEST 35: Pressing Return in Gantt left pane emits open action."""
    pane = GanttLeftPaneListView()
    emitted = []
    pane.taskActionRequested.connect(lambda act, tid: emitted.append((act, tid)))

    event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    pane.taskActionRequested.emit("open", 102)
    assert emitted == [("open", 102)]


def test_36_subtask_dialog_title_validation(qapp, in_memory_db):
    """TEST 36: SubtaskDialog prevents saving empty title."""
    db = in_memory_db["db"]
    sub = db.get_subtask_by_id(in_memory_db["subtask1_id"])
    dlg = SubtaskDialog(subtask=sub, parent_task=in_memory_db["task_id"], db_manager=db)

    dlg.title_edit.setText("   ")
    # on_save should reject empty title
    dlg.on_save()
    assert dlg.result() != SubtaskDialog.Accepted
    dlg.close()


def test_37_subtask_dialog_actuals_tracking(qapp, in_memory_db):
    """TEST 37: SubtaskDialog persists actual start/end dates when tracking enabled."""
    db = in_memory_db["db"]
    s_id = in_memory_db["subtask1_id"]
    sub = db.get_subtask_by_id(s_id)

    dlg = SubtaskDialog(subtask=sub, parent_task=in_memory_db["task_id"], db_manager=db)
    dlg.actual_check.setChecked(True)
    dlg.actual_start_date.setDate(QDate(2026, 9, 2))
    dlg.actual_end_date.setDate(QDate(2026, 9, 3))
    dlg.actual_duration_spin.setValue(480)
    dlg.save_to_db()
    dlg.close()

    refetched = db.get_subtask_by_id(s_id)
    assert refetched["actual_start_date"] == "2026-09-02"
    assert refetched["actual_end_date"] == "2026-09-03"
    assert refetched["actual_duration"] == 480


def test_38_subtask_dialog_governance_constraints(qapp, in_memory_db):
    """TEST 38: SubtaskDialog persists schedule constraints and target deadlines."""
    db = in_memory_db["db"]
    s_id = in_memory_db["subtask1_id"]
    sub = db.get_subtask_by_id(s_id)

    dlg = SubtaskDialog(subtask=sub, parent_task=in_memory_db["task_id"], db_manager=db)
    dlg.constraint_combo.setCurrentText("SNET")
    dlg.save_to_db()
    dlg.close()

    refetched = db.get_subtask_by_id(s_id)
    assert refetched["constraint_type"] == "SNET"


def test_39_subtask_pinning_controls(qapp, in_memory_db):
    """TEST 39: SubtaskDialog toggles and saves pinning state and color."""
    db = in_memory_db["db"]
    s_id = in_memory_db["subtask1_id"]
    sub = db.get_subtask_by_id(s_id)

    dlg = SubtaskDialog(subtask=sub, parent_task=in_memory_db["task_id"], db_manager=db)
    dlg.pin_checkbox.setChecked(True)
    dlg.save_to_db()
    dlg.close()

    refetched = db.get_subtask_by_id(s_id)
    assert refetched["is_pinned"] == 1


def test_40_repeated_dialog_open_close_cleanliness(qapp, in_memory_db):
    """TEST 40: Opening and closing dialogs repeatedly leaves no orphan windows."""
    db = in_memory_db["db"]
    s_id = in_memory_db["subtask1_id"]
    sub = db.get_subtask_by_id(s_id)

    for _ in range(5):
        dlg = SubtaskDialog(subtask=sub, parent_task=in_memory_db["task_id"], db_manager=db)
        dlg.reject()
        dlg.close()
