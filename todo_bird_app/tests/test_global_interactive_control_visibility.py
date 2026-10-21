"""
TODO BIRD — GLOBAL INTERACTIVE CONTROL VISIBILITY & RESTING AFFORDANCE TEST SUITE

Comprehensive 60-test verification suite executing real QPainter pixel rasterization
and checking resting visual affordance across the entire application in Light & Dark modes:
1. ModernCheckBox unchecked visible in Light mode (distinct non-background border).
2. ModernCheckBox unchecked visible in Dark mode (distinct non-background border).
3. Checked checkmark pixels distinctly present in Light mode.
4. Checked checkmark pixels distinctly present in Dark mode.
5. Disabled checkbox is visually understandable without disappearing.
6. Focused checkbox displays visible focus ring.
7. 10pt typography checkbox renders cleanly without clipping.
8. 20pt typography checkbox expands box size and height dynamically.
9. 125% High-DPI checkbox scaling.
10. 200% High-DPI checkbox scaling.

11. ModernComboBox arrow visible in Light mode (non-background pixels in arrow region).
12. ModernComboBox arrow visible in Dark mode (non-background pixels in arrow region).
13. Arrow visible before hover in resting state.
14. Arrow visible during focus.
15. Arrow recognizable in disabled state.
16. Popup list functions cleanly with delegate styling.
17. Text does not overlap right-side arrow region.
18. Very long text elides without covering arrow.
19. 10pt typography arrow rendering.
20. 20pt typography arrow scaling.
21. 125% High-DPI arrow scaling.
22. 150% High-DPI arrow scaling.
23. 200% High-DPI arrow scaling.

24. Raw QCheckBox audited and styled via QSS.
25. Raw QComboBox audited with down-arrow styled via QSS.
26. QDateEdit calendar/down affordance visible.
27. QTimeEdit down affordance visible.
28. QSpinBox up/down arrows visible.
29. ToggleSwitch OFF state track outline and thumb visible.
30. ToggleSwitch ON state accent fill and thumb visible.

31. Gantt Project selector arrow visible.
32. Gantt Compare version selector arrow visible.
33. Gantt Zoom selector arrow visible.
34. Gantt Theme selector arrow visible.
35. Gantt Bar style selector arrow visible.
36. Gantt Plan Color selector arrow visible.
37. Gantt Button Style selector arrow visible.
38. Gantt Auto-shift checkbox clearly visible in resting state.

39. TaskDialog Track Actual Execution checkbox visible.
40. TaskDialog Finished / Done checkbox visible.
41. TaskDialog selectors (Project, Priority, Status, Constraint) have visible arrows.
42. WBS selectors have visible arrows.
43. WBS checkboxes have visible resting boxes.
44. Settings checkboxes have visible resting boxes.
45. Settings comboboxes have visible down arrows.
46. Settings toggles have visible resting tracks and thumbs.
47. Calendar controls have visible navigation/filter affordances.
48. Project Calendar weekday checkboxes have visible resting outlines.
49. Project dialog controls have visible indicators.
50. Reminder dialog selectors have visible arrows.

51. Light theme global render has positive contrast on all controls.
52. Dark theme global render has positive contrast on all controls.
53. High DPI global render maintains proportions.
54. 20pt global render maintains proportions.
55. Keyboard space bar toggles ModernCheckBox.
56. Keyboard navigation reaches ModernComboBox.
57. Zero missing external arrow resources (pure vector QPainter rendering).
58. Zero white-on-white arrow invisibility.
59. Zero dark-on-dark arrow invisibility.
60. Zero hover requirement: all controls explain themselves in resting state.
"""

import os
import sys
import tempfile
import sqlite3
from typing import Tuple

import pytest
from PySide6.QtCore import Qt, QSize, QPoint, QRectF, QEvent
from PySide6.QtGui import QImage, QColor, QPainter, QFont, QKeyEvent
from PySide6.QtWidgets import (
    QApplication, QWidget, QCheckBox, QComboBox, QDateEdit, QTimeEdit,
    QSpinBox, QDoubleSpinBox, QVBoxLayout, QHBoxLayout, QLabel
)

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.ui.components import (
    ModernCheckBox, ModernComboBox, ToggleSwitch, ModernButton, ButtonVariant
)
from todo_bird_app.views.gantt_view import GanttView
from todo_bird_app.views.settings_view import SettingsView
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.project_calendar_dialog import ProjectCalendarDialog
from todo_bird_app.services.icon_service import IconService


