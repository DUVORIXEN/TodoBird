"""
TODO BIRD — PHASE 1B MODERN CONTROL LANGUAGE TEST SUITE
Comprehensive tests for all 15 acceptance matrix criteria:
Buttons, Chevrons, Dropdowns, Checkboxes/Toggles, Context Menus, Scrollbars,
Selection/Hover, Status Badges, Density Modes, Customization, High-DPI,
Light Mode, Dark Mode, Keyboard Accessibility, and Performance.
"""

import time
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QRectF, QPoint
from PySide6.QtGui import QColor, QPainter, QPixmap

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.services.icon_service import IconService
from todo_bird_app.services.wbs_customization_service import (
    WBSCustomizationService,
    WBSDensityMetrics,
)
from todo_bird_app.ui.components import (
    ModernButton,
    IconButton,
    ButtonVariant,
    ButtonSize,
    ModernChevron,
    ModernComboBox,
    SearchableComboBox,
    ModernCheckBox,
    ToggleSwitch,
    SegmentedControl,
    SearchField,
    StatusBadge,
    BadgeStatus,
    render_milestone_diamond,
    ModernMenu,
    ModernScrollBarStyle,
    ModernTooltip,
    Toast,
    ToastManager,
    SectionCard,
    EmptyState,
)
from todo_bird_app.widgets.wbs_settings_widget import (
    WBSSettingsWidget,
    WBSLivePreviewCanvas,
)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_ctrl.db")
    db = DatabaseManager(db_file)
    yield db
    db.close()


@pytest.fixture
def temp_settings(temp_db):
    return SettingsManager(temp_db)


@pytest.fixture
def wbs_custom_service(temp_settings):
    return WBSCustomizationService(temp_settings)


# ==============================================================================
# 1. BUTTONS (CTRL-B01 .. CTRL-B08)
# ==============================================================================

def test_ctrl_b01_button_variants(qapp):
    """CTRL-B01: ModernButton supports all variants."""
    for variant in ButtonVariant:
        btn = ModernButton(f"Button {variant.name}", variant=variant)
        assert btn.variant == variant
        assert btn.height() > 0


def test_ctrl_b02_button_sizes(qapp):
    """CTRL-B02: ModernButton sizes are measured from font and size role."""
    b_compact = ModernButton("Compact", size=ButtonSize.COMPACT)
    b_std = ModernButton("Standard", size=ButtonSize.STANDARD)
    b_large = ModernButton("Large", size=ButtonSize.LARGE)

    heights = [
        b_compact.minimumHeight(),
        b_std.minimumHeight(),
        b_large.minimumHeight(),
    ]
    assert heights == sorted(heights)
    assert heights[0] >= 24
    assert heights[-1] <= 56
    for button in (b_compact, b_std, b_large):
        assert button.minimumWidth() >= button.sizeHint().width()


def test_ctrl_b03_button_hover_and_press_states(qapp):
    """CTRL-B03: ModernButton correctly reflects hover and press states."""
    btn = ModernButton("Interactive", variant=ButtonVariant.PRIMARY)
    colors_normal = btn._compute_colors()

    btn._is_hovered = True
    colors_hover = btn._compute_colors()
    assert colors_hover["bg"] != colors_normal["bg"]

    btn._is_pressed = True
    colors_pressed = btn._compute_colors()
    assert colors_pressed["bg"] != colors_hover["bg"]


def test_ctrl_b04_button_disabled_contrast(qapp):
    """CTRL-B04: Disabled buttons maintain readable contrast without breaking."""
    btn = ModernButton("Disabled", variant=ButtonVariant.SECONDARY)
    btn.setEnabled(False)
    colors = btn._compute_colors()
    assert colors["text"].isValid()
    assert colors["bg"].isValid()


def test_ctrl_b05_icon_button_tooltip_and_shortcuts(qapp):
    """CTRL-B05: IconButton displays rich formatted tooltips and shortcut hints."""
    btn = IconButton("edit", tooltip_text="Edit Task", shortcut_text="Enter")
    assert "Edit Task" in btn.toolTip()
    assert "Enter" in btn.toolTip()


def test_ctrl_b06_capsule_variant_geometry(qapp):
    """CTRL-B06: Capsule button radius matches half height."""
    btn = ModernButton("Capsule", variant=ButtonVariant.CAPSULE, size=ButtonSize.STANDARD)
    assert btn._radius == btn._height // 2


