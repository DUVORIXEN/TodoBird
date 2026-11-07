"""
TODO BIRD — 1-CLICK SAMPLE EXECUTIVE PROJECT SERVICE
Provides a realistic, self-contained demo workspace with multi-level WBS subtasks,
Planned vs. Actual dates, dependencies, and pins so first-time users immediately
see the Dashboard charts, WBS hierarchy rollups, and Gantt timeline in action.
Can be loaded or cleanly removed in a single click without affecting user data.
"""

import json
import logging
from datetime import date, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class SampleProjectService:
    SAMPLE_PROJECT_NAME = "🚀 [Sample] Executive Product Launch"

    @classmethod
    def get_sample_project_id(cls, db_manager) -> Optional[int]:
        if not db_manager:
            return None
        try:
            for proj in db_manager.get_all_projects():
                if proj.get("name") == cls.SAMPLE_PROJECT_NAME:
                    return int(proj["id"])
        except Exception as e:
            logger.error(f"Error checking sample project: {e}")
        return None

    @classmethod
    def has_sample_project(cls, db_manager) -> bool:
        return cls.get_sample_project_id(db_manager) is not None

    @classmethod
    def load_sample_project(cls, db_manager) -> Optional[int]:
        """
        Creates the Sample Executive Project with 4 parent tasks, nested WBS subtasks,
        Plan vs. Actual execution dates, and dependencies. Returns project_id.
        """
        if not db_manager:
            return None

        existing_id = cls.get_sample_project_id(db_manager)
        if existing_id is not None:
            return existing_id

        today = date.today()
        d_str = lambda offset: (today + timedelta(days=offset)).isoformat()

        project_id = db_manager.insert_project({
            "name": cls.SAMPLE_PROJECT_NAME,
            "color": "#E95420",
            "icon": "folder",
            "description": "Interactive demo project showcasing WBS rollups, Critical Path dependencies, and Plan vs. Actual Gantt execution.",
            "working_weekdays": [0, 1, 2, 3, 4],
        })

        # Task 1: Completed Phase (Plan vs Actual on time)
        t1_id = db_manager.insert_task({
            "title": "Phase 1: Executive Strategy & Architecture Blueprint",
            "project_id": project_id,
            "priority": "High",
            "status": "Completed",
            "planned_date": d_str(-5),
            "due_date": d_str(-3),
            "actual_start_date": d_str(-5),
            "actual_end_date": d_str(-3),
            "actual_start_time": "09:00",
            "actual_end_time": "17:00",
            "estimated_duration": 480,
            "planned_effort_minutes": 480,
            "actual_duration": 450,
            "progress": 100,
            "show_in_gantt": 1,
            "is_pinned": 1,
            "pin_color": "#10B981",
            "description": "Completed strategy phase demonstrating 100% progress and Plan vs. Actual parity.",
        })
        db_manager.insert_subtask(
            task_id=t1_id,
            title="1.1 Define Q4 OKRs & KPIs",
            is_completed=True,
            position=0,
            planned_date=d_str(-5),
            due_date=d_str(-4),
            estimated_duration=240,
            progress=100,
            show_in_gantt=True,
        )
        db_manager.insert_subtask(
            task_id=t1_id,
            title="1.2 Finalize Technical System Design",
            is_completed=True,
            position=1,
            planned_date=d_str(-4),
            due_date=d_str(-3),
            estimated_duration=240,
            progress=100,
            show_in_gantt=True,
        )

        # Task 2: Active Today Phase (In Progress with nested WBS subtasks)
        t2_id = db_manager.insert_task({
            "title": "Phase 2: Core Platform Engineering & WBS Execution",
            "project_id": project_id,
            "priority": "High",
            "status": "In Progress",
            "planned_date": d_str(-2),
            "due_date": d_str(2),
            "actual_start_date": d_str(-2),
            "actual_start_time": "09:30",
            "estimated_duration": 960,
            "planned_effort_minutes": 960,
            "actual_duration": 540,
            "progress": 60,
            "dependencies": json.dumps([t1_id]),
            "show_in_gantt": 1,
            "is_pinned": 1,
            "pin_color": "#E95420",
            "description": "Active engineering sprint linked to Phase 1. Expand in WBS view to inspect subtask rollups.",
        })
        st2_1 = db_manager.insert_subtask(
            task_id=t2_id,
            title="2.1 Build Offline SQLite & CPM Scheduling Engine",
            is_completed=True,
            position=0,
            planned_date=d_str(-2),
            due_date=d_str(0),
            estimated_duration=480,
            progress=100,
            show_in_gantt=True,
        )
        db_manager.insert_subtask(
            task_id=t2_id,
            title="2.1.1 Verify Working Calendar & Dependency Math",
            is_completed=True,
            position=0,
            parent_subtask_id=st2_1,
            planned_date=d_str(-1),
            due_date=d_str(0),
            estimated_duration=240,
            progress=100,
            show_in_gantt=True,
        )
        db_manager.insert_subtask(
            task_id=t2_id,
            title="2.2 Polish Interactive Gantt & World Clock UI",
            is_completed=False,
            position=1,
            planned_date=d_str(0),
            due_date=d_str(2),
            estimated_duration=480,
            progress=40,
            show_in_gantt=True,
        )

        # Task 3: Upcoming Store Packaging & QA
        t3_id = db_manager.insert_task({
            "title": "Phase 3: Microsoft Store (MSIX) & Ubuntu Snap Certification",
            "project_id": project_id,
            "priority": "High",
            "status": "Today",
            "planned_date": d_str(3),
            "due_date": d_str(6),
            "estimated_duration": 720,
            "planned_effort_minutes": 720,
            "progress": 0,
            "dependencies": json.dumps([t2_id]),
            "show_in_gantt": 1,
            "description": "Cross-platform store packaging and automated test verification.",
        })
        db_manager.insert_subtask(
            task_id=t3_id,
            title="3.1 Build Signed Windows Store MSIX & Inno Setup",
            is_completed=False,
            position=0,
            planned_date=d_str(3),
            due_date=d_str(4),
            estimated_duration=360,
            progress=0,
            show_in_gantt=True,
        )
        db_manager.insert_subtask(
            task_id=t3_id,
            title="3.2 Publish Ubuntu Software Snap Revision to Stable",
            is_completed=False,
            position=1,
            planned_date=d_str(5),
            due_date=d_str(6),
            estimated_duration=360,
            progress=0,
            show_in_gantt=True,
        )

        # Task 4: Launch Milestone
        db_manager.insert_task({
            "title": "Phase 4: Global Public Release & Community Check-In",
            "project_id": project_id,
            "priority": "High",
            "status": "Inbox",
            "planned_date": d_str(7),
            "due_date": d_str(8),
            "estimated_duration": 240,
            "planned_effort_minutes": 240,
            "progress": 0,
            "dependencies": json.dumps([t3_id]),
            "show_in_gantt": 1,
            "is_pinned": 1,
            "pin_color": "#3B82F6",
            "description": "Global release milestone and collecting user feedback ratings.",
        })

        cls._emit_tasks_changed()
        logger.info(f"Loaded sample executive project (project_id={project_id})")
        return project_id

    @classmethod
    def remove_sample_project(cls, db_manager) -> bool:
        """Cleanly removes only the sample project and its tasks/subtasks."""
        pid = cls.get_sample_project_id(db_manager)
        if pid is None:
            return False

        try:
            with db_manager.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM tasks WHERE project_id = ?;", (pid,))
                task_ids = [int(r[0]) for r in cursor.fetchall()]
                for tid in task_ids:
                    cursor.execute("DELETE FROM subtasks WHERE task_id = ?;", (tid,))
                cursor.execute("DELETE FROM tasks WHERE project_id = ?;", (pid,))
                cursor.execute("DELETE FROM projects WHERE id = ?;", (pid,))
                conn.commit()
            cls._emit_tasks_changed()
            logger.info(f"Removed sample executive project (project_id={pid})")
            return True
        except Exception as e:
            logger.error(f"Failed to remove sample project: {e}")
            return False

    @staticmethod
    def _emit_tasks_changed():
        try:
            from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
            _GLOBAL_EVENT_BUS.tasks_changed.emit()
        except Exception:
            pass
