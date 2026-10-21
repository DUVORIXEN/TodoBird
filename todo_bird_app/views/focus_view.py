import os
import sys
import logging
import time
from datetime import datetime
from typing import List, Optional

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QLineEdit, QMessageBox, QComboBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from todo_bird_app.views.base_view import BaseView
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.controllers.delay_engine import DelayEngine, TimingStatus
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.widgets.three_w_one_h_dialog import ThreeWOneHDialog
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.services.typography_service import TypographyService

logger = logging.getLogger(__name__)


class FocusView(BaseView):
    """
    Distraction-free Focus Workspace for timeboxing active tasks.
    Includes explicit task selection, monotonic live timer, pause/resume/end state machine,
    and single-authority Actual execution persistence.
    """
    def __init__(self, db_manager, settings_manager=None, parent=None):
        task_controller = None
        if isinstance(db_manager, TaskController) and settings_manager is None:
            task_controller = db_manager
            db_manager = task_controller.db_manager
            from todo_bird_app.settings.settings_manager import SettingsManager
            settings_manager = SettingsManager(db_manager)

        super().__init__(
            db_manager, settings_manager,
            title="Focus Mode", subtitle="Distraction-free timeboxing for active tasks",
            parent=parent, typography_area="focus"
        )
        self._owns_task_controller = task_controller is None
        self._cleaned_up = False
        self.task_controller = task_controller or TaskController(db_manager)
        self._connect_task_controller_signal(
            "tasks_changed",
            self._on_external_tasks_changed,
        )

        self.current_task: Optional[Task] = None
        self.elapsed_seconds = 0
        self.state = "IDLE"  # IDLE | RUNNING | PAUSED
        self._last_tick_monotonic = 0.0

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._on_timer_tick)
        self.timer.start()

        self._init_ui()
        self.refresh_data()

    def cleanup(self):
        """Stops timers and releases event-bus subscriptions on shutdown."""
        if getattr(self, "_cleaned_up", False):
            return
        self._cleaned_up = True
        self.state = "IDLE"
        if hasattr(self, "timer") and self.timer is not None:
            try:
                self.timer.stop()
            except Exception:
                pass
        try:
            super().cleanup()
        except Exception:
            pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def deleteLater(self):
        self.cleanup()
        super().deleteLater()

    def _init_ui(self):
        container = QFrame()
        container.setObjectName("CardWidget")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        # 1. Explicit Task Selector Bar
        selector_card = QFrame()
        selector_card.setStyleSheet("background: rgba(255, 255, 255, 0.04); border-radius: 8px; padding: 6px;")
        selector_layout = QHBoxLayout(selector_card)
        selector_layout.setContentsMargins(8, 4, 8, 4)
        selector_layout.setSpacing(12)

        lbl_select = QLabel("Focus Target:")
        lbl_select.setStyleSheet(
            "font-weight: 700; color: inherit;"
        )
        TypographyService.set_relative_font_role(
            lbl_select,
            delta_pt=2,
            weight="bold",
        )
        selector_layout.addWidget(lbl_select)

        self.task_selector_combo = QComboBox()
        self.task_selector_combo.setFixedHeight(36)
        self.task_selector_combo.currentIndexChanged.connect(self._on_selector_index_changed)
        selector_layout.addWidget(self.task_selector_combo, 1)

        layout.addWidget(selector_card)

        # 2. Header Task Title
        self.lbl_task_title = QLabel("Select a task to enter Focus Mode")
        self.lbl_task_title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(
            self.lbl_task_title,
            delta_pt=10,
            weight="bold",
        )
        self.lbl_task_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.lbl_task_title)

        # 3. Meta & Project Info
        self.lbl_meta = QLabel("Select a task above")
        self.lbl_meta.setAlignment(Qt.AlignCenter)
        self.lbl_meta.setStyleSheet(
            "color: #9CA3AF;"
        )
        layout.addWidget(self.lbl_meta)

        # 4. Big Timer Display
        self.lbl_timer = QLabel("00:00:00")
        timer_font = QFont("Monospace", 48)
        timer_font.setBold(True)
        self.lbl_timer.setFont(timer_font)
        self.lbl_timer.setAlignment(Qt.AlignCenter)
        self.lbl_timer.setStyleSheet("color: #3584E4; margin: 12px 0;")
        layout.addWidget(self.lbl_timer)

        # 5. Remaining Time & Planned Stats
        self.lbl_remaining = QLabel("Planned: 0m • Elapsed: 0m • Remaining: 0m")
        self.lbl_remaining.setAlignment(Qt.AlignCenter)
        self.lbl_remaining.setStyleSheet(
            "color: #10B981; font-weight: 600;"
        )
        layout.addWidget(self.lbl_remaining)

        # 5b. Velocity & Start Intelligence Banner
        self.lbl_velocity_banner = QLabel("")
        self.lbl_velocity_banner.setAlignment(Qt.AlignCenter)
        self.lbl_velocity_banner.setWordWrap(True)
        self.lbl_velocity_banner.hide()
        layout.addWidget(self.lbl_velocity_banner)

        # 6. Action Buttons Row (Start/Pause/Resume, End Session, Complete Task, 3W1H)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        self.btn_toggle = QPushButton("▶ Start Focus")
        self.btn_toggle.setObjectName("PrimaryButton")
        self.btn_toggle.setFixedHeight(42)
        self.btn_toggle.setMinimumWidth(145)
        self.btn_toggle.clicked.connect(self.toggle_focus_timer)
        btn_layout.addWidget(self.btn_toggle)

        self.btn_end = QPushButton("⏹ End Session")
        self.btn_end.setFixedHeight(42)
        self.btn_end.setMinimumWidth(135)
        self.btn_end.setEnabled(False)
        self.btn_end.clicked.connect(self.end_focus_session)
        btn_layout.addWidget(self.btn_end)

        self.btn_3w1h = QPushButton("3W1H Reflection")
        self.btn_3w1h.setFixedHeight(42)
        self.btn_3w1h.setStyleSheet("background: rgba(245, 158, 11, 0.15); color: #F59E0B; font-weight: 600; padding: 0 12px; border-radius: 6px;")
        self.btn_3w1h.clicked.connect(self.open_3w1h_dialog)
        self.btn_3w1h.hide()
        btn_layout.addWidget(self.btn_3w1h)

        self.btn_complete = QPushButton("Complete Task")
        self.btn_complete.setFixedHeight(42)
        self.btn_complete.setMinimumWidth(145)
        self.btn_complete.clicked.connect(self.complete_focus_task)
        btn_layout.addWidget(self.btn_complete)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 7. Distraction Capture Section
        notes_frame = QFrame()
        notes_layout = QVBoxLayout(notes_frame)
        notes_layout.setContentsMargins(0, 8, 0, 0)
        lbl_distract = QLabel(" Quick Distraction Note Capture")
        lbl_distract.setStyleSheet(
            "font-weight: 600; color: #9CA3AF;"
        )
        notes_layout.addWidget(lbl_distract)

        self.txt_note = QLineEdit()
        self.txt_note.setPlaceholderText("Capture thoughts or interruptions without leaving focus...")
        self.txt_note.returnPressed.connect(self.add_distraction_note)
        notes_layout.addWidget(self.txt_note)

        layout.addWidget(notes_frame)
        self.main_layout.addWidget(container, 1)

    # --------------------------------------------------------------------------
    # ELIGIBLE TASK SELECTION & REFRESH
    # --------------------------------------------------------------------------
    def get_eligible_tasks(self) -> List[Task]:
        all_tasks = self.task_controller.get_all_tasks()
        return [
            t for t in all_tasks
            if t.status not in (TaskStatus.COMPLETED, TaskStatus.CANCELLED)
        ]

    def refresh_data(self):
        super().refresh_data()
        eligible = self.get_eligible_tasks()
        current_id = self.current_task.id if self.current_task else None

        self.task_selector_combo.blockSignals(True)
        self.task_selector_combo.clear()

        if not eligible:
            self.task_selector_combo.addItem("No active tasks available", None)
            self.current_task = None
            self._update_task_ui()
            self.task_selector_combo.blockSignals(False)
            return

        selected_idx = 0
        for idx, task in enumerate(eligible):
            date_str = f" • Planned {task.planned_date}" if task.planned_date else ""
            prio_str = f" • {task.priority.value} priority" if task.priority else ""
            label = f"{task.title}{date_str}{prio_str} [{task.status.value}]"
            self.task_selector_combo.addItem(label, task.id)
            if current_id is not None and task.id == current_id:
                selected_idx = idx

        self.task_selector_combo.setCurrentIndex(selected_idx)
        self.task_selector_combo.blockSignals(False)

        # Retain or set selected task
        selected_task_id = self.task_selector_combo.currentData()
        if selected_task_id:
            self.select_task_by_id(selected_task_id)

    def _on_selector_index_changed(self, index: int):
        task_id = self.task_selector_combo.itemData(index)
        if task_id:
            # If a session was actively running, pause or end before switching
            if self.state in ("RUNNING", "PAUSED"):
                self.end_focus_session()
            self.select_task_by_id(task_id)

    def select_task_by_id(self, task_id: int):
        task = self.task_controller.get_task(task_id)
        if not task:
            return
        self.current_task = task
        self.elapsed_seconds = (task.actual_duration or 0) * 60
        self._update_task_ui()

    def _update_task_ui(self):
        if not self.current_task:
            eligible = self.get_eligible_tasks()
            if not eligible:
                self.lbl_task_title.setText("No active tasks available")
                self.lbl_meta.setText("Create a task or schedule tasks for Today to begin focusing")
            else:
                self.lbl_task_title.setText("Select a task to enter Focus Mode")
                self.lbl_meta.setText("Choose a focus target from the dropdown above")
            self.lbl_timer.setText("00:00:00")
            self.lbl_remaining.setText("Planned: 0m • Elapsed: 0m • Remaining: 0m")
            self.btn_toggle.setEnabled(False)
            self.btn_end.setEnabled(False)
            self.btn_complete.setEnabled(False)
            return

        self.btn_toggle.setEnabled(True)
        self.btn_complete.setEnabled(True)
        self.lbl_task_title.setText(self.current_task.title)
        category = self.current_task.category or "Inbox"
        priority = self.current_task.priority.value if self.current_task.priority else "Medium"
        planned_time = f" • {self.current_task.planned_start_time}–{self.current_task.planned_end_time}" if self.current_task.planned_start_time else ""
        self.lbl_meta.setText(f"{category} • {priority} Priority{planned_time}")
        self._update_timer_display()

        # Start timing velocity & delay reflection.
        engine = DelayEngine(self.settings_manager)
        timing_status, diff_mins = engine.evaluate_start_timing(self.current_task)

        if timing_status == TimingStatus.EARLY_START:
            early_str = f"{diff_mins // 60}h {diff_mins % 60}m" if diff_mins >= 60 else f"{diff_mins}m"
            self.lbl_velocity_banner.setText(f"Early Start: Outstanding momentum! Starting {early_str} ahead of schedule!")
            self.lbl_velocity_banner.setStyleSheet(
                "color: #10B981; font-weight: 700; "
                "background: rgba(16, 185, 129, 0.12); "
                "padding: 8px; border-radius: 6px; margin: 4px 0;"
            )
            self.lbl_velocity_banner.show()
            self.btn_3w1h.hide()
        elif timing_status == TimingStatus.DELAYED_START:
            slip_str = f"{diff_mins // 60}h {diff_mins % 60}m" if diff_mins >= 60 else f"{diff_mins}m"
            self.lbl_velocity_banner.setStyleSheet(
                "color: #F59E0B; font-weight: 600; "
                "background: rgba(245, 158, 11, 0.12); "
                "padding: 8px; border-radius: 6px; margin: 4px 0;"
            )
            self.lbl_velocity_banner.setText(
                f"Schedule Slip: Task started past planned schedule (+{slip_str})."
            )
            self.lbl_velocity_banner.show()
            self.btn_3w1h.show()
        else:
            self.lbl_velocity_banner.hide()
            self.btn_3w1h.hide()

    def open_new_task_dialog(self):
        projects = self.task_controller.get_all_projects()
        dlg = TaskDialog(projects, db_manager=self.db_manager, settings_manager=self.settings_manager, parent=self)
        if dlg.exec() == TaskDialog.Accepted:
            new_task = dlg.get_task()
            self.task_controller.add_task(new_task)
            self.refresh_data()

    def open_3w1h_dialog(self):
        if not self.current_task:
            return
        engine = DelayEngine(self.settings_manager)
        _, diff_mins = engine.evaluate_start_timing(self.current_task)
        dlg = ThreeWOneHDialog(self.current_task, delay_minutes=diff_mins, parent=self)
        if dlg.exec() == ThreeWOneHDialog.Accepted:
            import html as html_mod
            reflection = dlg.get_reflection_text()
            current_desc = self.current_task.description or ""
            escaped_reflection = html_mod.escape(reflection)
            reflection_html = f"<p>{escaped_reflection}</p>"
            self.current_task.description = current_desc + reflection_html
            self.task_controller.update_task(self.current_task)

    def _on_external_tasks_changed(self):
        # Refresh task selector and current task without interrupting a live running timer
        try:
            if not getattr(self, "task_controller", None) or not getattr(self, "db_manager", None):
                return
            if self.state == "IDLE":
                self.refresh_data()
            elif self.current_task and self.current_task.id is not None:
                updated = self.task_controller.get_task(self.current_task.id)
                if updated and updated.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
                    self.end_focus_session()
                    self.refresh_data()
        except Exception:
            pass

    # --------------------------------------------------------------------------
    # STATE MACHINE & EXECUTION LIFECYCLE
    # --------------------------------------------------------------------------
    def toggle_focus_timer(self):
        if not self.current_task:
            return
        if self.state == "IDLE":
            self.start_focus_session()
        elif self.state == "RUNNING":
            self.pause_focus_session()
        elif self.state == "PAUSED":
            self.resume_focus_session()

    def start_focus_session(self):
        if not self.current_task or self.state == "RUNNING":
            return

        now = datetime.now()
        # Record actual_start_date and actual_start_time exactly once on first start
        if not self.current_task.actual_start_date:
            self.current_task.actual_start_date = now.strftime("%Y-%m-%d")
        if not self.current_task.actual_start_time:
            self.current_task.actual_start_time = now.strftime("%H:%M")

        # Promote status to In Progress
        if self.current_task.status in (TaskStatus.INBOX, TaskStatus.PLANNED):
            self.current_task.status = TaskStatus.IN_PROGRESS

        self.task_controller.update_task(self.current_task)

        self.state = "RUNNING"
        self._last_tick_monotonic = time.monotonic()
        self.timer.start()
        self.btn_toggle.setText("⏸ Pause Focus")
        self.btn_end.setEnabled(True)
        self.task_selector_combo.setEnabled(False)

    def pause_focus_session(self):
        if self.state != "RUNNING":
            return

        self.timer.stop()
        self.state = "PAUSED"
        self.btn_toggle.setText("▶ Resume Focus")
        self._persist_current_duration()

    def resume_focus_session(self):
        if self.state != "PAUSED" or not self.current_task:
            return

        self.state = "RUNNING"
        self._last_tick_monotonic = time.monotonic()
        self.timer.start()
        self.btn_toggle.setText("⏸ Pause Focus")

    def end_focus_session(self):
        if not self.current_task:
            return

        self.timer.stop()
        self.state = "IDLE"
        self.btn_toggle.setText("▶ Start Focus")
        self.btn_end.setEnabled(False)
        self.task_selector_combo.setEnabled(True)
        now = datetime.now()
        # Ending "now" must move BOTH end fields together: keeping a stale
        # end_date from a previous session while writing a fresh end_time
        # manufactures finish-before-start records (hard invariant violation).
        self.current_task.actual_end_date = now.strftime("%Y-%m-%d")
        self.current_task.actual_end_time = now.strftime("%H:%M")
        self._persist_current_duration()

    def complete_focus_task(self):
        if not self.current_task:
            return

        self.timer.stop()
        self.state = "IDLE"
        self.btn_toggle.setText("▶ Start Focus")
        self.btn_end.setEnabled(False)
        self.task_selector_combo.setEnabled(True)

        now = datetime.now()
        if not self.current_task.actual_start_date:
            self.current_task.actual_start_date = now.strftime("%Y-%m-%d")
        self.current_task.actual_end_date = now.strftime("%Y-%m-%d")
        self.current_task.actual_end_time = now.strftime("%H:%M")
        self.current_task.actual_duration = max(1, self.elapsed_seconds // 60)
        self.current_task.status = TaskStatus.COMPLETED
        self.current_task.progress = 100

        task_title = self.current_task.title
        act_dur = self.current_task.actual_duration

        self.task_controller.update_task(self.current_task)
        if "pytest" not in sys.modules and not os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") and not os.environ.get("QT_QPA_PLATFORM"):
            try:
                QMessageBox.information(
                    self, "Task Completed",
                    f" Task \"{task_title}\" marked as completed!\nActual duration: {act_dur} min"
                )
            except Exception:
                pass
        self.refresh_data()

    # --------------------------------------------------------------------------
    # TIMING & CONTROLLED PERSISTENCE
    # --------------------------------------------------------------------------
    def _on_timer_tick(self):
        if self.state != "RUNNING":
            return

        self.elapsed_seconds += 1
        self._update_timer_display()

        # Controlled persistence cadence: Save every 30 seconds to DB (never every 1s)
        if self.current_task and self.elapsed_seconds % 30 == 0:
            self._persist_current_duration()

    def _persist_current_duration(self):
        if not self.current_task:
            return
        calculated_mins = self.elapsed_seconds // 60
        if self.current_task.actual_duration != calculated_mins:
            self.current_task.actual_duration = calculated_mins
            self.task_controller.update_task(self.current_task)

    def _update_timer_display(self):
        hrs = self.elapsed_seconds // 3600
        mins = (self.elapsed_seconds % 3600) // 60
        secs = self.elapsed_seconds % 60
        self.lbl_timer.setText(f"{hrs:02d}:{mins:02d}:{secs:02d}")

        if self.current_task:
            est_mins = self.current_task.estimated_duration or 0
            act_mins = self.elapsed_seconds // 60
            rem_mins = max(0, est_mins - act_mins)
            self.lbl_remaining.setText(f"Planned: {est_mins}m • Elapsed: {act_mins}m • Remaining: {rem_mins}m")

    def add_distraction_note(self):
        note_text = self.txt_note.text().strip()
        if note_text and self.current_task:
            current_notes = self.current_task.notes or ""
            timestamp = datetime.now().strftime("%H:%M")
            self.current_task.notes = (current_notes + f"\n• [{timestamp} Focus Note]: {note_text}").strip()
            self.task_controller.update_task(self.current_task)
            self.txt_note.clear()
            if not os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") and not os.environ.get("QT_QPA_PLATFORM"):
                try:
                    QMessageBox.information(self, "Note Captured", f"Captured note: \"{note_text}\"")
                except Exception:
                    pass
