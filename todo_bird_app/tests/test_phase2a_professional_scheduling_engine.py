"""
Tests for Phase 2A: Professional Scheduling Engine Foundation.

Verifies:
1. Single task CPM calculations
2. Simple FS chain (A -> B -> C)
3. Parallel paths (critical vs floating)
4. Converging network (max predecessor EF)
5. Diverging network (min successor LS)
6. Multiple critical paths
7. Free float vs Total float mathematical distinction
8. Explicit later planned start anchor constraint
9. Disconnected components inside one project
10. Zero-duration milestone node
11. Unscheduled task (missing start) diagnostic
12. Invalid duration (negative) diagnostic
13. Simple cycle (A -> B -> A) detection without graph mutation
14. Partial cyclic project (unaffected acyclic analysis)
15. Missing dependency reference diagnostic
16. Completed task planned CPM semantics
17. Cancelled task behavior
18. 5000-node synthetic DAG performance (no recursion, O(V+E))
19. Determinism across multiple executions
20. Pure object evaluation (zero DB required)
21. Mathematical invariant checks (EF >= ES, LF >= LS, TF = LS - ES = LF - EF)
"""

from datetime import datetime, timedelta, date, time
import pytest

from todo_bird_app.models.task import Task, TaskStatus, TaskPriority, TaskCategory
from todo_bird_app.services.cpm_scheduling_service import (
    CPMSchedulingService,
    DiagnosticCode,
    SchedulingResult,
    ScheduleNodeResult,
    DependencyType,
)


def _make_task(
    task_id: int,
    title: str = "",
    planned_date: str = "2026-09-01",
    planned_start_time: str = "09:00",
    estimated_duration: int = 120,  # minutes
    dependencies: list = None,
    project_id: int = 1,
    status: TaskStatus = TaskStatus.PLANNED,
    is_milestone: bool = False,
) -> Task:
    t = Task(
        id=task_id,
        title=title or f"Task {task_id}",
        project_id=project_id,
        planned_date=planned_date,
        planned_start_time=planned_start_time,
        estimated_duration=estimated_duration,
        dependencies=list(dependencies or []),
        status=status,
    )
    if is_milestone:
        t.is_milestone = True
    return t


# ------------------------------------------------------------
# 1. Single Task
# ------------------------------------------------------------
def test_01_single_task_cpm():
    # Single task of 2 days (2880 minutes)
    t = _make_task(1, "A", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880)
    res = CPMSchedulingService.calculate_schedule([t])

    assert res.is_complete is True
    assert res.has_cycles is False
    assert len(res.nodes) == 1

    node = res.nodes[1]
    assert node.schedulable is True
    assert node.earliest_start == datetime(2026, 9, 1, 0, 0)
    assert node.earliest_finish == datetime(2026, 9, 3, 0, 0)
    assert node.latest_start == datetime(2026, 9, 1, 0, 0)
    assert node.latest_finish == datetime(2026, 9, 3, 0, 0)
    assert node.total_float_minutes == 0
    assert node.free_float_minutes == 0
    assert node.is_critical is True
    assert res.critical_task_ids == (1,)
    assert res.critical_paths == ((1,),)


# ------------------------------------------------------------
# 2. Simple FS Chain (A -> B -> C)
# ------------------------------------------------------------
def test_02_simple_fs_chain():
    # A (2d = 2880m) -> B (3d = 4320m) -> C (1d = 1440m)
    t_a = _make_task(1, "A", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880)
    t_b = _make_task(2, "B", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=4320, dependencies=[1])
    t_c = _make_task(3, "C", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=1440, dependencies=[2])

    res = CPMSchedulingService.calculate_schedule([t_a, t_b, t_c])

    assert res.is_complete is True
    assert res.project_start == datetime(2026, 9, 1, 0, 0)
    assert res.project_finish == datetime(2026, 9, 7, 0, 0)  # 2 + 3 + 1 = 6 days

    # All nodes are critical
    for tid in (1, 2, 3):
        node = res.nodes[tid]
        assert node.total_float_minutes == 0
        assert node.free_float_minutes == 0
        assert node.is_critical is True

    assert res.nodes[1].earliest_start == datetime(2026, 9, 1, 0, 0)
    assert res.nodes[1].earliest_finish == datetime(2026, 9, 3, 0, 0)

    assert res.nodes[2].earliest_start == datetime(2026, 9, 3, 0, 0)
    assert res.nodes[2].earliest_finish == datetime(2026, 9, 6, 0, 0)

    assert res.nodes[3].earliest_start == datetime(2026, 9, 6, 0, 0)
    assert res.nodes[3].earliest_finish == datetime(2026, 9, 7, 0, 0)

    assert res.critical_task_ids == (1, 2, 3)
    assert res.critical_paths == ((1, 2, 3),)


