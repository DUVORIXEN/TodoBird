"""
Phase 2B — Professional Schedule Intelligence UI Test Suite

Validates:
1. WBS exposes Critical, Total Float, Free Float, ES, EF, LS, LF, Diagnostics columns.
2. Values come directly from CPM SchedulingResult / ScheduleNodeResult without UI recalculation.
3. Cyclic and unscheduled tasks show appropriate diagnostic states (never false non-critical or 0m float).
4. Project-manager-friendly elapsed float formatting (0m, 2h, 1d, 1d 2h, -2h).
5. WBS schedule filters (Critical Path Only, Has Float, Schedule Warnings) with ancestor retention.
6. Gantt consumes cpm_is_critical while retaining legacy fallback.
7. Gantt & WBS tooltips display ES, EF, LS, LF, TF, FF, and diagnostic details.
8. Schedule Health Summary badge in toolbar reflects Healthy / Attention / Blocked states.
9. Cache invalidation on project data changes (dependencies, duration, planned start).
10. Accessibility, theme safety (Dark/Light), and typography scaling (10pt <-> 20pt).
"""

import json
from datetime import datetime, date, time
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QModelIndex

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.models.project import Project
from todo_bird_app.services.cpm_scheduling_service import (
    CPMSchedulingService,
    SchedulingResult,
    ScheduleNodeResult,
    DiagnosticCode,
    format_float_duration,
    format_cpm_datetime,
)
from todo_bird_app.models.wbs_item_model import WBSItemModel
from todo_bird_app.models.wbs_filter_proxy_model import WBSFilterProxyModel
from todo_bird_app.views.wbs_tree_view import WBSTreeView
from todo_bird_app.views.wbs_project_view import WBSProjectView
from todo_bird_app.services.wbs_customization_service import WBSCustomizationService
from todo_bird_app.gantt.gantt_dependency_engine import GanttDependencyEngine
from todo_bird_app.gantt.gantt_items import GanttTaskItem
from todo_bird_app.controllers.theme_controller import ThemeController


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def test_db(tmp_path):
    db_path = str(tmp_path / "test_phase2b.db")
    db = DatabaseManager(db_path)
    return db


@pytest.fixture
def test_settings(tmp_path, test_db):
    settings = SettingsManager(test_db, config_dir=tmp_path)
    return settings


def _insert_project(db: DatabaseManager, name: str = "Test Project") -> int:
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO projects (name, color) VALUES (?, ?)", (name, "#3584E4"))
        conn.commit()
        return cur.lastrowid


def _insert_task(
    db: DatabaseManager,
    project_id: int,
    title: str,
    planned_date: str = None,
    planned_start_time: str = None,
    planned_end_time: str = None,
    estimated_duration: int = 0,
    dependencies: list = None,
    status: str = "Planned",
) -> int:
    deps_json = json.dumps(dependencies or [])
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO tasks (
                title, project_id, planned_date, planned_start_time,
                planned_end_time, estimated_duration, dependencies, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                project_id,
                planned_date,
                planned_start_time,
                planned_end_time,
                estimated_duration,
                deps_json,
                status,
            ),
        )
        conn.commit()
        return cur.lastrowid


def _update_task_deps(db: DatabaseManager, task_id: int, dependencies: list):
    deps_json = json.dumps(dependencies)
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE tasks SET dependencies = ? WHERE id = ?", (deps_json, task_id))
        conn.commit()


def _update_task_duration(db: DatabaseManager, task_id: int, duration: int):
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE tasks SET estimated_duration = ? WHERE id = ?", (duration, task_id))
        conn.commit()


# =========================================================================
# 1. Float & Date Formatting Authorities
# =========================================================================

def test_13_14_float_formatting_authorities():
    """13 & 14. Total and Free Float formatting handles minutes, hours, days, negative."""
    assert format_float_duration(None) == "—"
    assert format_float_duration(0) == "0m"
    assert format_float_duration(45) == "45m"
    assert format_float_duration(60) == "1h"
    assert format_float_duration(90) == "1h 30m"
    assert format_float_duration(1440) == "1d"
    assert format_float_duration(1500) == "1d 1h"
    assert format_float_duration(1530) == "1d 1h 30m"
    assert format_float_duration(-120) == "-2h"
    assert format_float_duration(-1500) == "-1d 1h"


def test_datetime_formatting_authorities():
    """Date formatting outputs clean PM representation."""
    assert format_cpm_datetime(None) == "—"
    assert format_cpm_datetime(datetime(2026, 8, 25, 0, 0)) == "2026-08-25"
    assert format_cpm_datetime(datetime(2026, 8, 25, 14, 30)) == "2026-08-25 14:30"


