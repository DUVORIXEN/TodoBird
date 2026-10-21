# WBS Raw Summary Human Failure Forensic Report

## 1 Classification

`todo_bird_phase2e_wbs_raw_summary_authority_repaired_again_human_witness_required`

This repair is not a Human Accepted or Beta Ready declaration. Phase 2F is not started.

## 2 Current live DB state

Read-only production inspection was performed against `todo_bird_app/data/todo_bird.db` using SQLite `mode=ro`. The production DB hash was unchanged by the witness read.

Project `SCHEDULING WITNESS` exists as project id `5`.

Parent task `Foundation` exists as task id `13` with these raw DB fields:

- `planned_date`: `2026-09-01`
- `planned_start_time`: `00:00`
- `due_date`: `2026-09-05`
- `planned_end_time`: `00:00`
- `estimated_duration`: `5760`
- `planned_effort_minutes`: `0`
- `daily_dedication_minutes`: `0`
- `show_in_gantt`: `1`
- `status`: `In Progress`
- `updated_at`: `2026-08-27 15:23:11`

Children located for task id `13`:

- Subtask id `12`, `Excavation`: `planned_date=2026-09-01`, `due_date=2026-09-02`, `planned_start_time=00:00`, `planned_end_time=00:00`, `estimated_duration=1440`
- Subtask id `13`, `Reinforcement`: `planned_date=2026-09-02`, `due_date=2026-09-04`, `planned_start_time=09:00`, `planned_end_time=00:00`, `estimated_duration=2340`

## 3 Whether witness record was already contaminated

`LEGACY TEST RECORD CONTAMINATED`

The live production parent already contains raw `due_date=2026-09-05` and raw `estimated_duration=5760`. That means the failed human witness cannot be used to prove the current read path is still deriving summary fields at dialog-open time, because the DB source row itself already stores the summary-like values.

No production repair was attempted.

## 4 Exact first authority-crossing point

For the current live record, the first observed authority crossing point is the database row itself: `DatabaseManager.get_task_by_id(13)` already returns `due_date=2026-09-05` and `estimated_duration=5760`.

A fresh temp-DB reproduction isolated the active remaining root cause before this fix:

- A raw parent with no explicit finish entered `planned_date=2026-09-01`, `planned_start_time=09:00`, `due_date=None`, `planned_end_time=None`, `estimated_duration=7200`.
- Opening the real `TaskDialog` populated Qt finish widgets from defaults instead of preserving the null-finish contract.
- Saving the dialog materialized raw finish fields back into the task through `TaskDialog.on_save()`.
- The `WorkEffortEditor` could also recalculate and overwrite raw effort fields for no-finish tasks during the same save path.

So the proven current-code authority crossing was in `TaskDialog` field population/save semantics for tasks with no explicit raw finish. The earlier Gantt/WBS projection leak had already been repaired in the prior pass, but the dialog still had its own null-finish write hazard.

## 5 Exact write path

The write path capable of contaminating a raw parent was:

`DatabaseManager.get_task_by_id` -> `Task.from_row` -> `TaskController.get_task` -> `TaskDialog.__init__` -> finish widget default population -> `TaskDialog.on_save()` -> `TaskController.update_task()` -> `DatabaseManager.update_task()` -> SQL `UPDATE tasks`.

After the repair, write tracing in the fresh witness shows zero schedule-field `UPDATE tasks` statements from:

- Child creation
- WBS refresh
- Gantt refresh
- Edit Task open from the real Gantt action path

The traced schedule fields were `planned_date`, `due_date`, `planned_start_time`, `planned_end_time`, and `estimated_duration`.

## 6 TaskDialog source path

`TaskDialog` now treats passed objects as hints, not authority. For an existing task with a positive id, it re-resolves the canonical raw task through:

`TaskDialog._resolve_canonical_raw_task()` -> `DatabaseManager.get_task_by_id(task.id)` -> `Task.from_row(row)`

The dialog records this as `task_source_path = "DatabaseManager.get_task_by_id"` in the tested path.

This prevents a WBS row, Gantt row, summary-decorated `Task`, stale selected-task reference, or task-shaped projection object from feeding editable raw fields.

## 7 Finish-field semantic contract

Raw planned finish is optional persisted user input.

- If `Planned finish` is checked, `due_date` and `planned_end_time` are raw editable/persisted fields.
- If `Planned finish` is unchecked, `due_date` and `planned_end_time` remain `None`, and `estimated_duration` remains the editable raw duration authority.
- WBS summary finish is display/rollup metadata only.
- CPM forecast finish is forecast metadata only.

The dialog may display a disabled placeholder date when no raw finish exists, but save must persist `None` for raw finish while the checkbox is unchecked.

## 8 Duration authority

`estimated_duration` is raw task authority. WBS rollup must never replace a parent task's raw `estimated_duration` with the derived summary span.

For the fresh witness, the parent raw duration remains `7200` minutes, while the derived WBS/Gantt summary span remains `5760` minutes from `2026-09-01 09:00` to `2026-09-05 09:00`.

Child creation, child edit, child delete, indent, outdent, WBS refresh, Gantt refresh, save/reopen, and app restart all preserve the parent raw duration in the new forensic tests.

## 9 Fix applied

Changed `todo_bird_app/widgets/task_dialog.py`:

- `TaskDialog.__init__` now canonicalizes existing task input through `_resolve_canonical_raw_task`.
- Added explicit `Planned finish` checkbox semantics for main tasks.
- No-finish tasks keep `duration_spin` editable and do not recalculate duration from finish widgets.
- `TaskDialog.on_save()` persists raw `due_date` and `planned_end_time` only when `Planned finish` is checked.
- No-finish save preserves raw `planned_effort_minutes`, `daily_dedication_minutes`, and `allocation_mode` unless the user actually touches effort controls.
- Subtask editing now has the same nullable finish contract.

