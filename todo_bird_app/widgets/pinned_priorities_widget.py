from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QApplication,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPalette, QFont

from todo_bird_app.services.typography_service import TypographyService


def _safe_color(value, fallback):
    color = QColor(value or "")
    return color.name() if color.isValid() else fallback


def _contrast_text(background):
    c = QColor(background)
    if not c.isValid():
        return "#FFFFFF"
    luminance = (
        0.299 * c.red()
        + 0.587 * c.green()
        + 0.114 * c.blue()
    )
    return "#111827" if luminance > 160 else "#FFFFFF"


def _appearance_palette(style_mode, app_theme, pin_color):
    """
    Return card visual tokens.

    Auto follows the Todo Bird application theme.
    Pin color always remains the visual priority accent.
    """
    style_mode = (style_mode or "auto").lower()
    app_theme = (app_theme or "dark").lower()

    if style_mode == "auto":
        style_mode = "light" if app_theme == "light" else "dark"

    if style_mode == "light":
        return {
            "card_bg": "#F8FAFC",
            "title": "#111827",
            "meta": "#475569",
            "muted": "#64748B",
            "control_bg": "#E2E8F0",
            "control_hover": "#CBD5E1",
            "control_text": "#111827",
            "panel_bg": "rgba(255,255,255,115)",
            "panel_border": "rgba(100,116,139,90)",
        }

    if style_mode == "glass":
        if app_theme == "light":
            return {
                "card_bg": "rgba(255,255,255,185)",
                "title": "#111827",
                "meta": "#334155",
                "muted": "#64748B",
                "control_bg": "rgba(15,23,42,18)",
                "control_hover": "rgba(15,23,42,35)",
                "control_text": "#111827",
                "panel_bg": "rgba(255,255,255,70)",
                "panel_border": "rgba(100,116,139,80)",
            }
        return {
            "card_bg": "rgba(28,34,46,195)",
            "title": "#F8FAFC",
            "meta": "#CBD5E1",
            "muted": "#94A3B8",
            "control_bg": "rgba(255,255,255,22)",
            "control_hover": "rgba(255,255,255,48)",
            "control_text": "#F8FAFC",
            "panel_bg": "rgba(255,255,255,7)",
            "panel_border": "rgba(148,163,184,55)",
        }

    if style_mode == "high_contrast":
        return {
            "card_bg": "#000000",
            "title": "#FFFFFF",
            "meta": "#FFFFFF",
            "muted": "#E5E7EB",
            "control_bg": "#FFFFFF",
            "control_hover": "#FACC15",
            "control_text": "#000000",
            "panel_bg": "#050505",
            "panel_border": "#FFFFFF",
        }

    # Dark
    return {
        "card_bg": "#181D26",
        "title": "#F9FAFB",
        "meta": "#B8C0CC",
        "muted": "#9CA3AF",
        "control_bg": "#303744",
        "control_hover": "#485160",
        "control_text": "#FFFFFF",
        "panel_bg": "rgba(255,255,255,7)",
        "panel_border": "rgba(148,163,184,40)",
    }