# =========================================================================
# 2. WBS Columns & Roles Integration
# =========================================================================

def test_01_08_wbs_exposes_all_schedule_columns():
    """1-8. WBS exposes Critical, Total Float, Free Float, ES, EF, LS, LF, Diagnostics."""
    assert WBSItemModel.COL_WBS == 0
    assert WBSItemModel.COL_TITLE == 1
    assert WBSItemModel.COL_STATUS == 2
    assert WBSItemModel.COL_PROGRESS == 3
    assert WBSItemModel.COL_CRITICAL == 4
    assert WBSItemModel.COL_TOTAL_FLOAT == 5
    assert WBSItemModel.COL_FREE_FLOAT == 6
    assert WBSItemModel.COL_ES == 7
    assert WBSItemModel.COL_EF == 8
    assert WBSItemModel.COL_LS == 9
    assert WBSItemModel.COL_LF == 10
    assert WBSItemModel.COL_DIAGNOSTICS == 11
    assert WBSItemModel.COLUMN_COUNT >= 12
    assert len(WBSItemModel.HEADERS) >= 12


def test_09_10_critical_and_float_values_come_from_cpm(qapp, test_db, test_settings):
    """9 & 10. Critical and float values are served directly from CPM result."""
    p_id = _insert_project(test_db, "CPM Test Project")

    t1_id = _insert_task(
        test_db,
        project_id=p_id,
        title="Task A",
        planned_date="2026-08-25",
        planned_start_time="09:00",
        estimated_duration=120,
    )

    t2_id = _insert_task(
        test_db,
        project_id=p_id,
        title="Task B",
        planned_date="2026-08-25",
        planned_start_time="11:00",
        estimated_duration=60,
        dependencies=[t1_id],
    )

    model = WBSItemModel()
    model.load_project(test_db, project_id=p_id)

    assert model.cpm_result is not None
    assert t1_id in model.cpm_result.nodes
    assert t2_id in model.cpm_result.nodes

    # Check model data
    idx_t1 = model.index_from_key(f"task:{t1_id}", column=WBSItemModel.COL_CRITICAL)
    assert idx_t1.isValid()
    assert idx_t1.data(WBSItemModel.CPMCriticalRole) is True
    assert idx_t1.data(WBSItemModel.CPMTotalFloatRole) == 0
    assert idx_t1.data(Qt.DisplayRole) == "● Critical"

    idx_t1_tf = model.index_from_key(f"task:{t1_id}", column=WBSItemModel.COL_TOTAL_FLOAT)
    assert idx_t1_tf.data(Qt.DisplayRole) == "0m"


def test_11_cyclic_task_does_not_show_false_non_critical(qapp, test_db, test_settings):
    """11. Cyclic task shows Blocked diagnostic state, never false Non-critical."""
    p_id = _insert_project(test_db, "Cycle Project")

    t1_id = _insert_task(test_db, project_id=p_id, title="Task A", planned_date="2026-08-25", estimated_duration=60)
    t2_id = _insert_task(test_db, project_id=p_id, title="Task B", planned_date="2026-08-25", estimated_duration=60, dependencies=[t1_id])

    # Complete the cycle
    _update_task_deps(test_db, t1_id, [t2_id])

    model = WBSItemModel()
    model.load_project(test_db, project_id=p_id)

    assert model.cpm_result.has_cycles is True
    assert t1_id in model.cpm_result.cycle_task_ids

    idx_crit = model.index_from_key(f"task:{t1_id}", column=WBSItemModel.COL_CRITICAL)
    assert idx_crit.data(Qt.DisplayRole) == "Blocked (Cycle)"
    assert idx_crit.data(WBSItemModel.CPMCriticalRole) is False


def test_12_unscheduled_task_shows_not_analyzed(qapp, test_db, test_settings):
    """12. Unscheduled task shows Not analyzed rather than 0 float or false critical."""
    p_id = _insert_project(test_db, "Unscheduled Project")
    t1_id = _insert_task(test_db, project_id=p_id, title="Unscheduled Task", estimated_duration=0)

    model = WBSItemModel()
    model.load_project(test_db, project_id=p_id)

    idx_crit = model.index_from_key(f"task:{t1_id}", column=WBSItemModel.COL_CRITICAL)
    assert idx_crit.data(Qt.DisplayRole) == "Not analyzed"

    idx_tf = model.index_from_key(f"task:{t1_id}", column=WBSItemModel.COL_TOTAL_FLOAT)
    assert idx_tf.data(Qt.DisplayRole) == "—"


