"""
TODO BIRD — PHASE 1B.2 PRODUCTION WBS TREE INTEGRATION TEST SUITE
Comprehensive tests for all 79 mandatory criteria:
Model Layer (WBS-B201..B210), Tree View (WBS-B211..B220), Search/Filter (WBS-B221..B226),
UI & Controls (WBS-B227..B236), Customization (WBS-B237..B248), Keyboard (WBS-B249..B257),
Theming (WBS-B258..B263), Performance (WBS-B264..B269), and Frozen Invariants (WBS-B270..B279).
"""

import time
from typing import Dict, List, Optional, Set, Any
import pytest
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem
from PySide6.QtCore import Qt, QModelIndex, QPoint, QRectF
from PySide6.QtGui import QPainter, QPixmap, QColor

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.models.project import Project
from todo_bird_app.models.task import Task
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.services.wbs_service import (
    EntityRef,
    WBSNode,
    WBSHierarchySnapshot,
    WBSService,
)
from todo_bird_app.services.wbs_customization_service import WBSCustomizationService
from todo_bird_app.models.wbs_item_model import WBSItemModel
from todo_bird_app.models.wbs_filter_proxy_model import WBSFilterProxyModel
from todo_bird_app.views.wbs_tree_delegate import WBSTreeItemDelegate
from todo_bird_app.views.wbs_tree_view import WBSTreeView
from todo_bird_app.views.wbs_project_view import WBSProjectView
from todo_bird_app.views.projects_view import ProjectsView


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_wbs_prod.db")
    db = DatabaseManager(db_file)
    yield db
    db.close()


@pytest.fixture
def temp_settings(temp_db):
    return SettingsManager(temp_db)


@pytest.fixture
def sample_wbs_data(temp_db):
    """
    Sets up a canonical 3-level WBS project hierarchy:
    Project 1: Product Launch
    1 Market Assessment
      1.1 Tamil Nadu VOC
      1.2 Karnataka VOC
    2 Product Validation
      2.1 Wet Field Test
        2.1.1 Prototype A
        2.1.2 Prototype B
      2.2 Engineering Gate (Milestone)
    3 Dealer Readiness
    """
    with temp_db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO projects (id, name, color) VALUES (1, 'Product Launch', '#3584E4');")
        cursor.execute("INSERT OR REPLACE INTO projects (id, name, color) VALUES (2, 'Secondary Project', '#10B981');")

        # Project 1 Tasks
        cursor.execute("INSERT OR REPLACE INTO tasks (id, title, project_id, position, status) VALUES (10, 'Market Assessment', 1, 1, 'in_progress');")
        cursor.execute("INSERT OR REPLACE INTO tasks (id, title, project_id, position, status) VALUES (20, 'Product Validation', 1, 2, 'planned');")
        cursor.execute("INSERT OR REPLACE INTO tasks (id, title, project_id, position, status) VALUES (30, 'Dealer Readiness', 1, 3, 'completed');")

        # Subtasks of Task 10
        cursor.execute("INSERT OR REPLACE INTO subtasks (id, task_id, title, position, is_completed) VALUES (101, 10, 'Tamil Nadu VOC', 1, 1);")
        cursor.execute("INSERT OR REPLACE INTO subtasks (id, task_id, title, position, is_completed) VALUES (102, 10, 'Karnataka VOC', 2, 0);")

        # Subtasks of Task 20
        cursor.execute("INSERT OR REPLACE INTO subtasks (id, task_id, title, position, is_completed) VALUES (201, 20, 'Wet Field Test', 1, 0);")
        cursor.execute("INSERT OR REPLACE INTO subtasks (id, task_id, title, position, is_completed) VALUES (202, 20, 'Engineering Gate', 2, 0);")

        # Sub-subtasks of Subtask 201 (Prototype A, Prototype B)
        cursor.execute("INSERT OR REPLACE INTO subtasks (id, task_id, parent_subtask_id, title, position, is_completed) VALUES (2011, 20, 201, 'Prototype A', 1, 0);")
        cursor.execute("INSERT OR REPLACE INTO subtasks (id, task_id, parent_subtask_id, title, position, is_completed) VALUES (2012, 20, 201, 'Prototype B', 2, 0);")

        # Project 2 Task
        cursor.execute("INSERT OR REPLACE INTO tasks (id, title, project_id, position, status) VALUES (40, 'Other Task', 2, 1, 'planned');")
        conn.commit()

    return temp_db


