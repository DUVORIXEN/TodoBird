
from pathlib import Path


TREE = Path(
    "todo_bird_app/views/wbs_tree_view.py"
).read_text()

VIEW = Path(
    "todo_bird_app/views/wbs_project_view.py"
).read_text()

SERVICE = Path(
    "todo_bird_app/services/wbs_mutation_service.py"
).read_text()


def test_tree_has_indent_outdent_signals():
    assert "hierarchyIndentRequested = Signal(object)" in TREE
    assert "hierarchyOutdentRequested = Signal(object)" in TREE


def test_keyboard_tab_indent():
    assert "if key == Qt.Key_Tab:" in TREE
    assert "self.hierarchyIndentRequested.emit(entity_key)" in TREE


def test_keyboard_shift_tab_outdent():
    assert "if key == Qt.Key_Backtab:" in TREE
    assert "self.hierarchyOutdentRequested.emit(entity_key)" in TREE


def test_view_routes_to_mutation_authority():
    assert "WBSMutationService.indent(" in VIEW
    assert "WBSMutationService.outdent(" in VIEW


def test_context_menu_has_indent_outdent():
    assert '"Indent"' in VIEW
    assert '"Outdent"' in VIEW
    assert 'shortcut="Tab"' in VIEW
    assert 'shortcut="Shift+Tab"' in VIEW


def test_successful_hierarchy_edit_reuses_existing_refresh_signal():
    assert "self.refresh_hierarchy()" in VIEW
    assert "self.hierarchyChanged.emit(key)" in VIEW


def test_no_direct_hierarchy_sql_in_view():
    forbidden = (
        "UPDATE subtasks SET parent_subtask_id",
        "UPDATE subtasks SET position",
        "UPDATE tasks SET position",
    )

    for token in forbidden:
        assert token not in VIEW


def test_main_tasks_remain_roots():
    assert "ERR_TASK_PARENT_FORBIDDEN" in SERVICE
    assert "Main tasks are WBS roots" in SERVICE
