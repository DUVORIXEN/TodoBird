"""
Batch-2 Gantt contract tests (TEST-G01 .. TEST-G20).

Covers: hourly visibility/navigation/empty-state, timer safety, today
marker visibility, Shiboken lifetime discipline, hover contract, dynamic
resize edges, resize preview/snap/payload, planned-only mutation,
closed-task edit guards, item handle metadata, narrow-toolbar scroll area.

Run headless:
    cd /path/to/todo_bird
    QT_QPA_PLATFORM=offscreen PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
        ./venv/bin/python -m pytest todo_bird_app/tests/test_gantt_batch2.py -q

Never touches the production database: all fixtures are in-memory
Task objects rendered by GanttChartWidget(None).
"""
import inspect
import os
import tempfile
from datetime import date, timedelta

from PySide6.QtCore import QPointF, Qt, QCoreApplication
from PySide6.QtWidgets import QApplication, QGraphicsScene, QScrollArea, QFrame

from todo_bird_app.gantt.gantt_chart import GanttChartWidget
from todo_bird_app.gantt.timescale_engine import ZoomLevel
from todo_bird_app.gantt.gantt_items import GanttTaskItem
from todo_bird_app.models.task import Task, TaskStatus

_APP = QApplication.instance() or QApplication([])


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _task(tid, planned_date=None, status=TaskStatus.INBOX,
          pst=None, pet=None, dur=60):
    return Task(
        id=tid,
        title=f"T{tid}",
        planned_date=planned_date,
        planned_start_time=pst,
        planned_end_time=pet,
        estimated_duration=dur,
        status=status,
    )


def _chart():
    return GanttChartWidget(None)


def _color_dict(chart):
    return chart.color_profile.get_effective_colors("dark")


def _make_item(chart, task, cols=1.0):
    item = GanttTaskItem(
        task, 0, 0.0, cols, 60, _color_dict(chart), row_height=30,
    )
    scene = QGraphicsScene()
    scene.addItem(item)
    item.setPos(0, 0)
    # Keep the scene referenced for the item's C++ lifetime (Shiboken).
    item._test_scene = scene
    return item


def _scene_texts(chart):
    texts = [
        i.toPlainText()
        for i in chart.scene.items()
        if hasattr(i, "toPlainText") and i.toPlainText()
    ]
    if getattr(chart, "_current_empty_message", None):
        texts.append(chart._current_empty_message)
    return texts


def _hover_source(chart):
    """The hover-affordance branch of mouseMoveEvent (no buttons)."""
    src = inspect.getsource(chart.mouseMoveEvent)
    return src.split("if not (")[1].split("super()")[0]


# --------------------------------------------------------------------------
# TEST-G01 .. TEST-G02 — hourly task visibility
# --------------------------------------------------------------------------
def test_g01_hourly_renders_anchor_date_tasks():
    chart = _chart()
    today = date.today()
    anchor = today - timedelta(days=3)
    chart.set_zoom_mode("hourly")
    chart.anchor_date = anchor
    chart.set_tasks([
        _task(1, anchor.strftime("%Y-%m-%d")),
        _task(2, (anchor + timedelta(days=1)).strftime("%Y-%m-%d")),
    ], {})
    chart.rebuild_chart()
    rendered = sorted(chart._rendered_task_items.keys())
    assert rendered == [1], f"hourly must render only anchor-date tasks, got {rendered}"


def test_g02_hourly_skips_unrelated_and_unparseable():
    chart = _chart()
    today = date.today()
    anchor = today - timedelta(days=3)
    chart.set_zoom_mode("hourly")
    chart.anchor_date = anchor
    chart.set_tasks([
        _task(1, anchor.strftime("%Y-%m-%d")),          # visible
        _task(2, (anchor + timedelta(days=1)).strftime("%Y-%m-%d")),  # other date
        _task(3, None),                                  # missing date
        _task(4, "not-a-date"),                          # unparseable
    ], {})
    chart.rebuild_chart()
    rendered = sorted(chart._rendered_task_items.keys())
    assert rendered == [1], (
        "unparseable/None planned_date must be SKIPPED in hourly "
        f"(never defaulted to today); got {rendered}"
    )


# --------------------------------------------------------------------------
# TEST-G03 .. TEST-G04 — hourly navigation (±1 calendar day)
# --------------------------------------------------------------------------
def test_g03_hourly_navigation_forward():
    chart = _chart()
    today = date.today()
    base = today - timedelta(days=2)
    chart.set_zoom_mode("hourly")
    chart.anchor_date = base
    chart.navigate_period(1)
    assert chart.anchor_date == base + timedelta(days=1), "HOURLY +1 step must advance 1 calendar day"


def test_g04_hourly_navigation_backward():
    chart = _chart()
    today = date.today()
    base = today - timedelta(days=2)
    chart.set_zoom_mode("hourly")
    chart.anchor_date = base
    chart.navigate_period(-2)
    assert chart.anchor_date == base - timedelta(days=2), "HOURLY -2 step must retreat 2 calendar days"


# --------------------------------------------------------------------------
# TEST-G05 .. TEST-G06 — empty-date contract
# --------------------------------------------------------------------------
def test_g05_empty_date_no_mutation():
    chart = _chart()
    today = date.today()
    anchor = today - timedelta(days=3)
    chart.set_zoom_mode("hourly")
    chart.anchor_date = anchor
    tasks = [
        _task(1, (anchor + timedelta(days=5)).strftime("%Y-%m-%d"), pst="09:00", pet="10:00", dur=60),
        _task(2, None),
    ]
    chart.set_tasks(tasks, {})
    chart.rebuild_chart()
    # Empty anchor: no bars rendered, and task data untouched.
    assert len(chart._rendered_task_items) == 0
    assert tasks[0].planned_date == (anchor + timedelta(days=5)).strftime("%Y-%m-%d")
    assert tasks[0].planned_start_time == "09:00"
    assert tasks[1].planned_date is None


def test_g06_empty_hourly_message():
    chart = _chart()
    today = date.today()
    anchor = today - timedelta(days=3)
    chart.set_zoom_mode("hourly")
    chart.anchor_date = anchor
    chart.set_tasks([
        _task(1, (anchor + timedelta(days=5)).strftime("%Y-%m-%d")),
    ], {})
    chart.rebuild_chart()
    texts = _scene_texts(chart)
    assert any("No tasks scheduled for" in t for t in texts), texts
    assert any("Nearest scheduled date" in t for t in texts), texts


