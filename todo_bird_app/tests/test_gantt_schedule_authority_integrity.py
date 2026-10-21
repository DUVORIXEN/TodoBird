from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from todo_bird_app.gantt.timescale_engine import TimescaleEngine, ZoomLevel
from todo_bird_app.services.gantt_wbs_adapter import GanttWBSAdapter
from todo_bird_app.services.wbs_rollup_service import WBSRollupService
from todo_bird_app.services.wbs_service import EntityRef, WBSHierarchySnapshot, WBSNode


def node(key, parent, depth, code, title, status="Planned"):
    return WBSNode(
        key=key,
        project_id=1,
        parent_key=parent,
        title=title,
        sibling_order=1,
        depth=depth,
        wbs_code=code,
        child_count=0,
        has_children=False,
        status=status,
        is_completed=status == "Completed",
        created_at="2026-01-01",
    )


def snapshot(nodes, children, roots):
    return WBSHierarchySnapshot(
        project_id=1,
        nodes_by_key=nodes,
        children_by_parent=children,
        root_keys=roots,
        orphaned_keys=[],
        total_nodes=len(nodes),
        max_depth=max((n.depth for n in nodes.values()), default=0),
        revision=1,
    )


def test_adapter_uses_rollup_actual_activity_without_fabricating_finish():
    root = EntityRef.task(1)
    leaf = EntityRef.subtask(10)
    snap = snapshot(
        {
            root: node(root, None, 0, "1", "Summary"),
            leaf: node(leaf, root, 1, "1.1", "Open Work", "In Progress"),
        },
        {None: [root], root: [leaf], leaf: []},
        [root],
    )
    payloads = {
        root: {"show_in_gantt": False},
        leaf: {
            "show_in_gantt": True,
            "status": "In Progress",
            "planned_date": "2026-09-01",
            "planned_start_time": "08:00",
            "due_date": "2026-09-01",
            "planned_end_time": "10:00",
            "actual_start_date": "2026-09-01",
            "actual_start_time": "09:00",
            "actual_duration": 60,
        },
    }
    rollups = WBSRollupService.calculate(snap, payloads)

    rows = GanttWBSAdapter.build_rows(snap, payloads, rollups)
    summary = rows[0]

    assert [row.title for row in rows] == ["Summary", "Open Work"]
    assert summary.is_summary is True
    assert summary.show_in_gantt is True
    assert summary.actual_start.strftime("%Y-%m-%d %H:%M") == "2026-09-01 09:00"
    assert summary.actual_finish is None
    assert summary.latest_actual_activity_at.strftime("%Y-%m-%d %H:%M") == "2026-09-01 09:00"


def test_adapter_summary_baseline_span_and_variance_are_consistent():
    root = EntityRef.task(1)
    a = EntityRef.subtask(20)
    b = EntityRef.subtask(21)
    snap = snapshot(
        {
            root: node(root, None, 0, "1", "Summary"),
            a: node(a, root, 1, "1.1", "A"),
            b: node(b, root, 1, "1.2", "B"),
        },
        {None: [root], root: [a, b], a: [], b: []},
        [root],
    )
    payloads = {
        root: {"show_in_gantt": True},
        a: {
            "show_in_gantt": True,
            "planned_date": "2026-09-03",
            "planned_start_time": "08:00",
            "due_date": "2026-09-03",
            "planned_end_time": "12:00",
            "baseline_start": "2026-09-01 08:00",
            "baseline_finish": "2026-09-01 12:00",
        },
        b: {
            "show_in_gantt": True,
            "planned_date": "2026-09-04",
            "planned_start_time": "09:00",
            "due_date": "2026-09-04",
            "planned_end_time": "17:00",
            "baseline_start": "2026-09-02 09:00",
            "baseline_finish": "2026-09-02 17:00",
        },
    }

    summary = GanttWBSAdapter.build_rows(snap, payloads)[0]

    assert summary.baseline_start.strftime("%Y-%m-%d %H:%M") == "2026-09-01 08:00"
    assert summary.baseline_finish.strftime("%Y-%m-%d %H:%M") == "2026-09-02 17:00"
    assert summary.baseline_duration_minutes == 1980
    assert summary.start_variance_minutes == 2880
    assert summary.finish_variance_minutes == 2880


def test_timescale_includes_open_actual_current_date_without_persisting_finish():
    min_date, max_date = TimescaleEngine.get_relevant_date_range(
        date(2026, 8, 23),
        [{"actual_start_date": "2026-08-20", "actual_end_date": None}],
    )

    assert min_date <= date(2026, 8, 20)
    assert max_date >= date.today()


def test_rebuild_chart_releases_scene_owned_references_before_scene_clear():
    source = Path("todo_bird_app/gantt/gantt_chart.py").read_text(encoding="utf-8")
    body = source.split("def rebuild_chart(self):", 1)[1].split("app_theme =", 1)[0]
    expected = [
        "self.current_time_line_item = None",
        "self._resize_preview = None",
        "self._resize_item = None",
        "self._drag_item = None",
        "self._dependency_graphics = []",
        "self._rendered_task_items = {}",
        "self.scene.clear()",
    ]

    positions = [body.index(item) for item in expected]

    assert positions == sorted(positions)


def test_gantt_wbs_adapter_is_read_only_and_has_no_sql_writes():
    source = Path("todo_bird_app/services/gantt_wbs_adapter.py").read_text(encoding="utf-8")

    assert re.search(r"\b(INSERT|UPDATE|DELETE|REPLACE|DROP|ALTER)\b", source, re.IGNORECASE) is None
    assert ".commit(" not in source


def test_timescale_range_includes_all_schedule_authority_layers():
    min_date, max_date = TimescaleEngine.get_relevant_date_range(
        date(2026, 8, 23),
        [
            {
                "planned_date": "2026-09-01",
                "due_date": "2026-09-02",
                "cpm_earliest_finish": "2026-10-01T17:00:00",
                "baseline_finish": "2026-11-01 17:00",
                "constraint_datetime": "2026-12-01 09:00",
                "deadline_datetime": "2027-01-01 17:00",
            }
        ],
    )

    assert min_date == date(2026, 8, 23)
    assert max_date == date(2027, 1, 1)
