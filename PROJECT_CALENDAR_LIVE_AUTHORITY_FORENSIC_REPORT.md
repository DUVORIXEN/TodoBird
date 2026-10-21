# Project Calendar Live Authority Forensic Report

Date: 2026-08-28
Final classification: `todo_bird_phase2e_project_calendar_live_authority_fixed_human_witness_required`

No Phase 2F started or authorized.

## Witness Failure Reproduction

Live production data was inspected read-only.

Project: `SCHEDULING WITNESS FINAL`

Observed raw data:

- Project id: `6`
- Project row `working_weekdays`: `NULL`
- Project row `calendar_exceptions`: `[]`
- Global setting `working_weekdays`: `[0, 1, 2, 3, 4, 5]`
- Task id: `14`
- Task title: `Foundation`
- Planned start: `2026-09-01 09:00`
- Stored finish: `2026-09-07 09:00`
- Stored estimated duration: `7200` minutes
- Sep 5 project exception: none

Old effective result:

- Project `NULL` calendar became hard Mon-Fri.
- Sep 5 was treated as non-working.
- Five nominal working days from `2026-09-01 09:00` landed on `2026-09-07 09:00`.

Corrected effective result:

- Project `NULL` calendar inherits the global Mon-Sat working week.
- Sep 5 is `Working`.
- Five nominal working days from `2026-09-01 09:00` lands on `2026-09-05 09:00`.

## Root Cause Chain

Root cause 1: `DatabaseManager.get_project_calendar()` masked global settings.

When a project had no explicit calendar, it returned `[0, 1, 2, 3, 4]` instead of the configured app working week. This made a globally enabled Saturday invisible to the selected project/task runtime.

Root cause 2: consumers did not share one resolver.

`TaskDialog`, `ScheduleVersionService`, `WBSItemModel`, and `WBSRollupService` built their own `ProjectCalendarSpec` objects. This made dict/list/object differences risky and made fallback behaviour hard to reason about.

Root cause 3: database calendar dictionaries were not first-class inputs.

`ScheduleCalendar.from_project_calendar()` accepted object attributes like `working_weekdays` and `exceptions`, but DB calendar dictionaries use `working_weekdays` and `calendar_exceptions`. Passing DB-shaped data directly could silently revert to Mon-Fri.

Root cause 4: open dialogs did not refresh the calculated target from a changed effective calendar.

An already-open task dialog could keep the old target unless the user touched a scheduling field. The dialog now listens for working-calendar changes and recomputes target/workload state from the common resolver.

Root cause 5: exception type was inferred from display text.

`ProjectCalendarDialog._on_save()` used substring matching, so `"Non-Working Holiday"` could be treated as working because it contains `"Working"`. The type is now stored as a boolean in `Qt.UserRole`.

## Permanent Fix

The calendar authority is now centralized:

- `DatabaseManager.get_project_calendar()` resolves explicit project weekdays, then global `settings.working_weekdays`, then default Mon-Fri.
- `schedule_calendar_service.project_calendar_spec_from_source()` parses dicts, JSON strings, `ProjectCalendarSpec`, `ScheduleCalendar`, and project-like objects.
- `schedule_calendar_service.effective_project_calendar_from_db()` is the DB-backed resolver used by TaskDialog, ScheduleVersionService, WBSItemModel, and WBSRollupService.
- `schedule_calendar_service.classify_calendar_date()` is the UI label authority for working/non-working/holiday/override status.
- `TaskDialog` refreshes schedule target/work effort on working-calendar events and normalizes stored hard-Mon-Fri fallback artifacts on open.
- `WorkEffortEditor` uses the same classifier for visible row status.
- `ProjectCalendarDialog` saves exception type from a boolean role, not from label text.

## Runtime Consumer Findings

| Consumer | Before | After |
| --- | --- | --- |
| Project Calendar dialog | project `NULL` loaded as Mon-Fri; Saturday unchecked for null project calendars | null project calendar inherits global Mon-Sat; Saturday checked |
| DB rows/settings | project id `6` has `working_weekdays=NULL`; settings has Mon-Sat | same stored data, but effective read resolves Mon-Sat |
| ScheduleCalendarService | object-only parsing risk; DB dict risked Mon-Fri fallback | common parser accepts DB dict/spec/object/schedule calendar shapes |
| TaskDialog | existing stale target could remain Sep 7 | live read-only open shows calculated target `2026-09-05 09:00` |
| CPM | with wrong effective calendar, Sep 5 excluded | task id `14` CPM finish `2026-09-05 09:00` |
| WorkEffortEditor | Saturday could be missing from Fixed Daily and labelled generically | 4h/day shows Tue-Sat and `1200` minutes; status labels are precise |
| WBS | internal CPM rebuild had local calendar conversion | internal CPM rebuild uses common resolver |
| Gantt | adapter remains read-only; relied on upstream WBS/CPM metadata where applicable | read-only projection preserved; no raw production mutation |
| Schedule snapshots | local calendar conversion | snapshot capture uses common resolver and produces Sep 5 for task id `14` |

