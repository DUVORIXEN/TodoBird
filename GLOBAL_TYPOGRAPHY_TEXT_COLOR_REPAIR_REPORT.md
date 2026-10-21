# Todo Bird Phase 2E Global Typography And Text Color Repair Report

## 1 Classification
todo_bird_phase2e_global_typography_text_color_fixed_human_witness_required

## 2 Typography authority map
`SettingsManager` stores `ui_font_family`, `ui_font_size`, `ui_font_weight`, `ui_density`, and `button_design_mode`. `AppearanceService.read()` resolves them into one `AppearanceSettings` object and `AppearanceSettings.font()` creates the canonical application font. `ThemeController.apply_theme()` applies that font to `QApplication`, stamps the live app properties, notifies `TypographyService`, and then propagates appearance to existing widgets.

## 3 Text-color authority map
`AppearanceService.TEXT_COLOR_ROLES` now declares the required semantic roles: primary, secondary, muted, disabled, headings, status-on-color text, links, placeholders, table headers, section headers, and sidebar states. `qpalette_from_tokens()`, QSS token substitution, widget palette specialization, and custom paint components all read from the same resolved token dictionary.

## 4 Hardcoded dark/black defects found
Dark-mode failures came from scattered fixed or invalid text declarations such as black/dark label colors and `color: inherit` in Qt QSS. The sanitizer now replaces unreadable fixed label/input text colors in dark mode, and the task dialog heading no longer declares `color: inherit`.

## 5 Hardcoded light/white defects found
Light-mode failures came from text-on-status roles using white text on fills that were too bright for safe contrast, plus disabled text that was too pale on white. `DANGER`, `SUCCESS`, `TEXT_DISABLED`, and dark-mode `LINK` were adjusted for contrast while schedule-specific `GANTT_ACTUAL` remains `#10B981`.

## 6 QSS defects
Both `dark.qss` and `light.qss` now provide semantic selectors for labels, group boxes, check boxes, radio buttons, headings, secondary text, table headers, item views, menus, tabs, sidebars, inputs, disabled inputs, primary buttons, and destructive buttons. Destructive buttons now use `@DANGER`, `@TEXT_ON_DANGER`, and `@DANGER_HOVER` rather than literal red/white assumptions.

## 7 Palette defects
The global palette now sets `WindowText`, `Text`, `ButtonText`, `ToolTipText`, `PlaceholderText`, `Link`, `LinkVisited`, `BrightText`, disabled text roles, highlight, and highlighted text. Per-widget application also specializes `WindowText`, `Text`, and `ButtonText` from the widget semantic role so heading labels carry heading color in the palette, not only in QSS.

## 8 Custom-paint defects
`ModernButton` and `ModernComboBox` now inherit current app theme/accent when constructed after a live theme change and stamp `todoBirdTheme`/`todoBirdAccent` for diagnostics. `ModernButton` danger rendering now uses semantic `DANGER` and `TEXT_ON_DANGER`.

## 9 Heading semantic architecture
Heading widgets are detected from `todoBirdTextRole`, `heading=true`, object names such as `HeaderTitle`, and `TypographyService.set_relative_font_role(delta_pt >= 4)`. They resolve to `HEADING_PRIMARY`; secondary heading roles resolve to `HEADING_SECONDARY` when assigned by typography role metadata.

## 10 Body-text architecture
Default body text resolves to `TEXT_PRIMARY`. Secondary, muted, placeholder, disabled, table header, section header, sidebar, link, and text-on-status roles are explicit tokens rather than ad hoc color choices in individual widgets.

## 11 Font family propagation
Font family remains centralized in `AppearanceSettings.font()` and `QApplication.setFont()`. Live app properties also expose `todoBirdFontFamily` so late-created custom controls can inherit the current appearance state.

## 12 Font size/geometry behavior
Font size remains bounded by the existing 8-20 pt authority. `_ensure_font_safe_control_geometry()` gives Qt buttons, line edits, combo boxes, date/time edits, spin boxes, and text edits a font-aware minimum height so larger fonts do not clip.

## 13 Font weight propagation
`AppearanceSettings.font()` maps normal, medium, semibold, and bold through `font_weight_to_qt()`. `TypographyService.set_relative_font_role()` preserves per-widget relative weights while also marking heading text roles for color resolution.

## 14 Light mode result
Light semantic contrast probe: `TEXT_DISABLED #64748B` on `#FFFFFF` = 4.759; `TEXT_ON_DANGER #FFFFFF` on `#DC2626` = 4.829; `TEXT_ON_SUCCESS #FFFFFF` on `#047857` = 5.484; `LINK #2563EB` on `#FFFFFF` = 5.169.

## 15 Dark mode result
Dark semantic contrast probe: `TEXT_DISABLED #8792A6` on `#242538` = 4.791; `TEXT_ON_DANGER #FFFFFF` on `#DC2626` = 4.829; `TEXT_ON_SUCCESS #FFFFFF` on `#047857` = 5.484; `LINK #7EA6FF` on `#242538` = 6.290.

## 16 Files changed
`todo_bird_app/services/appearance_service.py`; `todo_bird_app/controllers/theme_controller.py`; `todo_bird_app/services/typography_service.py`; `todo_bird_app/themes/dark.qss`; `todo_bird_app/themes/light.qss`; `todo_bird_app/themes/tokens.py`; `todo_bird_app/ui/design_tokens.py`; `todo_bird_app/ui/components/modern_button.py`; `todo_bird_app/ui/components/modern_combobox.py`; `todo_bird_app/widgets/task_dialog.py`; `todo_bird_app/tests/test_global_typography_and_text_color_authority.py`; `todo_bird_app/tests/test_batch37_defects.py`; `tools/run_isolated_pytest.py`.

## 17 Real-window rendering evidence
`test_global_typography_and_text_color_authority.py` renders real `MainWindow`, settings view, task dialog, raw Qt table, `ModernButton`, and `ModernComboBox` widgets with `QWidget.render()` under offscreen Qt. The real main-window light-to-dark switch produced image deltas and confirmed `HeaderTitle` palette color becomes `#FFFFFF` in dark mode.

## 18 Exact targeted + full regression
Targeted: `test_global_typography_and_text_color_authority.py` collected 136 tests and passed 136/136 in 69.31s, max RSS 351096 KB. Full isolated regression: 106/106 test files passed, 2298 passed, 0 failed, 0 errors, 0 skipped, peak per-file RSS 560344 KB, elapsed 347.194s. The reusable anti-crash runner is `tools/run_isolated_pytest.py`; it writes durable summaries to `build/test_reports/isolated_pytest_summary.json`. Runner smoke after resume: 1/1 file, 2 passed, peak RSS 128984 KB.

## 19 Production DB hash
Before and after hash for `/home/athidhi_onlg/todo_bird/todo_bird_app/data/todo_bird.db`: `0fadcb23e4b5361985d93643a122d1744dc00f0c3800fb1a3d5c955caafea05f`.

## 20 Human witness steps
Open Todo Bird, switch to dark mode, and inspect header, sidebar, Settings, task dialog, tables/tree views, Gantt, Calendar, and custom controls. Change font family, size, and weight while Settings remains open. Confirm headings, labels, placeholders, disabled controls, selected sidebar text, status buttons, and custom-painted controls update live without restart and without black/dark text remaining on dark surfaces.