# ------------------------------------------------------------
# 3. Parallel Paths (Critical vs Floating)
# ------------------------------------------------------------
def test_03_parallel_paths():
    # Path 1 (Critical): A (2d) -> C (2d) = 4d (5760m)
    # Path 2 (Floating): B (1d) -> D (1d) = 2d (2880m)
    t_a = _make_task(1, "A", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880)
    t_c = _make_task(3, "C", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880, dependencies=[1])

    t_b = _make_task(2, "B", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=1440)
    t_d = _make_task(4, "D", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=1440, dependencies=[2])

    res = CPMSchedulingService.calculate_schedule([t_a, t_b, t_c, t_d])

    assert res.project_start == datetime(2026, 9, 1, 0, 0)
    assert res.project_finish == datetime(2026, 9, 5, 0, 0)  # 4 days

    # Path 1 is critical
    assert res.nodes[1].is_critical is True
    assert res.nodes[1].total_float_minutes == 0
    assert res.nodes[3].is_critical is True
    assert res.nodes[3].total_float_minutes == 0

    # Path 2 has 2 days (2880m) of float
    assert res.nodes[2].is_critical is False
    assert res.nodes[2].total_float_minutes == 2880
    assert res.nodes[4].is_critical is False
    assert res.nodes[4].total_float_minutes == 2880

    assert res.critical_task_ids == (1, 3)
    assert res.critical_paths == ((1, 3),)


# ------------------------------------------------------------
# 4. Converging Network
# ------------------------------------------------------------
def test_04_converging_network():
    # A (2d) -> C (1d)
    # B (4d) -> C (1d)
    # C must start after B finishes (the later predecessor)
    t_a = _make_task(1, "A", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880)
    t_b = _make_task(2, "B", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=5760)
    t_c = _make_task(3, "C", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=1440, dependencies=[1, 2])

    res = CPMSchedulingService.calculate_schedule([t_a, t_b, t_c])

    assert res.nodes[3].earliest_start == datetime(2026, 9, 5, 0, 0)  # max(Sept 3, Sept 5) = Sept 5
    assert res.nodes[3].earliest_finish == datetime(2026, 9, 6, 0, 0)
    assert res.nodes[2].is_critical is True
    assert res.nodes[3].is_critical is True
    assert res.nodes[1].is_critical is False
    assert res.nodes[1].total_float_minutes == 2880
    assert res.critical_task_ids == (2, 3)


# ------------------------------------------------------------
# 5. Diverging Network
# ------------------------------------------------------------
def test_05_diverging_network():
    # A (2d) -> B (2d)
    # A (2d) -> C (4d)
    # Backward pass chooses min(LS(B), LS(C))
    t_a = _make_task(1, "A", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880)
    t_b = _make_task(2, "B", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880, dependencies=[1])
    t_c = _make_task(3, "C", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=5760, dependencies=[1])

    res = CPMSchedulingService.calculate_schedule([t_a, t_b, t_c])

    assert res.project_finish == datetime(2026, 9, 7, 0, 0)  # A (2d) + C (4d) = 6d
    # C is critical (4d), B has 2d float
    assert res.nodes[1].is_critical is True
    assert res.nodes[3].is_critical is True
    assert res.nodes[2].is_critical is False
    assert res.nodes[2].total_float_minutes == 2880
    assert res.critical_task_ids == (1, 3)


