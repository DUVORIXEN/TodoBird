import logging
from pathlib import Path
from typing import List
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox,
    QPushButton, QTableWidget, QTableWidgetItem, QFrame, QMessageBox,
    QFileDialog, QCheckBox
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices

from todo_bird_app.views.base_view import BaseView
from todo_bird_app.services.pilot_issue_logger import PilotIssueLogger
from todo_bird_app.__version__ import __version__

logger = logging.getLogger(__name__)


MOOD_OPTIONS = [
    "🤩 Loving It!",
    "😊 Happy & Productive",
    "🙂 Good / Useful",
    "🤔 Confused / Need Help",
    "🐛 Found a Bug",
]


class PilotFeedbackView(BaseView):
    """
    User Feedback, Sentiment Rating, Community Check-In & Store Pulse View.
    Enables users to share who they are, how they feel about Todo Bird (1–5 stars + mood),
    and transmit feedback directly to DUVORIXEN via GitHub Community Wall, Cloud Webhook,
    or Store Reviews, while also displaying live store status & release download counts.
    """
    def __init__(self, db_manager, settings_manager, parent=None):
        super().__init__(
            db_manager,
            settings_manager,
            title="User Feedback & Community Pulse",
            subtitle=f"Share How You Feel, Community Check-In & Store Analytics (v{__version__})",
            parent=parent,
        )
        self.logger_engine = PilotIssueLogger()
        self.selected_rating: int = 5
        self.selected_feeling: str = MOOD_OPTIONS[0]
        self.mood_buttons: List[QPushButton] = []
        self.star_buttons: List[QPushButton] = []
        self._init_ui()
        self.refresh_data()

    def _init_ui(self):
        # 1. Store Status & Live Download Analytics Banner
        store_frame = QFrame()
        store_frame.setObjectName("CardWidget")
        s_layout = QVBoxLayout(store_frame)
        s_layout.setContentsMargins(16, 12, 16, 12)
        s_layout.setSpacing(8)

        s_top = QHBoxLayout()
        s_title = QLabel("📊 Official Store Status & Download Analytics (DUVORIXEN)")
        s_title.setStyleSheet("font-weight: 700; font-size: 13.5px; color: #38BDF8;")
        s_top.addWidget(s_title)
        s_top.addStretch()

        self.channel_badge = QLabel(f"Channel: {self.logger_engine.detect_install_channel()}")
        self.channel_badge.setStyleSheet(
            "background-color: rgba(16, 185, 129, 0.18); color: #34D399; "
            "font-weight: 600; font-size: 11px; padding: 3px 10px; border-radius: 8px;"
        )
        s_top.addWidget(self.channel_badge)
        s_layout.addLayout(s_top)

        s_info_row = QHBoxLayout()
        self.lbl_store_status = QLabel(
            "• Ubuntu Software (Snap Store): LIVE on latest/stable (v1.0.1, Rev 3)   "
            "• Windows Store: DUVORIXEN.TODOBIRD v1.0.1.0 (MSIX + Setup.exe)"
        )
        self.lbl_store_status.setWordWrap(True)
        self.lbl_store_status.setStyleSheet("font-size: 12px;")
        s_info_row.addWidget(self.lbl_store_status, 1)

        self.btn_refresh_downloads = QPushButton("🔄 Check Live Downloads")
        self.btn_refresh_downloads.setCursor(Qt.PointingHandCursor)
        self.btn_refresh_downloads.clicked.connect(self._on_fetch_live_downloads)
        s_info_row.addWidget(self.btn_refresh_downloads)

        self.btn_snap_metrics = QPushButton("Ubuntu Snap Metrics ↗")
        self.btn_snap_metrics.setCursor(Qt.PointingHandCursor)
        self.btn_snap_metrics.setToolTip("Open Snapcraft Developer Metrics (installs by country & version)")
        self.btn_snap_metrics.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://snapcraft.io/todo-bird"))
        )
        s_info_row.addWidget(self.btn_snap_metrics)

        self.btn_ms_store = QPushButton("Microsoft Partner Center ↗")
        self.btn_ms_store.setCursor(Qt.PointingHandCursor)
        self.btn_ms_store.setToolTip("Open Microsoft Store Partner Center Analytics & Reviews")
        self.btn_ms_store.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://partner.microsoft.com/dashboard"))
        )
        s_info_row.addWidget(self.btn_ms_store)

        s_layout.addLayout(s_info_row)

        # Webhook configuration row for direct developer notifications
        wh_row = QHBoxLayout()
        wh_lbl = QLabel("🔔 Direct Feedback Webhook (Discord / Slack / Google Script / API):")
        wh_lbl.setStyleSheet("font-size: 11.5px; color: #94A3B8;")
        wh_row.addWidget(wh_lbl)

        self.txt_webhook_url = QLineEdit()
        self.txt_webhook_url.setPlaceholderText("https://... (Optional: paste Webhook URL to receive instant notifications)")
        if self.settings_manager:
            self.txt_webhook_url.setText(str(self.settings_manager.get("feedback_webhook_url", "") or ""))
        wh_row.addWidget(self.txt_webhook_url, 1)

        self.btn_save_webhook = QPushButton("Save Webhook")
        self.btn_save_webhook.setCursor(Qt.PointingHandCursor)
        self.btn_save_webhook.clicked.connect(self._on_save_webhook)
        wh_row.addWidget(self.btn_save_webhook)

        s_layout.addLayout(wh_row)
        self.main_layout.addWidget(store_frame)

        # 2. User Sentiment, Community Check-In & Feedback Form
        form_frame = QFrame()
        form_frame.setObjectName("CardWidget")
        f_layout = QVBoxLayout(form_frame)
        f_layout.setContentsMargins(16, 12, 16, 12)
        f_layout.setSpacing(8)

        lbl_title = QLabel("💬 How Are You Feeling About Todo Bird? (Community Check-In & Feedback)")
        lbl_title.setStyleSheet("font-weight: 700; font-size: 14px; color: #E95420;")
        f_layout.addWidget(lbl_title)

        # Mood + Star Rating Row
        sentiment_row = QHBoxLayout()
        sentiment_row.setSpacing(6)
        mood_lbl = QLabel("Your Feeling:")
        mood_lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
        sentiment_row.addWidget(mood_lbl)

        for idx, mood_text in enumerate(MOOD_OPTIONS):
            m_btn = QPushButton(mood_text)
            m_btn.setCheckable(True)
            m_btn.setCursor(Qt.PointingHandCursor)
            m_btn.clicked.connect(lambda _c=False, m=mood_text: self._set_feeling(m))
            sentiment_row.addWidget(m_btn)
            self.mood_buttons.append(m_btn)

        sentiment_row.addSpacing(12)
        star_lbl = QLabel("Rating:")
        star_lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
        sentiment_row.addWidget(star_lbl)

        for s_val in range(1, 6):
            s_btn = QPushButton(f"{s_val} ★")
            s_btn.setCheckable(True)
            s_btn.setCursor(Qt.PointingHandCursor)
            s_btn.setFixedWidth(44)
            s_btn.clicked.connect(lambda _c=False, v=s_val: self._set_rating(v))
            sentiment_row.addWidget(s_btn)
            self.star_buttons.append(s_btn)

        sentiment_row.addStretch()
        f_layout.addLayout(sentiment_row)
        self._set_feeling(MOOD_OPTIONS[0])
        self._set_rating(5)

        # Who Is Using Todo Bird (Optional User Profile Row)
        profile_row = QHBoxLayout()
        profile_row.setSpacing(8)

        self.txt_user_name = QLineEdit()
        self.txt_user_name.setPlaceholderText("Your Name / Handle (optional)")
        if self.settings_manager:
            sal = str(self.settings_manager.get("user_display_name") or self.settings_manager.get("user_salutation") or "")
            if sal and sal != "friend":
                self.txt_user_name.setText(sal)
        profile_row.addWidget(self.txt_user_name, 1)

        self.cmb_user_role = QComboBox()
        self.cmb_user_role.addItems([
            "Role: Software Engineer / Dev",
            "Role: Project / Product Manager",
            "Role: Founder / Executive",
            "Role: Student / Researcher",
            "Role: Designer / Creator",
            "Role: Personal Productivity",
            "Role: Other",
        ])
        profile_row.addWidget(self.cmb_user_role, 1)

        self.txt_user_country = QLineEdit()
        self.txt_user_country.setPlaceholderText("Country / City (e.g. India, USA, UK)")
        if self.settings_manager:
            ctry = str(self.settings_manager.get("user_country") or self.settings_manager.get("region_country") or "")
            if ctry:
                self.txt_user_country.setText(ctry)
        profile_row.addWidget(self.txt_user_country, 1)

        self.txt_user_email = QLineEdit()
        self.txt_user_email.setPlaceholderText("Email / Contact (optional)")
        profile_row.addWidget(self.txt_user_email, 1)

        f_layout.addLayout(profile_row)

        # Title + Category + Severity Row
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.txt_title = QLineEdit()
        self.txt_title.setPlaceholderText("Headline / Summary (e.g. 'Loving the Gantt & World Clock!' or feature idea)...")
        row1.addWidget(self.txt_title, 2)

        self.cmb_category = QComboBox()
        self.cmb_category.addItems([
            "Appreciation & Review",
            "Feature Request / Idea",
            "First-Time UX / Teaching",
            "Bug / Issue Report",
        ])
        row1.addWidget(self.cmb_category, 1)

        self.cmb_severity = QComboBox()
        self.cmb_severity.addItems(["Low", "Medium", "High", "Critical"])
        self.cmb_severity.setCurrentText("Medium")
        row1.addWidget(self.cmb_severity, 1)

        f_layout.addLayout(row1)

        self.txt_desc = QTextEdit()
        self.txt_desc.setPlaceholderText(
            "Tell us how you feel about Todo Bird, how it's helping your daily workflow, "
            "or what features you'd love to see next..."
        )
        self.txt_desc.setMaximumHeight(68)
        f_layout.addWidget(self.txt_desc)

        # Action Buttons Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.send_github_btn = QPushButton("🚀 Submit & Send to Developer (GitHub Wall) ↗")
        self.send_github_btn.setObjectName("PrimaryButton")
        self.send_github_btn.setCursor(Qt.PointingHandCursor)
        self.send_github_btn.setToolTip(
            "Saves your feedback AND opens a pre-filled post on DUVORIXEN/TodoBird so the creator sees it immediately!"
        )
        self.send_github_btn.clicked.connect(lambda: self.submit_issue(send_to_github=True))
        btn_row.addWidget(self.send_github_btn)

        sub_btn = QPushButton("💾 Submit Feedback")
        sub_btn.setCursor(Qt.PointingHandCursor)
        sub_btn.clicked.connect(lambda: self.submit_issue(send_to_github=False))
        btn_row.addWidget(sub_btn)

        exp_btn = QPushButton("📤 Export JSON Report")
        exp_btn.setCursor(Qt.PointingHandCursor)
        exp_btn.clicked.connect(self.export_report)
        btn_row.addWidget(exp_btn)

        btn_row.addStretch()
        f_layout.addLayout(btn_row)

        self.main_layout.addWidget(form_frame)

        # 3. Recorded Feedback & Community Pulse Table
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Date", "User & Country", "Feeling", "Rating", "Channel", "Title", "Status"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.main_layout.addWidget(self.table, 1)

    def _set_feeling(self, feeling: str):
        self.selected_feeling = feeling
        for btn in self.mood_buttons:
            active = btn.text() == feeling
            btn.setChecked(active)
            if active:
                btn.setStyleSheet(
                    "QPushButton { background-color: #E95420; color: #FFFFFF; font-weight: 700; "
                    "border-radius: 6px; padding: 4px 10px; border: none; }"
                )
            else:
                btn.setStyleSheet("")

    def _set_rating(self, stars: int):
        self.selected_rating = int(max(1, min(5, stars)))
        for idx, btn in enumerate(self.star_buttons):
            val = idx + 1
            active = val <= self.selected_rating
            btn.setChecked(val == self.selected_rating)
            if active:
                btn.setStyleSheet(
                    "QPushButton { background-color: rgba(245, 158, 11, 0.25); color: #FBBF24; "
                    "border: 1px solid #F59E0B; font-weight: 700; border-radius: 6px; padding: 4px; }"
                )
            else:
                btn.setStyleSheet("")

    def _on_save_webhook(self):
        url = self.txt_webhook_url.text().strip()
        if url and not url.startswith("https://"):
            QMessageBox.warning(self, "Invalid Webhook", "Webhook URL must start with https://")
            return
        if self.settings_manager:
            self.settings_manager.set("feedback_webhook_url", url)
        self.btn_save_webhook.setText("Saved ✓")

    def _on_fetch_live_downloads(self):
        self.btn_refresh_downloads.setText("Fetching...")
        stats = self.logger_engine.fetch_github_release_downloads()
        self.btn_refresh_downloads.setText("🔄 Check Live Downloads")

        if stats.get("ok"):
            assets_str = " | ".join(
                f"{a['name']}: {a['downloads']} downloads"
                for a in stats.get("assets", [])
            ) or "No release assets found"
            self.lbl_store_status.setText(
                f"• Ubuntu Snap Store: LIVE v1.0.1 (Rev 3)   "
                f"• GitHub Release ({stats.get('latest_tag')}): {stats.get('total_downloads')} total downloads ({assets_str})"
            )
        else:
            self.lbl_store_status.setText(
                f"• Ubuntu Snap Store: LIVE v1.0.1 (Rev 3)   "
                f"• Windows Store: v1.0.1.0 MSIX Ready (Offline / GitHub API unreachable: {stats.get('error', '')[:45]})"
            )

    def submit_issue(self, send_to_github: bool = False):
        title = self.txt_title.text().strip()
        desc = self.txt_desc.toPlainText().strip()
        sev = self.cmb_severity.currentText()
        category = self.cmb_category.currentText()
        user_name = self.txt_user_name.text().strip()
        user_role = self.cmb_user_role.currentText().replace("Role: ", "").strip()
        user_country = self.txt_user_country.text().strip()
        user_email = self.txt_user_email.text().strip()

        if not title:
            QMessageBox.warning(self, "Required", "Please enter an issue title or feedback headline.")
            return

        if self.settings_manager:
            if user_name:
                self.settings_manager.set("user_display_name", user_name)
            if user_country:
                self.settings_manager.set("user_country", user_country)

        issue = self.logger_engine.log_issue(
            title=title,
            severity=sev,
            description=desc,
            rating=self.selected_rating,
            feeling=self.selected_feeling,
            category=category,
            user_name=user_name,
            user_role=user_role,
            user_country=user_country,
            user_email=user_email,
        )

        # Deliver via configured HTTPS Webhook if present
        webhook_url = self.txt_webhook_url.text().strip()
        webhook_note = ""
        if webhook_url.startswith("https://"):
            ok, msg = self.logger_engine.send_webhook_payload(webhook_url, issue)
            webhook_note = f"\n\nWebhook delivery: {msg}" if ok else f"\n\nWebhook notice: {msg}"

        # Optionally open pre-filled GitHub Community Feedback Wall
        if send_to_github:
            gh_url = self.logger_engine.build_github_feedback_url(issue)
            QDesktopServices.openUrl(QUrl(gh_url))

        self.txt_title.clear()
        self.txt_desc.clear()
        QMessageBox.information(
            self,
            "Submitted",
            f"Thank you! Your feedback ({self.selected_rating}★ — {self.selected_feeling}) "
            f"has been recorded.{webhook_note}",
        )
        self.refresh_data()

    def export_report(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Diagnostic & Feedback Report",
            "todobird_feedback_report.json",
            "JSON Files (*.json)",
        )
        if not file_path:
            return

        if self.logger_engine.export_issue_report(Path(file_path)):
            QMessageBox.information(self, "Export Complete", f"Diagnostic report saved to:\n{file_path}")

    def refresh_data(self):
        issues = self.logger_engine.get_all_issues()
        self.table.setRowCount(len(issues))

        for idx, issue in enumerate(reversed(issues)):
            user_str = issue.get("user_name") or "Anonymous"
            if issue.get("user_country"):
                user_str += f" ({issue['user_country']})"
            rating_val = int(issue.get("rating", 5) or 5)
            rating_str = f"{rating_val} ★"

            self.table.setItem(idx, 0, QTableWidgetItem(issue.get("issue_id", "")))
            self.table.setItem(idx, 1, QTableWidgetItem(issue.get("date", "")[:10]))
            self.table.setItem(idx, 2, QTableWidgetItem(user_str))
            self.table.setItem(idx, 3, QTableWidgetItem(issue.get("feeling", "😊 Happy")))
            self.table.setItem(idx, 4, QTableWidgetItem(rating_str))
            self.table.setItem(idx, 5, QTableWidgetItem(issue.get("install_channel", issue.get("os", ""))))
            self.table.setItem(idx, 6, QTableWidgetItem(issue.get("title", "")))
            self.table.setItem(idx, 7, QTableWidgetItem(issue.get("status", "Submitted")))
