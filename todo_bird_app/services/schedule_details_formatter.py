"""
TODO BIRD - SCHEDULE DETAILS FORMATTER SERVICE

Canonical collector and presentation authority for Schedule Details popup/copy
content. This module consumes existing task, WBS, Gantt, CPM, baseline,
revision, calendar, and actual-execution fields. It does not run CPM math.
"""

from __future__ import annotations

import html
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from todo_bird_app.services.cpm_scheduling_service import (
    format_cpm_datetime,
    format_float_duration,
)
from todo_bird_app.services.execution_performance_service import (
    ExecutionPerformanceService,
    ExecutionState,
)
from todo_bird_app.services.schedule_variance_service import format_variance_duration


_WEEKDAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_NOT_AVAILABLE = "Not available"
_NOT_ANALYZED = "Not analyzed"


@dataclass
class ScheduleDetailsModel:
    """Canonical structured representation of an inspectable schedule entity."""

    title: str
    entity_type: str = "task"
    entity_id: Optional[int] = None
    depth: int = 0
    wbs_code: str = ""
    wbs_path: str = ""
    parent_path: str = ""
    project_id: Optional[int] = None
    project_name: str = ""
    status: str = "Planned"
    priority: str = "Medium"
    progress: int = 0
    is_summary: bool = False
    is_milestone: bool = False
    is_read_only: bool = False

    planned_start: Optional[str] = None
    planned_finish: Optional[str] = None
    planned_duration_minutes: Optional[int] = None
    planned_effort_minutes: Optional[int] = None
    daily_dedication_minutes: Optional[int] = None
    gantt_bar_start: Optional[str] = None
    gantt_bar_finish: Optional[str] = None
    gantt_bar_left_x: Optional[float] = None
    gantt_bar_right_x: Optional[float] = None

    has_cpm: bool = False
    has_cycle: bool = False
    cpm_analysis_status: str = "not_analyzed"
    cpm_es: Optional[str] = None
    cpm_ef: Optional[str] = None
    cpm_ls: Optional[str] = None
    cpm_lf: Optional[str] = None
    cpm_tf: Optional[int] = None
    cpm_ff: Optional[int] = None
    cpm_is_critical: Optional[bool] = None

    predecessors: List[str] = field(default_factory=list)
    successors: List[str] = field(default_factory=list)

    constraint_type: Optional[str] = None
    constraint_datetime: Optional[str] = None
    deadline_datetime: Optional[str] = None
    constraint_diagnostics: List[str] = field(default_factory=list)

    calendar_name: Optional[str] = None
    working_weekdays: Optional[Tuple[int, ...]] = None

    has_baseline: bool = False
    baseline_start: Optional[str] = None
    baseline_finish: Optional[str] = None
    baseline_duration_minutes: Optional[int] = None
    baseline_start_variance_minutes: Optional[int] = None
    baseline_variance_minutes: Optional[int] = None
    has_revision: bool = False
    revision_name: Optional[str] = None
    revision_start: Optional[str] = None
    revision_finish: Optional[str] = None
    revision_variance_minutes: Optional[int] = None

    actual_state: str = "not_started"
    actual_start: Optional[str] = None
    actual_finish: Optional[str] = None
    actual_duration_minutes: Optional[int] = None
    actual_elapsed_span_minutes: Optional[int] = None
    actual_variance_display: Optional[str] = None

    delay_minutes: int = 0
    delay_percentage: float = 0.0
    delay_reason: Optional[str] = None
    delay_notes: Optional[str] = None
    diagnostics: List[str] = field(default_factory=list)