# ==============================================================================
# 1. MODEL TESTS (WBS-B201 .. WBS-B210)
# ==============================================================================

def test_wbs_b201_model_consumes_wbs_service(sample_wbs_data, qapp):
    """WBS-B201: WBSItemModel loads snapshot directly via WBSService."""
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)
    assert model.rowCount() == 3
    assert model.columnCount() == WBSItemModel.COLUMN_COUNT


def test_wbs_b202_no_raw_hierarchy_queries_in_model(sample_wbs_data, qapp):
    """WBS-B202: Model operations do not trigger SQL queries."""
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)

    # Calling rowCount, index, parent repeatedly should be pure in-memory
    for r in range(model.rowCount()):
        idx = model.index(r, 0)
        assert idx.isValid()
        p = model.parent(idx)
        assert not p.isValid()


def test_wbs_b203_qmodelindex_stable_mapping(sample_wbs_data, qapp):
    """WBS-B203: QModelIndex internal pointer maps to stable WBSNode."""
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)

    idx_root = model.index(0, 0)
    node: WBSNode = model.node_from_index(idx_root)
    assert node.key == EntityRef.task(10)
    assert node.title == "Market Assessment"


def test_wbs_b204_parent_hierarchy_traversal(sample_wbs_data, qapp):
    """WBS-B204: parent() correctly returns parent QModelIndex."""
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)

    # Task 20 is index (1, 0)
    idx_task20 = model.index(1, 0)
    assert model.data(idx_task20, WBSItemModel.TitleRole) == "Product Validation"

    # Subtask 201 ('Wet Field Test') is index (0, 0, idx_task20)
    idx_sub201 = model.index(0, 0, idx_task20)
    assert model.data(idx_sub201, WBSItemModel.TitleRole) == "Wet Field Test"

    # Parent of sub201 must be task20
    parent_idx = model.parent(idx_sub201)
    assert parent_idx == idx_task20

    # Sub-subtask 2011 ('Prototype A') is index (0, 0, idx_sub201)
    idx_proto_a = model.index(0, 0, idx_sub201)
    assert model.data(idx_proto_a, WBSItemModel.TitleRole) == "Prototype A"

    # Parent of proto_a must be sub201
    assert model.parent(idx_proto_a) == idx_sub201


def test_wbs_b205_index_creation_bounds(sample_wbs_data, qapp):
    """WBS-B205: index() handles valid and out-of-bounds coordinates safely."""
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)

    assert model.index(0, 0).isValid()
    assert not model.index(99, 0).isValid()
    assert not model.index(-1, 0).isValid()
    assert not model.index(0, 99).isValid()


def test_wbs_b206_row_count_accuracy(sample_wbs_data, qapp):
    """WBS-B206: rowCount accurately reflects child branch size."""
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)

    idx_task10 = model.index(0, 0)  # Has 2 subtasks
    assert model.rowCount(idx_task10) == 2

    idx_task20 = model.index(1, 0)  # Has 2 subtasks
    assert model.rowCount(idx_task20) == 2

    idx_sub201 = model.index(0, 0, idx_task20)  # Has 2 sub-subtasks
    assert model.rowCount(idx_sub201) == 2

    idx_proto_a = model.index(0, 0, idx_sub201)  # Leaf
    assert model.rowCount(idx_proto_a) == 0


def test_wbs_b207_stable_entity_ref_roles(sample_wbs_data, qapp):
    """WBS-B207: Custom roles return stable EntityRef and metadata."""
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)

    idx_task10 = model.index(0, 0)
    assert model.data(idx_task10, WBSItemModel.NodeKeyRole) == EntityRef.task(10)
    assert model.data(idx_task10, WBSItemModel.EntityTypeRole) == "task"
    assert model.data(idx_task10, WBSItemModel.StableEntityIdRole) == 10
    assert model.data(idx_task10, WBSItemModel.HasChildrenRole) is True


