# Todo Bird WBS Calculation Integrity Report

Date: 2026-08-27
Classification: `todo_bird_phase2e_scheduling_engine_robust_human_witness_required`

## WBS Architecture Result

Task remains the WBS root entity. Subtasks can nest below the owning task. Mutation authority remains `WBSMutationService`; read-side hierarchy authority remains `WBSService`; rollup authority remains `WBSRollupService`; Gantt rows are read-only projections through `GanttWBSAdapter`.

## Rollup Rules Confirmed

- Parent planned start = earliest scheduled descendant start.
- Parent planned finish = latest scheduled descendant finish.
- Parent duration = elapsed calendar span, not a sum of child durations.
- Derived summary dates/duration stay out of parent raw Task schedule fields.
- Planned effort = additive over active leaves.
- Cancelled planned work is excluded from planned effort rollups.
- Actual effort = additive historical work effort, including cancelled work already performed.
- Actual elapsed = full calendar envelope only when actual finish is complete.
- Open actual summaries do not fabricate finish; they carry `latest_actual_activity_at`.
- Progress rule:
  - Effort-weighted when positive planned effort exists.
  - Otherwise average active leaf progress.
  - Otherwise completed-active ratio.
- Summary payloads are not counted as leaf work, preventing double counting.

## Defect Repaired

Deep WBS traversal used recursive code paths. That was safe for normal trees but brittle for very deep WBS structures and Gantt descendant traversal. `WBSService.build_from_raw` and `WBSService.get_descendants` now use explicit stacks.

Code:

- `todo_bird_app/services/wbs_service.py:313`
- `todo_bird_app/services/wbs_service.py:403`

## Tests Added

New file: `todo_bird_app/tests/test_wbs_calculation_integrity.py`

Coverage:

- Span duration vs effort sum.
- Nested summary no double count.
- Open actual summary no fabricated finish.
- Progress fallback rule.
- Cancelled planned work exclusion with actual effort retained.
- 1200-level deep WBS hierarchy build and descendant lookup.

Result:

- 6 passed in the new file.
- Older WBS files also passed inside the targeted and full isolated runs.

## Raw vs Summary Addendum

The follow-up WBS authority repair confirms that Gantt/WBS presentation rows no longer copy derived rollup dates, elapsed span, effort, or progress into raw parent `Task` fields. New file `todo_bird_app/tests/test_wbs_raw_vs_summary_authority.py` adds 56 targeted checks, including the `SCHEDULING WITNESS` scenario and summary/read-only schedule-change guard matrix.

Latest evidence: targeted 56 passed; impacted 154 passed; full isolated regression 110/110 files, 2374 passed, 0 failed, 0 errors, peak RSS `442472` KB. Production DB hash remained `0fadcb23e4b5361985d93643a122d1744dc00f0c3800fb1a3d5c955caafea05f`.

## Remaining Decision

The progress fallback behavior is now documented by tests, but if the product owner wants a different zero-effort fallback than active-leaf average/completed-ratio, that is a business-rule decision, not a defect.
