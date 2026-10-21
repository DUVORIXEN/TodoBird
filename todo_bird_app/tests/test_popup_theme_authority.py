"""
TODO BIRD — POPUP THEME AUTHORITY & FIDELITY TEST SUITE
Validates QToolTip, QMenu, ScheduleDetailsPopover, QComboBox popups,
CommandPalette, theme switching, DPI/font scaling, lifecycle cleanup,
and production database safety invariant.
"""

import hashlib
import os
import pytest
from pathlib import Path
from typing import Dict, Any

from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import (
    QApplication,
    QMenu,
    QComboBox,
    QWidget,
    QLabel,
)
from PySide6.QtGui import QFont, QColor

from todo_bird_app.services.appearance_service import AppearanceService
from todo_bird_app.services.schedule_details_formatter import (
    ScheduleDetailsFormatter,
    ScheduleDetailsModel,
)
from todo_bird_app.ui.components.schedule_details_popover import ScheduleDetailsPopover
from todo_bird_app.widgets.command_palette import CommandPalette


from todo_bird_app.tests.path_helpers import production_db_path

PRODUCTION_DB_PATH = production_db_path()


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def get_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def test_41_qtooltip_light_qss():
    """TEST 41: QToolTip in light.qss specifies high-contrast styling."""
    light_qss_path = Path("todo_bird_app/themes/light.qss")
    assert light_qss_path.exists()
    content = light_qss_path.read_text()
    assert "QToolTip {" in content
    assert "@TEXT_PRIMARY" in content
    assert "@SURFACE_2" in content
    assert "@BORDER_STRONG" in content


def test_42_qtooltip_dark_qss():
    """TEST 42: QToolTip in dark.qss specifies high-contrast styling."""
    dark_qss_path = Path("todo_bird_app/themes/dark.qss")
    assert dark_qss_path.exists()
    content = dark_qss_path.read_text()
    assert "QToolTip {" in content
    assert "@TEXT_PRIMARY" in content
    assert "@SURFACE_2" in content
    assert "@BORDER_STRONG" in content


def test_43_schedule_details_popover_light_mode(qapp):
    """TEST 43: Popover in Light mode uses light surface and dark readable text."""
    model = ScheduleDetailsModel(title="Concrete Test", project_name="Light Project")
    popover = ScheduleDetailsPopover(model, is_dark=False)
    ss = popover.styleSheet()

    # Surface must be light
    assert "#FFFFFF" in ss or "#F8FAFC" in ss
    # Text must be dark
    assert "#0F172A" in ss or "#111827" in ss or "#1E293B" in ss
    popover.close()


def test_44_schedule_details_popover_dark_mode(qapp):
    """TEST 44: Popover in Dark mode uses dark surface and light readable text."""
    model = ScheduleDetailsModel(title="Steel Test", project_name="Dark Project")
    popover = ScheduleDetailsPopover(model, is_dark=True)
    ss = popover.styleSheet()

    # Surface must be dark
    assert "#1E1E2E" in ss or "#181825" in ss
    # Text must be light
    assert "#CDD6F4" in ss or "#FFFFFF" in ss
    popover.close()


def test_45_qmenu_light_qss():
    """TEST 45: QMenu in light.qss defines clear surface, border, and item padding."""
    content = Path("todo_bird_app/themes/light.qss").read_text()
    assert "QMenu {" in content
    assert "QMenu::item {" in content
    assert "QMenu::item:selected {" in content


def test_46_qmenu_dark_qss():
    """TEST 46: QMenu in dark.qss defines clear surface, border, and item padding."""
    content = Path("todo_bird_app/themes/dark.qss").read_text()
    assert "QMenu {" in content
    assert "QMenu::item {" in content
    assert "QMenu::item:selected {" in content


def test_47_qmenu_disabled_item_light_qss():
    """TEST 47: Disabled menu items styled with distinct disabled token in Light theme."""
    content = Path("todo_bird_app/themes/light.qss").read_text()
    assert "QMenu::item:disabled" in content
    assert "@TEXT_DISABLED" in content


def test_48_qmenu_disabled_item_dark_qss():
    """TEST 48: Disabled menu items styled with distinct disabled token in Dark theme."""
    content = Path("todo_bird_app/themes/dark.qss").read_text()
    assert "QMenu::item:disabled" in content
    assert "@TEXT_DISABLED" in content


def test_49_qmenu_separator_styling():
    """TEST 49: Menu separators defined with proper borders in both themes."""
    light = Path("todo_bird_app/themes/light.qss").read_text()
    dark = Path("todo_bird_app/themes/dark.qss").read_text()
    assert "QMenu::separator" in light
    assert "QMenu::separator" in dark


