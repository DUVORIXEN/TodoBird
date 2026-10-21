# Todo Bird Phase 2E Full System Audit - Master Defect Register

Audit date: 2026-08-25

Final beta classification: `todo_bird_phase2e_full_system_audit_complete_beta_blocked`

## Audit Evidence Summary

- Canonical runtime entry point verified: `todo_bird_app/app.py`, not `main.py`.
- Bounded runtime witness passed on copied DB: `PYTHONFAULTHANDLER=1 QT_FATAL_WARNINGS=0 QT_QPA_PLATFORM=offscreen ./venv/bin/python -X faulthandler -m todo_bird_app.app --check-init --database /tmp/todo_bird_phase2e_audit_runtime.db`.
- Production DB main-file hash stayed unchanged before/after copied-DB runtime witness: `8317754aae5262bda93363b38e627fff94bc23061241c9b9023de41b19b53ecc`.
- Production DB sidecars existed during audit: `todo_bird.db-wal` and `todo_bird.db-shm`.
- Schema table reports version 16; SQLite `PRAGMA user_version` reports 0; code constant `CURRENT_SCHEMA_VERSION = 15`.
- Test tree contains 95 `test_*.py` files. Full monolithic execution was not rerun in this audit pass because the user-reported failure mode is IDE/test-process exhaustion. Audit witnesses were isolated subprocesses.
- PASS observations: Gantt scene reference release occurs before `scene.clear()`; normal CPM criticality uses total float exactly equal to zero; deadline service uses deterministic safe/missed logic.

## System Map

Runtime:

`todo_bird_app.app.main()` -> `QApplication` -> `DatabaseManager` -> `SettingsManager` -> `ThemeController` -> `MainWindow`.

Main UI:

`MainWindow` owns one `TaskController`, a `NavigationController`, `CommandRegistry`, sidebar/header, and a `QStackedWidget` containing Dashboard, Inbox, Today, Focus, Upcoming, Projects, Completed, Daily Review, Gantt, Settings, Pilot Feedback, Calendar, and Analytics.

Scheduling and WBS:

UI views -> `TaskController` / direct DB paths -> services (`CPMSchedulingService`, `ScheduleConstraintService`, `ScheduleVarianceService`, `ScheduleVersionService`, `WBSService`, `WBSRollupService`, `GanttWBSAdapter`) -> models (`Task`, `Project`, WBS models) -> `DatabaseManager` SQLite persistence -> Qt signals/global event bus -> refreshed views -> Gantt/WBS rendering.

Rendering:

Gantt view -> `GanttWBSAdapter` rows -> `GanttChartWidget` -> `QGraphicsScene`/`GanttTaskItem`/dependency graphics/timescale paint. WBS view -> `WBSItemModel`/`WBSFilterProxyModel` -> `WBSTreeView`/delegate.

Persistence:

`todo_bird_app/data/todo_bird.db` is the default database. `TODO_BIRD_DB` or `--database` can redirect runtime. `DatabaseManager` initializes schema and enables WAL on first connection.

## Defect Counts

- Total defects: 14
- S0 CRITICAL: 0
- S1 HIGH: 5
- S2 MEDIUM: 8
- S3 LOW: 1

## AUD-001

ID: AUD-001

Severity: S1 HIGH

Area: Actual execution, Task Dialog, Execution Performance, production data

Type: Data integrity / state-machine authority leak

Observed behavior: The app allows and production data contains tasks whose status is `In Progress` while `actual_end_date` is populated. Production read-only query found task IDs 6 and 7 in this contradictory state. `ExecutionPerformanceService` classifies any task with `actual_finish_dt` as completed even if its status is `In Progress`.

Expected behavior: Actual execution state must be mutually exclusive: Not tracked has no actual start/finish, In Progress has actual start and no actual finish, Finished has actual start and actual finish. UI and services must agree.

Root cause: `TaskDialog` stores the actual finish checkbox independently from selected status, then assigns `self.task.status = selected_status` after writing actual dates. The execution service infers completed state from actual finish alone.

Evidence: `todo_bird_app/widgets/task_dialog.py:437-439`, `todo_bird_app/widgets/task_dialog.py:507-508`, `todo_bird_app/widgets/task_dialog.py:2252-2282`, `todo_bird_app/services/execution_performance_service.py:174-183`; production DB check found IDs 6 and 7; isolated witness returned `execution_state completed` for an `In Progress` task with an actual finish.

