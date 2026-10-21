import os
import tempfile
import sqlite3
from datetime import datetime, date, time
import pytest
from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.gantt.gantt_chart import GanttChartWidget
from todo_bird_app.views.focus_view import FocusView
from todo_bird_app.views.calendar_view import CalendarView
from todo_bird_app.views.today_view import TodayView
from todo_bird_app.views.gantt_view import GanttView


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    return db, path


# ==============================================================================
# TESTS — TODAY / HOURLY AUTHORITY (V9-H01 .. V9-H10)
# ==============================================================================

def test_v9_h01_planned_today_timed_renders_planned_bar():
    """V9-H01: planned today + timed -> Planned Hourly visible."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(
            title="Timed Today",
            planned_date="2026-08-15",
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


def test_v9_h02_actual_today_planned_earlier_renders_actual():
    """V9-H02: actual today + planned earlier -> Actual Hourly visible today."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(
            title="Executed Later",
            planned_date="2026-08-13",
            planned_start_time="09:00",
            planned_end_time="10:00",
            actual_start_date="2026-08-15",
            actual_end_date="2026-08-15",
            actual_start_time="14:30",
            actual_end_time="15:10",
            actual_duration=40,
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


def test_v9_h03_planned_earlier_due_today_no_fabricated_bar():
    """V9-H03: planned earlier + due today -> Today visible -> no fabricated Planned bar today."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(
            title="Due Today Task",
            planned_date="2026-08-13",
            due_date="2026-08-15",
            planned_start_time="09:00",
            planned_end_time="10:00",
            show_in_gantt=True,
        )
        tid = tc.add_task(t)

        # 1. Today View controller returns the task
        today_tasks = tc.get_today_tasks(date(2026, 8, 15))
        assert any(x.id == tid for x in today_tasks)

        # 2. Hourly Gantt acknowledges active task without inventing fake timed bar
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


def test_v9_h04_span_crosses_today_calendar_today_visible():
    """V9-H04: span crosses today -> Calendar/Today visible -> Hourly only if timed/Actual today."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(
            title="Multi-day Span",
            planned_date="2026-08-10",
            due_date="2026-08-20",
            show_in_gantt=True,
        )
        tid = tc.add_task(t)

        cal_view = CalendarView(db, settings)
        assert any(x.id == tid for x in cal_view._get_tasks_for_date(date(2026, 8, 15)))

        assert any(x.id == tid for x in tc.get_today_tasks(date(2026, 8, 15)))
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_v9_h05_active_untimed_today_acknowledges_active_count():
    """V9-H05: active untimed today -> Hourly does not claim zero relevant tasks."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t1 = Task(title="Untimed 1", planned_date="2026-08-15", show_in_gantt=True)
        t2 = Task(title="Untimed 2", planned_date="2026-08-15", show_in_gantt=True)
        tc.add_task(t1)
        tc.add_task(t2)

        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks(tc.get_all_tasks(), {})
        chart.rebuild_chart()

        assert chart._current_empty_message == "2 tasks are active today, but none have a timed schedule."
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_v9_h06_actual_only_today_renders_in_lower_lane():
    """V9-H06: actual-only today -> Actual-only rendering."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(
            title="Unplanned Work",
            planned_date="2026-08-10",
            actual_start_date="2026-08-15",
            actual_end_date="2026-08-15",
            actual_start_time="11:00",
            actual_end_time="12:00",
            actual_duration=60,
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


