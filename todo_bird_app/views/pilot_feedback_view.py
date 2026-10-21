import logging
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox, QPushButton, QTableWidget, QTableWidgetItem, QFrame, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt

from todo_bird_app.views.base_view import BaseView
from todo_bird_app.services.pilot_issue_logger import PilotIssueLogger
from todo_bird_app.services.path_resolver import PathResolver
from todo_bird_app.__version__ import __version__

logger = logging.getLogger(__name__)

class PilotFeedbackView(BaseView):
    """
    Pilot Feedback & Diagnostics View.
    Allows pilot users on Ubuntu 24.04 and Windows 11 to submit local issue reports,
    view recorded issues, and export diagnostic logs.
    """
    def __init__(self, db_manager, settings_manager, parent=None):
        super().__init__(db_manager, settings_manager, title="Pilot Feedback & Diagnostics", subtitle=f"Parallel Pilot Issue Tracker (v{__version__})", parent=parent)
        self.logger_engine = PilotIssueLogger()
        self._init_ui()
        self.refresh_data()

    def _init_ui(self):
        # 1. Issue Form Frame
        form_frame = QFrame()
        form_frame.setObjectName("CardWidget")
        f_layout = QVBoxLayout(form_frame)
        f_layout.setContentsMargins(16, 12, 16, 12)
        f_layout.setSpacing(8)

        lbl_title = QLabel(" Submit Pilot Issue / Feedback")
        lbl_title.setStyleSheet("font-weight: 700; font-size: 14px; color: #E95420;")
        f_layout.addWidget(lbl_title)

        row1 = QHBoxLayout()
        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("Issue Summary / Title...")
        row1.addWidget(self.txt_title, 2)

        self.cmb_severity = QComboBox()
        self.cmb_severity.addItems(["Low", "Medium", "High", "Critical"])
        self.cmb_severity.setCurrentText("Medium")
        row1.addWidget(self.cmb_severity, 1)

        f_layout.addLayout(row1)

        self.txt_desc = QTextEdit()
        self.txt_desc.setPlaceholderText("Description and steps to reproduce...")
        self.txt_desc.setMaximumHeight(70)
        f_layout.addWidget(self.txt_desc)

        btn_row = QHBoxLayout()
        sub_btn = QPushButton("Submit Issue")
        sub_btn.setObjectName("PrimaryButton")
        sub_btn.clicked.connect(self.submit_issue)
        btn_row.addWidget(sub_btn)

        exp_btn = QPushButton(" Export Diagnostic Report")
        exp_btn.clicked.connect(self.export_report)
        btn_row.addWidget(exp_btn)

        btn_row.addStretch()
        f_layout.addLayout(btn_row)

        self.main_layout.addWidget(form_frame)

        # 2. Issues Table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["ID", "Date", "OS", "Severity", "Title", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.main_layout.addWidget(self.table, 1)

    def submit_issue(self):
        title = self.txt_title.text().strip()
        desc = self.txt_desc.toPlainText().strip()
        sev = self.cmb_severity.currentText()

        if not title:
            QMessageBox.warning(self, "Required", "Please enter an issue title.")
            return

        self.logger_engine.log_issue(title=title, severity=sev, description=desc)
        self.txt_title.clear()
        self.txt_desc.clear()
        QMessageBox.information(self, "Submitted", "Pilot issue recorded locally.")
        self.refresh_data()

    def export_report(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export Diagnostic Report", "todobird_pilot_report.json", "JSON Files (*.json)")
        if not file_path:
            return

        if self.logger_engine.export_issue_report(Path(file_path)):
            QMessageBox.information(self, "Export Complete", f"Diagnostic report saved to:\n{file_path}")

    def refresh_data(self):
        issues = self.logger_engine.get_all_issues()
        self.table.setRowCount(len(issues))

        for idx, issue in enumerate(issues):
            self.table.setItem(idx, 0, QTableWidgetItem(issue.get("issue_id", "")))
            self.table.setItem(idx, 1, QTableWidgetItem(issue.get("date", "")[:10]))
            self.table.setItem(idx, 2, QTableWidgetItem(issue.get("os", "")))
            self.table.setItem(idx, 3, QTableWidgetItem(issue.get("severity", "")))
            self.table.setItem(idx, 4, QTableWidgetItem(issue.get("title", "")))
            self.table.setItem(idx, 5, QTableWidgetItem(issue.get("status", "")))
