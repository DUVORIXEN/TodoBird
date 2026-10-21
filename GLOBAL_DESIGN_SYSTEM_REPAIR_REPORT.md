## 1 Classification
todo_bird_phase2e_global_design_system_fixed_human_witness_required

## 2 Global visual authority map
Canonical authority is now `AppearanceService` plus `ThemeController`: user settings are read once into `AppearanceSettings`, converted into semantic design tokens, applied to `QApplication` palette/font/QSS, then propagated through `_GLOBAL_EVENT_BUS.appearance_changed`. Shared components consume semantic tokens and density metrics. Local overrides remain limited to explicit per-view choices such as Gantt light/dark/color preferences and WBS personalization. Legacy hardcoded/QPainter/QSS paths were moved to semantic tokens where they affected global theme, accent, typography, density, or button style.

## 3 Competing authorities found
The app previously had parallel visual authorities: theme QSS, palette, typography service, local widget stylesheets, custom paint colors, ModernButton class globals, Gantt-local button mode, settings-only values, and stale fixed-size tests. Test lifecycle also had competing Qt teardown owners: shared pytest cleanup and local test cleanup both closed top-level widgets, while the old shared cleanup forced global deferred deletes.

## 4 Font propagation root cause
Font changes were persisted but not applied through one live path. Some views listened only to typography areas, some custom widgets kept fixed geometry, and `QApplication` font changes did not force existing painted controls to recalculate size or repaint.

## 5 Heading/text color root cause
Heading and body colors were split between QSS, local stylesheets, custom card styles, and custom paint code. Several paths used fixed black/gray values instead of semantic `TEXT_PRIMARY`, `TEXT_SECONDARY`, or `TEXT_MUTED`.

## 6 Button oversizing root cause
Buttons and controls mixed fixed heights such as 34/40 px with global QSS padding. That ignored font metrics and density, so font or density changes could create oversized controls or stale tests that enforced oversized geometry.

## 7 Color-scheme propagation root cause
Accent/color scheme values were not canonical. Some code wrote raw accent colors, some read `color_scheme`, some read `accent_scheme`, and custom paint controls ignored palette or token updates.

## 8 Button-style propagation root cause
`ModernButton.set_global_design_mode` changed a class value but did not refresh existing instances. Gantt also had its own button-style path, so visible buttons could remain on the old style until recreated.

## 9 Gantt Refresh visibility root cause
The Gantt toolbar had too many same-priority controls in one row. Inside the scroll area, `widgetResizable=True` plus preferred-width controls allowed the Refresh button to collapse to width 0 in the real layout. After repair the live geometry witness showed Refresh visible with x=654, y=21, width=80, height=32, viewport width=812, toolbar width=1300.

## 10 New canonical design-system architecture
User Settings -> `AppearanceService.read()` -> `AppearanceSettings` -> semantic tokens -> `ThemeController.apply_theme()` -> `QApplication` palette/font/QSS -> global appearance event -> shared components and views. Theme, accent scheme, font family, font size, font weight, density, and button style now share this path.

## 11 Typography result
Application font family, size, and weight now update live through `QApplication.setFont`, typography notification, appearance event propagation, and component geometry refresh. MainWindow, GanttView, SettingsView, TaskDialog, dashboard cards, buttons, combo boxes, search fields, checkboxes, toggles, and segmented controls participate.

## 12 Color/theme result
Semantic roles now cover application background, surfaces, borders, text roles, accent states, status colors, focus ring, and Gantt roles. Professional Blue, Indigo, Emerald, Amber, Rose, Graphite/Neutral, and existing compatible schemes resolve to live tokens.

## 13 Button style result
ModernButton instances update in place for flat, 3d_raised, executive_soft, neumorphic, and glow styles. Button density and style changes refresh existing instances without requiring view recreation.

## 14 Gantt toolbar result
The primary row now keeps Project, Compare Current Against, Fit Project, Refresh, Zoom/Scale, Today, Timeline, Appearance, and Layers visible with measured widths. Secondary visual settings moved into Appearance/View Options, navigation into Timeline, and layer toggles into Layers.

## 15 Files changed
Changed areas: `todo_bird_app/services/appearance_service.py`, `settings/settings_manager.py`, `controllers/theme_controller.py`, `controllers/task_controller.py`, `views/base_view.py`, `views/main_window.py`, `views/gantt_view.py`, `views/dashboard_view.py`, `views/settings_view.py`, `views/wbs_project_view.py`, `ui/components/modern_button.py`, `ui/components/modern_combobox.py`, `ui/components/modern_checkbox.py`, `ui/components/toggle_switch.py`, `ui/components/segmented_control.py`, `ui/components/search_field.py`, `themes/dark.qss`, `themes/light.qss`, `widgets/modern_card.py`, `widgets/dashboard_charts.py`, `widgets/sidebar.py`, `tests/conftest.py`, `tests/test_global_design_system_propagation.py`, and stale geometry/theme expectation tests.

## 16 Real-window rendering tests
`todo_bird_app/tests/test_global_design_system_propagation.py` contains 112 tests, including real-window rendering coverage for MainWindow, GanttView in actual MainWindow layout, SettingsView, and TaskDialog. It passed after the Qt teardown fix: 112 passed in 23.64s focused, and 112 passed in 26.13s inside the isolated full regression.

## 17 Targeted test results
Focused recovery passed for the global design system, interactive control visibility, typography geometry, responsive dashboard charts, schedule baseline variance, cross-view consistency, Gantt batch2, Phase 1B control language, reverse typography scaling, accessibility foundation, responsive toolbar/workspace, suite smoke, and UX personalization. The IDE/test crash root cause was fixed by removing forced global deferred-delete flushing and eliminating duplicate local top-level-widget cleanup ownership.

## 18 Exact full regression
Command: `python3 /tmp/todo_bird_isolated_pytest_runner.py /home/athidhi_onlg/todo_bird`. Result: 103 test files, 2073 passed, 0 failed, 0 errors, 0 skipped, 0 xfailed, 0 xpassed, 0 failing files. Peak measured per-file max RSS was 437628 KB. Each test file ran in a fresh Python process with `QT_QPA_PLATFORM=offscreen`, `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`, `PYTHONDONTWRITEBYTECODE=1`, faulthandler, and a 120s per-file timeout.

## 19 Production DB hash
Production DB witness hash before targeted closure and after full isolated regression matched: `0fadcb23e4b5361985d93643a122d1744dc00f0c3800fb1a3d5c955caafea05f  todo_bird_app/data/todo_bird.db`.

## 20 Human witness checklist
Human witness still required: verify Gantt Refresh is visible in the real IDE/app window; Theme, Color Scheme/Accent, Font Family, Font Size, Font Weight, Density, and Button Style update live without restart/reopen/double-toggle; Dashboard, WBS, Gantt, Settings, and Task Dialog share typography/colors; buttons are no longer oversized; color schemes are visibly distinct and professional.