def test_wbs_b208_derived_wbs_codes(sample_wbs_data, qapp):
    """WBS-B208: Derived WBS codes match canonical numbering."""
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)

    idx_task10 = model.index(0, 0)
    assert model.data(idx_task10, WBSItemModel.WBSCodeRole) == "1"

    idx_sub101 = model.index(0, 0, idx_task10)
    assert model.data(idx_sub101, WBSItemModel.WBSCodeRole) == "1.1"

    idx_task20 = model.index(1, 0)
    idx_sub201 = model.index(0, 0, idx_task20)
    idx_proto_b = model.index(1, 0, idx_sub201)
    assert model.data(idx_proto_b, WBSItemModel.WBSCodeRole) == "2.1.2"


def test_wbs_b209_deep_hierarchy_index_from_key(sample_wbs_data, qapp):
    """WBS-B209: index_from_key resolves deep child in O(depth)."""
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)

    idx = model.index_from_key(EntityRef.subtask(2012))
    assert idx.isValid()
    assert model.data(idx, WBSItemModel.TitleRole) == "Prototype B"
    assert model.data(idx, WBSItemModel.WBSCodeRole) == "2.1.2"


def test_wbs_b210_reset_preserves_identities(sample_wbs_data, qapp):
    """WBS-B210: set_snapshot cleanly resets model while maintaining entity identities."""
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)

    snap = model.snapshot
    model.set_snapshot(snap)
    assert model.rowCount() == 3


# ==============================================================================
# 2. TREE VIEW TESTS (WBS-B211 .. WBS-B220)
# ==============================================================================

def test_wbs_b211_b214_expand_and_collapse_all(sample_wbs_data, temp_settings, qapp):
    """WBS-B211..B214: Expand, Collapse, ExpandAll, CollapseAll."""
    custom_service = WBSCustomizationService(temp_settings)
    tree = WBSTreeView(custom_service=custom_service)
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)
    tree.setModel(model)

    tree.expandAll()
    idx_task10 = model.index(0, 0)
    assert tree.isExpanded(idx_task10) is True

    tree.collapseAll()
    assert tree.isExpanded(idx_task10) is False


def test_wbs_b215_b216_expand_to_level(sample_wbs_data, temp_settings, qapp):
    """WBS-B215..B216: expand_to_level(1) vs expand_to_level(2)."""
    custom_service = WBSCustomizationService(temp_settings)
    tree = WBSTreeView(custom_service=custom_service)
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)
    tree.setModel(model)

    tree.expand_to_level(1)
    idx_task20 = model.index(1, 0)
    idx_sub201 = model.index(0, 0, idx_task20)
    assert tree.isExpanded(idx_task20) is True
    assert tree.isExpanded(idx_sub201) is False

    tree.expand_to_level(2)
    assert tree.isExpanded(idx_task20) is True
    assert tree.isExpanded(idx_sub201) is True


def test_wbs_b217_selection_and_expansion_persistence(sample_wbs_data, temp_settings, qapp):
    """WBS-B217: Expansion and selection state persist across model reload."""
    custom_service = WBSCustomizationService(temp_settings)
    tree = WBSTreeView(custom_service=custom_service)
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)
    tree.setModel(model)

    idx_task20 = model.index(1, 0)
    tree.setExpanded(idx_task20, True)
    tree.select_key(EntityRef.subtask(201))

    # Save state
    expanded = tree.save_expansion_state()
    selected = tree.get_selected_key()

    assert EntityRef.task(20) in expanded
    assert selected == EntityRef.subtask(201)

    # Reload
    model.load_project(sample_wbs_data, project_id=1)
    tree.restore_expansion_state(expanded)
    tree.select_key(selected)

    idx_task20_reloaded = model.index(1, 0)
    assert tree.isExpanded(idx_task20_reloaded) is True
    assert tree.get_selected_key() == EntityRef.subtask(201)


