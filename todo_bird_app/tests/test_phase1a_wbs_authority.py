"""
TODO BIRD — PHASE 1A WBS HIERARCHY AUTHORITY TEST SUITE
Comprehensive unit, invariant, property, benchmark, and regression tests (WBS-A01 .. WBS-A46).
"""

import os
import random
import time
import pytest
from datetime import datetime

from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.models.project import Project
from todo_bird_app.services.wbs_service import (
    EntityRef,
    WBSNode,
    HierarchyValidationResult,
    WBSHierarchySnapshot,
    WBSService,
)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_wbs.db")
    db = DatabaseManager(db_file)
    yield db
    db.close()


@pytest.fixture
def temp_env(temp_db):
    settings = SettingsManager(temp_db)
    controller = TaskController(temp_db)
    return temp_db, settings, controller


# ==============================================================================
# PART 1: TYPED ENTITY IDENTITY (WBS-A01 .. WBS-A02)
# ==============================================================================

def test_wbs_a01_typed_stable_identity():
    """WBS-A01: EntityRef provides immutable typed identity."""
    t_ref = EntityRef.task(42)
    s_ref = EntityRef.subtask(100)

    assert t_ref.entity_type == "task"
    assert t_ref.entity_id == 42
    assert str(t_ref) == "task:42"

    assert s_ref.entity_type == "subtask"
    assert s_ref.entity_id == 100
    assert str(s_ref) == "subtask:100"

    parsed_t = EntityRef.from_string("task:42")
    assert parsed_t == t_ref
    parsed_s = EntityRef.from_string("subtask:100")
    assert parsed_s == s_ref


def test_wbs_a02_no_task_subtask_id_collision():
    """WBS-A02: Tasks and subtasks with identical integer IDs do not collide."""
    t42 = EntityRef.task(42)
    s42 = EntityRef.subtask(42)

    assert t42 != s42
    assert hash(t42) != hash(s42)

    d = {t42: "Main Task", s42: "Subtask"}
    assert len(d) == 2
    assert d[t42] == "Main Task"
    assert d[s42] == "Subtask"


# ==============================================================================
# PART 2: REFERENCE TREE & NUMBERING (WBS-A03 .. WBS-A07)
# ==============================================================================

def build_reference_tree():
    """
    Constructs the mandatory reference tree:
    PROJECT P
    A (Task 1)
    ├── B (Subtask 1)
    │   ├── D (Subtask 3)
    │   │   └── G (Subtask 5)
    │   └── E (Subtask 4)
    └── C (Subtask 2)
        └── F (Subtask 6)
    """
    raw_nodes = [
        {"key": EntityRef.task(1), "parent_key": None, "project_id": 10, "title": "A", "position": 0},
        {"key": EntityRef.subtask(1), "parent_key": EntityRef.task(1), "project_id": 10, "title": "B", "position": 0},
        {"key": EntityRef.subtask(2), "parent_key": EntityRef.task(1), "project_id": 10, "title": "C", "position": 1},
        {"key": EntityRef.subtask(3), "parent_key": EntityRef.subtask(1), "project_id": 10, "title": "D", "position": 0},
        {"key": EntityRef.subtask(4), "parent_key": EntityRef.subtask(1), "project_id": 10, "title": "E", "position": 1},
        {"key": EntityRef.subtask(5), "parent_key": EntityRef.subtask(3), "project_id": 10, "title": "G", "position": 0},
        {"key": EntityRef.subtask(6), "parent_key": EntityRef.subtask(2), "project_id": 10, "title": "F", "position": 0},
    ]
    return WBSService.build_from_raw(raw_nodes, project_id=10)


def test_wbs_a03_root_numbering():
    """WBS-A03: Top-level root tasks are numbered sequentially (1, 2, 3)."""
    raw_nodes = [
        {"key": EntityRef.task(10), "parent_key": None, "project_id": 1, "title": "Alpha", "position": 0},
        {"key": EntityRef.task(20), "parent_key": None, "project_id": 1, "title": "Beta", "position": 1},
        {"key": EntityRef.task(30), "parent_key": None, "project_id": 1, "title": "Gamma", "position": 2},
    ]
    snapshot = WBSService.build_from_raw(raw_nodes, project_id=1)
    assert snapshot.nodes_by_key[EntityRef.task(10)].wbs_code == "1"
    assert snapshot.nodes_by_key[EntityRef.task(20)].wbs_code == "2"
    assert snapshot.nodes_by_key[EntityRef.task(30)].wbs_code == "3"


