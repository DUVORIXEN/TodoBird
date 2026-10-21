"""
TODO BIRD — WORLD CLOCK POPOVER
Floating quick-access dialog showing live world clocks with instant type switching,
theme selection across 5 themes, and add/remove capabilities.
"""

from typing import Optional, Dict, Any, List

from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QComboBox,
    QFrame,
    QApplication,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QFont, QColor

from todo_bird_app.services.appearance_service import AppearanceService
from todo_bird_app.services.world_clock_service import (
    WorldClockItem,
    WorldClockService,
)
from todo_bird_app.widgets.world_clock_card import WorldClockCard
from todo_bird_app.widgets.add_world_clock_dialog import AddWorldClockDialog


class WorldClockPopover(QDialog):
    """
    Persistent floating popup providing global multi-city time tracking,
    type selection (Analog/Digital), and 5 themes.
    """

    clocks_changed = Signal()

    def __init__(
        self,
        settings_manager=None,
        parent=None,
        is_dark: Optional[bool] = None,
        accent_color: Optional[str] = None,
    ):
        super().__init__(parent)
        self.settings_manager = settings_manager

        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setObjectName("WorldClockPopover")
        self.resize(720, 480)

        # Theme resolution
        app = QApplication.instance()
        appearance = AppearanceService.read(None, app=app)
        self._is_dark = is_dark if is_dark is not None else appearance.is_dark
        self._accent = accent_color or appearance.accent_color

        # Clock settings
        self.clock_type = WorldClockService.get_clock_type(self.settings_manager)
        self.clock_theme = WorldClockService.get_clock_theme(self.settings_manager)
        self.use_24h = WorldClockService.get_use_24h(self.settings_manager)
        self.clocks: List[WorldClockItem] = WorldClockService.load_clocks(self.settings_manager)

        self.cards: List[WorldClockCard] = []
        self._init_ui()
        self._apply_theme()

    def _init_ui(self):
        root_vbox = QVBoxLayout(self)
        root_vbox.setContentsMargins(16, 14, 16, 14)
        root_vbox.setSpacing(12)

        # 1. Header Row
        header = QHBoxLayout()
        header.setSpacing(8)

        title_lbl = QLabel("Global World Clock", self)
        title_lbl.setObjectName("popover_header_title")
        title_lbl.setFont(QFont("Inter", 13, QFont.Bold))
        header.addWidget(title_lbl)

        header.addStretch()

        # Clock Type Toggle: Analog vs Digital
        self.btn_type_analog = QPushButton("Analog", self)
        self.btn_type_analog.setObjectName("btn_toggle_type")
        self.btn_type_analog.setCheckable(True)
        self.btn_type_analog.setChecked(self.clock_type == "analog")
        self.btn_type_analog.clicked.connect(lambda: self._set_type("analog"))
        header.addWidget(self.btn_type_analog)

        self.btn_type_digital = QPushButton(" Digital", self)
        self.btn_type_digital.setObjectName("btn_toggle_type")
        self.btn_type_digital.setCheckable(True)
        self.btn_type_digital.setChecked(self.clock_type == "digital")
        self.btn_type_digital.clicked.connect(lambda: self._set_type("digital"))
        header.addWidget(self.btn_type_digital)

        # Theme Selector Dropdown (5 Themes)
        self.theme_combo = QComboBox(self)
        self.theme_combo.setObjectName("theme_selector_combo")
        themes = [
            ("minimal", " Minimal"),
            ("luxury", " Luxury"),
            ("cyberpunk", " Cyberpunk"),
            ("retro_lcd", " Retro LCD"),
            ("solar", "Solar Orbit"),
        ]
        for t_key, t_label in themes:
            self.theme_combo.addItem(t_label, t_key)
        cur_idx = self.theme_combo.findData(self.clock_theme)
        if cur_idx >= 0:
            self.theme_combo.setCurrentIndex(cur_idx)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        header.addWidget(self.theme_combo)

        # Close X Button
        self.btn_close = QPushButton("✕", self)
        self.btn_close.setObjectName("btn_popover_close")
        self.btn_close.setFixedSize(26, 26)
        self.btn_close.clicked.connect(self.close)
        header.addWidget(self.btn_close)

        root_vbox.addLayout(header)

        # 2. Scrollable Clocks Container
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("popover_scroll")
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setFixedHeight(320)

        self.scroll_content = QWidget()
        self.cards_layout = QHBoxLayout(self.scroll_content)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(12)
        self.scroll_area.setWidget(self.scroll_content)

        root_vbox.addWidget(self.scroll_area, 1)

        # 3. Footer Bar
        footer = QHBoxLayout()
        footer.setSpacing(10)

        self.btn_add = QPushButton("+ Add Country / City", self)
        self.btn_add.setObjectName("btn_add_location")
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.clicked.connect(self._open_add_dialog)
        footer.addWidget(self.btn_add)

        # 12h / 24h toggle button
        self.btn_24h = QPushButton("24H Mode" if self.use_24h else "12H Mode", self)
        self.btn_24h.setObjectName("btn_toggle_24h")
        self.btn_24h.clicked.connect(self._toggle_24h)
        footer.addWidget(self.btn_24h)

        footer.addStretch()

        hint_lbl = QLabel("Esc to close • Select any country or city", self)
        hint_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
        footer.addWidget(hint_lbl)

        root_vbox.addLayout(footer)

        self._render_cards()

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 120 if self._is_dark else 50))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)

    def _render_cards(self):
        # Clear existing cards
        for card in self.cards:
            card.deleteLater()
        self.cards.clear()

        # Sort pinned first
        sorted_clocks = sorted(self.clocks, key=lambda c: not c.is_pinned)

        for item in sorted_clocks:
            card = WorldClockCard(
                clock_item=item,
                clock_type=self.clock_type,
                theme=self.clock_theme,
                use_24h=self.use_24h,
                is_dark=self._is_dark,
                accent_color=self._accent,
                parent=self.scroll_content,
            )
            card.remove_requested.connect(self._remove_clock)
            card.pin_toggled.connect(self._toggle_pin_clock)
            self.cards_layout.addWidget(card)
            self.cards.append(card)

        self.cards_layout.addStretch()

    def _set_type(self, clock_type: str):
        self.clock_type = clock_type
        self.btn_type_analog.setChecked(clock_type == "analog")
        self.btn_type_digital.setChecked(clock_type == "digital")
        WorldClockService.set_clock_type(self.settings_manager, clock_type)
        for card in self.cards:
            card.set_clock_type(clock_type)

    def _on_theme_changed(self):
        new_theme = self.theme_combo.currentData()
        if new_theme:
            self.clock_theme = new_theme
            WorldClockService.set_clock_theme(self.settings_manager, new_theme)
            for card in self.cards:
                card.set_theme(new_theme, is_dark=self._is_dark, accent_color=self._accent)

    def _toggle_24h(self):
        self.use_24h = not self.use_24h
        self.btn_24h.setText("24H Mode" if self.use_24h else "12H Mode")
        WorldClockService.set_use_24h(self.settings_manager, self.use_24h)
        for card in self.cards:
            card.set_format_24h(self.use_24h)

    def _open_add_dialog(self):
        region_country = ""
        if self.settings_manager is not None:
            try:
                region_country = str(self.settings_manager.get("region_country", "") or "")
            except Exception:
                region_country = ""
        dlg = AddWorldClockDialog(
            is_dark=self._is_dark,
            accent_color=self._accent,
            parent=self,
            region_country=region_country,
        )
        if dlg.exec() == QDialog.Accepted and dlg.created_clock:
            self.clocks.append(dlg.created_clock)
            WorldClockService.save_clocks(self.settings_manager, self.clocks)
            self._render_cards()
            self.clocks_changed.emit()

    def _remove_clock(self, clock_id: str):
        self.clocks = [c for c in self.clocks if c.id != clock_id]
        WorldClockService.save_clocks(self.settings_manager, self.clocks)
        self._render_cards()
        self.clocks_changed.emit()

    def _toggle_pin_clock(self, clock_id: str):
        for c in self.clocks:
            if c.id == clock_id:
                c.is_pinned = not c.is_pinned
                break
        WorldClockService.save_clocks(self.settings_manager, self.clocks)
        self._render_cards()
        self.clocks_changed.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def _apply_theme(self):
        bg = "#181825" if self._is_dark else "#FFFFFF"
        surface = "#242538" if self._is_dark else "#F8FAFC"
        border = "#3D3F56" if self._is_dark else "#CBD5E1"
        text = "#F4F7FB" if self._is_dark else "#0F172A"
        accent = self._accent

        self.setStyleSheet(f"""
            QDialog#WorldClockPopover {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 12px;
                color: {text};
            }}
            QLabel#popover_header_title {{
                color: {text};
            }}
            QPushButton#btn_toggle_type {{
                background-color: {surface};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 4px 10px;
                color: {text};
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#btn_toggle_type:checked {{
                background-color: {accent};
                color: #FFFFFF;
                border-color: {accent};
            }}
            QComboBox#theme_selector_combo {{
                background-color: {surface};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 4px 8px;
                color: {text};
                font-size: 11px;
            }}
            QPushButton#btn_popover_close {{
                background-color: transparent;
                border: 1px solid {border};
                border-radius: 6px;
                color: {text};
            }}
            QPushButton#btn_popover_close:hover {{
                background-color: {border};
            }}
            QScrollArea#popover_scroll {{
                background-color: transparent;
                border: none;
            }}
            QPushButton#btn_add_location {{
                background-color: {accent};
                color: #FFFFFF;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                border: none;
            }}
            QPushButton#btn_toggle_24h {{
                background-color: {surface};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 6px 12px;
                color: {text};
                font-size: 11px;
                font-weight: 600;
            }}
        """)
