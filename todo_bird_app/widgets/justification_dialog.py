from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QTextEdit,
    QPushButton,
    QFrame,
    QScrollArea,
    QWidget,
    QSizePolicy,
    QDateEdit,
    QTimeEdit,
    QCheckBox,
)
from PySide6.QtCore import Qt, QDate, QTime, QCoreApplication, QEvent, QTimer
from datetime import date, datetime, time
import re

from todo_bird_app.models.task import Task


DELAY_REASONS = [
    "Task took longer than expected",
    "Interrupted by another task",
    "Meeting or phone call",
    "Technical problem",
    "Waiting for someone",
    "Low energy or health",
    "Priority changed",
    "Personal reason",
    "Other",
]


class DelayJustificationDialog(QDialog):
    """
    Professional 3W1H+ recovery workspace.

    Captures:
      WHAT happened?
      WHY did it happen?
      WHO owns recovery?
      WHEN will recovery happen?
      HOW will recurrence be prevented?

    The dialog is intentionally scrollable and resizable so content
    never overlaps on smaller displays or larger application fonts.
    """

    def __init__(
        self,
        task: Task,
        delay_minutes: int = 0,
        parent=None,
    ):
        super().__init__(parent)

        self.task = task
        self.delay_minutes = max(
            0,
            int(delay_minutes or 0),
        )

        self.selected_reason = (
            DELAY_REASONS[0]
        )
        self.notes = ""

        self.setWindowTitle(
            "3W1H+ Recovery & Delay Review"
        )
        self.setWindowFlags(
            Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint |
            Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint
        )
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.register(self, role="delay_justification_dialog")

        # Never return to the old fixed 480x360 layout.
        self.setMinimumSize(
            680,
            560,
        )

        self.resize(
            820,
            760,
        )

        self.setSizeGripEnabled(True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        self._init_ui()
        self._restore_existing_recovery()

    def done(self, r):
        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.unregister(self)
        super().done(r)
        QTimer.singleShot(0, self.deleteLater)

    def deleteLater(self):
        try:
            super().deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        except RuntimeError:
            pass

    def _delay_text(self):
        minutes = int(
            self.delay_minutes
            or 0
        )

        days, remainder = divmod(
            minutes,
            1440,
        )

        hours, mins = divmod(
            remainder,
            60,
        )

        parts = []

        if days:
            parts.append(
                f"{days}d"
            )

        if hours:
            parts.append(
                f"{hours}h"
            )

        if mins or not parts:
            parts.append(
                f"{mins}m"
            )

        return " ".join(parts)


    def _make_editor(
        self,
        placeholder,
        height=72,
    ):
        editor = QTextEdit()

        editor.setPlaceholderText(
            placeholder
        )

        editor.setMinimumHeight(
            height
        )

        editor.setMaximumHeight(
            max(
                height,
                105,
            )
        )

        editor.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        return editor


    def _add_question(
        self,
        layout,
        number,
        title,
        explanation,
        editor,
    ):
        card = QFrame()
        card.setObjectName(
            "CardWidget"
        )

        card_layout = QVBoxLayout(
            card
        )

        card_layout.setContentsMargins(
            14,
            10,
            14,
            12,
        )

        card_layout.setSpacing(6)

        heading = QLabel(
            f"{number}. {title}"
        )

        heading.setStyleSheet(
            "font-weight:700;"
            "font-size:13px;"
        )

        card_layout.addWidget(
            heading
        )

        hint = QLabel(
            explanation
        )

        hint.setWordWrap(True)
        hint.setStyleSheet(
            "color:#6B7280;"
            "font-size:11px;"
        )

        card_layout.addWidget(
            hint
        )

        card_layout.addWidget(
            editor
        )

        layout.addWidget(
            card
        )


    def _init_ui(self):
        outer = QVBoxLayout(
            self
        )

        outer.setContentsMargins(
            14,
            14,
            14,
            14,
        )

        outer.setSpacing(10)

        # -----------------------------------------------
        # Fixed header
        # -----------------------------------------------
        header = QFrame()
        header.setObjectName(
            "CardWidget"
        )

        header_layout = QVBoxLayout(
            header
        )

        header_layout.setContentsMargins(
            16,
            12,
            16,
            12,
        )

        title = QLabel("3W1H+ Recovery Review")

        title.setStyleSheet(
            "font-size:18px;"
            "font-weight:800;"
        )

        header_layout.addWidget(
            title
        )

        task_label = QLabel(
            f"<b>Task:</b> "
            f"{self.task.title}"
        )

        task_label.setWordWrap(True)

        header_layout.addWidget(
            task_label
        )

        delay_label = QLabel(
            "Schedule variance: "
            f"<b>{self._delay_text()}</b>"
        )

        delay_label.setStyleSheet(
            "color:#DC2626;"
            "font-weight:650;"
        )

        header_layout.addWidget(
            delay_label
        )

        explanation = QLabel(
            "Capture the recovery plan now so the delay becomes "
            "actionable information rather than only a red warning."
        )

        explanation.setWordWrap(True)
        explanation.setStyleSheet(
            "color:#6B7280;"
        )

        header_layout.addWidget(
            explanation
        )

        outer.addWidget(
            header
        )

        # -----------------------------------------------
        # Scrollable body
        # -----------------------------------------------
        scroll = QScrollArea()

        scroll.setWidgetResizable(
            True
        )

        scroll.setFrameShape(
            QFrame.Shape.NoFrame
        )

        body = QWidget()

        body_layout = QVBoxLayout(
            body
        )

        body_layout.setContentsMargins(
            4,
            4,
            8,
            8,
        )

        body_layout.setSpacing(
            10
        )

        reason_card = QFrame()
        reason_card.setObjectName(
            "CardWidget"
        )

        reason_layout = QVBoxLayout(
            reason_card
        )

        reason_layout.setContentsMargins(
            14,
            10,
            14,
            12,
        )

        reason_title = QLabel(
            "Primary delay category"
        )

        reason_title.setStyleSheet(
            "font-weight:700;"
        )

        reason_layout.addWidget(
            reason_title
        )

        self.reason_combo = QComboBox()
        self.reason_combo.addItems(
            DELAY_REASONS
        )

        reason_layout.addWidget(
            self.reason_combo
        )

        body_layout.addWidget(
            reason_card
        )

        self.what_input = self._make_editor(
            "Describe exactly what happened."
        )

        self.why_input = self._make_editor(
            "Describe the root cause — not only the symptom."
        )

        self.who_input = self._make_editor(
            "Name the person/team responsible for recovery.",
            64,
        )

        self.how_input = self._make_editor(
            "Define prevention, countermeasure or changed working method."
        )

        self._add_question(
            body_layout,
            "W1",
            "WHAT happened?",
            "State the event or deviation clearly.",
            self.what_input,
        )

        self._add_question(
            body_layout,
            "W2",
            "WHY did it happen?",
            "Capture the real root cause or contributing cause.",
            self.why_input,
        )

        self._add_question(
            body_layout,
            "W3",
            "WHO owns recovery?",
            "Assign clear recovery ownership.",
            self.who_input,
        )

        # Structured Date + Time Container for W4 (WHEN)
        when_card = QFrame()
        when_card.setObjectName("CardWidget")
        when_card_layout = QVBoxLayout(when_card)
        when_card_layout.setContentsMargins(14, 10, 14, 12)
        when_card_layout.setSpacing(6)

        when_title = QLabel("4. WHEN will it recover? (Target Date & Time)")
        when_title.setStyleSheet("font-weight:700;")
        when_card_layout.addWidget(when_title)

        when_hint = QLabel("Define target revised date and time commitment.")
        when_hint.setStyleSheet("color:#6B7280; font-size:11px;")
        when_card_layout.addWidget(when_hint)

        when_row = QHBoxLayout()
        when_row.setSpacing(8)

        self.date_when = QDateEdit()
        self.date_when.setCalendarPopup(True)
        self.date_when.setDisplayFormat("yyyy-MM-dd")
        self.date_when.setDate(QDate.currentDate())

        self.time_when = QTimeEdit()
        self.time_when.setDisplayFormat("HH:mm")
        self.time_when.setTime(QTime(9, 0))

        self.chk_time_not_decided = QCheckBox("Time not decided")

        when_lbl_icon = QLabel()
        from todo_bird_app.services.icon_service import IconService
        when_lbl_icon.setPixmap(IconService.get_pixmap("calendar", 14, "#9AA6BD"))
        when_row.addWidget(when_lbl_icon)
        when_row.addWidget(self.date_when, 3)
        when_row.addWidget(QLabel(""))
        when_row.addWidget(self.time_when, 2)
        when_row.addWidget(self.chk_time_not_decided, 3)
        when_card_layout.addLayout(when_row)

        self.lbl_when_summary = QLabel()
        self.lbl_when_summary.setStyleSheet("font-size:12px; color:#9CA3AF; font-style:italic;")
        when_card_layout.addWidget(self.lbl_when_summary)

        self.date_when.dateChanged.connect(lambda _d: self._update_when_summary())
        self.time_when.timeChanged.connect(lambda _t: self._update_when_summary())
        self.chk_time_not_decided.toggled.connect(lambda _c: self._update_when_summary())

        body_layout.addWidget(when_card)

        self._add_question(
            body_layout,
            "H1",
            "HOW will recurrence be prevented?",
            "Record the preventive action or process improvement.",
            self.how_input,
        )

        notes_card = QFrame()
        notes_card.setObjectName(
            "CardWidget"
        )

        notes_layout = QVBoxLayout(
            notes_card
        )

        notes_layout.setContentsMargins(
            14,
            10,
            14,
            12,
        )

        notes_title = QLabel(
            "Additional notes"
        )

        notes_title.setStyleSheet(
            "font-weight:700;"
        )

        notes_layout.addWidget(
            notes_title
        )

        self.notes_input = (
            self._make_editor(
                "Optional supporting context, lesson learned, "
                "escalation or follow-up notes."
            )
        )

        notes_layout.addWidget(
            self.notes_input
        )

        body_layout.addWidget(
            notes_card
        )

        body_layout.addStretch()

        scroll.setWidget(
            body
        )

        outer.addWidget(
            scroll,
            1,
        )

        # -----------------------------------------------
        # Fixed bottom actions
        # -----------------------------------------------
        action_frame = QFrame()
        action_frame.setObjectName(
            "CardWidget"
        )

        action_layout = QHBoxLayout(
            action_frame
        )

        action_layout.setContentsMargins(
            12,
            8,
            12,
            8,
        )

        hint = QLabel(
            "Recovery information is stored with this task."
        )

        hint.setStyleSheet(
            "color:#6B7280;"
            "font-size:11px;"
        )

        action_layout.addWidget(
            hint
        )

        action_layout.addStretch()

        cancel_btn = QPushButton(
            "Skip / Dismiss (Optional)"
        )

        cancel_btn.clicked.connect(
            self.reject
        )

        action_layout.addWidget(
            cancel_btn
        )

        save_btn = QPushButton(
            "Save Recovery"
        )

        save_btn.setObjectName(
            "PrimaryButton"
        )

        save_btn.clicked.connect(
            self.on_save
        )

        action_layout.addWidget(
            save_btn
        )

        outer.addWidget(
            action_frame
        )


    def _restore_existing_recovery(self):
        """
        Re-open an existing 3W1H record without losing prior work.
        """
        notes = (
            self.task.delay_notes
            or ""
        )

        if not notes:
            return

        mapping = {
            "WHAT:": self.what_input,
            "WHY:": self.why_input,
            "WHO:": self.who_input,
            "HOW:": self.how_input,
            "NOTES:": self.notes_input,
        }
        parse_keys = [*mapping.keys(), "WHEN:"]

        current_key = None
        collected = {
            key: []
            for key in parse_keys
        }

        for line in notes.splitlines():
            matched = False

            for key in parse_keys:
                if line.startswith(key):
                    current_key = key

                    collected[key].append(
                        line[len(key):].strip()
                    )

                    matched = True
                    break

            if (
                not matched
                and current_key
            ):
                collected[
                    current_key
                ].append(
                    line
                )

        for key, editor in mapping.items():
            value = "\n".join(
                collected[key]
            ).strip()

            if value:
                editor.setPlainText(
                    value
                )

        reason = (
            self.task.delay_reason
            or ""
        )

        if reason:
            index = (
                self.reason_combo.findText(
                    reason
                )
            )

            if index >= 0:
                self.reason_combo.setCurrentIndex(
                    index
                )


        # 4. Restore WHEN Date/Time
        p_date = getattr(self.task, "planned_date", None)
        if p_date:
            qd = QDate.fromString(str(p_date)[:10], "yyyy-MM-dd")
            if qd.isValid():
                self.date_when.setDate(qd)
        p_time = getattr(self.task, "planned_start_time", None)
        if p_time and str(p_time).strip():
            qt = QTime.fromString(str(p_time).strip()[:5], "HH:mm")
            if qt.isValid():
                self.time_when.setTime(qt)
                self.chk_time_not_decided.setChecked(False)
            else:
                self.chk_time_not_decided.setChecked(True)
        else:
            legacy_when = " ".join(collected.get("WHEN:", [])).strip()
            legacy_date = re.search(r"\d{4}-\d{2}-\d{2}", legacy_when)
            legacy_time = re.search(r"\b\d{1,2}:\d{2}\b", legacy_when)

            if legacy_date:
                qd = QDate.fromString(legacy_date.group(0), "yyyy-MM-dd")
                if qd.isValid():
                    self.date_when.setDate(qd)

            if "time not decided" in legacy_when.lower():
                self.chk_time_not_decided.setChecked(True)
            elif legacy_time:
                qt = QTime.fromString(legacy_time.group(0), "HH:mm")
                if qt.isValid():
                    self.time_when.setTime(qt)
                    self.chk_time_not_decided.setChecked(False)
                else:
                    self.chk_time_not_decided.setChecked(True)
            else:
                self.chk_time_not_decided.setChecked(True)

        self._update_when_summary()

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
        self.selected_reason = (
            self.reason_combo
            .currentText()
        )

        when_date_str = self.date_when.date().toString("yyyy-MM-dd")
        if self.chk_time_not_decided.isChecked():
            when_val = f"{when_date_str} (Time not decided)"
            if hasattr(self.task, "planned_start_time"):
                self.task.planned_start_time = None
        else:
            when_time_str = self.time_when.time().toString("HH:mm")
            when_val = f"{when_date_str} {when_time_str}"
            if hasattr(self.task, "planned_start_time"):
                self.task.planned_start_time = when_time_str

        if hasattr(self.task, "planned_date"):
            self.task.planned_date = when_date_str

        recovery = {
            "WHAT": self.what_input.toPlainText().strip(),
            "WHY": self.why_input.toPlainText().strip(),
            "WHO": self.who_input.toPlainText().strip(),
            "WHEN": when_val,
            "HOW": self.how_input.toPlainText().strip(),
            "NOTES": self.notes_input.toPlainText().strip(),
        }

        self.notes = "\n".join(
            f"{key}: {value}"
            for key, value in recovery.items()
            if value
        )

        self.accept()
