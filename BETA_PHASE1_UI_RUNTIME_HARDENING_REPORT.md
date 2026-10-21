# Todo Bird Beta: Phase 1 UI Runtime Hardening Report

**Audit & Repair Date:** 2026-09-18  
**Release Stage:** Parallel Pilot 1  
**Final Classification:** `todo_bird_phase1_ui_runtime_hardening_repaired_human_witness_required`

---

## 1. Root Cause Summary
- **Defect A (Settings Dashboard Tab):** `_populate_dashboard_settings` was duplicated three times due to past automated patch scripts. One copy was misplaced inside `GreetingEditDialog`, and an obsolete copy inside `SettingsView` shadowed the canonical version with reorder controls. Crucially, `QListWidget` and `QListWidgetItem` were omitted from imports, and `_populate_dashboard_settings(dashboard_layout)` was never invoked in `_init_ui`, leaving the Dashboard tab blank and crash-prone.
- **Defect B (Unsafe Qt Layout Clearing):** Multiple views relied on raw `while layout.count(): item = layout.takeAt(0); if item.widget(): item.widget().deleteLater()` loops without unparenting, recursive layout destruction, or deleting `QLayoutItem` wrappers, risking dangling pointers and glibc `free(): invalid pointer` crashes.
- **Defect C (Dashboard World Clock Lifecycle):** `self.clock_timer` in `DashboardView` lacked deterministic stopping on `cleanup()`, and `_update_clock_times_only()` did not validate widget validity via `shiboken6.isValid()` or catch `RuntimeError: Internal C++ object already deleted`, exposing the application to crashes if widgets were deleted asynchronously.

---

