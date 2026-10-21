"""
Batch-2 Gantt soak tests (TEST-G21..G25).

Self-contained pytest module — run as a SEPARATE subprocess so a native
Qt segfault cannot kill the main suite:

    QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest \
        todo_bird_app/tests/test_gantt_soak.py -q

or directly:

    QT_QPA_PLATFORM=offscreen ./venv/bin/python todo_bird_app/tests/test_gantt_soak.py

TEST-G21: repeated zoom switching — cycle all six modes 50+ times.
TEST-G22: repeated period navigation — 200+ navigate_period(±1) calls.
TEST-G23: repeated rebuild_chart() — bounded scene, no Shiboken errors.
TEST-G24: simulated minute-tick loop — no scene.clear(), marker consistency.
TEST-G25: resize/move interaction soak — hit-testing + planned-only payloads.

Constraints:
- Exactly ONE QApplication (module-scoped, guarded).
- Headless Qt via QT_QPA_PLATFORM=offscreen set BEFORE any Qt import.
- Production DB (todo_bird_app/data/todo_bird.db relative to project root) is NEVER touched:
  every widget is constructed with settings_manager=None.
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from datetime import date, timedelta

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from todo_bird_app.gantt.gantt_chart import GanttChartWidget
from todo_bird_app.gantt.timescale_engine import add_months
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority, TaskCategory

# ---------------------------------------------------------------
# Module-scoped application — exactly one, guarded.
# ---------------------------------------------------------------
APP = QApplication.instance() or QApplication([])

PROJ = {1: "Proj"}


def _make_task(
    tid: int,
    planned_date: str = None,
    status: TaskStatus = TaskStatus.PLANNED,
) -> Task:
    return Task(
        id=tid,
        title=f"T{tid}",
        project_id=1,
        priority=TaskPriority.MEDIUM,
        category=TaskCategory.WORK,
        planned_date=planned_date,
        due_date=planned_date,
        planned_start_time="09:00",
        planned_end_time="10:00",
        estimated_duration=60,
        progress=0,
        status=status,
        dependencies=[],
        tags=[],
    )


def _make_widget(
    zoom: str = "daily",
    anchor: date = None,
    tasks: list = None,
) -> GanttChartWidget:
    widget = GanttChartWidget(settings_manager=None)
    if anchor is not None:
        widget.anchor_date = anchor
    widget.set_zoom_mode(zoom)
    if tasks is not None:
        widget.set_tasks(tasks, PROJ)
    widget.rebuild_chart()
    return widget


# ---------------------------------------------------------------
# TEST-G21: repeated zoom switching
# ---------------------------------------------------------------
def test_g21_zoom_switch_soak():
    """TEST-G21 — cycle Hourly->Daily->Weekly->Monthly->Yearly->Multi-Year
    50+ times; widget must stay responsive (columns non-empty)."""
    today = date.today()
    tasks = [_make_task(1, today.strftime("%Y-%m-%d")), _make_task(2, None)]
    widget = _make_widget(zoom="daily", anchor=today, tasks=tasks)

    modes = ["hourly", "daily", "weekly", "monthly", "yearly", "multi_year"]
    for i in range(60):  # 10 full cycles == 60 switches
        mode = modes[i % len(modes)]
        widget.set_zoom_mode(mode)
        APP.processEvents()
        assert widget.columns, (
            f"TEST-G21: columns empty after switch to {mode}"
        )
        assert widget.anchor_date == today, (
            "TEST-G21: anchor_date drifted during zoom switches"
        )
    assert len(widget.columns) > 0


# ---------------------------------------------------------------
# TEST-G22: repeated period navigation
# ---------------------------------------------------------------
def test_g22_navigation_soak():
    """TEST-G22 — 200+ navigate_period(+/-1) calls across zoom modes;
    anchor_date must advance by the correct calendar unit each step."""
    start = date(2026, 8, 14)

    # (zoom, forward, backward, expected_shift_fn)
    scenarios = [
        ("hourly", 40, 40, lambda d, s: d + timedelta(days=s)),
        ("daily", 40, 40, lambda d, s: d + timedelta(days=s)),
        ("weekly", 20, 20, lambda d, s: d + timedelta(weeks=s)),
        ("monthly", 20, 20, lambda d, s: add_months(d, s)),
        ("yearly", 10, 10, lambda d, s: date(d.year + s, d.month, 1)),
        (
            "multi_year",
            10,
            10,
            lambda d, s: date(d.year + (s * 5), d.month, 1),
        ),
    ]

    total_navigations = 0
    for zoom, fwd, bwd, shift in scenarios:
        widget = _make_widget(zoom=zoom, anchor=start, tasks=[])
        anchor = start
        for _ in range(fwd):
            widget.navigate_period(1)
            expected = shift(anchor, 1)
            assert widget.anchor_date == expected, (
                f"TEST-G22 {zoom}: +1 expected {expected} got "
                f"{widget.anchor_date}"
            )
            anchor = widget.anchor_date
            total_navigations += 1
        for _ in range(bwd):
            widget.navigate_period(-1)
            expected = shift(anchor, -1)
            assert widget.anchor_date == expected, (
                f"TEST-G22 {zoom}: -1 expected {expected} got "
                f"{widget.anchor_date}"
            )
            anchor = widget.anchor_date
            total_navigations += 1
        # zoom change must not blow up either
        widget.set_zoom_mode("daily")
        assert widget.columns

    assert total_navigations >= 200, (
        f"TEST-G22: only {total_navigations} navigations executed"
    )


# ---------------------------------------------------------------
# TEST-G23: repeated rebuild
# ---------------------------------------------------------------
def test_g23_rebuild_soak():
    """TEST-G23 — 100+ rebuild_chart() calls (direct and via set_tasks);
    scene item count stays bounded and no RuntimeError (Shiboken)
    surfaces on marker items."""
    today = date.today()
    widget = _make_widget(zoom="daily", anchor=today, tasks=[])

    # Fixed configuration: identical rebuilds must produce a stable count.
    fixed_tasks = [_make_task(10, today.strftime("%Y-%m-%d"))]
    widget.set_tasks(fixed_tasks, PROJ)
    counts = []
    for _ in range(110):
        widget.rebuild_chart()  # RuntimeError would propagate here
        counts.append(len(widget.scene.items()))
        assert len(widget.scene.items()) > 0, "TEST-G23: scene emptied"

    assert max(counts) - min(counts) <= 3, (
        f"TEST-G23: unbounded growth: {counts[:5]}...{counts[-5:]}"
    )

    # Varying task lists via set_tasks (each rebuilds internally).
    for n in range(30):
        tasks = [
            _make_task(
                100 + i,
                (today + timedelta(days=i)).strftime("%Y-%m-%d"),
            )
            for i in range(n % 5 + 1)
        ]
        widget.set_tasks(tasks, PROJ)
        assert len(widget.scene.items()) > 0
        # Marker helpers must tolerate stale wrappers across rebuilds.
        widget.update_current_time_marker()
        widget._clear_current_time_marker()

    assert len(widget.scene.items()) > 0


# ---------------------------------------------------------------
# TEST-G24: simulated minute-tick loop
# ---------------------------------------------------------------
def test_g24_timer_tick_soak():
    """TEST-G24 — 300 _on_minute_tick() calls; scene is never cleared
    (item count never resets), no exception, and current_time_line_item
    stays consistent with _today_visible()."""
    today = date.today()
    widget = _make_widget(
        zoom="daily",
        anchor=today,
        tasks=[_make_task(20, today.strftime("%Y-%m-%d"))],
    )
    assert widget._today_visible() is True
    baseline = len(widget.scene.items())
    assert baseline > 0

    for _ in range(300):
        widget._on_minute_tick()  # RuntimeError would propagate here
        count = len(widget.scene.items())
        assert count >= baseline, (
            "TEST-G24: item count dropped — scene was cleared by tick"
        )

    # When today is visible the live marker must exist after ticks.
    assert widget.current_time_line_item is not None, (
        "TEST-G24: live marker missing while today is visible"
    )

    # When today is NOT visible the marker must stay absent.
    far = today + timedelta(days=60)
    widget2 = _make_widget(zoom="daily", anchor=far, tasks=[])
    assert widget2._today_visible() is False
    widget2.update_current_time_marker()
    assert widget2.current_time_line_item is None
    for _ in range(100):
        widget2._on_minute_tick()
        assert widget2.current_time_line_item is None, (
            "TEST-G24: marker present although today is off-range"
        )


# ---------------------------------------------------------------
# TEST-G25: resize / move interaction soak
# ---------------------------------------------------------------
def test_g25_resize_interaction_soak():
    """TEST-G25 — many _bar_interaction_mode + _build_resize_payload
    sequences across bar widths 36..200 (plus short bars) in hourly and
    daily zoom; no crash, payloads are None or planned-only (never
    actual_* keys)."""
    today = date.today()

    # ----- HOURLY -----
    widget = _make_widget(
        zoom="hourly",
        anchor=today,
        tasks=[_make_task(30, today.strftime("%Y-%m-%d"))],
    )
    item = widget._rendered_task_items.get(30)
    assert item is not None, "TEST-G25: hourly task did not render"
    base_pos = item.scenePos()

    widths = [36, 40, 48, 60, 80, 100, 140, 200, 24, 16, 10]
    probes = [-10, -6, -1, 0, 1, 6, 12, 25, 50, 75, 100, 150, 200]
    for w in widths:
        item.bar_pixel_width = float(w)
        for local_x in probes:
            mode = widget._bar_interaction_mode(
                item, base_pos + QPointF(local_x, 15)
            )
            assert mode in ("left", "right", "move", None), (
                f"TEST-G25 hourly w={w} x={local_x}: bad mode {mode!r}"
            )
        for edge in ("left", "right"):
            for delta in (-90, -60, -30, -10, -5, 0, 5, 10, 30, 60, 90):
                payload = widget._build_resize_payload(
                    item, edge, delta
                )
                if payload is not None:
                    assert isinstance(payload, dict)
                    assert not any(
                        k.startswith("actual") for k in payload
                    ), (
                        f"TEST-G25 hourly: payload leaked actual_*: "
                        f"{sorted(payload)}"
                    )
                    assert payload["edit_kind"] == "resize"
                    assert payload["resize_edge"] == edge

    # ----- DAILY -----
    widget2 = _make_widget(
        zoom="daily",
        anchor=today,
        tasks=[_make_task(31, today.strftime("%Y-%m-%d"))],
    )
    item2 = widget2._rendered_task_items.get(31)
    assert item2 is not None, "TEST-G25: daily task did not render"
    base_pos2 = item2.scenePos()
    item2.bar_pixel_width = 120.0
    for local_x in probes:
        mode = widget2._bar_interaction_mode(
            item2, base_pos2 + QPointF(local_x, 15)
        )
        assert mode in ("left", "right", "move", None)
    for edge in ("left", "right"):
        for delta in (-90, -60, -30, -1, 0, 1, 30, 60, 90):
            payload = widget2._build_resize_payload(item2, edge, delta)
            if payload is not None:
                assert isinstance(payload, dict)
                assert not any(
                    k.startswith("actual") for k in payload
                ), (
                    f"TEST-G25 daily: payload leaked actual_*: "
                    f"{sorted(payload)}"
                )
                assert payload["edit_kind"] == "resize"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))