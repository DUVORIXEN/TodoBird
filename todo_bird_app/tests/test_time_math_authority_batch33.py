"""
Tests for TODO BIRD Batch 3.3 Time-Math Authority & Planned-Bar Pipeline.
Covers TM01..TM15 and PB01..PB08.
"""

import os
import tempfile
from datetime import date, datetime, time
import pytest
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import QRectF

from todo_bird_app.utils.time_math import (
    parse_hhmm,
    format_hhmm,
    format_duration_display,
    minutes_between_same_day,
    combine_date_time,
    duration_between,
    segment_interval_by_day,
    clamp_minutes,
    minutes_to_x,
    duration_to_width,
    snap_minutes,
    DAY_MINUTES,
)
from PySide6.QtWidgets import QApplication
from todo_bird_app.database import DatabaseManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.gantt.gantt_chart import GanttChartWidget
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
# TIME-MATH TESTS (TM01 .. TM15)
# ==============================================================================

def test_tm01_zero_time():
    """TM01: 00:00 -> 0 minutes."""
    assert parse_hhmm("00:00") == 0
    assert format_hhmm(0) == "00:00"


def test_tm02_end_of_day_minute():
    """TM02: 23:59 -> 1439 minutes."""
    assert parse_hhmm("23:59") == 1439
    assert format_hhmm(1439) == "23:59"


def test_tm03_morning_odd_minutes():
    """TM03: 08:23 -> 503 minutes."""
    assert parse_hhmm("08:23") == 503
    assert format_hhmm(503) == "08:23"


def test_tm04_early_morning_odd_minutes():
    """TM04: 06:11 -> 371 minutes."""
    assert parse_hhmm("06:11") == 371
    assert format_hhmm(371) == "06:11"


def test_tm05_same_day_difference():
    """TM05: 08:23 -> 21:45 = 802m."""
    s = parse_hhmm("08:23")
    e = parse_hhmm("21:45")
    assert s == 503
    assert e == 1305
    assert minutes_between_same_day(s, e) == 802


def test_tm06_multi_day_datetime_duration():
    """TM06: 14 Aug 10:00 -> 16 Aug 17:00 = 3300m."""
    dur = duration_between(
        "2026-08-14", "10:00",
        "2026-08-16", "17:00",
    )
    assert dur == 3300


def test_tm07_segments_sum_to_total_duration():
    """TM07: Daily segments sum to total datetime duration (3300)."""
    segments = segment_interval_by_day(
        "2026-08-14", "10:00",
        "2026-08-16", "17:00",
    )
    assert len(segments) == 3
    total_dur = sum(s.duration_minutes for s in segments)
    assert total_dur == 3300


def test_tm08_intermediate_day_is_full_day():
    """TM08: 15 Aug intermediate segment = 1440m [0, 1440)."""
    segments = segment_interval_by_day(
        "2026-08-14", "10:00",
        "2026-08-16", "17:00",
    )
    seg15 = next(s for s in segments if s.date == date(2026, 8, 15))
    assert seg15.start_minute == 0
    assert seg15.end_minute_exclusive == 1440
    assert seg15.duration_minutes == 1440


def test_tm09_cross_midnight_next_day():
    """TM09: cross-midnight 23:30 -> 00:45 next day = 75m."""
    dur = duration_between(
        "2026-08-15", "23:30",
        "2026-08-16", "00:45",
    )
    assert dur == 75
    segments = segment_interval_by_day(
        "2026-08-15", "23:30",
        "2026-08-16", "00:45",
    )
    assert sum(s.duration_minutes for s in segments) == 75


def test_tm10_invalid_reverse_same_day_rejected():
    """TM10: invalid reverse same-day range rejected."""
    dur = duration_between("2026-08-15", "10:00", "2026-08-15", "09:00")
    assert dur == -60  # Negative duration
    segments = segment_interval_by_day("2026-08-15", "10:00", "2026-08-15", "09:00")
    assert segments == []  # Rejected from segmentation


