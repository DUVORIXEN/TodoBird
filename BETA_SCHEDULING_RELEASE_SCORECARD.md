# Todo Bird Phase 2E Beta Scheduling Release Scorecard

## 1 Classification

`todo_bird_phase2e_beta_ready`

Historical raw-vs-summary repair classification: `todo_bird_phase2e_wbs_raw_summary_authority_fixed_human_witness_required`; accepted by the final Phase 2E gate.

Final narrow Phase 2E beta-gate audit accepts the current live human witness and closes the former witness-pending scheduling gate. Phase 2F remains not started.

## 2 Calculation authority architecture

Canonical authorities are now consistent: CPM in `CPMSchedulingService`, calendar arithmetic in `schedule_calendar_service.py`, constraints/deadlines in `schedule_constraint_service.py`, baseline/revision in `ScheduleVersionService` plus immutable DB tables, execution truth in `ExecutionPerformanceService`, WBS rollup in `WBSRollupService`, and Gantt projection in `GanttWBSAdapter`/`TimescaleEngine`.

## 3 Defects found by severity

High: Free Float clamped negative values to zero. Fixed.
High: schedule snapshot duration could use wall span instead of `estimated_duration`. Fixed.
High: schedule-version internal CPM ignored project calendar. Fixed.
High: WBS/Gantt presentation rows copied derived summary dates, span, effort, and progress into raw parent Task fields. Fixed.
Medium: recursive WBS build/descendant traversal could fail on deep hierarchy. Fixed.

## 4 Task/subtask calculation result

Task fields preserve frozen semantics: `estimated_duration` is planned elapsed span, `planned_effort_minutes` is planned work, `daily_dedication_minutes` is dedication/capacity, and `actual_duration` is actual work effort. Tests confirm early actual fields do not rewrite planned forecast.

## 5 Working-calendar result

Calendar arithmetic is day-level and deterministic: working day = 1440 minutes, non-working day = 0 minutes, finish boundaries are exclusive. Internal schedule-version CPM now uses the DB project calendar.

## 6 Dependency result

FS, SS, FF, and SF with lag/lead remain covered by existing suites. Graph integrity diagnostics cover cycles, self references, missing refs, invalid lags/types, duplicates, and cross-project dependencies.

## 7 CPM forward/backward result

Forward pass applies predecessor bounds and forward constraints. Backward pass applies successor bounds and backward constraints. Existing and new oracle tests pass for simple, parallel, disconnected, milestone, zero-duration, lag/lead, and 5000-node chain cases.

## 8 TF/FF/critical result

Total Float remains integer minutes and can be negative. Free Float is independently computed and now preserves negative values. Critical remains strict `TF == 0`; negative TF is distinct from ordinary critical path.

## 9 Constraint/deadline result

ASAP/ALAP/SNET/SNLT/FNET/FNLT/MSO/MFO are recognized. FNLT is `LF <= constraint`. Deadlines are SAFE/MISSED only: safe iff EF <= deadline, missed iff EF > deadline.

## 10 WBS hierarchy result

Task remains WBS root. Subtasks can nest under the owning task. Unsafe root indentation, self-parenting, cycle, cross-main-task, and cross-project moves remain rejected by `WBSMutationService`.

## 11 WBS roll-up result

Rollups use earliest start/latest finish envelopes, span duration rather than duration sum, additive effort, full actual elapsed only when complete, and no summary-payload double counting. Derived WBS summary values now stay in `gantt_summary_*`/`gantt_rollup_*` metadata and never overwrite parent raw planned inputs. Progress fallback is documented by tests.

## 12 Baseline/revision result

Canonical immutable tables are `schedule_versions` and `schedule_version_items`. Legacy task/subtask baseline columns remain compatibility/cache fields. Opening comparison views was not found to be a baseline creation authority.

## 13 Actual execution result

State A/B/C is field-derived only. No actual finish is fabricated from due dates, baseline, revision, CPM, effort, progress, or current time. Open actual analysis uses now without persistence.

## 14 Variance result

