"""
TODO BIRD — ANALOG CLOCK WIDGET
High-performance, antialiased vector analog clock supporting 5 distinct visual themes:
1. Modern Minimal
2. Classic Luxury / Executive Chronometer
3. Cyberpunk / Neon HUD
4. Retro Matrix / Phosphor LCD
5. Solar / Day-Night Orbit
"""

import math
from datetime import datetime
from typing import Optional, Dict, Any

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, Signal
from PySide6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QPolygonF,
    QFont,
    QLinearGradient,
    QRadialGradient,
)

from todo_bird_app.services.world_clock_service import WorldClockService


class AnalogClockWidget(QWidget):
    """
    Renders an interactive, theme-aware Analog Clock for any global timezone.
    """

    time_updated = Signal()

    def __init__(
        self,
        timezone_name: str = "UTC",
        theme: str = "minimal",
        is_dark: bool = True,
        accent_color: str = "#E95420",
        parent=None,
        standalone: bool = True,
    ):
        super().__init__(parent)
        self.timezone_name = timezone_name
        self.theme = theme
        self.is_dark = is_dark
        self.accent_color = accent_color

        # Compact header fit: default footprint stays at/below ~120px.
        # Callers needing larger faces (cards) set their own fixed size.
        self.setMinimumSize(80, 80)
        self.resize(120, 120)

        # Internal tick timer (runs every second)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._on_tick)
        
        if standalone:
            self._timer.start()

        # Cache initial time info
        self._info = WorldClockService.get_time_info(self.timezone_name)

    def set_timezone(self, timezone_name: str):
        self.timezone_name = timezone_name
        self._info = WorldClockService.get_time_info(self.timezone_name)
        self.update()

    def set_theme(self, theme: str, is_dark: Optional[bool] = None, accent_color: Optional[str] = None):
        self.theme = theme
        if is_dark is not None:
            self.is_dark = is_dark
        if accent_color is not None:
            self.accent_color = accent_color
        self.update()

    def _on_tick(self):
        self._info = WorldClockService.get_time_info(self.timezone_name)
        self.time_updated.emit()
        self.update()

    def update_time(self, info: Dict[str, Any]):
        """Standard contract for external timer updates."""
        if not info:
            info = WorldClockService.get_time_info(self.timezone_name)
        self._info = info
        self.update()
        
    def paintEvent(self, event):
        side = min(self.width(), self.height())
        if side <= 10:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # Center coordinates
        painter.translate(self.width() / 2.0, self.height() / 2.0)
        radius = (side / 2.0) - 6.0

        # Delegate to theme renderer
        if self.theme == "luxury":
            self._paint_luxury(painter, radius)
        elif self.theme == "cyberpunk":
            self._paint_cyberpunk(painter, radius)
        elif self.theme == "retro_lcd":
            self._paint_retro_lcd(painter, radius)
        elif self.theme == "solar":
            self._paint_solar(painter, radius)
        else:
            self._paint_minimal(painter, radius)

        painter.end()

    # =========================================================================
    # THEME 1: MODERN MINIMAL
    # =========================================================================
    def _minimal_colors(self) -> dict:
        """Visual-only palette roles for the minimal face.

        Face = palette card bg, ticks = palette secondary text, hands =
        palette primary text. ``is_dark`` mirrors the active palette's
        Window lightness (set by callers from the theme setting).
        """
        if self.is_dark:
            return {"bg": "#1E1E2E", "tick": "#9CA3AF", "hand": "#F3F4F6"}
        return {"bg": "#FFFFFF", "tick": "#6B7280", "hand": "#1F2937"}

    def _paint_minimal(self, p: QPainter, r: float):
        # Visual-only minimal face. Dial/hand math and time reads untouched.
        # No heavy rim (1px subtle edge), thinner ticks; second hand uses
        # the semantic accent (default #E95420, user-overridable).
        # Decorative faces below (cyberpunk/matrix) keep fixed hues by design.
        roles = self._minimal_colors()
        bg_color = QColor(roles["bg"])
        border_color = QColor(roles["tick"])
        tick_color = QColor(roles["tick"])
        hand_color = QColor(roles["hand"])
        accent = QColor(self.accent_color)

        # Dial Background & subtle edge (no heavy rim)
        p.setPen(QPen(border_color, 1.0))
        p.setBrush(QBrush(bg_color))
        p.drawEllipse(QPointF(0, 0), r, r)

        # Hour Ticks (12 ticks, thinner)
        for i in range(12):
            angle = i * 30.0
            rad = math.radians(angle)
            is_major = (i % 3 == 0)
            inner_r = r - (8.0 if is_major else 5.0)
            outer_r = r - 2.0
            p.setPen(QPen(tick_color, 1.5 if is_major else 1.0))
            p.drawLine(
                QPointF(inner_r * math.sin(rad), -inner_r * math.cos(rad)),
                QPointF(outer_r * math.sin(rad), -outer_r * math.cos(rad)),
            )

        # Hands
        hour = self._info["hour"] % 12
        minute = self._info["minute"]
        second = self._info["second"]

        self._draw_needle_hand(p, angle_deg=(hour + minute / 60.0) * 30.0, length=r * 0.52, width=4.0, color=hand_color)
        self._draw_needle_hand(p, angle_deg=(minute + second / 60.0) * 6.0, length=r * 0.76, width=2.5, color=hand_color)
        self._draw_second_hand(p, angle_deg=second * 6.0, length=r * 0.85, color=accent)

        # Center pivot cap
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(accent))
        p.drawEllipse(QPointF(0, 0), 4.0, 4.0)

    # =========================================================================
    # THEME 2: CLASSIC LUXURY / CHRONOMETER
    # =========================================================================
    def _paint_luxury(self, p: QPainter, r: float):
        # Visual-only luxury face. Hand/tick math and time reads untouched.
        # Light-mode golds are deepened (#8A6D1C hands, #7A6116 numerals) so
        # they stay readable on the #F8F9FA dial; dark-mode hues unchanged.
        gold = QColor("#D4AF37")
        dial_bg = QColor("#0D1117") if self.is_dark else QColor("#F8F9FA")
        hand_color = QColor("#E5C158") if self.is_dark else QColor("#8A6D1C")
        text_color = QColor("#D4AF37") if self.is_dark else QColor("#7A6116")

        # Double Gold Outer Bezel
        gradient = QRadialGradient(0, 0, r)
        gradient.setColorAt(0.0, dial_bg)
        gradient.setColorAt(0.92, dial_bg)
        gradient.setColorAt(0.96, QColor("#D4AF37"))
        gradient.setColorAt(1.0, QColor("#8A6D1C"))

        p.setPen(QPen(gold, 2.0))
        p.setBrush(QBrush(gradient))
        p.drawEllipse(QPointF(0, 0), r, r)

        # Inner Railroad Track
        p.setPen(QPen(QColor(gold.red(), gold.green(), gold.blue(), 100), 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(0, 0), r * 0.82, r * 0.82)
        p.drawEllipse(QPointF(0, 0), r * 0.76, r * 0.76)

        # Roman Numerals for 12, 3, 6, 9
        font = QFont("Georgia", max(8, int(r * 0.14)), QFont.Bold)
        p.setFont(font)
        p.setPen(text_color)
        numerals = [(0, "XII"), (90, "III"), (180, "VI"), (270, "IX")]
        for deg, text in numerals:
            rad = math.radians(deg)
            dist = r * 0.62
            x = dist * math.sin(rad)
            y = -dist * math.cos(rad)
            p.drawText(QRectF(x - 20, y - 10, 40, 20), Qt.AlignCenter, text)

        # Faceted Dauphine Hands
        hour = self._info["hour"] % 12
        minute = self._info["minute"]
        second = self._info["second"]

        self._draw_dauphine_hand(p, angle_deg=(hour + minute / 60.0) * 30.0, length=r * 0.55, width=6.0, color=hand_color)
        self._draw_dauphine_hand(p, angle_deg=(minute + second / 60.0) * 6.0, length=r * 0.78, width=4.5, color=hand_color)
        self._draw_second_hand(p, angle_deg=second * 6.0, length=r * 0.88, color=gold)

        # Center Pivot
        p.setPen(QPen(gold, 1.0))
        p.setBrush(QBrush(dial_bg))
        p.drawEllipse(QPointF(0, 0), 4.5, 4.5)

    # =========================================================================
    # THEME 3: CYBERPUNK / NEON HUD
    # =========================================================================
    def _paint_cyberpunk(self, p: QPainter, r: float):
        cyan = QColor("#00F0FF")
        magenta = QColor("#FF007F")
        yellow = QColor("#FFE600")
        dark_hud = QColor("#0A0A14")

        # Obsidian Dark Face
        p.setPen(QPen(cyan, 2.0))
        p.setBrush(QBrush(dark_hud))
        p.drawEllipse(QPointF(0, 0), r, r)

        # Concentric Tech Grid Rings
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 240, 255, 60), 1.0, Qt.DashLine))
        p.drawEllipse(QPointF(0, 0), r * 0.70, r * 0.70)
        p.setPen(QPen(QColor(255, 0, 127, 60), 1.0, Qt.DotLine))
        p.drawEllipse(QPointF(0, 0), r * 0.40, r * 0.40)

        # Angular Sci-Fi Ticks
        for i in range(12):
            angle = i * 30.0
            rad = math.radians(angle)
            is_cardinal = (i % 3 == 0)
            inner_r = r - (10.0 if is_cardinal else 6.0)
            p.setPen(QPen(magenta if is_cardinal else cyan, 2.0 if is_cardinal else 1.0))
            p.drawLine(
                QPointF(inner_r * math.sin(rad), -inner_r * math.cos(rad)),
                QPointF((r - 2) * math.sin(rad), -(r - 2) * math.cos(rad)),
            )

        # Neon Hands
        hour = self._info["hour"] % 12
        minute = self._info["minute"]
        second = self._info["second"]

        self._draw_needle_hand(p, (hour + minute / 60.0) * 30.0, length=r * 0.50, width=5.0, color=magenta)
        self._draw_needle_hand(p, (minute + second / 60.0) * 6.0, length=r * 0.75, width=3.0, color=cyan)
        self._draw_second_hand(p, second * 6.0, length=r * 0.88, color=yellow)

        # Crosshair Center
        p.setPen(QPen(yellow, 1.5))
        p.setBrush(QBrush(dark_hud))
        p.drawEllipse(QPointF(0, 0), 5.0, 5.0)

    # =========================================================================
    # THEME 4: RETRO MATRIX / PHOSPHOR LCD
    # =========================================================================
    def _paint_retro_lcd(self, p: QPainter, r: float):
        phosphor = QColor("#4ADE80")  # Vintage green phosphor
        lcd_bg = QColor("#0F1A12")    # Deep dark green matrix
        bezel = QColor("#223322")

        # Outer Vintage CRT Bezel
        p.setPen(QPen(bezel, 3.0))
        p.setBrush(QBrush(lcd_bg))
        p.drawEllipse(QPointF(0, 0), r, r)

        # Pixelated Dot Ring
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(phosphor.red(), phosphor.green(), phosphor.blue(), 120)))
        for i in range(60):
            rad = math.radians(i * 6.0)
            dot_r = 1.0 if i % 5 != 0 else 2.0
            dist = r - 6.0
            p.drawEllipse(QPointF(dist * math.sin(rad), -dist * math.cos(rad)), dot_r, dot_r)

        # 12 Blocky Indices
        p.setBrush(QBrush(phosphor))
        for i in range(12):
            rad = math.radians(i * 30.0)
            dist = r - 12.0
            p.drawRect(QRectF(dist * math.sin(rad) - 2.0, -dist * math.cos(rad) - 2.0, 4.0, 4.0))

        # Blocky Hands
        hour = self._info["hour"] % 12
        minute = self._info["minute"]
        second = self._info["second"]

        self._draw_blocky_hand(p, (hour + minute / 60.0) * 30.0, length=r * 0.48, width=5.0, color=phosphor)
        self._draw_blocky_hand(p, (minute + second / 60.0) * 6.0, length=r * 0.72, width=3.5, color=phosphor)
        self._draw_second_hand(p, second * 6.0, length=r * 0.85, color=QColor("#86EFAC"))

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(phosphor))
        p.drawRect(QRectF(-3.0, -3.0, 6.0, 6.0))

    # =========================================================================
    # THEME 5: SOLAR / DAY-NIGHT ORBIT
    # =========================================================================
    def _paint_solar(self, p: QPainter, r: float):
        phase = self._info.get("solar_phase", "day")
        grad = QRadialGradient(0, 0, r)

        if phase == "day":
            grad.setColorAt(0.0, QColor("#FDE68A"))  # Sunny core
            grad.setColorAt(0.6, QColor("#60A5FA"))  # Sky blue
            grad.setColorAt(1.0, QColor("#1D4ED8"))  # Deep blue rim
            hand_color = QColor("#FFFFFF")
            sec_color = QColor("#F59E0B")
            icon = ""
        elif phase in ("dawn", "dusk"):
            grad.setColorAt(0.0, QColor("#F43F5E"))  # Crimson twilight
            grad.setColorAt(0.5, QColor("#8B5CF6"))  # Purple haze
            grad.setColorAt(1.0, QColor("#1E1B4B"))  # Night horizon
            hand_color = QColor("#FFFFFF")
            sec_color = QColor("#FB923C")
            icon = ""
        else:  # Night
            grad.setColorAt(0.0, QColor("#1E1B4B"))  # Midnight core
            grad.setColorAt(0.7, QColor("#0F172A"))  # Slate night
            grad.setColorAt(1.0, QColor("#020617"))  # Obsidian edge
            hand_color = QColor("#E2E8F0")
            sec_color = QColor("#38BDF8")
            icon = ""

        # Celestial Face
        p.setPen(QPen(QColor(255, 255, 255, 60), 1.5))
        p.setBrush(QBrush(grad))
        p.drawEllipse(QPointF(0, 0), r, r)

        # Starry points for night
        if phase == "night":
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(255, 255, 255, 180)))
            for star_x, star_y in [(-r * 0.4, -r * 0.3), (r * 0.5, -r * 0.2), (-r * 0.3, r * 0.5), (r * 0.3, r * 0.4)]:
                p.drawEllipse(QPointF(star_x, star_y), 1.2, 1.2)

        # Sun / Moon Glyph at Top
        font = QFont("Sans", max(8, int(r * 0.16)))
        p.setFont(font)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(-15, -r * 0.65, 30, 20), Qt.AlignCenter, icon)

        # Radial Ticks
        for i in range(12):
            rad = math.radians(i * 30.0)
            inner_r = r - (7.0 if i % 3 == 0 else 4.0)
            p.setPen(QPen(QColor(255, 255, 255, 180 if i % 3 == 0 else 90), 1.5))
            p.drawLine(
                QPointF(inner_r * math.sin(rad), -inner_r * math.cos(rad)),
                QPointF((r - 2) * math.sin(rad), -(r - 2) * math.cos(rad)),
            )

        # Hands
        hour = self._info["hour"] % 12
        minute = self._info["minute"]
        second = self._info["second"]

        self._draw_needle_hand(p, (hour + minute / 60.0) * 30.0, length=r * 0.52, width=4.5, color=hand_color)
        self._draw_needle_hand(p, (minute + second / 60.0) * 6.0, length=r * 0.76, width=2.8, color=hand_color)
        self._draw_second_hand(p, second * 6.0, length=r * 0.86, color=sec_color)

        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(sec_color))
        p.drawEllipse(QPointF(0, 0), 4.0, 4.0)

    # =========================================================================
    # HAND DRAWING PRIMITIVES
    # =========================================================================
    def _draw_needle_hand(self, p: QPainter, angle_deg: float, length: float, width: float, color: QColor):
        p.save()
        p.rotate(angle_deg)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color))
        half_w = width / 2.0
        poly = QPolygonF([
            QPointF(-half_w, 4.0),
            QPointF(half_w, 4.0),
            QPointF(half_w * 0.4, -length),
            QPointF(-half_w * 0.4, -length),
        ])
        p.drawPolygon(poly)
        p.restore()

    def _draw_dauphine_hand(self, p: QPainter, angle_deg: float, length: float, width: float, color: QColor):
        p.save()
        p.rotate(angle_deg)
        p.setPen(Qt.NoPen)

        # Left facet (highlight)
        p.setBrush(QBrush(color.lighter(120)))
        poly_l = QPolygonF([
            QPointF(0, 0),
            QPointF(-width / 2.0, -length * 0.35),
            QPointF(0, -length),
        ])
        p.drawPolygon(poly_l)

        # Right facet (shadow)
        p.setBrush(QBrush(color.darker(120)))
        poly_r = QPolygonF([
            QPointF(0, 0),
            QPointF(width / 2.0, -length * 0.35),
            QPointF(0, -length),
        ])
        p.drawPolygon(poly_r)
        p.restore()

    def _draw_blocky_hand(self, p: QPainter, angle_deg: float, length: float, width: float, color: QColor):
        p.save()
        p.rotate(angle_deg)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color))
        p.drawRect(QRectF(-width / 2.0, -length, width, length))
        p.restore()

    def _draw_second_hand(self, p: QPainter, angle_deg: float, length: float, color: QColor):
        p.save()
        p.rotate(angle_deg)
        p.setPen(QPen(color, 1.5))
        p.drawLine(QPointF(0, 10.0), QPointF(0, -length))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(color))
        p.drawEllipse(QPointF(0, 10.0), 3.0, 3.0)
        p.restore()
