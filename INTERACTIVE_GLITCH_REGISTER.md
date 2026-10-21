# Todo Bird Phase 2E Interactive Glitch Register

Date: 2026-09-03

Final classification:

`todo_bird_phase2e_beta_ready`

| ID | Severity | Symptom | Root Cause | Repair | Proof | Status |
| --- | --- | --- | --- | --- | --- | --- |
| INT-S1-001 | S1 | Subtask dependency authoring unavailable/not discoverable | Dependency picker was task-only | Added task/subtask typed dependency authoring service and TaskDialog controls | `test_dependency_authoring_workflow.py`, 67 passed | Fixed |
| INT-S1-002 | S1 | Subtask dependency metadata could be lost | Subtask collect/insert/update paths omitted dependencies | Preserved dependencies in subtask metadata and DB persistence | Subtask modal dependency persistence test passed | Fixed |
| INT-S1-003 | S1 | Typed subtask dependencies could be rejected by controller | Controller used legacy task-only validation | Routed typed payloads to `DependencyAuthoringService` | TaskController typed validation tests passed | Fixed |
| INT-S1-004 | S1 | Cross-project typed dependency could be misclassified | Active-project candidate snapshot hid external nodes | Added all-project lookup for cross-project detection | Cross-project validation tests passed | Fixed |
| INT-S1-005 | S1 | Blocker/delay category could enter confusing none state | Lowercase/empty/null category values not normalized strictly | Normalized none-like values and tightened save validation | `test_status_blocker_delay_workflow.py`, 59 passed | Fixed |
| INT-S2-006 | S2 | Blocker/delay controls looked dead when status was not Blocked/Delayed | Disabled controls lacked clear per-control explanation | Added status-gate tooltips/accessibility | Tooltip and gating tests passed | Fixed |
| INT-S2-007 | S2 | Dependency add flow was too hidden in table-only UI | User had to discover row checkboxes and embedded cells | Added explicit predecessor/type/lag/add/remove workflow | Global interaction tests passed | Fixed |
| INT-S2-008 | S2 | Task pin color dropdown looked dead when task was not pinned | Disabled dropdown had no object name/help text | Added object names, accessible names, and tooltips for task/subtask pin color dropdowns | Global disabled-combo audit passed | Fixed |
| INT-D1-009 | Decision | New unsaved task/subtask cannot author dependencies immediately | No stable task/subtask database ID exists before first save | UI now explains save-first requirement | Global disabled-control audit passed | Accepted constraint |
| INT-S1-010 | S1 | Schedule Details for planned Gantt bars was incomplete | Formatter exposed a partial presentation model instead of the complete inspector contract | Added canonical `ScheduleDetailsCollector` and full section formatter | `test_schedule_details_completeness_parity.py`, 89 passed in full run | Fixed |
| INT-S1-011 | S1 | Project output could be blank in Schedule Details | Gantt/WBS callers depended on incomplete view-local project state | Added project-map/database fallback resolution in Gantt and WBS detail paths | Gantt/WBS parity and project-name resolver tests passed | Fixed |
| INT-S1-012 | S1 | WBS Schedule Details dropped CPM/planned/dependency metadata | WBS path passed raw `WBSNode` into the formatter | WBS detail path now resolves a schedule-rich `GanttWBSRow` using existing adapter authority | WBS schedule-rich-row guard test passed | Fixed |
| INT-S2-013 | S2 | Inspector could not explain rendered planned bar x-position | Gantt chart did not attach rendered bar geometry to the task object | Captured `gantt_bar_left_x` and `gantt_bar_right_x` after bar creation | Gantt geometry guard test passed | Fixed |
| INT-S2-014 | S2 | Gantt action handling could regress after helper insertion | Helper was temporarily placed before the existing open/complete/start action block | Restored action branches to `on_gantt_task_action` and placed helper at class scope | Gantt action-structure guard test passed | Fixed |
| INT-S2-015 | S2 | DB safety tests could fail after legitimate older DB changes | Tests encoded a stale absolute production DB hash | Replaced stale constants with same-test before/after hash invariants | Popup and world-clock authority tests passed | Fixed |
| INT-D1-016 | Decision | Plain SQLite CLI production probes can change main DB bytes under WAL | Opening the WAL database with plain `sqlite3` can checkpoint sidecar state | Logged checkpoint behavior; future witnesses should use copied DBs or hash-only checks unless checkpointing is intended | Current logical integrity `ok`, counts unchanged at 5 projects / 10 tasks / 9 subtasks | Tooling caution |
| INT-S2-017 | S2 | Dashboard hover tooltip/popup unreadable in Light mode | Dashboard chart hover path called native `QToolTip.showText` directly and relied on stale global/native tooltip state | Added dashboard tooltip theme resolver, rich tooltip markup, and per-hover `QToolTip` palette synchronization | `test_dashboard_light_popup_theme_authority.py`, 28 passed; full isolated 3028 passed | Fixed |
| INT-S2-018 | S2 | Repeated PySide6/IDE test sessions could crash during theme switch after closing MainWindow | Hidden shutdown-complete top-level windows and native tooltip labels could survive into the next `QApplication.setStyleSheet` pass | ThemeController clears native tooltip widgets and deletes hidden shutdown-complete top-level windows before QSS swap; MainWindow disconnects owned theme hooks on close | Two-test crash reproducer now passes; `test_shutdown_lifecycle.py` passed; full isolated 3028 passed | Fixed |
| INT-S1-019 | S1 | Dashboard Light-mode tooltip still unreadable through ordinary widget hover | The live path used `QWidget.setToolTip(...) -> QEvent.ToolTip -> QTipLabel`, bypassing the earlier chart hit-region helper | Added `AnimatedDashboardChart.event(...)` tooltip interception and `DashboardTooltipEventFilter` for non-chart dashboard widgets | Before RGB `(17,24,39)/(17,24,39)`; after RGB `(238,242,247)/(17,24,39)`; S1 forensics 43 passed | Fixed |
| INT-S1-020 | S1 | Subtask Blocker/Delay Management lacked task-level parity | Canonical `SubtaskDialog`, inline subtask editor, and `subtasks` persistence contract were not aligned | Added matching controls, validation, save/reopen persistence, and `_ensure_subtask_workflow_schema(...)` | S1 forensics 43 passed; status workflow 59 passed; Phase 2D migration 68 passed | Fixed |
| INT-S1-021 | S1 | Reminder Snooze action could fail | `QAction.triggered` lambda required a positional checked argument even though this runtime can emit a zero-argument signal | Added safe button slot, zero-argument-safe action binding, and themed `reminder_snooze_menu` | S1 forensics 43 passed; reminder policy/startup files passed in tail regression | Fixed |
| INT-S1-022 | S1 | Isolated WBS test file passed assertions then crashed with signal 11 | `test_wbs_raw_vs_summary_authority.py` created Qt model objects without owning a `QApplication` fixture | Added module-level `qapp` lifecycle fixture | Isolated replay: 56 passed, return code 0; tail regression passed through the same file | Fixed |
| INT-S2-023 | S2 | World Clock country discovery returned only 15 countries | `pytz` was absent and fallback used only popular presets | Added dependency-free OS tzdb fallback using `iso3166.tab`, `zone1970.tab`, and `zone.tab` | `test_world_clock_authority.py`: 26 passed; tail regression completed | Fixed |
| INT-S1-024 | S1 | WBS parent/main-task schedule columns showed empty dash state while child subtasks had valid CPM values | Parent WBS rows are summaries, not CPM leaves, and no derived summary CPM display contract existed | Added `WBSCPMSummaryResult`, WBS summary display labels, Gantt summary CPM metadata parity, and dashboard schedule summary projection | `test_wbs_parent_summary_dashboard_parity.py`: 41 passed; adjacent bundle 153 passed; impacted bundle 162 passed | Fixed |