# ------------------------------------------------------------
# 6. Multiple Critical Paths
# ------------------------------------------------------------
def test_06_multiple_critical_paths():
    # Branch 1: A (3d) -> B (2d) = 5d
    # Branch 2: C (2d) -> D (3d) = 5d
    t_a = _make_task(1, "A", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=4320)
    t_b = _make_task(2, "B", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880, dependencies=[1])

    t_c = _make_task(3, "C", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880)
    t_d = _make_task(4, "D", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=4320, dependencies=[3])

    res = CPMSchedulingService.calculate_schedule([t_a, t_b, t_c, t_d])

    assert res.project_finish == datetime(2026, 9, 6, 0, 0)  # 5 days
    # All 4 tasks have Total Float == 0 and are critical
    for tid in (1, 2, 3, 4):
        assert res.nodes[tid].total_float_minutes == 0
        assert res.nodes[tid].is_critical is True

    assert res.critical_task_ids == (1, 2, 3, 4)
    assert set(res.critical_paths) == {(1, 2), (3, 4)}


# ------------------------------------------------------------
# 7. Free Float vs Total Float
# ------------------------------------------------------------
def test_07_free_float_distinction():
    # A (2d) -> B (2d) -> D (2d) [Total 6d]
    # C (1d) -> B (2d)
    # A is critical (2d + 2d + 2d = 6d).
    # C (1d) finishes at day 1. B starts at day 2.
    # C free float = min(ES(B)) - EF(C) = 2d - 1d = 1d (1440m).
    # C total float = LS(C) - ES(C) = 1d (1440m).
    t_a = _make_task(1, "A", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880)
    t_c = _make_task(2, "C", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=1440)
    t_b = _make_task(3, "B", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880, dependencies=[1, 2])
    t_d = _make_task(4, "D", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880, dependencies=[3])

    res = CPMSchedulingService.calculate_schedule([t_a, t_c, t_b, t_d])

    assert res.nodes[1].is_critical is True
    assert res.nodes[3].is_critical is True
    assert res.nodes[4].is_critical is True

    assert res.nodes[2].is_critical is False
    assert res.nodes[2].free_float_minutes == 1440
    assert res.nodes[2].total_float_minutes == 1440


# ------------------------------------------------------------
# 8. Explicit Later Planned Start Constraint
# ------------------------------------------------------------
def test_08_explicit_later_planned_start():
    # A (2d, Sept 1-3) -> B (1d, planned for Sept 5)
    # B's dependency allows start on Sept 3, but explicit planned start is Sept 5.
    # B should start on Sept 5.
    t_a = _make_task(1, "A", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880)
    t_b = _make_task(2, "B", planned_date="2026-09-05", planned_start_time="00:00", estimated_duration=1440, dependencies=[1])

    res = CPMSchedulingService.calculate_schedule([t_a, t_b])

    assert res.nodes[1].earliest_finish == datetime(2026, 9, 3, 0, 0)
    assert res.nodes[2].earliest_start == datetime(2026, 9, 5, 0, 0)
    assert res.nodes[2].earliest_finish == datetime(2026, 9, 6, 0, 0)
    assert res.project_finish == datetime(2026, 9, 6, 0, 0)


# ------------------------------------------------------------
# 9. Disconnected Components
# ------------------------------------------------------------
def test_09_disconnected_components():
    # Island 1: A (4d) -> B (2d) = 6d
    # Island 2: C (2d) -> D (1d) = 3d
    t_a = _make_task(1, "A", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=5760)
    t_b = _make_task(2, "B", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880, dependencies=[1])

    t_c = _make_task(3, "C", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880)
    t_d = _make_task(4, "D", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=1440, dependencies=[3])

    res = CPMSchedulingService.calculate_schedule([t_a, t_b, t_c, t_d])

    assert res.project_finish == datetime(2026, 9, 7, 0, 0)  # 6 days
    assert res.nodes[1].is_critical is True
    assert res.nodes[2].is_critical is True

    # Island 2 tasks have 3 days (4320m) of float
    assert res.nodes[3].is_critical is False
    assert res.nodes[3].total_float_minutes == 4320
    assert res.nodes[4].is_critical is False
    assert res.nodes[4].total_float_minutes == 4320


