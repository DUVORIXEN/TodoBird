"""
TODO BIRD — WORLD CLOCK VIEW
Full-featured World Clock section providing a responsive grid of world clocks,
interactive cross-timezone time converter slider, theme switching across 5 themes,
and global country/city authoring.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone as dt_timezone

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QComboBox,
    QSlider,
    QFrame,
    QGridLayout,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QColor

from todo_bird_app.views.base_view import BaseView
from todo_bird_app.services.appearance_service import AppearanceService
from todo_bird_app.services.world_clock_service import (
    WorldClockItem,
    WorldClockService,
    country_code_to_flag,
)
from todo_bird_app.widgets.world_clock_card import WorldClockCard
from todo_bird_app.widgets.add_world_clock_dialog import AddWorldClockDialog


class WorldClockView(BaseView):
    """
    Dedicated view in MainWindow for multi-timezone executive time planning.
    """

    def __init__(self, db_manager=None, settings_manager=None, parent=None):
        super().__init__(db_manager, settings_manager, parent)
        self.setObjectName("WorldClockView")

        self.clock_type = WorldClockService.get_clock_type(self.settings_manager)
        self.clock_theme = WorldClockService.get_clock_theme(self.settings_manager)
        self.use_24h = WorldClockService.get_use_24h(self.settings_manager)
        self.clocks: List[WorldClockItem] = WorldClockService.load_clocks(self.settings_manager)
        self.cards: List[WorldClockCard] = []

        self._is_dark = True
        self._accent = "#2563EB"

        self._init_ui()

    def _init_ui(self):
        root_layout = self.main_layout
        root_layout.setContentsMargins(24, 20, 24, 20)
        root_layout.setSpacing(16)

        # 1. Top Control Bar
        top_bar = QHBoxLayout()
        top_bar.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        view_title = QLabel("Global World Clock & Timezone Planner", self)
        view_title.setObjectName("view_title")
        view_title.setFont(QFont("Inter", 18, QFont.Bold))
        view_sub = QLabel("Track time across 249 countries with Analog and Digital displays.", self)
        view_sub.setObjectName("view_subtitle")
        view_sub.setStyleSheet("color: #94A3B8; font-size: 13px;")
        title_box.addWidget(view_title)
        title_box.addWidget(view_sub)
        top_bar.addLayout(title_box, 1)

        # Type Toggle (Analog / Digital)
        self.btn_type_analog = QPushButton("Analog", self)
        self.btn_type_analog.setObjectName("btn_nav_toggle")
        self.btn_type_analog.setCheckable(True)
        self.btn_type_analog.setChecked(self.clock_type == "analog")
        self.btn_type_analog.clicked.connect(lambda: self._set_clock_type("analog"))
        top_bar.addWidget(self.btn_type_analog)

        self.btn_type_digital = QPushButton(" Digital", self)
        self.btn_type_digital.setObjectName("btn_nav_toggle")
        self.btn_type_digital.setCheckable(True)
        self.btn_type_digital.setChecked(self.clock_type == "digital")
        self.btn_type_digital.clicked.connect(lambda: self._set_clock_type("digital"))
        top_bar.addWidget(self.btn_type_digital)

        # Theme Dropdown (5 Themes)
        self.theme_combo = QComboBox(self)
        self.theme_combo.setObjectName("theme_dropdown")
        themes = [
            ("minimal", " Modern Minimal"),
            ("luxury", " Classic Luxury"),
            ("cyberpunk", " Cyberpunk HUD"),
            ("retro_lcd", " Retro Matrix LCD"),
            ("solar", " Solar Day-Night"),
        ]
        for t_key, t_label in themes:
            self.theme_combo.addItem(t_label, t_key)
        cur_idx = self.theme_combo.findData(self.clock_theme)
        if cur_idx >= 0:
            self.theme_combo.setCurrentIndex(cur_idx)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        top_bar.addWidget(self.theme_combo)

        # 24H Toggle
        self.btn_24h = QPushButton("24H Mode" if self.use_24h else "12H Mode", self)
        self.btn_24h.setObjectName("btn_nav_toggle")
        self.btn_24h.clicked.connect(self._toggle_24h)
        top_bar.addWidget(self.btn_24h)

        # Add Location Button
        self.btn_add = QPushButton("+ Add Country / City", self)
        self.btn_add.setObjectName("btn_add_main")
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.clicked.connect(self._open_add_dialog)
        top_bar.addWidget(self.btn_add)

        root_layout.addLayout(top_bar)

        # 2. Cross-Timezone Time Scrubber / Meeting Planner Card
        self.converter_frame = QFrame(self)
        self.converter_frame.setObjectName("converter_frame")
        conv_layout = QVBoxLayout(self.converter_frame)
        conv_layout.setContentsMargins(16, 12, 16, 12)
        conv_layout.setSpacing(8)

        conv_header = QHBoxLayout()
        conv_title = QLabel(" Interactive Timezone Scrubber (Meeting Overlap Finder)", self.converter_frame)
        conv_title.setFont(QFont("Inter", 11, QFont.Bold))
        conv_header.addWidget(conv_title)
        conv_header.addStretch()

        self.slider_val_lbl = QLabel("Live Current Time", self.converter_frame)
        self.slider_val_lbl.setStyleSheet("color: #38BDF8; font-weight: bold; font-size: 11px;")
        conv_header.addWidget(self.slider_val_lbl)

        btn_reset_live = QPushButton("Reset to Now", self.converter_frame)
        btn_reset_live.setObjectName("btn_reset_scrubber")
        btn_reset_live.clicked.connect(self._reset_scrubber)
        conv_header.addWidget(btn_reset_live)

        self.btn_find_overlap = QPushButton(" Find Best Overlap", self.converter_frame)
        self.btn_find_overlap.setObjectName("btn_reset_scrubber")
        self.btn_find_overlap.setCursor(Qt.PointingHandCursor)
        self.btn_find_overlap.setToolTip(
            "Scan the whole day and jump to the local hour when the most "
            "added cities are inside working hours (09:00-18:00)."
        )
        self.btn_find_overlap.clicked.connect(self._find_best_overlap)
        conv_header.addWidget(self.btn_find_overlap)
        conv_layout.addLayout(conv_header)

        # Time slider (0 to 1439 minutes of the day)
        self.time_slider = QSlider(Qt.Horizontal, self.converter_frame)
        self.time_slider.setRange(0, 1439)
        now = datetime.now()
        cur_min = now.hour * 60 + now.minute
        self.time_slider.setValue(cur_min)
        self.time_slider.valueChanged.connect(self._on_slider_changed)
        conv_layout.addWidget(self.time_slider)

        root_layout.addWidget(self.converter_frame)

        # 3. Grid of World Clocks
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setObjectName("view_scroll")
        self.scroll_area.setWidgetResizable(True)

        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setContentsMargins(8, 8, 8, 8)
        self.grid_layout.setSpacing(16)
        self.scroll_area.setWidget(self.grid_container)

        root_layout.addWidget(self.scroll_area, 1)

        self._render_grid()
        self._apply_theme()

    def _render_grid(self):
        for card in self.cards:
            card.deleteLater()
        self.cards.clear()

        # Sort pinned first
        sorted_clocks = sorted(self.clocks, key=lambda c: not c.is_pinned)

        cols = 4  # 4 clocks per row
        for idx, item in enumerate(sorted_clocks):
            card = WorldClockCard(
                clock_item=item,
                clock_type=self.clock_type,
                theme=self.clock_theme,
                use_24h=self.use_24h,
                is_dark=self._is_dark,
                accent_color=self._accent,
                parent=self.grid_container,
            )
            card.remove_requested.connect(self._remove_clock)
            card.pin_toggled.connect(self._toggle_pin_clock)
            row = idx // cols
            col = idx % cols
            self.grid_layout.addWidget(card, row, col)
            self.cards.append(card)
        # Re-apply the scrubber state after a rebuild so freshly created
        # cards show the same simulated moment as the rest.
        if getattr(self, "_simulating", False):
            self._on_slider_changed(self.time_slider.value())

    def _set_clock_type(self, clock_type: str):
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
        dlg = AddWorldClockDialog(is_dark=self._is_dark, accent_color=self._accent, parent=self)
        if dlg.exec() == AddWorldClockDialog.Accepted and dlg.created_clock:
            self.clocks.append(dlg.created_clock)
            WorldClockService.save_clocks(self.settings_manager, self.clocks)
            self._render_grid()

    def _remove_clock(self, clock_id: str):
        self.clocks = [c for c in self.clocks if c.id != clock_id]
        WorldClockService.save_clocks(self.settings_manager, self.clocks)
        self._render_grid()

    def _toggle_pin_clock(self, clock_id: str):
        for c in self.clocks:
            if c.id == clock_id:
                c.is_pinned = not c.is_pinned
                break
        WorldClockService.save_clocks(self.settings_manager, self.clocks)
        self._render_grid()

    def _simulated_local_dt(self, val: int) -> datetime:
        """Aware datetime in the viewer's local zone for scrub minute `val`."""
        now = datetime.now().astimezone()
        return now.replace(
            hour=val // 60, minute=val % 60, second=0, microsecond=0
        )

    def _on_slider_changed(self, val: int):
        h = val // 60
        m = val % 60
        self._simulating = True
        sim_dt = self._simulated_local_dt(val)
        full = shoulder = 0
        for card in self.cards:
            info = card.set_simulated_local(sim_dt)
            hour = info["hour"] + info["minute"] / 60.0
            if 9.0 <= hour < 18.0:
                full += 1
            elif 8.0 <= hour < 21.0:
                shoulder += 1
        total = len(self.cards)
        overlap_note = f" • {full}/{total} in work hours" if total else ""
        self.slider_val_lbl.setText(
            f"Simulating Local: {h:02d}:{m:02d}{overlap_note}"
        )

    def _reset_scrubber(self):
        now = datetime.now()
        cur_min = now.hour * 60 + now.minute
        self.time_slider.setValue(cur_min)
        self._simulating = False
        for card in self.cards:
            card.clear_simulated_local()
        self.slider_val_lbl.setText("Live Current Time")

    def _find_best_overlap(self):
        """
        Scans the day in 15-minute steps and jumps to the local time when the
        most added cities sit inside working hours (09:00-18:00), with
        08:00-09:00 / 18:00-21:00 shoulder hours as tie-breakers.
        """
        if not self.cards:
            self.slider_val_lbl.setText("Add cities to find an overlap")
            return
        best_val, best_score = None, (-1, -1)
        for minute in range(0, 1440, 15):
            sim_dt = self._simulated_local_dt(minute)
            full = shoulder = 0
            for card in self.cards:
                info = card.set_simulated_local(sim_dt)
                hour = info["hour"] + info["minute"] / 60.0
                if 9.0 <= hour < 18.0:
                    full += 1
                elif 8.0 <= hour < 21.0:
                    shoulder += 1
            score = (full, shoulder)
            if score > best_score:
                best_score, best_val = score, minute
        self.time_slider.setValue(best_val)
        # setValue is a no-op when the value is unchanged — re-apply explicitly
        # so the cards always reflect the best-overlap moment.
        self._on_slider_changed(best_val)
        h, m = best_val // 60, best_val % 60
        self.slider_val_lbl.setText(
            f"Best Overlap: {h:02d}:{m:02d} • {best_score[0]}/{len(self.cards)} in work hours"
        )

    def set_theme(self, is_dark: bool, accent_color: str):
        self._is_dark = is_dark
        self._accent = accent_color
        self._apply_theme()
        for card in self.cards:
            card.set_theme(self.clock_theme, is_dark=is_dark, accent_color=accent_color)

    def apply_appearance(self, appearance=None):
        if appearance is None:
            appearance = AppearanceService.read(self.settings_manager)
        self.set_theme(appearance.is_dark, appearance.accent_color)

    def _apply_theme(self):
        bg = "#181825" if self._is_dark else "#F8FAFC"
        surface = "#1E1E2E" if self._is_dark else "#FFFFFF"
        border = "#3D3F56" if self._is_dark else "#CBD5E1"
        text = "#F4F7FB" if self._is_dark else "#0F172A"
        accent = self._accent

        self.setStyleSheet(f"""
            QWidget#WorldClockView {{
                background-color: transparent;
                color: {text};
            }}
            QLabel#view_title {{
                color: {text};
            }}
            QPushButton#btn_nav_toggle {{
                background-color: {surface};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 6px 14px;
                color: {text};
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton#btn_nav_toggle:checked {{
                background-color: {accent};
                color: #FFFFFF;
                border-color: {accent};
            }}
            QComboBox#theme_dropdown {{
                background-color: {surface};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 6px 12px;
                color: {text};
                font-size: 12px;
            }}
            QPushButton#btn_add_main {{
                background-color: {accent};
                color: #FFFFFF;
                font-weight: bold;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 12px;
                border: none;
            }}
            QFrame#converter_frame {{
                background-color: {surface};
                border: 1px solid {border};
                border-radius: 10px;
            }}
            QPushButton#btn_reset_scrubber {{
                background-color: transparent;
                border: 1px solid {border};
                border-radius: 4px;
                padding: 3px 8px;
                font-size: 10px;
                color: {text};
            }}
            QScrollArea#view_scroll {{
                background-color: transparent;
                border: none;
            }}
        """)
