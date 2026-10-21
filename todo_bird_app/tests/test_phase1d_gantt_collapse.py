
from pathlib import Path
from types import SimpleNamespace

from todo_bird_app.views.gantt_view import GanttView


def _row(key, depth, summary=False):
    return SimpleNamespace(
        title=key,
        gantt_depth=depth,
        gantt_wbs_key=key,
        gantt_is_summary=summary,
        gantt_collapsed=False,
    )


def test_collapse_hides_only_descendants():
    view = SimpleNamespace(
        _gantt_collapsed_keys={"task:A"},
    )

    items = [
        _row("task:A", 0, True),
        _row("subtask:B", 1, True),
        _row("subtask:C", 2, False),
        _row("task:D", 0, True),
        _row("subtask:E", 1, False),
    ]

    visible = GanttView._apply_gantt_collapse_visibility(
        view,
        items,
    )

    assert [x.gantt_wbs_key for x in visible] == [
        "task:A",
        "task:D",
        "subtask:E",
    ]

    assert visible[0].gantt_collapsed is True
    assert visible[1].gantt_collapsed is False


def test_nested_collapse_respects_parent_order():
    view = SimpleNamespace(
        _gantt_collapsed_keys={"subtask:B"},
    )

    items = [
        _row("task:A", 0, True),
        _row("subtask:B", 1, True),
        _row("subtask:C", 2, False),
        _row("subtask:D", 1, False),
    ]

    visible = GanttView._apply_gantt_collapse_visibility(
        view,
        items,
    )

    assert [x.gantt_wbs_key for x in visible] == [
        "task:A",
        "subtask:B",
        "subtask:D",
    ]


def test_inbox_rows_are_not_affected_by_project_collapse():
    view = SimpleNamespace(
        _gantt_collapsed_keys={"task:A"},
    )

    items = [
        _row("task:A", 0, True),
        _row("subtask:B", 1, False),
        _row("inbox-task:91", 0, False),
    ]

    visible = GanttView._apply_gantt_collapse_visibility(
        view,
        items,
    )

    assert [x.gantt_wbs_key for x in visible] == [
        "task:A",
        "inbox-task:91",
    ]


def test_progress_and_scene_lifetime_contracts():
    items = Path(
        "todo_bird_app/gantt/gantt_items.py"
    ).read_text()

    chart = Path(
        "todo_bird_app/gantt/gantt_chart.py"
    ).read_text()

    assert "PHASE 1D SUMMARY PROGRESS INDICATOR" in items
    assert "gantt_rollup_progress" in items

    start = chart.index("def rebuild_chart")

    refs = [
        chart.index(
            "self.current_time_line_item = None",
            start,
        ),
        chart.index(
            "self._resize_preview = None",
            start,
        ),
        chart.index(
            "self._resize_item = None",
            start,
        ),
        chart.index(
            "self._drag_item = None",
            start,
        ),
        chart.index(
            "self._dependency_graphics = []",
            start,
        ),
        chart.index(
            "self._rendered_task_items = {}",
            start,
        ),
        chart.index(
            "self.scene.clear()",
            start,
        ),
    ]

    assert refs == sorted(refs)
