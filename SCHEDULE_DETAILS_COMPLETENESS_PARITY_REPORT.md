# Todo Bird Phase 2E Schedule Details Completeness Parity Report

Date: 2026-09-03

Final classification:

`todo_bird_phase2e_schedule_details_completeness_fixed_human_witness_required`

## Scope

This pass fixes the Schedule Details popup/copy inspector for planned Gantt and WBS rows. It stays inside Phase 2E, does not start Phase 2F, does not change CPM/dependency math, and does not declare Beta Ready or Human Accepted.

The repaired contract is: every graphically displayed Gantt/WBS schedule value must have an explainable Schedule Details value, with explicit state for unavailable/null data.

## Root Cause

1. `ScheduleDetailsFormatter` was acting as a partial presentation formatter, not a complete inspector contract. It omitted or under-exposed planned input, CPM forecast state, successors, constraint/deadline detail, calendar, baseline/revision values, and actual tracking state.
2. Gantt details could receive a blank project name because the caller depended on view-local project state rather than resolving from the task/project map/database.
3. WBS details were built from raw `WBSNode` objects. That dropped adapter-enriched values such as planned bar dates, CPM fields, rollups, dependencies, and source payload metadata.
4. Rendered Gantt bar x-coordinates were not attached to the inspectable task object, so the inspector could not report the actual bar geometry used by the scene.
5. During repair, a helper insertion temporarily moved later Gantt actions under the helper scope. This was fixed and guarded with a regression test.
6. Two older tests encoded a stale absolute production DB hash. The durable invariant is now before/after hash equality inside the test path, not a frozen historical hash.

## Implementation

- Rebuilt `todo_bird_app/services/schedule_details_formatter.py` around `ScheduleDetailsModel`, `ScheduleDetailsCollector`, and `ScheduleDetailsFormatter`.
- The collector consumes existing canonical task, subtask, WBS, Gantt, CPM, dependency, calendar, baseline/revision, and actual-execution values.
- The formatter does not import or execute CPM/dependency solvers.
- `Not analyzed` is emitted for CPM fields when analysis has not run; dates are not invented.
- Gantt rendering now attaches `gantt_bar_left_x` and `gantt_bar_right_x` to the task object after bar creation.
- Gantt Schedule Details project names resolve from view map, chart map, DB project row/object, or safe fallback.
- WBS Schedule Details now converts the clicked key into a schedule-rich `GanttWBSRow` through the existing snapshot/rollup/adapter authority.
- WBS project name lookup no longer depends on an undefined `self.project` attribute.

## Covered Sections

- Identity
- Planned Input
- Current Forecast / CPM
- Dependencies
- Constraint / Deadline
- Calendar
- Baseline / Revision
- Actual

## Validation

- `python3 -m py_compile ...`
  - Modified source and test files compiled successfully.
- Focused affected-area run:
  - `QT_QPA_PLATFORM=offscreen python3 -m pytest todo_bird_app/tests/test_schedule_details_completeness_parity.py todo_bird_app/tests/test_schedule_details_copy_interaction.py todo_bird_app/tests/test_popup_theme_authority.py todo_bird_app/tests/test_gantt_toolbar_runtime_ui.py todo_bird_app/tests/test_double_click_edit_workflow.py todo_bird_app/tests/test_phase2e_gantt_wbs_ui_closure.py todo_bird_app/tests/test_global_interactive_functionality.py -q`
  - 289 passed, 1 warning.
- Stale production-hash focused run:
  - `QT_QPA_PLATFORM=offscreen python3 -m pytest todo_bird_app/tests/test_world_clock_authority.py todo_bird_app/tests/test_popup_theme_authority.py todo_bird_app/tests/test_schedule_details_completeness_parity.py todo_bird_app/tests/test_schedule_details_copy_interaction.py -q`
  - 163 passed.
- Final source-cleanup focused run:
  - `QT_QPA_PLATFORM=offscreen python3 -m pytest todo_bird_app/tests/test_schedule_details_completeness_parity.py todo_bird_app/tests/test_schedule_details_copy_interaction.py -q`
  - 109 passed.
- Final isolated regression:
  - `QT_QPA_PLATFORM=offscreen python3 tools/run_isolated_pytest.py`
  - 126/126 files passed.
  - 3000 tests passed.
  - 0 failed, 0 errors, 0 skipped.
  - Peak RSS: 580632 KB.
  - Elapsed: 391.661s.

## Production DB Safety

- Production DB path: `todo_bird_app/data/todo_bird.db`
- SHA-256 before final full run: `62ef4a07b83b40c2d0c6cfd097c413ec925851bfd0ca09bf6946de1cb2de1d2b`
- SHA-256 immediately after final full run: `62ef4a07b83b40c2d0c6cfd097c413ec925851bfd0ca09bf6946de1cb2de1d2b`
- Current SHA-256 after a post-validation plain `sqlite3` integrity/count probe: `c472bda5ad40392be808ca07bb607e6728e1b0d72faa2d5ae8d5f0a402835b29`
- SQLite integrity check: `ok`
- Read-only counts: 5 projects, 10 tasks, 9 subtasks.

The Schedule Details repair did not intentionally write schedule data. The post-validation plain SQLite CLI probe checkpointed the WAL state into the main DB file, changing the byte-level hash while preserving logical integrity/counts. Future production witnesses should avoid plain `sqlite3` opens on this WAL database and should use copied DBs or hash-only before/after checks unless a checkpoint is explicitly intended.

## Human Witness Required

Manual live desktop confirmation is still required:

- Open the project Gantt/WBS containing `Cycle Task 9`.
- Open Schedule Details from the planned Gantt bar and from the WBS row.
- Confirm the Project field is populated.
- Confirm all required sections are visible.
- Confirm planned bar dates match the visible bar.
- Confirm CPM fields show analyzed values when available and `Not analyzed` when CPM is unavailable.
- Confirm predecessors and successors are both listed where present.

This closes the automated Schedule Details completeness defect only. Human acceptance remains pending.
