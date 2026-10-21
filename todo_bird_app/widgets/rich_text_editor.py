"""
Rich Text Editor Widget (Batch 3.10J — Phase 1C S4.1)
Reusable rich-text editing widget with formatting toolbar for Todo Bird.
Supports Bold, Italic, Underline, Bullet/Numbered Lists, Hyperlinks.
Extended: Font Family/Size/Color, Clear Formatting, mixed-selection, shortcuts,
HTML storage, sanitization, dark/light, high-DPI, responsive toolbar.
Stores content as HTML for persistence. Backward-compatible with plain text.
"""

import logging
import re

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QToolBar,
    QTextEdit,
    QInputDialog,
    QComboBox,
    QToolButton,
    QMenu,
    QColorDialog,
    QApplication,
    QSizePolicy,
)
from PySide6.QtGui import (
    QFont,
    QFontDatabase,
    QTextCharFormat,
    QTextCursor,
    QTextListFormat,
    QTextDocument,
    QAction,
    QKeySequence,
    QBrush,
    QColor,
    QShortcut,
)
from PySide6.QtCore import Qt, QSize, Signal

logger = logging.getLogger(__name__)

try:
    from todo_bird_app.ui.design_tokens import DesignTokens  # type: ignore
except Exception:  # pragma: no cover
    DesignTokens = None  # type: ignore


_FONT_SIZE_PRESETS = [8, 9, 10, 11, 12, 13, 14, 16, 18, 20, 24, 28, 32, 36, 48, 64]
_FONT_SIZE_MIN = 6
_FONT_SIZE_MAX = 96


def _contrast_ratio(hex_fg: str, hex_bg: str) -> float:
    """WCAG 2.1 contrast ratio helper."""

    def _parse(c: str):
        c = str(c).strip().lstrip("#")
        if len(c) == 3:
            c = "".join(ch * 2 for ch in c)
        if len(c) >= 6:
            try:
                return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
            except ValueError:
                pass
        return (255, 255, 255)

    def _lum(r: int, g: int, b: int) -> float:
        def _ch(v: int) -> float:
            s = v / 255.0
            return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

        return 0.2126 * _ch(r) + 0.7152 * _ch(g) + 0.0722 * _ch(b)

    try:
        r1, g1, b1 = _parse(hex_fg)
        r2, g2, b2 = _parse(hex_bg)
        l1 = _lum(r1, g1, b1)
        l2 = _lum(r2, g2, b2)
        lighter = max(l1, l2)
        darker = min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)
    except Exception:
        return 4.5