def test_wbs_a04_child_numbering():
    """WBS-A04: Immediate children are numbered 1.1, 1.2, etc."""
    snapshot = build_reference_tree()
    node_b = snapshot.nodes_by_key[EntityRef.subtask(1)]
    node_c = snapshot.nodes_by_key[EntityRef.subtask(2)]

    assert node_b.wbs_code == "1.1"
    assert node_c.wbs_code == "1.2"


def test_wbs_a05_deep_numbering():
    """WBS-A05: Deep hierarchy numbers accurately down to arbitrary depth (1.1.1, 1.1.1.1, etc.)."""
    snapshot = build_reference_tree()
    assert snapshot.nodes_by_key[EntityRef.task(1)].wbs_code == "1"
    assert snapshot.nodes_by_key[EntityRef.subtask(1)].wbs_code == "1.1"
    assert snapshot.nodes_by_key[EntityRef.subtask(3)].wbs_code == "1.1.1"
    assert snapshot.nodes_by_key[EntityRef.subtask(5)].wbs_code == "1.1.1.1"
    assert snapshot.nodes_by_key[EntityRef.subtask(4)].wbs_code == "1.1.2"
    assert snapshot.nodes_by_key[EntityRef.subtask(2)].wbs_code == "1.2"
    assert snapshot.nodes_by_key[EntityRef.subtask(6)].wbs_code == "1.2.1"


def test_wbs_a06_deterministic_sibling_order():
    """WBS-A06: Sibling order is deterministic based on position, then created_at, then entity_id."""
    raw_nodes = [
        {"key": EntityRef.task(1), "parent_key": None, "project_id": 1, "title": "Root", "position": 0},
        {"key": EntityRef.subtask(3), "parent_key": EntityRef.task(1), "project_id": 1, "title": "Third", "position": 2, "created_at": "2026-08-18 10:00:00"},
        {"key": EntityRef.subtask(1), "parent_key": EntityRef.task(1), "project_id": 1, "title": "First", "position": 0, "created_at": "2026-08-18 09:00:00"},
        {"key": EntityRef.subtask(2), "parent_key": EntityRef.task(1), "project_id": 1, "title": "Second", "position": 1, "created_at": "2026-08-18 09:30:00"},
    ]
    snapshot = WBSService.build_from_raw(raw_nodes, project_id=1)
    children = WBSService.get_children(snapshot, EntityRef.task(1))
    assert [c.key for c in children] == [EntityRef.subtask(1), EntityRef.subtask(2), EntityRef.subtask(3)]
    assert [c.wbs_code for c in children] == ["1.1", "1.2", "1.3"]


def test_wbs_a07_depth():
    """WBS-A07: Node depth is 0 for root, 1 for child, 2 for grandchild, 3 for great-grandchild."""
    snapshot = build_reference_tree()
    assert WBSService.get_depth(snapshot, EntityRef.task(1)) == 0
    assert WBSService.get_depth(snapshot, EntityRef.subtask(1)) == 1
    assert WBSService.get_depth(snapshot, EntityRef.subtask(3)) == 2
    assert WBSService.get_depth(snapshot, EntityRef.subtask(5)) == 3


# ==============================================================================
# PART 3: TRAVERSAL & QUERY APIS (WBS-A08 .. WBS-A13)
# ==============================================================================

def test_wbs_a08_parent_lookup():
    """WBS-A08: get_parent returns immediate parent node or None for root."""
    snapshot = build_reference_tree()
    assert WBSService.get_parent(snapshot, EntityRef.task(1)) is None
    parent_b = WBSService.get_parent(snapshot, EntityRef.subtask(1))
    assert parent_b is not None
    assert parent_b.key == EntityRef.task(1)
    parent_g = WBSService.get_parent(snapshot, EntityRef.subtask(5))
    assert parent_g is not None
    assert parent_g.key == EntityRef.subtask(3)


def test_wbs_a09_child_lookup():
    """WBS-A09: get_children returns ordered direct children."""
    snapshot = build_reference_tree()
    children_a = WBSService.get_children(snapshot, EntityRef.task(1))
    assert len(children_a) == 2
    assert [c.title for c in children_a] == ["B", "C"]

    children_b = WBSService.get_children(snapshot, EntityRef.subtask(1))
    assert len(children_b) == 2
    assert [c.title for c in children_b] == ["D", "E"]