## 2. Production Files Modified
1. [`todo_bird_app/views/settings_view.py`](file:///home/athidhi_onlg/todo_bird/todo_bird_app/views/settings_view.py)
2. [`todo_bird_app/views/dashboard_view.py`](file:///home/athidhi_onlg/todo_bird/todo_bird_app/views/dashboard_view.py)
3. [`todo_bird_app/views/calendar_view.py`](file:///home/athidhi_onlg/todo_bird/todo_bird_app/views/calendar_view.py)
4. [`todo_bird_app/views/projects_view.py`](file:///home/athidhi_onlg/todo_bird/todo_bird_app/views/projects_view.py)
5. [`todo_bird_app/widgets/work_effort_editor.py`](file:///home/athidhi_onlg/todo_bird/todo_bird_app/widgets/work_effort_editor.py)
6. [`todo_bird_app/tests/test_phase1_ui_runtime_hardening.py`](file:///home/athidhi_onlg/todo_bird/todo_bird_app/tests/test_phase1_ui_runtime_hardening.py) *(New test suite)*

---

## 3. Duplicate Method & Import Cleanup in SettingsView
- **Imports Added:** Added `QListWidget` and `QListWidgetItem` to `from PySide6.QtWidgets import (...)`.
- **Misplaced Duplicate Removed:** Removed the orphaned copy of `_populate_dashboard_settings` from lines 64–146 inside `GreetingEditDialog`.
- **Obsolete Shadowing Copy Removed:** Removed the legacy copy from lines 540–622 inside `SettingsView`.
- **Canonical Implementation Preserved:** Preserved the complete implementation at line 219 (with `QListWidget.InternalMove`, Move Up/Down buttons, and `_on_clocks_reordered`).
- **Tab Population Wired:** Added `self._populate_dashboard_settings(dashboard_layout)` immediately following the creation of `dashboard_layout` in `_init_ui`.

---

## 4. Layout Clearing Normalization Sites
Replaced proven unsafe raw `takeAt(0)` loops with canonical `clear_layout(layout)`:
- `dashboard_view.py`: `_apply_layout_preset` row layout clearing replaced with `clear_layout(self.layout)`. Reordering in `_rebuild_kpi_grid` safely preserved.
- `calendar_view.py`: `update_task_list` / `refresh_data` task list clearing replaced with `clear_layout(self.task_list_layout)`.
- `projects_view.py`: `load_project_tasks` task list clearing replaced with `clear_layout(self.task_list_layout)`.
- `work_effort_editor.py`: `_rebuild_custom_table` custom table clearing replaced with `clear_layout(self.custom_alloc_layout)`.

---

## 5. Dashboard World Clock Lifecycle & Stale-Pointer Guard
- **Deterministic Teardown:** In `DashboardView.cleanup()`, `self.clock_timer.stop()` is explicitly called when active, and `self._clock_widgets` is cleared to release references.
- **Stale-Pointer Safety:** In `_update_clock_times_only()`:
  - Verifies timer is active before processing.
  - Inspects `shiboken6.isValid(widget)` where available.
  - Traps `RuntimeError` matching `"Internal C++ object"` or `"already deleted"` to prevent crashes on deferred-deleted objects.
  - Prunes deleted objects from `self._clock_widgets`.

---

## 6. Critical Invariants Preserved
- No modifications made to scheduling semantics, CPM algorithms, or WBS mutations.
- No modifications made to `TaskController` event bus ownership or reminder polling intervals.
- The canonical Gantt scene-clear ordering was strictly preserved:
  ```python
  self.current_time_line_item = None
  self._resize_preview = None
  self._resize_item = None
  self._drag_item = None
  self._dependency_graphics = []
  self._rendered_task_items = {}
  self.scene.clear()
  ```

---

## 7. Production Database Safety Verification
- **Target DB:** [`todo_bird_app/data/todo_bird.db`](file:///home/athidhi_onlg/todo_bird/todo_bird_app/data/todo_bird.db)
- **Pre-Repair SHA-256:** `1057930f3cf85c99c580609784361df379339db590bc4ba1dbc87f67ae9d4514`
- **Post-Repair SHA-256:** `1057930f3cf85c99c580609784361df379339db590bc4ba1dbc87f67ae9d4514`
- **Result:** Exact match. Zero mutations to production database.

---

## 8. Targeted Test Coverage
New dedicated test module [`todo_bird_app/tests/test_phase1_ui_runtime_hardening.py`](file:///home/athidhi_onlg/todo_bird/todo_bird_app/tests/test_phase1_ui_runtime_hardening.py) executed and passed (12/12):
1. `test_01_settings_view_instantiates_and_tab_count`
2. `test_02_settings_dashboard_tab_populated_not_blank`
3. `test_03_populate_dashboard_settings_exists_exactly_once`
4. `test_04_dashboard_settings_reorder_controls_function_without_error`
5. `test_05_dashboard_clock_timer_starts_correctly`
6. `test_06_dashboard_cleanup_stops_clock_timer_and_clears_widgets`
7. `test_07_dashboard_clock_update_skips_invalid_or_deleted_widget`
8. `test_08_no_duplicate_clock_timer_created`
9. `test_09_calendar_view_rebuilds_layout_cleanly`
10. `test_10_projects_view_rebuilds_layout_cleanly`
11. `test_11_work_effort_editor_rebuilds_custom_table_cleanly`
12. `test_12_clean_shutdown`
Adjacent targeted suite (`test_settings*`, `test_dashboard*`, `test_world_clock*`): **93/93 PASSED**.

---

## 9. Final Isolated Regression Suite Metrics
- **Command:** `python3 tools/run_isolated_pytest.py`
- **Total Test Files Executed:** 139
- **Completed Files:** 139
- **Total Tests Passed:** 3,241
- **Tests Failed:** 0
- **Tests Errors:** 0
- **Tests Skipped:** 0
- **Elapsed Wall-Clock Time:** 383.354s
- **Peak RSS:** 784,308 KB
- **Final Summary JSON Path:** [`build/test_reports/isolated_pytest_summary.json`](file:///home/athidhi_onlg/todo_bird/build/test_reports/isolated_pytest_summary.json)

---

## 10. Remaining Human Witness Verification
The following items remain for the human release gatekeeper to witness:
- [ ] Open Settings → **Dashboard** tab and verify the World Clocks card is populated and interactive.
- [ ] Test reordering world clocks using **Move Up**, **Move Down**, and drag-and-drop.
- [ ] Verify that Dashboard header world clocks tick normally at their configured interval.
- [ ] Switch between sections (Dashboard, Calendar, Projects, Settings) and confirm no flickering, crashes, or `free(): invalid pointer` errors occur.
- [ ] Verify clean shutdown on closing the application window.
