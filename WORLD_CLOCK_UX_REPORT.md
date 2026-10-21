# TODO BIRD — GLOBAL WORLD CLOCK UX REPORT
**Component:** Global World Clock System & Timezone Authority
**Date:** 2026-09-02
**Status:** IMPLEMENTED & VERIFIED

---

## 1. Executive Summary

In response to human user request, an enterprise-grade, offline-first **Global World Clock System** has been introduced across Todo Bird. It enables users to track time across any country or city worldwide with **Analog** and **Digital** displays, **5 distinct themes**, an interactive **Cross-Timezone Meeting Scrubber**, and **seamless global accessibility** across the entire application.

The entire system operates 100% offline using Python's native `zoneinfo` and `pytz` databases with zero external network requests. All existing scheduling math, CPM algorithms, working calendars, actual authority, baseline governance, and production database safety remain completely untouched.

---

## 2. Architecture & Data Flow

```
                               ┌─────────────────────────────┐
                               │     SettingsManager         │
                               │  • world_clocks (list)      │
                               │  • world_clock_type         │
                               │  • world_clock_theme        │
                               │  • world_clock_24h          │
                               └──────────────┬──────────────┘
                                              │
                                              ▼
                               ┌─────────────────────────────┐
                               │     WorldClockService       │
                               │  • 249 ISO countries        │
                               │  • 498+ IANA timezones      │
                               │  • Relative offsets (±Xh)   │
                               │  • Solar day/night phases   │
                               └──────────────┬──────────────┘
                                              │
                   ┌──────────────────────────┼──────────────────────────┐
                   ▼                          ▼                          ▼
      ┌────────────────────────┐ ┌────────────────────────┐ ┌────────────────────────┐
      │   AnalogClockWidget    │ │   DigitalClockWidget   │ │    WorldClockCard      │
      │  • QPainter rendering  │ │  • Big readable font   │ │  • City & country flag │
      │  • Smooth hour/min/sec │ │  • Date & offset badge │ │  • Pinning / Delete    │
      │  • 5 Theme Renderers   │ │  • 12h / 24h toggle    │ │  • Offset & Day badge  │
      └────────────────────────┘ └────────────────────────┘ └────────────────────────┘
                   │                          │                          │
                   └──────────────────────────┼──────────────────────────┘
                                              │
                   ┌──────────────────────────┴──────────────────────────┐
                   ▼                                                     ▼
      ┌────────────────────────┐                            ┌────────────────────────┐
      │   WorldClockPopover    │                            │     WorldClockView     │
      │  • Floating dialog     │                            │  • Dedicated full view │
      │  • HeaderBar "🌐" btn  │                            │  • Multi-clock grid    │
      │  • Shortcut Ctrl+Alt+W │                            │  • Timezone Scrubber   │
      │  • Command Palette     │                            │  • Meeting overlap tool│
      └────────────────────────┘                            └────────────────────────┘
```

---

## 3. Clock Types

1. **Analog Clock (`AnalogClockWidget`)**:
   - Custom `QPainter` canvas with `Antialiasing` and `TextAntialiasing`.
   - Distinct hour, minute, and stepping second hands.
   - Dial indices: ticks, Roman numerals, or block markers depending on theme.
   - Dynamic celestial icon (☀️ Sun / 🌙 Moon / 🌅 Twilight).
   - Center pivot cap and counterweight second hand.
2. **Digital Clock (`DigitalClockWidget`)**:
   - Large, high-legibility digital typography.
   - 12-hour format (with AM/PM badge) and 24-hour format toggles.
   - Date badge (`Wed, Sep 02`) and Timezone abbreviation + UTC offset (`JST • UTC+09:00`).
   - Relative difference badge (`+3.5h ahead`, `9.5h behind`, `Same time`).

---

## 4. Five Curated Visual Themes

