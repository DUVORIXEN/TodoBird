# Todo Bird Phase 2E Dashboard Light-Mode Popup Theme Repair Report

Date: 2026-09-03

Final classification:

`todo_bird_phase2e_live_ui_runtime_s1_failures_fixed_human_witness_required`

## Scope

This repair is limited to Dashboard hover-triggered tooltip/popup readability and Qt theme-switch stability. No scheduling, CPM, WBS, dependency, database schema, or task-save logic was changed.

## Defect

Dashboard chart hover tooltips could display with stale/dark native tooltip styling after Light mode was active, making the popup unreadable. During focused runtime testing, a second stability defect was reproduced: a closed `MainWindow` that had completed shutdown but remained as a hidden Qt top-level could crash the next `QApplication.setStyleSheet(...)` call in the same QApplication session.

## Root Cause

Dashboard chart hover surfaces called `QToolTip.showText(...)` directly from the chart base and relied on global/native tooltip state. That state can be stale during live Light/Dark changes and can outlive the dashboard widget.

The PySide6 crash came from a global stylesheet swap while Qt still retained hidden shutdown-complete top-level widgets, and sometimes an internal tooltip label. This is the same class of defect that makes repeated IDE/test sessions unstable even when individual tests pass.

## Dashboard Hover Inventory

| Surface | Control/Card | Popup Type | Previous Authority | New Authority |
| --- | --- | --- | --- | --- |
| Workload and Capacity | `capacity_stacked_bar` / `AdvancedCapacityChart` | Native `QToolTip` | Direct text + global/native palette | `dashboard_tooltip_theme`, `dashboard_tooltip_html`, `QToolTip` palette sync |
| Task Status Breakdown | `status_donut` / `AdvancedStatusChart` | Native `QToolTip` | Direct text + global/native palette | Same shared dashboard tooltip authority |
| Execution Activity | `weekly_chart` / `AdvancedWeeklyActivityChart` | Native `QToolTip` | Direct text + global/native palette | Same shared dashboard tooltip authority |

Global `QToolTip` QSS remains tokenized in both `light.qss` and `dark.qss` with `@SURFACE_2`, `@TEXT_PRIMARY`, and `@BORDER_STRONG`.

## Repair

- Added `DashboardTooltipTheme` and dashboard tooltip resolver helpers in `todo_bird_app/widgets/dashboard_charts.py`.
- Dashboard tooltip colors now resolve from the current widget/app semantic theme at hover time:
  - Light: `SURFACE_2 #eef2f7`, `TEXT_PRIMARY #111827`, `TEXT_SECONDARY #475569`, `BORDER_STRONG #94a3b8`.
  - Dark: `SURFACE_2 #2a2b3d`, `TEXT_PRIMARY #f4f7fb`, `TEXT_SECONDARY #b7c0d1`, `BORDER_STRONG #647084`.
- Mouse and keyboard chart inspection now route through one `_show_dashboard_tooltip(...)` path.
- `ThemeController.apply_theme(...)` now clears active native tooltip widgets and deletes hidden shutdown-complete top-level windows before the global QSS swap.
- `MainWindow.closeEvent(...)` now hides native tooltips, disconnects owned theme signal hooks, and clears the QApplication theme-controller reference when it owns it.

## Verification

- `python3 -m py_compile todo_bird_app/controllers/theme_controller.py todo_bird_app/views/main_window.py todo_bird_app/widgets/dashboard_charts.py todo_bird_app/tests/test_dashboard_light_popup_theme_authority.py` passed.
- `QT_QPA_PLATFORM=offscreen python3 -m pytest todo_bird_app/tests/test_dashboard_light_popup_theme_authority.py -q` passed: 28 passed.
- `QT_QPA_PLATFORM=offscreen python3 -m pytest todo_bird_app/tests/test_dashboard_light_popup_theme_authority.py todo_bird_app/tests/test_popup_theme_authority.py todo_bird_app/tests/test_phase1f722_dashboard_chart_interaction.py todo_bird_app/tests/test_shutdown_lifecycle.py -q` passed: 94 passed.
- `QT_QPA_PLATFORM=offscreen python3 tools/run_isolated_pytest.py` passed: 127/127 files, 3028 passed, 0 failed, 0 errors, peak RSS 547688 KB, elapsed 302.66s.

## Production DB Safety

Production DB hash before full isolated run:

`c472bda5ad40392be808ca07bb607e6728e1b0d72faa2d5ae8d5f0a402835b29`

Production DB hash after full isolated run:

`c472bda5ad40392be808ca07bb607e6728e1b0d72faa2d5ae8d5f0a402835b29`

No production database write, schema change, or SQLite production connection was introduced.

## Human Witness Required

Manual live desktop witness is still required:

1. Open Todo Bird.
2. Switch to Light mode.
3. Open Dashboard.
4. Hover Workload and Capacity, Task Status Breakdown, and Execution Activity chart elements.
5. Confirm each popup has light background, dark readable text, visible border, and no stale dark-mode background.
6. Switch Light to Dark and Dark to Light while Dashboard exists, then repeat hover checks.

Beta Ready, Human Accepted, and Phase 2F are not declared by this report.

## 2026-09-03 Reopened S1 Addendum

The human-visible Dashboard failure was traced deeper than the earlier chart hit-region helper. The actual live path is ordinary Qt widget tooltip handling:

`DashboardView -> QWidget.setToolTip(...) -> QEvent.ToolTip -> QTipLabel/qtooltip_label`

The previous repair styled only the custom chart-region hover helper. The reopened fix now intercepts the native `QEvent.ToolTip` path in `AnimatedDashboardChart.event(...)` and installs `DashboardTooltipEventFilter` on non-chart dashboard tooltip owners such as the range combo.

Runtime proof:

- Before repair: `QTipLabel/qtooltip_label`, base RGB `(17, 24, 39)`, text RGB `(17, 24, 39)`.
- After repair: `QTipLabel/qtooltip_label`, base RGB `(238, 242, 247)`, text RGB `(17, 24, 39)`.

Current focused S1 validation:

- `test_phase2e_s1_live_runtime_forensics.py`: 43 passed.
- Tail isolated regression files 88-128: 41/41 passed, 1188 passed, 0 failed, 0 errors.

Dashboard automated gate is closed. Human desktop witness remains required.
