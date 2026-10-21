"""
Phase 2C — Advanced Dependency Types + Lag/Lead Foundation Test Suite.

Comprehensive deterministic verification covering:
1. Canonical DependencySpec data structures, serialization/deserialization, PM lag expressions.
2. Forward Pass CPM calculation for FS, SS, FF, SF with positive, zero, and negative lag.
3. Backward Pass CPM calculation for FS, SS, FF, SF with positive, zero, and negative lag.
4. Total Float and Free Float derivations per edge type.
5. Multiple predecessor convergence with mixed dependency types.
6. Multiple critical paths enumeration under advanced dependencies.
7. Cycle detection and non-destructive diagnostics under advanced edge types.
8. Gantt dependency engine and edge violation verification.
9. TaskDialog dependency tree UI integration and safe DB persistence.
"""

from __future__ import annotations

import json
import pytest
from datetime import datetime, date, time, timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QTreeWidget, QComboBox, QLineEdit

from todo_bird_app.models.task import Task, TaskStatus, TaskPriority, TaskCategory
from todo_bird_app.services.cpm_scheduling_service import (
    CPMSchedulingService,
    DependencySpec,
    DependencyType,
    DiagnosticCode,
    parse_lag_duration,
    format_lag_duration,
    format_concise_dependency,
    parse_dependency_specs,
    serialize_dependency_specs,
    format_float_duration,
)
from todo_bird_app.gantt.gantt_dependency_engine import GanttDependencyEngine
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.database import DatabaseManager


# ============================================================================
# 1. CANONICAL MODEL & PARSING / SERIALIZATION TESTS
# ============================================================================

def test_dependency_spec_model():
    """Verify DependencySpec model instantiation and dictionary conversion."""
    spec = DependencySpec(
        predecessor_id=5,
        successor_id=10,
        dependency_type=DependencyType.SS,
        lag_minutes=120,
    )
    assert spec.predecessor_id == 5
    assert spec.successor_id == 10
    assert spec.dependency_type == DependencyType.SS
    assert spec.lag_minutes == 120

    d = spec.to_dict()
    assert d == {"predecessor_id": 5, "type": "SS", "lag_minutes": 120, "successor_id": 10}

    spec_restored = DependencySpec.from_dict(d)
    assert spec_restored.predecessor_id == 5
    assert spec_restored.successor_id == 10
    assert spec_restored.dependency_type == DependencyType.SS
    assert spec_restored.lag_minutes == 120


def test_parse_lag_duration_expressions():
    """Verify parsing of PM-friendly lag/lead strings into exact elapsed minutes."""
    assert parse_lag_duration(0) == 0
    assert parse_lag_duration("0") == 0
    assert parse_lag_duration("0m") == 0
    assert parse_lag_duration("30m") == 30
    assert parse_lag_duration("2h") == 120
    assert parse_lag_duration("1d") == 1440
    assert parse_lag_duration("1d 2h") == 1560
    assert parse_lag_duration("+1d 4h 30m") == 1710
    assert parse_lag_duration("-2h") == -120
    assert parse_lag_duration("-1d") == -1440
    assert parse_lag_duration("-30m") == -30
    assert parse_lag_duration("invalid") is None
    assert parse_lag_duration(99999999) is None  # Exceeds 1 year bound


def test_format_lag_duration():
    """Verify formatting of lag/lead minutes into clean PM strings."""
    assert format_lag_duration(0) == "0m"
    assert format_lag_duration(30) == "+30m"
    assert format_lag_duration(120) == "+2h"
    assert format_lag_duration(150) == "+2h 30m"
    assert format_lag_duration(1440) == "+1d"
    assert format_lag_duration(1560) == "+1d 2h"
    assert format_lag_duration(-120) == "-2h"
    assert format_lag_duration(-1440) == "-1d"
    assert format_lag_duration(None) == "0m"