| Theme | Aesthetic Description | Dial Face Styling | Hands & Indicators |
| :--- | :--- | :--- | :--- |
| **1. Modern Minimal** | Clean, borderless contemporary slate | Soft matte surface (`#1E1E2E` / `#FFFFFF`), thin 1px border | Sleek tapered slate hands, vibrant accent-colored second hand |
| **2. Classic Luxury** | Executive chronometer / haute horlogerie | Deep navy/charcoal sunray face, double gold bezel, inner railroad track | Polished gold faceted dauphine hands, Roman numerals (XII, III, VI, IX) |
| **3. Cyberpunk HUD** | Futuristic high-contrast sci-fi HUD | Obsidian dark background (`#0A0A14`), concentric neon tech grid rings | Glowing wireframe magenta hour hand, cyan minute hand, laser yellow second hand |
| **4. Retro Matrix LCD** | Vintage CRT / pixel matrix phosphor LCD | Dark olive green/amber LCD matrix (`#0F1A12`), pixelated dot ring | Phosphor green (`#4ADE80`) blocky stepped hands, square pixel center cap |
| **5. Solar Day-Night** | Astronomical dynamic celestial gradient | Radial sky gradient changing automatically: sunny day, crimson dawn/dusk, starry night | Semi-translucent hands revealing celestial sky, miniature sun/moon icon |

---

## 5. Country & City Selection Authority

- **Full Global Coverage**: Covers all **249 ISO countries** and **498+ IANA timezones**.
- **Searchable Country & City Picker (`AddWorldClockDialog`)**:
  - Instant live filter as user types (e.g. "Tokyo", "London", "Germany", "India", "Brazil").
  - Quick-add preset chips: London, New York, San Francisco, Tokyo, Paris, Berlin, New Delhi, Singapore, Dubai, Sydney.
  - Generates authentic Unicode country flag emojis (`🇺🇸`, `🇬🇧`, `🇯🇵`, `🇮🇳`, `🇦🇪`, etc.) using ISO regional indicator codes.
  - Live preview card displaying current local time, offset, and solar state before adding.
  - Custom label support (e.g. "Dev Team HQ", "Client Branch", "Family").

---

## 6. Global Application Integration

The World Clock is accessible everywhere in Todo Bird:
1. **Top HeaderBar**:
   - Prominent `🌐 World Clock` button in `HeaderBarWidget` with cursor hand and tooltip.
   - One-click opens the floating `WorldClockPopover`.
2. **Global Keyboard Shortcut**:
   - Registered `Ctrl+Alt+W` in `CommandRegistry` for instant global popup triggering from any screen.
3. **Command Palette (`Ctrl+K`)**:
   - `🌐 Open World Clock` — opens floating popover.
   - `🌐 Go to World Clock View` — navigates to full view.
4. **Dedicated Navigation View (`WorldClockView`)**:
   - Added `world_clock` to navigation sidebar (`NAV_ITEMS`) and `NavigationController`.
   - Includes interactive **Timezone Scrubber / Meeting Overlap Finder**: dragging the time slider shows what 3 PM in your local time corresponds to across all worldwide offices simultaneously.

---

## 7. Verification & Automated Test Evidence

Tested under `todo_bird_app/tests/test_world_clock_authority.py`:
- Country and timezone discovery (240+ countries): **PASSED**
- Flag emoji generation: **PASSED**
- Location search by city & country: **PASSED**
- Time information and UTC offset calculation: **PASSED**
- Relative offset calculation (ahead/behind): **PASSED**
- Solar day/night calculation: **PASSED**
- Settings persistence (load/save): **PASSED**
- Clock type switching (analog ↔ digital): **PASSED**
- All 5 theme definitions and painters: **PASSED**
- AnalogClockWidget rendering across all 5 themes: **PASSED**
- DigitalClockWidget 12h/24h toggle and themes: **PASSED**
- WorldClockCard dynamic switching & pinning: **PASSED**
- AddWorldClockDialog search and add: **PASSED**
- WorldClockPopover interactive open/close: **PASSED**
- WorldClockView multi-clock grid & scrubber: **PASSED**
- HeaderBar button & signal connection: **PASSED**
- CommandPalette world clock actions: **PASSED**
- Global shortcut `Ctrl+Alt+W` registration: **PASSED**
- Production DB invariant verification: **PASSED**
