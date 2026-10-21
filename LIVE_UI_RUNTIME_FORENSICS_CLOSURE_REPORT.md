# Todo Bird Phase 2E Live UI Runtime Forensics Closure Report

Date: 2026-09-03

Final classification:

`todo_bird_phase2e_live_ui_runtime_s1_failures_fixed_human_witness_required`

## Scope

This closure covers the reopened Phase 2E live UI failures reported by the user:

- Dashboard Light-mode popups/tooltips were inconsistent and could still render unreadable.
- Status -> Blocker/Delay Management controls appeared present but did not behave reliably.
- Reminder Snooze was not working reliably.
- Repeated test/IDE sessions were crashing after apparently passing tests.

No CPM math, WBS rollup math, dependency scheduling logic, or Phase 2F work was started.

## Root Causes

### Dashboard Native Tooltip Path

The previous Dashboard repair covered the custom chart hit-region hover helper, but the live human-visible failure came through standard Qt widget tooltips:

`DashboardView -> AdvancedCapacityChart / AdvancedStatusChart / AdvancedWeeklyActivityChart -> QWidget.setToolTip(...) -> QEvent.ToolTip -> QTipLabel`

Before repair, a direct `QHelpEvent(QEvent.ToolTip)` on the real capacity chart produced a native `QTipLabel` named `qtooltip_label` with no local style, and the active Light-mode tooltip palette was dark-on-dark:

- `BEFORE_POPUP_CLASS QTipLabel`
- `BEFORE_POPUP_OBJECT qtooltip_label`
- `BEFORE_QTOOLTIP_BASE_RGB (17, 24, 39)`
- `BEFORE_QTOOLTIP_TEXT_RGB (17, 24, 39)`

The permanent repair routes ordinary dashboard `QEvent.ToolTip` handling through `show_dashboard_widget_tooltip(...)`, which applies the current semantic tooltip palette immediately before `QToolTip.showText(...)`. Non-chart dashboard widgets use `DashboardTooltipEventFilter`.

After repair:

- `AFTER_POPUP_CLASS QTipLabel`
- `AFTER_POPUP_OBJECT qtooltip_label`
- `AFTER_QTOOLTIP_BASE_RGB (238, 242, 247)`
- `AFTER_QTOOLTIP_TEXT_RGB (17, 24, 39)`

### Status, Blocker, and Delay Workflow

Task status controls had partial UI gating, but the runtime signal path and actual combo popup activation were not proven. Subtask status/blocker/delay parity was structurally incomplete: the canonical `SubtaskDialog`, the inline TaskDialog subtask editor, and the `subtasks` persistence contract were not all aligned.

The repair adds:

- Stable object names, focus policy, popup-view names, and runtime signal logs for TaskDialog status and blocker/delay controls.
- The same workflow controls to canonical `SubtaskDialog` and inline "Edit Subtask Details".
- Subtask persistence for `status`, `delay_category`, `delay_reason`, `delay_notes`, and `delay_recorded_at`.
- A non-version-bumped schema hardening path, `_ensure_subtask_workflow_schema(...)`, while keeping `CURRENT_SCHEMA_VERSION = 16` so the packaged production DB is not forced into a test-time migration.

### Reminder Snooze

The snooze menu connected `QAction.triggered` using a lambda that required a positional checked argument. In this PySide6 runtime the signal can be emitted through a zero-argument path, so snooze actions could fail to call `on_snooze_selected(...)`.

The repair adds:

- A safe snooze button slot, `_on_snooze_button_clicked(self, _checked=False)`.
- Zero-argument-safe snooze action binding: `lambda _checked=False, m=minutes: ...`.
- A themed `QMenu` named `reminder_snooze_menu` so reminder popups follow the same Light/Dark semantic surface contract.

### Repeated Test/IDE Crash

The isolated regression exposed a concrete teardown crash: `test_wbs_raw_vs_summary_authority.py` passed all 56 assertions, then exited with signal 11. The file used `WBSItemModel`, a `QAbstractItemModel`, without explicitly owning a `QApplication` fixture. That can pass tests and still crash during Qt teardown.

The repair adds an explicit module-level `qapp` lifecycle fixture for that file. The same file now exits with return code 0 under the isolated runner.

### World Clock Regression Found During Tail Run

The final tail regression found an unrelated failure in World Clock country discovery: `pytz` is not installed in this venv, so `WorldClockService` fell back to the 15 popular presets while its contract expects 200+ countries.

The repair keeps the service offline and dependency-free by reading the OS timezone database files:

- `iso3166.tab`
- `zone1970.tab`
- `zone.tab`

`test_world_clock_authority.py` now passes again.

## Files Changed

