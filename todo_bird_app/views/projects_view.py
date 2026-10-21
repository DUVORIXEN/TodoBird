"""
TODO BIRD — PROJECTS VIEW
Organize tasks into structured projects with dual view modes:
- Classic List View with Pinned Priorities Strip
- Production WBS Hierarchy View (QAbstractItemModel + QTreeView + QStyledItemDelegate)
"""

from typing import Optional
from PySide6.QtWidgets import (
    QInputDialog,
    QMessageBox,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QWidget,
    QFrame, QListWidget, QListWidgetItem, QStackedWidget, QSizePolicy,
    QMenu
)
from PySide6.QtCore import Qt

from todo_bird_app.views.base_view import BaseView
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.widgets.task_item_widget import TaskItemWidget
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.subtask_dialog import SubtaskDialog
from todo_bird_app.widgets.pinned_priorities_widget import PinnedPrioritiesWidget
from todo_bird_app.widgets.project_dialog import ProjectDialog
from todo_bird_app.widgets.toast_banner import ToastBanner
from todo_bird_app.widgets.state_panel import StatePanel
from todo_bird_app.models.project import Project
from todo_bird_app.models.task import Task
from todo_bird_app.views.wbs_project_view import WBSProjectView
from todo_bird_app.ui.components.segmented_control import SegmentedControl
from todo_bird_app.services.wbs_service import EntityRef
from todo_bird_app.services.wbs_mutation_service import WBSMutationService
from todo_bird_app.utils.qt_cleanup import clear_layout