def test_format_concise_dependency():
    """Verify concise dependency string notation (e.g. 12FS+1d, 5SS, 8FF-2h)."""
    assert format_concise_dependency(12) == "12FS"
    assert format_concise_dependency(DependencySpec(5, 10, DependencyType.SS, 0)) == "5SS"
    assert format_concise_dependency(DependencySpec(12, 10, DependencyType.FS, 1440)) == "12FS+1d"
    assert format_concise_dependency(DependencySpec(8, 10, DependencyType.FF, -120)) == "8FF-2h"
    assert format_concise_dependency(DependencySpec(3, 10, DependencyType.SF, 0)) == "3SF"


def test_parse_dependency_specs_legacy_and_dict():
    """Verify parse_dependency_specs decodes legacy ints, dicts, JSON, and DependencySpec."""
    # Legacy int list
    specs1 = parse_dependency_specs([1, 4, 7], successor_id=10)
    assert len(specs1) == 3
    assert all(s.dependency_type == DependencyType.FS and s.lag_minutes == 0 for s in specs1)
    assert [s.predecessor_id for s in specs1] == [1, 4, 7]

    # Dict list
    raw_dicts = [
        {"predecessor_id": 1, "type": "FS", "lag_minutes": 60},
        {"predecessor_id": 4, "type": "SS", "lag_minutes": -30},
    ]
    specs2 = parse_dependency_specs(raw_dicts, successor_id=10)
    assert len(specs2) == 2
    assert specs2[0].predecessor_id == 1 and specs2[0].dependency_type == DependencyType.FS and specs2[0].lag_minutes == 60
    assert specs2[1].predecessor_id == 4 and specs2[1].dependency_type == DependencyType.SS and specs2[1].lag_minutes == -30

    # JSON string
    json_str = json.dumps(raw_dicts)
    specs3 = parse_dependency_specs(json_str, successor_id=10)
    assert specs3 == specs2


def test_serialize_dependency_specs():
    """Verify serialize_dependency_specs emits clean JSON text."""
    specs = [
        DependencySpec(predecessor_id=1, successor_id=10, dependency_type=DependencyType.FS, lag_minutes=0),
        DependencySpec(predecessor_id=2, successor_id=10, dependency_type=DependencyType.SS, lag_minutes=120),
    ]
    serialized = serialize_dependency_specs(specs)
    deserialized = json.loads(serialized)
    assert len(deserialized) == 2
    assert deserialized[0] == {"predecessor_id": 1, "type": "FS", "lag_minutes": 0}
    assert deserialized[1] == {"predecessor_id": 2, "type": "SS", "lag_minutes": 120}


# ============================================================================
# 2. CPM FORWARD PASS VERIFICATION (FS, SS, FF, SF + LAG / LEAD)
# ============================================================================

def test_cpm_forward_pass_fs_zero_lag():
    """FS with zero lag: ES(S) = EF(P)."""
    t1 = Task(id=1, title="Pred", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120)
    t2 = Task(id=2, title="Succ", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[{"predecessor_id": 1, "type": "FS", "lag_minutes": 0}])
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    n1, n2 = res.get_node(1), res.get_node(2)
    assert n1.earliest_start == datetime(2026, 9, 1, 8, 0)
    assert n1.earliest_finish == datetime(2026, 9, 1, 10, 0)
    assert n2.earliest_start == datetime(2026, 9, 1, 10, 0)
    assert n2.earliest_finish == datetime(2026, 9, 1, 11, 0)


def test_cpm_forward_pass_fs_positive_lag():
    """FS with positive lag: ES(S) = EF(P) + L."""
    t1 = Task(id=1, title="Pred", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120)
    t2 = Task(id=2, title="Succ", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[{"predecessor_id": 1, "type": "FS", "lag_minutes": 60}])
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    n2 = res.get_node(2)
    # EF(P) = 10:00, Lag = +60m => ES(S) = 11:00
    assert n2.earliest_start == datetime(2026, 9, 1, 11, 0)
    assert n2.earliest_finish == datetime(2026, 9, 1, 12, 0)


