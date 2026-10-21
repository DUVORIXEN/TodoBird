# TODO BIRD — PRODUCTION READINESS AUDIT REPORT
**Date:** August 14, 2026
**Audit Mode:** MODE 1 - Evidence-Based Assessment Only (No Modifications)
**Version:** 0.9.0-pilot1
**Auditor Role:** Principal Architect + Multi-Domain Engineer

---

## EXECUTIVE SUMMARY

**PRODUCTION READINESS: NOT READY**

TODO BIRD demonstrates **solid architectural foundation** but exhibits **critical gaps** in production discipline across testing, internationalization, accessibility, and defect remediation.

**Maturity Score: 42/100**
- Data Integrity: 75/100
- Core Task Workflow: 60/100
- Gantt Visualization: 55/100
- Calendar: 50/100
- Focus Mode: 40/100
- Cross-View Consistency: 60/100
- UX/Responsiveness: 65/100
- Testing Infrastructure: 25/100
- Performance Validation: 30/100
- Internationalization: 10/100
- Accessibility: 15/100
- Release Engineering: 20/100

**Recommendation:** Requires **Phase 1 Foundation Work** (8-12 weeks) before beta release.

---

## 15 MAJOR FINDINGS

### FINDING 1: NO UNIT TEST FRAMEWORK EXISTS
**Severity:** P0 (Blocker)
**Area:** Testing
**Evidence:**
- `/todo_bird_app/tests/`: 4 files total (642 LOC)
  - `test_suite.py` (197 LOC) - 30 integration criteria only
  - `acceptance_witness.py` (176 LOC) - End-to-end scenario witness
  - `benchmark_witness.py` (160 LOC) - Performance data collection
  - `generate_large_dataset.py` (109 LOC) - Synthetic data generator
- `grep "def test_\|class Test" `: 0 matches
- No pytest, unittest, or tox configuration

**Root Cause:** Testing strategy relies solely on acceptance/integration layer. No isolated unit tests for models, controllers, or engines.

**User Impact:**
- Regressions hide until late in development
- Refactoring carries high risk
- Debugging is expensive (requires full app launch)
- Code coverage unmeasured

**Correct Production Behavior:**
Production systems require layered testing:
- Unit tests for all models, engines, controllers (70%+ coverage target)
- Integration tests for cross-component workflows
- UI interaction tests for critical paths
- Data consistency tests for database operations

**Safest Repair Strategy:**
1. Create pytest infrastructure in `tests/` (conftest.py, fixtures)
2. Write unit tests for:
   - `models/task.py` - validation, serialization
   - `controllers/delay_engine.py` - delay calculations
   - `gantt/timescale_engine.py` - date/time math
   - `gantt/gantt_dependency_engine.py` - cycle detection, critical path
   - `database.py` - CRUD operations, migrations
3. Target: 200+ unit tests before P1 completion
4. Integrate into CI/CD pipeline

**Regression Risk:** LOW - Adding unit tests does not break existing code if integrated carefully

---

### FINDING 2: HOURLY GANTT MODE VISIBILITY NOT VALIDATED
**Severity:** P0 (Blocker)
**Area:** Gantt
**Evidence:**
- `gantt/timescale_engine.py` line 51: `ZoomLevel.HOURLY` defined
- `gantt_chart.py` line 75: `zoom_mode` can be `ZoomLevel.HOURLY`
- `timescale_engine.py` lines 103-116: Hourly column generation (24 hourly columns for anchor_date)
- `gantt_view.py`: Hourly mode accessible from UI
- **No visibility test** in `test_suite.py` for hourly mode rendering
- No test for hourly navigation (prev/next)
- No test for task filtering by hour

**Root Cause:**
- Hourly mode exists but is not systematically tested
- Task filtering logic uses `planned_date` exact match, but hourly mode needs `planned_date + planned_start_time` precision
- No acceptance witness for hourly visibility

**User Impact:**
- Tasks may appear to "disappear" when viewing hourly Gantt
- Hourly navigation unpredictable
- User unclear why tasks not visible
- Violates principle: "A task must never appear deleted without clear explanation"

**Correct Production Behavior:**
1. Hourly Gantt filters tasks where `task.planned_date == anchor_date AND task.planned_start_time falls within visible hour`
2. Prev/Next hour navigation updates anchor_date intelligently (midnight boundary handling)
3. If a task exists but is off-anchor-date, display: "Task scheduled for [DATE]. Jump to [DATE] →"
4. Task must remain visible consistently across zoom levels

**Safest Repair Strategy:**
1. Implement hourly task visibility test (acceptance test in test_suite.py)
2. Verify: Create task → Gantt hourly view → task visible
3. Test navigation: Jump to different hours, tasks follow
4. Add guard: If `zoom_mode == HOURLY`, validate `planned_start_time` is set on all visible tasks
5. Add "jump to date" affordance when tasks off-date

**Regression Risk:** MEDIUM - May require refactoring task filtering logic

---

