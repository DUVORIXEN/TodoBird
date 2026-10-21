"""
TODO BIRD — WBS TREE VIEW (QTreeView)
Professional, high-performance hierarchical tree view for Todo Bird WBS.
Replaces default Qt branch icons, handles custom vector chevron interaction,
smooth keyboard navigation, expansion state persistence, and modern theming.
"""

from typing import Optional, Set
from PySide6.QtCore import Qt, QModelIndex, Signal, QRectF, QEvent, QMimeData
from PySide6.QtWidgets import QTreeView, QAbstractItemView, QHeaderView, QWidget
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPainter, QDrag, QColor, QPen

from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.services.wbs_service import EntityRef, WBSNode
from todo_bird_app.models.wbs_item_model import WBSItemModel
from todo_bird_app.models.wbs_filter_proxy_model import WBSFilterProxyModel
from todo_bird_app.views.wbs_tree_delegate import WBSTreeItemDelegate
from todo_bird_app.ui.components.modern_scrollbar import ModernScrollBarStyle
from todo_bird_app.services.wbs_customization_service import WBSCustomizationService


class WBSTreeView(QTreeView):
    """
    Production WBS QTreeView component.
    """

    taskSelected = Signal(object)      # (EntityRef)
    taskDoubleClicked = Signal(object) # (EntityRef)
    taskContextMenuRequested = Signal(object, object) # (EntityRef, QPoint)
    hierarchyIndentRequested = Signal(object)         # (EntityRef)
    hierarchyOutdentRequested = Signal(object)        # (EntityRef)
    hierarchyDropRequested = Signal(object, object, str)
    # source EntityRef, target EntityRef, zone(before|into|after)

    def __init__(
        self,
        custom_service: Optional[WBSCustomizationService] = None,
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
    ):
        super().__init__(parent)
        self._custom_service = custom_service
        self._is_dark = is_dark
        self._accent_color = accent_color
        self._expanded_keys: Set[EntityRef] = set()

        # Delegate
        self._delegate = WBSTreeItemDelegate(
            custom_service=custom_service,
            parent=self,
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self.setItemDelegate(self._delegate)

        # Invariants & Appearance Configuration
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(False)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAnimated(True)
        self.setExpandsOnDoubleClick(False)
        self.setRootIsDecorated(False)  # Custom chevrons painted by delegate
        self.setIndentation(0)          # Delegate handles column 0 indentation
        self.setFocusPolicy(Qt.StrongFocus)

        # Phase 1F.4 — custom WBS hierarchy accessibility semantics.
        self.setAccessibleName("Work breakdown structure")
        self.setAccessibleDescription(
            "Hierarchical project tasks. "
            "Use arrow keys to navigate, Enter to open, "
            "Tab and Shift+Tab to indent or outdent, "
            "and Alt+Up or Alt+Down to reorder."
        )

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu_requested)

        # Phase 1E.4 — safe custom drag/drop.
        #
        # Qt's native model-drop pipeline is intentionally NOT used.
        # startDrag()/dropEvent() below exchange only typed EntityRefs
        # and emit a mutation request to WBSProjectView.
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropOverwriteMode(False)

        self._wbs_drag_target_key = None
        self._wbs_drag_zone = None
        self._wbs_drag_target_rect = None

        # Signals
        self.doubleClicked.connect(self._on_double_clicked)
        self.clicked.connect(self._on_clicked)
        self.expanded.connect(self._on_expanded_node)
        self.collapsed.connect(self._on_collapsed_node)

        self._setup_header()
        self._apply_theme()

    def setModel(self, model):
        super().setModel(model)
        self._setup_header()

    def _setup_header(self):
        header = self.header()
        if not header:
            return
        header.setStretchLastSection(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setMinimumSectionSize(90)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        if header.count() >= WBSItemModel.COLUMN_COUNT:
            header.setSectionResizeMode(WBSItemModel.COL_WBS, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_TITLE, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_STATUS, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_PROGRESS, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_CRITICAL, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_TOTAL_FLOAT, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_FREE_FLOAT, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_ES, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_EF, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_LS, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_LF, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_DIAGNOSTICS, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_BASELINE_START, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_BASELINE_FINISH, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_START_VARIANCE, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_FINISH_VARIANCE, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_DURATION_VARIANCE, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_CONSTRAINT, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_CONSTRAINT_DATE, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_DEADLINE, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_DEADLINE_VARIANCE, QHeaderView.Interactive)
            header.setSectionResizeMode(WBSItemModel.COL_CONSTRAINT_STATUS, QHeaderView.Interactive)

            header.resizeSection(WBSItemModel.COL_WBS, 130)
            header.resizeSection(WBSItemModel.COL_TITLE, 220)
            header.resizeSection(WBSItemModel.COL_STATUS, 110)
            header.resizeSection(WBSItemModel.COL_PROGRESS, 100)
            header.resizeSection(WBSItemModel.COL_CRITICAL, 105)
            header.resizeSection(WBSItemModel.COL_TOTAL_FLOAT, 95)
            header.resizeSection(WBSItemModel.COL_FREE_FLOAT, 95)
            header.resizeSection(WBSItemModel.COL_ES, 115)
            header.resizeSection(WBSItemModel.COL_EF, 115)
            header.resizeSection(WBSItemModel.COL_LS, 115)
            header.resizeSection(WBSItemModel.COL_LF, 115)
            header.resizeSection(WBSItemModel.COL_DIAGNOSTICS, 120)
            header.resizeSection(WBSItemModel.COL_BASELINE_START, 115)
            header.resizeSection(WBSItemModel.COL_BASELINE_FINISH, 115)
            header.resizeSection(WBSItemModel.COL_START_VARIANCE, 95)
            header.resizeSection(WBSItemModel.COL_FINISH_VARIANCE, 95)
            header.resizeSection(WBSItemModel.COL_DURATION_VARIANCE, 95)
            header.resizeSection(WBSItemModel.COL_CONSTRAINT, 125)
            header.resizeSection(WBSItemModel.COL_CONSTRAINT_DATE, 130)
            header.resizeSection(WBSItemModel.COL_DEADLINE, 130)
            header.resizeSection(WBSItemModel.COL_DEADLINE_VARIANCE, 120)
            header.resizeSection(WBSItemModel.COL_CONSTRAINT_STATUS, 130)

        self.apply_column_visibility()

    def apply_column_visibility(self):
        header = self.header()
        if not header or header.count() < WBSItemModel.COLUMN_COUNT:
            return

        if self._custom_service:
            show_code = self._custom_service.get_preference("wbs_show_code", True)
            show_status = self._custom_service.get_preference("wbs_show_status", True)
            show_progress = self._custom_service.get_preference("wbs_show_progress", True)
            show_critical = self._custom_service.get_preference("wbs_show_critical", True)
            show_total_float = self._custom_service.get_preference("wbs_show_total_float", True)
            show_free_float = self._custom_service.get_preference("wbs_show_free_float", False)
            show_es = self._custom_service.get_preference("wbs_show_es", False)
            show_ef = self._custom_service.get_preference("wbs_show_ef", False)
            show_ls = self._custom_service.get_preference("wbs_show_ls", False)
            show_lf = self._custom_service.get_preference("wbs_show_lf", False)
            show_diag = self._custom_service.get_preference("wbs_show_diagnostics", False)
            show_b_start = self._custom_service.get_preference("wbs_show_baseline_start", False)
            show_b_finish = self._custom_service.get_preference("wbs_show_baseline_finish", False)
            show_s_var = self._custom_service.get_preference("wbs_show_start_variance", False)
            show_f_var = self._custom_service.get_preference("wbs_show_finish_variance", True)
            show_d_var = self._custom_service.get_preference("wbs_show_duration_variance", False)
            show_ctype = self._custom_service.get_preference("wbs_show_constraint_type", True)
            show_cdate = self._custom_service.get_preference("wbs_show_constraint_date", True)
            show_deadline = self._custom_service.get_preference("wbs_show_deadline", False)
            show_dl_var = self._custom_service.get_preference("wbs_show_deadline_variance", False)
            show_cstat = self._custom_service.get_preference("wbs_show_constraint_status", True)
        else:
            show_code = True
            show_status = True
            show_progress = True
            show_critical = True
            show_total_float = True
            show_free_float = False
            show_es = False
            show_ef = False
            show_ls = False
            show_lf = False
            show_diag = False
            show_b_start = False
            show_b_finish = False
            show_s_var = False
            show_f_var = True
            show_d_var = False
            show_ctype = True
            show_cdate = True
            show_deadline = False
            show_dl_var = False
            show_cstat = True

        header.setSectionHidden(WBSItemModel.COL_WBS, not show_code)
        header.setSectionHidden(WBSItemModel.COL_STATUS, not show_status)
        header.setSectionHidden(WBSItemModel.COL_PROGRESS, not show_progress)
        header.setSectionHidden(WBSItemModel.COL_CRITICAL, not show_critical)
        header.setSectionHidden(WBSItemModel.COL_TOTAL_FLOAT, not show_total_float)
        header.setSectionHidden(WBSItemModel.COL_FREE_FLOAT, not show_free_float)
        header.setSectionHidden(WBSItemModel.COL_ES, not show_es)
        header.setSectionHidden(WBSItemModel.COL_EF, not show_ef)
        header.setSectionHidden(WBSItemModel.COL_LS, not show_ls)
        header.setSectionHidden(WBSItemModel.COL_LF, not show_lf)
        header.setSectionHidden(WBSItemModel.COL_DIAGNOSTICS, not show_diag)
        header.setSectionHidden(WBSItemModel.COL_BASELINE_START, not show_b_start)
        header.setSectionHidden(WBSItemModel.COL_BASELINE_FINISH, not show_b_finish)
        header.setSectionHidden(WBSItemModel.COL_START_VARIANCE, not show_s_var)
        header.setSectionHidden(WBSItemModel.COL_FINISH_VARIANCE, not show_f_var)
        header.setSectionHidden(WBSItemModel.COL_DURATION_VARIANCE, not show_d_var)
        header.setSectionHidden(WBSItemModel.COL_CONSTRAINT, not show_ctype)
        header.setSectionHidden(WBSItemModel.COL_CONSTRAINT_DATE, not show_cdate)
        header.setSectionHidden(WBSItemModel.COL_DEADLINE, not show_deadline)
        header.setSectionHidden(WBSItemModel.COL_DEADLINE_VARIANCE, not show_dl_var)
        header.setSectionHidden(WBSItemModel.COL_CONSTRAINT_STATUS, not show_cstat)

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color
        self._delegate.set_theme(is_dark, accent_color)
        self._apply_theme()
        self.viewport().update()

    def _apply_theme(self):
        if self._custom_service:
            surfaces = self._custom_service.get_surface_colors(self._is_dark, self._accent_color)
            bg = surfaces["bg_panel"]
            header_bg = surfaces["bg_header"]
            header_fg = surfaces["text_secondary"]
            border_col = surfaces["border_subtle"]
        else:
            bg = "#1C1D2C" if self._is_dark else "#FFFFFF"
            header_bg = "#181926" if self._is_dark else "#F8FAFC"
            header_fg = "#A6ADC8" if self._is_dark else "#64748B"
            border_col = "#2E3045" if self._is_dark else "#E2E8F0"

        accent = self._accent_color
        scrollbar_qss = ModernScrollBarStyle.get_qss(self._is_dark, accent)

        self.setStyleSheet(f"""
            QTreeView {{
                background-color: {bg};
                border: none;
                outline: none;
            }}
            QHeaderView::section {{
                background-color: {header_bg};
                color: {header_fg};
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                padding: 6px 10px;
                border: none;
                border-bottom: 1px solid {border_col};
            }}
            {scrollbar_qss}
        """)

    # -------------------------------------------------------------------------
    # Expansion & Selection Helpers
    # -------------------------------------------------------------------------

    def get_source_node(self, proxy_index: QModelIndex) -> Optional[WBSNode]:
        if not proxy_index.isValid():
            return None
        model = self.model()
        if isinstance(model, WBSFilterProxyModel):
            src_idx = model.mapToSource(proxy_index)
            src_model: WBSItemModel = model.sourceModel()
            return src_model.node_from_index(src_idx)
        elif isinstance(model, WBSItemModel):
            return model.node_from_index(proxy_index)
        return None

    def get_source_key(self, proxy_index: QModelIndex) -> Optional[EntityRef]:
        node = self.get_source_node(proxy_index)
        return node.key if node else None

    def save_expansion_state(self) -> Set[EntityRef]:
        """Returns the set of currently expanded EntityRef keys."""
        return set(self._expanded_keys)

    def restore_expansion_state(self, expanded_keys: Set[EntityRef]):
        """Restores branch expansion for the given stable EntityRef keys."""
        self._expanded_keys = set(expanded_keys)
        model = self.model()
        if not model:
            return

        def _check_and_expand(idx: QModelIndex):
            if not idx.isValid():
                return
            key = self.get_source_key(idx)
            if key in self._expanded_keys:
                self.setExpanded(idx, True)

            child_rows = model.rowCount(idx)
            for r in range(child_rows):
                _check_and_expand(model.index(r, 0, idx))

        root_rows = model.rowCount(QModelIndex())
        for r in range(root_rows):
            _check_and_expand(model.index(r, 0, QModelIndex()))

    def get_selected_key(self) -> Optional[EntityRef]:
        indexes = self.selectedIndexes()
        if indexes:
            return self.get_source_key(indexes[0])
        return None

    def select_key(self, key: EntityRef):
        model = self.model()
        if not model:
            return

        target_idx = QModelIndex()
        if isinstance(model, WBSFilterProxyModel):
            src_model: WBSItemModel = model.sourceModel()
            src_idx = src_model.index_from_key(key)
            if src_idx.isValid():
                target_idx = model.mapFromSource(src_idx)
        elif isinstance(model, WBSItemModel):
            target_idx = model.index_from_key(key)

        if target_idx.isValid():
            self.setCurrentIndex(target_idx)
            self.selectionModel().select(
                target_idx,
                self.selectionModel().SelectionFlag.ClearAndSelect | self.selectionModel().SelectionFlag.Rows
            )
            self.scrollTo(target_idx)

    def expand_to_level(self, max_level: int):
        """Expands tree nodes up to depth max_level (1 = roots only, 2 = roots + depth 1, etc.)."""
        model = self.model()
        if not model:
            return

        self.collapseAll()

        def _expand_level(idx: QModelIndex, current_depth: int):
            if current_depth > max_level or not idx.isValid():
                return
            self.setExpanded(idx, True)
            child_rows = model.rowCount(idx)
            for r in range(child_rows):
                _expand_level(model.index(r, 0, idx), current_depth + 1)

        root_rows = model.rowCount(QModelIndex())
        for r in range(root_rows):
            _expand_level(model.index(r, 0, QModelIndex()), 1)

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------

    def _on_expanded_node(self, index: QModelIndex):
        key = self.get_source_key(index)
        if key:
            self._expanded_keys.add(key)

    def _on_collapsed_node(self, index: QModelIndex):
        key = self.get_source_key(index)
        if key and key in self._expanded_keys:
            self._expanded_keys.remove(key)

    def _on_clicked(self, index: QModelIndex):
        key = self.get_source_key(index)
        if key:
            self.taskSelected.emit(key)

    def _on_double_clicked(self, index: QModelIndex):
        key = self.get_source_key(index)
        if key:
            self.taskDoubleClicked.emit(key)

    def _on_context_menu_requested(self, pos):
        idx = self.indexAt(pos)
        key = self.get_source_key(idx) if idx.isValid() else None
        global_pos = self.viewport().mapToGlobal(pos)
        self.taskContextMenuRequested.emit(key, global_pos)

    # ------------------------------------------------------------------
    # Phase 1E.4 — Safe typed WBS Drag & Drop
    # ------------------------------------------------------------------

    _WBS_MIME_TYPE = "application/x-todo-bird-wbs-entity"

    def _encode_drag_key(self, key: EntityRef) -> bytes:
        return (
            f"{key.entity_type}:{int(key.entity_id)}"
        ).encode("utf-8")

    def _decode_drag_key(self, mime_data) -> Optional[EntityRef]:
        if (
            mime_data is None
            or not mime_data.hasFormat(
                self._WBS_MIME_TYPE
            )
        ):
            return None

        try:
            raw = bytes(
                mime_data.data(
                    self._WBS_MIME_TYPE
                )
            ).decode("utf-8")

            entity_type, raw_id = raw.split(
                ":",
                1,
            )

            entity_id = int(raw_id)

            if entity_type == "task":
                return EntityRef.task(entity_id)

            if entity_type == "subtask":
                return EntityRef.subtask(entity_id)

        except Exception:
            return None

        return None

    def _node_for_key(
        self,
        key: EntityRef,
    ) -> Optional[WBSNode]:
        model = self.model()

        if model is None:
            return None

        source_model = (
            model.sourceModel()
            if hasattr(model, "sourceModel")
            else model
        )

        if source_model is None:
            return None

        if not hasattr(
            source_model,
            "index_from_key",
        ):
            return None

        source_index = source_model.index_from_key(
            key,
            0,
        )

        if not source_index.isValid():
            return None

        if hasattr(
            source_model,
            "node_from_index",
        ):
            return source_model.node_from_index(
                source_index
            )

        return None

    def _root_task_key(
        self,
        key: EntityRef,
    ) -> Optional[EntityRef]:
        """
        Resolve the canonical main-task root from the current snapshot.
        """

        if key.entity_type == "task":
            return key

        node = self._node_for_key(key)

        visited = set()

        while node is not None:
            if node.key in visited:
                return None

            visited.add(node.key)

            if node.parent_key is None:
                return (
                    node.key
                    if node.key.entity_type == "task"
                    else None
                )

            if node.parent_key.entity_type == "task":
                return node.parent_key

            node = self._node_for_key(
                node.parent_key
            )

        return None

    def _key_is_descendant_of(
        self,
        candidate_key: EntityRef,
        ancestor_key: EntityRef,
    ) -> bool:
        """
        Read-only current-snapshot cycle preview.
        Service repeats authoritative validation transactionally.
        """

        node = self._node_for_key(
            candidate_key
        )

        visited = set()

        while (
            node is not None
            and node.parent_key is not None
        ):
            parent_key = node.parent_key

            if parent_key == ancestor_key:
                return True

            if parent_key in visited:
                return False

            visited.add(parent_key)

            node = self._node_for_key(
                parent_key
            )

        return False

    def _drop_zone_for_index(
        self,
        index: QModelIndex,
        pos,
    ) -> str:
        rect = self.visualRect(index)

        if rect.height() <= 0:
            return "into"

        relative = (
            float(pos.y() - rect.top())
            / float(rect.height())
        )

        if relative < 0.25:
            return "before"

        if relative > 0.75:
            return "after"

        return "into"

    def _drop_intent_is_plausible(
        self,
        source_key: EntityRef,
        target_key: EntityRef,
        zone: str,
    ) -> bool:
        """
        Fast read-only UX validation.

        Database authority repeats all safety checks inside
        WBSMutationService.drag_drop_move().
        """

        if source_key == target_key:
            return False

        source_node = self._node_for_key(
            source_key
        )
        target_node = self._node_for_key(
            target_key
        )

        if (
            source_node is None
            or target_node is None
        ):
            return False

        # Main tasks can only reorder relative to other main roots.
        if source_key.entity_type == "task":
            return (
                target_key.entity_type == "task"
                and zone in ("before", "after")
            )

        if source_key.entity_type != "subtask":
            return False

        source_root = self._root_task_key(
            source_key
        )
        target_root = self._root_task_key(
            target_key
        )

        # No cross-main-task drag.
        if (
            source_root is None
            or target_root is None
            or source_root != target_root
        ):
            return False

        if target_key.entity_type == "task":
            # A subtask may return INTO its own task only.
            return (
                zone == "into"
                and target_key == source_root
            )

        if target_key.entity_type != "subtask":
            return False

        if zone == "into":
            # Never parent under a descendant.
            if self._key_is_descendant_of(
                target_key,
                source_key,
            ):
                return False

            return True

        # before/after places source into target's sibling scope.
        proposed_parent = target_node.parent_key

        if proposed_parent is None:
            # A subtask may never become a task-root sibling.
            return False

        if proposed_parent == source_key:
            return False

        if (
            proposed_parent.entity_type == "subtask"
            and self._key_is_descendant_of(
                proposed_parent,
                source_key,
            )
        ):
            return False

        return True

    def _clear_drag_feedback(self):
        self._wbs_drag_target_key = None
        self._wbs_drag_zone = None
        self._wbs_drag_target_rect = None

        viewport = self.viewport()

        if viewport is not None:
            viewport.update()

    def startDrag(self, supportedActions):
        index = self.currentIndex()

        if not index.isValid():
            return

        source_key = self.get_source_key(
            index
        )

        if source_key is None:
            return

        mime = QMimeData()
        mime.setData(
            self._WBS_MIME_TYPE,
            self._encode_drag_key(
                source_key
            ),
        )

        drag = QDrag(self)
        drag.setMimeData(mime)

        try:
            drag.exec(Qt.MoveAction)
        finally:
            self._clear_drag_feedback()

    def dragEnterEvent(self, event):
        source_key = self._decode_drag_key(
            event.mimeData()
        )

        if source_key is None:
            event.ignore()
            return

        event.setDropAction(
            Qt.MoveAction
        )
        event.accept()

    def dragMoveEvent(self, event):
        source_key = self._decode_drag_key(
            event.mimeData()
        )

        pos = event.position().toPoint()
        target_index = self.indexAt(pos)

        if (
            source_key is None
            or not target_index.isValid()
        ):
            self._clear_drag_feedback()
            event.ignore()
            return

        target_key = self.get_source_key(
            target_index
        )

        if target_key is None:
            self._clear_drag_feedback()
            event.ignore()
            return

        zone = self._drop_zone_for_index(
            target_index,
            pos,
        )

        if not self._drop_intent_is_plausible(
            source_key,
            target_key,
            zone,
        ):
            self._clear_drag_feedback()
            event.ignore()
            return

        self._wbs_drag_target_key = (
            target_key
        )
        self._wbs_drag_zone = zone
        self._wbs_drag_target_rect = (
            self.visualRect(
                target_index
            )
        )

        self.viewport().update()

        event.setDropAction(
            Qt.MoveAction
        )
        event.accept()

    def dragLeaveEvent(self, event):
        self._clear_drag_feedback()
        event.accept()

    def dropEvent(self, event):
        source_key = self._decode_drag_key(
            event.mimeData()
        )

        target_key = (
            self._wbs_drag_target_key
        )
        zone = self._wbs_drag_zone

        valid = (
            source_key is not None
            and target_key is not None
            and zone
            in ("before", "into", "after")
            and self._drop_intent_is_plausible(
                source_key,
                target_key,
                zone,
            )
        )

        self._clear_drag_feedback()

        if not valid:
            event.ignore()
            return

        # Critical invariant:
        # DO NOT call super().dropEvent().
        # That would enter Qt's model mutation pipeline.
        self.hierarchyDropRequested.emit(
            source_key,
            target_key,
            zone,
        )

        event.setDropAction(
            Qt.MoveAction
        )
        event.accept()

    def paintEvent(self, event):
        super().paintEvent(event)

        rect = self._wbs_drag_target_rect
        zone = self._wbs_drag_zone

        if (
            rect is None
            or zone
            not in ("before", "into", "after")
        ):
            return

        painter = QPainter(
            self.viewport()
        )

        painter.setRenderHint(
            QPainter.Antialiasing,
            True,
        )

        accent = QColor(
            self._accent_color
        )

        if zone == "into":
            fill = QColor(accent)
            fill.setAlpha(34)

            painter.fillRect(
                rect.adjusted(
                    1,
                    1,
                    -1,
                    -1,
                ),
                fill,
            )

            pen = QPen(
                accent,
                1.5,
            )

            painter.setPen(pen)
            painter.drawRoundedRect(
                QRectF(
                    rect.adjusted(
                        1,
                        1,
                        -1,
                        -1,
                    )
                ),
                5.0,
                5.0,
            )

        else:
            y = (
                rect.top() + 1
                if zone == "before"
                else rect.bottom() - 1
            )

            pen = QPen(
                accent,
                2.0,
            )

            painter.setPen(pen)

            painter.drawLine(
                rect.left() + 4,
                y,
                rect.right() - 4,
                y,
            )

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        pos = event.position().toPoint()
        idx = self.indexAt(pos)

        if idx.isValid() and idx.column() == WBSItemModel.COL_WBS and event.button() == Qt.LeftButton:
            node = self.get_source_node(idx)
            if node and node.has_children:
                metrics = self._custom_service.get_density_metrics() if self._custom_service else None
                indent_px = metrics.indent_px if metrics else 20
                start_x = 8.0 + node.depth * indent_px
                click_x = pos.x()

                # Hit region for chevron is 28px wide
                if start_x - 4 <= click_x <= start_x + 24:
                    self.setExpanded(idx, not self.isExpanded(idx))
                    event.accept()
                    return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        pos = event.position().toPoint()
        idx = self.indexAt(pos)

        if idx.isValid() and idx.column() == WBSItemModel.COL_WBS and event.button() == Qt.LeftButton:
            node = self.get_source_node(idx)
            if node and node.has_children:
                metrics = self._custom_service.get_density_metrics() if self._custom_service else None
                indent_px = metrics.indent_px if metrics else 20
                start_x = 8.0 + node.depth * indent_px
                click_x = pos.x()

                # Hit region for chevron is 28px wide: preserve normal expand/collapse
                if start_x - 4 <= click_x <= start_x + 24:
                    self.setExpanded(idx, not self.isExpanded(idx))
                    event.accept()
                    return

        if idx.isValid() and event.button() == Qt.LeftButton:
            key = self.get_source_key(idx)
            if key:
                self.taskDoubleClicked.emit(key)
                event.accept()
                return

        super().mouseDoubleClickEvent(event)

    def event(self, event):
        """
        Route WBS hierarchy Tab commands before Qt focus traversal.

        QWidget normally consumes Tab / Shift+Tab to move focus between
        controls before QTreeView.keyPressEvent() receives them.

        In the WBS tree:
            Tab        -> Indent
            Shift+Tab  -> Outdent

        All other events use normal Qt handling.
        """
        if event.type() == QEvent.KeyPress:
            key = event.key()

            if key in (Qt.Key_Tab, Qt.Key_Backtab):
                cur_idx = self.currentIndex()

                if cur_idx.isValid():
                    entity_key = self.get_source_key(cur_idx)

                    if entity_key:
                        if key == Qt.Key_Backtab:
                            self.hierarchyOutdentRequested.emit(
                                entity_key
                            )
                        else:
                            self.hierarchyIndentRequested.emit(
                                entity_key
                            )

                event.accept()
                return True

        return super().event(event)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        cur_idx = self.currentIndex()

        # Phase 1E professional hierarchy keyboard editing.
        #
        # Tab       -> indent
        # Shift+Tab -> Qt.Key_Backtab -> outdent
        #
        # These commands operate only when a valid WBS row is selected.
        if key == Qt.Key_Backtab:
            if cur_idx.isValid():
                entity_key = self.get_source_key(cur_idx)
                if entity_key:
                    self.hierarchyOutdentRequested.emit(entity_key)
            event.accept()
            return

        if key == Qt.Key_Tab:
            if cur_idx.isValid():
                entity_key = self.get_source_key(cur_idx)
                if entity_key:
                    self.hierarchyIndentRequested.emit(entity_key)
            event.accept()
            return

        if key in (Qt.Key_Return, Qt.Key_Enter):
            if cur_idx.isValid():
                entity_key = self.get_source_key(cur_idx)
                if entity_key:
                    self.taskDoubleClicked.emit(entity_key)
            event.accept()
            return

        elif key == Qt.Key_Right:
            if cur_idx.isValid():
                if self.model().rowCount(cur_idx) > 0 and not self.isExpanded(cur_idx):
                    self.setExpanded(cur_idx, True)
                elif self.isExpanded(cur_idx):
                    first_child = self.model().index(0, 0, cur_idx)
                    if first_child.isValid():
                        self.setCurrentIndex(first_child)
            event.accept()
            return

        elif key == Qt.Key_Left:
            if cur_idx.isValid():
                if self.isExpanded(cur_idx):
                    self.setExpanded(cur_idx, False)
                else:
                    parent_idx = cur_idx.parent()
                    if parent_idx.isValid():
                        self.setCurrentIndex(parent_idx)
            event.accept()
            return

        super().keyPressEvent(event)
