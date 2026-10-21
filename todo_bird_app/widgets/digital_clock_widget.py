"""
TODO BIRD — DIGITAL CLOCK WIDGET
Theme-aware digital clock display supporting 12h/24h formats,
seconds, relative offsets, and 5 curated visual themes:
1. Modern Minimal
2. Classic Luxury / Chronometer
3. Cyberpunk / Neon HUD
4. Retro Matrix / Phosphor LCD
5. Solar / Day-Night Orbit
"""

from typing import Optional, Dict, Any

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QColor

from todo_bird_app.services.world_clock_service import WorldClockService


class DigitalClockWidget(QWidget):
    """
    Renders an interactive, theme-styled Digital Clock for any global timezone.
    """

    time_updated = Signal()

    def __init__(
        self,
        timezone_name: str = "UTC",
        theme: str = "minimal",
        use_24h: bool = False,
        is_dark: bool = True,
        accent_color: str = "#E95420",
        parent=None,
        standalone: bool = True,
        display_size: str = "large",
    ):
        super().__init__(parent)
        self.timezone_name = timezone_name
        self.theme = theme
        self.use_24h = use_24h
        self.is_dark = is_dark
        self.accent_color = accent_color
        # Visual-only size variant: "compact" (header strip) or "large"
        # (cards/dialogs). Timer, signals and tz logic untouched.
        self.display_size = display_size if display_size == "compact" else "large"

        self._init_ui()

        # Update timer
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)
        
        if standalone:
            self._timer.start()

        self._refresh_display()

    def _init_ui(self):
        # Visual rhythm follows the spacing scale (4/8/12/16): outer 12/8,
        # frame padding 12/8, row gaps 8/4. Time/tz logic untouched.
        is_compact = getattr(self, "display_size", "large") == "compact"
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4 if is_compact else 12, 2 if is_compact else 8, 4 if is_compact else 12, 2 if is_compact else 8)
        layout.setSpacing(2 if is_compact else 4)
        layout.setAlignment(Qt.AlignCenter)

        # Container Frame
        self.frame = QFrame(self)
        self.frame.setObjectName("digital_clock_frame")
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(4 if is_compact else 12, 2 if is_compact else 8, 4 if is_compact else 12, 2 if is_compact else 8)
        frame_layout.setSpacing(2 if is_compact else 4)
        frame_layout.setAlignment(Qt.AlignCenter)

        # Time Row (Hour:Minute:Second + AM/PM)
        time_row = QHBoxLayout()
        time_row.setAlignment(Qt.AlignCenter)
        time_row.setSpacing(4 if is_compact else 8)

        self.time_lbl = QLabel("00:00:00", self.frame)
        self.time_lbl.setObjectName("digital_time_label")
        self.time_lbl.setAlignment(Qt.AlignCenter)

        self.ampm_lbl = QLabel("AM", self.frame)
        self.ampm_lbl.setObjectName("digital_ampm_label")
        self.ampm_lbl.setAlignment(Qt.AlignBottom)

        time_row.addWidget(self.time_lbl)
        time_row.addWidget(self.ampm_lbl)
        frame_layout.addLayout(time_row)

        # Details Row (Date & TZ Abbr)
        details_row = QHBoxLayout()
        details_row.setAlignment(Qt.AlignCenter)
        details_row.setSpacing(8)

        self.date_lbl = QLabel("Wed, Sep 02", self.frame)
        self.date_lbl.setObjectName("digital_date_label")

        self.tz_lbl = QLabel("UTC+00:00", self.frame)
        self.tz_lbl.setObjectName("digital_tz_label")

        details_row.addWidget(self.date_lbl)
        details_row.addWidget(self.tz_lbl)
        frame_layout.addLayout(details_row)

        if is_compact:
            self.date_lbl.setVisible(False)
            self.tz_lbl.setVisible(False)

        layout.addWidget(self.frame)
        self._apply_theme()

    def set_timezone(self, timezone_name: str):
        self.timezone_name = timezone_name
        self._refresh_display()

    def set_format_24h(self, use_24h: bool):
        self.use_24h = use_24h
        self._refresh_display()

    def set_theme(self, theme: str, is_dark: Optional[bool] = None, accent_color: Optional[str] = None):
        self.theme = theme
        if is_dark is not None:
            self.is_dark = is_dark
        if accent_color is not None:
            self.accent_color = accent_color
        self._apply_theme()
        self._refresh_display()

    def set_display_size(self, display_size: str):
        """Visual-only size variant: 'compact' (15px time) or 'large' (24px)."""
        self.display_size = display_size if display_size == "compact" else "large"
        is_compact = self.display_size == "compact"
        if hasattr(self, "date_lbl") and hasattr(self, "tz_lbl"):
            self.date_lbl.setVisible(not is_compact)
            self.tz_lbl.setVisible(not is_compact)
        if hasattr(self, "layout") and self.layout():
            self.layout().setContentsMargins(4 if is_compact else 12, 2 if is_compact else 8, 4 if is_compact else 12, 2 if is_compact else 8)
            self.layout().setSpacing(2 if is_compact else 4)
        if hasattr(self, "frame") and self.frame and self.frame.layout():
            self.frame.layout().setContentsMargins(4 if is_compact else 12, 2 if is_compact else 8, 4 if is_compact else 12, 2 if is_compact else 8)
            self.frame.layout().setSpacing(2 if is_compact else 4)
        self._apply_theme()

    def _on_tick(self):
        self._refresh_display()
        self.time_updated.emit()

    def _refresh_display(self):
        info = WorldClockService.get_time_info(self.timezone_name)
        self.update_time(info)
        
    def update_time(self, info: Dict[str, Any]):
        """Standard contract for external timer updates."""
        if not info:
            info = WorldClockService.get_time_info(self.timezone_name)
            
        if self.use_24h:
            self.time_lbl.setText(info["time_24h"])
            self.ampm_lbl.setVisible(False)
        else:
            # Split time and AM/PM
            t_str = info["time_12h"]
            parts = t_str.split(" ")
            self.time_lbl.setText(parts[0])
            self.ampm_lbl.setText(parts[1] if len(parts) > 1 else "")
            self.ampm_lbl.setVisible(True)

        self.date_lbl.setText(info["date_display"])
        self.tz_lbl.setText(f"{info['tz_abbr']} • {info['utc_offset']}")

    def _apply_theme(self):
        # Visual-only theme table. Time/tz computation, signatures and the
        # time_updated signal are untouched. Decorative faces (luxury gold,
        # cyberpunk neon, retro phosphor) keep fixed hues by design in both
        # modes; minimal/solar follow light/dark semantic contrast. Light
        # luxury golds are deepened (#7A6116/#85711B) so time stays readable
        # on the #FDFBF7 dial.
        # Size variants (M5 S5.2.1): compact time 15px semibold (header
        # strip), large time 22-26px bold (cards/dialogs); supports stay
        # 10-11px muted; frame radius 8 (CARD_RADIUS sm), padding 12/8;
        # minimal is borderless transparent text-only; time uses
        # tabular-nums so seconds ticks never jitter the layout.
        compact = getattr(self, "display_size", "large") == "compact"
        time_weight = "600" if compact else "700"
        ampm_size = "10px" if compact else "11px"
        support_size = "10px"

        def _sized(base: str) -> str:
            return "15px" if compact else base

        if self.theme == "luxury":
            bg = "#0F172A" if self.is_dark else "#FDFBF7"
            border = "#D4AF37"
            time_color = "#E5C158" if self.is_dark else "#7A6116"
            sub_color = "#B38B22" if self.is_dark else "#85711B"
            font_family = "Georgia, serif"
            font_size = _sized("24px")
            frame_box = (
                f"background-color: {bg};\n"
                f"                border: 1px solid {border};"
            )
        elif self.theme == "cyberpunk":
            bg = "#0A0A14"
            border = "#00F0FF"
            time_color = "#00F0FF"
            sub_color = "#FF007F"
            font_family = "'Courier New', monospace"
            font_size = _sized("25px")
            frame_box = (
                f"background-color: {bg};\n"
                f"                border: 1px solid {border};"
            )
        elif self.theme == "retro_lcd":
            bg = "#0F1A12"
            border = "#2A4530"
            time_color = "#4ADE80"
            sub_color = "#22C55E"
            font_family = "'Consolas', monospace"
            font_size = _sized("24px")
            frame_box = (
                f"background-color: {bg};\n"
                f"                border: 1px solid {border};"
            )
        elif self.theme == "solar":
            bg = "#1E1B4B" if self.is_dark else "#F0F9FF"
            border = "#60A5FA" if self.is_dark else "#38BDF8"
            time_color = "#FDE68A" if self.is_dark else "#0369A1"
            sub_color = "#93C5FD" if self.is_dark else "#0284C7"
            font_family = "Inter, sans-serif"
            font_size = _sized("24px")
            frame_box = (
                f"background-color: {bg};\n"
                f"                border: 1px solid {border};"
            )
        else:  # minimal
            # Semantic tokens for proper light/dark readability; the frame
            # itself stays transparent and borderless (text-only minimal).
            if self.is_dark:
                time_color = "#F4F7FB"
                sub_color = "#94A3B8"
            else:
                time_color = "#0F172A"
                sub_color = "#64748B"
            font_family = "Inter, sans-serif"
            font_size = _sized("24px")
            frame_box = "background: transparent;\n                border: none;"

        self.frame.setStyleSheet(f"""
            QFrame#digital_clock_frame {{
                {frame_box}
                border-radius: 8px;
            }}
            QLabel#digital_time_label {{
                /* tabular-nums: digit advances stay fixed so seconds ticks never jitter the layout */
                font-family: {font_family};
                font-size: {font_size};
                font-weight: {time_weight};
                letter-spacing: 0px;
                color: {time_color};
            }}
            QLabel#digital_ampm_label {{
                font-family: {font_family};
                font-size: {ampm_size};
                font-weight: 600;
                color: {sub_color};
                padding-bottom: 4px;
            }}
            QLabel#digital_date_label, QLabel#digital_tz_label {{
                font-family: {font_family};
                font-size: {support_size};
                color: {sub_color};
            }}
        """)