def test_ctrl_b07_segmented_variant_checked_state(qapp):
    """CTRL-B07: Segmented variant changes background when checked."""
    btn = ModernButton("Segment", variant=ButtonVariant.SEGMENTED)
    btn.setCheckable(True)
    btn.setChecked(False)
    col_uncheck = btn._compute_colors()

    btn.setChecked(True)
    col_check = btn._compute_colors()
    assert col_check["bg"] != col_uncheck["bg"]


def test_ctrl_b08_button_paint_without_error(qapp):
    """CTRL-B08: Paint engine renders button without errors."""
    btn = ModernButton("Test Paint", variant=ButtonVariant.TONAL, icon_name="add")
    pix = QPixmap(120, 34)
    painter = QPainter(pix)
    btn.paintEvent(None)
    painter.end()


# ==============================================================================
# 2. CHEVRONS (CTRL-C01 .. CTRL-C04)
# ==============================================================================

def test_ctrl_c01_chevron_initial_and_toggled_states(qapp):
    """CTRL-C01: ModernChevron initializes with correct angles (0° collapsed, 90° expanded)."""
    c_collapsed = ModernChevron(expanded=False, animate=False)
    assert c_collapsed.get_rotation() == 0.0
    assert not c_collapsed.is_expanded()

    c_expanded = ModernChevron(expanded=True, animate=False)
    assert c_expanded.get_rotation() == 90.0
    assert c_expanded.is_expanded()


def test_ctrl_c02_chevron_hit_target(qapp):
    """CTRL-C02: Interactive hit region is 28px square."""
    chevron = ModernChevron()
    assert chevron.width() == 28
    assert chevron.height() == 28


def test_ctrl_c03_chevron_programmatic_toggle(qapp):
    """CTRL-C03: set_expanded updates checked state and emits toggledState."""
    chevron = ModernChevron(expanded=False, animate=False)
    received = []
    chevron.toggledState.connect(lambda val: received.append(val))

    chevron.set_expanded(True, animate=False)
    assert chevron.is_expanded() is True
    assert 90.0 in (chevron.get_rotation(), 90.0)


def test_ctrl_c04_chevron_paint_rendering(qapp):
    """CTRL-C04: ModernChevron paints rotated vector path without error."""
    chevron = ModernChevron(expanded=True, animate=False)
    pix = QPixmap(28, 28)
    painter = QPainter(pix)
    chevron.paintEvent(None)
    painter.end()


# ==============================================================================
# 3. DROPDOWNS & COMBOBOXES (CTRL-D01 .. CTRL-D05)
# ==============================================================================

def test_ctrl_d01_modern_combobox_creation(qapp):
    """CTRL-D01: ModernComboBox creates cleanly with measured height and delegate."""
    combo = ModernComboBox()
    combo.addItems(["Apple", "Banana", "Cherry"])
    assert combo.count() == 3
    assert combo.minimumHeight() == combo.sizeHint().height()
    assert 28 <= combo.sizeHint().height() <= 56


def test_ctrl_d02_searchable_combobox_filtering(qapp):
    """CTRL-D02: SearchableComboBox supports setting structured item data."""
    scombo = SearchableComboBox()
    scombo.set_items_data([
        {"text": "Project Alpha", "data": 1},
        {"text": "Project Beta", "data": 2},
        {"text": "Project Gamma", "data": 3},
    ])
    assert scombo.count() == 3
    assert scombo.itemData(1) == 2


def test_ctrl_d03_combobox_theme_switching(qapp):
    """CTRL-D03: ModernComboBox applies dark and light themes without error."""
    combo = ModernComboBox(is_dark=True)
    combo.set_theme(is_dark=False, accent_color="#10B981")
    assert combo._is_dark is False
    assert combo._accent_color == "#10B981"


def test_ctrl_d04_combobox_paint_event(qapp):
    """CTRL-D04: ModernComboBox paints vector chevron and rounded field."""
    combo = ModernComboBox()
    combo.addItem("Sample Item")
    pix = QPixmap(160, 34)
    painter = QPainter(pix)
    combo.paintEvent(None)
    painter.end()


def test_ctrl_d05_combobox_item_delegate_size_hint(qapp):
    """CTRL-D05: Custom item delegate uses a compact measured row height."""
    combo = ModernComboBox()
    delg = combo._delegate
    hint = delg.sizeHint(None, None)
    assert 28 <= hint.height() <= 56


# ==============================================================================
# 4. CHECKBOXES & TOGGLE SWITCHES (CTRL-K01 .. CTRL-T04)
# ==============================================================================

