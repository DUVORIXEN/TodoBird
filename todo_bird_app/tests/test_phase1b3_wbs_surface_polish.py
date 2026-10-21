"""
TODO BIRD — PHASE 1B.3 TEST SUITE
WBS VISUAL SURFACE POLISH & PREMIUM LIGHT/DARK HIERARCHY DEPTH
Tests layered semantic surfaces, parent row elevation, selection accent indicators,
calm status badges, container panel wrapping, customization controls, and frozen invariants.
"""

import pytest
import time
from typing import Dict, Any
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem, QStyle, QFrame, QWidget
from PySide6.QtCore import Qt, QRectF, QModelIndex
from PySide6.QtGui import QPainter, QPixmap, QColor, QFont

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.services.wbs_service import WBSService, EntityRef, WBSNode, WBSHierarchySnapshot
from todo_bird_app.services.wbs_customization_service import WBSCustomizationService
from todo_bird_app.models.wbs_item_model import WBSItemModel
from todo_bird_app.models.wbs_filter_proxy_model import WBSFilterProxyModel
from todo_bird_app.views.wbs_tree_delegate import WBSTreeItemDelegate
from todo_bird_app.views.wbs_tree_view import WBSTreeView
from todo_bird_app.views.wbs_project_view import WBSProjectView
from todo_bird_app.widgets.wbs_settings_widget import WBSSettingsWidget, WBSLivePreviewCanvas
from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.ui.components.status_badge import StatusBadge, BadgeStatus


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_wbs_polish.db")
    db = DatabaseManager(db_file)
    yield db
    db.close()


@pytest.fixture
def temp_settings(temp_db):
    return SettingsManager(temp_db)


@pytest.fixture
def sample_wbs_data(temp_db):
    """Sets up standard 3-level WBS test project."""
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO projects (id, name, color) VALUES (1, 'Product Launch', '#3584E4');")
        cursor.execute("INSERT OR REPLACE INTO tasks (id, title, project_id, position, status) VALUES (10, 'Market Assessment', 1, 1, 'in_progress');")
        cursor.execute("INSERT OR REPLACE INTO tasks (id, title, project_id, position, status) VALUES (20, 'Product Validation', 1, 2, 'planned');")
        cursor.execute("INSERT OR REPLACE INTO subtasks (id, task_id, title, position, is_completed) VALUES (101, 10, 'Tamil Nadu VOC', 1, 1);")
        cursor.execute("INSERT OR REPLACE INTO subtasks (id, task_id, title, position, is_completed) VALUES (102, 10, 'Karnataka VOC', 2, 0);")
        cursor.execute("INSERT OR REPLACE INTO subtasks (id, task_id, title, position, is_completed) VALUES (201, 20, 'Wet Field Test', 1, 0);")
        cursor.execute("INSERT OR REPLACE INTO subtasks (id, task_id, parent_subtask_id, title, position, is_completed) VALUES (2011, 20, 201, 'Prototype A', 1, 0);")
        conn.commit()
    return temp_db


# ==============================================================================
# 1. SEMANTIC SURFACE TOKENS & HIERARCHY (WBS-B301 .. WBS-B302)
# ==============================================================================

def test_wbs_b301_surface_tokens_dark_and_light(temp_settings):
    """WBS-B301: Centralized semantic surface tokens for dark and light modes."""
    service = WBSCustomizationService(temp_settings)

    dark_surfaces = service.get_surface_colors(is_dark=True, accent_color="#3584E4")
    assert "bg_base" in dark_surfaces
    assert "bg_panel" in dark_surfaces
    assert "bg_toolbar" in dark_surfaces
    assert "bg_header" in dark_surfaces
    assert "summary_alpha" in dark_surfaces
    assert "hover_alpha" in dark_surfaces
    assert "selected_alpha" in dark_surfaces
    assert "guide_alpha" in dark_surfaces

    light_surfaces = service.get_surface_colors(is_dark=False, accent_color="#3584E4")
    assert light_surfaces["bg_base"] == "#F1F5F9"
    assert light_surfaces["bg_panel"] == "#FFFFFF"
    assert light_surfaces["border_subtle"] == "#E2E8F0"