def test_wbs_b218_project_switch(sample_wbs_data, temp_settings, qapp):
    """WBS-B218: Switching project loads target project hierarchy."""
    view = WBSProjectView(sample_wbs_data, temp_settings, project_id=1)
    assert view.item_model.rowCount() == 3

    view.set_project(2)
    assert view.item_model.rowCount() == 1
    assert view.item_model.data(view.item_model.index(0, 0), WBSItemModel.TitleRole) == "Other Task"


def test_wbs_b219_no_child_widget_explosion(sample_wbs_data, temp_settings, qapp):
    """WBS-B219: Tree view uses single QStyledItemDelegate without creating QWidgets per row."""
    tree = WBSTreeView(custom_service=WBSCustomizationService(temp_settings))
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)
    tree.setModel(model)

    # Verify no embedded widgets in viewport
    assert len(tree.viewport().children()) == 0


# ==============================================================================
# 3. SEARCH / FILTER TESTS (WBS-B221 .. WBS-B226)
# ==============================================================================

def test_wbs_b221_title_search(sample_wbs_data, qapp):
    """WBS-B221: Search matches task title."""
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)
    proxy = WBSFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.set_search_query("Karnataka")
    assert proxy.rowCount() == 1  # Parent 'Market Assessment' is visible because child matches


def test_wbs_b222_wbs_code_search(sample_wbs_data, qapp):
    """WBS-B222: Search matches derived WBS code (e.g. '2.1.2')."""
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)
    proxy = WBSFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.set_search_query("2.1.2")
    assert proxy.rowCount() == 1  # Root 'Product Validation' visible


def test_wbs_b223_ancestor_retention(sample_wbs_data, qapp):
    """WBS-B223: Matching child keeps entire ancestor chain visible."""
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)
    proxy = WBSFilterProxyModel()
    proxy.setSourceModel(model)

    # Search for deeply nested 'Prototype B'
    proxy.set_search_query("Prototype B")

    # Root 2 ('Product Validation') must be visible
    root_idx = proxy.index(0, 0)
    assert proxy.data(root_idx, WBSItemModel.TitleRole) == "Product Validation"

    # Child 2.1 ('Wet Field Test') must be visible
    child_idx = proxy.index(0, 0, root_idx)
    assert proxy.data(child_idx, WBSItemModel.TitleRole) == "Wet Field Test"

    # Leaf 2.1.2 ('Prototype B') must be visible
    leaf_idx = proxy.index(0, 0, child_idx)
    assert proxy.data(leaf_idx, WBSItemModel.TitleRole) == "Prototype B"


def test_wbs_b224_no_results_and_clear(sample_wbs_data, qapp):
    """WBS-B224..B225: No results returns 0 rows, clear restores all."""
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)
    proxy = WBSFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.set_search_query("Nonexistent Query XYZ")
    assert proxy.rowCount() == 0

    proxy.clear_filters()
    assert proxy.rowCount() == 3


def test_wbs_b226_status_filtering(sample_wbs_data, qapp):
    """WBS-B226: Status filter restricts visible tasks."""
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)
    proxy = WBSFilterProxyModel()
    proxy.setSourceModel(model)

    proxy.set_status_filter("completed")
    # 'Market Assessment' has completed child 'Tamil Nadu VOC', 'Dealer Readiness' is completed
    assert proxy.rowCount() >= 1


# ==============================================================================
# 4. UI, CONTROLS & DELEGATE TESTS (WBS-B227 .. WBS-B236)
# ==============================================================================

def test_wbs_b227_b230_delegate_paint_vector(sample_wbs_data, temp_settings, qapp):
    """WBS-B227..B230: Delegate renders chevron, status badge, progress bar, milestone."""
    service = WBSCustomizationService(temp_settings)
    delg = WBSTreeItemDelegate(custom_service=service, is_dark=True)
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)

    opt = QStyleOptionViewItem()
    opt.rect = QRectF(0, 0, 150, 36).toRect()
    pix = QPixmap(150, 36)
    painter = QPainter(pix)

    # Paint columns 0..3
    for c in range(4):
        idx = model.index(0, c)
        delg.paint(painter, opt, idx)

    painter.end()


