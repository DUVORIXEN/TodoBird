from __future__ import annotations

from todo_bird_app.services.wbs_rollup_service import WBSRollupService
from todo_bird_app.services.wbs_service import EntityRef, WBSHierarchySnapshot, WBSNode, WBSService


def node(key, parent, depth, code, status="Planned", milestone=False):
    return WBSNode(
        key=key,
        project_id=1,
        parent_key=parent,
        title=str(key),
        sibling_order=1,
        depth=depth,
        wbs_code=code,
        child_count=0,
        has_children=False,
        status=status,
        is_milestone=milestone,
        is_completed=status == "Completed",
        created_at="2026-01-01",
    )


def snapshot(nodes, children, roots):
    return WBSHierarchySnapshot(
        project_id=1,
        nodes_by_key=nodes,
        children_by_parent=children,
        root_keys=roots,
        orphaned_keys=[],
        total_nodes=len(nodes),
        max_depth=max((n.depth for n in nodes.values()), default=0),
        revision=1,
    )


def test_rollup_duration_is_elapsed_span_and_effort_is_additive():
    root = EntityRef.task(1)
    a = EntityRef.subtask(10)
    b = EntityRef.subtask(11)
    snap = snapshot(
        {
            root: node(root, None, 0, "1"),
            a: node(a, root, 1, "1.1"),
            b: node(b, root, 1, "1.2"),
        },
        {None: [root], root: [a, b], a: [], b: []},
        [root],
    )
    payloads = {
        root: {
            "planned_effort_minutes": 9999,
            "actual_duration": 9999,
        },
        a: {
            "planned_date": "2026-09-01",
            "planned_start_time": "08:00",
            "due_date": "2026-09-01",
            "planned_end_time": "10:00",
            "planned_effort_minutes": 120,
            "actual_duration": 30,
        },
        b: {
            "planned_date": "2026-09-03",
            "planned_start_time": "09:00",
            "due_date": "2026-09-03",
            "planned_end_time": "12:00",
            "planned_effort_minutes": 180,
            "actual_duration": 45,
        },
    }

    result = WBSRollupService.calculate(snap, payloads)[root]

    assert result.is_summary is True
    assert result.planned_start.strftime("%Y-%m-%d %H:%M") == "2026-09-01 08:00"
    assert result.planned_finish.strftime("%Y-%m-%d %H:%M") == "2026-09-03 12:00"
    assert result.planned_elapsed_minutes == 3120
    assert result.planned_elapsed_minutes != 300
    assert result.planned_effort_minutes == 300
    assert result.actual_effort_minutes == 75


def test_nested_summary_payload_is_not_double_counted():
    root = EntityRef.task(1)
    summary = EntityRef.subtask(20)
    a = EntityRef.subtask(21)
    b = EntityRef.subtask(22)
    snap = snapshot(
        {
            root: node(root, None, 0, "1"),
            summary: node(summary, root, 1, "1.1"),
            a: node(a, summary, 2, "1.1.1"),
            b: node(b, summary, 2, "1.1.2"),
        },
        {None: [root], root: [summary], summary: [a, b], a: [], b: []},
        [root],
    )
    payloads = {
        summary: {"planned_effort_minutes": 8000, "actual_duration": 8000, "progress": 99},
        a: {"planned_effort_minutes": 100, "actual_duration": 40, "progress": 25},
        b: {"planned_effort_minutes": 300, "actual_duration": 60, "progress": 75},
    }

    results = WBSRollupService.calculate(snap, payloads)

    assert results[summary].leaf_count == 2
    assert results[root].leaf_count == 2
    assert results[summary].planned_effort_minutes == 400
    assert results[root].planned_effort_minutes == 400
    assert results[root].actual_effort_minutes == 100
    assert results[root].progress_percent == 62