class ProjectsView(BaseView):
    """
    Projects View — Organize tasks into custom projects with custom color accents
    and full WBS planning hierarchy support.
    """

    def __init__(self, db_manager, settings_manager, parent=None):
        super().__init__(db_manager, settings_manager, title="Projects", subtitle="Organize tasks into structured projects and WBS plans", parent=parent, typography_area="tasklist")
        self.task_controller = TaskController(db_manager)
        self._connect_task_controller_signal("tasks_changed", self.refresh_data)
        self._connect_task_controller_signal("projects_changed", self.refresh_data)
        self.selected_project_id = 1
        self._init_ui()
        self.refresh_data()

    def _init_ui(self):
        container_layout = QHBoxLayout()
        container_layout.setSpacing(16)

        # ---------------------------------------------------------------------
        # Left panel: Project list
        # ---------------------------------------------------------------------
        self.left_panel = QFrame()
        left_panel = self.left_panel
        left_panel.setObjectName("CardWidget")

        # Phase 1F.5:
        # 240px remains the preferred desktop width, but the project
        # navigator may contract on smaller windows.
        left_panel.setMinimumWidth(180)
        left_panel.setMaximumWidth(240)
        left_panel.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Expanding,
        )
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)

        proj_header = QHBoxLayout()
        proj_title = QLabel("Projects")
        proj_title.setStyleSheet(
            "color: inherit; font-weight: 700;"
        )
        proj_title.setProperty(
            "_todo_bird_font_delta_pt",
            4,
        )
        proj_title.setProperty(
            "_todo_bird_font_role_weight",
            "bold",
        )
        add_proj_btn = QPushButton("+ New")
        add_proj_btn.setCursor(Qt.PointingHandCursor)
        add_proj_btn.setAccessibleName("Create new project")
        add_proj_btn.setAccessibleDescription(
            "Create and configure a new project."
        )
        add_proj_btn.setToolTip("Create a new project")
        add_proj_btn.clicked.connect(self.open_new_project_dialog)

        proj_header.addWidget(proj_title)
        proj_header.addStretch()
        proj_header.addWidget(add_proj_btn)
        left_layout.addLayout(proj_header)

        self.project_list = QListWidget()
        self.project_list.setAccessibleName("Project list")
        self.project_list.setAccessibleDescription(
            "Select the project whose tasks and WBS should be displayed."
        )
        self.project_list.setFrameShape(QFrame.NoFrame)
        self.project_list.setStyleSheet("background: transparent;")
        self.project_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.project_list.itemClicked.connect(self.on_project_selected)
        self.project_list.customContextMenuRequested.connect(
            self.open_project_list_context_menu
        )
        left_layout.addWidget(self.project_list)

        container_layout.addWidget(left_panel)

        # ---------------------------------------------------------------------
        # Right panel: Mode Switcher + Stacked Views (List vs WBS)
        # ---------------------------------------------------------------------
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # Top Bar: Project Name + View Mode Switcher
        top_bar = QHBoxLayout()
        self.proj_name_label = QLabel("Inbox")
        self.proj_name_label.setAccessibleName("Selected project")
        self.proj_name_label.setAccessibleDescription(
            "Name of the project currently displayed."
        )
        self.proj_name_label.setStyleSheet(
            "color: inherit; font-weight: 700;"
        )
        self.proj_name_label.setProperty(
            "_todo_bird_font_delta_pt",
            6,
        )
        self.proj_name_label.setProperty(
            "_todo_bird_font_role_weight",
            "bold",
        )
        self.proj_name_label.setSizePolicy(
            QSizePolicy.Ignored,
            QSizePolicy.Preferred,
        )
        self.proj_name_label.setMinimumWidth(80)
        self.proj_name_label.setContextMenuPolicy(Qt.CustomContextMenu)
        self.proj_name_label.customContextMenuRequested.connect(
            self.open_selected_project_context_menu
        )
        self.proj_name_label.setToolTip("Right-click to rename or edit this project")
        top_bar.addWidget(
            self.proj_name_label,
            1,
        )
        top_bar.addStretch()

        theme_mode = str(self.settings_manager.get("theme", "dark")).lower()
        is_dark = (theme_mode == "dark")
        accent = self.settings_manager.get("accent_color", "#3584E4")
        self.view_mode_control = SegmentedControl(
            segments=[("WBS Hierarchy", "wbs"), ("Task List", "list")],
            selected_index=0,
            parent=self,
            is_dark=is_dark,
            accent_color=accent,
        )
        self.view_mode_control.setMinimumWidth(190)
        self.view_mode_control.setMaximumWidth(240)
        self.view_mode_control.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Fixed,
        )
        self.view_mode_control.setAccessibleName("Project view mode")
        self.view_mode_control.setToolTip(
            "Switch between WBS Hierarchy and Task List"
        )
        self.view_mode_control.valueChanged.connect(self._on_view_mode_changed)
        top_bar.addWidget(self.view_mode_control)
        right_layout.addLayout(top_bar)

        # Stack for List View vs WBS View
        self.view_stack = QStackedWidget(self)

        # Page 0: WBS Hierarchy View
        self.wbs_view = WBSProjectView(
            db_manager=self.db_manager,
            settings_manager=self.settings_manager,
            project_id=self.selected_project_id,
            parent=self,
            is_dark=is_dark,
            accent_color=accent,
        )
        self.wbs_view.taskOpenRequested.connect(self._on_wbs_open_task)
        self.wbs_view.taskAddRequested.connect(self._on_wbs_add_task)
        self.wbs_view.taskDeleteRequested.connect(self._on_wbs_delete_task)
        self.wbs_view.taskPinToggled.connect(self._on_wbs_pin_toggle)
        self.wbs_view.hierarchyChanged.connect(
            self._on_wbs_hierarchy_changed
        )
        self.view_stack.addWidget(self.wbs_view)

        # Page 1: Classic List View with Pinned Strip
        list_container = QWidget()
        list_vbox = QVBoxLayout(list_container)
        list_vbox.setContentsMargins(0, 0, 0, 0)
        list_vbox.setSpacing(8)

        self.pinned_priorities = PinnedPrioritiesWidget(self.db_manager, parent=self)
        self.pinned_priorities.edit_requested.connect(self.open_edit_dialog)
        self.pinned_priorities.changed.connect(self.refresh_data)
        list_vbox.addWidget(self.pinned_priorities)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        self.task_container = QWidget()
        self.task_list_layout = QVBoxLayout(self.task_container)
        self.task_list_layout.setContentsMargins(0, 8, 0, 8)
        self.task_list_layout.setSpacing(8)

        scroll.setWidget(self.task_container)
        list_vbox.addWidget(scroll, 1)
        self.view_stack.addWidget(list_container)

        right_layout.addWidget(self.view_stack, 1)
        container_layout.addWidget(right_panel, 1)
        self.main_layout.addLayout(container_layout)

    def _on_view_mode_changed(self, index: int, label: str, data: any):
        if data == "wbs":
            self.view_stack.setCurrentIndex(0)
            self.wbs_view.set_project(self.selected_project_id)
        else:
            self.view_stack.setCurrentIndex(1)
            self.load_project_tasks()

    def set_project_scope(self, project_id: Optional[int] = None, mode: Optional[str] = "wbs"):
        """
        Called when navigating to ProjectsView from Dashboard or external triggers.
        Sets the active project and view mode ('wbs' or 'list').
        """
        if project_id is not None:
            self.selected_project_id = project_id

        if mode == "wbs":
            if hasattr(self, "view_mode_control"):
                self.view_mode_control.set_selected_index(0, notify=False)
            if hasattr(self, "view_stack"):
                self.view_stack.setCurrentIndex(0)
            if hasattr(self, "wbs_view") and self.selected_project_id is not None:
                self.wbs_view.set_project(self.selected_project_id)
        elif mode == "list":
            if hasattr(self, "view_mode_control"):
                self.view_mode_control.set_selected_index(1, notify=False)
            if hasattr(self, "view_stack"):
                self.view_stack.setCurrentIndex(1)
            self.load_project_tasks()

    def refresh_project_schedule(self, project_id: Optional[int] = None):
        """
        Single canonical project schedule refresh route.
        Reloads project tasks from DB, recalculates CPM schedule via WBS model,
        and refreshes WBS & Gantt views.
        """
        pid = project_id if project_id is not None else self.selected_project_id
        if hasattr(self, "wbs_view") and hasattr(self.wbs_view, "model") and self.wbs_view.model():
            self.wbs_view.model().rebuild_rollups()
            if hasattr(self.wbs_view, "tree_view") and self.wbs_view.tree_view and hasattr(self.wbs_view.tree_view, "viewport"):
                vp = self.wbs_view.tree_view.viewport()
                if vp and hasattr(vp, "update"):
                    vp.update()
        if hasattr(self, "gantt_view") and self.gantt_view:
            if hasattr(self.gantt_view, "refresh_project_schedule"):
                self.gantt_view.refresh_project_schedule(pid)
            else:
                self.gantt_view.refresh_data()
        self.refresh_data()

    def refresh_data(self):
        super().refresh_data()
        if hasattr(self, "pinned_priorities"):
            self.pinned_priorities.refresh_data()

        # Refresh projects list
        self.project_list.clear()
        projects = self.task_controller.get_all_projects()

        if not projects:
            self.selected_project_id = None
            self.proj_name_label.setText("No Projects")
            if hasattr(self, "wbs_view"):
                self.wbs_view.set_project(None)
            self.load_project_tasks()
            return

        # Ensure valid selected_project_id
        valid_ids = [p.id for p in projects]
        if self.selected_project_id not in valid_ids:
            self.selected_project_id = valid_ids[0]

        selected_item = None
        for proj in projects:
            tasks_cnt = len(self.task_controller.get_project_tasks(proj.id))
            item = QListWidgetItem(f"{proj.name} ({tasks_cnt})")
            item.setData(Qt.UserRole, proj.id)
            self.project_list.addItem(item)
            if proj.id == self.selected_project_id:
                selected_item = item

        if selected_item:
            self.project_list.setCurrentItem(selected_item)

        # Update Project Title
        proj_map = {p.id: p for p in projects}
        current_proj = proj_map.get(self.selected_project_id)
        if current_proj:
            self.proj_name_label.setText(current_proj.name)

        # Update WBS View
        if hasattr(self, "wbs_view"):
            self.wbs_view.set_project(self.selected_project_id)

        self.load_project_tasks()

    def on_project_selected(self, item: QListWidgetItem):
        self.selected_project_id = item.data(Qt.UserRole)
        projects = {p.id: p for p in self.task_controller.get_all_projects()}
        current_proj = projects.get(self.selected_project_id)
        if current_proj:
            self.proj_name_label.setText(current_proj.name)

        if hasattr(self, "wbs_view"):
            self.wbs_view.set_project(self.selected_project_id)
        self.load_project_tasks()

    def _on_wbs_hierarchy_changed(self, key):
        """
        Phase 1E post-commit refresh bridge.

        WBSProjectView has already rebuilt itself from DB truth.
        Here we publish through the canonical TaskController event bus,
        allowing Gantt and other task consumers to refresh normally.
        """
        try:
            self.task_controller.notify_tasks_changed()
        except Exception:
            # Structural mutation already committed; keep Projects view
            # consistent even if an external listener has a defect.
            self.refresh_data()

    def load_project_tasks(self):
        clear_layout(self.task_list_layout)

        if self.selected_project_id is None:
            state_panel = StatePanel(self)
            state_panel.show_no_selection(
                title="No project selected",
                description="Create or select a project to view and organize its tasks.",
                action_text="Create Project",
                action_callback=self.open_new_project_dialog,
            )
            self.task_list_layout.addWidget(state_panel)
            return

        projects = {p.id: p for p in self.task_controller.get_all_projects()}
        current_proj = projects.get(self.selected_project_id)

        tasks = self.task_controller.get_project_tasks(self.selected_project_id)

        if not tasks:
            state_panel = StatePanel(self)
            state_panel.show_empty(
                title="No tasks in this project yet",
                description="Build your project plan by adding its first task.",
                action_text="Add Task",
                action_callback=lambda: self.open_new_task_dialog_for_project(self.selected_project_id),
                icon="task",
            )
            self.task_list_layout.addWidget(state_panel)
            return

        for task in tasks:
            p_name = current_proj.name if current_proj else "Project"
            widget = TaskItemWidget(task, project_name=p_name, settings_manager=self.settings_manager)
            widget.status_toggled.connect(self.task_controller.toggle_task_complete)
            widget.edit_requested.connect(self.open_edit_dialog)
            widget.delete_requested.connect(self.task_controller.delete_task)
            self.task_list_layout.addWidget(widget)

        self.task_list_layout.addStretch()

    def open_new_task_dialog_for_project(self, project_id: Optional[int]):
        projects = self.task_controller.get_all_projects()
        dlg = TaskDialog(projects, db_manager=self.db_manager, settings_manager=self.settings_manager, parent=self)
        if project_id and hasattr(dlg, "project_combo"):
            idx = dlg.project_combo.findData(project_id)
            if idx >= 0:
                dlg.project_combo.setCurrentIndex(idx)
        if dlg.exec() == TaskDialog.Accepted:
            self.task_controller.add_task(dlg.get_task())

    def open_new_project_dialog(self):
        dlg = ProjectDialog(parent=self)
        if dlg.exec() == ProjectDialog.Accepted:
            new_proj = dlg.get_project()
            self.task_controller.add_project(new_proj)
            ToastBanner.show_message(self, f"Project '{new_proj.name}' created!", "success")

    def _project_by_id(self, project_id: Optional[int]) -> Optional[Project]:
        if project_id is None:
            return None
        try:
            return self.task_controller.get_project(int(project_id))
        except Exception:
            return None

    def open_project_list_context_menu(self, pos):
        item = self.project_list.itemAt(pos)
        if item is None:
            return

        self.project_list.setCurrentItem(item)
        self.on_project_selected(item)
        self.open_project_context_menu(
            item.data(Qt.UserRole),
            self.project_list.viewport().mapToGlobal(pos),
        )

    def open_selected_project_context_menu(self, pos):
        if self.selected_project_id is None:
            return
        self.open_project_context_menu(
            self.selected_project_id,
            self.proj_name_label.mapToGlobal(pos),
        )

    def open_project_context_menu(self, project_id: Optional[int], global_pos):
        project = self._project_by_id(project_id)
        if project is None:
            return

        menu = QMenu(self)
        rename_action = menu.addAction("Rename Project")
        edit_action = menu.addAction("Edit Project Details")

        chosen_action = menu.exec(global_pos)
        if chosen_action == rename_action:
            self.rename_project(project.id)
        elif chosen_action == edit_action:
            self.open_edit_project_dialog(project.id)

    def rename_project(
        self,
        project_id: Optional[int] = None,
        new_name: Optional[str] = None,
    ) -> bool:
        project = self._project_by_id(project_id or self.selected_project_id)
        if project is None:
            return False

        if new_name is None:
            entered_name, accepted = QInputDialog.getText(
                self,
                "Rename Project",
                "Project name:",
                text=project.name,
            )
            if not accepted:
                return False
            new_name = entered_name

        clean_name = str(new_name or "").strip()
        if not clean_name:
            QMessageBox.warning(
                self,
                "Project Name Required",
                "Project name cannot be empty.",
            )
            return False

        if clean_name == project.name:
            return True

        project.name = clean_name
        success = self.task_controller.update_project(project)
        if success:
            self.selected_project_id = project.id
            self.refresh_data()
            ToastBanner.show_message(
                self,
                f"Project renamed to '{clean_name}'.",
                "success",
            )
        return success

    def open_edit_project_dialog(self, project_id: Optional[int] = None) -> bool:
        project = self._project_by_id(project_id or self.selected_project_id)
        if project is None:
            return False

        dlg = ProjectDialog(
            project=project,
            settings_manager=self.settings_manager,
            parent=self,
        )
        if dlg.exec() != ProjectDialog.Accepted:
            return False

        updated_project = dlg.get_project()
        success = self.task_controller.update_project(updated_project)
        if success:
            self.selected_project_id = updated_project.id
            self.refresh_data()
            ToastBanner.show_message(
                self,
                f"Project '{updated_project.name}' updated.",
                "success",
            )
        return success

    def open_edit_dialog(self, task_id: int):
        task = self.task_controller.get_task(task_id)
        if not task:
            return
        projects = self.task_controller.get_all_projects()
        dlg = TaskDialog(projects, task, db_manager=self.db_manager, settings_manager=self.settings_manager, parent=self)
        if dlg.exec() == TaskDialog.Accepted:
            updated_task = dlg.get_task()
            self.task_controller.update_task(updated_task)
            ToastBanner.show_message(self, "Task updated successfully!", "success")
            self.refresh_project_schedule()

    def open_subtask_edit_dialog(self, subtask_id: int):
        if not self.db_manager:
            return
        subtask = self.db_manager.get_subtask_by_id(subtask_id)
        if not subtask:
            return
        parent_task_id = subtask.get("task_id")
        parent_task = self.task_controller.get_task(parent_task_id) if parent_task_id else None
        dlg = SubtaskDialog(
            subtask=subtask,
            parent_task=parent_task or parent_task_id or 0,
            db_manager=self.db_manager,
            settings_manager=self.settings_manager,
            parent=self,
        )
        if dlg.exec() == SubtaskDialog.Accepted:
            ToastBanner.show_message(self, "Subtask updated successfully!", "success")
            self.refresh_project_schedule()

    # -------------------------------------------------------------------------
    # WBS View Signal Handlers
    # -------------------------------------------------------------------------

    def _on_wbs_open_task(self, entity_ref: EntityRef):
        if entity_ref.entity_type == "task":
            self.open_edit_dialog(entity_ref.entity_id)
        elif entity_ref.entity_type == "subtask":
            self.open_subtask_edit_dialog(entity_ref.entity_id)

    def _on_wbs_add_task(self, parent_key: Optional[EntityRef]):
        """
        WBS creation command.

        None:
            create a canonical ROOT Task using the existing TaskDialog.

        EntityRef:
            create a canonical Subtask child through
            WBSMutationService.create_child().

        The view never writes hierarchy fields directly.
        """

        # ------------------------------------------------------------
        # Existing root-task workflow — preserve exactly.
        # ------------------------------------------------------------
        if parent_key is None:
            projects = self.task_controller.get_all_projects()

            new_task = Task(
                title="",
                project_id=self.selected_project_id,
            )

            dlg = TaskDialog(
                projects,
                new_task,
                db_manager=self.db_manager,
                settings_manager=self.settings_manager,
                parent=self,
            )

            if dlg.exec() == TaskDialog.Accepted:
                created_task = dlg.get_task()
                self.task_controller.add_task(
                    created_task
                )

                ToastBanner.show_message(
                    self,
                    "Task created successfully!",
                    "success",
                )

            return

        # ------------------------------------------------------------
        # Professional WBS child workflow.
        # ------------------------------------------------------------
        parent_node = None

        try:
            parent_node = (
                self.wbs_view.item_model.snapshot.nodes_by_key.get(
                    parent_key
                )
            )
        except Exception:
            parent_node = None

        parent_title = (
            getattr(
                parent_node,
                "title",
                "",
            )
            or "selected item"
        )

        title, accepted = QInputDialog.getText(
            self,
            "Add Child Task",
            f"New child under “{parent_title}”:",
        )

        if not accepted:
            return

        clean_title = str(
            title or ""
        ).strip()

        if not clean_title:
            return

        result = WBSMutationService.create_child(
            self.db_manager,
            parent_key,
            clean_title,
        )

        if not result.success:
            QMessageBox.warning(
                self,
                "Unable to Add Child",
                result.message
                or "The child task could not be created.",
            )
            return

        # Clear derived rollups before rebuilding consumers.
        try:
            from todo_bird_app.services.wbs_rollup_service import (
                WBSRollupService,
            )

            WBSRollupService.clear_cache()
        except Exception:
            # Cache invalidation must never turn a successfully committed
            # DB mutation into a false failure.
            pass

        # Rebuild WBS immediately from canonical DB truth.
        self.wbs_view.refresh_hierarchy()

        # Expand the parent so the child is visible.
        if parent_key.entity_type == "subtask":
            try:
                source_idx = (
                    self.wbs_view.item_model.index_from_key(
                        parent_key,
                        0,
                    )
                )

                if source_idx.isValid():
                    proxy_idx = (
                        self.wbs_view.proxy_model.mapFromSource(
                            source_idx
                        )
                    )

                    if proxy_idx.isValid():
                        self.wbs_view.tree_view.setExpanded(
                            proxy_idx,
                            True,
                        )
            except Exception:
                pass

        # Select + reveal newly created child.
        try:
            self.wbs_view.tree_view.select_key(
                result.key
            )
        except Exception:
            pass

        # Canonical global notification:
        # Projects/Gantt/all TaskController consumers refresh through the
        # already accepted production bus.
        self.task_controller.notify_tasks_changed()

        ToastBanner.show_message(
            self,
            f"Child task “{clean_title}” created.",
            "success",
        )

    def _on_wbs_delete_task(self, entity_ref: EntityRef):
        if entity_ref.entity_type == "task":
            self.task_controller.delete_task(entity_ref.entity_id)
            ToastBanner.show_message(self, "Task deleted successfully.", "info")

    def _on_wbs_pin_toggle(self, entity_ref: EntityRef):
        if entity_ref.entity_type == "task":
            task = self.task_controller.get_task(entity_ref.entity_id)
            if task:
                task.is_pinned = not task.is_pinned
                self.task_controller.update_task(task)
                msg = "Task pinned to top priority" if task.is_pinned else "Task unpinned"
                ToastBanner.show_message(self, msg, "info")

    def on_theme_changed(self, theme_name: str):
        """Dynamically applies theme switch (light/dark) to all project sub-views."""
        is_dark = str(theme_name).lower() == "dark"
        accent = self.settings_manager.get("accent_color", "#3584E4")
        if hasattr(self, "view_mode_control") and self.view_mode_control:
            self.view_mode_control.set_theme(is_dark, accent)
        if hasattr(self, "wbs_view") and self.wbs_view:
            self.wbs_view.set_theme(is_dark, accent)
        self.update()
