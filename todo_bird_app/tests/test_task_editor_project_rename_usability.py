import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QGroupBox, QLabel, QTabWidget

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.project import Project
from todo_bird_app.models.task import Task
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.views.projects_view import ProjectsView
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.toast_banner import ToastBanner


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "task_editor_project_ui.db"))
    yield db
    db.close()


@pytest.fixture
def temp_settings(temp_db):
    return SettingsManager(temp_db)


def test_task_dialog_uses_clear_four_tab_layout(qapp, temp_db, temp_settings):
    task = Task(title="Foundation Setup")

    dialog = TaskDialog(
        projects=[],
        task=task,
        db_manager=temp_db,
        settings_manager=temp_settings,
    )

    try:
        tabs = dialog.findChild(QTabWidget, "TaskDialogTabs")
        assert tabs is dialog.task_dialog_tabs
        assert [tabs.tabText(i) for i in range(tabs.count())] == [
            "Basics",
            "Schedule",
            "Breakdown",
            "Status",
        ]
        assert tabs.usesScrollButtons() is True
    finally:
        dialog.close()


def test_task_dialog_labels_are_task_friendly(qapp, temp_db, temp_settings):
    task = Task(title="Foundation Setup")

    dialog = TaskDialog(
        projects=[],
        task=task,
        db_manager=temp_db,
        settings_manager=temp_settings,
    )

    try:
        labels = {label.text() for label in dialog.findChildren(QLabel)}
        group_titles = {group.title() for group in dialog.findChildren(QGroupBox)}

        assert "Task title *" in labels
        assert "Estimated duration" in labels
        assert "Calculated target" in labels
        assert "Target finish" in labels
        assert "Workload" in labels
        assert "Planned Schedule" in group_titles
        assert "Rules and Deadlines" in group_titles
        assert "Actual Tracking" in group_titles
        assert "Workload Planning" in group_titles
        assert "Task Breakdown" in group_titles
        assert "Status and Dependencies" in group_titles
    finally:
        dialog.close()


def test_estimated_duration_days_sets_target_finish_from_project_calendar(
    qapp,
    temp_db,
    temp_settings,
):
    project_id = temp_db.insert_project({"name": "Mon Sat Project"})
    temp_db.set_project_calendar(project_id, working_weekdays=[0, 1, 2, 3, 4, 5])
    project = Project.from_row(temp_db.get_project(project_id))
    task = Task(
        title="Foundation",
        project_id=project_id,
        planned_date="2026-09-01",
        planned_start_time="09:00",
        due_date=None,
        planned_end_time=None,
        estimated_duration=0,
    )

    dialog = TaskDialog(
        projects=[project],
        task=task,
        db_manager=temp_db,
        settings_manager=temp_settings,
    )

    try:
        dialog.duration_days_spin.setValue(5.0)

        assert dialog.duration_spin.value() == 7200
        assert dialog.estimated_finish_label.text() == "2026-09-05 09:00"
        assert dialog.planned_finish_checkbox.isChecked() is True
        assert dialog.due_date_edit.date().toString("yyyy-MM-dd") == "2026-09-05"
        assert dialog.end_time_edit.time().toString("HH:mm") == "09:00"

        dialog.on_save()
        saved = dialog.get_task()
        assert saved.estimated_duration == 7200
        assert saved.due_date == "2026-09-05"
        assert saved.planned_end_time == "09:00"
    finally:
        dialog.close()


def test_project_view_exposes_right_click_rename_entry_points(
    qapp,
    temp_db,
    temp_settings,
):
    view = ProjectsView(temp_db, temp_settings)

    try:
        assert view.project_list.contextMenuPolicy() == Qt.CustomContextMenu
        assert view.proj_name_label.contextMenuPolicy() == Qt.CustomContextMenu
        assert hasattr(view, "open_project_list_context_menu")
        assert hasattr(view, "open_selected_project_context_menu")
        assert hasattr(view, "rename_project")
    finally:
        view.close()


def test_project_rename_updates_database_and_refreshes_header(
    qapp,
    temp_db,
    temp_settings,
    monkeypatch,
):
    monkeypatch.setattr(
        ToastBanner,
        "show_message",
        staticmethod(lambda *args, **kwargs: None),
    )
    project_id = temp_db.insert_project(
        {
            "name": "Original Build",
            "color": "#3584E4",
            "description": "Rename witness",
        }
    )
    view = ProjectsView(temp_db, temp_settings)

    try:
        assert view.rename_project(project_id, "Renamed Build") is True

        saved = temp_db.get_project(project_id)
        assert saved["name"] == "Renamed Build"
        assert view.selected_project_id == project_id
        assert "Renamed Build" in view.proj_name_label.text()
    finally:
        view.close()
