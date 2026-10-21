"""
TODO BIRD — Background Overlay & Legibility Engine (Batch 3.5)
Renders the customizable application background behind views with:
- Configurable fit modes: Fill, Fit, Center, Tile
- Smooth opacity (0% to 100%)
- Adaptive contrast overlay (Light frosted / Dark translucent)
- Zero UI freeze / cached scaled pixmaps
- Guaranteed text readability
"""
import logging
from typing import Optional
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QPixmap, QColor, QBrush
from PySide6.QtCore import Qt, QRect

from todo_bird_app.services.media_service import MediaService
from todo_bird_app.services.appearance_service import AppearanceService
from todo_bird_app.services.background_service import (
    BACKGROUND_MODE_IMAGE,
    BACKGROUND_MODE_SOLID,
    BACKGROUND_MODE_THEME_DEFAULT,
    BACKGROUND_MODE_TRANSPARENT,
    BackgroundConfig,
    BackgroundService,
)
from todo_bird_app.settings.settings_manager import SettingsManager

logger = logging.getLogger(__name__)


class BackgroundOverlayWidget(QWidget):
    """Underlay widget rendering application background with adaptive legibility overlay."""

    def __init__(self, parent: Optional[QWidget] = None, settings_manager: Optional[SettingsManager] = None):
        super().__init__(parent)
        self.settings = settings_manager or SettingsManager()
        self.view_id: Optional[str] = None
        self.config = BackgroundConfig()
        self._cached_pixmap: Optional[QPixmap] = None
        self._last_image_path: str = ""
        self._last_size: tuple = (0, 0)
        self._last_fit_mode: str = ""
        self._scaled_pixmap: Optional[QPixmap] = None
        self._last_failed_image_path: str = ""
        self.setAutoFillBackground(False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.reload_settings()

    def set_view_id(self, view_id: Optional[str]):
        view_id = str(view_id or "").strip().lower() or None
        if self.view_id != view_id:
            self.view_id = view_id
            self.reload_settings()

    def reload_settings(self, settings_manager: Optional[SettingsManager] = None, view_id: Optional[str] = None):
        """Reloads background configuration from settings."""
        if settings_manager is not None:
            self.settings = settings_manager
        if view_id is not None:
            self.view_id = str(view_id or "").strip().lower() or None

        appearance = AppearanceService.read(self.settings)
        self.config = BackgroundService.effective_config(
            self.settings,
            view_id=self.view_id,
            tokens=appearance.tokens,
        )
        self.bg_mode = self.config.mode
        self.bg_image_path = self.config.image
        self.fit_mode = self.config.fit
        self.opacity = self.config.opacity
        self.overlay_mode = self.config.overlay_mode
        self.bg_color = self.config.color
        self._scaled_pixmap = None
        self.update()

    def reload_from_settings(self, settings_manager: Optional[SettingsManager] = None, view_id: Optional[str] = None):
        """Alias for reload_settings."""
        self.reload_settings(settings_manager, view_id=view_id)

    def set_background_image(self, relative_or_abs_path: str, fit_mode: str = "fill", opacity: float = 0.35):
        """Sets new background parameters and repaints."""
        self.bg_mode = BACKGROUND_MODE_IMAGE if relative_or_abs_path else BACKGROUND_MODE_THEME_DEFAULT
        self.bg_image_path = relative_or_abs_path
        self.fit_mode = fit_mode.lower()
        self.opacity = max(0.0, min(1.0, opacity))
        self.config = self.config.with_changes(
            mode=self.bg_mode,
            image=self.bg_image_path,
            fit=self.fit_mode,
            opacity=self.opacity,
        )
        self._scaled_pixmap = None
        self.update()

    def _theme_default_color(self) -> QColor:
        try:
            appearance = AppearanceService.read(self.settings)
            color = QColor(appearance.tokens["APP_BACKGROUND"])
        except Exception:
            color = QColor("#161821")
        return color if color.isValid() else QColor("#161821")

    def _paint_theme_default(self, painter: QPainter, opacity: float = 1.0):
        color = self._theme_default_color()
        color.setAlphaF(max(0.0, min(1.0, opacity)))
        painter.fillRect(self.rect(), color)

    def _load_current_pixmap(self) -> Optional[QPixmap]:
        if not self.bg_image_path:
            return None
        if self._last_image_path != self.bg_image_path:
            self._cached_pixmap = MediaService.load_pixmap(self.bg_image_path)
            self._last_image_path = self.bg_image_path
            self._scaled_pixmap = None
            self._last_size = (0, 0)
            self._last_fit_mode = ""
        if self._cached_pixmap is None or self._cached_pixmap.isNull():
            return None
        return self._cached_pixmap

    def _scaled_for_current_rect(self, pixmap: QPixmap) -> QPixmap:
        size_key = (self.width(), self.height())
        if (
            self._scaled_pixmap is not None
            and not self._scaled_pixmap.isNull()
            and self._last_size == size_key
            and self._last_fit_mode == self.fit_mode
        ):
            return self._scaled_pixmap

        if self.fit_mode == "fit":
            mode = Qt.AspectRatioMode.KeepAspectRatio
        elif self.fit_mode == "stretch":
            mode = Qt.AspectRatioMode.IgnoreAspectRatio
        else:
            mode = Qt.AspectRatioMode.IgnoreAspectRatio

        self._scaled_pixmap = pixmap.scaled(
            self.width(),
            self.height(),
            mode,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._last_size = size_key
        self._last_fit_mode = self.fit_mode
        return self._scaled_pixmap

    def paintEvent(self, event):
        if self.bg_mode == BACKGROUND_MODE_TRANSPARENT and self.opacity <= 0.0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            painter.end()
            return

        if self.bg_mode == BACKGROUND_MODE_THEME_DEFAULT:
            self._paint_theme_default(painter)
            painter.end()
            return

        if self.bg_mode == BACKGROUND_MODE_SOLID:
            color = QColor(self.bg_color)
            if not color.isValid():
                color = self._theme_default_color()
            color.setAlphaF(self.opacity)
            painter.fillRect(self.rect(), color)
            painter.end()
            return

        if self.bg_mode == BACKGROUND_MODE_TRANSPARENT:
            self._paint_theme_default(painter, opacity=self.opacity)
            painter.end()
            return

        if self.bg_mode == BACKGROUND_MODE_IMAGE:
            if not self.bg_image_path:
                self._paint_theme_default(painter)
                painter.end()
                return

            pixmap = self._load_current_pixmap()
            if pixmap is None:
                if getattr(self, "_last_failed_image_path", "") != self.bg_image_path:
                    logger.warning("Background image could not be loaded: %s", self.bg_image_path)
                    self._last_failed_image_path = self.bg_image_path
                self._paint_theme_default(painter)
                painter.end()
                return
            self._last_failed_image_path = ""
            painter.setOpacity(self.opacity)
            if self.fit_mode == "fill":
                painter.drawPixmap(0, 0, w, h, pixmap)
            elif self.fit_mode == "fit":
                scaled = self._scaled_for_current_rect(pixmap)
                x = (w - scaled.width()) // 2
                y = (h - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
            elif self.fit_mode == "stretch":
                painter.drawPixmap(0, 0, self._scaled_for_current_rect(pixmap))
            elif self.fit_mode == "center":
                cw, ch = pixmap.width(), pixmap.height()
                x = (w - cw) // 2
                y = (h - ch) // 2
                painter.drawPixmap(x, y, pixmap)
            elif self.fit_mode == "tile":
                brush = QBrush(pixmap)
                painter.fillRect(self.rect(), brush)

            # Legibility overlay
            painter.setOpacity(1.0)
            is_dark = str(self.settings.get("theme", "dark")).lower() == "dark"
            if self.overlay_mode == "dark_translucent" or (self.overlay_mode == "auto" and is_dark):
                # Dark frosted overlay
                painter.fillRect(self.rect(), QColor(24, 24, 37, int(200 * self.opacity + 30)))
            elif self.overlay_mode == "light_frosted" or (self.overlay_mode == "auto" and not is_dark):
                # Light frosted overlay
                painter.fillRect(self.rect(), QColor(248, 250, 252, int(190 * self.opacity + 40)))

        painter.end()
