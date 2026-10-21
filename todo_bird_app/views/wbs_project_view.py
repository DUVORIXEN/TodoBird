"""
TODO BIRD — PRODUCTION WBS PROJECT VIEW
Integrated project planning workspace hosting WBSTreeView, WBSFilterProxyModel,
WBSItemModel, modern toolbar (search, status filters, density switcher, expand levels),
empty state placeholders, and ModernMenu context interactions.
"""

from typing import Optional, Set
from PySide6.QtCore import Qt, Signal, QPoint, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QMessageBox,
    QInputDialog,
    QSizePolicy,
    QLabel,
)
from PySide6.QtGui import QKeySequence, QShortcut

try:
    import shiboken6
except Exception:
    shiboken6 = None

from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.services.wbs_service import EntityRef, WBSNode, WBSService
from todo_bird_app.services.wbs_mutation_service import WBSMutationService
from todo_bird_app.models.wbs_item_model import WBSItemModel
from todo_bird_app.models.wbs_filter_proxy_model import WBSFilterProxyModel
from todo_bird_app.views.wbs_tree_view import WBSTreeView
from todo_bird_app.services.wbs_customization_service import WBSCustomizationService
from todo_bird_app.widgets.state_panel import StatePanel
from todo_bird_app.ui.components import (
    ModernButton,
    IconButton,
    ButtonVariant,
    ButtonSize,
    SearchField,
    ModernComboBox,
    SegmentedControl,
    ModernMenu,
    EmptyState,
    ToastManager,
    ScheduleDetailsPopover,
)
from todo_bird_app.services.schedule_details_formatter import ScheduleDetailsFormatter