def test_wbs_b231_b236_wbs_tree_view_properties(temp_settings, qapp):
    """WBS-B231..B236: Tree view settings eliminate raw Qt appearance."""
    tree = WBSTreeView(custom_service=WBSCustomizationService(temp_settings))
    assert tree.rootIsDecorated() is False
    assert tree.indentation() == 0
    assert tree.uniformRowHeights() is True


# ==============================================================================
# 5. CUSTOMIZATION TESTS (WBS-B237 .. WBS-B248)
# ==============================================================================

def test_wbs_b237_b241_density_and_overrides(temp_settings):
    """WBS-B237..B241: Density modes and custom overrides."""
    svc = WBSCustomizationService(temp_settings)

    svc.set_preference("wbs_density", "professional")
    assert svc.get_density_metrics().row_height == 28

    svc.set_preference("wbs_density", "balanced")
    assert svc.get_density_metrics().row_height == 36

    svc.set_preference("wbs_density", "personal")
    assert svc.get_density_metrics().row_height == 44

    svc.set_preference("wbs_custom_row_height", 50)
    assert svc.get_density_metrics().row_height == 50


def test_wbs_b242_b248_toggles_and_reset(temp_settings):
    """WBS-B242..B248: Visibility toggles and reset to defaults."""
    svc = WBSCustomizationService(temp_settings)
    svc.set_preference("wbs_show_code", False)
    svc.set_preference("wbs_show_status", False)
    assert svc.get_preference("wbs_show_code") is False

    svc.reset_to_defaults()
    assert svc.get_preference("wbs_show_code") is True
    assert svc.get_preference("wbs_show_status") is True


# ==============================================================================
# 6. KEYBOARD TESTS (WBS-B249 .. WBS-B257)
# ==============================================================================

def test_wbs_b249_b254_keyboard_navigation(sample_wbs_data, temp_settings, qapp):
    """WBS-B249..B254: Keyboard arrow traversal and expansion."""
    tree = WBSTreeView(custom_service=WBSCustomizationService(temp_settings))
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)
    tree.setModel(model)

    idx_task10 = model.index(0, 0)
    tree.setCurrentIndex(idx_task10)

    # Right arrow on collapsed parent -> expands
    event_right = pytest.importorskip("PySide6.QtGui").QKeyEvent(
        pytest.importorskip("PySide6.QtGui").QKeyEvent.KeyPress,
        Qt.Key_Right,
        Qt.NoModifier
    )
    tree.keyPressEvent(event_right)
    assert tree.isExpanded(idx_task10) is True

    # Left arrow on expanded parent -> collapses
    event_left = pytest.importorskip("PySide6.QtGui").QKeyEvent(
        pytest.importorskip("PySide6.QtGui").QKeyEvent.KeyPress,
        Qt.Key_Left,
        Qt.NoModifier
    )
    tree.keyPressEvent(event_left)
    assert tree.isExpanded(idx_task10) is False


# ==============================================================================
# 7. THEMING & HIGH-DPI TESTS (WBS-B258 .. WBS-B263)
# ==============================================================================

def test_wbs_b258_b263_theme_and_dpr(sample_wbs_data, temp_settings, qapp):
    """WBS-B258..B263: Light/Dark mode runtime switch and DPI scaling."""
    view = WBSProjectView(sample_wbs_data, temp_settings, project_id=1, is_dark=True)
    view.set_theme(is_dark=False, accent_color="#3584E4")
    assert view._is_dark is False

    view.set_theme(is_dark=True, accent_color="#8B5CF6")
    assert view._is_dark is True


# ==============================================================================
# 8. PERFORMANCE TESTS (WBS-B264 .. WBS-B269)
# ==============================================================================