class ScheduleDetailsCollector:
    """Builds a complete ScheduleDetailsModel from one canonical entity."""

    @classmethod
    def collect(
        cls,
        entity: Any,
        *,
        project_name: Optional[str] = None,
        db_manager: Any = None,
    ) -> ScheduleDetailsModel:
        source_payload = cls._source_payload(entity)

        def prop(key: str, default: Any = None) -> Any:
            value = cls._value(entity, key, None)
            if cls._present(value):
                return value
            value = cls._value(source_payload, key, None)
            if cls._present(value):
                return value
            return default

        key = cls._entity_ref(entity, source_payload)
        project_id = cls._project_id(entity, source_payload, key, db_manager)
        resolved_project_name = cls._project_name(
            explicit=project_name,
            entity=entity,
            payload=source_payload,
            project_id=project_id,
            db_manager=db_manager,
        )
        snapshot = cls._snapshot(project_id, db_manager)
        node = snapshot.nodes_by_key.get(key) if snapshot is not None and key else None
        payload_by_key = cls._payloads(snapshot, db_manager)

        title = str(
            prop("title")
            or prop("name")
            or (node.title if node is not None else "")
            or ""
        ).replace("\u21b3", "").strip()

        depth = cls._int(prop("gantt_depth", prop("depth", getattr(node, "depth", 0))), 0)
        is_summary = bool(
            prop("gantt_is_summary", prop("is_summary", False))
            or (node.has_children if node is not None else False)
        )
        is_milestone = bool(prop("gantt_is_milestone", prop("is_milestone", False)))
        is_read_only = bool(prop("gantt_read_only", prop("is_read_only", is_summary)))
        wbs_code = str(prop("gantt_wbs_code", prop("wbs_code", getattr(node, "wbs_code", ""))) or "")

        raw_item_type = str(
            prop("gantt_item_type", prop("entity_type", getattr(key, "entity_type", "task")))
            or "task"
        ).lower()
        if is_summary:
            entity_type = "summary"
        elif "subtask" in raw_item_type or (key and key.entity_type == "subtask") or depth > 0:
            entity_type = "subtask"
        else:
            entity_type = "task"

        wbs_path = cls._wbs_path(snapshot, key) if snapshot is not None and key else ""
        parent_path = cls._parent_path(snapshot, key) if snapshot is not None and key else ""

        status_raw = prop("status", getattr(node, "status", "Planned"))
        priority_raw = prop("priority", "Medium")
        status_val = str(getattr(status_raw, "value", status_raw) or "Planned")
        priority_val = str(getattr(priority_raw, "value", priority_raw) or "Medium")
        progress = max(0, min(100, cls._int(prop("progress", prop("progress_percent", 0)), 0)))

        gantt_start = prop("gantt_planned_start")
        gantt_finish = prop("gantt_planned_finish")
        planned_start = gantt_start or prop("planned_start") or prop("planned_date")
        planned_finish = gantt_finish or prop("planned_finish") or prop("target_finish") or prop("due_date")
        planned_start = cls._combine_date_time(planned_start, prop("planned_start_time"))
        planned_finish = cls._combine_date_time(planned_finish, prop("planned_end_time"))

        duration = prop("estimated_duration", prop("planned_duration_minutes", prop("planned_elapsed_minutes")))
        effort = prop("planned_effort_minutes")
        dedication = prop("daily_dedication_minutes")

        cpm_tf = prop("cpm_total_float_minutes", prop("cpm_total_float", prop("total_float")))
        cpm_ff = prop("cpm_free_float_minutes", prop("cpm_free_float", prop("free_float")))
        cpm_es = prop("cpm_earliest_start", prop("earliest_start"))
        cpm_ef = prop("cpm_earliest_finish", prop("earliest_finish"))
        cpm_ls = prop("cpm_latest_start", prop("latest_start"))
        cpm_lf = prop("cpm_latest_finish", prop("latest_finish"))
        cpm_status = str(prop("cpm_analysis_status", prop("gantt_cpm_analysis_status", "not_analyzed")) or "not_analyzed")
        cpm_schedulable = bool(prop("cpm_schedulable", False))
        cpm_crit_raw = prop("cpm_is_critical", prop("is_critical", prop("gantt_critical_path", None)))
        cpm_crit = None if cpm_crit_raw is None else bool(cpm_crit_raw)
        cpm_diagnostics = cls._diagnostics(prop("cpm_diagnostics", prop("diagnostics", [])))
        has_cycle = bool(prop("gantt_dependency_cycle", False)) or "DEPENDENCY_CYCLE" in cpm_diagnostics
        has_cpm = (
            cpm_status.lower() == "analyzed"
            or cpm_schedulable
            or any(value is not None for value in (cpm_tf, cpm_ff, cpm_es, cpm_ef, cpm_ls, cpm_lf))
        )
        if has_cycle and cpm_status.lower() == "not_analyzed":
            cpm_status = "blocked"

        predecessors, successors = cls._relationships(
            key=key,
            prop=prop,
            snapshot=snapshot,
            payload_by_key=payload_by_key,
        )

        constraint_type = prop("constraint_type")
        constraint_type = str(constraint_type) if cls._present(constraint_type) else None
        if constraint_type and constraint_type.upper() == "ASAP":
            constraint_type = None

        calendar_name, working_weekdays = cls._calendar(project_id, db_manager)
        revision = cls._latest_revision(project_id, key, db_manager)

        actual_start = cls._combine_date_time(prop("actual_start_date"), prop("actual_start_time"))
        actual_finish = cls._combine_date_time(prop("actual_end_date"), prop("actual_end_time"))
        actual_duration = prop("actual_duration", prop("actual_duration_minutes"))
        actual_elapsed = prop("actual_elapsed_minutes")
        if actual_elapsed is None and actual_start and actual_finish:
            actual_elapsed = cls._elapsed_minutes(actual_start, actual_finish)
        actual_state, actual_variance, actual_diags = cls._actual_state(
            entity,
            prop,
            actual_start,
            actual_finish,
            progress,
        )

        return ScheduleDetailsModel(
            title=title,
            entity_type=entity_type,
            entity_id=key.entity_id if key else cls._int(prop("id"), None),
            depth=depth,
            wbs_code=wbs_code,
            wbs_path=wbs_path,
            parent_path=parent_path,
            project_id=project_id,
            project_name=resolved_project_name,
            status=status_val,
            priority=priority_val,
            progress=progress,
            is_summary=is_summary,
            is_milestone=is_milestone,
            is_read_only=is_read_only,
            planned_start=cls._to_text(planned_start),
            planned_finish=cls._to_text(planned_finish),
            planned_duration_minutes=cls._int(duration, None),
            planned_effort_minutes=cls._int(effort, None),
            daily_dedication_minutes=cls._int(dedication, None),
            gantt_bar_start=cls._to_text(gantt_start or planned_start),
            gantt_bar_finish=cls._to_text(gantt_finish or planned_finish),
            gantt_bar_left_x=cls._float(prop("gantt_bar_left_x"), None),
            gantt_bar_right_x=cls._float(prop("gantt_bar_right_x"), None),
            has_cpm=has_cpm,
            has_cycle=has_cycle,
            cpm_analysis_status=cpm_status,
            cpm_es=cls._to_text(cpm_es),
            cpm_ef=cls._to_text(cpm_ef),
            cpm_ls=cls._to_text(cpm_ls),
            cpm_lf=cls._to_text(cpm_lf),
            cpm_tf=cls._int(cpm_tf, None),
            cpm_ff=cls._int(cpm_ff, None),
            cpm_is_critical=cpm_crit,
            predecessors=predecessors,
            successors=successors,
            constraint_type=constraint_type,
            constraint_datetime=cls._to_text(prop("constraint_datetime")),
            deadline_datetime=cls._to_text(prop("deadline_datetime")),
            constraint_diagnostics=cpm_diagnostics,
            calendar_name=calendar_name,
            working_weekdays=working_weekdays,
            has_baseline=bool(prop("has_baseline", prop("gantt_has_baseline", False)) or prop("baseline_start") or prop("baseline_finish")),
            baseline_start=cls._to_text(prop("baseline_start")),
            baseline_finish=cls._to_text(prop("baseline_finish")),
            baseline_duration_minutes=cls._int(prop("baseline_duration_minutes"), None),
            baseline_start_variance_minutes=cls._int(prop("start_variance_minutes", prop("gantt_start_variance")), None),
            baseline_variance_minutes=cls._int(prop("finish_variance_minutes", prop("gantt_finish_variance")), None),
            has_revision=bool(revision),
            revision_name=revision.get("name") if revision else None,
            revision_start=revision.get("start") if revision else None,
            revision_finish=revision.get("finish") if revision else None,
            revision_variance_minutes=revision.get("variance_minutes") if revision else None,
            actual_state=actual_state,
            actual_start=cls._to_text(actual_start),
            actual_finish=cls._to_text(actual_finish),
            actual_duration_minutes=cls._int(actual_duration, None),
            actual_elapsed_span_minutes=cls._int(actual_elapsed, None),
            actual_variance_display=actual_variance,
            delay_minutes=cls._int(prop("delay_minutes"), 0),
            delay_percentage=cls._float(prop("delay_percentage"), 0.0),
            delay_reason=prop("delay_reason"),
            delay_notes=prop("delay_notes"),
            diagnostics=actual_diags,
        )

    @staticmethod
    def _present(value: Any) -> bool:
        return value is not None and value != ""

    @staticmethod
    def _source_payload(entity: Any) -> Any:
        if isinstance(entity, Mapping):
            return entity.get("source_payload") or {}
        return getattr(entity, "source_payload", {}) or {}

    @staticmethod
    def _value(obj: Any, key: str, default: Any = None) -> Any:
        if obj is None:
            return default
        if isinstance(obj, Mapping):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @staticmethod
    def _int(value: Any, default: Optional[int] = 0) -> Optional[int]:
        if value is None or value == "":
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _float(value: Any, default: Optional[float] = 0.0) -> Optional[float]:
        if value is None or value == "":
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_text(value: Any) -> Optional[str]:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value.isoformat(sep=" ", timespec="minutes")
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    @classmethod
    def _combine_date_time(cls, raw_date: Any, raw_time: Any = None) -> Any:
        if raw_date is None or raw_date == "":
            return None
        if isinstance(raw_date, datetime):
            return raw_date
        if isinstance(raw_date, date):
            if raw_time:
                return f"{raw_date.isoformat()} {str(raw_time)[:5]}"
            return raw_date.isoformat()
        text = str(raw_date)
        if raw_time and " " not in text and "T" not in text:
            return f"{text} {str(raw_time)[:5]}"
        return text

    @classmethod
    def _elapsed_minutes(cls, start: Any, finish: Any) -> Optional[int]:
        try:
            s = datetime.fromisoformat(str(start).replace("T", " "))
            f = datetime.fromisoformat(str(finish).replace("T", " "))
            return max(0, int((f - s).total_seconds() // 60))
        except Exception:
            return None

    @classmethod
    def _entity_ref(cls, entity: Any, payload: Any = None) -> Any:
        try:
            from todo_bird_app.services.wbs_service import EntityRef
        except Exception:
            return None

        key = cls._value(entity, "key", None)
        if isinstance(key, EntityRef):
            return key

        raw_key = (
            cls._value(entity, "gantt_wbs_key", None)
            or cls._value(entity, "wbs_key", None)
            or cls._value(entity, "entity_key", None)
        )
        if raw_key:
            try:
                return EntityRef.from_string(str(raw_key))
            except Exception:
                pass

        entity_type = (
            cls._value(entity, "gantt_entity_type", None)
            or cls._value(entity, "entity_type", None)
            or cls._value(payload, "entity_type", None)
        )
        entity_id = (
            cls._value(entity, "gantt_entity_id", None)
            or cls._value(entity, "entity_id", None)
            or cls._value(entity, "id", None)
            or cls._value(payload, "id", None)
        )
        if entity_id is None:
            return None
        if not entity_type:
            raw_item_type = str(cls._value(entity, "gantt_item_type", "") or "").lower()
            depth = cls._int(cls._value(entity, "gantt_depth", cls._value(entity, "depth", 0)), 0)
            entity_type = "subtask" if "subtask" in raw_item_type or depth > 0 else "task"
        try:
            return EntityRef(str(entity_type), int(entity_id))
        except Exception:
            return None

    @classmethod
    def _project_id(cls, entity: Any, payload: Any, key: Any, db_manager: Any) -> Optional[int]:
        raw = cls._value(entity, "project_id", cls._value(payload, "project_id", None))
        if raw is not None and raw != "":
            try:
                return int(raw)
            except (TypeError, ValueError):
                pass
        if key is not None and key.entity_type == "subtask" and db_manager is not None:
            try:
                sub = db_manager.get_subtask_by_id(int(key.entity_id))
                task_id = sub.get("task_id") if sub else None
                task = db_manager.get_task_by_id(int(task_id)) if task_id else None
                raw = task.get("project_id") if isinstance(task, Mapping) else getattr(task, "project_id", None)
                return int(raw) if raw not in (None, "") else None
            except Exception:
                return None
        return None

    @classmethod
    def _project_name(
        cls,
        *,
        explicit: Optional[str],
        entity: Any,
        payload: Any,
        project_id: Optional[int],
        db_manager: Any,
    ) -> str:
        for value in (
            explicit,
            cls._value(entity, "project_name", None),
            cls._value(payload, "project_name", None),
        ):
            if value not in (None, ""):
                return str(value)
        if project_id is None:
            return "Inbox"
        if db_manager is not None:
            try:
                project = db_manager.get_project(int(project_id))
                if isinstance(project, Mapping):
                    name = project.get("name")
                else:
                    name = getattr(project, "name", None)
                if name:
                    return str(name)
            except Exception:
                pass
        return f"Project #{project_id}"

    @classmethod
    def _snapshot(cls, project_id: Optional[int], db_manager: Any) -> Any:
        if project_id is None or db_manager is None:
            return None
        try:
            from todo_bird_app.services.wbs_service import WBSService

            return WBSService.build_project_hierarchy(db_manager, project_id=project_id)
        except Exception:
            return None

    @classmethod
    def _payloads(cls, snapshot: Any, db_manager: Any) -> Dict[Any, Any]:
        if snapshot is None or db_manager is None:
            return {}
        try:
            from todo_bird_app.services.wbs_rollup_service import WBSRollupService

            return WBSRollupService._bulk_fetch_payloads(
                db_manager,
                list(snapshot.nodes_by_key.keys()),
                project_id=snapshot.project_id,
            )
        except Exception:
            return {}

    @classmethod
    def _wbs_path(cls, snapshot: Any, key: Any) -> str:
        parts = []
        cursor = key
        seen = set()
        while cursor is not None and cursor not in seen:
            seen.add(cursor)
            node = snapshot.nodes_by_key.get(cursor)
            if node is None:
                break
            parts.append(node.title or str(cursor))
            cursor = node.parent_key
        return " > ".join(reversed(parts))

    @classmethod
    def _parent_path(cls, snapshot: Any, key: Any) -> str:
        node = snapshot.nodes_by_key.get(key)
        if node is None or node.parent_key is None:
            return "Root"
        return cls._wbs_path(snapshot, node.parent_key)

    @classmethod
    def _candidate_refs_by_id(cls, snapshot: Any) -> Dict[int, Tuple[Any, ...]]:
        refs: Dict[int, List[Any]] = {}
        if snapshot is None:
            return {}
        for key in snapshot.nodes_by_key:
            refs.setdefault(int(key.entity_id), []).append(key)
        return {entity_id: tuple(values) for entity_id, values in refs.items()}

    @classmethod
    def _dependency_specs(cls, raw: Any, snapshot: Any) -> Tuple[Any, ...]:
        if not raw:
            return ()
        try:
            from todo_bird_app.services.dependency_authoring_service import (
                parse_authoring_dependency_specs,
            )

            return parse_authoring_dependency_specs(
                raw,
                fallback_entity_type="task",
                candidates_by_id=cls._candidate_refs_by_id(snapshot),
            )
        except Exception:
            return ()

    @classmethod
    def _relationships(
        cls,
        *,
        key: Any,
        prop,
        snapshot: Any,
        payload_by_key: Mapping[Any, Any],
    ) -> Tuple[List[str], List[str]]:
        if key is None:
            fallback_summary = str(prop("gantt_dependency_summary", "") or "").strip()
            if fallback_summary and fallback_summary.lower() != "no dependencies":
                return [fallback_summary], []
            return [], []

        predecessor_specs = cls._dependency_specs(prop("dependencies"), snapshot)
        predecessors = [
            cls._relationship_line(snapshot, spec.predecessor_key, spec.dependency_type.value, spec.lag_minutes)
            for spec in predecessor_specs
        ]

        successors: List[str] = []
        if snapshot is not None:
            for candidate_key in cls._ordered_keys(snapshot):
                if candidate_key == key:
                    continue
                candidate_payload = payload_by_key.get(candidate_key)
                specs = cls._dependency_specs(
                    cls._value(candidate_payload, "dependencies", None),
                    snapshot,
                )
                for spec in specs:
                    if spec.predecessor_key == key:
                        successors.append(
                            cls._relationship_line(
                                snapshot,
                                candidate_key,
                                spec.dependency_type.value,
                                spec.lag_minutes,
                            )
                        )
        return predecessors, successors

    @classmethod
    def _relationship_line(cls, snapshot: Any, key: Any, dep_type: str, lag_minutes: int) -> str:
        name = cls._wbs_path(snapshot, key) if snapshot is not None and key in snapshot.nodes_by_key else str(key)
        lag_label = f"Lead {abs(int(lag_minutes))} min" if int(lag_minutes or 0) < 0 else f"Lag {int(lag_minutes or 0)} min"
        return f"{name} | {dep_type or 'FS'} | {lag_label}"

    @staticmethod
    def _ordered_keys(snapshot: Any) -> List[Any]:
        ordered: List[Any] = []
        stack = list(reversed(snapshot.root_keys))
        while stack:
            key = stack.pop()
            ordered.append(key)
            for child in reversed(snapshot.children_by_parent.get(key, [])):
                stack.append(child)
        return ordered

    @staticmethod
    def _diagnostics(raw: Any) -> List[str]:
        if raw is None:
            return []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except Exception:
                raw = [raw]
        result: List[str] = []
        items = raw if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) else [raw]
        for item in items:
            value = getattr(item, "value", str(item))
            if value:
                result.append(str(value))
        return result

    @classmethod
    def _calendar(cls, project_id: Optional[int], db_manager: Any) -> Tuple[Optional[str], Optional[Tuple[int, ...]]]:
        if project_id is None or db_manager is None:
            return None, None
        try:
            from todo_bird_app.services.schedule_calendar_service import (
                effective_project_calendar_from_db,
            )

            spec = effective_project_calendar_from_db(db_manager, project_id)
            weekdays = getattr(spec, "working_weekdays", None) if spec is not None else None
            weekdays_tuple = tuple(int(day) for day in weekdays) if weekdays is not None else None
            return f"Project Calendar #{project_id}", weekdays_tuple
        except Exception:
            return None, None

    @classmethod
    def _latest_revision(cls, project_id: Optional[int], key: Any, db_manager: Any) -> Optional[Dict[str, Any]]:
        if project_id is None or key is None or db_manager is None:
            return None
        if not hasattr(db_manager, "get_latest_approved_revision"):
            return None
        try:
            version = db_manager.get_latest_approved_revision(int(project_id))
            if not version:
                return None
            items = db_manager.get_schedule_version_items(int(version["id"]))
            item = next(
                (
                    row
                    for row in items
                    if str(row.get("entity_type")) == key.entity_type
                    and int(row.get("entity_id")) == int(key.entity_id)
                ),
                None,
            )
            if not item:
                return {
                    "name": version.get("name"),
                    "start": None,
                    "finish": None,
                    "variance_minutes": None,
                }
            return {
                "name": version.get("name"),
                "start": item.get("start"),
                "finish": item.get("finish"),
                "variance_minutes": None,
            }
        except Exception:
            return None

    @classmethod
    def _actual_state(
        cls,
        entity: Any,
        prop,
        actual_start: Any,
        actual_finish: Any,
        progress: int,
    ) -> Tuple[str, Optional[str], List[str]]:
        status_text = str(prop("status", "") or "").lower()
        if actual_finish or progress >= 100 or status_text == "completed":
            fallback_state = "completed"
        elif actual_start:
            fallback_state = "in_progress"
        else:
            fallback_state = "not_started"

        try:
            if isinstance(entity, Mapping):
                return fallback_state, None, []
            result = ExecutionPerformanceService.analyze_task_execution(entity)
            variance = (
                result.start_variance_display
                if result.execution_state == ExecutionState.IN_PROGRESS
                else result.finish_variance_display
            )
            return result.execution_state.value, variance, list(result.diagnostics or [])
        except Exception:
            return fallback_state, None, []


class ScheduleDetailsFormatter:
    """
    Enterprise schedule details formatter.
    Consumes canonical analytical values without recalculating CPM or schedule math.
    """

    @classmethod
    def build_from_entity(
        cls,
        entity: Any,
        project_name: Optional[str] = None,
        db_manager: Any = None,
    ) -> ScheduleDetailsModel:
        return ScheduleDetailsCollector.collect(
            entity,
            project_name=project_name,
            db_manager=db_manager,
        )

    @classmethod
    def format_type_label(cls, model: ScheduleDetailsModel) -> str:
        if model.is_summary:
            return "Summary"
        if model.is_milestone:
            return "Milestone"
        if model.entity_type == "subtask":
            if model.depth <= 1:
                return "Subtask"
            return f"Level {model.depth} Subtask"
        return "Task"

    @classmethod
    def format_duration_with_canonical(cls, minutes: Optional[int]) -> str:
        if minutes is None:
            return "None"
        if minutes == 0:
            return "0 min"
        disp = format_float_duration(minutes)
        if abs(minutes) >= 60:
            return f"{disp} ({minutes} min)"
        return f"{minutes} min"

    @classmethod
    def format_duration_days(cls, minutes: Optional[int]) -> str:
        if minutes is None:
            return _NOT_AVAILABLE
        return f"{minutes / 1440:.2f} days"

    @classmethod
    def format_float_with_canonical(cls, minutes: Optional[int]) -> str:
        if minutes is None:
            return "None"
        if minutes == 0:
            return "0 min"
        disp = format_float_duration(minutes)
        if abs(minutes) >= 60:
            return f"{disp} ({minutes} min)"
        return f"{minutes} min"

    @classmethod
    def _datetime_or_state(cls, value: Optional[str], state: str = _NOT_AVAILABLE) -> str:
        return format_cpm_datetime(value) if value else state

    @classmethod
    def _cpm_datetime_or_state(cls, model: ScheduleDetailsModel, value: Optional[str]) -> str:
        return format_cpm_datetime(value) if model.has_cpm and value else _NOT_ANALYZED

    @classmethod
    def _float_or_state(cls, model: ScheduleDetailsModel, value: Optional[int]) -> str:
        if model.is_summary and value is None:
            return "N/A (Summary)"
        return cls.format_float_with_canonical(value) if model.has_cpm and value is not None else _NOT_ANALYZED

    @classmethod
    def _critical_or_state(cls, model: ScheduleDetailsModel) -> str:
        if model.is_summary:
            if not model.has_cpm or model.cpm_is_critical is None:
                return "N/A (Summary)"
            return "Contains Critical" if model.cpm_is_critical else "No Critical"
        if not model.has_cpm or model.cpm_is_critical is None:
            return _NOT_ANALYZED
        return "Yes" if model.cpm_is_critical else "No"

    @staticmethod
    def _weekdays_text(days: Optional[Tuple[int, ...]]) -> str:
        if days is None:
            return _NOT_AVAILABLE
        return ", ".join(_WEEKDAY_NAMES[int(day)] for day in days if 0 <= int(day) <= 6)

    @classmethod
    def _variance_text(cls, value: Optional[int]) -> str:
        return format_variance_duration(value) if value is not None else _NOT_AVAILABLE

    @classmethod
    def format_plain_text(cls, model: ScheduleDetailsModel) -> str:
        lines: List[str] = []

        lines.append(f"Task: {model.title}")
        lines.append(f"Type: {cls.format_type_label(model)}")
        lines.append(f"Project: {model.project_name or _NOT_AVAILABLE}")
        lines.append(f"WBS Path / Parent: {model.wbs_path or model.parent_path or _NOT_AVAILABLE}")
        if model.wbs_code:
            lines.append(f"WBS Code: {model.wbs_code}")
        lines.append(f"Status: {model.status or _NOT_AVAILABLE}")
        lines.append(f"Priority: {model.priority or _NOT_AVAILABLE}")
        if model.is_summary:
            lines.append("Summary Source: Derived WBS summary values; raw task input remains unchanged.")
        lines.append("")

        lines.append("--- Planned Input ---")
        lines.append(f"Planned Start: {cls._datetime_or_state(model.planned_start)}")
        lines.append(f"Planned/Target Finish: {cls._datetime_or_state(model.planned_finish)}")
        lines.append(f"Planned Finish: {cls._datetime_or_state(model.planned_finish)}")
        lines.append(f"Estimated Duration: {cls.format_duration_days(model.planned_duration_minutes)}")
        lines.append(
            "Estimated Duration Minutes: "
            + (str(model.planned_duration_minutes) if model.planned_duration_minutes is not None else _NOT_AVAILABLE)
        )
        lines.append(
            "Planned Duration: "
            + (
                cls.format_duration_with_canonical(model.planned_duration_minutes)
                if model.planned_duration_minutes is not None
                else _NOT_AVAILABLE
            )
        )
        lines.append(
            "Planned Effort: "
            + (
                cls.format_duration_with_canonical(model.planned_effort_minutes)
                if model.planned_effort_minutes is not None
                else _NOT_AVAILABLE
            )
        )
        lines.append(
            "Daily Dedication: "
            + (
                cls.format_duration_with_canonical(model.daily_dedication_minutes)
                if model.daily_dedication_minutes is not None
                else _NOT_AVAILABLE
            )
        )
        lines.append(f"Progress: {model.progress}%")
        lines.append(f"Gantt Bar Start: {cls._datetime_or_state(model.gantt_bar_start or model.planned_start)}")
        lines.append(f"Gantt Bar Finish: {cls._datetime_or_state(model.gantt_bar_finish or model.planned_finish)}")
        if model.gantt_bar_left_x is not None and model.gantt_bar_right_x is not None:
            lines.append(f"Gantt Bar Left X: {model.gantt_bar_left_x:.2f}")
            lines.append(f"Gantt Bar Right X: {model.gantt_bar_right_x:.2f}")
        else:
            lines.append("Gantt Bar Left X: Not captured in this inspector context")
            lines.append("Gantt Bar Right X: Not captured in this inspector context")
        lines.append("")

        lines.append("--- Current Forecast / CPM ---")
        status = "Analyzed" if model.has_cpm else "Not analyzed"
        if model.has_cycle:
            status = "Blocked - dependency cycle"
        elif model.cpm_analysis_status:
            normalized = model.cpm_analysis_status.replace("_", " ").strip()
            status = normalized[:1].upper() + normalized[1:] if normalized else status
        lines.append(f"CPM Status: {status}")
        if model.has_cycle:
            lines.append("CPM: Not analyzed (Dependency Cycle detected)")
        lines.append(f"ES: {cls._cpm_datetime_or_state(model, model.cpm_es)}")
        lines.append(f"EF: {cls._cpm_datetime_or_state(model, model.cpm_ef)}")
        lines.append(f"LS: {cls._cpm_datetime_or_state(model, model.cpm_ls)}")
        lines.append(f"LF: {cls._cpm_datetime_or_state(model, model.cpm_lf)}")
        lines.append(f"Total Float: {cls._float_or_state(model, model.cpm_tf)}")
        lines.append(f"Free Float: {cls._float_or_state(model, model.cpm_ff)}")
        lines.append(f"Critical: {cls._critical_or_state(model)}")
        lines.append("")

        lines.append("--- Dependencies ---")
        if model.predecessors:
            lines.append("Predecessors:")
            lines.extend(f"- {item}" for item in model.predecessors)
        else:
            lines.append("Predecessors: None")
        if model.successors:
            lines.append("Successors:")
            lines.extend(f"- {item}" for item in model.successors)
        else:
            lines.append("Successors: None")
        lines.append("")

        lines.append("--- Constraint / Deadline ---")
        if model.constraint_type:
            constraint = model.constraint_type
            if model.constraint_datetime:
                constraint += f" ({format_cpm_datetime(model.constraint_datetime)})"
            lines.append(f"Constraint: {constraint}")
            lines.append(f"Constraint Type: {model.constraint_type}")
            lines.append(f"Constraint Date: {cls._datetime_or_state(model.constraint_datetime)}")
        else:
            lines.append("Constraint: None")
            lines.append("Constraint Type: None")
            lines.append("Constraint Date: None")
        lines.append(f"Deadline: {cls._datetime_or_state(model.deadline_datetime, 'None')}")
        if model.constraint_diagnostics:
            lines.append("Constraint Diagnostics:")
            lines.extend(f"- {item}" for item in model.constraint_diagnostics)
        else:
            lines.append("Constraint Diagnostics: None")
        lines.append("")

        lines.append("--- Calendar ---")
        lines.append(f"Effective Project Calendar: {model.calendar_name or _NOT_AVAILABLE}")
        lines.append(f"Working Weekdays: {cls._weekdays_text(model.working_weekdays)}")
        lines.append("")

        lines.append("--- Baseline / Revision ---")
        if model.baseline_start or model.baseline_finish:
            lines.append(
                "Original Baseline: "
                f"{cls._datetime_or_state(model.baseline_start)} -> {cls._datetime_or_state(model.baseline_finish)}"
            )
            lines.append(f"Baseline Start: {cls._datetime_or_state(model.baseline_start)}")
            lines.append(f"Baseline Finish: {cls._datetime_or_state(model.baseline_finish)}")
        elif model.has_baseline:
            lines.append("Original Baseline: Active snapshot")
            lines.append("Baseline: Active snapshot")
        else:
            lines.append("Original Baseline: Not Baselined")
            lines.append("Baseline: Not Baselined")
        if model.has_revision:
            lines.append(f"Approved Revision: {model.revision_name or 'Approved Revision'}")
            lines.append(f"Revision Start: {cls._datetime_or_state(model.revision_start)}")
            lines.append(f"Revision Finish: {cls._datetime_or_state(model.revision_finish)}")
        else:
            lines.append("Approved Revision: None")
            lines.append("Revision: None")
        lines.append(
            "Current Forecast Variance vs Baseline: "
            f"Start {cls._variance_text(model.baseline_start_variance_minutes)}, "
            f"Finish {cls._variance_text(model.baseline_variance_minutes)}"
        )
        lines.append(f"Current Forecast Variance vs Revision: {cls._variance_text(model.revision_variance_minutes)}")
        lines.append("")

        lines.append("--- Actual ---")
        if model.actual_state == "not_started":
            lines.append("Actual Tracking: Not Tracked")
            lines.append("Actual: Not Tracked")
            lines.append("Actual Start: None")
            lines.append("Actual Finish: None")
            lines.append("Actual Elapsed Span: None")
        elif model.actual_state == "in_progress":
            elapsed = (
                f"{model.actual_elapsed_span_minutes} min"
                if model.actual_elapsed_span_minutes is not None
                else _NOT_AVAILABLE
            )
            logged = (
                f" ({model.actual_duration_minutes} min logged)"
                if model.actual_duration_minutes is not None
                else ""
            )
            lines.append("Actual Tracking: In Progress")
            lines.append(f"Actual: {cls._datetime_or_state(model.actual_start)} -> In Progress{logged}")
            lines.append(f"Actual Start: {cls._datetime_or_state(model.actual_start)}")
            lines.append("Actual Finish: In Progress")
            lines.append(f"Actual Elapsed Span: {elapsed}")
        else:
            elapsed = (
                f"{model.actual_elapsed_span_minutes} min"
                if model.actual_elapsed_span_minutes is not None
                else _NOT_AVAILABLE
            )
            logged = (
                f" ({model.actual_duration_minutes} min logged)"
                if model.actual_duration_minutes is not None
                else ""
            )
            lines.append("Actual Tracking: Finished")
            lines.append(
                f"Actual: {cls._datetime_or_state(model.actual_start)} -> "
                f"{cls._datetime_or_state(model.actual_finish)}{logged}"
            )
            lines.append(f"Actual Start: {cls._datetime_or_state(model.actual_start)}")
            lines.append(f"Actual Finish: {cls._datetime_or_state(model.actual_finish)}")
            lines.append(f"Actual Elapsed Span: {elapsed}")
        lines.append(f"Execution Variance: {model.actual_variance_display or _NOT_AVAILABLE}")

        if model.delay_minutes > 0:
            lines.append("")
            lines.append(f"Delay: {model.delay_minutes} min ({model.delay_percentage:.1f}%)")
            if model.delay_reason:
                lines.append(f"Delay Reason: {model.delay_reason}")
            if model.delay_notes:
                lines.append(f"Delay Notes: {model.delay_notes}")

        if model.diagnostics:
            lines.append("")
            lines.append("Execution Diagnostics:")
            lines.extend(f"- {item}" for item in model.diagnostics[:3])

        return "\n".join(lines).strip()

    @classmethod
    def format_html(cls, model: ScheduleDetailsModel, is_dark: bool = True) -> str:
        badge_bg = "#3584E4" if not model.is_summary else "#8B5CF6"
        text = "#F8FAFC" if is_dark else "#111827"
        muted = "#CBD5E1" if is_dark else "#4B5563"
        surface = "#0F172A" if is_dark else "#FFFFFF"
        border = "#334155" if is_dark else "#CBD5E1"
        type_str = cls.format_type_label(model)
        wbs_part = f" [{model.wbs_code}]" if model.wbs_code else ""
        plain = html.escape(cls.format_plain_text(model))
        return (
            "<div style='font-family: inherit; font-size: 13px; line-height: 1.45;'>"
            f"<div style='font-size: 15px; font-weight: bold; color: {text}; margin-bottom: 4px;'>{html.escape(model.title)}</div>"
            f"<div style='margin-bottom: 8px; color: {muted};'>"
            f"<span style='background-color: {badge_bg}; color: #FFFFFF; font-size: 11px; font-weight: bold; padding: 2px 6px; border-radius: 4px;'>"
            f"{html.escape(type_str + wbs_part)}</span>"
            f" &nbsp; <b>{html.escape(model.project_name or _NOT_AVAILABLE)}</b>"
            f" &nbsp; | &nbsp; <b>{html.escape(model.status or _NOT_AVAILABLE)}</b> ({model.progress}%)"
            "</div>"
            f"<pre style='white-space: pre-wrap; margin: 0; padding: 10px; border: 1px solid {border}; border-radius: 6px; "
            f"background: {surface}; color: {text}; font-family: inherit; font-size: 12px; line-height: 1.45;'>"
            f"{plain}</pre></div>"
        )
