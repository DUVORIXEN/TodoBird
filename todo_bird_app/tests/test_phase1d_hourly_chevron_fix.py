
from pathlib import Path


def test_nested_chevron_hitbox_is_not_depth_shifted():
    src = Path(
        "todo_bird_app/gantt/gantt_left_pane.py"
    ).read_text()

    assert "row_rect = self.visualRect(index)" in src
    assert "hit_left = row_rect.left() + 4" in src
    assert "hit_right = row_rect.left() + 38" in src

    # Defect must not return.
    assert "depth * 18" not in src


def test_hourly_does_not_fabricate_intermediate_planned_segments():
    src = Path(
        "todo_bird_app/gantt/gantt_chart.py"
    ).read_text()

    assert (
        "PHASE 1D — HOURLY PLANNED-DAY SEGMENT"
        in src
    )

    start = src.index(
        "PHASE 1D — HOURLY PLANNED-DAY SEGMENT"
    )
    end = src.index(
        "ACTUAL-ONLY ACTIVE DAY FALLBACK",
        start,
    )
    planned_block = src[start:end]

    assert "planned_active_today" in planned_block
    assert "p == self.anchor_date" in planned_block
    assert "d == self.anchor_date" in planned_block
    assert "end_minutes = 1440" not in planned_block
    assert "duration_m = 1440" not in planned_block
    assert "1440 - start_minutes" in src


def test_hourly_geometry_is_clamped_to_one_day():
    src = Path(
        "todo_bird_app/gantt/gantt_chart.py"
    ).read_text()

    assert "min(1439, int(start_minutes))" in src
    assert "1440 - start_minutes" in src


def test_scene_lifetime_guard_still_precedes_clear():
    src = Path(
        "todo_bird_app/gantt/gantt_chart.py"
    ).read_text()

    start = src.index("def rebuild_chart")

    refs = [
        src.index(
            "self.current_time_line_item = None",
            start,
        ),
        src.index(
            "self._resize_preview = None",
            start,
        ),
        src.index(
            "self._resize_item = None",
            start,
        ),
        src.index(
            "self._drag_item = None",
            start,
        ),
        src.index(
            "self._dependency_graphics = []",
            start,
        ),
        src.index(
            "self._rendered_task_items = {}",
            start,
        ),
        src.index(
            "self.scene.clear()",
            start,
        ),
    ]

    assert refs == sorted(refs)