def test_tm11_one_minute_logical_duration():
    """TM11: 1-minute logical duration remains 1m despite minimum visual width."""
    dur = duration_between("2026-08-15", "08:15", "2026-08-15", "08:16")
    assert dur == 1
    assert format_duration_display(dur) == "1 min"
    # Math width at 60px/hour = 1px, visual width minimum = 16px
    math_w = duration_to_width(dur, 60.0)
    assert math_w == 1.0


def test_tm12_exact_one_hour_format():
    """TM12: 60m = exactly 1 hour."""
    assert format_duration_display(60) == "1h"


def test_tm13_ninety_minutes_format():
    """TM13: 90m = 1h 30m."""
    assert format_duration_display(90) == "1h 30m"


def test_tm14_planned_and_actual_same_minute_to_pixel_authority():
    """TM14: planned and actual use same minute-to-pixel authority."""
    px60 = 60.0
    assert minutes_to_x(480, px60) == 480.0  # 08:00
    assert minutes_to_x(503, px60) == 503.0  # 08:23
    assert duration_to_width(60, px60) == 60.0
    assert duration_to_width(84, px60) == 84.0


def test_tm15_snap_minutes_deterministic():
    """TM15: deterministic snap without banker's rounding."""
    assert snap_minutes(7, 15) == 0
    assert snap_minutes(8, 15) == 15
    assert snap_minutes(15, 15) == 15
    assert snap_minutes(22, 15) == 15
    assert snap_minutes(23, 15) == 30


# ==============================================================================
# PLANNED-BAR TESTS (PB01 .. PB08)
# ==============================================================================

