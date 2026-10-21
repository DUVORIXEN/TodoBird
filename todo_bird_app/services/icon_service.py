"""
TODO BIRD — CENTRALIZED VECTOR ICON & DRAWING SERVICE
Provides crisp, theme-aware, high-DPI vector icons and shapes across the entire application.
Eliminates emoji mismatches and blurry bitmaps by utilizing vector QPainterPaths and DPI-aware caching.
"""

from typing import Dict, Tuple, Optional
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QPixmap,
    QIcon,
)


class IconService:
    """
    Central authority for vector icon rendering and pixmap caching.
    Supports DPR (Device Pixel Ratio) scaling (1.0, 1.25, 1.5, 2.0).
    """

    _pixmap_cache: Dict[Tuple[str, int, float, str], QPixmap] = {}

    # Names that create_path() can render as a proper vector glyph. Anything
    # outside this set falls back to a plain-text label at call sites.
    KNOWN_ICON_NAMES = frozenset({
        "chevron_down", "expand", "chevron_right", "collapse", "chevron_up",
        "chevron_left", "add", "plus", "close", "cross", "check", "checkmark",
        "dash", "indeterminate", "milestone", "diamond", "search", "edit",
        "trash", "delete", "more", "ellipsis", "filter", "sort", "settings",
        "refresh", "pin", "folder", "summary", "task", "file", "home",
        "inbox", "tray", "star", "target", "calendar", "check_circle",
        "chart", "chat", "globe", "bell", "clock", "sun", "moon",
    })

    @classmethod
    def has_icon(cls, name: str) -> bool:
        return str(name or "") in cls.KNOWN_ICON_NAMES

    @classmethod
    def clear_cache(cls):
        cls._pixmap_cache.clear()

    @classmethod
    def create_path(cls, icon_name: str, rect: QRectF) -> QPainterPath:
        """Constructs a vector QPainterPath normalized into rect."""
        path = QPainterPath()
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        cx = x + w / 2.0
        cy = y + h / 2.0

        if icon_name in ("chevron_down", "expand"):
            # Downward chevron (V-shape)
            path.moveTo(x + w * 0.15, y + h * 0.35)
            path.lineTo(cx, y + h * 0.70)
            path.lineTo(x + w * 0.85, y + h * 0.35)

        elif icon_name in ("chevron_right", "collapse"):
            # Rightward chevron (>-shape)
            path.moveTo(x + w * 0.35, y + h * 0.15)
            path.lineTo(x + w * 0.70, cy)
            path.lineTo(x + w * 0.35, y + h * 0.85)

        elif icon_name == "chevron_up":
            # Upward chevron (^-shape)
            path.moveTo(x + w * 0.15, y + h * 0.65)
            path.lineTo(cx, y + h * 0.30)
            path.lineTo(x + w * 0.85, y + h * 0.65)

        elif icon_name == "chevron_left":
            # Leftward chevron (<-shape)
            path.moveTo(x + w * 0.65, y + h * 0.15)
            path.lineTo(x + w * 0.30, cy)
            path.lineTo(x + w * 0.65, y + h * 0.85)

        elif icon_name == "add" or icon_name == "plus":
            # Plus icon
            path.moveTo(cx, y + h * 0.18)
            path.lineTo(cx, y + h * 0.82)
            path.moveTo(x + w * 0.18, cy)
            path.lineTo(x + w * 0.82, cy)

        elif icon_name == "close" or icon_name == "cross":
            # X / Close icon
            path.moveTo(x + w * 0.25, y + h * 0.25)
            path.lineTo(x + w * 0.75, y + h * 0.75)
            path.moveTo(x + w * 0.75, y + h * 0.25)
            path.lineTo(x + w * 0.25, y + h * 0.75)

        elif icon_name in ("check", "checkmark"):
            # Checkmark
            path.moveTo(x + w * 0.16, y + h * 0.52)
            path.lineTo(x + w * 0.40, y + h * 0.76)
            path.lineTo(x + w * 0.84, y + h * 0.24)

        elif icon_name in ("dash", "indeterminate"):
            # Horizontal dash
            path.moveTo(x + w * 0.20, cy)
            path.lineTo(x + w * 0.80, cy)

        elif icon_name in ("milestone", "diamond"):
            # Diamond gateway milestone
            path.moveTo(cx, y + h * 0.10)
            path.lineTo(x + w * 0.90, cy)
            path.lineTo(cx, y + h * 0.90)
            path.lineTo(x + w * 0.10, cy)
            path.closeSubpath()

        elif icon_name == "search":
            # Search magnifying glass
            radius = min(w, h) * 0.28
            glass_cx = x + w * 0.42
            glass_cy = y + h * 0.42
            path.addEllipse(QPointF(glass_cx, glass_cy), radius, radius)
            path.moveTo(glass_cx + radius * 0.707, glass_cy + radius * 0.707)
            path.lineTo(x + w * 0.85, y + h * 0.85)

        elif icon_name == "edit":
            # Pencil / Edit icon
            path.moveTo(x + w * 0.65, y + h * 0.15)
            path.lineTo(x + w * 0.85, y + h * 0.35)
            path.lineTo(x + w * 0.35, y + h * 0.85)
            path.lineTo(x + w * 0.15, y + h * 0.85)
            path.lineTo(x + w * 0.15, y + h * 0.65)
            path.closeSubpath()

        elif icon_name == "trash" or icon_name == "delete":
            # Trash can
            path.moveTo(x + w * 0.25, y + h * 0.30)
            path.lineTo(x + w * 0.75, y + h * 0.30)
            path.moveTo(x + w * 0.32, y + h * 0.30)
            path.lineTo(x + w * 0.35, y + h * 0.85)
            path.lineTo(x + w * 0.65, y + h * 0.85)
            path.lineTo(x + w * 0.68, y + h * 0.30)
            # Lid handle
            path.moveTo(x + w * 0.40, y + h * 0.30)
            path.lineTo(x + w * 0.40, y + h * 0.20)
            path.lineTo(x + w * 0.60, y + h * 0.20)
            path.lineTo(x + w * 0.60, y + h * 0.30)

        elif icon_name == "more" or icon_name == "ellipsis":
            # Three dots
            dot_r = min(w, h) * 0.08
            path.addEllipse(QPointF(x + w * 0.25, cy), dot_r, dot_r)
            path.addEllipse(QPointF(cx, cy), dot_r, dot_r)
            path.addEllipse(QPointF(x + w * 0.75, cy), dot_r, dot_r)

        elif icon_name == "filter":
            # Funnel icon
            path.moveTo(x + w * 0.15, y + h * 0.20)
            path.lineTo(x + w * 0.85, y + h * 0.20)
            path.lineTo(x + w * 0.58, y + h * 0.55)
            path.lineTo(x + w * 0.58, y + h * 0.82)
            path.lineTo(x + w * 0.42, y + h * 0.72)
            path.lineTo(x + w * 0.42, y + h * 0.55)
            path.closeSubpath()

        elif icon_name == "sort":
            # Up/down sort arrows
            path.moveTo(x + w * 0.35, y + h * 0.70)
            path.lineTo(x + w * 0.35, y + h * 0.30)
            path.lineTo(x + w * 0.20, y + h * 0.45)
            path.moveTo(x + w * 0.65, y + h * 0.30)
            path.lineTo(x + w * 0.65, y + h * 0.70)
            path.lineTo(x + w * 0.80, y + h * 0.55)

        elif icon_name == "settings":
            # Cog / Settings
            outer_r = min(w, h) * 0.38
            inner_r = min(w, h) * 0.18
            path.addEllipse(QPointF(cx, cy), outer_r, outer_r)
            path.addEllipse(QPointF(cx, cy), inner_r, inner_r)

        elif icon_name == "refresh":
            # Circular arrow
            r = min(w, h) * 0.32
            path.arcMoveTo(cx - r, cy - r, r * 2, r * 2, 45)
            path.arcTo(cx - r, cy - r, r * 2, r * 2, 45, 270)
            # Arrowhead
            head_x = cx + r * 0.707
            head_y = cy - r * 0.707
            path.lineTo(head_x + w * 0.08, head_y - h * 0.08)
            path.moveTo(head_x, head_y)
            path.lineTo(head_x - w * 0.08, head_y - h * 0.08)

        elif icon_name == "pin":
            # Pin icon
            path.moveTo(cx - w * 0.20, y + h * 0.20)
            path.lineTo(cx + w * 0.20, y + h * 0.20)
            path.lineTo(cx + w * 0.10, y + h * 0.55)
            path.lineTo(cx + w * 0.25, y + h * 0.55)
            path.lineTo(cx, y + h * 0.85)
            path.lineTo(cx - w * 0.25, y + h * 0.55)
            path.lineTo(cx - w * 0.10, y + h * 0.55)
            path.closeSubpath()

        elif icon_name == "folder" or icon_name == "summary":
            # Folder outline
            path.moveTo(x + w * 0.15, y + h * 0.25)
            path.lineTo(x + w * 0.42, y + h * 0.25)
            path.lineTo(x + w * 0.52, y + h * 0.35)
            path.lineTo(x + w * 0.85, y + h * 0.35)
            path.lineTo(x + w * 0.85, y + h * 0.78)
            path.lineTo(x + w * 0.15, y + h * 0.78)
            path.closeSubpath()

        elif icon_name == "task" or icon_name == "file":
            # Task document outline
            path.moveTo(x + w * 0.22, y + h * 0.18)
            path.lineTo(x + w * 0.60, y + h * 0.18)
            path.lineTo(x + w * 0.78, y + h * 0.36)
            path.lineTo(x + w * 0.78, y + h * 0.82)
            path.lineTo(x + w * 0.22, y + h * 0.82)
            path.closeSubpath()

        elif icon_name == "home":
            # House outline
            path.moveTo(x + w * 0.15, y + h * 0.50)
            path.lineTo(cx, y + h * 0.18)
            path.lineTo(x + w * 0.85, y + h * 0.50)
            path.moveTo(x + w * 0.25, y + h * 0.45)
            path.lineTo(x + w * 0.25, y + h * 0.82)
            path.lineTo(x + w * 0.75, y + h * 0.82)
            path.lineTo(x + w * 0.75, y + h * 0.45)

        elif icon_name == "inbox" or icon_name == "tray":
            # Inbox tray
            path.moveTo(x + w * 0.15, y + h * 0.55)
            path.lineTo(x + w * 0.32, y + h * 0.55)
            path.lineTo(x + w * 0.40, y + h * 0.70)
            path.lineTo(x + w * 0.60, y + h * 0.70)
            path.lineTo(x + w * 0.68, y + h * 0.55)
            path.lineTo(x + w * 0.85, y + h * 0.55)
            path.moveTo(x + w * 0.15, y + h * 0.55)
            path.lineTo(x + w * 0.22, y + h * 0.25)
            path.lineTo(x + w * 0.78, y + h * 0.25)
            path.lineTo(x + w * 0.85, y + h * 0.55)
            path.moveTo(x + w * 0.15, y + h * 0.55)
            path.lineTo(x + w * 0.15, y + h * 0.78)
            path.lineTo(x + w * 0.85, y + h * 0.78)
            path.lineTo(x + w * 0.85, y + h * 0.55)

        elif icon_name == "star":
            # Five-point star outline
            import math
            outer_r = min(w, h) * 0.40
            inner_r = outer_r * 0.42
            for i in range(5):
                outer_angle = -math.pi / 2 + i * 2 * math.pi / 5
                inner_angle = outer_angle + math.pi / 5
                ox = cx + outer_r * math.cos(outer_angle)
                oy = cy + outer_r * math.sin(outer_angle)
                ix = cx + inner_r * math.cos(inner_angle)
                iy = cy + inner_r * math.sin(inner_angle)
                if i == 0:
                    path.moveTo(ox, oy)
                else:
                    path.lineTo(ox, oy)
                path.lineTo(ix, iy)
            path.closeSubpath()

        elif icon_name == "target":
            # Target / focus circles with center dot
            r1 = min(w, h) * 0.38
            r2 = min(w, h) * 0.22
            r3 = min(w, h) * 0.07
            path.addEllipse(QPointF(cx, cy), r1, r1)
            path.addEllipse(QPointF(cx, cy), r2, r2)
            path.addEllipse(QPointF(cx, cy), r3, r3)

        elif icon_name == "calendar":
            # Calendar page with binding rings
            path.addRect(QRectF(x + w * 0.16, y + h * 0.24, w * 0.68, h * 0.60))
            path.moveTo(x + w * 0.16, y + h * 0.42)
            path.lineTo(x + w * 0.84, y + h * 0.42)
            path.moveTo(x + w * 0.33, y + h * 0.14)
            path.lineTo(x + w * 0.33, y + h * 0.32)
            path.moveTo(x + w * 0.67, y + h * 0.14)
            path.lineTo(x + w * 0.67, y + h * 0.32)

        elif icon_name == "check_circle":
            # Circle with checkmark
            r = min(w, h) * 0.38
            path.addEllipse(QPointF(cx, cy), r, r)
            path.moveTo(x + w * 0.30, cy)
            path.lineTo(x + w * 0.45, y + h * 0.66)
            path.lineTo(x + w * 0.72, y + h * 0.36)

        elif icon_name == "chart":
            # Bar chart
            path.moveTo(x + w * 0.18, y + h * 0.85)
            path.lineTo(x + w * 0.85, y + h * 0.85)
            path.moveTo(x + w * 0.30, y + h * 0.85)
            path.lineTo(x + w * 0.30, y + h * 0.55)
            path.moveTo(x + w * 0.52, y + h * 0.85)
            path.lineTo(x + w * 0.52, y + h * 0.35)
            path.moveTo(x + w * 0.74, y + h * 0.85)
            path.lineTo(x + w * 0.74, y + h * 0.18)

        elif icon_name == "chat":
            # Speech bubble
            path.moveTo(x + w * 0.15, y + h * 0.20)
            path.lineTo(x + w * 0.85, y + h * 0.20)
            path.lineTo(x + w * 0.85, y + h * 0.65)
            path.lineTo(x + w * 0.42, y + h * 0.65)
            path.lineTo(x + w * 0.22, y + h * 0.84)
            path.lineTo(x + w * 0.24, y + h * 0.65)
            path.lineTo(x + w * 0.15, y + h * 0.65)
            path.closeSubpath()

        elif icon_name == "globe":
            # Globe with meridians
            r = min(w, h) * 0.38
            path.addEllipse(QPointF(cx, cy), r, r)
            path.moveTo(x + w * 0.12, cy)
            path.lineTo(x + w * 0.88, cy)
            path.moveTo(cx, y + h * 0.12)
            path.lineTo(cx, y + h * 0.88)
            path.moveTo(x + w * 0.24, y + h * 0.22)
            path.quadTo(cx, cy, x + w * 0.24, y + h * 0.78)
            path.moveTo(x + w * 0.76, y + h * 0.22)
            path.quadTo(cx, cy, x + w * 0.76, y + h * 0.78)

        elif icon_name == "bell":
            # Notification bell
            path.moveTo(x + w * 0.24, y + h * 0.62)
            path.lineTo(x + w * 0.24, y + h * 0.46)
            path.quadTo(x + w * 0.24, y + h * 0.18, cx, y + h * 0.18)
            path.quadTo(x + w * 0.76, y + h * 0.18, x + w * 0.76, y + h * 0.46)
            path.lineTo(x + w * 0.76, y + h * 0.62)
            path.lineTo(x + w * 0.86, y + h * 0.74)
            path.lineTo(x + w * 0.14, y + h * 0.74)
            path.closeSubpath()
            # Clapper
            path.moveTo(x + w * 0.42, y + h * 0.82)
            path.quadTo(cx, y + h * 0.92, x + w * 0.58, y + h * 0.82)

        elif icon_name == "clock":
            # Clock face with hands
            r = min(w, h) * 0.38
            path.addEllipse(QPointF(cx, cy), r, r)
            path.moveTo(cx, cy)
            path.lineTo(cx, y + h * 0.26)
            path.moveTo(cx, cy)
            path.lineTo(x + w * 0.64, cy)

        elif icon_name == "sun":
            # Sun with rays
            r = min(w, h) * 0.22
            path.addEllipse(QPointF(cx, cy), r, r)
            import math as _m
            for i in range(8):
                ang = i * _m.pi / 4
                x1 = cx + (r * 1.6) * _m.cos(ang)
                y1 = cy + (r * 1.6) * _m.sin(ang)
                x2 = cx + (r * 2.1) * _m.cos(ang)
                y2 = cy + (r * 2.1) * _m.sin(ang)
                path.moveTo(x1, y1)
                path.lineTo(x2, y2)

        elif icon_name == "moon":
            # Crescent moon
            path.moveTo(x + w * 0.62, y + h * 0.14)
            path.quadTo(x + w * 0.18, y + h * 0.28, x + w * 0.30, cy)
            path.quadTo(x + w * 0.40, y + h * 0.76, x + w * 0.86, y + h * 0.72)
            path.quadTo(x + w * 0.70, y + h * 0.92, x + w * 0.52, y + h * 0.88)
            path.quadTo(x + w * 0.14, y + h * 0.72, x + w * 0.26, y + h * 0.34)
            path.quadTo(x + w * 0.36, y + h * 0.14, x + w * 0.62, y + h * 0.14)

        else:
            # Fallback circle
            r = min(w, h) * 0.35
            path.addEllipse(QPointF(cx, cy), r, r)

        return path

    @classmethod
    def render_vector_icon(
        cls,
        painter: QPainter,
        icon_name: str,
        rect: QRectF,
        color: QColor,
        stroke_width: float = 1.6,
        filled: bool = False,
    ):
        """Paints a vector icon directly onto the provided QPainter with antialiasing."""
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        path = cls.create_path(icon_name, rect)

        if filled or icon_name in ("milestone", "diamond"):
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawPath(path)
            # Add subtle crisp stroke for diamond
            pen = QPen(color.lighter(115), stroke_width)
            pen.setJoinStyle(Qt.RoundJoin)
            pen.setCapStyle(Qt.RoundCap)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(pen)
            painter.drawPath(path)
        else:
            pen = QPen(color, stroke_width)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)

        painter.restore()

    @classmethod
    def get_pixmap(
        cls,
        icon_name: str,
        size_px: int = 16,
        color: str = "#CDD6F4",
        dpr: float = 1.0,
        filled: bool = False,
    ) -> QPixmap:
        """Retrieves a cached DPI-scaled vector pixmap."""
        cache_key = (icon_name, size_px, dpr, color)
        if cache_key in cls._pixmap_cache:
            return cls._pixmap_cache[cache_key]

        physical_size = int(size_px * dpr)
        pixmap = QPixmap(physical_size, physical_size)
        pixmap.fill(Qt.transparent)
        pixmap.setDevicePixelRatio(dpr)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(0, 0, size_px, size_px)
        cls.render_vector_icon(
            painter,
            icon_name,
            rect,
            QColor(color),
            stroke_width=1.6,
            filled=filled,
        )
        painter.end()

        cls._pixmap_cache[cache_key] = pixmap
        return pixmap

    @classmethod
    def get_icon(cls, icon_name: str, color: str = "#CDD6F4") -> QIcon:
        """Builds a QIcon supporting 1.0x and 2.0x DPI."""
        icon = QIcon()
        icon.addPixmap(cls.get_pixmap(icon_name, 16, color, 1.0))
        icon.addPixmap(cls.get_pixmap(icon_name, 16, color, 2.0))
        return icon
