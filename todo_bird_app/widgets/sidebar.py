from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QStackedWidget,
    QSizePolicy,
    QToolButton,
    QMenu,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import (
    Qt,
    Signal,
    QTimer,
    QPoint,
    QPointF,
    QMimeData,
)
from PySide6.QtGui import (
    QFontMetrics,
    QAction,
    QDrag,
    QPainter,
    QPen,
    QColor,
    QPixmap,
)


class SidebarItemWidget(QPushButton):
    """
    One Todo Bird navigation destination.

    Phase 1F.6.1 keeps navigation semantics independent from presentation:
    the same destination can render as an expanded sidebar row, compact rail
    icon, slim item, tile, glass-dock item, or minimal navigation item.
    """

    def __init__(
        self,
        key: str,
        label: str,
        icon_str: str = "pin",
        count: int = 0,
        parent=None,
        sidebar=None,
    ):
        super().__init__(parent)
        self.key = key
        self.label_text = label
        self.icon_str = icon_str
        self.count = count
        self.sidebar = sidebar
        self._navigation_style = "expanded"
        self._horizontal = False
        self._horizontal_compact_fit = False

        self._drag_start_pos = None
        self._drop_indicator = "none"
        self._is_dragged = False

        self.setObjectName("SidebarItem")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(label)
        self.setToolTip(label)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setAcceptDrops(True)

        self._init_ui()

    def _set_item_icon(self, icon_str: str):
        """Render the item icon as a crisp vector glyph; fall back to text."""
        from todo_bird_app.services.icon_service import IconService

        if IconService.has_icon(icon_str):
            self._icon_is_vector = True
            self.icon_label.setPixmap(
                IconService.get_pixmap(icon_str, 16, "#9AA6BD")
            )
        else:
            self._icon_is_vector = False
            self.icon_label.setText(icon_str)

    def _init_ui(self):
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(12, 8, 12, 8)
        self._layout.setSpacing(10)

        self.icon_label = QLabel()
        self._set_item_icon(self.icon_str)
        self.icon_label.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )

        self.text_label = QLabel(self.label_text)
        self.text_label.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )

        self._layout.addWidget(self.icon_label)
        self._layout.addWidget(self.text_label, 1)

        self.badge_label = QLabel()
        self.badge_label.setObjectName("SidebarBadge")
        self.badge_label.setAlignment(Qt.AlignCenter)
        self.badge_label.setAttribute(
            Qt.WA_TransparentForMouseEvents,
            True,
        )
        self._layout.addWidget(self.badge_label)

        self.update_count(self.count)

    def horizontal_full_width(self) -> int:
        """
        Width required to show this horizontal navigation item without
        truncating its visible destination label.

        Qt QPushButton's native sizeHint does not account reliably for our
        child-label layout because the button itself has no text. Therefore
        Todo Bird owns this content width explicitly.
        """
        metrics = QFontMetrics(self.text_label.font())
        text_width = metrics.horizontalAdvance(
            self.label_text
        )

        icon_width = max(
            20,
            self.icon_label.sizeHint().width(),
        )

        badge_width = 0
        if self.count > 0:
            badge_width = max(
                22,
                self.badge_label.sizeHint().width(),
            )

        style_extra = {
            "expanded": 34,
            "slim": 24,
            "tiles": 40,
            "glass": 32,
            "minimal": 18,
            "rail": 16,
        }.get(
            self._navigation_style,
            30,
        )

        if self._navigation_style == "rail":
            return 46

        return max(
            72,
            icon_width
            + text_width
            + badge_width
            + style_extra,
        )

    def set_horizontal_fit_mode(
        self,
        compact: bool,
    ):
        """
        Compact horizontal fit hides labels completely instead of allowing
        Qt to clip them into fragments such as 'Da' or 'Proj'.

        Full destination text remains in tooltip and accessibility metadata.
        """
        self._horizontal_compact_fit = bool(compact)

        if not self._horizontal:
            return

        if self._horizontal_compact_fit:
            self.text_label.hide()

            # Badges remain useful, but only when a count exists.
            self.badge_label.setVisible(
                self.count > 0
                and self._navigation_style != "minimal"
            )

            self.setMinimumWidth(46)
            self.setMaximumWidth(58)
            self.setSizePolicy(
                QSizePolicy.Fixed,
                QSizePolicy.Fixed,
            )

            self.setToolTip(self.label_text)

        else:
            show_text = self._navigation_style != "rail"
            self.text_label.setVisible(show_text)

            self.badge_label.setVisible(
                self.count > 0
                and self._navigation_style != "minimal"
            )

            if self._navigation_style == "rail":
                width = 46
            else:
                width = self.horizontal_full_width()

            self.setMinimumWidth(width)
            self.setMaximumWidth(width)
            self.setSizePolicy(
                QSizePolicy.Fixed,
                QSizePolicy.Fixed,
            )

        self.updateGeometry()
        self.update()

    def apply_navigation_style(
        self,
        style: str,
        horizontal: bool = False,
    ):
        style = str(style or "expanded").lower().strip()
        self._navigation_style = style
        self._horizontal = bool(horizontal)

        self.setProperty("navStyle", style)
        self.setProperty(
            "navOrientation",
            "horizontal" if horizontal else "vertical",
        )

        show_text = style not in ("rail",)
        show_badge = style not in ("minimal",)

        # Horizontal minimal mode still benefits from destination labels.
        if horizontal and style == "minimal":
            show_text = True

        self.text_label.setVisible(show_text)
        self.badge_label.setVisible(
            show_badge and self.count > 0
        )

        if style == "rail":
            self._layout.setContentsMargins(8, 8, 8, 8)
            self._layout.setSpacing(0)
            self._layout.setAlignment(Qt.AlignCenter)
            self.setMinimumSize(42, 42)

        elif style == "slim":
            self._layout.setContentsMargins(8, 6, 8, 6)
            self._layout.setSpacing(6)
            self._layout.setAlignment(Qt.AlignVCenter)
            self.setMinimumHeight(36)

        elif style == "tiles":
            self._layout.setContentsMargins(12, 10, 12, 10)
            self._layout.setSpacing(9)
            self._layout.setAlignment(Qt.AlignVCenter)
            self.setMinimumHeight(48)

        elif style == "glass":
            self._layout.setContentsMargins(10, 8, 10, 8)
            self._layout.setSpacing(7)
            self._layout.setAlignment(Qt.AlignVCenter)
            self.setMinimumHeight(40)

        elif style == "minimal":
            self._layout.setContentsMargins(7, 5, 7, 5)
            self._layout.setSpacing(6)
            self._layout.setAlignment(Qt.AlignVCenter)
            self.setMinimumHeight(32)

        else:
            self._layout.setContentsMargins(12, 8, 12, 8)
            self._layout.setSpacing(10)
            self._layout.setAlignment(Qt.AlignVCenter)
            self.setMinimumHeight(40)

        if horizontal:
            # Never leave a horizontal navigation item at Qt's generic
            # button sizeHint (~45 px). Establish deterministic content fit.
            self.set_horizontal_fit_mode(
                self._horizontal_compact_fit
            )
        else:
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
            self.setSizePolicy(
                QSizePolicy.Preferred,
                QSizePolicy.Fixed,
            )

        self.style().unpolish(self)
        self.style().polish(self)
        self.updateGeometry()
        self.update()

    def update_count(self, count: int):
        self.count = max(0, int(count or 0))

        if self.count > 0:
            self.badge_label.setText(str(self.count))
            self.badge_label.setVisible(
                self._navigation_style != "minimal"
            )
        else:
            self.badge_label.clear()
            self.badge_label.setVisible(False)

        reorder_hint = "Drag to reorder. Use Alt+Shift+Arrow to move."
        if self.count:
            self.setAccessibleDescription(
                f"{self.label_text}. {self.count} items. {reorder_hint}"
            )
        else:
            self.setAccessibleDescription(
                f"{self.label_text}. {reorder_hint}"
            )

    def set_label(self, label: str):
        """Live-retranslate the item's display label (language switch)."""
        if label == self.label_text:
            return
        self.label_text = label
        self.text_label.setText(label)
        if self._navigation_style == "rail":
            self.setToolTip(label)
        else:
            self.setToolTip(label)
        reorder_hint = "Drag to reorder. Use Alt+Shift+Arrow to move."
        if self.count:
            self.setAccessibleDescription(
                f"{self.label_text}. {self.count} items. {reorder_hint}"
            )
        else:
            self.setAccessibleDescription(
                f"{self.label_text}. {reorder_hint}"
            )
        self.updateGeometry()

    def set_selected(self, selected: bool):
        self.setChecked(selected)
        self.setProperty(
            "selected",
            "true" if selected else "false",
        )
        self.style().unpolish(self)
        self.style().polish(self)

    def _get_sidebar(self):
        if getattr(self, "sidebar", None) is not None:
            return self.sidebar
        curr = self.parentWidget()
        while curr is not None:
            if isinstance(curr, SidebarWidget):
                return curr
            curr = curr.parentWidget()
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            (event.buttons() & Qt.LeftButton)
            and self._drag_start_pos is not None
        ):
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            distance = (pos - self._drag_start_pos).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._start_drag()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _start_drag(self):
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-todobird-nav-key", self.key.encode("utf-8"))
        mime.setText(self.key)
        drag.setMimeData(mime)

        pixmap = self.grab()
        drag.setPixmap(pixmap)
        hotspot = self._drag_start_pos or QPoint(pixmap.width() // 2, pixmap.height() // 2)
        drag.setHotSpot(hotspot)

        eff = QGraphicsOpacityEffect(self)
        eff.setOpacity(0.4)
        self.setGraphicsEffect(eff)
        self._is_dragged = True

        try:
            drag.exec(Qt.MoveAction)
        finally:
            self.setGraphicsEffect(None)
            self._is_dragged = False
            self._drag_start_pos = None
            self.update()

    def _get_mime_key(self, mime: QMimeData):
        if mime.hasFormat("application/x-todobird-nav-key"):
            return bytes(mime.data("application/x-todobird-nav-key")).decode("utf-8")
        if mime.hasText():
            text = mime.text()
            if text in SidebarWidget.canonical_navigation_keys():
                return text
        return None

    def _update_drop_indicator(self, pos):
        if self._horizontal:
            is_before = pos.x() < (self.width() / 2.0)
        else:
            is_before = pos.y() < (self.height() / 2.0)

        new_ind = "before" if is_before else "after"
        if new_ind != self._drop_indicator:
            self.set_drop_indicator(new_ind)

    def set_drop_indicator(self, indicator: str):
        if self._drop_indicator != indicator:
            self._drop_indicator = indicator
            self.update()

    def dragEnterEvent(self, event):
        key = self._get_mime_key(event.mimeData())
        if key and key != self.key:
            event.acceptProposedAction()
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self._update_drop_indicator(pos)
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        key = self._get_mime_key(event.mimeData())
        if key and key != self.key:
            event.acceptProposedAction()
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self._update_drop_indicator(pos)
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self.set_drop_indicator("none")
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        key = self._get_mime_key(event.mimeData())
        ind = self._drop_indicator
        self.set_drop_indicator("none")

        if key and key != self.key:
            event.acceptProposedAction()
            sidebar = self._get_sidebar()
            if sidebar:
                sidebar.reorder_navigation_item(key, self.key, ind)
            return
        super().dropEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)

        if self._drop_indicator in ("before", "after"):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing, True)
            accent = QColor(str(self.property("todoBirdAccent") or ""))
            if not accent.isValid():
                app = QApplication.instance()
                accent = (
                    app.palette().highlight().color()
                    if app is not None
                    else QColor("#2563EB")
                )
            pen = QPen(accent, 3.0)
            painter.setPen(pen)
            if self._horizontal:
                x = 2.0 if self._drop_indicator == "before" else self.width() - 2.0
                painter.drawLine(QPointF(x, 4), QPointF(x, self.height() - 4))
            else:
                y = 2.0 if self._drop_indicator == "before" else self.height() - 2.0
                painter.drawLine(QPointF(8, y), QPointF(self.width() - 8, y))
            painter.end()

    def keyPressEvent(self, event):
        modifiers = event.modifiers()
        is_alt_shift = (modifiers == (Qt.AltModifier | Qt.ShiftModifier))
        is_alt = (modifiers == Qt.AltModifier)
        key = event.key()

        if is_alt_shift or is_alt:
            if key in (Qt.Key_Up, Qt.Key_Left):
                sidebar = self._get_sidebar()
                if sidebar:
                    sidebar.move_navigation_item(self.key, -1)
                    self.setFocus()
                    event.accept()
                    return
            elif key in (Qt.Key_Down, Qt.Key_Right):
                sidebar = self._get_sidebar()
                if sidebar:
                    sidebar.move_navigation_item(self.key, 1)
                    self.setFocus()
                    event.accept()
                    return

        super().keyPressEvent(event)


