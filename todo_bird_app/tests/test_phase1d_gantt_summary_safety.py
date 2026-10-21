
from pathlib import Path


def test_phase1d_summary_interaction_contract():
    chart = Path(
        "todo_bird_app/gantt/gantt_chart.py"
    ).read_text()

    items = Path(
        "todo_bird_app/gantt/gantt_items.py"
    ).read_text()

    assert "def _schedule_editable_leaf_authority(" in chart
    assert 'getattr(task, "gantt_read_only", False)' in chart
    assert 'getattr(task, "gantt_is_summary", False)' in chart

    # Existing scheduling authority must still be called for leaves.
    assert "return self._schedule_editable_leaf_authority(item)" in chart

    # Derived summaries cannot advertise resize.
    assert "left_handle.setVisible(" in items
    assert "right_handle.setVisible(" in items
    assert "not is_read_only" in items


def test_phase1d_scene_lifetime_contract_untouched():
    chart = Path(
        "todo_bird_app/gantt/gantt_chart.py"
    ).read_text()

    i_time = chart.index(
        "self.current_time_line_item = None",
        chart.index("def rebuild_chart"),
    )
    i_resize_preview = chart.index(
        "self._resize_preview = None",
        i_time,
    )
    i_resize_item = chart.index(
        "self._resize_item = None",
        i_resize_preview,
    )
    i_drag = chart.index(
        "self._drag_item = None",
        i_resize_item,
    )
    i_deps = chart.index(
        "self._dependency_graphics = []",
        i_drag,
    )
    i_rendered = chart.index(
        "self._rendered_task_items = {}",
        i_deps,
    )
    i_clear = chart.index(
        "self.scene.clear()",
        i_rendered,
    )

    assert (
        i_time
        < i_resize_preview
        < i_resize_item
        < i_drag
        < i_deps
        < i_rendered
        < i_clear
    )
