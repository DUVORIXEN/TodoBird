# Todo Bird Phase 2E - Beta Fix Plan

Audit date: 2026-09-03

Final beta classification: `todo_bird_phase2e_beta_ready`

This plan supersedes the 2026-08-25 blocked stabilization plan. The former P0/S1 beta blockers are closed by later Phase 2E reports and the accepted `Reinforcement Final` live witness. This document is retained as historical release-control context only.

## Closed Before Beta

| Former Area | Current Gate Status |
| --- | --- |
| Actual execution state invariant | Closed |
| Calendar-aware CPM scheduling | Closed |
| Original baseline immutability | Closed |
| Schedule version DB governance | Closed |
| Production DB safety and release test isolation | Closed |
| Gantt Fit Project / WBS-Gantt schedule parity | Closed |
| Task/Subtask edit, dependency, status, blocker, delay, and save/reopen paths | Closed |
| Dashboard Light-mode tooltip and global popup consistency | Closed |
| Reminder Snooze | Closed |
| PySide6 teardown/theme/MainWindow lifecycle crashes | Closed |

## Final Gate Evidence

- Accepted live witness: `Reinforcement Final`, FS predecessor `Foundation > Excavation Final`, lag 0, Mon-Sat calendar, CPM analyzed, WBS and Gantt copied details matched.
- Focused S1 UI/runtime forensics: 43 passed.
- Production DB safety replay: 26 passed.
- Legacy migration replay: 68 passed.
- WBS teardown crash replay: 56 passed, return code 0.
- Bounded isolated tail regression: 41/41 files, 1188 passed, 0 failed, 0 errors.

## Post-Beta Debt

The only remaining work is non-blocking release-control polish: durable evidence-runner improvements, optional S3 visual/accessibility expansion, and continued discipline around copied/read-only production DB witnesses.

## Stop Condition

Phase 2E is Beta Ready. Do not begin Phase 2F until the user explicitly authorizes the next phase.
