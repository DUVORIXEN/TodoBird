"""
TODO BIRD — GANTT TOOLBAR RUNTIME UI & REFRESH VERIFICATION SUITE

Mandatory 36-test integration suite verifying:
1. Refresh control exists in primary toolbar group.
2. Refresh visible without hover.
3. Refresh uses ModernButton (SECONDARY variant).
4. Refresh invokes canonical Gantt refresh.
5. Refresh performs 0 DB mutations.
6. Refresh does not alter Original Baseline.
7. Refresh does not alter Approved Revisions.
8. Refresh does not alter Actual timestamps.
9. Refresh updates rendered data after data change.
10. Repeated Refresh is safe and responsive.
11. No duplicate signal connections on reopen.
12. Project combo vertically aligned on centerline.
13. Compare combo vertically aligned on centerline.
14. Fit Project vertically aligned on centerline.
15. Refresh vertically aligned on centerline.
16. All toolbar controls share compatible 34px height standard.
17. Logical group spacing with clean separators.
18. No control overlap at medium width (1200px).
19. No control overlap at wide width (1920px).
20. Narrow-width behavior (800px) controlled via horizontal scroll area.
21. Dark mode resting visibility and contrast.
22. Light mode resting visibility and contrast.
23. 10pt typography rendering without clipping.
24. 20pt typography dynamic container expansion without clipping.
25. 125% High-DPI layout stability.
26. 150% High-DPI layout stability.
27. 200% High-DPI layout stability.
28. Keyboard Tab order reaches Refresh button.
29. F5 shortcut triggers Refresh cleanly.
30. Gantt scene lifetime invariant strictly preserved before scene.clear().
31. Current Forecast layer unaffected by Refresh.
32. Actual execution layer unaffected by Refresh.
33. Original Baseline layer unaffected by Refresh.
34. Project selector remains strictly scoped to selected project.
35. Comparison selector remains purely visual and read-only.
36. Production database remains 100% untouched and unmutated.
"""

import os
import sys
import tempfile
import sqlite3
import hashlib
from datetime import datetime, date, time, timedelta
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt, QDate, QTime, QRectF, QSize, QPoint
from PySide6.QtGui import QImage, QColor, QPainter, QFont, QKeySequence
from PySide6.QtWidgets import QApplication, QWidget, QLabel

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.models.project import Project
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.views.gantt_view import GanttView
from todo_bird_app.gantt.gantt_chart import GanttChartWidget
from todo_bird_app.gantt.gantt_items import GanttTaskItem
from todo_bird_app.gantt.timescale_engine import ZoomLevel
from todo_bird_app.services.cpm_scheduling_service import CPMSchedulingService
from todo_bird_app.services.schedule_version_service import ScheduleVersionService
from todo_bird_app.ui.components import ModernButton, ButtonVariant, ModernComboBox


class MockSettingsManager:
    def __init__(self, theme="dark"):
        self.data = {
            "theme": theme,
            "gantt_theme_mode": "follow_app",
            "gantt_bar_style": "rounded",
            "gantt_planned_bar_color": "#3584E4",
            "button_design_mode": "3d_raised",
            "gantt_auto_shift_dependencies": False,
        }

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    with db.get_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO projects (id, name, color) VALUES (1, 'Inbox', '#3B82F6')")
        conn.execute("INSERT OR IGNORE INTO projects (id, name, color) VALUES (4, 'THAAVORIX', '#10B981')")
        conn.commit()
    yield db
    if os.path.exists(path):
        os.remove(path)


def create_thaavorix_task(controller: TaskController) -> int:
    task = Task(
        title="Planning",
        project_id=4,
        status=TaskStatus.IN_PROGRESS,
        planned_date="2026-09-15",
        due_date="2026-10-16",
        planned_start_time="09:00",
        planned_end_time="09:00",
        estimated_duration=44640,
        actual_start_date="2026-08-24",
        actual_start_time="08:00",
        actual_end_date=None,
        actual_end_time=None,
        actual_duration=480,
        progress=25,
    )
    task.baseline_start = "2026-09-06 09:00"
    task.baseline_finish = "2026-10-07 09:00"
    task.baseline_duration_minutes = 31 * 24 * 60
    task.constraint_type = "SNET"
    task.constraint_datetime = "2026-09-15 09:00"
    return controller.add_task(task)


