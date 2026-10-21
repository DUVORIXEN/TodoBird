# Todo Bird Phase 2E Global Interactive Functionality Audit

Date: 2026-09-02

Final classification:

`todo_bird_phase2e_global_interactive_functionality_fixed_human_witness_required`

## Authority Boundary

- Phase 2E only.
- No Phase 2F work was started.
- This report does not declare Beta Ready or Human Accepted.
- Production database was treated as read-only during verification.

## Root Cause Findings

1. Task dependency authoring was task-only. Subtasks already participated in CPM/WBS/Gantt propagation, but the Task Dialog did not expose a usable subtask predecessor workflow.
2. Subtask edit/save paths dropped dependency metadata, so even a future UI control would not have persisted subtask dependencies correctly.
3. Controller-level dependency validation used the legacy task-only validation path and could reject or misclassify typed task/subtask dependency edges.
4. Blocker/delay controls were present but too easy to treat as dead because disabled controls did not consistently explain the status gate.
5. Lowercase/empty/null blocker category values were not normalized strongly enough, allowing confusing category states.
6. The global interaction audit found one additional disabled dropdown without naming/help text: task pin color.

## Repairs Completed

- Added `todo_bird_app/services/dependency_authoring_service.py`.
- Reworked `TaskDialog` dependency authoring for typed task/subtask predecessor candidates, dependency type, lag/lead, add/remove, and validation feedback.
- Added subtask dependency authoring inside the subtask edit dialog.
- Preserved legacy task-to-task dependency storage while adding typed storage for subtask-capable edges.
- Added validation for self-dependency, duplicate dependency, stale/missing references, cross-project references, ineligible summary/closed nodes, and cycles.
- Updated `TaskController.update_task` to route typed dependency payloads through the new task/subtask validator.
- Repaired blocker/delay category normalization and enabled/disabled tooltips.
- Added object names, accessible names, and tooltips to the task and nested pin color dropdowns.

## Interactive Inventory

Static source inventory, excluding backups and `__pycache__`:

- Widget/control references: 989 matches across 82 files.
- Signal/state-management references: 939 matches across 85 files.
- Python files searched: 266.

Primary surfaces audited:

| Surface | Result |
| --- | --- |
| MainWindow navigation sections | Closed by real `MainWindow` interaction tests |
| Command registry shortcuts | Closed by static/global audit of `CommandRegistry` path |
| Task creation/edit dialog | Closed for dependency/status/blocker/delay audited paths |
| Subtask edit dialog | Closed for dependency metadata authoring and persistence |
| WBS hierarchy propagation | Closed by WBS/CPM/Gantt focused tests |
| Gantt schedule propagation | Closed by focused and isolated regression tests |
| Settings view organization/performance | Existing tests passed in isolated regression |
| Reminder/startup controls | Existing tests passed in isolated regression |
| Disabled dropdown discoverability | Repaired for audited TaskDialog controls |

## Task/Subtask Parity Matrix

| Workflow | Task | Subtask | Status |
| --- | --- | --- | --- |
| Can be a dependency predecessor | Yes | Yes, when leaf/open | Closed |
| Can be a dependency successor | Yes | Yes, when persisted | Closed |
| FS/SS/FF/SF type support | Yes | Yes | Closed |
| Lag/lead support | Yes | Yes | Closed |
| Self-dependency rejection | Yes | Yes | Closed |
| Duplicate rejection | Yes | Yes | Closed |
| Cross-project rejection | Yes | Yes | Closed |
| Cycle rejection | Yes | Yes | Closed |
| CPM result propagation | Yes | Yes | Closed |
| WBS/Gantt propagation | Yes | Yes | Closed |

## Verification Evidence

- Syntax check passed for modified source and new tests.
- `QT_QPA_PLATFORM=offscreen python3 -m pytest todo_bird_app/tests/test_global_interactive_functionality.py -q`
  - 58 passed in 13.56s.
- Focused affected-area run:
  - 305 passed in 36.87s.
- Mandated isolated full regression:
  - Command: `python3 tools/run_isolated_pytest.py`
  - 121/121 files passed.
  - 2817 tests passed.
  - 0 failed, 0 errors, 0 skipped.
  - Peak RSS: 526016 KB.
  - Elapsed: 372.171s.

## Production Database Safety

- Production DB path: `todo_bird_app/data/todo_bird.db`
- SHA-256 before verification: `aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`
- SHA-256 after verification: `aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`
- Read-only counts: 5 projects, 10 tasks, 9 subtasks.
- Human witness rows read-only:
  - Subtask 14: `Excavation Final`, task 14, no parent subtask, dependencies `[]`.
  - Subtask 15: `Reinforcement Final`, task 14, no parent subtask, dependencies `[]`.

## Remaining Release Gate

Automated interaction and regression gates are closed. Human witness is still required because the user-reported workflow must be exercised manually in the live desktop UI before any Beta Ready or Human Accepted statement can be made.