def test_wbs_b302_no_pure_black_in_dark_mode(temp_settings):
    """WBS-B302: WBS dark mode does not use #000000 or flat single-tone dark background."""
    service = WBSCustomizationService(temp_settings)
    surfaces = service.get_surface_colors(is_dark=True, accent_color="#3584E4")

    assert surfaces["bg_base"] != "#000000"
    assert surfaces["bg_panel"] != "#000000"
    assert surfaces["bg_header"] != "#000000"
    # Layered separation: base vs panel vs header
    assert surfaces["bg_base"] != surfaces["bg_panel"]
    assert surfaces["bg_panel"] != surfaces["bg_header"]


# ==============================================================================
# 2. PARENT / SUMMARY ROW TREATMENT (WBS-B303)
# ==============================================================================

def test_wbs_b303_parent_summary_row_tinting(sample_wbs_data, temp_settings, qapp):
    """WBS-B303: Parent summary rows receive subtle tonal elevation and semibold typography."""
    service = WBSCustomizationService(temp_settings)
    delg = WBSTreeItemDelegate(custom_service=service, is_dark=True)
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)

    # Task 10 (Market Assessment) is a parent with subtasks
    idx_parent = model.index(0, WBSItemModel.COL_TITLE)
    assert idx_parent.data(WBSItemModel.HasChildrenRole) is True

    # Render parent row into test pixmap
    pix = QPixmap(300, 36)
    painter = QPainter(pix)
    opt = QStyleOptionViewItem()
    opt.rect = QRectF(0, 0, 300, 36).toRect()
    opt.state = QStyle.State_Enabled

    # Paint should execute cleanly with summary background
    delg.paint(painter, opt, idx_parent)
    painter.end()


# ==============================================================================
# 3. SELECTION & HOVER TREATMENT (WBS-B304 .. WBS-B305)
# ==============================================================================

def test_wbs_b304_selection_surface_and_accent_indicator(sample_wbs_data, temp_settings, qapp):
    """WBS-B304: Selected row renders with subtle accent tint and 3px left edge indicator bar."""
    service = WBSCustomizationService(temp_settings)
    delg = WBSTreeItemDelegate(custom_service=service, is_dark=True, accent_color="#3584E4")
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)

    idx_col0 = model.index(0, WBSItemModel.COL_WBS)

    pix = QPixmap(140, 36)
    painter = QPainter(pix)
    opt = QStyleOptionViewItem()
    opt.rect = QRectF(0, 0, 140, 36).toRect()
    opt.state = QStyle.State_Enabled | QStyle.State_Selected

    delg.paint(painter, opt, idx_col0)
    painter.end()


def test_wbs_b305_hover_subtle_tonal_shift(sample_wbs_data, temp_settings, qapp):
    """WBS-B305: Hover surface applies subtle tonal shift without overpowering selection."""
    service = WBSCustomizationService(temp_settings)
    delg = WBSTreeItemDelegate(custom_service=service, is_dark=True)
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)

    idx_col1 = model.index(0, WBSItemModel.COL_TITLE)

    pix = QPixmap(200, 36)
    painter = QPainter(pix)
    opt = QStyleOptionViewItem()
    opt.rect = QRectF(0, 0, 200, 36).toRect()
    opt.state = QStyle.State_Enabled | QStyle.State_MouseOver

    delg.paint(painter, opt, idx_col1)
    painter.end()


# ==============================================================================
# 4. CONTAINER PANEL & TOOLBAR TREATMENT (WBS-B306)
# ==============================================================================

