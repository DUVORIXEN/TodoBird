# Changelog

## 1.0.0 — Public Release (2026-09-26)

First public release of Todo Bird. This build follows the 0.9.0 beta series,
which hardens the scheduling engine (CPM, constraints, calendars, baselines),
the Gantt/WBS surfaces, reminder policy, and cross-platform platform adapters
(Windows 10/11, macOS 13+, Ubuntu 22.04+; ChromeOS via the Linux/Crostini
runtime).

### Task windows

- New/Edit Task dialog rebuilt for clarity and space: larger hero title field,
  flat-card group sections, no horizontal scrollbars at the default window
  size (the Schedule tab previously clipped constraint, deadline and workload
  controls).
- Sub-task (and nested sub-sub-task) editing reworked: the breakdown tree now
  stretches the name column instead of truncating titles, shows an empty-state
  hint, and supports keyboard-first entry — Enter adds a subtask,
  Ctrl+Enter nests under the selection, Delete removes checked rows, F2 opens
  the detail editor.
- Power-user shortcuts: Ctrl+S / Ctrl+Enter save, Ctrl+1–4 switch tabs, and
  Save is the dialog's default button.
- The Blocker/Delay panel and the read-only Baseline row now appear only when
  they carry information.
- Priority, status, and pin-color pickers use painted color swatches; pinned
  sub-tasks are marked with a widely-supported glyph.
- Dates use one consistent ISO format across the dialog, the standalone
  sub-task dialog, and the quick preview editor.

### Fixed on Windows (native build)

- Checkbox tick marks were invisible on Windows: the theme injects the
  checkmark SVG path into the stylesheet, and on Windows that path contained
  backslashes, which QSS treats as escape sequences — the `:checked` rule
  failed to parse (Qt logged "Could not parse application stylesheet") and
  the tick image never loaded. Paths are now POSIX-normalized and quoted, so
  the rule parses on every platform and drive/path combinations containing
  spaces (e.g. `C:\Program Files\...`) work too.
- The Windows packaging spec now bundles the QtSvg image-format plugin
  (required to render the SVG tick at all) and disables UPX, which is known
  to corrupt Qt DLLs so plugins fail to load silently.
- Regression tests simulate Windows paths and assert the stylesheet parses
  without warnings and that a checked box paints its tick
  (`tests/test_windows_stylesheet_paths.py`).

### Cross-platform UI rendering

- Removed color-emoji from all window chrome (navigation, header bar, task
  cards, dashboard, settings, dialogs, command palette) in favor of painted
  vector icons via the central IconService. Emoji glyphs rendered as boxes on
  systems without a color-emoji font (common on minimal Linux installs);
  chrome is now font-independent everywhere.
- Added vector glyphs (home, inbox, star, target, calendar, check-circle,
  chart, chat, globe, bell, clock, sun, moon) to the icon service, and the
  sidebar brand mark now uses the real application asset.
- Translation packs migrated to emoji-free source keys (World Clock, Mode,
  Light, Dark, Support Todo Bird) across all ten languages.

### Performance

- Dashboard rebuilds are coalesced: bursts of data-change signals now trigger
  one deferred refresh instead of one full dashboard rebuild per signal, and
  the redundant second build at startup was removed.
- Gantt health chips, dependency tree columns, and the work-effort editor
  layout were adjusted to eliminate horizontal overflow and forced scrolling
  at default window sizes.

### Housekeeping

- Version promoted to 1.0.0 (Public Release); Windows application ID updated
  accordingly.
- The legacy `font_density` hook is documented as superseded by the
  appearance engine's `ui_density` setting.

### Known limitations

- Android and iOS are not target platforms for the Qt 6 / PySide6 desktop
  application; a mobile companion would be a separate native project reusing
  the planning core.
- Country flag icons in the World Clock selector use regional-indicator
  emoji and require a color-emoji font on Linux.
- Minor: dialog chrome tooltips and hints are English-only; full interface
  translation covers navigation, header, and menus.