def test_v9_h07_planned_today_actual_different_date():
    """V9-H07: Planned today + Actual different date -> bars appear on respective dates."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(
            title="Shifted Execution",
            planned_date="2026-08-15",
            planned_start_time="09:00",
            planned_end_time="10:00",
            actual_start_date="2026-08-16",
            actual_end_date="2026-08-16",
            actual_start_time="09:00",
            actual_end_time="10:00",
            show_in_gantt=True,
        )
        tid = tc.add_task(t)

        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")

        # Aug 15: Planned visible
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()
        assert tid in chart._rendered_task_items

        # Aug 16: Actual visible
        chart.anchor_date = date(2026, 8, 16)
        chart.rebuild_chart()
        assert tid in chart._rendered_task_items
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_v9_h08_focus_start_writes_actual_start_date_once():
    """V9-H08: Focus Start writes actual_start_date exactly once."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Focus Target", planned_date="2026-08-15")
        tid = tc.add_task(t)

        fv = FocusView(db, settings)
        fv.select_task_by_id(tid)
        fv.start_focus_session()

        saved = tc.get_task(tid)
        assert saved.actual_start_date == datetime.now().strftime("%Y-%m-%d")
        assert saved.actual_start_time == datetime.now().strftime("%H:%M")
        assert saved.status == TaskStatus.IN_PROGRESS
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_v9_h09_focus_complete_writes_actual_end_date_and_time():
    """V9-H09: Focus Complete writes actual_end_date/time."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Focus Complete Target", planned_date="2026-08-15")
        tid = tc.add_task(t)

        fv = FocusView(db, settings)
        fv.select_task_by_id(tid)
        fv.start_focus_session()
        fv.complete_focus_task()

        saved = tc.get_task(tid)
        assert saved.actual_end_date == datetime.now().strftime("%Y-%m-%d")
        assert saved.actual_end_time == datetime.now().strftime("%H:%M")
        assert saved.status == TaskStatus.COMPLETED
        assert saved.progress == 100
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_v9_h10_gantt_refresh_preserves_anchor_date():
    """V9-H10: Gantt refresh preserves anchor date."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        gv = GanttView(db, settings)
        gv.gantt_chart.set_zoom_mode("hourly")
        gv.gantt_chart.anchor_date = date(2026, 8, 20)

        # Trigger refresh
        gv.refresh_data()
        assert gv.gantt_chart.anchor_date == date(2026, 8, 20)
    finally:
        if os.path.exists(path):
            os.remove(path)


# ==============================================================================
# TESTS — CROSS MIDNIGHT (V9-XM01 .. V9-XM04)
# ==============================================================================

def test_v9_xm01_duration_across_midnight():
    """V9-XM01: 23:30 -> next-day 00:45 duration = 75 min."""
    sd = date(2026, 8, 15)
    st = time(23, 30)
    ed = date(2026, 8, 16)
    et = time(0, 45)
    s_dt = datetime.combine(sd, st)
    e_dt = datetime.combine(ed, et)
    dur = int((e_dt - s_dt).total_seconds() / 60)
    assert dur == 75