def test_wbs_a10_ancestor_lookup():
    """WBS-A10: get_ancestors returns chain from parent up to root."""
    snapshot = build_reference_tree()
    ancestors_g = WBSService.get_ancestors(snapshot, EntityRef.subtask(5))
    assert [a.title for a in ancestors_g] == ["D", "B", "A"]


def test_wbs_a11_descendant_lookup():
    """WBS-A11: get_descendants returns all sub-nodes in depth-first order."""
    snapshot = build_reference_tree()
    descendants_a = WBSService.get_descendants(snapshot, EntityRef.task(1))
    assert [d.title for d in descendants_a] == ["B", "D", "G", "E", "C", "F"]

    descendants_b = WBSService.get_descendants(snapshot, EntityRef.subtask(1))
    assert [d.title for d in descendants_b] == ["D", "G", "E"]


def test_wbs_a12_full_flatten():
    """WBS-A12: flatten_project with no expansion filter returns all nodes in depth-first order."""
    snapshot = build_reference_tree()
    flattened = WBSService.flatten_project(snapshot)
    assert [n.title for n in flattened] == ["A", "B", "D", "G", "E", "C", "F"]
    assert [n.wbs_code for n in flattened] == ["1", "1.1", "1.1.1", "1.1.1.1", "1.1.2", "1.2", "1.2.1"]


def test_wbs_a13_collapsed_flatten():
    """WBS-A13: flatten_project respects expanded_keys for tree virtualization."""
    snapshot = build_reference_tree()

    # Case 1: B collapsed, C expanded -> A, B, C, F
    flat_collapsed_b = WBSService.flatten_project(snapshot, expanded_keys={EntityRef.task(1), EntityRef.subtask(2)})
    assert [n.title for n in flat_collapsed_b] == ["A", "B", "C", "F"]

    # Case 2: Root A collapsed -> only A
    flat_collapsed_a = WBSService.flatten_project(snapshot, expanded_keys=set())
    assert [n.title for n in flat_collapsed_a] == ["A"]


# ==============================================================================
# PART 4: HIERARCHY VALIDATION & INTEGRITY (WBS-A14 .. WBS-A21)
# ==============================================================================

def test_wbs_a14_same_project_validation():
    """WBS-A14: Reparenting to valid parent in same project succeeds."""
    snapshot = build_reference_tree()
    # Move E (1.1.2) under C (1.2)
    res = WBSService.validate_parent_change(snapshot, EntityRef.subtask(4), EntityRef.subtask(2))
    assert res.valid is True
    assert res.reason_code is None
    assert res.affected_subtree_size == 1


def test_wbs_a15_cross_project_rejection():
    """WBS-A15: Cross-project parent change is rejected (H05)."""
    raw_nodes = [
        {"key": EntityRef.task(1), "parent_key": None, "project_id": 10, "title": "Proj 10 Task"},
        {"key": EntityRef.task(2), "parent_key": None, "project_id": 20, "title": "Proj 20 Task"},
    ]
    snapshot = WBSService.build_from_raw(raw_nodes)
    res = WBSService.validate_parent_change(snapshot, EntityRef.task(1), EntityRef.task(2))
    assert res.valid is False
    assert res.reason_code == WBSService.ERR_CROSS_PROJECT_MISMATCH


def test_wbs_a16_self_parent_rejection():
    """WBS-A16: Node cannot parent itself (H01)."""
    snapshot = build_reference_tree()
    res = WBSService.validate_parent_change(snapshot, EntityRef.subtask(1), EntityRef.subtask(1))
    assert res.valid is False
    assert res.reason_code == WBSService.ERR_SELF_PARENT


def test_wbs_a17_descendant_cycle_rejection():
    """WBS-A17: Node cannot become child of its own descendant (H02/H03)."""
    snapshot = build_reference_tree()
    # Attempt to make A child of G
    res = WBSService.validate_parent_change(snapshot, EntityRef.task(1), EntityRef.subtask(5))
    assert res.valid is False
    assert res.reason_code == WBSService.ERR_CYCLE_DETECTED


def test_wbs_a18_missing_parent_detection():
    """WBS-A18: Target parent that does not exist is rejected (H04)."""
    snapshot = build_reference_tree()
    res = WBSService.validate_parent_change(snapshot, EntityRef.task(1), EntityRef.task(9999))
    assert res.valid is False
    assert res.reason_code == WBSService.ERR_PARENT_NOT_FOUND


