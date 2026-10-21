import logging
from collections import defaultdict
from datetime import date, timedelta
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QScrollArea, QWidget, QFrame
)
from PySide6.QtCore import Qt

from todo_bird_app.views.base_view import BaseView
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.widgets.task_item_widget import TaskItemWidget
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.state_panel import StatePanel
from todo_bird_app.utils.qt_cleanup import clear_layout

logger = logging.getLogger(__name__)

class UpcomingView(BaseView):
    """
    Upcoming View — Scalable future tasks schedule with range filtering and SQL batch pagination.
    Prevents widget explosion by fetching and rendering only visible page items (Default 100).
    """
    def __init__(self, db_manager, settings_manager, parent=None):
        super().__init__(db_manager, settings_manager, title="Upcoming Schedule", subtitle="Look ahead at upcoming tasks & deadlines", parent=parent, typography_area="tasklist")
        self.task_controller = TaskController(db_manager)
        self._connect_task_controller_signal("tasks_changed", self.refresh_data)

        self.current_page = 1
        self.page_size = 100
        self.range_days = 30  # Default Next 30 days

        self._init_ui()
        self.refresh_data()

    def _init_ui(self):
        # 1. Filter Toolbar
        toolbar = QFrame()
        toolbar.setObjectName("CardWidget")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 6, 12, 6)

        tb_layout.addWidget(QLabel("Range:"))
        self.range_combo = QComboBox()
        self.range_combo.addItems(["Next 7 days", "Next 30 days", "Next 90 days", "This year", "All future"])
        self.range_combo.setCurrentText("Next 30 days")
        self.range_combo.currentTextChanged.connect(self.on_range_changed)
        tb_layout.addWidget(self.range_combo)

        tb_layout.addWidget(QLabel("Page Size:"))
        self.size_combo = QComboBox()
        self.size_combo.addItems(["50", "100", "250"])
        self.size_combo.setCurrentText("100")
        self.size_combo.currentTextChanged.connect(self.on_page_size_changed)
        tb_layout.addWidget(self.size_combo)

        tb_layout.addStretch()
        self.main_layout.addWidget(toolbar)

        # 2. Pagination & Status Bar
        self.pagi_card = QFrame()
        self.pagi_card.setObjectName("CardWidget")
        p_layout = QHBoxLayout(self.pagi_card)
        p_layout.setContentsMargins(12, 6, 12, 6)

        self.lbl_count_info = QLabel("Showing 0 upcoming tasks")
        self.lbl_count_info.setStyleSheet("font-weight: 600; color: #E95420;")
        p_layout.addWidget(self.lbl_count_info)
        p_layout.addStretch()

        self.btn_first_page = QPushButton("⏪ First")
        self.btn_first_page.setFixedWidth(65)
        self.btn_first_page.clicked.connect(self.first_page)
        p_layout.addWidget(self.btn_first_page)

        self.btn_prev_page = QPushButton("◀ Prev")
        self.btn_prev_page.setFixedWidth(65)
        self.btn_prev_page.clicked.connect(self.prev_page)
        p_layout.addWidget(self.btn_prev_page)

        self.lbl_page_num = QLabel("Page 1 of 1")
        self.lbl_page_num.setStyleSheet("color: #9CA3AF; padding: 0 8px;")
        p_layout.addWidget(self.lbl_page_num)

        self.btn_next_page = QPushButton("Next ▶")
        self.btn_next_page.setFixedWidth(65)
        self.btn_next_page.clicked.connect(self.next_page)
        p_layout.addWidget(self.btn_next_page)

        self.btn_last_page = QPushButton("Last ⏩")
        self.btn_last_page.setFixedWidth(65)
        self.btn_last_page.clicked.connect(self.last_page)
        p_layout.addWidget(self.btn_last_page)

        self.main_layout.addWidget(self.pagi_card)

        # 3. Tasks List Scroll Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        self.list_container = QWidget()
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 8, 0, 8)
        self.list_layout.setSpacing(12)

        scroll.setWidget(self.list_container)
        self.main_layout.addWidget(scroll, 1)

    def _get_end_date_str(self):
        today = date.today()
        if self.range_days == 7:
            return (today + timedelta(days=7)).strftime("%Y-%m-%d")
        elif self.range_days == 30:
            return (today + timedelta(days=30)).strftime("%Y-%m-%d")
        elif self.range_days == 90:
            return (today + timedelta(days=90)).strftime("%Y-%m-%d")
        elif self.range_days == 365:
            return date(today.year, 12, 31).strftime("%Y-%m-%d")
        else:
            return None

    def on_range_changed(self, text: str):
        if "7" in text:
            self.range_days = 7
        elif "30" in text:
            self.range_days = 30
        elif "90" in text:
            self.range_days = 90
        elif "year" in text:
            self.range_days = 365
        else:
            self.range_days = 99999

        self.current_page = 1
        self.refresh_data()

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
        end_date = self._get_end_date_str()
        total_count = self.task_controller.get_upcoming_tasks_count(end_date=end_date)
        total_pages = max(1, (total_count + self.page_size - 1) // self.page_size)
        self.current_page = total_pages
        self.refresh_data()

    def refresh_data(self):
        super().refresh_data()
        # Clear layout completely using shared qt_cleanup utility
        clear_layout(self.list_layout)

        end_date = self._get_end_date_str()
        total_count = self.task_controller.get_upcoming_tasks_count(end_date=end_date)
        total_pages = max(1, (total_count + self.page_size - 1) // self.page_size)

        if self.current_page > total_pages:
            self.current_page = total_pages

        offset = (self.current_page - 1) * self.page_size
        page_tasks = self.task_controller.get_upcoming_tasks(end_date=end_date, limit=self.page_size, offset=offset)[:self.page_size]

        # Update Pagination Controls
        range_label = self.range_combo.currentText()
        if total_count > 0:
            start_idx = offset + 1
            end_idx = min(offset + len(page_tasks), total_count)
            self.lbl_count_info.setText(f"Showing {start_idx}–{end_idx} of {total_count} tasks ({range_label})")
        else:
            self.lbl_count_info.setText(f"Showing 0 upcoming tasks ({range_label})")

        self.lbl_page_num.setText(f"Page {self.current_page} of {total_pages}")
        self.btn_first_page.setEnabled(self.current_page > 1)
        self.btn_prev_page.setEnabled(self.current_page > 1)
        self.btn_next_page.setEnabled(self.current_page < total_pages)
        self.btn_last_page.setEnabled(self.current_page < total_pages)

        if not page_tasks:
            state_panel = StatePanel(self)
            state_panel.show_empty(
                title="No upcoming tasks scheduled",
                description="Plan ahead by setting planned dates on your tasks.",
                action_text="Add Task",
                action_callback=self.open_new_task_dialog,
                icon="calendar",
            )
            self.list_layout.addWidget(state_panel)
            return

        projects = {p.id: p.name for p in self.task_controller.get_all_projects()}

        grouped = defaultdict(list)
        for t in page_tasks:
            grouped[t.planned_date or "Unscheduled"].append(t)

        for date_str, group_tasks in grouped.items():
            header = QLabel(date_str)
            header.setStyleSheet("color: #E95420; margin-top: 6px;")
            self.list_layout.addWidget(header)

            for task in group_tasks:
                proj_name = projects.get(task.project_id, "Inbox")
                widget = TaskItemWidget(task, project_name=proj_name, settings_manager=self.settings_manager)
                widget.status_toggled.connect(self.task_controller.toggle_task_complete)
                widget.edit_requested.connect(self.open_edit_dialog)
                widget.delete_requested.connect(self.task_controller.delete_task)
                self.list_layout.addWidget(widget)

        self.list_layout.addStretch()

    def open_new_task_dialog(self):
        projects = self.task_controller.get_all_projects()
        dlg = TaskDialog(projects, db_manager=self.db_manager, settings_manager=self.settings_manager, parent=self)
        if dlg.exec() == TaskDialog.Accepted:
            new_task = dlg.get_task()
            if not new_task.planned_date:
                new_task.planned_date = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
            self.task_controller.add_task(new_task)

    def open_edit_dialog(self, task_id: int):
        task = self.task_controller.get_task(task_id)
        if not task:
            return
        projects = self.task_controller.get_all_projects()
        dlg = TaskDialog(projects, task, db_manager=self.db_manager, settings_manager=self.settings_manager, parent=self)
        if dlg.exec() == TaskDialog.Accepted:
            updated_task = dlg.get_task()
            self.task_controller.update_task(updated_task)