Schedule variance remains Current Forecast - Baseline/Revision. Execution variance remains Actual - Reference. Negative means early/ahead; positive means late/behind; integer minutes are the calculation unit.

## 15 Gantt adapter/geometry result

Gantt adapter is read-only and uses WBS rollups. Timescale includes planned, CPM, baseline, constraint, deadline, and actual layers. The required scene-clear lifetime ordering is present and tested.

## 16 Cross-view consistency

Full isolated regression evidence passed across WBS, Gantt, dashboard, execution, baseline, constraint, and production DB safety suites. Newer accepted human-witness evidence covers the live `Reinforcement Final` CPM/WBS/Gantt detail parity.

## 17 Performance

Pure-data benchmark: 100 tasks CPM 0.0034s, WBS 0.0024s, adapter 0.0028s; 1000 tasks CPM 0.0163s, WBS 0.0217s, adapter 0.0079s; 5000 tasks CPM 0.1025s, WBS 0.1107s, adapter 0.0440s.

## 18 Exact tests

Latest raw-vs-summary repair tests: 56 targeted passed. Impacted isolated run: 154 passed. Historical full isolated regression: 110 files, 2374 passed, 0 failed, 0 errors, peak RSS 442472 KB, elapsed 339.526s.

Final narrow gate evidence on 2026-09-03:

- Accepted live witness: `Reinforcement Final`, Mon-Sat calendar, FS predecessor `Foundation > Excavation Final`, lag 0, CPM analyzed, ES/EF/LS/LF/TF/FF/Critical matching WBS and Gantt copied details.
- Focused S1 UI/runtime forensics: 43 passed.
- Production DB safety replay: 26 passed.
- Legacy migration replay: 68 passed.
- Bounded isolated tail regression: 41/41 files, 1188 passed, 0 failed, 0 errors.

## 19 Production DB hash

Before this final narrow gate audit: `20cd4ba626ac19a2aee61a83f1d2fb0455785cf2b66c62ddb23e1cd7a085f8b4`
After this final narrow gate audit: `20cd4ba626ac19a2aee61a83f1d2fb0455785cf2b66c62ddb23e1cd7a085f8b4`

Production DB unchanged during this final narrow gate audit. No plain SQLite production schema/count inspection was used in this audit.

## 20 Remaining decisions/blockers

No remaining S0/S1 beta blockers. The current human witness is accepted by the 2026-09-03 final gate brief. Progress fallback behavior is documented; any alternate zero-effort progress rule is a non-blocking product decision. No Phase 2F authorization was made.

## 21 Duration/time roundtrip closure - 2026-08-28

Classification: `todo_bird_phase2e_task_duration_time_roundtrip_fixed_human_witness_required`

Root cause fixed: the Edit Task scheduling path could derive `estimated_duration` back from finish/start endpoint distance and collapse a 5-working-day entry (`7200 mins`) into 4 endpoint days (`5760 mins`). The corrected authority is start + estimated duration + project calendar -> calculated target finish; finish -> duration only under explicit finish edit/recovery mode.

Production witness was read-only. The earlier `SCHEDULING WITNESS FRESH` note is archival and is superseded by the accepted final live witness for `Reinforcement Final`. It is not an open beta blocker.

New evidence:

- Focused forensic suite: 50 passed, 0 failed.
- Impacted bundle: 134 passed, 0 failed.
- Full isolated regression: 114 files, 2456 passed, 0 failed, 0 errors, 0 skipped, peak RSS 1214520 KB, elapsed 360.032s.

This closes the code defect. Human witness is accepted by the final gate brief. Phase 2F remains not started.

## 22 Project calendar duration/workload closure - 2026-08-28

Classification: `todo_bird_phase2e_project_calendar_duration_workload_fixed_human_witness_required`

Root cause fixed: exact whole-day task durations were still being placed as elapsed working-minute blocks in CPM and some dialog paths, while workload planning used global working-week settings instead of the selected project's calendar. A separate Qt lifetime problem in the duration-forensics tests caused repeated full dialog construction to leave child workload editors and deferred deletes alive, reproducing the IDE-crash pattern as a 140s timeout and 2053172 KB RSS.