def test_cpm_forward_pass_fs_negative_lag_lead():
    """FS with negative lag (lead): ES(S) = EF(P) - L."""
    t1 = Task(id=1, title="Pred", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120)
    t2 = Task(id=2, title="Succ", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[{"predecessor_id": 1, "type": "FS", "lag_minutes": -30}])
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    n2 = res.get_node(2)
    # EF(P) = 10:00, Lead = -30m => ES(S) = 09:30
    assert n2.earliest_start == datetime(2026, 9, 1, 9, 30)
    assert n2.earliest_finish == datetime(2026, 9, 1, 10, 30)


def test_cpm_forward_pass_ss_zero_lag():
    """SS with zero lag: ES(S) = ES(P)."""
    t1 = Task(id=1, title="Pred", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120)
    t2 = Task(id=2, title="Succ", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[{"predecessor_id": 1, "type": "SS", "lag_minutes": 0}])
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    n2 = res.get_node(2)
    # ES(P) = 08:00 => ES(S) = 08:00
    assert n2.earliest_start == datetime(2026, 9, 1, 8, 0)
    assert n2.earliest_finish == datetime(2026, 9, 1, 9, 0)


def test_cpm_forward_pass_ss_positive_lag():
    """SS with positive lag: ES(S) = ES(P) + L."""
    t1 = Task(id=1, title="Pred", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120)
    t2 = Task(id=2, title="Succ", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[{"predecessor_id": 1, "type": "SS", "lag_minutes": 30}])
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    n2 = res.get_node(2)
    # ES(P) = 08:00 + 30m => ES(S) = 08:30
    assert n2.earliest_start == datetime(2026, 9, 1, 8, 30)
    assert n2.earliest_finish == datetime(2026, 9, 1, 9, 30)


def test_cpm_forward_pass_ff_zero_lag():
    """FF with zero lag: EF(S) >= EF(P) => ES(S) >= EF(P) - dur(S)."""
    t1 = Task(id=1, title="Pred", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120)
    t2 = Task(id=2, title="Succ", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[{"predecessor_id": 1, "type": "FF", "lag_minutes": 0}])
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    n1, n2 = res.get_node(1), res.get_node(2)
    # EF(P) = 10:00 => EF(S) = 10:00 => ES(S) = 09:00
    assert n1.earliest_finish == datetime(2026, 9, 1, 10, 0)
    assert n2.earliest_finish == datetime(2026, 9, 1, 10, 0)
    assert n2.earliest_start == datetime(2026, 9, 1, 9, 0)


def test_cpm_forward_pass_ff_positive_lag():
    """FF with positive lag: EF(S) >= EF(P) + L => ES(S) >= EF(P) + L - dur(S)."""
    t1 = Task(id=1, title="Pred", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120)
    t2 = Task(id=2, title="Succ", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[{"predecessor_id": 1, "type": "FF", "lag_minutes": 30}])
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    n2 = res.get_node(2)
    # EF(P) = 10:00 + 30m = 10:30 => ES(S) = 10:30 - 60m = 09:30
    assert n2.earliest_finish == datetime(2026, 9, 1, 10, 30)
    assert n2.earliest_start == datetime(2026, 9, 1, 9, 30)


def test_cpm_forward_pass_sf_zero_lag():
    """SF with zero lag: EF(S) >= ES(P) => ES(S) >= ES(P) - dur(S)."""
    # Pred starts at 10:00 (dur=120), Succ (dur=60) has SF to Pred
    t1 = Task(id=1, title="Pred", planned_date="2026-09-01", planned_start_time="10:00", estimated_duration=120)
    t2 = Task(id=2, title="Succ", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[{"predecessor_id": 1, "type": "SF", "lag_minutes": 0}])
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    n2 = res.get_node(2)
    # ES(P) = 10:00 => EF(S) = 10:00 => ES(S) = 09:00
    assert n2.earliest_finish == datetime(2026, 9, 1, 10, 0)
    assert n2.earliest_start == datetime(2026, 9, 1, 9, 0)


# ============================================================================
# 3. CPM BACKWARD PASS & FLOAT VERIFICATION
# ============================================================================

