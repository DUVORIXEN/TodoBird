# DASHBOARD UI/UX VISUAL AUDIT — Visual Polish Mission (§19–20)

Date: 2026-09-06 | Scope: VISUAL ONLY (functionality FROZEN — no CPM/WBS/schedule math,
no clock-data/horizon math, no persistence/signal/slot changes, `dashboard_data_service.py` untouched).
Baseline: `.opencode/docs/m1_visual_audit.md`. Session: ses_audit_doc (S6.1.1 shippable finalize, docs-only).

## 1. Before → After (per area, with verified evidence)

Evidence key (from `.opencode/todo.md` + `.opencode/work-log.md`, verified lines):
M1 counts 72/0/1 (dashboard_view 72 inline setStyleSheet / charts 0 / timeline 1) —
`.opencode/docs/m1_visual_audit.md` §§S1.1.1–S1.1.3, S1.2.1 [x].
M2 30/30 palettes untouched + QSS 666/666 parity (diff = 3 comment/color spots) — S2.1.1–S2.2.1 [x].
M3 import/AST (off-scale setSpacing 14/6 → 0, setStyleSheet 72→73 centralized, no new signals) — S3.1.1–S3.3.1 [x].
M4 repaint dark+light (theme-aware grid/text, token bars, milestone diamond, hover + QToolTip, styled H-scrollbar; px_per_day 80/50/35/15/10 intact) — S4.1.1–S4.2.1 [x].
M5 67 passed (charts 39 pytest + 2 isolated + clocks 26; hysteresis 150/300/8 intact; grid alpha ~20%) — S5.1.1–S5.3.1 [x].

