# Todo Bird Calculation Authority Matrix Final

Date: 2026-08-27
Classification: `todo_bird_phase2e_scheduling_engine_robust_human_witness_required`

| Calculation / Field | Canonical Authority | Storage / Source | Confirmed Rule |
| --- | --- | --- | --- |
| Planned elapsed span | `CPMSchedulingService`, `ScheduleVersionService` | `estimated_duration` | Duration authority is the task/subtask planned elapsed minutes, not wall-clock snapshot span. |
| Planned work effort | `WBSRollupService`, task/subtask editors | `planned_effort_minutes` | Effort is additive and separate from elapsed span. |
| Daily dedication | Working effort UI/services | `daily_dedication_minutes` | Dedication supports effort planning but is not actual elapsed. |
| Actual work effort | `ExecutionPerformanceService`, `WBSRollupService` | `actual_duration` | Logged effort remains separate from actual elapsed. |
| Actual elapsed span | `ExecutionPerformanceService` | `actual_start_date/time`, `actual_end_date/time` | Full calendar elapsed; weekends/non-working days included. |
| Actual state A | `ExecutionPerformanceService.derive_execution_state` | no actual start, no actual finish | NOT TRACKED; no Actual bar. |
| Actual state B | `ExecutionPerformanceService.derive_execution_state` | actual start, no actual finish | IN PROGRESS; visual end is canonical now only, never persisted. |
| Actual state C | `ExecutionPerformanceService.derive_execution_state` | actual start and actual finish | FINISHED; historical closed Actual bar. |
| Current forecast | `CPMSchedulingService.calculate_schedule` | planned dates, duration, deps, constraints, project calendar | Early actual start does not rewrite forecast. |
| Project calendar | `schedule_calendar_service.py` | project working weekdays and exceptions | Working dates are 1440 minutes; non-working dates are 0 minutes; finish is exclusive. |
| Dependencies | `CPMSchedulingService` | `dependencies` specs | FS/SS/FF/SF with lag/lead are evaluated with calendar arithmetic. |
| Dependency graph integrity | `CPMSchedulingService` | task dependency specs | Cycles, self references, missing refs, invalid lags/types, duplicates, and cross-project references produce diagnostics. |
| CPM forward pass | `CPMSchedulingService` | ES/EF dictionaries | Uses max predecessor bound plus own planned start/forward constraints. |
| CPM backward pass | `CPMSchedulingService` | LS/LF dictionaries | Uses min successor bound plus backward constraints. |
| Total Float | `CPMSchedulingService` | result object | `TF = LS - ES` in integer minutes; negative TF is preserved. |
| Free Float | `CPMSchedulingService` | result object | Edge-specific FF is independent of TF and now preserves negative values. |
| Criticality | `CPMSchedulingService` | result object | Critical iff `TF == 0`; negative TF is not normal critical. |
| Constraints | `CPMSchedulingService`, `ScheduleConstraintService` | `constraint_type`, `constraint_datetime` | ASAP/ALAP/SNET/SNLT/FNET/FNLT/MSO/MFO are recognized; FNLT means LF <= constraint. |
| Deadlines | `ScheduleConstraintService`, CPM diagnostics | `deadline_datetime` | Safe iff EF <= deadline; missed iff EF > deadline; no risk window. |
| Baseline and revision | `ScheduleVersionService`, `DatabaseManager` | `schedule_versions`, `schedule_version_items` | Original baseline and revisions are immutable snapshots; legacy columns are cache/compatibility only. |
| Schedule variance | `ScheduleVarianceService` | baseline/revision vs current forecast | Current Forecast - Reference; negative early/ahead, positive late/behind. |
| Execution variance | `ExecutionPerformanceService` | actual vs reference | Actual - Reference; start and finish kept separate; finish variance null while open. |
| WBS hierarchy | `WBSService`, `WBSMutationService` | tasks/subtasks/parent_subtask_id | Tasks are roots; subtasks nest only inside owning task; unsafe cross-project/cross-task moves rejected. |
| WBS rollup | `WBSRollupService` | WBS snapshot plus payloads | Dates are envelope, duration is span, effort is additive, progress rule documented, no parent raw-field mutation. |
| WBS raw vs summary | Raw Task editors/DB for raw fields; `WBSRollupService` for summary fields | Raw fields: `planned_*`, `due_*`, `estimated_duration`; summary fields: `gantt_summary_*`, `gantt_rollup_*` | Derived WBS summary values never overwrite raw parent Task planned input. |
| Gantt rows | `GanttWBSAdapter`, `GanttView`, `GanttChart` | WBS snapshot plus rollups plus raw entity payload | Read-only projection; summary geometry uses `gantt_*` metadata and schedule writes are blocked for summary/read-only rows. |
| Gantt geometry/range | `TimescaleEngine`, `GanttChart` | row schedule fields | Date range includes planned/current/baseline/actual/constraint/deadline layers. |
| Qt scene lifetime | `GanttChart.rebuild_chart` | scene-owned item refs | Persistent item references are cleared before `scene.clear()`. |

