"""
TODO BIRD — SMART MILESTONE MICRO-PULSE & STORE REVIEW BANNER
Non-intrusive floating in-window banner that triggers at a natural moment of
delight (e.g., completing 3+ tasks) to ask how the user feels about Todo Bird
and offer 1-click check-in to the Developer's GitHub Wall / Webhook or Store Review.
"""

import logging
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QColor, QDesktopServices

from todo_bird_app.services.pilot_issue_logger import PilotIssueLogger

logger = logging.getLogger(__name__)


class MilestonePulseBanner(QFrame):
    """
    In-window celebratory micro-pulse banner mounted inside MainWindow.centralWidget().
    """
    open_feedback_requested = Signal()
    dismissed = Signal()

    def __init__(self, settings_manager=None, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.logger_engine = PilotIssueLogger()
        self._last_logged_issue = None

        self.setObjectName("MilestonePulseBanner")
        self.setFixedSize(440, 148)
        self.setStyleSheet(
            "QFrame#MilestonePulseBanner {"
            "  background-color: #161925;"
            "  border: 2px solid #10B981;"
            "  border-radius: 14px;"
            "}"
            "QFrame#MilestonePulseBanner QLabel {"
            "  color: #F8FAFC;"
            "  background: transparent;"
            "}"
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)

        self._init_ui()

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 12, 16, 12)
        self.main_layout.setSpacing(8)

        # Header Row
        top_row = QHBoxLayout()
        self.title_lbl = QLabel("🎉 Milestone Reached! How does Todo Bird feel?")
        self.title_lbl.setStyleSheet("font-weight: 700; font-size: 13px; color: #34D399;")
        top_row.addWidget(self.title_lbl, 1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; color: #94A3B8; border: none; font-weight: bold; }"
            "QPushButton:hover { color: #FFFFFF; }"
        )
        close_btn.clicked.connect(self._on_dismiss)
        top_row.addWidget(close_btn)
        self.main_layout.addLayout(top_row)

        self.subtitle_lbl = QLabel("Tap an emoji to let DUVORIXEN know how your experience is going:")
        self.subtitle_lbl.setWordWrap(True)
        self.subtitle_lbl.setStyleSheet("font-size: 11.5px; color: #CBD5E1;")
        self.main_layout.addWidget(self.subtitle_lbl)

        # Step 1: Emoji Mood Row
        self.emoji_row_widget = QFrame()
        self.emoji_row_widget.setStyleSheet("background: transparent; border: none;")
        emoji_layout = QHBoxLayout(self.emoji_row_widget)
        emoji_layout.setContentsMargins(0, 2, 0, 0)
        emoji_layout.setSpacing(6)

        self.mood_buttons = []
        for label_text, stars in [
            ("🤩 Loving It", 5),
            ("😊 Happy", 5),
            ("🙂 Good", 4),
            ("🤔 Confused", 3),
        ]:
            btn = QPushButton(label_text)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background: rgba(255,255,255,0.08); color: #F8FAFC; "
                "border: 1px solid rgba(255,255,255,0.16); border-radius: 8px; padding: 5px 8px; font-size: 11.5px; font-weight: 600; }"
                "QPushButton:hover { background: rgba(233, 84, 32, 0.35); border-color: #E95420; }"
            )
            btn.clicked.connect(lambda _c=False, m=label_text, s=stars: self._on_mood_clicked(m, s))
            emoji_layout.addWidget(btn)
            self.mood_buttons.append(btn)

        self.main_layout.addWidget(self.emoji_row_widget)

        # Step 2: Thank You + 1-Click Share Actions (hidden initially)
        self.thanks_row_widget = QFrame()
        self.thanks_row_widget.setStyleSheet("background: transparent; border: none;")
        thanks_layout = QHBoxLayout(self.thanks_row_widget)
        thanks_layout.setContentsMargins(0, 2, 0, 0)
        thanks_layout.setSpacing(6)

        self.send_dev_btn = QPushButton("🚀 Send to Developer (GitHub) ↗")
        self.send_dev_btn.setCursor(Qt.PointingHandCursor)
        self.send_dev_btn.setStyleSheet(
            "QPushButton { background: #E95420; color: #FFFFFF; font-weight: 700; "
            "border-radius: 8px; padding: 5px 10px; font-size: 11.5px; border: none; }"
        )
        self.send_dev_btn.clicked.connect(self._on_send_to_github)
        thanks_layout.addWidget(self.send_dev_btn)

        self.store_rate_btn = QPushButton("⭐ Rate on Store ↗")
        self.store_rate_btn.setCursor(Qt.PointingHandCursor)
        self.store_rate_btn.setStyleSheet(
            "QPushButton { background: #2563EB; color: #FFFFFF; font-weight: 600; "
            "border-radius: 8px; padding: 5px 10px; font-size: 11.5px; border: none; }"
        )
        self.store_rate_btn.clicked.connect(self._on_rate_store)
        thanks_layout.addWidget(self.store_rate_btn)

        self.more_btn = QPushButton("💬 Add Note")
        self.more_btn.setCursor(Qt.PointingHandCursor)
        self.more_btn.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.1); color: #E2E8F0; "
            "border-radius: 8px; padding: 5px 10px; font-size: 11.5px; border: none; }"
        )
        self.more_btn.clicked.connect(self._on_open_feedback)
        thanks_layout.addWidget(self.more_btn)

        self.thanks_row_widget.hide()
        self.main_layout.addWidget(self.thanks_row_widget)

    def _on_mood_clicked(self, mood: str, stars: int):
        user_name = ""
        user_country = ""
        webhook_url = ""
        if self.settings_manager:
            self.settings_manager.set("milestone_pulse_completed", True)
            user_name = str(self.settings_manager.get("user_display_name") or self.settings_manager.get("user_salutation") or "")
            if user_name == "friend":
                user_name = ""
            user_country = str(self.settings_manager.get("user_country") or self.settings_manager.get("region_country") or "")
            webhook_url = str(self.settings_manager.get("feedback_webhook_url") or "").strip()

        self._last_logged_issue = self.logger_engine.log_issue(
            title=f"Milestone Check-In: {mood}",
            severity="Low",
            description=f"User completed milestone tasks and rated Todo Bird {stars}/5 ({mood}).",
            rating=stars,
            feeling=mood,
            category="Milestone Check-In",
            user_name=user_name,
            user_country=user_country,
        )

        if webhook_url.startswith("https://"):
            self.logger_engine.send_webhook_payload(webhook_url, self._last_logged_issue)

        self.title_lbl.setText(f"💜 Thank you! Recorded: {mood} ({stars}★)")
        self.subtitle_lbl.setText("Share your check-in with DUVORIXEN or rate us on the Store:")
        self.emoji_row_widget.hide()
        self.thanks_row_widget.show()

    def _on_send_to_github(self):
        if self._last_logged_issue:
            url = self.logger_engine.build_github_feedback_url(self._last_logged_issue)
            QDesktopServices.openUrl(QUrl(url))
        self.hide()

    def _on_rate_store(self):
        channel = self.logger_engine.detect_install_channel()
        if "Windows" in channel or "Microsoft" in channel:
            QDesktopServices.openUrl(QUrl("https://apps.microsoft.com/"))
        else:
            QDesktopServices.openUrl(QUrl("https://snapcraft.io/todo-bird"))
        self.hide()

    def _on_open_feedback(self):
        self.hide()
        self.open_feedback_requested.emit()

    def _on_dismiss(self):
        if self.settings_manager:
            self.settings_manager.set("milestone_pulse_completed", True)
        self.hide()
        self.dismissed.emit()
