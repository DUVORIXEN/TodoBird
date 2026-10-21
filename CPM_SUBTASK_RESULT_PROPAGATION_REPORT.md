# CPM Subtask Result Propagation Report

Date: 2026-09-02
Final classification: `todo_bird_phase2e_cpm_subtask_result_propagation_fixed_human_witness_required`

No Phase 2F started or authorized. This report does not declare Beta Ready or Human Accepted.

## Scope

This pass investigated the proven human-witness defect where a WBS parent task showed analyzed schedule data, but its leaf subtasks did not:

- Project: `SCHEDULING WITNESS FINAL`
- Parent: `Foundation`
- Intended leaves: `Excavation Final` and `Reinforcement Final`
- Intended dependency: `Excavation Final -> Reinforcement Final`, FS, lag 0
- Observed failure: WBS leaf rows showed `Critical = Not analyzed` and blank CPM fields; the Gantt tooltip for `Reinforcement Final` showed `CPM: Not analyzed`.

The fix stayed within Phase 2E result propagation. CPM forward/backward math, lag math, criticality math, and calendar math were not rewritten.

## Production Witness Safety

Production DB was inspected read-only only.

Hash before and after read-only witness:
`aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`

Current production rows for `SCHEDULING WITNESS FINAL`:

| Row | ID | Parent | Title | Start | Finish | Duration | Dependencies | Gantt |
| --- | ---: | --- | --- | --- | --- | ---: | --- | ---: |
| Project | 6 | - | `SCHEDULING WITNESS FINAL` | - | - | - | - | - |
| Task | 14 | project 6 | `Foundation` | `2026-09-02 09:00` | `2026-09-03 09:00` | 2880 | `[]` | 1 |
| Subtask | 14 | task 14 | `Excavation Final` | `2026-09-02 09:00` | `2026-09-03 09:00` | 2880 | `[]` | 1 |
| Subtask | 15 | task 14 | `Reinforcement Final` | `2026-09-02 09:00` | - | 2880 | `[]` | 1 |

The current live `Reinforcement Final` row no longer contains the pasted oracle dependency; it stores `dependencies=[]`. Therefore the FS chain was proven in a disposable oracle database, not by mutating production data.

## Root Cause

The defect was not an arithmetic failure inside `CPMSchedulingService`. It was a graph-admission and result-propagation failure:

1. `WBSItemModel.rebuild_cpm_schedule()` loaded only `get_tasks_by_project()`, so subtasks were excluded from the WBS CPM network.
2. `CPMSchedulingService.calculate_schedule()` accepts only items whose `gantt_item_type` is `task`. WBS/Gantt subtask presentation rows carried `gantt_item_type=subtask`, so they were filtered out if passed directly.
3. WBS roles looked up CPM results only for `entity_type == "task"`, which made leaf subtasks display `Not analyzed`.
4. `GanttDependencyEngine.annotate()` reset all CPM fields before reapplying task-only results, so subtask tooltips lost upstream metadata and fell back to `CPM: Not analyzed`.
5. Bare integer IDs could collide between tasks and subtasks, so a permanent fix needed typed keys, not ID-only lookups.

## Corrected Product Contract

Leaf/work-package rows are CPM participants:

- leaf tasks participate in CPM;
- leaf subtasks participate in CPM;
- completed, cancelled, archived, and summary rows do not participate as leaf CPM activities;
- WBS summary parents are derived projections and do not own a leaf `CPMNodeResult`.

Summary dates, duration, effort, and progress remain rollups. Leaf CPM fields remain canonical outputs from `CPMSchedulingService` through the WBS CPM adapter.

## Permanent Fix

New adapter:

- `todo_bird_app/services/wbs_cpm_adapter.py`
- Builds a typed WBS leaf network from task and subtask rows.
- Uses `EntityRef(entity_type, entity_id)` so `task:7` and `subtask:7` cannot collide.
- Rewrites task/subtask dependencies into synthetic canonical `Task` objects accepted by `CPMSchedulingService`.
- Preserves missing/self/cycle diagnostics through typed key helpers.
- Maintains legacy `cpm_result.nodes[task_id]` compatibility for task leaves only while keeping typed lookup authoritative.