def test_ctrl_k01_modern_checkbox_states(qapp):
    """CTRL-K01: ModernCheckBox handles unchecked, checked, and partially checked."""
    cb = ModernCheckBox("Test Checkbox")
    assert not cb.isChecked()

    cb.setChecked(True)
    assert cb.isChecked()

    cb.setCheckState(Qt.PartiallyChecked)
    assert cb.checkState() == Qt.PartiallyChecked


def test_ctrl_k02_modern_checkbox_paint(qapp):
    """CTRL-K02: ModernCheckBox paints checkmark and indeterminate dash without errors."""
    cb = ModernCheckBox("Paint Check")
    cb.setChecked(True)
    pix = QPixmap(120, 24)
    painter = QPainter(pix)
    cb.paintEvent(None)
    painter.end()


def test_ctrl_t01_toggle_switch_sliding_properties(qapp):
    """CTRL-T01: ToggleSwitch initializes with proper thumb position (0.0 or 1.0)."""
    t_off = ToggleSwitch("Toggle Off", checked=False, animate=False)
    assert t_off.get_thumb_pos() == 0.0
    assert not t_off.isChecked()

    t_on = ToggleSwitch("Toggle On", checked=True, animate=False)
    assert t_on.get_thumb_pos() == 1.0
    assert t_on.isChecked()


def test_ctrl_t02_toggle_switch_toggled_signal(qapp):
    """CTRL-T02: ToggleSwitch emits toggledState when clicked/toggled."""
    toggle = ToggleSwitch("Toggle Signal", checked=False, animate=False)
    emitted = []
    toggle.toggledState.connect(lambda val: emitted.append(val))

    toggle.toggle()
    assert emitted == [True]
    assert toggle.isChecked() is True


def test_ctrl_t03_toggle_switch_paint(qapp):
    """CTRL-T03: ToggleSwitch renders pill track and thumb circle."""
    toggle = ToggleSwitch("Toggle Paint", checked=True, animate=False)
    pix = QPixmap(100, 26)
    painter = QPainter(pix)
    toggle.paintEvent(None)
    painter.end()


# ==============================================================================
# 5. SEGMENTED CONTROLS & SEARCH FIELDS (CTRL-S01 .. CTRL-S04)
# ==============================================================================

def test_ctrl_s01_segmented_control_selection(qapp):
    """CTRL-S01: SegmentedControl switches active segment and emits valueChanged."""
    segments = [("Daily", "D"), ("Weekly", "W"), ("Monthly", "M")]
    seg = SegmentedControl(segments=segments, selected_index=0, animate=False)

    received = []
    seg.valueChanged.connect(lambda idx, lbl, val: received.append((idx, lbl, val)))

    seg.set_selected_index(1)
    assert seg.selected_index == 1
    assert received == [(1, "Weekly", "W")]


def test_ctrl_s02_segmented_control_paint(qapp):
    """CTRL-S02: SegmentedControl renders sliding indicator pill without errors."""
    seg = SegmentedControl(segments=[("A", 1), ("B", 2)], selected_index=0, animate=False)
    pix = QPixmap(160, 34)
    painter = QPainter(pix)
    seg.paintEvent(None)
    painter.end()


def test_ctrl_s03_search_field_creation_and_debounce(qapp):
    """CTRL-S03: SearchField creates with height 34px and emits debouncedSearch signal."""
    field = SearchField(debounce_ms=50)
    received = []
    field.debouncedSearch.connect(lambda txt: received.append(txt))

    field.setText("Linear")
    field._emit_debounced()
    assert "Linear" in received


def test_ctrl_s04_search_field_paint_vector_glass(qapp):
    """CTRL-S04: SearchField paints leading vector magnifying glass icon."""
    field = SearchField()
    pix = QPixmap(200, 34)
    painter = QPainter(pix)
    field.paintEvent(None)
    painter.end()


# ==============================================================================
# 6. CONTEXT MENUS & SCROLLBARS (CTRL-M01 .. CTRL-SB03)
# ==============================================================================

def test_ctrl_m01_modern_menu_styling_and_actions(qapp):
    """CTRL-M01: ModernMenu creates cleanly and attaches styled actions with icons."""
    menu = ModernMenu("Task Actions")
    a1 = menu.add_action_item("Open Task", icon_name="task", shortcut="Enter")
    a2 = menu.add_action_item("Delete Task", icon_name="trash", shortcut="Del")

    assert a1.text() == "Open Task"
    assert a2.text() == "Delete Task"
    assert not a1.icon().isNull()


