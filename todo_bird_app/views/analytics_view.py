from collections import Counter
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QFrame, QGridLayout, QScrollArea, QWidget, QComboBox, QPushButton, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt

from todo_bird_app.views.base_view import BaseView
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.controllers.delay_engine import DelayEngine, TimingStatus
from todo_bird_app.services.report_exporter import ReportExporterService
from todo_bird_app.services.typography_service import TypographyService
from todo_bird_app.models.task import TaskStatus

class AnalyticsView(BaseView):
    """
    Enhanced Analytics View — Productivity intelligence, planned vs actual hours,
    planning accuracy, delay reasons, and recovery metrics.
    """
    def __init__(self, db_manager, settings_manager, parent=None):
        super().__init__(db_manager, settings_manager, title="Productivity Analytics", subtitle="Track execution rates, completion trends & efficiency", parent=parent, typography_area="analytics")
        self.task_controller = TaskController(db_manager)
        self._connect_task_controller_signal("tasks_changed", self.refresh_data)
        self.delay_engine = DelayEngine(settings_manager)
        self._init_ui()
        self.refresh_data()

    def _init_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(16)

        # Export Action Row
        export_row = QHBoxLayout()
        export_pdf_btn = QPushButton(" Export PDF Report")
        export_pdf_btn.clicked.connect(self.export_pdf)
        export_csv_btn = QPushButton("Export CSV Data")
        export_csv_btn.clicked.connect(self.export_csv)
        export_row.addStretch()
        export_row.addWidget(export_pdf_btn)
        export_row.addWidget(export_csv_btn)
        layout.addLayout(export_row)

        # Overview Grid
        grid_card = QFrame()
        grid_card.setObjectName("CardWidget")
        g_layout = QGridLayout(grid_card)
        g_layout.setSpacing(16)

        self.lbl_planned_hrs = QLabel("0.0h")
        self.lbl_planned_hrs.setStyleSheet("font-weight: 800; color: #3584E4;")
        TypographyService.set_relative_font_role(self.lbl_planned_hrs, delta_pt=12, weight="bold")

        self.lbl_actual_hrs = QLabel("0.0h")
        self.lbl_actual_hrs.setStyleSheet("font-weight: 800; color: #10B981;")
        TypographyService.set_relative_font_role(self.lbl_actual_hrs, delta_pt=12, weight="bold")

        self.lbl_accuracy = QLabel("100.0%")
        self.lbl_accuracy.setStyleSheet("font-weight: 800; color: #E95420;")
        TypographyService.set_relative_font_role(self.lbl_accuracy, delta_pt=12, weight="bold")

        self.lbl_early_count = QLabel("0")
        self.lbl_early_count.setStyleSheet("font-weight: 800; color: #065F46;")
        TypographyService.set_relative_font_role(self.lbl_early_count, delta_pt=12, weight="bold")

        self.lbl_ontime_count = QLabel("0")
        self.lbl_ontime_count.setStyleSheet("font-weight: 800; color: #10B981;")
        TypographyService.set_relative_font_role(self.lbl_ontime_count, delta_pt=12, weight="bold")

        self.lbl_delayed_count = QLabel("0")
        self.lbl_delayed_count.setStyleSheet("font-weight: 800; color: #EF4444;")
        TypographyService.set_relative_font_role(self.lbl_delayed_count, delta_pt=12, weight="bold")

        g_layout.addWidget(QLabel("Planned Hours"), 0, 0)
        g_layout.addWidget(self.lbl_planned_hrs, 1, 0)

        g_layout.addWidget(QLabel("Actual Hours"), 0, 1)
        g_layout.addWidget(self.lbl_actual_hrs, 1, 1)

        g_layout.addWidget(QLabel("Planning Accuracy"), 0, 2)
        g_layout.addWidget(self.lbl_accuracy, 1, 2)

        g_layout.addWidget(QLabel("Completed Early"), 2, 0)
        g_layout.addWidget(self.lbl_early_count, 3, 0)

        g_layout.addWidget(QLabel("Completed On Time"), 2, 1)
        g_layout.addWidget(self.lbl_ontime_count, 3, 1)

        g_layout.addWidget(QLabel("Delayed Tasks"), 2, 2)
        g_layout.addWidget(self.lbl_delayed_count, 3, 2)

        layout.addWidget(grid_card)

        # Detailed Breakdown Grid
        detail_layout = QHBoxLayout()
        detail_layout.setSpacing(16)

        # Delay Analysis Card
        delay_card = QFrame()
        delay_card.setObjectName("CardWidget")
        d_layout = QVBoxLayout(delay_card)
        delay_title = QLabel("Delay & Recovery Metrics")
        delay_title.setStyleSheet("font-weight: 700; color: inherit;")
        TypographyService.set_relative_font_role(delay_title, delta_pt=4, weight="bold")
        d_layout.addWidget(delay_title)

        self.lbl_avg_delay = QLabel("Average Delay: 0 mins")
        self.lbl_avg_delay.setStyleSheet("font-weight: 600; color: inherit;")
        TypographyService.set_relative_font_role(self.lbl_avg_delay, delta_pt=2, weight="semibold")
        d_layout.addWidget(self.lbl_avg_delay)

        self.lbl_common_reason = QLabel("Most Common Reason: None")
        self.lbl_common_reason.setStyleSheet("color: #9CA3AF;")
        TypographyService.set_relative_font_role(self.lbl_common_reason, delta_pt=2)
        d_layout.addWidget(self.lbl_common_reason)

        self.lbl_recovered_count = QLabel("Recovered Tasks: 0")
        self.lbl_recovered_count.setStyleSheet("color: #10B981; font-weight: 600;")
        TypographyService.set_relative_font_role(self.lbl_recovered_count, delta_pt=2, weight="semibold")
        d_layout.addWidget(self.lbl_recovered_count)

        d_layout.addStretch()

        # Priority Breakdown Card
        prio_card = QFrame()
        prio_card.setObjectName("CardWidget")
        p_layout = QVBoxLayout(prio_card)
        p_layout.addWidget(QLabel("Task Priority Distribution"))
        self.prio_info_lbl = QLabel("No data")
        self.prio_info_lbl.setStyleSheet("color: #9CA3AF;")
        p_layout.addWidget(self.prio_info_lbl)
        p_layout.addStretch()

        detail_layout.addWidget(delay_card, 1)
        detail_layout.addWidget(prio_card, 1)

        layout.addLayout(detail_layout)

        scroll.setWidget(container)
        self.main_layout.addWidget(scroll, 1)

    def refresh_data(self):
        super().refresh_data()
        tasks = self.task_controller.get_all_tasks()
        total = len(tasks)
        if total == 0:
            self.lbl_planned_hrs.setText("0.0h")
            self.lbl_actual_hrs.setText("0.0h")
            self.lbl_accuracy.setText("100.0%")
            self.lbl_early_count.setText("0")
            self.lbl_ontime_count.setText("0")
            self.lbl_delayed_count.setText("0")
            self.lbl_avg_delay.setText("Average Delay: 0 mins")
            self.lbl_common_reason.setText("Most Common Reason: None")
            self.lbl_recovered_count.setText("Recovered Tasks: 0")
            self.prio_info_lbl.setText("No task activity data yet. Complete tasks and focus sessions to generate analytics.")
            return

        planned_mins = sum(t.estimated_duration for t in tasks)
        actual_mins = sum(t.actual_duration for t in tasks)

        self.lbl_planned_hrs.setText(f"{planned_mins / 60.0:.1f}h")
        self.lbl_actual_hrs.setText(f"{actual_mins / 60.0:.1f}h")

        # Calculate accuracy. With nothing planned but real work logged, calling
        # it "100% accurate" is misleading — zero planning accuracy is honest.
        if planned_mins > 0:
            diff = abs(actual_mins - planned_mins)
            accuracy = max(0.0, round((1.0 - diff / planned_mins) * 100.0, 1))
        elif actual_mins > 0:
            accuracy = 0.0
        else:
            accuracy = 100.0
        self.lbl_accuracy.setText(f"{accuracy}%")

        # Classify timing statuses
        early_cnt, ontime_cnt, delayed_cnt, recovered_cnt = 0, 0, 0, 0
        delays_list = []
        reasons = []

        for t in tasks:
            status, delay_mins, _ = self.delay_engine.analyze_task_timing(t)
            if t.status == TaskStatus.COMPLETED:
                if status == TimingStatus.COMPLETED_BEFORE_TIME:
                    early_cnt += 1
                elif status == TimingStatus.COMPLETED_ON_TIME:
                    ontime_cnt += 1
                else:
                    delayed_cnt += 1
            elif delay_mins > 0:
                delayed_cnt += 1

            if delay_mins > 0:
                delays_list.append(delay_mins)
            if t.delay_reason:
                reasons.append(t.delay_reason)

        # "Recovered" = tasks the user logged a delay against (delay_minutes)
        # that were STILL completed — late start, on-time finish. Counting the
        # timing-classified late completions here was a tautology (recovered
        # == delayed by construction).
        recovered_cnt = sum(
            1
            for t in tasks
            if t.status == TaskStatus.COMPLETED
            and int(getattr(t, "delay_minutes", 0) or 0) > 0
        )

        self.lbl_early_count.setText(str(early_cnt))
        self.lbl_ontime_count.setText(str(ontime_cnt))
        self.lbl_delayed_count.setText(str(delayed_cnt))

        avg_delay = round(sum(delays_list) / len(delays_list), 1) if delays_list else 0
        self.lbl_avg_delay.setText(f"Average Delay: {avg_delay} mins")

        common_reason = Counter(reasons).most_common(1)
        self.lbl_common_reason.setText(f"Most Common Reason: {common_reason[0][0]}" if common_reason else "Most Common Reason: None")
        self.lbl_recovered_count.setText(f"Recovered Delayed Tasks: {recovered_cnt}")

        prio_counts = Counter(t.priority.value for t in tasks)
        p_lines = [f"• {k}: {v} tasks" for k, v in prio_counts.items()]
        self.prio_info_lbl.setText("\n".join(p_lines))

    def export_pdf(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export PDF Performance Report", "todo_bird_report.pdf", "PDF Files (*.pdf)")
        if file_path:
            success = ReportExporterService.export_analytics_to_pdf(self.db_manager, file_path)
            if success:
                QMessageBox.information(self, "Export Success", f"Report successfully exported to:\n{file_path}")
            else:
                QMessageBox.warning(self, "Export Failed", "Failed to generate PDF report.")

    def export_csv(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export CSV Tasks Data", "todo_bird_tasks.csv", "CSV Files (*.csv)")
        if file_path:
            success = ReportExporterService.export_tasks_to_csv(self.db_manager, file_path)
            if success:
                QMessageBox.information(self, "Export Success", f"Tasks data successfully exported to:\n{file_path}")
            else:
                QMessageBox.warning(self, "Export Failed", "Failed to export CSV file.")
