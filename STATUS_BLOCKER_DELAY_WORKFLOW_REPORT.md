# Todo Bird Phase 2E Status, Blocker, and Delay Workflow Report

Date: 2026-09-03

Final classification:

`todo_bird_phase2e_live_ui_runtime_s1_failures_fixed_human_witness_required`

## Human-Witness Failure

The user reported that the Status -> Blocker/Delay Management dropdowns were visually present but not working reliably.

## Root Cause

The repaired path showed three issues:

1. Blocker/delay controls were correctly gated by status, but disabled controls did not consistently explain why they were disabled.
2. Category normalization accepted ambiguous stored values such as lowercase `none`, empty string, and `null`.
3. Without strict normalization, category-required validation could become confusing and appear broken to the user.

## Implementation

Task Dialog changes:

- Added stable object names and accessible names:
  - `task_status_combo`
  - `blocker_category_combo`
  - `blocker_reason_input`
  - `blocker_notes_input`
- Normalized stored blocker/delay category values:
  - `""`
  - `"none"`
  - `"None"`
  - `"null"`
- Disabled blocker/delay controls now explain that they become available only when Status is Blocked or Delayed.
- Enabled blocker/delay controls now expose actionable tooltips.
- Save validation now treats empty/none/null category values as missing.
- Reason validation remains mandatory for Blocked and Delayed states.

## State Gate

| Status | Blocker/Delay Fields |
| --- | --- |
| Inbox | Disabled |
| Planned | Disabled |
| In Progress | Disabled |
| Blocked | Enabled |
| Delayed | Enabled |
| Moved | Disabled |
| Completed | Disabled |
| Cancelled | Disabled |

## Tests Added

- `todo_bird_app/tests/test_status_blocker_delay_workflow.py`
  - 59 tests.
  - Covers immediate status gating, non-blocker saves, Blocked/Delayed category and reason validation, category persistence, lowercase/empty/null normalization, task-done checkbox state transitions, combo focus/model behavior, tooltips, and validation bypass prevention.

## Verification

- Status/blocker/delay workflow: 59 passed.
- Focused affected-area run: 305 passed.
- Full isolated regression: 121/121 files, 2817 tests passed, 0 failures.

## Release Note

The automated gate is closed for the repaired blocker/delay workflow. Human witness is still required before declaring the workflow Human Accepted.

## 2026-09-03 Reopened S1 Addendum

The reopened runtime audit found the earlier report was incomplete for live interaction proof and subtask parity:

- TaskDialog now logs real `currentIndexChanged`, `currentTextChanged`, and `activated` handler execution for status changes.
- TaskDialog status and blocker category popup views now have stable object names and strong focus policy for mouse-open regression coverage.
- The inline "Edit Subtask Details" dialog now has the same Status and Blocker/Delay Management group.
- The canonical `SubtaskDialog` now has matching status/blocker/delay controls and save validation.
- Subtask workflow persistence is protected by `_ensure_subtask_workflow_schema(...)`, adding `status`, `delay_category`, `delay_reason`, `delay_notes`, and `delay_recorded_at` where needed while keeping release schema version 16.

Current proof:

- `test_status_blocker_delay_workflow.py`: 59 passed inside tail regression.
- `test_phase2e_s1_live_runtime_forensics.py`: 43 passed.
- `test_double_click_edit_workflow.py`: covered in the 223-test adjacent regression.
- `test_phase2d_schedule_baseline_variance.py`: 68 passed after legacy migration replay.

The automated blocker/delay workflow is fixed for task and subtask paths. Human witness remains required.
