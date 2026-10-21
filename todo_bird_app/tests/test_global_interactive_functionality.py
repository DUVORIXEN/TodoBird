import inspect

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton

from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.project import Project
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.ui.components.modern_combobox import ModernComboBox
from todo_bird_app.views.main_window import MainWindow
from todo_bird_app.widgets.task_dialog import TaskDialog


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def app_env(tmp_path, qapp):
    db = DatabaseManager.for_test(str(tmp_path / "global_interaction.db"))
    with db.get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, color) VALUES (1, 'Global Interaction', '#2563EB')"
        )
        conn.commit()
    settings = SettingsManager(db, config_dir=tmp_path / "config")
    theme = ThemeController(settings)
    qapp.theme_controller = theme
    return db, settings, theme


def _seed_task_pair(db):
    pred_id = db.insert_task(
        Task(
            title="Predecessor",
            project_id=1,
            planned_date="2026-09-01",
            planned_start_time="09:00",
            estimated_duration=1440,
            show_in_gantt=True,
        ).to_dict()
    )
    succ_id = db.insert_task(
        Task(
            title="Successor",
            project_id=1,
            planned_date="2026-09-02",
            planned_start_time="09:00",
            estimated_duration=1440,
            show_in_gantt=True,
        ).to_dict()
    )
    return pred_id, succ_id


def _task_dialog(app_env):
    db, settings, _theme = app_env
    _pred_id, succ_id = _seed_task_pair(db)
    return TaskDialog(
        projects=[Project(id=1, name="Global Interaction", color="#2563EB")],
        task=Task.from_row(db.get_task_by_id(succ_id)),
        db_manager=db,
        settings_manager=settings,
    )


MAIN_VIEW_KEYS = [
    "dashboard",
    "inbox",
    "today",
    "focus",
    "upcoming",
    "projects",
    "completed",
    "calendar",
    "gantt",
    "analytics",
    "daily_review",
    "feedback",
    "settings",
]


@pytest.mark.parametrize("view_key", MAIN_VIEW_KEYS)
def test_real_mainwindow_navigation_sections_are_reachable(qapp, app_env, view_key):
    db, settings, theme = app_env
    window = MainWindow(db, settings, theme)

    window.navigation_controller.set_active_section(view_key)
    qapp.processEvents()

    index, widget = window.view_stack_map[view_key]
    assert window.stacked_widget.currentIndex() == index
    assert window.stacked_widget.currentWidget() is widget


TASK_DIALOG_COMBOS = [
    "project_combo",
    "prio_combo",
    "cat_combo",
    "constraint_type_combo",
    "status_combo",
    "recurring_combo",
    "startup_reminder_combo",
    "pin_color_combo",
    "allocation_mode_combo",
    "blocker_category_combo",
    "dependency_predecessor_combo",
    "dependency_type_combo",
]


@pytest.mark.parametrize("attr", TASK_DIALOG_COMBOS)
def test_task_dialog_dropdowns_have_models_and_keyboard_focus(qapp, app_env, attr):
    dialog = _task_dialog(app_env)
    combo = getattr(dialog, attr)

    assert isinstance(combo, QComboBox)
    assert combo.count() > 0
    assert combo.currentIndex() >= 0
    assert combo.focusPolicy() != Qt.NoFocus


@pytest.mark.parametrize("attr", TASK_DIALOG_COMBOS)
def test_task_dialog_dropdown_popups_can_open_and_close(qapp, app_env, attr):
    dialog = _task_dialog(app_env)
    combo = getattr(dialog, attr)

    combo.showPopup()
    qapp.processEvents()
    combo.hidePopup()
    qapp.processEvents()

    assert combo.count() > 0


