
from pathlib import Path


MODEL = Path(
    "todo_bird_app/models/wbs_item_model.py"
).read_text()

TREE = Path(
    "todo_bird_app/views/wbs_tree_view.py"
).read_text()

VIEW = Path(
    "todo_bird_app/views/wbs_project_view.py"
).read_text()

SERVICE = Path(
    "todo_bird_app/services/wbs_mutation_service.py"
).read_text()


def test_model_is_drag_source_but_not_drop_authority():
    assert "Qt.ItemIsDragEnabled" in MODEL
    assert "Qt.ItemIsDropEnabled" not in MODEL
    assert "def dropMimeData(" not in MODEL
    assert "def moveRows(" not in MODEL


def test_tree_uses_private_typed_mime():
    assert (
        'application/x-todo-bird-wbs-entity'
        in TREE
    )
    assert "EntityRef.task(" in TREE
    assert "EntityRef.subtask(" in TREE


def test_tree_never_calls_super_drop_event():
    start = TREE.index(
        "    def dropEvent(self, event):"
    )
    end = TREE.index(
        "    def paintEvent(self, event):",
        start,
    )

    block = TREE[start:end]

    # Ignore comments when checking executable drop behaviour.
    executable_lines = []

    for line in block.splitlines():
        stripped = line.strip()

        if stripped.startswith("#"):
            continue

        executable_lines.append(line)

    executable = "\n".join(
        executable_lines
    )

    assert "super().dropEvent(" not in executable
    assert "hierarchyDropRequested.emit" in executable


def test_tree_exposes_three_drop_zones():
    assert 'return "before"' in TREE
    assert 'return "into"' in TREE
    assert 'return "after"' in TREE


def test_tree_has_visual_drop_feedback():
    assert "_wbs_drag_target_rect" in TREE
    assert "painter.drawLine(" in TREE
    assert "painter.drawRoundedRect(" in TREE


def test_project_view_routes_drop_to_service():
    assert (
        "hierarchyDropRequested.connect"
        in VIEW
    )
    assert (
        "WBSMutationService.drag_drop_move("
        in VIEW
    )


def test_service_owns_transactional_drop():
    start = SERVICE.index(
        "    def drag_drop_move("
    )
    end = SERVICE.index(
        "    def reparent_subtask(",
        start,
    )

    block = SERVICE[start:end]

    assert 'conn.execute("BEGIN IMMEDIATE")' in block
    assert "conn.commit()" in block
    assert "conn.rollback()" in block
    assert "_move_subtask_to_scope(" in block
    assert "ERR_CYCLE" in block
    assert "ERR_CROSS_TASK" in block
    assert "ERR_CROSS_PROJECT" in block


def test_drag_drop_does_not_convert_task_entities():
    start = SERVICE.index(
        "    def drag_drop_move("
    )
    end = SERVICE.index(
        "    def reparent_subtask(",
        start,
    )

    block = SERVICE[start:end]

    assert "ERR_TASK_PARENT_FORBIDDEN" in block
    assert "UPDATE tasks SET" not in block


def test_existing_keyboard_hierarchy_commands_preserved():
    assert "Qt.Key_Tab" in TREE
    assert "Qt.Key_Backtab" in TREE
    assert "hierarchyIndentRequested" in TREE
    assert "hierarchyOutdentRequested" in TREE