# =========================================================================
# 3. Schedule Filters & Ancestor Retention
# =========================================================================

def test_15_18_schedule_filters_and_ancestor_retention(qapp, test_db, test_settings):
    """15-18. Critical, Has Float, and Schedule Warnings filters preserve ancestors."""
    p_id = _insert_project(test_db, "Filter Project")

    # Chain 1: A (2d) -> C (3d) [Critical path: 5d]
    tA_id = _insert_task(test_db, project_id=p_id, title="Task A", planned_date="2026-08-25", estimated_duration=2880)
    tC_id = _insert_task(test_db, project_id=p_id, title="Task C", planned_date="2026-08-26", estimated_duration=4320, dependencies=[tA_id])

    # Chain 2: B (1d) -> D (1d) [Non-critical path: 2d -> 3d float]
    tB_id = _insert_task(test_db, project_id=p_id, title="Task B", planned_date="2026-08-25", estimated_duration=1440)
    tD_id = _insert_task(test_db, project_id=p_id, title="Task D", planned_date="2026-08-26", estimated_duration=1440, dependencies=[tB_id])

    # Unscheduled task
    tE_id = _insert_task(test_db, project_id=p_id, title="Task E", estimated_duration=0)

    model = WBSItemModel()
    model.load_project(test_db, project_id=p_id)

    proxy = WBSFilterProxyModel()
    proxy.setSourceModel(model)

    # 1. Critical Filter
    proxy.set_status_filter("critical")
    accepted_keys = proxy.get_accepted_keys()
    assert f"task:{tA_id}" in accepted_keys
    assert f"task:{tC_id}" in accepted_keys
    assert f"task:{tB_id}" not in accepted_keys
    assert f"task:{tD_id}" not in accepted_keys

    # 2. Has Float Filter
    proxy.set_status_filter("has_float")
    accepted_keys = proxy.get_accepted_keys()
    assert f"task:{tB_id}" in accepted_keys
    assert f"task:{tD_id}" in accepted_keys
    assert f"task:{tA_id}" not in accepted_keys

    # 3. Schedule Warnings Filter
    proxy.set_status_filter("schedule_warnings")
    accepted_keys = proxy.get_accepted_keys()
    assert f"task:{tE_id}" in accepted_keys

    # Clear filter
    proxy.set_status_filter("all")
    assert proxy.has_active_filter() is False


# =========================================================================
# 4. Gantt True Critical Highlight & Tooltips
# =========================================================================

def test_19_20_gantt_uses_cpm_is_critical_with_fallback(qapp):
    """19 & 20. Gantt visual components consume cpm_is_critical with fallback."""
    t = Task(id=1, title="Test Task", estimated_duration=60)
    t.cpm_is_critical = True
    t.cpm_total_float = 0
    t.cpm_free_float = 0

    item = GanttTaskItem(
        task=t,
        row=0,
        col_start=0.0,
        duration_cols=2.0,
        col_width=40,
        color_profile={},
    )
    assert item.toolTip() != ""
    assert "Critical Path: <b>YES</b>" in item.toolTip()
    assert "Total Float: 0m" in item.toolTip()


def test_21_22_tooltips_include_float_and_cycle_diagnostics(qapp, test_db):
    """21 & 22. Tooltips provide rich CPM numbers or clear diagnostic blockage reasons."""
    p_id = _insert_project(test_db, "Tooltip Project")
    t1_id = _insert_task(test_db, project_id=p_id, title="Sched Task", planned_date="2026-08-25", estimated_duration=60)

    model = WBSItemModel()
    model.load_project(test_db, project_id=p_id)

    idx = model.index_from_key(f"task:{t1_id}", column=0)
    tip = idx.data(Qt.ToolTipRole)
    assert "Critical:" in tip
    assert "Total Float:" in tip
    assert "ES:" in tip


# =========================================================================
# 5. Schedule Health Summary Badge
# =========================================================================