def test_real_task_dialog_dependency_add_and_remove_buttons_are_not_dead(
    qapp, app_env
):
    dialog = _task_dialog(app_env)

    before = [
        dialog.dependency_tree.topLevelItem(i).checkState(0)
        for i in range(dialog.dependency_tree.topLevelItemCount())
    ]
    dialog.dependency_predecessor_combo.setCurrentIndex(0)
    QTest.mouseClick(dialog.dependency_add_button, Qt.LeftButton)
    after_add = [
        dialog.dependency_tree.topLevelItem(i).checkState(0)
        for i in range(dialog.dependency_tree.topLevelItemCount())
    ]
    dialog.dependency_tree.setCurrentItem(dialog.dependency_tree.topLevelItem(0))
    QTest.mouseClick(dialog.dependency_remove_button, Qt.LeftButton)
    after_remove = [
        dialog.dependency_tree.topLevelItem(i).checkState(0)
        for i in range(dialog.dependency_tree.topLevelItemCount())
    ]

    assert before != after_add
    assert after_remove[0] == Qt.Unchecked


def test_real_task_dialog_blocker_dropdown_is_not_dead_after_status_change(
    qapp, app_env
):
    dialog = _task_dialog(app_env)

    dialog.status_combo.setCurrentIndex(dialog.status_combo.findData(TaskStatus.BLOCKED))
    qapp.processEvents()
    dialog.blocker_category_combo.setCurrentText("Dependency")

    assert dialog.blocker_category_combo.isEnabled()
    assert dialog.blocker_category_combo.currentText() == "Dependency"


def test_real_mainwindow_enabled_combos_have_usable_models(qapp, app_env):
    db, settings, theme = app_env
    window = MainWindow(db, settings, theme)
    window.show()
    qapp.processEvents()

    combos = window.findChildren(QComboBox) + window.findChildren(ModernComboBox)
    enabled = [combo for combo in combos if combo.isVisible() and combo.isEnabled()]

    assert enabled
    assert all(combo.count() > 0 for combo in enabled)
    assert all(combo.currentIndex() >= 0 for combo in enabled)


def test_real_mainwindow_navigation_buttons_are_clickable(qapp, app_env):
    db, settings, theme = app_env
    window = MainWindow(db, settings, theme)
    window.show()
    qapp.processEvents()

    buttons = [
        button
        for button in window.findChildren(QPushButton)
        if button.isVisible() and button.isEnabled() and button.text().strip()
    ]

    assert buttons
    assert all(button.focusPolicy() != Qt.NoFocus for button in buttons[:20])


CONTROL_PATTERNS = [
    ("TaskDialog", TaskDialog, "QComboBox"),
    ("TaskDialog", TaskDialog, "QPushButton"),
    ("TaskDialog", TaskDialog, "QCheckBox"),
    ("TaskDialog", TaskDialog, "QDateEdit"),
    ("TaskDialog", TaskDialog, "QTimeEdit"),
    ("TaskDialog", TaskDialog, "QSpinBox"),
    ("TaskDialog", TaskDialog, "clicked.connect"),
    ("TaskDialog", TaskDialog, "currentIndexChanged.connect"),
    ("TaskDialog", TaskDialog, "toggled.connect"),
    ("TaskDialog", TaskDialog, "setEnabled"),
    ("MainWindow", MainWindow, "CommandRegistry"),
    ("MainWindow", MainWindow, "section_changed.connect"),
    ("MainWindow", MainWindow, "TaskDialog"),
    ("MainWindow", MainWindow, "SettingsView"),
    ("MainWindow", MainWindow, "GanttView"),
]


@pytest.mark.parametrize("name,obj,pattern", CONTROL_PATTERNS)
def test_static_interaction_inventory_contains_expected_control_paths(
    name, obj, pattern
):
    source = inspect.getsource(obj)

    assert pattern in source, f"{name} should expose {pattern} in the audited path"


def test_no_enabled_task_dialog_combo_is_empty_or_silent(qapp, app_env):
    dialog = _task_dialog(app_env)
    combos = dialog.findChildren(QComboBox)

    assert combos
    for combo in combos:
        if not combo.isEnabled():
            assert combo.toolTip() or combo.accessibleDescription() or combo.accessibleName()
            continue
        assert combo.count() > 0
        assert combo.currentIndex() >= 0


def test_no_enabled_task_dialog_button_is_label_less(qapp, app_env):
    dialog = _task_dialog(app_env)
    buttons = [button for button in dialog.findChildren(QPushButton) if button.isEnabled()]

    assert buttons
    assert all(button.text().strip() or button.icon() for button in buttons)
