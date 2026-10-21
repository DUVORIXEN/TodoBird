import logging
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QWidget, QFrame,
    QDialog, QTextEdit, QMessageBox
)
from todo_bird_app.widgets.rich_text_editor import RichTextEditor
from PySide6.QtCore import Qt

from todo_bird_app.views.base_view import BaseView
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.widgets.task_item_widget import TaskItemWidget
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.toast_banner import ToastBanner
from todo_bird_app.widgets.pinned_priorities_widget import PinnedPrioritiesWidget
from todo_bird_app.widgets.state_panel import StatePanel
from todo_bird_app.models.task import Task, TaskStatus

from todo_bird_app.utils.qt_cleanup import clear_layout

logger = logging.getLogger(__name__)

PAGE_SIZE = 100

class InboxView(BaseView):
    """
    Inbox View — Fast capture and task management with SQL batch pagination.
    Renders 100 items per page with clear page navigation controls.
    """
    def __init__(self, db_manager, settings_manager, parent=None):
        super().__init__(db_manager, settings_manager, title="Inbox", subtitle="Capture & organize incoming tasks", parent=parent, typography_area="tasklist")
        self.task_controller = TaskController(db_manager)
        self._connect_task_controller_signal("tasks_changed", self.refresh_data)
        self.current_page = 1
        self._init_ui()
        self.refresh_data()

    def _init_ui(self):
        # Quick Add Bar
        quick_frame = QFrame()
        quick_frame.setObjectName("CardWidget")
        q_layout = QHBoxLayout(quick_frame)
        q_layout.setContentsMargins(12, 8, 12, 8)

        self.quick_input = QLineEdit()
        self.quick_input.setPlaceholderText(
            " Quick Capture — title only (Press Enter)…"
        )
        self.quick_input.returnPressed.connect(self.quick_add_task)
        q_layout.addWidget(self.quick_input)

        # -------------------------------------------------
        # Two explicit creation modes.
        #
        # Enter / Quick Capture:
        #   title-only inbox capture.
        #
        # Full Task:
        #   professional schedule/status/Gantt/dependencies dialog.
        # -------------------------------------------------
        quick_btn = QPushButton(
            " Quick Capture"
        )
        quick_btn.setToolTip(
            "Capture the title immediately to Inbox. "
            "No schedule is required."
        )
        quick_btn.clicked.connect(
            self.quick_add_task
        )
        q_layout.addWidget(
            quick_btn
        )

        add_btn = QPushButton(
            "＋ Full Task…"
        )
        add_btn.setObjectName(
            "PrimaryButton"
        )
        add_btn.setToolTip(
            "Create a fully scheduled task with date, "
            "time, status, Gantt, dependencies and workflow."
        )
        add_btn.clicked.connect(
            self.open_new_task_dialog
        )
        q_layout.addWidget(
            add_btn
        )

        self.main_layout.addWidget(quick_frame)

        # Premium persistent pinned-priority workspace
        self.pinned_priorities = PinnedPrioritiesWidget(
            self.db_manager,
            parent=self,
        )
        self.pinned_priorities.edit_requested.connect(
            self.open_edit_dialog
        )
        self.pinned_priorities.changed.connect(
            self.refresh_data
        )
        self.main_layout.addWidget(self.pinned_priorities)

        # Pagination & Counter Bar (Top)
        self.pagi_card = QFrame()
        self.pagi_card.setObjectName("CardWidget")
        p_layout = QHBoxLayout(self.pagi_card)
        p_layout.setContentsMargins(12, 6, 12, 6)

        self.lbl_count_info = QLabel("Showing 0 tasks")
        self.lbl_count_info.setStyleSheet("font-weight: 600; color: #3584E4;")
        p_layout.addWidget(self.lbl_count_info)
        p_layout.addStretch()

        self.btn_prev_page = QPushButton("◀ Prev")
        self.btn_prev_page.setMinimumWidth(64)
        self.btn_prev_page.clicked.connect(self.prev_page)
        p_layout.addWidget(self.btn_prev_page)

        self.lbl_page_num = QLabel("Page 1 of 1")
        self.lbl_page_num.setStyleSheet("color: palette(mid); padding: 0 8px;")
        p_layout.addWidget(self.lbl_page_num)

        self.btn_next_page = QPushButton("Next ▶")
        self.btn_next_page.setMinimumWidth(64)
        self.btn_next_page.clicked.connect(self.next_page)
        p_layout.addWidget(self.btn_next_page)

        self.main_layout.addWidget(self.pagi_card)

        # Tasks list scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }")

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 8, 0, 8)
        self.list_layout.setSpacing(8)

        scroll.setWidget(self.list_container)
        self.main_layout.addWidget(scroll, 1)

    def open_new_task_dialog(self):
        """
        Full task creation authority.

        Unlike Quick Capture, this path persists the complete
        TaskDialog schedule/workflow model.
        """
        projects = (
            self.task_controller
            .get_all_projects()
        )

        dlg = TaskDialog(
            projects,
            db_manager=self.db_manager,
            settings_manager=self.settings_manager,
            parent=self,
        )

        # If the operator has already typed a title into
        # Quick Capture, reuse it rather than losing the typing.
        typed_title = (
            self.quick_input
            .text()
            .strip()
        )

        if typed_title:
            dlg.title_input.setText(
                typed_title
            )

        if (
            dlg.exec()
            != TaskDialog.Accepted
        ):
            return

        new_task = dlg.get_task()

        task_id = (
            self.task_controller
            .add_task(
                new_task
            )
        )

        # -------------------------------------------------
        # Persist recursive hierarchy for brand-new tasks.
        # -------------------------------------------------
        def save_nodes(
            nodes,
            parent_subtask_id=None,
        ):
            for fallback_position, subtask in enumerate(
                nodes
            ):
                position = int(
                    subtask.get(
                        "position",
                        fallback_position,
                    )
                )

                subtask_id = (
                    self.db_manager
                    .insert_subtask(
                        task_id=task_id,
                        title=subtask.get(
                            "title",
                            "",
                        ),
                        is_completed=bool(
                            subtask.get(
                                "is_completed",
                                False,
                            )
                        ),
                        position=position,
                        parent_subtask_id=parent_subtask_id,
                        description=subtask.get(
                            "description",
                            "",
                        ),
                        planned_date=subtask.get(
                            "planned_date"
                        ),
                        due_date=subtask.get(
                            "due_date"
                        ),
                        planned_start_time=subtask.get(
                            "planned_start_time"
                        ),
                        planned_end_time=subtask.get(
                            "planned_end_time"
                        ),
                        estimated_duration=int(
                            subtask.get(
                                "estimated_duration",
                                0,
                            )
                            or 0
                        ),
                        priority=subtask.get(
                            "priority",
                            "Medium",
                        ),
                        progress=int(
                            subtask.get(
                                "progress",
                                0,
                            )
                            or 0
                        ),
                        show_in_gantt=bool(
                            subtask.get(
                                "show_in_gantt",
                                False,
                            )
                        ),
                        is_pinned=bool(
                            subtask.get(
                                "is_pinned",
                                False,
                            )
                        ),
                        pin_color=subtask.get(
                            "pin_color",
                            "#E95420",
                        ),
                        pin_position=int(
                            subtask.get(
                                "pin_position",
                                0,
                            )
                            or 0
                        ),
                    )
                )

                save_nodes(
                    subtask.get(
                        "children",
                        [],
                    ),
                    subtask_id,
                )

        save_nodes(
            dlg.get_pending_subtasks()
        )

        # -------------------------------------------------
        # READ-AFTER-WRITE VERIFICATION
        #
        # We verify database truth immediately rather than
        # trusting only the in-memory dialog object.
        # -------------------------------------------------
        saved = (
            self.task_controller
            .get_task(
                task_id
            )
        )

        if saved is None:
            QMessageBox.critical(
                self,
                "Task Save Verification Failed",
                "Todo Bird could not read the newly created "
                "task back from the database.",
            )
            return

        expected = {
            "planned_date":
                new_task.planned_date,

            "due_date":
                new_task.due_date,

            "planned_start_time":
                new_task.planned_start_time,

            "planned_end_time":
                new_task.planned_end_time,

            "estimated_duration":
                int(
                    new_task.estimated_duration
                    or 0
                ),

            "show_in_gantt":
                bool(
                    new_task.show_in_gantt
                ),
        }

        actual = {
            "planned_date":
                saved.planned_date,

            "due_date":
                saved.due_date,

            "planned_start_time":
                saved.planned_start_time,

            "planned_end_time":
                saved.planned_end_time,

            "estimated_duration":
                int(
                    saved.estimated_duration
                    or 0
                ),

            "show_in_gantt":
                bool(
                    saved.show_in_gantt
                ),
        }

        mismatches = [
            key
            for key in expected
            if expected[key]
            != actual[key]
        ]

        if mismatches:
            QMessageBox.warning(
                self,
                "Schedule Verification Warning",
                "The task was created, but these schedule "
                "fields did not persist exactly:\n\n"
                + "\n".join(
                    "• "
                    + key
                    + ": expected "
                    + repr(expected[key])
                    + ", saved "
                    + repr(actual[key])
                    for key in mismatches
                ),
            )

        else:
            schedule_text = (
                f"{saved.planned_date or 'No date'} "
                f"{saved.planned_start_time or '--:--'}"
                f"–"
                f"{saved.planned_end_time or '--:--'}"
            )

            QMessageBox.information(
                self,
                "Task Created",
                f"{saved.title}\n"
                f"{schedule_text}\n"
                f"Duration: "
                f"{saved.estimated_duration or 0} min\n"
                f"Gantt: "
                f"{'Yes' if saved.show_in_gantt else 'No'}",
            )

        self.quick_input.clear()

        self.refresh_data()

    def quick_add_task(self):
        text = self.quick_input.text().strip()
        if not text:
            return

        task = Task(title=text, status=TaskStatus.INBOX)
        self.task_controller.add_task(task)
        self.quick_input.clear()

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.refresh_data()

    def next_page(self):
        self.current_page += 1
        self.refresh_data()

    def refresh_data(self):
        if hasattr(self, "pinned_priorities"):
            self.pinned_priorities.refresh_data()

        # Clear current list
        clear_layout(self.list_layout)

        total_count = self.task_controller.get_inbox_tasks_count()
        total_pages = max(1, (total_count + PAGE_SIZE - 1) // PAGE_SIZE)

        if self.current_page > total_pages:
            self.current_page = total_pages

        offset = (self.current_page - 1) * PAGE_SIZE
        page_tasks = self.task_controller.get_inbox_tasks(limit=PAGE_SIZE, offset=offset)

        # Update Pagination Controls
        if total_count > 0:
            start_idx = offset + 1
            end_idx = min(offset + len(page_tasks), total_count)
            self.lbl_count_info.setText(f"Showing {start_idx}–{end_idx} of {total_count} tasks")
        else:
            self.lbl_count_info.setText("Showing 0 tasks")

        self.lbl_page_num.setText(f"Page {self.current_page} of {total_pages}")
        self.btn_prev_page.setEnabled(self.current_page > 1)
        self.btn_next_page.setEnabled(self.current_page < total_pages)

        projects = {p.id: p.name for p in self.task_controller.get_all_projects()}

        if not page_tasks:
            state_panel = StatePanel(self)
            state_panel.show_empty(
                title="Inbox is clear",
                description="Capture incoming ideas or tasks using the bar above.",
                action_text="＋ Full Task…",
                action_callback=self.open_new_task_dialog,
                icon="inbox",
            )
            self.list_layout.addWidget(state_panel)
            return

        for task in page_tasks:
            proj_name = projects.get(task.project_id, "Inbox")
            widget = TaskItemWidget(task, project_name=proj_name, settings_manager=self.settings_manager)
            widget.status_toggled.connect(self.task_controller.toggle_task_complete)
            widget.preview_requested.connect(self.open_task_preview)
            widget.edit_requested.connect(self.open_edit_dialog)
            widget.delete_requested.connect(self.task_controller.delete_task)
            self.list_layout.addWidget(widget)

        self.list_layout.addStretch()

    def open_edit_dialog(self, task_id: int):
        task = self.task_controller.get_task(task_id)
        if not task:
            return
        projects = self.task_controller.get_all_projects()
        dlg = TaskDialog(projects, task, db_manager=self.db_manager, settings_manager=self.settings_manager, parent=self)
        if dlg.exec() == TaskDialog.Accepted:
            self.task_controller.update_task(dlg.get_task())
            ToastBanner.show_message(self, "Task updated successfully!", "success")
