# TODO BIRD — DOUBLE-CLICK EDIT UX REPORT
**Phase 2E Human-Witness Interaction Closure**
**Component:** Double-Click Routing, Canonical `SubtaskDialog`, & Typed Entity Resolution
**Date:** 2026-09-02
**Status:** IMPLEMENTED & VERIFIED

---

## 1. Executive Summary

Previously, double-clicking rows in the WBS tree or bars in the Gantt chart either triggered inconsistent behavior, failed to open nested subtasks, or opened the wrong dialog when multiple tasks/subtasks shared identical titles. Additionally, there was no standalone canonical editor for subtasks, forcing users through limited inline mechanisms.

This mission implements:
1. **Canonical `SubtaskDialog`**: A modal editor supporting top-level and nested subtasks of any depth, editing title, description, planned start/finish times, duration (with minutes-to-days bidirectional sync), priority, progress, Gantt visibility, pinned state/color, actual execution, and schedule governance constraints.
2. **Deterministic Double-Click Routing**: Stable, typed entity resolution distinguishing Tasks (`entity_type="task"`) from Subtasks (`entity_type="subtask"`), guaranteeing that double-clicking a subtask never opens the parent Task dialog.
3. **Chevron Hit Separation**: Double-clicking the expand/collapse chevron in WBS expands/collapses the tree branch without opening an edit dialog.
4. **Keyboard Accessibility**: Pressing `Return` / `Enter` or `Ctrl+Enter` on a selected item triggers the canonical edit action.
5. **Live Refresh Pipeline**: Saving either a Task or Subtask persists changes to SQLite, triggers CPM recalculation, and live-refreshes both WBS and Gantt views.

---

## 2. Typed Identity & Routing Architecture

```
                       User Interaction
           [ Double-Click / Enter on Row or Bar ]
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
       WBS Tree View                     Gantt Chart
    (EntityRef payload)            (item_id, item_type)
              │                               │
              ▼                               ▼
   Chevron Hit Check?                Synthetic Negative ID?
    ├─ Yes: Toggle branch             ├─ Yes (< 0): Subtask ID = abs(id)
    └─ No:  Emit typed key            └─ No  (> 0): Task ID = id
              │                               │
              └───────────────┬───────────────┘
                              ▼
                   Typed Entity Resolution
                              │
             ┌────────────────┴────────────────┐
             ▼                                 ▼
   entity_type == "task"             entity_type == "subtask"
             │                                 │
             ▼                                 ▼
      Open TaskDialog                  Open SubtaskDialog
             │                                 │
             └────────────────┬────────────────┘
                              ▼
                    Save to Database (SQLite)
                              │
                              ▼
            Live CPM Schedule & View Refresh Pipeline
                 • db_manager.update_task/subtask
                 • refresh_project_schedule()
                 • left_pane_list.update()
                 • gantt_chart.update()
```

---

## 3. The Canonical `SubtaskDialog`

Located at `todo_bird_app/widgets/subtask_dialog.py`, the `SubtaskDialog` provides comprehensive editing capabilities:
- **Identity**: Subtask Title, Description, and Parent Task/Subtask hierarchy indicator.
- **Planned Timing**: Planned start date & time, finish date & time, duration in minutes with synced fractional days (`480 min = 1.0 day`).
- **Status & Progress**: Planned, In Progress, Completed, Blocked, On Hold; interactive progress slider & spin box (0–100%).
- **Gantt & Visuals**: Toggle "Show in Gantt Chart", pinning toggle with color selection.
- **Actual Execution Tracking**: Actual start date/time, actual finish date/time, actual duration in minutes.
- **Schedule Governance**: ASAP, ALAP, SNET, SNLT, FNET, FNLT, MSO, MFO constraint selection, constraint datetime, and hard target deadline.

---

## 4. Safety & Edge Case Handling

1. **Duplicate Title Safety**:
   - Tasks and subtasks are identified strictly by immutable database primary keys (`id`), never by string matching on `title`. Two subtasks titled `"Inspection"` under the same task operate completely independently without cross-mutation.
2. **Nested Subtasks of Arbitrary Depth**:
   - Top-level subtasks (depth 1) and nested subtasks (depth 2+) route to `SubtaskDialog` with their specific `subtask_id`. Gantt negative IDs (`-subtask_id`) are cleanly decoded to positive primary keys.
3. **Summary Rows Protection**:
   - Summary rows representing rolled-up schedule groups cannot have their summary dates directly edited. If a summary row corresponds to an underlying Task, that Task editor is opened; otherwise an explanatory banner guides the user.
4. **WBS Chevron Hit Separation**:
   - The double-click handler inspects horizontal click coordinates (`start_x - 4 <= click_x <= start_x + 24`). Clicks in the chevron region only toggle node expansion, preserving expected desktop tree behavior.

---

## 5. Verification & Test Evidence

Tested under `todo_bird_app/tests/test_double_click_edit_workflow.py`:
- WBS double-click signal emission: **PASSED**
- Subtask WBS double-click opens `SubtaskDialog`: **PASSED**
- Nested subtask (depth=2) opens `SubtaskDialog`: **PASSED**
- Gantt bar Task double-click routes to `TaskDialog`: **PASSED**
- Gantt bar Subtask double-click routes to `SubtaskDialog`: **PASSED**
- Gantt nested subtask routing without parent delegation: **PASSED**
- Gantt left pane double-click routing: **PASSED**
- Stable typed identity routing (`EntityRef`): **PASSED**
- Duplicate title safety under concurrent edits: **PASSED**
- Summary row edit guard: **PASSED**
- Chevron toggle decoupled from edit trigger: **PASSED**
- Subtask save persistence to SQLite: **PASSED**
- Keyboard `Return` / `Enter` and `Ctrl+Enter` triggers: **PASSED**
- SubtaskDialog title validation & actuals persistence: **PASSED**
- Governance constraints persistence: **PASSED**
- Rapid repeated open/close cycle cleanliness: **PASSED**
