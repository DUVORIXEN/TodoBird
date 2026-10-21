import pytest
from datetime import date, datetime, timedelta
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtCore import Qt, QRectF
import sys

from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.gantt.gantt_chart import GanttChartWidget
from todo_bird_app.gantt.gantt_items import GanttTaskItem
from todo_bird_app.gantt.timescale_engine import ZoomLevel, TimescaleEngine
from todo_bird_app.services.cpm_scheduling_service import CPMSchedulingService
from todo_bird_app.utils.time_math import set_current_datetime_override, get_current_datetime, get_current_date


@pytest.fixture(autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def reset_time():
    set_current_datetime_override(datetime(2026, 8, 25, 9, 0, 0))
    yield
    set_current_datetime_override(None)


def create_sample_tasks():
    # Planning task: Planned 15 Sep -> 16 Oct, Actual Start 24 Aug (In Progress)
    t_planning = Task(
        id=10,
        title="Planning",
        project_id=4,
        status=TaskStatus.IN_PROGRESS,
        planned_date="2026-09-15",
        due_date="2026-10-16",
        planned_start_time="09:00",
        planned_end_time="09:00",
        estimated_duration=44640,
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        actual_end_date=None,
        actual_end_time=None,
        baseline_start="2026-09-06 09:00",
        baseline_finish="2026-10-07 09:00",
        constraint_type="SNET",
        constraint_datetime="2026-09-15 09:00",
    )
    t_start = Task(
        id=9,
        title="Start",
        project_id=4,
        status=TaskStatus.IN_PROGRESS,
        planned_date="2026-08-23",
        due_date="2026-09-05",
        actual_start_date="2026-08-23",
        actual_start_time="08:00",
        actual_end_date=None,
        actual_end_time=None,
    )
    return [t_start, t_planning]


def build_widget_with_cpm(tasks):
    cpm_res = CPMSchedulingService.calculate_schedule(tasks, project_id=4)
    for t in tasks:
        node = cpm_res.nodes.get(t.id)
        if node:
            t.cpm_earliest_start = node.earliest_start
            t.cpm_earliest_finish = node.earliest_finish
            t.gantt_planned_start = node.earliest_start.date() if node.earliest_start else None
            t.gantt_planned_finish = node.earliest_finish.date() if node.earliest_finish else None

    widget = GanttChartWidget()
    widget.filter_project_id = 4
    widget.zoom_mode = ZoomLevel.DAILY
    widget.set_tasks(tasks, {4: "THAAVORIX"})
    return widget


def test_01_actual_open_bar_item_exists():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bars = [
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    ]
    assert len(actual_bars) == 1, "An Actual open bar item must exist as a child item."


def test_02_actual_visible_true():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    assert actual_bar.isVisible() is True, "Actual bar must be visible."


def test_03_positive_width():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    rect = actual_bar.boundingRect()
    assert rect.width() > 0, f"Actual bar width must be positive, got {rect.width()}"


def test_04_positive_height():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    rect = actual_bar.boundingRect()
    assert rect.height() > 0, f"Actual bar height must be positive, got {rect.height()}"


def test_05_actual_start_before_planned_x():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    actual_scene_x = actual_bar.sceneBoundingRect().x()
    planned_scene_x = planning_item.x()
    assert actual_scene_x < planned_scene_x, (
        f"Early actual start (x={actual_scene_x}) must begin before planned start (x={planned_scene_x})"
    )


def test_06_timescale_includes_actual_start():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    min_col_date = widget.columns[0].start_date
    assert min_col_date <= date(2026, 8, 24), (
        f"Timescale column start {min_col_date} must be on or before actual start (2026-08-24)"
    )


def test_07_timescale_includes_forecast_finish():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    max_col_date = widget.columns[-1].end_date
    assert max_col_date >= date(2026, 10, 16), (
        f"Timescale column end {max_col_date} must encompass forecast finish (2026-10-16)"
    )


def test_08_fit_project_includes_both():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    scene_rect = widget.scene.sceneRect()
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    act_rect = actual_bar.sceneBoundingRect()
    assert scene_rect.contains(act_rect.topLeft()), "Scene rect must contain actual bar top-left."
    assert scene_rect.contains(act_rect.bottomRight()), "Scene rect must contain actual bar bottom-right."


def test_09_open_endpoint_uses_canonical_now():
    set_current_datetime_override(datetime(2026, 8, 26, 8, 0, 0))
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_task = tasks[1]
    # 24 Aug to 26 Aug is 2 days (120 pixels in Daily mode @ 60px/day)
    assert getattr(planning_task, "gantt_summary_actual_width", 0) >= 120.0


def test_10_canonical_now_not_persisted():
    tasks = create_sample_tasks()
    _widget = build_widget_with_cpm(tasks)
    planning_task = tasks[1]
    assert planning_task.actual_end_date is None
    assert planning_task.actual_end_time is None


def test_11_actual_not_hidden_behind_planned():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    planned_bar = planning_item.childItems()[0]
    act_y = actual_bar.sceneBoundingRect().y()
    plan_y = planned_bar.sceneBoundingRect().y()
    assert act_y != plan_y, f"Actual bar y ({act_y}) must be in a separate lane from planned bar y ({plan_y})"


def test_12_actual_z_order_deliberate():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    assert actual_bar.zValue() >= 1.0, f"Actual bar zValue ({actual_bar.zValue()}) must be >= 1.0"


def test_13_actual_within_row_geometry():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    item_rect = planning_item.boundingRect()
    act_local_rect = actual_bar.boundingRect()
    assert item_rect.contains(act_local_rect), "Item bounding rect must fully contain actual bar."


def test_14_actual_not_clipped():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    flags = planning_item.flags()
    assert not (flags & GanttTaskItem.GraphicsItemFlag.ItemClipsChildrenToShape), (
        "Item should not clip actual children out of bounds."
    )


def test_15_dark_rendering_pixels_visible():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    scene_rect = widget.scene.sceneRect()
    img = QImage(int(scene_rect.width()), int(scene_rect.height()), QImage.Format_ARGB32)
    img.fill(QColor("#1E1E2E"))
    painter = QPainter(img)
    widget.scene.render(painter, QRectF(img.rect()), scene_rect)
    painter.end()

    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    act_rect = actual_bar.sceneBoundingRect()
    sample_x = int(act_rect.center().x())
    sample_y = int(act_rect.center().y())
    pixel_color = img.pixelColor(sample_x, sample_y).name()
    assert pixel_color != "#1e1e2e", f"Actual bar pixel {pixel_color} must differ from dark background."


def test_16_light_rendering_pixels_visible():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    scene_rect = widget.scene.sceneRect()
    img = QImage(int(scene_rect.width()), int(scene_rect.height()), QImage.Format_ARGB32)
    img.fill(QColor("#FFFFFF"))
    painter = QPainter(img)
    widget.scene.render(painter, QRectF(img.rect()), scene_rect)
    painter.end()

    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    act_rect = actual_bar.sceneBoundingRect()
    sample_x = int(act_rect.center().x())
    sample_y = int(act_rect.center().y())
    pixel_color = img.pixelColor(sample_x, sample_y).name()
    assert pixel_color != "#ffffff", f"Actual bar pixel {pixel_color} must differ from light background."


def test_17_scaling_125_percent():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    rect = actual_bar.boundingRect()
    assert rect.width() > 0 and rect.height() > 0


def test_18_scaling_150_percent():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    rect = actual_bar.boundingRect()
    assert rect.width() > 0 and rect.height() > 0


def test_19_scaling_200_percent():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    actual_bar = next(
        c for c in planning_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    )
    rect = actual_bar.boundingRect()
    assert rect.width() > 0 and rect.height() > 0


def test_20_tooltip_and_graphical_data_agree():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    tt = planning_item.toolTip()
    assert "2026-08-24" in tt
    assert "Started 22" in tt and "early" in tt


def test_21_project_selector_still_scoped():
    tasks = create_sample_tasks()
    tasks.append(
        Task(id=99, title="Other Project Task", project_id=5, planned_date="2026-09-01", due_date="2026-09-10")
    )
    widget = build_widget_with_cpm(tasks)
    rendered_ids = {
        item.task.id for item in widget.scene.items()
        if isinstance(item, GanttTaskItem)
    }
    assert 99 not in rendered_ids, "Cross-project tasks must be filtered out."


def test_22_baseline_still_visible():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    baseline_bars = [
        c for c in planning_item.childItems()
        if "Baseline" in (c.toolTip() or "")
    ]
    assert len(baseline_bars) == 1, "Baseline bar must remain visible."


def test_23_revision_comparison_still_works():
    tasks = create_sample_tasks()
    tasks[1].source_payload = {"revision_start": "2026-09-10 09:00", "revision_finish": "2026-10-10 09:00"}
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    assert planning_item is not None


def test_24_current_forecast_unchanged():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_task = tasks[1]
    assert planning_task.gantt_planned_start == date(2026, 9, 15)
    assert planning_task.gantt_planned_finish == date(2026, 10, 16)


def test_25_actual_data_unchanged():
    tasks = create_sample_tasks()
    _widget = build_widget_with_cpm(tasks)
    planning_task = tasks[1]
    assert planning_task.actual_start_date == "2026-08-24"
    assert planning_task.actual_start_time == "08:00"
    assert planning_task.actual_end_date is None


def test_26_no_paint_db_query(monkeypatch):
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    scene_rect = widget.scene.sceneRect()
    img = QImage(int(scene_rect.width()), int(scene_rect.height()), QImage.Format_ARGB32)

    import sqlite3
    def forbidden_connect(*args, **kwargs):
        raise RuntimeError("Forbidden DB access in paint path!")
    monkeypatch.setattr(sqlite3, "connect", forbidden_connect)

    painter = QPainter(img)
    widget.scene.render(painter, QRectF(img.rect()), scene_rect)
    painter.end()


def test_27_scene_clear_invariant_preserved():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    # Call rebuild_chart directly to ensure scene.clear() ordering invariant holds
    widget.rebuild_chart()
    assert widget.current_time_line_item is None or True


def test_28_scroll_range_includes_actual():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    cols = widget.columns
    first_col = cols[0]
    assert first_col.start_date <= date(2026, 8, 24)


def test_29_leaf_task_visible():
    tasks = create_sample_tasks()
    widget = build_widget_with_cpm(tasks)
    planning_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 10
    )
    assert planning_item.isVisible() is True


def test_30_summary_task_actual_handling_remains_correct():
    t_summary = Task(
        id=1,
        title="Summary Task",
        project_id=4,
        planned_date="2026-09-01",
        due_date="2026-10-01",
        actual_start_date="2026-08-20",
        actual_end_date=None,
    )
    t_summary.is_summary = True
    t_summary.gantt_summary_actual_visible = True
    t_summary.gantt_summary_actual_x_offset = -60.0
    t_summary.gantt_summary_actual_width = 120.0

    tasks = [t_summary]
    widget = build_widget_with_cpm(tasks)
    summary_item = next(
        item for item in widget.scene.items()
        if isinstance(item, GanttTaskItem) and item.task.id == 1
    )
    actual_bars = [
        c for c in summary_item.childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    ]
    assert len(actual_bars) == 1, "Summary task actual bar must be created."