class PinnedTaskCard(QFrame):
    """Compact premium card representing one persistent pinned task."""

    edit_requested = Signal(int)
    unpin_requested = Signal(int)
    move_left_requested = Signal(int)
    move_right_requested = Signal(int)

    def __init__(
        self,
        task_row,
        project_name="Inbox",
        can_move_left=False,
        can_move_right=False,
        appearance_mode="auto",
        app_theme="dark",
        settings_manager=None,
        parent=None,
    ):
        super().__init__(parent)

        self.settings_manager = settings_manager or getattr(parent, "settings_manager", None)
        self.task_id = int(task_row["id"])
        self.pin_color = _safe_color(
            task_row.get("pin_color"),
            "#E95420"
        )

        visual = _appearance_palette(
            appearance_mode,
            app_theme,
            self.pin_color,
        )

        self.setObjectName("PinnedTaskCard")
        self.setMinimumWidth(285)
        self.setMaximumWidth(365)
        self.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Fixed
        )

        self.setStyleSheet(
            f"""
            QFrame#PinnedTaskCard {{
                background: {visual["card_bg"]};
                border: 1px solid {self.pin_color};
                border-left: 6px solid {self.pin_color};
                border-radius: 11px;
            }}

            QFrame#PinnedTaskCard QLabel {{
                background: transparent;
            }}

            QFrame#PinnedTaskCard QPushButton#PinControl {{
                color: {visual["control_text"]};
                background: {visual["control_bg"]};
                border: 1px solid rgba(148,163,184,95);
                border-radius: 6px;
                padding: 5px 8px;
                min-height: 22px;
            }}

            QFrame#PinnedTaskCard QPushButton#PinControl:hover {{
                background: {visual["control_hover"]};
                border: 1px solid {self.pin_color};
            }}

            QFrame#PinnedTaskCard QPushButton#PinControl:disabled {{
                color: rgba(128,128,128,110);
                background: rgba(128,128,128,20);
                border-color: rgba(128,128,128,40);
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 10, 9)
        layout.setSpacing(6)

        # ----------------------------------------------------
        # TITLE
        # ----------------------------------------------------
        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        from todo_bird_app.services.icon_service import IconService
        self.pin_icon_label = QLabel()
        self.pin_icon_label.setPixmap(
            IconService.get_pixmap("pin", 14, "#E95420")
        )
        self.pin_icon_label.setStyleSheet("font-size: 17px;")
        title_row.addWidget(self.pin_icon_label)

        self.title_label = QLabel(
            task_row.get("title") or "Untitled"
        )
        self.title_label.setWordWrap(False)
        self.title_label.setToolTip(task_row.get("title") or "")
        self.title_label.setStyleSheet(
            f"""
            color: {visual["title"]};
            """
        )
        title_row.addWidget(self.title_label, 1)

        layout.addLayout(title_row)

        # ----------------------------------------------------
        # HIGH-VISIBILITY ACTION TOOLBAR
        # ----------------------------------------------------
        controls = QHBoxLayout()
        controls.setSpacing(5)

        self.left_btn = QPushButton("◀  Left")
        self.left_btn.setObjectName("PinControl")
        self.left_btn.setToolTip(
            "Move this pinned priority one position left"
        )
        self.left_btn.setEnabled(can_move_left)
        self.left_btn.clicked.connect(
            lambda: self.move_left_requested.emit(
                self.task_id
            )
        )

        self.right_btn = QPushButton("Right  ▶")
        self.right_btn.setObjectName("PinControl")
        self.right_btn.setToolTip(
            "Move this pinned priority one position right"
        )
        self.right_btn.setEnabled(can_move_right)
        self.right_btn.clicked.connect(
            lambda: self.move_right_requested.emit(
                self.task_id
            )
        )

        self.unpin_btn = QPushButton("✕")
        self.unpin_btn.setObjectName("PinControl")
        self.unpin_btn.setToolTip(
            "Remove this task from Pinned Priorities"
        )
        self.unpin_btn.clicked.connect(
            lambda: self.unpin_requested.emit(
                self.task_id
            )
        )

        controls.addWidget(self.left_btn)
        controls.addWidget(self.right_btn)
        controls.addStretch()
        controls.addWidget(self.unpin_btn)

        layout.addLayout(controls)

        # ----------------------------------------------------
        # META
        # ----------------------------------------------------
        status = task_row.get("status") or "Inbox"
        progress = max(
            0,
            min(
                int(task_row.get("progress") or 0),
                100,
            ),
        )
        priority = task_row.get("priority") or "Medium"

        status_icons = {
            "Inbox": "○",
            "Planned": "◦",
            "In Progress": "▶",
            "Moved": "↪",
            "Completed": "✓",
        }

        status_icon = status_icons.get(status, "○")

        self.meta_label = QLabel(
            f"{project_name}   "
            f"{status_icon} {status}   "
            f"{progress}%"
        )
        self.meta_label.setStyleSheet(
            f"""
            color: {visual["meta"]};
            """
        )
        layout.addWidget(self.meta_label)

        schedule_bits = []

        planned_date = task_row.get("planned_date")
        if planned_date:
            schedule_bits.append(
                f"Planned {planned_date}"
            )

        start_time = task_row.get(
            "planned_start_time"
        )
        end_time = task_row.get(
            "planned_end_time"
        )

        if start_time or end_time:
            schedule_bits.append(
                f"{start_time or '--:--'}"
                f"–{end_time or '--:--'}"
            )

        schedule_bits.append(
            priority
        )

        self.schedule_label = QLabel(
            "   ".join(schedule_bits)
        )
        self.schedule_label.setStyleSheet(
            f"""
            color: {visual["muted"]};
            """
        )
        layout.addWidget(self.schedule_label)

        # ----------------------------------------------------
        # PRIMARY ACTION
        # ----------------------------------------------------
        open_text_color = _contrast_text(
            self.pin_color
        )

        self.open_btn = QPushButton("Open Task")
        self.open_btn.setCursor(Qt.PointingHandCursor)
        self.open_btn.setStyleSheet(
            f"""
            QPushButton {{
                color: {open_text_color};
                background: {self.pin_color};
                border-radius: 7px;
                padding: 6px 11px;
                border: 1px solid {self.pin_color};
            }}
            QPushButton:hover {{
                border: 2px solid {visual["title"]};
            }}
            """
        )
        self.open_btn.clicked.connect(
            lambda: self.edit_requested.emit(
                self.task_id
            )
        )
        layout.addWidget(self.open_btn)

        self.apply_typography()

    def apply_typography(self):
        """Applies configured pinned_tasks typography to card and its children."""
        base_font = TypographyService.get_font_for_area("pinned_tasks", self.settings_manager)
        self.setFont(base_font)

        title_font = QFont(base_font)
        title_font.setPointSize(max(8, base_font.pointSize() + 2))
        title_font.setWeight(base_font.weight())
        self.title_label.setFont(title_font)

        meta_font = QFont(base_font)
        meta_font.setPointSize(max(7, base_font.pointSize() - 1))
        meta_font.setWeight(QFont.Weight.Normal)
        self.meta_label.setFont(meta_font)
        self.schedule_label.setFont(meta_font)

        self.left_btn.setFont(base_font)
        self.right_btn.setFont(base_font)
        self.unpin_btn.setFont(base_font)
        self.open_btn.setFont(base_font)

        custom_color = TypographyService.get_font_color_for_area("pinned_tasks", self.settings_manager)
        if custom_color:
            self.title_label.setStyleSheet(f"color: {custom_color};")


class PinnedPrioritiesWidget(QFrame):
    """
    Reusable premium Pinned Priorities workspace.

    Pin updates are narrow SQL operations and do not overwrite
    task workflow/scheduling metadata.
    """

    edit_requested = Signal(int)
    changed = Signal()

    def __init__(
        self,
        db_manager,
        settings_manager=None,
        parent=None,
    ):
        super().__init__(parent)

        self.db_manager = db_manager
        self.settings_manager = (
            settings_manager
            or getattr(parent, "settings_manager", None)
        )
        self._cleaned_up = False
        self._global_typography_connected = False

        self.setObjectName(
            "PinnedPrioritiesPanel"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 9, 12, 10)
        outer.setSpacing(7)

        # ----------------------------------------------------
        # HEADER
        # ----------------------------------------------------
        header = QHBoxLayout()

        self.title_label = QLabel(
            "Pinned Priorities"
        )
        self.title_label.setStyleSheet(
            "font-size: 14px; font-weight: 800;"
        )

        self.count_label = QLabel("0 pinned")

        self.hint_label = QLabel(
            "Edit task, then enable Pin this task"
        )

        header.addWidget(self.title_label)
        header.addWidget(self.count_label)
        header.addStretch()
        header.addWidget(self.hint_label)

        outer.addLayout(header)

        try:
            from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
            _GLOBAL_EVENT_BUS.typography_changed.connect(self.apply_typography)
            self._global_typography_connected = True
        except Exception:
            pass

        # ----------------------------------------------------
        # HORIZONTAL CARD STRIP
        # ----------------------------------------------------
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )
        self.scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setMinimumHeight(155)

        self.content = QWidget()
        self.cards_layout = QHBoxLayout(
            self.content
        )
        self.cards_layout.setContentsMargins(
            1, 2, 1, 2
        )
        self.cards_layout.setSpacing(9)
        self.cards_layout.setAlignment(
            Qt.AlignLeft
        )

        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll, 1)

        self.refresh_data()

    def cleanup(self):
        if getattr(self, "_cleaned_up", False):
            return
        self._cleaned_up = True
        try:
            from todo_bird_app.controllers.task_controller import (
                _GLOBAL_EVENT_BUS,
            )
            if getattr(self, "_global_typography_connected", False):
                try:
                    _GLOBAL_EVENT_BUS.typography_changed.disconnect(
                        self.apply_typography
                    )
                except Exception:
                    pass
                self._global_typography_connected = False
        except Exception:
            pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def deleteLater(self):
        self.cleanup()
        super().deleteLater()

    def apply_typography(self):
        """Applies configured pinned_tasks typography to panel and all cards."""
        if getattr(self, "_cleaned_up", False):
            return

        self._apply_panel_style()
        for i in range(self.cards_layout.count()):
            item = self.cards_layout.itemAt(i)
            if item:
                w = item.widget()
                if isinstance(w, PinnedTaskCard):
                    w.apply_typography()

    def _setting(self, key, default):
        if self.settings_manager is None:
            return default
        try:
            return self.settings_manager.get(
                key,
                default,
            )
        except Exception:
            return default

    def _app_theme(self):
        value = self._setting(
            "theme",
            "",
        )

        if value in ("dark", "light"):
            return value

        app = QApplication.instance()
        if app is None:
            return "dark"

        window_color = app.palette().color(
            QPalette.Window
        )
        return (
            "light"
            if window_color.lightness() > 128
            else "dark"
        )

    def _style_mode(self):
        value = str(
            self._setting(
                "pinned_card_style",
                "auto",
            )
        ).lower()

        allowed = {
            "auto",
            "light",
            "dark",
            "glass",
            "high_contrast",
        }

        return (
            value
            if value in allowed
            else "auto"
        )

    def _apply_panel_style(self):
        visual = _appearance_palette(
            self._style_mode(),
            self._app_theme(),
            "#E95420",
        )

        self.setStyleSheet(
            f"""
            QFrame#PinnedPrioritiesPanel {{
                background: {visual["panel_bg"]};
                border: 1px solid {visual["panel_border"]};
                border-radius: 12px;
            }}
            """
        )

        panel_font = TypographyService.get_font_for_area("pinned_tasks", self.settings_manager)
        self.setFont(panel_font)

        title_font = QFont(panel_font)
        title_font.setPointSize(max(9, panel_font.pointSize() + 3))
        title_font.setWeight(panel_font.weight())
        self.title_label.setFont(title_font)
        self.title_label.setStyleSheet(
            f"""
            color: {visual["title"]};
            """
        )

        self.count_label.setFont(panel_font)
        self.count_label.setStyleSheet(
            f"""
            color: {visual["muted"]};
            """
        )

        self.hint_label.setFont(panel_font)
        self.hint_label.setStyleSheet(
            f"""
            color: {visual["muted"]};
            """
        )

    def _get_projects(self):
        try:
            rows = self.db_manager.get_all_projects()
        except Exception:
            rows = []

        return {
            int(row.get("id")):
            row.get("name", "Inbox")
            for row in rows
            if row.get("id") is not None
        }

    def _get_pinned_rows(self):
        with self.db_manager.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM tasks
                WHERE is_pinned = 1
                ORDER BY
                    CASE
                        WHEN pin_position IS NULL
                             OR pin_position <= 0
                        THEN 2147483647
                        ELSE pin_position
                    END ASC,
                    id DESC;
                """
            ).fetchall()

        return [dict(row) for row in rows]

    def refresh_data(self):
        self._apply_panel_style()

        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        rows = self._get_pinned_rows()
        projects = self._get_projects()

        self.count_label.setText(
            f"{len(rows)} pinned"
        )

        panel_font = TypographyService.get_font_for_area("pinned_tasks", self.settings_manager)

        if not rows:
            visual = _appearance_palette(
                self._style_mode(),
                self._app_theme(),
                "#E95420",
            )

            empty = QLabel(
                "No pinned priorities yet. "
                "Open a task and enable "
                "Pin this task in the task editor."
            )
            empty.setFont(panel_font)
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                f"""
                color: {visual["muted"]};
                padding: 28px 18px;
                """
            )
            self.cards_layout.addWidget(empty)
            self.cards_layout.addStretch()
            return

        appearance_mode = self._style_mode()
        app_theme = self._app_theme()

        for index, row in enumerate(rows):
            project_name = projects.get(
                int(row.get("project_id") or 1),
                "Inbox",
            )

            card = PinnedTaskCard(
                row,
                project_name=project_name,
                can_move_left=index > 0,
                can_move_right=(
                    index < len(rows) - 1
                ),
                appearance_mode=appearance_mode,
                app_theme=app_theme,
                settings_manager=self.settings_manager,
                parent=self.content,
            )

            card.edit_requested.connect(
                self.edit_requested.emit
            )

            card.unpin_requested.connect(
                self.unpin_task
            )

            card.move_left_requested.connect(
                lambda task_id, direction=-1:
                self.move_task(
                    task_id,
                    direction,
                )
            )

            card.move_right_requested.connect(
                lambda task_id, direction=1:
                self.move_task(
                    task_id,
                    direction,
                )
            )

            self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()

    def unpin_task(self, task_id: int):
        with self.db_manager.get_connection() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET is_pinned = 0,
                    pin_position = 0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?;
                """,
                (task_id,),
            )
            conn.commit()

        self._normalize_positions()
        self.refresh_data()
        self.changed.emit()
        try:
            from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
            _GLOBAL_EVENT_BUS.tasks_changed.emit()
        except Exception:
            pass

    def move_task(
        self,
        task_id: int,
        direction: int,
    ):
        rows = self._get_pinned_rows()
        ids = [
            int(row["id"])
            for row in rows
        ]

        if task_id not in ids:
            return

        current = ids.index(task_id)
        target = current + direction

        if target < 0 or target >= len(ids):
            return

        ids[current], ids[target] = (
            ids[target],
            ids[current],
        )

        with self.db_manager.get_connection() as conn:
            for pos, pinned_id in enumerate(
                ids,
                start=1,
            ):
                conn.execute(
                    """
                    UPDATE tasks
                    SET pin_position = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?;
                    """,
                    (pos, pinned_id),
                )
            conn.commit()

        self.refresh_data()
        self.changed.emit()

    def _normalize_positions(self):
        rows = self._get_pinned_rows()

        with self.db_manager.get_connection() as conn:
            for pos, row in enumerate(
                rows,
                start=1,
            ):
                conn.execute(
                    """
                    UPDATE tasks
                    SET pin_position = ?
                    WHERE id = ?;
                    """,
                    (
                        pos,
                        int(row["id"]),
                    ),
                )
            conn.commit()