### FINDING 3: SCENE RECONSTRUCTION STABILITY UNKNOWN
**Severity:** P0 (Blocker)
**Area:** Gantt
**Evidence:**
- `gantt_chart.py` line 118: `self.timer.timeout.connect(self.rebuild_chart)` - Full scene rebuild every 60 seconds
- Line 2270: `self.scene.clear()` called on every rebuild
- Lines 2253-2269: Documented Qt lifetime safety (good) but **tested only at v30 acceptance level**
- No unit test validates:
  - Scene clear doesn't leak Python references
  - Hover operations don't trigger rebuild
  - Mouse movement doesn't rebuild (only layout calculation)
  - 100 zoom changes + 50 drag operations don't accumulate garbage

**Root Cause:**
- Scene clearing implemented correctly in principle
- **But**: No automated regression test proves hover/mouse operations don't cause destructive repaints
- Previous defect: "hovering has caused date/time/reference lines to disappear temporarily"
- No soak test validates 100 interactions without flicker

**User Impact:**
- Hover instability: User hovers task → reference lines disappear → confusing UX
- Flicker on every 60-second rebuild with many tasks
- Unclear whether visual corruption is UI state or rendering bug

**Correct Production Behavior:**
1. Hover operation: lightweight (no scene rebuild)
2. Only data changes trigger scene rebuild (task change, zoom, filter)
3. No mouse movement triggers full scene reconstruction
4. 60-second timer only refreshes "now" line, not entire scene