# ------------------------------------------------------------
# 10. Zero-Duration Milestone Node
# ------------------------------------------------------------
def test_10_zero_duration_milestone_node():
    # A (2d) -> M (0d milestone) -> B (1d)
    t_a = _make_task(1, "A", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880)
    t_m = _make_task(2, "Milestone", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=0, dependencies=[1], is_milestone=True)
    t_b = _make_task(3, "B", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=1440, dependencies=[2])

    res = CPMSchedulingService.calculate_schedule([t_a, t_m, t_b])

    assert res.nodes[2].earliest_start == datetime(2026, 9, 3, 0, 0)
    assert res.nodes[2].earliest_finish == datetime(2026, 9, 3, 0, 0)
    assert res.nodes[2].total_float_minutes == 0
    assert res.nodes[2].is_critical is True
    assert res.critical_task_ids == (1, 2, 3)


# ------------------------------------------------------------
# 11. Unscheduled Task (Missing Start)
# ------------------------------------------------------------
def test_11_unscheduled_task_diagnostic():
    t_valid = _make_task(1, "Valid", planned_date="2026-09-01", estimated_duration=120)
    t_invalid = _make_task(2, "No Start", planned_date=None, estimated_duration=120)

    res = CPMSchedulingService.calculate_schedule([t_valid, t_invalid])

    assert res.nodes[1].schedulable is True
    assert res.nodes[2].schedulable is False
    assert DiagnosticCode.UNSCHEDULED_NO_START in res.nodes[2].diagnostic_codes
    assert any(d.code == DiagnosticCode.UNSCHEDULED_NO_START for d in res.diagnostics)


# ------------------------------------------------------------
# 12. Invalid Duration (Negative)
# ------------------------------------------------------------
def test_12_invalid_duration_diagnostic():
    t_neg = _make_task(1, "Negative Dur", planned_date="2026-09-01", estimated_duration=-60)
    res = CPMSchedulingService.calculate_schedule([t_neg])

    assert res.nodes[1].schedulable is False
    assert DiagnosticCode.INVALID_DURATION in res.nodes[1].diagnostic_codes


# ------------------------------------------------------------
# 13. Simple Cycle (A -> B -> A)
# ------------------------------------------------------------
def test_13_simple_cycle_detection():
    t_a = _make_task(1, "A", dependencies=[2])
    t_b = _make_task(2, "B", dependencies=[1])

    res = CPMSchedulingService.calculate_schedule([t_a, t_b])

    assert res.has_cycles is True
    assert set(res.cycle_task_ids) == {1, 2}
    assert res.nodes[1].schedulable is False
    assert res.nodes[2].schedulable is False
    assert DiagnosticCode.DEPENDENCY_CYCLE in res.nodes[1].diagnostic_codes
    assert DiagnosticCode.DEPENDENCY_CYCLE in res.nodes[2].diagnostic_codes


# ------------------------------------------------------------
# 14. Partial Cyclic Project (Acyclic Unaffected Analysis)
# ------------------------------------------------------------
def test_14_partial_cyclic_project():
    # Island 1 (Cycle): 1 -> 2 -> 1
    t_1 = _make_task(1, "Cycle 1", dependencies=[2])
    t_2 = _make_task(2, "Cycle 2", dependencies=[1])

    # Island 2 (Clean): 3 (2d) -> 4 (2d)
    t_3 = _make_task(3, "Clean 3", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880)
    t_4 = _make_task(4, "Clean 4", planned_date="2026-09-01", planned_start_time="00:00", estimated_duration=2880, dependencies=[3])

    res = CPMSchedulingService.calculate_schedule([t_1, t_2, t_3, t_4])

    assert res.has_cycles is True
    assert set(res.cycle_task_ids) == {1, 2}

    # Island 2 is cleanly scheduled
    assert res.nodes[3].schedulable is True
    assert res.nodes[4].schedulable is True
    assert res.nodes[3].is_critical is True
    assert res.nodes[4].is_critical is True
    assert res.critical_task_ids == (3, 4)


