
from types import SimpleNamespace

from PySide6.QtCore import QModelIndex

from todo_bird_app.models.wbs_item_model import (
    WBSItemModel,
)
from todo_bird_app.models.wbs_filter_proxy_model import (
    WBSFilterProxyModel,
)
from todo_bird_app.services.wbs_service import (
    EntityRef,
)


def node(
    key,
    title,
    code,
    status,
    parent_key,
    depth,
    has_children=False,
):
    return SimpleNamespace(
        key=key,
        title=title,
        wbs_code=code,
        status=status,
        parent_key=parent_key,
        depth=depth,
        has_children=has_children,
        is_milestone=False,
        project_id=1,
        is_completed=(
            status == "completed"
        ),
    )


def make_model(
    nodes_by_key,
    children_by_parent,
    root_keys,
):
    model = WBSItemModel()

    snapshot = SimpleNamespace(
        project_id=1,
        nodes_by_key=nodes_by_key,
        children_by_parent=children_by_parent,
        root_keys=root_keys,
        orphaned_keys=[],
        total_nodes=len(nodes_by_key),
        max_depth=max(
            (
                getattr(n, "depth", 0)
                for n in nodes_by_key.values()
            ),
            default=0,
        ),
        revision=1,
    )

    model.beginResetModel()
    model._snapshot = snapshot
    model._rollups = {}
    model._snapshot_rollup_valid = False
    model._rebuild_progress_cache()
    model.endResetModel()

    return model


def visible_root_count(proxy):
    return proxy.rowCount(
        QModelIndex()
    )


def test_descendant_match_retains_ancestors():
    root = EntityRef.task(1)
    child = EntityRef.subtask(10)
    grandchild = EntityRef.subtask(11)
    sibling = EntityRef.subtask(12)

    nodes = {
        root: node(
            root,
            "Program",
            "1",
            "planned",
            None,
            0,
            True,
        ),
        child: node(
            child,
            "Design",
            "1.1",
            "planned",
            root,
            1,
            True,
        ),
        grandchild: node(
            grandchild,
            "Needle Task",
            "1.1.1",
            "planned",
            child,
            2,
            False,
        ),
        sibling: node(
            sibling,
            "Procurement",
            "1.2",
            "planned",
            root,
            1,
            False,
        ),
    }

    children = {
        root: [
            child,
            sibling,
        ],
        child: [
            grandchild,
        ],
        grandchild: [],
        sibling: [],
    }

    model = make_model(
        nodes,
        children,
        [root],
    )

    proxy = WBSFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.set_search_query(
        "needle"
    )

    assert proxy._accepted_keys == {
        root,
        child,
        grandchild,
    }

    # One root remains visible because its descendant matched.
    assert visible_root_count(proxy) == 1


def test_nonmatching_sibling_not_in_acceptance_cache():
    root = EntityRef.task(1)
    match = EntityRef.subtask(10)
    other = EntityRef.subtask(11)

    nodes = {
        root: node(
            root,
            "Root",
            "1",
            "planned",
            None,
            0,
            True,
        ),
        match: node(
            match,
            "Target Alpha",
            "1.1",
            "planned",
            root,
            1,
        ),
        other: node(
            other,
            "Beta",
            "1.2",
            "planned",
            root,
            1,
        ),
    }

    model = make_model(
        nodes,
        {
            root: [match, other],
            match: [],
            other: [],
        },
        [root],
    )

    proxy = WBSFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.set_search_query(
        "alpha"
    )

    assert root in proxy._accepted_keys
    assert match in proxy._accepted_keys
    assert other not in proxy._accepted_keys


def test_status_filter_retains_parent_of_matching_child():
    root = EntityRef.task(1)
    child = EntityRef.subtask(10)

    nodes = {
        root: node(
            root,
            "Completed Summary",
            "1",
            "completed",
            None,
            0,
            True,
        ),
        child: node(
            child,
            "Live Child",
            "1.1",
            "in_progress",
            root,
            1,
        ),
    }

    model = make_model(
        nodes,
        {
            root: [child],
            child: [],
        },
        [root],
    )

    proxy = WBSFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.set_status_filter(
        "active"
    )

    # Parent itself is completed, but must remain as hierarchy context
    # because its child is active.
    assert root in proxy._accepted_keys
    assert child in proxy._accepted_keys


def test_clear_filters_restores_no_cache_all_rows_mode():
    root = EntityRef.task(1)

    model = make_model(
        {
            root: node(
                root,
                "Root",
                "1",
                "planned",
                None,
                0,
            )
        },
        {
            root: [],
        },
        [root],
    )

    proxy = WBSFilterProxyModel()
    proxy.setSourceModel(model)
    proxy.set_search_query(
        "does-not-match"
    )

    assert proxy._accepted_keys == set()

    proxy.clear_filters()

    assert proxy._accepted_keys is None
    assert proxy.has_active_filter() is False
    assert visible_root_count(proxy) == 1


def test_deep_5000_node_tree_filters_without_recursion():
    """
    Regression for the old recursive _has_matching_descendant path.

    A 5000-level tree exceeds normal Python recursion limits.
    Phase 1F.1 must calculate ancestor retention iteratively.
    """

    count = 5000

    nodes = {}
    children = {}
    root = EntityRef.task(1)
    previous = None

    for i in range(count):
        if i == 0:
            key = root
            parent_key = None
        else:
            key = EntityRef.subtask(
                10000 + i
            )
            parent_key = previous

        title = (
            "Deep Needle"
            if i == count - 1
            else f"Node {i}"
        )

        nodes[key] = node(
            key,
            title,
            (
                "1"
                if i == 0
                else f"1.{i}"
            ),
            "planned",
            parent_key,
            i,
            i < count - 1,
        )

        children.setdefault(
            key,
            [],
        )

        if previous is not None:
            children.setdefault(
                previous,
                [],
            ).append(key)

        previous = key

    model = make_model(
        nodes,
        children,
        [root],
    )

    proxy = WBSFilterProxyModel()
    proxy.setSourceModel(model)

    # This is the operation that previously depended on recursive
    # descendant scanning.
    proxy.set_search_query(
        "deep needle"
    )

    assert len(
        proxy._accepted_keys
    ) == count

    assert root in proxy._accepted_keys


def test_filter_hot_path_contains_no_recursive_call():
    from pathlib import Path

    src = Path(
        "todo_bird_app/models/"
        "wbs_filter_proxy_model.py"
    ).read_text()

    start = src.index(
        "    def filterAcceptsRow("
    )

    # Use the next function definition as the structural boundary.
    # Do not depend on comment wording/spacing.
    end = src.index(
        "    def _node_matches(",
        start,
    )

    block = src[start:end]

    assert (
        "_has_matching_descendant("
        not in block
    )

    assert "_accepted_keys" in block


def test_legacy_helper_itself_is_non_recursive():
    from pathlib import Path

    src = Path(
        "todo_bird_app/models/"
        "wbs_filter_proxy_model.py"
    ).read_text()

    start = src.index(
        "    def _has_matching_descendant("
    )

    block = src[start:]

    # Definition appears exactly once. There is no call to itself
    # inside its implementation.
    assert (
        block.count(
            "_has_matching_descendant("
        )
        == 1
    )
