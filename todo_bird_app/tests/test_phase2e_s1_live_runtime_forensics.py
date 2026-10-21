"""
TODO BIRD - Phase 2E S1 live UI runtime forensics.

Focused coverage for the human-witness failures:
- Dashboard native tooltip path uses the live QTipLabel/qtooltip_label surface.
- Task Status -> Blocker/Delay dropdowns open by mouse and persist.
- Inline Edit Subtask Details workflow uses the same blocker/delay contract.
- Reminder Snooze button opens the menu and stores snooze state.
"""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QHelpEvent, QColor, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QToolTip,
)

from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.database import CURRENT_SCHEMA_VERSION, DatabaseManager, PRODUCTION_DB_PATH
from todo_bird_app.models.project import Project
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.services.appearance_service import (
    contrast_ratio,
    qpalette_from_tokens,
    semantic_tokens_for,
)
from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.widgets.dashboard_charts import (
    AdvancedCapacityChart,
    AdvancedStatusChart,
    AdvancedWeeklyActivityChart,
    AnimatedDashboardChart,
    apply_dashboard_tooltip_theme,
    dashboard_tooltip_html,
    install_dashboard_tooltip_filter,
)
from todo_bird_app.widgets.reminder_dialog import ReminderDialog
from todo_bird_app.widgets.task_dialog import TaskDialog


LIGHT_TOOLTIP_BG = "#eef2f7"
LIGHT_TOOLTIP_TEXT = "#111827"
DARK_TOOLTIP_BG = "#2a2b3d"
DARK_TOOLTIP_TEXT = "#f4f7fb"
MIN_AA_CONTRAST = 4.5


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def workflow_db(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "phase2e_s1_live_ui.db"))
    with db.get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, color) "
            "VALUES (1, 'Workflow', '#2563EB')"
        )
        conn.commit()
    return db


@pytest.fixture
def theme_env(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "phase2e_s1_theme.db"))
    settings = SettingsManager(db, config_dir=tmp_path / "config")
    controller = ThemeController(settings)
    return db, settings, controller


class DictSettings:
    def __init__(self, initial=None):
        self.values = dict(initial or {})

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


def _project():
    return Project(id=1, name="Workflow", color="#2563EB")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _set_app_theme(qapp, *, is_dark: bool, accent: str = "#3584E4"):
    tokens = semantic_tokens_for(is_dark, accent)
    palette = qpalette_from_tokens(tokens)
    qapp.setProperty("todoBirdTheme", "dark" if is_dark else "light")
    qapp.setProperty("todoBirdAccent", accent)
    qapp.setPalette(palette)
    QToolTip.setPalette(palette)


def _poison_native_tooltip_palette():
    palette = QToolTip.palette()
    palette.setColor(QPalette.ToolTipBase, QColor("#111827"))
    palette.setColor(QPalette.ToolTipText, QColor("#111827"))
    QToolTip.setPalette(palette)


