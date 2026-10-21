# Project Calendar Live Authority Diagnostic

Date: 2026-08-28
Classification: `todo_bird_phase2e_project_calendar_live_authority_fixed_human_witness_required`

No Beta Ready, no Human Accepted, no Phase 2F.

## Root Cause

The project calendar service itself was not the primary arithmetic defect. The live failure was an effective-calendar authority defect:

1. Production project `SCHEDULING WITNESS FINAL` is project id `6`.
2. Its project row has `working_weekdays = NULL` and `calendar_exceptions = []`.
3. The settings table has `working_weekdays = [0, 1, 2, 3, 4, 5]`, so Saturday is enabled globally.
4. `DatabaseManager.get_project_calendar()` converted a `NULL` project calendar into hard Mon-Fri `[0, 1, 2, 3, 4]`, masking the global Mon-Sat setting for TaskDialog, WorkEffortEditor, CPM, WBS, and snapshots.
5. Several consumers rebuilt their own calendar spec, so dict/object/default behaviour could drift.
6. `ProjectCalendarDialog._on_save()` inferred exception type from display text; `"Non-Working Holiday"` contained `"Working"` and could be saved as a working exception.

## Corrected Precedence

1. Date exception / override for the project.
2. Explicit project working weekdays.
3. Global configured working weekdays when the project has no explicit calendar.
4. Default Mon-Fri only when neither project nor global configuration is valid.

Duplicate date exceptions keep the last saved/listed decision, matching `ProjectCalendarSpec.is_working_day()`.

## Label Semantics

The workload calendar status labels are now distinct:

| Condition | Label |
| --- | --- |
| Weekday enabled by effective calendar | `Working` |
| Weekday disabled by effective calendar | `Non-working` |
| Named non-working exception containing holiday | `Holiday` |
| Other non-working exception | `Non-working exception` |
| Explicit working-date exception | `Working override` |

## Production Read-Only State

Production DB path: `todo_bird_app/data/todo_bird.db`

Hash before/after read-only witnesses:
`aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`

| Source | Evidence |
| --- | --- |
| `projects` | id `6`, name `SCHEDULING WITNESS FINAL`, `working_weekdays = NULL`, `calendar_exceptions = []` |
| `settings` | `working_weekdays = [0, 1, 2, 3, 4, 5]` |
| `project_calendar_exceptions` | no rows for project `6`; no row for `2026-09-05` |
| `tasks` | task id `14`, title `Foundation`, start `2026-09-01 09:00`, stored finish `2026-09-07 09:00`, `estimated_duration = 7200` |

Production was inspected read-only only. The stored task row remains unchanged until the user saves it through the patched dialog.

## Runtime Consumer Trace

| Consumer | Effective calendar after fix | Source path |
| --- | --- | --- |
| Project Calendar dialog | checked weekdays `[0, 1, 2, 3, 4, 5]`; Saturday checked; no exceptions | `DatabaseManager.get_project_calendar()` |
| DB read model | project `NULL` inherits global setting `[0, 1, 2, 3, 4, 5]` | `database.py:get_project_calendar` |
| ScheduleCalendarService | `ScheduleCalendar(working_weekdays=(0,1,2,3,4,5), holidays=[], working_overrides=[])` | `effective_project_calendar_from_db()` / `project_calendar_spec_from_source()` |
| TaskDialog | existing stale production task opens with target `2026-09-05 09:00` from `7200` minutes | `_current_project_calendar_spec()` and stale Mon-Fri artifact normalization |
| WorkEffortEditor | fixed daily 4h/day shows `5 working days (Tue, Wed, Thu, Fri, Sat) = 20h` | project calendar provider + `classify_calendar_date()` |
| CPM | task id `14` earliest finish `2026-09-05 09:00` | `CPMSchedulingService.calculate_schedule()` |
| Schedule snapshot | task id `14` snapshot finish `2026-09-05 09:00` | `ScheduleVersionService.capture_current_schedule_snapshot()` |
| WBS | one-node production hierarchy read-only; rollup path now resolves calendar through shared helper | `WBSService` + `WBSRollupService` |
| Gantt | one read-only projected row for `Foundation`; adapter remains non-mutating | `GanttWBSAdapter.build_project_rows()` |

## Code Fixes

| File | Change |
| --- | --- |
| `todo_bird_app/database.py` | `get_project_calendar()` now uses explicit project weekdays, then global `settings.working_weekdays`, then Mon-Fri default. |
| `todo_bird_app/services/schedule_calendar_service.py` | Added robust dict/object/spec parser, common DB resolver, date classifier, duplicate exception precedence, and label vocabulary. |
| `todo_bird_app/widgets/task_dialog.py` | Uses the common resolver, refreshes on working-calendar changes, and normalizes stale hard-Mon-Fri stored finish artifacts on open. |
| `todo_bird_app/widgets/work_effort_editor.py` | Uses common calendar classification for row labels and keeps project calendar provider as the live authority. |
| `todo_bird_app/widgets/project_calendar_dialog.py` | Stores exception type in `Qt.UserRole` boolean instead of parsing user-facing text. |
| `todo_bird_app/services/schedule_version_service.py` | Uses common DB calendar resolver. |
| `todo_bird_app/models/wbs_item_model.py` | Uses common DB calendar resolver for internal CPM rebuild. |
| `todo_bird_app/services/wbs_rollup_service.py` | Uses common DB calendar resolver for automatic CPM rollup calculation. |

## Validation

Focused validation:

- `test_project_calendar_live_authority_forensics.py`: 55 passed.
- `test_project_calendar_duration_authority.py`: 50 passed.
- `test_workload_calendar_weekday_authority.py`: 27 passed.
- `test_task_duration_time_roundtrip_forensics.py`: 50 passed.
- `test_scheduling_engine_integrity.py` + `test_working_calendar_cpm_authority.py`: 96 passed.
- `test_phase2e_constraints_calendars.py`: 100 passed with `QT_QPA_PLATFORM=offscreen`.
- `test_phase2e_production_db_safety.py`: 26 passed.
- `test_shutdown_lifecycle.py`: 23 passed with `QT_QPA_PLATFORM=offscreen`.

Full isolated validation:

- Command: `python3 tools/run_isolated_pytest.py`
- Result: 117/117 files, 2588 passed, 0 failed, 0 errors, 0 skipped.
- Peak RSS: 411420 KB.
- Elapsed: 339.193s.

One direct local pytest attempt against Qt suites aborted before `QT_QPA_PLATFORM=offscreen` was set for those processes. The same files passed when rerun headless, and the isolated runner completed successfully.