class SidebarWidget(QWidget):
    """
    Todo Bird Adaptive Navigation Dock.

    Navigation destination semantics stay stable while presentation may move
    between left/right sidebars and top/bottom horizontal docks.
    """

    section_changed = Signal(str)

    # Local layout/presentation signal. MainWindow owns physical placement.
    navigation_preferences_changed = Signal(str, str, str)

    NAV_ITEMS = [
        ("dashboard", "Dashboard", "home"),
        ("inbox", "Inbox", "inbox"),
        ("today", "Today", "star"),
        ("focus", "Focus Mode", "target"),
        ("upcoming", "Upcoming", "calendar"),
        ("projects", "Projects", "folder"),
        ("completed", "Completed", "check_circle"),
        ("calendar", "Calendar", "calendar"),
        ("gantt", "Gantt Chart", "chart"),
        ("analytics", "Analytics", "chart"),
        ("daily_review", "Daily Review", "search"),
        ("feedback", "Pilot Feedback", "chat"),
        ("world_clock", "World Clock", "globe"),
        ("settings", "Settings", "settings"),
    ]

    VALID_POSITIONS = (
        "left",
        "right",
        "top",
        "bottom",
    )

    VALID_STYLES = (
        "expanded",
        "rail",
        "slim",
        "tiles",
        "glass",
        "minimal",
    )

    VALID_ALIGNMENTS = (
        "left",
        "center",
        "right",
    )

    STYLE_WIDTHS = {
        "expanded": 240,
        "rail": 76,
        "slim": 132,
        "tiles": 276,
        "glass": 250,
        "minimal": 184,
    }

    STYLE_HEIGHTS = {
        "expanded": 62,
        "rail": 54,
        "slim": 52,
        "tiles": 76,
        "glass": 62,
        "minimal": 48,
    }

    def __init__(
        self,
        settings_manager=None,
        parent=None,
    ):
        super().__init__(parent)

        self.settings_manager = settings_manager
        self.setObjectName("SidebarContainer")
        self.setAccessibleName("Todo Bird navigation")

        self.item_widgets = {}
        self._all_item_widgets = {}
        self._selected_key = "dashboard"

        # Phase 1F.6.2.1 — navigation personalization authorities.
        self.navigation_order = self._read_navigation_order()
        self.navigation_favorites = self._read_key_list(
            "navigation_favorites",
            [],
        )
        self.navigation_hidden = self._read_key_list(
            "navigation_hidden_items",
            [],
        )
        self._horizontal_overflow_keys = []
        self._cleaned_up = False
        self._global_typography_connected = False

        self.navigation_position = self._read_choice(
            "navigation_position",
            "left",
            self.VALID_POSITIONS,
        )
        self.navigation_style = self._read_choice(
            "navigation_style",
            "expanded",
            self.VALID_STYLES,
        )
        self.navigation_alignment = self._read_choice(
            "navigation_alignment",
            "left",
            self.VALID_ALIGNMENTS,
        )

        self._init_ui()
        self._apply_typography()

        try:
            from todo_bird_app.controllers.task_controller import (
                _GLOBAL_EVENT_BUS,
            )
            _GLOBAL_EVENT_BUS.typography_changed.connect(
                self._apply_typography
            )
            self._global_typography_connected = True
        except Exception:
            pass

        self.apply_navigation_preferences(
            self.navigation_position,
            self.navigation_style,
            self.navigation_alignment,
            persist=False,
            emit_change=False,
        )

    def cleanup(self):
        """Disconnect global event-bus hooks for closed navigation widgets."""
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
                        self._apply_typography
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

    @classmethod
    def canonical_navigation_keys(cls):
        return [
            key
            for key, _title, _icon in cls.NAV_ITEMS
        ]

    def _read_key_list(self, setting_key, default):
        canonical = self.canonical_navigation_keys()

        if self.settings_manager is None:
            raw = list(default)
        else:
            raw = self.settings_manager.get(
                setting_key,
                list(default),
            )

        if not isinstance(raw, list):
            raw = list(default)

        result = []

        for value in raw:
            key = str(value)

            if (
                key in canonical
                and key not in result
            ):
                result.append(key)

        return result

    def _read_navigation_order(self):
        canonical = self.canonical_navigation_keys()

        if self.settings_manager is None:
            return list(canonical)

        raw = self.settings_manager.get(
            "navigation_order",
            canonical,
        )

        if not isinstance(raw, list):
            raw = []

        order = []

        for value in raw:
            key = str(value)

            if (
                key in canonical
                and key not in order
            ):
                order.append(key)

        # Forward compatibility: newly introduced destinations append
        # automatically instead of disappearing from older preferences.
        for key in canonical:
            if key not in order:
                order.append(key)

        return order

    def _persist_navigation_personalization(self):
        if self.settings_manager is None:
            return

        self.settings_manager.set(
            "navigation_order",
            list(self.navigation_order),
        )
        self.settings_manager.set(
            "navigation_favorites",
            list(self.navigation_favorites),
        )
        self.settings_manager.set(
            "navigation_hidden_items",
            list(self.navigation_hidden),
        )

    def visible_navigation_keys(self):
        hidden = set(self.navigation_hidden)

        return [
            key
            for key in self.navigation_order
            if key not in hidden
        ]

    def _navigation_priority_keys(self):
        """
        Overflow priority:
          1. selected destination
          2. favorites
          3. remaining destinations in customer order
        """
        visible = self.visible_navigation_keys()
        priority = []

        if self._selected_key in visible:
            priority.append(self._selected_key)

        for key in self.navigation_favorites:
            if (
                key in visible
                and key not in priority
            ):
                priority.append(key)

        for key in visible:
            if key not in priority:
                priority.append(key)

        return priority

    def _read_choice(
        self,
        key,
        default,
        valid,
    ):
        if self.settings_manager is None:
            return default

        value = str(
            self.settings_manager.get(key, default)
            or default
        ).lower().strip()

        return value if value in valid else default

    def retranslate_ui(self):
        """Live-retranslate every navigation label (language switch)."""
        from todo_bird_app.services.language_service import t

        titles = {key: t(title) for key, title, _icon in self.NAV_ITEMS}
        for orientation_items in self._all_item_widgets.values():
            for key, item in orientation_items.items():
                translated = titles.get(key)
                if translated:
                    item.set_label(translated)
        self.updateGeometry()

    def _create_item_set(
        self,
        parent,
        layout,
        orientation_name,
    ):
        items = {}

        from todo_bird_app.services.language_service import t as _t

        for key, title, icon in self.NAV_ITEMS:
            item = SidebarItemWidget(
                key,
                _t(title),
                icon,
                parent=parent,
                sidebar=self,
            )
            item.clicked.connect(
                lambda _checked=False, k=key:
                self.select_item(k)
            )
            item.customContextMenuRequested.connect(
                lambda pos, k=key, w=item:
                self._show_navigation_item_menu(
                    k,
                    w.mapToGlobal(pos),
                )
            )

            layout.addWidget(item)
            items[key] = item

        self._all_item_widgets[
            orientation_name
        ] = items

        return items

    def _set_brand_pixmap(self, label):
        """Paint the real bird asset; fall back to a wordmark-safe initial."""
        from pathlib import Path
        from PySide6.QtGui import QPixmap

        asset = Path(__file__).resolve().parent.parent / "assets" / "icons" / "todo-bird.png"
        pm = QPixmap(str(asset)) if asset.exists() else QPixmap()
        if not pm.isNull():
            label.setFixedSize(24, 24)
            label.setScaledContents(True)
            label.setPixmap(
                pm.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            label.setText("T")
            label.setFixedWidth(24)

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.pages = QStackedWidget(self)
        self.pages.setObjectName("NavigationPages")
        root.addWidget(self.pages)

        # -------------------------------------------------
        # Vertical sidebar page
        # -------------------------------------------------
        self.vertical_page = QWidget(self.pages)
        v_main = QVBoxLayout(self.vertical_page)
        v_main.setContentsMargins(12, 14, 12, 14)
        v_main.setSpacing(10)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(6, 2, 4, 8)
        brand_row.setSpacing(8)

        self._logo_label = QLabel()
        self._logo_label.setAccessibleName("Todo Bird")
        self._set_brand_pixmap(self._logo_label)

        self._app_title = QLabel("TODO BIRD")
        self._app_title.setObjectName("SidebarBrandTitle")
        self._app_title.setStyleSheet(
            "letter-spacing: 1px;"
        )

        self.vertical_style_button = QPushButton("◫")
        self.vertical_style_button.setObjectName(
            "NavigationCustomizeButton"
        )
        self.vertical_style_button.setToolTip(
            "Cycle navigation style"
        )
        self.vertical_style_button.setAccessibleName(
            "Change navigation style"
        )
        self.vertical_style_button.clicked.connect(
            self.cycle_navigation_style
        )

        brand_row.addWidget(self._logo_label)
        brand_row.addWidget(self._app_title)
        brand_row.addStretch(1)
        brand_row.addWidget(self.vertical_style_button)
        v_main.addLayout(brand_row)

        self.vertical_separator = QFrame()
        self.vertical_separator.setFrameShape(QFrame.HLine)
        self.vertical_separator.setObjectName(
            "NavigationSeparator"
        )
        v_main.addWidget(self.vertical_separator)

        self.vertical_scroll = QScrollArea()
        self.vertical_scroll.setWidgetResizable(True)
        self.vertical_scroll.setFrameShape(QFrame.NoFrame)
        self.vertical_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.vertical_scroll.setStyleSheet(
            "QScrollArea { background: transparent; }"
        )

        vertical_content = QWidget()
        vertical_layout = QVBoxLayout(vertical_content)
        vertical_layout.setContentsMargins(0, 4, 0, 4)
        vertical_layout.setSpacing(4)

        self.vertical_items = self._create_item_set(
            vertical_content,
            vertical_layout,
            "vertical",
        )

        vertical_layout.addStretch(1)
        self.vertical_scroll.setWidget(vertical_content)
        v_main.addWidget(self.vertical_scroll, 1)

        self.pages.addWidget(self.vertical_page)

        # -------------------------------------------------
        # Horizontal top/bottom dock page
        # -------------------------------------------------
        self.horizontal_page = QWidget(self.pages)
        h_main = QHBoxLayout(self.horizontal_page)
        h_main.setContentsMargins(10, 7, 10, 7)
        h_main.setSpacing(8)

        self._horizontal_logo = QLabel()
        self._horizontal_logo.setAccessibleName("Todo Bird")
        self._set_brand_pixmap(self._horizontal_logo)

        self._horizontal_title = QLabel("TODO BIRD")
        self._horizontal_title.setObjectName(
            "SidebarBrandTitle"
        )

        h_main.addWidget(self._horizontal_logo)
        h_main.addWidget(self._horizontal_title)

        self.horizontal_scroll = QScrollArea()
        self.horizontal_scroll.setWidgetResizable(True)
        self.horizontal_scroll.setFrameShape(QFrame.NoFrame)
        self.horizontal_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.horizontal_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAsNeeded
        )
        self.horizontal_scroll.setStyleSheet(
            "QScrollArea { background: transparent; }"
        )

        self.horizontal_content = QWidget()
        self.horizontal_layout = QHBoxLayout(
            self.horizontal_content
        )
        self.horizontal_layout.setContentsMargins(2, 0, 2, 0)
        self.horizontal_layout.setSpacing(5)

        self.horizontal_items = self._create_item_set(
            self.horizontal_content,
            self.horizontal_layout,
            "horizontal",
        )

        self.horizontal_layout.addStretch(1)

        self.horizontal_scroll.setWidget(
            self.horizontal_content
        )
        h_main.addWidget(
            self.horizontal_scroll,
            1,
        )

        self.more_button = QToolButton(self.horizontal_page)
        self.more_button.setObjectName("NavigationMoreButton")
        self.more_button.setText("•••")
        self.more_button.setToolTip(
            "More navigation destinations"
        )
        self.more_button.setAccessibleName(
            "More navigation destinations"
        )
        self.more_button.setPopupMode(
            QToolButton.InstantPopup
        )
        self.more_menu = QMenu(self.more_button)
        self.more_button.setMenu(self.more_menu)
        self.more_button.hide()
        h_main.addWidget(self.more_button)

        self.horizontal_style_button = QPushButton("◫")
        self.horizontal_style_button.setObjectName(
            "NavigationCustomizeButton"
        )
        self.horizontal_style_button.setToolTip(
            "Cycle navigation style"
        )
        self.horizontal_style_button.setAccessibleName(
            "Change navigation style"
        )
        self.horizontal_style_button.clicked.connect(
            self.cycle_navigation_style
        )
        h_main.addWidget(self.horizontal_style_button)

        self.pages.addWidget(self.horizontal_page)

        self._apply_navigation_order_and_visibility()

        self.select_item(
            self._selected_key,
            emit=False,
        )

    def _apply_navigation_order_and_visibility(self):
        visible = set(self.visible_navigation_keys())

        for item_set in self._all_item_widgets.values():
            for key, item in item_set.items():
                item.setVisible(key in visible)

        for layout, item_set in (
            (
                self.vertical_scroll.widget().layout(),
                self.vertical_items,
            ),
            (
                self.horizontal_layout,
                self.horizontal_items,
            ),
        ):
            for item in item_set.values():
                layout.removeWidget(item)

            insert_at = 0

            for key in self.navigation_order:
                item = item_set.get(key)

                if item is None:
                    continue

                layout.insertWidget(
                    insert_at,
                    item,
                )
                insert_at += 1

        self._rebuild_more_menu()

    def _title_for_key(self, key):
        for item_key, title, _icon in self.NAV_ITEMS:
            if item_key == key:
                return title

        return key

    def _icon_for_key(self, key):
        for item_key, _title, icon in self.NAV_ITEMS:
            if item_key == key:
                return icon

        return "•"

    def _show_navigation_item_menu(
        self,
        key,
        global_pos,
    ):
        menu = QMenu(self)

        is_favorite = (
            key in self.navigation_favorites
        )

        favorite_action = QAction(
            (
                "★ Remove from Favorites"
                if is_favorite
                else "☆ Add to Favorites"
            ),
            menu,
        )

        favorite_action.triggered.connect(
            lambda:
            self.set_navigation_favorite(
                key,
                not is_favorite,
            )
        )

        menu.addAction(favorite_action)
        menu.addSeparator()

        try:
            index = self.navigation_order.index(key)
        except ValueError:
            index = -1

        earlier = QAction(
            "Move Earlier",
            menu,
        )
        earlier.setEnabled(index > 0)
        earlier.triggered.connect(
            lambda:
            self.move_navigation_item(
                key,
                -1,
            )
        )
        menu.addAction(earlier)

        later = QAction(
            "Move Later",
            menu,
        )
        later.setEnabled(
            index >= 0
            and index < len(self.navigation_order) - 1
        )
        later.triggered.connect(
            lambda:
            self.move_navigation_item(
                key,
                1,
            )
        )
        menu.addAction(later)

        move_start = QAction(
            "Move to Start",
            menu,
        )
        move_start.setEnabled(index > 0)
        move_start.triggered.connect(
            lambda:
            self.move_navigation_item_to_index(
                key,
                0,
            )
        )
        menu.addAction(move_start)

        move_end = QAction(
            "Move to End",
            menu,
        )
        move_end.setEnabled(
            index >= 0
            and index < len(self.navigation_order) - 1
        )
        move_end.triggered.connect(
            lambda:
            self.move_navigation_item_to_index(
                key,
                len(self.navigation_order) - 1,
            )
        )
        menu.addAction(move_end)

        menu.addSeparator()

        hide_action = QAction(
            "Hide from Navigation",
            menu,
        )

        # Never make the active destination disappear under the cursor.
        hide_action.setEnabled(
            key != self._selected_key
        )

        hide_action.triggered.connect(
            lambda:
            self.set_navigation_hidden(
                key,
                True,
            )
        )

        menu.addAction(hide_action)
        menu.exec(global_pos)

    def set_navigation_favorite(
        self,
        key,
        favorite=True,
    ):
        if key not in self.canonical_navigation_keys():
            return

        if favorite:
            if key not in self.navigation_favorites:
                self.navigation_favorites.append(key)
        else:
            self.navigation_favorites = [
                item
                for item in self.navigation_favorites
                if item != key
            ]

        self._persist_navigation_personalization()
        self._rebuild_more_menu()

        if self.navigation_position in ("top", "bottom"):
            QTimer.singleShot(
                0,
                self._apply_horizontal_fit,
            )

    def set_navigation_hidden(
        self,
        key,
        hidden=True,
    ):
        if key not in self.canonical_navigation_keys():
            return

        if hidden:
            if (
                key != self._selected_key
                and key not in self.navigation_hidden
            ):
                self.navigation_hidden.append(key)
        else:
            self.navigation_hidden = [
                item
                for item in self.navigation_hidden
                if item != key
            ]

        self._persist_navigation_personalization()
        self._apply_navigation_order_and_visibility()

        if self.navigation_position in ("top", "bottom"):
            QTimer.singleShot(
                0,
                self._apply_horizontal_fit,
            )

    def move_navigation_item(
        self,
        key,
        delta,
    ):
        if key not in self.navigation_order:
            return

        old_index = self.navigation_order.index(key)
        new_index = max(
            0,
            min(
                len(self.navigation_order) - 1,
                old_index + int(delta),
            ),
        )

        if old_index == new_index:
            return

        self.navigation_order.pop(old_index)
        self.navigation_order.insert(
            new_index,
            key,
        )

        self._persist_navigation_personalization()
        self._apply_navigation_order_and_visibility()

        if self.navigation_position in ("top", "bottom"):
            QTimer.singleShot(
                0,
                self._apply_horizontal_fit,
            )

    def reorder_navigation_item(
        self,
        source_key: str,
        target_key: str,
        position: str = "before",
    ) -> bool:
        """
        Reorders source_key relative to target_key ('before' or 'after').
        Persists order once and updates visible layouts immediately.
        """
        if (
            source_key not in self.navigation_order
            or target_key not in self.navigation_order
            or source_key == target_key
        ):
            return False

        order = [k for k in self.navigation_order if k != source_key]
        tgt_idx = order.index(target_key)
        insert_idx = tgt_idx if position == "before" else tgt_idx + 1
        order.insert(insert_idx, source_key)

        if order == self.navigation_order:
            return False

        self.navigation_order = order
        self._persist_navigation_personalization()
        self._apply_navigation_order_and_visibility()

        if self.navigation_position in ("top", "bottom"):
            QTimer.singleShot(
                0,
                self._apply_horizontal_fit,
            )

        return True

    def move_navigation_item_to_index(
        self,
        key: str,
        target_index: int,
    ) -> bool:
        if key not in self.navigation_order:
            return False

        old_idx = self.navigation_order.index(key)
        target_idx = max(
            0,
            min(
                len(self.navigation_order) - 1,
                int(target_index),
            ),
        )

        if old_idx == target_idx:
            return False

        order = [k for k in self.navigation_order if k != key]
        order.insert(target_idx, key)

        if order == self.navigation_order:
            return False

        self.navigation_order = order
        self._persist_navigation_personalization()
        self._apply_navigation_order_and_visibility()

        if self.navigation_position in ("top", "bottom"):
            QTimer.singleShot(
                0,
                self._apply_horizontal_fit,
            )

        return True

    def reset_navigation_order(self):
        self.navigation_order = (
            self.canonical_navigation_keys()
        )
        self._persist_navigation_personalization()
        self._apply_navigation_order_and_visibility()

        if self.navigation_position in ("top", "bottom"):
            QTimer.singleShot(
                0,
                self._apply_horizontal_fit,
            )

    def restore_all_navigation_items(self):
        self.navigation_hidden = []
        self._persist_navigation_personalization()
        self._apply_navigation_order_and_visibility()

        if self.navigation_position in ("top", "bottom"):
            QTimer.singleShot(
                0,
                self._apply_horizontal_fit,
            )

    def reset_navigation_personalization(self):
        self.navigation_order = (
            self.canonical_navigation_keys()
        )
        self.navigation_favorites = []
        self.navigation_hidden = []

        self._persist_navigation_personalization()
        self._apply_navigation_order_and_visibility()

        if self.navigation_position in ("top", "bottom"):
            QTimer.singleShot(
                0,
                self._apply_horizontal_fit,
            )

    def _rebuild_more_menu(self):
        if not hasattr(self, "more_menu"):
            return

        self.more_menu.clear()

        overflow = list(
            self._horizontal_overflow_keys
        )

        for key in overflow:
            title = self._title_for_key(key)
            icon = self._icon_for_key(key)

            action = QAction(
                f"{icon}  {title}",
                self.more_menu,
            )

            if key in self.navigation_favorites:
                action.setText(
                    "★ " if key in self.navigation_favorites else "☆ "
                )

            action.triggered.connect(
                lambda _checked=False, k=key:
                self.select_item(k)
            )

            self.more_menu.addAction(action)

        if (
            overflow
            and self.navigation_hidden
        ):
            self.more_menu.addSeparator()

        if self.navigation_hidden:
            hidden_menu = self.more_menu.addMenu(
                "Show Hidden Destination"
            )

            for key in self.navigation_order:
                if key not in self.navigation_hidden:
                    continue

                action = QAction(
                    (
                        f"{self._icon_for_key(key)}  "
                        f"{self._title_for_key(key)}"
                    ),
                    hidden_menu,
                )

                action.triggered.connect(
                    lambda _checked=False, k=key:
                    self.set_navigation_hidden(
                        k,
                        False,
                    )
                )

                hidden_menu.addAction(action)

            self.more_menu.addSeparator()

            restore_action = QAction(
                "Show All Destinations",
                self.more_menu,
            )
            restore_action.triggered.connect(
                self.restore_all_navigation_items
            )
            self.more_menu.addAction(
                restore_action
            )

        self.more_button.setVisible(
            bool(
                overflow
                or self.navigation_hidden
            )
        )

    def _horizontal_full_required_width(self) -> int:
        """
        Required viewport width for complete horizontal labels.

        Includes item spacing and conservative room for branding /
        customization controls.
        """
        widths = [
            item.horizontal_full_width()
            for item in self.horizontal_items.values()
        ]

        spacing = max(
            0,
            len(widths) - 1,
        ) * max(
            0,
            self.horizontal_layout.spacing(),
        )

        return (
            sum(widths)
            + spacing
            + 20
        )

    def _horizontal_compact_required_width(self) -> int:
        count = len(self.horizontal_items)

        spacing = max(
            0,
            count - 1,
        ) * max(
            0,
            self.horizontal_layout.spacing(),
        )

        return (
            count * 52
            + spacing
            + 20
        )

    def _apply_horizontal_fit(self):
        """
        Phase 1F.6.2.1.1 — clean horizontal overflow.

        Non-Rail styles:
            Every destination that remains directly visible keeps its
            COMPLETE icon + canonical label + badge.

            When there is insufficient width, lower-priority destinations
            move completely into ••• More.

            Todo Bird never produces a mixed strip where a few destinations
            have names and the rest become unexplained icons.

        Rail:
            Explicit customer choice for icon-only navigation.
        """
        if getattr(self, "_cleaned_up", False):
            return

        if self.navigation_position not in (
            "top",
            "bottom",
        ):
            return

        available = max(
            0,
            self.horizontal_scroll.viewport().width(),
        )

        visible_keys = self.visible_navigation_keys()

        for key, item in self.horizontal_items.items():
            item.setVisible(
                key in visible_keys
            )

        if not visible_keys:
            self._horizontal_overflow_keys = []
            self._rebuild_more_menu()
            return

        spacing = max(
            0,
            self.horizontal_layout.spacing(),
        )

        # -------------------------------------------------
        # Explicit Rail style remains icon-only by design.
        # -------------------------------------------------
        if self.navigation_style == "rail":
            usable = max(
                120,
                available - 64,
            )

            priority = self._navigation_priority_keys()
            chosen = []
            used = 0

            for key in priority:
                width = 54

                if (
                    not chosen
                    or used + width <= usable
                ):
                    chosen.append(key)
                    used += width + spacing

            if (
                self._selected_key in visible_keys
                and self._selected_key not in chosen
            ):
                if chosen:
                    chosen[-1] = self._selected_key
                else:
                    chosen.append(self._selected_key)

            chosen_set = set(chosen)

            self._horizontal_overflow_keys = [
                key
                for key in visible_keys
                if key not in chosen_set
            ]

            for key in visible_keys:
                item = self.horizontal_items[key]

                if key in chosen_set:
                    item.show()
                    item.set_horizontal_fit_mode(True)
                else:
                    item.hide()

            required = (
                20
                + len(chosen) * (54 + spacing)
            )

            self.horizontal_content.setMinimumWidth(
                max(
                    100,
                    required,
                )
            )

            self._rebuild_more_menu()
            self.horizontal_content.updateGeometry()
            self.horizontal_scroll.updateGeometry()
            return

        # -------------------------------------------------
        # All other styles use full semantic destinations.
        # -------------------------------------------------
        priority = self._navigation_priority_keys()

        # Reserve room for ••• More when overflow is needed.
        more_reserve = 64
        usable = max(
            160,
            available - more_reserve,
        )

        chosen = []
        used = 0

        for key in priority:
            item = self.horizontal_items[key]

            # Force full presentation before measuring.
            item.set_horizontal_fit_mode(False)

            width = item.horizontal_full_width()

            additional = width

            if chosen:
                additional += spacing

            if (
                not chosen
                or used + additional <= usable
            ):
                chosen.append(key)
                used += additional

        # The active destination must always remain directly reachable.
        if (
            self._selected_key in visible_keys
            and self._selected_key not in chosen
        ):
            selected_width = self.horizontal_items[
                self._selected_key
            ].horizontal_full_width()

            # Remove lowest-priority items until active item fits.
            while (
                chosen
                and used
                + selected_width
                + spacing
                > usable
            ):
                removed = chosen.pop()

                removed_width = self.horizontal_items[
                    removed
                ].horizontal_full_width()

                used -= removed_width

                if chosen:
                    used -= spacing

            chosen.append(
                self._selected_key
            )

        # Deduplicate while preserving priority order.
        deduped = []

        for key in chosen:
            if key not in deduped:
                deduped.append(key)

        chosen = deduped
        chosen_set = set(chosen)

        self._horizontal_overflow_keys = [
            key
            for key in visible_keys
            if key not in chosen_set
        ]

        for key in visible_keys:
            item = self.horizontal_items[key]

            if key in chosen_set:
                item.show()

                # Critical visual contract:
                # direct visibility means complete label + badge.
                item.set_horizontal_fit_mode(False)
            else:
                item.hide()

        required = 20

        for index, key in enumerate(chosen):
            required += self.horizontal_items[
                key
            ].horizontal_full_width()

            if index:
                required += spacing

        self.horizontal_content.setMinimumWidth(
            max(
                100,
                required,
            )
        )

        self._rebuild_more_menu()
        self.horizontal_content.updateGeometry()
        self.horizontal_scroll.updateGeometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if self.navigation_position in (
            "top",
            "bottom",
        ):
            QTimer.singleShot(
                0,
                self._apply_horizontal_fit,
            )

    def _iter_items(self):
        for item_set in self._all_item_widgets.values():
            for item in item_set.values():
                yield item

    def _apply_typography(self):
        from todo_bird_app.services.typography_service import (
            TypographyService,
        )

        font = TypographyService.get_font_for_area(
            "sidebar",
            self.settings_manager,
        )

        self.setFont(font)

        TypographyService.apply_to_widget(
            self,
            "sidebar",
            self.settings_manager,
        )

        for item in self._iter_items():
            item.setFont(font)

            item.text_label.setFont(font)

            icon_font = type(font)(font)
            icon_font.setPointSize(
                max(
                    10,
                    font.pointSize() + 4,
                )
            )
            item.icon_label.setFont(icon_font)

            badge_font = type(font)(font)
            badge_font.setPointSize(
                max(
                    7,
                    font.pointSize() - 2,
                )
            )
            item.badge_label.setFont(
                badge_font
            )

        if hasattr(self, "_logo_label"):
            logo_font = type(font)(font)
            logo_font.setPointSize(
                max(
                    14,
                    font.pointSize() + 10,
                )
            )
            self._logo_label.setFont(
                logo_font
            )
            self._horizontal_logo.setFont(
                logo_font
            )

        if hasattr(self, "_app_title"):
            title_font = type(font)(font)
            title_font.setPointSize(
                max(
                    12,
                    font.pointSize() + 6,
                )
            )
            title_font.setWeight(
                font.Weight.ExtraBold
            )
            self._app_title.setFont(
                title_font
            )
            self._horizontal_title.setFont(
                title_font
            )

    def apply_navigation_preferences(
        self,
        position=None,
        style=None,
        alignment=None,
        *,
        persist=True,
        emit_change=True,
    ):
        position = str(
            position
            or self.navigation_position
            or "left"
        ).lower().strip()

        style = str(
            style
            or self.navigation_style
            or "expanded"
        ).lower().strip()

        alignment = str(
            alignment
            or self.navigation_alignment
            or "left"
        ).lower().strip()

        if position not in self.VALID_POSITIONS:
            position = "left"

        if style not in self.VALID_STYLES:
            style = "expanded"

        if alignment not in self.VALID_ALIGNMENTS:
            alignment = "left"

        self.navigation_position = position
        self.navigation_style = style
        self.navigation_alignment = alignment

        horizontal = position in (
            "top",
            "bottom",
        )

        self.setProperty(
            "navPosition",
            position,
        )
        self.setProperty(
            "navStyle",
            style,
        )
        self.setProperty(
            "navOrientation",
            "horizontal"
            if horizontal
            else "vertical",
        )

        self.pages.setCurrentWidget(
            self.horizontal_page
            if horizontal
            else self.vertical_page
        )

        # item_widgets remains the active orientation map for
        # compatibility with existing code.
        self.item_widgets = (
            self.horizontal_items
            if horizontal
            else self.vertical_items
        )

        for item in self._iter_items():
            item.apply_navigation_style(
                style,
                horizontal=horizontal,
            )

        compact_brand = style in (
            "rail",
            "minimal",
        )

        self._app_title.setVisible(
            not compact_brand
        )
        self._horizontal_title.setVisible(
            style not in (
                "rail",
                "minimal",
                "slim",
            )
        )

        if horizontal:
            height = self.STYLE_HEIGHTS.get(
                style,
                62,
            )

            self.setMinimumWidth(420)
            self.setMaximumWidth(1400)
            self.setMinimumHeight(height)
            self.setMaximumHeight(height)

            self.setSizePolicy(
                QSizePolicy.Expanding,
                QSizePolicy.Fixed,
            )

        else:
            width = self.STYLE_WIDTHS.get(
                style,
                240,
            )

            self.setMinimumWidth(width)
            self.setMaximumWidth(width)
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)

            self.setSizePolicy(
                QSizePolicy.Fixed,
                QSizePolicy.Expanding,
            )

        self.select_item(
            self._selected_key,
            emit=False,
        )

        if horizontal:
            QTimer.singleShot(
                0,
                self._apply_horizontal_fit,
            )

        if persist and self.settings_manager is not None:
            self.settings_manager.set(
                "navigation_position",
                position,
            )
            self.settings_manager.set(
                "navigation_style",
                style,
            )
            self.settings_manager.set(
                "navigation_alignment",
                alignment,
            )

        self.style().unpolish(self)
        self.style().polish(self)
        self.updateGeometry()
        self.update()

        if emit_change:
            self.navigation_preferences_changed.emit(
                position,
                style,
                alignment,
            )

    def cycle_navigation_style(self):
        current = self.navigation_style

        try:
            idx = self.VALID_STYLES.index(
                current
            )
        except ValueError:
            idx = 0

        next_style = self.VALID_STYLES[
            (idx + 1)
            % len(self.VALID_STYLES)
        ]

        self.apply_navigation_preferences(
            self.navigation_position,
            next_style,
            self.navigation_alignment,
            persist=True,
            emit_change=True,
        )

    def select_item(
        self,
        key: str,
        *,
        emit=True,
    ):
        if key not in {
            item_key
            for item_key, _, _ in self.NAV_ITEMS
        }:
            return

        self._selected_key = key

        for item_set in self._all_item_widgets.values():
            for item_key, button in item_set.items():
                button.set_selected(
                    item_key == key
                )

        if (
            self.navigation_position in ("top", "bottom")
            and hasattr(self, "horizontal_scroll")
        ):
            QTimer.singleShot(
                0,
                self._apply_horizontal_fit,
            )

        if emit:
            self.section_changed.emit(key)

    def set_badge_count(
        self,
        key: str,
        count: int,
    ):
        for item_set in self._all_item_widgets.values():
            if key in item_set:
                item_set[key].update_count(
                    count
                )

        if self.navigation_position in ("top", "bottom"):
            QTimer.singleShot(
                0,
                self._apply_horizontal_fit,
            )