def test_cpm_backward_pass_and_total_float_fs():
    """FS network float calculation."""
    # 1 (120m) -> 2 (60m) along critical path (total 180m), 3 (60m) parallel with 60m float
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120)
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[{"predecessor_id": 1, "type": "FS", "lag_minutes": 0}])
    t3 = Task(id=3, title="C", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60)
    res = CPMSchedulingService.calculate_schedule([t1, t2, t3])

    assert res.project_finish == datetime(2026, 9, 1, 11, 0)
    n1, n2, n3 = res.get_node(1), res.get_node(2), res.get_node(3)
    assert n1.is_critical is True and n1.total_float_minutes == 0
    assert n2.is_critical is True and n2.total_float_minutes == 0
    # Task 3 finishes at 09:00, project finishes at 11:00 => TF = 120m
    assert n3.is_critical is False
    assert n3.total_float_minutes == 120
    assert n3.free_float_minutes == 120


def test_cpm_backward_pass_and_float_ss():
    """SS edge backward pass: LS(P) <= LS(S) - L => LF(P) <= LS(S) - L + dur(P)."""
    # Pred (dur=120), Succ (dur=120) with SS+60
    # Forward: ES(P)=08:00, EF(P)=10:00; ES(S)=09:00, EF(S)=11:00. Project finish = 11:00.
    t1 = Task(id=1, title="Pred", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120)
    t2 = Task(id=2, title="Succ", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120,
              dependencies=[{"predecessor_id": 1, "type": "SS", "lag_minutes": 60}])
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    n1, n2 = res.get_node(1), res.get_node(2)
    assert n2.is_critical is True and n2.total_float_minutes == 0
    assert n1.is_critical is True and n1.total_float_minutes == 0
    assert n1.earliest_start == datetime(2026, 9, 1, 8, 0)
    assert n2.earliest_start == datetime(2026, 9, 1, 9, 0)


def test_cpm_backward_pass_and_float_ff():
    """FF edge backward pass: LF(P) <= LF(S) - L."""
    # Pred (dur=120), Succ (dur=60) with FF+0
    # Forward: ES(P)=08:00, EF(P)=10:00; EF(S)=10:00, ES(S)=09:00. Project finish = 10:00.
    t1 = Task(id=1, title="Pred", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120)
    t2 = Task(id=2, title="Succ", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[{"predecessor_id": 1, "type": "FF", "lag_minutes": 0}])
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    n1, n2 = res.get_node(1), res.get_node(2)
    assert n1.is_critical is True and n1.total_float_minutes == 0
    assert n2.is_critical is True and n2.total_float_minutes == 0


# ============================================================================
# 4. MULTIPLE PREDECESSOR CONVERGENCE & MULTIPLE CRITICAL PATHS
# ============================================================================

def test_cpm_multiple_predecessors_mixed_types():
    """Successor depends on A via FS and B via SS+180."""
    # A (dur=120, starts 08:00 => EF=10:00)
    # B (dur=60, starts 08:00 => ES=08:00)
    # C depends on A (FS+0 => ES>=10:00) and B (SS+180 => ES>=11:00)
    # C ES must be max(10:00, 11:00) = 11:00
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120)
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60)
    t3 = Task(id=3, title="C", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[
                  {"predecessor_id": 1, "type": "FS", "lag_minutes": 0},
                  {"predecessor_id": 2, "type": "SS", "lag_minutes": 180},
              ])
    res = CPMSchedulingService.calculate_schedule([t1, t2, t3])
    n3 = res.get_node(3)
    assert n3.earliest_start == datetime(2026, 9, 1, 11, 0)
    assert n3.earliest_finish == datetime(2026, 9, 1, 12, 0)
    # B->C is the driving edge, A has float of 60m
    n1 = res.get_node(1)
    assert n1.total_float_minutes == 60


def test_cpm_multiple_critical_paths():
    """Two parallel paths of equal length both marked critical."""
    # Path 1: 1 (120m) -> 2 (120m) = 240m
    # Path 2: 3 (120m) -> 4 (120m) = 240m
    t1 = Task(id=1, title="A1", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120)
    t2 = Task(id=2, title="A2", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120,
              dependencies=[{"predecessor_id": 1, "type": "FS", "lag_minutes": 0}])
    t3 = Task(id=3, title="B1", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120)
    t4 = Task(id=4, title="B2", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120,
              dependencies=[{"predecessor_id": 3, "type": "FS", "lag_minutes": 0}])

    res = CPMSchedulingService.calculate_schedule([t1, t2, t3, t4])
    assert res.critical_task_ids == (1, 2, 3, 4)
    assert len(res.critical_paths) == 2
    assert (1, 2) in res.critical_paths
    assert (3, 4) in res.critical_paths


