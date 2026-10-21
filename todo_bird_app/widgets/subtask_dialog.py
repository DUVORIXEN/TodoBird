"""
TODO BIRD — SUBTASK EDIT DIALOG
Canonical modal editor for top-level and nested subtasks.
Provides deep hierarchical editing of schedule, dependencies, actuals,
governance constraints, and presentation properties.
"""

from datetime import datetime, date, time
from typing import Optional, Dict, Any, List, Union

from PySide6.QtCore import Qt, QDate, QTime, QDateTime
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QScrollArea,
    QFrame,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QSpinBox,
    QDoubleSpinBox,
    QDateEdit,
    QTimeEdit,
    QDateTimeEdit,
    QPushButton,
    QGroupBox,
    QFileDialog,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QApplication,
)

from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.services.appearance_service import AppearanceService, text_color_on
from todo_bird_app.services.wbs_service import EntityRef
from todo_bird_app.utils.time_math import combine_date_time, format_duration_display
from todo_bird_app.widgets.rich_text_editor import RichTextEditor
from todo_bird_app.widgets.task_dialog import (
    BLOCKER_CATEGORY_OPTIONS,
    WORKFLOW_STATUS_OPTIONS,
    _coerce_task_status,
)


class SubtaskDialog(QDialog):
    """
    Canonical modal dialog for editing Subtasks and nested Subtasks.
    Can operate both on a direct DB record or within parent TaskDialog.
    """

    def __init__(
        self,
        subtask: Union[Dict[str, Any], int],
        parent_task: Union[Task, int],
        db_manager: Any = None,
        settings_manager: Any = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.db_manager = db_manager
        self.settings_manager = settings_manager

        # Resolve subtask dict
        if isinstance(subtask, int):
            self.subtask_id = subtask
            self.subtask_data = self.db_manager.get_subtask_by_id(subtask) if self.db_manager else {}
            if not self.subtask_data:
                self.subtask_data = {"id": subtask, "title": f"Subtask #{subtask}"}
        elif isinstance(subtask, dict):
            self.subtask_data = dict(subtask)
            self.subtask_id = self.subtask_data.get("id")
        else:
            self.subtask_id = getattr(subtask, "id", None)
            self.subtask_data = {"id": self.subtask_id, "title": getattr(subtask, "title", "")}

        # Resolve parent task
        if isinstance(parent_task, Task):
            self.parent_task = parent_task
            self.task_id = int(parent_task.id or 0)
        else:
            self.task_id = int(parent_task or self.subtask_data.get("task_id", 0))
            if self.db_manager:
                self.parent_task = self.db_manager.get_task_by_id(self.task_id)
            else:
                self.parent_task = None

        self.setWindowTitle(f"Edit Subtask: {self.subtask_data.get('title', 'Subtask')}")
        self.setMinimumSize(480, 520)
        self.resize(580, 680)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("SubtaskDialog")

        # Theme resolution
        app = QApplication.instance()
        appearance = AppearanceService.read(self.settings_manager, app=app)
        self._is_dark = appearance.is_dark
        self._tokens = appearance.tokens
        self._accent = appearance.accent_color

        self._init_ui()
        self._apply_theme()

    def _duration_days_from_minutes(self, minutes: int) -> float:
        try:
            clean_minutes = max(0, int(minutes or 0))
        except (TypeError, ValueError):
            clean_minutes = 0
        return round(clean_minutes / 480.0, 2)

    def _duration_minutes_from_days(self, days: float) -> int:
        try:
            clean_days = max(0.0, float(days or 0.0))
        except (TypeError, ValueError):
            clean_days = 0.0
        return int(round(clean_days * 480.0))

    def _init_ui(self):
        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(12, 12, 12, 12)
        main_vbox.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        # 1. Title
        self.title_edit = QLineEdit(self.subtask_data.get("title", ""))
        self.title_edit.setObjectName("subtask_title_input")
        self.title_edit.setPlaceholderText("Subtask title...")
        form.addRow("Name", self.title_edit)

        # 2. Description
        self.description_edit = RichTextEditor(settings_manager=self.settings_manager)
        self.description_edit.setHtml(self.subtask_data.get("description", ""))
        self.description_edit.setMinimumHeight(90)
        form.addRow("Description", self.description_edit)

        # 3. Planned Start Date & Time
        self.planned_date_edit = QDateEdit()
        self.planned_date_edit.setCalendarPopup(True)
        self.planned_date_edit.setDisplayFormat("yyyy-MM-dd")
        p_val = self.subtask_data.get("planned_date")
        p_date = QDate.fromString(p_val, "yyyy-MM-dd") if p_val else QDate.currentDate()
        self.planned_date_edit.setDate(p_date if p_date.isValid() else QDate.currentDate())

        self.start_time_edit = QTimeEdit()
        self.start_time_edit.setDisplayFormat("HH:mm")
        st_val = self.subtask_data.get("planned_start_time")
        if st_val:
            self.start_time_edit.setTime(QTime.fromString(st_val, "HH:mm"))
        else:
            self.start_time_edit.setTime(QTime(9, 0))

        start_row = QHBoxLayout()
        start_row.addWidget(self.planned_date_edit, 1)
        start_row.addWidget(QLabel("at"))
        start_row.addWidget(self.start_time_edit, 1)
        form.addRow("Planned start", start_row)

        # 4. Planned Finish Date & Time
        self.finish_checkbox = QCheckBox("Specify Finish")
        self.finish_checkbox.setChecked(
            bool(self.subtask_data.get("due_date") or self.subtask_data.get("planned_end_time"))
        )

        self.due_date_edit = QDateEdit()
        self.due_date_edit.setCalendarPopup(True)
        self.due_date_edit.setDisplayFormat("yyyy-MM-dd")
        d_val = self.subtask_data.get("due_date")
        d_date = QDate.fromString(d_val, "yyyy-MM-dd") if d_val else p_date
        self.due_date_edit.setDate(d_date if d_date.isValid() else p_date)

        self.end_time_edit = QTimeEdit()
        self.end_time_edit.setDisplayFormat("HH:mm")
        et_val = self.subtask_data.get("planned_end_time")
        if et_val:
            self.end_time_edit.setTime(QTime.fromString(et_val, "HH:mm"))
        else:
            self.end_time_edit.setTime(QTime(17, 0))

        finish_row = QHBoxLayout()
        finish_row.addWidget(self.finish_checkbox)
        finish_row.addWidget(self.due_date_edit, 1)
        finish_row.addWidget(QLabel("at"))
        finish_row.addWidget(self.end_time_edit, 1)
        form.addRow("Planned finish", finish_row)

        # 5. Duration
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(0, 1000000)
        self.duration_spin.setSuffix(" mins")
        self.duration_spin.setValue(int(self.subtask_data.get("estimated_duration") or 0))

        self.duration_days_spin = QDoubleSpinBox()
        self.duration_days_spin.setRange(0.0, 10000.0)
        self.duration_days_spin.setDecimals(2)
        self.duration_days_spin.setSingleStep(0.5)
        self.duration_days_spin.setSuffix(" days")
        self.duration_days_spin.setValue(self._duration_days_from_minutes(self.duration_spin.value()))

        dur_row = QHBoxLayout()
        dur_row.addWidget(self.duration_days_spin, 1)
        dur_row.addWidget(self.duration_spin, 1)
        form.addRow("Duration", dur_row)

        # Wire duration & finish calculation
        self._syncing_duration = False

        def on_duration_mins_changed(val: int):
            if self._syncing_duration:
                return
            self._syncing_duration = True
            try:
                self.duration_days_spin.setValue(self._duration_days_from_minutes(val))
            finally:
                self._syncing_duration = False

        def on_duration_days_changed(val: float):
            if self._syncing_duration:
                return
            self._syncing_duration = True
            try:
                mins = self._duration_minutes_from_days(val)
                self.duration_spin.setValue(mins)
            finally:
                self._syncing_duration = False

        self.duration_spin.valueChanged.connect(on_duration_mins_changed)
        self.duration_days_spin.valueChanged.connect(on_duration_days_changed)

        # 6. Status & Progress
        self.status_combo = QComboBox()
        self.status_combo.setObjectName("subtask_status_combo")
        self.status_combo.setAccessibleName("Subtask status")
        self.status_combo.setFocusPolicy(Qt.StrongFocus)
        for label, status in WORKFLOW_STATUS_OPTIONS:
            self.status_combo.addItem(label, status)
        self.status_combo.view().setObjectName("subtask_status_combo_popup_view")
        default_status = (
            TaskStatus.COMPLETED
            if bool(self.subtask_data.get("is_completed"))
            or int(self.subtask_data.get("progress", 0) or 0) >= 100
            else TaskStatus.PLANNED
        )
        current_status = _coerce_task_status(
            self.subtask_data.get("status"),
            default_status,
        )
        s_idx = self.status_combo.findData(current_status)
        if s_idx >= 0:
            self.status_combo.setCurrentIndex(s_idx)

        self.progress_spin = QSpinBox()
        self.progress_spin.setRange(0, 100)
        self.progress_spin.setSuffix("%")
        self.progress_spin.setValue(int(self.subtask_data.get("progress", 0) or 0))

        stat_row = QHBoxLayout()
        stat_row.addWidget(self.status_combo, 1)
        stat_row.addWidget(QLabel("Progress:"))
        stat_row.addWidget(self.progress_spin, 1)
        form.addRow("Status", stat_row)

        self.blocker_group = QGroupBox("Blocker / Delay Management")
        blocker_form = QFormLayout(self.blocker_group)

        self.blocker_category_combo = QComboBox(self.blocker_group)
        self.blocker_category_combo.setObjectName("subtask_blocker_category_combo")
        self.blocker_category_combo.setAccessibleName("Subtask blocker or delay category")
        self.blocker_category_combo.setFocusPolicy(Qt.StrongFocus)
        self.blocker_category_combo.addItems(BLOCKER_CATEGORY_OPTIONS)
        self.blocker_category_combo.view().setObjectName(
            "subtask_blocker_category_combo_popup_view"
        )
        existing_category = (self.subtask_data.get("delay_category") or "None").strip()
        if existing_category.lower() in {"", "none", "null"}:
            existing_category = "None"
        cat_idx = self.blocker_category_combo.findText(
            existing_category,
            Qt.MatchFixedString,
        )
        if cat_idx < 0 and existing_category:
            self.blocker_category_combo.addItem(existing_category)
            cat_idx = self.blocker_category_combo.findText(
                existing_category,
                Qt.MatchFixedString,
            )
        if cat_idx >= 0:
            self.blocker_category_combo.setCurrentIndex(cat_idx)

        self.blocker_reason_input = QLineEdit(
            self.subtask_data.get("delay_reason", "") or "",
            self.blocker_group,
        )
        self.blocker_reason_input.setObjectName("subtask_blocker_reason_input")
        self.blocker_reason_input.setAccessibleName("Subtask blocker or delay reason")
        self.blocker_reason_input.setPlaceholderText(
            "What is stopping or delaying this subtask?"
        )

        self.blocker_notes_input = RichTextEditor(settings_manager=self.settings_manager)
        self.blocker_notes_input.setObjectName("subtask_blocker_notes_input")
        self.blocker_notes_input.setAccessibleName("Subtask blocker recovery notes")
        self.blocker_notes_input.setHtml(self.subtask_data.get("delay_notes", "") or "")
        self.blocker_notes_input.setPlaceholderText(
            "Owner, action required, expected resolution, decision needed..."
        )

        self.workflow_hint = QLabel()
        self.workflow_hint.setObjectName("subtask_workflow_hint")
        self.workflow_hint.setWordWrap(True)
        self.workflow_hint.setStyleSheet("font-size: 11px; opacity: 0.85;")

        blocker_form.addRow("Category", self.blocker_category_combo)
        blocker_form.addRow("Reason", self.blocker_reason_input)
        blocker_form.addRow("Recovery / Notes", self.blocker_notes_input)
        blocker_form.addRow("", self.workflow_hint)
        form.addRow("Workflow", self.blocker_group)

        self._status_blocker_delay_handler_count = 0
        self._status_blocker_delay_signal_log = []

        def update_workflow_ui(*_args):
            self._status_blocker_delay_handler_count += 1
            self._status_blocker_delay_signal_log.append(
                (
                    self.status_combo.currentIndex(),
                    self.status_combo.currentText(),
                    self.status_combo.currentData(),
                )
            )
            status = self.status_combo.currentData()
            enabled = status in (TaskStatus.BLOCKED, TaskStatus.DELAYED)
            self.blocker_category_combo.setEnabled(enabled)
            self.blocker_reason_input.setEnabled(enabled)
            self.blocker_notes_input.setEnabled(enabled)
            if status == TaskStatus.BLOCKED:
                hint = "Blocked: choose a category and record the reason before saving."
            elif status == TaskStatus.DELAYED:
                hint = "Delayed: capture the cause and recovery action before saving."
            elif status == TaskStatus.IN_PROGRESS:
                hint = "In Progress: progress represents real execution."
            elif status == TaskStatus.COMPLETED:
                hint = "Completed: saving will mark this subtask done."
            else:
                hint = "Blocker and delay fields enable only for Blocked or Delayed status."
            self.workflow_hint.setText(hint)

        self._update_status_blocker_delay_ui = update_workflow_ui
        self.status_combo.currentIndexChanged.connect(update_workflow_ui)
        self.status_combo.currentTextChanged.connect(update_workflow_ui)
        self.status_combo.activated.connect(update_workflow_ui)
        update_workflow_ui()

        # 7. Priority & Gantt
        self.priority_combo = QComboBox()
        for p in TaskPriority:
            self.priority_combo.addItem(p.value, p)
        cur_prio = self.subtask_data.get("priority", "Medium")
        p_idx = self.priority_combo.findText(cur_prio if isinstance(cur_prio, str) else cur_prio.value)
        if p_idx >= 0:
            self.priority_combo.setCurrentIndex(p_idx)

        self.gantt_checkbox = QCheckBox("Show in Gantt")
        self.gantt_checkbox.setChecked(bool(self.subtask_data.get("show_in_gantt", 1)))

        prio_row = QHBoxLayout()
        prio_row.addWidget(self.priority_combo, 1)
        prio_row.addWidget(self.gantt_checkbox)
        form.addRow("Priority", prio_row)

        # 8. Pinned
        self.pin_checkbox = QCheckBox("Pin this item")
        self.pin_checkbox.setChecked(bool(self.subtask_data.get("is_pinned", 0)))
        self.pin_color_combo = QComboBox()
        pin_colors = [
            ("Orange", "#E95420"),
            ("Blue", "#3584E4"),
            ("Purple", "#8B5CF6"),
            ("Green", "#10B981"),
            ("Amber", "#F59E0B"),
            ("Red", "#DC2626"),
            ("Graphite", "#374151"),
        ]
        for l, c in pin_colors:
            self.pin_color_combo.addItem(l, c)
        c_idx = self.pin_color_combo.findData(self.subtask_data.get("pin_color", "#E95420"))
        if c_idx >= 0:
            self.pin_color_combo.setCurrentIndex(c_idx)
        self.pin_color_combo.setEnabled(self.pin_checkbox.isChecked())
        self.pin_checkbox.toggled.connect(self.pin_color_combo.setEnabled)

        pin_row = QHBoxLayout()
        pin_row.addWidget(self.pin_checkbox)
        pin_row.addWidget(self.pin_color_combo)
        form.addRow("Pinned", pin_row)

        # 9. Actual Execution
        actual_group = QGroupBox("Actual Execution")
        actual_form = QFormLayout(actual_group)
        self.actual_check = QCheckBox("Tracked Execution")
        self.actual_check.setChecked(bool(self.subtask_data.get("actual_start_date")))

        self.actual_start_date = QDateEdit()
        self.actual_start_date.setCalendarPopup(True)
        self.actual_start_date.setDisplayFormat("yyyy-MM-dd")
        act_s_str = self.subtask_data.get("actual_start_date") or self.subtask_data.get("planned_date")
        act_s_date = QDate.fromString(act_s_str, "yyyy-MM-dd") if act_s_str else QDate.currentDate()
        self.actual_start_date.setDate(act_s_date if act_s_date.isValid() else QDate.currentDate())

        self.actual_end_date = QDateEdit()
        self.actual_end_date.setCalendarPopup(True)
        self.actual_end_date.setDisplayFormat("yyyy-MM-dd")
        act_e_str = self.subtask_data.get("actual_end_date") or self.subtask_data.get("due_date")
        act_e_date = QDate.fromString(act_e_str, "yyyy-MM-dd") if act_e_str else act_s_date
        self.actual_end_date.setDate(act_e_date if act_e_date.isValid() else act_s_date)

        self.actual_duration_spin = QSpinBox()
        self.actual_duration_spin.setRange(0, 1000000)
        self.actual_duration_spin.setSuffix(" mins")
        self.actual_duration_spin.setValue(int(self.subtask_data.get("actual_duration") or 0))

        actual_form.addRow("Tracking", self.actual_check)
        actual_form.addRow("Actual Start", self.actual_start_date)
        actual_form.addRow("Actual Finish", self.actual_end_date)
        actual_form.addRow("Effort Logged", self.actual_duration_spin)

        def set_actuals_enabled(en):
            self.actual_start_date.setEnabled(en)
            self.actual_end_date.setEnabled(en)
            self.actual_duration_spin.setEnabled(en)

        self.actual_check.toggled.connect(set_actuals_enabled)
        set_actuals_enabled(self.actual_check.isChecked())
        form.addRow("Actuals", actual_group)

        # 10. Constraints & Deadlines
        gov_group = QGroupBox("Schedule Governance & Constraints")
        gov_form = QFormLayout(gov_group)

        self.constraint_combo = QComboBox()
        for c in ["ASAP", "ALAP", "SNET", "SNLT", "FNET", "FNLT", "MSO", "MFO"]:
            self.constraint_combo.addItem(c)
        cur_c = self.subtask_data.get("constraint_type", "ASAP") or "ASAP"
        c_i = self.constraint_combo.findText(cur_c)
        if c_i >= 0:
            self.constraint_combo.setCurrentIndex(c_i)

        self.constraint_dt_edit = QDateTimeEdit()
        self.constraint_dt_edit.setCalendarPopup(True)
        self.constraint_dt_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        c_dt_str = self.subtask_data.get("constraint_datetime")
        if c_dt_str:
            self.constraint_dt_edit.setDateTime(QDateTime.fromString(c_dt_str[:16], "yyyy-MM-dd HH:mm"))
        else:
            self.constraint_dt_edit.setDateTime(QDateTime.currentDateTime())

        self.deadline_dt_edit = QDateTimeEdit()
        self.deadline_dt_edit.setCalendarPopup(True)
        self.deadline_dt_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        d_dt_str = self.subtask_data.get("deadline_datetime")
        if d_dt_str:
            self.deadline_dt_edit.setDateTime(QDateTime.fromString(d_dt_str[:16], "yyyy-MM-dd HH:mm"))
        else:
            self.deadline_dt_edit.setDateTime(QDateTime.currentDateTime().addDays(7))

        gov_form.addRow("Constraint Type", self.constraint_combo)
        gov_form.addRow("Constraint Date/Time", self.constraint_dt_edit)
        gov_form.addRow("Target Deadline", self.deadline_dt_edit)
        form.addRow("Governance", gov_group)

        layout.addLayout(form)
        scroll.setWidget(scroll_content)
        main_vbox.addWidget(scroll, 1)

        # Action Buttons
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 8, 0, 0)
        button_layout.setSpacing(10)

        button_layout.addStretch(1)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setObjectName("btn_subtask_cancel")
        self.btn_cancel.clicked.connect(self.reject)
        button_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save Subtask")
        self.btn_save.setObjectName("btn_subtask_save")
        self.btn_save.setDefault(True)
        self.btn_save.clicked.connect(self.on_save)
        button_layout.addWidget(self.btn_save)

        main_vbox.addLayout(button_layout)

    def _apply_theme(self):
        tokens = self._tokens
        bg = tokens.get("SURFACE_1", "#1E1E2E" if self._is_dark else "#FFFFFF")
        text = tokens.get("TEXT_PRIMARY", "#F4F7FB" if self._is_dark else "#111827")
        border = tokens.get("BORDER_NORMAL", "#3D3F56" if self._is_dark else "#CBD5E1")
        accent = self._accent

        self.setStyleSheet(f"""
            QDialog#SubtaskDialog {{
                background-color: {bg};
                color: {text};
            }}
            QPushButton#btn_subtask_save {{
                background-color: {accent};
                color: {text_color_on(accent)};
                font-weight: 600;
                padding: 6px 18px;
                border-radius: 6px;
            }}
            QPushButton#btn_subtask_cancel {{
                background-color: transparent;
                color: {text};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 6px 14px;
            }}
        """)

    def get_subtask_data(self) -> Dict[str, Any]:
        """Gathers edited values into canonical subtask dict."""
        data = dict(self.subtask_data)
        data["title"] = self.title_edit.text().strip()
        data["description"] = self.description_edit.toHtml()
        data["planned_date"] = self.planned_date_edit.date().toString("yyyy-MM-dd")
        data["planned_start_time"] = self.start_time_edit.time().toString("HH:mm")

        if self.finish_checkbox.isChecked():
            data["due_date"] = self.due_date_edit.date().toString("yyyy-MM-dd")
            data["planned_end_time"] = self.end_time_edit.time().toString("HH:mm")
        else:
            data["due_date"] = None
            data["planned_end_time"] = None

        data["estimated_duration"] = self.duration_spin.value()
        status_item = self.status_combo.currentData()
        status = _coerce_task_status(status_item)
        progress = self.progress_spin.value()
        if status == TaskStatus.COMPLETED:
            progress = 100
            self.progress_spin.setValue(100)
        elif status in (TaskStatus.INBOX, TaskStatus.PLANNED) and 0 < progress < 100:
            status = TaskStatus.IN_PROGRESS
            idx = self.status_combo.findData(TaskStatus.IN_PROGRESS)
            if idx >= 0:
                self.status_combo.setCurrentIndex(idx)
        elif progress >= 100:
            status = TaskStatus.COMPLETED
            idx = self.status_combo.findData(TaskStatus.COMPLETED)
            if idx >= 0:
                self.status_combo.setCurrentIndex(idx)

        data["status"] = status.value
        prio_item = self.priority_combo.currentData()
        data["priority"] = prio_item.value if hasattr(prio_item, "value") else self.priority_combo.currentText()
        data["progress"] = progress
        data["show_in_gantt"] = 1 if self.gantt_checkbox.isChecked() else 0

        category = self.blocker_category_combo.currentText().strip()
        reason = self.blocker_reason_input.text().strip()
        notes = self.blocker_notes_input.toHtml().strip()
        if status in (TaskStatus.BLOCKED, TaskStatus.DELAYED):
            data["delay_category"] = category
            data["delay_reason"] = reason
            data["delay_notes"] = notes
            data["delay_recorded_at"] = datetime.now().isoformat(timespec="seconds")
        else:
            data["delay_category"] = (
                category
                if category and category != "None"
                else self.subtask_data.get("delay_category", "") or ""
            )
            data["delay_reason"] = reason or self.subtask_data.get("delay_reason", "") or ""
            data["delay_notes"] = notes or self.subtask_data.get("delay_notes", "") or ""
            data["delay_recorded_at"] = self.subtask_data.get("delay_recorded_at")

        data["is_pinned"] = 1 if self.pin_checkbox.isChecked() else 0
        data["pin_color"] = self.pin_color_combo.currentData()

        if self.actual_check.isChecked():
            data["actual_start_date"] = self.actual_start_date.date().toString("yyyy-MM-dd")
            data["actual_end_date"] = self.actual_end_date.date().toString("yyyy-MM-dd")
            data["actual_duration"] = self.actual_duration_spin.value()
        else:
            data["actual_start_date"] = None
            data["actual_end_date"] = None
            data["actual_duration"] = 0

        c_type = self.constraint_combo.currentText()
        data["constraint_type"] = c_type
        if c_type in ("SNET", "SNLT", "FNET", "FNLT", "MSO", "MFO"):
            data["constraint_datetime"] = self.constraint_dt_edit.dateTime().toString("yyyy-MM-dd HH:mm")
        else:
            data["constraint_datetime"] = None

        data["deadline_datetime"] = self.deadline_dt_edit.dateTime().toString("yyyy-MM-dd HH:mm")
        return data

    def save_to_db(self) -> bool:
        """Persists subtask updates to database if db_manager is present."""
        if not self.db_manager or not self.subtask_id:
            return False
        data = self.get_subtask_data()
        try:
            return bool(
                self.db_manager.update_subtask(
                    subtask_id=int(self.subtask_id),
                    title=data.get("title", ""),
                    is_completed=bool(data.get("progress", 0) == 100 or data.get("status") == "Completed"),
                    position=int(self.subtask_data.get("position", 0) or 0),
                    parent_subtask_id=self.subtask_data.get("parent_subtask_id"),
                    description=data.get("description", ""),
                    planned_date=data.get("planned_date"),
                    due_date=data.get("due_date"),
                    planned_start_time=data.get("planned_start_time"),
                    planned_end_time=data.get("planned_end_time"),
                    estimated_duration=data.get("estimated_duration", 0),
                    priority=data.get("priority", "Medium"),
                    progress=data.get("progress", 0),
                    status=data.get("status", "Planned"),
                    delay_category=data.get("delay_category", "") or "",
                    delay_reason=data.get("delay_reason", "") or "",
                    delay_notes=data.get("delay_notes", "") or "",
                    delay_recorded_at=data.get("delay_recorded_at"),
                    show_in_gantt=bool(data.get("show_in_gantt", 1)),
                    is_pinned=bool(data.get("is_pinned", 0)),
                    pin_color=data.get("pin_color", "#E95420"),
                    actual_start_date=data.get("actual_start_date"),
                    actual_end_date=data.get("actual_end_date"),
                    actual_start_time=data.get("actual_start_time"),
                    actual_end_time=data.get("actual_end_time"),
                    actual_duration=data.get("actual_duration", 0),
                    planned_effort_minutes=data.get("planned_effort_minutes", 0),
                    daily_dedication_minutes=data.get("daily_dedication_minutes", 0),
                    allocation_mode=data.get("allocation_mode", "fixed_daily"),
                    baseline_start=data.get("baseline_start"),
                    baseline_finish=data.get("baseline_finish"),
                    baseline_duration_minutes=data.get("baseline_duration_minutes"),
                    baseline_planned_effort_minutes=data.get("baseline_planned_effort_minutes"),
                    constraint_type=data.get("constraint_type", "ASAP"),
                    constraint_datetime=data.get("constraint_datetime"),
                    deadline_datetime=data.get("deadline_datetime"),
                )
            )
        except Exception:
            return False

    def on_save(self):
        title = self.title_edit.text().strip()
        if not title:
            self.title_edit.setStyleSheet("border: 2px solid #EF4444;")
            return

        status = self.status_combo.currentData()
        if status in (TaskStatus.BLOCKED, TaskStatus.DELAYED):
            category = self.blocker_category_combo.currentText().strip()
            reason = self.blocker_reason_input.text().strip()
            if category.lower() in {"", "none", "null"}:
                QMessageBox.warning(
                    self,
                    "Blocker Category Required",
                    "Please select what is blocking or delaying this subtask.",
                )
                self.blocker_category_combo.setFocus()
                return
            if not reason:
                QMessageBox.warning(
                    self,
                    "Blocker Reason Required",
                    "Please record the reason this subtask is blocked or delayed.",
                )
                self.blocker_reason_input.setFocus()
                return

        if self.db_manager and self.subtask_id:
            if not self.save_to_db():
                QMessageBox.warning(
                    self,
                    "Save Failed",
                    "Todo Bird could not save this subtask. Please try again.",
                )
                return

        self.accept()