def test_wbs_b306_wbs_project_view_panel_container(sample_wbs_data, temp_settings, qapp):
    """WBS-B306: WBSProjectView wraps tree and toolbar inside QFrame#WBSPanelWidget."""
    pview = WBSProjectView(sample_wbs_data, temp_settings, project_id=1, is_dark=True)

    assert hasattr(pview, "panel")
    assert pview.panel.objectName() == "WBSPanelWidget"
    assert hasattr(pview, "toolbar_container")
    assert pview.toolbar_container.objectName() == "WBSToolbarContainer"

    # Theme updates correctly
    pview.set_theme(is_dark=False, accent_color="#10B981")
    assert pview._is_dark is False
    assert pview._accent_color == "#10B981"


# ==============================================================================
# 5. STATUS BADGES & CALIBRATED CONTRAST (WBS-B307)
# ==============================================================================

def test_wbs_b307_calm_status_badges_dark_mode():
    """WBS-B307: Status badges in dark mode are de-saturated and calm."""
    cfg = StatusBadge.STATUS_CONFIG

    # Planned
    assert cfg[BadgeStatus.PLANNED]["dark_bg"] == "#222334"
    # Blocked (non-glowing deep burgundy)
    assert cfg[BadgeStatus.BLOCKED]["dark_bg"] == "#321C22"
    # Delayed (non-glowing deep amber)
    assert cfg[BadgeStatus.DELAYED]["dark_bg"] == "#2E2316"
    # In Progress
    assert cfg[BadgeStatus.IN_PROGRESS]["dark_bg"] == "#182538"
    # Completed
    assert cfg[BadgeStatus.COMPLETED]["dark_bg"] == "#162B22"


# ==============================================================================
# 6. CUSTOMIZATION OPTIONS (WBS-B308 .. WBS-B310)
# ==============================================================================

def test_wbs_b308_wbs_customization_surface_styles(temp_settings):
    """WBS-B308: Customization service supports clean, soft_panels, and minimal styles."""
    service = WBSCustomizationService(temp_settings)

    service.set_preference("wbs_surface_style", "minimal")
    surf_min = service.get_surface_colors(is_dark=True, accent_color="#3584E4")
    assert surf_min["border_panel"] == "transparent"

    service.set_preference("wbs_surface_style", "clean")
    surf_clean = service.get_surface_colors(is_dark=True, accent_color="#3584E4")
    assert surf_clean["border_panel"] == "#2E3045"


def test_wbs_b309_wbs_customization_summary_emphasis_and_contrast(temp_settings):
    """WBS-B309: Customization service supports summary emphasis and guide contrast levels."""
    service = WBSCustomizationService(temp_settings)

    service.set_preference("wbs_summary_emphasis", "strong")
    surf_strong = service.get_surface_colors(is_dark=True, accent_color="#3584E4")
    assert surf_strong["summary_alpha"] == 22

    service.set_preference("wbs_guide_contrast", "high")
    surf_high = service.get_surface_colors(is_dark=True, accent_color="#3584E4")
    assert surf_high["guide_alpha"] == 50


def test_wbs_b310_settings_widget_and_live_preview(temp_settings, qapp):
    """WBS-B310: WBSSettingsWidget exposes surface style controls and updates live preview."""
    service = WBSCustomizationService(temp_settings)
    widget = WBSSettingsWidget(service, is_dark=True)

    assert hasattr(widget, "_style_control")
    assert hasattr(widget, "_emphasis_control")
    assert hasattr(widget, "_contrast_control")
    assert hasattr(widget, "_preview_canvas")

    # Change surface style through widget
    widget._style_control.set_selected_index(1)
    assert service.get_preference("wbs_surface_style") == "soft_panels"

    # Reset to defaults
    widget._on_reset_clicked()
    assert service.get_preference("wbs_surface_style") == "clean"
    assert service.get_preference("wbs_summary_emphasis") == "standard"
    assert service.get_preference("wbs_guide_contrast") == "low"


# ==============================================================================
# 7. LIGHT MODE SURFACE DEPTH (WBS-B311)
# ==============================================================================

