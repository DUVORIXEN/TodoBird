"""
TODO BIRD — WBS FILTER PROXY MODEL (QSortFilterProxyModel)

Phase 1F.1:
Hierarchy-safe filtering with one iterative acceptance-cache build per
filter/model change.

Large-tree invariant:
    filterAcceptsRow() performs O(1) key membership lookup.
    It never recursively walks descendants.

Ancestor-retention semantics remain identical:
    if any descendant matches, every ancestor remains visible.
"""

from typing import Optional, Set

from PySide6.QtCore import (
    QSortFilterProxyModel,
    QModelIndex,
)

from todo_bird_app.models.wbs_item_model import (
    WBSItemModel,
)
from todo_bird_app.services.wbs_service import (
    EntityRef,
)


class WBSFilterProxyModel(QSortFilterProxyModel):
    """
    Hierarchy-safe WBS filtering proxy.

    Filter acceptance is precomputed iteratively from the canonical
    WBSHierarchySnapshot whenever:
    - search text changes
    - status filter changes
    - filters clear
    - source model resets/changes

    This prevents repeated recursive descendant scans during Qt
    filtering of large/deep project hierarchies.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._search_query: str = ""
        self._status_filter: str = "all"

        # None means no active filter: every row is accepted.
        self._accepted_keys: Optional[Set[EntityRef]] = None

        # Direct matches are retained separately for compatibility/
        # diagnostics and cheap descendant checks.
        self._direct_match_keys: Set[EntityRef] = set()

        # We own ancestor retention explicitly.
        self.setRecursiveFilteringEnabled(False)

    # ------------------------------------------------------------------
    # Source-model lifecycle
    # ------------------------------------------------------------------

    def setSourceModel(self, source_model):
        old_model = self.sourceModel()

        if old_model is not None:
            try:
                old_model.modelReset.disconnect(
                    self._on_source_model_changed
                )
            except Exception:
                pass

            try:
                old_model.dataChanged.disconnect(
                    self._on_source_model_changed
                )
            except Exception:
                pass

        super().setSourceModel(source_model)

        if source_model is not None:
            try:
                source_model.modelReset.connect(
                    self._on_source_model_changed
                )
            except Exception:
                pass

            try:
                source_model.dataChanged.connect(
                    self._on_source_model_changed
                )
            except Exception:
                pass

        self._rebuild_acceptance_cache()

    def _on_source_model_changed(self, *args):
        self._rebuild_acceptance_cache()
        self._notify_filter_changed()

    def _notify_filter_changed(self) -> None:
        """
        Notify Qt that row filtering changed.

        Qt 6.10+ deprecates invalidateFilter().
        Prefer beginFilterChange()/endFilterChange() when available,
        while keeping a compatibility fallback for older PySide6 builds.
        """
        begin = getattr(
            self,
            "beginFilterChange",
            None,
        )

        end = getattr(
            self,
            "endFilterChange",
            None,
        )

        if callable(begin) and callable(end):
            begin()

            try:
                # PySide6 versions differ in whether Directions is exposed.
                directions = getattr(
                    type(self),
                    "Direction",
                    None,
                )

                if directions is not None:
                    rows = getattr(
                        directions,
                        "Rows",
                        None,
                    )

                    if rows is not None:
                        end(rows)
                        return

                # Current Qt accepts default direction when omitted.
                end()
                return

            except TypeError:
                try:
                    end()
                    return
                except Exception:
                    pass

            except Exception:
                pass

        # Compatibility fallback for older bindings.
        self.invalidateFilter()

    # ------------------------------------------------------------------
    # Public filter API — frozen Phase 1B contract
    # ------------------------------------------------------------------

    def set_search_query(self, query: str):
        normalized = str(query or "").strip()

        if normalized == self._search_query:
            return

        self._search_query = normalized
        self._rebuild_acceptance_cache()
        self._notify_filter_changed()

    def set_status_filter(self, status: str):
        normalized = str(
            status or "all"
        ).lower().strip()

        if not normalized:
            normalized = "all"

        if normalized == self._status_filter:
            return

        self._status_filter = normalized
        self._rebuild_acceptance_cache()
        self._notify_filter_changed()

    def clear_filters(self):
        changed = bool(
            self._search_query
            or self._status_filter != "all"
        )

        self._search_query = ""
        self._status_filter = "all"
        self._accepted_keys = None
        self._direct_match_keys.clear()

        if changed:
            self._notify_filter_changed()

    def has_active_filter(self) -> bool:
        return bool(
            self._search_query
        ) or self._status_filter != "all"

    # ------------------------------------------------------------------
    # O(n) iterative acceptance-cache authority
    # ------------------------------------------------------------------

    def _node_object_matches(self, node) -> bool:
        if node is None:
            return False

        title = str(
            getattr(node, "title", "") or ""
        ).lower()

        code = str(
            getattr(node, "wbs_code", "") or ""
        ).lower()

        status = str(
            getattr(node, "status", "") or ""
        ).lower()

        key = getattr(node, "key", None)
        entity_type = getattr(key, "entity_type", getattr(node, "entity_type", ""))
        entity_id = getattr(key, "entity_id", getattr(node, "entity_id", None))

        # Status / Schedule filter.
        if self._status_filter != "all":
            if self._status_filter == "active":
                if status in (
                    "completed",
                    "cancelled",
                ):
                    return False
            elif self._status_filter == "critical":
                model = self.sourceModel()
                cpm_res = getattr(model, "cpm_result", None)
                if cpm_res is None:
                    return False
                cpm_node = cpm_res.get_node(key) if key is not None else None
                if not cpm_node or not cpm_node.is_critical:
                    return False
            elif self._status_filter == "has_float":
                model = self.sourceModel()
                cpm_res = getattr(model, "cpm_result", None)
                if cpm_res is None:
                    return False
                cpm_node = cpm_res.get_node(key) if key is not None else None
                if not cpm_node or cpm_node.total_float_minutes is None or cpm_node.total_float_minutes <= 0:
                    return False
            elif self._status_filter == "schedule_warnings":
                model = self.sourceModel()
                cpm_res = getattr(model, "cpm_result", None)
                if cpm_res is None:
                    return False
                if key is not None and key in set(getattr(cpm_res, "cycle_keys", ()) or ()):
                    return True
                cpm_node = cpm_res.get_node(key) if key is not None else None
                if not cpm_node or not cpm_node.schedulable or cpm_node.diagnostic_codes:
                    return True
                return False
            elif status != self._status_filter:
                return False

        # Search query.
        if self._search_query:
            q = self._search_query.lower()

            if (
                q not in title
                and q not in code
                and q not in status
            ):
                return False

        return True

    def get_accepted_keys(self) -> Set[str]:
        """Returns set of accepted EntityRefs or string representations."""
        if self._accepted_keys is None:
            return set()
        return {str(k) for k in self._accepted_keys}

    def _rebuild_acceptance_cache(self):
        """
        Build accepted-key closure in one non-recursive tree pass.

        Complexity:
            O(number of WBS nodes + edges)

        Algorithm:
        1. Calculate direct matches exactly once per node.
        2. Iterative post-order traversal.
        3. Accept a node when:
              node matches directly
              OR any child is accepted.
        """

        if not self.has_active_filter():
            self._accepted_keys = None
            self._direct_match_keys.clear()
            return

        model: Optional[WBSItemModel] = (
            self.sourceModel()
        )

        if model is None:
            self._accepted_keys = set()
            self._direct_match_keys.clear()
            return

        snapshot = getattr(
            model,
            "snapshot",
            None,
        )

        if snapshot is None:
            self._accepted_keys = set()
            self._direct_match_keys.clear()
            return

        nodes_by_key = getattr(
            snapshot,
            "nodes_by_key",
            {},
        ) or {}

        children_by_parent = getattr(
            snapshot,
            "children_by_parent",
            {},
        ) or {}

        root_keys = list(
            getattr(
                snapshot,
                "root_keys",
                [],
            )
            or []
        )

        direct_matches: Set[EntityRef] = set()

        for key, node in nodes_by_key.items():
            if self._node_object_matches(node):
                direct_matches.add(key)

        accepted: Set[EntityRef] = set()

        # Iterative post-order:
        # (key, False) = descend
        # (key, True)  = children already processed
        stack = []

        for root_key in reversed(root_keys):
            stack.append(
                (root_key, False)
            )

        visited = set()

        while stack:
            key, expanded = stack.pop()

            if expanded:
                child_keys = children_by_parent.get(
                    key,
                    [],
                )

                if (
                    key in direct_matches
                    or any(
                        child_key in accepted
                        for child_key in child_keys
                    )
                ):
                    accepted.add(key)

                continue

            if key in visited:
                # Defensive malformed-snapshot protection.
                continue

            visited.add(key)

            stack.append(
                (key, True)
            )

            child_keys = children_by_parent.get(
                key,
                [],
            )

            for child_key in reversed(
                child_keys
            ):
                if child_key in nodes_by_key:
                    stack.append(
                        (child_key, False)
                    )

        # Defensive support for orphan/unreachable nodes.
        #
        # Canonical WBSService should normally produce no orphans, but a
        # direct matching orphan should not disappear because of a damaged
        # snapshot. Walk only parent links; no recursion.
        for key in direct_matches:
            if key in accepted:
                continue

            current_key = key
            chain_seen = set()

            while (
                current_key is not None
                and current_key not in chain_seen
            ):
                chain_seen.add(
                    current_key
                )
                accepted.add(
                    current_key
                )

                node = nodes_by_key.get(
                    current_key
                )

                current_key = (
                    getattr(
                        node,
                        "parent_key",
                        None,
                    )
                    if node is not None
                    else None
                )

        self._direct_match_keys = direct_matches
        self._accepted_keys = accepted

    # ------------------------------------------------------------------
    # Qt filtering hot path
    # ------------------------------------------------------------------

    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QModelIndex,
    ) -> bool:
        if not self.has_active_filter():
            return True

        if self._accepted_keys is None:
            self._rebuild_acceptance_cache()

        model: Optional[WBSItemModel] = (
            self.sourceModel()
        )

        if model is None:
            return True

        idx = model.index(
            source_row,
            0,
            source_parent,
        )

        if not idx.isValid():
            return False

        key = model.data(
            idx,
            WBSItemModel.NodeKeyRole,
        )

        return bool(
            key is not None
            and key in (
                self._accepted_keys
                or set()
            )
        )

    # ------------------------------------------------------------------
    # Compatibility helpers
    # ------------------------------------------------------------------

    def _node_matches(
        self,
        source_row: int,
        source_parent: QModelIndex,
    ) -> bool:
        """
        Phase 1B compatibility helper.

        No descendant recursion is performed here.
        """

        model: Optional[WBSItemModel] = (
            self.sourceModel()
        )

        if model is None:
            return True

        idx = model.index(
            source_row,
            0,
            source_parent,
        )

        if not idx.isValid():
            return False

        node = model.data(
            idx,
            WBSItemModel.NodeObjectRole,
        )

        return self._node_object_matches(
            node
        )

    def _has_matching_descendant(
        self,
        source_row: int,
        source_parent: QModelIndex,
    ) -> bool:
        """
        Compatibility helper retained for existing callers/tests.

        Phase 1F.1:
        Uses the precomputed acceptance cache and checks only immediate
        children. No recursive Python tree scan.
        """

        model: Optional[WBSItemModel] = (
            self.sourceModel()
        )

        if model is None:
            return False

        if self._accepted_keys is None:
            self._rebuild_acceptance_cache()

        idx = model.index(
            source_row,
            0,
            source_parent,
        )

        if not idx.isValid():
            return False

        node = model.data(
            idx,
            WBSItemModel.NodeObjectRole,
        )

        if node is None:
            return False

        snapshot = model.snapshot

        for child_key in (
            snapshot.children_by_parent.get(
                node.key,
                [],
            )
        ):
            if child_key in (
                self._accepted_keys
                or set()
            ):
                return True

        return False
