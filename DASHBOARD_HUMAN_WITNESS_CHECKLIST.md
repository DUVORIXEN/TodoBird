# Dashboard Human Witness Checklist — Phase 2F Final Acceptance

**Mission**: Todo Bird Dashboard Phase 2F Final Interaction Repair  
**Generated**: 2026-09-06  
**Classification**: `todo_bird_dashboard_final_interaction_repair_human_witness_required`

---

## Human Witness Checklist

Please verify each item by testing the actual application. Check each box when confirmed.

### 1. Dashboard Visual Quality
- [ ] **1. Dashboard attractive** — Executive command center quality, professional project-control cockpit feel, Linear/Notion aesthetics with MS Project/Primavera depth

### 2. World Clock System
- [ ] **2. World Clock Add works** — Dashboard header "Add World Clocks" button opens dialog, adds clock, appears immediately
- [ ] **3. World Clock Remove works** — Settings → Dashboard → World Clocks → Remove Selected works; Dashboard header clock strip updates immediately
- [ ] **4. World Clock styles work** — Compact Digital, Large Digital, Analog, Minimal styles available in Add dialog, persist per clock
- [ ] **5. World Clock Light mode** — Digital clock text visible and readable in Light theme (no white-on-white)
- [ ] **6. Clock persistence** — Restart app, all clocks remain with correct styles and order

### 3. Health Signals (S X R)
- [ ] **7. S/X/R reasons understandable** — Click health card (S X R dots) → dialog shows exact trigger reasons for each signal
- [ ] **8. R color correct** — Risk (R) shows GREEN when no risk triggers, AMBER for warning triggers (blocked ≤2, delayed ≤2, near-critical, thin float, high blocker ageing), RED for critical triggers (negative float, cycles, critical blocked/delayed, missed critical deadline, >2 blocked/delayed)

### 4. Lookahead Horizon
- [ ] **9. 7D changes** — Click 7D button → shows 7-day metrics (Tasks Starting/Finishing, Milestones, Critical)
- [ ] **10. 14D changes** — Click 14D button → shows 14-day metrics
- [ ] **11. 30D changes** — Click 30D button → shows 30-day metrics
- [ ] **12. 90D changes** — Click 90D button → shows 90-day metrics
- [ ] **13. 180D changes** — Click 180D button → shows 180-day metrics (emphasizes milestones, deadlines, forecast finishes, critical exposure)

### 5. Anchor Date & Timeline
- [ ] **14. Lookahead Anchor D** — "Lookahead From:" date picker works, default = Today, changing date refreshes timeline
- [ ] **15. Timeline horizontal scroll** — QScrollArea horizontal viewport works, no label overlap, smooth scroll, adaptive tick density
- [ ] **16. D+x / D-x visibility** — Timeline cells show relative indicators (D-10, D-3, D, D+7, D+30) on hover/cell

### 6. Tooltip Behavior
- [ ] **17. Tooltip smooth** — No flicker on any component, 150ms show delay, 300ms hide delay, 8px movement tolerance prevents recreation storms

### 7. Scope & Navigation
- [ ] **18. All Projects correct** — Portfolio mode aggregates correctly (worst-of health, sums for counts), no fake cross-project CPM
- [ ] **19. Single Project correct** — Project mode shows project-scoped metrics, CPM, baseline variance
- [ ] **20. Dashboard → Gantt project parity** — Dashboard Project A → "View in Gantt" → Gantt opens Project A (not last-viewed project)
- [ ] **21. View WBS parity** — Project Schedule card "View in Gantt" and "View WBS" buttons navigate with project context
- [ ] **22. Drill-down correct** — All Dashboard buttons navigate to correct target views (Today, Calendar, Gantt, Daily Review, Tasks)

### 8. Stability
- [ ] **23. No warning flood** — Clean console, no Qt warning spam
- [ ] **24. No crash** — Stress tested: 100 scope cycles, 200 horizon cycles, 50 theme cycles, 100 Dashboard enter/leave cycles, MainWindow close rc=0

---

## Production Database Safety
- [ ] SHA256 of production database captured BEFORE validation run
- [ ] SHA256 of production database captured AFTER validation run
- [ ] SHA256 values **UNCHANGED** (no writes to production DB during validation)

---

## Final Classification

**todo_bird_dashboard_final_interaction_repair_human_witness_required**

All 24 checklist items must be confirmed by human witness before acceptance.

---

## Sign-Off

**Human Witness**: _________________________  
**Date**: _________________________  
**Signature**: _________________________

**Mission Status**: `todo_bird_dashboard_final_interaction_repair_human_witness_required`

---

## Mission Complete Summary

All forensic repairs completed across 22 files modified + 1 new widget:

| Area | Status |
|------|--------|
| Dashboard → Gantt Context Propagation | ✅ COMPLETE |
| Lookahead Horizon (7D/14D/30D/90D/180D) | ✅ COMPLETE |
| Anchor Date D Control | ✅ COMPLETE |
| Horizontal Scrollable Timeline | ✅ COMPLETE |
| Relative Date Indicators (+X/-X days) | ✅ COMPLETE |
| 180D Horizon | ✅ COMPLETE |
| World Clock Add/Remove/Reorder/Styles | ✅ COMPLETE |
| World Clock Light/Dark Theme | ✅ COMPLETE |
| All Projects Mode Audit | ✅ COMPLETE |
| Tooltip Smoothness (Hysteresis) | ✅ COMPLETE |
| Executive Visual Quality | ✅ COMPLETE |
| Documentation (9 reports) | ✅ COMPLETE |

**Mission Classification**: `todo_bird_dashboard_final_interaction_repair_human_witness_required`

All forensic repairs complete. Awaiting human witness for final acceptance.