def test_wbs_b311_light_mode_surfaces(sample_wbs_data, temp_settings, qapp):
    """WBS-B311: Light mode renders soft neutral backdrop, clean raised WBS panel, and subtle borders."""
    service = WBSCustomizationService(temp_settings)
    delg = WBSTreeItemDelegate(custom_service=service, is_dark=False, accent_color="#3584E4")
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)

    pix = QPixmap(300, 36)
    painter = QPainter(pix)
    opt = QStyleOptionViewItem()
    opt.rect = QRectF(0, 0, 300, 36).toRect()
    opt.state = QStyle.State_Enabled

    for col in range(WBSItemModel.COLUMN_COUNT):
        idx = model.index(0, col)
        delg.paint(painter, opt, idx)
    painter.end()


# ==============================================================================
# 8. DROPDOWN POPUP & THEME SYNCHRONIZATION (WBS-B313 .. WBS-B314)
# ==============================================================================

def test_wbs_b313_modern_combobox_status_items_and_popup_rendering(qapp):
    """WBS-B313: ModernComboBox renders status items with semantic dots and visible text in popup."""
    from todo_bird_app.ui.components.modern_combobox import ModernComboBox, ModernComboItemDelegate

    for is_dark in (True, False):
        cb = ModernComboBox(is_dark=is_dark, accent_color="#3584E4")
        cb.addItem("All Statuses", "all")
        cb.addItem("Active Only", "active")
        cb.addItem("Planned", "planned")
        cb.addItem("In Progress", "in_progress")
        cb.addItem("Blocked", "blocked")
        cb.addItem("Completed", "completed")
        cb.addItem("Delayed", "delayed")

        assert cb.count() == 7

        delegate = cb.itemDelegate()
        assert isinstance(delegate, ModernComboItemDelegate)

        # Paint each item in popup list to verify zero exceptions and valid render
        pix = QPixmap(200, 32)
        painter = QPainter(pix)
        opt = QStyleOptionViewItem()
        opt.rect = QRectF(0, 0, 200, 32).toRect()
        opt.state = QStyle.State_Enabled | QStyle.State_Selected

        for i in range(cb.count()):
            delegate.paint(painter, opt, cb.model().index(i, 0))
        painter.end()


def test_wbs_b314_projects_view_theme_synchronization(sample_wbs_data, temp_settings, qapp):
    """WBS-B314: ProjectsView dynamically responds to theme changes and updates WBS sub-views."""
    from todo_bird_app.views.projects_view import ProjectsView

    pview = ProjectsView(sample_wbs_data, temp_settings)
    assert pview.wbs_view is not None

    # Switch to light theme
    pview.on_theme_changed("light")
    assert pview.wbs_view._is_dark is False
    assert pview.view_mode_control._is_dark is False

    # Switch to dark theme
    pview.on_theme_changed("dark")
    assert pview.wbs_view._is_dark is True
    assert pview.view_mode_control._is_dark is True


# ==============================================================================
# 9. FROZEN INVARIANTS & INTEGRITY (WBS-B312)
# ==============================================================================

def test_wbs_b312_full_regression_preservation(sample_wbs_data, temp_settings):
    """WBS-B312: TaskController, WBS numbering, nesting, and database integrity remain 100% intact."""
    controller = TaskController(sample_wbs_data)
    snap = WBSService.build_project_hierarchy(sample_wbs_data, project_id=1)

    # 1. Nesting intact
    assert snap.total_nodes >= 4
    assert EntityRef.task(10) in snap.nodes_by_key
    assert snap.nodes_by_key[EntityRef.task(10)].wbs_code == "1"
    assert snap.nodes_by_key[EntityRef.subtask(101)].wbs_code == "1.1"

    # 2. Database quick check & FK check
    with sample_wbs_data.get_connection() as conn:
        res = [r[0] for r in conn.execute("PRAGMA quick_check;").fetchall()]
        assert res == ["ok"]
        fk_res = conn.execute("PRAGMA foreign_key_check;").fetchall()
        assert fk_res == []
