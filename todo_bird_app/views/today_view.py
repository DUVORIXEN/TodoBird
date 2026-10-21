from datetime import date
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget, QFrame,
    QProgressBar, QPushButton, QComboBox
)
from PySide6.QtCore import Qt

from todo_bird_app.views.base_view import BaseView
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.controllers.workload_engine import WorkloadEngine, WorkloadState
from todo_bird_app.widgets.task_item_widget import TaskItemWidget
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.pinned_priorities_widget import PinnedPrioritiesWidget
from todo_bird_app.widgets.state_panel import StatePanel
from todo_bird_app.services.typography_service import TypographyService
from todo_bird_app.utils.qt_cleanup import clear_layout

WORKLOAD_STATE_COLORS = {
    WorkloadState.UNDER_CAPACITY: "#10B981",
    WorkloadState.BALANCED: "#3584E4",
    WorkloadState.SLIGHTLY_OVERLOADED: "#F59E0B",
    WorkloadState.SEVERELY_OVERLOADED: "#EF4444",
}

class TodayView(BaseView):
    """
    Today View — Focus view for today's planned commitments with workload confidence.
    """
    def __init__(self, db_manager, settings_manager, parent=None):
        super().__init__(db_manager, settings_manager, title="Today's Plan", subtitle="Focus on tasks scheduled for today", parent=parent, typography_area="tasklist")
        self.task_controller = TaskController(db_manager)
        self._connect_task_controller_signal("tasks_changed", self.refresh_data)
        self.workload_engine = WorkloadEngine(settings_manager)
        self.current_page = 1
        self.page_size = 100
        self._init_ui()
        self.refresh_data()

    def _init_ui(self):
        # Progress Card Summary
        self.summary_card = QFrame()
        self.summary_card.setObjectName("CardWidget")
        sum_layout = QVBoxLayout(self.summary_card)

        head_layout = QHBoxLayout()
        self.date_label = QLabel(date.today().strftime('%A, %B %d, %Y'))
        self.date_label.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(
            self.date_label,
            delta_pt=4,
            weight="bold",
        )
        self.stat_label = QLabel("0 / 0 Completed")
        self.stat_label.setStyleSheet("color: #9CA3AF;")

        head_layout.addWidget(self.date_label)
        head_layout.addStretch()
        head_layout.addWidget(self.stat_label)
        sum_layout.addLayout(head_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setTextVisible(False)
        sum_layout.addWidget(self.progress_bar)

        # Workload Confidence Banner
        self.workload_label = QLabel("")
        self.workload_label.setStyleSheet("padding-top: 4px;")
        sum_layout.addWidget(self.workload_label)

        self.main_layout.addWidget(self.summary_card)

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

        self.pagi_card = QFrame()
        self.pagi_card.setObjectName("CardWidget")
        p_layout = QHBoxLayout(self.pagi_card)
        p_layout.setContentsMargins(12, 6, 12, 6)

        self.lbl_count_info = QLabel("Showing 0 tasks")
        self.lbl_count_info.setStyleSheet("font-weight: 600; color: #E95420;")
        p_layout.addWidget(self.lbl_count_info)
        p_layout.addStretch()

        p_layout.addWidget(QLabel("Page Size:"))
        self.size_combo = QComboBox()
        self.size_combo.addItems(["50", "100", "250"])
        self.size_combo.setCurrentText("100")
        self.size_combo.currentTextChanged.connect(self.on_page_size_changed)
        p_layout.addWidget(self.size_combo)

        self.btn_first_page = QPushButton("⏪ First")
        self.btn_first_page.setMinimumWidth(64)
        self.btn_first_page.clicked.connect(self.first_page)
        p_layout.addWidget(self.btn_first_page)

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

        self.btn_last_page = QPushButton("Last ⏩")
        self.btn_last_page.setMinimumWidth(64)
        self.btn_last_page.clicked.connect(self.last_page)
        p_layout.addWidget(self.btn_last_page)

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

    def on_page_size_changed(self, text: str):
        try:
            self.page_size = int(text)
        except ValueError:
            self.page_size = 100
        self.current_page = 1
        self.refresh_data()

    def first_page(self):
        self.current_page = 1
        self.refresh_data()

    def prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self.refresh_data()

    def next_page(self):
        self.current_page += 1
        self.refresh_data()

    def last_page(self):
        tasks = self.task_controller.get_today_tasks()
        total_pages = max(
            1,
            (len(tasks) + self.page_size - 1) // self.page_size,
        )
        self.current_page = total_pages
        self.refresh_data()

    def refresh_data(self):
        super().refresh_data()
        if hasattr(self, "pinned_priorities"):
            self.pinned_priorities.refresh_data()

        # Clear current list
        clear_layout(self.list_layout)

        tasks = self.task_controller.get_today_tasks()
        projects = {p.id: p.name for p in self.task_controller.get_all_projects()}

        total = len(tasks)
        total_pages = max(
            1,
            (total + self.page_size - 1) // self.page_size,
        )
        if self.current_page > total_pages:
            self.current_page = total_pages
        if self.current_page < 1:
            self.current_page = 1
        offset = (self.current_page - 1) * self.page_size
        page_tasks = tasks[offset: offset + self.page_size]

        completed = sum(1 for t in tasks if t.status.value == "Completed")
        pct = int((completed / total * 100)) if total > 0 else 0

        self.stat_label.setText(f"{completed} / {total} Completed ({pct}%)")
        self.progress_bar.setValue(pct)

        # Workload Confidence Evaluation
        state, p_hrs, a_hrs, advice = self.workload_engine.evaluate_day_workload(tasks)
        w_color = WORKLOAD_STATE_COLORS.get(state, "#3584E4")
        self.workload_label.setText(f"Workload Confidence: {state.value} ({p_hrs:.1f}h planned / {a_hrs:.1f}h target) — {advice}")
        self.workload_label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {w_color}; padding-top: 4px;")

        if total > 0:
            start_idx = offset + 1
            end_idx = min(offset + len(page_tasks), total)
            self.lbl_count_info.setText(
                f"Showing {start_idx}–{end_idx} of {total} tasks"
            )
        else:
            self.lbl_count_info.setText("Showing 0 tasks")

        self.lbl_page_num.setText(
            f"Page {self.current_page} of {total_pages}"
        )
        self.btn_first_page.setEnabled(self.current_page > 1)
        self.btn_prev_page.setEnabled(self.current_page > 1)
        self.btn_next_page.setEnabled(self.current_page < total_pages)
        self.btn_last_page.setEnabled(self.current_page < total_pages)

        if not tasks:
            state_panel = StatePanel(self)
            state_panel.show_empty(
                title="No tasks scheduled for today",
                description="Your schedule is clear. Plan new tasks or relax!",
                action_text="Add Task",
                action_callback=self.open_new_task_dialog,
                icon="",
            )
            self.list_layout.addWidget(state_panel)
            return

        for task in page_tasks:
            proj_name = projects.get(task.project_id, "Inbox")
            widget = TaskItemWidget(task, project_name=proj_name, settings_manager=self.settings_manager)
            widget.status_toggled.connect(self.task_controller.toggle_task_complete)
            widget.edit_requested.connect(self.open_edit_dialog)
            widget.preview_requested.connect(self.open_task_preview)
            widget.delete_requested.connect(self.task_controller.delete_task)
            self.list_layout.addWidget(widget)

        self.list_layout.addStretch()

    def open_new_task_dialog(self):
        projects = self.task_controller.get_all_projects()
        dlg = TaskDialog(projects, db_manager=self.db_manager, settings_manager=self.settings_manager, parent=self)
        if dlg.exec() == TaskDialog.Accepted:
            new_task = dlg.get_task()
            if not new_task.planned_date:
                new_task.planned_date = date.today().strftime("%Y-%m-%d")
            self.task_controller.add_task(new_task)

    def open_edit_dialog(self, task_id: int):
        task = self.task_controller.get_task(task_id)
        if not task:
            return
        projects = self.task_controller.get_all_projects()
        dlg = TaskDialog(projects, task, db_manager=self.db_manager, settings_manager=self.settings_manager, parent=self)
        if dlg.exec() == TaskDialog.Accepted:
            self.task_controller.update_task(dlg.get_task())
