# TODO BIRD — SCHEDULE DETAILS COPY UX REPORT
**Phase 2E Human-Witness Interaction Closure**
**Component:** Schedule Details Popover & Plain Text Clipboard Formatter
**Date:** 2026-09-02
**Status:** IMPLEMENTED & VERIFIED

---

## 1. Executive Summary

A critical human witness usability friction point was identified in Todo Bird's Gantt and WBS views: while the hover popups contained vital scheduling diagnostics (CPM early/late dates, float values, critical path flags, predecessor relationships, constraints, and baseline variances), users were unable to easily copy this information into LLMs such as ChatGPT for external schedule auditing and critical path analysis.

This mission delivers an enterprise-grade, theme-aware, persistent **Schedule Details Popover** (`ScheduleDetailsPopover`) and an immutable **Schedule Details Formatter** (`ScheduleDetailsFormatter`), accessible via right-click context menus, explicit buttons, and keyboard shortcuts across both Gantt and WBS views.

---

## 2. Architecture & Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                       Gantt / WBS View                      │
│   • Bar / Row Right-Click: "📋 Copy Schedule Details"        │
│   • Bar / Row Right-Click: "🔍 View Schedule Details..."     │
│   • Synchronized Left Pane Right-Click Actions              │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 ScheduleDetailsFormatter                    │
│   • build_from_entity(entity, project_name, db_manager)    │
│   • format_plain_text(model) -> Markdown text for ChatGPT   │
│   • format_html(model, is_dark) -> Rich rendered popover    │
└──────────────────────────────┬──────────────────────────────┘
                               │
                 ┌─────────────┴─────────────┐
                 ▼                           ▼
┌─────────────────────────────────┐ ┌─────────────────────────────────┐
│     Direct Clipboard Copy       │ │     ScheduleDetailsPopover      │
│  • System clipboard updated     │ │  • Persistent floating window   │
│  • Instant toast notification   │ │  • Selectable text browser      │
│  • Zero GUI interruptions       │ │  • Accessible [Copy Details]    │
│                                 │ │  • Ctrl+C & Esc shortcuts       │
└─────────────────────────────────┘ └─────────────────────────────────┘
```

---

## 3. Formatted Plain Text Structure (Optimized for ChatGPT)

The formatted plain text follows a canonical, deterministic structure specifically designed for clarity when pasted into ChatGPT or other analysis tools:

```text
Task: Reinforcement Final
Type: Level 2 Subtask [1.2.1]
Project: Metro Station Alpha
Status: In Progress
Priority: Urgent
Progress: 45%

Planned Schedule:
- Start: 2026-09-03 08:00
- Finish: 2026-09-05 17:00
- Duration: 2d (960 min)

CPM Analysis:
- ES: 2026-09-03 08:00
- EF: 2026-09-05 17:00
- LS: 2026-09-03 08:00
- LF: 2026-09-05 17:00
- Total Float: 0 min
- Free Float: 0 min
- Critical: Yes

Predecessors:
- Excavation Final | FS | Lag 0
- Rebar Delivery | SS | Lag 120

Constraint: SNET (2026-09-03 08:00)
Deadline: 2026-09-06 17:00

Baseline:
- 2026-09-01 08:00 → 2026-09-03 17:00
- Planned Duration: 2d (960 min)
- Finish Variance: +2d Late (+960 min)

Actual: 2026-09-03 08:15 → In Progress (480 min logged)
Execution Performance: +15m Late Start
Diagnostics:
- Path Criticality: High Risk
```

### Strict Non-Fabrication Rule
If a task has not undergone CPM analysis, has no baseline set, or has no recorded actuals, the formatter **never fabricates values**:
- Unanalyzed CPM: omits ES/EF/LS/LF or reports `CPM: Not analyzed`
- Unset baseline: `Baseline: Not Baselined`
- Unrecorded actuals: `Actual: Not Tracked`
- Empty dependencies: `Predecessors: None`

---

## 4. UI Component: `ScheduleDetailsPopover`

- **Window Flags**: `Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint`
- **Behavior**:
  - Persistent: does not auto-dismiss when the user moves the mouse into the window or selects text.
  - Interactive: user can highlight arbitrary text with mouse or keyboard.
  - One-Click Copy: contains prominent `[ 📋 Copy Details ]` button with visual confirmation (`✓ Copied!`).
  - Keyboard Support: `Ctrl+C` immediately copies all details; `Esc` closes the popover.
  - Drop Shadow: high-resolution subtle drop shadow for depth separation.
  - Theme Awareness: dynamically styles background, borders, and text in both Light (`#FFFFFF`, `#0F172A`) and Dark (`#1E1E2E`, `#F4F7FB`) modes.

---

## 5. Integration Points

1. **Gantt Chart Items (`GanttChartWidget` & `GanttItemView`)**:
   - Right-click context menu on any bar, milestone, or summary item provides:
     - `📋 Copy Schedule Details` (copies directly to clipboard with toast confirmation)
     - `🔍 View Schedule Details...` (opens persistent `ScheduleDetailsPopover`)
2. **Gantt Left Pane (`GanttLeftPaneListView`)**:
   - Context menu and shortcuts wired to `taskActionRequested` with actions `"copy_details"` and `"view_details"`.
3. **WBS Tree View (`WBSProjectView` & `ProjectsView`)**:
   - Right-click on any WBS row provides `📋 Copy Schedule Details` and `🔍 View Schedule Details...`.
   - Toast notification feedback upon copy.

---

## 6. Verification & Test Evidence

Tested under `todo_bird_app/tests/test_schedule_details_copy_interaction.py`:
- Task, Subtask, nested subtask, milestone, and summary model builds: **PASSED**
- Plain text clipboard extraction: **PASSED**
- CPM ES, EF, LS, LF, Total Float, Free Float fidelity: **PASSED**
- Critical flag and predecessor formatting: **PASSED**
- Absence of fabricated data: **PASSED**
- Non-transient popover behavior and keyboard shortcuts (`Ctrl+C`, `Esc`): **PASSED**
- Rich HTML hierarchical formatting: **PASSED**

---

## 7. Completeness Parity Addendum - 2026-09-03

Final classification for this addendum:

`todo_bird_phase2e_schedule_details_completeness_fixed_human_witness_required`

The original copy UX work made Schedule Details reachable and copyable. This addendum repairs the content contract: copied/plain-text details now expose the same canonical values that Gantt/WBS already display.

### Repaired Content Authority

- Added `ScheduleDetailsCollector` as the single collector feeding `ScheduleDetailsModel`.
- The formatter now exposes stable sections: Identity, Planned Input, Current Forecast / CPM, Dependencies, Constraint / Deadline, Calendar, Baseline / Revision, and Actual.
- Planned Gantt bar start/finish are reported from the same canonical fields used to render the bar.
- Rendered Gantt bar x-coordinates are attached to the chart task and exposed when available.
- CPM status and ES/EF/LS/LF/TF/FF/critical values are emitted from adapter/database values only.
- Unanalyzed CPM fields explicitly show `Not analyzed`.
- WBS Schedule Details now uses schedule-rich adapter rows instead of raw WBS nodes.
- Project name resolution now falls back through project maps and database project rows instead of showing blank output.

### Additional Evidence

- New completeness parity suite: `todo_bird_app/tests/test_schedule_details_completeness_parity.py`
  - 89 tests in the final isolated run.
- Schedule Details copy interaction suite remained green.
- Final isolated regression: 126/126 files, 3000 passed, 0 failed, 0 errors.

Human witness is still required for the exact live desktop workflow; this addendum is not a Beta Ready or Human Accepted declaration.