Affected files: `todo_bird_app/widgets/task_dialog.py`, `todo_bird_app/services/execution_performance_service.py`, `todo_bird_app/database.py`, views consuming execution state.

User impact: A user can believe work is still in progress while analytics/Gantt/performance calculations treat it as finished.

Data risk: High. Contradictory rows already exist.

Calculation risk: High. Start/finish variance and execution state can be wrong.

Rendering risk: Medium. Actual bars can render closed rather than open.

Recommended fix: Centralize an `ActualExecutionState` invariant at save time and DB-controller boundary. Refuse `In Progress` with actual finish, auto-align status only with explicit user confirmation, and add production data diagnostic reporting without mutation.

Regression tests needed: TaskDialog save matrix for every status/actual checkbox combination; DB/controller invariant tests; production-data diagnostic test using a temp copy; Gantt open-vs-closed actual bar pixel test.

Beta blocker? YES

## AUD-002

ID: AUD-002

Severity: S1 HIGH

Area: CPM, working calendars, schedule calculation

Type: Calculation correctness

Observed behavior: CPM forward pass computes `EF = ES + duration` in raw minutes. Project calendar checks only whether the start day is working. A Friday 09:00 task with 960 minutes on a Mon-Fri calendar finishes Saturday 01:00 with no diagnostic.

Expected behavior: Working calendar must affect schedule calculations where appropriate. A non-working Saturday finish should be advanced into the next working window or clearly diagnosed by a documented calendar model.

Root cause: `CPMSchedulingService` uses naive elapsed-time addition for planned schedule duration and applies calendar only as a start-date availability check.

Evidence: `todo_bird_app/services/cpm_scheduling_service.py:895-970`, `todo_bird_app/services/cpm_scheduling_service.py:1135-1146`; isolated witness returned ES `2026-09-04 09:00:00`, EF `2026-09-05 01:00:00`, diagnostics `[]`.

Affected files: `todo_bird_app/services/cpm_scheduling_service.py`, `todo_bird_app/services/schedule_constraint_service.py`, `todo_bird_app/utils/working_calendar.py`, Gantt/WBS views.

User impact: Forecast dates can land on non-working days even when the project calendar says they should not.

Data risk: Medium. Incorrect forecasts may be baselined or approved.

Calculation risk: High. ES/EF/LS/LF/float/deadline outcomes can be materially wrong.

Rendering risk: Medium. Gantt bars show calendar-invalid spans.

Recommended fix: Define a single planned schedule calendar engine for working-time addition/subtraction, exceptions, leads/lags, constraints, and backward pass. Keep actual elapsed full-calendar and separate.

Regression tests needed: Mon-Fri, Mon-Sat, 7-day, weekend-only, holiday exception, working override, long task crossing exception, backward pass with constraints, and deadline/float cases.

Beta blocker? YES

## AUD-003

ID: AUD-003

Severity: S1 HIGH

Area: Baseline, approved revisions, WBS UI, DB persistence

Type: Historical authority destruction

Observed behavior: WBS exposes "Replace Original Baseline..." and "Clear Original Baseline..." and DB methods update/null baseline columns on projects, tasks, and subtasks. This conflicts with Phase 2E language describing immutable schedule versions preserving original baseline history.

Expected behavior: Original Baseline must be explicit, immutable, complete, transactional, and historical. Approved revisions must not make Original Baseline destructible.

Root cause: Phase 2D mutable baseline columns remain a destructive authority path alongside Phase 2E schedule versions.

Evidence: `todo_bird_app/views/wbs_project_view.py:661-744`, `todo_bird_app/database.py:1375-1475`, `todo_bird_app/services/schedule_version_service.py:1-6`.

Affected files: `todo_bird_app/views/wbs_project_view.py`, `todo_bird_app/database.py`, `todo_bird_app/services/schedule_version_service.py`, `todo_bird_app/services/schedule_variance_service.py`.

User impact: A user can destroy or overwrite history while believing the baseline is approved/historical.

Data risk: High. Historical comparison can be lost.

Calculation risk: High. Variance against baseline changes retroactively.

Rendering risk: Medium. Gantt/WBS baseline bars can silently change or disappear.

Recommended fix: Make Original Baseline a schedule-version snapshot, not mutable task columns. Remove destructive replace/clear actions or convert them to create-new-revision / archive-visible-baseline workflows with explicit audit trail.