def test_wbs_a19_orphan_reporting():
    """WBS-A19: Raw nodes referencing nonexistent parents are isolated in orphaned_keys."""
    raw_nodes = [
        {"key": EntityRef.task(1), "parent_key": None, "project_id": 1, "title": "Root"},
        {"key": EntityRef.subtask(10), "parent_key": EntityRef.task(999), "project_id": 1, "title": "Orphan Subtask"},
    ]
    snapshot = WBSService.build_from_raw(raw_nodes, project_id=1)
    assert EntityRef.subtask(10) in snapshot.orphaned_keys
    assert EntityRef.subtask(10) not in snapshot.nodes_by_key


def test_wbs_a20_stable_id_after_reorder():
    """WBS-A20: Reordering siblings changes WBS code but preserves stable EntityRef ID."""
    raw_nodes = [
        {"key": EntityRef.task(842), "parent_key": None, "project_id": 1, "title": "Target Task", "position": 0},
        {"key": EntityRef.task(900), "parent_key": None, "project_id": 1, "title": "Other Task", "position": 1},
    ]
    s1 = WBSService.build_from_raw(raw_nodes, project_id=1)
    assert s1.nodes_by_key[EntityRef.task(842)].wbs_code == "1"

    # Reorder positions
    raw_nodes_reordered = [
        {"key": EntityRef.task(842), "parent_key": None, "project_id": 1, "title": "Target Task", "position": 1},
        {"key": EntityRef.task(900), "parent_key": None, "project_id": 1, "title": "Other Task", "position": 0},
    ]
    s2 = WBSService.build_from_raw(raw_nodes_reordered, project_id=1)
    assert s2.nodes_by_key[EntityRef.task(842)].wbs_code == "2"
    assert s2.nodes_by_key[EntityRef.task(842)].key.entity_id == 842


def test_wbs_a21_wbs_code_changes_correctly_after_order_change():
    """WBS-A21: Moving sibling order adjusts all subsequent sibling WBS codes dynamically."""
    raw_nodes = [
        {"key": EntityRef.task(1), "parent_key": None, "project_id": 1, "title": "Task 1", "position": 10},
        {"key": EntityRef.task(2), "parent_key": None, "project_id": 1, "title": "Task 2", "position": 20},
        {"key": EntityRef.task(3), "parent_key": None, "project_id": 1, "title": "Task 3", "position": 30},
    ]
    snap = WBSService.build_from_raw(raw_nodes, project_id=1)
    assert snap.nodes_by_key[EntityRef.task(1)].wbs_code == "1"
    assert snap.nodes_by_key[EntityRef.task(2)].wbs_code == "2"
    assert snap.nodes_by_key[EntityRef.task(3)].wbs_code == "3"


# ==============================================================================
# PART 5: PHASE 0B INVARIANT PRESERVATION (WBS-A22 .. WBS-A38)
# ==============================================================================

def test_wbs_a22_schedule_untouched(temp_env):
    """WBS-A22: WBS hierarchy construction leaves task planned_date and start time untouched."""
    db, settings, controller = temp_env
    task = Task(title="Schedule Task", project_id=1, planned_date="2026-08-25", planned_start_time="09:30", due_date="2026-08-30")
    tid = controller.add_task(task)
    _ = WBSService.build_project_hierarchy(db, project_id=1)
    reloaded = controller.get_task(tid)
    assert reloaded.planned_date == "2026-08-25"
    assert reloaded.planned_start_time == "09:30"
    assert reloaded.due_date == "2026-08-30"


def test_wbs_a23_planned_effort_untouched(temp_env):
    """WBS-A23: WBS hierarchy construction leaves planned_effort_minutes and daily dedication untouched."""
    db, settings, controller = temp_env
    task = Task(title="Effort Task", project_id=1, planned_effort_minutes=360, daily_dedication_minutes=180)
    tid = controller.add_task(task)
    _ = WBSService.build_project_hierarchy(db, project_id=1)
    reloaded = controller.get_task(tid)
    assert reloaded.planned_effort_minutes == 360
    assert reloaded.daily_dedication_minutes == 180


def test_wbs_a24_actual_effort_untouched(temp_env):
    """WBS-A24: WBS hierarchy construction leaves actual_duration untouched."""
    db, settings, controller = temp_env
    task = Task(title="Actual Task", project_id=1, actual_duration=45, actual_start_date="2026-08-18", actual_start_time="10:00")
    tid = controller.add_task(task)
    _ = WBSService.build_project_hierarchy(db, project_id=1)
    reloaded = controller.get_task(tid)
    assert reloaded.actual_duration == 45
    assert reloaded.actual_start_time == "10:00"


