# TODO BIRD — FUTURE iOS & iPadOS DESIGN PORTABILITY GUIDANCE

## Objective
This document outlines the architectural and design portability guidelines for future native iOS 17+ and iPadOS 17+ frontends sharing the TODO BIRD core model, scheduling engine, and design language.

> [!NOTE]
> The current PySide6 desktop UI is intentionally **not** an iOS application. PySide6 desktop views will not run unmodified on iOS. Rather, the visual tokens, semantic interaction models, information hierarchies, and design systems established in this hardening phase are designed to transfer directly to SwiftUI / native Apple frameworks.

---

## 1. Portable Design Concepts (Directly Transferable to iOS/iPadOS)

| Concept | Desktop Implementation | iOS / iPadOS Equivalent (SwiftUI) |
| :--- | :--- | :--- |
| **Typography Hierarchy** | `TypographyRole`: Display, Page Title, Section Title, Card Title, Body, Secondary Body, Metadata, Caption | SwiftUI Dynamic Type styles: `.largeTitle`, `.title`, `.title2`, `.headline`, `.body`, `.subheadline`, `.footnote`, `.caption` |
| **Spacing System** | Canonical 8-step scale: 4, 8, 12, 16, 20, 24, 32, 40 px (`SPACING_SCALE`) | Standard SwiftUI layout tokens / padding multiples (4pt grid: 4, 8, 12, 16, 20, 24, 32, 40) |
| **Corner Radii** | `RADIUS_SM=6`, `RADIUS_MD=10`, `RADIUS_LG=14`, `RADIUS_XL=20`, `RADIUS_FULL=9999` | RoundedRectangle cornerRadius: 6pt, 10pt, 14pt, 20pt, capsule |
| **Semantic Colors** | `surface_base`, `surface_raised`, `text_primary`, `text_secondary`, `accent`, `success`, `warning`, `danger`, `critical_path` | Semantic Asset Catalog / `Color(.systemBackground)`, `Color(.secondarySystemBackground)`, `Color.accentColor` |
| **Theme System** | Light, Dark, OLED Midnight Black, Warm Paper / Sepia, Nord / Slate Blue | iOS Light/Dark mode + custom color schemes via `.preferredColorScheme()` or Environment overrides |
| **Information Hierarchy** | Title → Priority Badge → Status Chip → Project Indicator → Dates / Effort | Primary list cell layout with trailing accessory indicators |
| **Reminder Semantics** | Periodic polling, nonblocking popover/card, Snooze intervals (15m, 1h, 3h, 1d), Complete, Dismiss | UNUserNotificationCenter local notifications + Notification Content Extension with actionable buttons |
| **Card & Surface Hierarchy** | Flat cards, subtle borders (1px @border), elevated cards on dark mode | Inset grouped list styles, card shapes with material blur (`.regularMaterial`, `.thinMaterial`) |
| **Execution State System** | Invariant-enforced task status: INBOX, PLANNED, IN_PROGRESS, COMPLETED, DELAYED, CANCELLED | Shared SQLite database or core logic engine via C++/Python bridge or Swift port |

---

## 2. Desktop-Specific Concepts vs. iOS Equivalents

| Desktop Interaction / Concept | Nature | iOS / iPadOS Equivalent |
| :--- | :--- | :--- |
| **Hover States** | Pointer-only cues, border highlight, background hover tint | Tap feedback, selection highlights, iPadOS pointer hover effects (`.hoverEffect()`) |
| **Right-Click Context Menus** | Desktop `customContextMenuRequested` | iOS Long-Press Context Menus (`.contextMenu { ... }`) |
| **Mouse Drag & Drop (WBS/Gantt)**| Pixel-level cursor dragging, resize handles | Long-press to drag list items (`.onMove`), pinch-to-zoom timeline on iPadOS |
| **Multi-Window Geometry** | `QMainWindow`, `QDialog.resize()`, `QSizeGrip` | Adaptive sheets (`.sheet(isPresented:)`), full-screen covers, NavigationSplitView (iPadOS) |
| **Splitters** | `QSplitter` with drag divider | `NavigationSplitView(sidebar:content:detail:)` on iPadOS, drill-down stack on iPhone |
| **System Tray & Autostart** | `QSystemTrayIcon`, desktop autostart entry (`~/.config/autostart`) | Background Tasks framework, WidgetKit complications, Live Activities |
| **Desktop Companion** | Floating desktop widget (`DesktopCompanionWidget`) | Lock Screen / Home Screen Widgets (WidgetKit) and Dynamic Island / Live Activity |

---

## 3. Touch Target Sizing & Safe Areas

- **Desktop Density**: Desktop controls comfortably use 28–34px heights with tight horizontal spacing.
- **Future Mobile Target**: iOS human interface guidelines recommend minimum 44×44 pt touch targets.
- **Guidance for Core Logic**: Presentation models and data structures must remain decoupled from widget pixel heights so mobile view shells can bind the same underlying entity models to 44pt touch rows without refactoring backend services.

---

## 4. Summary Architecture
```
+--------------------------------------------------------------------+
|                         Shared Core Logic                          |
|  - SQLite Database & Schema Authority                              |
|  - CPM Scheduling Math & Dependency Engine                         |
|  - Working Week & Calendar Calculation                             |
|  - Execution State Invariant Hardening                             |
|  - Reminder Policy Engine & Snooze Math                            |
|  - Centralized Design Tokens (Spacing, Radii, Semantic Colors)     |
+---------------------------------+----------------------------------+
                                  |
         +------------------------+------------------------+
         |                                                 |
+--------v-----------------------+       +-----------------v----------------+
|    Desktop Shell (PySide6)     |       |   Future iOS Shell (SwiftUI)     |
| - Ubuntu 24.04/26.04 & Windows |       | - iOS 17+ / iPadOS 17+           |
| - HeaderBar & Sidebar Nav      |       | - TabView & NavigationSplitView  |
| - Gantt QGraphicsView Scene    |       | - Canvas / Swift Charts Timeline |
| - Nonmodal QDialog Reminders   |       | - Actionable Local Notifications |
| - Mouse / Keyboard Focus Rings |       | - Dynamic Type & Haptic Engine   |
+--------------------------------+       +----------------------------------+
```
