
from pathlib import Path

SRC = Path(
    "todo_bird_app/models/"
    "wbs_filter_proxy_model.py"
).read_text()


def test_filter_change_helper_exists():
    assert (
        "def _notify_filter_changed("
        in SRC
    )


def test_public_filter_methods_use_helper():
    public_start = SRC.index(
        "    # Public filter API — frozen Phase 1B contract"
    )

    public_block = SRC[
        public_start:
    ]

    assert (
        "self._notify_filter_changed()"
        in public_block
    )


def test_deprecated_call_only_remains_as_compatibility_fallback():
    # Exactly one deprecated invocation may remain:
    # inside _notify_filter_changed() for older PySide6 builds.
    assert SRC.count(
        "self.invalidateFilter()"
    ) == 1


def test_filter_semantic_methods_preserved():
    for name in (
        "set_search_query",
        "set_status_filter",
        "clear_filters",
        "filterAcceptsRow",
        "_rebuild_acceptance_cache",
        "_node_matches",
        "_has_matching_descendant",
    ):
        assert (
            f"def {name}("
            in SRC
        )