class RichTextEditor(QWidget):
    """
    A composite widget providing a formatting toolbar and QTextEdit.

    Usage:
        editor = RichTextEditor()
        editor.setHtml("<p>Hello <b>World</b></p>")
        html = editor.toHtml()
        plain = editor.toPlainText()
    """

    # kept for external signal wiring if needed
    formattingChanged = Signal() if hasattr(QWidget, "destroyed") else None  # type: ignore

    def __init__(self, parent=None, settings_manager=None):
        super().__init__(parent)
        if settings_manager is None and parent is not None:
            settings_manager = getattr(parent, "settings_manager", None)
        self.settings_manager = settings_manager
        self._recent_colors: list[str] = []
        self._load_recent_colors()
        self._init_ui()
        self._apply_description_defaults()

    # ── UI ────────────────────────────────────────────────────────────

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # --- Formatting Toolbar ---
        self.toolbar = QToolBar("Formatting", self)
        self.toolbar.setMovable(False)
        self.toolbar.setFloatable(False)
        self.toolbar.setIconSize(QSize(16, 16))
        # allow expansion / overflow handling on narrow width
        self.toolbar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.toolbar.setStyleSheet(self._toolbar_stylesheet())
        # enable extension overflow button (More …) on narrow width
        try:
            # Qt automatically shows extension button when not enough space
            pass
        except Exception:
            pass

        # ---------- Font Family ----------
        self.font_family_combo = QComboBox(self)
        self.fontFamilyCombo = self.font_family_combo  # alias
        self.font_family_combo.setEditable(True)
        self.font_family_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.font_family_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.font_family_combo.setMaxVisibleItems(22)
        self.font_family_combo.setMinimumWidth(108)
        self.font_family_combo.setMaximumWidth(200)
        self.font_family_combo.setToolTip("Font Family")
        try:
            le = self.font_family_combo.lineEdit()
            if le is not None:
                le.setPlaceholderText("Font")
        except Exception:
            pass
        # populate installed families sorted case-insensitive
        try:
            families = sorted(QFontDatabase.families(), key=lambda n: n.lower())  # type: ignore[attr-defined]
        except Exception:
            try:
                families = sorted(QFontDatabase().families(), key=lambda n: n.lower())  # type: ignore
            except Exception:
                families = ["Arial", "Helvetica", "Times New Roman", "Courier New", "Inter"]
        # deduplicate and strip empties
        seen = set()
        uniq = []
        for f in families:
            if f and f not in seen:
                seen.add(f)
                uniq.append(f)
        self.font_family_combo.addItems(uniq)
        self.font_family_combo.setCurrentIndex(-1)
        # keep editable lineEdit placeholder for mixed state
        try:
            if self.font_family_combo.lineEdit() is not None:
                self.font_family_combo.lineEdit().setPlaceholderText("Font")
        except Exception:
            pass
        self.font_family_combo.activated.connect(self._on_font_family_activated)
        # also handle Enter in editable field
        try:
            self.font_family_combo.lineEdit().returnPressed.connect(self._on_font_family_return)
        except Exception:
            pass
        self.toolbar.addWidget(self.font_family_combo)

        # ---------- Font Size ----------
        self.font_size_combo = QComboBox(self)
        self.fontSizeCombo = self.font_size_combo  # alias
        self.font_size_combo.setEditable(True)
        self.font_size_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.font_size_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.font_size_combo.setMinimumWidth(56)
        self.font_size_combo.setMaximumWidth(80)
        self.font_size_combo.setToolTip("Font Size (6–96 pt)")
        for sz in _FONT_SIZE_PRESETS:
            self.font_size_combo.addItem(str(sz), sz)
        self.font_size_combo.setCurrentIndex(-1)
        try:
            if self.font_size_combo.lineEdit() is not None:
                self.font_size_combo.lineEdit().setPlaceholderText("Size")
        except Exception:
            pass
        self.font_size_combo.activated.connect(self._on_font_size_activated)
        try:
            self.font_size_combo.lineEdit().returnPressed.connect(self._on_font_size_return)
        except Exception:
            pass
        # also handle editing finished for custom values
        self.font_size_combo.editTextChanged.connect(self._on_font_size_edit_text_changed)  # live, but cheap
        self.toolbar.addWidget(self.font_size_combo)

        # ---------- Font Color ----------
        self.color_button = QToolButton(self)
        self.colorButton = self.color_button  # alias
        self.color_button.setText("A")
        self.color_button.setToolTip("Font Color — Auto/Theme Text or Custom")
        self.color_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.color_button.setMinimumWidth(36)
        self.color_button.setStyleSheet(
            "QToolButton { padding: 3px 6px; border: 1px solid transparent; border-radius: 6px; font-weight: 700; }"
        )
        self._color_menu = QMenu(self.color_button)
        self._build_color_menu()
        self.color_button.setMenu(self._color_menu)
        self._current_color: QColor | None = None  # None == Auto/Theme
        self._update_color_swatch(None)
        self.toolbar.addWidget(self.color_button)

        self.toolbar.addSeparator()

        # Bold
        self.bold_action = QAction("B", self)
        self.bold_action.setToolTip("Bold (Ctrl+B)")
        self.bold_action.setCheckable(True)
        self.bold_action.setShortcut(QKeySequence("Ctrl+B"))
        self.bold_action.triggered.connect(self._toggle_bold)
        font_bold = QFont()
        font_bold.setBold(True)
        self.bold_action.setFont(font_bold)
        self.toolbar.addAction(self.bold_action)

        # Italic
        self.italic_action = QAction("I", self)
        self.italic_action.setToolTip("Italic (Ctrl+I)")
        self.italic_action.setCheckable(True)
        self.italic_action.setShortcut(QKeySequence("Ctrl+I"))
        self.italic_action.triggered.connect(self._toggle_italic)
        font_italic = QFont()
        font_italic.setItalic(True)
        self.italic_action.setFont(font_italic)
        self.toolbar.addAction(self.italic_action)

        # Underline
        self.underline_action = QAction("U", self)
        self.underline_action.setToolTip("Underline (Ctrl+U)")
        self.underline_action.setCheckable(True)
        self.underline_action.setShortcut(QKeySequence("Ctrl+U"))
        self.underline_action.triggered.connect(self._toggle_underline)
        font_underline = QFont()
        font_underline.setUnderline(True)
        self.underline_action.setFont(font_underline)
        self.toolbar.addAction(self.underline_action)

        self.toolbar.addSeparator()

        # Bullet List
        self.bullet_action = QAction("• List", self)
        self.bullet_action.setToolTip("Bullet List")
        self.bullet_action.setCheckable(True)
        self.bullet_action.triggered.connect(self._toggle_bullet_list)
        self.toolbar.addAction(self.bullet_action)

        # Numbered List
        self.number_action = QAction("1. List", self)
        self.number_action.setToolTip("Numbered List")
        self.number_action.setCheckable(True)
        self.number_action.triggered.connect(self._toggle_numbered_list)
        self.toolbar.addAction(self.number_action)

        self.toolbar.addSeparator()

        # Insert Link
        self.link_action = QAction("Link", self)
        self.link_action.setToolTip("Insert Link (Ctrl+K)")
        self.link_action.setShortcut(QKeySequence("Ctrl+K"))
        self.link_action.triggered.connect(self._insert_link)
        self.toolbar.addAction(self.link_action)

        # Clear Formatting
        self.clear_format_action = QAction("Clear", self)
        self.clearFormatAction = self.clear_format_action  # alias
        self.clear_action = self.clear_format_action  # alias
        self.clear_format_action.setToolTip("Clear Formatting (Ctrl+\\ or Ctrl+Shift+N)")
        self.clear_format_action.setShortcut(QKeySequence("Ctrl+\\"))
        self.clear_format_action.triggered.connect(self._clear_formatting)
        self.toolbar.addAction(self.clear_format_action)
        # second shortcut Ctrl+Shift+N via QShortcut (QAction only holds one)
        try:
            self._clear_shortcut2 = QShortcut(QKeySequence("Ctrl+Shift+N"), self)
            self._clear_shortcut2.activated.connect(self._clear_formatting)
        except Exception:
            self._clear_shortcut2 = None  # type: ignore

        # Paste plain shortcut is handled in keyPressEvent (Ctrl+Shift+V)

        layout.addWidget(self.toolbar)

        # --- Text Editor ---
        self.editor = QTextEdit()
        self.editor.setAcceptRichText(True)
        self.editor.cursorPositionChanged.connect(self._update_toolbar_state)
        # also update on selection change via same signal; ensure textChanged doesn't spam
        try:
            self.editor.currentCharFormatChanged.connect(lambda _fmt: self._update_toolbar_state())
        except Exception:
            pass
        layout.addWidget(self.editor)

        # apply theme-aware editor stylesheet (dark/light readable)
        self._apply_editor_theme()
        self._update_toolbar_state()

    # ── Customer Description Defaults ─────────────────────────────

    def _description_default_values(self):
        """
        Resolve Description Editor defaults from canonical SettingsManager.

        Inline HTML formatting always wins over these defaults.
        Defaults affect:
        - new/unformatted content
        - typing format
        - Auto/Theme text presentation
        """
        app_font = QApplication.font()
        family = app_font.family()
        size = app_font.pointSize() if app_font.pointSize() > 0 else 13
        color_mode = "auto"
        color_hex = ""

        sm = self.settings_manager
        if sm is not None:
            try:
                use_app = bool(sm.get("description_font_use_app_default", True))
            except Exception:
                use_app = True

            if not use_app:
                try:
                    configured_family = str(
                        sm.get("description_font_family", "") or ""
                    ).strip()
                    if configured_family:
                        family = configured_family
                except Exception:
                    pass

                try:
                    size = int(sm.get("description_font_size", size) or size)
                except (TypeError, ValueError):
                    pass

                try:
                    color_mode = str(
                        sm.get("description_font_color_mode", "auto") or "auto"
                    ).lower()
                except Exception:
                    color_mode = "auto"

                try:
                    color_hex = str(
                        sm.get("description_font_color", "") or ""
                    ).strip()
                except Exception:
                    color_hex = ""

        size = max(_FONT_SIZE_MIN, min(_FONT_SIZE_MAX, int(size)))
        return family, size, color_mode, color_hex

    def _apply_description_defaults(self):
        """
        Apply customer defaults non-destructively.

        Important:
        QTextDocument.defaultFont controls inherited/unformatted content.
        Explicit existing HTML spans retain their own family/size/color.
        """
        try:
            family, size, color_mode, color_hex = self._description_default_values()

            default_font = QFont(family)
            default_font.setPointSize(int(size))
            self.editor.document().setDefaultFont(default_font)

            # Set typing format for newly entered text.
            fmt = QTextCharFormat()
            fmt.setFont(default_font)
            fmt.setFontPointSize(float(size))

            if color_mode == "custom":
                color = QColor(color_hex)
                if color.isValid():
                    fmt.setForeground(QBrush(color))
                    self._current_color = color
                    self._update_color_swatch(color)
                else:
                    fmt.clearForeground()
            else:
                fmt.clearForeground()

            # No selection: affects future typing only.
            self.editor.mergeCurrentCharFormat(fmt)

            # Keep toolbar selectors in sync with resolved defaults.
            try:
                idx = self.font_family_combo.findText(family)
                if idx >= 0:
                    self.font_family_combo.blockSignals(True)
                    self.font_family_combo.setCurrentIndex(idx)
                    self.font_family_combo.blockSignals(False)
            except Exception:
                pass

            try:
                self.font_size_combo.blockSignals(True)
                self.font_size_combo.setCurrentText(str(size))
                self.font_size_combo.blockSignals(False)
            except Exception:
                pass

        except Exception:
            logger.exception("Unable to apply Description Editor defaults")

    def refresh_description_defaults(self):
        """Public live-refresh hook used by Settings."""
        self._apply_description_defaults()
        self._apply_editor_theme()
        self._update_toolbar_state()

    # ── Public API ──────────────────────────────────────────────

    def setHtml(self, html: str):
        """Load HTML content. Plain text is auto-handled by QTextEdit."""
        # sanitize unsafe HTML before loading (strip script/style/on* handlers)
        sanitized = self._sanitize_html(html or "")
        if sanitized and not self._looks_like_html(sanitized):
            import html as html_mod

            escaped = html_mod.escape(sanitized)
            sanitized = f"<p>{escaped.replace(chr(10), '</p><p>')}</p>"
        self.editor.setHtml(sanitized or "")
        # Existing explicit HTML formatting remains untouched.
        # Re-establish customer defaults only as the typing/default authority.
        self._apply_description_defaults()

    def toHtml(self) -> str:
        """Returns the current content as HTML."""
        return self.editor.toHtml()

    def toPlainText(self) -> str:
        """Returns the current content as plain text (strips formatting)."""
        return self.editor.toPlainText()

    def setPlaceholderText(self, text: str):
        """Set placeholder text for the editor."""
        self.editor.setPlaceholderText(text)

    def setMaximumHeight(self, maxh: int):  # type: ignore[override]
        """Set maximum height for the editor portion."""
        self.editor.setMaximumHeight(maxh)

    def clear(self):
        """Clear the editor content."""
        self.editor.clear()

    def setReadOnly(self, ro: bool):
        """Set read-only mode."""
        self.editor.setReadOnly(ro)
        self.toolbar.setEnabled(not ro)

    def document(self):
        """Access the underlying QTextDocument."""
        return self.editor.document()

    # ── Stylesheets ─────────────────────────────────────────────

    def _toolbar_stylesheet(self) -> str:
        radius = getattr(DesignTokens, "RADIUS_SM", 6) if DesignTokens else 6
        spacing = getattr(DesignTokens, "SPACING_XS", 4) if DesignTokens else 4
        return f"""
            QToolBar {{
                spacing: 2px;
                padding: 2px;
                border: none;
                background: transparent;
            }}
            QToolButton {{
                padding: 3px 4px;
                border: 1px solid transparent;
                border-radius: {radius}px;
                font-size: 12px;
                min-width: 20px;
            }}
            QToolButton:hover {{
                background: rgba(128, 128, 128, 0.15);
                border-color: rgba(128, 128, 128, 0.25);
            }}
            QToolButton:checked {{
                background: rgba(100, 140, 255, 0.2);
                border-color: rgba(100, 140, 255, 0.4);
            }}
            QToolButton:focus {{
                border-color: rgba(100, 140, 255, 0.55);
            }}
            QComboBox {{
                padding: 2px 6px;
                border: 1px solid rgba(128,128,128,0.25);
                border-radius: {radius}px;
                font-size: 12px;
                min-height: 22px;
            }}
            QComboBox:hover {{
                border-color: rgba(128,128,128,0.4);
            }}
            QComboBox:focus {{
                border-color: rgba(100, 140, 255, 0.55);
            }}
            QComboBox::drop-down {{
                border: none;
                width: 18px;
            }}
        """

    def _apply_editor_theme(self):
        """Apply palette-aware stylesheet so Auto color maps to theme text."""
        try:
            pal = self.palette()
            base = pal.base().color().name()
            text = pal.text().color().name()
            # keep subtle border using DesignTokens if available
            border = getattr(DesignTokens, "LIGHT_BORDER", "#E2E8F0")
            # detect dark via luminance of base
            is_dark = QColor(base).lightness() < 128
            if is_dark and DesignTokens:
                border = getattr(DesignTokens, "DARK_BORDER", "#313244")
            self.editor.setStyleSheet(
                f"QTextEdit {{ background: {base}; color: {text}; border: 1px solid {border}; "
                f"border-radius: 6px; padding: 6px; selection-background-color: rgba(100,140,255,0.35); }}"
            )
        except Exception:
            pass

    # ── Color menu & recent colors ──────────────────────────────

    def _build_color_menu(self):
        self._color_menu.clear()
        auto_act = self._color_menu.addAction("Auto / Theme Text")
        auto_act.setToolTip("Reset to theme default text color")
        auto_act.triggered.connect(lambda: self._on_color_auto())
        self._color_menu.addSeparator()
        custom_act = self._color_menu.addAction("Custom…")
        custom_act.triggered.connect(lambda: self._on_color_custom())
        if self._recent_colors:
            self._color_menu.addSeparator()
            for hex_col in self._recent_colors[:6]:
                act = self._color_menu.addAction(f"  {hex_col}")
                # swatch via icon color square
                try:
                    # set background via stylesheet trick not needed; use text
                    pass
                except Exception:
                    pass
                act.setData(hex_col)
                act.triggered.connect(lambda checked=False, c=hex_col: self._apply_color(QColor(c)))

    def _load_recent_colors(self):
        try:
            from PySide6.QtCore import QSettings

            s = QSettings("TodoBird", "RichTextEditor")
            val = s.value("recentColors", [])
            if isinstance(val, list):
                self._recent_colors = [str(x) for x in val if str(x).startswith("#")][:6]
            elif isinstance(val, str) and val:
                self._recent_colors = [val]
        except Exception:
            self._recent_colors = []

    def _save_recent_colors(self):
        try:
            from PySide6.QtCore import QSettings

            s = QSettings("TodoBird", "RichTextEditor")
            s.setValue("recentColors", self._recent_colors[:6])
        except Exception:
            pass

    def _push_recent_color(self, hex_col: str):
        hex_col = str(hex_col).strip()
        if not hex_col.startswith("#"):
            return
        hex_col = hex_col.upper()
        if hex_col in self._recent_colors:
            self._recent_colors.remove(hex_col)
        self._recent_colors.insert(0, hex_col)
        self._recent_colors = self._recent_colors[:6]
        self._save_recent_colors()
        self._build_color_menu()

    def _update_color_swatch(self, color: QColor | None):
        """Update color button swatch preview; dashed when mixed (None sentinel handled outside)."""
        try:
            if color is None or not color.isValid():
                # Auto — theme text swatch: transparent with border
                self.color_button.setStyleSheet(
                    "QToolButton { padding: 3px 6px; border: 1px solid rgba(128,128,128,0.3); "
                    "border-radius: 6px; font-weight: 700; background: transparent; }"
                )
                self.color_button.setToolTip("Font Color: Auto / Theme Text")
                self._current_color = None
            else:
                hex_col = color.name().upper()
                # contrast warning vs editor background
                try:
                    bg_hex = self.palette().base().color().name()
                    ratio = _contrast_ratio(hex_col, bg_hex)
                    if ratio < 1.5:
                        self.color_button.setToolTip(f"Font Color: {hex_col} — low contrast vs background ({ratio:.2f})")
                        logger.warning("RichTextEditor low contrast color %s on %s ratio %.2f", hex_col, bg_hex, ratio)
                    else:
                        self.color_button.setToolTip(f"Font Color: {hex_col}")
                except Exception:
                    self.color_button.setToolTip(f"Font Color: {hex_col}")
                # swatch: bottom border colored
                self.color_button.setStyleSheet(
                    f"QToolButton {{ padding: 3px 6px; border: 1px solid {hex_col}; "
                    f"border-radius: 6px; font-weight: 700; border-bottom: 3px solid {hex_col}; background: rgba(128,128,128,0.06); }}"
                )
                self._current_color = color
        except Exception:
            pass

    def _set_color_button_mixed(self):
        """Show indeterminate dashed swatch for mixed color selection."""
        try:
            self.color_button.setStyleSheet(
                "QToolButton { padding: 3px 6px; border: 1px dashed rgba(128,128,128,0.6); "
                "border-radius: 6px; font-weight: 700; background: repeating-linear-gradient(45deg, transparent, transparent 3px, rgba(128,128,128,0.08) 3px, rgba(128,128,128,0.08) 6px); }"
            )
            self.color_button.setToolTip("Font Color: Mixed — pick to apply to selection")
            self._current_color = None
        except Exception:
            pass

    # ── Format Actions ──────────────────────────────────────────

    def _toggle_bold(self):
        fmt = QTextCharFormat()
        cursor = self.editor.textCursor()
        current_weight = cursor.charFormat().fontWeight()
        fmt.setFontWeight(QFont.Weight.Normal if current_weight == QFont.Weight.Bold else QFont.Weight.Bold)
        self._merge_format(fmt)

    def _toggle_italic(self):
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self.editor.textCursor().charFormat().fontItalic())
        self._merge_format(fmt)

    def _toggle_underline(self):
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not self.editor.textCursor().charFormat().fontUnderline())
        self._merge_format(fmt)

    def _toggle_bullet_list(self):
        self._toggle_list(QTextListFormat.Style.ListDisc)

    def _toggle_numbered_list(self):
        self._toggle_list(QTextListFormat.Style.ListDecimal)

    def _toggle_list(self, style: QTextListFormat.Style):
        cursor = self.editor.textCursor()
        current_list = cursor.currentList()

        if current_list and current_list.format().style() == style:
            block = cursor.block()
            fmt = block.blockFormat()
            fmt.setIndent(0)
            cursor.setBlockFormat(fmt)
            current_list.remove(block)
        else:
            list_fmt = QTextListFormat()
            list_fmt.setStyle(style)
            list_fmt.setIndent(1)
            cursor.createList(list_fmt)

        self.editor.setTextCursor(cursor)
        self._update_toolbar_state()

    def _insert_link(self):
        cursor = self.editor.textCursor()
        selected_text = cursor.selectedText()

        url, ok = QInputDialog.getText(self, "Insert Link", "URL:", text="https://")
        if not ok or not url.strip():
            return

        link_text = selected_text if selected_text else url
        html_link = f'<a href="{url}">{link_text}</a>'
        cursor.insertHtml(html_link)

    def _merge_format(self, fmt: QTextCharFormat):
        """Legacy merge: if no selection, select WordUnderCursor (for Bold/Italic/Underline)."""
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        cursor.mergeCharFormat(fmt)
        self.editor.mergeCurrentCharFormat(fmt)

    def _apply_char_format(self, fmt: QTextCharFormat):
        """
        Apply char format respecting typing vs selection-only rule:
        - with selection: merge only selection
        - without selection: setCurrentCharFormat for next typed text (no word auto-select)
        """
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.mergeCharFormat(fmt)
            self.editor.setTextCursor(cursor)
            self.editor.mergeCurrentCharFormat(fmt)
        else:
            self.editor.mergeCurrentCharFormat(fmt)

    # ── Font family handlers ────────────────────────────────────

    def _on_font_family_activated(self, index_or_text=None):
        # QComboBox.activated(int) gives index; we need text
        if isinstance(index_or_text, int):
            text = self.font_family_combo.itemText(index_or_text)
        else:
            text = str(index_or_text or self.font_family_combo.currentText()).strip()
        if not text or text.lower() == "mixed":
            return
        fmt = QTextCharFormat()
        # use QFont to avoid deprecated setFontFamily segfault edge
        _f = QFont()
        _f.setFamily(text)
        fmt.setFont(_f)
        # also set family string for Qt compatibility (type: ignore)
        try:
            fmt.setFontFamily(text)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._apply_char_format(fmt)
        # focus back to editor
        self.editor.setFocus()

    def _on_font_family_return(self):
        text = self.font_family_combo.currentText().strip()
        if not text:
            return
        fmt = QTextCharFormat()
        _f = QFont()
        _f.setFamily(text)
        fmt.setFont(_f)
        try:
            fmt.setFontFamily(text)  # type: ignore[attr-defined]
        except Exception:
            pass
        self._apply_char_format(fmt)
        self.editor.setFocus()

    # ── Font size handlers ──────────────────────────────────────

    def _on_font_size_activated(self, index_or_text=None):
        if isinstance(index_or_text, int):
            text = self.font_size_combo.itemText(index_or_text)
        else:
            text = str(index_or_text or self.font_size_combo.currentText()).strip()
        self._apply_font_size_text(text)

    def _on_font_size_return(self):
        text = self.font_size_combo.currentText().strip()
        self._apply_font_size_text(text)

    def _on_font_size_edit_text_changed(self, _text: str):
        # we do not auto-apply on every keystroke; just allow typing
        pass

    def _apply_font_size_text(self, text: str):
        text = str(text).strip().replace("pt", "").strip()
        if not text or text.lower() == "mixed":
            return
        try:
            size = int(float(text))
        except ValueError:
            return
        # clamp 6-96
        size = max(_FONT_SIZE_MIN, min(_FONT_SIZE_MAX, size))
        fmt = QTextCharFormat()
        fmt.setFontPointSize(float(size))
        self._apply_char_format(fmt)
        self.editor.setFocus()

    # ── Color handlers ──────────────────────────────────────────

    def _on_color_auto(self):
        fmt = QTextCharFormat()
        fmt.clearForeground()
        # also ensure brush cleared: use clearForeground is enough, but also set invalid
        self._apply_char_format(fmt)
        self._update_color_swatch(None)
        self.editor.setFocus()

    def _on_color_custom(self):
        initial = self._current_color if self._current_color and self._current_color.isValid() else QColor("#000000")
        # use palette text as fallback initial if Auto
        if initial is None or not initial.isValid():
            try:
                initial = self.palette().text().color()
            except Exception:
                initial = QColor("#3584E4")
        color = QColorDialog.getColor(initial, self, "Choose Font Color")
        if not color.isValid():
            return
        self._apply_color(color)

    def _apply_color(self, color: QColor):
        if not color or not color.isValid():
            return
        fmt = QTextCharFormat()
        fmt.setForeground(QBrush(color))
        self._apply_char_format(fmt)
        self._update_color_swatch(color)
        self._push_recent_color(color.name())
        self._build_color_menu()
        self.editor.setFocus()

    # ── Clear formatting ────────────────────────────────────────

    def _clear_formatting(self):
        cursor = self.editor.textCursor()
        # Build default format from the current Description Editor customer default.
        self._apply_description_defaults()
        default_font = self.editor.document().defaultFont()
        # fallback to app font
        try:
            app_font = QApplication.font()
            if not default_font.family():
                default_font = app_font
        except Exception:
            pass
        fmt = QTextCharFormat()
        # reset family/size to document default (or app default)
        if default_font.family():
            _df = QFont()
            _df.setFamily(default_font.family())
            fmt.setFont(_df)
            try:
                fmt.setFontFamily(default_font.family())  # type: ignore[attr-defined]
            except Exception:
                pass
        if default_font.pointSize() > 0:
            fmt.setFontPointSize(float(default_font.pointSize()))
        else:
            fmt.setFontPointSize(13.0)
        fmt.clearForeground()
        fmt.setFontWeight(QFont.Weight.Normal)
        fmt.setFontItalic(False)
        fmt.setFontUnderline(False)
        # clear other properties
        fmt.setFontStrikeOut(False)
        if cursor.hasSelection():
            cursor.setCharFormat(fmt)
            self.editor.setTextCursor(cursor)
            self.editor.mergeCurrentCharFormat(fmt)
        else:
            # no selection: affect current word + future typing
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            if cursor.hasSelection():
                cursor.setCharFormat(fmt)
                self.editor.setTextCursor(cursor)
            self.editor.mergeCurrentCharFormat(fmt)
        self._update_toolbar_state()

    # ── Toolbar State Sync ──────────────────────────────────────

    def _collect_selection_formats(self):
        """
        Returns sets of (families, sizes, colors_hex) for selection.
        If no selection, returns single-value sets for cursor position.
        """
        cursor = self.editor.textCursor()
        doc = self.editor.document()
        families: set[str] = set()
        sizes: set[int] = set()
        colors: set[str | None] = set()

        def _fmt_to_vals(fmt: QTextCharFormat):
            try:
                fam = fmt.font().family() or ""
            except Exception:
                fam = ""
            # fontPointSize returns 0 if not set → use integer rounded
            try:
                _ps = fmt.fontPointSize()
            except Exception:
                try:
                    _ps = fmt.font().pointSizeF()
                except Exception:
                    _ps = 0
            sz = int(round(_ps)) if _ps and _ps > 0 else 0
            # foreground color: if no brush or style NoBrush → None (Auto)
            brush = fmt.foreground()
            try:
                _no_brush = Qt.BrushStyle.NoBrush  # type: ignore[attr-defined]
            except Exception:
                _no_brush = 0  # type: ignore
            if brush.style() == _no_brush or brush.color() == QColor():
                col = None
            else:
                try:
                    c = brush.color()
                    col = c.name().upper() if c.isValid() else None
                except Exception:
                    col = None
            return fam, sz, col

        if not cursor.hasSelection():
            fmt = cursor.charFormat()
            # fallback to currentCharFormat if charFormat empty (at block start)
            try:
                _ffam = fmt.font().family() if fmt else ""
            except Exception:
                _ffam = ""
            try:
                _fps = fmt.fontPointSize() if fmt else 0
            except Exception:
                _fps = 0
            if not _ffam and (not _fps or _fps == 0):
                try:
                    fmt = self.editor.currentCharFormat()
                except Exception:
                    pass
            fam, sz, col = _fmt_to_vals(fmt)
            if fam:
                families.add(fam)
            # if size 0, try default
            if sz:
                sizes.add(sz)
            else:
                # use document default or current
                try:
                    df = doc.defaultFont().pointSize()
                    if df > 0:
                        sizes.add(int(df))
                except Exception:
                    pass
            colors.add(col)
            return families, sizes, colors

        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        # sample at most 200 chars to avoid O(n) on huge selections, but cover edges
        # collect first, middle, last and stepping
        tmp = QTextCursor(doc)
        # collect unique positions: start, end-1, midpoint, and every ~20 chars if needed
        positions = set()
        positions.add(start)
        if end > start:
            positions.add(end - 1)
            positions.add((start + end) // 2)
            step = max(1, (end - start) // 20)
            for p in range(start, end, step):
                positions.add(p)
        for pos in sorted(positions):
            tmp.setPosition(pos)
            fmt = tmp.charFormat()
            fam, sz, col = _fmt_to_vals(fmt)
            if fam:
                families.add(fam)
            if sz:
                sizes.add(sz)
            colors.add(col)
        # also include charFormat at cursor for completeness
        fmt2 = cursor.charFormat()
        fam2, sz2, col2 = _fmt_to_vals(fmt2)
        if fam2:
            families.add(fam2)
        if sz2:
            sizes.add(sz2)
        colors.add(col2)
        return families, sizes, colors

    def _update_toolbar_state(self):
        """Update toolbar toggle states to reflect cursor position."""
        cursor = self.editor.textCursor()
        char_fmt = cursor.charFormat()
        # fallback to currentCharFormat when charFormat is empty (e.g., at document start)
        try:
            _cfam = char_fmt.font().family() if char_fmt else ""
            _cps = char_fmt.fontPointSize() if char_fmt else 0
        except Exception:
            _cfam = ""
            _cps = 0
        if not _cfam and (not _cps or _cps == 0):
            try:
                char_fmt = self.editor.currentCharFormat()
            except Exception:
                pass

        self.bold_action.blockSignals(True)
        self.bold_action.setChecked(char_fmt.fontWeight() == QFont.Weight.Bold)
        self.bold_action.blockSignals(False)

        self.italic_action.blockSignals(True)
        self.italic_action.setChecked(char_fmt.fontItalic())
        self.italic_action.blockSignals(False)

        self.underline_action.blockSignals(True)
        self.underline_action.setChecked(char_fmt.fontUnderline())
        self.underline_action.blockSignals(False)

        current_list = cursor.currentList()
        self.bullet_action.blockSignals(True)
        self.number_action.blockSignals(True)
        if current_list:
            style = current_list.format().style()
            self.bullet_action.setChecked(style == QTextListFormat.Style.ListDisc)
            self.number_action.setChecked(style == QTextListFormat.Style.ListDecimal)
        else:
            self.bullet_action.setChecked(False)
            self.number_action.setChecked(False)
        self.bullet_action.blockSignals(False)
        self.number_action.blockSignals(False)

        # --- Font family / size / color mixed handling ---
        families, sizes, colors = self._collect_selection_formats()

        # Font Family combo
        self.font_family_combo.blockSignals(True)
        try:
            if len(families) == 1:
                fam = next(iter(families))
                idx = self.font_family_combo.findText(fam)
                if idx >= 0:
                    self.font_family_combo.setCurrentIndex(idx)
                else:
                    # custom family not in list → set text
                    self.font_family_combo.setCurrentText(fam)
                try:
                    le = self.font_family_combo.lineEdit()
                    if le:
                        le.setPlaceholderText("Font")
                except Exception:
                    pass
                self.font_family_combo.setToolTip(f"Font Family: {fam}")
            elif len(families) == 0:
                # no info → blank
                try:
                    if self.font_family_combo.lineEdit():
                        self.font_family_combo.lineEdit().clear()
                        self.font_family_combo.lineEdit().setPlaceholderText("Font")
                except Exception:
                    self.font_family_combo.setCurrentIndex(-1)
                self.font_family_combo.setToolTip("Font Family")
            else:
                # mixed
                try:
                    le = self.font_family_combo.lineEdit()
                    if le:
                        le.clear()
                        le.setPlaceholderText("Mixed")
                    else:
                        self.font_family_combo.setCurrentIndex(-1)
                except Exception:
                    self.font_family_combo.setCurrentIndex(-1)
                self.font_family_combo.setToolTip("Font Family: Mixed — pick to apply to selection")
        finally:
            self.font_family_combo.blockSignals(False)

        # Font Size combo
        self.font_size_combo.blockSignals(True)
        try:
            if len(sizes) == 1:
                sz = next(iter(sizes))
                txt = str(sz)
                idx = self.font_size_combo.findText(txt)
                if idx >= 0:
                    self.font_size_combo.setCurrentIndex(idx)
                else:
                    self.font_size_combo.setCurrentText(txt)
                try:
                    le = self.font_size_combo.lineEdit()
                    if le:
                        le.setPlaceholderText("Size")
                except Exception:
                    pass
                self.font_size_combo.setToolTip(f"Font Size: {sz} pt")
            elif len(sizes) == 0:
                try:
                    if self.font_size_combo.lineEdit():
                        self.font_size_combo.lineEdit().clear()
                        self.font_size_combo.lineEdit().setPlaceholderText("Size")
                except Exception:
                    self.font_size_combo.setCurrentIndex(-1)
                self.font_size_combo.setToolTip("Font Size")
            else:
                try:
                    le = self.font_size_combo.lineEdit()
                    if le:
                        le.clear()
                        le.setPlaceholderText("Mixed")
                    else:
                        self.font_size_combo.setCurrentIndex(-1)
                except Exception:
                    self.font_size_combo.setCurrentIndex(-1)
                self.font_size_combo.setToolTip("Font Size: Mixed — pick to apply to selection")
        finally:
            self.font_size_combo.blockSignals(False)

        # Color swatch
        try:
            if len(colors) == 1:
                col = next(iter(colors))
                if col is None:
                    self._update_color_swatch(None)
                else:
                    self._update_color_swatch(QColor(col))
            elif len(colors) == 0:
                self._update_color_swatch(None)
            else:
                self._set_color_button_mixed()
        except Exception:
            pass

    # ── Key handling ────────────────────────────────────────────

    def keyPressEvent(self, event):  # type: ignore[override]
        # Ctrl+Shift+V → paste plain text (no formatting)
        try:
            if event.modifiers() == (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier) and event.key() == Qt.Key.Key_V:
                clipboard = QApplication.clipboard()
                if clipboard is not None:
                    text = clipboard.text()
                    if text:
                        self.editor.insertPlainText(text)
                        return
            # ensure Ctrl+B/I/U/K/Z/Y/A/C/X/V still handled via QAction shortcuts / editor default
        except Exception:
            pass
        super().keyPressEvent(event)

    # ── Sanitization ────────────────────────────────────────────

    @staticmethod
    def _sanitize_html(html: str) -> str:
        """Strip unsafe tags/attributes: script, style, on* handlers."""
        if not html:
            return html
        # remove script and style blocks (case-insensitive, multiline)
        html = re.sub(r"<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script\s*>", "", html, flags=re.IGNORECASE | re.DOTALL)
        html = re.sub(r"<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style\s*>", "", html, flags=re.IGNORECASE | re.DOTALL)
        # remove on* attributes (onclick, onload etc.) — quoted or unquoted
        html = re.sub(
            r"\s+on\w+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)",
            "",
            html,
            flags=re.IGNORECASE,
        )
        # remove javascript: urls in href/src
        html = re.sub(r"""href\s*=\s*["']\s*javascript:[^"']*["']""", 'href="#"', html, flags=re.IGNORECASE)
        html = re.sub(r"""src\s*=\s*["']\s*javascript:[^"']*["']""", 'src=""', html, flags=re.IGNORECASE)
        return html

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _looks_like_html(text: str) -> bool:
        """Heuristic: does text contain HTML tags?"""
        if not text:
            return False
        stripped = text.strip()
        return (
            stripped.startswith("<!")  # doctype
            or stripped.startswith("<p")
            or stripped.startswith("<h")
            or stripped.startswith("<div")
            or stripped.startswith("<br")
            or stripped.startswith("<ul")
            or stripped.startswith("<ol")
            or stripped.startswith("<font")
            or stripped.startswith("<span")
            or "</" in stripped
        )

    # ── Focus & tab order ───────────────────────────────────────

    def focusInEvent(self, event):  # type: ignore[override]
        super().focusInEvent(event)
        # ensure toolbar combos → editor tab order is logical
        try:
            self.setTabOrder(self.font_family_combo, self.font_size_combo)
            self.setTabOrder(self.font_size_combo, self.color_button)
            self.setTabOrder(self.color_button, self.editor)
        except Exception:
            pass

    def showEvent(self, event):  # type: ignore[override]
        super().showEvent(event)
        self._apply_editor_theme()

    def changeEvent(self, event):  # type: ignore[override]
        # handle palette/theme change for dark/light readability
        try:
            if event.type() == event.Type.PaletteChange:
                self._apply_editor_theme()
        except Exception:
            pass
        super().changeEvent(event)
