# Todo Bird Gantt Schedule Integrity Report

Date: 2026-08-27
Classification: `todo_bird_phase2e_scheduling_engine_robust_human_witness_required`

## Scope

Audited Gantt schedule data flow, WBS adapter behavior, time range inclusion, actual lane semantics, baseline summary projection, and Qt scene lifetime safety. This pass did not redesign visuals.

## Adapter Result

`GanttWBSAdapter` remains a read-only projection:

- It consumes `WBSHierarchySnapshot` plus `WBSRollupService` results.
- It preserves WBS pre-order and parent visibility closure.
- It marks summary rows read-only.
- It exposes planned span, planned effort, actual effort, actual start, actual finish, and latest actual activity from the rollup service.
- It does not perform SQL writes.

## Geometry And Range Result

`TimescaleEngine.get_relevant_date_range` includes:

- Planned start/finish.
- Due date.
- CPM ES/EF.
- Baseline start/finish.
- Constraint date.
- Deadline date.
- Actual start/finish.
- Current date for open actual rows, without persisting that date as an actual finish.

New tests confirm all schedule authority layers expand the visible date range.

## Actual Bar Result

Confirmed:

- No Actual bar without explicit actual start.
- Open Actual uses actual start to display-only current time/current date and keeps actual finish null.
- Summary Actual uses WBS rollup `latest_actual_activity_at` rather than progress, effort, baseline, or forecast.
- Planned resize payloads do not mutate actual fields.

## Qt Scene Lifetime Result

The required ordering before `scene.clear()` is present and tested:

```python
self.current_time_line_item = None
self._resize_preview = None
self._resize_item = None
self._drag_item = None
self._dependency_graphics = []
self._rendered_task_items = {}
self.scene.clear()
```

Code: `todo_bird_app/gantt/gantt_chart.py:2753`

## Tests Added

New file: `todo_bird_app/tests/test_gantt_schedule_authority_integrity.py`

Coverage:

- Adapter uses rollup actual activity and does not fabricate summary finish.
- Summary baseline span and variance projection remain consistent.
- Timescale includes open actual current date without persisted finish.
- Scene-owned references are released before `scene.clear()`.
- Adapter has no SQL write statements.
- Timescale includes all schedule authority layers.

Result:

- 6 passed in the new file.
- Existing Gantt files passed in the targeted and full isolated runs.