## Release Gate Note

All automated evidence gathered in this pass supports the robust/human-witness-required classification. The WBS raw-vs-summary repair adds 56 targeted authority tests and a full 110-file isolated regression with 2374 passed, 0 failed, 0 errors. This matrix does not declare Beta Ready, Human Accepted, or Phase 2F.

## 2026-08-28 Duration/Time Roundtrip Addendum

Classification: `todo_bird_phase2e_task_duration_time_roundtrip_fixed_human_witness_required`

| Calculation / Field | Canonical Authority | Storage / Source | Confirmed Rule |
| --- | --- | --- | --- |
| Estimated duration days | `TaskDialog` duration controls plus `schedule_calendar_service.py` | `estimated_duration` minutes | `1 scheduled day = 1440 minutes`; 5 days stores `7200`, not endpoint wall-span `5760`. |
| Task target finish | `TaskDialog._finish_from_start_and_duration` | Derived UI target; optional `due_date` / `planned_end_time` when finish is saved | Start + stored duration + project calendar derives target finish. |
| Finish-to-duration recalculation | `TaskDialog._scheduled_duration_between` | `estimated_duration` only during explicit finish authority | Recalculate from finish only when stored duration is zero on open or when finish is intentionally edited. |
| Subtask target finish | `TaskDialog` subtask editor | subtask `estimated_duration`, `due_date`, `planned_end_time` | Subtasks use the same day/minute and calendar authority as tasks. |
| Upcoming range current date | `TaskController` | `get_current_datetime()` | Upcoming queries use app time authority, not raw `date.today()`. |

Evidence: `TASK_DURATION_TIME_ROUNDTRIP_FORENSIC_REPORT.md`; focused forensic 50 passed; impacted bundle 134 passed; full isolated regression 114 files, 2456 passed, 0 failed, 0 errors. Production DB hash stayed `aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff` before/after read-only witness. This addendum does not declare Beta Ready, Human Accepted, or Phase 2F.

## 2026-08-28 Project Calendar Duration/Workload Addendum

Classification: `todo_bird_phase2e_project_calendar_duration_workload_fixed_human_witness_required`

| Calculation / Field | Canonical Authority | Storage / Source | Confirmed Rule |
| --- | --- | --- | --- |
| Nominal whole-day task placement | `schedule_calendar_service.add_working_days_preserve_time` / `subtract_working_days_preserve_time` | `estimated_duration` minutes | Exact whole-day duration uses working-date sequence while preserving clock time; Tue 2026-09-01 09:00 + 5 Mon-Sat working days = Sat 2026-09-05 09:00. |
| CPM task duration placement | `CPMSchedulingService` | project calendar + task `estimated_duration` | Task durations use nominal whole-day placement when a project calendar exists; dependency lag/lead remains minute arithmetic. |
| Workload fixed daily | `WorkEffortEditor` with selected project calendar provider | project working weekdays, holidays, working overrides | Fixed Daily counts selected project working dates, not global Mon-Fri defaults. |
| Workload custom by day | `WorkEffortEditor` | `task_allocations` / custom allocation dictionaries | Custom daily values survive working/non-working reclassification; Saturday effort is not destroyed when Saturday becomes non-working. |
| Task dialog Qt lifetime | `TaskDialog.cleanup`, `WorkEffortEditor.cleanup` | Qt object lifecycle and event bus connections | Dialog-heavy tests and real dialogs disconnect workload listeners and drain deferred deletes instead of accumulating orphan Qt objects. |