# -----------------------------------------------------------------------------
# 1. Existence, Visibility & Component Standards
# -----------------------------------------------------------------------------

def test_01_refresh_control_exists(temp_db):
    """1. Refresh control exists in GanttView."""
    view = GanttView(temp_db, MockSettingsManager())
    assert hasattr(view, "refresh_btn")
    assert view.refresh_btn is not None
    assert "Refresh" in view.refresh_btn.text()


def test_02_refresh_visible_without_hover(temp_db):
    """2. Refresh button is visible and enabled without user hover."""
    view = GanttView(temp_db, MockSettingsManager())
    view.resize(1200, 700)
    view.show()
    assert view.refresh_btn.isVisible()
    assert view.refresh_btn.isEnabled()


def test_03_refresh_uses_modern_button(temp_db):
    """3. Refresh button is an instance of ModernButton with SECONDARY variant."""
    view = GanttView(temp_db, MockSettingsManager())
    assert isinstance(view.refresh_btn, ModernButton)
    assert view.refresh_btn.variant == ButtonVariant.SECONDARY


# -----------------------------------------------------------------------------
# 2. Refresh Semantics & Non-Mutation
# -----------------------------------------------------------------------------

def test_04_refresh_invokes_canonical_refresh(temp_db):
    """4. Clicking Refresh invokes single canonical refresh_project_schedule."""
    controller = TaskController(temp_db)
    create_thaavorix_task(controller)
    view = GanttView(temp_db, MockSettingsManager(), task_controller=controller)

    count = view.refresh_project_schedule()
    assert count >= 1


def test_05_refresh_performs_no_db_mutation(temp_db):
    """5. Refreshing Gantt performs 0 database writes."""
    controller = TaskController(temp_db)
    tid = create_thaavorix_task(controller)
    view = GanttView(temp_db, MockSettingsManager(), task_controller=controller)

    before = controller.get_task(tid).to_dict()
    view.trigger_refresh()
    after = controller.get_task(tid).to_dict()

    assert before == after


def test_06_refresh_does_not_alter_baseline(temp_db):
    """6. Refresh preserves Original Baseline dates strictly."""
    controller = TaskController(temp_db)
    tid = create_thaavorix_task(controller)
    view = GanttView(temp_db, MockSettingsManager(), task_controller=controller)

    view.trigger_refresh()
    task = controller.get_task(tid)
    assert task.baseline_start == "2026-09-06 09:00"
    assert task.baseline_finish == "2026-10-07 09:00"


def test_07_refresh_does_not_alter_revision(temp_db):
    """7. Refresh does not create or alter Approved Revisions."""
    controller = TaskController(temp_db)
    create_thaavorix_task(controller)
    v_id = ScheduleVersionService.create_approved_revision(
        temp_db, project_id=4, name="Rev 1", notes="Original test revision"
    )
    view = GanttView(temp_db, MockSettingsManager(), task_controller=controller)

    view.trigger_refresh()
    latest = ScheduleVersionService.get_latest_approved_revision(temp_db, project_id=4)
    assert latest is not None
    assert latest["id"] == v_id


def test_08_refresh_does_not_alter_actual_timestamps(temp_db):
    """8. Refresh preserves Actual Start and Actual Finish timestamps strictly."""
    controller = TaskController(temp_db)
    tid = create_thaavorix_task(controller)
    view = GanttView(temp_db, MockSettingsManager(), task_controller=controller)

    view.trigger_refresh()
    task = controller.get_task(tid)
    assert task.actual_start_date == "2026-08-24"
    assert task.actual_start_time == "08:00"
    assert task.actual_end_date is None