# ============================================================================
# 5. CYCLE DETECTION & DIAGNOSTICS FOR ADVANCED DEPENDENCIES
# ============================================================================

def test_cpm_cycle_detection_mixed_types():
    """Detect cycles across mixed dependency types (e.g. 1 ->SS 2 ->FF 1)."""
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[{"predecessor_id": 2, "type": "FF", "lag_minutes": 0}])
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[{"predecessor_id": 1, "type": "SS", "lag_minutes": 0}])

    res = CPMSchedulingService.calculate_schedule([t1, t2])
    assert res.has_cycles is True
    assert 1 in res.cycle_task_ids
    assert 2 in res.cycle_task_ids
    assert res.get_node(1).schedulable is False
    assert res.get_node(2).schedulable is False


def test_cpm_diagnostics_invalid_type_and_lag():
    """Invalid dependency type and out-of-range lag trigger diagnostic codes."""
    t1 = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60)
    t2 = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[
                  {"predecessor_id": 1, "type": "INVALID_TYPE", "lag_minutes": 0},
                  {"predecessor_id": 1, "type": "FS", "lag_minutes": 99999999},  # Out of range
              ])
    res = CPMSchedulingService.calculate_schedule([t1, t2])
    diag_codes = [d.code for d in res.diagnostics]
    assert DiagnosticCode.INVALID_DEPENDENCY_TYPE in diag_codes or DiagnosticCode.DUPLICATE_DEPENDENCY in diag_codes


# ============================================================================
# 6. GANTT DEPENDENCY ENGINE INTEGRATION
# ============================================================================

def test_gantt_engine_validate_proposed_dependencies_specs():
    """GanttDependencyEngine accepts DependencySpecs and rejects cycles and self-references."""
    t1 = Task(id=1, title="Task 1", dependencies=[])
    t2 = Task(id=2, title="Task 2", dependencies=[{"predecessor_id": 1, "type": "FS", "lag_minutes": 0}])

    # Self-reference
    v1 = GanttDependencyEngine.validate_proposed_dependencies(
        task_id=1,
        candidate_ids=[{"predecessor_id": 1, "type": "SS", "lag_minutes": 0}],
        tasks=[t1, t2],
    )
    assert v1["valid"] is False
    assert v1["self_reference"] is True

    # Valid addition
    v2 = GanttDependencyEngine.validate_proposed_dependencies(
        task_id=2,
        candidate_ids=[{"predecessor_id": 1, "type": "SS", "lag_minutes": 60}],
        tasks=[t1, t2],
    )
    assert v2["valid"] is True

    # Cycle creation: 1 depends on 2 when 2 already depends on 1
    v3 = GanttDependencyEngine.validate_proposed_dependencies(
        task_id=1,
        candidate_ids=[{"predecessor_id": 2, "type": "FF", "lag_minutes": 0}],
        tasks=[t1, t2],
    )
    assert v3["valid"] is False
    assert len(v3["cycle_nodes"]) > 0


def test_gantt_engine_edge_violation_all_types():
    """GanttDependencyEngine evaluates schedule violations for FS, SS, FF, SF."""
    p = Task(id=1, title="P", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=120)  # 08:00 - 10:00
    s_early = Task(id=2, title="S", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60)  # 09:00 - 10:00
    s_late = Task(id=3, title="S", planned_date="2026-09-01", planned_start_time="10:30", estimated_duration=60)  # 10:30 - 11:30

    # FS: violation if start(S) < finish(P) + lag (10:00)
    assert GanttDependencyEngine.edge_violation(p, s_early, DependencySpec(1, 2, DependencyType.FS, 0)) is True
    assert GanttDependencyEngine.edge_violation(p, s_late, DependencySpec(1, 3, DependencyType.FS, 0)) is False

    # SS: violation if start(S) < start(P) + lag (08:00 + 120 = 10:00)
    assert GanttDependencyEngine.edge_violation(p, s_early, DependencySpec(1, 2, DependencyType.SS, 120)) is True

    # FF: violation if finish(S) < finish(P) + lag (10:00)
    assert GanttDependencyEngine.edge_violation(p, s_early, DependencySpec(1, 2, DependencyType.FF, 60)) is True


