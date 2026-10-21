"""
TODO BIRD — WORLD CLOCK CARD
Container card hosting an Analog or Digital clock, city name, country flag,
relative time difference badge, solar phase indicator, and action buttons.
"""

from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from todo_bird_app.services.world_clock_service import (
    WorldClockItem,
    WorldClockService,
    country_code_to_flag,
)
from todo_bird_app.widgets.analog_clock_widget import AnalogClockWidget
from todo_bird_app.widgets.digital_clock_widget import DigitalClockWidget


class WorldClockCard(QFrame):
    """
    Renders one configured world clock card.
    Supports live switching between Analog and Digital clock displays.
    """

    remove_requested = Signal(str)  # clock_id
    pin_toggled = Signal(str)       # clock_id

    def __init__(
        self,
        clock_item: WorldClockItem,
        clock_type: str = "analog",
        theme: str = "minimal",
        use_24h: bool = False,
        is_dark: bool = True,
        accent_color: str = "#2563EB",
        parent=None,
    ):
        super().__init__(parent)
        self.clock_item = clock_item
        self.clock_type = clock_type
        self.theme = theme
        self.use_24h = use_24h
        self.is_dark = is_dark
        self.accent_color = accent_color

        self.setObjectName("WorldClockCard")
        self.setMinimumSize(220, 260)

        self._init_ui()
        self._update_badges()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(8)

        # 1. Header Bar: Flag + City Name + Actions
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        flag = country_code_to_flag(self.clock_item.country_code)
        self.flag_lbl = QLabel(flag, self)
        self.flag_lbl.setStyleSheet("font-size: 18px;")
        header_layout.addWidget(self.flag_lbl)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)

        display_name = self.clock_item.custom_label or self.clock_item.city
        self.city_lbl = QLabel(display_name, self)
        self.city_lbl.setObjectName("card_city_title")
        self.city_lbl.setFont(QFont("Inter", 12, QFont.Bold))
        title_box.addWidget(self.city_lbl)

        self.country_lbl = QLabel(self.clock_item.country_name, self)
        self.country_lbl.setObjectName("card_country_sub")
        self.country_lbl.setFont(QFont("Inter", 9))
        title_box.addWidget(self.country_lbl)

        header_layout.addLayout(title_box, 1)

        # Pin / Delete Action Buttons
        self.btn_pin = QPushButton("★" if self.clock_item.is_pinned else "☆", self)
        self.btn_pin.setObjectName("btn_card_action")
        self.btn_pin.setFixedSize(24, 24)
        self.btn_pin.setToolTip("Pin to Top")
        self.btn_pin.clicked.connect(lambda: self.pin_toggled.emit(self.clock_item.id))
        header_layout.addWidget(self.btn_pin)

        self.btn_delete = QPushButton("✕", self)
        self.btn_delete.setObjectName("btn_card_action")
        self.btn_delete.setFixedSize(24, 24)
        self.btn_delete.setToolTip("Remove Clock")
        self.btn_delete.clicked.connect(lambda: self.remove_requested.emit(self.clock_item.id))
        header_layout.addWidget(self.btn_delete)

        main_layout.addLayout(header_layout)

        # 2. Clock Display (Analog or Digital)
        self.clock_container = QVBoxLayout()
        self.clock_container.setAlignment(Qt.AlignCenter)

        if self.clock_type == "digital":
            self.clock_widget = DigitalClockWidget(
                timezone_name=self.clock_item.timezone,
                theme=self.theme,
                use_24h=self.use_24h,
                is_dark=self.is_dark,
                accent_color=self.accent_color,
                parent=self,
            )
        else:
            self.clock_widget = AnalogClockWidget(
                timezone_name=self.clock_item.timezone,
                theme=self.theme,
                is_dark=self.is_dark,
                accent_color=self.accent_color,
                parent=self,
            )
            self.clock_widget.setFixedSize(140, 140)

        self.clock_widget.time_updated.connect(self._update_badges)
        self.clock_container.addWidget(self.clock_widget)
        main_layout.addLayout(self.clock_container, 1)

        # 3. Badges Row (Relative Offset + Solar Indicator)
        badge_layout = QHBoxLayout()
        badge_layout.setContentsMargins(0, 4, 0, 0)
        badge_layout.setSpacing(6)
        badge_layout.setAlignment(Qt.AlignCenter)

        self.offset_badge = QLabel("Same time", self)
        self.offset_badge.setObjectName("card_offset_badge")
        badge_layout.addWidget(self.offset_badge)

        self.solar_badge = QLabel(" Day", self)
        self.solar_badge.setObjectName("card_solar_badge")
        badge_layout.addWidget(self.solar_badge)

        main_layout.addLayout(badge_layout)

        # 4. Meeting-planner simulation row (visible only while the view's
        # timezone scrubber is active — shows what LOCAL time it would be in
        # this city and whether that lands inside working hours).
        self.sim_lbl = QLabel("", self)
        self.sim_lbl.setObjectName("card_sim_badge")
        self.sim_lbl.setAlignment(Qt.AlignCenter)
        self.sim_lbl.setVisible(False)
        main_layout.addWidget(self.sim_lbl)

        self._apply_theme()

    def set_clock_type(self, clock_type: str):
        if clock_type == self.clock_type:
            return
        self.clock_type = clock_type

        # Re-create the appropriate clock widget
        self.clock_container.removeWidget(self.clock_widget)
        self.clock_widget.deleteLater()

        if self.clock_type == "digital":
            self.clock_widget = DigitalClockWidget(
                timezone_name=self.clock_item.timezone,
                theme=self.theme,
                use_24h=self.use_24h,
                is_dark=self.is_dark,
                accent_color=self.accent_color,
                parent=self,
            )
        else:
            self.clock_widget = AnalogClockWidget(
                timezone_name=self.clock_item.timezone,
                theme=self.theme,
                is_dark=self.is_dark,
                accent_color=self.accent_color,
                parent=self,
            )
            self.clock_widget.setFixedSize(140, 140)

        self.clock_widget.time_updated.connect(self._update_badges)
        self.clock_container.addWidget(self.clock_widget)
        self._update_badges()

    def set_theme(self, theme: str, is_dark: Optional[bool] = None, accent_color: Optional[str] = None):
        self.theme = theme
        if is_dark is not None:
            self.is_dark = is_dark
        if accent_color is not None:
            self.accent_color = accent_color

        self.clock_widget.set_theme(theme, is_dark=self.is_dark, accent_color=self.accent_color)
        self._apply_theme()

    def set_format_24h(self, use_24h: bool):
        self.use_24h = use_24h
        if isinstance(self.clock_widget, DigitalClockWidget):
            self.clock_widget.set_format_24h(use_24h)

    def _update_badges(self):
        info = WorldClockService.get_time_info(self.clock_item.timezone)
        self.offset_badge.setText(f"{info['relative_str']} • {info['day_relative']}")
        phase = info.get("solar_phase", "day")
        if phase == "day":
            self.solar_badge.setText(" Day")
        elif phase in ("dawn", "dusk"):
            self.solar_badge.setText(" Twilight")
        else:
            self.solar_badge.setText(" Night")

    # --------------------------------------------------------------
    # Meeting-planner simulation (driven by the view's scrubber)
    # --------------------------------------------------------------
    def set_simulated_local(self, local_aware_dt):
        """
        Shows what local time `local_aware_dt` (aware datetime in the VIEWER's
        zone) is in this card's city, plus a working-hours verdict.

        Returns the computed time info dict so the view can aggregate overlap
        scores across cards. Pass None via clear_simulated_local() to go live.
        """
        info = WorldClockService.get_time_info(
            self.clock_item.timezone,
            base_time=local_aware_dt,
        )
        hour = info["hour"] + info["minute"] / 60.0
        if 9.0 <= hour < 18.0:
            verdict, marker = "Work hours", ""
        elif 8.0 <= hour < 21.0:
            verdict, marker = "Shoulder", ""
        else:
            verdict, marker = "Off hours", ""
        sim_time = (
            info["time_24h_short"] if self.use_24h else info["time_12h_short"]
        )
        self.sim_lbl.setText(
            f"{marker} {sim_time} there • {info['day_relative']} • {verdict}"
        )
        self.sim_lbl.setVisible(True)
        return info

    def clear_simulated_local(self):
        self.sim_lbl.setVisible(False)
        self.sim_lbl.setText("")

    def _apply_theme(self):
        bg = "#181825" if self.is_dark else "#FFFFFF"
        border = "#313244" if self.is_dark else "#CBD5E1"
        text_primary = "#F4F7FB" if self.is_dark else "#0F172A"
        text_muted = "#A6ADC8" if self.is_dark else "#64748B"
        badge_bg = "#242538" if self.is_dark else "#F1F5F9"
        btn_hover = "#313244" if self.is_dark else "#E2E8F0"

        self.setStyleSheet(f"""
            QFrame#WorldClockCard {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 12px;
            }}
            QLabel#card_city_title {{
                color: {text_primary};
            }}
            QLabel#card_country_sub {{
                color: {text_muted};
            }}
            QPushButton#btn_card_action {{
                background-color: transparent;
                color: {text_muted};
                border: none;
                border-radius: 4px;
                font-size: 13px;
            }}
            QPushButton#btn_card_action:hover {{
                background-color: {btn_hover};
                color: {text_primary};
            }}
            QLabel#card_offset_badge, QLabel#card_solar_badge {{
                background-color: {badge_bg};
                color: {text_muted};
                font-size: 10px;
                font-weight: 600;
                padding: 3px 8px;
                border-radius: 6px;
                border: 1px solid {border};
            }}
            QLabel#card_sim_badge {{
                background-color: {badge_bg};
                color: {text_primary};
                font-size: 11px;
                font-weight: 700;
                padding: 4px 8px;
                border-radius: 6px;
                border: 1px solid {self.accent_color};
            }}
        """)
