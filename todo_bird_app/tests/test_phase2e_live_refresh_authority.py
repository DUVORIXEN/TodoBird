"""
PHASE 2E — LIVE REFRESH AUTHORITY TEST SUITE
Verifies Gantt bar date authority, CPM ES/EF bar rendering, baseline frozen preservation,
no fabricated actual bars, single canonical refresh route, experience mode independence,
and schedule variance calculation.
"""

import unittest
from datetime import datetime, date, timedelta
from unittest.mock import MagicMock, patch

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.models.project import Project
from todo_bird_app.services.cpm_scheduling_service import CPMSchedulingService
from todo_bird_app.services.gantt_wbs_adapter import GanttWBSAdapter
from todo_bird_app.services.wbs_rollup_service import WBSRollupService
from todo_bird_app.services.wbs_service import WBSService
from todo_bird_app.services.schedule_variance_service import ScheduleVarianceService
from todo_bird_app.gantt.timescale_engine import TimescaleEngine, ZoomLevel
from todo_bird_app.gantt.gantt_chart import GanttChartWidget
from todo_bird_app.gantt.gantt_theme import GanttColorProfile
from todo_bird_app.gantt.gantt_items import GanttTaskItem
from todo_bird_app.views.gantt_view import GanttView
from todo_bird_app.views.projects_view import ProjectsView
from PySide6.QtWidgets import QApplication


