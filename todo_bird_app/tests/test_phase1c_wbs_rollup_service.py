
from todo_bird_app.services.wbs_service import (
    EntityRef,
    WBSNode,
    WBSHierarchySnapshot,
)
from todo_bird_app.services.wbs_rollup_service import (
    WBSRollupService,
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


def test_parent_rollup_schedule_effort_actual_and_weighted_progress():
    p = EntityRef.task(1)
    a = EntityRef.subtask(10)
    b = EntityRef.subtask(11)

    nodes = {
        p: node(p, None, 0, "1"),
        a: node(a, p, 1, "1.1", "In Progress"),
        b: node(b, p, 1, "1.2", "Completed"),
    }

    snap = snapshot(
        nodes,
        {
            None: [p],
            p: [a, b],
            a: [],
            b: [],
        },
        [p],
    )

    payloads = {
        a: {
            "status": "In Progress",
            "planned_date": "2026-08-13",
            "due_date": "2026-08-14",
            "planned_start_time": "08:00",
            "planned_end_time": "12:00",
            "planned_effort_minutes": 240,
            "actual_duration": 90,
            "actual_start_date": "2026-08-13",
            "actual_start_time": "09:00",
            "progress": 50,
        },
        b: {
            "status": "Completed",
            "planned_date": "2026-08-15",
            "due_date": "2026-08-15",
            "planned_start_time": "10:00",
            "planned_end_time": "18:00",
            "planned_effort_minutes": 120,
            "actual_duration": 130,
            "actual_start_date": "2026-08-15",
            "actual_start_time": "10:00",
            "actual_end_date": "2026-08-15",
            "actual_end_time": "17:00",
            "progress": 100,
        },
    }

    r = WBSRollupService.calculate(snap, payloads)[p]

    assert r.is_summary is True
    assert r.leaf_count == 2
    assert r.planned_effort_minutes == 360
    assert r.actual_effort_minutes == 220

    assert r.planned_start.strftime("%Y-%m-%d %H:%M") == "2026-08-13 08:00"
    assert r.planned_finish.strftime("%Y-%m-%d %H:%M") == "2026-08-15 18:00"

    # (50*240 + 100*120) / 360 = 66.67 -> 67
    assert r.progress == 67

    # One leaf still In Progress: summary actual finish MUST remain open.
    assert r.actual_start.strftime("%Y-%m-%d %H:%M") == "2026-08-13 09:00"
    assert r.actual_finish is None
    assert r.actual_elapsed_minutes is None
    assert r.all_terminal is False


def test_nested_summaries_do_not_double_count():
    root = EntityRef.task(1)
    summary = EntityRef.subtask(2)
    a = EntityRef.subtask(3)
    b = EntityRef.subtask(4)

    nodes = {
        root: node(root, None, 0, "1"),
        summary: node(summary, root, 1, "1.1"),
        a: node(a, summary, 2, "1.1.1"),
        b: node(b, summary, 2, "1.1.2"),
    }

    snap = snapshot(
        nodes,
        {
            None: [root],
            root: [summary],
            summary: [a, b],
            a: [],
            b: [],
        },
        [root],
    )

    payloads = {
        # Deliberately give summary its own effort. It must NOT be counted.
        summary: {
            "planned_effort_minutes": 9999,
            "actual_duration": 9999,
        },
        a: {
            "planned_effort_minutes": 100,
            "actual_duration": 40,
            "progress": 20,
        },
        b: {
            "planned_effort_minutes": 300,
            "actual_duration": 60,
            "progress": 80,
        },
    }

    results = WBSRollupService.calculate(snap, payloads)

    assert results[summary].planned_effort_minutes == 400
    assert results[root].planned_effort_minutes == 400

    assert results[summary].actual_effort_minutes == 100
    assert results[root].actual_effort_minutes == 100

    assert results[root].leaf_count == 2

    # (20*100 + 80*300) / 400 = 65
    assert results[root].progress == 65


def test_cancelled_excluded_from_progress_but_actual_effort_retained():
    p = EntityRef.task(1)
    active = EntityRef.subtask(2)
    cancelled = EntityRef.subtask(3)

    nodes = {
        p: node(p, None, 0, "1"),
        active: node(active, p, 1, "1.1", "In Progress"),
        cancelled: node(cancelled, p, 1, "1.2", "Cancelled"),
    }

    snap = snapshot(
        nodes,
        {
            None: [p],
            p: [active, cancelled],
            active: [],
            cancelled: [],
        },
        [p],
    )

    payloads = {
        active: {
            "status": "In Progress",
            "planned_effort_minutes": 100,
            "actual_duration": 30,
            "progress": 40,
        },
        cancelled: {
            "status": "Cancelled",
            "planned_effort_minutes": 900,
            "actual_duration": 55,
            "progress": 90,
        },
    }

    r = WBSRollupService.calculate(snap, payloads)[p]

    assert r.progress == 40
    assert r.actual_effort_minutes == 85
    assert r.cancelled_leaf_count == 1
    assert r.active_leaf_count == 1


def test_zero_effort_fallback_is_deterministic_average():
    p = EntityRef.task(1)
    a = EntityRef.subtask(2)
    b = EntityRef.subtask(3)

    nodes = {
        p: node(p, None, 0, "1"),
        a: node(a, p, 1, "1.1"),
        b: node(b, p, 1, "1.2"),
    }

    snap = snapshot(
        nodes,
        {
            None: [p],
            p: [a, b],
            a: [],
            b: [],
        },
        [p],
    )

    payloads = {
        a: {
            "planned_effort_minutes": 0,
            "progress": 20,
        },
        b: {
            "planned_effort_minutes": 0,
            "progress": 80,
        },
    }

    assert WBSRollupService.calculate(snap, payloads)[p].progress == 50


def test_milestone_is_zero_or_one_hundred():
    m1 = EntityRef.task(1)
    m2 = EntityRef.task(2)

    nodes = {
        m1: node(m1, None, 0, "1", "Planned", True),
        m2: node(m2, None, 0, "2", "Completed", True),
    }

    snap = snapshot(
        nodes,
        {
            None: [m1, m2],
            m1: [],
            m2: [],
        },
        [m1, m2],
    )

    payloads = {
        m1: {
            "status": "Planned",
            "progress": 85,
        },
        m2: {
            "status": "Completed",
            "progress": 3,
        },
    }

    results = WBSRollupService.calculate(snap, payloads)

    assert results[m1].progress == 0
    assert results[m2].progress == 100


def test_actual_finish_only_after_all_relevant_leaf_work_terminal():
    p = EntityRef.task(1)
    a = EntityRef.subtask(2)
    b = EntityRef.subtask(3)

    nodes = {
        p: node(p, None, 0, "1"),
        a: node(a, p, 1, "1.1", "Completed"),
        b: node(b, p, 1, "1.2", "Cancelled"),
    }

    snap = snapshot(
        nodes,
        {
            None: [p],
            p: [a, b],
            a: [],
            b: [],
        },
        [p],
    )

    payloads = {
        a: {
            "status": "Completed",
            "actual_start_date": "2026-08-10",
            "actual_start_time": "08:00",
            "actual_end_date": "2026-08-12",
            "actual_end_time": "16:00",
            "actual_duration": 480,
        },
        b: {
            "status": "Cancelled",
            "actual_duration": 25,
        },
    }

    r = WBSRollupService.calculate(snap, payloads)[p]

    assert r.all_terminal is True
    assert r.actual_finish_complete is True
    assert r.actual_start.strftime("%Y-%m-%d %H:%M") == "2026-08-10 08:00"
    assert r.actual_finish.strftime("%Y-%m-%d %H:%M") == "2026-08-12 16:00"

    # Pure calendar elapsed: 56 hours.
    assert r.actual_elapsed_minutes == 56 * 60

    # Work effort remains a completely separate authority.
    assert r.actual_effort_minutes == 505


def test_completed_leaf_missing_actual_end_keeps_parent_finish_open():
    p = EntityRef.task(1)
    a = EntityRef.subtask(2)

    nodes = {
        p: node(p, None, 0, "1"),
        a: node(a, p, 1, "1.1", "Completed"),
    }

    snap = snapshot(
        nodes,
        {
            None: [p],
            p: [a],
            a: [],
        },
        [p],
    )

    payloads = {
        a: {
            "status": "Completed",
            "actual_start_date": "2026-08-10",
            "actual_start_time": "08:00",
            # No explicit end.
            "actual_duration": 60,
        },
    }

    r = WBSRollupService.calculate(snap, payloads)[p]

    assert r.all_terminal is True
    assert r.actual_finish_complete is False
    assert r.actual_finish is None
    assert r.actual_elapsed_minutes is None


def test_parent_elapsed_is_envelope_not_sum_of_child_durations():
    p = EntityRef.task(1)
    a = EntityRef.subtask(2)
    b = EntityRef.subtask(3)

    nodes = {
        p: node(p, None, 0, "1"),
        a: node(a, p, 1, "1.1"),
        b: node(b, p, 1, "1.2"),
    }

    snap = snapshot(
        nodes,
        {
            None: [p],
            p: [a, b],
            a: [],
            b: [],
        },
        [p],
    )

    payloads = {
        a: {
            "planned_date": "2026-08-13",
            "due_date": "2026-08-13",
            "planned_start_time": "08:00",
            "planned_end_time": "12:00",
            "estimated_duration": 240,
        },
        b: {
            "planned_date": "2026-08-13",
            "due_date": "2026-08-13",
            "planned_start_time": "10:00",
            "planned_end_time": "18:00",
            "estimated_duration": 480,
        },
    }

    r = WBSRollupService.calculate(snap, payloads)[p]

    # Envelope 08:00 -> 18:00 = 600 minutes.
    # NOT 240 + 480 = 720.
    assert r.planned_elapsed_minutes == 600


def test_leaf_taskstatus_enum_supported():
    from todo_bird_app.models.task import Task, TaskStatus

    key = EntityRef.task(1)

    nodes = {
        key: node(key, None, 0, "1", "Completed"),
    }

    snap = snapshot(
        nodes,
        {
            None: [key],
            key: [],
        },
        [key],
    )

    task = Task(
        id=1,
        status=TaskStatus.COMPLETED,
        progress=11,
        planned_effort_minutes=60,
    )

    r = WBSRollupService.calculate(
        snap,
        {key: task},
    )[key]

    assert r.progress == 100
    assert r.completed_leaf_count == 1


def test_large_linear_project_stays_linear():
    # Practical guard against accidental descendant rescans / O(n^2).
    count = 5000

    nodes = {}
    children = {None: []}
    payloads = {}

    previous = None

    for i in range(1, count + 1):
        key = EntityRef.subtask(i)
        parent = previous

        nodes[key] = WBSNode(
            key=key,
            project_id=1,
            parent_key=parent,
            title=str(i),
            sibling_order=1,
            depth=i - 1,
            wbs_code=str(i),
            child_count=1 if i < count else 0,
            has_children=i < count,
            status="Planned",
            is_milestone=False,
            is_completed=False,
            created_at="2026-01-01",
        )

        if parent is None:
            children[None] = [key]
        else:
            children[parent] = [key]

        children.setdefault(key, [])
        payloads[key] = {
            "planned_effort_minutes": 1,
            "progress": 50,
        }

        previous = key

    snap = snapshot(
        nodes,
        children,
        children[None],
    )

    results = WBSRollupService.calculate(
        snap,
        payloads,
    )

    root = children[None][0]
    assert len(results) == count

    # Only deepest node is a leaf; ancestor payloads are summaries
    # and therefore intentionally not double-counted.
    assert results[root].leaf_count == 1
    assert results[root].planned_effort_minutes == 1
    assert results[root].progress == 50
