# Todo Bird Phase 2E Scheduling Engine Integrity Report

Date: 2026-08-27
Classification: `todo_bird_phase2e_scheduling_engine_robust_human_witness_required`

## Scope

Audited the scheduling calculation path for task/subtask timing semantics, working-calendar arithmetic, dependencies, CPM forward/backward pass, TF/FF, criticality, constraints, deadlines, actual execution, baseline/revision snapshots, and performance. This was not a visual redesign and did not start Phase 2F.

## Authorities Reviewed

- Planned elapsed span: `estimated_duration`.
- Planned work effort: `planned_effort_minutes`.
- Daily dedication: `daily_dedication_minutes`.
- Actual work effort: `actual_duration`.
- Actual elapsed span: explicit Actual Start to explicit Actual Finish, or Actual Start to display-only canonical now for in-progress analysis. It is full calendar elapsed time and is never reduced by the working calendar.
- Current forecast: `CPMSchedulingService.calculate_schedule`.
- Working calendar: `schedule_calendar_service.py`.
- Constraints/deadlines: `schedule_constraint_service.py` and CPM diagnostics.
- Baseline/revision snapshots: immutable `schedule_versions` and `schedule_version_items`.

## Defects Found And Repaired

1. High: negative Free Float was silently clamped to zero in the CPM result.
   - Evidence: new test `test_negative_free_float_value_is_not_silently_clamped` failed with `0 == -360`.
   - Root cause: `CPMSchedulingService` stored `max(0, ff_minutes)`.
   - Fix: preserve `int(ff_minutes)` in `ScheduleNodeResult.free_float_minutes` while retaining `NEGATIVE_FLOAT` diagnostics.
   - Code: `todo_bird_app/services/cpm_scheduling_service.py:1152`.

2. High: schedule snapshot duration could become calendar wall span instead of `estimated_duration` when a CPM object was supplied.
   - Evidence: new test failed with `4320 == 1440` for a Friday-to-Monday one-working-day task.
   - Root cause: `ScheduleNodeResult` has no `planned_duration_minutes`, so `_snapshot_from_record` computed wall elapsed from CPM start/finish before using record duration.
   - Fix: use CPM duration when explicitly present, otherwise use record `estimated_duration`, with wall elapsed only as last fallback.
   - Code: `todo_bird_app/services/schedule_version_service.py:72`.

3. High: schedule-version internal CPM ignored the DB project calendar.
   - Evidence: new test failed with `2026-09-12 09:00` instead of Mon-Fri calendar finish `2026-09-14 09:00`.
   - Root cause: `ScheduleVersionService.capture_current_schedule_snapshot` calculated CPM without passing `project_calendar`.
   - Fix: added DB calendar adapter and passed it into CPM.
   - Code: `todo_bird_app/services/schedule_version_service.py:180` and `todo_bird_app/services/schedule_version_service.py:228`.

4. Medium: deep WBS traversal had recursion risk that could affect Gantt baseline summary traversal and large nested WBS structures.
   - Evidence: new deep hierarchy witness covers 1200 nested levels.
   - Fix: made `WBSService.build_from_raw` and `WBSService.get_descendants` iterative.
   - Code: `todo_bird_app/services/wbs_service.py:313` and `todo_bird_app/services/wbs_service.py:403`.

## Confirmed Correct After Audit

- Criticality is strict `TF == 0`; negative TF is distinct and not normal critical.
- FNLT is evaluated as `LF <= constraint`, with negative float when EF exceeds the constraint.
- Deadlines are deterministic SAFE/MISSED using `EF <= deadline` or `EF > deadline`; no arbitrary risk window is active.
- FS/SS/FF/SF with lag/lead use calendar arithmetic.
- Actual execution state is derived only from actual start/finish fields.
- Early actual start does not rewrite current forecast.
- Open actual analysis uses canonical now only for display/analysis and does not persist a finish.
- Actual elapsed spans weekends and non-working days.
- Cycle/self/missing/duplicate dependency diagnostics are covered by existing suites.

## Tests

- New witness suite first run: 3 failed defects reproduced, then 20 passed after repair.
- Targeted impacted run: 20 files, 676 passed, 0 failed, 0 errors, peak RSS 157304 KB.
- Full isolated regression: 109 files, 2318 passed, 0 failed, 0 errors, peak RSS 560416 KB, elapsed 339.168s.

Command:

```bash
python3 tools/run_isolated_pytest.py --timeout 140
```

## Performance

Pure-data benchmark on this host:

| Tasks | CPM seconds | WBS rollup seconds | Gantt adapter seconds |
| ---: | ---: | ---: | ---: |
| 100 | 0.0034 | 0.0024 | 0.0028 |
| 1000 | 0.0163 | 0.0217 | 0.0079 |
| 5000 | 0.1025 | 0.1107 | 0.0440 |

## Production DB Hash

- Before validation: `0fadcb23e4b5361985d93643a122d1744dc00f0c3800fb1a3d5c955caafea05f`
- After validation: `0fadcb23e4b5361985d93643a122d1744dc00f0c3800fb1a3d5c955caafea05f`

Production DB was not mutated.
