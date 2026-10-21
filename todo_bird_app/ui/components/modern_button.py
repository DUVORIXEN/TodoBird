"""
TODO BIRD — MODERN BUTTON COMPONENT SYSTEM
Provides a premium, unified button system matching modern market benchmarks (Linear, Notion, Things).
Supports variants (Primary, Secondary, Ghost, Tonal, Danger, Capsule, Segmented),
states (normal, hover, pressed, focused, disabled, checked), keyboard accessibility, and tooltips.
"""

from enum import Enum
from typing import Optional
from PySide6.QtCore import Qt, QRectF, QSize, Signal, QPropertyAnimation, QEasingCurve, QEvent
from PySide6.QtWidgets import QAbstractButton, QWidget, QSizePolicy, QApplication
from PySide6.QtGui import (
    QPainter,
    QPainterPath,
    QColor,
    QPen,
    QBrush,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QFocusEvent,
    QLinearGradient,
)

from todo_bird_app.ui.design_tokens import DesignTokens
from todo_bird_app.services.icon_service import IconService
from todo_bird_app.services.appearance_service import semantic_tokens_for


class ButtonVariant(Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    GHOST = "ghost"
    TONAL = "tonal"
    DANGER = "danger"
    CAPSULE = "capsule"
    SEGMENTED = "segmented"


class ButtonSize(Enum):
    COMPACT = "compact"      # 28px height, 12px font
    STANDARD = "standard"    # 34px height, 13px font
    LARGE = "large"          # 40px height, 14px font


class ButtonStyleDesign(Enum):
    FLAT_MODERN = "flat"
    RAISED_3D = "3d_raised"
    EXECUTIVE_SOFT = "executive_soft"
    NEUMORPHIC_3D = "neumorphic"
    GLOW_OUTLINE = "glow"


class ModernButton(QAbstractButton):
    """
    State-of-the-art modern interactive button with customizable 3D design modes.
    Renders with vector antialiasing, 3D specular gradients, bevel highlights,
    crisp focus ring, hover highlight, and tactile press state.
    """
    _global_design_mode: ButtonStyleDesign = ButtonStyleDesign.RAISED_3D
    _global_density: str = "balanced"

    @classmethod
    def set_global_design_mode(cls, mode: ButtonStyleDesign):
        if not isinstance(mode, ButtonStyleDesign):
            try:
                mode = ButtonStyleDesign(str(mode))
            except Exception:
                mode = ButtonStyleDesign.RAISED_3D
        cls._global_design_mode = mode
        cls.refresh_all_instances()

    @classmethod
    def get_global_design_mode(cls) -> ButtonStyleDesign:
        return cls._global_design_mode

    @classmethod
    def set_global_density(cls, density: str):
        density = str(density or "balanced").lower().strip()
        if density not in {"compact", "balanced", "spacious"}:
            density = "balanced"
        cls._global_density = density
        cls.refresh_all_instances()

    @classmethod
    def refresh_all_instances(cls):
        app = QApplication.instance()
        if app is None:
            return
        for widget in list(app.allWidgets()):
            if isinstance(widget, cls):
                widget._update_geometry()
                widget.update()

    def __init__(
        self,
        text: str = "",
        variant: ButtonVariant = ButtonVariant.SECONDARY,
        size: ButtonSize = ButtonSize.STANDARD,
        icon_name: Optional[str] = None,
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

        self.setText(text)
        self._variant = variant
        self._size = size
        self._icon_name = icon_name
        self._is_dark = is_dark
        self._accent_color = accent_color
        self._is_hovered = False
        self._is_pressed = False
        self._is_focused = False

        self.setFocusPolicy(Qt.StrongFocus)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("todoBirdTheme", "dark" if self._is_dark else "light")
        self.setProperty("todoBirdAccent", self._accent_color)
        self._update_geometry()

    def setText(self, text: str):
        super().setText(text)
        if hasattr(self, "_padding_h"):
            self._update_geometry()
            self.update()

    # -------------------------------------------------------------------------
    # Properties & Setters
    # -------------------------------------------------------------------------

    @property
    def variant(self) -> ButtonVariant:
        return self._variant

    @variant.setter
    def variant(self, val: ButtonVariant):
        self._variant = val
        self.update()

    @property
    def button_size(self) -> ButtonSize:
        return self._size

    @button_size.setter
    def button_size(self, val: ButtonSize):
        self._size = val
        self._update_geometry()
        self.update()

    @property
    def icon_name(self) -> Optional[str]:
        return self._icon_name

    @icon_name.setter
    def icon_name(self, val: Optional[str]):
        self._icon_name = val
        self.update()

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color
        self.setProperty("todoBirdTheme", "dark" if self._is_dark else "light")
        self.setProperty("todoBirdAccent", self._accent_color)
        self._update_geometry()
        self.update()

    def _update_geometry(self):
        density = self._global_density
        density_height_delta = {
            "compact": -2,
            "balanced": 0,
            "spacious": 4,
        }.get(density, 0)
        density_padding_delta = {
            "compact": -2,
            "balanced": 0,
            "spacious": 3,
        }.get(density, 0)

        if self._size == ButtonSize.COMPACT:
            self._height = 26 + density_height_delta
            self._padding_h = 8 + density_padding_delta
            self._padding_v = 3 + max(0, density_height_delta // 2)
            self._radius = 5
            self._icon_size = 13
        elif self._size == ButtonSize.LARGE:
            self._height = 36 + density_height_delta
            self._padding_h = 14 + density_padding_delta
            self._padding_v = 6 + max(0, density_height_delta // 2)
            self._radius = 8
            self._icon_size = 17
        else:  # STANDARD
            self._height = 30 + density_height_delta
            self._padding_h = 10 + density_padding_delta
            self._padding_v = 4 + max(0, density_height_delta // 2)
            self._radius = 6
            self._icon_size = 15

        if self._variant == ButtonVariant.CAPSULE:
            self._radius = self._height // 2

        self._height = max(24, int(self._height))
        self._padding_h = max(6, int(self._padding_h))
        self._padding_v = max(2, int(self._padding_v))
        hint = self.sizeHint()
        self.setMinimumWidth(hint.width())
        self.setMinimumHeight(hint.height())
        self.setMaximumHeight(16777215)
        self.updateGeometry()

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        text_w = fm.horizontalAdvance(self.text()) if self.text() else 0
        icon_w = (self._icon_size + 6) if self._icon_name else 0
        total_w = text_w + icon_w + (self._padding_h * 2)
        font_h = fm.height() + (self._padding_v * 2) + 2
        eff_h = max(self._height, font_h)
        if not self.text() and self._icon_name:
            total_w = eff_h  # Square icon button
        return QSize(max(total_w, eff_h), eff_h)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event is not None and event.type() == QEvent.FontChange:
            self._update_geometry()
            self.update()

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._is_pressed = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._is_pressed = False
            self.update()
        super().mouseReleaseEvent(event)

    def focusInEvent(self, event: QFocusEvent):
        self._is_focused = True
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event: QFocusEvent):
        self._is_focused = False
        self.update()
        super().focusOutEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)

    # -------------------------------------------------------------------------
    # Color Computation & Paint Engine
    # -------------------------------------------------------------------------

    def _compute_colors(self) -> dict:
        accent = QColor(self._accent_color)
        is_disabled = not self.isEnabled()

        tokens = semantic_tokens_for(self._is_dark, self._accent_color)
        bg_base = QColor(tokens["SURFACE_2"])
        border_base = QColor(tokens["BORDER_NORMAL"])
        text_base = QColor(tokens["TEXT_PRIMARY"])
        text_muted = QColor(tokens["TEXT_MUTED"])

        if is_disabled:
            return {
                "bg": QColor(bg_base.red(), bg_base.green(), bg_base.blue(), 60),
                "border": QColor(border_base.red(), border_base.green(), border_base.blue(), 60),
                "text": text_muted,
                "icon": text_muted,
            }

        # 1. PRIMARY
        if self._variant == ButtonVariant.PRIMARY:
            bg = accent
            border = accent.lighter(120)
            if self._is_pressed:
                bg = accent.darker(120)
                border = accent.darker(110)
            elif self._is_hovered:
                bg = accent.lighter(112)
                border = accent.lighter(130)
            return {
                "bg": bg,
                "border": border,
                "text": QColor(tokens["TEXT_ON_ACCENT"]),
                "icon": QColor(tokens["TEXT_ON_ACCENT"]),
            }

        # 2. DANGER
        elif self._variant == ButtonVariant.DANGER:
            danger_col = QColor(tokens["DANGER"])
            bg = danger_col
            border = danger_col.lighter(120)
            if self._is_pressed:
                bg = danger_col.darker(120)
            elif self._is_hovered:
                bg = danger_col.lighter(112)
            return {
                "bg": bg,
                "border": border,
                "text": QColor(tokens["TEXT_ON_DANGER"]),
                "icon": QColor(tokens["TEXT_ON_DANGER"]),
            }

        # 3. TONAL
        elif self._variant == ButtonVariant.TONAL:
            alpha = 45 if self._is_dark else 25
            if self._is_hovered:
                alpha += 25
            if self._is_pressed:
                alpha += 40
            bg = QColor(accent.red(), accent.green(), accent.blue(), alpha)
            border = QColor(accent.red(), accent.green(), accent.blue(), 180) if not self._is_hovered else accent
            return {"bg": bg, "border": border, "text": accent if self._is_dark else accent.darker(120), "icon": accent}

        # 4. GHOST
        elif self._variant == ButtonVariant.GHOST:
            bg = QColor(255, 255, 255, 18) if (self._is_dark and self._is_hovered) else (QColor(0, 0, 0, 12) if self._is_hovered else QColor(0, 0, 0, 0))
            if self._is_pressed:
                bg = QColor(255, 255, 255, 30) if self._is_dark else QColor(0, 0, 0, 24)
            border = accent if self._is_hovered else QColor(tokens["BORDER_SUBTLE"])
            return {"bg": bg, "border": border, "text": text_base, "icon": text_base}

        # 5. SEGMENTED
        elif self._variant == ButtonVariant.SEGMENTED:
            if self.isChecked():
                bg = accent if self._is_dark else accent.lighter(140)
                border = accent
                text_col = QColor(tokens["TEXT_ON_ACCENT"]) if self._is_dark else accent.darker(150)
            else:
                bg = QColor(0, 0, 0, 0)
                border = border_base
                text_col = text_muted if not self._is_hovered else text_base
            return {"bg": bg, "border": border, "text": text_col, "icon": text_col}

        # 6. SECONDARY & CAPSULE (Default)
        else:
            bg = bg_base
            border = border_base
            if self._is_hovered:
                bg = bg.lighter(110) if self._is_dark else bg.darker(104)
                border = accent
            if self._is_pressed:
                bg = bg.darker(110)
            return {"bg": bg, "border": border, "text": text_base, "icon": text_base}

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self._is_pressed:
            rect = rect.translated(0, 1.2)  # Tactile press depth

        colors = self._compute_colors()
        mode = self._global_design_mode

        # Background Path
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)

        base_bg = colors["bg"]

        # 3D Raised / Glass specular gradient rendering
        if mode == ButtonStyleDesign.RAISED_3D and base_bg.alpha() > 0:
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0.0, base_bg.lighter(118))
            grad.setColorAt(0.5, base_bg)
            grad.setColorAt(1.0, base_bg.darker(115))
            painter.fillPath(path, QBrush(grad))

            # 1px top inner specular highlight edge
            hi_rect = QRectF(rect.x() + 2, rect.y() + 1, rect.width() - 4, 1.2)
            hi_path = QPainterPath()
            hi_path.addRoundedRect(hi_rect, 1.0, 1.0)
            painter.fillPath(hi_path, QBrush(QColor(255, 255, 255, 60 if self._is_dark else 120)))

            # Bottom bevel shadow edge
            sh_rect = QRectF(rect.x() + 2, rect.bottom() - 2, rect.width() - 4, 1.2)
            sh_path = QPainterPath()
            sh_path.addRoundedRect(sh_rect, 1.0, 1.0)
            painter.fillPath(sh_path, QBrush(QColor(0, 0, 0, 70 if self._is_dark else 40)))

        elif mode == ButtonStyleDesign.EXECUTIVE_SOFT and base_bg.alpha() > 0:
            grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            grad.setColorAt(0.0, base_bg.lighter(108))
            grad.setColorAt(1.0, base_bg.darker(106))
            painter.fillPath(path, QBrush(grad))
        elif mode == ButtonStyleDesign.NEUMORPHIC_3D and base_bg.alpha() > 0:
            painter.fillPath(path, QBrush(base_bg))
            # Embossed rim
            rim_pen = QPen(QColor(255, 255, 255, 45) if self._is_dark else QColor(0, 0, 0, 30), 1.2)
            painter.strokePath(path, rim_pen)
        elif mode == ButtonStyleDesign.GLOW_OUTLINE and base_bg.alpha() > 0:
            painter.fillPath(path, QBrush(base_bg))
            # Accent glow outline
            glow_col = QColor(self._accent_color)
            glow_col.setAlpha(90 if not self._is_hovered else 160)
            glow_pen = QPen(glow_col, 2.0 if self._is_hovered else 1.5)
            painter.strokePath(path, glow_pen)
        else:
            # FLAT_MODERN or default
            painter.fillPath(path, QBrush(base_bg))

        # Draw Border - Always prominent 3D outline box
        if colors["border"].alpha() > 0:
            bw = 2.0 if (self._is_hovered or self._is_focused) else 1.5
            border_pen = QPen(colors["border"], bw)
            painter.strokePath(path, border_pen)

        # Draw Keyboard Focus Ring
        if self._is_focused and self.isEnabled():
            focus_rect = rect.adjusted(-1, -1, 1, 1)
            focus_path = QPainterPath()
            focus_path.addRoundedRect(focus_rect, self._radius + 1, self._radius + 1)
            focus_pen = QPen(QColor(self._accent_color), 1.8)
            painter.strokePath(focus_path, focus_pen)

        # Content Layout (Icon + Text)
        content_rect = rect
        has_text = bool(self.text())
        has_icon = bool(self._icon_name)

        btn_font = QFont(self.font())
        if self._variant == ButtonVariant.PRIMARY:
            btn_font.setWeight(QFont.DemiBold)
        painter.setFont(btn_font)

        if has_icon and not has_text:
            # Centered Icon Only
            icon_box = QRectF(
                (content_rect.width() - self._icon_size) / 2.0,
                (content_rect.height() - self._icon_size) / 2.0,
                self._icon_size,
                self._icon_size,
            )
            IconService.render_vector_icon(painter, self._icon_name, icon_box, colors["icon"])

        elif has_icon and has_text:
            # Icon + Text
            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(self.text())
            gap = 6
            total_content_w = self._icon_size + gap + text_w
            start_x = (content_rect.width() - total_content_w) / 2.0

            icon_box = QRectF(start_x, (content_rect.height() - self._icon_size) / 2.0, self._icon_size, self._icon_size)
            IconService.render_vector_icon(painter, self._icon_name, icon_box, colors["icon"])

            text_rect = QRectF(start_x + self._icon_size + gap, 0, text_w + 4, content_rect.height())
            painter.setPen(colors["text"])
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())

        elif has_text:
            # Text Only Centered
            painter.setPen(colors["text"])
            painter.drawText(content_rect, Qt.AlignCenter, self.text())

        painter.end()


class IconButton(ModernButton):
    """
    Specialized compact icon-only button with rich tooltip and shortcut badge support.
    """

    def __init__(
        self,
        icon_name: str,
        tooltip_text: str = "",
        shortcut_text: str = "",
        variant: ButtonVariant = ButtonVariant.GHOST,
        size: ButtonSize = ButtonSize.STANDARD,
        parent: Optional[QWidget] = None,
        is_dark: bool = True,
        accent_color: str = DesignTokens.COLOR_ACCENT,
    ):
        super().__init__(
            text="",
            variant=variant,
            size=size,
            icon_name=icon_name,
            parent=parent,
            is_dark=is_dark,
            accent_color=accent_color,
        )
        self._shortcut_text = shortcut_text
        self._tooltip_text = tooltip_text
        self._apply_tooltip()

    def _apply_tooltip(self):
        if self._tooltip_text and self._shortcut_text:
            self.setToolTip(f"{self._tooltip_text} ({self._shortcut_text})")
        elif self._tooltip_text:
            self.setToolTip(self._tooltip_text)
        elif self._shortcut_text:
            self.setToolTip(self._shortcut_text)

    def set_shortcut_hint(self, shortcut: str):
        self._shortcut_text = shortcut
        self._apply_tooltip()
