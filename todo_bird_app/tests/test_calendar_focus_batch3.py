import os
import sys
import tempfile
from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority, TaskCategory
from todo_bird_app.models.project import Project
from todo_bird_app.views.calendar_view import CalendarView
from todo_bird_app.views.focus_view import FocusView
from todo_bird_app.views.gantt_view import GanttView

import pytest

_APP = QApplication.instance() or QApplication([])

@pytest.fixture(autouse=True)
def stop_timers_after_test():
    yield
    for widget in list(_APP.topLevelWidgets()):
        if isinstance(widget, (CalendarView, FocusView, GanttView)):
            try:
                if hasattr(widget, "cleanup"):
                    widget.cleanup()
            except Exception:
                pass
            try:
                widget.close()
            except Exception:
                pass
            try:
                widget.deleteLater()
            except Exception:
                pass
    _APP.processEvents()


def _temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(path)
    return db, path


# ==============================================================================
# WORKSTREAM A: CALENDAR TESTS (CAL01 .. CAL06)
# ==============================================================================

def test_cal01_single_day_task_appears_on_correct_date():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Single Day Task", planned_date="2026-08-12", due_date="2026-08-12")
        tc.add_task(t)

        cal_view = CalendarView(db, settings)
        cal_view.calendar.setSelectedDate(QDate(2026, 8, 12))
        cal_view.refresh_data()

        # Check tasks listed for 2026-08-12
        displayed_tasks = cal_view._get_tasks_for_date(date(2026, 8, 12))
        assert any(task.title == "Single Day Task" for task in displayed_tasks)

        # Should NOT appear on 2026-08-13
        assert not any(task.title == "Single Day Task" for task in cal_view._get_tasks_for_date(date(2026, 8, 13)))
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_cal02_multi_day_task_spans_all_expected_dates():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        # Task from Aug 10 to Aug 14
        t = Task(title="Multi Day Campaign", planned_date="2026-08-10", due_date="2026-08-14")
        tc.add_task(t)

        cal_view = CalendarView(db, settings)
        for day in [10, 11, 12, 13, 14]:
            tasks = cal_view._get_tasks_for_date(date(2026, 8, day))
            assert any(task.title == "Multi Day Campaign" for task in tasks), f"Task must appear on 2026-08-{day}"

        # Must not appear before start or after due
        assert not any(task.title == "Multi Day Campaign" for task in cal_view._get_tasks_for_date(date(2026, 8, 9)))
        assert not any(task.title == "Multi Day Campaign" for task in cal_view._get_tasks_for_date(date(2026, 8, 15)))
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_cal03_planned_time_block_appears_correctly():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Timed Meeting", planned_date="2026-08-12", planned_start_time="09:00", planned_end_time="10:30")
        tc.add_task(t)

        cal_view = CalendarView(db, settings)
        tasks = cal_view._get_tasks_for_date(date(2026, 8, 12))
        matched = [task for task in tasks if task.title == "Timed Meeting"]
        assert len(matched) == 1
        assert matched[0].planned_start_time == "09:00"
        assert matched[0].planned_end_time == "10:30"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_cal04_edit_task_refreshes_calendar():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Original Title", planned_date="2026-08-12")
        tid = tc.add_task(t)

        cal_view = CalendarView(db, settings)
        cal_view.calendar.setSelectedDate(QDate(2026, 8, 12))

        # Edit task
        t_edit = tc.get_task(tid)
        t_edit.title = "Updated Title"
        t_edit.planned_date = "2026-08-15"
        tc.update_task(t_edit)

        # Old date should not have task
        assert not any(task.title == "Updated Title" for task in cal_view._get_tasks_for_date(date(2026, 8, 12)))
        # New date should have task
        assert any(task.title == "Updated Title" for task in cal_view._get_tasks_for_date(date(2026, 8, 15)))
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_cal05_status_update_refreshes_calendar():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Status Task", planned_date="2026-08-12", status=TaskStatus.INBOX)
        tid = tc.add_task(t)

        cal_view = CalendarView(db, settings)
        tc.toggle_task_complete(tid)

        tasks = cal_view._get_tasks_for_date(date(2026, 8, 12))
        assert any(task.id == tid and task.status == TaskStatus.COMPLETED for task in tasks)
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_cal06_invalid_date_safe():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t1 = Task(title="Invalid Date Task", planned_date="INVALID-DATE", due_date="NOT-A-DATE")
        t2 = Task(title="Empty Date Task", planned_date=None, due_date=None)
        tc.add_task(t1)
        tc.add_task(t2)

        cal_view = CalendarView(db, settings)
        # Should not crash on any date selection
        cal_view.calendar.setSelectedDate(QDate(2026, 8, 12))
        cal_view.refresh_data()
        tasks = cal_view._get_tasks_for_date(date(2026, 8, 12))
        assert len(tasks) == 0
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_cal_hover_01_empty_state_persists_across_mouse_moves():
    """CAL-HOVER-01: Empty state message and nearest task text remain visible across 400+ mouse moves."""
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent, QPointF
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        # Task on 13 Aug
        t = Task(title="Prior Milestone", planned_date="2026-08-13")
        tc.add_task(t)

        cal_view = CalendarView(db, settings)
        cal_view.resize(900, 600)
        cal_view.show()
        _APP.processEvents()

        # Select empty date 15 Aug
        cal_view.calendar.setSelectedDate(QDate(2026, 8, 15))
        _APP.processEvents()

        assert cal_view.empty_state_card.isVisible()
        assert "15 Aug 2026" in cal_view.lbl_empty_main.text()
        assert "13 Aug 2026" in cal_view.lbl_empty_nearest.text()
        assert cal_view.lbl_empty_nearest.isVisible()

        # Simulate 400+ mouse moves across grid, card, side panel, empty space
        for px in range(0, 900, 20):
            for py in range(0, 600, 30):
                evt = QMouseEvent(QEvent.MouseMove, QPointF(px, py), QPointF(px, py), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
                _APP.sendEvent(cal_view, evt)
                _APP.sendEvent(cal_view.empty_state_card, evt)
                _APP.sendEvent(cal_view.lbl_empty_main, evt)
        _APP.processEvents()

        # Verify stability
        assert cal_view.empty_state_card.isVisible()
        assert "15 Aug 2026" in cal_view.lbl_empty_main.text()
        assert "13 Aug 2026" in cal_view.lbl_empty_nearest.text()
        assert cal_view.empty_state_card.width() > 0
        assert cal_view.empty_state_card.height() > 0
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_cal_hover_02_message_does_not_require_refresh():
    """CAL-HOVER-02: Empty state message remains visible after hover without requiring refresh_data()."""
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent, QPointF
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        cal_view = CalendarView(db, settings)
        cal_view.resize(900, 600)
        cal_view.show()
        cal_view.calendar.setSelectedDate(QDate(2026, 8, 15))
        _APP.processEvents()

        for px in range(500, 850, 10):
            evt = QMouseEvent(QEvent.MouseMove, QPointF(px, 200), QPointF(px, 200), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
            _APP.sendEvent(cal_view.empty_state_card, evt)
        _APP.processEvents()

        # No refresh called; card must still be visible and populated
        assert cal_view.empty_state_card.isVisible()
        assert "15 Aug 2026" in cal_view.lbl_empty_main.text()
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_cal_hover_03_date_change_switches_empty_and_active_states():
    """CAL-HOVER-03: Switching between empty date and populated date updates visibility deterministically."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Active Date Task", planned_date="2026-08-12")
        tc.add_task(t)

        cal_view = CalendarView(db, settings)
        cal_view.show()

        # 1. Empty date (Aug 15)
        cal_view.calendar.setSelectedDate(QDate(2026, 8, 15))
        _APP.processEvents()
        assert cal_view.empty_state_card.isVisible()
        assert not cal_view.task_scroll.isVisible()

        # 2. Date with task (Aug 12)
        cal_view.calendar.setSelectedDate(QDate(2026, 8, 12))
        _APP.processEvents()
        assert not cal_view.empty_state_card.isVisible()
        assert cal_view.task_scroll.isVisible()

        # 3. Switch back to empty date (Aug 15)
        cal_view.calendar.setSelectedDate(QDate(2026, 8, 15))
        _APP.processEvents()
        assert cal_view.empty_state_card.isVisible()
        assert not cal_view.task_scroll.isVisible()
        assert "15 Aug 2026" in cal_view.lbl_empty_main.text()
    finally:
        if os.path.exists(path):
            os.remove(path)


# ==============================================================================
# WORKSTREAM B & C: FOCUS MODE TESTS (FOC01 .. FOC10)
# ==============================================================================

def test_foc01_explicit_task_selection():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t1 = Task(title="Task One", status=TaskStatus.PLANNED)
        t2 = Task(
            title="Task Two",
            status=TaskStatus.IN_PROGRESS,
            actual_start_date=date.today().strftime("%Y-%m-%d"),
            actual_start_time="09:00",
        )
        tc.add_task(t1)
        tc.add_task(t2)

        focus_view = FocusView(db, settings)
        eligible = focus_view.get_eligible_tasks()
        assert len(eligible) >= 2
        titles = [t.title for t in eligible]
        assert "Task One" in titles and "Task Two" in titles

        # Explicitly select Task Two
        focus_view.select_task_by_id(t2.id)
        assert focus_view.current_task.id == t2.id
        assert focus_view.current_task.title == "Task Two"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_foc02_start_sets_actual_start_exactly_once():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Focus Target", planned_date="2026-08-12", planned_start_time="08:00", status=TaskStatus.PLANNED)
        tid = tc.add_task(t)

        focus_view = FocusView(db, settings)
        focus_view.select_task_by_id(tid)
        assert focus_view.current_task.actual_start_time is None

        # Start Focus session
        focus_view.start_focus_session()
        assert focus_view.state == "RUNNING"
        first_actual_start = focus_view.current_task.actual_start_time
        assert first_actual_start is not None
        assert ":" in first_actual_start

        # Pause and resume — actual_start_time must NOT be overwritten
        focus_view.pause_focus_session()
        focus_view.resume_focus_session()
        assert focus_view.current_task.actual_start_time == first_actual_start
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_foc03_timer_accumulation_accurate():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Accumulation Target", status=TaskStatus.PLANNED)
        tid = tc.add_task(t)

        focus_view = FocusView(db, settings)
        focus_view.select_task_by_id(tid)
        focus_view.start_focus_session()

        # Simulate 120 seconds of ticks
        for _ in range(120):
            focus_view._on_timer_tick()

        assert focus_view.elapsed_seconds == 120
        assert focus_view.current_task.actual_duration == 2 # 120s = 2 min
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_foc04_pause_stops_accumulation():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Pause Target", status=TaskStatus.PLANNED)
        tid = tc.add_task(t)

        focus_view = FocusView(db, settings)
        focus_view.select_task_by_id(tid)
        focus_view.start_focus_session()

        for _ in range(30):
            focus_view._on_timer_tick()
        assert focus_view.elapsed_seconds == 30

        focus_view.pause_focus_session()
        assert focus_view.state == "PAUSED"

        # Ticks while paused must not increase elapsed time
        for _ in range(10):
            focus_view._on_timer_tick()
        assert focus_view.elapsed_seconds == 30
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_foc05_resume_continues():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Resume Target", status=TaskStatus.PLANNED)
        tid = tc.add_task(t)

        focus_view = FocusView(db, settings)
        focus_view.select_task_by_id(tid)
        focus_view.start_focus_session()

        for _ in range(40):
            focus_view._on_timer_tick()
        focus_view.pause_focus_session()

        focus_view.resume_focus_session()
        assert focus_view.state == "RUNNING"
        for _ in range(20):
            focus_view._on_timer_tick()

        assert focus_view.elapsed_seconds == 60
        assert focus_view.current_task.actual_duration == 1
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_foc06_end_finalizes():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="End Target", status=TaskStatus.PLANNED)
        tid = tc.add_task(t)

        focus_view = FocusView(db, settings)
        focus_view.select_task_by_id(tid)
        focus_view.start_focus_session()
        for _ in range(90):
            focus_view._on_timer_tick()

        focus_view.end_focus_session()
        assert focus_view.state == "IDLE"

        # Verify persisted DB task
        db_task = tc.get_task(tid)
        assert db_task.actual_duration == 1 # 90s // 60 = 1m
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_foc07_complete_finalizes_actual_end():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(
            title="Complete Target",
            status=TaskStatus.IN_PROGRESS,
            actual_start_date=(date.today() - timedelta(days=1)).strftime("%Y-%m-%d"),
            actual_start_time="09:00",
        )
        tid = tc.add_task(t)

        focus_view = FocusView(db, settings)
        focus_view.select_task_by_id(tid)
        focus_view.start_focus_session()
        for _ in range(60):
            focus_view._on_timer_tick()

        focus_view.complete_focus_task()
        assert focus_view.state == "IDLE"

        db_task = tc.get_task(tid)
        assert db_task.status == TaskStatus.COMPLETED
        assert db_task.actual_end_time is not None
        assert db_task.actual_duration >= 1
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_foc08_completed_cancelled_cannot_start():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t_done = Task(title="Done Task", status=TaskStatus.COMPLETED)
        t_canc = Task(title="Cancelled Task", status=TaskStatus.CANCELLED)
        tc.add_task(t_done)
        tc.add_task(t_canc)

        focus_view = FocusView(db, settings)
        eligible = focus_view.get_eligible_tasks()
        eligible_ids = [t.id for t in eligible]
        assert t_done.id not in eligible_ids
        assert t_canc.id not in eligible_ids
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_foc09_planned_fields_unchanged():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(
            title="Freeze Planned Fields",
            planned_date="2026-08-12",
            planned_start_time="08:00",
            planned_end_time="09:00",
            estimated_duration=60,
            due_date="2026-08-15",
            status=TaskStatus.PLANNED,
        )
        tid = tc.add_task(t)

        focus_view = FocusView(db, settings)
        focus_view.select_task_by_id(tid)
        focus_view.start_focus_session()
        for _ in range(150):
            focus_view._on_timer_tick()
        focus_view.end_focus_session()

        db_task = tc.get_task(tid)
        assert db_task.planned_date == "2026-08-12"
        assert db_task.planned_start_time == "08:00"
        assert db_task.planned_end_time == "09:00"
        assert db_task.estimated_duration == 60
        assert db_task.due_date == "2026-08-15"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_foc10_no_duplicate_timer():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Single Timer Target", status=TaskStatus.PLANNED)
        tid = tc.add_task(t)

        focus_view = FocusView(db, settings)
        focus_view.select_task_by_id(tid)
        focus_view.start_focus_session()
        focus_view.start_focus_session() # Redundant start call
        assert focus_view.timer.isActive()
        assert focus_view.state == "RUNNING"
        focus_view.timer.stop()
    finally:
        if os.path.exists(path):
            os.remove(path)


# ==============================================================================
# WORKSTREAM D: CROSS-VIEW SYNCHRONIZATION (X01 .. X10)
# ==============================================================================

def test_x01_title_edit_syncs_calendar_and_gantt():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Alpha", planned_date="2026-08-12", show_in_gantt=True)
        tid = tc.add_task(t)

        cal_view = CalendarView(db, settings)
        gantt_view = GanttView(db, settings)
        gantt_view.gantt_chart.anchor_date = date(2026, 8, 12)
        gantt_view.refresh_data()

        # Update title
        t_edit = tc.get_task(tid)
        t_edit.title = "Beta"
        tc.update_task(t_edit)

        cal_tasks = cal_view._get_tasks_for_date(date(2026, 8, 12))
        assert any(task.title == "Beta" for task in cal_tasks)

        gantt_tasks = [item.task for item in gantt_view.gantt_chart._rendered_task_items.values()]
        assert any(task.title == "Beta" for task in gantt_tasks)
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_x03_start_focus_syncs_gantt_actual():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(
            title="Focus Gantt Sync",
            planned_date="2026-08-12",
            planned_start_time="08:00",
            estimated_duration=60,
            show_in_gantt=True,
        )
        tid = tc.add_task(t)

        focus_view = FocusView(db, settings)
        gantt_view = GanttView(db, settings)
        gantt_view.gantt_chart.set_zoom_mode("hourly")
        gantt_view.gantt_chart.anchor_date = date(2026, 8, 12)
        gantt_view.refresh_data()

        # Start Focus
        focus_view.select_task_by_id(tid)
        focus_view.start_focus_session()

        # Gantt chart should reflect the task's new actual_start_time
        gantt_item = gantt_view.gantt_chart._rendered_task_items.get(tid)
        assert gantt_item is not None
        assert gantt_item.task.actual_start_time is not None
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_x04_focus_duration_tick_updates_actual_preserves_planned():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Focus Tick", planned_date="2026-08-12", planned_start_time="08:00", estimated_duration=60, show_in_gantt=True)
        tid = tc.add_task(t)

        focus_view = FocusView(db, settings)
        focus_view.select_task_by_id(tid)
        focus_view.start_focus_session()

        for _ in range(60):
            focus_view._on_timer_tick()
        focus_view.end_focus_session()

        db_task = tc.get_task(tid)
        assert db_task.actual_duration == 1
        assert db_task.planned_start_time == "08:00"
        assert db_task.estimated_duration == 60
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_x08_complete_from_focus_refreshes_all_views():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Complete Cross Sync", planned_date="2026-08-12", show_in_gantt=True)
        tid = tc.add_task(t)

        cal_view = CalendarView(db, settings)
        focus_view = FocusView(db, settings)
        focus_view.select_task_by_id(tid)
        focus_view.start_focus_session()

        for _ in range(60):
            focus_view._on_timer_tick()
        focus_view.complete_focus_task()

        # Check in DB
        db_task = tc.get_task(tid)
        assert db_task.status == TaskStatus.COMPLETED

        # Check Calendar reflects Completed
        cal_tasks = cal_view._get_tasks_for_date(date(2026, 8, 12))
        assert any(task.id == tid and task.status == TaskStatus.COMPLETED for task in cal_tasks)
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_x09_restart_app_preserves_finalized_fields():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Persist Target", planned_date="2026-08-12", planned_start_time="08:00", estimated_duration=60)
        tid = tc.add_task(t)

        focus_view = FocusView(db, settings)
        focus_view.select_task_by_id(tid)
        focus_view.start_focus_session()
        for _ in range(120):
            focus_view._on_timer_tick()
        focus_view.end_focus_session()

        # Simulate App Restart with new DatabaseManager / TaskController instances
        db_restarted = DatabaseManager(path)
        tc_restarted = TaskController(db_restarted)
        restarted_task = tc_restarted.get_task(tid)

        assert restarted_task.actual_duration == 2
        assert restarted_task.actual_start_time is not None
        assert restarted_task.planned_start_time == "08:00"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_x10_no_duplicate_writes_or_refresh_loops():
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        t = Task(title="Loop Prevention", planned_date="2026-08-12")
        tid = tc.add_task(t)

        cal_view = CalendarView(db, settings)
        focus_view = FocusView(db, settings)

        refresh_counts = {"cal": 0, "focus": 0}

        def on_cal_refresh():
            refresh_counts["cal"] += 1

        def on_focus_refresh():
            refresh_counts["focus"] += 1

        cal_view.task_controller.tasks_changed.connect(on_cal_refresh)
        focus_view.task_controller.tasks_changed.connect(on_focus_refresh)

        # One task update
        t_edit = tc.get_task(tid)
        t_edit.title = "Loop Prevention Edited"
        tc.update_task(t_edit)

        # Both views should receive exactly 1 notification without endless recursive loops
        assert refresh_counts["cal"] == 1
        assert refresh_counts["focus"] == 1
    finally:
        if os.path.exists(path):
            os.remove(path)