Propagation changes:

- `WBSRollupService` now computes WBS leaf CPM through `calculate_wbs_cpm()` and injects typed CPM early dates into payloads.
- `WBSItemModel` now exposes ES, EF, LS, LF, Total Float, Free Float, Critical, Schedule Health, tooltips, and accessible text for analyzable task and subtask leaves.
- `WBSFilterProxyModel` now evaluates critical/float/warning filters through typed keys instead of task-only guards.
- `GanttWBSAdapter` carries canonical CPM fields and dependency summaries into Gantt rows.
- `GanttView` attaches canonical CPM metadata to task and subtask presentation items.
- `GanttDependencyEngine` restores canonical WBS CPM metadata after its legacy task-only reset.
- `GanttTaskItem` tooltip now shows Current Forecast Start/Finish, ES/EF/LS/LF, Total Float, Free Float, Critical, Critical Path, and dependency summary when canonical CPM data exists.
- `ScheduleVersionService` and `ScheduleVarianceService` now understand typed WBS CPM results for subtasks.

## Disposable FS Oracle

The executable oracle used:

- `Foundation` as a WBS summary parent.
- `Excavation Final` as a leaf subtask.
- `Reinforcement Final` as a leaf subtask.
- Dependency: `Excavation Final -> Reinforcement Final`, FS, lag 0.

| Entity | CPM Included | CPM Key | Synthetic CPM ID | Duration | Predecessors | Successors | ES | EF | LS | LF | TF | FF | Critical | Diagnostics |
| --- | --- | --- | ---: | ---: | --- | --- | --- | --- | --- | --- | ---: | ---: | --- | --- |
| Foundation | no | `task:1` | - | derived | - | - | - | - | - | - | - | - | no leaf result | summary parent |
| Excavation Final | yes | `subtask:1` | 1 | 2880 | - | `subtask:2` | `2026-09-01 09:00` | `2026-09-02 09:00` | `2026-09-01 09:00` | `2026-09-02 09:00` | 0 | 0 | true | `[]` |
| Reinforcement Final | yes | `subtask:2` | 2 | 2880 | `subtask:1` | - | `2026-09-02 09:00` | `2026-09-03 09:00` | `2026-09-02 09:00` | `2026-09-03 09:00` | 0 | 0 | true | `[]` |

Dependency math expected versus actual:

- Excavation EF: `2026-09-02 09:00`
- Reinforcement ES: `2026-09-02 09:00`
- FS lag 0 rule: successor ES equals predecessor EF
- Result: matched
- Reinforcement EF: `2026-09-03 09:00`

This proves the leaf subtask graph is now calculated and the FS edge is preserved without changing CPM math.

## UI Propagation Oracle

For `Reinforcement Final`, the disposable oracle proved:

- WBS ES: `2026-09-02 09:00`
- WBS EF: `2026-09-03 09:00`
- WBS LS: `2026-09-02 09:00`
- WBS LF: `2026-09-03 09:00`
- WBS Total Float: `0m`
- WBS Free Float: `0m`
- WBS Critical: `Critical`
- WBS Schedule Health: `Healthy`
- Gantt analysis status: `analyzed`
- Gantt dependency summary: `1 predecessor`
- Tooltip contains Current Forecast Start: true
- Tooltip contains ES/EF/LS/LF: true
- Tooltip contains `CPM: Not analyzed`: false

## ID and Key Audit

Typed result mapping is mandatory because SQLite task IDs and subtask IDs are independent sequences.

Covered collision case:

- `task:2` and `subtask:2` can both exist.
- The CPM adapter gives each typed key an independent synthetic CPM node.
- WBS/Gantt/snapshot lookup uses `EntityRef`, not bare integer IDs.
- Legacy `.nodes[task_id]` access is retained only for task leaf compatibility and cannot make a summary task read a subtask result.

## Tests Added

New file:
`todo_bird_app/tests/test_cpm_subtask_result_propagation.py`

45 targeted tests cover:

- task/subtask leaf admission to CPM;
- summary parent exclusion;
- FS dependency preservation;
- WBS ES/EF/LS/LF/TF/FF/Critical/Schedule Health roles;
- WBS tooltip and accessibility text;
- WBS critical/float/warning filters;
- Gantt row metadata propagation;
- Gantt tooltip removal of false `CPM: Not analyzed`;
- `GanttDependencyEngine` post-reset metadata restoration;
- typed task/subtask ID collision safety;
- nested subtasks;
- dependency variants FS/SS/FF/SF and lag/lead;
- schedule snapshot and variance typed CPM lookup;
- production DB read-only hash stability;
- runner/report existence;
- source guards against task-only regressions.

## Validation Evidence

Syntax:

- `python3 -m py_compile todo_bird_app/services/wbs_cpm_adapter.py todo_bird_app/services/wbs_rollup_service.py todo_bird_app/models/wbs_item_model.py todo_bird_app/models/wbs_filter_proxy_model.py todo_bird_app/services/gantt_wbs_adapter.py todo_bird_app/views/gantt_view.py todo_bird_app/gantt/gantt_dependency_engine.py todo_bird_app/gantt/gantt_items.py todo_bird_app/services/schedule_version_service.py todo_bird_app/services/schedule_variance_service.py`
- Result: passed.

Focused new suite:

- `python3 -m pytest todo_bird_app/tests/test_cpm_subtask_result_propagation.py -q`
- Result: 45 passed, 0 failed.

Impacted UI/scheduling bundle:

- `QT_QPA_PLATFORM=offscreen python3 -m pytest todo_bird_app/tests/test_cpm_subtask_result_propagation.py todo_bird_app/tests/test_phase2e_live_refresh_authority.py todo_bird_app/tests/test_phase2b_schedule_intelligence_ui.py todo_bird_app/tests/test_phase1d_gantt_wbs_adapter.py todo_bird_app/tests/test_gantt_schedule_authority_integrity.py todo_bird_app/tests/test_wbs_raw_summary_human_failure_forensics.py todo_bird_app/tests/test_phase2a_professional_scheduling_engine.py todo_bird_app/tests/test_phase2c_advanced_dependencies.py todo_bird_app/tests/test_working_calendar_cpm_authority.py -q`
- Result: 250 passed, 0 failed.

Adjacent scheduling/rollup/snapshot bundle:

- `QT_QPA_PLATFORM=offscreen python3 -m pytest todo_bird_app/tests/test_schedule_versions.py todo_bird_app/tests/test_phase2d_schedule_baseline_variance.py todo_bird_app/tests/test_wbs_rollup_service.py todo_bird_app/tests/test_wbs_calculation_integrity.py todo_bird_app/tests/test_wbs_raw_vs_summary_authority.py todo_bird_app/tests/test_phase2e_runtime_constraint_refresh.py todo_bird_app/tests/test_project_calendar_live_authority_forensics.py todo_bird_app/tests/test_project_calendar_duration_authority.py todo_bird_app/tests/test_phase2e_constraints_calendars.py -q`
- Result: 391 passed, 0 failed.

Full isolated regression:

- Command: `python3 tools/run_isolated_pytest.py`
- Result: passed.
- Files: 118/118.
- Tests: 2633 passed, 0 failed, 0 errors, 0 skipped.
- Peak RSS: 410460 KB.
- Elapsed: 341.715s.
- Summary JSON: `build/test_reports/isolated_pytest_summary.json`

## Release Gate

Code defect status: fixed.

Human witness remains required because production data was not modified and the final visible desktop confirmation must be performed in the real app.

Expected human witness after creating or correcting the FS dependency in the desktop UI:

- `Excavation Final` shows analyzed CPM fields in WBS.
- `Reinforcement Final` shows analyzed CPM fields in WBS.
- `Reinforcement Final` Gantt tooltip does not show `CPM: Not analyzed`.
- Tooltip shows Current Forecast Start/Finish, ES/EF/LS/LF, Total Float, Free Float, Critical yes/no, and dependency summary.

Final classification:

`todo_bird_phase2e_cpm_subtask_result_propagation_fixed_human_witness_required`