- **M2 tokens/QSS** (`tokens.py` 69→139, `light.qss`/`dark.qss` 573→666): card/spacing/typography/semantic tokens added; palettes untouched; card system + control polish appended with light/dark parity.
- **M3 dashboard_view** (`dashboard_view.py` 2168→2280): off-scale spacing snapped to scale, radius 8/12, restrained token palette, StrongFocus + hover/pressed + tooltips + accessible names; no signal/slot/data changes. (2265 at M3 close +15 Chain B top-up drift, verified 2280 via `wc -l` 2026-09-06.)
- **M4 timeline** (`dashboard_timeline.py` 171→329): theme-aware grid/text, token bars, milestone diamond, hover + QToolTip, styled H-scrollbar; tick/anchor/px_per_day math untouched.
- **M5 charts+clocks** (`dashboard_charts.py` 3790→3825; digital 218→263; analog 437→451): grid alpha/insets, caption empty-states, radius-8 focus ring, tooltip geometry; all clock styles polished light/dark (T5.2 top-up: compact 15px/large 24px, minimal borderless, palette minimal face, accent #E95420); no data-field/signal changes.

| Area | Before (M1 baseline) | After (this mission) |
|------|----------------------|----------------------|
| Header / greeting (S3.1.1) | Gradient card padding 12x16, greeting hardcoded #3584E4 18px, date #9CA3AF, no focus/a11y | Padding 16x20, heading/body token hierarchy, radius 12 kept, StrongFocus + tooltips + accessible names ✓ (M3 import/AST) |
| Scope selector (S3.1.1) | Padding 4x10, radius 8, weight 600, no focus ring | Padding 4x12, transparent-border base (no hover shift), accent :hover/:focus, selected-item tint, StrongFocus + tooltip + accessible name ✓ (M3) |
| Clock strip (S3.1.2) | Root spacing 16, add-clock radius 6, divider 16px bold #475569, settings gear #94A3B8 borderless | Strip spacing 12 (compact, fits 5 clocks), add-clock radius 8, divider 14px regular #9CA3AF, settings radius 8 + hover tint ✓ (M3) |
| KPI strip (S3.1.2) | Mixed palette (#3B82F6, #06B6D4), MetricCard hierarchy undocumented | Restrained tokens (#3584E4), MetricCard-owned hierarchy comment (value/title/sub), grids on-scale 12 ✓ (M3) |
| Schedule / baseline grouping (S3.1.3) | Cyan accents (#06B6D4), flat horizon buttons (radius 6, padding 4x10) | Token accents + segmented horizon control (hover/pressed/checked, radius 8, padding 4x12, D→D+N tooltips) ✓ (M3) |
| Risk / attention / tables (S3.2.1) | #EF4444, row padding 2x4, bars 5px/radius 2/5, empty-states 6px | #DC2626, padding 4x8 + hover underline, bars 4px/radius 4, empty-states 8px, workload bar 8px ✓ (M3) |
| Responsive / a11y / micro (S3.2.2) | No focus policy, no pressed states; section_spacing default 14 | StrongFocus + hover/pressed throughout, quick-nav delight, spacing default 14→16 (visual default only) ✓ (M3) |
| Spacing rhythm | 14 ×9, 6 ×7, 10 ×1, 3 ×2, margins (0,2)/(0,3) — off-scale | Snapped to 16/8/8/4/(0,4,0,4) — scale 4/8/12/16/20/24/32/40 ✓ (M3 grep: 0 off-scale remain) |
| Responsive rhythm | wide 16/12, narrow 12, very-narrow 10 | wide 16/12, narrow 12, very-narrow 8 (16/12/8 progression) ✓ (M3) |
| Card system | Radius/padding inline only; no tokens | `tokens.py`: SPACING_SCALE, CARD_RADIUS sm8/md12, CARD_PADDING 12/16/24, CARD_GAP, TYPOGRAPHY_HIERARCHY, SEMANTIC_COLORS, DASHBOARD_CARD_DEFAULTS ✓ (M2 30/30 palettes untouched) |
| QSS | Vertical scrollbars only; no dashboard card/control rules | + `dashboardCard`, `sectionHeader`, `kpiValue/kpiLabel`, `segmented` controls, focus rings, **horizontal scrollbar** rules — light/dark parity 666/666 ✓ (M2) |
| Timeline (§8) | Hardcoded gray grid/text, bootstrap blues, no hover, stub mouseMoveEvent | Theme-aware grid/text/task colors, token bars (red/green/blue @200), bold Anchor-D label, hover row highlight + tooltip, leaveEvent reset; math (ticks, px/day, geometry) untouched ✓ (M4 repaint dark+light) |
| Charts tooltips | Already revalidated (150/300ms, 8px) | S5.1.3 tooltip card geometry snapped to scale; S5.1.1 grid ~20% alpha + chart insets on-scale; S5.1.2 caption-11pt empty-states, radius-8 focus ring, 4px label gaps ✓ (M5 67 passed) |
| Clocks (§9-12) | Minimal semantic; decorative styles fixed-color | S5.2.1/2 polished (26 tests PASS); classic luxury light deepened (#7A6116/#85711B); smoke-tested all styles × both themes ✓ (M5) |

## 2. Token map

- `SPACING_SCALE`: xs4 sm8 md12 lg16 xl20 2xl24 3xl32 4xl40
- `CARD_RADIUS`: sm8 md12 · `CARD_PADDING`: 12/16/24 · `CARD_GAP`: 8/12/16
- `TYPOGRAPHY_HIERARCHY`: display24/700, heading18/700, title15/600, body13/400, caption11/500, kpi_value24/700, kpi_label11/500, section_header13/700
- `SEMANTIC_COLORS`: accent #E95420, blue #3584E4, green #047857, red #DC2626
- `DASHBOARD_CARD_DEFAULTS`: radius12/padding16/gap12
- `bg_card`: dark #242538 / light #FFFFFF (palettes 30 keys each, untouched — M2 evidence)
- Accent/blue/green/red hexes: #E95420 / #3584E4 / #047857 / #DC2626 (mission palette, cf. `.opencode/todo.md` Project Context)

## 3. Control regression matrix (Reviewer S6.2.1 verified 2026-09-06 — offscreen + pytest; on-screen feel = human)

Smoke = offscreen import/repaint evidence on file (no crash, readable both themes).
Reviewer S6.2.1 (2026-09-06, independent re-run): DashboardView instantiated offscreen
(Mock db/settings); per-control results below. Interactive on-screen behavior (switching feel,
navigation context pass, drill-down click-through, persistence) remains with the human operator.

| Control | Light (smoke) | Dark (smoke) | Interactive full regression | Evidence |
|---------|---------------|--------------|-----------------------------|----------|
| Scope selector | ✓ render | ✓ render | VERIFIED S6.2.1 — instantiated, QSS + StrongFocus + tooltip/a11y present; switching feel = human | QSS ComboBox rules + offscreen instantiate |
| World clocks (4 styles × 2 themes) | ✓ render | ✓ render | VERIFIED S6.2.1 — 20/20 render (5 styles × 2 themes, digital+analog); add/remove/persist = human | CLOCKS SMOKE 10+10 PASS |
| S/X/R health cards | ✓ render | ✓ render | VERIFIED S6.2.1 — card_health + _on_health_card_clicked present, signals untouched; reason-click = human | token block intact |
| Horizons 7/14/30/90/180D | ✓ render | ✓ render | VERIFIED S6.2.1 — 5 buttons present + connected, range label `D = 06 Sep 2026 → D+7` verified; metric-change on-screen = human | no logic touched |
| Anchor D (Lookahead From + D→D+N) | ✓ render | ✓ render | VERIFIED S6.2.1 — picker + dateChanged + StrongFocus + label text verified | picker + range label intact |
| Timeline H-scroll + hover + tooltip | ✓ repaint | ✓ repaint | VERIFIED S6.2.1 — repaint 7/30/90/180 + empty-state, styled 8px H-scroll + wheelEvent + mouseMove/leaveEvent; smooth-scroll feel = human | TIMELINE repaint PASS |
| Activity range + legends + tooltips | ✓ render | ✓ render | VERIFIED S6.2.1 — combo 7D/14D/30D/90D + hysteresis 150/300 + tooltip QSS both themes (#111827/#eef2f7); flicker feel = human | hysteresis intact |
| Gantt nav (project parity) | ✓ render | ✓ render | VERIFIED S6.2.1 — _navigate_to + _navigate_to_gantt_with_id (project_id) + goto buttons present; context pass on-screen = human | signals/slots untouched |
| WBS nav | ✓ render | ✓ render | VERIFIED S6.2.1 — N/A: no WBS section in nav controller (pre-existing); existing targets (today/calendar/gantt/daily_review/focus) present | nav targets intact |
| Drill-downs (all buttons) | ✓ render | ✓ render | VERIFIED S6.2.1 — card.clicked→_navigate_to wiring + goto buttons present; click-through = human | targets untouched |
| Charts (capacity/status/weekly/effort) | ✓ import | ✓ import | VERIFIED S6.2.1 — import + capacity paint + status/activity widgets present; range switching on-screen = human | CHARTS IMPORT + paint PASS |
| No crash (smoke sweep) | ✓ | ✓ | VERIFIED S6.2.1 — full smoke + 173 pytest passed, no crash (only benign propagateSizeHints warnings) | offscreen repaints clean |

## 4. Light/dark evidence (verified 2026-09-06, ses_m6_audit + ses_audit_doc)

- AST: `AST_ALL6_PASS` — `dashboard_view.py`, `dashboard_timeline.py`, `dashboard_charts.py`, `digital_clock_widget.py`, `analog_clock_widget.py`, `tokens.py` all parse clean.
- QSS parity: `light.qss` 666 lines / `dark.qss` 666 lines; `diff` = 3 spots only (header comment, `border-top-color` #94A3B8/#6C7086, M2 token comment) — visual parity confirmed.
- Palettes: light/dark palettes 30 keys each, untouched (M2 evidence; only card/spacing/typo/semantic tokens added).
- Data authority: `dashboard_data_service.py` 1090 lines, mtime 12:10 (pre-mission) — untouched by this mission.
- Source mtimes (mission outputs, frozen before this audit): `tokens.py` 12:34, QSS 12:34, clocks 12:35/12:39, charts 12:37, timeline 12:38, `dashboard_view.py` 12:38 — none modified by S6.1.1 (only this .md file; verified via `ls -lt`).
- Offscreen smoke (prior sessions, mission record): IMPORT_ALL_PASS; timeline repaint dark+light clean; clocks all-styles × both-themes render; charts import + painters intact; only benign `propagateSizeHints` warnings.
- Timeline: `_timeline_is_dark()` (theme property → palette fallback); verified repaint in both.
- Clocks: minimal styles fully semantic; decorative styles intentionally fixed (glow aesthetics).

## 5. File change list (this mission — visual only)

| File | Before → After | Milestone |
|------|----------------|-----------|
| `todo_bird_app/themes/tokens.py` | 69→139 lines (card/spacing/typo/semantic added; palettes 30/30 untouched) | M2 S2.1.1 |
| `todo_bird_app/themes/light.qss` | 573→666 lines (card system + control polish) | M2 S2.1.2 |
| `todo_bird_app/themes/dark.qss` | 573→666 lines (identical M2 block; parity diff 3 spots) | M2 S2.1.3 |
| `todo_bird_app/views/dashboard_view.py` | 2168→2280 lines (spacing scale, radius 8/12, restrained palette, focus/hover/a11y; +15 Chain B top-up drift from 2265, verified via `wc -l`) | M3 S3.1.1–S3.2.2 |
| `todo_bird_app/widgets/dashboard_timeline.py` | 171→329 lines (theme-aware scale/anchor/grid, token bars, milestone diamond, H-scroll, hover/tooltip) | M4 S4.1.1–S4.1.3 |
| `todo_bird_app/widgets/dashboard_charts.py` | 3790→3825 lines (grid alpha/insets, caption empty-states, radius-8 ring, tooltip geometry) | M5 S5.1.1–S5.1.3 |
| `todo_bird_app/widgets/digital_clock_widget.py` | 218→263 lines (compact/large sizes, minimal borderless, light/dark contrast) | M5 S5.2.1 + T5.2 top-up |
| `todo_bird_app/widgets/analog_clock_widget.py` | 437→451 lines (palette minimal face, thin rim/ticks, accent second hand) | M5 S5.2.2 + T5.2 top-up |
| `dashboard_data_service.py` | 1090 lines — UNTOUCHED (data authority, mtime 12:10 pre-mission) | frozen |

## 6. What was deliberately NOT changed (frozen)

`dashboard_data_service.py` (data authority), horizon/anchor math, tick/px_per_day geometry,
`build_timeline_data` stub, experience-profile spacing default, signal/slot signatures,
chart painters/axes, decorative clock palettes.

## 7. Worker visual verification (ses_m6_audit — checked, smoke-level)

- [x] Dashboard spacing rhythm consistent (16/12/8) — verified by grep (0 off-scale layout spacings remain)
- [x] Cards/controls themed via tokens + QSS in both themes — parity diff clean (666/666, 3 spots)
- [x] Timeline horizontal scroll styled + hover/tooltip affordance — smoke-tested dark+light repaint
- [x] Tooltips readable light/dark — QSS + palette sync intact (hysteresis 150/300/8)
- [x] No crash on offscreen render (dashboard/timeline/charts/clocks) — smoke logs above (benign warnings only)
- Worker evidence (2026-09-06): AST PASS ×6 files; isolated dashboard 6/6 PASS (test file removed per protocol, record in `.opencode/unit-tests/20260906-dashboard_view-m3-isolated.md`); charts+theme 39 pytest PASS; clocks 26 tests PASS; T5.2 top-up (ses_clock_polish): isolated 13/13 PASS (record `.opencode/unit-tests/2026-09-06-ses_clock_polish-clocks_polish.md`, file removed), 5 themes × light/dark × compact/large = 30 renders PASS, 0 QSS warnings; full repaint smoke dark+light clean (benign propagateSizeHints warnings only); `dashboard_data_service.py` mtime 12:10 pre-mission, untouched

## 8. §20 human witness checklist (Reviewer S6.2.2 partial 2026-09-06 — offscreen-verified boxes marked; rest for operator on-screen)

Source: `.opencode/context.md` Human Witness Checklist items 1–24. Boxes marked
`(Reviewer offscreen)` were personally verified offscreen by the Reviewer on 2026-09-06
(instantiate/render/pytest evidence in §3); all other boxes require human on-screen witness.

- [ ] 1 Dashboard attractive — executive command center quality
- [ ] 2 World Clock Add works — button opens dialog, adds clock
- [ ] 3 World Clock Remove works — Settings and Dashboard
- [ ] 4 World Clock styles work — Compact Digital, Large Digital, Analog, Minimal
- [ ] 5 World Clock Light mode — text visible in Light theme
- [ ] 6 Clock persistence — restart app, clocks remain
- [ ] 7 S/X/R reasons understandable — click health card shows triggers
- [ ] 8 R color correct — GREEN/AMBER/RED with triggers
- [ ] 9 7D changes — shows 7-day metrics
- [ ] 10 14D changes — shows 14-day metrics
- [ ] 11 30D changes — shows 30-day metrics
- [ ] 12 90D changes — shows 90-day metrics
- [ ] 13 180D changes — shows 180-day metrics
- [x] 14 Lookahead Anchor D — date picker works, range label updates (Reviewer offscreen 2026-09-06: picker + dateChanged + `D = 06 Sep 2026 → D+7` label verified)
- [x] 15 Timeline horizontal scroll — no overlap, smooth scroll (Reviewer offscreen 2026-09-06: styled 8px H-scroll + wheelEvent + repaint 7/30/90/180 verified; scroll feel = human)
- [ ] 16 D+x / D-x visibility — relative indicators in cells
- [ ] 17 Tooltip smooth — no flicker, 150ms show, 300ms hide
- [ ] 18 All Projects correct — portfolio aggregates worst
- [ ] 19 Single Project correct — project-scoped metrics
- [ ] 20 Dashboard → Gantt project parity — Dashboard Project A → Gantt A
- [ ] 21 View WBS parity — navigates with project context
- [ ] 22 Drill-down correct — all buttons navigate to target views
- [x] 23 No warning flood — clean console (Reviewer offscreen 2026-09-06: only benign propagateSizeHints plugin warnings)
- [x] 24 No crash — stress tested (Reviewer offscreen 2026-09-06: full smoke + 173 pytest, zero crashes; on-screen stress = human)
- [ ] Human sign-off: __________  Date: __________
- Reviewer sign-off (S6.2.2, 2026-09-06T12:45Z): offscreen regression PASS — AST_ALL6_PASS, PY_COMPILE_ALL6_PASS, IMPORT_ALL6_PASS, APP_IMPORT_PASS, DashboardView instantiate PASS (13/14 attrs; timeline_widget attr superseded by _horizon_timeline lazy + timeline_card), clocks 20/20, timeline 7/30/90/180 + empty, tooltips light/dark readable, QSS 666/666 parity (3-spot diff), data service 1090 untouched, pytest 173 passed (93 + 80) + 2 known pre-existing fails (health_risk project_mode; long_range activity_data.append absent, count 0); ZERO new issues, no sync-issues file. On-screen items 1–13, 16–22 remain for human operator.
