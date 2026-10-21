
from pathlib import Path


def test_task_controller_has_public_structural_refresh_hook():
    src = Path(
        "todo_bird_app/controllers/task_controller.py"
    ).read_text()

    assert "def notify_tasks_changed(self)" in src
    assert "_GLOBAL_EVENT_BUS.tasks_changed.emit()" in src


def test_wbs_view_uses_canonical_mutation_service():
    src = Path(
        "todo_bird_app/views/wbs_project_view.py"
    ).read_text()

    assert (
        "from todo_bird_app.services.wbs_mutation_service "
        "import WBSMutationService"
        in src
    )

    assert "WBSMutationService.move_up(" in src
    assert "WBSMutationService.move_down(" in src


def test_context_menu_exposes_move_up_down():
    src = Path(
        "todo_bird_app/views/wbs_project_view.py"
    ).read_text()

    assert '"Move Up"' in src
    assert '"Move Down"' in src
    assert '"Alt+Up"' in src
    assert '"Alt+Down"' in src


def test_wbs_model_remains_read_only():
    src = Path(
        "todo_bird_app/models/wbs_item_model.py"
    ).read_text()

    # Phase 1E.4 allows rows to START a drag while the model remains
    # non-editable and is never a Qt drop/move authority.
    assert "Qt.ItemIsEnabled" in src
    assert "Qt.ItemIsSelectable" in src
    assert "Qt.ItemIsDragEnabled" in src

    assert "Qt.ItemIsEditable" not in src
    assert "Qt.ItemIsDropEnabled" not in src
    assert "def dropMimeData(" not in src
    assert "def moveRows(" not in src

    assert "def dropMimeData" not in src


def test_projects_view_bridges_hierarchy_to_controller():
    src = Path(
        "todo_bird_app/views/projects_view.py"
    ).read_text()

    assert "self.wbs_view.hierarchyChanged.connect" in src
    assert "def _on_wbs_hierarchy_changed" in src
    assert "self.task_controller.notify_tasks_changed()" in src


def test_gantt_still_consumes_task_controller_signal():
    src = Path(
        "todo_bird_app/views/gantt_view.py"
    ).read_text()
    base_src = Path(
        "todo_bird_app/views/base_view.py"
    ).read_text()

    assert (
        'self._connect_task_controller_signal("tasks_changed", self.refresh_data)'
        in src
    )
    assert "_task_controller_signal_connections" in base_src


def test_no_direct_db_hierarchy_write_in_wbs_view():
    src = Path(
        "todo_bird_app/views/wbs_project_view.py"
    ).read_text()

    forbidden = [
        "UPDATE tasks SET position",
        "UPDATE subtasks SET position",
        "parent_subtask_id = ?",
    ]

    for token in forbidden:
        assert token not in src
