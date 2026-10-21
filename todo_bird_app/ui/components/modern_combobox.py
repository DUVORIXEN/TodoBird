"""
TODO BIRD — MODERN COMBOBOX & SEARCHABLE DROPDOWN SYSTEM
Provides a premium dropdown control with custom-styled popup menu,
high-DPI vector chevron, semantic focus ring, and searchable filtering for large option sets.
"""

from typing import Optional, List, Any, Callable
from PySide6.QtCore import Qt, QRectF, QSize, Signal, QPoint, QEvent
from PySide6.QtWidgets import (
    QComboBox,
    QWidget,
    QLineEdit,
    QListView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
    QVBoxLayout,
    QDialog,
    QFrame,
    QScrollArea,
    QApplication,
)
from PySide6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QFont,
    QMouseEvent,
    QKeyEvent,
    QLinearGradient,
)

from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.services.icon_service import IconService
from todo_bird_app.services.appearance_service import semantic_tokens_for


class ModernComboItemDelegate(QStyledItemDelegate):
    """Clean, high-density item delegate for dropdown popups with semantic status indicators."""

    STATUS_DOTS = {
        "all": "#3584E4",
        "all statuses": "#3584E4",
        "active": "#F59E0B",
        "active only": "#F59E0B",
        "planned": "#64748B",
        "in_progress": "#3B82F6",
        "in progress": "#3B82F6",
        "blocked": "#EF4444",
        "completed": "#10B981",
        "delayed": "#F59E0B",
        "milestone": "#8B5CF6",
        "moved": "#8B5CF6",
        "cancelled": "#64748B",
    }

    def __init__(self, parent=None, is_dark: bool = True, accent_color: str = DesignTokens.COLOR_ACCENT):
        super().__init__(parent)
        self.is_dark = is_dark
        self.accent_color = accent_color

    def sizeHint(self, option: Optional[QStyleOptionViewItem], index) -> QSize:
        w = option.rect.width() if (option and hasattr(option, "rect")) else 120
        fm = option.fontMetrics if option is not None else None
        h = max(28, int(fm.height() + 8) if fm is not None else 28)
        return QSize(w, h)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        rect = QRectF(option.rect).adjusted(2, 1, -2, -1)
        is_selected = bool(option.state & QStyle.State_Selected)
        is_hovered = bool(option.state & QStyle.State_MouseOver)
        accent = QColor(self.accent_color)

        # 1. Background
        if is_selected:
            if self.is_dark:
                bg = QColor(accent.red(), accent.green(), accent.blue(), 55)
            else:
                bg = QColor(accent.red(), accent.green(), accent.blue(), 30)
            painter.fillPath(self._rounded_path(rect, 6), QBrush(bg))
            # Left accent indicator on selected item
            ind_bar = QRectF(rect.x() + 1, rect.y() + 2, 2.5, rect.height() - 4)
            painter.fillPath(self._rounded_path(ind_bar, 1.2), QBrush(accent))
        elif is_hovered:
            bg = QColor(255, 255, 255, 16) if self.is_dark else QColor(0, 0, 0, 12)
            painter.fillPath(self._rounded_path(rect, 6), QBrush(bg))

        # 2. Text, Icon & Status Dot
        text = str(index.data(Qt.DisplayRole) or "")
        data_val = str(index.data(Qt.UserRole) or "").lower()
        icon = index.data(Qt.DecorationRole)

        text_x = rect.x() + 10.0
        cy = rect.y() + rect.height() / 2.0

        if icon:
            icon_rect = QRectF(rect.x() + 6, cy - 8.0, 16, 16)
            if hasattr(icon, "paint"):
                icon.paint(painter, icon_rect.toRect())
            text_x += 22.0
        else:
            # Check for semantic status dot
            dot_key = data_val if data_val in self.STATUS_DOTS else text.lower()
            if dot_key in self.STATUS_DOTS:
                dot_col = QColor(self.STATUS_DOTS[dot_key])
                dot_rect = QRectF(text_x, cy - 3.5, 7.0, 7.0)
                path_dot = QPainterPath()
                path_dot.addEllipse(dot_rect)
                painter.fillPath(path_dot, QBrush(dot_col))
                text_x += 14.0

        tokens = semantic_tokens_for(self.is_dark, self.accent_color)
        if is_selected:
            text_col = QColor(tokens["TEXT_ON_ACCENT"]) if self.is_dark else accent.darker(130)
        else:
            text_col = QColor(tokens["TEXT_PRIMARY"])

        painter.setPen(text_col)
        font = painter.font()
        font.setWeight(QFont.DemiBold if is_selected else QFont.Normal)
        painter.setFont(font)

        text_rect = QRectF(text_x, rect.y(), rect.width() - (text_x - rect.x()) - 8, rect.height())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)

        painter.restore()

    def _rounded_path(self, rect: QRectF, radius: float) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path


