## 1 Classification
todo_bird_phase2e_background_customization_fixed_human_witness_required

## 2 Existing image-background architecture
Todo Bird already had `BackgroundOverlayWidget` rendering a configurable image underlay from legacy keys: `background_mode`, `background_custom_image_path`, `background_fit_mode`, `background_opacity`, and `background_overlay_mode`. That image feature was preserved and bridged into the new model.

## 3 Canonical background architecture
The canonical path is now: global background settings -> optional view override -> `BackgroundService.effective_config()` -> `BackgroundOverlayWidget` -> active MainWindow view rendering. No per-view painting system was added.

## 4 Background modes
The four canonical modes are `theme_default`, `solid`, `image`, and `transparent`. Legacy `none` maps to Theme Default, and legacy `custom` maps to Image.

## 5 Global/per-view inheritance
Global settings live in `global_background_*`. Per-view overrides live in `view_background_overrides` by stable view id. Views inherit global background until an override is enabled; reset removes only the override.

## 6 Solid color implementation
Solid backgrounds persist normalized color values such as `#RRGGBB` or `#AARRGGBB`. Presets include Theme Surface, Graphite, Slate, Midnight, Navy, Indigo, Emerald Tint, Warm Sand, Soft Grey, and Pure White.

## 7 Image preservation
Existing managed image import remains through `MediaService.import_media(..., category="backgrounds")`. Image mode supports Fill, Fit, Stretch, Center, Tile, opacity, and image overlay mode. Missing/corrupt images safely fall back to Theme Default rendering.

## 8 Transparency implementation
Transparent mode paints only the background layer with controlled alpha. It does not apply `WA_TranslucentBackground` to buttons, text, editors, tables, cards, combo boxes, or dialogs. True desktop-through translucency was not enabled for Beta because the safe requirement is background-layer transparency.

## 9 Readability safeguards
Interactive surfaces remain semantic surfaces above the background. Gantt bars/text/grid, WBS tree surfaces, dashboard cards, dialogs, and controls are not globally made transparent.

## 10 Settings UX
Settings -> Appearance now exposes Apply Background To, current-view label, Background Mode, Solid Color presets/custom color, Image picker/fit/opacity/overlay, Transparent opacity, Reset This View to Global Background, and Reset All Backgrounds. Changes update the live overlay immediately.

## 11 Files changed
Primary files: `todo_bird_app/services/background_service.py`, `todo_bird_app/ui/background_overlay.py`, `todo_bird_app/settings/settings_manager.py`, `todo_bird_app/views/settings_view.py`, `todo_bird_app/views/main_window.py`, `todo_bird_app/controllers/navigation_controller.py`, and `todo_bird_app/tests/test_background_customization_system.py`.

## 12 Targeted tests
Passed: `test_background_customization_system.py` with 75 tests in 35.76s. Also passed legacy/background-adjacent checks: `test_ux_sellability_personalization_batch35.py` with 25 passed, `test_batch310g_personalization.py` with 18 passed, and `test_global_design_system_propagation.py` with 112 passed.

## 13 Full regression
Isolated full regression passed with one fresh Python process per test file: 104 files, 2148 passed, 0 failed, 0 errors, 0 skipped, 0 xfailed, 0 xpassed. Peak measured per-file RSS was 440704 KB.

## 14 Production DB hash
Production DB hash before and after remained unchanged: `0fadcb23e4b5361985d93643a122d1744dc00f0c3800fb1a3d5c955caafea05f  todo_bird_app/data/todo_bird.db`.

## 15 Human witness checklist
Human witness still required: verify Theme Default, Solid Color, Image, and Transparent backgrounds in the real app; verify Entire App vs Current View/Window behavior; verify Dashboard, Gantt, Projects/WBS, Calendar, Analytics, and Settings inheritance; verify Gantt Refresh remains visible; verify cards/dialogs/controls remain readable; verify existing image background still works.