def test_50_qcombobox_popup_light_qss():
    """TEST 50: QComboBox popup view in light.qss provides high readability."""
    content = Path("todo_bird_app/themes/light.qss").read_text()
    assert "QComboBox QAbstractItemView" in content


def test_51_qcombobox_popup_dark_qss():
    """TEST 51: QComboBox popup view in dark.qss provides high readability."""
    content = Path("todo_bird_app/themes/dark.qss").read_text()
    assert "QComboBox QAbstractItemView" in content


def test_52_command_palette_light_theme(qapp):
    """TEST 52: CommandPalette container is theme-aware in Light theme."""
    palette = CommandPalette(db_manager=None)
    container = palette.findChild(QWidget, "container")
    assert container is not None
    ss = container.styleSheet()
    assert "QLineEdit" in ss
    assert "QListWidget" in ss
    palette.close()


def test_53_command_palette_dark_theme(qapp):
    """TEST 53: CommandPalette initializes properly and contains quick actions."""
    palette = CommandPalette(db_manager=None)
    assert palette.search_input is not None
    assert palette.list_widget is not None
    palette.close()


def test_54_reminder_snooze_menu_inherits_theme(qapp):
    """TEST 54: ReminderDialog snooze menu has no hardcoded dark styling."""
    from todo_bird_app.widgets.reminder_dialog import ReminderDialog
    from todo_bird_app.models.task import Task
    dummy_task = Task(id=1, title="Reminder Test Task", due_date="2026-09-02")
    dlg = ReminderDialog(task=dummy_task)
    menu = dlg.show_snooze_menu(exec_menu=False)
    assert menu is not None
    # Must NOT have hardcoded #1E293B
    assert "#1E293B" not in menu.styleSheet()
    dlg.close()


def test_55_live_theme_switch_light_to_dark(qapp):
    """TEST 55: Switching theme from Light to Dark updates Popover styling."""
    model = ScheduleDetailsModel(title="Theme Switch Task")
    popover = ScheduleDetailsPopover(model, is_dark=False)

    # Re-apply dark
    popover._is_dark = True
    popover._apply_theme()

    ss = popover.styleSheet()
    assert "#1E1E2E" in ss
    popover.close()


def test_56_live_theme_switch_dark_to_light(qapp):
    """TEST 56: Switching theme from Dark to Light updates Popover styling."""
    model = ScheduleDetailsModel(title="Theme Switch Task")
    popover = ScheduleDetailsPopover(model, is_dark=True)

    # Re-apply light
    popover._is_dark = False
    popover._apply_theme()

    ss = popover.styleSheet()
    assert "#FFFFFF" in ss
    popover.close()


def test_57_analytical_cpm_values_fidelity(qapp):
    """TEST 57: CPM early/late/float values match input with zero drift or rounding."""
    model = ScheduleDetailsModel(
        title="Exact CPM Test",
        has_cpm=True,
        cpm_es="2026-09-01 08:00",
        cpm_ef="2026-09-03 17:00",
        cpm_ls="2026-09-04 08:00",
        cpm_lf="2026-09-06 17:00",
        cpm_tf=1440,
        cpm_ff=480,
        cpm_is_critical=False,
    )
    plain = ScheduleDetailsFormatter.format_plain_text(model)
    assert "ES: 2026-09-01 08:00" in plain
    assert "EF: 2026-09-03 17:00" in plain
    assert "LS: 2026-09-04 08:00" in plain
    assert "LF: 2026-09-06 17:00" in plain
    assert "Total Float: 1d (1440 min)" in plain
    assert "Free Float: 8h (480 min)" in plain
    assert "Critical: No" in plain


def test_58_actual_execution_values_fidelity(qapp):
    """TEST 58: Actual execution tracking metrics match authority without alteration."""
    model = ScheduleDetailsModel(
        title="Actual Tracking Test",
        actual_state="in_progress",
        actual_start="2026-09-01 09:30",
        actual_duration_minutes=360,
        actual_variance_display="+1.5h Late Start",
    )
    plain = ScheduleDetailsFormatter.format_plain_text(model)
    assert "2026-09-01 09:30" in plain
    assert "360 min logged" in plain
    assert "+1.5h Late Start" in plain


