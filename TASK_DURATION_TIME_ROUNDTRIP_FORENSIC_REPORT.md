# Task Duration Time Roundtrip Forensic Report

Date: 2026-08-28

Classification: `todo_bird_phase2e_task_duration_time_roundtrip_fixed_human_witness_required`

## 1 Scope

This pass investigated the fresh-task scheduling witness:

- Project: `SCHEDULING WITNESS FRESH`
- Task: `Foundation`
- Intended input: start `2026-09-01 09:00`, duration `5 working days`
- Expected under Todo Bird day-level calendar contract: `5.00 days`, `7200 mins`, target finish `2026-09-05 09:00` for Mon-Sat.

No Phase 2F work was started. Production DB access was read-only only.

## 2 Production Witness

Read-only SQLite URI was used against `todo_bird_app/data/todo_bird.db`.

- Hash before: `aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`
- Hash after: `aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`
- Hash unchanged: `True`

Observed live project row:

- `id=5`
- `name='SCHEDULING WITNESS FRESH'`
- `working_weekdays=None`
- `calendar_exceptions='[]'`

Observed live `Foundation` row:

- `id=13`
- `project_id=5`
- `planned_date='2026-09-01'`
- `planned_start_time='00:00'`
- `due_date='2026-09-04'`
- `planned_end_time='00:00'`
- `estimated_duration=5760`
- `planned_effort_minutes=0`
- `daily_dedication_minutes=0`
- `status='In Progress'`

Conclusion: the live row is already contaminated and was not rewritten in this pass. The project row also does not currently contain a persisted Mon-Sat calendar. The code fix and tests use disposable temp DB witnesses for the intended Mon-Sat contract.

## 3 Root Cause

The failure was in the TaskDialog create/edit/reopen authority, not in WBS/Gantt summary presentation.

The old behavior allowed start/date changes and dialog reopen to recalculate `estimated_duration` from the visible finish fields. For an inclusive working-day target such as `2026-09-01 09:00` through `2026-09-05 09:00`, that can collapse to elapsed endpoint distance (`4 days = 5760 mins`) instead of the user's intended scheduled duration (`5 days = 7200 mins`). If finish widgets held midnight defaults, save could persist `00:00` times and the shortened finish/date combination.

The corrected direction is:

- Start + estimated duration + project calendar -> target finish.
- Finish -> estimated duration only when an explicit finish exists and the stored duration is zero, or when the user intentionally edits finish in finish mode.
- Opening and saving an untouched task preserves raw schedule fields exactly.

## 4 Code Changes

`todo_bird_app/widgets/task_dialog.py`

- Added explicit day contract: `ESTIMATED_DAY_MINUTES = 1440`.
- Added bidirectional UI controls: minutes spin plus `EstimatedDurationDaysSpin`.
- Added calendar-aware target helpers:
  - `_finish_from_start_and_duration`
  - `_scheduled_duration_between`
  - `_duration_from_schedule_finish`
- Start/date/project changes now move calculated target finish from existing duration instead of shrinking duration.
- Existing tasks and subtasks recalculate from finish only when stored `estimated_duration` is zero.
- Subtask editor gained `SubtaskEstimatedDurationDaysSpin` and uses the same scheduled duration authority.
- Tasks with actual execution data now open the Schedule tab, preserving the new organization while keeping actual tracking fields visible.

`todo_bird_app/controllers/task_controller.py`

- Fixed `get_upcoming_tasks` and `get_upcoming_tasks_count` to use `get_current_datetime()` instead of `date.today()`, closing a deterministic full-suite failure on 2026-08-28.

`todo_bird_app/tests/test_planned_duration_authority_batch33a.py`

- Updated two legacy assertions to the corrected authority rule: changing start date/time preserves estimated duration and moves target finish; finish edits still recalculate duration.

`todo_bird_app/tests/test_task_duration_time_roundtrip_forensics.py`

- Added 50 forensic tests covering fresh create/save/reopen, open/save untouched, Mon-Fri/Mon-Sat/7-day oracles for 1/2/5/6/7/10 day cases, start times `00:00`, `08:00`, `09:00`, `13:30`, weekend/holiday/override behavior, baseline/snapshot/WBS/Gantt read paths, subtask parity, source guards, and production DB read-only hash stability.

## 5 Static Search Classification

Source-only search was run over `todo_bird_app` excluding tests, backup files, and `__pycache__`.

Classified write/pass-through authorities:

- `todo_bird_app/widgets/task_dialog.py:2620`: writes `self.duration_spin.value()` into `self.task.estimated_duration`. Correct after direction fix.
- `todo_bird_app/database.py:1508`, `todo_bird_app/database.py:2499`: DB persistence pass-through for task/subtask duration. Correct; no calculation.
- `todo_bird_app/gantt/gantt_chart.py:1449`, `todo_bird_app/views/gantt_view.py:2807`, `todo_bird_app/views/gantt_view.py:2836`, `todo_bird_app/views/gantt_view.py:2857`: Gantt schedule payload writes. Not part of fresh create/reopen; summary/read-only row safety remains covered by tests.
- `todo_bird_app/views/inbox_view.py:243`, `todo_bird_app/views/main_window.py:561`: subtask/new-item payload pass-through. No duration-from-finish calculation.
- `todo_bird_app/models/task.py:243`, `todo_bird_app/models/wbs_item_model.py:334`, `:373`, `:443`: model/read adapter pass-through. No mutation.

Classified calculation authorities:

- `todo_bird_app/widgets/task_dialog.py:185`, `:224`, `:236`, `:249`: corrected dialog target/duration helpers.
- `todo_bird_app/services/schedule_calendar_service.py:147`, `:222`: canonical day-level working-calendar arithmetic.
- `todo_bird_app/services/cpm_scheduling_service.py:548`, `:594`, `:600`: CPM uses raw duration plus calendar arithmetic.
- `todo_bird_app/utils/time_math.py:139`, `:267`: general elapsed-time utility, now not directly used by subtask editor.

Classified `.days` findings:

- `schedule_calendar_service.py`: calendar-day iteration, not raw task duration persistence.
- `timescale_engine.py`, `gantt_chart.py`, `calendar_view.py`: timeline/layout/date-span presentation.
- `gantt_dependency_engine.py:1082`: dependency date-span preservation; time-based branch preserves `estimated_duration` and does not calculate a new stored duration from `.days`.

Classified `date.today()` findings:

- Most remaining findings are UI labels, view anchors, reminder/default-date helpers, or non-persistence services.
- `TaskController.get_upcoming_tasks*` was a real app-time authority mismatch and was fixed to `get_current_datetime()`.

## 6 Validation Evidence

Syntax:

- `python3 -m py_compile todo_bird_app/controllers/task_controller.py todo_bird_app/widgets/task_dialog.py todo_bird_app/tests/test_task_duration_time_roundtrip_forensics.py todo_bird_app/tests/test_planned_duration_authority_batch33a.py` passed.

Focused forensic:

- `python3 tools/run_isolated_pytest.py todo_bird_app/tests/test_task_duration_time_roundtrip_forensics.py --timeout 180 --summary build/test_reports/task_duration_time_roundtrip_forensics.json`
- Result: 1/1 files, 50 passed, 0 failed, 0 errors, peak RSS 1214292 KB, elapsed 24.715s.

Impacted bundle:

- `python3 tools/run_isolated_pytest.py todo_bird_app/tests/test_task_duration_time_roundtrip_forensics.py todo_bird_app/tests/test_task_editor_project_rename_usability.py todo_bird_app/tests/test_wbs_raw_summary_human_failure_forensics.py todo_bird_app/tests/test_planned_duration_authority_batch33a.py todo_bird_app/tests/test_planned_effort_authority_batch33b.py todo_bird_app/tests/test_work_calendar_persistence_batch33d.py todo_bird_app/tests/test_phase2c1_dependency_picker_project_scope.py --timeout 180 --summary build/test_reports/task_duration_time_roundtrip_impacted.json`
- Result: 7/7 files, 134 passed, 0 failed, 0 errors, peak RSS 1214484 KB, elapsed 33.849s.

Additional deterministic full-suite stops fixed before final pass:

- `test_cross_view_consistency_and_s1_closure.py`: 56 passed after replacing upcoming-task `date.today()` with app time authority.
- `test_execution_aware_schedule_authority.py`: 50 passed after opening actual-tracked tasks on Schedule tab.

Full isolated regression:

- `python3 tools/run_isolated_pytest.py --timeout 180 --summary build/test_reports/task_duration_time_roundtrip_full.json`
- Result: 114/114 files, 2456 passed, 0 failed, 0 errors, 0 skipped, peak RSS 1214520 KB, elapsed 360.032s.

## 7 Release Decision

Fixed in code and regression-covered. The production witness row remains contaminated because production DB was intentionally read-only in this pass.

Final classification:

`todo_bird_phase2e_task_duration_time_roundtrip_fixed_human_witness_required`

This report does not declare Beta Ready, Human Accepted, or Phase 2F.
