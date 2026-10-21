# Todo Bird Phase 2E Dependency Authoring Workflow Report

Date: 2026-09-02

Final classification:

`todo_bird_phase2e_global_interactive_functionality_fixed_human_witness_required`

## Human-Witness Failure

The user needed to author:

- Predecessor: `Excavation Final`
- Successor: `Reinforcement Final`
- Type: FS
- Lag: 0

The production DB read-only witness confirms both are leaf subtasks under task 14:

- `Excavation Final`: subtask id 14, dependencies `[]`
- `Reinforcement Final`: subtask id 15, dependencies `[]`

The production database was not changed by the automated repair or verification.

## Root Cause

The scheduling engine had already grown beyond the dialog:

- WBS and CPM included subtasks.
- Gantt/WBS propagation consumed subtask scheduling results.
- The dependency editor still exposed task-only predecessor rows.
- The subtask editor did not provide a dependency authoring surface.
- The subtask persistence path did not carry dependency metadata through collect/insert/update.
- Controller validation still treated dependencies as legacy task IDs unless specially handled.

## Implementation

New dependency authority:

- `todo_bird_app/services/dependency_authoring_service.py`

Key behavior:

- Builds dependency candidates from the WBS project hierarchy.
- Includes open leaf tasks and open leaf subtasks.
- Excludes self, summary parents, completed/cancelled/archived nodes, and cross-project nodes.
- Normalizes legacy task IDs and typed task/subtask references.
- Validates typed dependency edges before save.
- Detects self-dependency, duplicates, missing/stale references, cross-project references, ineligible nodes, and cycles.

Task Dialog changes:

- Added visible Add Dependency controls:
  - Predecessor selector
  - Type selector: FS, SS, FF, SF
  - Lag/lead input
  - Add Dependency button
  - Remove Selected button
  - Inline status label
- Existing dependency table now carries typed entity keys.
- Task-to-task legacy storage remains compatible.
- Task-to-subtask and subtask-capable edges use typed dependency storage.

Subtask editor changes:

- Existing persisted subtasks can now author dependencies from the subtask edit dialog.
- New unsaved subtasks show an explicit disabled-state explanation because they do not yet have a stable database identity.
- Subtask metadata now preserves `dependencies` through edit, collect, insert, and update paths.

Controller changes:

- `TaskController.update_task` now detects typed dependency payloads.
- Typed payloads use `DependencyAuthoringService.validate_dependencies`.
- Legacy task-only payloads continue to use the legacy Gantt dependency validation path.

## Validation Matrix

| Edge | Result |
| --- | --- |
| Task -> Task | Passed |
| Task -> Subtask | Passed |
| Subtask -> Task | Passed |
| Subtask -> Subtask | Passed |
| FS | Passed |
| SS | Passed |
| FF | Passed |
| SF | Passed |
| Positive lag | Passed |
| Zero lag | Passed |
| Negative lag/lead | Passed |
| Self-dependency rejection | Passed |
| Duplicate rejection | Passed |
| Cross-project rejection | Passed |
| Cycle rejection | Passed |
| Summary-node exclusion | Passed |
| Closed-node exclusion | Passed |
| WBS/CPM propagation | Passed |
| Gantt row propagation | Passed |

## Tests Added

- `todo_bird_app/tests/test_dependency_authoring_workflow.py`
  - 67 tests.
  - Covers 48 typed edge combinations across predecessor/successor kind, dependency type, and lag value.
  - Covers UI add/remove controls, subtask modal dependency save, controller validation, WBS CPM recompute, and Gantt propagation.

## Verification

- Focused dependency workflow: 67 passed.
- Existing Phase 2C dependency tests: passed.
- Focused affected-area run: 305 passed.
- Full isolated regression: 121/121 files, 2817 tests passed, 0 failures.

## Release Note

The automated gate is closed for dependency authoring. Human witness is still required to confirm the live UI path for `Excavation Final -> Reinforcement Final`, FS, 0 lag.