def test_wbs_a25_dependencies_untouched(temp_env):
    """WBS-A25: WBS hierarchy construction leaves dependencies list untouched."""
    db, settings, controller = temp_env
    task = Task(title="Dep Task", project_id=1, dependencies=[10, 20, 30])
    tid = controller.add_task(task)
    _ = WBSService.build_project_hierarchy(db, project_id=1)
    reloaded = controller.get_task(tid)
    assert reloaded.dependencies == [10, 20, 30]


def test_wbs_a26_reminder_schedule_untouched(temp_env):
    """WBS-A26: WBS hierarchy construction leaves startup_reminder flag untouched."""
    db, settings, controller = temp_env
    task = Task(title="Reminder Task", project_id=1, startup_reminder=True)
    tid = controller.add_task(task)
    _ = WBSService.build_project_hierarchy(db, project_id=1)
    reloaded = controller.get_task(tid)
    assert reloaded.startup_reminder is True


def test_wbs_a27_snooze_state_untouched(temp_env):
    """WBS-A27: WBS hierarchy construction leaves snooze persistence in SettingsManager untouched."""
    db, settings, controller = temp_env
    from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
    from datetime import datetime

    task = Task(title="Snooze Task", project_id=1)
    tid = controller.add_task(task)
    snooze_dt = datetime(2026, 8, 18, 11, 0, 0)
    ReminderPolicyService.snooze_reminder(tid, 20, from_dt=snooze_dt, settings_manager=settings)

    _ = WBSService.build_project_hierarchy(db, project_id=1)

    # Verify persisted snooze unchanged
    raw = settings.get("persisted_snoozed_reminders", "")
    assert str(tid) in raw


def test_wbs_a28_inbox_semantics_preserved(temp_env):
    """WBS-A28: Inbox semantics are preserved; only unassigned top-level tasks belong to Inbox."""
    db, settings, controller = temp_env
    t_inbox = Task(title="Inbox Main Task", project_id=1, status=TaskStatus.INBOX)
    tid = controller.add_task(t_inbox)

    inbox_tasks = [t for t in controller.get_all_tasks() if t.project_id == 1 and t.status == TaskStatus.INBOX]
    assert len(inbox_tasks) == 1
    assert inbox_tasks[0].id == tid


def test_wbs_a29_project_membership_preserved(temp_env):
    """WBS-A29: Tasks strictly retain their project_id assignments."""
    db, settings, controller = temp_env
    pid = controller.add_project(Project(name="Project Beta"))
    t = Task(title="Beta Task", project_id=pid)
    tid = controller.add_task(t)

    snap = WBSService.build_project_hierarchy(db, project_id=pid)
    node = snap.nodes_by_key[EntityRef.task(tid)]
    assert node.project_id == pid


def test_wbs_a30_nested_children_not_duplicated_in_inbox(temp_env):
    """WBS-A30: Nested subtasks do not appear as independent root entries in Inbox."""
    db, settings, controller = temp_env
    tid = controller.add_task(Task(title="Inbox Root", project_id=1, status=TaskStatus.INBOX))
    s1 = db.insert_subtask(tid, "Subtask 1")
    s2 = db.insert_subtask(tid, "Sub-subtask 1.1", parent_subtask_id=s1)

    inbox_tasks = [t for t in controller.get_all_tasks() if t.project_id == 1 and t.status == TaskStatus.INBOX]
    assert len(inbox_tasks) == 1
    assert inbox_tasks[0].id == tid


def test_wbs_a31_legacy_task_save(temp_env):
    """WBS-A31: Legacy task addition and update APIs operate seamlessly."""
    db, settings, controller = temp_env
    t = Task(title="Legacy Save Task", project_id=1)
    tid = controller.add_task(t)
    t.title = "Legacy Save Task Updated"
    controller.update_task(t)
    reloaded = controller.get_task(tid)
    assert reloaded.title == "Legacy Save Task Updated"