Regression tests needed: Attempts to replace/clear original baseline fail or create new versions; original version items remain byte-identical after edits; WBS/Gantt comparison stays stable after current forecast changes.

Beta blocker? YES

## AUD-004

ID: AUD-004

Severity: S1 HIGH

Area: Schedule versions schema v16

Type: DB integrity / governance

Observed behavior: `schedule_versions` and `schedule_version_items` lack DB-level uniqueness and immutability guarantees. `delete_schedule_version()` deletes any version ID. Version items use polymorphic `entity_type/entity_id` with no FK to tasks/subtasks. Sequence order is computed as `len(versions)+1`, so gaps/deletes/duplicates can create ambiguous order.

Expected behavior: Version history should be immutable, ordered deterministically, project-isolated, duplicate-resistant, and protected against orphan/invalid items.

Root cause: Governance is implemented as service convention rather than enforced persistence rules.

Evidence: `todo_bird_app/database.py:674-787`, `todo_bird_app/services/schedule_version_service.py:115-160`; current production DB had no orphan items, but schema permits them.

Affected files: `todo_bird_app/database.py`, `todo_bird_app/services/schedule_version_service.py`, schedule comparison consumers.

User impact: Schedule comparison can become non-deterministic or historically invalid after deletes/imports/direct DB paths.

Data risk: High. Approved snapshots can be deleted or duplicated.

Calculation risk: Medium. Variance reference selection can point to wrong or incomplete items.

Rendering risk: Medium. Revision/baseline bars can be incomplete or stale.

Recommended fix: Add DB constraints and service guards: one original baseline per project, unique `(project_id, sequence_order)`, guarded deletion of original baseline, valid version type checks, item uniqueness, and explicit orphan diagnostics.

Regression tests needed: Duplicate original baseline rejected; duplicate sequence rejected; original delete blocked; orphan item creation rejected or diagnosed; latest revision deterministic after deletion.

Beta blocker? YES

## AUD-005

ID: AUD-005

Severity: S1 HIGH

Area: Production DB safety, tests, persistence lifecycle

Type: Test architecture / destructive write surface

Observed behavior: `DatabaseManager` opens read/write, initializes migrations, and executes WAL mode on connection. A test named "no production DB mutation" opens the live production DB through `DatabaseManager`. `MainWindow.closeEvent()` persists geometry to settings on normal close. Production DB sidecars existed during audit; main DB hash stayed unchanged, but sidecar metadata changed during inspection.

Expected behavior: Audit/test code must never open production DB through write-capable application managers. UI smoke must use a copy. Read-only inspection should be isolated from WAL side effects where possible.

Root cause: The default DB manager is both application runtime and migration authority, with no read-only/audit mode. Some tests hardcode production DB path.

Evidence: `todo_bird_app/database.py:20-37`, `todo_bird_app/app.py:47-48`, `todo_bird_app/views/main_window.py:655-660`, `todo_bird_app/tests/test_execution_aware_schedule_authority.py:872-880`; production DB hash `8317754aae5262bda93363b38e627fff94bc23061241c9b9023de41b19b53ecc`.

Affected files: `todo_bird_app/database.py`, `todo_bird_app/app.py`, `todo_bird_app/views/main_window.py`, `todo_bird_app/tests/test_execution_aware_schedule_authority.py`, witness scripts.

User impact: Release validation can accidentally mutate real user data or sidecar state.

Data risk: High.

Calculation risk: Medium, because migrations/baselines/settings can change under test.

Rendering risk: Low direct risk, medium indirect risk through settings.

Recommended fix: Add a read-only DB inspection path using SQLite URI mode and no migrations/WAL change; forbid production path in pytest fixtures; make smoke tests copy DB first; gate app close geometry writes behind runtime mode where needed.

Regression tests needed: Test suite fails if `DatabaseManager` is constructed with production path under pytest; read-only inspector cannot write; check-init with `--database` leaves production hash and sidecars unchanged.

Beta blocker? YES

## AUD-006

ID: AUD-006

Severity: S2 MEDIUM

Area: Backup, restore, portable archive

Type: Recovery completeness

Observed behavior: Backup checkpoints WAL then copies the main DB file. Restore copies the backup over the destination but does not clear/check destination `-wal` and `-shm` sidecars. Portable export/import includes tasks and projects but not schedule versions, schedule version items, calendar exception rows as first-class rows, media, or all recovery metadata.

Expected behavior: Backup/restore should preserve a consistent full application state and avoid stale WAL/SHM confusion after restore.

