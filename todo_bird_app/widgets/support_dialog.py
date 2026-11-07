from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QMessageBox, QFrame, QLineEdit, QApplication
)
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont

import logging
from todo_bird_app.services.support_service import SupportService
from todo_bird_app.utils.qr_code import QRCodeWidget

logger = logging.getLogger(__name__)


class SupportTodoBirdDialog(QDialog):
    """
    Non-blocking Razorpay Support & Appreciation Dialog for TODO BIRD.
    Provides direct 1-click access to Razorpay (https://razorpay.me/@duvorixen),
    scannable phone QR code, tier presets, link copy, Razorpay URL configuration,
    Supporter Badge toggle, and quick feedback link.
    """
    feedback_requested = Signal()
    supporter_status_changed = Signal(bool)

    def __init__(self, support_service: SupportService, parent=None, is_automatic_prompt=False):
        super().__init__(parent)
        self.support_service = support_service
        self.is_automatic_prompt = is_automatic_prompt
        self.setObjectName("SupportTodoBirdDialog")

        self.setWindowTitle("Support Todo Bird — Razorpay")
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setModal(False)
        self.setMinimumWidth(520)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header Row with Razorpay Badge
        header_row = QHBoxLayout()
        title_label = QLabel("💜 Support Todo Bird via Razorpay")
        title_font = title_label.font()
        title_font.setPointSize(15)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_row.addWidget(title_label)
        header_row.addStretch()

        badge = QLabel("OFFICIAL RAZORPAY")
        badge.setStyleSheet(
            "background-color: #2563EB; color: #FFFFFF; font-weight: 700; "
            "font-size: 10px; padding: 4px 10px; border-radius: 10px;"
        )
        header_row.addWidget(badge)
        layout.addLayout(header_row)

        # Copy + Scannable Phone QR Code Row
        mid_row = QHBoxLayout()
        mid_row.setSpacing(16)

        body_copy = (
            "Todo Bird is 100% free, offline-first, and ad-free.\n\n"
            "If Todo Bird is helping you organize, plan, and execute your work with clarity, "
            "you can optionally support its continued development via Razorpay "
            "(UPI, Cards, NetBanking & International supported).\n\n"
            "📱 Scan the QR code with your phone camera or UPI app, or click a tier below!"
        )
        body_label = QLabel(body_copy)
        body_label.setWordWrap(True)
        body_label.setStyleSheet("QLabel { line-height: 1.45; }")
        mid_row.addWidget(body_label, 1)

        qr_box = QVBoxLayout()
        qr_box.setSpacing(4)
        self.qr_widget = QRCodeWidget(self.support_service.get_support_url(), size_px=116, parent=self)
        qr_box.addWidget(self.qr_widget, alignment=Qt.AlignCenter)
        qr_caption = QLabel("Scan with Phone")
        qr_caption.setAlignment(Qt.AlignCenter)
        qr_caption.setStyleSheet("font-size: 10px; font-weight: 600; color: #94A3B8;")
        qr_box.addWidget(qr_caption)
        mid_row.addLayout(qr_box)

        layout.addLayout(mid_row)

        # Quick Tier Chips Card
        tiers_frame = QFrame()
        tiers_frame.setObjectName("CardWidget")
        tiers_layout = QVBoxLayout(tiers_frame)
        tiers_layout.setContentsMargins(14, 12, 14, 12)
        tiers_layout.setSpacing(10)

        tiers_title = QLabel("Choose a Support Tier (opens secure Razorpay checkout):")
        tiers_title.setStyleSheet("font-weight: 600; font-size: 12px;")
        tiers_layout.addWidget(tiers_title)

        tier_btns_row = QHBoxLayout()
        tier_btns_row.setSpacing(8)
        self.tier_buttons = []
        for label_text in [
            "☕ Coffee (₹199)",
            "🚀 Boost (₹499)",
            "💎 Champion (₹999)",
            "✨ Custom",
        ]:
            t_btn = QPushButton(label_text)
            t_btn.setCursor(Qt.PointingHandCursor)
            t_btn.clicked.connect(self._on_support_clicked)
            tier_btns_row.addWidget(t_btn)
            self.tier_buttons.append(t_btn)
        tiers_layout.addLayout(tier_btns_row)

        # Razorpay URL Display & Copy / Update Row
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        self.url_input = QLineEdit(self.support_service.get_support_url())
        self.url_input.setPlaceholderText("https://razorpay.me/@duvorixen")
        self.url_input.setToolTip("Razorpay payment link (HTTPS required)")
        url_row.addWidget(self.url_input, 1)

        self.copy_url_btn = QPushButton("Copy Link")
        self.copy_url_btn.setCursor(Qt.PointingHandCursor)
        self.copy_url_btn.clicked.connect(self._on_copy_url)
        url_row.addWidget(self.copy_url_btn)

        self.save_url_btn = QPushButton("Update Link")
        self.save_url_btn.setCursor(Qt.PointingHandCursor)
        self.save_url_btn.setToolTip("Save updated Razorpay link")
        self.save_url_btn.clicked.connect(self._on_update_url)
        url_row.addWidget(self.save_url_btn)

        tiers_layout.addLayout(url_row)

        # Supporter Badge Toggle
        is_supporter = False
        if self.support_service and self.support_service.settings:
            is_supporter = bool(self.support_service.settings.get("is_todo_bird_supporter", False))
        self.supporter_checkbox = QCheckBox("💎 I supported Todo Bird! Show Supporter Star Badge (★) in my Header Bar")
        self.supporter_checkbox.setChecked(is_supporter)
        self.supporter_checkbox.toggled.connect(self._on_supporter_toggled)
        tiers_layout.addWidget(self.supporter_checkbox)

        layout.addWidget(tiers_frame)

        # Don't Ask Again (only if automatic prompt)
        if self.is_automatic_prompt:
            self.dont_ask_checkbox = QCheckBox("Don't ask me again")
            self.dont_ask_checkbox.toggled.connect(self._on_dont_ask_toggled)
            layout.addWidget(self.dont_ask_checkbox)

        # Bottom Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.feedback_btn = QPushButton("💬 Share Feedback / Rate App")
        self.feedback_btn.setCursor(Qt.PointingHandCursor)
        self.feedback_btn.clicked.connect(self._on_feedback_clicked)
        btn_layout.addWidget(self.feedback_btn)

        btn_layout.addStretch()

        self.maybe_later_btn = QPushButton("Maybe Later")
        self.maybe_later_btn.setCursor(Qt.PointingHandCursor)
        self.maybe_later_btn.clicked.connect(self.reject)

        self.support_btn = QPushButton("Pay via Razorpay ↗")
        self.support_btn.setObjectName("PrimaryButton")
        self.support_btn.setCursor(Qt.PointingHandCursor)
        self.support_btn.clicked.connect(self._on_support_clicked)

        btn_layout.addWidget(self.maybe_later_btn)
        btn_layout.addWidget(self.support_btn)

        layout.addLayout(btn_layout)

        if self.is_automatic_prompt:
            self.support_service.record_support_prompt_shown()

    def _on_dont_ask_toggled(self, checked: bool):
        if checked:
            self.support_service.disable_automatic_prompts()

    def _on_copy_url(self):
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.support_service.get_support_url())
        self.copy_url_btn.setText("Copied ✓")

    def _on_update_url(self):
        candidate = self.url_input.text().strip()
        if not candidate.startswith("https://"):
            QMessageBox.critical(self, "Security Error", "Support URL must start with https://")
            return
        self.support_service.set_support_url(candidate)
        if hasattr(self, "qr_widget"):
            self.qr_widget.set_url(candidate)
        self.save_url_btn.setText("Saved ✓")

    def _on_supporter_toggled(self, checked: bool):
        if self.support_service and self.support_service.settings:
            self.support_service.settings.set("is_todo_bird_supporter", bool(checked))
        self.supporter_status_changed.emit(bool(checked))

    def _on_feedback_clicked(self):
        self.feedback_requested.emit()
        self.accept()

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
                "Todo Bird couldn't open the Razorpay support page. Please check your internet "
                "connection or browser configuration and try again."
            )
        else:
            self.accept()
