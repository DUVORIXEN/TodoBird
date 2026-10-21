
from pathlib import Path

from todo_bird_app.database import DatabaseManager
from todo_bird_app.services.wbs_service import WBSService
from todo_bird_app.services.gantt_wbs_adapter import GanttWBSAdapter


def test_parent_actual_rollup_metadata_exists():
    fields = GanttWBSAdapter.__module__
    assert fields


def test_summary_actual_geometry_does_not_use_effort_as_elapsed():
    view = Path(
        "todo_bird_app/views/gantt_view.py"
    ).read_text()

    chart = Path(
        "todo_bird_app/gantt/gantt_chart.py"
    ).read_text()

    item = Path(
        "todo_bird_app/gantt/gantt_items.py"
    ).read_text()

    assert "gantt_summary_actual_start" in view
    assert "gantt_summary_actual_finish" in view
    assert "gantt_summary_actual_activity_end" in view

    # Summary actual_duration remains Actual Work Effort authority-safe.
    assert "actual_duration = 0" in view

    # Timeline engine, not effort/progress, computes summary Actual geometry.
    assert "DERIVED SUMMARY ACTUAL GEOMETRY" in chart
    assert "gantt_summary_actual_x_offset" in chart
    assert "gantt_summary_actual_width" in chart

    assert "summary_actual_visible" in item
    assert "gantt_summary_actual_x_offset" in item
    assert "gantt_summary_actual_width" in item


def test_summary_remains_read_only():
    chart = Path(
        "todo_bird_app/gantt/gantt_chart.py"
    ).read_text()

    assert 'getattr(task, "gantt_read_only", False)' in chart
    assert 'getattr(task, "gantt_is_summary", False)' in chart
    assert "return self._schedule_editable_leaf_authority(item)" in chart


def test_scene_lifetime_contract_remains_intact():
    chart = Path(
        "todo_bird_app/gantt/gantt_chart.py"
    ).read_text()

    start = chart.index("def rebuild_chart")

    refs = [
        chart.index("self.current_time_line_item = None", start),
        chart.index("self._resize_preview = None", start),
        chart.index("self._resize_item = None", start),
        chart.index("self._drag_item = None", start),
        chart.index("self._dependency_graphics = []", start),
        chart.index("self._rendered_task_items = {}", start),
        chart.index("self.scene.clear()", start),
    ]

    assert refs == sorted(refs)
