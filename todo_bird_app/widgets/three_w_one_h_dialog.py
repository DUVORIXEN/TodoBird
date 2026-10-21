"""
3W1H Executive Reflection & Root-Cause Coaching Dialog (Batch 3.10I)
Structured WHAT / WHY / WHERE / WHEN / HOW workspace.
WHEN is bound directly to Todo Bird's existing task scheduling authority:
- Date -> task.planned_date (QDateEdit with calendar popup)
- Time -> task.planned_start_time (QTimeEdit)
- "Time not decided" checkbox (sets planned_start_time to None)
"""

import logging
import re
from datetime import date, datetime, time
from typing import Optional, Any, Union, Dict

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QTextEdit, QFrame, QDateEdit, QTimeEdit,
    QCheckBox, QWidget, QScrollArea
)
from PySide6.QtCore import Qt, QDate, QTime
from PySide6.QtGui import QFont, QIcon

from todo_bird_app.models.task import Task

logger = logging.getLogger(__name__)


def _get_field(obj: Any, key: str, default: Any = None) -> Any:
    """Helper to get field from either Task model instance or subtask dict."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _set_field(obj: Any, key: str, value: Any) -> None:
    """Helper to set field on either Task model instance or subtask dict."""
    if isinstance(obj, dict):
        obj[key] = value
    elif hasattr(obj, key):
        setattr(obj, key, value)
    else:
        try:
            setattr(obj, key, value)
        except Exception:
            pass


class ThreeWOneHDialog(QDialog):
    """
    3W1H Executive Reflection & Root-Cause Coaching Dialog.
    Guided structure: What, Why, Where, When, How.
    WHEN is bound to task.planned_date and task.planned_start_time.
    """
    def __init__(self, task: Union[Task, Dict[str, Any]], delay_minutes: int = 0, settings_manager=None, parent=None):
        super().__init__(parent)
        if settings_manager is None and parent is not None:
            settings_manager = getattr(parent, "settings_manager", None)
        self.settings_manager = settings_manager
        self.task = task
        self.delay_minutes = max(0, int(delay_minutes or 0))

        title = str(_get_field(task, "title", "Task") or "Task")
        self.setWindowTitle(f"3W1H Reflection — {title}")
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.resize(560, 640)
        self.setMinimumSize(480, 480)
        self.setSizeGripEnabled(True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._init_ui()
        self._load_from_task()

        from todo_bird_app.services.typography_service import TypographyService
        TypographyService.apply_to_widget(self, "dialogs", self.settings_manager)

        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.register(self, role="three_w_one_h_dialog")

    def done(self, r):
        super().done(r)
        self.deleteLater()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_widget = QWidget()
        layout = QVBoxLayout(scroll_widget)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header Card
        header = QFrame()
        header.setObjectName("CardWidget")
        header.setStyleSheet("background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 8px; padding: 12px;")
        h_layout = QVBoxLayout(header)
        h_layout.setSpacing(4)

        task_title = str(_get_field(self.task, "title", "Task") or "Task")
        title = QLabel(str(task_title))
        title.setStyleSheet("font-size: 15px; font-weight: 700; color: #F59E0B;")
        h_layout.addWidget(title)

        delay_desc = f"{self.delay_minutes // 60}h {self.delay_minutes % 60}m" if self.delay_minutes >= 60 else f"{self.delay_minutes}m"
        sub = QLabel(f"Schedule deviation detected (+{delay_desc}). Capture root-cause clarity to unblock and recover velocity.")
        sub.setStyleSheet("font-size: 12px; color: #9CA3AF;")
        sub.setWordWrap(True)
        h_layout.addWidget(sub)

        layout.addWidget(header)

        # 1. WHAT
        lbl_what = QLabel("1. WHAT needs to be done / blocker reality?")
        lbl_what.setStyleSheet("font-size: 13px; font-weight: 600; color: #E5E7EB;")
        layout.addWidget(lbl_what)

        self.txt_what = QLineEdit()
        self.txt_what.setPlaceholderText("e.g. Awaiting API credentials, unit test suite refactoring...")
        self.txt_what.setStyleSheet("background: rgba(255, 255, 255, 0.05); padding: 8px; border-radius: 6px;")
        layout.addWidget(self.txt_what)

        # 2. WHY
        lbl_why = QLabel("2. WHY is this required / did schedule slip?")
        lbl_why.setStyleSheet("font-size: 13px; font-weight: 600; color: #E5E7EB;")
        layout.addWidget(lbl_why)

        self.combo_why = QComboBox()
        self.combo_why.setEditable(True)
        self.combo_why.addItems([
            " External Blocker / Waiting on Dependency",
            "⏳ Underestimated Effort / Complexity",
            " Priority Shift / Emergency Request",
            " Team Resource Bottleneck",
            " Requirement Clarification Needed",
            " Technical Debt / Tooling Failure",
            "Other (Custom Reason)"
        ])
        self.combo_why.setStyleSheet("background: rgba(255, 255, 255, 0.05); padding: 6px; border-radius: 6px;")
        layout.addWidget(self.combo_why)

        # 3. WHERE
        lbl_where = QLabel("3. WHERE will it happen?")
        lbl_where.setStyleSheet("font-size: 13px; font-weight: 600; color: #E5E7EB;")
        layout.addWidget(lbl_where)

        self.txt_where = QLineEdit()
        self.txt_where.setPlaceholderText("e.g. Remote workspace, Lab environment, Backend service repo...")
        self.txt_where.setStyleSheet("background: rgba(255, 255, 255, 0.05); padding: 8px; border-radius: 6px;")
        layout.addWidget(self.txt_where)

        # 4. WHEN (Structured Date + Time Authority)
        lbl_when = QLabel("4. WHEN is the target schedule?")
        lbl_when.setStyleSheet("font-size: 13px; font-weight: 600; color: #E5E7EB;")
        layout.addWidget(lbl_when)

        when_container = QFrame()
        when_container.setStyleSheet("background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 6px; padding: 8px;")
        when_vbox = QVBoxLayout(when_container)
        when_vbox.setSpacing(6)
        when_vbox.setContentsMargins(6, 6, 6, 6)

        when_row = QHBoxLayout()
        when_row.setSpacing(8)

        lbl_d_icon = QLabel()
        from todo_bird_app.services.icon_service import IconService as _IS3W
        lbl_d_icon.setPixmap(_IS3W.get_pixmap("calendar", 14, "#9AA6BD"))
        lbl_t_icon = QLabel("")

        self.date_when = QDateEdit()
        self.date_when.setCalendarPopup(True)
        self.date_when.setDisplayFormat("yyyy-MM-dd")
        self.date_when.setDate(QDate.currentDate())
        self.date_when.setStyleSheet("background: rgba(255, 255, 255, 0.08); padding: 6px; border-radius: 4px;")

        self.time_when = QTimeEdit()
        self.time_when.setDisplayFormat("HH:mm")
        self.time_when.setTime(QTime(9, 0))
        self.time_when.setStyleSheet("background: rgba(255, 255, 255, 0.08); padding: 6px; border-radius: 4px;")

        self.chk_time_not_decided = QCheckBox("Time not decided")
        self.chk_time_not_decided.setStyleSheet("color: #D1D5DB; font-size: 12px;")

        when_row.addWidget(lbl_d_icon)
        when_row.addWidget(self.date_when, 3)
        when_row.addWidget(lbl_t_icon)
        when_row.addWidget(self.time_when, 2)
        when_row.addWidget(self.chk_time_not_decided, 3)
        when_vbox.addLayout(when_row)

        self.lbl_when_summary = QLabel()
        self.lbl_when_summary.setStyleSheet("font-size: 12px; color: #9CA3AF; font-style: italic; padding-left: 4px;")
        when_vbox.addWidget(self.lbl_when_summary)

        layout.addWidget(when_container)

        # Connect WHEN listeners for live summary updates
        self.date_when.dateChanged.connect(lambda _d: self._update_when_summary())
        self.time_when.timeChanged.connect(lambda _t: self._update_when_summary())
        self.chk_time_not_decided.toggled.connect(lambda _c: self._update_when_summary())

        # 5. HOW
        lbl_how = QLabel("5. HOW will it be done / recurrence prevented?")
        lbl_how.setStyleSheet("font-size: 13px; font-weight: 600; color: #E5E7EB;")
        layout.addWidget(lbl_how)

        self.txt_how = QLineEdit()
        self.txt_how.setPlaceholderText("e.g. Pair with senior engineer, mock external service, reduce scope...")
        self.txt_how.setStyleSheet("background: rgba(255, 255, 255, 0.05); padding: 8px; border-radius: 6px;")
        layout.addWidget(self.txt_how)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_cancel = QPushButton("Skip / Dismiss (Optional)")
        self.btn_cancel.setStyleSheet("padding: 8px 16px; border-radius: 6px; background: rgba(255, 255, 255, 0.08);")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        btn_layout.addStretch()

        self.btn_save = QPushButton(" Save Reflection & Schedule")
        self.btn_save.setStyleSheet("padding: 8px 20px; border-radius: 6px; background: #3584E4; color: white; font-weight: 600;")
        self.btn_save.clicked.connect(self.on_save)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

        scroll.setWidget(scroll_widget)
        main_layout.addWidget(scroll, 1)

    def _load_from_task(self):
        """Loads canonical date/time authority and existing reflection context."""
        # 1. Planned Date
        p_date = _get_field(self.task, "planned_date")
        if p_date:
            qd = QDate.fromString(str(p_date)[:10], "yyyy-MM-dd")
            if qd.isValid():
                self.date_when.setDate(qd)
            else:
                self.date_when.setDate(QDate.currentDate())
        else:
            self.date_when.setDate(QDate.currentDate())

        # 2. Planned Start Time
        p_time = _get_field(self.task, "planned_start_time")
        if p_time and str(p_time).strip():
            qt = QTime.fromString(str(p_time).strip()[:5], "HH:mm")
            if qt.isValid():
                self.time_when.setTime(qt)
                self.chk_time_not_decided.setChecked(False)
            else:
                self.time_when.setTime(QTime(9, 0))
                self.chk_time_not_decided.setChecked(True)
        else:
            self.time_when.setTime(QTime(9, 0))
            self.chk_time_not_decided.setChecked(True)

        self._update_when_summary()

        # 3. Restore existing text if available (backward compatibility)
        desc = _get_field(self.task, "description", "") or ""
        notes = _get_field(self.task, "delay_notes", "") or ""
        combined = f"{desc}\n{notes}"

        m_what = re.search(r"(?:- \*\*What\*\*:\s*|WHAT:\s*)([^\n]+)", combined, re.IGNORECASE)
        if m_what:
            self.txt_what.setText(m_what.group(1).strip())

        m_why = re.search(r"(?:- \*\*Why\*\*:\s*|WHY:\s*)([^\n]+)", combined, re.IGNORECASE)
        if m_why:
            why_text = m_why.group(1).strip()
            idx = self.combo_why.findText(why_text)
            if idx >= 0:
                self.combo_why.setCurrentIndex(idx)
            else:
                self.combo_why.setEditText(why_text)

        m_where = re.search(r"(?:- \*\*Where\*\*:\s*|WHERE:\s*)([^\n]+)", combined, re.IGNORECASE)
        if m_where:
            self.txt_where.setText(m_where.group(1).strip())

        m_how = re.search(r"(?:- \*\*How\*\*:\s*|HOW:\s*)([^\n]+)", combined, re.IGNORECASE)
        if m_how:
            self.txt_how.setText(m_how.group(1).strip())

    def _update_when_summary(self):
        """Updates muted human-readable schedule summary."""
        d = self.date_when.date()
        py_d = date(d.year(), d.month(), d.day())
        date_fmt = py_d.strftime("%A, %d %B %Y")

        if self.chk_time_not_decided.isChecked():
            self.time_when.setEnabled(False)
            self.lbl_when_summary.setText(f"{date_fmt} • Time not decided")
        else:
            self.time_when.setEnabled(True)
            t = self.time_when.time()
            if t.isValid():
                py_t = time(t.hour(), t.minute())
                time_fmt = py_t.strftime("%I:%M %p").lstrip("0")
                self.lbl_when_summary.setText(f"{date_fmt} at {time_fmt}")
            else:
                self.lbl_when_summary.setText(f"{date_fmt}")

    def on_save(self):
        """Saves structured WHEN back to existing planned schedule authority."""
        # 1. Update task planned_date
        planned_date_str = self.date_when.date().toString("yyyy-MM-dd")
        _set_field(self.task, "planned_date", planned_date_str)

        # 2. Update task planned_start_time (None if time not decided)
        if self.chk_time_not_decided.isChecked():
            _set_field(self.task, "planned_start_time", None)
        else:
            planned_time_str = self.time_when.time().toString("HH:mm")
            _set_field(self.task, "planned_start_time", planned_time_str)

        self.accept()

    def get_reflection_text(self) -> str:
        """Format 3W1H reflection into a structured markdown block."""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        revised_date = self.date_when.date().toString("yyyy-MM-dd")
        if self.chk_time_not_decided.isChecked():
            when_desc = f"{revised_date} (Time not decided)"
        else:
            when_desc = f"{revised_date} {self.time_when.time().toString('HH:mm')}"

        where_text = self.txt_where.text().strip()
        where_line = f"- **Where**: {where_text}\n" if where_text else ""

        return (
            f"\n\n### 3W1H Reflection ({now_str})\n"
            f"- **What**: {self.txt_what.text().strip() or 'Deviation noted'}\n"
            f"- **Why**: {self.combo_why.currentText()}\n"
            f"{where_line}"
            f"- **When**: Revised target {when_desc}\n"
            f"- **How**: {self.txt_how.text().strip() or 'Follow corrective action'}\n"
        )