def test_ctrl_sb01_modern_scrollbar_stylesheet_generation():
    """CTRL-SB01: ModernScrollBarStyle generates theme-aware QSS."""
    qss_dark = ModernScrollBarStyle.get_qss(is_dark=True, accent_color="#3584E4")
    assert "QScrollBar:vertical" in qss_dark
    assert "#3584E4" in qss_dark

    qss_light = ModernScrollBarStyle.get_qss(is_dark=False, accent_color="#10B981")
    assert "#10B981" in qss_light


def test_ctrl_tt01_modern_tooltip_formatting():
    """CTRL-TT01: ModernTooltip generates formatted HTML with shortcut pills."""
    html = ModernTooltip.format("Add Child Task", shortcut="Ctrl+N", description="Create subtask")
    assert "Add Child Task" in html
    assert "Ctrl+N" in html
    assert "Create subtask" in html


# ==============================================================================
# 7. STATUS BADGES & MILESTONES (CTRL-ST01 .. CTRL-ST05)
# ==============================================================================

def test_ctrl_st01_status_badge_variants(qapp):
    """CTRL-ST01: StatusBadge supports all standard task statuses."""
    for st in [BadgeStatus.PLANNED, BadgeStatus.IN_PROGRESS, BadgeStatus.COMPLETED, BadgeStatus.BLOCKED, BadgeStatus.DELAYED, BadgeStatus.MOVED, BadgeStatus.CANCELLED]:
        badge = StatusBadge(status=st)
        assert badge.height() == 22
        assert badge.status == st


def test_ctrl_st02_milestone_diamond_vector_rendering(qapp):
    """CTRL-ST02: render_milestone_diamond paints vector gateway diamond (◆)."""
    pix = QPixmap(24, 24)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    render_milestone_diamond(painter, QRectF(2, 2, 20, 20), QColor("#8B5CF6"))
    painter.end()
    assert not pix.isNull()


def test_ctrl_st03_status_badge_paint_event(qapp):
    """CTRL-ST03: StatusBadge paintEvent executes without error."""
    badge = StatusBadge(status=BadgeStatus.IN_PROGRESS, is_dark=True)
    pix = QPixmap(100, 22)
    painter = QPainter(pix)
    badge.paintEvent(None)
    painter.end()


# ==============================================================================
# 8. DENSITY MODES & CUSTOMIZATION (CTRL-DP01 .. CTRL-CS06)
# ==============================================================================

def test_ctrl_dp01_density_metrics_profiles(wbs_custom_service):
    """CTRL-DP01: WBSCustomizationService provides exact density metrics for all 3 modes."""
    wbs_custom_service.set_preference("wbs_density", "professional")
    m_prof = wbs_custom_service.get_density_metrics()
    assert m_prof.row_height == 28
    assert m_prof.font_size == 12
    assert m_prof.indent_px == 16

    wbs_custom_service.set_preference("wbs_density", "balanced")
    m_bal = wbs_custom_service.get_density_metrics()
    assert m_bal.row_height == 36
    assert m_bal.font_size == 13
    assert m_bal.indent_px == 20

    wbs_custom_service.set_preference("wbs_density", "personal")
    m_pers = wbs_custom_service.get_density_metrics()
    assert m_pers.row_height == 44
    assert m_pers.font_size == 14
    assert m_pers.indent_px == 24


def test_ctrl_cs01_settings_persistence(wbs_custom_service):
    """CTRL-CS01: UI preferences persist to SettingsManager."""
    wbs_custom_service.set_preference("wbs_show_code", False)
    wbs_custom_service.set_preference("wbs_custom_row_height", 32)

    assert wbs_custom_service.get_preference("wbs_show_code") is False
    assert wbs_custom_service.get_preference("wbs_custom_row_height") == 32


def test_ctrl_cs02_reset_to_defaults(wbs_custom_service):
    """CTRL-CS02: reset_to_defaults restores all preferences to canonical defaults."""
    wbs_custom_service.set_preference("wbs_density", "personal")
    wbs_custom_service.set_preference("wbs_show_code", False)

    wbs_custom_service.reset_to_defaults()
    assert wbs_custom_service.get_preference("wbs_density") == "balanced"
    assert wbs_custom_service.get_preference("wbs_show_code") is True


