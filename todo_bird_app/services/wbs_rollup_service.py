"""
TODO BIRD — WBS PROFESSIONAL PARENT ROLLUP AUTHORITY (Phase 1C)

Backward-compatible central authority for:
- existing Phase 1C WBS model/delegate/project contracts
- leaf-only aggregation
- calendar elapsed spans
- planned vs actual effort separation
- weighted progress
- project rollups
- diagnostics/confidence
- cached O(n) post-order computation

NO Qt.
NO DB writes.
NO parent-field mutation.
NO working-calendar reduction of elapsed time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Mapping, Optional, List, Tuple
from weakref import WeakKeyDictionary

from todo_bird_app.services.wbs_service import EntityRef, WBSHierarchySnapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RollupResult:
    # Original Phase-1C public contract
    node_key: Optional[EntityRef]
    leaf_count: int
    scheduled_leaf_count: int
    planned_start: Optional[datetime]
    planned_finish: Optional[datetime]
    planned_elapsed_minutes: Optional[int]
    planned_effort_minutes: int
    actual_effort_minutes: int
    actual_start: Optional[datetime]
    actual_finish: Optional[datetime]
    actual_elapsed_minutes: Optional[int]
    latest_actual_activity_at: Optional[datetime]
    progress_percent: int
    completed_leaf_count: int
    blocked_count: int
    delayed_count: int
    cancelled_count: int
    all_complete: bool
    is_summary: bool
    is_milestone: bool
    missing_schedule_count: int
    missing_effort_count: int
    missing_progress_count: int
    confidence: str
    source: str = "derived"

    # Extended compatibility / future consumers
    active_leaf_count: int = 0
    cancelled_leaf_count: int = 0
    milestone_leaf_count: int = 0
    has_schedule: bool = False
    has_actuals: bool = False
    all_terminal: bool = False
    actual_finish_complete: bool = False

    # Internal O(n) aggregate state
    _weighted_progress_sum: int = 0
    _positive_effort_sum: int = 0
    _active_progress_sum: int = 0
    _explicit_progress_count: int = 0
    _completed_active_count: int = 0

    @property
    def key(self):
        """Compatibility alias used by newer consumers."""
        return self.node_key

    @property
    def progress(self) -> int:
        """Compatibility alias used by newer consumers."""
        return self.progress_percent


class WBSRollupService:
    """Canonical derived WBS rollup service."""

    # Cache is scoped to the actual DatabaseManager object.
    # Never key by id(db_manager): CPython may reuse numeric object IDs.
    _cache = WeakKeyDictionary()

    # ==================================================================
    # CACHE
    # ==================================================================

    @classmethod
    def clear_cache(cls):
        cls._cache.clear()

    @classmethod
    def wire_signals(cls, snapshot, controller):
        """
        Compatibility hook.

        The authoritative invalidation remains explicit refresh/rebuild.
        If a controller exposes conventional mutation signals, clear cache
        opportunistically without creating a second controller authority.
        """
        if controller is None:
            return False

        connected = False
        for name in (
            "taskCreated",
            "taskUpdated",
            "taskDeleted",
            "task_changed",
            "tasksChanged",
            "dataChanged",
        ):
            sig = getattr(controller, name, None)
            if sig is not None and hasattr(sig, "connect"):
                try:
                    sig.connect(cls.clear_cache)
                    connected = True
                except Exception:
                    pass
        return connected

    # ==================================================================
    # PUBLIC DB-BACKED API — ORIGINAL CONTRACT
    # ==================================================================

    @classmethod
    def compute_all_rollups(
        cls,
        snapshot: WBSHierarchySnapshot,
        db_manager,
        cpm_result=None,
    ) -> Dict[EntityRef, RollupResult]:
        if db_manager is None or not snapshot.nodes_by_key:
            return {}

        # Callers passing an externally computed cpm_result bypass the cache:
        # that result is a moving object whose identity can't be keyed safely
        # (id() reuse would serve stale rollups). The auto-CPM path — the hot
        # one — is deterministic from (db, revision) and is cacheable.
        external_cpm = cpm_result is not None
        snapshot_key = (
            id(db_manager),
            snapshot.project_id,
            snapshot.revision,
            getattr(db_manager, "_data_revision", 0),
        )

        db_cache = cls._cache.get(db_manager)
        if db_cache is None:
            db_cache = {}
            cls._cache[db_manager] = db_cache

        if not external_cpm:
            cached = db_cache.get(snapshot_key)
            if cached is not None:
                return cached

        payloads = cls._bulk_fetch_payloads(
            db_manager,
            list(snapshot.nodes_by_key.keys()),
            project_id=snapshot.project_id,
        )

        if cpm_result is None and snapshot.project_id:
            try:
                from todo_bird_app.services.wbs_cpm_adapter import calculate_wbs_cpm

                proj_cal = None
                if hasattr(db_manager, "get_project_calendar"):
                    from todo_bird_app.services.schedule_calendar_service import (
                        effective_project_calendar_from_db,
                    )
                    proj_cal = effective_project_calendar_from_db(
                        db_manager,
                        snapshot.project_id,
                    )
                cpm_result = calculate_wbs_cpm(
                    snapshot,
                    db_manager,
                    project_calendar=proj_cal,
                    payload_by_key=payloads,
                )
            except Exception as e:
                logger.debug(f"compute_all_rollups automatic CPM calculation failed: {e}")

        if cpm_result is not None:
            from todo_bird_app.services.wbs_cpm_adapter import cpm_node_for_key

            for k, p in payloads.items():
                c_node = cpm_node_for_key(cpm_result, k)
                if c_node and c_node.earliest_start and c_node.earliest_finish:
                    p["cpm_earliest_start"] = c_node.earliest_start.isoformat()
                    p["cpm_earliest_finish"] = c_node.earliest_finish.isoformat()

        result = cls.calculate(snapshot, payloads)
        if not external_cpm:
            db_cache[snapshot_key] = result
        return result

    @classmethod
    def get_project_rollup(
        cls,
        snapshot: WBSHierarchySnapshot,
        db_manager,
    ) -> RollupResult:
        """
        Aggregate all project roots as one virtual summary.
        No second descendant scan.
        """
        rollups = cls.compute_all_rollups(snapshot, db_manager)
        roots = [
            rollups[k]
            for k in snapshot.root_keys
            if k in rollups
        ]

        return cls._merge_results(
            None,
            roots,
            is_summary=True,
            is_milestone=False,
        )

    @classmethod
    def get_rollup(
        cls,
        snapshot: WBSHierarchySnapshot,
        payload_or_db,
        key: EntityRef,
    ) -> Optional[RollupResult]:
        if hasattr(payload_or_db, "get_connection"):
            return cls.compute_all_rollups(
                snapshot,
                payload_or_db,
            ).get(key)

        return cls.calculate(
            snapshot,
            payload_or_db,
        ).get(key)

    # ==================================================================
    # PURE PAYLOAD API
    # ==================================================================

    @classmethod
    def calculate(
        cls,
        snapshot: WBSHierarchySnapshot,
        payload_by_key: Mapping[EntityRef, Any],
    ) -> Dict[EntityRef, RollupResult]:
        """
        O(n) iterative post-order traversal.

        Each leaf is processed once.
        Each child result is merged once into its direct parent.
        No descendant rescans.
        """
        results: Dict[EntityRef, RollupResult] = {}

        stack = [
            (key, False)
            for key in reversed(snapshot.root_keys)
        ]

        seen = set()

        while stack:
            key, visited = stack.pop()

            if not visited:
                if key in seen:
                    continue

                seen.add(key)
                stack.append((key, True))

                children = snapshot.children_by_parent.get(
                    key,
                    [],
                )
                for child in reversed(children):
                    stack.append((child, False))
                continue

            node = snapshot.nodes_by_key.get(key)
            if node is None:
                continue

            children = snapshot.children_by_parent.get(
                key,
                [],
            )

            if children:
                child_results = [
                    results[c]
                    for c in children
                    if c in results
                ]

                results[key] = cls._merge_results(
                    key,
                    child_results,
                    is_summary=True,
                    is_milestone=bool(node.is_milestone),
                )
            else:
                results[key] = cls._leaf_result(
                    key,
                    payload_by_key.get(key),
                    node_status=node.status,
                    is_completed=bool(node.is_completed),
                    is_milestone=bool(node.is_milestone),
                )

        # Defensive isolated-node handling.
        for key, node in snapshot.nodes_by_key.items():
            if key not in results:
                results[key] = cls._leaf_result(
                    key,
                    payload_by_key.get(key),
                    node_status=node.status,
                    is_completed=bool(node.is_completed),
                    is_milestone=bool(node.is_milestone),
                )

        return results

    # ==================================================================
    # LEAF DISCOVERY — PUBLIC ORIGINAL CONTRACT
    # ==================================================================

    @classmethod
    def get_leaves(
        cls,
        snapshot: WBSHierarchySnapshot,
        key: EntityRef,
    ) -> List[EntityRef]:
        """
        Return unique descendant leaves.

        This query API is intentionally separate from calculate(); calculate()
        itself never repeatedly calls get_leaves().
        """
        if key not in snapshot.nodes_by_key:
            return []

        children = snapshot.children_by_parent.get(key, [])
        if not children:
            return [key]

        leaves: List[EntityRef] = []
        stack = list(reversed(children))

        while stack:
            current = stack.pop()
            c = snapshot.children_by_parent.get(current, [])

            if c:
                stack.extend(reversed(c))
            else:
                leaves.append(current)

        return leaves

    # ==================================================================
    # BULK PAYLOAD FETCH — TWO PROJECT-SCOPED QUERIES
    # ==================================================================

    @classmethod
    def _bulk_fetch_payloads(
        cls,
        db_manager,
        keys,
        project_id=None,
    ) -> Dict[EntityRef, Dict[str, Any]]:

        wanted_tasks = {
            k.entity_id
            for k in keys
            if k.entity_type == "task"
        }
        wanted_subtasks = {
            k.entity_id
            for k in keys
            if k.entity_type == "subtask"
        }

        result: Dict[EntityRef, Dict[str, Any]] = {}

        if db_manager is None:
            return result

        with db_manager.get_connection() as conn:
            # ----------------------------------------------------------
            # Query 1: tasks
            # ----------------------------------------------------------
            if project_id is not None:
                rows = conn.execute(
                    "SELECT * FROM tasks WHERE project_id=?",
                    (project_id,),
                ).fetchall()
            elif wanted_tasks:
                placeholders = ",".join(
                    "?" for _ in wanted_tasks
                )
                rows = conn.execute(
                    f"SELECT * FROM tasks WHERE id IN ({placeholders})",
                    tuple(wanted_tasks),
                ).fetchall()
            else:
                rows = []

            for row in rows:
                d = dict(row)
                tid = int(d.get("id"))
                if wanted_tasks and tid not in wanted_tasks:
                    continue
                result[EntityRef.task(tid)] = d

            # ----------------------------------------------------------
            # Query 2: subtasks through owning task project
            # ----------------------------------------------------------
            if project_id is not None:
                rows = conn.execute(
                    """
                    SELECT s.*
                    FROM subtasks s
                    JOIN tasks t ON t.id = s.task_id
                    WHERE t.project_id=?
                    """,
                    (project_id,),
                ).fetchall()
            elif wanted_subtasks:
                placeholders = ",".join(
                    "?" for _ in wanted_subtasks
                )
                rows = conn.execute(
                    f"SELECT * FROM subtasks WHERE id IN ({placeholders})",
                    tuple(wanted_subtasks),
                ).fetchall()
            else:
                rows = []

            for row in rows:
                d = dict(row)
                sid = int(d.get("id"))
                if wanted_subtasks and sid not in wanted_subtasks:
                    continue

                # Subtasks use is_completed rather than canonical TaskStatus.
                if not d.get("status"):
                    d["status"] = (
                        "Completed"
                        if bool(d.get("is_completed"))
                        else "Planned"
                    )

                result[EntityRef.subtask(sid)] = d

        return result

    # ==================================================================
    # LEAF RESULT
    # ==================================================================

    @classmethod
    def _leaf_result(
        cls,
        key: EntityRef,
        payload: Any,
        *,
        node_status=None,
        is_completed=False,
        is_milestone=False,
    ) -> RollupResult:

        status = cls._status(payload, node_status)

        completed = (
            is_completed
            or status.lower() == "completed"
            or bool(cls._value(payload, "is_completed", False))
        )
        cancelled = status.lower() == "cancelled"
        blocked = status.lower() == "blocked"
        delayed = status.lower() == "delayed"

        planned_start = cls._leaf_planned_start(payload)
        planned_finish = cls._leaf_planned_finish(payload)

        scheduled = (
            planned_start is not None
            and planned_finish is not None
        )

        planned_elapsed = cls._elapsed(
            planned_start,
            planned_finish,
        )

        raw_planned_effort = max(
            0,
            cls._int(
                cls._value(
                    payload,
                    "planned_effort_minutes",
                    0,
                )
            ),
        )

        # Cancelled planned work is excluded from rollup plan.
        planned_effort = (
            0
            if cancelled
            else raw_planned_effort
        )

        # Actual work already performed remains historical truth,
        # including work on subsequently-cancelled tasks.
        actual_effort = max(
            0,
            cls._int(
                cls._value(
                    payload,
                    "actual_duration",
                    0,
                )
            ),
        )

        raw_progress = cls._clamp_progress(
            cls._value(payload, "progress", 0)
        )

        if cancelled:
            leaf_progress = 0
        elif completed:
            leaf_progress = 100
        elif is_milestone:
            leaf_progress = 0
        else:
            leaf_progress = raw_progress

        actual_start = cls._leaf_actual_start(payload)
        actual_end_raw = cls._leaf_actual_finish(payload)

        latest_actual_activity = cls._max_dt(
            actual_start,
            actual_end_raw,
        )

        # Completed work with an actual start must have an explicit end
        # before its summary can expose a final actual finish.
        finish_complete = (
            cancelled
            or (
                completed
                and (
                    actual_start is None
                    or actual_end_raw is not None
                )
            )
        )

        actual_finish = (
            actual_end_raw
            if completed and finish_complete
            else None
        )

        actual_elapsed = cls._elapsed(
            actual_start,
            actual_finish,
        )

        active_leaf_count = 0 if cancelled else 1
        explicit_progress_count = (
            1
            if (
                not cancelled
                and raw_progress != 0
            )
            else 0
        )

        positive_effort = (
            planned_effort
            if (
                not cancelled
                and planned_effort > 0
            )
            else 0
        )

        weighted_sum = (
            leaf_progress * positive_effort
        )

        missing_schedule = (
            0 if scheduled or cancelled else 1
        )
        missing_effort = (
            0
            if cancelled or raw_planned_effort > 0
            else 1
        )
        missing_progress = (
            0
            if (
                cancelled
                or completed
                or raw_progress != 0
            )
            else 1
        )

        confidence = cls._confidence(
            leaf_count=1,
            active_leaf_count=active_leaf_count,
            missing_schedule_count=missing_schedule,
            missing_effort_count=missing_effort,
            missing_progress_count=missing_progress,
        )

        return RollupResult(
            node_key=key,
            leaf_count=1,
            scheduled_leaf_count=1 if scheduled else 0,
            planned_start=planned_start,
            planned_finish=planned_finish,
            planned_elapsed_minutes=planned_elapsed,
            planned_effort_minutes=planned_effort,
            actual_effort_minutes=actual_effort,
            actual_start=actual_start,
            actual_finish=actual_finish,
            actual_elapsed_minutes=actual_elapsed,
            latest_actual_activity_at=latest_actual_activity,
            progress_percent=leaf_progress,
            completed_leaf_count=1 if completed else 0,
            blocked_count=1 if blocked else 0,
            delayed_count=1 if delayed else 0,
            cancelled_count=1 if cancelled else 0,
            all_complete=(completed or cancelled),
            is_summary=False,
            is_milestone=is_milestone,
            missing_schedule_count=missing_schedule,
            missing_effort_count=missing_effort,
            missing_progress_count=missing_progress,
            confidence=confidence,
            source="derived",
            active_leaf_count=active_leaf_count,
            cancelled_leaf_count=1 if cancelled else 0,
            milestone_leaf_count=1 if is_milestone else 0,
            has_schedule=scheduled,
            has_actuals=(
                actual_start is not None
                or actual_effort > 0
            ),
            all_terminal=(completed or cancelled),
            actual_finish_complete=finish_complete,
            _weighted_progress_sum=weighted_sum,
            _positive_effort_sum=positive_effort,
            _active_progress_sum=(
                leaf_progress
                if not cancelled
                else 0
            ),
            _explicit_progress_count=explicit_progress_count,
            _completed_active_count=(
                1
                if completed and not cancelled
                else 0
            ),
        )

    # ==================================================================
    # SUMMARY MERGE
    # ==================================================================

    @classmethod
    def _merge_results(
        cls,
        key: Optional[EntityRef],
        children: List[RollupResult],
        *,
        is_summary: bool,
        is_milestone: bool,
    ) -> RollupResult:

        if not children:
            return RollupResult(
                node_key=key,
                leaf_count=0,
                scheduled_leaf_count=0,
                planned_start=None,
                planned_finish=None,
                planned_elapsed_minutes=None,
                planned_effort_minutes=0,
                actual_effort_minutes=0,
                actual_start=None,
                actual_finish=None,
                actual_elapsed_minutes=None,
                latest_actual_activity_at=None,
                progress_percent=0,
                completed_leaf_count=0,
                blocked_count=0,
                delayed_count=0,
                cancelled_count=0,
                all_complete=False,
                is_summary=is_summary,
                is_milestone=is_milestone,
                missing_schedule_count=0,
                missing_effort_count=0,
                missing_progress_count=0,
                confidence="empty",
                source="derived",
            )

        leaf_count = sum(r.leaf_count for r in children)
        active_leaf_count = sum(
            r.active_leaf_count for r in children
        )
        cancelled_count = sum(
            r.cancelled_count for r in children
        )
        completed_leaf_count = sum(
            r.completed_leaf_count for r in children
        )

        scheduled_leaf_count = sum(
            r.scheduled_leaf_count for r in children
        )

        planned_starts = [
            r.planned_start
            for r in children
            if r.planned_start is not None
        ]
        planned_finishes = [
            r.planned_finish
            for r in children
            if r.planned_finish is not None
        ]

        planned_start = (
            min(planned_starts)
            if planned_starts
            else None
        )
        planned_finish = (
            max(planned_finishes)
            if planned_finishes
            else None
        )

        actual_starts = [
            r.actual_start
            for r in children
            if r.actual_start is not None
        ]
        actual_start = (
            min(actual_starts)
            if actual_starts
            else None
        )

        latest_actual_activity = cls._max_many(
            [
                r.latest_actual_activity_at
                for r in children
            ]
        )

        weighted_sum = sum(
            r._weighted_progress_sum for r in children
        )
        positive_effort_sum = sum(
            r._positive_effort_sum for r in children
        )
        active_progress_sum = sum(
            r._active_progress_sum for r in children
        )
        explicit_progress_count = sum(
            r._explicit_progress_count for r in children
        )
        completed_active_count = sum(
            r._completed_active_count for r in children
        )

        if active_leaf_count <= 0:
            progress = 0
        elif positive_effort_sum > 0:
            progress = cls._clamp_progress(
                round(
                    weighted_sum
                    / positive_effort_sum
                )
            )
        elif explicit_progress_count > 0:
            progress = cls._clamp_progress(
                round(
                    active_progress_sum
                    / active_leaf_count
                )
            )
        else:
            progress = cls._clamp_progress(
                round(
                    100
                    * completed_active_count
                    / active_leaf_count
                )
            )

        all_complete = (
            leaf_count > 0
            and (
                completed_leaf_count
                + cancelled_count
                == leaf_count
            )
        )

        finish_complete = (
            all_complete
            and all(
                r.actual_finish_complete
                for r in children
            )
        )

        if finish_complete:
            actual_finishes = [
                r.actual_finish
                for r in children
                if r.actual_finish is not None
            ]
            actual_finish = (
                max(actual_finishes)
                if actual_finishes
                else None
            )
        else:
            actual_finish = None

        planned_elapsed = cls._elapsed(
            planned_start,
            planned_finish,
        )

        # An unfinished summary has no final actual elapsed envelope.
        actual_elapsed = cls._elapsed(
            actual_start,
            actual_finish,
        )

        missing_schedule_count = sum(
            r.missing_schedule_count for r in children
        )
        missing_effort_count = sum(
            r.missing_effort_count for r in children
        )
        missing_progress_count = sum(
            r.missing_progress_count for r in children
        )

        confidence = cls._confidence(
            leaf_count=leaf_count,
            active_leaf_count=active_leaf_count,
            missing_schedule_count=missing_schedule_count,
            missing_effort_count=missing_effort_count,
            missing_progress_count=missing_progress_count,
        )

        return RollupResult(
            node_key=key,
            leaf_count=leaf_count,
            scheduled_leaf_count=scheduled_leaf_count,
            planned_start=planned_start,
            planned_finish=planned_finish,
            planned_elapsed_minutes=planned_elapsed,
            planned_effort_minutes=sum(
                r.planned_effort_minutes
                for r in children
            ),
            actual_effort_minutes=sum(
                r.actual_effort_minutes
                for r in children
            ),
            actual_start=actual_start,
            actual_finish=actual_finish,
            actual_elapsed_minutes=actual_elapsed,
            latest_actual_activity_at=latest_actual_activity,
            progress_percent=progress,
            completed_leaf_count=completed_leaf_count,
            blocked_count=sum(
                r.blocked_count for r in children
            ),
            delayed_count=sum(
                r.delayed_count for r in children
            ),
            cancelled_count=cancelled_count,
            all_complete=all_complete,
            is_summary=is_summary,
            is_milestone=is_milestone,
            missing_schedule_count=missing_schedule_count,
            missing_effort_count=missing_effort_count,
            missing_progress_count=missing_progress_count,
            confidence=confidence,
            source="derived",
            active_leaf_count=active_leaf_count,
            cancelled_leaf_count=cancelled_count,
            milestone_leaf_count=sum(
                r.milestone_leaf_count
                for r in children
            ),
            has_schedule=(
                planned_start is not None
                and planned_finish is not None
            ),
            has_actuals=(
                actual_start is not None
                or any(
                    r.actual_effort_minutes > 0
                    for r in children
                )
            ),
            all_terminal=all_complete,
            actual_finish_complete=finish_complete,
            _weighted_progress_sum=weighted_sum,
            _positive_effort_sum=positive_effort_sum,
            _active_progress_sum=active_progress_sum,
            _explicit_progress_count=explicit_progress_count,
            _completed_active_count=completed_active_count,
        )

    # ==================================================================
    # ORIGINAL HELPER CONTRACT
    # ==================================================================

    @classmethod
    def _leaf_planned_start(cls, payload):
        if not payload:
            return None

        cpm_start = cls._value(payload, "cpm_earliest_start") or cls._value(payload, "earliest_start")
        if cpm_start:
            from todo_bird_app.services.schedule_variance_service import parse_datetime_flexible
            parsed = parse_datetime_flexible(cpm_start)
            if parsed:
                return parsed

        planned_date = cls._value(
            payload,
            "planned_date",
        )
        start_time = cls._value(
            payload,
            "planned_start_time",
        )

        if not planned_date:
            return None

        if start_time:
            return cls._combine(
                planned_date,
                start_time,
            )

        # Date-only schedule starts at day boundary.
        return cls._combine(
            planned_date,
            "00:00",
        )

    @classmethod
    def _leaf_planned_finish(cls, payload):
        if not payload:
            return None

        cpm_finish_dt = None
        cpm_finish = cls._value(payload, "cpm_earliest_finish") or cls._value(payload, "earliest_finish")
        if cpm_finish:
            from todo_bird_app.services.schedule_variance_service import parse_datetime_flexible
            parsed = parse_datetime_flexible(cpm_finish)
            if parsed:
                cpm_finish_dt = parsed

        start = cls._leaf_planned_start(payload)
        raw_start = None

        planned_date = cls._value(
            payload,
            "planned_date",
        )
        due_date = cls._value(
            payload,
            "due_date",
        )
        end_time = cls._value(
            payload,
            "planned_end_time",
        )

        if planned_date:
            start_time = cls._value(
                payload,
                "planned_start_time",
            )
            raw_start = cls._combine(
                planned_date,
                start_time or "00:00",
            )

        raw_finish = None

        if end_time and (due_date or planned_date):
            raw_finish = cls._combine(
                due_date or planned_date,
                end_time,
            )

            if (
                raw_start is not None
                and raw_finish is not None
                and raw_finish < raw_start
                and (due_date or planned_date) == planned_date
            ):
                raw_finish += timedelta(days=1)

        else:
            estimated = max(
                0,
                cls._int(
                    cls._value(
                        payload,
                        "estimated_duration",
                        0,
                    )
                ),
            )

            if start is not None and estimated > 0:
                raw_finish = start + timedelta(minutes=estimated)

            # If a due date exists without a time, use end-of-day.
            elif due_date:
                raw_finish = cls._combine(
                    due_date,
                    "23:59",
                )

            # Date-only task with no explicit duration: same-day endpoint.
            elif planned_date and start is not None:
                raw_finish = cls._combine(
                    planned_date,
                    "23:59",
                )

        if cpm_finish_dt is not None:
            if raw_finish is not None and raw_finish > cpm_finish_dt:
                return raw_finish
            return cpm_finish_dt

        if raw_finish is not None:
            return raw_finish

        return None

    @classmethod
    def _leaf_actual_start(cls, payload):
        return cls._combine(
            cls._value(
                payload,
                "actual_start_date",
            ),
            cls._value(
                payload,
                "actual_start_time",
            ),
        )

    @classmethod
    def _leaf_actual_finish(cls, payload):
        return cls._combine(
            cls._value(
                payload,
                "actual_end_date",
            ),
            cls._value(
                payload,
                "actual_end_time",
            ),
        )

    # ==================================================================
    # LOW-LEVEL HELPERS
    # ==================================================================

    @staticmethod
    def _value(payload, name, default=None):
        if payload is None:
            return default
        if isinstance(payload, Mapping):
            return payload.get(name, default)
        return getattr(payload, name, default)

    @classmethod
    def _status(cls, payload, fallback=None) -> str:
        raw = cls._value(
            payload,
            "status",
            fallback,
        )
        if raw is None:
            return ""
        return str(getattr(raw, "value", raw))

    @staticmethod
    def _int(value) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _clamp_progress(cls, value) -> int:
        return max(
            0,
            min(
                100,
                cls._int(value),
            ),
        )

    @staticmethod
    def _combine(date_value, time_value):
        if not date_value or not time_value:
            return None

        text = f"{str(date_value).strip()} {str(time_value).strip()}"

        for fmt in (
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d %H:%M:%S",
        ):
            try:
                return datetime.strptime(
                    text,
                    fmt,
                )
            except (TypeError, ValueError):
                continue

        return None

    @staticmethod
    def _elapsed(start, finish):
        if start is None or finish is None:
            return None

        seconds = (
            finish - start
        ).total_seconds()

        if seconds < 0:
            return 0

        return int(seconds // 60)

    @staticmethod
    def _max_dt(a, b):
        vals = [
            v for v in (a, b)
            if v is not None
        ]
        return max(vals) if vals else None

    @staticmethod
    def _max_many(values):
        vals = [
            v for v in values
            if v is not None
        ]
        return max(vals) if vals else None

    @staticmethod
    def _confidence(
        *,
        leaf_count,
        active_leaf_count,
        missing_schedule_count,
        missing_effort_count,
        missing_progress_count,
    ):
        if leaf_count <= 0 or active_leaf_count <= 0:
            return "empty"

        if (
            missing_schedule_count == 0
            and missing_effort_count == 0
            and missing_progress_count == 0
        ):
            return "full"

        return "partial"