# ------------------------------------------------------------
# 15. Missing Dependency Reference
# ------------------------------------------------------------
def test_15_missing_dependency_reference():
    t_a = _make_task(1, "A", dependencies=[999])  # 999 does not exist
    res = CPMSchedulingService.calculate_schedule([t_a])

    assert DiagnosticCode.MISSING_TASK_REFERENCE in res.nodes[1].diagnostic_codes
    # Task 1 can still be scheduled as a root
    assert res.nodes[1].schedulable is True


# ------------------------------------------------------------
# 16. Completed Task CPM Semantics
# ------------------------------------------------------------
def test_16_completed_task_in_cpm_network():
    # Completed task in network retains planned CPM topology
    t_a = _make_task(1, "A", estimated_duration=120, status=TaskStatus.COMPLETED)
    t_b = _make_task(2, "B", estimated_duration=120, dependencies=[1], status=TaskStatus.IN_PROGRESS)

    res = CPMSchedulingService.calculate_schedule([t_a, t_b])

    assert res.nodes[1].schedulable is True
    assert res.nodes[2].schedulable is True
    assert res.nodes[1].is_critical is True
    assert res.nodes[2].is_critical is True


# ------------------------------------------------------------
# 17. Cancelled Task
# ------------------------------------------------------------
def test_17_cancelled_task_in_network():
    t_a = _make_task(1, "Cancelled", estimated_duration=60, status=TaskStatus.CANCELLED)
    res = CPMSchedulingService.calculate_schedule([t_a])

    assert res.nodes[1].schedulable is True
    assert res.nodes[1].is_critical is True


# ------------------------------------------------------------
# 18. 5000-Node Synthetic DAG Performance
# ------------------------------------------------------------
def test_18_5000_node_dag_performance():
    # Build 5,000 tasks in a chain + fan-out network
    tasks = []
    base_date = "2026-09-01"

    # Chain of 5,000 tasks: 0 -> 1 -> 2 -> ... -> 4999
    for i in range(5000):
        preds = [i - 1] if i > 0 else []
        tasks.append(
            Task(
                id=i,
                title=f"Task {i}",
                project_id=1,
                planned_date=base_date,
                planned_start_time="00:00",
                estimated_duration=10,
                dependencies=preds,
                status=TaskStatus.PLANNED,
            )
        )

    import time as pytime
    t0 = pytime.perf_counter()
    res = CPMSchedulingService.calculate_schedule(tasks)
    elapsed = pytime.perf_counter() - t0

    assert res.is_complete is True
    assert len(res.nodes) == 5000
    assert len(res.critical_task_ids) == 5000
    # Must execute in under 1.5 seconds for 5,000 nodes without recursion error
    assert elapsed < 1.5


# ------------------------------------------------------------
# 19. Determinism
# ------------------------------------------------------------
def test_19_determinism():
    tasks = [
        _make_task(1, "A", estimated_duration=120),
        _make_task(2, "B", estimated_duration=180, dependencies=[1]),
        _make_task(3, "C", estimated_duration=60, dependencies=[1]),
        _make_task(4, "D", estimated_duration=120, dependencies=[2, 3]),
    ]

    res1 = CPMSchedulingService.calculate_schedule(tasks)
    res2 = CPMSchedulingService.calculate_schedule(tasks)

    assert res1.critical_task_ids == res2.critical_task_ids
    assert res1.critical_paths == res2.critical_paths
    for tid in (1, 2, 3, 4):
        n1 = res1.nodes[tid]
        n2 = res2.nodes[tid]
        assert n1.earliest_start == n2.earliest_start
        assert n1.earliest_finish == n2.earliest_finish
        assert n1.latest_start == n2.latest_start
        assert n1.latest_finish == n2.latest_finish
        assert n1.total_float_minutes == n2.total_float_minutes
        assert n1.free_float_minutes == n2.free_float_minutes
        assert n1.is_critical == n2.is_critical


