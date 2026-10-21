# Classification

`todo_bird_phase2e_wbs_raw_summary_authority_fixed_human_witness_required`

Automated repair and regression evidence is complete. Human re-witness remains required before any stronger release acceptance. This does not start Phase 2F.

## Human-witness defect reproduced

The disposable witness scenario is `SCHEDULING WITNESS`: parent `Foundation` raw start `2026-09-01 09:00`, raw `estimated_duration` 5 working days, children `Excavation` 2 working days from `2026-09-01 09:00` and `Reinforcement` 3 working days from `2026-09-02 09:00`.

Expected WBS summary envelope: `2026-09-01 09:00` to `2026-09-05 09:00`, elapsed span `5760` minutes. Expected parent raw fields after reopening Edit Task: raw start still `2026-09-01 09:00`, raw finish still unset unless the user entered it, raw `estimated_duration` still `7200` minutes.

## Exact mutation root cause

Root cause was not `WBSRollupService`, `GanttWBSAdapter`, or hierarchy mutation. They were read-side/structure-side only. The defect lived in `GanttView._build_phase1d_wbs_gantt_items`, where WBS summary rows were materialized as synthetic `Task` objects with rollup values assigned into raw `Task` fields: `planned_date`, `due_date`, `planned_start_time`, `planned_end_time`, `estimated_duration`, `planned_effort_minutes`, and `progress`.

Because `TaskDialog` binds directly to those raw `Task` fields, any summary presentation object that reached edit/save behavior could show or persist derived WBS values as if they were human-entered parent inputs.

## Raw Task authority

Raw schedule fields remain DB/user-input authority only:

- `planned_date`
- `planned_start_time`
- `due_date`
- `planned_end_time`
- `estimated_duration`
- `planned_effort_minutes`
- `daily_dedication_minutes`
- `progress`

The Gantt WBS projection now fills these fields from the entity payload/source task, not from rollup output.

## WBS Summary authority

Derived summary values now live only in explicit Gantt metadata:

- `gantt_planned_start`
- `gantt_planned_finish`
- `gantt_summary_planned_start`
- `gantt_summary_planned_finish`
- `gantt_summary_planned_elapsed_minutes`
- `gantt_rollup_planned_effort`
- `gantt_rollup_progress`
- `gantt_rollup_leaf_count`

These are display/geometry values, not persistent raw Task inputs.

## Duration/span distinction

Parent raw `estimated_duration` remains the human-entered planned duration. WBS `summary_elapsed_span` remains the derived envelope from earliest descendant start to latest descendant finish. CPM ES/EF remains forecast authority and is still separate from both raw input and WBS summary envelope.

## WBS view changes

`todo_bird_app/views/gantt_view.py` now preserves raw payload/source values when building Gantt presentation tasks, records derived summary values under `gantt_*` metadata, and rejects summary/read-only schedule-change payloads before any SQL update. The SQL guard also checks the DB hierarchy and fails closed if it cannot prove the target is a leaf row.

## Task Dialog behavior

`todo_bird_app/widgets/task_dialog.py` remains raw-field bound. The fix prevents summary-derived values from being placed into those raw fields before dialog or persistence code can see them.

## Effort rollup result

Planned effort rollup remains additive over active leaves. The parent raw `planned_effort_minutes` is preserved independently from `gantt_rollup_planned_effort`, so a parent can keep its own raw effort while the WBS summary displays the child aggregate.

## Progress rollup rule

Progress rollup remains effort-weighted when positive planned effort exists, then active-leaf average, then completed-active ratio fallback. The parent raw `progress` is preserved independently from `gantt_rollup_progress`.

## CPM/Gantt isolation

The chart still renders from `gantt_planned_start` and `gantt_planned_finish`, and CPM forecast metadata still uses CPM-specific attributes. The repair prevents chart drag/resize payloads and in-memory task mutation from altering summary/read-only raw fields.

## Files changed

- `todo_bird_app/views/gantt_view.py`: raw-vs-summary projection split and fail-closed schedule-change guard.
- `todo_bird_app/gantt/gantt_chart.py`: summary/read-only payload markers and no-op local mutation for summary/read-only tasks.
- `todo_bird_app/tests/test_wbs_raw_vs_summary_authority.py`: 56 focused authority tests covering the witness and guard matrix.
- `todo_bird_app/tests/test_phase1d_live_wbs_gantt_rows.py`: existing WBS Gantt tests updated to the repaired raw-vs-summary contract.
- `WBS_CALCULATION_INTEGRITY_REPORT.md`, `CALCULATION_AUTHORITY_MATRIX_FINAL.md`, `BETA_SCHEDULING_RELEASE_SCORECARD.md`: release evidence addenda.

## Targeted/full tests

- Targeted: `python3 tools/run_isolated_pytest.py todo_bird_app/tests/test_wbs_raw_vs_summary_authority.py --timeout 140 --summary build/test_reports/wbs_raw_vs_summary_targeted.json` -> 56 passed, 0 failed, peak RSS `111696` KB, elapsed `2.44`s.
- Impacted: `python3 tools/run_isolated_pytest.py todo_bird_app/tests/test_wbs_raw_vs_summary_authority.py todo_bird_app/tests/test_phase1d_live_wbs_gantt_rows.py todo_bird_app/tests/test_gantt_schedule_authority_integrity.py todo_bird_app/tests/test_wbs_calculation_integrity.py todo_bird_app/tests/test_phase1c_wbs_rollup_service.py todo_bird_app/tests/test_gantt_batch2.py todo_bird_app/tests/test_phase2e_runtime_constraint_refresh.py --timeout 180 --summary build/test_reports/wbs_raw_vs_summary_impacted.json` -> 154 passed, 0 failed, peak RSS `135280` KB, elapsed `5.671`s.
- Full isolated regression: `python3 tools/run_isolated_pytest.py --timeout 180 --summary build/test_reports/wbs_raw_vs_summary_full.json` -> 110/110 files, 2374 passed, 0 failed, 0 errors, peak RSS `442472` KB, elapsed `339.526`s.

## Production DB hash

Before: `0fadcb23e4b5361985d93643a122d1744dc00f0c3800fb1a3d5c955caafea05f`

After: `0fadcb23e4b5361985d93643a122d1744dc00f0c3800fb1a3d5c955caafea05f`

Production DB file `todo_bird_app/data/todo_bird.db` is unchanged.

## Human re-witness steps

Create the disposable `SCHEDULING WITNESS` project, enter the parent/child dates above, open the WBS/Gantt view, then reopen `Foundation` in Edit Task. Acceptance requires the WBS summary to show `2026-09-01` through `2026-09-05` while the parent raw Task dialog still shows the original human-entered raw duration and does not inherit the summary finish.

`todo_bird_phase2e_wbs_raw_summary_authority_fixed_human_witness_required`