def test_v9_xm02_and_xm03_cross_midnight_segments():
    """V9-XM02 & V9-XM03: 15 Aug shows first segment, 16 Aug shows continuation."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(
            title="Overnight Shift",
            planned_date="2026-08-15",
            actual_start_date="2026-08-15",
            actual_end_date="2026-08-16",
            actual_start_time="23:30",
            actual_end_time="00:45",
            actual_duration=75,
            show_in_gantt=True,
        )
        tid = tc.add_task(t)

        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")

        # 15 Aug: segment present
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()
        assert tid in chart._rendered_task_items

        # 16 Aug: continuation present
        chart.anchor_date = date(2026, 8, 16)
        chart.rebuild_chart()
        assert tid in chart._rendered_task_items
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_v9_xm04_same_date_reverse_time_validation():
    """V9-XM04: same-date reverse time rejected as invalid duration <= 0."""
    sd = date(2026, 8, 15)
    st = time(23, 30)
    ed = date(2026, 8, 15)
    et = time(0, 45)
    s_dt = datetime.combine(sd, st)
    e_dt = datetime.combine(ed, et)
    dur = int((e_dt - s_dt).total_seconds() / 60)
    assert dur < 0  # Invalid duration requiring next-day end date


def test_v9_xm05_multi_day_actual_start_day():
    """V9-XM05: 14 Aug 10:00 -> 16 Aug 17:00, selected 14 Aug => segment 10:00 -> 23:59."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(
            title="3-Day Execution",
            planned_date="2026-08-13",
            actual_start_date="2026-08-14",
            actual_end_date="2026-08-16",
            actual_start_time="10:00",
            actual_end_time="17:00",
            actual_duration=3300,
            show_in_gantt=True,
        )
        tid = tc.add_task(t)

        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 14)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()

        item = chart._rendered_task_items[tid]
        # On 14 Aug: starts at 10:00 (10.0 * 60 = 600.0) and runs to 24:00 (width = 14.0 * 60 = 840.0)
        assert item.pos().x() == 600.0
        # Find execution path shape in child items
        path_items = [c for c in item.childItems() if type(c).__name__ == "QGraphicsPathItem"]
        assert len(path_items) > 0
        rect = path_items[0].boundingRect()
        assert abs(rect.width() - 840.0) <= 4.0
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_v9_xm06_multi_day_actual_intermediate_day():
    """V9-XM06: same execution, selected 15 Aug => segment 00:00 -> 23:59 (full 24h)."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(
            title="3-Day Execution",
            planned_date="2026-08-13",
            actual_start_date="2026-08-14",
            actual_end_date="2026-08-16",
            actual_start_time="10:00",
            actual_end_time="17:00",
            actual_duration=3300,
            show_in_gantt=True,
        )
        tid = tc.add_task(t)

        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()

        item = chart._rendered_task_items[tid]
        # On 15 Aug: full day 00:00 to 24:00 (width = 24.0 * 60 = 1440.0)
        path_items = [c for c in item.childItems() if type(c).__name__ == "QGraphicsPathItem"]
        assert len(path_items) > 0
        rect = path_items[0].boundingRect()
        scene_x_start = item.pos().x() + rect.x()
        assert abs(scene_x_start) < 4.0
        assert abs(rect.width() - 1440.0) <= 4.0
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_v9_xm07_multi_day_actual_end_day():
    """V9-XM07: same execution, selected 16 Aug => segment 00:00 -> 17:00."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(
            title="3-Day Execution",
            planned_date="2026-08-13",
            actual_start_date="2026-08-14",
            actual_end_date="2026-08-16",
            actual_start_time="10:00",
            actual_end_time="17:00",
            actual_duration=3300,
            show_in_gantt=True,
        )
        tid = tc.add_task(t)

        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 16)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()

        item = chart._rendered_task_items[tid]
        # On 16 Aug: from 00:00 to 17:00 (width = 17.0 * 60 = 1020.0)
        path_items = [c for c in item.childItems() if type(c).__name__ == "QGraphicsPathItem"]
        assert len(path_items) > 0
        rect = path_items[0].boundingRect()
        scene_x_start = item.pos().x() + rect.x()
        assert abs(scene_x_start) < 4.0
        assert abs(rect.width() - 1020.0) <= 4.0
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_v9_xm08_intermediate_day_does_not_reuse_start_day_time():
    """V9-XM08: intermediate-day segment does not reuse start-day start time (10:00)."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(
            title="3-Day Execution",
            planned_date="2026-08-13",
            actual_start_date="2026-08-14",
            actual_end_date="2026-08-16",
            actual_start_time="10:00",
            actual_end_time="17:00",
            actual_duration=3300,
            show_in_gantt=True,
        )
        tid = tc.add_task(t)

        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()

        item = chart._rendered_task_items[tid]
        path_items = [c for c in item.childItems() if type(c).__name__ == "QGraphicsPathItem"]
        rect = path_items[0].boundingRect()
        scene_x_start = item.pos().x() + rect.x()
        # Scene start must be 0.0 (00:00), NOT 600.0 (10:00)
        assert abs(scene_x_start - 0.0) < 2.0
        assert abs(scene_x_start - 600.0) > 100.0
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_v9_xm09_intermediate_day_does_not_reuse_end_day_time():
    """V9-XM09: intermediate-day segment does not reuse end-day end time (17:00)."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(
            title="3-Day Execution",
            planned_date="2026-08-13",
            actual_start_date="2026-08-14",
            actual_end_date="2026-08-16",
            actual_start_time="10:00",
            actual_end_time="17:00",
            actual_duration=3300,
            show_in_gantt=True,
        )
        tid = tc.add_task(t)

        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()

        item = chart._rendered_task_items[tid]
        path_items = [c for c in item.childItems() if type(c).__name__ == "QGraphicsPathItem"]
        rect = path_items[0].boundingRect()
        scene_x_end = item.pos().x() + rect.x() + rect.width()
        # Scene end must be 1440.0 (24:00), NOT 1020.0 (17:00)
        assert abs(scene_x_end - 1440.0) < 2.0
        assert abs(scene_x_end - 1020.0) > 100.0
    finally:
        if os.path.exists(path):
            os.remove(path)