Corrected authority:

- `estimated_duration` remains nominal raw minutes: `1 day = 1440`, `5 days = 7200`.
- Whole-day placement uses project working-date sequence and preserves clock time.
- Fractional days remain working-minute placement because Phase 2E has no persisted fractional-day calendar model.
- Fixed Daily and Custom by Day workload planning now use selected project weekdays, holidays, and working overrides.
- Custom daily values survive calendar reclassification.
- `TaskDialog` now explicitly cleans child workload editors and unregisters from window lifecycle tracking.

Evidence:

- Focused duration/workload/CPM authority group: 165 passed, 0 failed.
- Repaired semantic fallout: Phase 2B schedule filter, Phase 2E runtime constraint refresh, and schedule snapshot integrity files passed after fixture updates.
- Final full isolated regression: 116 files, 2533 passed, 0 failed, 0 errors, 0 skipped, peak RSS 410348 KB, elapsed 334.343s.
- `test_task_duration_time_roundtrip_forensics.py` after cleanup repair: 50 passed in 5.368s with 131368 KB RSS; final full run: 5.680s with 131584 KB RSS.
- Production DB read-only hash unchanged: `aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`.

Human witness is accepted by the final gate brief. Phase 2F remains not started.

## 23 Project calendar live authority closure - 2026-08-28

Classification: `todo_bird_phase2e_project_calendar_live_authority_fixed_human_witness_required`

Root cause fixed: project `NULL` calendar rows were resolved as hard Mon-Fri, masking global `settings.working_weekdays=[0, 1, 2, 3, 4, 5]` for project `SCHEDULING WITNESS FINAL`. Additional drift points were closed where DB dict calendars were not parsed as first-class inputs, runtime consumers duplicated calendar conversion, already-open Edit Task dialogs did not refresh target/workload from calendar events, and Project Calendar exception type was inferred from display text.

Corrected authority:

- Date exception / working override wins for that date.
- Explicit project weekdays win for normal dates.
- Project `NULL` weekdays inherit global working-week settings.
- Default Mon-Fri is only the final fallback.
- `TaskDialog`, `WorkEffortEditor`, CPM, schedule snapshots, WBS model/rollup, and Project Calendar dialog now use the same effective calendar authority.

Production read-only witness:

- Project `SCHEDULING WITNESS FINAL` id `6`: `working_weekdays=NULL`, no calendar exceptions.
- Global settings: `working_weekdays=[0, 1, 2, 3, 4, 5]`.
- Task `Foundation` id `14`: start `2026-09-01 09:00`, stored finish `2026-09-07 09:00`, duration `7200`.
- Effective target after fix: `2026-09-05 09:00` in read-only TaskDialog, CPM, and schedule snapshot paths.
- Fixed Daily workload witness: 4h/day across Tue, Wed, Thu, Fri, Sat = 1200 planned effort minutes.
- Production DB hash unchanged: `aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`.

Evidence:

- `PROJECT_CALENDAR_LIVE_AUTHORITY_DIAGNOSTIC.md`
- `PROJECT_CALENDAR_LIVE_AUTHORITY_FORENSIC_REPORT.md`
- New focused forensic suite: 55 passed, 0 failed.
- Adjacent impacted suites: 363 passed, 0 failed.
- Final full isolated regression: 117 files, 2588 passed, 0 failed, 0 errors, 0 skipped, peak RSS 411420 KB, elapsed 339.193s.

Human witness is accepted by the final gate brief. Phase 2F remains not started.

## 24 CPM subtask result propagation closure - 2026-09-02

Classification: `todo_bird_phase2e_cpm_subtask_result_propagation_fixed_human_witness_required`

Root cause fixed: WBS CPM rebuild admitted only main tasks, WBS data roles looked up CPM results only for `entity_type == "task"`, and Gantt dependency annotation reset CPM fields before restoring only task-level results. Subtasks were therefore either excluded from the CPM network or had calculated metadata dropped before WBS/Gantt display. Bare integer IDs also made task/subtask result lookup unsafe.