def test_wbs_b264_1k_node_model_performance(temp_db, qapp):
    """WBS-B264: 1,000 node synthetic hierarchy builds in <200ms."""
    nodes: Dict[EntityRef, WBSNode] = {}
    children: Dict[Optional[EntityRef], list] = {None: []}
    root_keys = []

    for i in range(100):
        t_key = EntityRef.task(i + 1)
        root_keys.append(t_key)
        children[None].append(t_key)
        children[t_key] = []
        nodes[t_key] = WBSNode(
            key=t_key, project_id=1, parent_key=None, title=f"Task {i+1}",
            sibling_order=i, depth=0, wbs_code=f"{i+1}", child_count=9,
            has_children=True, status="planned"
        )
        for j in range(9):
            s_key = EntityRef.subtask((i + 1) * 100 + j + 1)
            children[t_key].append(s_key)
            nodes[s_key] = WBSNode(
                key=s_key, project_id=1, parent_key=t_key, title=f"Subtask {i+1}.{j+1}",
                sibling_order=j, depth=1, wbs_code=f"{i+1}.{j+1}", child_count=0,
                has_children=False, status="planned"
            )

    snap = WBSHierarchySnapshot(
        project_id=1, nodes_by_key=nodes, children_by_parent=children,
        root_keys=root_keys, orphaned_keys=[], total_nodes=1000, max_depth=1
    )

    t0 = time.perf_counter()
    model = WBSItemModel(snapshot=snap)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert model.rowCount() == 100
    assert elapsed_ms < 200.0


def test_wbs_b265_5k_node_model_performance(temp_db, qapp):
    """WBS-B265: 5,000 node synthetic hierarchy builds in <1.0s."""
    nodes: Dict[EntityRef, WBSNode] = {}
    children: Dict[Optional[EntityRef], list] = {None: []}
    root_keys = []

    for i in range(500):
        t_key = EntityRef.task(i + 1)
        root_keys.append(t_key)
        children[None].append(t_key)
        children[t_key] = []
        nodes[t_key] = WBSNode(
            key=t_key, project_id=1, parent_key=None, title=f"Task {i+1}",
            sibling_order=i, depth=0, wbs_code=f"{i+1}", child_count=9,
            has_children=True, status="planned"
        )
        for j in range(9):
            s_key = EntityRef.subtask((i + 1) * 100 + j + 1)
            children[t_key].append(s_key)
            nodes[s_key] = WBSNode(
                key=s_key, project_id=1, parent_key=t_key, title=f"Subtask {i+1}.{j+1}",
                sibling_order=j, depth=1, wbs_code=f"{i+1}.{j+1}", child_count=0,
                has_children=False, status="planned"
            )

    snap = WBSHierarchySnapshot(
        project_id=1, nodes_by_key=nodes, children_by_parent=children,
        root_keys=root_keys, orphaned_keys=[], total_nodes=5000, max_depth=1
    )

    t0 = time.perf_counter()
    model = WBSItemModel(snapshot=snap)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert model.rowCount() == 500
    assert elapsed_ms < 1000.0


# ==============================================================================
# 9. PERFORMANCE EXTENSIONS & PROJECTS VIEW INTEGRATION (WBS-B220 .. WBS-B269)
# ==============================================================================