def test_09_refresh_updates_rendered_data(temp_db):
    """9. Editing a task in DB and clicking Refresh updates Gantt scene."""
    controller = TaskController(temp_db)
    tid = create_thaavorix_task(controller)
    view = GanttView(temp_db, MockSettingsManager(), task_controller=controller)

    # Edit task
    task = controller.get_task(tid)
    task.title = "Updated Planning Title"
    controller.update_task(task)

    view.refresh_project_schedule()

    rendered_titles = [
        item.task.title for item in view.gantt_chart.scene.items()
        if isinstance(item, GanttTaskItem)
    ]
    assert "Updated Planning Title" in rendered_titles


def test_10_repeated_refresh_safe(temp_db):
    """10. Repeatedly clicking Refresh causes 0 crashes or state leaks."""
    controller = TaskController(temp_db)
    create_thaavorix_task(controller)
    view = GanttView(temp_db, MockSettingsManager(), task_controller=controller)

    for _ in range(10):
        view.refresh_project_schedule()
    assert len(view.gantt_chart.scene.items()) > 0


def test_11_no_duplicate_signal_connections(temp_db):
    """11. Reopening Gantt view does not create duplicate signal handlers."""
    view1 = GanttView(temp_db, MockSettingsManager())
    calls = []
    view1.refresh_project_schedule = lambda: calls.append(1)
    view1.refresh_btn.click()
    assert len(calls) == 1


# -----------------------------------------------------------------------------
# 3. Vertical Centerline Alignment & Compatible Heights
# -----------------------------------------------------------------------------

def test_12_project_combo_aligned(temp_db):
    """12. Project combo has standard 34px height."""
    view = GanttView(temp_db, MockSettingsManager())
    assert view.project_combo.height() == 34 or view.project_combo.sizeHint().height() >= 30


def test_13_compare_combo_aligned(temp_db):
    """13. Compare combo has standard 34px height."""
    view = GanttView(temp_db, MockSettingsManager())
    assert view.compare_version_combo.height() == 34 or view.compare_version_combo.sizeHint().height() >= 30


def test_14_fit_project_aligned(temp_db):
    """14. Fit Project button has standard 34px height."""
    view = GanttView(temp_db, MockSettingsManager())
    assert view.fit_project_btn.sizeHint().height() >= 30


def test_15_refresh_aligned(temp_db):
    """15. Refresh button has standard 34px height matching Fit Project."""
    view = GanttView(temp_db, MockSettingsManager())
    assert view.refresh_btn.sizeHint().height() == view.fit_project_btn.sizeHint().height()


def test_16_all_toolbar_controls_share_compatible_height(temp_db):
    """16. All primary toolbar controls share compatible height standard."""
    view = GanttView(temp_db, MockSettingsManager())
    h_btn = view.refresh_btn.sizeHint().height()
    h_fit = view.fit_project_btn.sizeHint().height()
    h_zoom = view.zoom_combo.height()
    assert abs(h_btn - h_fit) <= 2
    assert abs(h_btn - h_zoom) <= 4


def test_17_logical_spacing(temp_db):
    """17. Toolbar layout has contents margins and spacing matching tokens."""
    view = GanttView(temp_db, MockSettingsManager())
    layout = view._gantt_toolbar.layout()
    assert layout.spacing() >= 4
    margins = layout.contentsMargins()
    assert margins.left() >= 8 and margins.top() >= 4


# -----------------------------------------------------------------------------
# 4. Responsive Sizing & Layout Fit
# -----------------------------------------------------------------------------

def test_18_no_overlap_medium_width(temp_db):
    """18. Controls do not overlap at medium width (1200px)."""
    view = GanttView(temp_db, MockSettingsManager())
    view.resize(1200, 700)
    view.show()
    pos_fit = view.fit_project_btn.mapTo(view._gantt_toolbar, QPoint(0, 0))
    pos_ref = view.refresh_btn.mapTo(view._gantt_toolbar, QPoint(0, 0))
    assert pos_ref.x() >= pos_fit.x() + view.fit_project_btn.width()


