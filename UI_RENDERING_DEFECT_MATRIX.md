# Todo Bird Phase 2E - UI Rendering Defect Matrix

Audit date: 2026-08-25

Final beta classification: `todo_bird_phase2e_full_system_audit_complete_beta_blocked`

Legend: PASS means code or runtime evidence supports the requirement. PARTIAL means some support exists but the full requested matrix is not proven. FAIL means the audited behavior contradicts the requirement.

## Matrix

| View/component | Light | Dark | 10pt | 20pt | 100% | 125% | 150% | 200% | Resting | Hover | Focus | Disabled | Result |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Application startup/MainWindow | PASS | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PASS | N/A | PARTIAL | N/A | PARTIAL: copied-DB check-init passes, but full visible DPI matrix not witnessed |
| Navigation/sidebar/header | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PARTIAL: keyboard and overflow tests exist, but not complete state/pixel matrix |
| Dashboard metrics/charts | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL: custom paint tests exist, many hardcoded colors remain |
| Inbox/Today/Upcoming/Completed task lists | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PARTIAL: list logic tested, but pagination fixed widths and DPI coverage remain fragile |
| Projects/WBS shell | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PARTIAL: WBS model authority exists; visual state matrix incomplete |
| WBS tree/delegate | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PARTIAL: row/delegate tests exist; large-font clipping still not fully proven |
| Task Dialog actual execution panel | PARTIAL | PARTIAL | PARTIAL | FAIL | PARTIAL | PARTIAL | PARTIAL | FAIL | FAIL | PARTIAL | PARTIAL | PARTIAL | FAIL: 85 px fixed controls and contradictory actual-finish state are confirmed |
| Project Dialog/calendar dialog | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PARTIAL: direct QSS and fixed assumptions remain |
| Gantt toolbar | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PARTIAL: wrapped in horizontal scroll area, but toolbar height is still fixed from size hint |
| Gantt current forecast bars | PASS | PARTIAL | N/A | N/A | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | N/A | PARTIAL: rendering tests exist, but calendar invalid forecasts can render as if valid |
| Gantt baseline bars | PARTIAL | PARTIAL | N/A | N/A | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | N/A | PARTIAL: baseline can be cleared/replaced, so visual authority is fragile |
| Gantt approved revision bars | PARTIAL | PARTIAL | N/A | N/A | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | N/A | PARTIAL: comparison selector exists, but version integrity is not DB-enforced |
| Gantt actual bars | PARTIAL | PARTIAL | N/A | N/A | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | N/A | PARTIAL: open actual display logic exists, but status/finish contradictions can render wrong layer |
| Gantt dependency graphics | PARTIAL | PARTIAL | N/A | N/A | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | N/A | PARTIAL: scene lifetime invariant passes; DB dependency integrity can bypass validation |
| Gantt constraints/deadlines | PARTIAL | PARTIAL | N/A | N/A | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | N/A | PARTIAL: deterministic deadline service exists; at-risk terminology is confusing |
| Gantt Fit Project | PARTIAL | PARTIAL | N/A | N/A | FAIL | FAIL | FAIL | FAIL | FAIL | N/A | PARTIAL | N/A | FAIL: button calls `go_to_today()` rather than fitting project authority range |
| Calendar view | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PARTIAL: local-day/date parsing assumptions need full boundary tests |
| Focus view/timer | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PARTIAL: lifecycle tests exist, but actual state invariant still leaks |
| Daily Review/Analytics | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL: hardcoded colors and actual data contradictions can mislead |
| Settings typography/theme controls | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PARTIAL: cleanup listener test exists; many direct style fragments remain |
| Reminder dialogs/subsystem | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PARTIAL: lifecycle tests improved; full visual/accessibility state matrix incomplete |
| ModernButton | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PARTIAL: custom paint path exists; full variant/state matrix not proven |
| ModernComboBox | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PARTIAL: paint/QSS interaction needs visual witness |
| ModernCheckbox/ToggleSwitch | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PARTIAL: state visibility needs pixel evidence in both themes |
| SegmentedControl | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PARTIAL: minimum height exists; large-font fit not fully proven |
| Empty/state panels/cards | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PARTIAL | PASS | PARTIAL | PARTIAL | PARTIAL | PARTIAL: accessible-name coverage exists in places, visual matrix incomplete |

## Confirmed Rendering Defects

1. Task Dialog actual execution controls use fixed 85 px widths and can conflict with larger typography.
2. Gantt `Fit Project` does not fit the project; it navigates to today.
3. Gantt health uses color/text categories that can imply deadline at-risk semantics not produced by the deadline service.
4. Extensive hardcoded colors/styles remain across views and widgets, so light/dark and accessibility behavior is not fully token-governed.
5. Visual test coverage exists for selected Gantt and component cases, but the requested full state/DPI/font matrix is incomplete.

## Rendering Passes Noted

1. `GanttChartWidget` releases persistent scene-owned references before `scene.clear()`.
2. Gantt timescale range extraction includes planned, CPM, baseline, actual, constraints, and deadlines at the engine level.
3. Toolbar scroll wrapping reduces overlap risk for narrow windows, though it is not a complete DPI proof.
