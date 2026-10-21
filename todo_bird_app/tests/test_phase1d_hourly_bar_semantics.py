
from pathlib import Path


def test_short_hourly_duration_is_not_implicit_milestone():
    src = Path(
        "todo_bird_app/gantt/gantt_items.py"
    ).read_text()

    assert "Milestone is a BUSINESS SEMANTIC" in src

    # Regression: visual width must never define business milestone.
    assert (
        "is_milestone = (self.duration_cols <= 0.5)"
        not in src
    )

    assert "gantt_is_milestone" in src


def test_hourly_timed_count_does_not_fabricate_multiday_span():
    src = Path(
        "todo_bird_app/gantt/gantt_chart.py"
    ).read_text()

    start = src.index(
        "def _hourly_timed_task_count"
    )
    end = src.index(
        "def _nearest_scheduled_date",
        start,
    )
    block = src[start:end]

    helper_start = src.index(
        "def _gantt_planned_date_range"
    )
    helper_end = src.index(
        "def _hourly_visible_task_count",
        helper_start,
    )
    helper_block = src[helper_start:helper_end]

    assert "_gantt_planned_date_range(task)" in block
    assert "gantt_planned_start" in helper_block
    assert "cpm_earliest_start" in helper_block
    assert "self.anchor_date" in block
    assert "span_start" not in block
    assert "span_end" not in block
    assert "has_timed_plan = True" not in block


def test_chart_is_hourly_planned_visibility_authority():
    chart = Path(
        "todo_bird_app/gantt/gantt_chart.py"
    ).read_text()

    items = Path(
        "todo_bird_app/gantt/gantt_items.py"
    ).read_text()

    assert (
        "task.gantt_hourly_has_planned_segment"
        in chart
    )

    assert (
        "Chart is the single Hourly geometry/date authority."
        in items
    )


def test_short_bar_geometry_remains_allowed():
    src = Path(
        "todo_bird_app/gantt/gantt_chart.py"
    ).read_text()

    # 15-minute-class geometry must remain legal.
    assert "dur_cols = max(" in src
    assert "0.25," in src


def test_scene_lifetime_guard_untouched():
    src = Path(
        "todo_bird_app/gantt/gantt_chart.py"
    ).read_text()

    start = src.index("def rebuild_chart")

    sequence = [
        "self.current_time_line_item = None",
        "self._resize_preview = None",
        "self._resize_item = None",
        "self._drag_item = None",
        "self._dependency_graphics = []",
        "self._rendered_task_items = {}",
        "self.scene.clear()",
    ]

    positions = [
        src.index(token, start)
        for token in sequence
    ]

    assert positions == sorted(positions)
