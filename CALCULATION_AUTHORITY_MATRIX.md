# Todo Bird Phase 2E - Calculation Authority Matrix

Audit date: 2026-08-25

Final beta classification: `todo_bird_phase2e_full_system_audit_complete_beta_blocked`

## Authority Rules Audited

- Planned elapsed span authority: `estimated_duration`.
- Planned work effort authority: `planned_effort_minutes`.
- Daily dedication authority: `daily_dedication_minutes`.
- Actual work effort authority: `actual_duration`.
- Actual elapsed authority: `actual_start_datetime -> actual_finish_datetime`, full calendar elapsed, never reduced by working calendar.
- Schedule references must remain distinct: raw planned input, current CPM forecast, original baseline, approved revisions, actual start, actual finish, actual work effort, actual elapsed.

## Matrix

| Metric | Canonical source | Formula | Unit | Calendar basis | Persistence | Views consuming it | Duplicate implementations | Status |
|---|---|---|---|---|---|---|---|---|
| Raw planned start | `Task.planned_date` + `Task.planned_start_time` | `combine_date_time(planned_date, planned_start_time)` | datetime | naive local date/time | `tasks.planned_date`, `planned_start_time`; subtasks equivalents | Task Dialog, Today, Upcoming, Calendar, WBS, Gantt, Dashboard | QDate widgets, `time_math`, CPM parser | PARTIAL: storage is clear, parsing is duplicated |
| Planned elapsed span | `Task.estimated_duration` | minutes added to CPM ES for EF | minutes | currently raw elapsed minutes | `tasks.estimated_duration`; subtasks equivalents | Task Dialog, Gantt, WBS, CPM, schedule versions | CPM, Gantt drag updates, DB defaults | FAIL: working calendar not applied to planned schedule effort |
| Planned work effort | `planned_effort_minutes` | explicit user-entered work effort | minutes | working calendar/resource context where workload applies | `tasks.planned_effort_minutes`, `subtasks.planned_effort_minutes`, allocations | Today workload, Dashboard, WBS rollups, Task Dialog | Work effort editor, workload engine, rollups | PARTIAL: mostly separated from elapsed duration, but backup/archive and version coverage are incomplete |
| Daily dedication | `daily_dedication_minutes` | explicit daily resource capacity/dedication | minutes/day | working day context | tasks/subtasks fields, allocations | Workload, Task Dialog, WBS | Workload and effort helpers | PARTIAL: authority exists, but full cross-view audit needs durable evidence |
| Actual start | `actual_start_date` + `actual_start_time` | `combine_date_time(actual_start_date, actual_start_time)` | datetime | full calendar local time | task/subtask actual columns | Focus, Task Dialog, Gantt, WBS rollup, Analytics | Focus writes, Task Dialog writes, Gantt reads | PARTIAL: actual start may be present while status semantics diverge |
| Actual finish | `actual_end_date` + `actual_end_time` | `combine_date_time(actual_end_date, actual_end_time)` | datetime | full calendar local time | task/subtask actual columns | Task Dialog, Gantt, Analytics, ExecutionPerformanceService | Task Dialog, Focus completion, controller toggles | FAIL: `In Progress` with actual finish is allowed and present |
| Actual work effort | `actual_duration` | explicit minutes worked/logged | minutes | not reduced by working calendar | `tasks.actual_duration`, `subtasks.actual_duration` | Task Dialog, Focus, Dashboard, Analytics, WBS rollups | Focus timer, WorkEffortEditor, TaskDialog spinbox | PARTIAL: distinct from elapsed, but state invariant can mislead consumers |
| Actual elapsed | actual start -> actual finish, or open actual -> now for display | `duration_between(start, finish_or_now)` then `max(0, minutes)` | minutes | full calendar elapsed | persisted start/finish only; open visual end is display-only | Gantt actual bar, Task Dialog, ExecutionPerformanceService | `time_math`, Gantt rendering helpers | PASS/PARTIAL: full-minute witness passed; timezone/DST naive |
| CPM ES | `CPMSchedulingService.calculate_schedule()` | max dependency/constraint/planned bounds | datetime | raw elapsed minutes plus start-day calendar diagnostic | calculated in memory | Gantt, WBS, variance, schedule versions | CPM service only for main authority | PARTIAL: dependency math exists, calendar model incomplete |
| CPM EF | CPM ES + duration | `ef = es + timedelta(minutes=dur)` | datetime | raw elapsed minutes | calculated in memory / captured to version items | Gantt, WBS, deadlines, versions | CPM and snapshot fallback | FAIL: ignores non-working spans/exceptions |
| CPM LS/LF | backward pass | derived from project finish, successors, lag/lead, constraints | datetime | raw elapsed minutes | calculated in memory | Gantt, WBS, critical path | CPM service | PARTIAL: same calendar limitation as ES/EF |
| Total float | CPM backward/forward result | `LS - ES` or `LF - EF` | minutes | raw elapsed minutes | calculated in memory | Gantt health, WBS diagnostics | CPM service | PASS/PARTIAL: criticality uses `TF == 0`; calendar limits still affect value |
| Free float | successor slack | min successor slack, clamped to `max(0, ff)` | minutes | raw elapsed minutes | calculated in memory | Gantt/WBS diagnostics | CPM service | PARTIAL: negative free float diagnostic exists, displayed value clamps |
| Criticality | CPM total float | `is_critical = (total_float == 0)` | boolean | CPM basis | calculated in memory | Gantt, WBS | CPM service | PASS: audited code obeys `TF == 0`, not `TF <= 0` |
| Negative float | CPM diagnostics | total/free float below zero -> diagnostic | minutes/diagnostic | CPM basis | calculated in memory | Gantt/WBS health | CPM service | PARTIAL: represented, but calendar errors can create false/hidden float |
| Dependencies FS/SS/FF/SF | dependency JSON -> parsed specs | relation-specific bounds plus lag minutes | datetime/minutes | CPM basis | `tasks.dependencies` JSON | Task Dialog dependency picker, Gantt, CPM | Controller validation and DB storage | PARTIAL: controller validates, DB can bypass |
| Constraints | `constraint_type`, `constraint_datetime` | ASAP/ALAP/SNET/SNLT/FNET/FNLT/MSO/MFO rules | datetime/diagnostic | CPM basis | task/subtask constraint fields | Task Dialog, Gantt, CPM | ScheduleConstraintService and CPM parser | PARTIAL: math exists, actual-vs-constraint diagnostics need broader coverage |
| Deadlines | `deadline_datetime` | safe if `EF <= deadline`; missed if `EF > deadline` | datetime/diagnostic | CPM basis | task/subtask deadline fields | Gantt/WBS/CPM | ScheduleConstraintService and CPM diagnostics | PASS/PARTIAL: deterministic safe/missed exists; Gantt at-risk wording conflicts |
| Project calendar working days | project working weekdays/exceptions | `ProjectCalendarSpec.is_working_day(date)` | boolean/date | project-specific date calendar | projects fields and exception table | Settings/project calendar, CPM, WBS/Gantt | Project DB fields, ScheduleConstraintService | FAIL: only start-day diagnostic affects CPM, not duration scheduling |
| Original baseline | baseline/version snapshot | captured current/baseline fields | datetime/minutes | schedule reference | mutable task baseline columns plus schedule_versions/items | WBS, Gantt, variance | ScheduleVarianceService, ScheduleVersionService, DB baseline methods | FAIL: original baseline can be replaced/cleared |
| Approved revision | `ScheduleVersionService.create_approved_revision()` | snapshot current CPM ES/EF/items | datetime/minutes | current CPM basis | schedule_versions/items | Gantt comparison combo, tests, variance lookup | ScheduleVersionService + DB direct create | PARTIAL: UI selector exists; DB governance and subtask completeness are weak |
| Schedule variance | current forecast - baseline/revision | signed minutes | minutes | schedule reference basis | calculated in service, baseline stored | WBS/Gantt/Dashboard candidates | ScheduleVarianceService | PARTIAL: depends on mutable baseline and revision integrity |
| Execution variance | actual - reference | negative early/ahead, positive late/behind | minutes | actual full calendar vs selected schedule reference | calculated in service | Task Dialog, Analytics, Gantt/WBS candidates | ExecutionPerformanceService | FAIL/PARTIAL: actual state contradiction changes completed/in-progress semantics |
| WBS planned rollup | WBS snapshot leaf dates | min start, max finish, effort/progress aggregation | datetime/minutes/percent | source row basis | calculated in memory/cache | WBS tree, Gantt summary rows | WBSRollupService, WBSService | PARTIAL: appears centralized, but calendar/version/archive gaps affect authority |
| Gantt visible range | `TimescaleEngine.get_relevant_date_range()` | min/max across planned, CPM, baseline, actual, constraints, deadlines | date range | display date range | in memory | Gantt chart | TimescaleEngine and Gantt commands | PARTIAL: engine includes authorities, but Fit Project button calls today |
| Delay velocity/status | `DelayEngine` and timing status consumers | threshold/status classification | labels/minutes | local date/time | calculated/displayed | Dashboard, Gantt health, Analytics | delay engine and Gantt health | PARTIAL: terminology overlaps with deadline at-risk wording |

## High-Risk Calculation Findings

1. Working calendar is the highest calculation blocker. Planned schedule duration currently crosses non-working time as raw elapsed minutes.
2. Actual execution state is the highest cross-view authority blocker. Finish data can exist while status remains In Progress.
3. Baseline/revision separation is not fully protected. Mutable baseline columns and immutable schedule version language coexist.
4. Date parsing accepts different formats depending on service. Ambiguous day/month input is not consistently rejected.
5. Fit Project has the right data extraction engine nearby, but the UI command is wired to `go_to_today()`.

## Witnesses

- Calendar witness: Friday 2026-09-04 09:00 + 960 minutes under Mon-Fri calendar produced Saturday 2026-09-05 01:00 and no diagnostic.
- Execution witness: `In Progress` task with actual finish returned execution state `completed`, start variance `-31680`, finish variance `-75120`.
- Date witness: `2024-02-29` accepted, `2026-02-29` rejected, `29/02/2024` accepted only by constraint parser, `03/04/2026` parsed as 2026-04-03 only by constraint parser.
- Actual elapsed witness: 2026-08-24 09:00 -> 2026-08-25 09:01 returned 1441 minutes.
