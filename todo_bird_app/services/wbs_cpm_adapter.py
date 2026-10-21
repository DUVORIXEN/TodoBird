"""
Todo Bird WBS CPM adapter.

This module is intentionally pure-data: it does not perform CPM mathematics.
It adapts WBS leaf work packages to the existing CPMSchedulingService, then
maps the canonical results back to typed EntityRef keys so task/subtask integer
IDs cannot collide in UI consumers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from todo_bird_app.models.task import Task
from todo_bird_app.services.cpm_scheduling_service import (
    CPMSchedulingService,
    DependencySpec,
    DependencyType,
    ScheduleDiagnostic,
    ScheduleNodeResult,
    SchedulingResult,
    parse_lag_duration,
)
from todo_bird_app.services.schedule_constraint_service import ProjectCalendarSpec
from todo_bird_app.services.wbs_service import EntityRef, WBSHierarchySnapshot


@dataclass(frozen=True)
class WBSCPMInputNode:
    key: EntityRef
    cpm_id: int
    title: str
    entity_type: str
    entity_id: int
    duration_minutes: int
    planned_date: Optional[str]
    planned_start_time: Optional[str]
    predecessors: Tuple[EntityRef, ...]
    successors: Tuple[EntityRef, ...]


@dataclass(frozen=True)
class WBSCPMSummaryResult:
    """
    Derived schedule envelope for a WBS summary row.

    This is presentation metadata only. It is not a CPM leaf node and must not
    be written back into task/subtask raw schedule fields.
    """
    key: EntityRef
    descendant_leaf_count: int
    schedulable_leaf_count: int
    blocked_leaf_count: int
    unanalyzed_leaf_count: int
    critical_leaf_count: int
    earliest_start: Optional[Any]
    earliest_finish: Optional[Any]
    latest_start: Optional[Any]
    latest_finish: Optional[Any]
    diagnostic_codes: Tuple[Any, ...] = ()
    contains_cycle: bool = False

    @property
    def contains_critical(self) -> bool:
        return self.critical_leaf_count > 0

    @property
    def schedulable(self) -> bool:
        return self.schedulable_leaf_count > 0

    @property
    def analysis_status(self) -> str:
        if self.contains_cycle:
            return "blocked"
        if self.blocked_leaf_count > 0:
            return "incomplete"
        if self.schedulable_leaf_count > 0:
            return "summary"
        return "not_analyzed"

    @property
    def critical_label(self) -> str:
        if self.contains_critical:
            return "Contains Critical"
        if self.schedulable_leaf_count > 0:
            return "No Critical"
        return "N/A (Summary)"

    @property
    def health_label(self) -> str:
        if self.contains_cycle:
            return "Blocked (Cycle)"
        if self.blocked_leaf_count > 0:
            return "At Risk"
        if self.schedulable_leaf_count > 0:
            return "Healthy"
        return "N/A (Summary)"


class WBSCPMNodeMap(dict):
    """EntityRef-keyed node map with legacy task-id read compatibility."""

    @staticmethod
    def _legacy_key(key: Any) -> Any:
        if isinstance(key, int):
            return EntityRef.task(key)
        return key

    def __contains__(self, key: Any) -> bool:
        return dict.__contains__(self, key) or dict.__contains__(self, self._legacy_key(key))

    def __getitem__(self, key: Any) -> ScheduleNodeResult:
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        return dict.__getitem__(self, self._legacy_key(key))

    def get(self, key: Any, default=None):
        if dict.__contains__(self, key):
            return dict.get(self, key, default)
        return dict.get(self, self._legacy_key(key), default)


@dataclass(frozen=True)
class WBSCPMResult:
    project_id: Optional[int]
    cpm_result: SchedulingResult
    nodes: WBSCPMNodeMap
    cpm_id_by_key: Dict[EntityRef, int]
    key_by_cpm_id: Dict[int, EntityRef]
    input_nodes: Dict[EntityRef, WBSCPMInputNode]
    dependency_specs_by_key: Dict[EntityRef, Tuple[DependencySpec, ...]]
    diagnostics: Tuple[ScheduleDiagnostic, ...]
    has_cycles: bool
    cycle_keys: Tuple[EntityRef, ...]
    critical_keys: Tuple[EntityRef, ...]
    critical_paths: Tuple[Tuple[EntityRef, ...], ...]
    is_complete: bool

    def get_node(
        self,
        key_or_id: Any,
        entity_type: Optional[str] = None,
    ) -> Optional[ScheduleNodeResult]:
        key = coerce_entity_ref(key_or_id, entity_type=entity_type)
        if key is not None:
            return self.nodes.get(key)

        try:
            legacy_id = int(key_or_id)
        except (TypeError, ValueError):
            return None

        task_key = EntityRef.task(legacy_id)
        if task_key in self.nodes:
            return self.nodes[task_key]
        return None

    @property
    def total_tasks(self) -> int:
        return len(self.nodes)

    @property
    def schedulable_tasks(self) -> int:
        return sum(1 for node in self.nodes.values() if node.schedulable)

    @property
    def critical_task_ids(self) -> Tuple[int, ...]:
        return tuple(self.cpm_id_by_key[key] for key in self.critical_keys)

    @property
    def cycle_task_ids(self) -> Tuple[int, ...]:
        return tuple(self.cpm_id_by_key[key] for key in self.cycle_keys)


def coerce_entity_ref(
    key_or_id: Any,
    *,
    entity_type: Optional[str] = None,
) -> Optional[EntityRef]:
    if isinstance(key_or_id, EntityRef):
        return key_or_id

    if isinstance(key_or_id, tuple) and len(key_or_id) == 2:
        try:
            return EntityRef(str(key_or_id[0]), int(key_or_id[1]))
        except Exception:
            return None

    if isinstance(key_or_id, str) and ":" in key_or_id:
        try:
            return EntityRef.from_string(key_or_id)
        except Exception:
            return None

    if entity_type:
        try:
            return EntityRef(str(entity_type), int(key_or_id))
        except Exception:
            return None

    return None


def cpm_node_for_key(
    cpm_result: Any,
    key: EntityRef,
) -> Optional[ScheduleNodeResult]:
    if cpm_result is None or key is None:
        return None
    typed_result = hasattr(cpm_result, "cpm_id_by_key")

    getter = getattr(cpm_result, "get_node", None)
    if callable(getter):
        for candidate in (
            key,
            (key.entity_type, key.entity_id),
            str(key),
        ):
            try:
                node = getter(candidate)
            except TypeError:
                node = None
            if node is not None:
                return node
        if key.entity_type == "task" and not typed_result:
            try:
                node = getter(key.entity_id)
            except TypeError:
                node = None
            if node is not None:
                return node

    nodes = getattr(cpm_result, "nodes", None)
    if isinstance(nodes, Mapping):
        for candidate in (
            key,
            (key.entity_type, key.entity_id),
            str(key),
        ):
            node = nodes.get(candidate)
            if node is not None:
                return node
        if key.entity_type == "task" and not typed_result:
            node = nodes.get(key.entity_id)
            if node is not None:
                return node

    return None


def cpm_key_in_cycles(cpm_result: Any, key: EntityRef) -> bool:
    if cpm_result is None or key is None:
        return False
    cycle_keys = getattr(cpm_result, "cycle_keys", None)
    if cycle_keys is not None:
        return key in set(cycle_keys)
    return key.entity_type == "task" and key.entity_id in set(
        getattr(cpm_result, "cycle_task_ids", ()) or ()
    )


def build_wbs_cpm_summary_by_key(
    snapshot: WBSHierarchySnapshot,
    cpm_result: Any,
) -> Dict[EntityRef, WBSCPMSummaryResult]:
    """
    Build descendant CPM summary envelopes for WBS parent rows.

    Rules:
    - summary ES/LS use the earliest descendant ES/LS.
    - summary EF/LF use the latest descendant EF/LF.
    - summary duration/span is an envelope, not a sum.
    - total/free float remain intentionally undefined for summaries.
    - critical means the summary contains at least one critical descendant.
    """
    if cpm_result is None or snapshot is None or not snapshot.nodes_by_key:
        return {}

    aggregate_by_key: Dict[EntityRef, WBSCPMSummaryResult] = {}
    summary_by_key: Dict[EntityRef, WBSCPMSummaryResult] = {}

    def first_min(values: List[Any]) -> Optional[Any]:
        clean = [v for v in values if v is not None]
        return min(clean) if clean else None

    def first_max(values: List[Any]) -> Optional[Any]:
        clean = [v for v in values if v is not None]
        return max(clean) if clean else None

    for node in sorted(
        snapshot.nodes_by_key.values(),
        key=lambda item: item.depth,
        reverse=True,
    ):
        children = snapshot.children_by_parent.get(node.key, [])
        if children:
            child_summaries = [
                aggregate_by_key[child]
                for child in children
                if child in aggregate_by_key
            ]
            result = WBSCPMSummaryResult(
                key=node.key,
                descendant_leaf_count=sum(s.descendant_leaf_count for s in child_summaries),
                schedulable_leaf_count=sum(s.schedulable_leaf_count for s in child_summaries),
                blocked_leaf_count=sum(s.blocked_leaf_count for s in child_summaries),
                unanalyzed_leaf_count=sum(s.unanalyzed_leaf_count for s in child_summaries),
                critical_leaf_count=sum(s.critical_leaf_count for s in child_summaries),
                earliest_start=first_min([s.earliest_start for s in child_summaries]),
                earliest_finish=first_max([s.earliest_finish for s in child_summaries]),
                latest_start=first_min([s.latest_start for s in child_summaries]),
                latest_finish=first_max([s.latest_finish for s in child_summaries]),
                diagnostic_codes=tuple(
                    code
                    for summary in child_summaries
                    for code in summary.diagnostic_codes
                ),
                contains_cycle=any(s.contains_cycle for s in child_summaries),
            )
            aggregate_by_key[node.key] = result
            summary_by_key[node.key] = result
            continue

        cpm_node = cpm_node_for_key(cpm_result, node.key)
        in_cycle = cpm_key_in_cycles(cpm_result, node.key)
        schedulable = bool(cpm_node and getattr(cpm_node, "schedulable", False) and not in_cycle)
        blocked = bool(cpm_node and not schedulable) or in_cycle
        diagnostics = tuple(getattr(cpm_node, "diagnostic_codes", ()) or ()) if cpm_node else ()

        aggregate_by_key[node.key] = WBSCPMSummaryResult(
            key=node.key,
            descendant_leaf_count=1,
            schedulable_leaf_count=1 if schedulable else 0,
            blocked_leaf_count=1 if blocked else 0,
            unanalyzed_leaf_count=0 if cpm_node else 1,
            critical_leaf_count=1 if (schedulable and bool(getattr(cpm_node, "is_critical", False))) else 0,
            earliest_start=getattr(cpm_node, "earliest_start", None) if schedulable else None,
            earliest_finish=getattr(cpm_node, "earliest_finish", None) if schedulable else None,
            latest_start=getattr(cpm_node, "latest_start", None) if schedulable else None,
            latest_finish=getattr(cpm_node, "latest_finish", None) if schedulable else None,
            diagnostic_codes=diagnostics,
            contains_cycle=in_cycle,
        )

    return summary_by_key


def calculate_wbs_cpm(
    snapshot: WBSHierarchySnapshot,
    db_manager,
    *,
    project_calendar: Optional[ProjectCalendarSpec] = None,
    payload_by_key: Optional[Mapping[EntityRef, Any]] = None,
) -> WBSCPMResult:
    if db_manager is None:
        raise ValueError("db_manager is required")

    if payload_by_key is None:
        from todo_bird_app.services.wbs_rollup_service import WBSRollupService

        payload_by_key = WBSRollupService._bulk_fetch_payloads(
            db_manager,
            list(snapshot.nodes_by_key.keys()),
            project_id=snapshot.project_id,
        )

    leaf_keys = _ordered_leaf_keys(snapshot, payload_by_key)
    cpm_id_by_key = {key: idx + 1 for idx, key in enumerate(leaf_keys)}
    key_by_cpm_id = {cpm_id: key for key, cpm_id in cpm_id_by_key.items()}

    tasks: List[Task] = []
    dependency_specs_by_key: Dict[EntityRef, Tuple[DependencySpec, ...]] = {}
    predecessor_keys_by_key: Dict[EntityRef, List[EntityRef]] = {
        key: [] for key in leaf_keys
    }
    successor_keys_by_key: Dict[EntityRef, List[EntityRef]] = {
        key: [] for key in leaf_keys
    }
    missing_dependency_ids: Dict[int, int] = {}
    missing_base = len(cpm_id_by_key) + 1_000_000

    def missing_cpm_id(raw_id: int) -> int:
        if raw_id not in missing_dependency_ids:
            missing_dependency_ids[raw_id] = missing_base + len(missing_dependency_ids)
        return missing_dependency_ids[raw_id]

    for key in leaf_keys:
        payload = payload_by_key.get(key)
        raw_deps = _raw_dependencies(payload)
        rewritten_deps: List[DependencySpec] = []
        successor_cpm_id = cpm_id_by_key[key]

        for raw_item, spec in _dependency_specs(raw_deps):
            pred_key = _resolve_predecessor_key(
                raw_item,
                spec.predecessor_id,
                successor_key=key,
                cpm_id_by_key=cpm_id_by_key,
            )
            predecessor_cpm_id = (
                cpm_id_by_key[pred_key]
                if pred_key in cpm_id_by_key
                else missing_cpm_id(int(spec.predecessor_id))
            )
            rewritten_deps.append(
                DependencySpec(
                    predecessor_id=predecessor_cpm_id,
                    successor_id=successor_cpm_id,
                    dependency_type=spec.dependency_type,
                    lag_minutes=int(spec.lag_minutes or 0),
                )
            )
            if pred_key in cpm_id_by_key:
                predecessor_keys_by_key[key].append(pred_key)
                successor_keys_by_key[pred_key].append(key)

        dependency_specs_by_key[key] = tuple(rewritten_deps)
        tasks.append(_task_from_payload(key, payload, successor_cpm_id, rewritten_deps, snapshot.project_id))

    cpm_result = CPMSchedulingService.calculate_schedule(
        tasks,
        project_id=snapshot.project_id,
        project_calendar=project_calendar,
    )

    nodes = WBSCPMNodeMap()
    for cpm_id, node in (getattr(cpm_result, "nodes", {}) or {}).items():
        key = key_by_cpm_id.get(int(cpm_id))
        if key is not None:
            nodes[key] = node

    input_nodes: Dict[EntityRef, WBSCPMInputNode] = {}
    for key in leaf_keys:
        payload = payload_by_key.get(key)
        input_nodes[key] = WBSCPMInputNode(
            key=key,
            cpm_id=cpm_id_by_key[key],
            title=str(_value(payload, "title", "") or ""),
            entity_type=key.entity_type,
            entity_id=key.entity_id,
            duration_minutes=_int(_value(payload, "estimated_duration", 0)),
            planned_date=_optional_text(_value(payload, "planned_date", None)),
            planned_start_time=_optional_text(_value(payload, "planned_start_time", None)),
            predecessors=tuple(predecessor_keys_by_key[key]),
            successors=tuple(successor_keys_by_key[key]),
        )

    cycle_keys = tuple(
        key_by_cpm_id[cpm_id]
        for cpm_id in getattr(cpm_result, "cycle_task_ids", ()) or ()
        if cpm_id in key_by_cpm_id
    )
    critical_keys = tuple(
        key_by_cpm_id[cpm_id]
        for cpm_id in getattr(cpm_result, "critical_task_ids", ()) or ()
        if cpm_id in key_by_cpm_id
    )
    critical_paths = tuple(
        tuple(key_by_cpm_id[cpm_id] for cpm_id in path if cpm_id in key_by_cpm_id)
        for path in getattr(cpm_result, "critical_paths", ()) or ()
    )

    return WBSCPMResult(
        project_id=snapshot.project_id,
        cpm_result=cpm_result,
        nodes=nodes,
        cpm_id_by_key=cpm_id_by_key,
        key_by_cpm_id=key_by_cpm_id,
        input_nodes=input_nodes,
        dependency_specs_by_key=dependency_specs_by_key,
        diagnostics=tuple(getattr(cpm_result, "diagnostics", ()) or ()),
        has_cycles=bool(getattr(cpm_result, "has_cycles", False)),
        cycle_keys=cycle_keys,
        critical_keys=critical_keys,
        critical_paths=critical_paths,
        is_complete=bool(getattr(cpm_result, "is_complete", True)),
    )


def _ordered_leaf_keys(
    snapshot: WBSHierarchySnapshot,
    payload_by_key: Mapping[EntityRef, Any],
) -> List[EntityRef]:
    ordered: List[EntityRef] = []
    stack = list(reversed(snapshot.root_keys))
    while stack:
        key = stack.pop()
        children = snapshot.children_by_parent.get(key, [])
        for child in reversed(children):
            stack.append(child)
        if children:
            continue
        payload = payload_by_key.get(key)
        if payload is None:
            continue
        if _is_closed(payload):
            continue
        ordered.append(key)
    return ordered


def _is_closed(payload: Any) -> bool:
    status = str(
        getattr(_value(payload, "status", ""), "value", _value(payload, "status", ""))
        or ""
    ).strip().lower()
    if status in {"completed", "cancelled", "archived"}:
        return True
    if bool(_value(payload, "is_completed", False)):
        return True
    return False


def _task_from_payload(
    key: EntityRef,
    payload: Any,
    cpm_id: int,
    dependencies: Iterable[DependencySpec],
    project_id: Optional[int],
) -> Task:
    return Task(
        id=cpm_id,
        project_id=project_id,
        title=str(_value(payload, "title", "") or str(key)),
        status=_value(payload, "status", "Planned") or "Planned",
        planned_date=_value(payload, "planned_date", None),
        due_date=_value(payload, "due_date", None),
        planned_start_time=_value(payload, "planned_start_time", None),
        planned_end_time=_value(payload, "planned_end_time", None),
        estimated_duration=_int(_value(payload, "estimated_duration", 0)),
        dependencies=list(dependencies),
        baseline_start=_value(payload, "baseline_start", None),
        baseline_finish=_value(payload, "baseline_finish", None),
        baseline_duration_minutes=_optional_int(_value(payload, "baseline_duration_minutes", None)),
        baseline_planned_effort_minutes=_optional_int(_value(payload, "baseline_planned_effort_minutes", None)),
        constraint_type=_value(payload, "constraint_type", "ASAP") or "ASAP",
        constraint_datetime=_value(payload, "constraint_datetime", None),
        deadline_datetime=_value(payload, "deadline_datetime", None),
    )


def _resolve_predecessor_key(
    raw_item: Any,
    predecessor_id: int,
    *,
    successor_key: EntityRef,
    cpm_id_by_key: Mapping[EntityRef, int],
) -> EntityRef:
    explicit = _explicit_predecessor_key(raw_item, predecessor_id)
    if explicit is not None:
        return explicit

    if predecessor_id < 0:
        return EntityRef.subtask(abs(int(predecessor_id)))

    task_key = EntityRef.task(predecessor_id)
    subtask_key = EntityRef.subtask(predecessor_id)

    if successor_key.entity_type == "subtask":
        if subtask_key in cpm_id_by_key:
            return subtask_key
        if task_key in cpm_id_by_key:
            return task_key
    else:
        if task_key in cpm_id_by_key:
            return task_key
        if subtask_key in cpm_id_by_key:
            return subtask_key

    return EntityRef(successor_key.entity_type, predecessor_id)


def _explicit_predecessor_key(raw_item: Any, predecessor_id: int) -> Optional[EntityRef]:
    if isinstance(raw_item, Mapping):
        raw_key = (
            raw_item.get("predecessor_key")
            or raw_item.get("entity_key")
            or raw_item.get("wbs_key")
        )
        if raw_key:
            parsed = coerce_entity_ref(raw_key)
            if parsed is not None:
                return parsed

        raw_type = (
            raw_item.get("predecessor_entity_type")
            or raw_item.get("predecessor_type")
            or raw_item.get("entity_type")
            or raw_item.get("kind")
        )
        if raw_type:
            try:
                return EntityRef(str(raw_type), predecessor_id)
            except Exception:
                return None
    return None


def _dependency_specs(raw_dependencies: Any) -> List[Tuple[Any, DependencySpec]]:
    if raw_dependencies is None:
        return []
    raw = raw_dependencies
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if not isinstance(raw, (list, tuple, set)):
        raw = [raw]

    result: List[Tuple[Any, DependencySpec]] = []
    for item in raw:
        if isinstance(item, DependencySpec):
            result.append((item, item))
        elif isinstance(item, Mapping):
            pred_id = _int(
                item.get("predecessor_id")
                if "predecessor_id" in item
                else item.get("id", item.get("task_id", 0))
            )
            raw_type = str(item.get("type") or item.get("dependency_type") or "FS").upper().strip()
            try:
                dep_type = DependencyType(raw_type)
            except ValueError:
                dep_type = DependencyType.FS
            parsed_lag = parse_lag_duration(item.get("lag_minutes", 0))
            result.append(
                (
                    item,
                    DependencySpec(
                        predecessor_id=pred_id,
                        dependency_type=dep_type,
                        lag_minutes=int(parsed_lag or 0),
                    ),
                )
            )
        else:
            try:
                pred_id = int(item)
            except (TypeError, ValueError):
                continue
            result.append(
                (
                    item,
                    DependencySpec(
                        predecessor_id=pred_id,
                        dependency_type=DependencyType.FS,
                        lag_minutes=0,
                    ),
                )
            )
    return result


def _raw_dependencies(payload: Any) -> Any:
    return _value(payload, "dependencies", [])


def _value(payload: Any, name: str, default=None):
    if payload is None:
        return default
    if isinstance(payload, Mapping):
        return payload.get(name, default)
    return getattr(payload, name, default)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return int(default or 0)


def _optional_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_text(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value)