def test_pb01_planned_today_standard_renders():
    """PB01: planned today 08:00->09:00 renders at x=480, w=60."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        tid = tc.add_task(Task(
            title="PB01 Task",
            planned_date="2026-08-15",
            planned_start_time="08:00",
            planned_end_time="09:00",
            estimated_duration=60,
            show_in_gantt=True,
        ))
        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()

        item = chart._rendered_task_items[tid]
        assert item.pos().x() == 480.0
        assert item.bar_pixel_width == 60.0

        # Render QImage pixel verification
        img = QImage(1600, 400, QImage.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        chart.scene.render(p, target=QRectF(0, 0, 1600, 400), source=QRectF(0, 0, 1600, 400))
        p.end()

        # Check that pixels around X=500, Y=70 (inside 480..540) have non-zero alpha
        pixel_color = img.pixelColor(500, 70)
        assert pixel_color.alpha() > 0
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_pb02_planned_today_odd_minute_renders():
    """PB02: planned today 08:23->09:47 renders exact x=503, w=84."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        tid = tc.add_task(Task(
            title="PB02 Task",
            planned_date="2026-08-15",
            planned_start_time="08:23",
            planned_end_time="09:47",
            estimated_duration=84,
            show_in_gantt=True,
        ))
        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()

        item = chart._rendered_task_items[tid]
        assert item.pos().x() == 503.0
        assert item.bar_pixel_width == 84.0

        # Render QImage pixel verification
        img = QImage(1600, 400, QImage.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        chart.scene.render(p, target=QRectF(0, 0, 1600, 400), source=QRectF(0, 0, 1600, 400))
        p.end()

        # Check that pixels at X=520, Y=70 (inside 503..587) have non-zero alpha
        pixel_color = img.pixelColor(520, 70)
        assert pixel_color.alpha() > 0
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_pb03_spanning_task_does_not_fabricate_planned_bar():
    """PB03: planned earlier spanning today does not fabricate timed Planned bar."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        tid = tc.add_task(Task(
            title="Spanning Task",
            planned_date="2026-08-13",
            due_date="2026-08-17",
            planned_start_time="08:00",
            planned_end_time="09:00",
            show_in_gantt=True,
        ))
        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()

        # On 15 Aug: active untimed state (no fabricated 08:00 bar)
        assert chart._current_empty_message is not None
        assert "1 task is active today, but none have a timed schedule." in chart._current_empty_message
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_pb04_untimed_today_acknowledged():
    """PB04: untimed today acknowledged but not rendered as fake bar."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        tid = tc.add_task(Task(
            title="Untimed Task",
            planned_date="2026-08-15",
            show_in_gantt=True,
        ))
        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()

        assert chart._current_empty_message == "1 task is active today, but none have a timed schedule."
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_pb05_show_in_gantt_false_excluded():
    """PB05: show_in_gantt false excluded."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        tid = tc.add_task(Task(
            title="Excluded Task",
            planned_date="2026-08-15",
            planned_start_time="08:00",
            planned_end_time="09:00",
            show_in_gantt=False,
        ))
        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()

        assert chart._current_empty_message is not None
        assert "No tasks scheduled for 15 Aug 2026" in chart._current_empty_message
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_pb06_subtask_planned_today_renders():
    """PB06: subtask planned-today bar renders."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        tid = tc.add_task(Task(title="Parent", show_in_gantt=True))
        sid = db.insert_subtask(
            task_id=tid,
            title="Sub Planned Today",
            planned_date="2026-08-15",
            planned_start_time="10:00",
            planned_end_time="11:30",
            estimated_duration=90,
            show_in_gantt=True,
        )
        gv = GanttView(db, settings)
        gv.gantt_chart.set_zoom_mode("hourly")
        gv.gantt_chart.anchor_date = date(2026, 8, 15)
        gv.refresh_data()

        sub_item = gv.gantt_chart._rendered_task_items.get(-sid)
        assert sub_item is not None
        assert sub_item.pos().x() == 600.0  # 10:00
        assert sub_item.bar_pixel_width == 90.0  # 90 mins
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_pb07_sub_subtask_planned_today_renders():
    """PB07: sub-subtask planned-today bar renders."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        tid = tc.add_task(Task(title="Parent", show_in_gantt=True))
        sid = db.insert_subtask(task_id=tid, title="Sub 1", show_in_gantt=True)
        ssid = db.insert_subtask(
            task_id=tid,
            parent_subtask_id=sid,
            title="Sub-Sub Planned Today",
            planned_date="2026-08-15",
            planned_start_time="14:00",
            planned_end_time="15:00",
            estimated_duration=60,
            show_in_gantt=True,
        )
        gv = GanttView(db, settings)
        gv.gantt_chart.set_zoom_mode("hourly")
        gv.gantt_chart.anchor_date = date(2026, 8, 15)
        gv.refresh_data()

        subsub_item = gv.gantt_chart._rendered_task_items.get(-ssid)
        assert subsub_item is not None
        assert subsub_item.pos().x() == 840.0  # 14:00
        assert subsub_item.bar_pixel_width == 60.0
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_pb08_actual_only_day_does_not_invent_planned():
    """PB08: actual-only day does not invent planned bar."""
    db, path = _temp_db()
    try:
        settings = SettingsManager(db)
        tc = TaskController(db)
        tid = tc.add_task(Task(
            title="Unplanned Actual Work",
            planned_date="2026-08-10",
            actual_start_date="2026-08-15",
            actual_end_date="2026-08-15",
            actual_start_time="14:00",
            actual_end_time="15:00",
            actual_duration=60,
            show_in_gantt=True,
        ))
        chart = GanttChartWidget(settings_manager=settings)
        chart.set_zoom_mode("hourly")
        chart.anchor_date = date(2026, 8, 15)
        chart.set_tasks([tc.get_task(tid)], {})
        chart.rebuild_chart()

        item = chart._rendered_task_items[tid]
        assert not item.has_planned_today
        assert item.has_actual_today
    finally:
        if os.path.exists(path):
            os.remove(path)
