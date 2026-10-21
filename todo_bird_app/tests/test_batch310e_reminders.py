import pytest
import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QComboBox, QSpinBox, QRadioButton
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont, QColor
from PySide6.QtTest import QTest

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.services.typography_service import TypographyService
from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
from todo_bird_app.widgets.reminder_dialog import ReminderDialog
from todo_bird_app.views.settings_view import SettingsView

@pytest.fixture(scope="session")
def qapp():
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app

@pytest.fixture
def temp_env():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_310e.db")
    db = DatabaseManager(db_path)
    settings = SettingsManager(db, config_dir=Path(temp_dir))
    ReminderPolicyService.reset_session_state()
    yield db, settings, temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)

def _activate_tab_of(view, widget):
    """QTest clicks route through the window, so the widget's tab page must
    be the current one before mouseClick can land."""
    page = widget
    while page is not None and page.parentWidget() is not None:
        if type(page.parentWidget()).__name__ == "QStackedWidget":
            view.settings_tabs.setCurrentWidget(page)
            return
        page = page.parentWidget()


# REM-E01: Override controls enable correctly
def test_rem_e01_override_controls_enable(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", False)
    view = SettingsView(db, settings)
    view.show()

    assert view.cb_rem_use_global.isChecked()
    assert not view.rem_fam_combo.isEnabled()
    assert not view.rem_sz_spin.isEnabled()
    assert not view.rem_wt_combo.isEnabled()

    # Uncheck "Use global Todo Bird font"
    view.cb_rem_use_global.click()
    assert not view.cb_rem_use_global.isChecked()
    assert view.rem_fam_combo.isEnabled()
    assert view.rem_sz_spin.isEnabled()
    assert view.rem_wt_combo.isEnabled()
    assert settings.get("font_override_reminder") is True

# REM-E02: Font family clickable & interactive
def test_rem_e02_font_family_clickable(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    view = SettingsView(db, settings)
    view.show()

    # Change family
    idx = view.rem_fam_combo.findText("Liberation Mono")
    if idx < 0:
        view.rem_fam_combo.addItem("Liberation Mono")
        idx = view.rem_fam_combo.findText("Liberation Mono")

    view.rem_fam_combo.setCurrentIndex(idx)
    assert settings.get("font_family_reminder") == "Liberation Mono"
    assert view.rem_preview_title.font().family() == "Liberation Mono"

# REM-E03: Font size clickable & changes preview
def test_rem_e03_font_size_clickable(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    view = SettingsView(db, settings)
    view.show()

    # Set value
    view.rem_sz_spin.setValue(16)
    assert settings.get("font_size_reminder") == 16
    # Title gets base + 4 = 20pt
    assert view.rem_preview_title.font().pointSize() == 20
    assert view.rem_preview_desc.font().pointSize() == 16

# REM-E04: Font weight clickable & changes preview
def test_rem_e04_font_weight_clickable(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    view = SettingsView(db, settings)
    view.show()

    view.rem_wt_combo.setCurrentText("Bold")
    assert settings.get("font_weight_reminder") == "bold"
    assert view.rem_preview_title.font().bold()

# REM-E05: Automatic color works
def test_rem_e05_automatic_color_works(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_color_mode_reminder", "custom")
    settings.set("font_color_reminder", "#E95420")
    view = SettingsView(db, settings)
    view.show()
    _activate_tab_of(view, view.rb_rem_color_auto)

    # Click auto radio
    QTest.mouseClick(view.rb_rem_color_auto, Qt.LeftButton)
    assert view.rb_rem_color_auto.isChecked()
    assert not view.btn_choose_rem_color.isEnabled()
    assert settings.get("font_color_mode_reminder") == "auto"
    assert TypographyService.get_font_color_for_area("reminder", settings) is None

# REM-E06: Custom color selector visible and enabled
def test_rem_e06_custom_color_selector_enabled(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_color_mode_reminder", "auto")
    view = SettingsView(db, settings)
    view.show()
    _activate_tab_of(view, view.rb_rem_color_custom)

    # Click custom radio
    QTest.mouseClick(view.rb_rem_color_custom, Qt.LeftButton)
    assert view.rb_rem_color_custom.isChecked()
    assert view.btn_choose_rem_color.isEnabled()
    assert settings.get("font_color_mode_reminder") == "custom"

# REM-E07: QColorDialog / custom color selection path
def test_rem_e07_custom_color_setting_updates(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    view = SettingsView(db, settings)

    settings.set("font_color_reminder", "#10B981")
    settings.set("font_color_mode_reminder", "custom")
    view.update_reminder_preview()

    assert "#10B981" in view.rem_preview_title.styleSheet()
    assert "#10B981" in view.rem_color_swatch.styleSheet()

# REM-E08: Color persists across reload
def test_rem_e08_color_persists(temp_env, qapp):
    db, settings, temp_dir = temp_env
    settings.set("font_color_reminder", "#8B5CF6")
    settings.set("font_color_mode_reminder", "custom")

    restarted = SettingsManager(db, config_dir=Path(temp_dir))
    view = SettingsView(db, restarted)
    assert view.rb_rem_color_custom.isChecked()
    assert restarted.get("font_color_reminder") == "#8B5CF6"

# REM-E09: Live preview family
def test_rem_e09_live_preview_family(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_family_reminder", "Courier")
    view = SettingsView(db, settings)

    assert view.rem_preview_title.font().family() == "Courier"
    assert view.rem_preview_desc.font().family() == "Courier"

# REM-E10: Live preview size
def test_rem_e10_live_preview_size(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_size_reminder", 14)
    view = SettingsView(db, settings)

    assert view.rem_preview_desc.font().pointSize() == 14
    assert view.rem_preview_title.font().pointSize() == 18

# REM-E11: Live preview weight
def test_rem_e11_live_preview_weight(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_weight_reminder", "bold")
    view = SettingsView(db, settings)

    assert view.rem_preview_title.font().bold()

# REM-E12: Live preview color
def test_rem_e12_live_preview_color(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_color_mode_reminder", "custom")
    settings.set("font_color_reminder", "#EF4444")
    view = SettingsView(db, settings)

    assert "#EF4444" in view.rem_preview_title.styleSheet()

# REM-E13: Actual ReminderDialog matches preview styling
def test_rem_e13_actual_reminder_dialog_matches_preview(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_family_reminder", "Liberation Mono")
    settings.set("font_size_reminder", 14)
    settings.set("font_color_mode_reminder", "custom")
    settings.set("font_color_reminder", "#3B82F6")

    view = SettingsView(db, settings)
    t = Task(id=1, title="Dealer Review", description="Review pricing")
    dlg = ReminderDialog(t, settings_manager=settings)

    assert dlg.title_label.font().family() == view.rem_preview_title.font().family()
    assert dlg.title_label.font().pointSize() == view.rem_preview_title.font().pointSize()
    assert "#3B82F6" in dlg.title_label.styleSheet()

# REM-E14: Large font no overlap
def test_rem_e14_large_font_no_overlap(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_size_reminder", 24)

    t = Task(id=1, title="Very Long Strategy Milestone With Extensive Sub-clauses", description="Detailed multi-line explanation of deliverables.")
    dlg = ReminderDialog(t, settings_manager=settings)
    dlg.show()

    # Window expands properly
    assert dlg.sizeHint().height() > 200
    assert dlg.title_label.wordWrap()
    assert dlg.btn_complete.isVisible()
    assert dlg.btn_snooze.isVisible()
    assert dlg.btn_open.isVisible()
    assert dlg.btn_dismiss.isVisible()

# REM-E15: Dark mode readable
def test_rem_e15_dark_mode_readable(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("theme", "dark")
    t = Task(id=1, title="Dark Mode Task", startup_reminder=True)
    dlg = ReminderDialog(t, settings_manager=settings)
    dlg.show()

    assert dlg.lbl_header_icon.isVisible()
    assert dlg.title_label.isVisible()
    assert dlg.btn_complete.isVisible()

# REM-E16: Light mode readable
def test_rem_e16_light_mode_readable(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("theme", "light")
    t = Task(id=1, title="Light Mode Task", startup_reminder=True)
    dlg = ReminderDialog(t, settings_manager=settings)
    dlg.show()

    assert dlg.lbl_header_icon.isVisible()
    assert dlg.title_label.isVisible()
    assert dlg.btn_complete.isVisible()

# REM-E17: Professional appearance
def test_rem_e17_professional_appearance(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("experience_mode", "professional")
    t = Task(id=1, title="Pro Task")
    dlg = ReminderDialog(t, settings_manager=settings)
    assert dlg.layout().contentsMargins().left() == 14

# REM-E18: Balanced appearance
def test_rem_e18_balanced_appearance(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("experience_mode", "balanced")
    t = Task(id=1, title="Balanced Task")
    dlg = ReminderDialog(t, settings_manager=settings)
    assert dlg.layout().contentsMargins().left() == 18

# REM-E19: Personal appearance
def test_rem_e19_personal_appearance(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("experience_mode", "personal")
    t = Task(id=1, title="Personal Task")
    dlg = ReminderDialog(t, settings_manager=settings)
    assert dlg.layout().contentsMargins().left() == 22

# REM-E20: app_startup exactly once
def test_rem_e20_app_startup_exactly_once(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("reminder_trigger_mode", "app_startup")
    tc = TaskController(db)
    t = Task(title="Launch Task", startup_reminder=True)
    tid = tc.add_task(t)
    t.id = tid

    # First fetch
    due_1 = ReminderPolicyService.get_startup_due_reminders(tc, settings)
    assert len(due_1) == 1
    assert due_1[0].id == tid

    ReminderPolicyService.mark_shown(tid)

    # Subsequent fetch suppresses
    due_2 = ReminderPolicyService.get_due_reminders(tc, settings)
    assert len(due_2) == 0

# REM-E21: scheduled_only no startup popup
def test_rem_e21_scheduled_only_no_startup_popup(temp_env):
    _, settings, _ = temp_env
    settings.set("reminder_trigger_mode", "scheduled_only")
    assert not ReminderPolicyService.should_show_on_startup(settings, is_session_startup=False)
    assert not ReminderPolicyService.should_show_on_startup(settings, is_session_startup=True)

# REM-E22: duplicate suppression remains
def test_rem_e22_duplicate_suppression_remains(temp_env):
    db, settings, _ = temp_env
    tc = TaskController(db)
    t = Task(title="Duplicate Test", startup_reminder=True)
    tid = tc.add_task(t)

    ReminderPolicyService.mark_shown(tid)
    assert len(ReminderPolicyService.get_due_reminders(tc, settings)) == 0

    # Dismiss also suppresses
    ReminderPolicyService.dismiss_reminder(tid)
    assert len(ReminderPolicyService.get_due_reminders(tc, settings)) == 0

# REM-E23: restart persistence
def test_rem_e23_restart_persistence(temp_env, qapp):
    db, settings, temp_dir = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_family_reminder", "DejaVu Serif")
    settings.set("font_size_reminder", 16)
    settings.set("font_weight_reminder", "bold")
    settings.set("font_color_mode_reminder", "custom")
    settings.set("font_color_reminder", "#EC4899")
    settings.set("reminder_trigger_mode", "scheduled_only")

    # Restart
    restarted = SettingsManager(db, config_dir=Path(temp_dir))
    assert restarted.get("font_family_reminder") == "DejaVu Serif"
    assert int(restarted.get("font_size_reminder")) == 16
    assert restarted.get("font_weight_reminder") == "bold"
    assert restarted.get("font_color_reminder") == "#EC4899"
    assert restarted.get("reminder_trigger_mode") == "scheduled_only"

    t = Task(id=1, title="Restarted Task", startup_reminder=True)
    dlg = ReminderDialog(t, settings_manager=restarted)
    assert dlg.font().family() == "DejaVu Serif"
    assert dlg.font().pointSize() == 16
    assert dlg.font().bold()
    assert "#EC4899" in dlg.title_label.styleSheet()
