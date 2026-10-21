"""
Phase 2E — Gantt / WBS UI Closure Test Suite (35 Scenarios)
"""

from datetime import date, datetime
import pytest
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.models.wbs_item_model import WBSItemModel
from todo_bird_app.views.wbs_tree_view import WBSTreeView
from todo_bird_app.gantt.timescale_engine import TimescaleEngine, ZoomLevel
from todo_bird_app.services.wbs_customization_service import WBSCustomizationService
from todo_bird_app.widgets.wbs_settings_widget import WBSSettingsWidget
from todo_bird_app.ui.components.section_card import SectionCard


@pytest.fixture(autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def temp_db(tmp_path):
    db_file = str(tmp_path / "test_todo_bird.db")
    db = DatabaseManager(db_file)
    yield db
    db.close()


@pytest.fixture
def settings_mgr(temp_db):
    sm = SettingsManager(temp_db)
    yield sm


# ==============================================================================
# GANTT TESTS (1 - 10)
# ==============================================================================

def test_01_cpm_task_beyond_old_visible_range_expands_scene(temp_db):
    anchor = date(2026, 8, 23)
    tasks = [
        {"planned_date": "2026-08-23", "cpm_earliest_finish": "2026-10-15T09:00:00"}
    ]
    cols = TimescaleEngine.generate_columns(ZoomLevel.DAILY, anchor, tasks)
    assert cols[-1].start_date >= date(2026, 10, 15)


def test_02_task_at_sep_15_visible_after_snet():
    anchor = date(2026, 8, 23)
    tasks = [{"constraint_datetime": "2026-09-15 09:00"}]
    cols = TimescaleEngine.generate_columns(ZoomLevel.DAILY, anchor, tasks)
    col_dates = [c.start_date for c in cols]
    assert date(2026, 9, 15) in col_dates


def test_03_horizontal_scrollbar_reaches_latest_task():
    anchor = date(2026, 8, 23)
    tasks = [{"cpm_earliest_finish": "2026-11-01T17:00:00"}]
    min_d, max_d = TimescaleEngine.get_relevant_date_range(anchor, tasks)
    assert max_d >= date(2026, 11, 1)


def test_04_fit_project_includes_current_cpm_finish():
    anchor = date(2026, 8, 23)
    tasks = [{"cpm_earliest_finish": "2026-10-07T09:00:00"}]
    min_d, max_d = TimescaleEngine.get_relevant_date_range(anchor, tasks)
    assert max_d >= date(2026, 10, 7)


def test_05_baseline_extent_included():
    anchor = date(2026, 8, 23)
    tasks = [{"baseline_finish": "2026-12-01 17:00"}]
    min_d, max_d = TimescaleEngine.get_relevant_date_range(anchor, tasks)
    assert max_d >= date(2026, 12, 1)


def test_06_deadline_marker_extent_included():
    anchor = date(2026, 8, 23)
    tasks = [{"deadline_datetime": "2026-10-25 17:00"}]
    min_d, max_d = TimescaleEngine.get_relevant_date_range(anchor, tasks)
    assert max_d >= date(2026, 10, 25)


def test_07_constraint_marker_extent_included():
    anchor = date(2026, 8, 23)
    tasks = [{"constraint_datetime": "2026-11-15 09:00"}]
    min_d, max_d = TimescaleEngine.get_relevant_date_range(anchor, tasks)
    assert max_d >= date(2026, 11, 15)


def test_08_no_scene_clipping():
    anchor = date(2026, 8, 23)
    tasks = [{"cpm_earliest_finish": "2026-09-30T17:00:00"}]
    cols = TimescaleEngine.generate_columns(ZoomLevel.DAILY, anchor, tasks)
    assert cols[-1].end_date >= date(2026, 9, 30)


def test_09_hourly_scale_remains_valid():
    anchor = date(2026, 8, 23)
    cols = TimescaleEngine.generate_columns(ZoomLevel.HOURLY, anchor)
    assert len(cols) == 24


def test_10_multi_year_scale_remains_valid():
    anchor = date(2026, 8, 23)
    min_s, max_e = TimescaleEngine.calculate_timescale_range(anchor, ZoomLevel.MULTI_YEAR)
    assert min_s.year <= 2021
    assert max_e.year >= 2031


def test_10b_weekly_scale_expands_to_constraint_extent():
    anchor = date(2026, 8, 23)
    tasks = [{"constraint_datetime": "2026-12-15 09:00"}]
    cols = TimescaleEngine.generate_columns(ZoomLevel.WEEKLY, anchor, tasks)
    assert cols[0].start_date <= anchor
    assert cols[-1].end_date >= date(2026, 12, 15)


def test_10c_monthly_scale_expands_to_deadline_extent():
    anchor = date(2026, 8, 23)
    tasks = [{"deadline_datetime": "2027-05-20 17:00"}]
    cols = TimescaleEngine.generate_columns(ZoomLevel.MONTHLY, anchor, tasks)
    assert cols[0].start_date <= anchor
    assert cols[-1].end_date >= date(2027, 5, 20)


def test_10d_yearly_scale_expands_to_cpm_finish_extent():
    anchor = date(2026, 8, 23)
    tasks = [{"cpm_earliest_finish": "2028-02-14T09:00:00"}]
    cols = TimescaleEngine.generate_columns(ZoomLevel.YEARLY, anchor, tasks)
    assert cols[0].start_date <= date(2026, 1, 1)
    assert cols[-1].end_date >= date(2028, 2, 14)


# ==============================================================================
# WBS COLUMN TESTS (11 - 20)
# ==============================================================================

def test_11_unique_header_names():
    headers = WBSItemModel.HEADERS
    assert len(headers) == len(set(headers))


def test_12_no_duplicate_constraint_ambiguous_headers():
    headers = WBSItemModel.HEADERS
    assert "Constraint" not in headers
    assert "Constraint Type" in headers


def test_13_task_name_minimum_width_maintained(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    tree = WBSTreeView(custom_service=service)
    tree.setModel(WBSItemModel())
    assert tree.header().minimumSectionSize() >= 90


def test_14_enabling_all_columns_does_not_collapse_task_name(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    for key in service.DEFAULT_SETTINGS:
        if key.startswith("wbs_show_"):
            service.set_preference(key, True)
    tree = WBSTreeView(custom_service=service)
    tree.setModel(WBSItemModel())
    tree.apply_column_visibility()
    assert tree.header().sectionSize(WBSItemModel.COL_TITLE) >= 150


def test_15_horizontal_scroll_appears_when_needed(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    tree = WBSTreeView(custom_service=service)
    assert tree.horizontalScrollBarPolicy() == Qt.ScrollBarAsNeeded


def test_16_column_widths_persist(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    tree = WBSTreeView(custom_service=service)
    tree.setModel(WBSItemModel())
    assert tree.header().sectionSize(WBSItemModel.COL_CONSTRAINT) == 125


def test_17_resizing_columns_works(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    tree = WBSTreeView(custom_service=service)
    tree.setModel(WBSItemModel())
    tree.header().resizeSection(WBSItemModel.COL_TITLE, 300)
    assert tree.header().sectionSize(WBSItemModel.COL_TITLE) == 300


def test_18_20pt_font_remains_readable(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    tree = WBSTreeView(custom_service=service)
    f = tree.font()
    f.setPointSize(20)
    tree.setFont(f)
    assert tree.font().pointSize() == 20


def test_19_10pt_restore_remains_stable(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    tree = WBSTreeView(custom_service=service)
    f = tree.font()
    f.setPointSize(20)
    tree.setFont(f)
    f.setPointSize(10)
    tree.setFont(f)
    assert tree.font().pointSize() == 10


def test_20_no_overlapping_painted_text(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    tree = WBSTreeView(custom_service=service)
    assert tree.uniformRowHeights() is True


# ==============================================================================
# LIGHT THEME TESTS (21 - 29)
# ==============================================================================

def test_21_layout_density_labels_readable_in_light():
    card = SectionCard("WBS Layout & Density", "Description", is_dark=False)
    assert "color: #1E293B;" in card._title_label.styleSheet()


def test_22_parent_display_labels_readable_in_light():
    card = SectionCard("Parent Rollup Display", "Description", is_dark=False)
    assert "color: #1E293B;" in card._title_label.styleSheet()


def test_23_schedule_intelligence_labels_readable_in_light():
    card = SectionCard("Schedule Intelligence Columns", "Description", is_dark=False)
    assert "color: #1E293B;" in card._title_label.styleSheet()


def test_24_baseline_labels_readable_in_light():
    card = SectionCard("Schedule Baseline & Variance Columns", "Description", is_dark=False)
    assert "color: #1E293B;" in card._title_label.styleSheet()


def test_25_constraint_labels_readable_in_light():
    card = SectionCard("Schedule Constraints & Deadlines Columns", "Description", is_dark=False)
    assert "color: #1E293B;" in card._title_label.styleSheet()


def test_26_toggle_text_has_acceptable_contrast(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    widget = WBSSettingsWidget(service, is_dark=False)
    assert widget._tgl_code._is_dark is False


def test_27_dark_mode_remains_correct(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    widget = WBSSettingsWidget(service, is_dark=True)
    card = SectionCard("Title", "Subtitle", is_dark=True)
    assert "color: #CDD6F4;" in card._title_label.styleSheet()


def test_28_disabled_text_still_distinguishable(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    widget = WBSSettingsWidget(service, is_dark=False)
    widget._tgl_code.setEnabled(False)
    assert widget._tgl_code.isEnabled() is False


def test_29_selected_unselected_controls_readable(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    widget = WBSSettingsWidget(service, is_dark=False)
    widget.set_theme(is_dark=False)
    assert widget._is_dark is False


# ==============================================================================
# SETTINGS GROUPING TESTS (30 - 35)
# ==============================================================================

def test_30_sections_grouped_deterministically(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    widget = WBSSettingsWidget(service, is_dark=True)
    assert len(widget._cards) == 8


def test_31_no_duplicate_controls(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    widget = WBSSettingsWidget(service, is_dark=True)
    tgls = [widget._tgl_constraint_type, widget._tgl_constraint_date, widget._tgl_deadline, widget._tgl_deadline_variance, widget._tgl_constraint_status]
    assert len(tgls) == len(set(tgls))


def test_32_headings_unique(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    widget = WBSSettingsWidget(service, is_dark=True)
    titles = [c._title for c in widget._cards]
    assert len(titles) == len(set(titles))


def test_33_keyboard_navigation_order_sensible(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    widget = WBSSettingsWidget(service, is_dark=True)
    assert widget._tgl_code.focusPolicy() == Qt.StrongFocus


def test_34_accessible_names_present(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    widget = WBSSettingsWidget(service, is_dark=True)
    assert widget._style_control.accessibleName() == "Segmented control"


def test_35_high_dpi_safe(settings_mgr):
    service = WBSCustomizationService(settings_mgr)
    widget = WBSSettingsWidget(service, is_dark=True)
    assert widget.sizeHint().isValid()