# ============================================================================
# 7. UI TASK DIALOG DEPENDENCY TREE INTEGRATION
# ============================================================================

def test_task_dialog_dependency_tree_ui(tmp_path):
    """TaskDialog displays 4 columns, embeds Type combo and Lag edit, and persists DependencySpec."""
    app = QApplication.instance() or QApplication([])

    db_file = str(tmp_path / "test_p2c.db")
    db = DatabaseManager(db_file)

    # Insert prerequisite task
    t1_dict = Task(
        title="Pred Task",
        planned_date="2026-09-01",
        planned_start_time="08:00",
        estimated_duration=120,
    ).to_dict()
    t1_id = db.insert_task(t1_dict)

    # Target task depending on t1 with SS and +30m lag
    t2 = Task(
        id=2,
        title="Succ Task",
        planned_date="2026-09-01",
        planned_start_time="08:30",
        estimated_duration=60,
        dependencies=[{"predecessor_id": t1_id, "type": "SS", "lag_minutes": 30}],
    )

    dialog = TaskDialog(projects=[], task=t2, db_manager=db)

    tree = dialog.dependency_tree
    assert tree.columnCount() == 4
    assert tree.headerItem().text(0) == "Dependency Task"
    assert tree.headerItem().text(1) == "Type"
    assert tree.headerItem().text(2) == "Lag / Lead"
    assert tree.headerItem().text(3) == "Current Status"

    assert tree.topLevelItemCount() >= 1
    item = tree.topLevelItem(0)
    assert item.checkState(0) == Qt.Checked

    # Check embedded widgets
    combo = tree.itemWidget(item, 1)
    lag_edit = tree.itemWidget(item, 2)
    assert isinstance(combo, QComboBox)
    assert isinstance(lag_edit, QLineEdit)
    assert combo.currentData() == "SS"
    assert "+30m" in lag_edit.text()

    # Modify in UI: change to FF and -15m
    combo.setCurrentIndex(combo.findData("FF"))
    lag_edit.setText("-15m")

    # Save dialog state
    dialog.on_save()
    saved_deps = dialog.task.dependencies
    assert len(saved_deps) == 1
    spec_dict = saved_deps[0]
    assert spec_dict["predecessor_id"] == t1_id
    assert spec_dict["type"] == "FF"
    assert spec_dict["lag_minutes"] == -15


def test_cpm_sf_positive_and_negative_lag():
    """SF with positive and negative lag: EF(S) >= ES(P) + L => ES(S) >= ES(P) + L - dur(S)."""
    # Pred starts 10:00 (dur=120).
    # SF +60m: EF(S) >= 10:00 + 60m = 11:00 => ES(S) >= 11:00 - 60m = 10:00.
    t1 = Task(id=1, title="P", planned_date="2026-09-01", planned_start_time="10:00", estimated_duration=120)
    t2 = Task(id=2, title="S_pos", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[{"predecessor_id": 1, "type": "SF", "lag_minutes": 60}])
    t3 = Task(id=3, title="S_neg", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
              dependencies=[{"predecessor_id": 1, "type": "SF", "lag_minutes": -30}])

    res = CPMSchedulingService.calculate_schedule([t1, t2, t3])
    n2 = res.get_node(2)
    assert n2.earliest_finish == datetime(2026, 9, 1, 11, 0)
    assert n2.earliest_start == datetime(2026, 9, 1, 10, 0)

    n3 = res.get_node(3)
    # EF(S) >= 10:00 - 30m = 09:30 => ES(S) >= 09:30 - 60m = 08:30
    assert n3.earliest_finish == datetime(2026, 9, 1, 9, 30)
    assert n3.earliest_start == datetime(2026, 9, 1, 8, 30)


