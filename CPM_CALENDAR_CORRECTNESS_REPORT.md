# CPM Calendar Correctness Report

## 1. Scope

Phase 2E S1 blocker 4 is closed at implementation level for working-calendar CPM calculation gaps. This report covers the pure calendar arithmetic authority, CPM forward pass, CPM backward pass, float math, constraints, dependencies, milestones, actual-execution non-regression, Gantt/WBS consumption, performance, regression evidence, and production DB safety witness.

This does not start Phase 2F and does not declare human acceptance or beta readiness.

## 2. Root Cause

`CPMSchedulingService.calculate_schedule(..., project_calendar=...)` accepted a project calendar, but CPM math still used raw `timedelta` for durations, lag/lead, finish-to-start conversions, backward pass requirements, float, and tight critical-edge detection. The calendar was only used after the fact to add a `CALENDAR_CONFLICT` diagnostic when a calculated ES landed on a non-working date.

That meant a task could be warned as non-working while still being scheduled through weekends/holidays, which is the core mathematical defect.

## 3. Canonical Authority

New canonical authority: `todo_bird_app/services/schedule_calendar_service.py`.

Rules:

- Working-calendar scope is day-level, not shift-hour scheduling.
- A working date contributes 1,440 working minutes.
- A non-working date contributes 0 working minutes.
- Finish boundaries are exclusive.
- Zero-duration milestones keep `ES == EF` and `LS == LF`.
- Without a project calendar, legacy elapsed-time behavior remains unchanged.
- Actual execution remains full elapsed calendar time and must not use this service.

## 4. Calendar Precedence

Calendar precedence is deterministic:

- Same-date project exceptions are evaluated in stored order; the last exception for that date wins.
- If no same-date exception exists, the project weekday rule applies.
- If no project calendar is supplied, CPM uses raw elapsed time.

`ProjectCalendarSpec.is_working_day()` was aligned with the new authority so model-level checks and CPM arithmetic do not disagree.

## 5. Duration Convention

The implemented convention is:

- `EF = ES + working_duration`.
- `LS = LF - working_duration`.
- A one-day task starting Monday 09:00 finishes Tuesday 09:00 on a Mon-Fri calendar.
- A one-day task starting Friday 09:00 finishes Monday 09:00 on a Mon-Fri calendar.
- A task finishing exactly at Saturday 00:00 may have that boundary instant as EF, but an FS successor with zero lag is normalized to the next working datetime.

## 6. Dependency Equations

Forward pass equations now use calendar arithmetic for all dependency types:

- FS: successor `ES >= predecessor EF + lag`.
- SS: successor `ES >= predecessor ES + lag`.
- FF: successor `EF >= predecessor EF + lag`, converted back to successor start by subtracting successor working duration.
- SF: successor `EF >= predecessor ES + lag`, converted back to successor start by subtracting successor working duration.

Positive lag and negative lead are both working-calendar minutes when a project calendar is supplied.

## 7. Backward Pass And Float

Backward pass equations now mirror the forward equations with the same calendar authority. Total float is calculated as working minutes between `ES` and `LS`, and verified equivalent to working minutes between `EF` and `LF`.

Critical classification remains canonical:

- `TF == 0` is critical.
- `TF < 0` is negative float/conflict state and is not classified as an ordinary critical path.

Free float now uses edge-specific working-calendar slack for FS, SS, FF, and SF.

## 8. Constraints And Deadlines

Constraint behavior:

- ASAP: schedules as early as dependencies allow.
- ALAP: shifts to latest calendar start without delaying project finish.
- SNET/FNET: lower bounds normalize forward to a working datetime.
- SNLT: latest-start upper bound normalizes backward to a working datetime.
- FNLT: preserves the frozen meaning `LF <= constraint`; it is not reversed.
- MSO/MFO: exact constraints remain conflict-checked against dependencies.
- Deadlines remain monitoring-only and do not move ES/EF.

## 9. Actual Execution And Historical Data

Actual execution is unchanged. `actual_elapsed_minutes` continues to use full calendar elapsed time across weekends and holidays.

Original Baseline and Approved Revision snapshots are immutable and are not recalculated or mutated by calendar CPM. New tests validate both with temp DBs only.

## 10. Gantt And WBS Consumption

WBS scheduling consumes `CPMSchedulingService.calculate_schedule(..., project_calendar=proj_cal)`.

Gantt refresh continues through the WBS rollup/CPM refresh route and consumes generated planned/CPM dates for visualization. Gantt UI geometry/date-range code still contains UI-only `timedelta` uses for rendering, drag ranges, and actual bars; these are not CPM arithmetic authority.

Known non-authority date math:

- `schedule_variance_service.py`: variance/fallback date arithmetic, not CPM calculation.
- `gantt_chart.py` and `gantt_view.py`: UI range, drag, and display mapping.
- `utils/working_calendar.py` / `services/working_week.py`: working-week and effort allocation helpers, not CPM network authority.

## 11. Performance

The calendar implementation loops by day boundaries, not minute-by-minute. A 5,000-node FS chain with a Mon-Fri calendar completed in 0.2469 seconds in the explicit runtime witness, with task 5000 finishing at `2026-09-10 20:20:00`.

Hotspot is still CPM graph traversal plus per-edge calendar day-boundary arithmetic. The observed case remains bounded and avoids O(duration-minutes) loops.

## 12. Evidence

Isolated subprocess evidence:

- `test_working_calendar_cpm_authority.py`: 88 passed in 0.41s.
- `test_phase2e_constraints_calendars.py`: 100 passed in 1.62s.
- `test_phase2a_professional_scheduling_engine.py`: 23 passed in 0.16s.
- `test_phase2c_advanced_dependencies.py`: 28 passed in 0.25s.
- `test_phase2d_schedule_baseline_variance.py`: 68 passed in 2.47s.
- `test_schedule_governance_authority.py`: 50 passed in 1.94s.
- `test_schedule_versions.py`: 23 passed in 0.71s.
- `test_execution_aware_schedule_authority.py`: 50 passed in 1.58s.
- `test_actual_execution_state_authority.py`: 50 passed in 0.72s.
- `test_actual_execution_semantics.py`: 30 passed in 1.32s.
- `test_gantt_project_selector.py`: 13 passed in 3.30s.
- `test_phase2e_gantt_wbs_ui_closure.py`: 38 passed in 1.12s.
- `test_phase1a_wbs_authority.py`: 46 passed in 3.49s.
- `test_phase2e_production_db_safety.py`: 26 passed in 0.23s.
- `test_shutdown_lifecycle.py`: 23 passed in 8.15s.

Production DB read-only witness:

- Counts selected read-only: projects 3, tasks 8, schedule_versions 3, schedule_version_items 6.
- Hash before: `8317754aae5262bda93363b38e627fff94bc23061241c9b9023de41b19b53ecc`.
- Hash after: `8317754aae5262bda93363b38e627fff94bc23061241c9b9023de41b19b53ecc`.
- Result: unchanged.

Classification: `todo_bird_phase2e_working_calendar_cpm_fixed_human_review_required`.
