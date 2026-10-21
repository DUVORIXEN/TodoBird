from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtCore import QUrl

import logging
from todo_bird_app.services.support_service import SupportService

logger = logging.getLogger(__name__)

class SupportTodoBirdDialog(QDialog):
    """
    Non-blocking dialog to present the optional Support Todo Bird message.
    """
    def __init__(self, support_service: SupportService, parent=None, is_automatic_prompt=False):
        super().__init__(parent)
        self.support_service = support_service
        self.is_automatic_prompt = is_automatic_prompt
        self.setObjectName("SupportTodoBirdDialog")
        
        self.setWindowTitle("Support Todo Bird")
        self.setModal(False)
        self.setMinimumWidth(450)
        self._init_ui()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        
        # Title
        title_label = QLabel("Support Todo Bird")
        title_font = title_label.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Copy
        body_copy = (
            "Todo Bird Beta is free to use.\n\n"
            "If Todo Bird is helping you organize, plan, and execute your work, "
            "you can optionally support its continued development.\n\n"
            "Your support helps improve reliability, performance, new features, "
            "documentation, and cross-platform support.\n\n"
            "Supporting Todo Bird is completely optional and does not unlock or "
            "restrict any feature."
        )
        body_label = QLabel(body_copy)
        body_label.setWordWrap(True)
        # Ensure it works nicely across themes
        body_label.setStyleSheet("QLabel { line-height: 1.4; }")
        layout.addWidget(body_label)
        
        # Don't Ask Again (only if automatic prompt)
        if self.is_automatic_prompt:
            self.dont_ask_checkbox = QCheckBox("Don't ask me again")
            self.dont_ask_checkbox.toggled.connect(self._on_dont_ask_toggled)
            layout.addWidget(self.dont_ask_checkbox)
            
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        
        self.maybe_later_btn = QPushButton("Maybe Later")
        self.maybe_later_btn.clicked.connect(self.reject)
        
        self.support_btn = QPushButton("Support Todo Bird")
        self.support_btn.setObjectName("PrimaryButton")
        self.support_btn.clicked.connect(self._on_support_clicked)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.maybe_later_btn)
        btn_layout.addWidget(self.support_btn)
        
        layout.addLayout(btn_layout)
        
        if self.is_automatic_prompt:
            self.support_service.record_support_prompt_shown()
            
    def _on_dont_ask_toggled(self, checked: bool):
        if checked:
            self.support_service.disable_automatic_prompts()
            
    def _on_support_clicked(self):
        url_str = self.support_service.get_support_url()
        url = QUrl(url_str)
        
        if url.scheme() != "https":
            QMessageBox.critical(self, "Security Error", "Support URL must be HTTPS.")
            return
            
        success = QDesktopServices.openUrl(url)
        if not success:
            QMessageBox.warning(
                self, 
                "Browser Error", 
                "Todo Bird couldn't open the support page. Please check your internet "
                "connection or browser configuration and try again."
            )
        else:
            self.accept()
