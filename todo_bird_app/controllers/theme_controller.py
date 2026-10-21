import logging
import os
import re
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer, QEvent
from PySide6.QtWidgets import QApplication, QToolTip
from PySide6.QtGui import QPalette, QColor, QFont, QFontDatabase
from todo_bird_app.services.appearance_service import (
    AppearanceService,
    qpalette_from_tokens,
)

logger = logging.getLogger(__name__)

class ThemeController(QObject):
    """
    Controller responsible for theme switching, QSS loading, token substitution,
    and QApplication global QPalette enforcement.
    """
    theme_changed = Signal(str)  # Emits theme name ("dark" or "light")
    appearance_changed = Signal(object)

    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.themes_dir = Path(__file__).parent.parent / "themes"
        self.current_mode = self.settings_manager.get("theme", "dark")
        self.accent_color = self.settings_manager.get("accent_color", "#E95420")
        self._is_applying_theme = False
        self._qss_raw_cache = {}
        # Deferred per-widget refinement pass: the visible theme (QSS,
        # palette, font) applies synchronously so clicks feel instant, then
        # the O(all-widgets) palette/sanitize walk runs on the next event
        # loop turn instead of blocking the click handler.
        self._walk_scheduled = False
        self._pending_walk_appearance = None

        app = QApplication.instance()
        if app is not None:
            try:
                hints = app.styleHints()
                if hasattr(hints, "colorSchemeChanged"):
                    hints.colorSchemeChanged.connect(self._on_system_color_scheme_changed)
            except Exception:
                pass

    def _on_system_color_scheme_changed(self, scheme=None) -> None:
        if str(self.current_mode).lower() == "system":
            self.apply_theme(mode="system")

    @staticmethod
    def _clear_native_tooltip_widgets(app: QApplication) -> None:
        if app is None:
            return
        try:
            QToolTip.hideText()
        except Exception:
            pass

        for widget in list(app.topLevelWidgets()):
            try:
                if widget.objectName() != "qtooltip_label":
                    continue
                widget.close()
                widget.deleteLater()
            except Exception:
                pass

        try:
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            app.processEvents()
        except Exception:
            pass

    @staticmethod
    def _delete_closed_shutdown_windows(app: QApplication) -> None:
        if app is None:
            return

        for widget in list(app.topLevelWidgets()):
            try:
                if widget.isVisible():
                    continue
                if not bool(getattr(widget, "_shutdown_in_progress", False)):
                    continue
                widget.deleteLater()
            except Exception:
                pass

        try:
            QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
            app.processEvents()
        except Exception:
            pass

    def apply_theme(
        self,
        mode: str = None,
        accent_color: str = None,
        *,
        accent_scheme: str = None,
        density: str = None,
        button_style: str = None,
    ):
        if self._is_applying_theme:
            return
        self._is_applying_theme = True
        try:
            scheme_was_provided = bool(accent_scheme)
            if mode:
                self.current_mode = mode
                self.settings_manager.set("theme", mode)
            if accent_scheme:
                accent_color = AppearanceService.set_accent_scheme(
                    self.settings_manager,
                    accent_scheme,
                )
            if accent_color:
                self.accent_color = accent_color
                self.settings_manager.set("accent_color", accent_color)
                if not scheme_was_provided:
                    self.settings_manager.set("accent_scheme", "")
                    self.settings_manager.set("color_scheme", "")
            if density:
                self.settings_manager.set("ui_density", density)
            if button_style:
                self.settings_manager.set("button_design_mode", button_style)

            app = QApplication.instance()
            appearance = AppearanceService.read(
                self.settings_manager,
                app=app,
            )
            self.current_mode = appearance.theme
            self.accent_color = appearance.accent_color
            palette_tokens = AppearanceService.qss_tokens(appearance)

            qss_filename = "dark.qss" if appearance.is_dark else "light.qss"
            if qss_filename not in self._qss_raw_cache:
                qss_path = self.themes_dir / qss_filename
                if not qss_path.exists():
                    logger.error(f"QSS stylesheet not found: {qss_path}")
                    return
                with open(qss_path, "r", encoding="utf-8") as f:
                    self._qss_raw_cache[qss_filename] = f.read()

            qss_content = self._qss_raw_cache[qss_filename]

            # Substitute color tokens (sort keys by length descending to avoid prefix overlap)
            sorted_tokens = sorted(palette_tokens.items(), key=lambda item: len(item[0]), reverse=True)
            for token_key, color_val in sorted_tokens:
                qss_content = qss_content.replace(f"@{token_key}", color_val)

            if app:
                self._clear_native_tooltip_widgets(app)
                self._delete_closed_shutdown_windows(app)

                for key, value in (
                    ("todoBirdTheme", appearance.theme),
                    ("todoBirdAccent", appearance.accent_color),
                    ("todoBirdDensity", appearance.density),
                    ("todoBirdButtonStyle", appearance.button_style),
                    ("todoBirdFontFamily", appearance.font_family),
                    ("todoBirdFontSize", appearance.font_size),
                    ("todoBirdFontWeight", appearance.font_weight),
                ):
                    app.setProperty(key, value)

                # 1. Enforce Global QPalette (including QToolTip so ALL native
                # tooltips — chart widgets, MetricCards, QLabels — render with
                # the correct light/dark background and text colors.
                qpalette = qpalette_from_tokens(appearance.tokens)
                app.setPalette(qpalette)
                # Synchronize Qt's global static QToolTip palette.  Without
                # this, native tooltips default to the system (dark) palette
                # even when the app is in light mode, because QToolTip is a
                # top-level window that does NOT inherit the app stylesheet's
                # QToolTip {} rule reliably on Linux / X11.
                QToolTip.setPalette(qpalette)

                # 2. Apply QSS Stylesheet
                # Per-area typography is now handled by TypographyService.
                # QSS font rules have been removed from area selectors.
                # Only QApplication.setFont() sets the global fallback.
                app.setFont(appearance.font())
                app.setStyleSheet(qss_content)

                # Emit global event so views can apply their specific fonts
                from todo_bird_app.services.typography_service import TypographyService
                TypographyService.notify_typography_changed()

                if os.environ.get("TODO_BIRD_SYNC_APPEARANCE"):
                    # Tests and tooling assert per-widget state immediately.
                    AppearanceService.apply_to_application(app, appearance)
                else:
                    # Cheap global component refresh stays synchronous; the
                    # expensive per-widget sweep is deferred off the click.
                    self._pending_walk_appearance = appearance
                    if not self._walk_scheduled:
                        self._walk_scheduled = True
                        QTimer.singleShot(0, self._run_pending_appearance_walk)

                try:
                    from todo_bird_app.controllers.task_controller import (
                        _GLOBAL_EVENT_BUS,
                    )

                    _GLOBAL_EVENT_BUS.appearance_changed.emit(appearance)
                except Exception:
                    pass

                logger.info(
                    "Appearance applied: theme=%s accent=%s font=%s %spt density=%s button=%s",
                    appearance.theme,
                    appearance.accent_color,
                    appearance.font_family,
                    appearance.font_size,
                    appearance.density,
                    appearance.button_style,
                )
                self.appearance_changed.emit(appearance)
                self.theme_changed.emit(self.current_mode)
        except Exception as e:
            logger.error(f"Error applying theme stylesheet: {e}")
        finally:
            self._is_applying_theme = False

    def _run_pending_appearance_walk(self):
        """Runs the deferred per-widget appearance refinement (latest wins)."""
        self._walk_scheduled = False
        appearance = self._pending_walk_appearance
        self._pending_walk_appearance = None
        app = QApplication.instance()
        if app is None or appearance is None:
            return
        try:
            AppearanceService.apply_to_application(app, appearance)
        except Exception as e:
            logger.error(f"Deferred appearance walk failed: {e}")

    def toggle_theme(self):
        new_mode = "light" if self.current_mode in {"dark", "oled", "nord"} else "dark"
        self.apply_theme(mode=new_mode)