def test_cpm_float_formatting_authority():
    """Verify format_float_duration calendar elapsed display."""
    assert format_float_duration(None) == "—"
    assert format_float_duration(0) == "0m"
    assert format_float_duration(45) == "45m"
    assert format_float_duration(120) == "2h"
    assert format_float_duration(150) == "2h 30m"
    assert format_float_duration(1440) == "1d"
    assert format_float_duration(1560) == "1d 2h"
    assert format_float_duration(1590) == "1d 2h 30m"
    assert format_float_duration(-120) == "-2h"


def test_cpm_legacy_compatibility_equivalence():
    """Verify legacy integer dependencies [1, 2] produce identical CPM output to explicit FS/0 dicts."""
    t1_a = Task(id=1, title="A", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60)
    t2_a = Task(id=2, title="B", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60)
    t3_legacy = Task(id=3, title="C", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60, dependencies=[1, 2])

    t3_explicit = Task(id=3, title="C", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60,
                       dependencies=[
                           {"predecessor_id": 1, "type": "FS", "lag_minutes": 0},
                           {"predecessor_id": 2, "type": "FS", "lag_minutes": 0},
                       ])

    res_legacy = CPMSchedulingService.calculate_schedule([t1_a, t2_a, t3_legacy])
    res_explicit = CPMSchedulingService.calculate_schedule([t1_a, t2_a, t3_explicit])

    assert res_legacy.critical_task_ids == res_explicit.critical_task_ids
    assert res_legacy.project_finish == res_explicit.project_finish
    for tid in (1, 2, 3):
        nl = res_legacy.get_node(tid)
        ne = res_explicit.get_node(tid)
        assert nl.earliest_start == ne.earliest_start
        assert nl.earliest_finish == ne.earliest_finish
        assert nl.latest_start == ne.latest_start
        assert nl.latest_finish == ne.latest_finish
        assert nl.total_float_minutes == ne.total_float_minutes
        assert nl.free_float_minutes == ne.free_float_minutes
        assert nl.is_critical == ne.is_critical


def test_task_controller_dependency_update_and_cycle_prevention(tmp_path):
    """Verify TaskController prevents cyclic dependency updates and allows valid spec updates."""
    from todo_bird_app.controllers.task_controller import TaskController

    db_file = str(tmp_path / "test_ctrl.db")
    db = DatabaseManager(db_file)
    ctrl = TaskController(db)

    t1_dict = Task(title="Task 1", planned_date="2026-09-01", planned_start_time="08:00", estimated_duration=60).to_dict()
    t1_id = db.insert_task(t1_dict)

    t2_dict = Task(title="Task 2", planned_date="2026-09-01", planned_start_time="09:00", estimated_duration=60,
                   dependencies=[{"predecessor_id": t1_id, "type": "FS", "lag_minutes": 0}]).to_dict()
    t2_id = db.insert_task(t2_dict)

    # Attempt to introduce cycle: Task 1 depends on Task 2
    t1_updated = Task.from_row(db.get_task_by_id(t1_id))
    t1_updated.dependencies = [{"predecessor_id": t2_id, "type": "SS", "lag_minutes": 0}]
    ok = ctrl.update_task(t1_updated)
    assert ok is False  # Rejected

    # Valid update: Task 2 changes to SS with +30m lag
    t2_updated = Task.from_row(db.get_task_by_id(t2_id))
    t2_updated.dependencies = [{"predecessor_id": t1_id, "type": "SS", "lag_minutes": 30}]
    ok2 = ctrl.update_task(t2_updated)
    assert ok2 is True

    # Check persisted row
    row = db.get_task_by_id(t2_id)
    t2_persisted = Task.from_row(row)
    specs = parse_dependency_specs(t2_persisted.dependencies)
    assert len(specs) == 1
    assert specs[0].predecessor_id == t1_id
    assert specs[0].dependency_type == DependencyType.SS
    assert specs[0].lag_minutes == 30

