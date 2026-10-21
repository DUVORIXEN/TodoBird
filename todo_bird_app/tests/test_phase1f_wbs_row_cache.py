
from types import SimpleNamespace
from pathlib import Path

from PySide6.QtCore import QModelIndex

from todo_bird_app.models.wbs_item_model import (
    WBSItemModel,
)
from todo_bird_app.services.wbs_service import (
    EntityRef,
)


def make_node(
    key,
    parent_key=None,
    depth=0,
    has_children=False,
):
    return SimpleNamespace(
        key=key,
        parent_key=parent_key,
        depth=depth,
        title=str(key),
        wbs_code="",
        status="planned",
        has_children=has_children,
        is_milestone=False,
        project_id=1,
        is_completed=False,
    )


def apply_snapshot(
    model,
    nodes,
    children,
    roots,
):
    snap = SimpleNamespace(
        project_id=1,
        nodes_by_key=nodes,
        children_by_parent=children,
        root_keys=roots,
        orphaned_keys=[],
        total_nodes=len(nodes),
        max_depth=max(
            (
                n.depth
                for n in nodes.values()
            ),
            default=0,
        ),
        revision=1,
    )

    model.beginResetModel()
    model._snapshot = snap
    model._rollups = {}
    model._snapshot_rollup_valid = False
    model._rebuild_row_cache()
    model._rebuild_progress_cache()
    model.endResetModel()


def test_root_row_positions_are_cached():
    model = WBSItemModel()

    a = EntityRef.task(1)
    b = EntityRef.task(2)
    c = EntityRef.task(3)

    nodes = {
        a: make_node(a),
        b: make_node(b),
        c: make_node(c),
    }

    apply_snapshot(
        model,
        nodes,
        {
            a: [],
            b: [],
            c: [],
        },
        [a, b, c],
    )

    assert model._row_by_key == {
        a: 0,
        b: 1,
        c: 2,
    }


def test_nested_sibling_positions_are_cached():
    model = WBSItemModel()

    root = EntityRef.task(1)
    a = EntityRef.subtask(10)
    b = EntityRef.subtask(11)
    c = EntityRef.subtask(12)

    nodes = {
        root: make_node(
            root,
            has_children=True,
        ),
        a: make_node(
            a,
            root,
            1,
        ),
        b: make_node(
            b,
            root,
            1,
        ),
        c: make_node(
            c,
            root,
            1,
        ),
    }

    apply_snapshot(
        model,
        nodes,
        {
            root: [a, b, c],
            a: [],
            b: [],
            c: [],
        },
        [root],
    )

    assert model._row_by_key[a] == 0
    assert model._row_by_key[b] == 1
    assert model._row_by_key[c] == 2


def test_parent_returns_correct_root_row():
    model = WBSItemModel()

    root_a = EntityRef.task(1)
    root_b = EntityRef.task(2)
    child = EntityRef.subtask(20)

    nodes = {
        root_a: make_node(root_a),
        root_b: make_node(
            root_b,
            has_children=True,
        ),
        child: make_node(
            child,
            root_b,
            1,
        ),
    }

    apply_snapshot(
        model,
        nodes,
        {
            root_a: [],
            root_b: [child],
            child: [],
        },
        [root_a, root_b],
    )

    child_idx = model.index_from_key(
        child
    )

    assert child_idx.isValid()

    parent_idx = model.parent(
        child_idx
    )

    assert parent_idx.isValid()
    assert parent_idx.row() == 1
    assert (
        parent_idx.internalPointer().key
        == root_b
    )


def test_parent_returns_correct_nested_row():
    model = WBSItemModel()

    root = EntityRef.task(1)
    first = EntityRef.subtask(10)
    second = EntityRef.subtask(11)
    grandchild = EntityRef.subtask(12)

    nodes = {
        root: make_node(
            root,
            has_children=True,
        ),
        first: make_node(
            first,
            root,
            1,
        ),
        second: make_node(
            second,
            root,
            1,
            has_children=True,
        ),
        grandchild: make_node(
            grandchild,
            second,
            2,
        ),
    }

    apply_snapshot(
        model,
        nodes,
        {
            root: [first, second],
            first: [],
            second: [grandchild],
            grandchild: [],
        },
        [root],
    )

    idx = model.index_from_key(
        grandchild
    )

    parent_idx = model.parent(idx)

    assert parent_idx.isValid()
    assert parent_idx.row() == 1
    assert (
        parent_idx.internalPointer().key
        == second
    )


def test_index_from_key_preserves_requested_column():
    model = WBSItemModel()

    root = EntityRef.task(1)
    child = EntityRef.subtask(10)

    nodes = {
        root: make_node(
            root,
            has_children=True,
        ),
        child: make_node(
            child,
            root,
            1,
        ),
    }

    apply_snapshot(
        model,
        nodes,
        {
            root: [child],
            child: [],
        },
        [root],
    )

    idx = model.index_from_key(
        child,
        column=3,
    )

    assert idx.isValid()
    assert idx.column() == 3
    assert idx.row() == 0


def test_row_cache_rebuild_tracks_reorder():
    model = WBSItemModel()

    root = EntityRef.task(1)
    a = EntityRef.subtask(10)
    b = EntityRef.subtask(11)

    nodes = {
        root: make_node(
            root,
            has_children=True,
        ),
        a: make_node(
            a,
            root,
            1,
        ),
        b: make_node(
            b,
            root,
            1,
        ),
    }

    children = {
        root: [a, b],
        a: [],
        b: [],
    }

    apply_snapshot(
        model,
        nodes,
        children,
        [root],
    )

    assert model._row_by_key[a] == 0
    assert model._row_by_key[b] == 1

    children2 = {
        root: [b, a],
        a: [],
        b: [],
    }

    apply_snapshot(
        model,
        nodes,
        children2,
        [root],
    )

    assert model._row_by_key[b] == 0
    assert model._row_by_key[a] == 1


def test_10000_sibling_last_item_resolves_correct_row():
    model = WBSItemModel()

    root = EntityRef.task(1)

    child_keys = [
        EntityRef.subtask(
            10000 + i
        )
        for i in range(10000)
    ]

    nodes = {
        root: make_node(
            root,
            has_children=True,
        )
    }

    children = {
        root: child_keys,
    }

    for key in child_keys:
        nodes[key] = make_node(
            key,
            root,
            1,
        )
        children[key] = []

    apply_snapshot(
        model,
        nodes,
        children,
        [root],
    )

    target = child_keys[-1]

    assert (
        model._row_by_key[target]
        == 9999
    )

    idx = model.index_from_key(
        target
    )

    assert idx.isValid()
    assert idx.row() == 9999


def test_parent_hot_path_contains_no_list_index():
    src = Path(
        "todo_bird_app/models/"
        "wbs_item_model.py"
    ).read_text()

    start = src.index(
        "    def parent("
    )

    end = src.index(
        "    def data(",
        start,
    )

    block = src[start:end]

    assert ".index(" not in block
    assert "_row_by_key" in block


def test_index_from_key_contains_no_sibling_list_scan():
    src = Path(
        "todo_bird_app/models/"
        "wbs_item_model.py"
    ).read_text()

    start = src.index(
        "    def index_from_key("
    )

    block = src[start:]

    assert "root_keys.index(" not in block
    assert "siblings.index(" not in block
    assert "_row_by_key" in block