## Open Glitches

No open automated S1/S2 interaction defects remain in the audited Phase 2E scope.

## Human Witness Accepted

The 2026-09-03 final gatekeeper brief accepts the current live witness and freezes the previously human-accepted interaction areas. These items are no longer open blockers:

- Open/Edit `Reinforcement Final`.
- Add predecessor `Excavation Final`.
- Select FS.
- Keep lag 0.
- Save.
- Confirm WBS/CPM/Gantt refresh in the live desktop UI.
- Open Schedule Details for the planned Gantt bar and WBS row for `Cycle Task 9`.
- Confirm the Project field is populated.
- Confirm Identity, Planned Input, Current Forecast / CPM, Dependencies, Constraint / Deadline, Calendar, Baseline / Revision, and Actual sections are visible.
- In Light mode, hover Dashboard Workload/Capacity, Status, Weekly Activity, and dashboard range controls; confirm readable light popups. Repeat after Light/Dark live switching.
- Dashboard Light-mode tooltip readability.
- Status -> Blocker workflow.
- Status -> Delay workflow.
- Task/Subtask status popup/signal/save/reopen parity.
- Reminder Snooze action and menu styling.

No open, partial, blocked, or decision-required S0/S1/S2 interaction defects remain in the Phase 2E beta gate. Phase 2F was not started.
