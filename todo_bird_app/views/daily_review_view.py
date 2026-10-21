from datetime import date
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget, QFrame, QGridLayout, QProgressBar
)
from PySide6.QtCore import Qt

from todo_bird_app.views.base_view import BaseView
from todo_bird_app.controllers.review_controller import ReviewController
from todo_bird_app.utils.time_math import format_duration_display
from todo_bird_app.services.typography_service import TypographyService

class DailyReviewView(BaseView):
    """
    Daily Review — Morning Plan vs Evening Actual Comparison & Productivity Analytics.
    Renders 4 clear sections: Today Overview, Work Effort Balance, Carryover, and Tomorrow Commitments.
    """
    def __init__(self, db_manager, settings_manager, parent=None):
        super().__init__(db_manager, settings_manager, title="Daily Review", subtitle="Morning planning & Evening Plan vs Actual review", parent=parent, typography_area="review")
        self.review_controller = ReviewController(db_manager, settings_manager=settings_manager)
        self._init_ui()
        self.refresh_data()

    def _init_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # 1. Productivity Breakdown Summary Card
        prod_card = QFrame()
        prod_card.setObjectName("CardWidget")
        card_layout = QVBoxLayout(prod_card)

        card_title = QLabel("Today's Productivity & Execution Health")
        card_title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(card_title, delta_pt=4, weight="bold")
        card_layout.addWidget(card_title)

        grid = QGridLayout()
        grid.setSpacing(16)

        self.prod_score_lbl = QLabel("100.0%")
        self.prod_score_lbl.setStyleSheet("color: #10B981;")

        self.completed_lbl = QLabel("0 Completed")
        self.completed_lbl.setStyleSheet("color: #10B981;")

        self.delayed_lbl = QLabel("0 Delayed")
        self.delayed_lbl.setStyleSheet("color: #EF4444;")

        self.moved_lbl = QLabel("0 Moved")
        self.moved_lbl.setStyleSheet("color: #E95420;")

        self.cancelled_lbl = QLabel("0 Cancelled")
        self.cancelled_lbl.setStyleSheet("color: #9CA3AF;")

        grid.addWidget(QLabel("Productivity Score:"), 0, 0)
        grid.addWidget(self.prod_score_lbl, 1, 0)

        grid.addWidget(self.completed_lbl, 0, 1)
        grid.addWidget(self.delayed_lbl, 1, 1)
        grid.addWidget(self.moved_lbl, 0, 2)
        grid.addWidget(self.cancelled_lbl, 1, 2)

        card_layout.addLayout(grid)
        layout.addWidget(prod_card)

        # 2. Plan vs Actual Split Columns (Morning vs Evening)
        split_layout = QHBoxLayout()
        split_layout.setSpacing(16)

        # Today Overview (Morning Plan + Overdue)
        today_card = QFrame()
        today_card.setObjectName("CardWidget")
        m_layout = QVBoxLayout(today_card)
        m_title = QLabel(" Today: Planned & Overdue")
        m_title.setStyleSheet("color: #3584E4; font-weight: 700;")
        TypographyService.set_relative_font_role(m_title, delta_pt=3, weight="bold")
        m_layout.addWidget(m_title)

        self.morning_tasks_lbl = QLabel("No tasks planned for today.")
        self.morning_tasks_lbl.setStyleSheet("color: #9CA3AF; line-height: 1.4;")
        m_layout.addWidget(self.morning_tasks_lbl)
        m_layout.addStretch()

        # Effort Balance Card
        effort_card = QFrame()
        effort_card.setObjectName("CardWidget")
        e_layout = QVBoxLayout(effort_card)
        e_title = QLabel("Work Effort & Capacity")
        e_title.setStyleSheet("color: #10B981; font-weight: 700;")
        TypographyService.set_relative_font_role(e_title, delta_pt=3, weight="bold")
        e_layout.addWidget(e_title)

        self.effort_summary_lbl = QLabel("Effort stats loading...")
        self.effort_summary_lbl.setStyleSheet("color: #9CA3AF; line-height: 1.4;")
        e_layout.addWidget(self.effort_summary_lbl)
        e_layout.addStretch()

        split_layout.addWidget(today_card, 1)
        split_layout.addWidget(effort_card, 1)
        layout.addLayout(split_layout)

        # 3. Carryover & Tomorrow Split Columns
        split_layout_bottom = QHBoxLayout()
        split_layout_bottom.setSpacing(16)

        # Carryover Card
        carry_card = QFrame()
        carry_card.setObjectName("CardWidget")
        c_layout = QVBoxLayout(carry_card)
        c_title = QLabel("↪ Carryover (Unfinished from Prior Days)")
        c_title.setStyleSheet("color: #F59E0B; font-weight: 700;")
        TypographyService.set_relative_font_role(c_title, delta_pt=3, weight="bold")
        c_layout.addWidget(c_title)

        self.carryover_lbl = QLabel("No pending tasks from previous days.")
        self.carryover_lbl.setStyleSheet("color: #9CA3AF; line-height: 1.4;")
        c_layout.addWidget(self.carryover_lbl)
        c_layout.addStretch()

        # Tomorrow Card
        tomorrow_card = QFrame()
        tomorrow_card.setObjectName("CardWidget")
        tom_layout = QVBoxLayout(tomorrow_card)
        tom_title = QLabel("Tomorrow: Upcoming Commitments")
        tom_title.setStyleSheet("color: #8B5CF6; font-weight: 700;")
        TypographyService.set_relative_font_role(tom_title, delta_pt=3, weight="bold")
        tom_layout.addWidget(tom_title)

        self.tomorrow_lbl = QLabel("No tasks scheduled for tomorrow yet.")
        self.tomorrow_lbl.setStyleSheet("color: #9CA3AF; line-height: 1.4;")
        tom_layout.addWidget(self.tomorrow_lbl)
        tom_layout.addStretch()

        split_layout_bottom.addWidget(carry_card, 1)
        split_layout_bottom.addWidget(tomorrow_card, 1)
        layout.addLayout(split_layout_bottom)

        scroll.setWidget(container)
        self.main_layout.addWidget(scroll, 1)

    def refresh_data(self):
        super().refresh_data()
        summary = self.review_controller.get_daily_review_summary()

        self.prod_score_lbl.setText(f"{summary['productivity_score']}%")
        self.completed_lbl.setText(f"{summary['completed_count']} Completed")
        self.moved_lbl.setText(f"↪ {summary['moved_count']} Moved")
        self.cancelled_lbl.setText(f" {summary['cancelled_count']} Cancelled")

        # Today Overview: planned tasks & overdue tasks
        planned = summary["planned_tasks"]
        overdue = summary["overdue_tasks"]
        t_lines = []
        if planned:
            t_lines.append(f"<b>Planned Today ({len(planned)}):</b>")
            for t in planned:
                st = f" [{t.status.value}]" if t.status.value != "Planned" else ""
                t_lines.append(f"• {t.title}{st}")
        else:
            t_lines.append("No tasks were planned specifically for today.")

        if overdue:
            t_lines.append(f"<br><b>Overdue Active ({len(overdue)}):</b>")
            for t in overdue[:5]:
                t_lines.append(f"• {t.title} (Due: {t.due_date})")
        self.morning_tasks_lbl.setText("<br>".join(t_lines))

        # Effort Balance: Planned Effort, Actual Effort, Capacity, Remaining
        p_eff = summary["planned_effort_total"]
        a_eff = summary["act_duration_total"]
        cap = summary["daily_capacity"]
        rem = summary["remaining_capacity"]

        e_lines = [
            f"<b>Planned Effort Today:</b> {format_duration_display(p_eff)} ({p_eff} mins)",
            f"<b>Actual Effort Logged:</b> {format_duration_display(a_eff)} ({a_eff} mins)",
            f"<b>Target Daily Capacity:</b> {format_duration_display(cap)} ({cap} mins)",
            f"<b>Remaining Daily Headroom:</b> {format_duration_display(rem)} ({rem} mins)",
        ]
        self.effort_summary_lbl.setText("<br>".join(e_lines))

        # Carryover
        carry = summary["carryover_tasks"]
        if carry:
            c_lines = [f"<b>{len(carry)} Unfinished tasks:</b>"]
            for t in carry[:6]:
                c_lines.append(f"• {t.title} (Planned: {t.planned_date})")
            self.carryover_lbl.setText("<br>".join(c_lines))
        else:
            self.carryover_lbl.setText(" Zero carryover backlog from prior days!")

        # Tomorrow
        tomorrow = summary["tomorrow_tasks"]
        if tomorrow:
            tom_lines = [f"<b>{len(tomorrow)} Tasks scheduled:</b>"]
            for t in tomorrow[:6]:
                tom_lines.append(f"• {t.title} ({t.priority.value})")
            self.tomorrow_lbl.setText("<br>".join(tom_lines))
        else:
            self.tomorrow_lbl.setText("No tasks scheduled for tomorrow yet.")