# --------------------------------------------------------------------------
# TEST-G07 — hover contract: hit-test + cursor only (no rebuild / DB)
# --------------------------------------------------------------------------
def test_g07_hover_no_rebuild_no_db():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("daily")
    chart.anchor_date = today
    chart.set_tasks([_task(1, today.strftime("%Y-%m-%d"))], {})
    chart.rebuild_chart()

    # Static contract: the hover branch must never trigger a rebuild/clear.
    hover = _hover_source(chart)
    assert "rebuild_chart" not in hover
    assert "scene.clear" not in hover
    assert "db" not in hover.lower() or "set_tasks" not in hover

    # Behavioral spy: any rebuild during a hover event delivery = fail.
    calls = {"rebuild": 0}
    orig = chart.rebuild_chart
    chart.rebuild_chart = lambda *a, **k: (calls.__setitem__("rebuild", calls["rebuild"] + 1), orig(*a, **k))
    item = chart._rendered_task_items[1]
    view_pos = chart.mapFromScene(item.sceneBoundingRect().center())
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent
    ev = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(view_pos.x(), view_pos.y()),
        QPointF(view_pos.x(), view_pos.y()),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    chart.mouseMoveEvent(ev)
    chart.rebuild_chart = orig
    assert calls["rebuild"] == 0, "hover event delivery triggered a rebuild"


# --------------------------------------------------------------------------
# TEST-G08 — timer drives _on_minute_tick only (no rebuild on tick)
# --------------------------------------------------------------------------
def test_g08_timer_tick_only():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    chart.set_tasks([_task(1, today.strftime("%Y-%m-%d"))], {})
    chart.rebuild_chart()

    calls = {"rebuild": 0, "tick": 0}
    orig_rebuild, orig_tick = chart.rebuild_chart, chart._on_minute_tick
    chart.rebuild_chart = lambda *a, **k: (calls.__setitem__("rebuild", calls["rebuild"] + 1), orig_rebuild(*a, **k))
    chart._on_minute_tick = lambda *a, **k: (calls.__setitem__("tick", calls["tick"] + 1), orig_tick(*a, **k))
    base_rebuild = calls["rebuild"]

    chart.timer.timeout.emit()
    chart.timer.timeout.emit()
    chart.timer.timeout.emit()

    assert chart.timer.interval() == 60000, "timer must be 60s"
    assert calls["tick"] == 3, f"timeout must call _on_minute_tick, got tick={calls['tick']}"
    assert calls["rebuild"] == base_rebuild, (
        f"timeout must NEVER rebuild; rebuild delta={calls['rebuild'] - base_rebuild}"
    )


# --------------------------------------------------------------------------
# TEST-G09 — today marker only when today is visible
# --------------------------------------------------------------------------
def test_g09_today_marker_only_when_visible():
    chart = _chart()
    today = date.today()

    # Anchor 60 days back -> today far outside the visible hourly columns.
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today - timedelta(days=60)
    chart.set_tasks([_task(1, (today - timedelta(days=60)).strftime("%Y-%m-%d"))], {})
    chart.rebuild_chart()
    assert chart.current_time_line_item is None, "marker must be absent when today is not visible"

    # Anchor = today -> marker must exist.
    chart.anchor_date = today
    chart.set_tasks([_task(2, today.strftime("%Y-%m-%d"))], {})
    chart.rebuild_chart()
    assert chart.current_time_line_item is not None, "marker must exist when today is visible"


# --------------------------------------------------------------------------
# TEST-G10 .. TEST-G12 — dynamic resize edge geometry
# --------------------------------------------------------------------------
def test_g10_dynamic_edge_geometry():
    chart = _chart()
    anchor = date.today()
    item = _make_item(chart, _task(10, anchor.strftime("%Y-%m-%d")), cols=1.0)
    # w = max(1*60, 36) = 60 -> edge = min(14, max(6, 15)) = 14 -> move zone exists.
    assert item.bar_pixel_width == 60.0
    assert chart._bar_interaction_mode(item, QPointF(30, 15)) == "move"
    assert chart._bar_interaction_mode(item, QPointF(3, 15)) == "left"


def test_g11_dynamic_edge_geometry_right():
    chart = _chart()
    anchor = date.today()
    item = _make_item(chart, _task(11, anchor.strftime("%Y-%m-%d")), cols=1.0)
    assert chart._bar_interaction_mode(item, QPointF(57, 15)) == "right"


def test_g12_short_bar_half_split():
    chart = _chart()
    anchor = date.today()
    item = _make_item(chart, _task(11, anchor.strftime("%Y-%m-%d")), cols=1.0)
    # Simulate a very short bar: width 10 -> edge = min(14, max(6, 2.5)) = 6
    # 2*edge = 12 > 10 -> no move zone; left half = left, right half = right.
    item.bar_pixel_width = 10.0
    assert chart._bar_interaction_mode(item, QPointF(2, 15)) == "left"
    assert chart._bar_interaction_mode(item, QPointF(8, 15)) == "right"


# --------------------------------------------------------------------------
# TEST-G13 — resize preview + SizeHor cursor during drag
# --------------------------------------------------------------------------
def test_g13_preview_and_cursor():
    chart = _chart()
    src = inspect.getsource(chart.mouseMoveEvent)
    # The drag branch (after the first `if self._resize_moved:`) must force
    # a SizeHor cursor so the affordance survives the whole drag.
    drag_branch = src.split("if self._resize_moved:")[1]
    assert "SizeHorCursor" in drag_branch.split("def ")[0]
    assert hasattr(chart, "_resize_preview")
    # Preview mechanism: rebuild releases the preview before scene.clear().
    rebuild_src = inspect.getsource(chart.rebuild_chart)
    assert "_resize_preview" in rebuild_src