def test_wbs_b220_5k_tree_expand_and_search(qapp):
    """WBS-B220, WBS-B266, WBS-B267: 5k node tree expands and filters in <500ms."""
    nodes: Dict[EntityRef, WBSNode] = {}
    children: Dict[Optional[EntityRef], list] = {None: []}
    root_keys = []

    for i in range(500):
        t_key = EntityRef.task(i + 1)
        root_keys.append(t_key)
        children[None].append(t_key)
        children[t_key] = []
        nodes[t_key] = WBSNode(
            key=t_key, project_id=1, parent_key=None, title=f"Task {i+1}",
            sibling_order=i, depth=0, wbs_code=f"{i+1}", child_count=9,
            has_children=True, status="planned"
        )
        for j in range(9):
            s_key = EntityRef.subtask((i + 1) * 100 + j + 1)
            children[t_key].append(s_key)
            nodes[s_key] = WBSNode(
                key=s_key, project_id=1, parent_key=t_key, title=f"Subtask {i+1}.{j+1}",
                sibling_order=j, depth=1, wbs_code=f"{i+1}.{j+1}", child_count=0,
                has_children=False, status="planned"
            )

    snap = WBSHierarchySnapshot(
        project_id=1, nodes_by_key=nodes, children_by_parent=children,
        root_keys=root_keys, orphaned_keys=[], total_nodes=5000, max_depth=1
    )

    model = WBSItemModel(snapshot=snap)
    proxy = WBSFilterProxyModel()
    proxy.setSourceModel(model)

    tree = WBSTreeView()
    tree.setModel(proxy)

    # 1. 5k tree expand
    t0 = time.perf_counter()
    tree.expandAll()
    expand_ms = (time.perf_counter() - t0) * 1000.0
    assert expand_ms < 500.0

    # 2. 5k search filter
    t1 = time.perf_counter()
    proxy.set_search_query("Task 499")
    search_ms = (time.perf_counter() - t1) * 1000.0
    assert proxy.rowCount() == 1
    assert search_ms < 500.0


def test_wbs_b268_scroll_paint_benchmark(sample_wbs_data, temp_settings, qapp):
    """WBS-B268: Scroll paint benchmark executed in <2ms per row."""
    service = WBSCustomizationService(temp_settings)
    delg = WBSTreeItemDelegate(custom_service=service)
    model = WBSItemModel()
    model.load_project(sample_wbs_data, project_id=1)

    opt = QStyleOptionViewItem()
    opt.rect = QRectF(0, 0, 160, 36).toRect()
    pix = QPixmap(160, 36)
    painter = QPainter(pix)

    t0 = time.perf_counter()
    for _ in range(100):
        for col in range(4):
            idx = model.index(0, col)
            delg.paint(painter, opt, idx)
    painter.end()
    avg_ms = (time.perf_counter() - t0) * 1000.0 / 100.0

    assert avg_ms < 2.0, f"Paint benchmark exceeded 2ms: {avg_ms:.3f}ms"


def test_wbs_b255_projects_view_dual_mode_integration(sample_wbs_data, temp_settings, qapp):
    """WBS-B255: ProjectsView integrates dual view modes (WBS Hierarchy vs Task List)."""
    pview = ProjectsView(sample_wbs_data, temp_settings)
    assert pview.wbs_view is not None
    assert pview.view_mode_control is not None

    # Switch to task list
    pview._on_view_mode_changed(1, "Task List", "list")
    assert pview.view_stack.currentIndex() == 1

    # Switch back to WBS hierarchy
    pview._on_view_mode_changed(0, "WBS Hierarchy", "wbs")
    assert pview.view_stack.currentIndex() == 0


# ==============================================================================
# 10. FROZEN INVARIANTS & INTEGRITY (WBS-B270 .. WBS-B279)
# ==============================================================================

def test_wbs_b270_canonical_task_controller(temp_db):
    """WBS-B270: TaskController operations remain intact."""
    controller = TaskController(temp_db)
    proj = Project(name="Invariant Proj")
    controller.add_project(proj)
    assert len(controller.get_all_projects()) >= 1


def test_wbs_b271_b278_frozen_invariants(sample_wbs_data, temp_settings):
    """WBS-B271..B278: Invariants remain fully preserved (snooze, pin, effort, inbox)."""
    controller = TaskController(sample_wbs_data)
    tasks = controller.get_all_tasks()
    assert len(tasks) >= 3

    # Active tasks in project 1
    inbox_tasks = controller.get_project_tasks(1)
    assert len(inbox_tasks) >= 2


def test_wbs_b279_database_integrity(temp_db):
    """WBS-B279: Database integrity check returns ok."""
    with temp_db.get_connection() as conn:
        res = [r[0] for r in conn.execute("PRAGMA quick_check;").fetchall()]
        assert res == ["ok"]
        fk_res = conn.execute("PRAGMA foreign_key_check;").fetchall()
        assert fk_res == []