Evidence: `PROJECT_CALENDAR_DURATION_WORKLOAD_AUTHORITY_REPORT.md`; focused authority group 165 passed; final full isolated regression 116 files, 2533 passed, 0 failed, 0 errors, peak RSS 410348 KB, elapsed 334.343s. The former duration-forensics timeout was reduced from 140s / 2053172 KB RSS to 5.368s / 131368 KB RSS. Production DB hash stayed `aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff` before/after read-only witness. This addendum does not declare Beta Ready, Human Accepted, or Phase 2F.

## 2026-08-28 Project Calendar Live Authority Addendum

Classification: `todo_bird_phase2e_project_calendar_live_authority_fixed_human_witness_required`

| Calculation / Field | Canonical Authority | Storage / Source | Confirmed Rule |
| --- | --- | --- | --- |
| Effective project calendar | `DatabaseManager.get_project_calendar`, `effective_project_calendar_from_db` | project `working_weekdays`, project exceptions, global `settings.working_weekdays` | Explicit project calendar wins; project `NULL` inherits global working weekdays; default Mon-Fri is only final fallback. |
| Calendar parser | `schedule_calendar_service.project_calendar_spec_from_source` | DB dicts, JSON strings, `ProjectCalendarSpec`, `ScheduleCalendar`, project-like objects | All runtime calendar shapes resolve through one parser, preventing dict/object drift. |
| Date status labels | `schedule_calendar_service.classify_calendar_date` | weekday rule plus exceptions | Labels distinguish `Working`, `Non-working`, `Holiday`, `Non-working exception`, and `Working override`. |
| Task target refresh | `TaskDialog` | selected project id, DB calendar resolver, `estimated_duration` | Already-open dialogs recompute target/workload when calendar settings change; stale hard-Mon-Fri artifacts normalize to the effective calendar. |
| Project calendar exception type | `ProjectCalendarDialog` | table item `Qt.UserRole` boolean | Exception type is saved from data role, not display text, so `Non-Working Holiday` cannot be misread as working. |
| CPM/WBS/snapshot calendar | `CPMSchedulingService`, `ScheduleVersionService`, `WBSItemModel`, `WBSRollupService` | common DB calendar resolver | Runtime consumers use the same effective calendar as TaskDialog and workload planning. |

Production read-only witness: project `SCHEDULING WITNESS FINAL` id `6` has `working_weekdays=NULL`, settings has `[0, 1, 2, 3, 4, 5]`, task `Foundation` id `14` stores start `2026-09-01 09:00`, finish `2026-09-07 09:00`, duration `7200`. After the fix, the effective calendar is Mon-Sat and the read-only TaskDialog/CPM/snapshot target is `2026-09-05 09:00`; production DB hash remained `aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`.

Evidence: `PROJECT_CALENDAR_LIVE_AUTHORITY_DIAGNOSTIC.md`; `PROJECT_CALENDAR_LIVE_AUTHORITY_FORENSIC_REPORT.md`; new focused forensic file 55 passed; final full isolated regression 117 files, 2588 passed, 0 failed, 0 errors, 0 skipped, peak RSS 411420 KB, elapsed 339.193s. This addendum does not declare Beta Ready, Human Accepted, or Phase 2F.

## 2026-09-02 CPM Subtask Result Propagation Addendum

Classification: `todo_bird_phase2e_cpm_subtask_result_propagation_fixed_human_witness_required`