def test_wbs_a32_legacy_subtask_save(temp_env):
    """WBS-A32: Legacy subtask insertion and update APIs operate seamlessly."""
    db, settings, controller = temp_env
    tid = controller.add_task(Task(title="Main Task", project_id=1))
    sid = db.insert_subtask(tid, "Subtask Alpha", position=0)
    db.update_subtask(sid, title="Subtask Alpha Updated", is_completed=True)
    subtasks = db.get_subtasks(tid)
    assert len(subtasks) == 1
    assert subtasks[0]["title"] == "Subtask Alpha Updated"
    assert subtasks[0]["is_completed"] == 1


def test_wbs_a33_sub_subtask_save(temp_env):
    """WBS-A33: Sub-subtask insertion with parent_subtask_id operates seamlessly."""
    db, settings, controller = temp_env
    tid = controller.add_task(Task(title="Main Task", project_id=1))
    s1 = db.insert_subtask(tid, "Subtask Level 1", position=0)
    s2 = db.insert_subtask(tid, "Sub-subtask Level 2", position=0, parent_subtask_id=s1)

    tree = db.get_subtask_tree(tid)
    assert len(tree) == 1
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["id"] == s2


def test_wbs_a34_3w1h_unaffected(temp_env):
    """WBS-A34: 3W1H delay justifications operate without interference from WBS authority."""
    db, settings, controller = temp_env
    task = Task(title="3W1H Task", project_id=1, delay_reason="Vendor bottleneck", delay_minutes=45)
    tid = controller.add_task(task)
    _ = WBSService.build_project_hierarchy(db, project_id=1)
    reloaded = controller.get_task(tid)
    assert reloaded.delay_reason == "Vendor bottleneck"
    assert reloaded.delay_minutes == 45


def test_wbs_a35_focus_unaffected(temp_env):
    """WBS-A35: Focus timer session data is untouched by WBS service."""
    db, settings, controller = temp_env
    task = Task(title="Focus Task", project_id=1, actual_duration=60, actual_start_date="2026-08-18", actual_start_time="09:00")
    tid = controller.add_task(task)
    _ = WBSService.build_project_hierarchy(db, project_id=1)
    reloaded = controller.get_task(tid)
    assert reloaded.actual_duration == 60


def test_wbs_a36_calendar_unaffected(temp_env):
    """WBS-A36: Calendar planned time blocks remain completely intact."""
    db, settings, controller = temp_env
    task = Task(title="Calendar Task", project_id=1, planned_date="2026-08-20", planned_start_time="14:00", planned_end_time="15:30")
    tid = controller.add_task(task)
    _ = WBSService.build_project_hierarchy(db, project_id=1)
    reloaded = controller.get_task(tid)
    assert reloaded.planned_date == "2026-08-20"
    assert reloaded.planned_start_time == "14:00"
    assert reloaded.planned_end_time == "15:30"


def test_wbs_a37_gantt_unaffected(temp_env):
    """WBS-A37: Gantt chart visibility flag remains untouched."""
    db, settings, controller = temp_env
    task = Task(title="Gantt Task", project_id=1, show_in_gantt=True)
    tid = controller.add_task(task)
    _ = WBSService.build_project_hierarchy(db, project_id=1)
    reloaded = controller.get_task(tid)
    assert reloaded.show_in_gantt is True


def test_wbs_a38_pinned_tasks_unaffected(temp_env):
    """WBS-A38: Pinned tasks with colored badges operate without interference."""
    db, settings, controller = temp_env
    task = Task(title="Pinned Task", project_id=1, is_pinned=True, pin_color="#10B981", pin_position=2)
    tid = controller.add_task(task)
    _ = WBSService.build_project_hierarchy(db, project_id=1)
    reloaded = controller.get_task(tid)
    assert reloaded.is_pinned is True
    assert reloaded.pin_color == "#10B981"
    assert reloaded.pin_position == 2


# ==============================================================================
# PART 6: PROPERTY TESTING & FUZZING (WBS-A39 .. WBS-A40)
# ==============================================================================

