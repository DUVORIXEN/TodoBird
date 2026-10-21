import pytest
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication, QColorDialog
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QColor, QFont
from PySide6.QtTest import QTest

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.models.task import Task
from todo_bird_app.services.typography_service import TypographyService
from todo_bird_app.widgets.reminder_dialog import ReminderDialog
from todo_bird_app.views.settings_view import SettingsView
from todo_bird_app.controllers.theme_controller import ThemeController

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
    db_path = os.path.join(temp_dir, "test_310f.db")
    db = DatabaseManager(db_path)
    settings = SettingsManager(db, config_dir=Path(temp_dir))
    yield db, settings, temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)

# COLOR01: Select Custom radio
def test_color01_select_custom_radio(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_color_mode_reminder", "auto")
    view = SettingsView(db, settings)
    view.show()

    assert view.rb_rem_color_auto.isChecked()
    assert not view.rb_rem_color_custom.isChecked()

    view.rb_rem_color_custom.click()
    assert view.rb_rem_color_custom.isChecked()
    assert settings.get("font_color_mode_reminder") == "custom"

# COLOR02: Choose Color becomes enabled
def test_color02_choose_color_becomes_enabled(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_color_mode_reminder", "auto")
    view = SettingsView(db, settings)
    view.show()

    assert not view.btn_choose_rem_color.isEnabled()

    view.rb_rem_color_custom.click()
    assert view.btn_choose_rem_color.isEnabled()

# COLOR03: Click Choose Color / swatch triggers handler
def test_color03_click_choose_color_triggers_handler(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_color_mode_reminder", "custom")
    view = SettingsView(db, settings)
    view.show()

    called = []
    with patch.object(QColorDialog, 'exec', return_value=QColorDialog.Accepted), \
         patch.object(QColorDialog, 'selectedColor', return_value=QColor("#E67E22")):
        view.btn_choose_rem_color.click()
        called.append(True)

    assert called == [True]
    assert settings.get("font_color_reminder") == "#E67E22"

# COLOR04: Mock/drive QColorDialog valid selection
def test_color04_drive_qcolordialog_valid_selection(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_color_mode_reminder", "custom")
    view = SettingsView(db, settings)
    view.show()

    with patch.object(QColorDialog, 'exec', return_value=QColorDialog.Accepted), \
         patch.object(QColorDialog, 'selectedColor', return_value=QColor("#8E44AD")):
        view.on_choose_reminder_color()

    assert settings.get("font_color_reminder") == "#8E44AD"
    assert settings.get("font_color_mode_reminder") == "custom"

# COLOR05: Swatch changes
def test_color05_swatch_changes(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_color_mode_reminder", "custom")
    settings.set("font_color_reminder", "#27AE60")
    view = SettingsView(db, settings)
    view.show()

    assert "#27AE60" in view.rem_color_swatch.styleSheet()

# COLOR06: Preview changes
def test_color06_preview_changes(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_color_mode_reminder", "custom")
    settings.set("font_color_reminder", "#E74C3C")
    view = SettingsView(db, settings)
    view.show()

    assert "#E74C3C" in view.rem_preview_title.styleSheet()
    assert "#E74C3C" in view.rem_preview_desc.styleSheet()

# COLOR07: Settings persist
def test_color07_settings_persist(temp_env, qapp):
    db, settings, temp_dir = temp_env
    settings.set("font_color_mode_reminder", "custom")
    settings.set("font_color_reminder", "#D35400")

    restarted = SettingsManager(db, config_dir=Path(temp_dir))
    assert restarted.get("font_color_mode_reminder") == "custom"
    assert restarted.get("font_color_reminder") == "#D35400"

# COLOR08: ReminderDialog uses custom color
def test_color08_reminder_dialog_uses_custom_color(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_color_mode_reminder", "custom")
    settings.set("font_color_reminder", "#9B59B6")

    t = Task(id=1, title="Branded Reminder Task", description="Testing custom color application.")
    dlg = ReminderDialog(t, settings_manager=settings)
    dlg.show()

    assert "#9B59B6" in dlg.title_label.styleSheet()
    assert "#9B59B6" in dlg.desc_label.styleSheet()

# COLOR09: Theme switch does not erase custom selection
def test_color09_theme_switch_preserves_custom_selection(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_color_mode_reminder", "custom")
    settings.set("font_color_reminder", "#1ABC9C")
    settings.set("theme", "dark")

    theme_ctrl = ThemeController(settings)
    theme_ctrl.apply_theme("light")

    assert settings.get("font_color_mode_reminder") == "custom"
    assert settings.get("font_color_reminder") == "#1ABC9C"

    # Dialog in light theme still has custom color
    t = Task(id=1, title="Light Theme Task", description="Preserves custom color.")
    dlg = ReminderDialog(t, settings_manager=settings)
    assert "#1ABC9C" in dlg.title_label.styleSheet()

# COLOR10: Switching back to Automatic restores theme color
def test_color10_switching_to_automatic_restores_theme_color(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_color_mode_reminder", "custom")
    settings.set("font_color_reminder", "#E67E22")
    view = SettingsView(db, settings)
    view.show()

    assert view.btn_choose_rem_color.isEnabled()

    # Switch back to Auto
    view.rb_rem_color_auto.click()
    assert view.rb_rem_color_auto.isChecked()
    assert not view.btn_choose_rem_color.isEnabled()
    assert settings.get("font_color_mode_reminder") == "auto"
    assert TypographyService.get_font_color_for_area("reminder", settings) is None

    # ReminderDialog uses theme color
    t = Task(id=1, title="Automatic Theme Task")
    dlg = ReminderDialog(t, settings_manager=settings)
    assert "color: inherit;" in dlg.title_label.styleSheet()

# SIZE01: Size spinbox clickable & interactive
def test_size01_size_spinbox_clickable(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_size_reminder", 11)
    view = SettingsView(db, settings)
    view.show()

    assert view.rem_sz_spin.isEnabled()
    assert view.rem_sz_spin.value() == 11

    view.rem_sz_spin.setValue(18)
    assert settings.get("font_size_reminder") == 18

# SIZE02: Preview changes
def test_size02_preview_changes(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_size_reminder", 18)
    view = SettingsView(db, settings)
    view.show()

    assert view.rem_preview_desc.font().pointSize() == 18
    assert view.rem_preview_title.font().pointSize() == 22

# SIZE03: Reminder changes
def test_size03_reminder_changes(temp_env, qapp):
    db, settings, _ = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_size_reminder", 18)

    t = Task(id=1, title="Size 18 Task")
    dlg = ReminderDialog(t, settings_manager=settings)
    dlg.show()

    assert dlg.font().pointSize() == 18
    assert dlg.title_label.font().pointSize() == 22

# SIZE04: Restart persists
def test_size04_restart_persists(temp_env, qapp):
    db, settings, temp_dir = temp_env
    settings.set("font_override_reminder", True)
    settings.set("font_size_reminder", 18)

    restarted = SettingsManager(db, config_dir=Path(temp_dir))
    assert int(restarted.get("font_size_reminder")) == 18

    t = Task(id=1, title="Persisted Size Task")
    dlg = ReminderDialog(t, settings_manager=restarted)
    assert dlg.font().pointSize() == 18