| Calculation / Field | Canonical Authority | Storage / Source | Confirmed Rule |
| --- | --- | --- | --- |
| WBS CPM network | `wbs_cpm_adapter.calculate_wbs_cpm` plus `CPMSchedulingService` | WBS snapshot, task rows, subtask rows, project calendar | Leaf tasks and leaf subtasks participate in CPM; WBS summary parents are derived projections and do not own leaf CPM results. |
| Typed CPM key mapping | `EntityRef`, `WBSCPMResult`, `WBSCPMNodeMap` | task/subtask entity type plus entity id | `task:N` and `subtask:N` are distinct. Legacy `.nodes[task_id]` compatibility is task-leaf-only and cannot cross-read subtask results. |
| Subtask dependencies | WBS CPM adapter dependency rewrite | `subtasks.dependencies` and typed dependency specs | Subtask dependency edges are rewritten to synthetic CPM IDs while preserving FS/SS/FF/SF, lag/lead, missing-ref diagnostics, and typed predecessor/successor identity. |
| WBS CPM display | `WBSItemModel` data roles | typed `WBSCPMResult` | Analyzable leaf rows expose ES, EF, LS, LF, Total Float, Free Float, Critical, Schedule Health, tooltip, and accessibility text. Summary rows remain rollup-only. |
| WBS CPM filters | `WBSFilterProxyModel` | typed `WBSCPMResult` | Critical, float, and warning filters evaluate both task and subtask leaves through typed keys. |
| Gantt CPM rows | `GanttWBSAdapter` and `GanttView` | WBS rows plus canonical CPM metadata | Gantt task and subtask rows carry current forecast, ES/EF/LS/LF, float, criticality, analysis status, diagnostics, and dependency summary. |
| Gantt CPM tooltip | `GanttDependencyEngine._apply_canonical_wbs_cpm_metadata`, `GanttTaskItem._set_rich_tooltip` | canonical WBS CPM metadata | Legacy task-only annotation reset cannot erase analyzed subtask CPM metadata; analyzed subtask tooltips no longer fall back to `CPM: Not analyzed`. |
| Schedule snapshot CPM | `ScheduleVersionService.capture_current_schedule_snapshot` | typed task/subtask CPM values | Task and subtask snapshot forecast fields are captured from typed WBS CPM results. |

Evidence: `CPM_SUBTASK_RESULT_PROPAGATION_REPORT.md`; new focused propagation suite 45 passed; impacted UI/scheduling bundle 250 passed; adjacent scheduling/rollup/snapshot bundle 391 passed; final full isolated regression 118 files, 2633 passed, 0 failed, 0 errors, 0 skipped, peak RSS 410460 KB, elapsed 341.715s. Production DB hash stayed `aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff` before/after read-only witness. This addendum does not declare Beta Ready, Human Accepted, or Phase 2F.

## 2026-09-04 WBS Parent Summary Dashboard Parity Addendum

Classification: `todo_bird_wbs_parent_summary_dashboard_parity_fixed_human_witness_required`

| Calculation / Field | Canonical Authority | Storage / Source | Confirmed Rule |
| --- | --- | --- | --- |
| WBS parent CPM summary | `wbs_cpm_adapter.build_wbs_cpm_summary_by_key` | Derived `WBSCPMSummaryResult`; no DB writes | Summary rows are not CPM leaf activities, but expose descendant CPM envelopes for display. |
| Summary ES / EF | `WBSCPMSummaryResult` over typed leaf CPM results | Child task/subtask CPM nodes | ES = earliest descendant ES; EF = latest descendant EF. |
| Summary LS / LF | `WBSCPMSummaryResult` over typed leaf CPM results | Child task/subtask CPM nodes | LS = earliest descendant LS; LF = latest descendant LF. |
| Summary Total Float / Free Float | Product display contract | No stored value | Float is not aggregated for summaries; display `N/A (Summary)`. |
| Summary criticality | `WBSCPMSummaryResult` | Child critical CPM leaves | Parent displays `Contains Critical` when any descendant leaf is critical; parent still has no `CPMNodeResultRole`. |
| Summary schedule health | `WBSItemModel` plus rollup missing-schedule state | Derived WBS/CPM metadata | Displays `Healthy`, `At Risk`, `Blocked (Cycle)`, or `N/A (Summary)`. |
| Dashboard schedule parity | `DashboardScheduleSummaryService` | Existing WBS/Gantt adapter rows | Dashboard project snapshot can consume forecast range, critical work count, and at-risk WBS count without duplicating CPM math. |

Evidence: `WBS_PARENT_SUMMARY_DASHBOARD_PARITY_REPORT.md`; new focused parity suite 41 passed; adjacent WBS/Gantt/CPM bundle 153 passed; impacted schedule-details/WBS UI/Gantt-dashboard bundle 162 passed. Production DB hash-only witness after the pass: `c8fb2bbe4f53fbce147a3fc5892014ede5a66a37030fb9dbe0e02ab2834f4513`. No Phase 2F work was started.
