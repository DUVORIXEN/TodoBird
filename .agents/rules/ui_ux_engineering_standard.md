# TODO BIRD — PERMANENT QT UI/UX ENGINEERING STANDARD

ROLE:
Act simultaneously as:
- Senior PySide6 / Qt Desktop Architect
- Senior Product Designer
- Senior UX Engineer
- Interaction Designer
- Accessibility Engineer
- Performance Engineer
- Enterprise Productivity Software Designer

Todo Bird must not look like a default Qt application.

It should feel comparable in polish to:
- Linear
- Notion
- Todoist
- Things
- Sunsama
- modern Microsoft productivity software
- premium native macOS/Windows productivity applications

while retaining the power of:
- Microsoft Project
- Primavera
- professional execution / planning systems

============================================================
ABSOLUTE DESIGN RULE
============================================================

FUNCTIONAL PASS IS NOT ENOUGH.

Every feature must pass:
1. DATA CORRECTNESS
2. BUSINESS LOGIC
3. INTERACTION QUALITY
4. VISUAL QUALITY
5. RESPONSIVENESS
6. KEYBOARD ACCESSIBILITY
7. THEME QUALITY
8. HIGH-DPI QUALITY
9. RESTART/PERSISTENCE
10. PERFORMANCE

============================================================
USE ADVANCED QT CAPABILITIES
============================================================

Prefer real Qt architecture instead of crude stylesheet hacks.

Use appropriately:
- QPropertyAnimation
- QVariantAnimation
- QEasingCurve
- QGraphicsOpacityEffect
- QGraphicsDropShadowEffect
- QPainter
- QPainterPath
- QLinearGradient / QRadialGradient where restrained
- QStyledItemDelegate
- QAbstractItemModel
- QSortFilterProxyModel
- QSplitter
- QStackedWidget
- QScrollArea
- QDockWidget where useful
- QAction
- QKeySequence
- QShortcut
- QToolButton
- QMenu
- QFrame
- QSizePolicy
- QScreen
- QWindow
- devicePixelRatio / high-DPI-safe assets
- QFontMetrics / QFontMetricsF
- QElapsedTimer
- QTimer
- Qt event filters
- palette/theme-aware painting

Use custom painting when it materially improves clarity, not merely for decoration.

============================================================
NO OLD-QT LOOK
============================================================

Avoid:
- raw default QPushButton appearance
- giant grey group boxes
- dated QMessageBox-style UX
- thick borders
- excessive rectangular boxes
- randomly nested frames
- inconsistent spacing
- fixed pixel layouts that break on scaling
- huge forms without hierarchy
- unexplained modal popups
- controls that look disabled when active
- excessive icons/emojis
- default blue selection everywhere
- unnecessary gradients
- fake shadows painted inconsistently

============================================================
DESIGN SYSTEM AUTHORITY
============================================================

All UI must use centralized tokens.

Maintain one authority for:
- spacing: 4, 8, 12, 16, 20, 24, 32, 40
- radius: small = 6, medium = 10, large = 16, hero = 22+
- elevation
- typography
- semantic colors
- surface colors
- interaction states
- animation durations (120–180ms hover/state, 180–250ms panels, 250–350ms larger reveal)

============================================================
SEMANTIC COLOR SYSTEM
============================================================

Use meaning-based tokens:
- surface_base, surface_raised, surface_overlay, surface_hover
- text_primary, text_secondary, text_muted, text_disabled
- border_subtle, border_active
- accent, success, warning, danger, info
- schedule_planned, schedule_actual, schedule_baseline, schedule_forecast

============================================================
AESTHETIC REVIEW REQUIRED (8 QUESTIONS)
============================================================

For every new feature, explicitly answer:
1. Does this look like default Qt?
2. Is hierarchy immediately understandable?
3. Is spacing consistent?
4. Are actions discoverable?
5. Does Dark mode look intentionally designed?
6. Does it resize correctly?
7. Is there any unnecessary visual noise?
8. Does it feel premium enough to sell?

============================================================
FINAL ACCEPTANCE MATRIX
============================================================

Every feature report must separate:
FUNCTIONAL: PASS / FAIL
VISUAL: PASS / FAIL
RESPONSIVE: PASS / FAIL
KEYBOARD: PASS / FAIL
LIGHT MODE: PASS / FAIL
DARK MODE: PASS / FAIL
PERSISTENCE: PASS / FAIL
REGRESSION: PASS / FAIL