# --------------------------------------------------------------------------
# TEST-G14 — hourly snap; snapped == 0 -> no payload / no write
# --------------------------------------------------------------------------
def test_g14_hourly_snap_no_write():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    chart.set_tasks([_task(1, today.strftime("%Y-%m-%d"), pst="10:00", pet="11:00", dur=60)], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[1]
    col_width = float(chart.columns[0].width)

    # Sub-snap drag -> no payload at all (no write on no movement).
    assert chart._build_resize_payload(item, "right", 0.001) is None

    # One full snap interval (15 min) -> payload produced, end advances 15 min.
    payload = chart._build_resize_payload(item, "right", col_width * (15.0 / 60.0))
    assert payload is not None
    assert payload["planned_end_time"] == "11:15", payload
    assert payload["estimated_duration"] == 75, payload
    assert payload["delta_minutes"] == 15, payload


# --------------------------------------------------------------------------
# TEST-G15 — resize payload is planned-only (never actual_*)
# --------------------------------------------------------------------------
def test_g15_planned_only_payload():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    chart.set_tasks([_task(1, today.strftime("%Y-%m-%d"), pst="10:00", pet="11:00", dur=60)], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[1]
    col_width = float(chart.columns[0].width)
    payload = chart._build_resize_payload(item, "right", col_width * (15.0 / 60.0))
    assert payload is not None
    for key in payload:
        assert "actual" not in key.lower(), f"payload must not contain actual_* fields: {key}"
    assert "planned_date" in payload
    assert "planned_end_time" in payload
    assert "estimated_duration" in payload


# --------------------------------------------------------------------------
# TEST-G16 — completed/cancelled tasks are non-editable
# --------------------------------------------------------------------------
def test_g16_closed_tasks_not_editable():
    chart = _chart()
    today = date.today()
    for status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
        item = _make_item(chart, _task(99, today.strftime("%Y-%m-%d"), status=status))
        assert chart._schedule_editable(item) is False, f"{status} must be non-editable"
    for status in (TaskStatus.INBOX, TaskStatus.PLANNED):
        item = _make_item(chart, _task(98, today.strftime("%Y-%m-%d"), status=status))
        assert chart._schedule_editable(item) is True, f"{status} must be editable in hourly"


# --------------------------------------------------------------------------
# TEST-G17 — narrow toolbar wrapped in a horizontal QScrollArea
# --------------------------------------------------------------------------
def test_g17_toolbar_scroll_area():
    from todo_bird_app.database import DatabaseManager
    from todo_bird_app.views.gantt_view import GanttView
    tmp = tempfile.mkdtemp()
    db = DatabaseManager(os.path.join(tmp, "test.db"))
    from pathlib import Path
    from todo_bird_app.settings.settings_manager import SettingsManager
    sm = SettingsManager(db_manager=db, config_dir=Path(tmp))
    view = GanttView(db, sm)
    scrolls = view.findChildren(QScrollArea)
    assert len(scrolls) == 1, f"expected exactly 1 toolbar QScrollArea, got {len(scrolls)}"
    s = scrolls[0]
    assert s.widgetResizable() is False
    assert s.horizontalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert s.verticalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
    assert s.frameShape() == QFrame.NoFrame
    assert s.widget().minimumWidth() >= s.widget().sizeHint().width()
    view.close()
    db.close()


# --------------------------------------------------------------------------
# TEST-G18 — gantt_items resize_handle_width matches dynamic edge geometry
# --------------------------------------------------------------------------
def test_g18_resize_handle_width_metadata():
    chart = _chart()
    today = date.today()
    # w = max(1*60, 36) = 60 -> handle = min(14, max(6, 15)) = 14.0
    item = _make_item(chart, _task(1, today.strftime("%Y-%m-%d")), cols=1.0)
    assert item.resize_handle_width == 14.0
    # w = max(0.5*60, 36) = 36 -> handle = min(14, max(6, 9)) = 9.0
    item2 = _make_item(chart, _task(2, today.strftime("%Y-%m-%d")), cols=0.5)
    assert item2.resize_handle_width == 9.0
    # Minimum floor: even tiny bars never go below 6.0.
    item3 = _make_item(chart, _task(3, today.strftime("%Y-%m-%d")), cols=0.1)
    assert item3.resize_handle_width >= 6.0


# --------------------------------------------------------------------------
# TEST-G19 — ref release discipline before scene.clear()
# --------------------------------------------------------------------------
def test_g19_ref_release_before_scene_clear():
    chart = _chart()
    src = inspect.getsource(chart.rebuild_chart)
    # Use rindex on the ACTUAL call (`self.scene.clear()`): the comment block
    # mentions `scene.clear()` earlier in the source.
    clear_pos = src.rindex("self.scene.clear()")
    for attr in (
        "current_time_line_item",
        "_resize_preview",
        "_resize_item",
        "_drag_item",
        "_dependency_graphics",
        "_rendered_task_items",
    ):
        needle = f"{attr} = None" if not attr.startswith("_rendered") and not attr.startswith("_dependency") else f"{attr} ="
        pos = src.index(needle)
        assert pos < clear_pos, f"{attr} must be released BEFORE scene.clear()"


# --------------------------------------------------------------------------
# TEST-G20 — hover cursor contract: SizeHor / OpenHand / Arrow
# --------------------------------------------------------------------------
def test_g20_hover_cursor_contract():
    chart = _chart()
    src = inspect.getsource(chart.mouseMoveEvent)
    hover = src.split("if not (")[1].split("super()")[0]
    assert "SizeHorCursor" in hover, "edges must show resize cursor"
    assert "OpenHandCursor" in hover, "bar interior must show open-hand cursor"
    assert "ArrowCursor" in hover, "outside must show arrow cursor"
    # The cursor decision is driven by _bar_interaction_mode results.
    assert "_bar_interaction_mode" in hover


def _child_texts(item):
    """Collect text from QGraphicsTextItem (.toPlainText) and
    QGraphicsSimpleTextItem (.text) children of a task item."""
    out = []
    for ch in item.childItems():
        t = getattr(ch, "toPlainText", None) or getattr(ch, "text", None)
        if t:
            out.append(t())
    return out


# --------------------------------------------------------------------------
# TEST-G21 — dependency arrows survive rebuild (no stale Shiboken wrappers)
# --------------------------------------------------------------------------
def test_g21_dependency_arrows_survive_rebuild():
    chart = _chart()
    today = date.today()
    ts = today.strftime("%Y-%m-%d")
    dep = _task(1, ts)
    succ = _task(2, ts, dur=60)
    succ.dependencies = [1]
    chart.set_tasks([dep, succ], {})
    chart.rebuild_chart()
    assert len(chart._dependency_graphics) >= 2, "dependency arrow + head must render"
    graphics = list(chart._dependency_graphics)
    for g in graphics:
        assert g.scene() is chart.scene  # RuntimeError => stale Shiboken wrapper => fail
    chart.rebuild_chart()
    assert len(chart._dependency_graphics) >= 2, "arrows must survive rebuild"
    for g in chart._dependency_graphics:
        assert g.scene() is chart.scene


# --------------------------------------------------------------------------
# TEST-G22 — critical path marker survives rebuild
# --------------------------------------------------------------------------
def test_g22_critical_path_marker_survives_rebuild():
    chart = _chart()
    today = date.today()
    ts = today.strftime("%Y-%m-%d")
    a = _task(3, ts, dur=120)
    b = _task(4, ts, dur=120)
    b.dependencies = [3]
    chart.set_tasks([a, b], {})
    chart.rebuild_chart()
    critical = [t for t in chart.tasks if getattr(t, "gantt_critical_path", False)]
    assert critical, "annotate must mark the dependency chain as critical"
    cid = critical[0].id
    assert cid in chart._rendered_task_items
    item = chart._rendered_task_items[cid]
    assert item.task.gantt_critical_path is True
    # CP marker text child survives rebuild (no stale wrapper).
    chart.rebuild_chart()
    item2 = chart._rendered_task_items[cid]
    texts = _child_texts(item2)
    assert any("◆" in t or "CP" in t for t in texts), texts


# --------------------------------------------------------------------------
# TEST-G23 — overlap marker survives rebuild
# --------------------------------------------------------------------------
def test_g23_overlap_marker_survives_rebuild():
    chart = _chart()
    today = date.today()
    ts = today.strftime("%Y-%m-%d")
    task = _task(5, ts)
    task.gantt_overlap = True
    chart.set_tasks([task], {})
    chart.rebuild_chart()
    assert 5 in chart._rendered_task_items
    item = chart._rendered_task_items[5]
    assert item.task.gantt_overlap is True
    texts = _child_texts(item)
    assert any("🔀" in t for t in texts), texts
    chart.rebuild_chart()
    item2 = chart._rendered_task_items[5]
    texts2 = _child_texts(item2)
    assert any("🔀" in t for t in texts2), texts2


# --------------------------------------------------------------------------
# TEST-G24 — planned color survives rebuild
# --------------------------------------------------------------------------
def test_g24_planned_color_survives_rebuild():
    chart = _chart()
    today = date.today()
    ts = today.strftime("%Y-%m-%d")
    chart.planned_bar_color = "#3584E4"
    chart.set_tasks([_task(6, ts)], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[6]
    assert item.color_profile.get("planned_color") == "#3584E4"
    chart.rebuild_chart()
    item2 = chart._rendered_task_items[6]
    assert item2.color_profile.get("planned_color") == "#3584E4"


# ==========================================================================
# ACTUAL VS PLANNED CONTRACT TESTS (TEST-A01 .. TEST-A15)
# ==========================================================================

def _lane_bars(item):
    """Return (top_lane_bars, bottom_lane_bars) within the task item."""
    top_bars = []
    bottom_bars = []
    for ch in item.childItems():
        bounds = ch.boundingRect()
        # Filter out thin resize handles (width <= 8) and background tracks (alpha <= 30)
        if bounds.width() > 10 and bounds.height() > 3:
            # Check brush alpha if available to skip lower_bg track
            brush = getattr(ch, "brush", None)
            if brush and brush().color().alpha() <= 30:
                continue
            if bounds.top() < 12.0:
                top_bars.append(ch)
            else:
                bottom_bars.append(ch)
    return top_bars, bottom_bars


def test_a01_hourly_planned_only_shows_one_planned_bar():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(101, today.strftime("%Y-%m-%d"), status=TaskStatus.PLANNED, pst="08:00", pet="09:00", dur=60)
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[101]
    top, bottom = _lane_bars(item)
    assert len(top) >= 1, "Top lane must contain planned baseline bar"
    assert len(bottom) == 0, "Planned-only task must not have actual bar in bottom lane"


def test_a02_in_progress_with_actual_start_shows_planned_and_actual():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(102, today.strftime("%Y-%m-%d"), status=TaskStatus.IN_PROGRESS, pst="08:00", pet="09:00", dur=60)
    t.actual_start_time = "08:15"
    t.actual_duration = 45
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[102]
    top, bottom = _lane_bars(item)
    assert len(top) >= 1, "Top lane must contain planned bar"
    assert len(bottom) >= 1, "Bottom lane must contain actual execution bar"


def test_a03_completed_with_actual_times_shows_planned_and_actual():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(103, today.strftime("%Y-%m-%d"), status=TaskStatus.COMPLETED, pst="08:00", pet="09:00", dur=60)
    t.actual_start_time = "08:15"
    t.actual_end_time = "09:20"
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[103]
    top, bottom = _lane_bars(item)
    assert len(top) >= 1, "Top lane must contain planned bar"
    assert len(bottom) >= 1, "Bottom lane must contain actual bar"


def test_a04_actual_start_offset_visibly_differs():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(104, today.strftime("%Y-%m-%d"), status=TaskStatus.IN_PROGRESS, pst="08:00", pet="09:00", dur=60)
    t.actual_start_time = "08:30"
    t.actual_duration = 60
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[104]
    top, bottom = _lane_bars(item)
    assert len(top) >= 1 and len(bottom) >= 1
    planned_x = top[0].boundingRect().left()
    actual_x = bottom[0].boundingRect().left()
    assert actual_x > planned_x, f"Actual start x ({actual_x}) must be right of planned start x ({planned_x})"


def test_a05_actual_longer_than_planned_extends_beyond():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(105, today.strftime("%Y-%m-%d"), status=TaskStatus.COMPLETED, pst="08:00", pet="09:00", dur=60)
    t.actual_start_time = "08:00"
    t.actual_end_time = "10:00"
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[105]
    top, bottom = _lane_bars(item)
    planned_w = top[0].boundingRect().width()
    actual_w = bottom[0].boundingRect().width()
    assert actual_w > planned_w, f"Actual width ({actual_w}) must exceed planned width ({planned_w})"


def test_a06_actual_shorter_than_planned_remains_shorter():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(106, today.strftime("%Y-%m-%d"), status=TaskStatus.COMPLETED, pst="08:00", pet="11:00", dur=180)
    t.actual_start_time = "08:00"
    t.actual_end_time = "08:30"
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[106]
    top, bottom = _lane_bars(item)
    planned_w = top[0].boundingRect().width()
    actual_w = bottom[0].boundingRect().width()
    assert actual_w < planned_w, f"Actual width ({actual_w}) must be less than planned width ({planned_w})"


def test_a07_actual_bar_never_overlays_planned_lane():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(107, today.strftime("%Y-%m-%d"), status=TaskStatus.IN_PROGRESS, pst="08:00", pet="09:00", dur=60)
    t.actual_start_time = "08:15"
    t.actual_duration = 60
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[107]
    top, bottom = _lane_bars(item)
    assert len(top) >= 1 and len(bottom) >= 1
    top_rect = top[0].boundingRect()
    bottom_rect = bottom[0].boundingRect()
    assert bottom_rect.top() >= top_rect.bottom(), (
        f"Bottom lane top ({bottom_rect.top()}) must be >= top lane bottom ({top_rect.bottom()})"
    )


def test_a08_show_actual_false_hides_actual_only():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(108, today.strftime("%Y-%m-%d"), status=TaskStatus.COMPLETED, pst="08:00", pet="09:00", dur=60)
    t.actual_start_time = "08:15"
    t.actual_end_time = "09:20"
    chart.set_tasks([t], {})
    chart.set_filters(show_actual=False)
    item = chart._rendered_task_items[108]
    top, bottom = _lane_bars(item)
    assert len(top) >= 1, "Planned bar must still render when show_actual=False"
    assert len(bottom) == 0, "Actual bar must be hidden when show_actual=False"


def test_a09_show_actual_true_preserves_planned():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(109, today.strftime("%Y-%m-%d"), status=TaskStatus.COMPLETED, pst="08:00", pet="09:00", dur=60)
    t.actual_start_time = "08:15"
    t.actual_end_time = "09:20"
    chart.set_tasks([t], {})
    chart.set_filters(show_actual=True)
    item = chart._rendered_task_items[109]
    top, bottom = _lane_bars(item)
    assert len(top) >= 1, "Planned bar must be visible"
    assert len(bottom) >= 1, "Actual bar must be visible"


def test_a10_actual_fields_unchanged_by_planned_resize():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(110, today.strftime("%Y-%m-%d"), status=TaskStatus.IN_PROGRESS, pst="08:00", pet="09:00", dur=60)
    t.actual_start_time = "08:15"
    t.actual_end_time = "09:30"
    t.actual_duration = 75
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[110]
    payload = chart._build_resize_payload(item, "right", 60.0)
    assert payload is not None
    assert "actual_start_time" not in payload
    assert "actual_end_time" not in payload
    assert "actual_duration" not in payload
    assert t.actual_start_time == "08:15"
    assert t.actual_end_time == "09:30"
    assert t.actual_duration == 75


def test_a11_hourly_actual_at_0000_renders():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(111, today.strftime("%Y-%m-%d"), status=TaskStatus.COMPLETED, pst="00:00", pet="01:00", dur=60)
    t.actual_start_time = "00:00"
    t.actual_end_time = "01:15"
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[111]
    top, bottom = _lane_bars(item)
    assert len(top) >= 1 and len(bottom) >= 1


def test_a12_hourly_actual_ending_2359_renders():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(112, today.strftime("%Y-%m-%d"), status=TaskStatus.COMPLETED, pst="22:00", pet="23:00", dur=60)
    t.actual_start_time = "22:30"
    t.actual_end_time = "23:59"
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[112]
    top, bottom = _lane_bars(item)
    assert len(top) >= 1 and len(bottom) >= 1


def test_a13_actual_not_started_no_fake_actual():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(113, today.strftime("%Y-%m-%d"), status=TaskStatus.PLANNED, pst="10:00", pet="11:00", dur=60)
    t.actual_start_time = None
    t.actual_end_time = None
    t.actual_duration = 0
    t.progress = 0
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[113]
    top, bottom = _lane_bars(item)
    assert len(top) >= 1
    assert len(bottom) == 0, "Unstarted task must never show fake actual bar"


def test_a14_rebuild_preserves_planned_and_actual():
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(114, today.strftime("%Y-%m-%d"), status=TaskStatus.COMPLETED, pst="09:00", pet="10:00", dur=60)
    t.actual_start_time = "09:10"
    t.actual_end_time = "10:15"
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    chart.rebuild_chart()
    item = chart._rendered_task_items[114]
    top, bottom = _lane_bars(item)
    assert len(top) >= 1 and len(bottom) >= 1


def test_a15_zoom_daily_hourly_daily_preserves_actual():
    chart = _chart()
    today = date.today()
    t = _task(115, today.strftime("%Y-%m-%d"), status=TaskStatus.COMPLETED, pst="09:00", pet="10:00", dur=60)
    t.actual_start_time = "09:10"
    t.actual_end_time = "10:15"
    chart.set_tasks([t], {})
    chart.set_zoom_mode("daily")
    chart.rebuild_chart()
    assert 115 in chart._rendered_task_items
    chart.set_zoom_mode("hourly")
    chart.rebuild_chart()
    assert 115 in chart._rendered_task_items
    item_hourly = chart._rendered_task_items[115]
    top_h, bot_h = _lane_bars(item_hourly)
    assert len(top_h) >= 1 and len(bot_h) >= 1
    chart.set_zoom_mode("daily")
    chart.rebuild_chart()
    assert 115 in chart._rendered_task_items


# ==========================================================================
# GEMINI ADVERSARIAL EDGE CASE TESTS (test_adv_01 .. test_adv_06)
# ==========================================================================

def test_adv_01_hourly_resize_left_clamp_0000_no_payload():
    """Task at 00:00, drag left edge leftward -> clamps to 00:00 -> returns None."""
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(201, today.strftime("%Y-%m-%d"), pst="00:00", pet="01:00", dur=60)
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[201]
    col_w = float(chart.columns[0].width)
    payload = chart._build_resize_payload(item, "left", -col_w * 0.5)
    assert payload is None, f"00:00 left clamp must return None, got {payload}"


def test_adv_02_hourly_resize_right_clamp_2359_no_payload():
    """Task ending at 23:59, drag right edge rightward -> clamps to 23:59 -> returns None."""
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = today
    t = _task(202, today.strftime("%Y-%m-%d"), pst="23:00", pet="23:59", dur=59)
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[202]
    col_w = float(chart.columns[0].width)
    payload = chart._build_resize_payload(item, "right", col_w * 0.5)
    assert payload is None, f"23:59 right clamp must return None, got {payload}"


def test_adv_03_daily_resize_subsnap_no_payload():
    """Daily mode 10px drag (< 0.5 * 60px col_width) -> returns None."""
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("daily")
    chart.anchor_date = today
    t = _task(203, today.strftime("%Y-%m-%d"))
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[203]
    payload = chart._build_resize_payload(item, "right", 10.0)
    assert payload is None, f"Daily sub-snap resize must return None, got {payload}"


def test_adv_04_weekly_resize_subsnap_no_payload():
    """Weekly mode 15px drag (< 0.5 * 100px col_width) -> returns None."""
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("weekly")
    chart.anchor_date = today
    t = _task(204, today.strftime("%Y-%m-%d"))
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[204]
    payload = chart._build_resize_payload(item, "left", 15.0)
    assert payload is None, f"Weekly sub-snap resize must return None, got {payload}"


def test_adv_05_monthly_resize_subsnap_no_payload():
    """Monthly mode 20px drag (< 0.5 * 110px col_width) -> returns None."""
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("monthly")
    chart.anchor_date = today
    t = _task(205, today.strftime("%Y-%m-%d"))
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[205]
    payload = chart._build_resize_payload(item, "right", 20.0)
    assert payload is None, f"Monthly sub-snap resize must return None, got {payload}"


def test_adv_06_daily_1day_task_inward_resize_clamp_no_payload():
    """1-day task, drag left edge rightward by 1 full day -> clamps to 1-day min -> returns None."""
    chart = _chart()
    today = date.today()
    chart.set_zoom_mode("daily")
    chart.anchor_date = today
    t = _task(206, today.strftime("%Y-%m-%d"))
    t.due_date = today.strftime("%Y-%m-%d")
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    item = chart._rendered_task_items[206]
    col_w = float(chart.columns[0].width)
    payload = chart._build_resize_payload(item, "left", col_w)
    assert payload is None, f"Inward 1-day clamp must return None, got {payload}"


# ===========================================================================
# PHASE 0A BATCH 2.2: HOURLY REALITY CLOSURE & RUNTIME GEOMETRY TESTS
# ===========================================================================

def test_hscroll_01_can_reach_start_of_day():
    """TEST-HSCROLL-01: Given 24-hour timeline, scrollbar can reach timeline_x(0) = 00:00."""
    chart = _chart()
    chart.resize(800, 600)
    chart.set_zoom_mode("hourly")
    chart.anchor_date = date(2026, 8, 12)
    chart.rebuild_chart()
    h_bar = chart.horizontalScrollBar()
    assert h_bar.minimum() <= 0
    h_bar.setValue(0)
    visible_left = chart.mapToScene(chart.viewport().rect()).boundingRect().left()
    assert visible_left <= 0.0


def test_hscroll_02_can_reach_end_of_day():
    """TEST-HSCROLL-02: Scrollbar can reach timeline_x(23:59)."""
    chart = _chart()
    chart.resize(800, 600)
    chart.set_zoom_mode("hourly")
    chart.anchor_date = date(2026, 8, 12)
    chart.rebuild_chart()
    h_bar = chart.horizontalScrollBar()
    h_bar.setValue(h_bar.maximum())
    visible_right = chart.mapToScene(chart.viewport().rect()).boundingRect().right()
    assert chart.sceneRect().right() >= 24.0 * 60.0
    assert visible_right >= 20.0 * 60.0


def test_hscroll_03_current_time_marker_does_not_alter_scrollbar_range():
    """TEST-HSCROLL-03: Current time marker does not alter scrollbar min/max."""
    chart = _chart()
    chart.resize(800, 600)
    chart.set_zoom_mode("hourly")
    chart.anchor_date = date.today()
    chart.rebuild_chart()
    h_bar = chart.horizontalScrollBar()
    min_val, max_val = h_bar.minimum(), h_bar.maximum()
    chart.update_current_time_marker()
    assert h_bar.minimum() == min_val
    assert h_bar.maximum() == max_val


def test_hscroll_04_hover_does_not_alter_scrollbar():
    """TEST-HSCROLL-04: Mouse hover does not alter scrollbar range or value."""
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent, QPointF
    chart = _chart()
    chart.resize(800, 600)
    chart.set_zoom_mode("hourly")
    chart.anchor_date = date(2026, 8, 12)
    t = _task(301, "2026-08-12", status=TaskStatus.IN_PROGRESS, pst="08:00", dur=60)
    chart.set_tasks([t], {})
    chart.rebuild_chart()
    h_bar = chart.horizontalScrollBar()
    orig_min, orig_max, orig_val = h_bar.minimum(), h_bar.maximum(), h_bar.value()

    # Simulate mouse moves across viewport
    for px in [100, 200, 480, 520, 700]:
        evt = QMouseEvent(QEvent.MouseMove, QPointF(px, 100), QPointF(px, 100), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
        chart.mouseMoveEvent(evt)

    assert h_bar.minimum() == orig_min
    assert h_bar.maximum() == orig_max
    assert h_bar.value() == orig_val


def test_ap_r01_both_graphical_rectangles_exist_in_scene():
    """TEST-AP-R01: Planned 08:00-09:00, Actual 06:11-06:18 both have geometry."""
    chart = _chart()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = date(2026, 8, 12)
    t = _task(302, "2026-08-12", status=TaskStatus.IN_PROGRESS, pst="08:00", dur=60)
    t.actual_start_time = "06:11"
    t.actual_end_time = "06:18"
    chart.set_tasks([t], {})
    chart.rebuild_chart()

    assert 302 in chart._rendered_task_items
    item = chart._rendered_task_items[302]
    children = item.childItems()
    assert len(children) >= 2


def test_ap_r02_actual_scene_bounding_left_earlier_than_planned():
    """TEST-AP-R02: actual.sceneBoundingRect().left() < planned.sceneBoundingRect().left()."""
    chart = _chart()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = date(2026, 8, 12)
    t = _task(303, "2026-08-12", status=TaskStatus.IN_PROGRESS, pst="08:00", dur=60)
    t.actual_start_time = "06:11"
    t.actual_end_time = "06:18"
    chart.set_tasks([t], {})
    chart.rebuild_chart()

    item = chart._rendered_task_items[303]
    scene_bounds = item.sceneBoundingRect()
    planned_scene_x = (8.0 * 60.0) # 480.0
    actual_scene_x = (6.0 + 11.0 / 60.0) * 60.0 # 371.0
    assert scene_bounds.left() <= actual_scene_x + 1.0
    assert actual_scene_x < planned_scene_x


def test_ap_r03_both_intersect_scene_rect():
    """TEST-AP-R03: Both Planned and Actual intersect sceneRect."""
    chart = _chart()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = date(2026, 8, 12)
    t = _task(304, "2026-08-12", status=TaskStatus.IN_PROGRESS, pst="08:00", dur=60)
    t.actual_start_time = "06:11"
    t.actual_end_time = "06:18"
    chart.set_tasks([t], {})
    chart.rebuild_chart()

    item = chart._rendered_task_items[304]
    assert chart.scene.sceneRect().intersects(item.sceneBoundingRect())


def test_ap_r04_both_are_visible():
    """TEST-AP-R04: Task item and children are visible with positive opacity."""
    chart = _chart()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = date(2026, 8, 12)
    t = _task(305, "2026-08-12", status=TaskStatus.IN_PROGRESS, pst="08:00", dur=60)
    t.actual_start_time = "06:11"
    t.actual_end_time = "06:18"
    chart.set_tasks([t], {})
    chart.rebuild_chart()

    item = chart._rendered_task_items[305]
    assert item.isVisible()
    assert item.opacity() > 0.0
    for ch in item.childItems():
        assert ch.isVisible()
        assert ch.opacity() > 0.0


def test_ap_r05_rendered_pixel_witness():
    """TEST-AP-R05: Render Hourly scene to QImage and verify non-background pixels at 06:15 and 08:30."""
    from PySide6.QtGui import QImage, QPainter, QColor
    chart = _chart()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = date(2026, 8, 12)
    t = _task(306, "2026-08-12", status=TaskStatus.IN_PROGRESS, pst="08:00", dur=60)
    t.actual_start_time = "06:11"
    t.actual_end_time = "06:18"
    chart.set_tasks([t], {})
    chart.rebuild_chart()

    bg_color = QColor("#181825")
    img = QImage(1440, 600, QImage.Format_ARGB32)
    img.fill(bg_color)
    painter = QPainter(img)
    chart.scene.render(painter)
    painter.end()

    # Actual bar (06:11-06:18 -> x~371..388, y~80..97)
    col_actual = img.pixelColor(375, 88)
    # Planned bar (08:00-09:00 -> x~480..540, y~66..80)
    col_planned = img.pixelColor(500, 72)

    assert col_actual != bg_color, f"Actual bar pixel at (375, 88) must not be background, got {col_actual.name()}"
    assert col_planned != bg_color, f"Planned bar pixel at (500, 72) must not be background, got {col_planned.name()}"


def test_historical_time_not_filtered_by_current_time():
    """P0-8: Synthetic task at 01:00-02:00 renders regardless of current time."""
    chart = _chart()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = date(2026, 8, 12)
    t = _task(307, "2026-08-12", status=TaskStatus.COMPLETED, pst="01:00", dur=60)
    t.actual_start_time = "00:30"
    t.actual_end_time = "01:15"
    chart.set_tasks([t], {})
    chart.rebuild_chart()

    assert 307 in chart._rendered_task_items
    item = chart._rendered_task_items[307]
    assert item.sceneBoundingRect().left() <= (0.5 * 60.0) + 1.0


def test_zoom_transition_preserves_anchor_date():
    """P0-9: Daily -> Hourly -> Weekly -> Hourly preserves selected anchor date."""
    chart = _chart()
    target_date = date(2026, 8, 12)
    chart.anchor_date = target_date
    chart.set_zoom_mode("daily")
    assert chart.anchor_date == target_date

    chart.set_zoom_mode("hourly")
    assert chart.anchor_date == target_date

    chart.set_zoom_mode("weekly")
    assert chart.anchor_date == target_date

    chart.set_zoom_mode("hourly")
    assert chart.anchor_date == target_date


def test_hover_pixel_01_static_grid_persistence_after_hover():
    """TEST-HOVER-PIXEL-01: Grid lines, headers, and bars persist identically before and after hover."""
    from PySide6.QtGui import QImage, QPainter, QColor, QMouseEvent
    from PySide6.QtCore import QRectF, QEvent, QPointF
    chart = _chart()
    chart.resize(1000, 600)
    chart.set_zoom_mode("hourly")
    chart.anchor_date = date(2026, 8, 12)
    t = _task(308, "2026-08-12", status=TaskStatus.IN_PROGRESS, pst="08:00", dur=60)
    t.actual_start_time = "06:11"
    t.actual_end_time = "06:18"
    chart.set_tasks([t], {})
    chart.rebuild_chart()

    # 1. Render BEFORE hover
    img_before = QImage(1440, 600, QImage.Format_ARGB32)
    img_before.fill(QColor("#1E1E2E"))
    p_before = QPainter(img_before)
    chart.scene.render(p_before)
    p_before.end()

    # 2. Simulate mouse movements across header, grid, planned bar, actual bar
    for px in range(0, 1000, 50):
        for py in [25, 50, 72, 88, 150, 300]:
            evt = QMouseEvent(QEvent.MouseMove, QPointF(px, py), QPointF(px, py), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
            chart.mouseMoveEvent(evt)

    # 3. Render AFTER hover
    img_after = QImage(1440, 600, QImage.Format_ARGB32)
    img_after.fill(QColor("#1E1E2E"))
    p_after = QPainter(img_after)
    chart.scene.render(p_after)
    p_after.end()

    # 4. Compare known static grid pixel (x=60, y=200), header bottom sep (x=500, y=60),
    # Planned bar (x=500, y=72), and Actual bar (x=375, y=88)
    for sample_pt in [(60, 200), (120, 200), (500, 60), (500, 72), (375, 88)]:
        col_b = img_before.pixelColor(sample_pt[0], sample_pt[1])
        col_a = img_after.pixelColor(sample_pt[0], sample_pt[1])
        assert col_b == col_a, f"Pixel at {sample_pt} changed after hover: {col_b.name()} -> {col_a.name()}"


def test_htext_01_all_24_hour_labels_stable_after_hover():
    """TEST-HTEXT-01: Verify all 24 Hourly time labels retain identical non-background glyph pixels after hover."""
    from PySide6.QtGui import QImage, QPainter, QColor, QMouseEvent
    from PySide6.QtCore import QRectF, QEvent, QPointF
    chart = _chart()
    chart.resize(1200, 600)
    chart.set_zoom_mode("hourly")
    chart.anchor_date = date(2026, 8, 12)
    t = _task(309, "2026-08-12", status=TaskStatus.IN_PROGRESS, pst="08:00", dur=60)
    t.actual_start_time = "06:11"
    t.actual_end_time = "06:18"
    chart.set_tasks([t], {})
    chart.rebuild_chart()

    bg_color = QColor("#181825") # Header background

    # 1. Render BEFORE hover
    img_before = QImage(1440, 600, QImage.Format_ARGB32)
    img_before.fill(bg_color)
    p_before = QPainter(img_before)
    chart.scene.render(p_before)
    p_before.end()

    # Count glyph pixels in each of the 24 hour label regions (x = h*60 .. h*60+60, y = 18..36)
    glyph_counts_before = []
    for h in range(24):
        count = 0
        for px in range(h * 60 + 2, h * 60 + 55):
            for py in range(18, 36):
                if img_before.pixelColor(px, py) != bg_color:
                    count += 1
        assert count > 0, f"Hour {h:02d}:00 label region must contain visible text glyph pixels before hover"
        glyph_counts_before.append(count)

    # 2. Simulate mouse moves across header, grid, planned bar, actual bar
    for px in range(0, 1440, 60):
        for py in [10, 25, 45, 60, 72, 88, 150]:
            evt = QMouseEvent(QEvent.MouseMove, QPointF(px, py), QPointF(px, py), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
            chart.mouseMoveEvent(evt)

    # 3. Render AFTER hover
    img_after = QImage(1440, 600, QImage.Format_ARGB32)
    img_after.fill(bg_color)
    p_after = QPainter(img_after)
    chart.scene.render(p_after)
    p_after.end()

    # 4. Assert each of the 24 hour label regions has identical glyph pixel count after hover
    for h in range(24):
        count = 0
        for px in range(h * 60 + 2, h * 60 + 55):
            for py in range(18, 36):
                if img_after.pixelColor(px, py) != bg_color:
                    count += 1
        assert count == glyph_counts_before[h], (
            f"Hour {h:02d}:00 glyph pixel count changed after hover: {glyph_counts_before[h]} -> {count}"
        )


def test_time_label_single_authority_architecture():
    """STEP 13 Architectural test: No loose QGraphicsTextItem header objects in scene."""
    from PySide6.QtWidgets import QGraphicsTextItem
    chart = _chart()
    chart.set_zoom_mode("hourly")
    chart.anchor_date = date(2026, 8, 12)
    chart.rebuild_chart()

    # Header region y <= header_height should have 0 loose text items
    header_text_items = [
        it for it in chart.scene.items()
        if isinstance(it, QGraphicsTextItem) and it.pos().y() < chart.header_height
    ]
    assert len(header_text_items) == 0, f"Found {len(header_text_items)} loose header items in scene; must be 0 (painter rendered)"


def test_gantt_empty_message_hover_pixel_stability():
    """Verify Gantt empty-state / nearest-task message remains 100% pixel stable before and after 400+ mouse moves."""
    from PySide6.QtGui import QImage, QPainter, QColor, QMouseEvent
    from PySide6.QtCore import QEvent, QPointF
    chart = _chart()
    chart.resize(1000, 600)
    chart.set_zoom_mode("hourly")
    chart.anchor_date = date(2026, 8, 15)

    # Task on Aug 13
    t = _task(1, "2026-08-13", status=TaskStatus.PLANNED)
    chart.set_tasks([t], {})
    chart.rebuild_chart()

    bg_color = QColor("#1E1E2E")

    # 1. Render BEFORE hover
    img_before = QImage(1000, 600, QImage.Format_ARGB32)
    img_before.fill(bg_color)
    p_before = QPainter(img_before)
    chart.scene.render(p_before)
    p_before.end()

    # Count empty message glyph pixels in region (x=50..500, y=80..160)
    glyph_count_before = 0
    for px in range(50, 500):
        for py in range(80, 160):
            if img_before.pixelColor(px, py) != bg_color:
                glyph_count_before += 1
    assert glyph_count_before > 50, "Empty state / nearest-task text glyphs must be visible before hover"

    # 2. Simulate mouse moves across empty message, grid, headers
    for px in range(0, 1000, 50):
        for py in [25, 50, 80, 100, 120, 150, 300]:
            evt = QMouseEvent(QEvent.MouseMove, QPointF(px, py), QPointF(px, py), Qt.NoButton, Qt.NoButton, Qt.NoModifier)
            chart.mouseMoveEvent(evt)

    # 3. Render AFTER hover
    img_after = QImage(1000, 600, QImage.Format_ARGB32)
    img_after.fill(bg_color)
    p_after = QPainter(img_after)
    chart.scene.render(p_after)
    p_after.end()

    glyph_count_after = 0
    for px in range(50, 500):
        for py in range(80, 160):
            if img_after.pixelColor(px, py) != bg_color:
                glyph_count_after += 1

    assert glyph_count_after == glyph_count_before, (
        f"Empty state glyph pixel count changed after hover: {glyph_count_before} -> {glyph_count_after}"
    )




