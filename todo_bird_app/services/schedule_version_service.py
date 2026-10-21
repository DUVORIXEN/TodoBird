"""
TODO BIRD - SCHEDULE VERSION SERVICE (Phase 2E)

Canonical approval authority for Original Baseline and Approved Revision
snapshots. Legacy baseline columns are kept as a display compatibility cache;
schedule_versions and schedule_version_items are the immutable history.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from todo_bird_app.database import (
    SCHEDULE_VERSION_APPROVED_REVISION,
    SCHEDULE_VERSION_ORIGINAL_BASELINE,
    ScheduleVersionGovernanceError,
)
from todo_bird_app.services.schedule_variance_service import parse_datetime_flexible

logger = logging.getLogger(__name__)


class ScheduleVersionService:
    """Service to create, query, and compare immutable schedule snapshots."""

    @staticmethod
    def _row_value(row: Any, key: str, default: Any = None) -> Any:
        if isinstance(row, dict):
            return row.get(key, default)
        return getattr(row, key, default)

    @staticmethod
    def _format_snapshot_datetime(value: Any) -> Optional[str]:
        parsed = parse_datetime_flexible(value)
        if parsed is None:
            return None
        return parsed.strftime("%Y-%m-%d %H:%M")

    @classmethod
    def _cpm_value(
        cls,
        cpm_results: Optional[Dict[Any, Any]],
        entity_type: str,
        entity_id: int,
    ) -> Optional[Any]:
        if not cpm_results:
            return None
        try:
            from todo_bird_app.services.wbs_service import EntityRef

            typed_key = EntityRef(entity_type, entity_id)
            if typed_key in cpm_results:
                return cpm_results[typed_key]
        except Exception:
            pass
        if (entity_type, entity_id) in cpm_results:
            return cpm_results[(entity_type, entity_id)]
        if entity_type == "task" and entity_id in cpm_results:
            return cpm_results[entity_id]
        return None

    @classmethod
    def _snapshot_from_record(
        cls,
        record: Dict[str, Any],
        *,
        entity_type: str,
        entity_id: int,
        task_id: Optional[int],
        parent_subtask_id: Optional[int],
        wbs_path: str,
        cpm_node: Optional[Any] = None,
    ) -> Dict[str, Any]:
        start = None
        finish = None
        duration = None

        if cpm_node is not None:
            if isinstance(cpm_node, dict):
                start = cpm_node.get("start") or cpm_node.get("earliest_start")
                finish = cpm_node.get("finish") or cpm_node.get("earliest_finish")
                duration = cpm_node.get("duration_minutes")
                if duration is None:
                    duration = cpm_node.get("planned_duration_minutes")
            elif getattr(cpm_node, "schedulable", True):
                start = getattr(cpm_node, "earliest_start", None)
                finish = getattr(cpm_node, "earliest_finish", None)
                duration = getattr(cpm_node, "planned_duration_minutes", None)
                if duration is None:
                    duration = getattr(cpm_node, "duration_minutes", None)

        if start is None and finish is None:
            planned_date = cls._row_value(record, "planned_date")
            planned_start_time = cls._row_value(record, "planned_start_time")
            due_date = cls._row_value(record, "due_date") or planned_date
            planned_end_time = cls._row_value(record, "planned_end_time")
            start = parse_datetime_flexible(planned_date, planned_start_time)
            finish = parse_datetime_flexible(due_date, planned_end_time)
            if finish is None and start is not None:
                raw_duration = cls._row_value(record, "estimated_duration", 0)
                try:
                    duration_minutes = int(raw_duration or 0)
                except (TypeError, ValueError):
                    duration_minutes = 0
                if duration_minutes == 0:
                    finish = start

        start_text = cls._format_snapshot_datetime(start)
        finish_text = cls._format_snapshot_datetime(finish)
        if duration is None:
            duration = cls._row_value(record, "estimated_duration")
        if duration is None and start_text and finish_text:
            start_dt = parse_datetime_flexible(start_text)
            finish_dt = parse_datetime_flexible(finish_text)
            if start_dt and finish_dt:
                duration = max(0, int((finish_dt - start_dt).total_seconds() / 60))
        try:
            duration = int(duration or 0)
        except (TypeError, ValueError):
            duration = 0

        planned_effort = cls._row_value(record, "planned_effort_minutes", 0)

        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "title": cls._row_value(record, "title", ""),
            "task_id": task_id,
            "parent_subtask_id": parent_subtask_id,
            "wbs_path": wbs_path,
            "sort_order": cls._row_value(record, "position", 0) or 0,
            "start": start_text,
            "finish": finish_text,
            "duration_minutes": duration,
            "planned_effort_minutes": planned_effort,
        }

    @classmethod
    def _subtask_wbs_path(cls, subtasks_by_id: Dict[int, Dict[str, Any]], subtask_id: int) -> str:
        row = subtasks_by_id.get(subtask_id)
        if not row:
            return f"subtask:{subtask_id}"
        task_id = int(row["task_id"])
        parts = [f"subtask:{subtask_id}"]
        parent_id = row.get("parent_subtask_id")
        seen = {subtask_id}
        while parent_id is not None:
            try:
                parent_id_int = int(parent_id)
            except (TypeError, ValueError):
                break
            if parent_id_int in seen:
                break
            seen.add(parent_id_int)
            parts.append(f"subtask:{parent_id_int}")
            parent_row = subtasks_by_id.get(parent_id_int)
            parent_id = parent_row.get("parent_subtask_id") if parent_row else None
        return f"task:{task_id}/" + "/".join(reversed(parts))

    @classmethod
    def _all_project_tasks(cls, db_manager, project_id: int) -> List[Dict[str, Any]]:
        with db_manager.get_connection() as conn:
            cursor = conn.cursor()
            if project_id in (1, 0, None):
                cursor.execute(
                    """
                    SELECT *
                    FROM tasks
                    WHERE project_id IS NULL OR project_id = 1 OR project_id = 0
                    ORDER BY position ASC, id ASC;
                    """
                )
            else:
                cursor.execute(
                    """
                    SELECT *
                    FROM tasks
                    WHERE project_id = ?
                    ORDER BY position ASC, id ASC;
                    """,
                    (project_id,),
                )
            return [dict(row) for row in cursor.fetchall()]

    @classmethod
    def _project_calendar_spec(cls, db_manager, project_id: int):
        try:
            from todo_bird_app.services.schedule_calendar_service import (
                effective_project_calendar_from_db,
            )

            return effective_project_calendar_from_db(db_manager, project_id)
        except Exception as exc:  # pragma: no cover - defensive fallback only
            logger.debug("Project calendar unavailable for schedule snapshot: %s", exc)
            return None

    @classmethod
    def capture_current_schedule_snapshot(
        cls,
        db_manager,
        project_id: int,
        cpm_results: Optional[Dict[Any, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Capture tasks and nested subtasks for the current forecast authority."""
        if db_manager is None:
            raise ValueError("db_manager is required")

        tasks = cls._all_project_tasks(db_manager, project_id)

        computed_cpm = None
        if cpm_results is None and tasks:
            try:
                from todo_bird_app.services.wbs_cpm_adapter import calculate_wbs_cpm
                from todo_bird_app.services.wbs_service import WBSService

                snapshot = WBSService.build_project_hierarchy(
                    db_manager,
                    project_id=project_id,
                )
                computed_cpm = calculate_wbs_cpm(
                    snapshot,
                    db_manager,
                    project_calendar=cls._project_calendar_spec(db_manager, project_id),
                )
            except Exception as exc:  # pragma: no cover - fallback is planned schedule
                logger.debug("CPM snapshot fallback to planned dates: %s", exc)
                computed_cpm = None

        items: List[Dict[str, Any]] = []
        for task in tasks:
            task_id = int(task["id"])
            cpm_node = cls._cpm_value(cpm_results, "task", task_id)
            if cpm_node is None and computed_cpm is not None:
                cpm_node = computed_cpm.get_node(("task", task_id))
            items.append(
                cls._snapshot_from_record(
                    task,
                    entity_type="task",
                    entity_id=task_id,
                    task_id=task_id,
                    parent_subtask_id=None,
                    wbs_path=f"task:{task_id}",
                    cpm_node=cpm_node,
                )
            )

            subtasks = [dict(row) for row in db_manager.get_all_subtasks_flat(task_id)]
            subtasks_by_id = {int(row["id"]): row for row in subtasks}
            for subtask in subtasks:
                subtask_id = int(subtask["id"])
                subtask_cpm = cls._cpm_value(cpm_results, "subtask", subtask_id)
                if subtask_cpm is None and computed_cpm is not None:
                    subtask_cpm = computed_cpm.get_node(("subtask", subtask_id))
                items.append(
                    cls._snapshot_from_record(
                        subtask,
                        entity_type="subtask",
                        entity_id=subtask_id,
                        task_id=task_id,
                        parent_subtask_id=subtask.get("parent_subtask_id"),
                        wbs_path=cls._subtask_wbs_path(subtasks_by_id, subtask_id),
                        cpm_node=subtask_cpm,
                    )
                )

        return items

    @classmethod
    def _baseline_payloads_from_snapshot(
        cls,
        items: List[Dict[str, Any]],
    ) -> tuple[Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]]]:
        task_baselines: Dict[int, Dict[str, Any]] = {}
        subtask_baselines: Dict[int, Dict[str, Any]] = {}
        for item in items:
            payload = {
                "baseline_start": item.get("start"),
                "baseline_finish": item.get("finish"),
                "baseline_duration_minutes": item.get("duration_minutes"),
                "baseline_planned_effort_minutes": item.get("planned_effort_minutes"),
            }
            if item.get("entity_type") == "task":
                task_baselines[int(item["entity_id"])] = payload
            elif item.get("entity_type") == "subtask":
                subtask_baselines[int(item["entity_id"])] = payload
        return task_baselines, subtask_baselines

    @staticmethod
    def get_original_baseline_version(db_manager, project_id: int) -> Optional[Dict[str, Any]]:
        if db_manager is None:
            return None
        if hasattr(db_manager, "get_original_schedule_version"):
            return db_manager.get_original_schedule_version(project_id)
        versions = db_manager.get_schedule_versions_for_project(project_id)
        return next(
            (
                v for v in versions
                if v.get("is_original_baseline") or v.get("version_type") == SCHEDULE_VERSION_ORIGINAL_BASELINE
            ),
            None,
        )

    @staticmethod
    def has_original_baseline(db_manager, project_id: int, include_legacy: bool = True) -> bool:
        if db_manager is None:
            return False
        if hasattr(db_manager, "has_original_baseline"):
            return bool(db_manager.has_original_baseline(project_id, include_legacy=include_legacy))
        return ScheduleVersionService.get_original_baseline_version(db_manager, project_id) is not None

    @staticmethod
    def ensure_original_baseline_migrated(db_manager, project_id: int) -> Optional[int]:
        """
        Idempotently migrate real Phase 2D legacy baseline evidence.

        This never invents an Original Baseline for a project with no legacy
        baseline metadata/items, which keeps comparison selectors read-only.
        """
        if db_manager is None:
            return None

        existing = ScheduleVersionService.get_original_baseline_version(db_manager, project_id)
        if existing is not None:
            return existing["id"]

        project = db_manager.get_project(project_id)
        if not project:
            return None

        all_tasks = ScheduleVersionService._all_project_tasks(db_manager, project_id)
        version_items: List[Dict[str, Any]] = []
        for task in all_tasks:
            task_id = int(ScheduleVersionService._row_value(task, "id"))
            if any(ScheduleVersionService._row_value(task, col) is not None for col in (
                "baseline_start",
                "baseline_finish",
                "baseline_duration_minutes",
                "baseline_planned_effort_minutes",
            )):
                version_items.append({
                    "entity_type": "task",
                    "entity_id": task_id,
                    "title": ScheduleVersionService._row_value(task, "title", ""),
                    "task_id": task_id,
                    "parent_subtask_id": None,
                    "wbs_path": f"task:{task_id}",
                    "sort_order": ScheduleVersionService._row_value(task, "position", 0) or 0,
                    "start": ScheduleVersionService._row_value(task, "baseline_start"),
                    "finish": ScheduleVersionService._row_value(task, "baseline_finish"),
                    "duration_minutes": ScheduleVersionService._row_value(task, "baseline_duration_minutes"),
                    "planned_effort_minutes": ScheduleVersionService._row_value(task, "baseline_planned_effort_minutes"),
                })

            subtasks = [dict(row) for row in db_manager.get_all_subtasks_flat(task_id)]
            subtasks_by_id = {int(row["id"]): row for row in subtasks}
            for subtask in subtasks:
                if not any(subtask.get(col) is not None for col in (
                    "baseline_start",
                    "baseline_finish",
                    "baseline_duration_minutes",
                    "baseline_planned_effort_minutes",
                )):
                    continue
                subtask_id = int(subtask["id"])
                version_items.append({
                    "entity_type": "subtask",
                    "entity_id": subtask_id,
                    "title": subtask.get("title", ""),
                    "task_id": task_id,
                    "parent_subtask_id": subtask.get("parent_subtask_id"),
                    "wbs_path": ScheduleVersionService._subtask_wbs_path(subtasks_by_id, subtask_id),
                    "sort_order": subtask.get("position", 0) or 0,
                    "start": subtask.get("baseline_start"),
                    "finish": subtask.get("baseline_finish"),
                    "duration_minutes": subtask.get("baseline_duration_minutes"),
                    "planned_effort_minutes": subtask.get("baseline_planned_effort_minutes"),
                })

        created_at = project.get("baseline_created_at") if isinstance(project, dict) else None
        if not created_at and not version_items:
            return None

        version_name = (
            project.get("baseline_name")
            if isinstance(project, dict) and project.get("baseline_name")
            else "Original Baseline"
        )
        migration_timestamp = created_at or datetime.now().isoformat()
        return db_manager.create_schedule_version(
            project_id=project_id,
            name=version_name,
            version_type=SCHEDULE_VERSION_ORIGINAL_BASELINE,
            created_at=migration_timestamp,
            approved_at=migration_timestamp,
            notes="Migrated Original Baseline Snapshot",
            is_original_baseline=True,
            sequence_order=1,
            items=version_items,
        )

    @classmethod
    def create_original_baseline(
        cls,
        db_manager,
        project_id: int,
        name: str = "Original Baseline",
        notes: Optional[str] = None,
        cpm_results: Optional[Dict[Any, Any]] = None,
        approved_at: Optional[str] = None,
    ) -> int:
        """Create the one immutable Original Baseline for a project."""
        if db_manager is None:
            raise ValueError("db_manager is required")
        existing = cls.get_original_baseline_version(db_manager, project_id)
        if existing is not None:
            raise ScheduleVersionGovernanceError(
                "Original Baseline already exists. Create an Approved Revision instead."
            )
        items = cls.capture_current_schedule_snapshot(db_manager, project_id, cpm_results=cpm_results)
        task_baselines, subtask_baselines = cls._baseline_payloads_from_snapshot(items)
        timestamp = approved_at or datetime.now().isoformat()
        db_manager.set_project_baseline(
            project_id,
            name,
            task_baselines,
            subtask_baselines=subtask_baselines,
            created_at=timestamp,
            notes=notes or "Original Baseline approval",
        )
        original = cls.get_original_baseline_version(db_manager, project_id)
        if original is None:
            raise ScheduleVersionGovernanceError("Original Baseline creation did not persist a version row.")
        return int(original["id"])

    @classmethod
    def create_approved_revision(
        cls,
        db_manager,
        project_id: int,
        name: Optional[str] = None,
        notes: Optional[str] = None,
        cpm_results: Optional[Dict[Any, Any]] = None,
        approved_at: Optional[str] = None,
    ) -> int:
        """
        Create a new immutable approved schedule revision snapshot.

        Original Baseline is never replaced; each call creates a distinct
        deterministic sequence row for the project.
        """
        if db_manager is None:
            raise ValueError("db_manager is required")

        now_str = approved_at or datetime.now().isoformat(timespec="seconds")
        items = cls.capture_current_schedule_snapshot(db_manager, project_id, cpm_results=cpm_results)

        if not name:
            versions = db_manager.get_schedule_versions_for_project(project_id)
            revision_count = sum(
                1 for v in versions
                if v.get("version_type") == SCHEDULE_VERSION_APPROVED_REVISION
                and not v.get("is_original_baseline")
            )
            name = f"Revision {revision_count + 1}"

        return db_manager.create_schedule_version(
            project_id=project_id,
            name=name,
            version_type=SCHEDULE_VERSION_APPROVED_REVISION,
            created_at=now_str,
            approved_at=now_str,
            notes=notes or "",
            is_original_baseline=False,
            sequence_order=None,
            items=items,
        )

    @classmethod
    def get_latest_approved_revision(cls, db_manager, project_id: int) -> Optional[Dict[str, Any]]:
        if db_manager is None:
            return None
        if hasattr(db_manager, "get_latest_approved_revision"):
            return db_manager.get_latest_approved_revision(project_id)
        versions = db_manager.get_schedule_versions_for_project(project_id)
        revisions = [
            v for v in versions
            if v.get("version_type") == SCHEDULE_VERSION_APPROVED_REVISION
            and not v.get("is_original_baseline")
        ]
        return revisions[-1] if revisions else None

    @classmethod
    def get_version_lookup(
        cls,
        db_manager,
        version_id: int,
    ) -> Dict[Tuple[str, int], Dict[str, Any]]:
        """Return {(entity_type, entity_id): snapshot item} for O(1) comparison."""
        if db_manager is None or not version_id:
            return {}

        items = db_manager.get_schedule_version_items(version_id)
        lookup: Dict[Tuple[str, int], Dict[str, Any]] = {}
        for item in items:
            key = (item["entity_type"], item["entity_id"])
            lookup[key] = item
        return lookup