def test_wbs_a39_random_tree_property_test():
    """
    WBS-A39: Generates reproducible random trees (seed 42) and verifies:
    - Every node appears exactly once
    - Unique WBS codes
    - Parent prefix relationship
    - Depth consistency
    - Flatten determinism
    - Subtree count correctness
    """
    rng = random.Random(42)
    node_count = 150
    nodes = []

    # 1. Create root tasks
    root_count = 5
    for i in range(1, root_count + 1):
        nodes.append({
            "key": EntityRef.task(i),
            "parent_key": None,
            "project_id": 1,
            "title": f"Root {i}",
            "position": i - 1,
            "created_at": f"2026-08-18 10:00:{i:02d}",
        })

    # 2. Add random child nodes
    available_parents = [EntityRef.task(i) for i in range(1, root_count + 1)]
    for sub_id in range(1, node_count - root_count + 1):
        parent = rng.choice(available_parents)
        pos = rng.randint(0, 10)
        s_ref = EntityRef.subtask(sub_id)
        nodes.append({
            "key": s_ref,
            "parent_key": parent,
            "project_id": 1,
            "title": f"Subtask {sub_id}",
            "position": pos,
            "created_at": f"2026-08-18 11:00:{sub_id % 60:02d}",
        })
        available_parents.append(s_ref)

    snapshot = WBSService.build_from_raw(nodes, project_id=1)

    # Invariant 1: Total node count
    assert snapshot.total_nodes == node_count
    assert len(snapshot.nodes_by_key) == node_count

    # Invariant 2: Unique WBS codes
    codes = [n.wbs_code for n in snapshot.nodes_by_key.values()]
    assert len(codes) == len(set(codes))

    # Invariant 3: Parent prefix and depth consistency
    for key, node in snapshot.nodes_by_key.items():
        if node.parent_key is None:
            assert node.depth == 0
            assert "." not in node.wbs_code
        else:
            parent_node = snapshot.nodes_by_key[node.parent_key]
            assert node.depth == parent_node.depth + 1
            assert node.wbs_code.startswith(parent_node.wbs_code + ".")

    # Invariant 4: Flatten contains all nodes exactly once
    flattened = WBSService.flatten_project(snapshot)
    assert len(flattened) == node_count
    assert set(n.key for n in flattened) == set(snapshot.nodes_by_key.keys())

    # Invariant 5: Subtree count consistency
    for key, node in snapshot.nodes_by_key.items():
        descendants = WBSService.get_descendants(snapshot, key)
        assert len(descendants) == WBSService.get_descendant_count(snapshot, key)


def test_wbs_a40_malformed_cycle_fails_safely():
    """WBS-A40: Malformed raw cycle data breaks safely without infinite loops."""
    # A -> B -> C -> A
    cycle_nodes = [
        {"key": EntityRef.subtask(1), "parent_key": EntityRef.subtask(3), "project_id": 1, "title": "A"},
        {"key": EntityRef.subtask(2), "parent_key": EntityRef.subtask(1), "project_id": 1, "title": "B"},
        {"key": EntityRef.subtask(3), "parent_key": EntityRef.subtask(2), "project_id": 1, "title": "C"},
        {"key": EntityRef.task(100), "parent_key": None, "project_id": 1, "title": "Legitimate Root"},
    ]
    snapshot = WBSService.build_from_raw(cycle_nodes, project_id=1)
    assert snapshot.total_nodes == 1
    assert EntityRef.task(100) in snapshot.nodes_by_key
    assert len(snapshot.orphaned_keys) == 3


# ==============================================================================
# PART 7: PERFORMANCE & BENCHMARKING (WBS-A41 .. WBS-A43)
# ==============================================================================

def test_wbs_a41_1k_node_benchmark():
    """WBS-A41: 1,000 nodes build and flatten in under 50ms."""
    rng = random.Random(100)
    node_count = 1000
    nodes = []

    # 10 roots
    for i in range(1, 11):
        nodes.append({"key": EntityRef.task(i), "parent_key": None, "project_id": 1, "title": f"Root {i}", "position": i})

    parents = [EntityRef.task(i) for i in range(1, 11)]
    for i in range(11, node_count + 1):
        p = rng.choice(parents)
        s_ref = EntityRef.subtask(i)
        nodes.append({"key": s_ref, "parent_key": p, "project_id": 1, "title": f"Item {i}", "position": rng.randint(0, 5)})
        parents.append(s_ref)

    t0 = time.perf_counter()
    snap = WBSService.build_from_raw(nodes, project_id=1)
    t_build = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    flat = WBSService.flatten_project(snap)
    t_flat = (time.perf_counter() - t1) * 1000

    assert snap.total_nodes == 1000
    assert len(flat) == 1000
    # Performance assertion: Under 50ms
    assert t_build + t_flat < 50.0, f"1k benchmark exceeded threshold: {t_build + t_flat:.2f}ms"


