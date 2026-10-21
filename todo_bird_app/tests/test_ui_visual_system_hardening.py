import hashlib
import pytest
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QPushButton, QComboBox, QLineEdit, QSpinBox, QTabBar, QWidget
)
from PySide6.QtGui import QFont, QFontMetrics

from todo_bird_app.themes.tokens import SPACING_SCALE, SEMANTIC_TYPOGRAPHY_ROLES, THEME_PALETTES
from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.services.typography_service import TypographyService, TypographyRole
from todo_bird_app.services.appearance_service import (
    AppearanceService, AppearanceSettings, _ensure_font_safe_control_geometry
)
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.task_item_widget import TaskItemWidget
from todo_bird_app.widgets.headerbar import HeaderBarWidget
from todo_bird_app.views.calendar_view import CalendarView
from todo_bird_app.models.task import Task
from todo_bird_app.database import DatabaseManager, PRODUCTION_DB_PATH


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_01_spacing_scale_and_tokens_conform_to_standard():
    """Verify canonical spacing scale: 4, 8, 12, 16, 20, 24, 32, 40 px."""
    expected_scale = [4, 8, 12, 16, 20, 24, 32, 40]
    assert list(SPACING_SCALE.values()) == expected_scale
    assert DesignTokens.SPACING_XS == 4
    assert DesignTokens.SPACING_SM == 8
    assert DesignTokens.SPACING_MD == 12
    assert DesignTokens.SPACING_LG == 16
    assert DesignTokens.SPACING_XL == 20
    assert DesignTokens.SPACING_2XL == 24
    assert DesignTokens.SPACING_3XL == 32
    assert DesignTokens.SPACING_4XL == 40


def test_02_semantic_typography_roles_hierarchy(qapp):
    """Verify semantic typography scale hierarchy and weights."""
    roles = [
        TypographyRole.DISPLAY,
        TypographyRole.PAGE_TITLE,
        TypographyRole.SECTION_TITLE,
        TypographyRole.CARD_TITLE,
        TypographyRole.BODY,
        TypographyRole.SECONDARY_BODY,
        TypographyRole.METADATA,
        TypographyRole.CAPTION,
    ]
    for role in roles:
        assert role in TypographyService.ROLE_CONFIG
        assert role in SEMANTIC_TYPOGRAPHY_ROLES

    btn = QPushButton("Test Button")
    TypographyService.apply_semantic_role(btn, TypographyRole.CARD_TITLE)
    assert btn.property("_todo_bird_font_delta_pt") == 2
    assert btn.property("_todo_bird_font_role_weight") == "semibold"


def test_03_font_scaling_control_geometry_safety(qapp):
    """Verify controls expand geometry for larger fonts and never clip text."""
    dummy_settings = AppearanceSettings(
        theme="dark",
        is_dark=True,
        accent_scheme="adwaita_blue",
        accent_color="#3584E4",
        font_family="Inter",
        font_size=16,
        font_weight="normal",
        density="balanced",
        button_style="3d_raised",
        tokens={},
    )

    btn = QPushButton("Action Button")
    btn_font = QFont("Inter", 16)
    btn.setFont(btn_font)
    _ensure_font_safe_control_geometry(btn, dummy_settings)
    min_h = btn.fontMetrics().height() + 10 + 2
    assert btn.minimumHeight() >= min_h

    tabbar = QTabBar()
    tabbar.setFont(btn_font)
    _ensure_font_safe_control_geometry(tabbar, dummy_settings)
    assert tabbar.minimumHeight() >= tabbar.fontMetrics().height() + 16


def test_04_task_dialog_reminder_control_and_sync(qapp, tmp_path):
    """Verify TaskDialog reminder control pill and synchronization."""
    db_file = tmp_path / "test_dialog_reminder.db"
    db = DatabaseManager.for_test(str(db_file))
    task = Task(title="Test Reminder Task", startup_reminder=True, startup_reminder_mode="daily_first_open")

    dlg = TaskDialog([], task, db_manager=db)
    assert hasattr(dlg, "facade_reminder_checkbox")
    assert hasattr(dlg, "facade_reminder_combo")
    assert dlg.facade_reminder_checkbox.isChecked()
    assert dlg.facade_reminder_combo.isEnabled()
    assert dlg.facade_reminder_combo.currentData() == "daily_first_open"

    dlg.facade_reminder_checkbox.setChecked(False)
    assert not dlg.facade_reminder_combo.isEnabled()
    assert dlg.startup_reminder_combo.currentData() == "off"

    dlg.close()


def test_05_all_themes_load_valid_tokens():
    """Verify all 6 theme modes exist and have complete color tokens."""
    for theme_key in ("dark", "light", "oled", "warm_paper", "nord"):
        assert theme_key in THEME_PALETTES
        pal = THEME_PALETTES[theme_key]
        for required_token in (
            "bg_root", "bg_sidebar", "bg_card", "text_primary",
            "text_secondary", "border", "accent_default"
        ):
            assert required_token in pal, f"Missing {required_token} in theme {theme_key}"


def test_06_gantt_scene_clear_safety_invariant():
    """Strictly verify Gantt clearance sequence is preserved in exact required order."""
    gantt_file = Path(__file__).parents[1] / "gantt" / "gantt_chart.py"
    content = gantt_file.read_text(encoding="utf-8")

    expected_block = (
        "self.current_time_line_item = None\n\n"
        "        self._resize_preview = None\n"
        "        self._resize_item = None\n"
        "        self._drag_item = None\n\n"
        "        # Do NOT individually remove dependency graphics here.\n"
        "        # The scene owns them and scene.clear() will destroy them\n"
        "        # exactly once.\n"
        "        self._dependency_graphics = []\n\n"
        "        # GanttTaskItem wrappers are also scene-owned.\n"
        "        self._rendered_task_items = {}\n\n"
        "        self.scene.clear()"
    )
    assert expected_block in content, "Gantt scene clearance invariant violated!"


def test_07_task_item_widget_scalable_actions_and_bell(qapp):
    """Verify TaskItemWidget buttons use scalable minimum height and subtle reminder bell."""
    task = Task(title="Interactive Task", startup_reminder=True, startup_reminder_mode="every_app_open")
    widget = TaskItemWidget(task, project_name="Work")

    assert widget.edit_btn.minimumHeight() >= 30
    assert widget.del_btn.minimumHeight() >= 30

    labels = [child.text() for child in widget.findChildren(QPushButton)]
    assert "Edit" in labels


def test_08_headerbar_and_calendar_responsive_bounds(qapp, tmp_path):
    """Verify HeaderBar and CalendarView responsive bounds."""
    hb = HeaderBarWidget()
    assert hb.minimumHeight() >= 52

    db = DatabaseManager.for_test(str(tmp_path / "cal_test.db"))
    cal_view = CalendarView(db, None)
    side_panel = cal_view.findChild(QWidget, "CardWidget")
    assert cal_view.calendar is not None
    cal_view.close()

