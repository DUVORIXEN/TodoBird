# Project Calendar Duration and Workload Authority Report

Date: 2026-08-28
Classification: `todo_bird_phase2e_project_calendar_duration_workload_fixed_human_witness_required`

## Scope

This pass stayed inside Phase 2E. It did not start Phase 2F and does not declare Beta Ready or Human Accepted.

The repaired human-witness defects were:

1. A five-working-day task on a Mon-Sat project calendar starting 2026-09-01 09:00 must calculate target finish as 2026-09-05 09:00, not 2026-09-07.
2. Workload Planning fixed daily and custom daily rows must use the selected project calendar, not global/default Mon-Fri settings.

## Root Cause

The raw storage representation and endpoint placement were mixed:

- `estimated_duration` correctly stores nominal minutes (`1 day = 1440`, `5 days = 7200`).
- Some UI/engine paths still treated exact whole-day task duration as elapsed working minutes, so five nominal working days could land after consuming five 24-hour working-minute blocks rather than selecting the fifth working date.
- `WorkEffortEditor` listened for calendar changes, but its active weekday authority came from global settings. That made Saturday disappear for selected Mon-Sat projects.
- The large duration-forensics test file only called `dialog.close()`, leaving child Qt workload editors and deferred deletes alive across many full `TaskDialog` constructions. In isolated validation this reproduced the user's crash pattern: timeout at 140s and about 2.05 GB RSS.

## Repairs

- Added `add_working_days_preserve_time` / `subtract_working_days_preserve_time` authority for nominal whole-day task placement.
- Kept fractional day entries on working-minute placement because the persisted model has no separate fractional-day count field.
- Updated `TaskDialog._finish_from_start_and_duration` so exact whole-day durations use project-calendar day placement and retain the same clock.
- Updated `CPMSchedulingService` so task durations use nominal whole-day placement when a project calendar is available; dependency lag/lead remains minute arithmetic.
- Updated `WorkEffortEditor` to accept a selected-project calendar provider and to pass project holidays/working overrides into fixed daily and custom by day calculations.
- Wired main-task and subtask `WorkEffortEditor` instances to `TaskDialog._current_project_calendar_spec`.
- Emitted `working_calendar_changed` after `DatabaseManager.set_project_calendar`.
- Added `TaskDialog.cleanup`, `closeEvent`, and `deleteLater` cleanup for child workload editor and window registry lifecycle.
- Updated the heavy duration-forensics test helper to call cleanup, close, deleteLater, and drain deferred Qt deletes.

## Human Witness Result

Focused temp-DB witness:

- Project calendar: Mon-Sat.
- Task: `Foundation`.
- Start: 2026-09-01 09:00.
- Estimated duration: 5.0 days.
- Stored duration: 7200 minutes.
- Calculated target finish: 2026-09-05 09:00.
- Fixed daily workload: 4h/day x Tue, Wed, Thu, Fri, Sat = 1200 planned effort minutes.

The old Sep 7 result is no longer produced for the Mon-Sat witness.

## Fractional-Day Decision

Documented behavior:

- 0.5 day = 720 nominal minutes, placed by working-minute arithmetic.
- 1.0 day = exact whole-day placement on the first working date.
- 1.5 days = 2160 nominal minutes, placed by working-minute arithmetic.
- 2.0 days = exact whole-day placement on the second working date.
- 5.0 days = exact whole-day placement on the fifth working date.

This avoids inventing a new fractional-day calendar model during Phase 2E.

## Static Audit

Command:

`rg -n "range\(5\)|Mon-Fri|Monday|Friday|weekday\(\) < 5|Qt\.Friday|\[0, 1, 2, 3, 4\]|\(0, 1, 2, 3, 4\)" todo_bird_app --glob '!todo_bird_app/tests/**' --glob '!todo_bird_app/models/__tests__/**' --glob '!**/*.bak' --glob '!**/*.bak_*' --glob '!**/__pycache__/**'`

Classified remaining occurrences:

- Safe defaults/fallbacks: `settings_manager.py`, `database.py`, `schedule_calendar_service.py`, `schedule_constraint_service.py`, `utils/working_calendar.py`.
- Safe selected-project fallback after DB calendar lookup: `task_dialog.py`, `schedule_version_service.py`, `wbs_item_model.py`, `wbs_rollup_service.py`.
- Safe calendar UI labels/default checkboxes: `project_calendar_dialog.py`, `working_week.py`.
- No remaining workload authority leak in `work_effort_editor.py`.
- `schedule_variance_service.py` has a no-CPM fallback that uses raw elapsed minutes only when no CPM node/calendar authority is supplied; WBS/Gantt active schedule paths use CPM first.

## Validation

Compile check passed:

`python3 -m py_compile todo_bird_app/services/schedule_calendar_service.py todo_bird_app/services/cpm_scheduling_service.py todo_bird_app/widgets/work_effort_editor.py todo_bird_app/widgets/task_dialog.py todo_bird_app/database.py todo_bird_app/tests/test_project_calendar_duration_authority.py todo_bird_app/tests/test_workload_calendar_weekday_authority.py todo_bird_app/tests/test_working_calendar_cpm_authority.py`

Focused authority validation:

- `test_project_calendar_duration_authority.py`: 50 passed.
- `test_workload_calendar_weekday_authority.py`: 27 passed.
- `test_working_calendar_cpm_authority.py`: 88 passed.
- Total focused group: 165 passed, 0 failed, 0 errors.

Regression fallout fixed and validated:

- `test_phase2b_schedule_intelligence_ui.py`: 15 passed after updating old fixture dates to the new nominal-day semantics.
- `test_phase2e_runtime_constraint_refresh.py`: 13 passed after updating old constraint fixtures to remain genuinely conflicting under the new semantics.
- `test_scheduling_engine_integrity.py`: 8 passed after updating snapshot finish expectations while preserving raw `duration_minutes`.

Qt lifetime/memory fix evidence:

- Before cleanup repair: `test_task_duration_time_roundtrip_forensics.py` timed out at 140s and reached 2053172 KB RSS.
- After cleanup repair: the same file passed 50 tests in 5.368s with 131368 KB RSS.
- Final full run: the same file passed 50 tests in 5.680s with 131584 KB RSS.

Final full isolated validation:

- Command: `python3 tools/run_isolated_pytest.py`
- Result: 116/116 files passed.
- Totals: 2533 passed, 0 failed, 0 errors, 0 skipped.
- Peak RSS: 410348 KB.
- Elapsed: 334.343s.

## Production DB Safety

Read-only production DB probe:

- Before hash: `aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`
- After hash: `aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`
- Unchanged: True
- Counts read: projects=5, tasks=10, schedule_versions=3

No production DB writes were performed.

## Release Gate

Code defect status: fixed.

Required final classification:

`todo_bird_phase2e_project_calendar_duration_workload_fixed_human_witness_required`

Human witness is still required. This report does not declare Beta Ready, Human Accepted, or Phase 2F.