Corrected authority:

- Leaf tasks and leaf subtasks are CPM activities.
- WBS summary parents are derived projections and do not own leaf CPM results.
- `EntityRef(task|subtask, id)` is the authoritative CPM lookup key.
- The WBS CPM adapter rewrites typed leaf dependencies into synthetic canonical tasks for `CPMSchedulingService` without changing CPM math.
- WBS rows, WBS filters, Gantt rows, Gantt metadata restore, Gantt tooltips, schedule snapshots, and variance lookup now consume the same typed CPM result.

Production read-only witness:

- Project `SCHEDULING WITNESS FINAL` id `6` exists.
- Task `Foundation` id `14` exists.
- Subtasks `Excavation Final` id `14` and `Reinforcement Final` id `15` exist.
- The earlier production `dependencies=[]` note is archival and superseded by the accepted final live witness for `Reinforcement Final` with FS predecessor `Foundation > Excavation Final`, lag 0.
- Production DB hash unchanged: `aeb6099473c5df10681ef9192c8226bdc455eeb19db5dca5a6ff1f00af8940ff`.

Disposable FS oracle:

- `Foundation` remained a summary parent and was not a leaf CPM activity.
- `Excavation Final` and `Reinforcement Final` were admitted as typed subtask CPM leaves.
- FS lag 0 result matched: Excavation EF `2026-09-02 09:00` equals Reinforcement ES `2026-09-02 09:00`; Reinforcement EF `2026-09-03 09:00`.
- WBS exposed Reinforcement ES/EF/LS/LF, Total Float `0m`, Free Float `0m`, Critical, and Healthy status.
- Gantt tooltip exposed Current Forecast Start/Finish, ES/EF/LS/LF, float, criticality, and dependency summary, with no false `CPM: Not analyzed`.

Evidence:

- New focused propagation suite: 45 passed, 0 failed.
- Impacted UI/scheduling bundle: 250 passed, 0 failed.
- Adjacent scheduling/rollup/snapshot bundle: 391 passed, 0 failed.
- Final full isolated regression: 118 files, 2633 passed, 0 failed, 0 errors, 0 skipped, peak RSS 410460 KB, elapsed 341.715s.
- Forensic report: `CPM_SUBTASK_RESULT_PROPAGATION_REPORT.md`.

Human witness is accepted by the final gate brief. Phase 2F remains not started.

## 25 WBS parent summary dashboard parity closure - 2026-09-04

Classification: `todo_bird_wbs_parent_summary_dashboard_parity_fixed_human_witness_required`

Root cause fixed: WBS parent/main-task rows were not CPM activities, and the item model only looked up CPM results by the row's own leaf key. This made valid child CPM schedule values disappear at the parent level as `-`/empty cells.

Corrected authority:

- Parent/main-task rows receive derived `WBSCPMSummaryResult` metadata.
- Parent `CPMNodeResultRole` remains `None`; summaries do not masquerade as CPM leaf nodes.
- Summary ES/EF/LS/LF are descendant CPM envelopes.
- Summary Total Float and Free Float are not aggregated and display `N/A (Summary)`.
- Summary criticality means `Contains Critical` when any descendant leaf is critical.
- Dashboard project snapshot schedule metrics now use existing WBS/Gantt summary authorities through `DashboardScheduleSummaryService`.

Evidence:

- New focused parent-summary/dashboard parity suite: 41 passed, 0 failed.
- Adjacent WBS/Gantt/CPM bundle: 153 passed, 0 failed.
- Impacted schedule-details/WBS UI/Gantt-dashboard bundle: 162 passed, 0 failed.
- Production DB hash-only witness: `c8fb2bbe4f53fbce147a3fc5892014ede5a66a37030fb9dbe0e02ab2834f4513`.

This is a Phase 2E maintenance fix only. Phase 2F remains not started.
