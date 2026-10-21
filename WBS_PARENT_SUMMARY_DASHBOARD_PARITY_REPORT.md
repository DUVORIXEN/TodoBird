# WBS Parent Summary Dashboard Parity Report

Date: 2026-09-04

Classification: `todo_bird_wbs_parent_summary_dashboard_parity_fixed_human_witness_required`

## Scope

Audited and fixed the Phase 2E gap where a WBS parent/main task such as `Foundation` could show rollup progress while CPM schedule columns showed only `-`/blank state even though child subtasks had valid CPM results.

No Phase 2F work was started.

## Root Cause

`WBSItemModel` looked up CPM fields only by the row's own `EntityRef`. That is correct for leaf tasks/subtasks, but a WBS parent is not a CPM activity. Because there was no derived parent CPM-summary contract, parent columns such as Critical, ES, EF, LS, LF, Total Float, Free Float, and Schedule Health fell back to empty display.

`GanttWBSAdapter` already carried WBS planned rollup geometry for summary rows, but summary CPM metadata stayed leaf-only. Dashboard project snapshot metrics were task-list/progress oriented and did not consume WBS forecast summary values.

## Confirmed Authority Model

Raw Task Input != Derived WBS Summary != Leaf CPM Result.

- Raw task fields stay in `tasks` / `subtasks` and remain editable user input.
- Leaf CPM results stay in `CPMSchedulingService` / `WBSCPMResult` and are keyed by typed `EntityRef`.
- Parent/main-task WBS rows now receive a derived, read-only `WBSCPMSummaryResult`.
- `CPMNodeResultRole` remains leaf-only. Parent rows do not pretend to be CPM activities.

## Summary Rules

| Field | Summary Rule |
| --- | --- |
| Summary Earliest Start | Earliest descendant schedulable CPM ES |
| Summary Earliest Finish | Latest descendant schedulable CPM EF |
| Summary Latest Start | Earliest descendant schedulable CPM LS |
| Summary Latest Finish | Latest descendant schedulable CPM LF |
| Summary Total Float | Not mathematically aggregated; display `N/A (Summary)` |
| Summary Free Float | Not mathematically aggregated; display `N/A (Summary)` |
| Summary Critical | `Contains Critical` when any descendant leaf is critical |
| Summary Schedule Health | `Healthy`, `At Risk`, `Blocked (Cycle)`, or `N/A (Summary)` from descendant schedule state |
| Summary Progress | Existing `WBSRollupService` weighted progress |

Summary span remains an envelope, not a sum of overlapping children.

## WBS Display Result

Parent summary rows now expose derived summary values for Critical, ES, EF, LS, LF, and Schedule Health. Float fields explicitly show `N/A (Summary)` rather than a misleading dash or fake aggregated float.

Leaf child rows keep their own CPM ES, EF, LS, LF, Total Float, Free Float, Critical, and diagnostics unchanged.

## Gantt Parity Result

Gantt planned summary bar geometry remains the existing WBS planned rollup envelope. Gantt summary rows now also carry derived CPM summary metadata (`cpm_earliest_start`, `cpm_earliest_finish`, `cpm_latest_start`, `cpm_latest_finish`, summary criticality, schedulable status, and diagnostics) for current-forecast/details parity.

No raw task plan is mutated by Gantt summary construction.

## Dashboard Parity Result

Added `DashboardScheduleSummaryService` as a pure-data dashboard projection over existing WBS/Gantt authorities. The dashboard project snapshot can now include supported schedule metrics such as project forecast range, critical work count, and at-risk WBS summary count without duplicating CPM math inside the UI.

## Production DB Safety

The production DB was not opened for writable schedule inspection in this pass. Hash-only witness after the fix:

`c8fb2bbe4f53fbce147a3fc5892014ede5a66a37030fb9dbe0e02ab2834f4513`

The new production DB test performs hash-only before/after verification and does not inspect or mutate production data.

## Evidence

- `python3 -m py_compile` passed for changed WBS/CPM/Gantt/dashboard/reporting modules.
- `todo_bird_app/tests/test_wbs_parent_summary_dashboard_parity.py`: 41 passed.
- Adjacent WBS/Gantt/CPM bundle: 153 passed.
- Impacted schedule-details/WBS UI/Gantt-dashboard bundle: 162 passed.

Bounded verification was used intentionally to avoid the repeated IDE crash pattern from broad GUI-heavy test loops.

## Final Classification

`todo_bird_wbs_parent_summary_dashboard_parity_fixed_human_witness_required`
