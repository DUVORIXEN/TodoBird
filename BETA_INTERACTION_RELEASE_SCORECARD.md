# Todo Bird Phase 2E Beta Interaction Release Scorecard

Date: 2026-09-03

Final classification:

`todo_bird_phase2e_beta_ready`

## Executive Result

The reopened live UI S1 repair is complete and the final Phase 2E gate accepts the current human witness. Phase 2E interaction scope is Beta Ready. Phase 2F remains not started.

## Scorecard

| Gate | Result | Evidence |
| --- | --- | --- |
| Schedule Details reachability | Pass | Existing copy/view context-menu paths remain green |
| Schedule Details completeness | Pass | 8 required sections emitted from `ScheduleDetailsModel` |
| Planned Gantt bar parity | Pass | Planned bar start/finish and rendered x-coordinate fields exposed when available |
| CPM parity | Pass | ES/EF/LS/LF/TF/FF/critical/status consumed from existing adapter values |
| Dependency parity | Pass | Predecessors and successors exposed using typed identity parsing |
| Project name resolution | Pass | Gantt/WBS now resolve through maps, DB rows/objects, and safe fallback |
| WBS detail data source | Pass | WBS details consume schedule-rich `GanttWBSRow`, not raw `WBSNode` only |
| Non-fabrication | Pass | Unanalyzed CPM fields display `Not analyzed`; missing values stay explicit |
| Production DB safety | Pass | Same-audit production DB hash remained unchanged; earlier SQLite CLI WAL checkpoint is documented as a tooling caution, not an app write |
| Dashboard Light-mode popups | Pass | Workload/Capacity, Status, and Weekly Activity hover popups use semantic Light tokens |
| Dashboard native QWidget tooltip path | Pass | `QEvent.ToolTip` on `QTipLabel/qtooltip_label` now applies current semantic palette |
| Reminder Snooze | Pass | Button slot and zero-argument-safe `QAction.triggered` binding defer reminders correctly |
| Task/Subtask Blocker/Delay workflow | Pass | TaskDialog, inline subtask editor, canonical SubtaskDialog, and subtask persistence now align |
| Qt test teardown stability | Pass | WBS raw-vs-summary file now owns `QApplication` and exits with rc=0 |
| World Clock discovery | Pass | Offline OS tzdb fallback returns full country/timezone inventory without `pytz` |
| Theme-switch crash guard | Pass | Closed shutdown windows and native tooltip labels are cleared before global QSS swaps |
| Bounded isolated regression | Pass | Files 1-86 passed in the first isolated pass; file 87 rerun green; files 88-128 passed as tail continuation |
| Human witness | Pass | Current gatekeeper brief marks the live witness accepted |
| Beta Ready declaration | Pass | No S0 or beta-blocking S1 items remain |
| Phase 2F | Not started | No Phase 2F work was authorized or performed |

## Test Evidence

- Compile gate:
  - `python3 -m py_compile todo_bird_app/controllers/theme_controller.py todo_bird_app/views/main_window.py todo_bird_app/widgets/dashboard_charts.py todo_bird_app/tests/test_dashboard_light_popup_theme_authority.py`
  - Modified source and tests compiled successfully.
- Dashboard popup theme command:
  - `QT_QPA_PLATFORM=offscreen python3 -m pytest todo_bird_app/tests/test_dashboard_light_popup_theme_authority.py -q`
  - 28 passed.
- Targeted affected-area command:
  - `QT_QPA_PLATFORM=offscreen python3 -m pytest todo_bird_app/tests/test_dashboard_light_popup_theme_authority.py todo_bird_app/tests/test_popup_theme_authority.py todo_bird_app/tests/test_phase1f722_dashboard_chart_interaction.py todo_bird_app/tests/test_shutdown_lifecycle.py -q`
  - 94 passed.
- Historical full isolated command:
  - `QT_QPA_PLATFORM=offscreen python3 tools/run_isolated_pytest.py`
  - 127/127 files passed.
  - 3028 tests passed.
  - 0 failed, 0 errors, 0 skipped.
  - Peak RSS: 547688 KB.
  - Elapsed: 302.66s.

## Production DB Safety

- Production DB SHA-256 before this final narrow gate audit: `20cd4ba626ac19a2aee61a83f1d2fb0455785cf2b66c62ddb23e1cd7a085f8b4`
- Production DB SHA-256 after this final narrow gate audit: `20cd4ba626ac19a2aee61a83f1d2fb0455785cf2b66c62ddb23e1cd7a085f8b4`

The earlier WAL checkpoint caution still stands: future witnesses should avoid plain `sqlite3` production DB opens unless checkpointing is intended.

## Release Authority Statement

Automated live UI S1 repair and accepted human witness are closed for Phase 2E. The next release action is a controlled beta handoff, not Phase 2F and not another repeated full-test loop.

## 2026-09-03 Reopened S1 Evidence

- Focused S1 forensics: 43 passed.
- Adjacent popup/status/reminder/window regression: 223 passed, 1 unrelated deprecation warning.
- Legacy migration replay: 68 passed.
- Production DB safety replay: 26 passed.
- WBS teardown crash replay: 56 passed, return code 0.
- World Clock authority replay: 26 passed.
- Bounded isolated tail regression: 41/41 files, 1188 passed, 0 failed, 0 errors, peak RSS 498744 KB.

Production DB logical safety after read-only check: `integrity_check=ok`, schema version 16, 5 projects, 10 tasks, 9 subtasks. A direct SQLite CLI schema probe checkpointed WAL bytes and changed the main-file hash; no app data edit or writable production migration was performed.