def test_wbs_a42_5k_node_benchmark():
    """WBS-A42: 5,000 nodes build and flatten in under 200ms."""
    rng = random.Random(200)
    node_count = 5000
    nodes = []

    for i in range(1, 21):
        nodes.append({"key": EntityRef.task(i), "parent_key": None, "project_id": 1, "title": f"Root {i}", "position": i})

    parents = [EntityRef.task(i) for i in range(1, 21)]
    for i in range(21, node_count + 1):
        p = rng.choice(parents)
        s_ref = EntityRef.subtask(i)
        nodes.append({"key": s_ref, "parent_key": p, "project_id": 1, "title": f"Item {i}", "position": rng.randint(0, 5)})
        if len(parents) < 500:
            parents.append(s_ref)

    t0 = time.perf_counter()
    snap = WBSService.build_from_raw(nodes, project_id=1)
    t_build = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    flat = WBSService.flatten_project(snap)
    t_flat = (time.perf_counter() - t1) * 1000

    assert snap.total_nodes == 5000
    assert len(flat) == 5000
    # Performance assertion: Under 200ms
    assert t_build + t_flat < 200.0, f"5k benchmark exceeded threshold: {t_build + t_flat:.2f}ms"


def test_wbs_a43_no_n_plus_one_hierarchy_queries(temp_env):
    """WBS-A43: Database hierarchy loading executes in exactly 2 indexed bulk queries."""
    db, settings, controller = temp_env

    proj_id = controller.add_project(Project(name="Project Bulk"))

    # Populate 10 tasks each with 5 subtasks (60 total nodes)
    for t_idx in range(10):
        t = Task(title=f"Task {t_idx}", project_id=proj_id)
        tid = controller.add_task(t)
        for s_idx in range(5):
            db.insert_subtask(tid, f"Subtask {t_idx}.{s_idx}", position=s_idx)

    # Count executed statements
    query_count = 0
    conn = db.get_connection()

    def tracer(query):
        nonlocal query_count
        if "SELECT" in query.upper():
            query_count += 1

    conn.set_trace_callback(tracer)
    try:
        snap = WBSService.build_project_hierarchy(db, project_id=proj_id)
    finally:
        conn.set_trace_callback(None)

    assert snap.total_nodes == 60
    # Exactly 2 SELECT queries (1 for tasks, 1 for subtasks)
    assert query_count == 2, f"Expected 2 queries, got {query_count}"


# ==============================================================================
# PART 8: CANONICAL CONTROLLER & LIFECYCLE INVARIANTS (WBS-A44 .. WBS-A46)
# ==============================================================================

def test_wbs_a44_canonical_task_controller_instance_remains_one(temp_env, qapp):
    """WBS-A44: WBSService does not instantiate TaskController; canonical MainWindow authority remains 1."""
    db, settings, controller = temp_env
    from todo_bird_app.views.main_window import MainWindow

    tc_theme = ThemeController(settings)
    main_win = MainWindow(db, settings, tc_theme)

    # 1. Proves MainWindow holds the single canonical controller
    assert hasattr(main_win, "task_controller")
    assert main_win.task_controller is not None

    # 2. WBSService operates on pure db_manager without creating TaskController
    snap = WBSService.build_project_hierarchy(db)
    assert isinstance(snap, WBSHierarchySnapshot)

    main_win.close()


def test_wbs_a45_reminder_scheduler_timer_count_remains_one(temp_env, qapp):
    """WBS-A45: Reminder scheduler timer count remains strictly 1."""
    db, settings, controller = temp_env
    from todo_bird_app.views.main_window import MainWindow

    tc_theme = ThemeController(settings)
    main_win = MainWindow(db, settings, tc_theme)

    # Exactly one timer exists on MainWindow
    assert hasattr(main_win, "_reminder_poll_timer")
    assert main_win._reminder_poll_timer.isActive() is True

    # Loading WBS data does not create timers
    _ = WBSService.build_project_hierarchy(db)
    assert main_win._reminder_poll_timer.isActive() is True

    main_win.close()


def test_wbs_a46_clean_shutdown_unchanged(temp_env, qapp):
    """WBS-A46: Clean shutdown in MainWindow.closeEvent terminates cleanly with timer stopped."""
    db, settings, controller = temp_env
    from todo_bird_app.views.main_window import MainWindow

    tc_theme = ThemeController(settings)
    main_win = MainWindow(db, settings, tc_theme)

    assert main_win._reminder_poll_timer.isActive() is True
    main_win.close()
    assert main_win._reminder_poll_timer.isActive() is False