Added `todo_bird_app/tests/test_wbs_raw_summary_human_failure_forensics.py` with fresh and legacy contamination coverage.

## 10 Fresh witness result

Fresh temp-DB project: `SCHEDULING WITNESS FRESH`.

Calendar: Monday through Saturday.

Raw parent after open/save/reopen:

- `planned_date`: `2026-09-01`
- `planned_start_time`: `09:00`
- `due_date`: `None`
- `planned_end_time`: `None`
- `estimated_duration`: `7200`
- `planned_effort_minutes`: `3000`
- `daily_dedication_minutes`: `480`

Derived WBS/Gantt summary:

- `summary_start`: `2026-09-01 09:00`
- `summary_finish`: `2026-09-05 09:00`
- `summary_span`: `5760`

The fresh record passes the intended raw-vs-summary contract.

## 11 Legacy contamination result

The intentionally contaminated temp-DB case is not silently repaired. When a row already stores `due_date=2026-09-05`, `planned_end_time=09:00`, and `estimated_duration=5760`, `TaskDialog` accurately displays those raw DB values.

The production `SCHEDULING WITNESS` row is in this same class of evidence: it is contaminated input data, not proof that the current WBS/Gantt read path is still deriving values into the dialog.

Existing production records require human review or explicit user-approved repair. They were not rewritten by this task.

## 12 Tests

Added targeted integration coverage for:

1. Fresh parent raw duration preserved after dialog save
2. Fresh parent raw start preserved
3. Child creation causes no parent schedule update
4. WBS refresh causes no parent schedule update
5. Gantt refresh causes no parent schedule update
6. Real Gantt open path uses canonical `TaskDialog`
7. `TaskDialog` displays raw duration
8. `TaskDialog` displays null planned-finish semantics
9. WBS summary still produces Sep 1 to Sep 5
10. Gantt summary still produces Sep 1 to Sep 5
11. Summary aliases do not leak into `TaskDialog`
12. Cache invalidation rebuilds from DB after child mutation
13. Save/reopen preserves raw inputs
14. App restart reopens raw inputs
15. Nested WBS parent raw duration preserved
16. Edit child preserves parent duration
17. Delete child preserves parent duration
18. Indent preserves parent duration
19. Outdent preserves parent duration
20. Production DB hash unchanged by temp forensic flow
21. Contaminated legacy record is not silently repaired

Validation:

- `python3 -m py_compile todo_bird_app/widgets/task_dialog.py todo_bird_app/tests/test_wbs_raw_summary_human_failure_forensics.py` passed.
- `python3 tools/run_isolated_pytest.py todo_bird_app/tests/test_wbs_raw_summary_human_failure_forensics.py --timeout 160 --summary build/test_reports/wbs_raw_summary_human_failure_forensics.json` passed: 1/1 files, 21 passed, 0 failed, 0 errors, peak RSS `198116` KB, elapsed `2.662`s.
- `python3 tools/run_isolated_pytest.py todo_bird_app/tests/test_wbs_raw_summary_human_failure_forensics.py todo_bird_app/tests/test_wbs_raw_vs_summary_authority.py todo_bird_app/tests/test_planned_duration_authority_batch33a.py todo_bird_app/tests/test_planned_effort_authority_batch33b.py todo_bird_app/tests/test_work_calendar_persistence_batch33d.py todo_bird_app/tests/test_phase2c1_dependency_picker_project_scope.py --timeout 180 --summary build/test_reports/wbs_raw_summary_human_failure_impacted.json` passed: 6/6 files, 135 passed, 0 failed, 0 errors, peak RSS `197884` KB, elapsed `9.662`s.

## 13 Full regression

Full isolated regression was run once with:

`python3 tools/run_isolated_pytest.py --timeout 180 --summary build/test_reports/wbs_raw_summary_human_failure_full.json`

Result: passed, 112/112 files, 2401 passed, 0 failed, 0 errors, peak RSS `434464` KB, elapsed `328.703`s.

This was not rerun after the IDE crash/resume because no further code changed before report creation.

## 14 Production DB hash

Production DB: `todo_bird_app/data/todo_bird.db`

- Before read-only live witness: `aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`
- After read-only live witness: `aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`
- Hash unchanged: `True`

The forensic temp-flow test also asserts production DB bytes remain unchanged while temp-DB witness operations run.

## 15 Human re-witness steps

Do not reuse the old production `SCHEDULING WITNESS` record, because it is already contaminated.

1. Create a new disposable project named `SCHEDULING WITNESS FRESH HUMAN`.
2. Set project calendar to Monday through Saturday.
3. Create parent task `Foundation` with planned start `2026-09-01 09:00`.
4. Enter estimated duration as 5 working days. In current storage terms, this is expected to remain raw `estimated_duration=7200`.
5. Leave `Planned finish` unchecked.
6. Add child `Excavation`, start `2026-09-01 09:00`, 2 working days.
7. Add child `Reinforcement`, start `2026-09-02 09:00`, 3 working days.
8. Open WBS/Gantt and confirm the derived summary shows `2026-09-01 09:00` to `2026-09-05 09:00`.
9. Open `Foundation` -> Edit Task.
10. Confirm `Planned finish` is unchecked.
11. Confirm raw planned start remains `2026-09-01 09:00`.
12. Confirm raw estimated duration remains the 5-day authority value and is not `5760`.
13. Save, close, reopen the task, and confirm the same raw values remain.

`todo_bird_phase2e_wbs_raw_summary_authority_repaired_again_human_witness_required`