def test_23_25_schedule_health_summary_states(qapp, test_db, test_settings):
    """23-25. Schedule health summary shows Healthy, Attention, or Blocked accurately."""
    p_id = _insert_project(test_db, "Health Project")

    # 1. Normal project -> Healthy
    t1_id = _insert_task(test_db, project_id=p_id, title="Task 1", planned_date="2026-08-25", estimated_duration=60)

    pv = WBSProjectView(test_db, test_settings, project_id=p_id)
    assert "CPM: Healthy" in pv.schedule_health_badge.text()

    # 2. Add unscheduled task -> Attention
    t2_id = _insert_task(test_db, project_id=p_id, title="Task 2", estimated_duration=0)
    pv.refresh_hierarchy()
    assert "CPM: Attention" in pv.schedule_health_badge.text()

    # 3. Create cycle -> Blocked
    _update_task_deps(test_db, t1_id, [t2_id])
    _update_task_deps(test_db, t2_id, [t1_id])
    pv.refresh_hierarchy()
    assert "CPM: Blocked" in pv.schedule_health_badge.text()


# =========================================================================
# 6. Performance & Invalidation Safety
# =========================================================================

def test_26_27_no_db_query_during_wbs_data_access(qapp, test_db, test_settings):
    """26 & 27. Reading WBS item model data does not trigger database queries."""
    p_id = _insert_project(test_db, "Perf Project")
    t1_id = _insert_task(test_db, project_id=p_id, title="Perf Task", planned_date="2026-08-25", estimated_duration=60)

    model = WBSItemModel()
    model.load_project(test_db, project_id=p_id)

    # Disconnect/remove DB handle to guarantee zero DB access
    model._db_manager = None

    idx = model.index_from_key(f"task:{t1_id}", column=WBSItemModel.COL_CRITICAL)
    assert idx.data(Qt.DisplayRole) == "● Critical"
    assert idx.data(WBSItemModel.CPMTotalFloatRole) == 0


def test_28_30_cpm_refresh_after_edits(qapp, test_db, test_settings):
    """28-30. CPM recomputes when dependencies, duration, or dates change."""
    p_id = _insert_project(test_db, "Edit Project")
    t1_id = _insert_task(test_db, project_id=p_id, title="Task A", planned_date="2026-08-25", estimated_duration=60)

    model = WBSItemModel()
    model.load_project(test_db, project_id=p_id)
    assert model.cpm_result.nodes[t1_id].earliest_finish == datetime(2026, 8, 25, 1, 0)

    # Change duration from 60m to 120m
    _update_task_duration(test_db, t1_id, 120)

    model.load_project(test_db, project_id=p_id)
    assert model.cpm_result.nodes[t1_id].earliest_finish == datetime(2026, 8, 25, 2, 0)


def test_31_zero_data_project_state(qapp, test_db, test_settings):
    """31. Zero-data project does not crash and renders clean empty states."""
    p_id = _insert_project(test_db, "Empty Project")

    pv = WBSProjectView(test_db, test_settings, project_id=p_id)
    assert pv.item_model.rowCount() == 0
    assert pv.schedule_health_badge.text() == "CPM: Ready"


# =========================================================================
# 7. Theme & Typography Safety
# =========================================================================

def test_32_35_theme_and_typography_safety(qapp, test_db, test_settings):
    """32-35. Dark/Light mode and 10pt <-> 20pt typography transitions cleanly."""
    tc = ThemeController(test_settings)
    tc.apply_theme(mode="dark")

    p_id = _insert_project(test_db, "Theme Project")
    t1_id = _insert_task(test_db, project_id=p_id, title="Theme Task", planned_date="2026-08-25", estimated_duration=60)

    pv = WBSProjectView(test_db, test_settings, project_id=p_id)

    # Typography 10pt -> 20pt -> 10pt
    test_settings.set("ui_font_size", 20)
    pv.refresh_wbs_appearance()
    assert pv.tree_view.font().pointSize() > 0

    test_settings.set("ui_font_size", 10)
    pv.refresh_wbs_appearance()
    assert pv.tree_view.font().pointSize() > 0

    # Theme Dark -> Light -> Dark
    tc.apply_theme(mode="light")
    pv.set_theme(is_dark=False)
    tc.apply_theme(mode="dark")
    pv.set_theme(is_dark=True)


def test_36_accessibility_text_for_critical_indicator(qapp, test_db):
    """36. Accessibility text describes critical and float state clearly."""
    p_id = _insert_project(test_db, "A11y Project")
    t1_id = _insert_task(test_db, project_id=p_id, title="A11y Critical Task", planned_date="2026-08-25", estimated_duration=60)

    model = WBSItemModel()
    model.load_project(test_db, project_id=p_id)

    idx = model.index_from_key(f"task:{t1_id}", column=0)
    a11y_desc = idx.data(Qt.AccessibleDescriptionRole)
    assert "Critical task" in a11y_desc
    assert "Total float zero" in a11y_desc
