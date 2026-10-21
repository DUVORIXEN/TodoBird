
from pathlib import Path


SERVICE = Path(
    "todo_bird_app/services/wbs_mutation_service.py"
).read_text()

PROJECTS = Path(
    "todo_bird_app/views/projects_view.py"
).read_text()

WBS_VIEW = Path(
    "todo_bird_app/views/wbs_project_view.py"
).read_text()


def test_add_child_signal_preserves_typed_parent():
    assert (
        "self.taskAddRequested.emit(selected_key)"
        in WBS_VIEW
    )
    assert (
        "self.taskAddRequested.emit(key)"
        in WBS_VIEW
    )


def test_projects_view_uses_parent_key():
    assert (
        "if parent_key is None:"
        in PROJECTS
    )
    assert (
        "WBSMutationService.create_child("
        in PROJECTS
    )


def test_root_task_creation_path_is_preserved():
    assert (
        "self.task_controller.add_task("
        in PROJECTS
    )
    assert (
        'project_id=self.selected_project_id'
        in PROJECTS
    )


def test_child_path_does_not_create_new_root_task():
    start = PROJECTS.index(
        "        # Professional WBS child workflow."
    )

    block = PROJECTS[start:]

    assert "WBSMutationService.create_child(" in block
    assert "self.task_controller.add_task(" not in block.split(
        "def _on_wbs_delete_task",
        1,
    )[0]


def test_create_child_is_transactional():
    start = SERVICE.index(
        "    def create_child("
    )

    end = SERVICE.index(
        "    def next_child_position(",
        start,
    )

    block = SERVICE[start:end]

    assert (
        'conn.execute("BEGIN IMMEDIATE")'
        in block
    )
    assert "conn.commit()" in block
    assert "conn.rollback()" in block
    assert "INSERT INTO subtasks" in block


def test_child_creation_never_converts_task_entity():
    start = SERVICE.index(
        "    def create_child("
    )

    end = SERVICE.index(
        "    def next_child_position(",
        start,
    )

    block = SERVICE[start:end]

    assert "INSERT INTO subtasks" in block
    assert "INSERT INTO tasks" not in block
    assert "UPDATE tasks" not in block


def test_success_refreshes_wbs_and_global_consumers():
    assert (
        "self.wbs_view.refresh_hierarchy()"
        in PROJECTS
    )
    assert (
        "self.task_controller.notify_tasks_changed()"
        in PROJECTS
    )


def test_new_child_is_reselected():
    assert (
        "self.wbs_view.tree_view.select_key("
        in PROJECTS
    )


def test_rollup_cache_invalidated_after_create():
    assert (
        "WBSRollupService.clear_cache()"
        in PROJECTS
    )