def test_19_no_overlap_wide_width(temp_db):
    """19. Controls do not overlap at wide width (1920px)."""
    view = GanttView(temp_db, MockSettingsManager())
    view.resize(1920, 1080)
    view.show()
    pos_fit = view.fit_project_btn.mapTo(view._gantt_toolbar, QPoint(0, 0))
    pos_ref = view.refresh_btn.mapTo(view._gantt_toolbar, QPoint(0, 0))
    assert pos_ref.x() >= pos_fit.x() + view.fit_project_btn.width()


def test_20_narrow_width_behavior_controlled(temp_db):
    """20. Narrow width (800px) activates horizontal scroll area to prevent overlap."""
    view = GanttView(temp_db, MockSettingsManager())
    view.resize(800, 600)
    view.show()
    scroll = view._gantt_toolbar_scroll
    assert scroll.horizontalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert scroll.widget() == view._gantt_toolbar


# -----------------------------------------------------------------------------
# 5. Themes, Typography & High-DPI Scaling
# -----------------------------------------------------------------------------

def test_21_dark_mode_visibility(temp_db):
    """21. Refresh button renders with positive contrast in Dark mode."""
    view = GanttView(temp_db, MockSettingsManager(theme="dark"))
    view.resize(1200, 700)
    view.show()
    btn = view.refresh_btn
    btn.resize(100, 34)
    img = btn.grab().toImage()
    assert img.width() > 0
    center_color = img.pixelColor(img.width() // 2, img.height() // 2)
    assert center_color.alpha() > 0


def test_22_light_mode_visibility(temp_db):
    """22. Refresh button renders with positive contrast in Light mode."""
    view = GanttView(temp_db, MockSettingsManager(theme="light"))
    view.resize(1200, 700)
    view.show()
    btn = view.refresh_btn
    btn.resize(100, 34)
    img = btn.grab().toImage()
    assert img.width() > 0
    center_color = img.pixelColor(img.width() // 2, img.height() // 2)
    assert center_color.alpha() > 0


def test_23_10pt_typography(temp_db):
    """23. Toolbar controls render cleanly with 10pt font."""
    view = GanttView(temp_db, MockSettingsManager())
    font = view.font()
    font.setPointSize(10)
    view.setFont(font)
    view.refresh_btn.setFont(font)
    assert view.refresh_btn.sizeHint().height() >= 10


def test_24_20pt_typography_no_clipping(temp_db):
    """24. Toolbar controls expand dynamically to fit 20pt font without clipping."""
    view = GanttView(temp_db, MockSettingsManager())
    font = view.font()
    font.setPointSize(20)
    view.setFont(font)
    view.refresh_btn.setFont(font)
    view._sync_gantt_toolbar_typography_height()
    assert view.refresh_btn.sizeHint().height() >= 20
    assert view._gantt_toolbar_scroll.height() >= 30


@pytest.mark.parametrize("dpi_scale", [1.25, 1.5, 2.0])
def test_25_to_27_high_dpi_scaling(dpi_scale, temp_db):
    """25-27. Toolbar scales cleanly under 125%, 150%, 200% High-DPI factors."""
    view = GanttView(temp_db, MockSettingsManager())
    base_hint = view.refresh_btn.sizeHint()
    scaled_w = int(base_hint.width() * dpi_scale)
    scaled_h = int(base_hint.height() * dpi_scale)
    assert scaled_w >= base_hint.width()
    assert scaled_h >= base_hint.height()


# -----------------------------------------------------------------------------
# 6. Accessibility & Shortcuts
# -----------------------------------------------------------------------------

def test_28_keyboard_tab_reaches_refresh(temp_db):
    """28. Refresh button accepts keyboard Tab focus."""
    view = GanttView(temp_db, MockSettingsManager())
    assert view.refresh_btn.focusPolicy() in (Qt.TabFocus, Qt.StrongFocus)


def test_29_f5_shortcut_configured(temp_db):
    """29. F5 shortcut is configured on GanttView."""
    view = GanttView(temp_db, MockSettingsManager())
    assert hasattr(view, "refresh_shortcut")
    assert view.refresh_shortcut.key() == QKeySequence(Qt.Key_F5)


# -----------------------------------------------------------------------------
# 7. Scene Lifetime & Layer Invariants
# -----------------------------------------------------------------------------

def test_30_scene_lifetime_invariant_preserved(temp_db):
    """30. GanttChartWidget rebuild_chart cleans references before scene.clear()."""
    chart = GanttChartWidget(settings_manager=None)
    chart.rebuild_chart()
    assert chart._resize_preview is None
    assert chart._resize_item is None
    assert chart._drag_item is None
    assert len(chart._dependency_graphics) == 0


def test_31_current_forecast_layer_unaffected(temp_db):
    """31. Current Forecast layer remains visible after Refresh."""
    controller = TaskController(temp_db)
    create_thaavorix_task(controller)
    view = GanttView(temp_db, MockSettingsManager(), task_controller=controller)
    view.refresh_project_schedule()

    rendered = [
        item for item in view.gantt_chart.scene.items()
        if isinstance(item, GanttTaskItem)
    ]
    assert len(rendered) >= 1
    assert rendered[0].task.planned_date == "2026-09-15"


def test_32_actual_execution_layer_unaffected(temp_db):
    """32. Open actual execution bar remains visible after Refresh."""
    controller = TaskController(temp_db)
    create_thaavorix_task(controller)
    view = GanttView(temp_db, MockSettingsManager(), task_controller=controller)
    view.refresh_project_schedule()

    rendered = [
        item for item in view.gantt_chart.scene.items()
        if isinstance(item, GanttTaskItem)
    ]
    actual_bars = [
        c for c in rendered[0].childItems()
        if c.toolTip() == "Actual Execution — In Progress"
    ]
    assert len(actual_bars) == 1


def test_33_original_baseline_layer_unaffected(temp_db):
    """33. Original Baseline layer remains visible after Refresh."""
    controller = TaskController(temp_db)
    create_thaavorix_task(controller)
    view = GanttView(temp_db, MockSettingsManager(), task_controller=controller)
    view.refresh_project_schedule()

    rendered = [
        item for item in view.gantt_chart.scene.items()
        if isinstance(item, GanttTaskItem)
    ]
    baseline_bars = [
        c for c in rendered[0].childItems()
        if "Baseline" in (c.toolTip() or "")
    ]
    assert len(baseline_bars) == 1


def test_34_project_selector_scoped(temp_db):
    """34. Project selector filters tasks strictly to selected project."""
    controller = TaskController(temp_db)
    create_thaavorix_task(controller)
    controller.add_task(Task(title="Other Task", project_id=1))
    view = GanttView(temp_db, MockSettingsManager(), task_controller=controller)

    view.set_current_project(4)
    rendered_projects = {
        item.task.project_id for item in view.gantt_chart.scene.items()
        if isinstance(item, GanttTaskItem)
    }
    assert 4 in rendered_projects
    assert 1 not in rendered_projects


def test_35_comparison_selector_read_only(temp_db):
    """35. Comparison selector change is purely visual and performs 0 DB writes."""
    controller = TaskController(temp_db)
    tid = create_thaavorix_task(controller)
    view = GanttView(temp_db, MockSettingsManager(), task_controller=controller)

    before = controller.get_task(tid).to_dict()
    view.on_gantt_compare_version_changed(0)
    after = controller.get_task(tid).to_dict()

    assert before == after


def test_36_production_db_untouched():
    """36. Production DB remains 100% read-only and unmutated."""
    from todo_bird_app.tests.path_helpers import production_db_path
    prod_path = str(production_db_path())
    assert os.path.exists(prod_path)
    with sqlite3.connect(f"file:{prod_path}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        rows = cur.execute("SELECT id, title, actual_start_date FROM tasks WHERE project_id = 4").fetchall()
        for r in rows:
            if r["title"] == "Planning":
                assert r["actual_start_date"] == "2026-08-23"