class ModernComboBox(QComboBox):
    """
    Modern Custom-Drawn QComboBox.
    Replaces default OS bevels with clean rounded container, focus ring, and vector chevron.
    """

    _global_density: str = "balanced"

    @classmethod
    def set_global_density(cls, density: str):
        density = str(density or "balanced").lower().strip()
        if density not in {"compact", "balanced", "spacious"}:
            density = "balanced"
        cls._global_density = density
        app = QApplication.instance()
        if app is None:
            return
        for widget in list(app.allWidgets()):
            if isinstance(widget, cls):
                widget._update_geometry()
                widget.update()

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
    ):
        super().__init__(parent)
        app = QApplication.instance()
        if app is not None:
            app_theme = str(app.property("todoBirdTheme") or "").lower()
            if app_theme in {"dark", "light"}:
                is_dark = app_theme == "dark"
            app_accent = QColor(str(app.property("todoBirdAccent") or ""))
            if app_accent.isValid():
                accent_color = app_accent.name().upper()

        self._is_dark = is_dark
        self._accent_color = accent_color
        self._is_hovered = False
        self._is_focused = False

        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setProperty("todoBirdTheme", "dark" if self._is_dark else "light")
        self.setProperty("todoBirdAccent", self._accent_color)
        self._update_geometry()

        # Apply custom delegate to popup list
        self._delegate = ModernComboItemDelegate(self, is_dark, accent_color)
        self.setItemDelegate(self._delegate)

        # Style popup view
        view = self.view()
        if isinstance(view, QListView):
            view.setSpacing(2)
            view.setUniformItemSizes(True)

        self._apply_theme_qss()

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color
        self.setProperty("todoBirdTheme", "dark" if self._is_dark else "light")
        self.setProperty("todoBirdAccent", self._accent_color)
        self._delegate.is_dark = is_dark
        self._delegate.accent_color = self._accent_color
        self._update_geometry()
        self._apply_theme_qss()
        self.update()

    def _update_geometry(self):
        self.setMinimumHeight(self.sizeHint().height())
        self.setMaximumHeight(16777215)
        self.updateGeometry()

    def _apply_theme_qss(self):
        tokens = semantic_tokens_for(self._is_dark, self._accent_color)
        popup_bg = tokens["SURFACE_1"]
        popup_border = tokens["BORDER_NORMAL"]
        text_col = tokens["TEXT_PRIMARY"]
        metrics = {
            "compact": (8, 4),
            "balanced": (10, 5),
            "spacious": (12, 7),
        }.get(self._global_density, (10, 5))
        padding_h, padding_v = metrics

        self.setStyleSheet(f"""
            QComboBox {{
                border: none;
                border-radius: 8px;
                background-color: transparent;
                padding-left: {padding_h}px;
                padding-right: 28px;
                color: transparent; /* Painted in paintEvent */
            }}
            QComboBox:hover {{
                border: none;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {popup_bg};
                border: 1px solid {popup_border};
                border-radius: 8px;
                padding: {max(3, padding_v - 1)}px;
                outline: none;
                color: {text_col};
                selection-background-color: transparent;
            }}
        """)

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        padding_v = {
            "compact": 4,
            "balanced": 5,
            "spacious": 7,
        }.get(self._global_density, 5)
        height_floor = {
            "compact": 28,
            "balanced": 30,
            "spacious": 32,
        }.get(self._global_density, 30)
        h = max(height_floor, int(fm.height() + (padding_v * 2) + 2))
        text_w = fm.horizontalAdvance(self.currentText()) if self.currentText() else 60
        w = max(110, int(text_w + 48))
        return QSize(w, h)

    def changeEvent(self, event):
        if event is not None and event.type() == QEvent.FontChange:
            try:
                self._update_geometry()
                self.update()
            except RuntimeError:
                pass

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self._is_focused = True
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._is_focused = False
        self.update()
        super().focusOutEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 8.0

        # Compute colors
        tokens = semantic_tokens_for(self._is_dark, self._accent_color)
        if not self.isEnabled():
            bg_col = QColor(tokens["SURFACE_2"])
            border_col = QColor(tokens["BORDER_SUBTLE"])
            text_col = QColor(tokens["TEXT_DISABLED"])
            chevron_col = QColor(tokens["TEXT_DISABLED"])
        else:
            bg_col = QColor(tokens["SURFACE_1"])
            border_col = QColor(self._accent_color) if (self._is_hovered or self._is_focused) else QColor(tokens["BORDER_NORMAL"])
            text_col = QColor(tokens["TEXT_PRIMARY"])
            chevron_col = QColor(self._accent_color) if self._is_hovered else QColor(tokens["TEXT_SECONDARY"])

        # Background & Border
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        painter.fillPath(path, QBrush(bg_col))

        # Top inner specular highlight line
        hi_rect = QRectF(rect.x() + 2, rect.y() + 1, rect.width() - 4, 1.0)
        hi_path = QPainterPath()
        hi_path.addRoundedRect(hi_rect, 1.0, 1.0)
        painter.fillPath(hi_path, QBrush(QColor(255, 255, 255, 45 if self._is_dark else 100)))

        painter.strokePath(path, QPen(border_col, 2.0 if (self._is_hovered or self._is_focused) else 1.5))

        # Focus ring
        if self._is_focused and self.isEnabled():
            focus_path = QPainterPath()
            focus_path.addRoundedRect(rect.adjusted(-1, -1, 1, 1), radius + 1, radius + 1)
            painter.strokePath(focus_path, QPen(QColor(self._accent_color), 1.8))

        # Right vector chevron
        chevron_size = max(14.0, round(self.height() * 0.40))
        chevron_box = QRectF(self.width() - chevron_size - 10, (self.height() - chevron_size) / 2.0, chevron_size, chevron_size)
        stroke_w = max(2.0, chevron_size * 0.14)
        IconService.render_vector_icon(painter, "chevron_down", chevron_box, chevron_col, stroke_width=stroke_w)

        # Selected text with elision to prevent chevron collision.
        # Editable combos (SearchableComboBox) render through their child
        # QLineEdit — painting here as well doubles the text at two offsets.
        text = self.currentText()
        if text and not self.isEditable():
            painter.setFont(self.font())
            painter.setPen(text_col)
            fm = self.fontMetrics()
            max_text_w = max(0, int(self.width() - chevron_size - 22))
            if max_text_w > 0:
                elided = fm.elidedText(text, Qt.ElideRight, max_text_w)
                text_rect = QRectF(12, 0, max_text_w, self.height())
                painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)

        painter.end()


class SearchableComboBox(ModernComboBox):
    """
    Searchable Dropdown for large option lists (100+ items).
    Filters items dynamically as the user types without requiring manual scrolling.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
    ):
        super().__init__(parent, is_dark, accent_color)
        self.setEditable(True)
        line_edit = self.lineEdit()
        if line_edit:
            line_edit.setPlaceholderText("Search or select...")
            line_edit.setStyleSheet("background: transparent; border: none; color: inherit; padding-left: 4px;")
            line_edit.setTextMargins(0, 0, 30, 0)
            line_edit.textChanged.connect(self._on_search_text_changed)

        self._all_items: List[dict] = []

    def set_items_data(self, items: List[dict]):
        """Populates with [{'text': str, 'data': any, 'icon': str}]."""
        self._all_items = list(items)
        self.clear()
        for item in items:
            self.addItem(item.get("text", ""), item.get("data"))

    def _on_search_text_changed(self, text: str):
        search_query = text.strip().lower()
        if not search_query:
            return

        for i in range(self.count()):
            item_text = self.itemText(i).lower()
            # If matches, select
            if search_query in item_text:
                pass