Root cause: Recovery is main-file centered and portable archive is limited to tasks/projects.

Evidence: `todo_bird_app/services/backup_manager.py:34-52`, `todo_bird_app/services/backup_manager.py:75-91`, `todo_bird_app/services/backup_manager.py:94-143`.

Affected files: `todo_bird_app/services/backup_manager.py`, `todo_bird_app/database.py`.

User impact: A beta user may restore or migrate and lose approved schedule history or carry stale WAL state.

Data risk: Medium.

Calculation risk: Medium, especially for baselines/revisions.

Rendering risk: Low direct risk, medium if schedule history is missing.

Recommended fix: Restore with closed connections, remove/checkpoint sidecars intentionally, verify `quick_check` after restore, and include all Phase 2E tables in portable archive with ID remapping rules.

Regression tests needed: Restore with existing WAL/SHM; portable export/import round-trips versions, version items, calendar exceptions, settings, and subtasks.

Beta blocker? NO

## AUD-007

ID: AUD-007

Severity: S2 MEDIUM

Area: Date/time parsing, locale, DST

Type: Calculation consistency

Observed behavior: General `parse_date()` accepts only `YYYY-MM-DD`, while constraint parsing also accepts `DD/MM/YYYY` and `DD-MM-YYYY`. The ambiguous string `03/04/2026` becomes `2026-04-03` in constraints and `None` in general parsing. All core datetimes are naive local-time values.

Expected behavior: There should be one date/time authority with explicit accepted formats, no silent ambiguity, and a documented local-time/DST policy.

Root cause: Date parsing is duplicated across utility and constraint services, and timezone handling is not centralized.

Evidence: `todo_bird_app/utils/time_math.py:108-130`, `todo_bird_app/services/schedule_constraint_service.py:96-127`; isolated witness showed `parse_date('03/04/2026') = None` and `parse_constraint_datetime('03/04/2026') = 2026-04-03 00:00:00`.

Affected files: `todo_bird_app/utils/time_math.py`, `todo_bird_app/services/schedule_constraint_service.py`, date widgets, schedule services.

User impact: Dates can be rejected or interpreted differently depending on field.

Data risk: Medium.

Calculation risk: Medium.

Rendering risk: Low to medium through wrong timeline placement.

Recommended fix: Create a single parser/formatter contract for storage and UI. Reject ambiguous non-ISO input unless a locale is explicitly selected. Document DST/local-time limitations or store timezone-aware instants where needed.

Regression tests needed: `YYYY-MM-DD`, invalid leap day, valid Feb 29, 2100 non-leap year, ambiguous `03/04/2026`, cross-midnight, 23h59/24h/24h01, DST transition policy tests.

Beta blocker? NO

## AUD-008

ID: AUD-008

Severity: S2 MEDIUM

Area: Gantt editing and controller authority

Type: Authority bypass / persistence rule leak

Observed behavior: Gantt schedule changes persist narrow SQL updates directly through `self.db_manager.get_connection()` and commit. Overlap feedback explicitly says the schedule is saved anyway. This bypasses `TaskController.update_task()` and any centralized validation rules.

Expected behavior: User schedule edits should pass through one canonical mutation authority that validates constraints, dependencies, project scope, and data invariants before persistence.

Root cause: Rendering interaction code owns part of schedule persistence.

Evidence: `todo_bird_app/views/gantt_view.py:2455-2554`, `todo_bird_app/views/gantt_view.py:2565-2583`.

Affected files: `todo_bird_app/views/gantt_view.py`, `todo_bird_app/controllers/task_controller.py`, `todo_bird_app/database.py`.

User impact: Dragging/resizing can save invalid overlaps or bypass diagnostics.

Data risk: Medium.

Calculation risk: Medium.

Rendering risk: Medium.

Recommended fix: Route Gantt edits through a schedule mutation service or controller method that validates and returns a structured diagnostic decision.

Regression tests needed: Drag creates valid persisted update; invalid overlap/constraint/dependency conflict either blocks or records explicit diagnostic; controller signal refresh still occurs once.

Beta blocker? NO

## AUD-009

ID: AUD-009

Severity: S2 MEDIUM

Area: Dependencies

Type: DB integrity / validation bypass

Observed behavior: `TaskController.update_task()` validates changed dependencies, but `DatabaseManager.update_task()` accepts and stores the `dependencies` JSON field directly. The DB schema stores dependencies as text without FK constraints.