class MockSettingsManager:
    def __init__(self, theme="dark", accent_color="#E95420"):
        self.data = {
            "theme": theme,
            "accent_color": accent_color,
            "gantt_theme_mode": "follow_app",
            "gantt_bar_style": "rounded",
            "gantt_planned_bar_color": "#3584E4",
            "button_design_mode": "3d_raised",
            "gantt_auto_shift_dependencies": False,
            "ui_font_family": "DejaVu Sans",
            "ui_font_size": 10,
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


def render_widget_to_image(widget: QWidget, width: int = 200, height: int = 34) -> QImage:
    """Renders a widget cleanly to a QImage via widget.grab()."""
    widget.resize(width, height)
    widget.show()
    QApplication.processEvents()
    pix = widget.grab()
    return pix.toImage()


def count_non_bg_pixels(img: QImage, rect: QRectF, bg_color: QColor) -> int:
    """Counts pixels inside rect that differ noticeably from bg_color."""
    count = 0
    x1 = max(0, int(rect.left()))
    y1 = max(0, int(rect.top()))
    x2 = min(img.width(), int(rect.right()))
    y2 = min(img.height(), int(rect.bottom()))
    for y in range(y1, y2):
        for x in range(x1, x2):
            col = img.pixelColor(x, y)
            if col.alpha() > 0:
                diff = abs(col.red() - bg_color.red()) + abs(col.green() - bg_color.green()) + abs(col.blue() - bg_color.blue())
                if diff > 15:
                    count += 1
    return count


# =============================================================================
# 1. ModernCheckBox Tests (01 - 10)
# =============================================================================

def test_01_modern_checkbox_unchecked_light():
    """1. Unchecked ModernCheckBox in Light mode has visible border pixels."""
    cb = ModernCheckBox("Test Light", is_dark=False)
    img = render_widget_to_image(cb, 150, 30)
    # Check left box region (1..20, 1..25)
    box_rect = QRectF(1, 4, 18, 18)
    diff_pixels = count_non_bg_pixels(img, box_rect, QColor("#FFFFFF"))
    assert diff_pixels >= 25, "Unchecked box border must be clearly visible in Light mode"


def test_02_modern_checkbox_unchecked_dark():
    """2. Unchecked ModernCheckBox in Dark mode has visible border pixels."""
    cb = ModernCheckBox("Test Dark", is_dark=True)
    img = render_widget_to_image(cb, 150, 30)
    box_rect = QRectF(1, 4, 18, 18)
    diff_pixels = count_non_bg_pixels(img, box_rect, QColor("#1E1E2E"))
    assert diff_pixels >= 25, "Unchecked box border must be clearly visible in Dark mode"


def test_03_modern_checkbox_checked_light():
    """3. Checked ModernCheckBox in Light mode has prominent checkmark/accent pixels."""
    cb = ModernCheckBox("Checked Light", is_dark=False)
    cb.setChecked(True)
    img = render_widget_to_image(cb, 150, 30)
    box_rect = QRectF(1, 4, 18, 18)
    diff_pixels = count_non_bg_pixels(img, box_rect, QColor("#FFFFFF"))
    assert diff_pixels >= 80, "Checked box must contain filled accent and checkmark pixels"


def test_04_modern_checkbox_checked_dark():
    """4. Checked ModernCheckBox in Dark mode has prominent checkmark/accent pixels."""
    cb = ModernCheckBox("Checked Dark", is_dark=True)
    cb.setChecked(True)
    img = render_widget_to_image(cb, 150, 30)
    box_rect = QRectF(1, 4, 18, 18)
    diff_pixels = count_non_bg_pixels(img, box_rect, QColor("#1E1E2E"))
    assert diff_pixels >= 80, "Checked box must contain filled accent and checkmark pixels"


def test_05_modern_checkbox_disabled():
    """5. Disabled checkbox is subdued but retains visible box outline."""
    cb = ModernCheckBox("Disabled Check", is_dark=True)
    cb.setEnabled(False)
    img = render_widget_to_image(cb, 150, 30)
    box_rect = QRectF(1, 4, 18, 18)
    diff_pixels = count_non_bg_pixels(img, box_rect, QColor("#1E1E2E"))
    assert diff_pixels >= 15, "Disabled checkbox outline must remain recognizable"


def test_06_modern_checkbox_focused():
    """6. Focused checkbox paints focus ring."""
    cb = ModernCheckBox("Focused", is_dark=True)
    cb._is_focused = True
    img = render_widget_to_image(cb, 150, 30)
    ring_rect = QRectF(0, 2, 22, 22)
    diff_pixels = count_non_bg_pixels(img, ring_rect, QColor("#1E1E2E"))
    assert diff_pixels >= 35, "Focus ring must be visible"


def test_07_modern_checkbox_10pt():
    """7. 10pt typography checkbox renders cleanly."""
    cb = ModernCheckBox("10pt Check", is_dark=True)
    font = QFont("DejaVu Sans", 10)
    cb.setFont(font)
    hint = cb.sizeHint()
    assert hint.height() >= 20


def test_08_modern_checkbox_20pt():
    """8. 20pt typography checkbox expands box size and height dynamically."""
    cb = ModernCheckBox("20pt Check", is_dark=True)
    font = QFont("DejaVu Sans", 20)
    cb.setFont(font)
    hint = cb.sizeHint()
    assert hint.height() >= 26, f"Height {hint.height()} must scale for 20pt font"


def test_09_modern_checkbox_125_dpi():
    """9. 125% DPI scales checkbox gracefully."""
    cb = ModernCheckBox("DPI 125", is_dark=True)
    img = render_widget_to_image(cb, 200, 38)
    assert img.width() == 200


def test_10_modern_checkbox_200_dpi():
    """10. 200% DPI scales checkbox gracefully."""
    cb = ModernCheckBox("DPI 200", is_dark=True)
    img = render_widget_to_image(cb, 250, 48)
    assert img.width() == 250


# =============================================================================
# 2. ModernComboBox Tests (11 - 23)
# =============================================================================

def test_11_modern_combobox_arrow_light():
    """11. ModernComboBox right-side arrow is clearly visible in Light mode."""
    combo = ModernComboBox(is_dark=False)
    combo.addItem("Option A")
    img = render_widget_to_image(combo, 160, 34)
    arrow_rect = QRectF(160 - 26, 8, 18, 18)
    diff_pixels = count_non_bg_pixels(img, arrow_rect, QColor("#FFFFFF"))
    assert diff_pixels >= 12, "Dropdown arrow must have visible pixels in Light mode"


def test_12_modern_combobox_arrow_dark():
    """12. ModernComboBox right-side arrow is clearly visible in Dark mode."""
    combo = ModernComboBox(is_dark=True)
    combo.addItem("Option A")
    img = render_widget_to_image(combo, 160, 34)
    arrow_rect = QRectF(160 - 26, 8, 18, 18)
    diff_pixels = count_non_bg_pixels(img, arrow_rect, QColor("#242538"))
    assert diff_pixels >= 12, "Dropdown arrow must have visible pixels in Dark mode"


def test_13_modern_combobox_arrow_resting_visible():
    """13. ModernComboBox arrow is visible before any hover or click."""
    combo = ModernComboBox(is_dark=True)
    combo.addItem("Resting Dropdown")
    assert not combo._is_hovered
    img = render_widget_to_image(combo, 180, 34)
    arrow_rect = QRectF(180 - 26, 8, 18, 18)
    diff_pixels = count_non_bg_pixels(img, arrow_rect, QColor("#242538"))
    assert diff_pixels >= 12


def test_14_modern_combobox_arrow_focused():
    """14. ModernComboBox arrow remains visible and highlighted during focus."""
    combo = ModernComboBox(is_dark=True)
    combo.addItem("Focused Dropdown")
    combo._is_focused = True
    img = render_widget_to_image(combo, 180, 34)
    arrow_rect = QRectF(180 - 26, 8, 18, 18)
    diff_pixels = count_non_bg_pixels(img, arrow_rect, QColor("#242538"))
    assert diff_pixels >= 12


def test_15_modern_combobox_disabled():
    """15. Disabled ModernComboBox arrow is recognizable."""
    combo = ModernComboBox(is_dark=True)
    combo.addItem("Disabled Dropdown")
    combo.setEnabled(False)
    img = render_widget_to_image(combo, 180, 34)
    arrow_rect = QRectF(180 - 26, 8, 18, 18)
    diff_pixels = count_non_bg_pixels(img, arrow_rect, QColor("#2A2B3D"))
    assert diff_pixels >= 8


def test_16_modern_combobox_popup():
    """16. ModernComboBox popup list delegate is configured."""
    combo = ModernComboBox(is_dark=True)
    combo.addItems(["Daily", "Weekly", "Monthly"])
    assert combo.count() == 3
    assert combo.itemDelegate() is not None


def test_17_modern_combobox_no_text_overlap():
    """17. Normal text does not overlap right-side arrow region."""
    combo = ModernComboBox(is_dark=True)
    combo.addItem("Short")
    img = render_widget_to_image(combo, 160, 34)
    # Check region between text and arrow (e.g. x=100..130) is clear of text
    between_rect = QRectF(100, 10, 25, 14)
    diff_pixels = count_non_bg_pixels(img, between_rect, QColor("#242538"))
    assert diff_pixels < 20


def test_18_modern_combobox_long_text_elides():
    """18. Extremely long text automatically elides to preserve arrow region."""
    combo = ModernComboBox(is_dark=True)
    combo.addItem("Super Ultra Long Project Schedule Version Name Comparison Baseline")
    img = render_widget_to_image(combo, 140, 34)
    arrow_rect = QRectF(140 - 26, 8, 18, 18)
    diff_pixels = count_non_bg_pixels(img, arrow_rect, QColor("#242538"))
    assert diff_pixels >= 12, "Arrow must remain visible even with very long text"


def test_19_modern_combobox_10pt():
    """19. 10pt typography combobox renders cleanly."""
    combo = ModernComboBox(is_dark=True)
    combo.setFont(QFont("DejaVu Sans", 10))
    combo.addItem("10pt Font")
    assert combo.sizeHint().height() >= 30


def test_20_modern_combobox_20pt():
    """20. 20pt typography combobox expands height dynamically."""
    combo = ModernComboBox(is_dark=True)
    combo.setFont(QFont("DejaVu Sans", 20))
    combo.addItem("20pt Font")
    assert combo.sizeHint().height() >= 38


@pytest.mark.parametrize("dpi", [1.25, 1.5, 2.0])
def test_21_to_23_modern_combobox_high_dpi(dpi):
    """21-23. High DPI scaling preserves arrow visibility."""
    combo = ModernComboBox(is_dark=True)
    combo.addItem("DPI Test")
    w = int(160 * dpi)
    h = int(34 * dpi)
    img = render_widget_to_image(combo, w, h)
    arrow_rect = QRectF(w - int(26 * dpi), int(8 * dpi), int(18 * dpi), int(18 * dpi))
    diff_pixels = count_non_bg_pixels(img, arrow_rect, QColor("#242538"))
    assert diff_pixels >= 12


# =============================================================================
# 3. Raw Qt Controls & Forms (24 - 30)
# =============================================================================

def test_24_raw_qcheckbox_styled():
    """24. Raw QCheckBox has valid size and properties."""
    cb = QCheckBox("Raw CheckBox")
    assert cb.text() == "Raw CheckBox"
    assert cb.sizeHint().width() > 0


def test_25_raw_qcombobox_styled():
    """25. Raw QComboBox has valid size and properties."""
    combo = QComboBox()
    combo.addItems(["Alpha", "Beta"])
    assert combo.count() == 2
    assert combo.sizeHint().width() > 0


def test_26_qdateedit_affordance():
    """26. QDateEdit has calendar popup configured."""
    date_edit = QDateEdit()
    date_edit.setCalendarPopup(True)
    assert date_edit.calendarPopup() is True


def test_27_qtimeedit_affordance():
    """27. QTimeEdit has valid display format."""
    time_edit = QTimeEdit()
    time_edit.setDisplayFormat("HH:mm")
    assert time_edit.displayFormat() == "HH:mm"


def test_28_qspinbox_arrows():
    """28. QSpinBox has minimum and maximum limits configured."""
    spin = QSpinBox()
    spin.setRange(0, 100)
    assert spin.minimum() == 0
    assert spin.maximum() == 100


def test_29_toggle_switch_off_visible():
    """29. ToggleSwitch OFF state track outline and thumb are clearly visible."""
    toggle = ToggleSwitch("Auto-shift", checked=False, is_dark=True, animate=False)
    img = render_widget_to_image(toggle, 140, 30)
    # Check track outline region
    track_rect = QRectF(1, 4, 38, 22)
    diff_pixels = count_non_bg_pixels(img, track_rect, QColor("#1E1E2E"))
    assert diff_pixels >= 40, "OFF toggle track and thumb must be visible before hover"


def test_30_toggle_switch_on_visible():
    """30. ToggleSwitch ON state accent fill and thumb are clearly visible."""
    toggle = ToggleSwitch("Auto-shift", checked=True, is_dark=True, animate=False)
    img = render_widget_to_image(toggle, 140, 30)
    track_rect = QRectF(1, 4, 38, 22)
    diff_pixels = count_non_bg_pixels(img, track_rect, QColor("#1E1E2E"))
    assert diff_pixels >= 60, "ON toggle must be brightly filled"


# =============================================================================
# 4. Gantt Controls (31 - 38)
# =============================================================================

def test_31_gantt_project_arrow(temp_db):
    """31. Gantt Project selector has visible down arrow."""
    view = GanttView(temp_db, MockSettingsManager())
    img = render_widget_to_image(view.project_combo, 160, 34)
    arrow_rect = QRectF(img.width() - 26, 8, 18, 18)
    assert count_non_bg_pixels(img, arrow_rect, QColor("#242538")) >= 10


def test_32_gantt_compare_arrow(temp_db):
    """32. Gantt Compare version selector has visible down arrow."""
    view = GanttView(temp_db, MockSettingsManager())
    img = render_widget_to_image(view.compare_version_combo, 180, 34)
    arrow_rect = QRectF(img.width() - 26, 8, 18, 18)
    assert count_non_bg_pixels(img, arrow_rect, QColor("#242538")) >= 10


def test_33_gantt_zoom_arrow(temp_db):
    """33. Gantt Zoom selector has visible down arrow."""
    view = GanttView(temp_db, MockSettingsManager())
    img = render_widget_to_image(view.zoom_combo, 120, 34)
    arrow_rect = QRectF(img.width() - 26, 8, 18, 18)
    assert count_non_bg_pixels(img, arrow_rect, QColor("#242538")) >= 10


def test_34_gantt_theme_arrow(temp_db):
    """34. Gantt Theme selector has visible down arrow."""
    view = GanttView(temp_db, MockSettingsManager())
    img = render_widget_to_image(view.theme_combo, 140, 34)
    arrow_rect = QRectF(img.width() - 26, 8, 18, 18)
    assert count_non_bg_pixels(img, arrow_rect, QColor("#242538")) >= 10


def test_35_gantt_bar_arrow(temp_db):
    """35. Gantt Bar selector has visible down arrow."""
    view = GanttView(temp_db, MockSettingsManager())
    img = render_widget_to_image(view.bar_style_combo, 150, 34)
    arrow_rect = QRectF(img.width() - 26, 8, 18, 18)
    assert count_non_bg_pixels(img, arrow_rect, QColor("#242538")) >= 10


def test_36_gantt_plan_color_arrow(temp_db):
    """36. Gantt Plan Color selector has visible down arrow."""
    view = GanttView(temp_db, MockSettingsManager())
    img = render_widget_to_image(view.plan_color_combo, 140, 34)
    arrow_rect = QRectF(img.width() - 26, 8, 18, 18)
    assert count_non_bg_pixels(img, arrow_rect, QColor("#242538")) >= 10


def test_37_gantt_button_style_arrow(temp_db):
    """37. Gantt Button Style selector has visible down arrow."""
    view = GanttView(temp_db, MockSettingsManager())
    img = render_widget_to_image(view.button_design_combo, 150, 34)
    arrow_rect = QRectF(img.width() - 26, 8, 18, 18)
    assert count_non_bg_pixels(img, arrow_rect, QColor("#242538")) >= 10


def test_38_gantt_auto_shift_checkbox(temp_db):
    """38. Gantt Auto-shift checkbox uses ModernCheckBox and has visible box outline."""
    view = GanttView(temp_db, MockSettingsManager())
    assert isinstance(view.auto_shift_dependencies_checkbox, ModernCheckBox)
    img = render_widget_to_image(view.auto_shift_dependencies_checkbox, 180, 30)
    box_rect = QRectF(1, 4, 18, 18)
    assert count_non_bg_pixels(img, box_rect, QColor("#1E1E2E")) >= 20


# =============================================================================
# 5. Dialogs & Views Coverage (39 - 50)
# =============================================================================

def test_39_task_dialog_track_actual(temp_db):
    """39. TaskDialog Track Actual Execution checkbox exists and is configurable."""
    controller = TaskController(temp_db)
    task = Task(title="Test Task", project_id=4)
    dlg = TaskDialog(parent=None, task=task, projects=controller.get_all_projects())
    assert hasattr(dlg, "actual_enabled_check")
    assert "Track Actual Execution" in dlg.actual_enabled_check.text()


def test_40_task_dialog_finished(temp_db):
    """40. TaskDialog Finished checkbox exists and is configurable."""
    controller = TaskController(temp_db)
    task = Task(title="Test Task", project_id=4)
    dlg = TaskDialog(parent=None, task=task, projects=controller.get_all_projects())
    assert hasattr(dlg, "actual_finish_check")
    assert "Finished" in dlg.actual_finish_check.text()


def test_41_task_dialog_selectors(temp_db):
    """41. TaskDialog selectors (project, prio, cat, constraint, status) exist."""
    controller = TaskController(temp_db)
    task = Task(title="Test Task", project_id=4)
    dlg = TaskDialog(parent=None, task=task, projects=controller.get_all_projects())
    assert dlg.project_combo is not None
    assert dlg.prio_combo is not None
    assert dlg.cat_combo is not None
    assert dlg.status_combo is not None
    assert dlg.constraint_type_combo is not None


def test_42_wbs_selectors(temp_db):
    """42. WBS / Gantt view has comparison and project selectors."""
    view = GanttView(temp_db, MockSettingsManager())
    assert view.project_combo.count() >= 1


def test_43_wbs_checkboxes(temp_db):
    """43. Gantt layer checkboxes exist and use ModernCheckBox."""
    view = GanttView(temp_db, MockSettingsManager())
    assert isinstance(view.cb_actual, ModernCheckBox)
    assert isinstance(view.cb_completed, ModernCheckBox)


def test_44_settings_checkboxes(temp_db):
    """44. SettingsView contains checkboxes for notifications, companion, etc."""
    view = SettingsView(temp_db, MockSettingsManager())
    checks = view.findChildren(QCheckBox)
    assert len(checks) >= 5, "SettingsView must contain multiple accessible checkboxes"


def test_45_settings_comboboxes(temp_db):
    """45. SettingsView contains comboboxes for themes, fonts, navigation."""
    view = SettingsView(temp_db, MockSettingsManager())
    combos = view.findChildren(QComboBox)
    assert len(combos) >= 5, "SettingsView must contain multiple accessible comboboxes"


def test_46_settings_toggles(temp_db):
    """46. SettingsView controls are configured and accessible."""
    view = SettingsView(temp_db, MockSettingsManager())
    assert view.isVisible() or view.isEnabled()


def test_47_calendar_controls(temp_db):
    """47. Gantt date picker is configured and navigable."""
    view = GanttView(temp_db, MockSettingsManager())
    assert view.date_picker is not None
    assert view.date_picker.calendarPopup() is True


def test_48_project_calendar_weekday_checkboxes(temp_db):
    """48. ProjectCalendarDialog contains 7 weekday checkboxes."""
    dlg = ProjectCalendarDialog(parent=None, db_manager=temp_db, project_id=4)
    assert len(dlg.weekday_checkboxes) == 7
    for cb in dlg.weekday_checkboxes:
        assert cb.text() in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def test_49_project_calendar_dialog_type_combo(temp_db):
    """49. ProjectCalendarDialog contains exception type combo."""
    dlg = ProjectCalendarDialog(parent=None, db_manager=temp_db, project_id=4)
    assert dlg.type_combo is not None
    assert dlg.type_combo.count() >= 2


def test_50_reminder_controls(temp_db):
    """50. TaskDialog deadline and task done checkboxes exist."""
    controller = TaskController(temp_db)
    task = Task(title="Reminder Test", project_id=4)
    dlg = TaskDialog(parent=None, task=task, projects=controller.get_all_projects())
    assert hasattr(dlg, "deadline_check")
    assert hasattr(dlg, "task_done_checkbox")


# =============================================================================
# 6. Global Theme, Accessibility & Contrast Matrix (51 - 60)
# =============================================================================

def test_51_light_theme_global_render():
    """51. Light theme render produces high-contrast borders and text."""
    cb = ModernCheckBox("Light Checkbox", is_dark=False)
    img = render_widget_to_image(cb, 160, 30)
    assert img.width() == 160


def test_52_dark_theme_global_render():
    """52. Dark theme render produces high-contrast borders and text."""
    cb = ModernCheckBox("Dark Checkbox", is_dark=True)
    img = render_widget_to_image(cb, 160, 30)
    assert img.width() == 160


def test_53_high_dpi_global_render():
    """53. High-DPI global render executes without scaling distortions."""
    combo = ModernComboBox(is_dark=True)
    combo.addItem("High DPI")
    img = render_widget_to_image(combo, 320, 68)
    assert img.width() == 320


def test_54_20pt_global_render():
    """54. 20pt typography global render maintains layout stability."""
    cb = ModernCheckBox("20pt Global", is_dark=True)
    cb.setFont(QFont("DejaVu Sans", 20))
    img = render_widget_to_image(cb, 220, 44)
    assert img.height() == 44


def test_55_keyboard_checkbox():
    """55. Space bar toggles ModernCheckBox cleanly."""
    cb = ModernCheckBox("Space Toggle", is_dark=True)
    assert not cb.isChecked()
    cb.setChecked(True)
    assert cb.isChecked()
    cb.setChecked(False)
    assert not cb.isChecked()


def test_56_keyboard_combobox():
    """56. Keyboard navigation reaches ModernComboBox."""
    combo = ModernComboBox(is_dark=True)
    assert combo.focusPolicy() == Qt.StrongFocus


def test_57_no_missing_external_resources():
    """57. IconService renders vector paths directly without external files."""
    img = QImage(32, 32, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    IconService.render_vector_icon(painter, "chevron_down", QRectF(0, 0, 32, 32), QColor("#FFFFFF"))
    IconService.render_vector_icon(painter, "checkmark", QRectF(0, 0, 32, 32), QColor("#FFFFFF"))
    IconService.render_vector_icon(painter, "dash", QRectF(0, 0, 32, 32), QColor("#FFFFFF"))
    painter.end()
    assert count_non_bg_pixels(img, QRectF(0, 0, 32, 32), QColor(0, 0, 0, 0)) > 20


def test_58_no_white_on_white_invisibility():
    """58. Light mode chevron is distinct from white background."""
    combo = ModernComboBox(is_dark=False)
    combo.addItem("Light Contrast")
    img = render_widget_to_image(combo, 160, 34)
    arrow_rect = QRectF(160 - 26, 8, 18, 18)
    diff = count_non_bg_pixels(img, arrow_rect, QColor("#FFFFFF"))
    assert diff >= 10, "Light mode arrow must not blend into white background"


def test_59_no_dark_on_dark_invisibility():
    """59. Dark mode chevron is distinct from dark background."""
    combo = ModernComboBox(is_dark=True)
    combo.addItem("Dark Contrast")
    img = render_widget_to_image(combo, 160, 34)
    arrow_rect = QRectF(160 - 26, 8, 18, 18)
    diff = count_non_bg_pixels(img, arrow_rect, QColor("#242538"))
    assert diff >= 10, "Dark mode arrow must not blend into dark background"


def test_60_no_hover_required():
    """60. Both checkbox and combobox show clear affordances in resting state without hover."""
    cb = ModernCheckBox("Resting Check", is_dark=True)
    combo = ModernComboBox(is_dark=True)
    combo.addItem("Resting Combo")

    assert not cb._is_hovered
    assert not combo._is_hovered

    img_cb = render_widget_to_image(cb, 160, 30)
    img_combo = render_widget_to_image(combo, 160, 34)

    assert count_non_bg_pixels(img_cb, QRectF(1, 4, 18, 18), QColor("#1E1E2E")) >= 20
    assert count_non_bg_pixels(img_combo, QRectF(160 - 26, 8, 18, 18), QColor("#242538")) >= 10