## Test Additions

New file: `todo_bird_app/tests/test_project_calendar_live_authority_forensics.py`

55 targeted tests were added:

- 12 parser shape cases for dict/list/JSON/spec/schedule calendar/project model/duplicate exception inputs.
- 12 date-status label cases for working, non-working, holiday, non-working exception, and working override.
- 6 global fallback calendar cases proving project `NULL` inherits global weekdays.
- Explicit project calendar override test.
- Exception persistence under global fallback test.
- New dialog, reopened stale dialog, already-open project-calendar change, already-open global-calendar change, and opened-after-change TaskDialog tests.
- WorkEffortEditor status label tests.
- ProjectCalendarDialog boolean-role save tests for non-working and working exception rows.
- Source guards proving runtime consumers use the shared calendar authority.
- CPM DB-dict conversion cases.
- Production read-only witness for `SCHEDULING WITNESS FINAL`.

## Validation Evidence

Focused tests:

- `python3 -m pytest todo_bird_app/tests/test_project_calendar_live_authority_forensics.py -q`: 55 passed.
- `python3 -m pytest todo_bird_app/tests/test_project_calendar_duration_authority.py -q`: 50 passed.
- `python3 -m pytest todo_bird_app/tests/test_workload_calendar_weekday_authority.py -q`: 27 passed.
- `python3 -m pytest todo_bird_app/tests/test_task_duration_time_roundtrip_forensics.py -q`: 50 passed.
- `python3 -m pytest todo_bird_app/tests/test_scheduling_engine_integrity.py todo_bird_app/tests/test_working_calendar_cpm_authority.py -q`: 96 passed.
- `QT_QPA_PLATFORM=offscreen python3 -m pytest todo_bird_app/tests/test_phase2e_constraints_calendars.py -q`: 100 passed.
- `python3 -m pytest todo_bird_app/tests/test_phase2e_production_db_safety.py -q`: 26 passed.
- `QT_QPA_PLATFORM=offscreen python3 -m pytest todo_bird_app/tests/test_shutdown_lifecycle.py -q`: 23 passed.
- `QT_QPA_PLATFORM=offscreen python3 -m pytest todo_bird_app/tests/test_wbs_raw_summary_human_failure_forensics.py -q`: 21 passed.

Full isolated regression:

- Command: `python3 tools/run_isolated_pytest.py`
- Result: passed.
- Files: 117/117.
- Tests: 2588 passed, 0 failed, 0 errors, 0 skipped.
- Peak RSS: 411420 KB.
- Elapsed: 339.193s.
- Summary JSON: `build/test_reports/isolated_pytest_summary.json`

## Production DB Safety

Production DB was only opened through read-only SQLite URI / `DatabaseManager.read_only()`.

Hash before read-only witness:
`aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`

Hash after read-only witness and full validation:
`aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`

The production row for task id `14` still stores `due_date='2026-09-07'` until the user saves the patched Edit Task dialog. The patched dialog opens the task with the corrected target `2026-09-05 09:00`, so saving from the UI will repair the persisted target without changing `estimated_duration=7200`.

## Remaining Human Witness

The code defect is fixed and automated evidence is green. A human witness is still required because the production DB was not modified by this pass and the final user-facing confirmation must be done through the real desktop UI.

Expected human witness:

- Open `SCHEDULING WITNESS FINAL`.
- Open `Foundation`.
- Confirm Estimated Duration is `5.00 days` / `7200 mins`.
- Confirm calculated target / target finish is `2026-09-05 09:00`.
- Confirm Fixed Daily at 4h/day counts Tue, Wed, Thu, Fri, Sat as five working days.
- Confirm Custom by Day labels Sep 5 as `Working`, not `Holiday`.

Final classification remains:
`todo_bird_phase2e_project_calendar_live_authority_fixed_human_witness_required`