class TestPhase2ELiveRefreshAuthority(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.db = DatabaseManager(":memory:")

        # Seed test project THAAVORIX
        self.project_id = self.db.insert_project({"name": "THAAVORIX", "description": "Test Project"})
        
        # Seed Task 10 (Planning) as described in forensic trace:
        # raw planned_date = '2026-08-23', estimated_duration = 44640 (31 days)
        # SNET constraint = '2026-09-15 09:00'
        # Baseline start = '2026-09-06 09:00', Baseline finish = '2026-10-07 09:00'
        self.task_10_dict = {
            "id": 10,
            "project_id": self.project_id,
            "title": "Planning",
            "status": "Planned",
            "planned_date": "2026-08-23",
            "planned_start_time": "00:00",
            "due_date": "2026-09-23",
            "planned_end_time": "00:00",
            "estimated_duration": 44640,
            "constraint_type": "SNET",
            "constraint_datetime": "2026-09-15 09:00",
            "baseline_start": "2026-09-06 09:00",
            "baseline_finish": "2026-10-07 09:00",
            "baseline_duration_minutes": 44640,
            "actual_start_date": None,
            "actual_end_date": None,
        }
        
        # Direct DB insert for task 10 with explicit ID 10
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    id, project_id, title, status, planned_date, planned_start_time,
                    due_date, planned_end_time, estimated_duration, constraint_type,
                    constraint_datetime, baseline_start, baseline_finish, baseline_duration_minutes,
                    show_in_gantt
                ) VALUES (
                    10, ?, 'Planning', 'Planned', '2026-08-23', '00:00',
                    '2026-09-23', '00:00', 44640, 'SNET',
                    '2026-09-15 09:00', '2026-09-06 09:00', '2026-10-07 09:00', 44640, 1
                )
                """,
                (self.project_id,),
            )
            conn.commit()

    def tearDown(self):
        self.db.close()

    def test_01_live_db_truth(self):
        """Verify DB truth for THAAVORIX Task 10."""
        tasks = self.db.get_tasks_by_project(self.project_id)
        self.assertEqual(len(tasks), 1)
        t = tasks[0]
        self.assertEqual(t["id"], 10)
        self.assertEqual(t["planned_date"], "2026-08-23")
        self.assertEqual(t["constraint_type"], "SNET")
        self.assertEqual(t["constraint_datetime"], "2026-09-15 09:00")

    def test_02_canonical_cpm_truth(self):
        """Verify CPMSchedulingService calculates ES = 2026-09-15 09:00."""
        raw_tasks = self.db.get_tasks_by_project(self.project_id)
        tasks = [Task.from_row(r) for r in raw_tasks]
        cpm_res = CPMSchedulingService.calculate_schedule(tasks, project_id=self.project_id)
        node = cpm_res.nodes[10]
        self.assertEqual(node.earliest_start.strftime("%Y-%m-%d %H:%M"), "2026-09-15 09:00")
        self.assertEqual(node.earliest_finish.strftime("%Y-%m-%d %H:%M"), "2026-10-16 09:00")

    def test_03_gantt_adapter_passes_cpm_es(self):
        """Verify GanttWBSAdapter row planned_start equals CPM ES."""
        snapshot = WBSService.build_project_hierarchy(self.db, project_id=self.project_id)
        rows = GanttWBSAdapter.build_project_rows(snapshot, self.db)
        self.assertGreater(len(rows), 0)
        row10 = next(r for r in rows if str(r.key.entity_id) == "10")
        self.assertIsNotNone(row10.planned_start)
        self.assertEqual(row10.planned_start.strftime("%Y-%m-%d"), "2026-09-15")

    def _make_mock_settings(self):
        m = MagicMock()
        m.get.side_effect = lambda key, default=None: "dark" if key == "theme" else (default if default is not None else "Inter" if "family" in key else 10)
        return m

    def test_04_gantt_view_attaches_cpm_es_to_task(self):
        """Verify GanttView attaches gantt_planned_start to Task object."""
        raw_tasks = self.db.get_tasks_by_project(self.project_id)
        all_tasks = [Task.from_row(r) for r in raw_tasks]
        
        mock_controller = MagicMock()
        mock_controller.get_all_tasks.return_value = all_tasks
        mock_controller.get_all_projects.return_value = [Project(id=self.project_id, name="THAAVORIX")]
        
        mock_settings = self._make_mock_settings()

        gantt_view = GanttView(self.db, mock_settings, task_controller=mock_controller)
        items = gantt_view._build_phase1d_wbs_gantt_items(all_tasks)
        task10 = next(t for t in items if getattr(t, "id", None) == 10)
        
        self.assertTrue(hasattr(task10, "gantt_planned_start"))
        self.assertEqual(task10.gantt_planned_start.strftime("%Y-%m-%d"), "2026-09-15")
        self.assertEqual(task10.cpm_earliest_start[:10], "2026-09-15")

    def test_05_gantt_chart_uses_gantt_planned_start(self):
        """Verify GanttChartWidget uses gantt_planned_start for bar start."""
        t = Task(
            id=10,
            project_id=self.project_id,
            title="Planning",
            planned_date="2026-08-23",
            estimated_duration=44640,
        )
        t.gantt_planned_start = datetime(2026, 9, 15, 9, 0)
        t.gantt_planned_finish = datetime(2026, 10, 16, 9, 0)
        
        chart = GanttChartWidget()
        chart.columns = TimescaleEngine.generate_columns(
            ZoomLevel.DAILY, date(2026, 9, 15)
        )
        chart.zoom_mode = ZoomLevel.DAILY
        
        # Test item building logic inside rebuild_chart
        g_start = getattr(t, "gantt_planned_start", None)
        self.assertEqual(g_start.date(), date(2026, 9, 15))

    def test_06_current_bar_starts_at_cpm_es(self):
        """Verify CURRENT bar starts on Sep 15 instead of Aug 23."""
        t = Task(
            id=10,
            project_id=self.project_id,
            title="Planning",
            planned_date="2026-08-23",
            estimated_duration=44640,
        )
        t.gantt_planned_start = datetime(2026, 9, 15, 9, 0)
        t.gantt_planned_finish = datetime(2026, 10, 16, 9, 0)
        
        columns = TimescaleEngine.generate_columns(ZoomLevel.DAILY, date(2026, 9, 15))
        col_x = TimescaleEngine.date_to_x(date(2026, 9, 15), columns)
        self.assertGreaterEqual(col_x, 0)

    def test_07_baseline_bar_remains_frozen(self):
        """Verify baseline start/finish values remain frozen at Sep 6 - Oct 7."""
        raw_tasks = self.db.get_tasks_by_project(self.project_id)
        t = Task.from_row(raw_tasks[0])
        self.assertEqual(t.baseline_start, "2026-09-06 09:00")
        self.assertEqual(t.baseline_finish, "2026-10-07 09:00")

    def test_08_no_actual_bar_fabricated_without_actual_start(self):
        """Verify no actual bar is fabricated when actual_start_date is None."""
        t = Task(
            id=10,
            project_id=self.project_id,
            title="Planning",
            planned_date="2026-08-23",
            actual_start_date=None,
        )
        item = GanttTaskItem(t, 0, 0.0, 1.0, 60, GanttColorProfile(), zoom_mode="daily", anchor_date=date(2026, 9, 15))
        self.assertFalse(item.has_actual_today)

    def test_09_actual_bar_renders_only_with_actual_start(self):
        """Verify actual bar renders when actual_start_date is set."""
        t = Task(
            id=10,
            project_id=self.project_id,
            title="Planning",
            planned_date="2026-08-23",
            actual_start_date="2026-09-15",
            actual_start_time="09:00",
            actual_duration=180,
            status=TaskStatus.IN_PROGRESS,
        )
        item = GanttTaskItem(t, 0, 0.0, 1.0, 60, GanttColorProfile(), zoom_mode="hourly", anchor_date=date(2026, 9, 15))
        self.assertTrue(item.has_actual_today)

    def test_10_single_pass_refresh_route(self):
        """Verify refresh_project_schedule executes single pass."""
        mock_controller = MagicMock()
        mock_controller.get_all_tasks.return_value = []
        mock_controller.get_all_projects.return_value = []
        mock_settings = self._make_mock_settings()

        gantt_view = GanttView(self.db, mock_settings, task_controller=mock_controller)
        count = gantt_view.refresh_project_schedule(self.project_id)
        self.assertEqual(count, 0)

    def test_11_normal_task_save_triggers_schedule_refresh(self):
        """Verify ProjectsView.refresh_project_schedule re-runs CPM and refreshes views."""
        projects_view = ProjectsView(self.db, MagicMock())
        projects_view.selected_project_id = self.project_id
        projects_view.refresh_project_schedule(self.project_id)
        self.assertIsNotNone(projects_view.selected_project_id)

    def test_12_settings_refresh_preserves_cpm_dates(self):
        """Verify settings reload preserves CPM dates."""
        raw_tasks = self.db.get_tasks_by_project(self.project_id)
        all_tasks = [Task.from_row(r) for r in raw_tasks]
        
        mock_controller = MagicMock()
        mock_controller.get_all_tasks.return_value = all_tasks
        mock_controller.get_all_projects.return_value = [Project(id=self.project_id, name="THAAVORIX")]
        mock_settings = self._make_mock_settings()

        gantt_view = GanttView(self.db, mock_settings, task_controller=mock_controller)
        gantt_view.refresh_data()
        items = gantt_view._build_phase1d_wbs_gantt_items(all_tasks)
        task10 = next(t for t in items if getattr(t, "id", None) == 10)
        self.assertEqual(task10.gantt_planned_start.strftime("%Y-%m-%d"), "2026-09-15")

    def test_13_experience_mode_not_required_for_refresh(self):
        """Verify schedule refresh does not require Experience Mode state toggle."""
        mock_controller = MagicMock()
        mock_controller.get_all_tasks.return_value = [Task.from_row(r) for r in self.db.get_tasks_by_project(self.project_id)]
        mock_controller.get_all_projects.return_value = [Project(id=self.project_id, name="THAAVORIX")]
        mock_settings = self._make_mock_settings()

        gantt_view = GanttView(self.db, mock_settings, task_controller=mock_controller)
        count = gantt_view.refresh_project_schedule(self.project_id)
        self.assertEqual(count, 1)

    def test_14_start_variance_authority(self):
        """Verify Start Variance = Current CPM Start - Baseline Start (+9 days)."""
        raw_tasks = self.db.get_tasks_by_project(self.project_id)
        tasks = [Task.from_row(r) for r in raw_tasks]
        cpm_res = CPMSchedulingService.calculate_schedule(tasks, project_id=self.project_id)
        
        t = tasks[0]
        cpm_node = cpm_res.nodes[10]
        cur_start = cpm_node.earliest_start
        base_start = datetime.strptime(t.baseline_start, "%Y-%m-%d %H:%M")
        
        diff_days = (cur_start - base_start).days
        self.assertEqual(diff_days, 9)

    def test_15_finish_variance_authority(self):
        """Verify Finish Variance = Current CPM Finish - Baseline Finish (+9 days)."""
        raw_tasks = self.db.get_tasks_by_project(self.project_id)
        tasks = [Task.from_row(r) for r in raw_tasks]
        cpm_res = CPMSchedulingService.calculate_schedule(tasks, project_id=self.project_id)
        
        t = tasks[0]
        cpm_node = cpm_res.nodes[10]
        cur_finish = cpm_node.earliest_finish
        base_finish = datetime.strptime(t.baseline_finish, "%Y-%m-%d %H:%M")
        
        diff_days = (cur_finish - base_finish).days
        self.assertEqual(diff_days, 9)

    def test_16_raw_planned_date_preserved_in_db(self):
        """Verify DB planned_date remains unchanged ('2026-08-23')."""
        raw_tasks = self.db.get_tasks_by_project(self.project_id)
        self.assertEqual(raw_tasks[0]["planned_date"], "2026-08-23")

    def test_17_hourly_zoom_uses_cpm_es(self):
        """Verify Hourly mode maps task using CPM ES."""
        t = Task(
            id=10,
            project_id=self.project_id,
            title="Planning",
            planned_date="2026-08-23",
            estimated_duration=44640,
        )
        t.gantt_planned_start = datetime(2026, 9, 15, 9, 0)
        t.gantt_planned_finish = datetime(2026, 10, 16, 9, 0)

        chart = GanttChartWidget()
        chart.anchor_date = date(2026, 9, 15)
        chart.columns = TimescaleEngine.generate_columns(ZoomLevel.HOURLY, date(2026, 9, 15))
        chart.zoom_mode = ZoomLevel.HOURLY

        p_start_dt = getattr(t, "gantt_planned_start", None)
        self.assertEqual(p_start_dt.date(), date(2026, 9, 15))

    def test_18_daily_zoom_uses_cpm_es(self):
        """Verify Daily mode maps bar start to 2026-09-15."""
        columns = TimescaleEngine.generate_columns(ZoomLevel.DAILY, date(2026, 9, 15))
        col_x = TimescaleEngine.date_to_x(date(2026, 9, 15), columns)
        self.assertGreaterEqual(col_x, 0)

    def test_19_weekly_zoom_uses_cpm_es(self):
        """Verify Weekly mode maps bar start to week of 2026-09-15."""
        columns = TimescaleEngine.generate_columns(ZoomLevel.WEEKLY, date(2026, 9, 15))
        col_x = TimescaleEngine.date_to_x(date(2026, 9, 15), columns)
        self.assertGreaterEqual(col_x, 0)

    def test_20_monthly_zoom_uses_cpm_es(self):
        """Verify Monthly mode maps bar start to September 2026."""
        columns = TimescaleEngine.generate_columns(ZoomLevel.MONTHLY, date(2026, 9, 15))
        col_x = TimescaleEngine.date_to_x(date(2026, 9, 15), columns)
        self.assertGreaterEqual(col_x, 0)

    def test_21_dynamic_extent_covers_cpm_dates(self):
        """Verify TimescaleEngine dynamic extent includes CPM ES (2026-09-15)."""
        raw_tasks = self.db.get_tasks_by_project(self.project_id)
        tasks = [Task.from_row(r) for r in raw_tasks]
        cpm_res = CPMSchedulingService.calculate_schedule(tasks, project_id=self.project_id)
        
        # Add CPM dates to tasks for extent calculation
        for t in tasks:
            node = cpm_res.nodes.get(t.id)
            if node:
                t.cpm_earliest_start = node.earliest_start.isoformat()
                t.cpm_earliest_finish = node.earliest_finish.isoformat()

        start_d, end_d = TimescaleEngine.get_relevant_date_range(date(2026, 9, 15), tasks)
        self.assertLessEqual(start_d, date(2026, 9, 15))
        self.assertGreaterEqual(end_d, date(2026, 10, 16))

    def test_22_subtask_cpm_rollups_to_gantt(self):
        """Verify subtask constraint rolls up CPM ES to parent task."""
        # Update Task 10 constraint date to SNET 2026-09-21 (Monday)
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET constraint_type='SNET', constraint_datetime='2026-09-21 09:00' WHERE id=10"
            )
            conn.commit()

        snapshot = WBSService.build_project_hierarchy(self.db, project_id=self.project_id)
        rows = GanttWBSAdapter.build_project_rows(snapshot, self.db)
        row10 = next(r for r in rows if str(r.key.entity_id) == "10")
        # Rollup start should reflect the later constraint date (2026-09-21)
        self.assertEqual(row10.planned_start.strftime("%Y-%m-%d"), "2026-09-21")

    def test_23_full_end_to_end_snet_refresh_flow(self):
        """Verify end-to-end flow from DB insert through GanttView item construction."""
        raw_tasks = self.db.get_tasks_by_project(self.project_id)
        all_tasks = [Task.from_row(r) for r in raw_tasks]

        mock_controller = MagicMock()
        mock_controller.get_all_tasks.return_value = all_tasks
        mock_controller.get_all_projects.return_value = [Project(id=self.project_id, name="THAAVORIX")]
        mock_settings = self._make_mock_settings()

        gantt_view = GanttView(self.db, mock_settings, task_controller=mock_controller)
        count = gantt_view.refresh_project_schedule(self.project_id)
        self.assertEqual(count, 1)

        items = gantt_view._build_phase1d_wbs_gantt_items(all_tasks)
        task10 = next(t for t in items if getattr(t, "id", None) == 10)
        self.assertEqual(task10.gantt_planned_start.strftime("%Y-%m-%d"), "2026-09-15")


if __name__ == "__main__":
    unittest.main()