Expected behavior: Dependency mutations should have one authoritative validation path, and invalid references should not be persistable by normal app code.

Root cause: Dependency integrity is controller-level convention, not DB/service invariant.

Evidence: `todo_bird_app/controllers/task_controller.py:104-132`, `todo_bird_app/database.py:883-982`, schema dependency field in `todo_bird_app/database.py`.

Affected files: `todo_bird_app/controllers/task_controller.py`, `todo_bird_app/database.py`, dependency picker/Gantt consumers.

User impact: Orphan, cross-project, or cyclic dependency data can enter through direct DB paths or future scripts.

Data risk: Medium.

Calculation risk: Medium to high if invalid dependencies reach CPM.

Rendering risk: Medium through wrong or missing dependency graphics.

Recommended fix: Move dependency update into a domain service and make DB methods private/low-level or validate dependency JSON before update. Consider normalized dependency table for enforced integrity.

Regression tests needed: Direct DB update rejects invalid dependency JSON or marks it diagnostic; controller and Gantt both use the same service; cross-project dependency cannot persist.

Beta blocker? NO

## AUD-010

ID: AUD-010

Severity: S2 MEDIUM

Area: Gantt Fit Project

Type: UX/rendering behavior mismatch

Observed behavior: The `Fit Project` button calls `gantt_chart.go_to_today()` rather than fitting the timeline to the selected project range. The timescale engine can calculate ranges from current, baseline, actual, constraints, and deadlines, but the button does not invoke that behavior.

Expected behavior: Fit Project should include all enabled visible schedule layers: current, baseline, revision, actual, constraints, and deadlines.

Root cause: Toolbar command is wired to a today navigation helper.

Evidence: `todo_bird_app/views/gantt_view.py:134-136`, `todo_bird_app/views/gantt_view.py:2220-2222`, `todo_bird_app/gantt/timescale_engine.py:66-138`.

Affected files: `todo_bird_app/views/gantt_view.py`, `todo_bird_app/gantt/gantt_chart.py`, `todo_bird_app/gantt/timescale_engine.py`.

User impact: A user can click Fit Project and still not see early actuals, late finishes, baselines, deadlines, or out-of-range project spans.

Data risk: Low.

Calculation risk: Low.

Rendering risk: Medium.

Recommended fix: Implement a real fit-to-visible-authorities command and reserve `go_to_today()` for a separate Today command.

Regression tests needed: Fit Project range includes current forecast, baseline, approved revision, open actual through now, deadlines, and constraints.

Beta blocker? NO

## AUD-011

ID: AUD-011

Severity: S2 MEDIUM

Area: UI rendering, typography, theme, high-DPI

Type: Rendering test gap / design system drift

Observed behavior: Current UI code still contains extensive hardcoded `setStyleSheet`, color, padding, radius, and fixed/minimum sizing across views and widgets. Example fixed controls include actual execution labels/checks at 85 px. Existing tests include some pixel checks, but coverage is uneven across all required component states, DPI levels, and Gantt layers.

Expected behavior: Font size should drive control size, density should add whitespace only, and critical controls/layers should have pixel witnesses for light/dark, 10pt/20pt, 100/125/150/200 percent, resting/hover/focus/disabled.

Root cause: Design system tokenization and test coverage evolved incrementally; old QSS and fixed geometry remain.

Evidence: `todo_bird_app/widgets/task_dialog.py:403`, `todo_bird_app/widgets/task_dialog.py:439`, `todo_bird_app/views/gantt_view.py:386-388`, `todo_bird_app/views/gantt_view.py:447-475`, `todo_bird_app/ui/components/search_field.py:46-79`, multiple hardcoded color/style hits in current app files.

Affected files: `todo_bird_app/views/*`, `todo_bird_app/widgets/*`, `todo_bird_app/ui/components/*`, `todo_bird_app/gantt/*`, typography tests.

User impact: Text/control clipping, inconsistent visibility, and color-only meaning remain likely at larger fonts and DPI.

Data risk: Low.

Calculation risk: Low.

Rendering risk: High.

Recommended fix: Add a visual witness matrix for critical controls and Gantt layers, then retire fixed widths/heights or compute them from font metrics and tokenized spacing.

Regression tests needed: Component state pixel tests for ModernButton, ModernComboBox, ModernCheckbox, ToggleSwitch, SegmentControl; Gantt layer pixel tests for current/baseline/revision/open actual/closed actual/dependency/constraint/deadline.

