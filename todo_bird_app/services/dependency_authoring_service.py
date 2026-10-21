"""
Dependency authoring authority for TaskDialog.

This module is UI-independent. It builds WBS-aware dependency candidates,
normalizes typed dependency references, and validates the authoring graph
without changing CPM mathematics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from todo_bird_app.models.task import TaskStatus
from todo_bird_app.services.cpm_scheduling_service import (
    DependencyType,
    parse_lag_duration,
)
from todo_bird_app.services.wbs_service import EntityRef, WBSService


@dataclass(frozen=True)
class DependencyAuthoringSpec:
    predecessor_key: EntityRef
    dependency_type: DependencyType = DependencyType.FS
    lag_minutes: int = 0

    def to_storage_dict(self, *, typed: bool = True) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "predecessor_id": self.predecessor_key.entity_id,
            "type": self.dependency_type.value,
            "lag_minutes": int(self.lag_minutes or 0),
        }
        if typed or self.predecessor_key.entity_type != "task":
            data["predecessor_entity_type"] = self.predecessor_key.entity_type
            data["predecessor_key"] = str(self.predecessor_key)
        return data


@dataclass(frozen=True)
class DependencyCandidate:
    key: EntityRef
    title: str
    display_title: str
    status: str
    project_id: Optional[int]
    has_children: bool = False
    is_closed: bool = False


@dataclass(frozen=True)
class DependencyValidationResult:
    valid: bool
    message: str
    normalized_dependencies: Tuple[DependencyAuthoringSpec, ...]
    missing_keys: Tuple[EntityRef, ...] = ()
    self_reference: bool = False
    duplicate_keys: Tuple[EntityRef, ...] = ()
    cycle_keys: Tuple[EntityRef, ...] = ()
    cross_project_keys: Tuple[EntityRef, ...] = ()
    ineligible_keys: Tuple[EntityRef, ...] = ()
    error_code: Optional[str] = None


def raw_dependency_list(raw: Any) -> List[Any]:
    if raw is None:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return []
    if isinstance(raw, (list, tuple, set)):
        return list(raw)
    return [raw]


def raw_dependencies_contain_typed_refs(raw: Any) -> bool:
    for item in raw_dependency_list(raw):
        if isinstance(item, Mapping) and (
            item.get("predecessor_key")
            or item.get("predecessor_entity_type")
            or item.get("predecessor_type")
            or item.get("entity_type")
            or item.get("kind") in {"task", "subtask"}
        ):
            return True
    return False


def parse_authoring_dependency_specs(
    raw: Any,
    *,
    fallback_entity_type: str = "task",
    candidates_by_id: Optional[Mapping[int, Sequence[EntityRef]]] = None,
) -> Tuple[DependencyAuthoringSpec, ...]:
    specs: List[DependencyAuthoringSpec] = []

    for item in raw_dependency_list(raw):
        parsed = _parse_one_dependency(
            item,
            fallback_entity_type=fallback_entity_type,
            candidates_by_id=candidates_by_id,
        )
        if parsed is not None:
            specs.append(parsed)

    result_by_key: Dict[EntityRef, DependencyAuthoringSpec] = {}
    order: List[EntityRef] = []
    for spec in specs:
        if spec.predecessor_key not in result_by_key:
            order.append(spec.predecessor_key)
        result_by_key[spec.predecessor_key] = spec
    return tuple(result_by_key[key] for key in order)


class DependencyAuthoringService:
    @classmethod
    def build_candidates(
        cls,
        db_manager: Any,
        *,
        project_id: Optional[int],
        successor_key: Optional[EntityRef],
    ) -> Tuple[DependencyCandidate, ...]:
        if db_manager is None:
            return ()

        snapshot = WBSService.build_project_hierarchy(
            db_manager,
            project_id=project_id,
        )

        title_counts: Dict[str, int] = {}
        for key, node in snapshot.nodes_by_key.items():
            if key.entity_type == "task":
                clean = (node.title or "").strip()
                title_counts[clean] = title_counts.get(clean, 0) + 1

        candidates: List[DependencyCandidate] = []
        ordered_keys = _ordered_snapshot_keys(snapshot)
        for key in ordered_keys:
            if successor_key is not None and key == successor_key:
                continue
            node = snapshot.nodes_by_key[key]
            if project_id is None and node.project_id is not None:
                continue
            has_children = bool(snapshot.children_by_parent.get(key))
            is_closed = _node_is_closed(node.status, node.is_completed)
            if has_children or is_closed:
                continue

            path = _display_path(snapshot, key)
            if key.entity_type == "task" and " > " not in path:
                clean = (node.title or f"Task {key.entity_id}").strip()
                display = (
                    f"{clean} — #{key.entity_id}"
                    if title_counts.get(clean, 0) > 1
                    else clean
                )
            else:
                display = f"{path} — #{key.entity_id}"

            candidates.append(
                DependencyCandidate(
                    key=key,
                    title=node.title or str(key),
                    display_title=display,
                    status=node.status or "Planned",
                    project_id=node.project_id,
                    has_children=has_children,
                    is_closed=is_closed,
                )
            )

        return tuple(candidates)

    @classmethod
    def validate_dependencies(
        cls,
        db_manager: Any,
        *,
        successor_key: EntityRef,
        raw_dependencies: Any,
        project_id: Optional[int],
    ) -> DependencyValidationResult:
        candidates = cls.build_candidates(
            db_manager,
            project_id=project_id,
            successor_key=successor_key,
        )
        candidates_by_id = _candidates_by_id(candidates)
        normalized = parse_authoring_dependency_specs(
            raw_dependencies,
            fallback_entity_type=successor_key.entity_type,
            candidates_by_id=candidates_by_id,
        )

        if successor_key in (spec.predecessor_key for spec in normalized):
            return DependencyValidationResult(
                valid=False,
                message=f"{successor_key} cannot depend on itself.",
                normalized_dependencies=normalized,
                self_reference=True,
                cycle_keys=(successor_key,),
                error_code="SELF_REFERENCE",
            )

        duplicates = _duplicate_keys(raw_dependencies, successor_key, candidates_by_id)
        if duplicates:
            return DependencyValidationResult(
                valid=False,
                message=(
                    "This dependency is already listed. Edit the existing row "
                    "or remove it before adding it again."
                ),
                normalized_dependencies=normalized,
                duplicate_keys=duplicates,
                error_code="DUPLICATE_DEPENDENCY",
            )

        snapshot = WBSService.build_project_hierarchy(
            db_manager,
            project_id=project_id,
        )
        nodes = snapshot.nodes_by_key
        missing = tuple(
            spec.predecessor_key
            for spec in normalized
            if spec.predecessor_key not in nodes
        )
        if missing:
            all_snapshot = WBSService.build_project_hierarchy(
                db_manager,
                project_id=None,
            )
            cross_project_missing = tuple(
                key
                for key in missing
                if key in all_snapshot.nodes_by_key
                and all_snapshot.nodes_by_key[key].project_id != project_id
            )
            if cross_project_missing:
                return DependencyValidationResult(
                    valid=False,
                    message="Dependencies can currently be created only inside the same project.",
                    normalized_dependencies=normalized,
                    cross_project_keys=cross_project_missing,
                    error_code="CROSS_PROJECT_DEPENDENCY",
                )
            return DependencyValidationResult(
                valid=False,
                message="Dependency target no longer exists. Refresh the task and choose a valid predecessor.",
                normalized_dependencies=normalized,
                missing_keys=missing,
                error_code="MISSING_DEPENDENCY",
            )

        successor_node = nodes.get(successor_key)
        successor_project_id = (
            successor_node.project_id
            if successor_node is not None
            else project_id
        )
        cross_project = tuple(
            spec.predecessor_key
            for spec in normalized
            if nodes.get(spec.predecessor_key) is not None
            and nodes[spec.predecessor_key].project_id != successor_project_id
        )
        if cross_project:
            return DependencyValidationResult(
                valid=False,
                message="Dependencies can currently be created only inside the same project.",
                normalized_dependencies=normalized,
                cross_project_keys=cross_project,
                error_code="CROSS_PROJECT_DEPENDENCY",
            )

        ineligible = tuple(
            spec.predecessor_key
            for spec in normalized
            if bool(snapshot.children_by_parent.get(spec.predecessor_key))
            or _node_is_closed(
                nodes[spec.predecessor_key].status,
                nodes[spec.predecessor_key].is_completed,
            )
        )
        if ineligible:
            return DependencyValidationResult(
                valid=False,
                message="Choose an open leaf task or subtask as the dependency predecessor.",
                normalized_dependencies=normalized,
                ineligible_keys=ineligible,
                error_code="INELIGIBLE_DEPENDENCY",
            )

        predecessor_map = cls._predecessor_map(
            db_manager,
            snapshot,
            successor_key=successor_key,
            replacement_specs=normalized,
        )
        cycle = _cycle_from_successor(successor_key, predecessor_map)
        if cycle:
            return DependencyValidationResult(
                valid=False,
                message=(
                    "Circular dependency detected.\n\n"
                    + " -> ".join(str(key) for key in cycle)
                    + "\n\nRemove one dependency before saving."
                ),
                normalized_dependencies=normalized,
                cycle_keys=tuple(cycle),
                error_code="DEPENDENCY_CYCLE",
            )

        return DependencyValidationResult(
            valid=True,
            message="Dependency graph is valid.",
            normalized_dependencies=normalized,
        )

    @classmethod
    def _predecessor_map(
        cls,
        db_manager: Any,
        snapshot,
        *,
        successor_key: EntityRef,
        replacement_specs: Sequence[DependencyAuthoringSpec],
    ) -> Dict[EntityRef, Tuple[EntityRef, ...]]:
        raw_by_key = _raw_dependencies_by_key(db_manager, snapshot.project_id)
        candidate_refs = _candidate_refs_by_id(snapshot)
        predecessor_map: Dict[EntityRef, Tuple[EntityRef, ...]] = {}

        for key in snapshot.nodes_by_key:
            if key == successor_key:
                predecessor_map[key] = tuple(
                    spec.predecessor_key
                    for spec in replacement_specs
                )
                continue
            specs = parse_authoring_dependency_specs(
                raw_by_key.get(key, []),
                fallback_entity_type=key.entity_type,
                candidates_by_id=candidate_refs,
            )
            predecessor_map[key] = tuple(spec.predecessor_key for spec in specs)

        if successor_key not in predecessor_map:
            predecessor_map[successor_key] = tuple(
                spec.predecessor_key
                for spec in replacement_specs
            )
        return predecessor_map


def storage_dependency(
    predecessor_key: EntityRef,
    dependency_type: Any = "FS",
    lag_minutes: int = 0,
    *,
    typed: bool = True,
) -> Dict[str, Any]:
    try:
        dep_type = DependencyType(str(dependency_type or "FS").upper())
    except ValueError:
        dep_type = DependencyType.FS
    return DependencyAuthoringSpec(
        predecessor_key=predecessor_key,
        dependency_type=dep_type,
        lag_minutes=int(lag_minutes or 0),
    ).to_storage_dict(typed=typed)


def _parse_one_dependency(
    item: Any,
    *,
    fallback_entity_type: str,
    candidates_by_id: Optional[Mapping[int, Sequence[EntityRef]]],
) -> Optional[DependencyAuthoringSpec]:
    if isinstance(item, DependencyAuthoringSpec):
        return item

    if isinstance(item, Mapping):
        pred_id = _int_or_none(
            item.get("predecessor_id")
            if "predecessor_id" in item
            else item.get("id", item.get("task_id"))
        )
        if pred_id is None:
            return None

        key = _explicit_predecessor_key(item, pred_id)
        if key is None:
            key = _fallback_key(pred_id, fallback_entity_type, candidates_by_id)

        raw_type = str(
            item.get("type")
            or item.get("dependency_type")
            or "FS"
        ).upper().strip()
        try:
            dep_type = DependencyType(raw_type)
        except ValueError:
            dep_type = DependencyType.FS

        lag = parse_lag_duration(item.get("lag_minutes", 0))
        return DependencyAuthoringSpec(
            predecessor_key=key,
            dependency_type=dep_type,
            lag_minutes=int(lag or 0),
        )

    pred_id = _int_or_none(item)
    if pred_id is None:
        return None
    return DependencyAuthoringSpec(
        predecessor_key=_fallback_key(pred_id, fallback_entity_type, candidates_by_id),
        dependency_type=DependencyType.FS,
        lag_minutes=0,
    )


def _explicit_predecessor_key(raw_item: Mapping[str, Any], predecessor_id: int) -> Optional[EntityRef]:
    raw_key = (
        raw_item.get("predecessor_key")
        or raw_item.get("entity_key")
        or raw_item.get("wbs_key")
    )
    if raw_key:
        try:
            return EntityRef.from_string(str(raw_key))
        except Exception:
            return None

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


def _fallback_key(
    predecessor_id: int,
    fallback_entity_type: str,
    candidates_by_id: Optional[Mapping[int, Sequence[EntityRef]]],
) -> EntityRef:
    refs = list((candidates_by_id or {}).get(int(predecessor_id), ()))
    desired = str(fallback_entity_type or "task").lower()
    for ref in refs:
        if ref.entity_type == desired:
            return ref
    if len(refs) == 1:
        return refs[0]
    return EntityRef(desired, predecessor_id)


def _candidates_by_id(
    candidates: Iterable[DependencyCandidate],
) -> Dict[int, Tuple[EntityRef, ...]]:
    refs: Dict[int, List[EntityRef]] = {}
    for candidate in candidates:
        refs.setdefault(candidate.key.entity_id, []).append(candidate.key)
    return {key: tuple(value) for key, value in refs.items()}


def _candidate_refs_by_id(snapshot) -> Dict[int, Tuple[EntityRef, ...]]:
    refs: Dict[int, List[EntityRef]] = {}
    for key in snapshot.nodes_by_key:
        refs.setdefault(key.entity_id, []).append(key)
    return {key: tuple(value) for key, value in refs.items()}


def _duplicate_keys(
    raw: Any,
    successor_key: EntityRef,
    candidates_by_id: Optional[Mapping[int, Sequence[EntityRef]]],
) -> Tuple[EntityRef, ...]:
    counts: Dict[EntityRef, int] = {}
    for spec in (
        _parse_one_dependency(
            item,
            fallback_entity_type=successor_key.entity_type,
            candidates_by_id=candidates_by_id,
        )
        for item in raw_dependency_list(raw)
    ):
        if spec is None:
            continue
        counts[spec.predecessor_key] = counts.get(spec.predecessor_key, 0) + 1
    return tuple(key for key, count in counts.items() if count > 1)


def _ordered_snapshot_keys(snapshot) -> List[EntityRef]:
    ordered: List[EntityRef] = []
    stack = list(reversed(snapshot.root_keys))
    while stack:
        key = stack.pop()
        ordered.append(key)
        for child in reversed(snapshot.children_by_parent.get(key, [])):
            stack.append(child)
    return ordered


def _display_path(snapshot, key: EntityRef) -> str:
    parts: List[str] = []
    cursor = key
    seen = set()
    while cursor is not None and cursor not in seen:
        seen.add(cursor)
        node = snapshot.nodes_by_key.get(cursor)
        if node is None:
            break
        parts.append(node.title or str(cursor))
        cursor = node.parent_key
    return " > ".join(reversed(parts)) if parts else str(key)


def _node_is_closed(status: Any, is_completed: bool = False) -> bool:
    if is_completed:
        return True
    raw = getattr(status, "value", status)
    return str(raw or "").strip().lower() in {
        "completed",
        "cancelled",
        "archived",
    }


def _raw_dependencies_by_key(
    db_manager: Any,
    project_id: Optional[int],
) -> Dict[EntityRef, Any]:
    raw_by_key: Dict[EntityRef, Any] = {}
    with db_manager.get_connection() as conn:
        cursor = conn.cursor()
        if project_id is None:
            cursor.execute(
                """
                SELECT id, dependencies
                FROM tasks
                WHERE project_id IS NULL;
                """
            )
        else:
            cursor.execute(
                """
                SELECT id, dependencies
                FROM tasks
                WHERE project_id = ?;
                """,
                (project_id,),
            )
        for row in cursor.fetchall():
            raw_by_key[EntityRef.task(row["id"])] = row["dependencies"] or "[]"

        if project_id is None:
            cursor.execute(
                """
                SELECT s.id, s.dependencies
                FROM subtasks s
                JOIN tasks t ON t.id = s.task_id
                WHERE t.project_id IS NULL;
                """
            )
        else:
            cursor.execute(
                """
                SELECT s.id, s.dependencies
                FROM subtasks s
                JOIN tasks t ON t.id = s.task_id
                WHERE t.project_id = ?;
                """,
                (project_id,),
            )
        for row in cursor.fetchall():
            raw_by_key[EntityRef.subtask(row["id"])] = row["dependencies"] or "[]"
    return raw_by_key


def _cycle_from_successor(
    successor_key: EntityRef,
    predecessor_map: Mapping[EntityRef, Sequence[EntityRef]],
) -> Tuple[EntityRef, ...]:
    path: List[EntityRef] = []
    visiting: set[EntityRef] = set()

    def visit(key: EntityRef) -> bool:
        if key in visiting:
            path.append(key)
            return key == successor_key
        visiting.add(key)
        path.append(key)
        for predecessor in predecessor_map.get(key, ()):
            if predecessor == successor_key:
                path.append(predecessor)
                return True
            if visit(predecessor):
                return True
        path.pop()
        visiting.remove(key)
        return False

    for predecessor in predecessor_map.get(successor_key, ()):
        path.clear()
        visiting.clear()
        if predecessor == successor_key:
            return (successor_key, predecessor)
        if visit(predecessor):
            return tuple(path)
    return ()


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
