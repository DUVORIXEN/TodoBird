"""
TODO BIRD — Work Breakdown Structure (WBS) Authority Service (Phase 1A)
Canonical parent/child hierarchy model, derived WBS numbering, deterministic
ordering, safe tree traversal, cycle prevention, and project-boundary validation.

PURE DATA SERVICE: Zero Qt dependencies, zero timers, zero UI logic.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set, Any, Tuple, Iterable
import logging

logger = logging.getLogger(__name__)


# ==============================================================================
# 1. CANONICAL TYPED ENTITY IDENTITY
# ==============================================================================

@dataclass(frozen=True)
class EntityRef:
    """
    Immutable typed entity reference preventing task vs subtask ID collisions.
    Example: EntityRef('task', 42) != EntityRef('subtask', 42).
    """
    entity_type: str  # "task" or "subtask"
    entity_id: int

    def __post_init__(self):
        norm_type = str(self.entity_type).lower().strip()
        if norm_type not in ("task", "subtask"):
            raise ValueError(f"Invalid entity_type '{self.entity_type}'; must be 'task' or 'subtask'.")
        object.__setattr__(self, "entity_type", norm_type)
        object.__setattr__(self, "entity_id", int(self.entity_id))

    def __str__(self) -> str:
        return f"{self.entity_type}:{self.entity_id}"

    def __repr__(self) -> str:
        return f"EntityRef({self.entity_type!r}, {self.entity_id!r})"

    @classmethod
    def from_string(cls, s: str) -> "EntityRef":
        parts = s.split(":", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid EntityRef string format: '{s}' (expected 'task:ID' or 'subtask:ID')")
        return cls(entity_type=parts[0].lower().strip(), entity_id=int(parts[1]))

    @classmethod
    def task(cls, task_id: int) -> "EntityRef":
        return cls(entity_type="task", entity_id=int(task_id))

    @classmethod
    def subtask(cls, subtask_id: int) -> "EntityRef":
        return cls(entity_type="subtask", entity_id=int(subtask_id))


# ==============================================================================
# 2. CANONICAL WBS NODE (HIERARCHY METADATA)
# ==============================================================================

@dataclass(frozen=True)
class WBSNode:
    """
    Lightweight, immutable WBS hierarchy representation.
    Holds structural and derived display metadata without duplicating full task payload.
    """
    key: EntityRef
    project_id: Optional[int]
    parent_key: Optional[EntityRef]
    title: str
    sibling_order: int
    depth: int
    wbs_code: str
    child_count: int
    has_children: bool
    status: Optional[str] = None
    is_milestone: bool = False
    is_completed: bool = False
    created_at: Optional[str] = None


# ==============================================================================
# 3. HIERARCHY VALIDATION RESULT
# ==============================================================================

@dataclass(frozen=True)
class HierarchyValidationResult:
    """
    Structured result returned by hierarchy validation routines.
    """
    valid: bool
    reason_code: Optional[str] = None
    message: Optional[str] = None
    affected_subtree_size: int = 0


# ==============================================================================
# 4. WBS HIERARCHY SNAPSHOT
# ==============================================================================

@dataclass(frozen=True)
class WBSHierarchySnapshot:
    """
    Immutable snapshot of a project's WBS hierarchy.
    Enables Phase 1B Qt QAbstractItemModel to adapt hierarchy safely and efficiently.
    """
    project_id: Optional[int]
    nodes_by_key: Dict[EntityRef, WBSNode]
    children_by_parent: Dict[Optional[EntityRef], List[EntityRef]]
    root_keys: List[EntityRef]
    orphaned_keys: List[EntityRef]
    total_nodes: int
    max_depth: int
    revision: int = 1


# ==============================================================================
# 5. WBS SERVICE AUTHORITY
# ==============================================================================

class WBSService:
    """
    Central Work Breakdown Structure authority for Todo Bird.
    Provides bulk loading, derived numbering, deterministic ordering, traversal,
    cycle prevention, and project-boundary validation.
    """

    # Validation Reason Codes
    ERR_SELF_PARENT = "SELF_PARENT"
    ERR_CYCLE_DETECTED = "CYCLE_DETECTED"
    ERR_PARENT_NOT_FOUND = "PARENT_NOT_FOUND"
    ERR_CROSS_PROJECT_MISMATCH = "CROSS_PROJECT_MISMATCH"
    ERR_NODE_NOT_FOUND = "NODE_NOT_FOUND"

    @classmethod
    def build_project_hierarchy(
        cls,
        db_manager: Any,
        project_id: Optional[int] = None,
        revision: int = 1
    ) -> WBSHierarchySnapshot:
        """
        Loads the hierarchy for a project (or all projects) in bulk via 2 indexed queries.
        Zero N+1 query overhead.
        """
        raw_items: List[Dict[str, Any]] = []

        with db_manager.get_connection() as conn:
            cursor = conn.cursor()

            # 1. Fetch Main Tasks
            if project_id is not None:
                cursor.execute("""
                    SELECT id, title, project_id, position, status, created_at
                    FROM tasks
                    WHERE project_id = ?
                    ORDER BY position ASC, created_at ASC, id ASC;
                """, (project_id,))
            else:
                cursor.execute("""
                    SELECT id, title, project_id, position, status, created_at
                    FROM tasks
                    ORDER BY position ASC, created_at ASC, id ASC;
                """)
            task_rows = cursor.fetchall()

            for r in task_rows:
                raw_items.append({
                    "key": EntityRef.task(r["id"]),
                    "parent_key": None,
                    "project_id": r["project_id"],
                    "title": r["title"] or "",
                    "position": int(r["position"] or 0),
                    "status": r["status"],
                    "is_completed": str(r["status"]).lower() == "completed",
                    "is_milestone": False,
                    "created_at": r["created_at"],
                })

            # 2. Fetch Subtasks
            if project_id is not None:
                cursor.execute("""
                    SELECT s.id, s.task_id, s.parent_subtask_id, s.title, s.position,
                           s.is_completed, s.created_at, t.project_id
                    FROM subtasks s
                    JOIN tasks t ON s.task_id = t.id
                    WHERE t.project_id = ?
                    ORDER BY s.parent_subtask_id, s.position ASC, s.created_at ASC, s.id ASC;
                """, (project_id,))
            else:
                cursor.execute("""
                    SELECT s.id, s.task_id, s.parent_subtask_id, s.title, s.position,
                           s.is_completed, s.created_at, t.project_id
                    FROM subtasks s
                    JOIN tasks t ON s.task_id = t.id
                    ORDER BY s.parent_subtask_id, s.position ASC, s.created_at ASC, s.id ASC;
                """)
            subtask_rows = cursor.fetchall()

            for r in subtask_rows:
                sub_parent = r["parent_subtask_id"]
                parent_ref = EntityRef.subtask(sub_parent) if sub_parent is not None else EntityRef.task(r["task_id"])
                raw_items.append({
                    "key": EntityRef.subtask(r["id"]),
                    "parent_key": parent_ref,
                    "project_id": r["project_id"],
                    "title": r["title"] or "",
                    "position": int(r["position"] or 0),
                    "status": "Completed" if r["is_completed"] else "Planned",
                    "is_completed": bool(r["is_completed"]),
                    "is_milestone": False,
                    "created_at": r["created_at"],
                })

        return cls.build_from_raw(raw_items, project_id=project_id, revision=revision)

    @classmethod
    def build_from_raw(
        cls,
        raw_nodes: List[Dict[str, Any]],
        project_id: Optional[int] = None,
        revision: int = 1
    ) -> WBSHierarchySnapshot:
        """
        Builds a canonical WBSHierarchySnapshot from raw node dictionaries.
        Guarantees deterministic sibling order, derived WBS codes, safe cycle
        mitigation, and orphan detection.
        """
        raw_map: Dict[EntityRef, Dict[str, Any]] = {}
        parent_map: Dict[EntityRef, Optional[EntityRef]] = {}

        for item in raw_nodes:
            key = item["key"]
            if isinstance(key, str):
                key = EntityRef.from_string(key)
            parent_key = item.get("parent_key")
            if isinstance(parent_key, str):
                parent_key = EntityRef.from_string(parent_key)

            raw_map[key] = {
                "key": key,
                "parent_key": parent_key,
                "project_id": item.get("project_id"),
                "title": item.get("title", ""),
                "position": int(item.get("position", 0) or 0),
                "status": item.get("status"),
                "is_milestone": bool(item.get("is_milestone", False)),
                "is_completed": bool(item.get("is_completed", False)),
                "created_at": item.get("created_at") or "",
            }
            parent_map[key] = parent_key

        # ----------------------------------------------------------------------
        # CYCLE & ORPHAN DETECTION (Safe Traversal Guarantee H03, H09, H10)
        # ----------------------------------------------------------------------
        orphaned_keys: List[EntityRef] = []
        valid_parent_map: Dict[EntityRef, Optional[EntityRef]] = {}

        for key, parent in parent_map.items():
            if parent is None:
                valid_parent_map[key] = None
                continue

            # Check if parent exists
            if parent not in raw_map:
                orphaned_keys.append(key)
                continue

            # Check for self-parenting
            if key == parent:
                orphaned_keys.append(key)
                continue

            # Trace ancestors to detect cycles
            visited: Set[EntityRef] = {key}
            curr = parent
            has_cycle = False
            while curr is not None:
                if curr in visited:
                    has_cycle = True
                    break
                visited.add(curr)
                curr = parent_map.get(curr)

            if has_cycle:
                orphaned_keys.append(key)
            else:
                valid_parent_map[key] = parent

        # Build raw adjacency list
        children_by_parent: Dict[Optional[EntityRef], List[EntityRef]] = {}
        for key, parent in valid_parent_map.items():
            children_by_parent.setdefault(parent, []).append(key)

        # Sort siblings deterministically (H08):
        # Order by (position, created_at, entity_id)
        for p_key, child_list in children_by_parent.items():
            child_list.sort(key=lambda k: (
                raw_map[k]["position"],
                raw_map[k]["created_at"],
                k.entity_id
            ))

        root_keys = list(children_by_parent.get(None, []))

        # ----------------------------------------------------------------------
        # DERIVE WBS CODES & DEPTH
        # ----------------------------------------------------------------------
        nodes_by_key: Dict[EntityRef, WBSNode] = {}
        max_depth = 0

        stack: List[Tuple[Optional[EntityRef], str, int]] = [(None, "", 0)]
        while stack:
            p_key, parent_code, depth = stack.pop()
            if depth > max_depth:
                max_depth = depth

            children = children_by_parent.get(p_key, [])
            child_frames: List[Tuple[EntityRef, str, int]] = []
            for idx, c_key in enumerate(children):
                sibling_order = idx + 1
                wbs_code = str(sibling_order) if not parent_code else f"{parent_code}.{sibling_order}"

                c_raw = raw_map[c_key]
                child_count = len(children_by_parent.get(c_key, []))

                node = WBSNode(
                    key=c_key,
                    project_id=c_raw["project_id"],
                    parent_key=p_key,
                    title=c_raw["title"],
                    sibling_order=sibling_order,
                    depth=depth,
                    wbs_code=wbs_code,
                    child_count=child_count,
                    has_children=child_count > 0,
                    status=c_raw["status"],
                    is_milestone=c_raw["is_milestone"],
                    is_completed=c_raw["is_completed"],
                    created_at=c_raw["created_at"],
                )
                nodes_by_key[c_key] = node
                child_frames.append((c_key, wbs_code, depth + 1))

            stack.extend(reversed(child_frames))

        return WBSHierarchySnapshot(
            project_id=project_id,
            nodes_by_key=nodes_by_key,
            children_by_parent=children_by_parent,
            root_keys=root_keys,
            orphaned_keys=orphaned_keys,
            total_nodes=len(nodes_by_key),
            max_depth=max_depth if nodes_by_key else 0,
            revision=revision,
        )

    # ==========================================================================
    # TRAVERSAL & QUERY APIS
    # ==========================================================================

    @classmethod
    def get_node(cls, snapshot: WBSHierarchySnapshot, key: EntityRef) -> Optional[WBSNode]:
        """Returns the WBSNode for a given key, or None if not found."""
        return snapshot.nodes_by_key.get(key)

    @classmethod
    def get_parent(cls, snapshot: WBSHierarchySnapshot, key: EntityRef) -> Optional[WBSNode]:
        """Returns the parent WBSNode of a given node, or None if root or missing."""
        node = snapshot.nodes_by_key.get(key)
        if node is None or node.parent_key is None:
            return None
        return snapshot.nodes_by_key.get(node.parent_key)

    @classmethod
    def get_children(cls, snapshot: WBSHierarchySnapshot, key: Optional[EntityRef]) -> List[WBSNode]:
        """Returns the ordered list of child WBSNodes for a parent key (None = roots)."""
        child_keys = snapshot.children_by_parent.get(key, [])
        return [snapshot.nodes_by_key[k] for k in child_keys if k in snapshot.nodes_by_key]

    @classmethod
    def get_ancestors(cls, snapshot: WBSHierarchySnapshot, key: EntityRef) -> List[WBSNode]:
        """
        Returns ancestor WBSNodes from immediate parent up to the top-level root.
        """
        ancestors: List[WBSNode] = []
        curr = cls.get_parent(snapshot, key)
        visited: Set[EntityRef] = set()

        while curr is not None and curr.key not in visited:
            ancestors.append(curr)
            visited.add(curr.key)
            curr = cls.get_parent(snapshot, curr.key)

        return ancestors

    @classmethod
    def get_descendants(cls, snapshot: WBSHierarchySnapshot, key: EntityRef) -> List[WBSNode]:
        """
        Returns all descendant WBSNodes in depth-first order.
        """
        descendants: List[WBSNode] = []
        stack = list(reversed(snapshot.children_by_parent.get(key, [])))
        while stack:
            child_key = stack.pop()
            child = snapshot.nodes_by_key.get(child_key)
            if child is None:
                continue
            descendants.append(child)
            stack.extend(reversed(snapshot.children_by_parent.get(child_key, [])))
        return descendants

    @classmethod
    def get_descendant_count(cls, snapshot: WBSHierarchySnapshot, key: EntityRef) -> int:
        """Returns total number of descendant nodes across all sub-levels.

        Iterative on purpose: deep hierarchies exceeded Python's recursion
        limit under the previous nested-helper version.
        """
        count = 0
        stack = list(snapshot.children_by_parent.get(key, []))
        while stack:
            child_key = stack.pop()
            count += 1
            stack.extend(snapshot.children_by_parent.get(child_key, []))
        return count

    @classmethod
    def get_depth(cls, snapshot: WBSHierarchySnapshot, key: EntityRef) -> int:
        """Returns the depth level of a node (0 = root)."""
        node = snapshot.nodes_by_key.get(key)
        return node.depth if node else -1

    @classmethod
    def is_descendant(
        cls,
        snapshot: WBSHierarchySnapshot,
        candidate: EntityRef,
        ancestor: EntityRef
    ) -> bool:
        """
        Returns True if `candidate` is a descendant of `ancestor`.
        """
        if candidate == ancestor:
            return False

        curr = cls.get_parent(snapshot, candidate)
        visited: Set[EntityRef] = set()
        while curr is not None and curr.key not in visited:
            if curr.key == ancestor:
                return True
            visited.add(curr.key)
            curr = cls.get_parent(snapshot, curr.key)

        return False

    @classmethod
    def flatten_project(
        cls,
        snapshot: WBSHierarchySnapshot,
        expanded_keys: Optional[Set[EntityRef]] = None
    ) -> List[WBSNode]:
        """
        Flattens the project hierarchy into a list in depth-first display order.
        If `expanded_keys` is provided, only nodes whose parent branch is expanded
        will include their children (essential for virtualized QTreeView syncing).
        If `expanded_keys` is None, all nodes are returned.
        """
        flattened: List[WBSNode] = []

        def dfs(p_key: Optional[EntityRef]):
            for child in cls.get_children(snapshot, p_key):
                flattened.append(child)
                if expanded_keys is None or child.key in expanded_keys:
                    dfs(child.key)

        dfs(None)
        return flattened

    # ==========================================================================
    # HIERARCHY MUTATION VALIDATION (INVARIANTS H01..H05)
    # ==========================================================================

    @classmethod
    def validate_parent_change(
        cls,
        snapshot: WBSHierarchySnapshot,
        node_key: EntityRef,
        new_parent_key: Optional[EntityRef],
        target_project_id: Optional[int] = None
    ) -> HierarchyValidationResult:
        """
        Validates whether changing `node_key`'s parent to `new_parent_key` is valid.
        Enforces H01 (no self-parent), H02/H03 (no cycles), H04 (parent must exist),
        and H05 (same-project boundary).
        """
        node = snapshot.nodes_by_key.get(node_key)
        if node is None:
            return HierarchyValidationResult(
                valid=False,
                reason_code=cls.ERR_NODE_NOT_FOUND,
                message=f"Node '{node_key}' not found in current hierarchy snapshot."
            )

        # H01: Self-parenting check
        if new_parent_key is not None and node_key == new_parent_key:
            return HierarchyValidationResult(
                valid=False,
                reason_code=cls.ERR_SELF_PARENT,
                message="A node cannot be its own parent (Invariant H01)."
            )

        # If moving to root (new_parent_key is None)
        if new_parent_key is None:
            subtree_size = cls.get_descendant_count(snapshot, node_key) + 1
            return HierarchyValidationResult(
                valid=True,
                affected_subtree_size=subtree_size
            )

        # H04: Parent must exist
        parent_node = snapshot.nodes_by_key.get(new_parent_key)
        if parent_node is None:
            return HierarchyValidationResult(
                valid=False,
                reason_code=cls.ERR_PARENT_NOT_FOUND,
                message=f"Target parent '{new_parent_key}' does not exist in hierarchy snapshot (Invariant H04)."
            )

        # H02/H03: Cycle check (cannot become child of own descendant)
        if cls.is_descendant(snapshot, new_parent_key, node_key):
            return HierarchyValidationResult(
                valid=False,
                reason_code=cls.ERR_CYCLE_DETECTED,
                message=f"Cannot move '{node.title}' under its own descendant '{parent_node.title}' (Invariant H02/H03)."
            )

        # H05: Same project boundary
        effective_target_proj = target_project_id if target_project_id is not None else node.project_id
        if parent_node.project_id != effective_target_proj:
            return HierarchyValidationResult(
                valid=False,
                reason_code=cls.ERR_CROSS_PROJECT_MISMATCH,
                message=(
                    f"Cross-project parenting rejected: Parent '{parent_node.title}' belongs to project "
                    f"{parent_node.project_id}, but child belongs to project {effective_target_proj} (Invariant H05)."
                )
            )

        subtree_size = cls.get_descendant_count(snapshot, node_key) + 1
        return HierarchyValidationResult(
            valid=True,
            affected_subtree_size=subtree_size
        )
