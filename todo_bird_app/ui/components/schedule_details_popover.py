"""
TODO BIRD — SCHEDULE DETAILS POPOVER COMPONENT
Inspectable, persistent, theme-aware popover dialog providing selectable and copyable
schedule analytics for Tasks, Subtasks, and Summary rows.
"""

from typing import Optional, Any
from PySide6.QtCore import Qt, QPoint, QTimer, QSize
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QApplication,
    QGraphicsDropShadowEffect,
)
from PySide6.QtGui import QColor, QKeySequence, QShortcut, QKeyEvent

from todo_bird_app.services.appearance_service import AppearanceService
from todo_bird_app.services.schedule_details_formatter import (
    ScheduleDetailsFormatter,
    ScheduleDetailsModel,
)


class ScheduleDetailsPopover(QDialog):
    """
    Persistent, inspectable schedule details popover dialog.
    Supports mouse text selection, prominent [Copy Details] action,
    Ctrl+C shortcut, Esc dismissal, and dynamic Light/Dark theming.
    """

    def __init__(
        self,
        entity: Any,
        parent: Optional[QWidget] = None,
        project_name: Optional[str] = None,
        db_manager: Any = None,
        is_dark: Optional[bool] = None,
        accent_color: Optional[str] = None,
    ):
        super().__init__(parent)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("ScheduleDetailsPopover")

        # Resolve entity model
        if isinstance(entity, ScheduleDetailsModel):
            self.model = entity
        else:
            self.model = ScheduleDetailsFormatter.build_from_entity(
                entity,
                project_name=project_name,
                db_manager=db_manager,
            )

        self.plain_text = ScheduleDetailsFormatter.format_plain_text(self.model)

        # Theme resolution
        app = QApplication.instance()
        appearance = AppearanceService.read(None, app=app)
        self._is_dark = is_dark if is_dark is not None else appearance.is_dark
        self._accent = accent_color or appearance.accent_color
        self._tokens = appearance.tokens

        self._init_ui()
        self._apply_theme()

        # Keyboard shortcuts
        copy_shortcut = QShortcut(QKeySequence.Copy, self)
        copy_shortcut.activated.connect(self.copy_details)
        esc_shortcut = QShortcut(QKeySequence("Esc"), self)
        esc_shortcut.activated.connect(self.close)

    def _init_ui(self):
        self.setMinimumWidth(380)
        self.setMaximumWidth(520)
        self.setMinimumHeight(280)
        self.resize(440, 360)

        main_vbox = QVBoxLayout(self)
        main_vbox.setContentsMargins(12, 12, 12, 12)
        main_vbox.setSpacing(8)

        # 1. Header Bar
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        type_label = ScheduleDetailsFormatter.format_type_label(self.model)
        self.badge_lbl = QLabel(type_label.upper())
        self.badge_lbl.setObjectName("popover_badge")
        header_layout.addWidget(self.badge_lbl)

        self.title_lbl = QLabel(self.model.title)
        self.title_lbl.setObjectName("popover_title")
        self.title_lbl.setWordWrap(True)
        header_layout.addWidget(self.title_lbl, 1)

        self.btn_close_x = QPushButton("✕", self)
        self.btn_close_x.setObjectName("btn_popover_close_x")
        self.btn_close_x.setFixedSize(24, 24)
        self.btn_close_x.setToolTip("Close (Esc)")
        self.btn_close_x.setAccessibleName("Close schedule details")
        self.btn_close_x.clicked.connect(self.close)
        header_layout.addWidget(self.btn_close_x)

        main_vbox.addLayout(header_layout)

        # 2. Selectable Content Browser
        self.browser = QTextBrowser()
        self.browser.setObjectName("popover_browser")
        self.browser.setOpenExternalLinks(False)
        self.browser.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
        )
        html_content = ScheduleDetailsFormatter.format_html(self.model, is_dark=self._is_dark)
        self.browser.setHtml(html_content)
        main_vbox.addWidget(self.browser, 1)

        # 3. Action Footer
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 4, 0, 0)
        footer_layout.setSpacing(8)

        self.btn_copy_details = QPushButton("Copy Details")
        self.btn_copy_details.setObjectName("btn_copy_details")
        self.btn_copy_details.setAccessibleName("Copy Details")
        self.btn_copy_details.setToolTip("Copy formatted schedule details to clipboard (Ctrl+C)")
        self.btn_copy_details.setFocusPolicy(Qt.StrongFocus)
        self.btn_copy_details.clicked.connect(self.copy_details)
        footer_layout.addWidget(self.btn_copy_details)

        footer_layout.addStretch(1)

        self.btn_close = QPushButton("Close")
        self.btn_close.setObjectName("btn_popover_close")
        self.btn_close.setToolTip("Close popover (Esc)")
        self.btn_close.clicked.connect(self.close)
        footer_layout.addWidget(self.btn_close)

        main_vbox.addLayout(footer_layout)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 110 if self._is_dark else 45))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

    def _apply_theme(self):
        if not self._is_dark:
            bg = "#FFFFFF"
            browser_bg = "#F8FAFC"
            border = "#CBD5E1"
            text = "#0F172A"
            btn_close_hover = "#E2E8F0"
        else:
            bg = "#1E1E2E"
            browser_bg = "#242538"
            border = "#3D3F56"
            text = "#F4F7FB"
            btn_close_hover = "#2A2B3D"

        badge_bg = "#8B5CF6" if self.model.is_summary else (self._accent or "#3584E4")

        self.setStyleSheet(f"""
            QDialog#ScheduleDetailsPopover {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 10px;
                color: {text};
            }}
            QLabel#popover_title {{
                color: {text};
                font-size: 14px;
                font-weight: bold;
            }}
            QLabel#popover_badge {{
                background-color: {badge_bg};
                color: #FFFFFF;
                font-size: 10px;
                font-weight: bold;
                padding: 2px 6px;
                border-radius: 4px;
            }}
            QTextBrowser#popover_browser {{
                background-color: {browser_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 6px;
            }}
            QPushButton#btn_copy_details {{
                background-color: {badge_bg};
                color: #FFFFFF;
                font-weight: 600;
                font-size: 12px;
                padding: 6px 14px;
                border: 1px solid transparent;
                border-radius: 6px;
            }}
            QPushButton#btn_copy_details:hover {{
                opacity: 0.9;
            }}
            QPushButton#btn_popover_close, QPushButton#btn_popover_close_x {{
                background-color: transparent;
                color: {text};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 12px;
            }}
            QPushButton#btn_popover_close:hover, QPushButton#btn_popover_close_x:hover {{
                background-color: {btn_close_hover};
            }}
        """)

    def copy_details(self):
        """Copies plain text schedule details to system clipboard and provides visual feedback."""
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self.plain_text)

        old_text = self.btn_copy_details.text()
        self.btn_copy_details.setText("Copied!")
        self.btn_copy_details.setEnabled(False)

        def restore():
            if self and self.isVisible():
                self.btn_copy_details.setText(old_text)
                self.btn_copy_details.setEnabled(True)

        QTimer.singleShot(1400, restore)

    def popup_at_point(self, global_point: QPoint):
        """Displays popover positioned nicely near global_point."""
        # Ensure within screen bounds
        screen = QApplication.screenAt(global_point) or QApplication.primaryScreen()
        if screen:
            screen_geom = screen.availableGeometry()
            x = min(global_point.x() + 10, screen_geom.right() - self.width() - 10)
            y = min(global_point.y() + 10, screen_geom.bottom() - self.height() - 10)
            x = max(screen_geom.left() + 10, x)
            y = max(screen_geom.top() + 10, y)
            self.move(x, y)
        else:
            self.move(global_point.x() + 10, global_point.y() + 10)
        self.show()
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self.close()
            event.accept()
            return
        if event.key() == Qt.Key_C and (event.modifiers() & Qt.ControlModifier):
            self.copy_details()
            event.accept()
            return
        super().keyPressEvent(event)
