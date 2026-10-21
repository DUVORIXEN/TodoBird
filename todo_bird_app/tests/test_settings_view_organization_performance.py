from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QComboBox,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTabWidget,
)

from todo_bird_app.views.settings_view import SettingsView


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


class MockSettingsManager:
    def __init__(self, initial=None):
        self._data = dict(initial or {})

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value


class MockDBManager:
    def __init__(self):
        self.db_path = ":memory:"

    def get_all_greetings(self):
        return []

    def get_greeting_by_day(self, _day):
        return None


def make_settings_view(qapp):
    view = SettingsView(MockDBManager(), MockSettingsManager())
    qapp.processEvents()
    return view


def test_settings_view_uses_clear_tabbed_sections(qapp):
    view = make_settings_view(qapp)

    tabs = view.findChild(QTabWidget, "SettingsTabs")
    assert tabs is view.settings_tabs
    assert tabs.count() == 7
    assert [tabs.tabText(i) for i in range(tabs.count())] == [
        "Appearance",
        "Typography",
        "Reminders",
        "Companion",
        "Planning",
        "System",
        "Dashboard",
    ]

    page_scrolls = view.findChildren(QScrollArea, "SettingsPageScroll")
    assert len(page_scrolls) == 7
    assert all(scroll.widgetResizable() for scroll in page_scrolls)


def test_settings_view_keeps_existing_controls_available(qapp):
    view = make_settings_view(qapp)

    for attr_name in (
        "theme_combo",
        "bg_mode_combo",
        "pinned_window_size_combo",
        "rem_window_size_combo",
        "greetings_table",
        "wbs_settings_widget",
        "cb_confirm_del",
    ):
        assert hasattr(view, attr_name), attr_name

    assert len(view.findChildren(QComboBox)) >= 5
    assert len(view.findChildren(QSpinBox)) >= 5


def test_settings_view_reuses_font_model_and_limits_size_recalculation(qapp):
    view = make_settings_view(qapp)

    assert view.font_family_combo.model() is view._font_family_model
    assert view.desc_font_family_combo.model() is view._font_family_model
    assert view.pinned_fam_combo.model() is view._font_family_model
    assert view.rem_fam_combo.model() is view._font_family_model

    for _area, widgets in view.area_typo_widgets.items():
        combo = widgets[1]
        if isinstance(combo, QComboBox):
            assert combo.model() is view._font_family_model

    for combo in view.findChildren(QComboBox):
        assert combo.sizeAdjustPolicy() == (
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )


def test_settings_view_hot_spinboxes_do_not_emit_on_each_keystroke(qapp):
    view = make_settings_view(qapp)

    for spin in view.findChildren(QSpinBox):
        assert spin.keyboardTracking() is False


def test_settings_view_greeting_table_uses_low_churn_scrolling(qapp):
    view = make_settings_view(qapp)

    table = view.findChild(QTableWidget)
    assert table is view.greetings_table
    assert table.verticalScrollMode() == QAbstractItemView.ScrollPerPixel
    assert table.horizontalScrollMode() == QAbstractItemView.ScrollPerPixel
    assert table.showGrid() is False
    assert table.alternatingRowColors() is True
    assert table.verticalHeader().isVisible() is False


def test_settings_view_coalesces_heavy_live_appearance_refresh(qapp):
    view = make_settings_view(qapp)
    view.theme_controller = MagicMock()

    view.on_font_size_changed(12)
    view.on_font_size_changed(13)

    assert view.settings_manager.get("ui_font_size") == 13
    assert view._appearance_apply_pending is True
    assert view.theme_controller.apply_theme.call_count == 0

    qapp.processEvents()

    assert view._appearance_apply_pending is False
    assert view.theme_controller.apply_theme.call_count == 1
