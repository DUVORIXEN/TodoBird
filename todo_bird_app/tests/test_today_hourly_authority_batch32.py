import os
import tempfile
from datetime import date, datetime, timedelta
import pytest

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QDate, QTime

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.views.calendar_view import CalendarView
from todo_bird_app.views.focus_view import FocusView
from todo_bird_app.views.gantt_view import GanttView
from todo_bird_app.gantt.gantt_chart import GanttChartWidget, ZoomLevel

_APP = QApplication.instance() or QApplication([])


def _temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(path)
    return db, path


def test_today_h01_planned_today_and_timed_renders_hourly_bar():
    """TODAY-H01: Task with planned_date today and planned_start_time renders on Hourly canvas."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        today_str = date(2026, 8, 15).strftime("%Y-%m-%d")

        t = Task(
            title="Timed Milestone",
            planned_date=today_str,
            planned_start_time="09:00",
            planned_end_time="10:30",
            estimated_duration=90,
            show_in_gantt=True,
        )
        tid = tc.add_task(t)

        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()

        assert chart._current_empty_message is None
        assert tid in chart._rendered_task_items
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_today_h02_planned_today_untimed_does_not_falsely_call_zero_tasks():
    """TODAY-H02: Task with planned_date today but untimed renders default slot."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        today_str = date(2026, 8, 15).strftime("%Y-%m-%d")

        t = Task(
            title="Untimed Task",
            planned_date=today_str,
            planned_start_time=None,
            show_in_gantt=True,
        )
        tid = tc.add_task(t)

        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()

        assert chart._current_empty_message is not None
        assert "1 task is active today, but none have a timed schedule" in chart._current_empty_message
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_today_h03_and_h04_multi_day_spanning_task_clarity():
    """TODAY-H03 & TODAY-H04: Multi-day task spanning today is reported as active/spanning without fabricating arbitrary time."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)

        # Task planned Aug 13 to Aug 17 (spans Aug 15)
        t = Task(
            title="Cross-Week Project",
            planned_date="2026-08-13",
            due_date="2026-08-17",
            planned_start_time="09:00",
            planned_end_time="10:00",
            show_in_gantt=True,
        )
        tid = tc.add_task(t)

        # 1. Calendar View on Aug 15 includes the spanning task
        cal_view = CalendarView(db, settings)
        cal_tasks = cal_view._get_tasks_for_date(date(2026, 8, 15))
        assert any(x.id == tid for x in cal_tasks)

        # 2. Hourly Gantt on Aug 15 reports active task without fabricating planned bar on Aug 15
        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()

        assert chart._current_empty_message is not None
        assert "1 task is active today, but none have a timed schedule" in chart._current_empty_message

        # 3. Hourly Gantt on Aug 25 (completely outside span) shows empty message with nearest date
        chart.anchor_date = date(2026, 8, 25)
        chart.rebuild_chart()
        assert chart._current_empty_message is not None
        assert "No tasks scheduled for 25 Aug 2026" in chart._current_empty_message
        assert "17 Aug" in chart._current_empty_message or "13 Aug" in chart._current_empty_message
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_today_h06_show_in_gantt_false_exclusion():
    """TODAY-H06: Task with show_in_gantt=False is excluded from Gantt for user preference."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        today_str = date(2026, 8, 15).strftime("%Y-%m-%d")

        t = Task(
            title="Hidden Gantt Task",
            planned_date=today_str,
            show_in_gantt=False,
        )
        tid = tc.add_task(t)

        gantt_view = GanttView(db, settings)
        gantt_view.gantt_chart.set_zoom_mode("hourly")
        gantt_view.gantt_chart.anchor_date = date(2026, 8, 15)
        gantt_view.refresh_data()

        assert tid not in gantt_view.gantt_chart._rendered_task_items
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_today_h07_and_h08_event_bus_refreshes_and_preserves_anchor_date():
    """TODAY-H07 & TODAY-H08: Global event bus notifies Gantt and preserves selected anchor date."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        target_date = date(2026, 8, 15)

        gantt_view = GanttView(db, settings)
        gantt_view.gantt_chart.set_zoom_mode("hourly")
        gantt_view.gantt_chart.anchor_date = target_date

        # Add new task through controller
        t = Task(
            title="Live Event Task",
            planned_date="2026-08-15",
            planned_start_time="14:00",
            show_in_gantt=True,
        )
        tid = tc.add_task(t)

        # Gantt anchor date preserved and task rendered
        assert gantt_view.gantt_chart.anchor_date == target_date
        assert tid in gantt_view.gantt_chart._rendered_task_items
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_today_h09_and_h10_planned_and_actual_bars_render():
    """TODAY-H09 & TODAY-H10: Task on anchor date with planned and actual renders both bars."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        today_str = date(2026, 8, 15).strftime("%Y-%m-%d")

        t = Task(
            title="Dual Bar Task",
            planned_date=today_str,
            planned_start_time="08:00",
            actual_start_date=today_str,
            actual_start_time="06:30",
            actual_duration=45,
            status=TaskStatus.IN_PROGRESS,
            show_in_gantt=True,
        )
        tid = tc.add_task(t)

        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()

        item = chart._rendered_task_items.get(tid)
        assert item is not None
        assert item.task.actual_start_time == "06:30"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_task_dialog_actual_execution_controls():
    """Verify TaskDialog allows viewing, editing, and saving Actual Start/End times."""
    from todo_bird_app.widgets.task_dialog import TaskDialog

    t = Task(
        title="Test Actual Dialog",
        planned_start_time="09:00",
        planned_end_time="10:00",
        actual_start_time="08:15",
        actual_end_time="09:00",
        actual_duration=45,
    )
    dialog = TaskDialog(projects=[], task=t)
    assert dialog.actual_enabled_check.isChecked()
    assert dialog.actual_start_edit.time().toString("HH:mm") == "08:15"
    assert dialog.actual_end_edit.time().toString("HH:mm") == "09:00"
    assert dialog.actual_duration_spin.value() == 45

    # Modify time and date
    dialog.actual_start_date_edit.setDate(QDate(2026, 8, 16))
    dialog.actual_end_date_edit.setDate(QDate(2026, 8, 16))
    dialog.actual_start_edit.setTime(QTime(7, 30))
    dialog.title_input.setText("Updated Task Title")
    dialog.on_save()
    saved_task = dialog.get_task()
    assert saved_task.actual_start_date == "2026-08-16"
    assert saved_task.actual_end_date == "2026-08-16"
    assert saved_task.actual_duration == 45  # Decoupled actual effort remains spinbox value
    assert "90" in dialog.actual_elapsed_label.text()  # Actual elapsed span reflects clock delta (07:30 to 09:00 = 90m)

    # Uncheck tracked
    dialog.actual_enabled_check.setChecked(False)
    dialog.on_save()
    cleared_task = dialog.get_task()
    assert cleared_task.actual_start_date is None
    assert cleared_task.actual_start_time is None
    assert cleared_task.actual_duration == 45  # Batch 3.9: Actual effort is preserved independently


def test_gantt_chart_resize_event_adapts_scene():
    """Verify GanttChartWidget adapts sceneRect to viewport dimensions and timescale bounds."""
    chart = GanttChartWidget()
    try:
        chart.rebuild_chart()
        scene_rect = chart.scene.sceneRect()
        assert scene_rect.width() >= 800
        assert scene_rect.height() >= 600
    finally:
        chart.timer.stop()
        chart.deleteLater()