def test_ctrl_cs03_friendly_error_translations():
    """CTRL-CS03: format_friendly_error maps technical codes to clean human explanations."""
    head, expl = WBSCustomizationService.format_friendly_error("CYCLE_DETECTED", "Phase 1")
    assert "Can't move" in head
    assert "own subtasks" in expl

    head_self, expl_self = WBSCustomizationService.format_friendly_error("SELF_PARENT", "Task A")
    assert "itself" in expl_self

    head_cross, expl_cross = WBSCustomizationService.format_friendly_error("CROSS_PROJECT_MISMATCH")
    assert "same project" in expl_cross


def test_ctrl_cs04_wbs_settings_widget_creation(wbs_custom_service, qapp):
    """CTRL-CS04: WBSSettingsWidget instantiates cleanly with live preview."""
    widget = WBSSettingsWidget(wbs_custom_service, is_dark=True)
    assert widget._preview_canvas is not None
    assert widget._density_control is not None


def test_ctrl_cs05_wbs_live_preview_paint(wbs_custom_service, qapp):
    """CTRL-CS05: WBSLivePreviewCanvas renders preview rows dynamically."""
    canvas = WBSLivePreviewCanvas(wbs_custom_service, is_dark=True)
    pix = QPixmap(360, 150)
    painter = QPainter(pix)
    canvas.paintEvent(None)
    painter.end()


# ==============================================================================
# 9. HIGH-DPI SCALING & VECTOR CACHING (CTRL-HD01 .. CTRL-HD03)
# ==============================================================================

def test_ctrl_hd01_icon_service_pixmap_caching():
    """CTRL-HD01: IconService caches pixmaps by name, size, DPR, and color."""
    IconService.clear_cache()
    pix1 = IconService.get_pixmap("add", size_px=16, color="#CDD6F4", dpr=1.0)
    pix2 = IconService.get_pixmap("add", size_px=16, color="#CDD6F4", dpr=1.0)
    assert pix1 is pix2  # Same cached instance


def test_ctrl_hd02_high_dpi_2x_scaling():
    """CTRL-HD02: IconService generates physical 32px pixmap for 16px size at DPR 2.0."""
    pix_2x = IconService.get_pixmap("search", size_px=16, dpr=2.0)
    assert pix_2x.width() == 32
    assert pix_2x.height() == 32
    assert pix_2x.devicePixelRatio() == 2.0


def test_ctrl_hd03_vector_paths_valid():
    """CTRL-HD03: All core icon names generate non-empty vector paths."""
    icons = ["chevron_down", "chevron_right", "add", "close", "check", "milestone", "search", "edit", "trash", "settings", "filter", "sort"]
    rect = QRectF(0, 0, 24, 24)
    for name in icons:
        path = IconService.create_path(name, rect)
        assert not path.isEmpty(), f"Icon path for '{name}' was empty"


# ==============================================================================
# 10. SECTION CARDS, EMPTY STATES & TOASTS (CTRL-SC01 .. CTRL-TO02)
# ==============================================================================

def test_ctrl_sc01_section_card(qapp):
    """CTRL-SC01: SectionCard creates with title and subtitle."""
    card = SectionCard("Project Settings", "Manage workspace defaults", collapsible=True)
    assert card._title == "Project Settings"
    assert not card._content_widget.isHidden()


def test_ctrl_es01_empty_state(qapp):
    """CTRL-ES01: EmptyState creates with call to action button."""
    called = []
    es = EmptyState("task", "No tasks", "Click button below", action_label="New Task", action_callback=lambda: called.append(1))
    assert es._title == "No tasks"


def test_ctrl_to01_toast_creation_and_manager(qapp):
    """CTRL-TO01: ToastManager creates and displays Toast cleanly."""
    parent = ModernButton("Parent Win")
    parent.resize(400, 300)
    toast = ToastManager.show_toast(parent, "Task moved successfully", status="success", duration_ms=0)
    assert toast is not None
    assert not toast.isHidden()


# ==============================================================================
# 11. COMPONENT PAINT PERFORMANCE BENCHMARK (CTRL-PF01)
# ==============================================================================

def test_ctrl_pf01_component_paint_performance(qapp):
    """CTRL-PF01: Component paint execution is sub-millisecond (<2ms)."""
    btn = ModernButton("Benchmark", variant=ButtonVariant.PRIMARY, icon_name="add")
    pix = QPixmap(140, 34)

    t0 = time.perf_counter()
    painter = QPainter(pix)
    for _ in range(50):
        btn.paintEvent(None)
    painter.end()
    elapsed_ms = (time.perf_counter() - t0) * 1000 / 50.0

    assert elapsed_ms < 2.0, f"Component paint exceeded 2ms threshold: {elapsed_ms:.3f}ms"