# ------------------------------------------------------------
# 20. Pure Object Evaluation
# ------------------------------------------------------------
def test_20_pure_object_zero_db():
    # Pass pure in-memory Task objects without any DB instance
    tasks = [
        _make_task(100, "Standalone 1", estimated_duration=60),
        _make_task(101, "Standalone 2", estimated_duration=120),
    ]
    res = CPMSchedulingService.calculate_schedule(tasks)
    assert res.schedulable_tasks == 2
    assert res.total_tasks == 2


# ------------------------------------------------------------
# 21. Mathematical Invariant Asserter across complex graph
# ------------------------------------------------------------
def test_21_mathematical_invariants():
    tasks = [
        _make_task(1, "Root A", estimated_duration=120),
        _make_task(2, "Root B", estimated_duration=240),
        _make_task(3, "Child A1", estimated_duration=180, dependencies=[1]),
        _make_task(4, "Child A2", estimated_duration=60, dependencies=[1]),
        _make_task(5, "Join AB", estimated_duration=300, dependencies=[2, 3]),
        _make_task(6, "Terminal", estimated_duration=60, dependencies=[4, 5]),
    ]
    res = CPMSchedulingService.calculate_schedule(tasks)

    for tid, node in res.nodes.items():
        if not node.schedulable:
            continue
        # 1. EF >= ES
        assert node.earliest_finish >= node.earliest_start
        # 2. LF >= LS
        assert node.latest_finish >= node.latest_start
        # 3. TF = LS - ES = LF - EF
        tf_start = int((node.latest_start - node.earliest_start).total_seconds() // 60)
        tf_finish = int((node.latest_finish - node.earliest_finish).total_seconds() // 60)
        assert tf_start == tf_finish
        assert node.total_float_minutes == tf_start
        # 4. Critical check: is_critical <=> TF == 0
        assert node.is_critical == (node.total_float_minutes == 0)


# ------------------------------------------------------------
# 22. Gantt Dependency Engine CPM Annotation
# ------------------------------------------------------------
def test_22_gantt_dependency_engine_cpm_annotation():
    from todo_bird_app.gantt.gantt_dependency_engine import GanttDependencyEngine

    task_a = _make_task(1, "A", planned_date="2026-09-01", estimated_duration=2880)
    task_b = _make_task(2, "B", planned_date="2026-09-01", estimated_duration=2880, dependencies=[1])
    task_c = _make_task(3, "C", planned_date="2026-09-01", estimated_duration=1440)  # Parallel shorter task

    tasks = [task_a, task_b, task_c]
    ann = GanttDependencyEngine.annotate(tasks)

    assert "cpm_result" in ann
    cpm_res = ann["cpm_result"]
    assert isinstance(cpm_res, SchedulingResult)
    assert cpm_res.critical_task_ids == (1, 2)

    # Check task attributes
    assert task_a.cpm_is_critical is True
    assert task_a.cpm_total_float == 0
    assert task_b.cpm_is_critical is True
    assert task_b.cpm_total_float == 0
    assert task_c.cpm_is_critical is False
    assert task_c.cpm_total_float == 4320  # Float = 4d - 1d = 3d = 4320m


# ------------------------------------------------------------
# 23. Gantt compute_cpm_schedule API
# ------------------------------------------------------------
def test_23_gantt_compute_cpm_schedule_api():
    from todo_bird_app.gantt.gantt_dependency_engine import GanttDependencyEngine

    tasks = [
        _make_task(10, "P1 Task", project_id=1, estimated_duration=120),
        _make_task(20, "P2 Task", project_id=2, estimated_duration=240),
    ]

    res_p1 = GanttDependencyEngine.compute_cpm_schedule(tasks, project_id=1)
    assert len(res_p1.nodes) == 1
    assert 10 in res_p1.nodes

    res_all = GanttDependencyEngine.compute_cpm_schedule(tasks)
    assert len(res_all.nodes) == 2