def _tooltip_snapshot(qapp, widget, text: str, *, is_dark: bool = False):
    _set_app_theme(qapp, is_dark=is_dark)
    widget.setProperty("todoBirdTheme", "dark" if is_dark else "light")
    widget.setProperty("todoBirdAccent", "#3584E4")
    widget.setToolTip(text)
    widget.resize(420, 220)
    widget.show()
    qapp.processEvents()
    _poison_native_tooltip_palette()

    pos = QPoint(max(1, widget.width() // 2), max(1, widget.height() // 2))
    event = QHelpEvent(QEvent.ToolTip, pos, widget.mapToGlobal(pos))
    handled = QApplication.sendEvent(widget, event)
    qapp.processEvents()

    popups = [
        w
        for w in QApplication.topLevelWidgets()
        if w.objectName() == "qtooltip_label"
        or "tooltip" in w.metaObject().className().lower()
    ]
    assert popups, "Native tooltip popup did not open"
    popup = popups[0]
    image = popup.grab().toImage()
    sample = image.pixelColor(
        max(0, min(3, image.width() - 1)),
        max(0, min(3, image.height() - 1)),
    )
    snapshot = {
        "handled": handled,
        "popup_class": popup.metaObject().className(),
        "object_name": popup.objectName(),
        "parent_class": popup.parent().metaObject().className() if popup.parent() else None,
        "visible": popup.isVisible(),
        "base_rgb": QToolTip.palette().color(QPalette.ToolTipBase).getRgb()[:3],
        "text_rgb": QToolTip.palette().color(QPalette.ToolTipText).getRgb()[:3],
        "pixel_rgb": sample.getRgb()[:3],
    }
    QToolTip.hideText()
    qapp.processEvents()
    return snapshot


def _task_dialog(db: DatabaseManager, *, status=TaskStatus.PLANNED, **overrides) -> TaskDialog:
    task = Task(
        title=overrides.pop("title", "Workflow Task"),
        project_id=1,
        planned_date="2026-09-01",
        planned_start_time="09:00",
        estimated_duration=1440,
        status=status,
        delay_category=overrides.pop("delay_category", ""),
        delay_reason=overrides.pop("delay_reason", ""),
        delay_notes=overrides.pop("delay_notes", ""),
        progress=overrides.pop("progress", 0),
        **overrides,
    )
    task_id = db.insert_task(task.to_dict())
    return TaskDialog(
        projects=[_project()],
        task=Task.from_row(db.get_task_by_id(task_id)),
        db_manager=db,
    )


def _set_status(dialog: TaskDialog, status: TaskStatus):
    index = dialog.status_combo.findData(status)
    assert index >= 0
    dialog.status_combo.setCurrentIndex(index)


def _open_combo_by_mouse(qapp, combo: QComboBox) -> bool:
    combo.setFocus()
    QTest.mouseClick(combo, Qt.LeftButton, Qt.NoModifier, combo.rect().center())
    qapp.processEvents()
    return combo.view().isVisible()


def _warning_recorder(monkeypatch):
    calls = []

    def record(_parent, title, message, *args, **kwargs):
        calls.append((title, message))
        return QMessageBox.Ok

    monkeypatch.setattr(QMessageBox, "warning", record)
    return calls


def _task_dialog_with_subtask(db: DatabaseManager, *, status=TaskStatus.PLANNED):
    task = Task(
        title="Parent Task",
        project_id=1,
        planned_date="2026-09-01",
        planned_start_time="09:00",
        estimated_duration=1440,
    )
    task_id = db.insert_task(task.to_dict())
    db.insert_subtask(
        task_id=task_id,
        title="Child Subtask",
        status=status.value,
        progress=0,
    )
    dialog = TaskDialog(
        projects=[_project()],
        task=Task.from_row(db.get_task_by_id(task_id)),
        db_manager=db,
    )
    item = dialog.subtask_tree.topLevelItem(0)
    assert item is not None
    dialog.subtask_tree.setCurrentItem(item)
    return dialog, item


def _open_inline_subtask_editor(monkeypatch, qapp, dialog: TaskDialog) -> QDialog:
    captured = []

    def fake_exec(self):
        captured.append(self)
        self.show()
        qapp.processEvents()
        return QDialog.Accepted

    monkeypatch.setattr(QDialog, "exec", fake_exec)
    dialog.edit_selected_subtask_details()
    assert captured, "Edit Subtask Details dialog was not opened"
    return captured[-1]


def _find_save_details_button(dialog: QDialog) -> QPushButton:
    for button in dialog.findChildren(QPushButton):
        if "Save Details" in button.text():
            return button
    raise AssertionError("Save Details button not found")


@pytest.mark.parametrize(
    "chart_cls,object_name",
    [
        (AdvancedCapacityChart, "AdvancedCapacityChart"),
        (AdvancedStatusChart, "AdvancedStatusChart"),
        (AdvancedWeeklyActivityChart, "AdvancedWeeklyActivityChart"),
    ],
)
def test_01_03_dashboard_chart_classes_are_actual_tooltip_parents(chart_cls, object_name):
    chart = chart_cls()
    assert isinstance(chart, AnimatedDashboardChart)
    assert chart.metaObject().className() == object_name
    chart.close()


@pytest.mark.parametrize(
    "chart_cls",
    [AdvancedCapacityChart, AdvancedStatusChart, AdvancedWeeklyActivityChart],
)
def test_04_06_light_native_tooltip_event_repairs_stale_palette(qapp, chart_cls):
    chart = chart_cls()
    snap = _tooltip_snapshot(qapp, chart, "Live dashboard tooltip", is_dark=False)
    assert snap["handled"] is True
    assert snap["object_name"] == "qtooltip_label"
    assert snap["parent_class"] == chart.metaObject().className()
    assert snap["base_rgb"] == (238, 242, 247)
    assert snap["text_rgb"] == (17, 24, 39)
    chart.close()


def test_07_light_dashboard_tooltip_contrast_is_readable(qapp):
    _set_app_theme(qapp, is_dark=False)
    chart = AdvancedCapacityChart()
    chart.setProperty("todoBirdTheme", "light")
    theme = apply_dashboard_tooltip_theme(chart)
    assert theme.background == LIGHT_TOOLTIP_BG
    assert theme.text_primary == LIGHT_TOOLTIP_TEXT
    assert contrast_ratio(theme.text_primary, theme.background) >= MIN_AA_CONTRAST
    chart.close()


def test_08_dark_dashboard_tooltip_contrast_is_readable(qapp):
    _set_app_theme(qapp, is_dark=True)
    chart = AdvancedStatusChart()
    chart.setProperty("todoBirdTheme", "dark")
    theme = apply_dashboard_tooltip_theme(chart)
    assert theme.background == DARK_TOOLTIP_BG
    assert theme.text_primary == DARK_TOOLTIP_TEXT
    assert contrast_ratio(theme.text_primary, theme.background) >= MIN_AA_CONTRAST
    chart.close()


def test_09_dashboard_tooltip_html_carries_explicit_theme_colors(qapp):
    _set_app_theme(qapp, is_dark=False)
    chart = AdvancedWeeklyActivityChart()
    chart.setProperty("todoBirdTheme", "light")
    html = dashboard_tooltip_html("Title\nBody", chart)
    assert 'data-todo-bird-dashboard-tooltip="1"' in html
    assert LIGHT_TOOLTIP_BG in html
    assert LIGHT_TOOLTIP_TEXT in html
    chart.close()


def test_10_dashboard_non_chart_tooltip_filter_fixes_qcombobox(qapp):
    combo = QComboBox()
    combo.addItems(["7D", "14D"])
    combo.setProperty("todoBirdTheme", "light")
    install_dashboard_tooltip_filter(combo)
    snap = _tooltip_snapshot(qapp, combo, "Choose how much execution history to visualize")
    assert snap["object_name"] == "qtooltip_label"
    assert snap["base_rgb"] == (238, 242, 247)
    assert snap["text_rgb"] == (17, 24, 39)
    combo.close()


def test_11_live_theme_switch_updates_open_dashboard_tooltip(qapp, theme_env):
    _db, _settings, controller = theme_env
    chart = AdvancedCapacityChart()
    chart.setProperty("todoBirdAccent", "#3584E4")
    chart.show()
    controller.apply_theme("dark")
    chart.setProperty("todoBirdTheme", "dark")
    dark_theme = apply_dashboard_tooltip_theme(chart)
    controller.apply_theme("light")
    chart.setProperty("todoBirdTheme", "light")
    light_theme = apply_dashboard_tooltip_theme(chart)
    assert dark_theme.background == DARK_TOOLTIP_BG
    assert light_theme.background == LIGHT_TOOLTIP_BG
    assert QToolTip.palette().color(QPalette.ToolTipBase).name() == LIGHT_TOOLTIP_BG
    chart.close()


def test_12_real_dashboard_view_tooltip_owners_are_named(qapp, theme_env):
    from todo_bird_app.views.main_window import MainWindow

    db, settings, controller = theme_env
    window = MainWindow(db, settings, controller)
    window.show()
    controller.apply_theme("light")
    qapp.processEvents()
    owners = [
        window.dashboard_view.capacity_stacked_bar,
        window.dashboard_view.status_donut,
        window.dashboard_view.weekly_chart,
        window.dashboard_view.activity_range_combo,
    ]
    assert {owner.objectName() for owner in owners} == {
        "dashboard_capacity_chart",
        "dashboard_status_chart",
        "dashboard_weekly_activity_chart",
        "dashboard_activity_range_combo",
    }
    assert all(owner.toolTip() for owner in owners)
    window.close()


def test_13_task_status_combo_runtime_inventory(workflow_db):
    dialog = _task_dialog(workflow_db)
    assert isinstance(dialog.status_combo, QComboBox)
    assert dialog.status_combo.objectName() == "task_status_combo"
    assert dialog.status_combo.isEnabled()
    assert dialog.status_combo.count() >= len(TaskStatus)
    assert dialog.status_combo.currentData() == TaskStatus.PLANNED
    dialog.close()


def test_14_task_status_popup_opens_by_mouse(qapp, workflow_db):
    dialog = _task_dialog(workflow_db)
    dialog.show()
    qapp.processEvents()
    assert _open_combo_by_mouse(qapp, dialog.status_combo)
    dialog.status_combo.hidePopup()
    dialog.close()


@pytest.mark.parametrize(
    "status",
    [
        TaskStatus.PLANNED,
        TaskStatus.IN_PROGRESS,
        TaskStatus.BLOCKED,
        TaskStatus.DELAYED,
    ],
)
def test_15_18_task_status_selection_enters_handler(qapp, workflow_db, status):
    dialog = _task_dialog(workflow_db)
    if dialog.status_combo.currentData() == status:
        _set_status(dialog, TaskStatus.INBOX)
        qapp.processEvents()
    before = dialog._status_blocker_delay_handler_count
    _set_status(dialog, status)
    qapp.processEvents()
    assert dialog.status_combo.currentData() == status
    assert dialog._status_blocker_delay_handler_count > before
    assert dialog._status_blocker_delay_signal_log
    dialog.close()


def test_19_blocker_controls_disabled_until_blocked(workflow_db):
    dialog = _task_dialog(workflow_db, status=TaskStatus.PLANNED)
    assert not dialog.blocker_category_combo.isEnabled()
    assert not dialog.blocker_reason_input.isEnabled()
    dialog.close()


def test_20_blocker_controls_enable_on_blocked(qapp, workflow_db):
    dialog = _task_dialog(workflow_db)
    _set_status(dialog, TaskStatus.BLOCKED)
    qapp.processEvents()
    assert dialog.blocker_category_combo.isEnabled()
    assert dialog.blocker_reason_input.isEnabled()
    assert dialog.blocker_notes_input.isEnabled()
    dialog.close()


def test_21_blocker_category_popup_opens_by_mouse(qapp, workflow_db):
    dialog = _task_dialog(workflow_db)
    dialog.show()
    _set_status(dialog, TaskStatus.BLOCKED)
    qapp.processEvents()
    assert _open_combo_by_mouse(qapp, dialog.blocker_category_combo)
    dialog.blocker_category_combo.hidePopup()
    dialog.close()


def test_22_blocker_category_model_contains_expected_items(qapp, workflow_db):
    dialog = _task_dialog(workflow_db)
    _set_status(dialog, TaskStatus.BLOCKED)
    texts = [
        dialog.blocker_category_combo.itemText(i)
        for i in range(dialog.blocker_category_combo.count())
    ]
    assert "Dependency" in texts
    assert "Technical Issue" in texts
    assert "Customer / Stakeholder" in texts
    dialog.close()


def test_23_blocker_category_selection_emits_signal(qapp, workflow_db):
    dialog = _task_dialog(workflow_db)
    _set_status(dialog, TaskStatus.BLOCKED)
    fired = []
    dialog.blocker_category_combo.currentIndexChanged.connect(fired.append)
    dialog.blocker_category_combo.setCurrentText("Dependency")
    qapp.processEvents()
    assert fired
    assert dialog.blocker_category_combo.currentText() == "Dependency"
    dialog.close()


def test_24_blocker_save_requires_non_none_category(monkeypatch, workflow_db):
    dialog = _task_dialog(workflow_db)
    warnings = _warning_recorder(monkeypatch)
    _set_status(dialog, TaskStatus.BLOCKED)
    dialog.blocker_category_combo.setCurrentText("None")
    dialog.blocker_reason_input.setText("Waiting for owner")
    dialog.on_save()
    assert warnings
    assert "Category Required" in warnings[0][0]


def test_25_blocker_save_requires_reason(monkeypatch, workflow_db):
    dialog = _task_dialog(workflow_db)
    warnings = _warning_recorder(monkeypatch)
    _set_status(dialog, TaskStatus.BLOCKED)
    dialog.blocker_category_combo.setCurrentText("Dependency")
    dialog.blocker_reason_input.clear()
    dialog.on_save()
    assert warnings
    assert "Reason Required" in warnings[0][0]


def test_26_blocker_save_and_reopen_persists(workflow_db):
    dialog = _task_dialog(workflow_db)
    _set_status(dialog, TaskStatus.BLOCKED)
    dialog.blocker_category_combo.setCurrentText("Technical Issue")
    dialog.blocker_reason_input.setText("Build server down")
    dialog.on_save()
    assert workflow_db.update_task(dialog.task.to_dict())
    reopened = TaskDialog(
        projects=[_project()],
        task=Task.from_row(workflow_db.get_task_by_id(dialog.task.id)),
        db_manager=workflow_db,
    )
    assert reopened.status_combo.currentData() == TaskStatus.BLOCKED
    assert reopened.blocker_category_combo.currentText() == "Technical Issue"
    assert reopened.blocker_reason_input.text() == "Build server down"
    reopened.close()


def test_27_delay_controls_enable_on_delayed(qapp, workflow_db):
    dialog = _task_dialog(workflow_db)
    _set_status(dialog, TaskStatus.DELAYED)
    qapp.processEvents()
    assert dialog.blocker_category_combo.isEnabled()
    assert dialog.blocker_reason_input.isEnabled()
    assert dialog.blocker_notes_input.isEnabled()
    dialog.close()


def test_28_delay_category_popup_opens_by_mouse(qapp, workflow_db):
    dialog = _task_dialog(workflow_db)
    dialog.show()
    _set_status(dialog, TaskStatus.DELAYED)
    qapp.processEvents()
    assert _open_combo_by_mouse(qapp, dialog.blocker_category_combo)
    dialog.blocker_category_combo.hidePopup()
    dialog.close()


def test_29_delay_category_model_contains_expected_items(workflow_db):
    dialog = _task_dialog(workflow_db)
    _set_status(dialog, TaskStatus.DELAYED)
    texts = [
        dialog.blocker_category_combo.itemText(i)
        for i in range(dialog.blocker_category_combo.count())
    ]
    assert "Decision / Approval" in texts
    assert "External Agency" in texts
    dialog.close()


def test_30_delay_category_selection_emits_signal(qapp, workflow_db):
    dialog = _task_dialog(workflow_db)
    _set_status(dialog, TaskStatus.DELAYED)
    fired = []
    dialog.blocker_category_combo.currentIndexChanged.connect(fired.append)
    dialog.blocker_category_combo.setCurrentText("Customer / Stakeholder")
    qapp.processEvents()
    assert fired
    assert dialog.blocker_category_combo.currentText() == "Customer / Stakeholder"
    dialog.close()


def test_31_delay_save_requires_non_none_category(monkeypatch, workflow_db):
    dialog = _task_dialog(workflow_db)
    warnings = _warning_recorder(monkeypatch)
    _set_status(dialog, TaskStatus.DELAYED)
    dialog.blocker_category_combo.setCurrentText("None")
    dialog.blocker_reason_input.setText("External wait")
    dialog.on_save()
    assert warnings
    assert "Category Required" in warnings[0][0]


def test_32_delay_save_persists(workflow_db):
    dialog = _task_dialog(workflow_db)
    _set_status(dialog, TaskStatus.DELAYED)
    dialog.blocker_category_combo.setCurrentText("External Agency")
    dialog.blocker_reason_input.setText("Permit review taking longer")
    dialog.on_save()
    assert dialog.task.status == TaskStatus.DELAYED
    assert dialog.task.delay_category == "External Agency"
    assert dialog.task.delay_reason == "Permit review taking longer"


def test_33_delay_reopen_persists(workflow_db):
    dialog = _task_dialog(workflow_db)
    _set_status(dialog, TaskStatus.DELAYED)
    dialog.blocker_category_combo.setCurrentText("Budget / Commercial")
    dialog.blocker_reason_input.setText("Budget freeze")
    dialog.on_save()
    assert workflow_db.update_task(dialog.task.to_dict())
    reopened = TaskDialog(
        projects=[_project()],
        task=Task.from_row(workflow_db.get_task_by_id(dialog.task.id)),
        db_manager=workflow_db,
    )
    assert reopened.status_combo.currentData() == TaskStatus.DELAYED
    assert reopened.blocker_category_combo.currentText() == "Budget / Commercial"
    reopened.close()


def test_34_subtask_workflow_schema_columns_exist(workflow_db):
    with workflow_db.get_connection() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(subtasks)").fetchall()}
        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert version == CURRENT_SCHEMA_VERSION
    assert {"status", "delay_category", "delay_reason", "delay_notes", "delay_recorded_at"} <= columns


@pytest.mark.parametrize("status", [TaskStatus.BLOCKED, TaskStatus.DELAYED])
def test_35_36_inline_subtask_status_controls_enable(monkeypatch, qapp, workflow_db, status):
    dialog, _item = _task_dialog_with_subtask(workflow_db)
    sub_dialog = _open_inline_subtask_editor(monkeypatch, qapp, dialog)
    combo = sub_dialog.findChild(QComboBox, "subtask_status_combo")
    category = sub_dialog.findChild(QComboBox, "subtask_blocker_category_combo")
    reason = sub_dialog.findChild(QLineEdit, "subtask_blocker_reason_input")
    assert combo is not None
    assert category is not None
    assert reason is not None
    combo.setCurrentIndex(combo.findData(status))
    qapp.processEvents()
    assert category.isEnabled()
    assert reason.isEnabled()
    sub_dialog.close()
    dialog.close()


@pytest.mark.parametrize(
    "status,category,reason",
    [
        (TaskStatus.BLOCKED, "Resource / Manpower", "Crew unavailable"),
        (TaskStatus.DELAYED, "External Agency", "Permit still pending"),
    ],
)
def test_37_38_inline_subtask_save_reopen_persists(
    monkeypatch, qapp, workflow_db, status, category, reason
):
    dialog, item = _task_dialog_with_subtask(workflow_db)
    sub_dialog = _open_inline_subtask_editor(monkeypatch, qapp, dialog)
    combo = sub_dialog.findChild(QComboBox, "subtask_status_combo")
    cat_combo = sub_dialog.findChild(QComboBox, "subtask_blocker_category_combo")
    reason_input = sub_dialog.findChild(QLineEdit, "subtask_blocker_reason_input")

    combo.setCurrentIndex(combo.findData(status))
    cat_combo.setCurrentText(category)
    reason_input.setText(reason)
    QTest.mouseClick(_find_save_details_button(sub_dialog), Qt.LeftButton)
    qapp.processEvents()

    metadata = item.data(0, Qt.UserRole + 1)
    assert metadata["status"] == status.value
    assert metadata["delay_category"] == category
    assert metadata["delay_reason"] == reason

    dialog.on_save()
    reopened = TaskDialog(
        projects=[_project()],
        task=Task.from_row(workflow_db.get_task_by_id(dialog.task.id)),
        db_manager=workflow_db,
    )
    reopened_meta = reopened.subtask_tree.topLevelItem(0).data(0, Qt.UserRole + 1)
    assert reopened_meta["status"] == status.value
    assert reopened_meta["delay_category"] == category
    assert reopened_meta["delay_reason"] == reason
    reopened.close()


def test_39_reminder_snooze_button_does_not_pass_checked_as_exec_menu(qapp):
    settings = DictSettings({"theme": "light", "accent_color": "#3584E4"})
    task = Task(id=901, title="Snooze Button")
    dialog = ReminderDialog(task, settings_manager=settings)
    calls = []

    def fake_show_snooze_menu(exec_menu=True):
        calls.append(exec_menu)

    dialog.show_snooze_menu = fake_show_snooze_menu
    dialog.btn_snooze.clicked.emit()
    assert calls == [True]
    dialog.close()


def test_40_reminder_snooze_menu_is_theme_explicit(qapp):
    settings = DictSettings({"theme": "light", "accent_color": "#3584E4"})
    task = Task(id=902, title="Snooze Menu")
    dialog = ReminderDialog(task, settings_manager=settings)
    menu = dialog.show_snooze_menu(exec_menu=False)
    style = menu.styleSheet()
    assert menu.objectName() == "reminder_snooze_menu"
    assert "#FFFFFF" in style
    assert "#111827" in style
    assert "QMenu::item:selected" in style
    dialog.close()


def test_41_reminder_snooze_selection_persists_until_time(qapp):
    settings = DictSettings({"theme": "light", "accent_color": "#3584E4"})
    ReminderPolicyService.reset_session_state(settings)
    task = Task(
        id=903,
        title="Snooze Persist",
        planned_date="2026-09-03",
        planned_start_time="10:00",
    )
    dialog = ReminderDialog(task, settings_manager=settings)
    dialog.on_snooze_selected(10)
    raw = settings.get("persisted_snoozed_reminders")
    persisted = json.loads(raw)
    assert str(task.id) in persisted
    until = datetime.fromisoformat(persisted[str(task.id)])
    assert until > datetime.now() + timedelta(minutes=9)


def test_42_reminder_snooze_action_trigger_accepts_zero_arg_signal(qapp):
    settings = DictSettings({"theme": "light", "accent_color": "#3584E4"})
    ReminderPolicyService.reset_session_state(settings)
    task = Task(id=904, title="Snooze Action")
    dialog = ReminderDialog(task, settings_manager=settings)
    menu = dialog.show_snooze_menu(exec_menu=False)
    action = menu.actions()[0]
    action.triggered.emit()
    persisted = json.loads(settings.get("persisted_snoozed_reminders"))
    assert str(task.id) in persisted
    dialog.close()


def test_43_production_db_unchanged_by_live_ui_forensics(qapp):
    assert PRODUCTION_DB_PATH.exists()
    before = _sha256(PRODUCTION_DB_PATH)
    _set_app_theme(qapp, is_dark=False)
    chart = AdvancedCapacityChart()
    theme = apply_dashboard_tooltip_theme(chart)
    assert theme.theme == "light"
    chart.close()
    after = _sha256(PRODUCTION_DB_PATH)
    assert after == before
