"""
TODO BIRD — MODERN SEARCH FIELD COMPONENT
Provides a sleek, rounded search input field with leading vector magnifying glass,
   ✕       """

from typing import Optional
from PySide6.QtCore import Qt, QRectF, QSize, Signal, QTimer, QEvent
from PySide6.QtWidgets import QLineEdit, QWidget, QHBoxLayout, QToolButton
from PySide6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QFont,
    QFocusEvent,
)

from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.services.icon_service import IconService
from todo_bird_app.services.appearance_service import semantic_tokens_for


class SearchField(QLineEdit):
    """
    Modern Search Field with leading vector icon, clear action, and debounced signal.
    """

    debouncedSearch = Signal(str)

    def __init__(
        self,
        placeholder: str = "Search tasks, WBS, projects...",
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
        debounce_ms: int = 200,
    ):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self._is_dark = is_dark
        self._accent_color = accent_color
        self._is_hovered = False
        self._is_focused = False

        self._update_geometry()
        self.setClearButtonEnabled(True)

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(debounce_ms)
        self._debounce_timer.timeout.connect(self._emit_debounced)

        self.textChanged.connect(self._on_text_changed)
        self._apply_style()

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color
        self._update_geometry()
        self._apply_style()
        self.update()

    def _update_geometry(self):
        fm = self.fontMetrics()
        self.setMinimumHeight(max(28, int(fm.height() + 12)))
        self.setMaximumHeight(16777215)
        self.updateGeometry()

    def _apply_style(self):
        tokens = semantic_tokens_for(self._is_dark, self._accent_color)
        bg = tokens["SURFACE_1"]
        text = tokens["TEXT_PRIMARY"]
        placeholder = tokens["TEXT_MUTED"]
        border = tokens["BORDER_NORMAL"]
        accent = self._accent_color

        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
                padding-left: 32px;
                padding-right: 28px;
            }}
            QLineEdit:hover {{
                border-color: {accent};
            }}
            QLineEdit:focus {{
                border: 1.5px solid {accent};
            }}
        """)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event is not None and event.type() == QEvent.FontChange:
            self._update_geometry()
            self._apply_style()

    def _on_text_changed(self, text: str):
        self._debounce_timer.start()

    def _emit_debounced(self):
        self.debouncedSearch.emit(self.text().strip())

    def paintEvent(self, event):
        super().paintEvent(event)

        # Paint Leading Vector Magnifying Glass
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        tokens = semantic_tokens_for(self._is_dark, self._accent_color)
        icon_col = QColor(self._accent_color) if self.hasFocus() else QColor(tokens["TEXT_SECONDARY"])
        icon_box = QRectF(10, (self.height() - 14) / 2.0, 14, 14)
        IconService.render_vector_icon(painter, "search", icon_box, icon_col, stroke_width=1.6)

        painter.end()
