import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QCalendarWidget, QScrollArea, QWidget, QFrame, QPushButton, QSizePolicy
)
from PySide6.QtCore import Qt, QDate, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QBrush

from todo_bird_app.views.base_view import BaseView
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.widgets.task_item_widget import TaskItemWidget
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.state_panel import StatePanel
from todo_bird_app.services.working_week import WorkingWeekService
from todo_bird_app.services.typography_service import TypographyService
from todo_bird_app.utils.qt_cleanup import clear_layout

logger = logging.getLogger(__name__)


class RichCalendarWidget(QCalendarWidget):
    """
    Enhanced QCalendarWidget that paints task indicators and multi-day badges into monthly cells.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self._date_task_counts = {}  # {date: count}
        self._date_has_multi_day = set()

    def set_task_indicators(self, date_counts: dict, multi_day_dates: set):
        self._date_task_counts = date_counts
        self._date_has_multi_day = multi_day_dates
        self.update()

    def paintCell(self, painter: QPainter, rect, qdate: QDate):
        super().paintCell(painter, rect, qdate)
        cell_date = date(qdate.year(), qdate.month(), qdate.day())

        count = self._date_task_counts.get(cell_date, 0)
        has_multi = cell_date in self._date_has_multi_day

        if count > 0 or has_multi:
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)

            # Draw indicator dot/pill near bottom of cell
            dot_color = QColor("#3584E4") if not has_multi else QColor("#8B5CF6")
            painter.setBrush(QBrush(dot_color))
            painter.setPen(Qt.NoPen)

            dot_size = 5.0
            x = rect.center().x() - (dot_size / 2.0)
            y = rect.bottom() - dot_size - 3.0
            painter.drawEllipse(QRectF(x, y, dot_size, dot_size))

            painter.restore()


class CalendarView(BaseView):
    """
    Calendar View — Interactive monthly schedule grid with multi-day span semantics,
    permanent empty-state container, and nearest-task guidance.
    """
    def __init__(self, db_manager, settings_manager, parent=None):
        super().__init__(
            db_manager, settings_manager,
            title="Calendar View", subtitle="Monthly schedule and multi-day execution overview",
            parent=parent, typography_area="calendar"
        )
        self.task_controller = TaskController(db_manager)
        self._connect_task_controller_signal("tasks_changed", self.refresh_data)
        self.working_week_service = WorkingWeekService(settings_manager)
        self._init_ui()
        self.apply_typography()
        self.refresh_data()
    def apply_typography(self):
        super().apply_typography()
        from todo_bird_app.services.typography_service import TypographyService
        font = TypographyService.get_font_for_area("calendar", self.settings_manager)
        if hasattr(self, "calendar") and self.calendar:
            self.calendar.setFont(font)
            from PySide6.QtWidgets import QTableView, QHeaderView, QToolButton, QSpinBox
            for t in (QTableView, QHeaderView, QToolButton, QSpinBox):
                for child in self.calendar.findChildren(t):
                    child.setFont(font)
        TypographyService.apply_to_widget(self, "calendar", self.settings_manager)

    def _init_ui(self):
        container_layout = QHBoxLayout()
        container_layout.setSpacing(16)

        # 1. Calendar Widget Card
        cal_card = QFrame()
        cal_card.setObjectName("CardWidget")
        cal_layout = QVBoxLayout(cal_card)

        self.calendar = RichCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.selectionChanged.connect(self.on_date_selected)
        cal_layout.addWidget(self.calendar)

        container_layout.addWidget(cal_card, 1)

        # 2. Tasks list side panel for selected date
        side_panel = QFrame()
        side_panel.setObjectName("CardWidget")
        side_panel.setMinimumWidth(280)
        side_panel.setMaximumWidth(420)
        side_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        side_layout = QVBoxLayout(side_panel)

        self.date_title = QLabel("Tasks for Selected Date")
        self.date_title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(
            self.date_title,
            delta_pt=4,
            weight="bold",
        )
        side_layout.addWidget(self.date_title)

        self.date_subtitle = QLabel("0 tasks scheduled")
        self.date_subtitle.setStyleSheet("color: #9CA3AF; margin-bottom: 8px;")
        side_layout.addWidget(self.date_subtitle)

        # Standard Phase 1F.9 StatePanel for empty date
        self.state_panel = StatePanel(self)
        self.empty_state_card = self.state_panel
        self.lbl_empty_main = self.state_panel.title_label
        self.lbl_empty_nearest = self.state_panel.desc_label
        self.lbl_empty_icon = self.state_panel.icon_label
        self.btn_empty_add = self.state_panel.btn_primary
        side_layout.addWidget(self.state_panel)

        # Scroll Area for active tasks
        self.task_scroll = QScrollArea()
        self.task_scroll.setWidgetResizable(True)
        self.task_scroll.setFrameShape(QFrame.NoFrame)
        self.task_scroll.setStyleSheet("background: transparent;")

        self.task_container = QWidget()
        self.task_list_layout = QVBoxLayout(self.task_container)
        self.task_list_layout.setContentsMargins(0, 4, 0, 4)
        self.task_list_layout.setSpacing(8)

        self.task_scroll.setWidget(self.task_container)
        side_layout.addWidget(self.task_scroll, 1)

        container_layout.addWidget(side_panel)
        self.main_layout.addLayout(container_layout)

    def on_date_selected(self):
        self.refresh_data()

    @staticmethod
    def _parse_date(date_val) -> Optional[date]:
        if not date_val:
            return None
        if isinstance(date_val, date):
            return date_val
        try:
            return datetime.strptime(str(date_val).strip()[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            return None

    def _get_tasks_for_date(self, target_date: date) -> List[Task]:
        all_tasks = self.task_controller.get_all_tasks()
        matched_tasks = []

        for task in all_tasks:
            p_date = self._parse_date(task.planned_date)
            d_date = self._parse_date(task.due_date)

            if p_date and d_date:
                # Multi-day span: start <= target <= due
                start = min(p_date, d_date)
                end = max(p_date, d_date)
                if start <= target_date <= end:
                    matched_tasks.append(task)
            elif p_date and p_date == target_date:
                matched_tasks.append(task)
            elif d_date and d_date == target_date:
                matched_tasks.append(task)

        return matched_tasks

    def _find_nearest_scheduled_date(self, target_date: date, all_tasks: List[Task]) -> Optional[date]:
        candidate_dates = set()
        for task in all_tasks:
            p_date = self._parse_date(task.planned_date)
            d_date = self._parse_date(task.due_date)
            if p_date:
                candidate_dates.add(p_date)
            if d_date:
                candidate_dates.add(d_date)

        other_dates = [d for d in candidate_dates if d != target_date]
        if not other_dates:
            return None

        other_dates.sort(key=lambda d: (abs((d - target_date).days), d))
        return other_dates[0]

    def _update_selected_date_state(self, selected_date: date, all_tasks: List[Task]):
        formatted_date = selected_date.strftime("%d %b %Y")
        nearest = self._find_nearest_scheduled_date(selected_date, all_tasks)
        if nearest:
            desc = f"Nearest scheduled task: {nearest.strftime('%d %b %Y')}"
        else:
            desc = "No tasks planned or due on this date."

        self.state_panel.show_empty(
            title=f"No tasks scheduled for {formatted_date}",
            description=desc,
            action_text="＋ Add Task for This Date",
            action_callback=self._add_task_for_selected_date,
            icon="calendar",
        )

    def _update_empty_state(self, selected_date: date, all_tasks: List[Task]):
        self._update_selected_date_state(selected_date, all_tasks)

    def _update_calendar_cell_indicators(self, all_tasks: List[Task]):
        date_counts = {}
        multi_day_dates = set()

        for task in all_tasks:
            p_date = self._parse_date(task.planned_date)
            d_date = self._parse_date(task.due_date)

            if p_date and d_date and p_date != d_date:
                start = min(p_date, d_date)
                end = max(p_date, d_date)
                days_count = min((end - start).days + 1, 90)
                for d_offset in range(days_count):
                    curr = start + timedelta(days=d_offset)
                    date_counts[curr] = date_counts.get(curr, 0) + 1
                    multi_day_dates.add(curr)
            elif p_date:
                date_counts[p_date] = date_counts.get(p_date, 0) + 1
            elif d_date:
                date_counts[d_date] = date_counts.get(d_date, 0) + 1

        self.calendar.set_task_indicators(date_counts, multi_day_dates)

    def refresh_data(self):
        super().refresh_data()
        qdate = self.calendar.selectedDate()
        sel_date = date(qdate.year(), qdate.month(), qdate.day())
        formatted_date = sel_date.strftime("%a, %d %b %Y")
        self.date_title.setText(f"Tasks for {formatted_date}")

        all_tasks = self.task_controller.get_all_tasks()
        self._update_calendar_cell_indicators(all_tasks)

        day_tasks = self._get_tasks_for_date(sel_date)
        projects = {p.id: p.name for p in self.task_controller.get_all_projects()}

        self.date_subtitle.setText(f"{len(day_tasks)} task{'s' if len(day_tasks) != 1 else ''} scheduled")

        if not day_tasks:
            self._update_selected_date_state(sel_date, all_tasks)
            self.state_panel.show()
            self.task_scroll.hide()
            return

        self.state_panel.hide()
        self.task_scroll.show()

        clear_layout(self.task_list_layout)

        for task in day_tasks:
            proj_name = projects.get(task.project_id, "Inbox")
            widget = TaskItemWidget(task, project_name=proj_name, settings_manager=self.settings_manager)
            widget.status_toggled.connect(self.task_controller.toggle_task_complete)
            widget.edit_requested.connect(self.open_edit_dialog)
            widget.delete_requested.connect(self.task_controller.delete_task)
            self.task_list_layout.addWidget(widget)

        self.task_list_layout.addStretch()

    def _add_task_for_selected_date(self):
        qdate = self.calendar.selectedDate()
        sel_date = date(qdate.year(), qdate.month(), qdate.day())
        date_str = sel_date.strftime("%Y-%m-%d")
        projects = self.task_controller.get_all_projects()

        initial_task = Task(
            title="",
            planned_date=date_str,
            due_date=date_str,
        )
        dlg = TaskDialog(
            projects,
            task=initial_task,
            db_manager=self.db_manager,
            settings_manager=self.settings_manager,
            parent=self,
        )
        if hasattr(dlg, "planned_date_edit") and hasattr(dlg.planned_date_edit, "setDate"):
            dlg.planned_date_edit.setDate(QDate(qdate.year(), qdate.month(), qdate.day()))
        if hasattr(dlg, "due_date_edit") and hasattr(dlg.due_date_edit, "setDate"):
            dlg.due_date_edit.setDate(QDate(qdate.year(), qdate.month(), qdate.day()))

        if dlg.exec() == TaskDialog.Accepted:
            new_task = dlg.get_task()
            if not new_task.planned_date:
                new_task.planned_date = date_str
            self.task_controller.add_task(new_task)
            self.refresh_data()

    def open_new_task_dialog_for_selected_date(self):
        self._add_task_for_selected_date()

    def open_edit_dialog(self, task_id: int):
        task = self.task_controller.get_task(task_id)
        if not task:
            return
        projects = self.task_controller.get_all_projects()
        dlg = TaskDialog(projects, task, db_manager=self.db_manager, settings_manager=self.settings_manager, parent=self)
        if dlg.exec() == TaskDialog.Accepted:
            updated_task = dlg.get_task()
            self.task_controller.update_task(updated_task)