Beta blocker? NO, unless human UI witness reproduces clipping on primary flows.

## AUD-012

ID: AUD-012

Severity: S2 MEDIUM

Area: Deadline terminology, Gantt health UI

Type: UX terminology conflict

Observed behavior: Deadline service explicitly defers arbitrary at-risk thresholds and sets `is_at_risk = False`, while Gantt health UI presents an "At Risk" bucket/chip.

Expected behavior: Deadline status should be deterministic safe/missed unless a separate at-risk product behavior is clearly named and sourced.

Root cause: Gantt health terminology mixes delay/timing categories with deadline contract language.

Evidence: `todo_bird_app/services/schedule_constraint_service.py:268-301`, `todo_bird_app/views/gantt_view.py:447-475`.

Affected files: `todo_bird_app/services/schedule_constraint_service.py`, `todo_bird_app/views/gantt_view.py`, delay/timing status consumers.

User impact: User may believe deadline risk thresholds exist when they do not.

Data risk: Low.

Calculation risk: Medium if users make decisions from a mislabeled status.

Rendering risk: Low.

Recommended fix: Rename the Gantt chip to the actual sourced concept, or introduce a documented at-risk algorithm separate from deadline safe/missed.

Regression tests needed: Deadline safe/missed labels; Gantt health source mapping; no deadline "at risk" unless documented.

Beta blocker? NO

## AUD-013

ID: AUD-013

Severity: S3 LOW

Area: Schema version reporting

Type: Maintainability / release metadata

Observed behavior: Code constant `CURRENT_SCHEMA_VERSION = 15`, migrations apply v16, production `schema_version` reports 16, and SQLite `PRAGMA user_version` reports 0.

Expected behavior: Schema version constants, migration table, and optional SQLite user_version should agree or be clearly documented.

Root cause: v16 migration was added without updating the top-level constant or PRAGMA.

Evidence: `todo_bird_app/database.py:9`, `todo_bird_app/database.py:124-128`, production read-only query: schema version 16, user_version 0.

Affected files: `todo_bird_app/database.py`, release diagnostics.

User impact: Low direct user impact, but release/debug tooling can misreport DB state.

Data risk: Low.

Calculation risk: Low.

Rendering risk: None.

Recommended fix: Update `CURRENT_SCHEMA_VERSION` to 16 and optionally set/check `PRAGMA user_version`.

Regression tests needed: Fresh DB and migrated DB report version 16 through every version authority.

Beta blocker? NO

## AUD-014

ID: AUD-014

Severity: S2 MEDIUM

Area: Test execution architecture, release evidence durability

Type: Verification process fragility

Observed behavior: User reported repeated IDE crashes from repeated test runs. Current `conftest.py` has an autouse Qt cleanup fixture, but previous sharded reclosure artifacts expected under `/tmp/todo_bird_phase2e_reclosure/` were not present after the crash. Full suite execution evidence is therefore not durable across IDE/session crashes in this pass.

Expected behavior: Release evidence should be generated by isolated subprocess shards, persisted to a durable repo or configured artifact directory, and summarized without requiring repeated monolithic IDE runs.

Root cause: Test execution/reporting has depended on temporary locations and repeated interactive runs; Qt lifecycle safety has improved but the evidence workflow is still fragile.

Evidence: `todo_bird_app/tests/conftest.py:33-87`, `todo_bird_app/tests/test_shutdown_lifecycle.py:534-549`, missing `/tmp/todo_bird_phase2e_reclosure/summary.json` and `/tmp/todo_bird_phase2e_reclosure/final_smoke.json` during this resumed audit.

Affected files: `todo_bird_app/tests/conftest.py`, release witness scripts, audit/reclosure scripts.

User impact: The IDE can crash or lose evidence, forcing repeated validation and eroding confidence.

Data risk: Low direct, medium if tests accidentally hit production DB.

Calculation risk: Low direct.

Rendering risk: Medium because visual tests are most likely to stress Qt lifetime.

Recommended fix: Add a durable `evidence/phase2e/` sharded runner that records exact files collected, assigned, executed, passed, failed, skipped, errors, duplicates, missing, and unknown. Run each shard in a fresh process and never from an IDE test adapter.

Regression tests needed: Shard manifest completeness, duplicate/missing detection, failed-shard resume, crash-resilient artifact write, and no production DB path usage.

Beta blocker? NO by itself, but it blocks credible release signoff until rerun.