**Safest Repair Strategy:**
1. **Add test:** Hover 20 tasks 5 times each → zero flicker/disappearance
2. **Add test:** Drag 10 tasks → scene remains stable
3. **Add test:** Resize 5 tasks → no render corruption
4. **Refactor hover handling:** Make lightweight (update color only, don't rebuild)
5. **Split timer:** 60s for "now line", 5s for item refresh only
6. Measure: Track QGraphicsScene item count before/after 100 operations

**Regression Risk:** MEDIUM - May require hover/mouse handler refactoring

---

### FINDING 4: TASK CONSISTENCY ACROSS VIEWS NOT FORMALLY TESTED
**Severity:** P0 (Blocker)
**Area:** Cross-View Consistency
**Evidence:**
- 16 views: Inbox, Today, Upcoming, Projects, Calendar, Gantt, Focus, Completed, Analytics, Daily Review, Settings, etc.
- `task_controller.py` emits `tasks_changed` signal on CRUD
- `grep "tasks_changed.connect"` returns 59 references across views
- **But**: No formal test confirms the same Task remains consistent across all views
- `test_suite.py`: No cross-view workflow test
- Missing test: Create T → Inbox sees T → Calendar sees T → Gantt sees T → Focus can select T → Edit from Calendar → All views update

**Root Cause:**
Signal-based update pattern exists but is **not systematically validated** end-to-end.

**User Impact:**
- User may see task in Inbox but not in Calendar (data inconsistency)
- Edit in one view doesn't propagate (stale cache)
- User loses trust in data ("did my edit save?")
- Critical production showstopper

**Correct Production Behavior:**
One task instance, one truth:
1. Create task → all views query fresh from DB on signal
2. Edit task → emit signal → affected views refresh from DB
3. Delete task → all dependent views remove reference
4. No view maintains independent cached copy

**Safest Repair Strategy:**
1. Create cross-view consistency test:
   ```python
   def test_cross_view_consistency():
       # Create task T
       # Assert Inbox sees T
       # Assert Calendar sees T
       # Assert Gantt filter-tree shows T
       # Assert Analytics counts T
       # Edit T (change status, due_date, priority)
       # Assert Inbox reflects edit
       # Assert Calendar reflects edit
       # Assert Gantt reflects edit
       # Delete T
       # Assert all views remove T
   ```
2. Add database-level assertion: `SELECT COUNT(*) WHERE id = T.id` returns exactly 1
3. Add view-layer test: Refresh each view, re-query, verify consistency

**Regression Risk:** LOW - Testing only, no logic change required

---

### FINDING 5: CALENDAR MULTI-DAY TASK SEMANTICS UNDEFINED
**Severity:** P1
**Area:** Calendar
**Evidence:**
- `calendar_view.py` lines 45-65: Calendar filtering:
  ```python
  day_tasks = [t for t in all_tasks if t.planned_date == sel_date_str or t.due_date == sel_date_str]
  ```
- Logic: Task visible if `planned_date == selected_date` OR `due_date == selected_date`
- **Problem:** A task from Aug 12 due Aug 15 appears only on Aug 12 and Aug 15, invisible on Aug 13-14
- No multi-day task bar
- No indication "this task spans multiple days"
- Known issue noted in requirements: "multi-day tasks should have clear calendar semantics"

**Root Cause:**
Calendar treats `planned_date` and `due_date` as independent filters, not as a range.

**User Impact:**
- Calendar appears incomplete ("where did my 4-day task go?")
- Impossible to see full project scope on calendar
- Violates real-world calendar semantics

**Correct Production Behavior:**
1. Task visible on calendar if: `planned_date <= selected_date <= due_date`
2. Multi-day task displays as continuous bar (or visual indicator)
3. Clicking task opens editor with full date range shown
4. Edit from calendar saves immediately and refreshes display

**Safest Repair Strategy:**
1. Change filter:
   ```python
   day_tasks = [t for t in all_tasks if
     (t.planned_date and t.planned_date <= sel_date_str) and
     (t.due_date and t.due_date >= sel_date_str)
   ]
   ```
2. Add multi-day visual (e.g., connected boxes or continuous bar)
3. Test: Create 5-day task → Calendar shows it on all 5 days
4. Test: Edit calendar task → all views refresh

**Regression Risk:** MEDIUM - Changes filtering logic

---

### FINDING 6: FOCUS MODE WORKFLOW INCOMPLETE
**Severity:** P1
**Area:** Focus
**Evidence:**
- `focus_view.py` lines 1-165 (165 LOC)
- UI elements exist: timer display, pause/resume buttons, distraction capture
- `_on_timer_tick()` increments elapsed_seconds, no persistence
- No actual task selection workflow (user must navigate elsewhere to select)
- Known issue: "operator reports it feels dummy"
- No integration: Focus session doesn't mark task `IN_PROGRESS` automatically
- Timer state lost on app restart

**Root Cause:**
Focus View has UI shell but lacks real workflow:
- No task selector
- No automatic status update
- No elapsed time persistence
- No resume-session capability
- No metrics (completion rate, interruptions, focus quality)

**User Impact:**
- Focus mode is unusable (can't select task to focus on)
- Timer resets on app restart (data loss)
- No feedback whether focus session was successful
- Feature feels abandoned

**Correct Production Behavior:**
1. Enter Focus → select task from Inbox/Today
2. Start → task status becomes `IN_PROGRESS`
3. Timer runs, captures pauses, interruptions
4. End Session → elapsed time saved, task remains at status (user decides if complete)
5. Metrics: total focus time, interruption count, quality rating
6. Persist across app restart

**Safest Repair Strategy:**
1. Add task selector: Quick list of Inbox/Today tasks (not full dialog)
2. On "Start": Update task status to `IN_PROGRESS`
3. On "End Session": Emit event to task_controller to update `actual_duration`, emit `tasks_changed`
4. Persist elapsed time in database (new table: `focus_sessions`)
5. On app restart, offer "Resume last session?"

**Regression Risk:** MEDIUM - Adds database schema (focus_sessions table)

---

### FINDING 7: INTERNATIONALIZATION ARCHITECTURE ABSENT
**Severity:** P2
**Area:** Internationalization
**Evidence:**
- `grep -r "i18n\|gettext\|tr("` → 0 production patterns
- Date/time: `strftime()` hardcoded format (52 occurrences)
- No locale awareness: settings don't include `date_format`, `time_format`, `week_start`, `language`
- No timezone handling
- All UI strings hardcoded English
- Example: `focus_view.py` line 37: `QLabel("Select a task to enter Focus Mode")` - hardcoded

**Root Cause:**
Internationalization was never architected. App is built monolithic English.

**User Impact:**
- Non-English users cannot use application
- Regional date/time formats wrong
- Work week assumptions (Monday start vs Sunday start)
- Export/import breaks with different locales
- Cannot build international product

**Correct Production Behavior:**
1. Centralized translation file (`.ts`, `.po`, or `.json`)
2. All UI strings wrapped: `self.tr("Select a task...")` or equivalent
3. Settings include: `language`, `date_format`, `time_format`, `week_start`, `timezone`
4. Database stores canonical ISO dates, app renders based on locale
5. Support: English, Indian languages (Hindi, Tamil, Telugu), European languages
6. Prepare architecture for: Arabic/RTL, CJK

**Safest Repair Strategy:**
1. Create `localization/` module with string catalog
2. Extract all hardcoded strings into constants
3. Add Settings fields: language, date_format, time_format, week_start
4. Wrap UI strings with translation lookup
5. Phase 1: English + Hindi
6. Do NOT use Qt's `tr()` (insufficient for this scale)

**Regression Risk:** MEDIUM - Refactoring all UI strings

---

### FINDING 8: ACCESSIBILITY NOT IMPLEMENTED
**Severity:** P2
**Area:** Accessibility
**Evidence:**
- `grep -r "AccessibleName\|setAccessibleDescription"` → 8 occurrences (minimal)
- No keyboard shortcuts documented (except Ctrl+K for command palette)
- No visible focus indicators on Gantt chart
- No ARIA-equivalent labels on custom widgets
- No screen reader support tested
- Gantt interactions: drag/resize/click - no keyboard alternative described

**Root Cause:**
Accessibility was not considered in design. No audit performed.

**User Impact:**
- Users with visual impairments cannot use application
- Keyboard-only users blocked
- Product violates WCAG 2.1 AA standards
- Cannot sell to enterprises (ADA compliance required)

**Correct Production Behavior:**
1. All interactive elements keyboard-navigable
2. Clear focus indicators
3. Accessible names on all controls
4. Keyboard shortcuts for critical tasks:
   - Tab/Shift+Tab: Navigate
   - Enter: Activate
   - Ctrl+N: New task
   - Ctrl+E: Edit task
   - Delete: Delete task
   - Ctrl+Z: Undo
5. Screen reader: Announces task, status, due date, priority

**Safest Repair Strategy:**
1. Audit with accessibility tool (WAVE, Axe)
2. Add KeyPress handlers to Gantt for:
   - Arrow keys: Move task
   - Ctrl+Arrow: Resize task
   - Delete: Remove task
   - Enter: Edit task
3. Add visible focus rings in stylesheet
4. Test with screen reader (NVDA, JAWS)

**Regression Risk:** MEDIUM - May require UI event handler refactoring

---

### FINDING 9: DEPENDENCY CYCLE DETECTION INCOMPLETE
**Severity:** P1
**Area:** Data Integrity
**Evidence:**
- `gantt/gantt_dependency_engine.py` exists for rendering dependencies
- `task_dialog.py`: Blocks self-dependency in UI only
- **No backend validation** in `task_controller.py` or `database.py` for:
  - Indirect cycles (A→B→C→A)
  - Cycle detection before write
- Test suite v30: No cycle creation test
- Known issue: "existing real test data has contained indirect cycles"

**Root Cause:**
Cycle detection logic not implemented in persistence layer. UI prevents self-dependency but not indirect cycles.

**User Impact:**
- User creates A→B→C→A → silent data corruption
- Gantt renderer undefined behavior (infinite loop risk)
- Critical path calculation breaks

**Correct Production Behavior:**
1. Before task update with new dependencies:
   - Build dependency graph
   - Run cycle detection (DFS)
   - Reject if cycle detected
   - Show user: "Cannot add: would create A→B→C→A cycle"
2. On app startup: Audit existing DB for cycles
3. If found: Alert user, offer repair options

**Safest Repair Strategy:**
1. Implement cycle detection in `task_controller.add_dependency()`:
   ```python
   def can_add_dependency(self, task_id, depends_on_task_id) -> bool:
       # Build graph, run DFS, return True if no cycle
   ```
2. Add test: Create A→B, B→C, attempt C→A (must reject)
3. Add startup audit: Scan all dependencies for cycles on app launch
4. If cycle found: Log and alert user

**Regression Risk:** LOW - New logic, isolated from existing

---

### FINDING 10: NO PERFORMANCE TARGETS VALIDATED
**Severity:** P1
**Area:** Performance
**Evidence:**
- `test_suite.py`: No performance measurements
- `benchmark_witness.py`: Collects memory/CPU but no assertions on targets
- Gantt rendering: Unknown performance at 100, 500, 1000 tasks
- Calendar: Unknown performance at 1000+ tasks
- Database queries: No index utilization confirmed
- No startup time target validated (target: <4s cold, <2s warm)

**Root Cause:**
Performance never measured systematically. No target thresholds defined.

**User Impact:**
- App may be unusably slow with 500+ tasks
- Database queries slow → UI hangs
- User cannot import large projects
- Enterprise adoption blocked

**Correct Production Behavior:**
1. Startup: <2s warm, <4s cold (with 1000 tasks)
2. View switch: <100ms perceived, <250ms absolute
3. Task save: <100ms
4. Gantt render: 100 tasks smooth, 500+ usable, 1000+ planned architecture
5. Database query: <50ms for common queries (planned_date range)

**Safest Repair Strategy:**
1. Define performance benchmarks in code comments
2. Add profiling:
   - Startup time measurement
   - Database query timing
   - Gantt render timing
   - Memory usage at various scales
3. Create performance test: Load 500 tasks, measure Gantt render
4. Add CI check: If performance regresses >10%, alert

**Regression Risk:** MEDIUM - May require query optimization (indexes)

---

### FINDING 11: 54 BACKUP FILES CAUSE REPOSITORY POLLUTION
**Severity:** P2
**Area:** Release Engineering
**Evidence:**
- `find todo_bird_app -name "*.bak*" | wc -l` → 54 files
- Examples:
  - `delay_engine.py.before_gantt_authority_fix_20260813_074432.bak`
  - `gantt_chart.py.before_advanced_gantt_20260814_062421.bak`
  - Multiple versions of same file (3-4 per component)
- Total size: ~200-500 KB of dead code
- Makes git history noisy
- Unclear which is "current" vs "rollback"

**Root Cause:**
Manual backup discipline before risky changes. No version control discipline.

**User Impact:**
- Repository clutter
- Slow clone/checkout
- Confusion about source of truth
- Unprofessional appearance
- Violates: "BACKUP CLUTTER: Do NOT delete backups until retention policy defined"

**Correct Production Behavior:**
1. Git is the backup system
2. If backup needed before risky change: `git stash` or `git branch`
3. Archive old files: Move to `ARCHIVE/` with date
4. Define retention: Keep last 3 known-good versions
5. Implement controlled backup strategy in Phase 3

**Safest Repair Strategy:**
1. Do NOT delete until recovery verified
2. Create: `/BACKUP_ARCHIVE/` directory
3. Move all `.bak*` files to archive with date
4. Commit: "chore: archive development backups"
5. Future: Use git workflows instead

**Regression Risk:** NONE - Moving files, not changing code

---

### FINDING 12: LARGE GANTT COMPONENT DIFFICULT TO MAINTAIN
**Severity:** P2
**Area:** Architecture
**Evidence:**
- `gantt_chart.py`: 2,505 lines
- Responsibilities:
  - Timeline rendering (columns, headers)
  - Task item rendering
  - Interactive drag/resize/click
  - Dependency rendering
  - Zoom control
  - Scene lifecycle
  - Mouse/keyboard handling
- Single class: GanttChartWidget (too many concerns)
- Refactoring risky: High coupling, many state variables

**Root Cause:**
Gantt component grew organically without incremental refactoring.

**User Impact:**
- Bugs in Gantt hard to isolate
- New features require full class understanding
- Risk of regression on any change
- Slower development

**Correct Production Behavior:**
Extract subcomponents:
- `GanttRenderEngine` - Timeline + scene rendering
- `GanttInteractionController` - Drag/resize/click handling
- `GanttDependencyRenderer` - Arrow rendering
- `GanttScheduleMapper` - Task position/width calculation
- `GanttTimelineRenderer` - Column/header rendering

**Safest Repair Strategy:**
1. **Do NOT refactor during defect repair** (Phase 0)
2. After Phase 1 stabilization:
   - Identify seams in current code
   - Extract interfaces
   - Move responsibilities incrementally
   - Add unit tests per extracted component
   - Validate behavior unchanged

**Regression Risk:** HIGH - Do not attempt in Phase 0/1

---

### FINDING 13: DATABASE SCHEMA MIGRATION UNTESTED
**Severity:** P1
**Area:** Data Integrity
**Evidence:**
- Schema v8 with migration path v1→v2→...→v8
- `database.py`: Linear migration (good design)
- **But**: No test confirms:
  - v7→v8 upgrade preserves existing data
  - Migration idempotent (running twice safe)
  - Rollback safety (can restore from backup)
- No test: Create task in v7 schema, migrate to v8, query task

**Root Cause:**
Migration logic exists but untested against real-world upgrades.

**User Impact:**
- User upgrades app → data corrupted/lost → catastrophic trust failure
- Cannot roll back if migration fails

**Correct Production Behavior:**
1. Migration is transactional
2. Before migration: Auto-backup
3. Test: Old schema → new schema → data intact
4. Test: Multiple runs same migration = idempotent

**Safest Repair Strategy:**
1. Create test: Create v1 task, run migrations v1→v8, query task (should exist)
2. Create test: Run migrate(v8) twice, no error
3. Create test: If migration fails mid-transaction, automatic rollback
4. Document: Backup location and recovery procedure

**Regression Risk:** MEDIUM - May require migration logic audit

---

### FINDING 14: GESTURE/RESIZE HANDLES NOT USABLE
**Severity:** P1
**Area:** Gantt
**Evidence:**
- `gantt_chart.py` lines 50-59: Resize state variables exist (`_resize_mode`, `_resize_item`, etc.)
- `_resize_edge_px = 14.0` - cursor change zone defined
- Known defect: "resize handles were implemented but not reliably usable"
- Known issue: "operator could not see expected ↔ cursor"
- Known issue: "preview rectangle did not appear"
- No test validates resize workflow

**Root Cause:**
Resize feature coded but not fully integrated:
- Cursor feedback incomplete
- Preview rectangle not displayed
- Persistence not tested
- Only drag/move operations actually used

**User Impact:**
- User attempts to resize task → unclear feedback → cannot complete action
- Violates affordance: "Give clear cursor feedback"

**Correct Production Behavior:**
1. Hover near task edge (14px zone) → cursor changes to ↔ (resize cursor)
2. Drag → preview rectangle shows new dimensions
3. Release → task resized and saved
4. Works for both edge (duration) and position (shift)

**Safest Repair Strategy:**
1. Verify cursor change logic: `setCursor(Qt.SizeHorCursor)` in hover
2. Implement preview rectangle (ghost outline)
3. Test: Resize 10 tasks, verify saved dimensions
4. Add to acceptance test

**Regression Risk:** MEDIUM - Mouse handling is fragile

---

### FINDING 15: AUTO-SHIFT DEPENDENCY BEHAVIOR UNRELIABLE
**Severity:** P1
**Area:** Project Management
**Evidence:**
- Feature exists: Dependency auto-shift when task schedule changes
- Known issue: "dependency auto-shift has not been reliably observed"
- Known issue: "cycle safety must remain"
- No test validates: Change task date → dependent task auto-shifts
- Logic exists in `gantt_dependency_engine.py` but integration unclear

**Root Cause:**
Auto-shift feature coded but:
- Conditions for activation unclear
- Cycle safety not validated
- No test confirms behavior

**User Impact:**
- User changes task date → critical path tasks don't auto-adjust → schedule becomes inconsistent
- Manual rescheduling required → workflow friction

**Correct Production Behavior:**
1. User drags Task A forward by 3 days
2. If Task B depends on A (Finish-to-Start):
   - Task B auto-shifts forward 3 days
   - Unless Task B has hard constraint (do not auto-shift tasks with `due_date` lock)
3. Cycle check: Auto-shift rejected if would create cycle

**Safest Repair Strategy:**
1. Test: Create A→B dependency
2. Change A end date +3 days
3. Assert B start date also +3 days
4. Test cycle case: Reject auto-shift if cycle
5. Add guard: Only auto-shift if no hard constraint

**Regression Risk:** MEDIUM - Dependency logic is complex

---

## P0 BLOCKER LIST

Tasks that must be completed before ANY beta release:

1. **Unit Test Framework** - Implement pytest, 200+ tests
2. **Hourly Gantt Visibility** - Validate and repair
3. **Cross-View Consistency** - Implement formal test, pass
4. **Scene Reconstruction** - Fix hover flicker/disappearance
5. **Task Persistence Guarantee** - Ensure task never appears lost
6. **Database Integrity** - Validate migrations, no orphans, no corruption

---

## MATURITY BREAKDOWN BY DIMENSION

| Dimension | Score | Status | Blocker Issues |
|-----------|-------|--------|-----------------|
| **Data Integrity** | 75/100 | Good | Orphan checks, cycle detection gaps |
| **Core Task Workflow** | 60/100 | Acceptable | Partial (missing subtask inheritance rules) |
| **Gantt Visualization** | 55/100 | At Risk | Hourly visibility, hover flicker, resize |
| **Calendar** | 50/100 | Poor | Multi-day semantics, edit refresh |
| **Focus Mode** | 40/100 | Poor | Workflow incomplete, no persistence |
| **Cross-View Consistency** | 60/100 | Acceptable | No formal test, signal-based OK |
| **UX/Responsiveness** | 65/100 | Good | Toolbar not adaptive to narrow windows |
| **Testing Infrastructure** | 25/100 | Poor | No unit tests, only acceptance |
| **Performance Validation** | 30/100 | Poor | No targets, no benchmarks, no assertions |
| **Internationalization** | 10/100 | None | No architecture, no translation |
| **Accessibility** | 15/100 | Minimal | No keyboard support, no a11y testing |
| **Release Engineering** | 20/100 | Poor | Backup clutter, no package strategy |

---

## 10-PHASE PRODUCTION ROADMAP

### PHASE 0: EMERGENCY STABILIZATION (Now - Week 2, 2 weeks)
**Goal:** Stop regressions, fix data-loss risks

**Must Do:**
- P0-1: Implement hourly Gantt visibility test + fix
- P0-2: Implement cross-view consistency test
- P0-3: Fix scene reconstruction hover flicker
- P0-4: Task backup on suspicious states

**Deliverables:**
- Hourly Gantt validated (acceptance test)
- Scene stability proven (soak test 100 operations)
- Task consistency test passing

---

### PHASE 1: FOUNDATION WORK (Week 3-10, 8 weeks)
**Goal:** Production-ready core infrastructure

**Must Do:**
- P1-1: Unit test framework + 200 unit tests
- P1-2: Focus mode workflow (task selector, persistence)
- P1-3: Calendar multi-day semantics
- P1-4: Dependency cycle detection + audit
- P1-5: Database migration validation
- P1-6: Performance targets + benchmarking
- P1-7: Resize handles usability
- P1-8: Auto-shift reliability + cycle safety
- P1-9: Backup file archive (cleanup)
- P1-10: Error recovery patterns

**Deliverables:**
- 200+ unit tests (70%+ coverage)
- All P0 blockers resolved
- Performance baselines established
- Feature workflows complete

**Files Most Likely to Change:**
- `tests/` - New comprehensive test suite
- `controllers/task_controller.py` - Add commands, validation
- `gantt/gantt_chart.py` - Fix hover, resize, scene handling
- `views/focus_view.py` - Implement full workflow
- `views/calendar_view.py` - Multi-day filtering
- `database.py` - Add migration tests, cycle detection
- `models/task.py` - Add validation invariants

---

### PHASE 2: INTERNATIONALIZATION (Week 11-14, 4 weeks)
**Goal:** Global readiness

**Must Do:**
- Localization architecture
- Extract strings to catalog
- Locale settings (date_format, time_format, week_start, timezone)
- Support: English, Hindi
- Prepare for: European, Arabic/RTL, CJK

**Deliverables:**
- App fully i18n-ready (strings in external files)
- Settings include locale options
- Date/time render based on user preference

---

### PHASE 3: ACCESSIBILITY (Week 15-16, 2 weeks)
**Goal:** WCAG 2.1 AA compliance

**Must Do:**
- Keyboard shortcuts (Tab, Enter, Ctrl+N, Delete, etc.)
- Visible focus indicators
- Accessible labels
- Screen reader testing
- Test with NVDA/JAWS

**Deliverables:**
- Keyboard-navigable application
- Screen reader compatible
- WCAG 2.1 AA audit passing

---

### PHASE 4: ARCHITECTURE REFACTORING (Week 17-20, 4 weeks)
**Goal:** Maintainability

**Must Do:**
- Extract Gantt subcomponents (only after Phase 1 stable)
- Reduce single-file complexity
- Clear architectural boundaries

**Deliverables:**
- Gantt split into 4-5 focused modules
- Test coverage maintained

---

### PHASE 5: PACKAGING & RELEASE (Week 21-22, 2 weeks)
**Goal:** Distributable product

**Must Do:**
- Linux .deb package
- Windows installer
- macOS preparation
- Update strategy
- Crash logging

**Deliverables:**
- Install/upgrade/uninstall validated
- Clean fresh install
- Data preservation on upgrade

---

### PHASE 6: PROFESSIONAL PM FEATURES (Week 23-26, 4 weeks)
**Goal:** Enterprise-ready

**Must Do:**
- Milestones
- Baseline snapshots
- Float/slack calculations
- Multiple dependency types (SS, FF, SF with lag/lead)
- Project health roll-up

**Deliverables:**
- Full project management capability
- Critical path + float visible

---

### PHASE 7: ADVANCED ANALYTICS (Week 27-28, 2 weeks)
**Goal:** Intelligence

**Must Do:**
- Personal: Completion rate, plan adherence, overdue analysis
- Manager: Project health, schedule variance, blockers
- Executive: Program KPIs, risk, delivery confidence

**Deliverables:**
- Dashboard KPIs meaningful and actionable

---

### PHASE 8: SMART ASSISTANCE (Week 29-30, 2 weeks)
**Goal:** Assistive AI

**Must Do:**
- Summarize project status
- Identify schedule risk
- Suggest priorities
- Propose recovery plan
- Recommend optimal scheduling

**Deliverables:**
- AI suggestions (read-only, no mutations without approval)

---

### PHASE 9: SCALE & PERFORMANCE (Week 31-32, 2 weeks)
**Goal:** Handle 10K+ tasks

**Must Do:**
- Row virtualization for Gantt
- Query optimization
- Caching strategy
- Stress test 10K tasks

**Deliverables:**
- App responsive at enterprise scale

---

### PHASE 10: INTERNATIONAL RELEASE (Week 33-36, 4 weeks)
**Goal:** Go global

**Must Do:**
- Translate to European languages
- Test RTL (Arabic) rendering
- Test CJK fonts
- Regional builds

**Deliverables:**
- Multi-language product
- Global ready

---

## TEST MATRIX

### Unit Tests (Phase 1)
```
models/
  └─ test_task.py (30 tests)
  └─ test_project.py (15 tests)

controllers/
  └─ test_task_controller.py (40 tests)
  └─ test_delay_engine.py (25 tests)

gantt/
  └─ test_timescale_engine.py (35 tests)
  └─ test_gantt_dependency_engine.py (30 tests)
  └─ test_gantt_chart_rendering.py (25 tests)

database/
  └─ test_database_crud.py (30 tests)
  └─ test_database_migrations.py (15 tests)

Total: ~245 unit tests
Target coverage: 70%+ of business logic
```

### Integration Tests (Phase 1)
```
Cross-View:
  └─ test_task_consistency_across_views.py (20 tests)

Gantt:
  └─ test_gantt_interaction_workflow.py (15 tests)
  └─ test_gantt_stability_soak.py (10 tests)

Calendar:
  └─ test_calendar_multi_day.py (10 tests)

Focus:
  └─ test_focus_workflow.py (15 tests)

Total: ~70 integration tests
```

### Acceptance Tests (Phase 0/1 - Maintain)
```
Current 30 tests + new:
  └─ test_hourly_gantt_visibility.py
  └─ test_dependency_cycle_detection.py
  └─ test_database_migration_safety.py
  └─ test_task_persistence_guarantee.py

Total: ~34 acceptance tests
```

---

## FILES MOST LIKELY TO CHANGE IN PHASE 1

**Critical Path (Highest Change Risk):**
1. `controllers/task_controller.py` - Add commands, validation
2. `gantt/gantt_chart.py` - Fix hover, resize, scene lifecycle
3. `views/focus_view.py` - Complete workflow
4. `views/calendar_view.py` - Multi-day filtering
5. `database.py` - Add validation, cycle detection

**High Change Risk:**
6. `gantt/gantt_dependency_engine.py` - Auto-shift + cycle logic
7. `models/task.py` - Add invariants, validation
8. `tests/test_suite.py` - Expand acceptance tests

**Moderate Change Risk:**
9. `controllers/delay_engine.py` - Logging, edge cases
10. `gantt/timescale_engine.py` - Hourly mode refinement

---

## FILES THAT MUST NOT BE TOUCHED WITHOUT EXPLICIT JUSTIFICATION

**Sacred (Proven Stable):**
- `app.py` - Entry point, single-instance socket working
- `database.py` (schema parts) - Migration path is precious, don't break
- `models/task.py` (core fields) - Schema depends on these
- `settings/settings_manager.py` - Settings persistence working
- `voice/voice_engine.py` - Offline TTS working, no need to touch
- `animations/companion_animator.py` - Companion working
- `theme_controller.py` (core logic) - Theming working

**Approach:**
- Only add new methods/fields
- Don't remove or rename core logic
- Additions must have regression tests

---

## DATABASE MIGRATION REQUIREMENT

**Question:** Need schema migration?

**Answer:** NO - Not in Phase 0/1

**Justification:**
- Current v8 schema handles:
  - Tasks with full field set
  - Subtasks with nesting
  - Dependencies as JSON array
  - Pins, delays, reminders
- No structural changes required for Phase 1 work
- Focus workflow can store in new `focus_sessions` table (additive, no migration needed)

**If v9 needed later:**
- Only for storage efficiency (e.g., normalize dependencies to separate table)
- Not required for correctness or features
- Defer to Phase 4+

---

## FIRST IMPLEMENTATION PLAN (Phase 0/1 Start)

### Week 1 (Emergency Mode - Hours 1-40)
**Daily standdown metrics:**
- Test suite runs
- No regressions
- Evidence collected

**Specific Tasks:**
1. Day 1-2: Hourly Gantt audit
   - Run Gantt in hourly mode
   - Create 5 hourly tasks
   - Verify visibility
   - Verify navigation
   - Document findings

2. Day 2-3: Scene stability test
   - Create 50-task Gantt
   - Perform 100 operations (drag, resize, zoom, hover)
   - Record: Any flicker? Any disappearance? Any crash?
   - Measure: Frame rate, CPU, memory

3. Day 4-5: Cross-view consistency audit
   - Manual test: Create task → Verify in all 16 views
   - Edit task → Verify update propagation
   - Delete task → Verify removal
   - Document failures

**Deliverable:** Audit report + Evidence video

---

### Week 2 (Unit Test Scaffold - Hours 41-80)
**Specific Tasks:**
1. Create pytest structure:
   - `tests/conftest.py` - Shared fixtures (DB, app context)
   - `tests/unit/` - Unit tests
   - `tests/integration/` - Integration tests
   - `tests/acceptance/` - Acceptance tests (current)

2. Write 20 unit tests for task model:
   - Validation
   - Serialization
   - Status transitions
   - Invariants

3. Write 15 unit tests for delay_engine:
   - Delay calculation
   - Category assignment
   - Edge cases

**Deliverable:** Test framework + 50 passing tests

---

### Week 3-10 (Phase 1 Execution)
See detailed Phase 1 breakdown above.

---

## EVIDENCE COLLECTION STRATEGY

For each defect fixed, capture:
- **Before video:** Show bug reproduction
- **After video:** Show fix in action
- **Code diff:** Highlight changes
- **Test:** New test validating fix
- **Performance:** Before/after metrics (if applicable)

Example:
```
DEFECT: Hourly Gantt shows no tasks

BEFORE:
- Create task: planned_date=2026-08-14, planned_start_time=10:00
- Switch Gantt to Hourly for 2026-08-14
- RESULT: No tasks visible ❌

ROOT CAUSE:
- hourly_filter logic uses planned_date only, ignores planned_start_time
- Task with planned_start_time=10:00 filtered out when viewing 11:00 hour

FIX:
- Change filter: visible_hour = planned_start_time // 60
- Match task.planned_start_time to selected hour

AFTER:
- Create task: planned_date=2026-08-14, planned_start_time=10:00
- Switch Gantt to Hourly for 2026-08-14, navigate to 10:00 hour
- RESULT: Task visible ✅

TEST:
- test_hourly_gantt_task_visibility_by_hour()
- Assertion: Task in hour 10 when started at 10:00

VIDEO EVIDENCE:
- 30-second screencast showing task appearing when navigating to correct hour
```

---

## CONCLUSION

TODO BIRD has a **solid architectural foundation** but needs **rigorous production discipline** across testing, defect remediation, and international/accessibility readiness.

**Do not declare production-ready until:**
1. ✅ All P0 blockers resolved
2. ✅ Unit test suite 200+ tests, 70%+ coverage
3. ✅ Cross-view consistency test passing
4. ✅ Performance baselines established
5. ✅ Internationalization architecture in place
6. ✅ Accessibility audit passing WCAG 2.1 AA
7. ✅ Packaging validated (install/upgrade/uninstall)

**Timeline:** 8-12 weeks to production-ready (Phases 0-5)

**Next Action:** Start Phase 0 Week 1 audit immediately.

---

**Audit Completed:** August 14, 2026
**Next Review:** After Phase 0 completion (Week 2)
