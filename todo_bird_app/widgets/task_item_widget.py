import logging
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QCheckBox, QLabel, QPushButton, QProgressBar
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon

from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.services.icon_manager import IconManager
from todo_bird_app.widgets.confirm_delete_dialog import ConfirmDeleteDialog

logger = logging.getLogger(__name__)

PRIORITY_COLORS = {
    TaskPriority.LOW: "#9CA3AF",
    TaskPriority.MEDIUM: "#3584E4",
    TaskPriority.HIGH: "#E95420",
    TaskPriority.URGENT: "#EF4444",
}

STATUS_COLORS = {
    TaskStatus.INBOX: "#3584E4",
    TaskStatus.PLANNED: "#8B5CF6",
    TaskStatus.IN_PROGRESS: "#F59E0B",
    TaskStatus.COMPLETED: "#10B981",
    TaskStatus.DELAYED: "#EF4444",
    TaskStatus.MOVED: "#E95420",
    TaskStatus.CANCELLED: "#6B7280",
}

class TaskItemWidget(QFrame):
    """
    Interactive Card Widget representing a Task item in views.
    Includes accessible icon action buttons, clean single status/priority chips,
    and high-contrast delete confirmation guard.
    """
    status_toggled = Signal(int)   # task_id
    preview_requested = Signal(int) # task_id
    edit_requested = Signal(int)    # task_id
    delete_requested = Signal(int)  # task_id

    def __init__(self, task: Task, project_name: str = "Inbox", settings_manager=None, parent=None):
        super().__init__(parent)
        self.task = task
        self.project_name = project_name
        self.settings_manager = settings_manager
        self.setObjectName("CardWidget")
        self.setCursor(Qt.PointingHandCursor)
        self._update_rich_tooltip()
        self._init_ui()

    @staticmethod
    def _html_to_plain(html_text: str) -> str:
        """Extract plain text from stored HTML without leaking tags (S4.2.2)."""
        if not html_text:
            return ""
        # Prefer Qt's rich-text parser; fallback to regex if Qt unavailable/headless.
        try:
            from PySide6.QtGui import QTextDocument

            doc = QTextDocument()
            doc.setHtml(html_text)
            return doc.toPlainText()
        except Exception:
            import re

            # strip script/style already sanitized, naive tag strip
            txt = re.sub(r"<[^>]+>", " ", html_text)
            # unescape entities
            import html as _html

            txt = _html.unescape(txt)
            # collapse whitespace
            txt = re.sub(r"\s+", " ", txt).strip()
            return txt

    def _update_rich_tooltip(self):
        import html
        from todo_bird_app.utils.time_math import format_duration_display
        lines = [f"<b>{html.escape(self.task.title)}</b>"]
        if self.task.description:
            # S4.2.2: never leak raw HTML tags into tooltip/preview; use plain extraction
            plain = self._html_to_plain(self.task.description).strip()
            # Remove newlines for single-line preview, truncate after plain conversion
            plain = plain.replace("\n", " ").replace("\r", " ")
            import re as _re

            plain = _re.sub(r"\s+", " ", plain).strip()
            preview = plain[:180]
            if len(plain) > 180:
                preview += "..."
            clean_desc = html.escape(preview)
            if clean_desc:
                lines.append(f"<i>{clean_desc}</i>")
        if self.task.planned_date:
            time_str = f" ({self.task.planned_start_time}–{self.task.planned_end_time})" if self.task.planned_start_time else ""
            lines.append(f"Planned: {self.task.planned_date}{time_str}")
        if self.task.due_date:
            lines.append(f"Due: {self.task.due_date}")
        if getattr(self.task, "planned_effort_minutes", 0) > 0:
            lines.append(f"Planned Effort: {format_duration_display(self.task.planned_effort_minutes)}")
        if getattr(self.task, "actual_duration", 0) > 0:
            lines.append(f"Actual Effort: {format_duration_display(self.task.actual_duration)}")
        self.setToolTip("<br>".join(lines))

    def _elided_pill(self, text: str, stylesheet: str, max_width: int = 140) -> QLabel:
        """Pill chip that yields width before it can crush the title."""
        badge = QLabel(text)
        fm = badge.fontMetrics()
        if fm.horizontalAdvance(text) > max_width - 22:
            badge.setText(fm.elidedText(text, Qt.ElideRight, max_width - 22))
        badge.setMaximumWidth(max_width)
        badge.setStyleSheet(stylesheet)
        return badge

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(6)

        # Standardized Row Order:
        # [Checkbox] [Title] [Priority Chip] [Single Status Chip] [Edit Icon] [Delete Icon]
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        # 1. Completion Checkbox
        self.checkbox = QCheckBox()
        self.checkbox.setCursor(Qt.PointingHandCursor)
        self.checkbox.setChecked(self.task.status == TaskStatus.COMPLETED)
        self.checkbox.stateChanged.connect(lambda: self.status_toggled.emit(self.task.id))
        top_row.addWidget(self.checkbox)

        # 1b. Optional Task Cover Thumbnail
        if getattr(self.task, "image_path", ""):
            from todo_bird_app.services.media_service import MediaService
            pm = MediaService.load_pixmap(self.task.image_path, max_width=32, max_height=32, use_thumbnail=True)
            if pm and not pm.isNull():
                thumb_lbl = QLabel()
                thumb_lbl.setFixedSize(32, 32)
                thumb_lbl.setPixmap(pm)
                thumb_lbl.setStyleSheet("border-radius: 4px; border: 1px solid palette(midlight);")
                top_row.addWidget(thumb_lbl)

        # 2. Title Label — stretch(1) lets it absorb ALL shrink; the capped
        # pills below never outbid it for space.
        self.title_label = QLabel(self.task.title)
        self.title_label.setStyleSheet(
            "text-decoration: line-through; color: palette(mid);"
            if self.task.status == TaskStatus.COMPLETED
            else ""
        )
        top_row.addWidget(self.title_label, 1)

        # 3. Priority Pill Chip (Appears Exactly Once)
        p_color = PRIORITY_COLORS.get(self.task.priority, "#3584E4")
        p_badge = self._elided_pill(
            self.task.priority.value,
            f"""
            background-color: {p_color}22;
            color: {p_color};
            border: 1px solid {p_color}44;
            border-radius: 6px;
            padding: 2px 8px;
        """,
        )
        top_row.addWidget(p_badge)

        # 4. Single Status Pill Chip (Appears Exactly Once)
        s_color = STATUS_COLORS.get(self.task.status, "#3584E4")
        s_badge = self._elided_pill(
            self.task.status.value,
            f"""
            background-color: {s_color}22;
            color: {s_color};
            border: 1px solid {s_color}44;
            border-radius: 6px;
            padding: 2px 8px;
        """,
        )
        top_row.addWidget(s_badge)

        # Show Project Pill Badge ONLY if custom project (never duplicate "Inbox")
        if self.project_name and self.project_name.lower() != "inbox":
            proj_badge = self._elided_pill(
                self.project_name,
                """
                background-color: rgba(128, 128, 128, 0.14);
                border-radius: 6px;
                padding: 2px 8px;
            """,
            )
            proj_badge.setToolTip(self.project_name)
            top_row.addWidget(proj_badge)

        # 4b. Reminder Bell Indicator
        has_reminder = bool(
            getattr(self.task, "startup_reminder", False)
            or (getattr(self.task, "startup_reminder_mode", "off") not in ("off", "", None))
        )
        if has_reminder:
            from todo_bird_app.services.icon_service import IconService
            rem_badge = QLabel()
            rem_badge.setPixmap(
                IconService.get_pixmap("bell", 13, "#6FA8F5")
            )
            rem_badge.setFixedSize(20, 18)
            rem_badge.setAlignment(Qt.AlignCenter)
            rem_badge.setToolTip("Reminder active")
            rem_badge.setStyleSheet("""
                background-color: rgba(53, 132, 228, 0.12);
                border: 1px solid rgba(53, 132, 228, 0.25);
                border-radius: 6px;
                padding: 2px 6px;
            """)
            top_row.addWidget(rem_badge)

        # 5. Edit Button (Action 1)
        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setMinimumWidth(68)
        self.edit_btn.setMinimumHeight(30)
        self.edit_btn.setCursor(Qt.PointingHandCursor)
        self.edit_btn.setToolTip("Open full task editor")
        self.edit_btn.setAccessibleName("Open full task editor")
        self.edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.task.id))
        top_row.addWidget(self.edit_btn)

        # 6. Delete Button (Action 2)
        del_icon = IconManager.get_icon("delete")
        self.del_btn = QPushButton()
        if not del_icon.isNull():
            self.del_btn.setIcon(del_icon)
            self.del_btn.setIconSize(QSize(16, 16))
        else:
            self.del_btn.setText(IconManager.get_fallback_emoji("delete") or "Delete")

        self.del_btn.setMinimumSize(30, 30)
        self.del_btn.setCursor(Qt.PointingHandCursor)
        self.del_btn.setToolTip("Delete task")
        self.del_btn.setAccessibleName("Delete task")
        self.del_btn.clicked.connect(self.on_delete_clicked)
        top_row.addWidget(self.del_btn)

        main_layout.addLayout(top_row)

        # Bottom info row: Date, duration, tags, progress
        meta_row = QHBoxLayout()
        meta_row.setContentsMargins(28, 0, 0, 0)
        meta_row.setSpacing(12)

        meta_info = []
        if self.project_name and self.project_name.lower() != "inbox":
            meta_info.append(self.project_name)
        if self.task.planned_date:
            meta_info.append(f"Planned: {self.task.planned_date}")
        if self.task.due_date:
            meta_info.append(f"Due: {self.task.due_date}")
        if self.task.estimated_duration > 0:
            meta_info.append(f"{self.task.estimated_duration}m est")

        if meta_info:
            meta_label = QLabel(" • ".join(meta_info))
            meta_label.setStyleSheet("color: palette(mid);")
            meta_row.addWidget(meta_label)

        meta_row.addStretch()

        if 0 < self.task.progress < 100:
            p_bar = QProgressBar()
            p_bar.setRange(0, 100)
            p_bar.setValue(self.task.progress)
            p_bar.setFixedWidth(100)
            p_bar.setFixedHeight(8)
            p_bar.setTextVisible(False)
            meta_row.addWidget(p_bar)

        main_layout.addLayout(meta_row)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.task.id is not None:
            self.preview_requested.emit(self.task.id)
            event.accept()
            return
        super().mousePressEvent(event)

    def on_delete_clicked(self):
        confirm = True
        if self.settings_manager:
            confirm = self.settings_manager.get("confirm_delete_task", True)

        if confirm:
            dlg = ConfirmDeleteDialog(self.task.title, parent=self)
            if dlg.exec() == ConfirmDeleteDialog.Accepted:
                self.delete_requested.emit(self.task.id)
        else:
            self.delete_requested.emit(self.task.id)
