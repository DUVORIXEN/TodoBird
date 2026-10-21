import logging
from typing import List, Optional
from datetime import date, datetime
from PySide6.QtCore import QObject, Signal, Qt

from todo_bird_app.gantt.gantt_dependency_engine import GanttDependencyEngine
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority, TaskCategory
from todo_bird_app.models.project import Project
from todo_bird_app.utils.time_math import get_current_datetime

logger = logging.getLogger(__name__)

class _TaskEventBus(QObject):
    tasks_changed = Signal()
    projects_changed = Signal()
    working_calendar_changed = Signal()
    typography_changed = Signal()
    appearance_changed = Signal(object)
    experience_mode_changed = Signal(str)
    world_clocks_changed = Signal()

_GLOBAL_EVENT_BUS = _TaskEventBus()

class TaskController(QObject):
    """
    Controller handling task and project CRUD logic with signal notifications.
    """
    tasks_changed = Signal()
    projects_changed = Signal()

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self._global_tasks_connected = False
        self._global_projects_connected = False
        # Bridge global bus signals to instance signals with UniqueConnection
        try:
            _GLOBAL_EVENT_BUS.tasks_changed.connect(self._on_bus_tasks_changed, Qt.UniqueConnection)
            self._global_tasks_connected = True
            _GLOBAL_EVENT_BUS.projects_changed.connect(self._on_bus_projects_changed, Qt.UniqueConnection)
            self._global_projects_connected = True
        except Exception:
            if not self._global_tasks_connected:
                _GLOBAL_EVENT_BUS.tasks_changed.connect(self._on_bus_tasks_changed)
                self._global_tasks_connected = True
            if not self._global_projects_connected:
                _GLOBAL_EVENT_BUS.projects_changed.connect(self._on_bus_projects_changed)
                self._global_projects_connected = True

        try:
            self.destroyed.connect(self._on_self_destroyed)
        except Exception:
            pass

    def _on_self_destroyed(self, *args):
        self.cleanup()

    def cleanup(self):
        if getattr(self, "_global_tasks_connected", False):
            try:
                _GLOBAL_EVENT_BUS.tasks_changed.disconnect(self._on_bus_tasks_changed)
            except Exception:
                pass
            self._global_tasks_connected = False
        if getattr(self, "_global_projects_connected", False):
            try:
                _GLOBAL_EVENT_BUS.projects_changed.disconnect(self._on_bus_projects_changed)
            except Exception:
                pass
            self._global_projects_connected = False

    def _on_bus_tasks_changed(self):
        self.tasks_changed.emit()

    def _on_bus_projects_changed(self):
        self.projects_changed.emit()

    def notify_tasks_changed(self) -> None:
        """
        Public notification hook for successful external transactional
        mutations such as WBS hierarchy/order changes.

        This intentionally reuses the canonical global task event bus so
        every existing TaskController consumer — including Gantt — refreshes
        through the same production signal path.
        """
        _GLOBAL_EVENT_BUS.tasks_changed.emit()

    @staticmethod
    def _normalize_progress(value: int) -> int:
        try:
            value = int(value)
        except (TypeError, ValueError):
            return 0
        return max(0, min(100, value))

    def add_task(self, task: Task) -> int:
        task.progress = self._normalize_progress(task.progress)
        task_dict = task.to_dict()
        task_id = self.db_manager.insert_task(task_dict)
        if task.id is None or task.id != task_id:
            task.id = task_id
        logger.info(f"Task added: ID={task_id}, Title='{task.title}'")
        _GLOBAL_EVENT_BUS.tasks_changed.emit()
        return task_id

    def update_task(self, task: Task) -> bool:
        if task.id is None:
            return False

        task.progress = self._normalize_progress(task.progress)

        existing_tasks = [Task.from_row(row) for row in self.db_manager.get_all_tasks()]
        current_db_task = next((t for t in existing_tasks if t.id == task.id), None)
        from todo_bird_app.services.cpm_scheduling_service import parse_dependency_specs
        from todo_bird_app.services.dependency_authoring_service import (
            DependencyAuthoringService,
            raw_dependencies_contain_typed_refs,
        )
        from todo_bird_app.services.wbs_service import EntityRef
        current_specs = parse_dependency_specs(current_db_task.dependencies if current_db_task else None, successor_id=task.id)
        new_specs = parse_dependency_specs(task.dependencies, successor_id=task.id)
        deps_changed = current_db_task is None or current_specs != new_specs
        has_typed_dependencies = raw_dependencies_contain_typed_refs(
            task.dependencies
        ) or raw_dependencies_contain_typed_refs(
            current_db_task.dependencies if current_db_task else None
        )

        if deps_changed or has_typed_dependencies:
            if has_typed_dependencies:
                validation = DependencyAuthoringService.validate_dependencies(
                    self.db_manager,
                    successor_key=EntityRef.task(task.id),
                    raw_dependencies=task.dependencies,
                    project_id=task.project_id,
                )
                if not validation.valid:
                    logger.warning(
                        "Typed task dependency validation failed for %s: %s",
                        task.id,
                        validation.message,
                    )
                    return False
            else:
                validation = GanttDependencyEngine.validate_proposed_dependencies(
                    task_id=task.id,
                    candidate_ids=task.dependencies,
                    tasks=existing_tasks,
                )
                if not validation["valid"] and not validation.get("missing_ids"):
                    logger.warning(
                        "Task dependency validation failed for %s: %s",
                        task.id,
                        validation["message"],
                    )
                    return False

        success = self.db_manager.update_task(task.to_dict())
        if success:
            logger.info(f"Task updated: ID={task.id}, Title='{task.title}'")
            _GLOBAL_EVENT_BUS.tasks_changed.emit()
        return success

    def delete_task(self, task_id: int) -> bool:
        success = self.db_manager.delete_task(task_id)
        if success:
            logger.info(f"Task deleted: ID={task_id}")
            _GLOBAL_EVENT_BUS.tasks_changed.emit()
        return success

    def pin_task(self, task_id: int) -> bool:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tasks
                SET is_pinned = 1,
                    pin_position = (SELECT COALESCE(MAX(pin_position), 0) + 1 FROM tasks WHERE is_pinned = 1),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (task_id,),
            )
            conn.commit()
            success = cursor.rowcount > 0
        if success:
            _GLOBAL_EVENT_BUS.tasks_changed.emit()
        return success

    def unpin_task(self, task_id: int) -> bool:
        with self.db_manager.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE tasks
                SET is_pinned = 0,
                    pin_position = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (task_id,),
            )
            conn.commit()
            success = cursor.rowcount > 0
        if success:
            _GLOBAL_EVENT_BUS.tasks_changed.emit()
        return success

    def toggle_task_complete(self, task_id: int) -> bool:
        task_data = self.db_manager.get_task_by_id(task_id)
        if not task_data:
            return False

        task = Task.from_row(task_data)
        from todo_bird_app.utils.time_math import get_current_datetime
        now = get_current_datetime()
        if task.status == TaskStatus.COMPLETED:
            task.status = TaskStatus.INBOX if task.planned_date is None else TaskStatus.PLANNED
            task.progress = 0
            task.actual_end_date = None
            task.actual_end_time = None
        else:
            task.status = TaskStatus.COMPLETED
            task.progress = 100
            # Explicit user completion: only stamp actual finish if tracking was active
            if task.actual_start_date:
                task.actual_end_date = now.strftime("%Y-%m-%d")
                task.actual_end_time = now.strftime("%H:%M")

        return self.update_task(task)

    def get_task(self, task_id: int) -> Optional[Task]:
        data = self.db_manager.get_task_by_id(task_id)
        return Task.from_row(data) if data else None

    def get_inbox_tasks(self, limit: int = 100, offset: int = 0) -> List[Task]:
        rows = self.db_manager.get_inbox_tasks(limit=limit, offset=offset)
        return [Task.from_row(r) for r in rows]

    def get_inbox_tasks_count(self) -> int:
        return self.db_manager.get_inbox_tasks_count()

    def get_today_tasks(self, target_date: Optional[date] = None) -> List[Task]:
        t_date = target_date or get_current_datetime().date()
        today_str = t_date.strftime("%Y-%m-%d")
        all_rows = self.db_manager.get_all_tasks()

        today_tasks = []
        for r in all_rows:
            t = Task.from_row(r)
            if t.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
                continue

            p_date = t.planned_date
            d_date = t.due_date
            act_s = t.actual_start_date
            act_e = t.actual_end_date or act_s

            is_relevant = (p_date == today_str)
            if not is_relevant and d_date == today_str:
                is_relevant = True

            if not is_relevant and p_date and d_date:
                try:
                    pd = datetime.strptime(p_date, "%Y-%m-%d").date()
                    dd = datetime.strptime(d_date, "%Y-%m-%d").date()
                    if min(pd, dd) <= t_date <= max(pd, dd):
                        is_relevant = True
                except Exception:
                    pass

            if not is_relevant and t.status == TaskStatus.IN_PROGRESS:
                is_relevant = True
            elif not is_relevant and act_s:
                if act_e:
                    is_relevant = (act_s <= today_str <= act_e)
                else:
                    is_relevant = (act_s == today_str)

            if not is_relevant and d_date and d_date < today_str:
                is_relevant = True

            if is_relevant:
                today_tasks.append(t)

        return today_tasks

    def get_upcoming_tasks(self, end_date: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Task]:
        today_str = get_current_datetime().date().strftime("%Y-%m-%d")
        rows = self.db_manager.get_upcoming_tasks_range(today_str, end_date=end_date, limit=limit, offset=offset)
        return [Task.from_row(r) for r in rows]

    def get_upcoming_tasks_count(self, end_date: Optional[str] = None) -> int:
        today_str = get_current_datetime().date().strftime("%Y-%m-%d")
        return self.db_manager.get_upcoming_tasks_count(today_str, end_date=end_date)

    def get_completed_tasks(self, limit: int = 100, offset: int = 0) -> List[Task]:
        rows = self.db_manager.get_completed_tasks(limit=limit, offset=offset)
        return [Task.from_row(r) for r in rows]

    def get_completed_tasks_count(self) -> int:
        return self.db_manager.get_completed_tasks_count()

    def get_project_tasks(self, project_id: int) -> List[Task]:
        rows = self.db_manager.get_tasks_by_project(project_id)
        return [Task.from_row(r) for r in rows]

    def get_all_tasks(self) -> List[Task]:
        rows = self.db_manager.get_all_tasks()
        return [Task.from_row(r) for r in rows]

    def search_tasks(self, query: str) -> List[Task]:
        rows = self.db_manager.search_tasks(query)
        return [Task.from_row(r) for r in rows]

    # Project management methods
    def get_all_projects(self) -> List[Project]:
        rows = self.db_manager.get_all_projects()
        return [Project.from_row(r) for r in rows]

    def get_project(self, project_id: int) -> Optional[Project]:
        row = self.db_manager.get_project(project_id)
        return Project.from_row(row) if row else None

    def add_project(self, project: Project) -> int:
        proj_id = self.db_manager.insert_project(project.to_dict())
        _GLOBAL_EVENT_BUS.projects_changed.emit()
        return proj_id

    def update_project(self, project: Project) -> bool:
        if project.id is None:
            return False

        success = self.db_manager.update_project(
            project.to_dict(),
            project.id,
        )
        if success:
            _GLOBAL_EVENT_BUS.projects_changed.emit()
        return success
