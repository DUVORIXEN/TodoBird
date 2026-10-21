"""
TODO BIRD — GANTT WBS ADAPTER (Phase 1D)

Pure-data bridge between:
    WBSHierarchySnapshot
    + Phase 1C WBSRollupService
    -> canonical Gantt hierarchy rows

Goals:
- one WBS ordering/depth truth
- one rollup truth
- summary rows are derived/read-only
- no DB writes
- no Qt
- no duplicate rollup mathematics
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from todo_bird_app.services.wbs_service import (
    EntityRef,
    WBSHierarchySnapshot,
)
from todo_bird_app.services.wbs_rollup_service import (
    RollupResult,
    WBSRollupService,
)
from todo_bird_app.services.wbs_cpm_adapter import cpm_node_for_key
from todo_bird_app.services.wbs_cpm_adapter import build_wbs_cpm_summary_by_key


@dataclass(frozen=True)
class GanttWBSRow:
    key: EntityRef
    parent_key: Optional[EntityRef]
    project_id: Optional[int]

    depth: int
    wbs_code: str
    title: str

    is_summary: bool
    is_milestone: bool
    is_read_only: bool
    show_in_gantt: bool

    planned_start: Optional[datetime]
    planned_finish: Optional[datetime]
    planned_elapsed_minutes: Optional[int]
    planned_effort_minutes: int

    actual_start: Optional[datetime]
    actual_finish: Optional[datetime]

    # Latest known descendant execution activity. This is NOT the same
    # as actual_finish. It is used only for the visual end of an active
    # summary Actual lane.
    latest_actual_activity_at: Optional[datetime]

    actual_effort_minutes: int
    actual_elapsed_minutes: Optional[int]

    progress_percent: int
    leaf_count: int
    blocked_count: int
    delayed_count: int
    cancelled_count: int
    confidence: str

    status: str
    source_payload: Optional[Any] = None

    # Phase 2D Schedule Baseline & Variance
    baseline_start: Optional[datetime] = None
    baseline_finish: Optional[datetime] = None
    baseline_duration_minutes: Optional[int] = None
    has_baseline: bool = False
    finish_variance_minutes: Optional[int] = None
    start_variance_minutes: Optional[int] = None

    # Phase 2E CPM propagation. Values are copied from canonical CPM results;
    # this adapter does not calculate ES/EF/LS/LF or float.
    cpm_earliest_start: Optional[datetime] = None
    cpm_earliest_finish: Optional[datetime] = None
    cpm_latest_start: Optional[datetime] = None
    cpm_latest_finish: Optional[datetime] = None
    cpm_total_float_minutes: Optional[int] = None
    cpm_free_float_minutes: Optional[int] = None
    cpm_is_critical: bool = False
    cpm_schedulable: bool = False
    cpm_diagnostics: tuple = ()
    cpm_analysis_status: str = "not_analyzed"
    dependency_summary: str = ""


class GanttWBSAdapter:
    """Canonical read-only hierarchy adapter for Gantt presentation."""

    @staticmethod
    def _value(payload: Any, name: str, default=None):
        if payload is None:
            return default
        if isinstance(payload, Mapping):
            return payload.get(name, default)
        return getattr(payload, name, default)

    @classmethod
    def build_rows(
        cls,
        snapshot: WBSHierarchySnapshot,
        payload_by_key: Mapping[EntityRef, Any],
        rollups: Optional[Mapping[EntityRef, RollupResult]] = None,
        cpm_result: Optional[Any] = None,
    ) -> List[GanttWBSRow]:
        """
        Produce deterministic pre-order WBS rows.

        Visibility:
        - leaf visible when its stored show_in_gantt is true
        - summary visible when:
            a) its own show_in_gantt is true, OR
            b) any descendant is visible
        This guarantees parents remain available for hierarchy context.
        """
        if rollups is None:
            rollups = WBSRollupService.calculate(
                snapshot,
                payload_by_key,
            )
        summary_cpm_by_key = build_wbs_cpm_summary_by_key(
            snapshot,
            cpm_result,
        )

        own_visible: Dict[EntityRef, bool] = {}
        effective_visible: Dict[EntityRef, bool] = {}

        for key in snapshot.nodes_by_key:
            payload = payload_by_key.get(key)

            raw = cls._value(
                payload,
                "show_in_gantt",
                False,
            )

            own_visible[key] = bool(raw)

        # ------------------------------------------------------------
        # Bottom-up visibility closure — iterative, no recursion.
        # ------------------------------------------------------------
        postorder = []
        stack = [
            (k, False)
            for k in reversed(snapshot.root_keys)
        ]

        seen = set()

        while stack:
            key, visited = stack.pop()

            if not visited:
                if key in seen:
                    continue

                seen.add(key)
                stack.append((key, True))

                for child in reversed(
                    snapshot.children_by_parent.get(
                        key,
                        [],
                    )
                ):
                    stack.append((child, False))
            else:
                postorder.append(key)

        for key in postorder:
            children = snapshot.children_by_parent.get(
                key,
                [],
            )

            descendant_visible = any(
                effective_visible.get(child, False)
                for child in children
            )

            effective_visible[key] = (
                own_visible.get(key, False)
                or descendant_visible
            )

        rows: List[GanttWBSRow] = []

        # ------------------------------------------------------------
        # Canonical pre-order traversal.
        # ------------------------------------------------------------
        stack = list(reversed(snapshot.root_keys))

        while stack:
            key = stack.pop()

            node = snapshot.nodes_by_key.get(key)
            if node is None:
                continue

            children = snapshot.children_by_parent.get(
                key,
                [],
            )

            # Push regardless of parent's own visibility because a child
            # may independently be visible.
            for child in reversed(children):
                stack.append(child)

            if not effective_visible.get(key, False):
                continue

            rollup = rollups.get(key)
            payload = payload_by_key.get(key)
            cpm_node = cpm_node_for_key(cpm_result, key) if cpm_result is not None else None

            status_raw = cls._value(
                payload,
                "status",
                node.status or "Planned",
            )
            status = str(
                getattr(status_raw, "value", status_raw)
                or "Planned"
            )

            is_summary = bool(children)
            summary_cpm = summary_cpm_by_key.get(key) if is_summary else None

            if rollup is None:
                # Defensive only: normal path has one RollupResult/node.
                planned_start = None
                planned_finish = None
                planned_elapsed = None
                planned_effort = 0
                actual_start = None
                actual_finish = None
                latest_actual_activity = None
                actual_effort = 0
                actual_elapsed = None
                progress = 100 if node.is_completed else 0
                leaf_count = 0
                blocked = 0
                delayed = 0
                cancelled = 0
                confidence = "empty"
            else:
                planned_start = rollup.planned_start
                planned_finish = rollup.planned_finish
                planned_elapsed = rollup.planned_elapsed_minutes
                planned_effort = rollup.planned_effort_minutes

                actual_start = rollup.actual_start
                actual_finish = rollup.actual_finish
                latest_actual_activity = (
                    rollup.latest_actual_activity_at
                )
                actual_effort = rollup.actual_effort_minutes
                actual_elapsed = rollup.actual_elapsed_minutes

                progress = rollup.progress_percent
                leaf_count = rollup.leaf_count
                blocked = rollup.blocked_count
                delayed = rollup.delayed_count
                cancelled = rollup.cancelled_count
                confidence = rollup.confidence

            # Baseline calculation for leaf / summary
            from todo_bird_app.services.schedule_variance_service import parse_datetime_flexible

            if planned_start is None and payload:
                planned_start = parse_datetime_flexible(cls._value(payload, "planned_start"))
            if planned_finish is None and payload:
                planned_finish = parse_datetime_flexible(cls._value(payload, "planned_finish"))
            if not is_summary and cpm_node is not None and getattr(cpm_node, "schedulable", False):
                planned_start = getattr(cpm_node, "earliest_start", None) or planned_start
                planned_finish = getattr(cpm_node, "earliest_finish", None) or planned_finish

            b_start: Optional[datetime] = None
            b_finish: Optional[datetime] = None
            b_dur: Optional[int] = None
            has_baseline: bool = False

            if not is_summary:
                b_start_raw = cls._value(payload, "baseline_start", None)
                b_finish_raw = cls._value(payload, "baseline_finish", None)
                b_dur_raw = cls._value(payload, "baseline_duration_minutes", None)
                if b_start_raw and b_finish_raw:
                    b_start = parse_datetime_flexible(b_start_raw)
                    b_finish = parse_datetime_flexible(b_finish_raw)
                    b_dur = int(b_dur_raw) if b_dur_raw is not None else None
                    has_baseline = bool(b_start and b_finish)
            else:
                # Summary baseline = min child baseline start, max child baseline finish
                from todo_bird_app.services.wbs_service import WBSService
                child_starts = []
                child_finishes = []
                descendants = WBSService.get_descendants(snapshot, key)
                for d_node in descendants:
                    d_payload = payload_by_key.get(d_node.key)
                    d_bs_raw = cls._value(d_payload, "baseline_start", None)
                    d_bf_raw = cls._value(d_payload, "baseline_finish", None)
                    if d_bs_raw and d_bf_raw:
                        d_bs = parse_datetime_flexible(d_bs_raw)
                        d_bf = parse_datetime_flexible(d_bf_raw)
                        if d_bs and d_bf:
                            child_starts.append(d_bs)
                            child_finishes.append(d_bf)
                if child_starts and child_finishes:
                    b_start = min(child_starts)
                    b_finish = max(child_finishes)
                    b_dur = int((b_finish - b_start).total_seconds() / 60)
                    has_baseline = True

            start_var = int((planned_start - b_start).total_seconds() / 60) if (has_baseline and planned_start and b_start) else None
            finish_var = int((planned_finish - b_finish).total_seconds() / 60) if (has_baseline and planned_finish and b_finish) else None
            diagnostics = tuple(getattr(cpm_node, "diagnostic_codes", ()) or ()) if cpm_node is not None else ()
            analysis_status = (
                "analyzed"
                if cpm_node is not None and getattr(cpm_node, "schedulable", False)
                else ("blocked" if cpm_node is not None else "not_analyzed")
            )
            if summary_cpm is not None:
                diagnostics = tuple(getattr(summary_cpm, "diagnostic_codes", ()) or ())
                analysis_status = getattr(summary_cpm, "analysis_status", "summary")
            dep_summary = cls._dependency_summary(cpm_result, key)

            rows.append(
                GanttWBSRow(
                    key=key,
                    parent_key=node.parent_key,
                    project_id=node.project_id,
                    depth=int(node.depth),
                    wbs_code=node.wbs_code,
                    title=node.title,
                    is_summary=is_summary,
                    is_milestone=bool(node.is_milestone),
                    # All summary schedules are derived from descendants.
                    is_read_only=is_summary,
                    show_in_gantt=True,
                    planned_start=planned_start,
                    planned_finish=planned_finish,
                    planned_elapsed_minutes=planned_elapsed,
                    planned_effort_minutes=int(planned_effort or 0),
                    actual_start=actual_start,
                    actual_finish=actual_finish,
                    latest_actual_activity_at=latest_actual_activity,
                    actual_effort_minutes=int(actual_effort or 0),
                    actual_elapsed_minutes=actual_elapsed,
                    baseline_start=b_start,
                    baseline_finish=b_finish,
                    baseline_duration_minutes=b_dur,
                    has_baseline=has_baseline,
                    start_variance_minutes=start_var,
                    finish_variance_minutes=finish_var,
                    cpm_earliest_start=(
                        getattr(summary_cpm, "earliest_start", None)
                        if summary_cpm is not None
                        else (getattr(cpm_node, "earliest_start", None) if cpm_node is not None else None)
                    ),
                    cpm_earliest_finish=(
                        getattr(summary_cpm, "earliest_finish", None)
                        if summary_cpm is not None
                        else (getattr(cpm_node, "earliest_finish", None) if cpm_node is not None else None)
                    ),
                    cpm_latest_start=(
                        getattr(summary_cpm, "latest_start", None)
                        if summary_cpm is not None
                        else (getattr(cpm_node, "latest_start", None) if cpm_node is not None else None)
                    ),
                    cpm_latest_finish=(
                        getattr(summary_cpm, "latest_finish", None)
                        if summary_cpm is not None
                        else (getattr(cpm_node, "latest_finish", None) if cpm_node is not None else None)
                    ),
                    cpm_total_float_minutes=(
                        None
                        if summary_cpm is not None
                        else (getattr(cpm_node, "total_float_minutes", None) if cpm_node is not None else None)
                    ),
                    cpm_free_float_minutes=(
                        None
                        if summary_cpm is not None
                        else (getattr(cpm_node, "free_float_minutes", None) if cpm_node is not None else None)
                    ),
                    cpm_is_critical=(
                        bool(getattr(summary_cpm, "contains_critical", False))
                        if summary_cpm is not None
                        else (bool(getattr(cpm_node, "is_critical", False)) if cpm_node is not None else False)
                    ),
                    cpm_schedulable=(
                        bool(getattr(summary_cpm, "schedulable", False))
                        if summary_cpm is not None
                        else (bool(getattr(cpm_node, "schedulable", False)) if cpm_node is not None else False)
                    ),
                    cpm_diagnostics=diagnostics,
                    cpm_analysis_status=analysis_status,
                    dependency_summary=dep_summary,
                    progress_percent=max(
                        0,
                        min(100, int(progress or 0)),
                    ),
                    leaf_count=int(leaf_count or 0),
                    blocked_count=int(blocked or 0),
                    delayed_count=int(delayed or 0),
                    cancelled_count=int(cancelled or 0),
                    confidence=confidence,
                    status=status,
                    source_payload=payload,
                )
            )

        return rows

    @classmethod
    def _dependency_summary(cls, cpm_result: Optional[Any], key: EntityRef) -> str:
        if cpm_result is None:
            return ""
        input_nodes = getattr(cpm_result, "input_nodes", {}) or {}
        input_node = input_nodes.get(key)
        if input_node is None:
            return ""
        pred_count = len(getattr(input_node, "predecessors", ()) or ())
        succ_count = len(getattr(input_node, "successors", ()) or ())
        if pred_count == 0 and succ_count == 0:
            return "No dependencies"
        parts = []
        if pred_count:
            parts.append(f"{pred_count} predecessor{'s' if pred_count != 1 else ''}")
        if succ_count:
            parts.append(f"{succ_count} successor{'s' if succ_count != 1 else ''}")
        return ", ".join(parts)

    @classmethod
    def build_project_rows(
        cls,
        snapshot: WBSHierarchySnapshot,
        db_manager,
    ) -> List[GanttWBSRow]:
        """
        DB-backed convenience API.

        Uses Phase 1C bulk payload fetch and cached rollup authority.
        Still performs no DB writes.
        """
        payloads = WBSRollupService._bulk_fetch_payloads(
            db_manager,
            list(snapshot.nodes_by_key.keys()),
            project_id=snapshot.project_id,
        )

        cpm_result = None
        if snapshot.project_id is not None:
            try:
                from todo_bird_app.services.schedule_calendar_service import (
                    effective_project_calendar_from_db,
                )
                from todo_bird_app.services.wbs_cpm_adapter import calculate_wbs_cpm

                cpm_result = calculate_wbs_cpm(
                    snapshot,
                    db_manager,
                    project_calendar=effective_project_calendar_from_db(
                        db_manager,
                        snapshot.project_id,
                    ),
                    payload_by_key=payloads,
                )
            except Exception:
                cpm_result = None

        rollups = WBSRollupService.compute_all_rollups(
            snapshot,
            db_manager,
            cpm_result=cpm_result,
        )

        return cls.build_rows(
            snapshot,
            payloads,
            rollups,
            cpm_result=cpm_result,
        )