- `todo_bird_app/widgets/dashboard_charts.py`
- `todo_bird_app/views/dashboard_view.py`
- `todo_bird_app/widgets/task_dialog.py`
- `todo_bird_app/widgets/subtask_dialog.py`
- `todo_bird_app/widgets/reminder_dialog.py`
- `todo_bird_app/database.py`
- `todo_bird_app/services/world_clock_service.py`
- `todo_bird_app/tests/test_phase2e_s1_live_runtime_forensics.py`
- `todo_bird_app/tests/test_wbs_raw_vs_summary_authority.py`

## Validation Evidence

- Compile gate:
  - `python3 -m py_compile todo_bird_app/database.py todo_bird_app/widgets/subtask_dialog.py todo_bird_app/widgets/task_dialog.py todo_bird_app/widgets/reminder_dialog.py todo_bird_app/widgets/dashboard_charts.py todo_bird_app/views/dashboard_view.py todo_bird_app/services/world_clock_service.py todo_bird_app/tests/test_phase2e_s1_live_runtime_forensics.py todo_bird_app/tests/test_wbs_raw_vs_summary_authority.py`
  - Passed.
- Focused live UI runtime forensics:
  - `QT_QPA_PLATFORM=offscreen PYTHONFAULTHANDLER=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 120 ./venv/bin/python -m pytest todo_bird_app/tests/test_phase2e_s1_live_runtime_forensics.py -q`
  - 43 passed.
- Adjacent popup/status/reminder/window regression:
  - `QT_QPA_PLATFORM=offscreen PYTHONFAULTHANDLER=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 180 ./venv/bin/python -m pytest ... -q`
  - 223 passed, 1 unrelated deprecation warning.
- Phase 2D legacy migration replay:
  - `QT_QPA_PLATFORM=offscreen PYTHONFAULTHANDLER=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 140 ./venv/bin/python -m pytest todo_bird_app/tests/test_phase2d_schedule_baseline_variance.py -q`
  - 68 passed.
- Production DB safety replay:
  - `QT_QPA_PLATFORM=offscreen PYTHONFAULTHANDLER=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 140 ./venv/bin/python -m pytest todo_bird_app/tests/test_phase2e_production_db_safety.py -q`
  - 26 passed.
- WBS teardown crash replay:
  - `timeout 300 ./venv/bin/python tools/run_isolated_pytest.py todo_bird_app/tests/test_wbs_raw_vs_summary_authority.py --timeout 140`
  - 56 passed, return code 0.
- World Clock authority replay:
  - `QT_QPA_PLATFORM=offscreen PYTHONFAULTHANDLER=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 timeout 140 ./venv/bin/python -m pytest todo_bird_app/tests/test_world_clock_authority.py -q`
  - 26 passed.
- Bounded isolated tail regression:
  - `timeout 1800 ./venv/bin/python tools/run_isolated_pytest.py <files 88-128> --timeout 140`
  - 41/41 files passed.
  - 1188 tests passed.
  - 0 failed, 0 errors.
  - Peak RSS: 498744 KB.
  - Elapsed: 100.916s.

The first full isolated pass had already completed files 1-86 before failing at file 87 on the schema-version mistake. After repair, file 87 and files 88-128 were rerun green. To respect the user's IDE-crash concern, I did not burn another full 128-file one-shot rerun after the bounded coverage was clean.

## Production DB Safety

Logical production DB state checked through read-only URI after validation:

- `PRAGMA integrity_check`: `ok`
- `schema_version`: 16
- `projects`: 5
- `tasks`: 10
- `subtasks`: 9
- Production `subtasks` schema remains without the new workflow columns, because the tests did not run a writable production migration.

Important note: the production DB file hash changed from the earlier pre-forensic value
`c472bda5ad40392be808ca07bb607e6728e1b0d72faa2d5ae8d5f0a402835b29`
to
`20cd4ba626ac19a2aee61a83f1d2fb0455785cf2b66c62ddb23e1cd7a085f8b4`.

This was caused by my direct `sqlite3 todo_bird_app/data/todo_bird.db ".schema subtasks"` inspection of a WAL-mode database, which can checkpoint sidecar WAL state into the main database file even when no app data is edited. The logical integrity, schema version, and row counts remain unchanged. Future production probes should use read-only SQLite URI mode only.

## Human Witness Required

Automated and live-equivalent paths are fixed, but a real desktop witness is still required before declaring Human Accepted or Beta Ready:

- Light mode Dashboard: hover Workload/Capacity, Status Breakdown, Weekly Activity, and the dashboard range combo.
- Switch Light -> Dark -> Light while Dashboard exists and repeat popup checks.
- Edit Task: change status to Blocked and Delayed, open category dropdown by mouse, enter reason, save, reopen, verify persistence.
- Edit Subtask through both the inline TaskDialog editor and canonical subtask dialog where reachable.
- Reminder popup: press Snooze, choose a snooze option, confirm the reminder is deferred and the menu styling is readable.

Beta Ready, Human Accepted, and Phase 2F are not declared by this report.