def test_open_actual_summary_never_fabricates_finish():
    root = EntityRef.task(1)
    open_leaf = EntityRef.subtask(30)
    done_leaf = EntityRef.subtask(31)
    snap = snapshot(
        {
            root: node(root, None, 0, "1"),
            open_leaf: node(open_leaf, root, 1, "1.1", "In Progress"),
            done_leaf: node(done_leaf, root, 1, "1.2", "Completed"),
        },
        {None: [root], root: [open_leaf, done_leaf], open_leaf: [], done_leaf: []},
        [root],
    )
    payloads = {
        open_leaf: {
            "status": "In Progress",
            "actual_start_date": "2026-09-01",
            "actual_start_time": "08:00",
            "actual_duration": 120,
            "progress": 50,
        },
        done_leaf: {
            "status": "Completed",
            "actual_start_date": "2026-09-02",
            "actual_start_time": "09:00",
            "actual_end_date": "2026-09-02",
            "actual_end_time": "12:00",
            "actual_duration": 180,
            "progress": 100,
        },
    }

    result = WBSRollupService.calculate(snap, payloads)[root]

    assert result.actual_start.strftime("%Y-%m-%d %H:%M") == "2026-09-01 08:00"
    assert result.actual_finish is None
    assert result.actual_elapsed_minutes is None
    assert result.latest_actual_activity_at.strftime("%Y-%m-%d %H:%M") == "2026-09-02 12:00"
    assert result.actual_effort_minutes == 300


def test_progress_falls_back_to_completed_active_ratio_when_no_effort_or_progress():
    root = EntityRef.task(1)
    done_leaf = EntityRef.subtask(40)
    planned_leaf = EntityRef.subtask(41)
    snap = snapshot(
        {
            root: node(root, None, 0, "1"),
            done_leaf: node(done_leaf, root, 1, "1.1", "Completed"),
            planned_leaf: node(planned_leaf, root, 1, "1.2", "Planned"),
        },
        {None: [root], root: [done_leaf, planned_leaf], done_leaf: [], planned_leaf: []},
        [root],
    )

    result = WBSRollupService.calculate(snap, {done_leaf: {}, planned_leaf: {}})[root]

    assert result.progress_percent == 50
    assert result.completed_leaf_count == 1
    assert result.active_leaf_count == 2


def test_cancelled_leaf_excludes_planned_work_and_retains_actual_effort():
    root = EntityRef.task(1)
    active = EntityRef.subtask(50)
    cancelled = EntityRef.subtask(51)
    snap = snapshot(
        {
            root: node(root, None, 0, "1"),
            active: node(active, root, 1, "1.1", "In Progress"),
            cancelled: node(cancelled, root, 1, "1.2", "Cancelled"),
        },
        {None: [root], root: [active, cancelled], active: [], cancelled: []},
        [root],
    )
    payloads = {
        active: {"status": "In Progress", "planned_effort_minutes": 100, "actual_duration": 20, "progress": 40},
        cancelled: {"status": "Cancelled", "planned_effort_minutes": 900, "actual_duration": 55, "progress": 90},
    }

    result = WBSRollupService.calculate(snap, payloads)[root]

    assert result.planned_effort_minutes == 100
    assert result.actual_effort_minutes == 75
    assert result.progress_percent == 40
    assert result.cancelled_leaf_count == 1


def test_deep_wbs_hierarchy_build_and_descendants_are_iterative():
    raw_nodes = [
        {
            "key": EntityRef.task(1),
            "parent_key": None,
            "project_id": 1,
            "title": "Root",
            "position": 0,
        }
    ]
    parent = EntityRef.task(1)
    for index in range(1, 1201):
        key = EntityRef.subtask(index)
        raw_nodes.append(
            {
                "key": key,
                "parent_key": parent,
                "project_id": 1,
                "title": f"Level {index}",
                "position": index,
            }
        )
        parent = key

    snap = WBSService.build_from_raw(raw_nodes, project_id=1)

    assert snap.total_nodes == 1201
    assert snap.max_depth >= 1200
    assert len(WBSService.get_descendants(snap, EntityRef.task(1))) == 1200