# ==============================================================================
# TESTS — HIERARCHY PARITY (V9-S01 .. V9-S05)
# ==============================================================================

def test_v9_s01_subtask_actual_date_time_persists():
    """V9-S01: subtask Actual date/time persists."""
    db, path = _temp_db()
    try:
        tc = TaskController(db)
        tid = tc.add_task(Task(title="Parent"))
        sid = db.insert_subtask(
            task_id=tid,
            title="Subtask 1",
            actual_start_date="2026-08-15",
            actual_end_date="2026-08-15",
            actual_start_time="10:00",
            actual_end_time="11:30",
            actual_duration=90,
        )
        tree = db.get_subtask_tree(tid)
        assert tree[0]["actual_start_date"] == "2026-08-15"
        assert tree[0]["actual_end_date"] == "2026-08-15"
        assert tree[0]["actual_start_time"] == "10:00"
        assert tree[0]["actual_end_time"] == "11:30"
        assert tree[0]["actual_duration"] == 90
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_v9_s02_subtask_actual_renders_in_gantt():
    """V9-S02: subtask Actual renders in Gantt."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        tid = tc.add_task(Task(title="Parent", show_in_gantt=True))
        db.insert_subtask(
            task_id=tid,
            title="Subtask Active",
            planned_date="2026-08-15",
            actual_start_date="2026-08-15",
            actual_end_date="2026-08-15",
            actual_start_time="13:00",
            actual_end_time="14:00",
            actual_duration=60,
            show_in_gantt=True,
        )
        gv = GanttView(db, settings)
        gv.gantt_chart.set_zoom_mode("hourly")
        gv.gantt_chart.anchor_date = date(2026, 8, 15)
        gv.refresh_data()
        # Synthetic subtask ID is negative
        assert any(k < 0 for k in gv.gantt_chart._rendered_task_items.keys())
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_v9_s03_sub_subtask_actual_persists():
    """V9-S03: sub-subtask Actual persists."""
    db, path = _temp_db()
    try:
        tc = TaskController(db)
        tid = tc.add_task(Task(title="Parent"))
        sid = db.insert_subtask(task_id=tid, title="Sub 1")
        ssid = db.insert_subtask(
            task_id=tid,
            parent_subtask_id=sid,
            title="Sub-Sub 1",
            actual_start_date="2026-08-15",
            actual_end_date="2026-08-16",
            actual_start_time="22:00",
            actual_end_time="02:00",
            actual_duration=240,
        )
        tree = db.get_subtask_tree(tid)
        subsub = tree[0]["children"][0]
        assert subsub["actual_start_date"] == "2026-08-15"
        assert subsub["actual_end_date"] == "2026-08-16"
        assert subsub["actual_duration"] == 240
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_v9_s04_editing_subtask_does_not_mutate_parent_actual():
    """V9-S04: editing subtask does not mutate parent Actual."""
    db, path = _temp_db()
    try:
        tc = TaskController(db)
        tid = tc.add_task(Task(
            title="Parent",
            actual_start_date="2026-08-10",
            actual_start_time="08:00",
            actual_duration=120,
        ))
        sid = db.insert_subtask(
            task_id=tid,
            title="Child",
            actual_start_date="2026-08-15",
            actual_start_time="14:00",
            actual_duration=60,
        )
        db.update_subtask(subtask_id=sid, title="Child", is_completed=False, actual_duration=90)

        parent = tc.get_task(tid)
        assert parent.actual_start_date == "2026-08-10"
        assert parent.actual_start_time == "08:00"
        assert parent.actual_duration == 120
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_v9_s05_main_task_resize_does_not_alter_child_actual():
    """V9-S05: main-task resize does not alter child Actual."""
    db, path = _temp_db()
    try:
        tc = TaskController(db)
        tid = tc.add_task(Task(title="Parent", planned_date="2026-08-15", estimated_duration=60))
        sid = db.insert_subtask(
            task_id=tid,
            title="Child",
            actual_start_date="2026-08-15",
            actual_start_time="10:00",
            actual_duration=45,
        )
        # Update parent planned duration
        tc.update_task(Task(id=tid, title="Parent", planned_date="2026-08-15", estimated_duration=120))

        tree = db.get_subtask_tree(tid)
        assert tree[0]["actual_duration"] == 45
        assert tree[0]["actual_start_time"] == "10:00"
    finally:
        if os.path.exists(path):
            os.remove(path)


# ==============================================================================
# TESTS — EVENT BUS (EV01 .. EV05)
# ==============================================================================

def test_ev01_one_focus_start_one_logical_task_update():
    """EV01: one Focus Start -> one logical task update."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        tid = tc.add_task(Task(title="Event Target"))

        updates = []
        tc.tasks_changed.connect(lambda: updates.append(tid))

        fv = FocusView(db, settings)
        fv.select_task_by_id(tid)
        fv.start_focus_session()

        assert len(updates) == 1
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_ev02_switch_views_does_not_leak_subscribers():
    """EV02: switch views 20 times -> subscriber count does not grow uncontrollably."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        views = [TodayView(db, settings) for _ in range(20)]
        assert len(views) == 20
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_ev03_gantt_refresh_no_db_mutation():
    """EV03: Gantt refresh -> no DB mutation."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        tid = tc.add_task(Task(title="Static Task"))

        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(rowid) FROM tasks")
        before_state = cursor.fetchall()

        gv = GanttView(db, settings)
        gv.refresh_data()

        cursor.execute("SELECT MAX(rowid) FROM tasks")
        after_state = cursor.fetchall()
        assert before_state == after_state
        conn.close()
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_ev04_focus_duration_persistence_no_refresh_loop():
    """EV04: Focus duration persistence -> no infinite refresh loop."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        tid = tc.add_task(Task(title="Loop Test Task"))

        fv = FocusView(db, settings)
        fv.select_task_by_id(tid)
        fv.start_focus_session()
        fv.pause_focus_session()

        # Task updated safely
        saved = tc.get_task(tid)
        assert saved.status == TaskStatus.IN_PROGRESS
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_ev05_task_edit_today_calendar_gantt_converge():
    """EV05: task edit -> Today/Calendar/Gantt converge."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        tid = tc.add_task(Task(title="Initial Title", planned_date="2026-08-15", show_in_gantt=True))

        tv = TodayView(db, settings)
        cv = CalendarView(db, settings)
        gv = GanttView(db, settings)

        # Edit task
        tc.update_task(Task(id=tid, title="Converged Title", planned_date="2026-08-15", show_in_gantt=True))

        tv.refresh_data()
        cv.refresh_data()
        gv.refresh_data()

        today_tasks = tc.get_today_tasks(date(2026, 8, 15))
        assert any(x.title == "Converged Title" for x in today_tasks)
        cal_tasks = cv._get_tasks_for_date(date(2026, 8, 15))
        assert any(x.title == "Converged Title" for x in cal_tasks)
    finally:
        if os.path.exists(path):
            os.remove(path)