class WBSProjectView(QWidget):
    """
    Production WBS Project Planning Workspace.
    """

    taskOpenRequested = Signal(object)    # (EntityRef)
    taskAddRequested = Signal(object)     # (parent_key or None)
    taskDeleteRequested = Signal(object)  # (EntityRef)
    taskPinToggled = Signal(object)       # (EntityRef)
    hierarchyChanged = Signal(object)      # (EntityRef changed)

    def __init__(
        self,
        db_manager,
        settings_manager,
        project_id: Optional[int] = None,
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
    ):
        super().__init__(parent)
        self._cleaned_up = False
        self._global_typography_connected = False
        self.db_manager = db_manager
        self.settings_manager = settings_manager
        self.project_id = project_id
        self._is_dark = is_dark
        self._accent_color = accent_color

        self.custom_service = WBSCustomizationService(settings_manager)

        # Core Models & View
        self.item_model = WBSItemModel(parent=self)
        self.proxy_model = WBSFilterProxyModel(parent=self)
        self.proxy_model.setSourceModel(self.item_model)

        self.tree_view = WBSTreeView(
            custom_service=self.custom_service,
            parent=self,
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self.tree_view.setModel(self.proxy_model)

        self._init_ui()
        self._setup_shortcuts()
        self._connect_signals()

        if self.project_id is not None or self.db_manager is not None:
            self.refresh_hierarchy()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ---------------------------------------------------------------------
        # Raised WBS Workspace Panel Container
        # ---------------------------------------------------------------------
        self.panel = QFrame(self)
        self.panel.setObjectName("WBSPanelWidget")
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # ---------------------------------------------------------------------
        # 1. Modern Toolbar Container
        # ---------------------------------------------------------------------
        self.toolbar_container = QWidget(self.panel)
        self.toolbar_container.setObjectName("WBSToolbarContainer")

        # Phase 1F.5.1 — responsive toolbar authority.
        #
        # A single QHBoxLayout cannot wrap. At narrow widths Qt eventually
        # has no legal geometry for Search + Status + Density + actions,
        # which caused controls to visually collide.
        #
        # Keep the normal desktop presentation as one row, but provide a
        # second row that becomes active only when horizontal space is low.
        self.toolbar_layout = QVBoxLayout(self.toolbar_container)
        self.toolbar_layout.setContentsMargins(14, 10, 14, 10)
        self.toolbar_layout.setSpacing(6)

        self.toolbar_primary_row = QWidget(self.toolbar_container)
        self.toolbar_primary_layout = QHBoxLayout(
            self.toolbar_primary_row
        )
        self.toolbar_primary_layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar_primary_layout.setSpacing(10)

        self.toolbar_secondary_row = QWidget(self.toolbar_container)
        self.toolbar_secondary_layout = QHBoxLayout(
            self.toolbar_secondary_row
        )
        self.toolbar_secondary_layout.setContentsMargins(0, 0, 0, 0)
        self.toolbar_secondary_layout.setSpacing(10)
        self.toolbar_secondary_row.hide()

        self.toolbar_layout.addWidget(self.toolbar_primary_row)
        self.toolbar_layout.addWidget(self.toolbar_secondary_row)

        self._toolbar_compact_mode = None

        # Search Field
        self.search_field = SearchField(
            placeholder="Search WBS (Ctrl+F)...",
            parent=self,
            is_dark=self._is_dark,
            accent_color=self._accent_color,
        )
        # Phase 1F.5 — responsive width:
        # preserve ~240px desktop presentation while allowing the
        # search field to absorb or release horizontal workspace.
        self.search_field.setMinimumWidth(160)
        self.search_field.setMaximumWidth(300)
        self.search_field.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )
        self.search_field.setAccessibleName("Search work breakdown structure")
        self.search_field.setAccessibleDescription(
            "Search project tasks by task name, WBS code, or status. "
            "Keyboard shortcut: Ctrl+F."
        )
        self.search_field.setToolTip(
            "Search tasks by name, WBS code, or status (Ctrl+F)"
        )
        self.search_field.debouncedSearch.connect(self._on_search_changed)
        self.toolbar_primary_layout.addWidget(
            self.search_field,
            1,
        )

        # Status Filter Combobox
        self.status_combo = ModernComboBox(
            is_dark=self._is_dark,
            accent_color=self._accent_color,
            parent=self,
        )
        self.status_combo.setMinimumWidth(110)
        self.status_combo.setMaximumWidth(145)
        self.status_combo.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Fixed,
        )
        self.status_combo.setAccessibleName("WBS status filter")
        self.status_combo.setAccessibleDescription(
            "Filter visible WBS tasks by execution status."
        )
        self.status_combo.setToolTip(
            "Filter WBS tasks by status"
        )
        self.status_combo.addItem("All Statuses", "all")
        self.status_combo.addItem("Active Only", "active")
        self.status_combo.addItem("Planned", "planned")
        self.status_combo.addItem("In Progress", "in_progress")
        self.status_combo.addItem("Blocked", "blocked")
        self.status_combo.addItem("Completed", "completed")
        self.status_combo.addItem("Delayed", "delayed")
        self.status_combo.insertSeparator(self.status_combo.count())
        self.status_combo.addItem("Critical Path Only", "critical")
        self.status_combo.addItem("⏳ Has Float Available", "has_float")
        self.status_combo.currentIndexChanged.connect(self._on_status_filter_changed)
        self.toolbar_primary_layout.addWidget(self.status_combo)

        # Schedule Health Summary Badge
        self.schedule_health_badge = QLabel("CPM: Ready")
        self.schedule_health_badge.setObjectName("ScheduleHealthBadge")
        self.schedule_health_badge.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Fixed,
        )
        self.schedule_health_badge.setStyleSheet(
            "color: #94A3B8; background: rgba(148, 163, 184, 0.12); "
            "border: 1px solid rgba(148, 163, 184, 0.3); border-radius: 6px; padding: 2px 8px; font-weight: 600;"
        )
        self.toolbar_primary_layout.addWidget(self.schedule_health_badge)

        # Density Segmented Control
        cur_density = self.custom_service.get_preference("wbs_density", "balanced")
        density_idx = 0 if cur_density == "professional" else (2 if cur_density == "personal" else 1)
        self.density_control = SegmentedControl(
            segments=[("Prof", "professional"), ("Bal", "balanced"), ("Pers", "personal")],
            selected_index=density_idx,
            parent=self,
            is_dark=self._is_dark,
            accent_color=self._accent_color,
        )
        self.density_control.setMinimumWidth(145)
        self.density_control.setMaximumWidth(175)
        self.density_control.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Fixed,
        )
        self.density_control.setAccessibleName("WBS display density")
        self.density_control.setToolTip(
            "Choose Professional, Balanced, or Personal WBS density"
        )
        self.density_control.valueChanged.connect(self._on_density_changed)
        self.toolbar_primary_layout.addWidget(self.density_control)

        # Expand Level Buttons
        self.btn_expand_all = IconButton(
            "chevron_down",
            tooltip_text="Expand All Branches",
            parent=self,
            is_dark=self._is_dark,
            accent_color=self._accent_color,
        )
        self.btn_expand_all.setAccessibleName("Expand all WBS branches")
        self.btn_expand_all.setAccessibleDescription(
            "Expand every visible branch in the work breakdown structure."
        )
        self.btn_expand_all.clicked.connect(self.tree_view.expandAll)
        self.toolbar_primary_layout.addWidget(self.btn_expand_all)

        self.btn_collapse_all = IconButton(
            "chevron_right",
            tooltip_text="Collapse All Branches",
            parent=self,
            is_dark=self._is_dark,
            accent_color=self._accent_color,
        )
        self.btn_collapse_all.setAccessibleName("Collapse all WBS branches")
        self.btn_collapse_all.setAccessibleDescription(
            "Collapse every visible branch in the work breakdown structure."
        )
        self.btn_collapse_all.clicked.connect(self.tree_view.collapseAll)
        self.toolbar_primary_layout.addWidget(self.btn_collapse_all)

        self.toolbar_primary_layout.addStretch()

        # Baseline Management Menu Action
        self.btn_baseline = ModernButton(
            "Baseline",
            variant=ButtonVariant.SECONDARY,
            size=ButtonSize.STANDARD,
            icon_name="schedule",
            parent=self,
            is_dark=self._is_dark,
            accent_color=self._accent_color,
        )
        self.btn_baseline.setAccessibleName("Schedule Baseline Management")
        self.btn_baseline.setAccessibleDescription("Set Original Baseline or approve immutable schedule revisions.")
        self.btn_baseline.setToolTip("Schedule Approval Controls")
        self.btn_baseline.clicked.connect(self._show_baseline_menu)
        self.toolbar_primary_layout.addWidget(self.btn_baseline)

        # View in Gantt Action
        self.btn_gantt = ModernButton(
            "Gantt",
            variant=ButtonVariant.SECONDARY,
            size=ButtonSize.STANDARD,
            parent=self,
            is_dark=self._is_dark,
            accent_color=self._accent_color,
        )
        self.btn_gantt.setAccessibleName("View project in Gantt timeline")
        self.btn_gantt.setToolTip("Switch to Gantt timeline view for this project")
        self.btn_gantt.clicked.connect(self._navigate_to_gantt)
        self.toolbar_primary_layout.addWidget(self.btn_gantt)

        # Primary Add Task Action
        self.btn_add_task = ModernButton(
            "New Task",
            variant=ButtonVariant.PRIMARY,
            size=ButtonSize.STANDARD,
            icon_name="add",
            parent=self,
            is_dark=self._is_dark,
            accent_color=self._accent_color,
        )
        self.btn_add_task.setAccessibleName("Create new project task")
        self.btn_add_task.setAccessibleDescription(
            "Create a new top-level task in the selected project."
        )
        self.btn_add_task.setToolTip(
            "Create a new top-level project task"
        )
        self.btn_add_task.clicked.connect(lambda: self.taskAddRequested.emit(None))
        self.toolbar_primary_layout.addWidget(self.btn_add_task)

        # Layout geometry becomes authoritative after the current event.
        QTimer.singleShot(
            0,
            self._apply_toolbar_responsive_layout,
        )

        panel_layout.addWidget(self.toolbar_container)

        # ---------------------------------------------------------------------
        # 2. Stacked Content (Tree View, Empty State, or No Results)
        # ---------------------------------------------------------------------
        self.stack = QStackedWidget(self.panel)

        # Page 0: Tree View
        self.stack.addWidget(self.tree_view)

        # Page 1: Empty State (True empty project)
        self.empty_state = EmptyState(
            icon_name="task",
            title="No tasks in this project yet",
            description="Build your project Work Breakdown Structure by adding the first task.",
            action_label="Add First Task",
            action_callback=lambda: self.taskAddRequested.emit(None),
            parent=self,
            is_dark=self._is_dark,
            accent_color=self._accent_color,
        )
        self.stack.addWidget(self.empty_state)

        # Page 2: Filtered No Results State
        self.no_results_state = StatePanel(self)
        self.no_results_state.show_no_results(
            title="No matching WBS items",
            description="No tasks match your current search and filter settings.",
            clear_filter_callback=self.clear_all_filters,
        )
        self.stack.addWidget(self.no_results_state)

        panel_layout.addWidget(self.stack, 1)
        main_layout.addWidget(self.panel, 1)
        self._apply_panel_theme()


        # Phase 1F.8.4:
        # Typography changes alter delegate sizeHint()/font metrics.
        # Reuse the existing queued view-only refresh path so shrinking
        # 20pt -> 10pt is as safe as enlarging 10pt -> 20pt.
        try:
            from todo_bird_app.controllers.task_controller import (
                _GLOBAL_EVENT_BUS,
            )

            _GLOBAL_EVENT_BUS.typography_changed.connect(
                self.refresh_wbs_appearance
            )
            self._global_typography_connected = True
        except Exception:
            pass

    def cleanup(self):
        if getattr(self, "_cleaned_up", False):
            return
        self._cleaned_up = True
        try:
            from todo_bird_app.controllers.task_controller import (
                _GLOBAL_EVENT_BUS,
            )
            if getattr(self, "_global_typography_connected", False):
                try:
                    _GLOBAL_EVENT_BUS.typography_changed.disconnect(
                        self.refresh_wbs_appearance
                    )
                except Exception:
                    pass
                self._global_typography_connected = False
        except Exception:
            pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def deleteLater(self):
        self.cleanup()
        super().deleteLater()

    def _clear_toolbar_row(self, layout):
        """
        Remove layout items without deleting their widgets.

        This lets the same live controls move safely between the desktop
        and compact toolbar rows without recreating signals or state.
        """
        while layout.count():
            layout.takeAt(0)

    def _apply_toolbar_responsive_layout(self):
        """
        Phase 1F.5.1 responsive toolbar reflow.

        Desktop mode keeps the accepted single-row presentation.
        Compact mode uses two rows so controls never overlap or disappear.
        """
        toolbar_container = getattr(
            self,
            "toolbar_container",
            None,
        )
        if toolbar_container is None:
            return

        try:
            if (
                shiboken6 is not None
                and not shiboken6.isValid(toolbar_container)
            ):
                return
            width = int(toolbar_container.width())
            view_width = int(self.width())
            if view_width > 0:
                width = min(width, view_width)
        except RuntimeError:
            return

        # Leave reserve for measured button widths, status controls and high-DPI.
        compact = width < 900

        if self._toolbar_compact_mode is compact:
            return

        self._toolbar_compact_mode = compact

        self._clear_toolbar_row(
            self.toolbar_primary_layout
        )
        self._clear_toolbar_row(
            self.toolbar_secondary_layout
        )

        if compact:
            # Row 1 — the two filtering authorities + schedule health.
            self.search_field.setMinimumWidth(140)

            self.toolbar_primary_layout.addWidget(
                self.search_field,
                1,
            )
            self.toolbar_primary_layout.addWidget(
                self.status_combo,
                0,
            )
            self.toolbar_primary_layout.addWidget(
                self.schedule_health_badge,
                0,
            )

            # Row 2 — presentation/actions.
            self.toolbar_secondary_layout.addWidget(
                self.density_control
            )
            self.toolbar_secondary_layout.addWidget(
                self.btn_expand_all
            )
            self.toolbar_secondary_layout.addWidget(
                self.btn_collapse_all
            )
            self.toolbar_secondary_layout.addStretch(1)
            self.toolbar_secondary_layout.addWidget(
                self.btn_baseline
            )
            self.toolbar_secondary_layout.addWidget(
                self.btn_add_task
            )

            self.toolbar_secondary_row.show()

        else:
            self.search_field.setMinimumWidth(160)

            self.toolbar_primary_layout.addWidget(
                self.search_field,
                1,
            )
            self.toolbar_primary_layout.addWidget(
                self.status_combo
            )
            self.toolbar_primary_layout.addWidget(
                self.schedule_health_badge
            )
            self.toolbar_primary_layout.addWidget(
                self.density_control
            )
            self.toolbar_primary_layout.addWidget(
                self.btn_expand_all
            )
            self.toolbar_primary_layout.addWidget(
                self.btn_collapse_all
            )
            self.toolbar_primary_layout.addStretch(1)
            self.toolbar_primary_layout.addWidget(
                self.btn_baseline
            )
            self.toolbar_primary_layout.addWidget(
                self.btn_add_task
            )

            self.toolbar_secondary_row.hide()

        try:
            toolbar_container.updateGeometry()
        except RuntimeError:
            return

    def resizeEvent(self, event):
        super().resizeEvent(event)

        toolbar_container = getattr(
            self,
            "toolbar_container",
            None,
        )
        if toolbar_container is not None:
            self._apply_toolbar_responsive_layout()

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color

        self.tree_view.set_theme(is_dark, accent_color)
        self.search_field.set_theme(is_dark, accent_color)
        self.status_combo.set_theme(is_dark, accent_color)
        self.density_control.set_theme(is_dark, accent_color)
        self.btn_expand_all.set_theme(is_dark, accent_color)
        self.btn_collapse_all.set_theme(is_dark, accent_color)
        self.btn_add_task.set_theme(is_dark, accent_color)
        self.empty_state.set_theme(is_dark, accent_color)
        self._apply_panel_theme()
        self.update()

    def _apply_panel_theme(self):
        surfaces = self.custom_service.get_surface_colors(self._is_dark, self._accent_color)
        bg_panel = surfaces["bg_panel"]
        bg_toolbar = surfaces["bg_toolbar"]
        border_panel = surfaces["border_panel"]
        border_subtle = surfaces["border_subtle"]

        self.panel.setStyleSheet(f"""
            QFrame#WBSPanelWidget {{
                background-color: {bg_panel};
                border: 1px solid {border_panel};
                border-radius: 10px;
            }}
        """)
        self.toolbar_container.setStyleSheet(f"""
            QWidget#WBSToolbarContainer {{
                background-color: {bg_toolbar};
                border-bottom: 1px solid {border_subtle};
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }}
        """)

    def _setup_shortcuts(self):
        # Ctrl+F to focus search
        shortcut_search = QShortcut(QKeySequence("Ctrl+F"), self)
        shortcut_search.activated.connect(self.search_field.setFocus)

        # Ctrl+N for new task
        shortcut_new = QShortcut(QKeySequence("Ctrl+N"), self)
        shortcut_new.activated.connect(lambda: self.taskAddRequested.emit(None))

        # Ctrl+Shift+N for child task
        shortcut_child = QShortcut(QKeySequence("Ctrl+Shift+N"), self)
        shortcut_child.activated.connect(self._on_add_child_shortcut)

        # Phase 1E professional sibling reorder.
        # Alt+Up / Alt+Down intentionally avoid stealing plain arrow
        # navigation from the tree.
        shortcut_move_up = QShortcut(QKeySequence("Alt+Up"), self)
        shortcut_move_up.activated.connect(
            lambda: self._move_selected_sibling(-1)
        )

        shortcut_move_down = QShortcut(QKeySequence("Alt+Down"), self)
        shortcut_move_down.activated.connect(
            lambda: self._move_selected_sibling(+1)
        )

    def _connect_signals(self):
        self.tree_view.taskDoubleClicked.connect(self.taskOpenRequested)
        self.tree_view.taskContextMenuRequested.connect(self._show_context_menu)
        self.tree_view.hierarchyIndentRequested.connect(
            self._indent_wbs_item
        )
        self.tree_view.hierarchyOutdentRequested.connect(
            self._outdent_wbs_item
        )
        self.tree_view.hierarchyDropRequested.connect(
            self._on_wbs_drop_requested
        )

    # -------------------------------------------------------------------------
    # Data Loading & Persistence
    # -------------------------------------------------------------------------

    def set_project(self, project_id: Optional[int]):
        """Switches active project and loads hierarchy."""
        self.project_id = project_id
        self.refresh_hierarchy()

    def _navigate_to_gantt(self):
        try:
            window = self.window()
            if hasattr(window, "navigation_controller"):
                window.navigation_controller.set_active_section("gantt", self.project_id)
        except Exception as e:
            logger.warning(f"Failed to navigate to Gantt: {e}")

    def refresh_hierarchy(self):
        """Reloads snapshot from database while preserving expansion and selection."""
        if not self.db_manager:
            return

        # 1. Save state
        expanded_keys = self.tree_view.save_expansion_state()
        selected_key = self.tree_view.get_selected_key()

        # 2. Load via WBSService
        snap = WBSService.build_project_hierarchy(
            self.db_manager,
            project_id=self.project_id,
        )
        # Supply the canonical DB manager so the model precomputes the
        # O(n) rollup cache during normal application refresh.
        self.item_model.set_snapshot(
            snap,
            db_manager=self.db_manager,
        )

        # 3. Handle Empty State vs Tree View vs Filtered No Results
        self._update_wbs_view_state()
        self._update_schedule_health_summary()
        if snap.total_nodes > 0:
            # 4. Restore state
            if expanded_keys:
                self.tree_view.restore_expansion_state(expanded_keys)
            else:
                # Default expand level 1 (roots)
                self.tree_view.expand_to_level(1)

            if selected_key:
                self.tree_view.select_key(selected_key)

    def _show_baseline_menu(self):
        menu = ModernMenu(parent=self, is_dark=self._is_dark, accent_color=self._accent_color)
        summary = self.item_model.get_project_variance_summary() if self.item_model else None
        has_baseline = bool(summary and summary.has_baseline and summary.tasks_baselined > 0)
        if self.db_manager and self.project_id is not None:
            try:
                from todo_bird_app.services.schedule_version_service import ScheduleVersionService
                has_baseline = has_baseline or ScheduleVersionService.has_original_baseline(
                    self.db_manager,
                    self.project_id,
                    include_legacy=True,
                )
            except Exception:
                pass

        if has_baseline:
            act_rev = menu.addAction(" Create Approved Revision...")
            act_rev.triggered.connect(self.create_approved_revision_action)
        else:
            act_set = menu.addAction("Set Original Baseline")
            act_set.triggered.connect(lambda: self.set_baseline_action(confirmed=True))

        menu.exec(self.btn_baseline.mapToGlobal(QPoint(0, self.btn_baseline.height() + 4)))

    def create_approved_revision_action(self):
        if not self.db_manager or self.project_id is None:
            return

        from todo_bird_app.services.schedule_version_service import ScheduleVersionService
        if not ScheduleVersionService.has_original_baseline(self.db_manager, self.project_id, include_legacy=True):
            QMessageBox.information(
                self,
                "Original Baseline Required",
                "Set Original Baseline before approving schedule revisions.",
            )
            return

        default_name = "Revision"
        try:
            versions = self.db_manager.get_schedule_versions_for_project(self.project_id)
            rev_count = sum(1 for v in versions if not v.get("is_original_baseline"))
            default_name = f"Revision {rev_count + 1}"
        except Exception:
            pass

        revision_name, ok = QInputDialog.getText(
            self,
            "Approve Current Forecast",
            "Revision Name:",
            text=default_name,
        )
        if not ok:
            return
        revision_name = revision_name.strip() or default_name
        from datetime import datetime
        timestamp = datetime.now().isoformat(timespec="seconds")
        reply = QMessageBox.question(
            self,
            "Create Approved Revision",
            "Create immutable Approved Revision?\n\n"
            f"Name: {revision_name}\n"
            f"Approval timestamp: {timestamp}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        cpm_res = getattr(self.item_model, "cpm_result", None)
        cpm_nodes = getattr(cpm_res, "nodes", None) if cpm_res else None
        v_id = ScheduleVersionService.create_approved_revision(
            self.db_manager,
            self.project_id,
            name=revision_name,
            cpm_results=cpm_nodes,
            approved_at=timestamp,
        )
        if v_id:
            self.refresh_hierarchy()
            ToastManager.show_toast(self, "Approved Schedule Revision created.", is_dark=self._is_dark)

    def set_baseline_action(self, confirmed: bool = False):
        if not self.db_manager or self.project_id is None:
            return

        summary = self.item_model.get_project_variance_summary() if self.item_model else None
        has_baseline = bool(summary and summary.has_baseline and summary.tasks_baselined > 0)
        from todo_bird_app.services.schedule_version_service import ScheduleVersionService
        has_baseline = has_baseline or ScheduleVersionService.has_original_baseline(
            self.db_manager,
            self.project_id,
            include_legacy=True,
        )

        if has_baseline:
            QMessageBox.information(
                self,
                "Original Baseline Frozen",
                "Original Baseline already exists and cannot be overwritten.\n\n"
                "Use Create Approved Revision for the current forecast.",
            )
            return

        cpm_res = getattr(self.item_model, "cpm_result", None)
        cpm_nodes = getattr(cpm_res, "nodes", None) if cpm_res else None
        v_id = ScheduleVersionService.create_original_baseline(
            self.db_manager,
            self.project_id,
            name="Original Baseline",
            cpm_results=cpm_nodes,
        )
        if v_id:
            self.refresh_hierarchy()
            ToastManager.show_toast(self, "Original Baseline saved.", is_dark=self._is_dark)

    def clear_baseline_action(self, confirmed: bool = False):
        if not self.db_manager or self.project_id is None:
            return

        QMessageBox.warning(
            self,
            "Original Baseline Frozen",
            "Original Baseline cannot be cleared in Phase 2E.\n\n"
            "This removes historical schedule reference.",
        )

    def _update_schedule_health_summary(self):
        if not hasattr(self, "schedule_health_badge") or not self.schedule_health_badge:
            return

        cpm_result = getattr(self.item_model, "cpm_result", None)
        baseline_summary = getattr(self.item_model, "get_project_variance_summary", lambda: None)()
        b_suffix = ""
        b_tip = ""
        if baseline_summary and baseline_summary.has_baseline and baseline_summary.tasks_baselined > 0:
            if baseline_summary.tasks_behind > 0:
                b_suffix = f" • {baseline_summary.tasks_behind} behind"
            else:
                b_suffix = " • On Baseline"
            b_tip = (
                f"<br/><br/><b> {baseline_summary.baseline_name or 'Baseline 1'}</b><br/>"
                f"• Baselined Tasks: {baseline_summary.tasks_baselined} / {baseline_summary.total_tasks}<br/>"
                f"• Ahead: {baseline_summary.tasks_ahead} | On Baseline: {baseline_summary.tasks_on_baseline} | Behind: {baseline_summary.tasks_behind}<br/>"
                f"• Critical Tasks Behind: {baseline_summary.critical_tasks_behind}"
            )

        if cpm_result is None or cpm_result.total_tasks == 0:
            self.schedule_health_badge.setText(f"CPM: Ready{b_suffix}")
            self.schedule_health_badge.setStyleSheet(
                "color: #94A3B8; background: rgba(148, 163, 184, 0.12); "
                "border: 1px solid rgba(148, 163, 184, 0.3); border-radius: 6px; padding: 2px 8px; font-weight: 600;"
            )
            self.schedule_health_badge.setToolTip(f"No tasks to schedule.{b_tip}")
            return

        crit_count = len(cpm_result.critical_task_ids)
        warning_count = len(cpm_result.diagnostics)
        has_cycles = cpm_result.has_cycles
        schedulable_count = cpm_result.schedulable_tasks

        if has_cycles:
            self.schedule_health_badge.setStyleSheet(
                "color: #EF4444; background: rgba(239, 68, 68, 0.15); "
                "border: 1px solid #EF4444; border-radius: 6px; padding: 2px 8px; font-weight: 700;"
            )
            self.schedule_health_badge.setToolTip(
                f"Schedule Blocked: Dependency cycle detected involving {len(cpm_result.cycle_task_ids)} task(s).{b_tip}"
            )
            self.schedule_health_badge.setText("CPM: Blocked")
            self.schedule_health_badge.setAccessibleName("Schedule analysis blocked")
            self.schedule_health_badge.setAccessibleDescription("Dependency cycle detected. Cannot compute critical path.")
        elif warning_count > 0 or schedulable_count < cpm_result.total_tasks:
            self.schedule_health_badge.setStyleSheet(
                "color: #F59E0B; background: rgba(245, 158, 11, 0.15); "
                "border: 1px solid #F59E0B; border-radius: 6px; padding: 2px 8px; font-weight: 600;"
            )
            diag_msgs = "<br/>• ".join([d.message for d in cpm_result.diagnostics[:5]])
            self.schedule_health_badge.setToolTip(
                f"<b>Schedule Warnings ({warning_count})</b><br/>• {diag_msgs}{b_tip}"
            )
            self.schedule_health_badge.setText(f"CPM: Attention ({crit_count} crit • {warning_count} warn)")
            self.schedule_health_badge.setAccessibleName("Schedule attention needed")
            self.schedule_health_badge.setAccessibleDescription(f"{crit_count} critical tasks and {warning_count} scheduling warnings.")
        else:
            self.schedule_health_badge.setText(f"CPM: Healthy ({crit_count} crit)")
            self.schedule_health_badge.setStyleSheet(
                "border: 1px solid #10B981; border-radius: 6px; padding: 2px 8px; font-weight: 600;"
            )
            self.schedule_health_badge.setToolTip(
                f"Schedule Healthy: {crit_count} critical tasks on {len(cpm_result.critical_paths)} critical path(s). All tasks schedulable.{b_tip}"
            )
            self.schedule_health_badge.setAccessibleName("Schedule healthy")
            self.schedule_health_badge.setAccessibleDescription(f"Schedule healthy. {crit_count} critical tasks.")

    def _update_wbs_view_state(self):
        if not self.item_model or self.item_model.rowCount() == 0:
            self.stack.setCurrentIndex(1)
        elif self.proxy_model.rowCount() == 0:
            self.stack.setCurrentIndex(2)
        else:
            self.stack.setCurrentIndex(0)
        self._update_schedule_health_summary()

    def clear_all_filters(self):
        self.search_field.clear()
        self.status_combo.setCurrentIndex(0)
        self.proxy_model.set_search_query("")
        self.proxy_model.set_status_filter("all")
        self._update_wbs_view_state()

    # -------------------------------------------------------------------------
    # UI Actions & Context Menu
    # -------------------------------------------------------------------------

    def _on_search_changed(self, query: str):
        self.proxy_model.set_search_query(query)
        self._update_wbs_view_state()

    def _on_status_filter_changed(self, index: int):
        status_val = self.status_combo.currentData() or "all"
        self.proxy_model.set_status_filter(str(status_val))
        self._update_wbs_view_state()

    def _on_density_changed(self, index: int, label: str, data: any):
        self.custom_service.set_preference("wbs_density", str(data))
        self.refresh_wbs_appearance()

    # -------------------------------------------------------------------------
    # Parent rollup preference wiring — Phase 1C S3.3.1 (no rollup calc here)
    # -------------------------------------------------------------------------
    def refresh_wbs_appearance(self):
        """
        Refresh WBS presentation without emitting structural model signals.

        Phase 1E crash repair:
        density/customization changes affect delegate paint/sizeHint only.
        Emitting QAbstractItemModel.layoutChanged for this is unsafe when the
        model is behind a proxy and the tree owns live persistent/current
        indexes.

        Defer the visual relayout until the current control event completes.
        """
        if getattr(self, "_cleaned_up", False):
            return

        self._apply_panel_theme()

        # Coalesce rapid preference changes into one queued visual refresh.
        if getattr(self, "_wbs_appearance_refresh_pending", False):
            return

        self._wbs_appearance_refresh_pending = True
        QTimer.singleShot(0, self._apply_wbs_appearance_refresh)

    def _apply_wbs_appearance_refresh(self):
        """
        View-only density/customization refresh.

        No model reset/layoutChanged and no hierarchy/DB mutation.
        """
        if getattr(self, "_cleaned_up", False):
            return

        self._wbs_appearance_refresh_pending = False

        tree = getattr(self, "tree_view", None)
        if tree is None:
            return

        try:
            # Delegate sizeHint() reads WBSCustomizationService dynamically.
            # Recalculate visible row geometry from those new metrics.
            tree.scheduleDelayedItemsLayout()
            tree.doItemsLayout()
            tree.updateGeometry()
            tree.apply_column_visibility()

            viewport = tree.viewport()
            if viewport is not None:
                viewport.update()

            header = tree.header()
            if header is not None:
                header.updateGeometry()
                header.viewport().update()

            self._update_schedule_health_summary()

        except RuntimeError:
            # Widget may be in Qt destruction during shutdown/navigation.
            # Never touch an already-deleted C++ object.
            return

    def on_wbs_preferences_changed(self):
        """Slot for WBSSettingsWidget.preferencesChanged → live preview.

        Wire externally as:
            settings_widget.preferencesChanged.connect(project_view.on_wbs_preferences_changed)
        Keeps toolbar/modern controls in sync with settings widget toggles.
        """
        self.refresh_wbs_appearance()

    def connect_settings_widget(self, widget):
        """Convenience: wire a WBSSettingsWidget's preferencesChanged to this view."""
        try:
            widget.preferencesChanged.connect(self.on_wbs_preferences_changed)
        except Exception:
            pass

    def _on_add_child_shortcut(self):
        selected_key = self.tree_view.get_selected_key()
        if selected_key:
            self.taskAddRequested.emit(selected_key)

    def _hierarchy_mutation_feedback(
        self,
        result,
        key: EntityRef,
        action_name: str,
    ) -> bool:
        """
        Common UI completion path for hierarchy mutations.

        Successful structural edits:
        DB truth -> WBS snapshot rebuild -> selection restore ->
        canonical hierarchyChanged signal -> Gantt refresh path.
        """

        if not result.success:
            if (
                result.reason_code
                == WBSMutationService.ERR_ALREADY_BOUNDARY
            ):
                # Boundary is a normal WBS editing condition.
                return False

            if (
                result.reason_code
                == WBSMutationService.ERR_TASK_PARENT_FORBIDDEN
            ):
                # Main tasks intentionally remain WBS roots.
                return False

            QMessageBox.warning(
                self,
                f"Unable to {action_name}",
                result.message
                or f"This WBS item cannot be {action_name.lower()}ed.",
            )
            return False

        # If the new parent is a subtask, explicitly expand it so the
        # successfully moved selected row remains visible.
        parent_to_expand = result.parent_key

        self.refresh_hierarchy()

        if (
            parent_to_expand is not None
            and getattr(
                parent_to_expand,
                "entity_type",
                None,
            ) == "subtask"
        ):
            try:
                self.tree_view.expand_key(
                    parent_to_expand
                )
            except Exception:
                # Some older WBSTreeView builds expose only index-based
                # expansion. Resolve safely through the model/proxy.
                try:
                    source_idx = self.item_model.index_from_key(
                        parent_to_expand,
                        0,
                    )
                    if source_idx.isValid():
                        proxy_idx = self.proxy_model.mapFromSource(
                            source_idx
                        )
                        if proxy_idx.isValid():
                            self.tree_view.setExpanded(
                                proxy_idx,
                                True,
                            )
                except Exception:
                    pass

        try:
            self.tree_view.select_key(key)
        except Exception:
            pass

        self.hierarchyChanged.emit(key)
        return True

    def _indent_wbs_item(self, key: EntityRef):
        if key is None:
            return

        result = WBSMutationService.indent(
            self.db_manager,
            key,
        )

        self._hierarchy_mutation_feedback(
            result,
            key,
            "Indent",
        )

    def _outdent_wbs_item(self, key: EntityRef):
        if key is None:
            return

        result = WBSMutationService.outdent(
            self.db_manager,
            key,
        )

        self._hierarchy_mutation_feedback(
            result,
            key,
            "Outdent",
        )

    def _on_wbs_drop_requested(
        self,
        source_key: EntityRef,
        target_key: EntityRef,
        zone: str,
    ):
        """
        Phase 1E.4 typed drop command.

        Tree supplies intent only.
        WBSMutationService owns all persistent mutation.
        """

        result = WBSMutationService.drag_drop_move(
            self.db_manager,
            source_key,
            target_key,
            zone,
        )

        self._hierarchy_mutation_feedback(
            result,
            source_key,
            "Move",
        )

    def _move_selected_sibling(self, direction: int):
        key = self.tree_view.get_selected_key()
        if key is None:
            return
        self._move_wbs_sibling(key, direction)

    def _move_wbs_sibling(
        self,
        key: EntityRef,
        direction: int,
    ):
        """
        Phase 1E sibling-order UI command.

        Persistent mutation is delegated exclusively to
        WBSMutationService. This view never writes DB hierarchy fields.
        """

        if key is None:
            return

        if direction < 0:
            result = WBSMutationService.move_up(
                self.db_manager,
                key,
            )
            direction_text = "up"
        else:
            result = WBSMutationService.move_down(
                self.db_manager,
                key,
            )
            direction_text = "down"

        if not result.success:
            if (
                result.reason_code
                == WBSMutationService.ERR_ALREADY_BOUNDARY
            ):
                # Boundary is normal UX, not an application error.
                return

            QMessageBox.warning(
                self,
                "Unable to Reorder",
                result.message
                or "This WBS item cannot be moved.",
            )
            return

        # Rebuild from canonical DB truth.
        # refresh_hierarchy() already preserves expansion + selection.
        self.refresh_hierarchy()

        # Notify the owning ProjectsView / TaskController path so every
        # production consumer, especially Gantt, can refresh.
        self.hierarchyChanged.emit(key)

        # Keep changed row selected after proxy/model reset.
        try:
            self.tree_view.select_key(key)
        except Exception:
            pass

    def _show_context_menu(self, key: Optional[EntityRef], pos: QPoint):
        menu = ModernMenu("Task Actions", parent=self, is_dark=self._is_dark, accent_color=self._accent_color)

        if key:
            can_move_up = False
            can_move_down = False
            can_indent = False
            can_outdent = False

            if self.item_model:
                source_idx = self.item_model.index_from_key(key, 0)
                if source_idx.isValid():
                    row = source_idx.row()
                    parent_idx = source_idx.parent()
                    total_siblings = self.item_model.rowCount(parent_idx)

                    can_move_up = (row > 0)
                    can_move_down = (row < total_siblings - 1)

                    if key.entity_type == "subtask":
                        can_indent = (row > 0)
                        can_outdent = parent_idx.isValid() and (parent_idx.data(WBSItemModel.EntityTypeRole) == "subtask")

            menu.add_action_item("Open Task", lambda: self.taskOpenRequested.emit(key), icon_name="task", shortcut="Enter")
            menu.add_action_item("Copy Schedule Details", lambda: self._copy_schedule_details(key), icon_name="copy", shortcut="Ctrl+C")
            menu.add_action_item("View Schedule Details...", lambda: self._view_schedule_details(key, pos), icon_name="info")
            menu.add_action_item("Add Child Task", lambda: self.taskAddRequested.emit(key), icon_name="add", shortcut="Ctrl+Shift+N")
            menu.add_action_item("Toggle Pin", lambda: self.taskPinToggled.emit(key), icon_name="pin")
            menu.addSeparator()

            # Phase 1E hierarchy editing with boundary gating.
            menu.add_action_item(
                "Indent",
                lambda: self._indent_wbs_item(key),
                icon_name="chevron_right",
                shortcut="Tab",
                enabled=can_indent,
            )
            menu.add_action_item(
                "Outdent",
                lambda: self._outdent_wbs_item(key),
                icon_name="chevron_left",
                shortcut="Shift+Tab",
                enabled=can_outdent,
            )

            menu.addSeparator()

            # Phase 1E structural ordering with boundary gating.
            menu.add_action_item(
                "Move Up",
                lambda: self._move_wbs_sibling(key, -1),
                icon_name="chevron_up",
                shortcut="Alt+Up",
                enabled=can_move_up,
            )
            menu.add_action_item(
                "Move Down",
                lambda: self._move_wbs_sibling(key, +1),
                icon_name="chevron_down",
                shortcut="Alt+Down",
                enabled=can_move_down,
            )

            menu.addSeparator()

            proxy_idx = self.tree_view.currentIndex()
            if proxy_idx.isValid():
                is_exp = self.tree_view.isExpanded(proxy_idx)
                if is_exp:
                    menu.add_action_item("Collapse Branch", lambda: self.tree_view.setExpanded(proxy_idx, False), icon_name="chevron_right")
                else:
                    menu.add_action_item("Expand Branch", lambda: self.tree_view.setExpanded(proxy_idx, True), icon_name="chevron_down")

            menu.addSeparator()
            menu.add_action_item("Delete Task", lambda: self._confirm_delete(key), icon_name="trash", shortcut="Del")
        else:
            menu.add_action_item("New Root Task", lambda: self.taskAddRequested.emit(None), icon_name="add", shortcut="Ctrl+N")
            menu.add_action_item("Expand All", self.tree_view.expandAll, icon_name="chevron_down")
            menu.add_action_item("Collapse All", self.tree_view.collapseAll, icon_name="chevron_right")

        menu.exec(pos)

    def _confirm_delete(self, key: EntityRef):
        confirm = self.settings_manager.get("confirm_delete_task", True)
        if confirm:
            reply = QMessageBox.question(
                self,
                "Delete Task",
                "Are you sure you want to delete this task and its hierarchy subtree?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        self.taskDeleteRequested.emit(key)

    def _copy_schedule_details(self, key: EntityRef):
        if not self.item_model or not key:
            return
        entity = self._schedule_details_entity_for_key(key)
        if not entity:
            return
        proj_name = self._schedule_details_project_name()
        model = ScheduleDetailsFormatter.build_from_entity(entity, project_name=proj_name, db_manager=self.db_manager)
        plain_text = ScheduleDetailsFormatter.format_plain_text(model)
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(plain_text)
        from todo_bird_app.widgets.toast_banner import ToastBanner
        ToastBanner.show_message(self, "Schedule details copied to clipboard!", "success")

    def _view_schedule_details(self, key: EntityRef, pos: QPoint):
        if not self.item_model or not key:
            return
        entity = self._schedule_details_entity_for_key(key)
        if not entity:
            return
        proj_name = self._schedule_details_project_name()
        popover = ScheduleDetailsPopover(
            entity,
            parent=self,
            project_name=proj_name,
            db_manager=self.db_manager,
            is_dark=self._is_dark,
            accent_color=self._accent_color,
        )
        popover.popup_at_point(pos)

    def _schedule_details_project_name(self) -> str:
        if self.project_id is None:
            return ""
        if self.db_manager is not None:
            try:
                project = self.db_manager.get_project(int(self.project_id))
                if isinstance(project, dict):
                    return str(project.get("name") or f"Project #{self.project_id}")
                name = getattr(project, "name", None)
                if name:
                    return str(name)
            except Exception:
                pass
        return f"Project #{self.project_id}"

    def _schedule_details_entity_for_key(self, key: EntityRef):
        snapshot = getattr(self.item_model, "snapshot", None)
        if snapshot is None:
            snapshot = getattr(self.item_model, "_snapshot", None)
        if snapshot is None:
            return None

        node = snapshot.nodes_by_key.get(key)
        if node is None:
            return None

        try:
            from todo_bird_app.services.gantt_wbs_adapter import GanttWBSAdapter
            from todo_bird_app.services.wbs_rollup_service import WBSRollupService

            payloads = WBSRollupService._bulk_fetch_payloads(
                self.db_manager,
                list(snapshot.nodes_by_key.keys()),
                project_id=snapshot.project_id,
            )
            rows = GanttWBSAdapter.build_rows(
                snapshot,
                payloads,
                rollups=getattr(self.item_model, "_rollups", None),
                cpm_result=getattr(self.item_model, "cpm_result", None),
            )
            for row in rows:
                if row.key == key:
                    return row
        except Exception:
            pass

        return node