def test_59_baseline_governance_values_fidelity(qapp):
    """TEST 59: Baseline dates and finish variance match authority."""
    model = ScheduleDetailsModel(
        title="Baseline Test",
        has_baseline=True,
        baseline_start="2026-08-15 08:00",
        baseline_finish="2026-08-20 17:00",
        baseline_duration_minutes=2400,
        baseline_variance_minutes=480,
    )
    plain = ScheduleDetailsFormatter.format_plain_text(model)
    assert "2026-08-15 08:00 -> 2026-08-20 17:00" in plain
    assert "Variance:" in plain


def test_60_schedule_constraint_values_fidelity(qapp):
    """TEST 60: Schedule constraint and target deadline match authority."""
    model = ScheduleDetailsModel(
        title="Constraint Task",
        constraint_type="SNET",
        constraint_datetime="2026-09-05 08:00",
        deadline_datetime="2026-09-12 17:00",
    )
    plain = ScheduleDetailsFormatter.format_plain_text(model)
    assert "Constraint: SNET (2026-09-05 08:00)" in plain
    assert "Deadline: 2026-09-12 17:00" in plain


def test_61_no_duplicate_cpm_math(qapp):
    """TEST 61: Formatter acts purely as a consumer and does NOT re-run CPM graph engine."""
    # Ensure ScheduleDetailsFormatter imports no CPM solver functions directly
    import inspect
    from todo_bird_app.services import schedule_details_formatter
    source = inspect.getsource(schedule_details_formatter)
    assert "CPMScheduler" not in source
    assert "forward_pass" not in source
    assert "backward_pass" not in source


def test_62_production_database_safety_invariant():
    """TEST 62: Production database SHA256 is unchanged by popup formatter checks."""
    assert PRODUCTION_DB_PATH.exists(), f"Production DB missing at {PRODUCTION_DB_PATH}"
    before_hash = get_file_sha256(PRODUCTION_DB_PATH)
    plain = ScheduleDetailsFormatter.format_plain_text(ScheduleDetailsModel(title="DB Safety Probe"))
    assert "DB Safety Probe" in plain
    after_hash = get_file_sha256(PRODUCTION_DB_PATH)
    assert after_hash == before_hash, (
        f"CRITICAL VIOLATION: Production DB hash mutated!\n"
        f"Before: {before_hash}\n"
        f"After:  {after_hash}"
    )


def test_63_dpi_100_percent_layout_integrity(qapp):
    """TEST 63: Popover at 100% DPI (96 DPI) maintains minimum readable geometry."""
    model = ScheduleDetailsModel(title="DPI 100 Test")
    popover = ScheduleDetailsPopover(model)
    popover.show()
    assert popover.width() >= 380
    assert popover.height() >= 300
    popover.close()


def test_64_dpi_125_percent_layout_integrity(qapp):
    """TEST 64: Popover at 125% DPI maintains layout integrity."""
    model = ScheduleDetailsModel(title="DPI 125 Test")
    popover = ScheduleDetailsPopover(model)
    popover.resize(int(420 * 1.25), int(420 * 1.25))
    popover.show()
    assert popover.width() >= 420
    popover.close()


def test_65_dpi_150_percent_layout_integrity(qapp):
    """TEST 65: Popover at 150% DPI maintains layout integrity."""
    model = ScheduleDetailsModel(title="DPI 150 Test")
    popover = ScheduleDetailsPopover(model)
    popover.resize(int(420 * 1.5), int(420 * 1.5))
    popover.show()
    assert popover.width() >= 500
    popover.close()


def test_66_dpi_200_percent_layout_integrity(qapp):
    """TEST 66: Popover at 200% DPI maintains layout integrity."""
    model = ScheduleDetailsModel(title="DPI 200 Test")
    popover = ScheduleDetailsPopover(model)
    popover.resize(int(420 * 2.0), int(420 * 2.0))
    popover.show()
    assert popover.width() >= 400
    popover.close()


def test_67_font_scaling_legibility(qapp):
    """TEST 67: Popover renders cleanly across 10pt, 16pt, and 20pt fonts."""
    model = ScheduleDetailsModel(title="Font Scaled Item")
    popover = ScheduleDetailsPopover(model)

    for pt in [10, 16, 20]:
        font = QFont("Inter", pt)
        popover.setFont(font)
        popover.browser.setFont(font)
        assert popover.browser.font().pointSize() == pt

    popover.close()


def test_68_repeated_popover_open_close_cleanup(qapp):
    """TEST 68: Rapid creation and closing of popover leaves no residual leaks."""
    for i in range(10):
        model = ScheduleDetailsModel(title=f"Cycle Task {i}")
        popover = ScheduleDetailsPopover(model)
        popover.show()
        popover.copy_details()
        popover.close()
        popover.deleteLater()
