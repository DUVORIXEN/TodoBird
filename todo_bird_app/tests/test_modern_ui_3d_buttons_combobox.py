"""
Unit & Integration Test Suite: Modern 3D UI, Button Style Modes, ModernComboBox, & Calculation Perfection.
"""

import pytest
from PySide6.QtWidgets import QApplication
from todo_bird_app.ui.components.modern_button import ModernButton, ButtonStyleDesign, ButtonVariant
from todo_bird_app.ui.components.modern_combobox import ModernComboBox
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.database import DatabaseManager


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_01_modern_button_design_modes(qapp):
    """1. Test ModernButton global design modes."""
    ModernButton.set_global_design_mode(ButtonStyleDesign.RAISED_3D)
    assert ModernButton.get_global_design_mode() == ButtonStyleDesign.RAISED_3D

    btn = ModernButton("3D Action", variant=ButtonVariant.PRIMARY)
    assert btn.text() == "3D Action"

    ModernButton.set_global_design_mode(ButtonStyleDesign.EXECUTIVE_SOFT)
    assert ModernButton.get_global_design_mode() == ButtonStyleDesign.EXECUTIVE_SOFT

    ModernButton.set_global_design_mode(ButtonStyleDesign.NEUMORPHIC_3D)
    assert ModernButton.get_global_design_mode() == ButtonStyleDesign.NEUMORPHIC_3D

    ModernButton.set_global_design_mode(ButtonStyleDesign.GLOW_OUTLINE)
    assert ModernButton.get_global_design_mode() == ButtonStyleDesign.GLOW_OUTLINE

    # Reset
    ModernButton.set_global_design_mode(ButtonStyleDesign.RAISED_3D)


def test_02_modern_combobox_selection(qapp):
    """2. Test ModernComboBox item selection and delegate."""
    combo = ModernComboBox()
    combo.addItems(["Option 1", "Option 2", "Option 3"])
    combo.setCurrentIndex(1)
    assert combo.currentText() == "Option 2"


def test_03_settings_button_design_mode_persistence(tmp_path):
    """3. Test button design mode persistence in settings."""
    db_path = str(tmp_path / "test_ui_settings.db")
    db = DatabaseManager(db_path)
    sm = SettingsManager(db)

    sm.set("button_design_mode", "3d_raised")
    assert sm.get("button_design_mode") == "3d_raised"

    sm.set("window_bg_palette", "Midnight Navy (#1E1F2E)")
    assert sm.get("window_bg_palette") == "Midnight Navy (#1E1F2E)"
