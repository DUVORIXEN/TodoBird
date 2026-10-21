"""
Project Calendar Dialog — Phase 2E.

Interactive Qt dialog to configure project working weekdays (Mon-Sun)
and manage project-specific holiday / overtime calendar exceptions.
"""

from typing import List, Dict, Any, Optional
from datetime import date, datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QDateEdit, QLineEdit, QComboBox, QMessageBox, QGroupBox,
    QWidget
)
from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor

from todo_bird_app.services.schedule_constraint_service import (
    CalendarException,
    ProjectCalendarSpec,
)


class ProjectCalendarDialog(QDialog):
    """
    Project Working Calendar and Exceptions Configuration Dialog.
    """

    WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    def __init__(self, project_id: Optional[int] = None, project_name: str = "", db_manager=None, parent=None):
        super().__init__(parent)
        self.project_id = project_id
        self.project_name = project_name
        self.db_manager = db_manager

        self.setWindowTitle(f"Project Calendar — {project_name}" if project_name else "Project Calendar")
        self.setMinimumSize(520, 480)
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.register(self, role="project_calendar_dialog")

        self.weekday_checkboxes: List[QCheckBox] = []
        self._init_ui()
        self._load_data()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # Title
        title_lbl = QLabel(f"Working Calendar: {self.project_name}" if self.project_name else "Project Working Calendar")
        title_lbl.setStyleSheet("font-size: 14pt; font-weight: 700;")
        main_layout.addWidget(title_lbl)

        # Group 1: Working Weekdays
        weekdays_group = QGroupBox("Working Weekdays (Standard Working Days)")
        weekdays_layout = QHBoxLayout(weekdays_group)
        weekdays_layout.setSpacing(10)

        for i, name in enumerate(self.WEEKDAY_NAMES):
            cb = QCheckBox(name[:3])
            cb.setToolTip(f"Enable {name} as standard working day")
            if i < 5:  # Mon-Fri checked by default
                cb.setChecked(True)
            self.weekday_checkboxes.append(cb)
            weekdays_layout.addWidget(cb)

        main_layout.addWidget(weekdays_group)

        # Group 2: Calendar Exceptions (Holidays / Special Working Days)
        exceptions_group = QGroupBox("Calendar Exceptions (Holidays & Special Overtime Days)")
        exceptions_vbox = QVBoxLayout(exceptions_group)
        exceptions_vbox.setSpacing(8)

        # Add exception input row
        add_row = QHBoxLayout()
        self.date_input = QDateEdit()
        self.date_input.setCalendarPopup(True)
        self.date_input.setDate(QDate.currentDate())
        self.date_input.setDisplayFormat("yyyy-MM-dd")

        self.type_combo = QComboBox()
        self.type_combo.addItem("Non-Working Holiday", False)
        self.type_combo.addItem("Special Working Day", True)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Exception description (e.g. National Holiday)...")

        self.btn_add = QPushButton("Add Exception")
        self.btn_add.clicked.connect(self._on_add_exception)

        add_row.addWidget(QLabel("Date:"))
        add_row.addWidget(self.date_input)
        add_row.addWidget(self.type_combo)
        add_row.addWidget(self.name_input)
        add_row.addWidget(self.btn_add)
        exceptions_vbox.addLayout(add_row)

        # Exceptions Table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Date", "Type", "Description", "Action"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        exceptions_vbox.addWidget(self.table)

        main_layout.addWidget(exceptions_group)

        # Action Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_cancel)

        self.btn_save = QPushButton(" Save Calendar")
        self.btn_save.setStyleSheet("background-color: #E95420; color: white; font-weight: 600; padding: 6px 16px; border-radius: 4px;")
        self.btn_save.clicked.connect(self._on_save)
        btn_box.addWidget(self.btn_save)

        main_layout.addLayout(btn_box)

    def _load_data(self):
        if not self.db_manager or self.project_id is None:
            return
        cal_data = self.db_manager.get_project_calendar(self.project_id)
        work_days = cal_data.get("working_weekdays", [0, 1, 2, 3, 4])
        for i, cb in enumerate(self.weekday_checkboxes):
            cb.setChecked(i in work_days)

        exceptions = cal_data.get("calendar_exceptions", [])
        self._populate_exceptions_table(exceptions)

    def _populate_exceptions_table(self, exceptions: List[Dict[str, Any]]):
        self.table.setRowCount(0)
        for ex in exceptions:
            row = self.table.rowCount()
            self.table.insertRow(row)

            d_str = str(ex.get("date") or ex.get("exception_date") or "")
            is_w = bool(ex.get("is_working"))
            name = str(ex.get("name") or "")

            item_d = QTableWidgetItem(d_str)
            item_d.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, item_d)

            item_t = QTableWidgetItem("Working override" if is_w else "Holiday")
            item_t.setData(Qt.UserRole, bool(is_w))
            item_t.setTextAlignment(Qt.AlignCenter)
            if not is_w:
                item_t.setForeground(QColor("#EF4444"))
            else:
                item_t.setForeground(QColor("#10B981"))
            self.table.setItem(row, 1, item_t)

            item_n = QTableWidgetItem(name)
            self.table.setItem(row, 2, item_n)

            btn_del = QPushButton("Delete")
            btn_del.setStyleSheet("color: #DC2626;")
            btn_del.clicked.connect(lambda _, r=row: self._delete_row(r))
            self.table.setCellWidget(row, 3, btn_del)

    def _on_add_exception(self):
        d_str = self.date_input.date().toString("yyyy-MM-dd")
        is_w = bool(self.type_combo.currentData())
        name = self.name_input.text().strip()

        # Check duplicate date in table
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0) and self.table.item(r, 0).text() == d_str:
                QMessageBox.warning(self, "Duplicate Date", f"An exception for {d_str} already exists.")
                return

        row = self.table.rowCount()
        self.table.insertRow(row)

        item_d = QTableWidgetItem(d_str)
        item_d.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(row, 0, item_d)

        item_t = QTableWidgetItem("Working override" if is_w else "Holiday")
        item_t.setData(Qt.UserRole, bool(is_w))
        item_t.setTextAlignment(Qt.AlignCenter)
        if not is_w:
            item_t.setForeground(QColor("#EF4444"))
        else:
            item_t.setForeground(QColor("#10B981"))
        self.table.setItem(row, 1, item_t)

        item_n = QTableWidgetItem(name)
        self.table.setItem(row, 2, item_n)

        btn_del = QPushButton("Delete")
        btn_del.setStyleSheet("color: #DC2626;")
        btn_del.clicked.connect(lambda _, r=row: self._delete_row(r))
        self.table.setCellWidget(row, 3, btn_del)

        self.name_input.clear()

    def _delete_row(self, row_idx: int):
        self.table.removeRow(row_idx)
        # Reconnect buttons
        for r in range(self.table.rowCount()):
            btn = self.table.cellWidget(r, 3)
            if isinstance(btn, QPushButton):
                btn.clicked.disconnect()
                btn.clicked.connect(lambda _, curr_r=r: self._delete_row(curr_r))

    def _on_save(self):
        selected_weekdays = [i for i, cb in enumerate(self.weekday_checkboxes) if cb.isChecked()]
        if not selected_weekdays:
            QMessageBox.warning(self, "No Working Days", "At least one working weekday must be selected.")
            return

        exceptions = []
        for r in range(self.table.rowCount()):
            d_item = self.table.item(r, 0)
            t_item = self.table.item(r, 1)
            n_item = self.table.item(r, 2)
            if d_item and t_item:
                role_value = t_item.data(Qt.UserRole)
                is_working = (
                    bool(role_value)
                    if role_value is not None
                    else t_item.text().strip().lower() in {
                        "working override",
                        "working day",
                        "special working day",
                    }
                )
                exceptions.append({
                    "date": d_item.text(),
                    "is_working": 1 if is_working else 0,
                    "name": n_item.text() if n_item else "",
                })

        if self.db_manager and self.project_id is not None:
            self.db_manager.set_project_calendar(self.project_id, selected_weekdays, exceptions)

        self.accept()
