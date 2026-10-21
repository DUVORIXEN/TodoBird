import shutil
import logging
from pathlib import Path
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox, QPushButton,
    QTimeEdit, QSpinBox, QSlider, QFrame, QFormLayout, QScrollArea,
    QWidget, QMessageBox, QColorDialog, QPlainTextEdit, QRadioButton, QButtonGroup,
    QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QLineEdit, QFileDialog, QDateEdit,
    QToolButton, QTabWidget, QAbstractItemView, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, QTime, QDate, QTimer, QStringListModel
from PySide6.QtGui import QFontDatabase, QFont, QColor, QIntValidator, QPixmap, QPainter, QIcon
from PySide6.QtWidgets import QApplication

from todo_bird_app.views.base_view import BaseView
from todo_bird_app.gantt.gantt_theme import DEFAULT_GANTT_COLORS, GanttColorProfile
from todo_bird_app.services.platform_service import get_platform_service
from todo_bird_app.services.working_week import WorkingWeekService, WEEKDAY_NAMES
from todo_bird_app.services.language_service import LanguageService
from todo_bird_app.services.region_service import RegionService
from todo_bird_app.services.media_service import MediaService
from todo_bird_app.services.companion_service import CompanionService
from todo_bird_app.widgets.toast_banner import ToastBanner
from todo_bird_app.widgets.reminder_dialog import ReminderCardFrame
from todo_bird_app.services.wbs_customization_service import WBSCustomizationService
from todo_bird_app.widgets.wbs_settings_widget import WBSSettingsWidget
from todo_bird_app.services.typography_service import AREAS, TypographyService
from todo_bird_app.services.appearance_service import (
    ACCENT_SCHEMES,
    AppearanceService,
    THEME_MODES,
    is_system_dark,
    text_color_on,
)
from todo_bird_app.services.background_service import (
    BACKGROUND_MODE_IMAGE,
    BACKGROUND_MODE_SOLID,
    BACKGROUND_MODE_THEME_DEFAULT,
    BACKGROUND_MODE_TRANSPARENT,
    BackgroundService,
)
from todo_bird_app.ui.components.modern_combobox import ModernComboBox
from todo_bird_app.ui.components.modern_button import ModernButton, ButtonStyleDesign, ButtonVariant
from todo_bird_app.widgets.add_world_clock_dialog import AddWorldClockDialog
from todo_bird_app.services.world_clock_service import WorldClockService
from todo_bird_app.widgets.digital_clock_widget import DigitalClockWidget


logger = logging.getLogger(__name__)


class GreetingEditDialog(QDialog):
    def __init__(self, parent=None, cycle_day=1, greeting_data=None, db_manager=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Greeting — Day {cycle_day}")
        self.setMinimumWidth(440)
        self.cycle_day = cycle_day
        self.db_manager = db_manager
        self.data = dict(greeting_data or {})
        self.image_path = self.data.get("image_path", "") or ""
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.register(self, role="greeting_edit_dialog")
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.title_edit = QLineEdit(self.data.get("title", f"Day {self.cycle_day} Focus"))
        form.addRow("Greeting Title:", self.title_edit)

        self.message_edit = QPlainTextEdit(self.data.get("message", "Execute with clarity."))
        self.message_edit.setMaximumHeight(80)
        form.addRow("Greeting Message / Quote:", self.message_edit)

        img_row = QHBoxLayout()
        self.preview_lbl = QLabel()
        self.preview_lbl.setFixedSize(56, 56)
        self.preview_lbl.setStyleSheet("border: 1px dashed #64748B; border-radius: 8px; background: rgba(0,0,0,0.04);")
        self.preview_lbl.setAlignment(Qt.AlignCenter)

        self.btn_choose_img = QPushButton(" Choose Image")
        self.btn_remove_img = QPushButton("Remove")

        def update_preview():
            if self.image_path:
                pm = MediaService.load_pixmap(self.image_path, max_width=56, max_height=56, use_thumbnail=True)
                if pm and not pm.isNull():
                    self.preview_lbl.setPixmap(pm)
                    self.btn_remove_img.setEnabled(True)
                    return
            self.preview_lbl.setText("No Img")
            self.btn_remove_img.setEnabled(False)

        def on_choose():
            f_path, _ = QFileDialog.getOpenFileName(self, "Choose Greeting Image", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp *.svg)")
            if f_path:
                meta = MediaService.import_media(f_path, category="greetings", db_manager=self.db_manager)
                if meta:
                    self.image_path = meta["relative_path"]
                    update_preview()

        def on_remove():
            self.image_path = ""
            update_preview()

        self.btn_choose_img.clicked.connect(on_choose)
        self.btn_remove_img.clicked.connect(on_remove)
        img_row.addWidget(self.preview_lbl)
        img_row.addWidget(self.btn_choose_img)
        img_row.addWidget(self.btn_remove_img)
        img_row.addStretch()
        form.addRow("Greeting Image:", img_row)
        update_preview()

        self.enabled_check = QCheckBox("Enable this day's greeting")
        self.enabled_check.setChecked(bool(self.data.get("enabled", 1)))
        form.addRow("", self.enabled_check)

        layout.addLayout(form)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("Save Greeting")
        btn_save.setObjectName("PrimaryButton")
        btn_save.clicked.connect(self.accept)
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

    def get_greeting_data(self):
        return {
            "cycle_day": self.cycle_day,
            "title": self.title_edit.text().strip(),
            "message": self.message_edit.toPlainText().strip(),
            "image_path": self.image_path,
            "enabled": self.enabled_check.isChecked(),
        }


class GreetingPreviewDialog(QDialog):
    def __init__(self, parent=None, title="Good Morning!", message="", image_path="", companion_avatar_pm=None):
        super().__init__(parent)
        self.setWindowTitle("Todo Bird Greeting Preview")
        self.setMinimumWidth(400)
        # Theme-aware: chrome and text colors come from the global theme QSS;
        # the dialog used to be dark-locked and washed out in light mode.
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.register(self, role="greeting_preview_dialog")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header_row = QHBoxLayout()
        if companion_avatar_pm and not companion_avatar_pm.isNull():
            avatar_lbl = QLabel()
            avatar_lbl.setPixmap(companion_avatar_pm.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            header_row.addWidget(avatar_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: palette(highlight);")
        header_row.addWidget(title_lbl, 1)
        layout.addLayout(header_row)

        if image_path:
            pm = MediaService.load_pixmap(image_path, max_width=320, max_height=180)
            if pm and not pm.isNull():
                img_lbl = QLabel()
                img_lbl.setAlignment(Qt.AlignCenter)
                img_lbl.setPixmap(pm)
                img_lbl.setStyleSheet("border-radius: 8px; border: 1px solid palette(midlight);")
                layout.addWidget(img_lbl)

        msg_lbl = QLabel(f'“{message}”')
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet("font-size: 14px; font-style: italic; padding: 6px 0;")
        layout.addWidget(msg_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Start My Day")
        btn_close.setObjectName("PrimaryButton")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

COLOR_KEYS = [
    ("planned_color", "Planned Task Bar"),
    ("actual_color", "Actual Task Bar"),
    ("completed_early_color", "Completed Before Time"),
    ("completed_ontime_color", "Completed On Time"),
    ("slight_delay_color", "Slight Delay"),
    ("moderate_delay_color", "Moderate Delay"),
    ("severe_delay_color", "Severe Delay"),
    ("cancelled_color", "Cancelled Task"),
    ("paused_color", "Paused Task"),
    ("milestone_color", "Milestone Marker"),
    ("critical_color", "Critical Task Highlight"),
    ("selected_color", "Selected Task Highlight"),
    ("hovered_color", "Hovered Task Highlight"),
]

class SettingsView(BaseView):
    """
    Preferences & Settings View — Comprehensive controls for appearance, Gantt customization,
    calendar working week, delay rules, appreciation, desktop integration, and backups.
    """
    def __init__(self, db_manager, settings_manager, parent=None):
        super().__init__(db_manager, settings_manager, title="Preferences & Settings", subtitle="Theme, Voice, Gantt Customization, Working Week, and System Integration", parent=parent)
        self.working_week_service = WorkingWeekService(settings_manager)
        self.color_buttons = {}
        self.custom_colors = dict(settings_manager.get("gantt_custom_colors", DEFAULT_GANTT_COLORS))
        self.day_checkboxes = {}
        self._reminder_resize_listener = None
        self._appearance_apply_pending = False
        self._init_ui()

    def _populate_dashboard_settings(self, layout: QVBoxLayout):
        card = QFrame()
        card.setObjectName("SettingsSubPanel")
        vbox = QVBoxLayout(card)
        
        lbl = QLabel(" World Clocks (Good Morning Strip)")
        lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        vbox.addWidget(lbl)
        
        desc = QLabel("Select up to 5 world clocks to display in the Dashboard header. Drag to reorder.")
        desc.setObjectName("SettingsHelperText")
        vbox.addWidget(desc)

        self.clocks_list_widget = QListWidget()
        self.clocks_list_widget.setMinimumHeight(150)
        self.clocks_list_widget.setDragDropMode(QListWidget.InternalMove)
        self.clocks_list_widget.setDefaultDropAction(Qt.MoveAction)
        vbox.addWidget(self.clocks_list_widget)
        
        btn_row = QHBoxLayout()
        btn_add = QPushButton("Add World Clock")
        btn_del = QPushButton("Remove Selected")
        btn_up = QPushButton("⬆ Move Up")
        btn_down = QPushButton("⬇ Move Down")
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addWidget(btn_up)
        btn_row.addWidget(btn_down)
        btn_row.addStretch()
        vbox.addLayout(btn_row)
        
        layout.addWidget(card)
        layout.addStretch()
        
        def refresh_clocks():
            self.clocks_list_widget.clear()
            # Use WorldClockService canonical authority
            clocks = WorldClockService.load_clocks(self.settings_manager)
            for clock in clocks:
                list_item = QListWidgetItem(f"{clock.city} ({clock.timezone})")
                list_item.setData(Qt.UserRole, clock.id)
                self.clocks_list_widget.addItem(list_item)
                    
        def add_clock():
            clocks = WorldClockService.load_clocks(self.settings_manager)
            if len(clocks) >= 5:
                QMessageBox.warning(self, "Limit Reached", "You can only add up to 5 world clocks.")
                return
            is_dark = str(self.settings_manager.get("theme", "dark")).lower() == "dark"
            accent = str(self.settings_manager.get("accent_color", "#3584E4"))
            dlg = AddWorldClockDialog(
                is_dark=is_dark,
                accent_color=accent,
                parent=self,
                region_country=str(self.settings_manager.get("region_country", "") or ""),
            )
            def on_created(item):
                clocks = WorldClockService.load_clocks(self.settings_manager)
                if item.id not in [c.id for c in clocks]:
                    clocks.append(item)
                    WorldClockService.save_clocks(self.settings_manager, clocks)
                    refresh_clocks()
                    # Notify dashboard and other views of world clock changes
                    try:
                        from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
                        _GLOBAL_EVENT_BUS.world_clocks_changed.emit()
                    except Exception:
                        pass
            dlg.clock_created.connect(on_created)
            dlg.exec()
            
        def del_clock():
            sel = self.clocks_list_widget.currentItem()
            if not sel: return
            cid_to_del = sel.data(Qt.UserRole)
            clocks = WorldClockService.load_clocks(self.settings_manager)
            new_clocks = [c for c in clocks if c.id != cid_to_del]
            WorldClockService.save_clocks(self.settings_manager, new_clocks)
            refresh_clocks()
            # Notify dashboard and other views of world clock changes
            try:
                from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
                _GLOBAL_EVENT_BUS.world_clocks_changed.emit()
            except Exception:
                pass
            
        def move_up():
            row = self.clocks_list_widget.currentRow()
            if row <= 0:
                return
            clocks = WorldClockService.load_clocks(self.settings_manager)
            clocks[row], clocks[row-1] = clocks[row-1], clocks[row]
            WorldClockService.save_clocks(self.settings_manager, clocks)
            refresh_clocks()
            self.clocks_list_widget.setCurrentRow(row-1)
            try:
                from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
                _GLOBAL_EVENT_BUS.world_clocks_changed.emit()
            except Exception:
                pass
            
        def move_down():
            row = self.clocks_list_widget.currentRow()
            clocks = WorldClockService.load_clocks(self.settings_manager)
            if row < 0 or row >= len(clocks) - 1:
                return
            clocks[row], clocks[row+1] = clocks[row+1], clocks[row]
            WorldClockService.save_clocks(self.settings_manager, clocks)
            refresh_clocks()
            self.clocks_list_widget.setCurrentRow(row+1)
            try:
                from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
                _GLOBAL_EVENT_BUS.world_clocks_changed.emit()
            except Exception:
                pass
            
        btn_add.clicked.connect(add_clock)
        btn_del.clicked.connect(del_clock)
        btn_up.clicked.connect(move_up)
        btn_down.clicked.connect(move_down)
        
        # Also handle drag-drop reorder
        self.clocks_list_widget.model().rowsMoved.connect(lambda: self._on_clocks_reordered())
        
        refresh_clocks()

    def _on_clocks_reordered(self):
        """Handle drag-drop reorder of world clocks."""
        clocks = WorldClockService.load_clocks(self.settings_manager)
        new_order = []
        for i in range(self.clocks_list_widget.count()):
            item = self.clocks_list_widget.item(i)
            cid = item.data(Qt.UserRole)
            for clock in clocks:
                if clock.id == cid:
                    new_order.append(clock)
                    break
        if len(new_order) == len(clocks):
            WorldClockService.save_clocks(self.settings_manager, new_order)
            try:
                from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
                _GLOBAL_EVENT_BUS.world_clocks_changed.emit()
            except Exception:
                pass

    def cleanup(self):
        listener = getattr(self, "_reminder_resize_listener", None)
        if listener is not None:
            try:
                from todo_bird_app.services.window_registry import WindowRegistry
                WindowRegistry.unregister_reminder_resize_listener(listener)
            except Exception:
                pass
            self._reminder_resize_listener = None
        super().cleanup()

    def _make_settings_page(self, tabs: QTabWidget, title: str) -> QVBoxLayout:
        scroll = QScrollArea()
        scroll.setObjectName("SettingsPageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: 0; }")
        scroll.viewport().setAutoFillBackground(False)

        container = QWidget()
        container.setObjectName("SettingsPage")
        container.setStyleSheet("background: transparent;")

        page_layout = QVBoxLayout(container)
        page_layout.setContentsMargins(12, 4, 12, 16)
        page_layout.setSpacing(14)

        scroll.setWidget(container)
        tabs.addTab(scroll, title)
        return page_layout

    def _optimize_combo(self, combo: QComboBox, minimum_chars: int = 18):
        combo.setMaxVisibleItems(min(combo.maxVisibleItems() or 18, 22))
        combo.setMinimumContentsLength(minimum_chars)
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        view = combo.view()
        if hasattr(view, "setUniformItemSizes"):
            view.setUniformItemSizes(True)

    @staticmethod
    def _create_tab_icon(emoji: str) -> QIcon:
        pm = QPixmap(24, 24)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        f = p.font()
        f.setPointSize(13)
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignCenter, emoji)
        p.end()
        return QIcon(pm)

    def _build_executive_header(self) -> QWidget:
        tokens = self._appearance_tokens()
        accent = tokens["ACCENT"]
        header_widget = QWidget()
        header_widget.setObjectName("SettingsHeaderWidget")
        h_layout = QHBoxLayout(header_widget)
        h_layout.setContentsMargins(4, 0, 4, 12)
        h_layout.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)

        icon_badge = QLabel()
        from todo_bird_app.services.icon_service import IconService as _IS_badge
        icon_badge.setPixmap(_IS_badge.get_pixmap("settings", 20, "#9AA6BD"))
        icon_badge.setStyleSheet(
            f"background-color: {accent};"
            f"color: {tokens['TEXT_ON_ACCENT']};"
            "border-radius: 9px; font-size: 16px;"
        )
        icon_badge.setFixedSize(34, 34)
        icon_badge.setAlignment(Qt.AlignCenter)
        title_row.addWidget(icon_badge)

        view_title = QLabel("Settings & Preferences")
        view_title.setObjectName("SettingsViewTitle")
        view_title.setStyleSheet("font-size: 20px; font-weight: 800;")
        title_row.addWidget(view_title)

        status_pill = QLabel("● Real-time Sync")
        status_pill.setStyleSheet(
            "background: rgba(16, 185, 129, 0.15);"
            "color: #10B981;"
            "border: 1px solid rgba(16, 185, 129, 0.35);"
            "border-radius: 11px;"
            "padding: 3px 10px;"
            "font-size: 11px;"
            "font-weight: 700;"
        )
        title_row.addWidget(status_pill)
        title_row.addStretch()
        title_box.addLayout(title_row)

        subtitle_lbl = QLabel(
            "Workspace styling, typography, notification timing, companion greetings, and local authority"
        )
        subtitle_lbl.setObjectName("SettingsHelperText")
        title_box.addWidget(subtitle_lbl)
        h_layout.addLayout(title_box, 1)

        search_box = QHBoxLayout()
        search_box.setSpacing(8)

        self.settings_search_input = QLineEdit()
        self.settings_search_input.setObjectName("SettingsSearchInput")
        self.settings_search_input.setPlaceholderText("Search settings…")
        self.settings_search_input.setClearButtonEnabled(True)
        self.settings_search_input.setMinimumWidth(220)
        self.settings_search_input.setMaximumWidth(320)
        self.settings_search_input.setFixedHeight(36)
        self.settings_search_input.setToolTip("Filter cards across every tab by keyword")
        self.settings_search_input.textChanged.connect(self._on_settings_search_changed)
        search_box.addWidget(self.settings_search_input)

        quick_backup = QPushButton("Quick Backup")
        quick_backup.setCursor(Qt.PointingHandCursor)
        quick_backup.setStyleSheet(
            "QPushButton {"
            f"background-color: {tokens['ACCENT_SUBTLE']};"
            f"border: 1px solid {tokens['ACCENT']};"
            f"color: {tokens['ACCENT']};"
            "border-radius: 9px;"
            "padding: 6px 14px;"
            "font-weight: 600;"
            "min-height: 22px;"
            "}"
            "QPushButton:hover {"
            f"background-color: {tokens['ACCENT']};"
            f"color: {tokens['TEXT_ON_ACCENT']};"
            "}"
        )
        quick_backup.clicked.connect(self.create_backup)
        search_box.addWidget(quick_backup)
        h_layout.addLayout(search_box)
        return header_widget

    def _on_settings_search_changed(self, query: str):
        query = query.strip().lower()
        matched_any = False
        first_match_tab_idx = None

        for tab_idx in range(self.settings_tabs.count()):
            tab_page = self.settings_tabs.widget(tab_idx)
            tab_has_match = False

            for card in tab_page.findChildren(QFrame, "CardWidget"):
                card_text = " ".join(lbl.text() for lbl in card.findChildren(QLabel)).lower()
                for btn in card.findChildren(QPushButton):
                    card_text += " " + btn.text().lower()
                for cb in card.findChildren(QCheckBox):
                    card_text += " " + cb.text().lower()

                # Non-destructive highlight via dynamic property — the old
                # inline setStyleSheet wiped the themed card surface.
                is_match = bool(query) and (query in card_text)
                card.setProperty("settingsHighlighted", is_match)
                card_style = card.style()
                card_style.unpolish(card)
                card_style.polish(card)

                if is_match:
                    tab_has_match = True
                    matched_any = True

            if tab_has_match and first_match_tab_idx is None:
                first_match_tab_idx = tab_idx

        if matched_any and first_match_tab_idx is not None:
            self.settings_tabs.setCurrentIndex(first_match_tab_idx)

    def _appearance_tokens(self):
        from todo_bird_app.services.appearance_service import semantic_tokens_for
        mode = str(self.settings_manager.get("theme", "dark") or "dark").lower()
        if mode == "system":
            is_dark = is_system_dark()
        else:
            is_dark = mode not in ("light", "warm_paper")
        accent = str(self.settings_manager.get("accent_color", "#3584E4") or "#3584E4")
        return semantic_tokens_for(is_dark, accent)

    def _sync_theme_accent_buttons(self):
        tokens = self._appearance_tokens()
        cur_theme = str(self.theme_combo.currentData() or "dark").lower()
        for code, btn in getattr(self, "_theme_buttons", {}).items():
            is_active = (str(btn.property("engineMode") or code) == cur_theme)
            # Each preset button previews its own palette, so it carries its
            # own surface color instead of a theme-derived one (a dark glass
            # blob used to sit on light-mode cards).
            preview_bg = str(btn.property("previewBg") or tokens["SURFACE_1"])
            btn.setStyleSheet(
                f"QPushButton {{"
                f"border: {2.5 if is_active else 1}px solid {tokens['ACCENT'] if is_active else tokens['BORDER_NORMAL']};"
                f"border-radius: 9px;"
                f"background-color: {preview_bg};"
                f"}}"
            )

        cur_accent = str(self.accent_combo.currentData() or "").lower()
        for code, btn in getattr(self, "_accent_buttons", {}).items():
            is_active = (code == cur_accent)
            btn.setStyleSheet(
                f"QPushButton {{"
                f"background-color: {ACCENT_SCHEMES.get(code, ('', '#3584E4'))[1]};"
                f"border: {2.5 if is_active else 1.5}px solid {tokens['TEXT_PRIMARY'] if is_active else tokens['BORDER_STRONG']};"
                f"border-radius: 15px;"
                f"}}"
            )

        self._restyle_live_preview(tokens)

    def _restyle_live_preview(self, tokens=None):
        """Keep the sample card button on the live accent across theme changes."""
        btn = getattr(self, "_preview_sample_btn", None)
        if btn is None:
            return
        if tokens is None:
            tokens = self._appearance_tokens()
        btn.setStyleSheet(
            "QPushButton {"
            f"background-color: {tokens['ACCENT']}; color: {tokens['TEXT_ON_ACCENT']};"
            "border: none; border-radius: 6px; padding: 4px 12px; font-weight: 600;"
            "min-height: 22px;"
            "}"
        )

    def on_appearance_changed(self, appearance=None):
        """BaseView hook: theme/accent changed app-wide; re-sync chrome."""
        self._sync_theme_accent_buttons()

    def retranslate_ui(self):
        """Live-retranslate settings chrome (tab labels + language card)."""
        svc = LanguageService.instance()
        tab_titles = [
            "Appearance", "Typography", "Reminders", "Companion",
            "Planning", "System", "Dashboard",
        ]
        for idx, title in enumerate(tab_titles):
            if idx < self.settings_tabs.count():
                self.settings_tabs.setTabText(idx, svc.t(title))

        if hasattr(self, "ui_language_combo") and hasattr(self, "_language_codes"):
            current = svc.current_language()
            if current in self._language_codes:
                idx = self._language_codes.index(current)
                if self.ui_language_combo.currentIndex() != idx:
                    self.ui_language_combo.blockSignals(True)
                    self.ui_language_combo.setCurrentIndex(idx)
                    self.ui_language_combo.blockSignals(False)

        if hasattr(self, "region_defaults_button"):
            self.region_defaults_button.setText(svc.t("Apply Region Defaults"))
            self.region_defaults_button.setToolTip(
                svc.t(
                    "Region defaults set the working week and 12/24-hour "
                    "clock for the selected country."
                )
            )

    def _build_live_ui_preview(self) -> QWidget:
        tokens = self._appearance_tokens()
        container = QFrame()
        container.setObjectName("LiveThemePreviewCard")
        l = QVBoxLayout(container)
        l.setSpacing(8)
        l.setContentsMargins(12, 12, 12, 12)

        header_row = QHBoxLayout()
        icon_title = QLabel(" <b>Live Theme & Typography Preview</b>")
        icon_title.setStyleSheet("font-size: 13px; font-weight: 700;")
        header_row.addWidget(icon_title)
        header_row.addStretch()
        l.addLayout(header_row)

        # Inner sample card simulating an executive task card. Surfaces come
        # from the tokenized theme rules for these objectNames.
        self._preview_sample_card = QFrame()
        self._preview_sample_card.setObjectName("PreviewSampleCard")
        sc_layout = QVBoxLayout(self._preview_sample_card)
        sc_layout.setSpacing(6)
        sc_layout.setContentsMargins(10, 10, 10, 10)

        self._preview_sample_heading = QLabel("Quarterly Systems Engineering Review")
        self._preview_sample_heading.setStyleSheet("font-size: 13px; font-weight: 800;")
        sc_layout.addWidget(self._preview_sample_heading)

        self._preview_sample_sub = QLabel("WBS 1.2.4 — Execution critical path with CPM schedule parity.")
        self._preview_sample_sub.setStyleSheet("font-size: 11px;")
        self._preview_sample_sub.setObjectName("SettingsHelperText")
        sc_layout.addWidget(self._preview_sample_sub)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(8)

        self._preview_badge_priority = QLabel(" HIGH PRIORITY ")
        self._preview_badge_priority.setStyleSheet(
            "background: rgba(239, 68, 68, 0.16); color: #EF4444; border: 1px solid rgba(239, 68, 68, 0.55); "
            "border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: bold;"
        )
        meta_row.addWidget(self._preview_badge_priority)

        self._preview_badge_status = QLabel(" IN PROGRESS ")
        self._preview_badge_status.setStyleSheet(
            "background: rgba(59, 130, 246, 0.16); color: #3B82F6; border: 1px solid rgba(59, 130, 246, 0.55); "
            "border-radius: 4px; padding: 2px 6px; font-size: 10px; font-weight: bold;"
        )
        meta_row.addWidget(self._preview_badge_status)

        self._preview_sample_btn = QPushButton("Mark Completed")
        self._preview_sample_btn.setMinimumHeight(26)
        self._preview_sample_btn.setStyleSheet(
            "QPushButton {"
            f"background-color: {tokens['ACCENT']}; color: {tokens['TEXT_ON_ACCENT']};"
            "border: none; border-radius: 6px; padding: 4px 12px; font-weight: 600;"
            "min-height: 22px;"
            "}"
        )
        meta_row.addStretch()
        meta_row.addWidget(self._preview_sample_btn)

        sc_layout.addLayout(meta_row)
        l.addWidget(self._preview_sample_card)

        return container

    def _apply_settings_window_polish(self):
        # Color-bearing chrome (tabs, cards, sub-panels) is owned by the
        # tokenized theme stylesheets; a widget-level sheet here would
        # override the active theme and dark-lock the light mode.
        for combo in self.findChildren(QComboBox):
            self._optimize_combo(combo)

        for spin in self.findChildren(QSpinBox):
            spin.setKeyboardTracking(False)

        for form in self.findChildren(QFormLayout):
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
            form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
            form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
            form.setHorizontalSpacing(20)
            form.setVerticalSpacing(12)

        # Sizing floors per control species. The old blanket 240px floor on
        # every combo AND spinbox turned numeric fields into monsters, while
        # the 380px cap elided long font names.
        for combo in self.findChildren(QComboBox):
            combo.setMinimumWidth(200)
            combo.setMaximumWidth(420)

        for spin in self.findChildren(QSpinBox):
            spin.setMinimumWidth(110)

        for date_edit in self.findChildren(QTimeEdit) + self.findChildren(QDateEdit):
            date_edit.setMinimumWidth(130)

        for table in self.findChildren(QTableWidget):
            table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
            table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            table.setShowGrid(False)
            table.setAlternatingRowColors(True)
            table.verticalHeader().setVisible(False)
            table.verticalHeader().setDefaultSectionSize(34)


    def _init_ui(self):
        self.setUpdatesEnabled(False)

        # Executive header: title, live search across every tab, quick backup.
        self.main_layout.addWidget(self._build_executive_header())

        self.settings_tabs = QTabWidget()
        self.settings_tabs.setObjectName("SettingsTabs")
        self.settings_tabs.setDocumentMode(True)
        self.settings_tabs.setMovable(False)
        self.settings_tabs.setUsesScrollButtons(True)
        self.settings_tabs.setElideMode(Qt.ElideRight)

        appearance_layout = self._make_settings_page(
            self.settings_tabs,
            "Appearance",
        )
        typography_layout = self._make_settings_page(
            self.settings_tabs,
            "Typography",
        )
        reminders_layout = self._make_settings_page(
            self.settings_tabs,
            "Reminders",
        )
        companion_layout = self._make_settings_page(
            self.settings_tabs,
            "Companion",
        )
        planning_layout = self._make_settings_page(
            self.settings_tabs,
            "Planning",
        )
        system_layout = self._make_settings_page(
            self.settings_tabs,
            "System",
        )
        dashboard_layout = self._make_settings_page(
            self.settings_tabs,
            "Dashboard",
        )
        self._populate_dashboard_settings(dashboard_layout)
        self._settings_page_layouts = (
            appearance_layout,
            typography_layout,
            reminders_layout,
            companion_layout,
            planning_layout,
            system_layout,
            dashboard_layout,
        )

        # Text-only tab pills: rasterized emoji icons render as tofu or
        # monochrome glyphs depending on the platform emoji font, and were
        # the least consistent element on the tab bar.

        layout = appearance_layout

        # 1. Main Appearance & Theme Card
        theme_card = QFrame()
        theme_card.setObjectName("CardWidget")
        t_layout = QFormLayout(theme_card)
        t_title = QLabel(" Appearance & Application Theme")
        t_title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(t_title, delta_pt=4, weight="bold")
        t_layout.addRow(t_title)

        t_sub = QLabel("Personalize application theme, accent scheme, button physics, and UI density.")
        t_sub.setObjectName("SettingsHelperText")
        t_sub.setStyleSheet("margin-bottom: 6px;")
        t_layout.addRow(t_sub)

        # Quick Theme Presets
        theme_cards_row = QHBoxLayout()
        theme_cards_row.setSpacing(8)
        theme_cards_row.setContentsMargins(0, 4, 0, 8)

        theme_presets = [
            ("dark", "Dark", "moon", "#1E1E2E", "#CDD6F4"),
            ("light", "Light", "sun", "#FFFFFF", "#1E293B"),
            ("cyberpunk", "Cyberpunk", "target", "#0D0221", "#00F0FF"),
            ("nord", "Nord", "star", "#2E3440", "#ECEFF4"),
            ("system", "System", "settings", "#181825", "#F8FAFC"),
        ]
        # Preset -> theme-engine mode. The engine has no "cyberpunk" mode;
        # its nearest surface (OLED midnight + cyan accents) is "oled".
        # Clicks looked dead because findData("cyberpunk") returned -1.
        PRESET_ENGINE_MODES = {
            "dark": "dark",
            "light": "light",
            "cyberpunk": "oled",
            "nord": "nord",
            "system": "system",
        }
        self._theme_buttons = {}
        for code, name, icon_str, bg_col, text_col in theme_presets:
            btn = QPushButton()
            btn.setMinimumSize(124, 40)
            btn.setProperty("previewBg", bg_col)
            btn.setProperty("engineMode", PRESET_ENGINE_MODES.get(code, code))
            btn.setCursor(Qt.PointingHandCursor)
            bl = QHBoxLayout(btn)
            bl.setContentsMargins(10, 4, 10, 4)
            bl.setSpacing(8)
            i_lbl = QLabel()
            from todo_bird_app.services.icon_service import IconService as _IS
            if _IS.has_icon(icon_str):
                i_lbl.setPixmap(_IS.get_pixmap(icon_str, 15, text_col))
            else:
                i_lbl.setText(icon_str)
                i_lbl.setStyleSheet("font-size: 15px;")
            bl.addWidget(i_lbl)
            t_lbl = QLabel(name)
            t_lbl.setStyleSheet(f"font-weight: 700; font-size: 12px; color: {text_col};")
            bl.addWidget(t_lbl)
            bl.addStretch()
            # Label colors are deliberately paired with each card's own
            # preview background (e.g. dark text on the white Light pill).
            # The app-wide text sanitizer judges against the theme direction
            # instead, and would repaint them invisible on the pill.
            for lbl in (i_lbl, t_lbl):
                lbl.setProperty("todoBirdAllowFixedTextColor", True)

            def make_theme_clk(c=code):
                engine_mode = PRESET_ENGINE_MODES.get(c, c)

                def _clk():
                    idx = self.theme_combo.findData(engine_mode)
                    if idx >= 0:
                        self.theme_combo.setCurrentIndex(idx)
                return _clk

            btn.clicked.connect(make_theme_clk(code))
            self._theme_buttons[code] = btn
            theme_cards_row.addWidget(btn)

        t_layout.addRow("Theme Presets", theme_cards_row)

        self.theme_combo = ModernComboBox()
        for key, label in AppearanceService.known_theme_items():
            self.theme_combo.addItem(label, key)
        current_theme = str(
            self.settings_manager.get("theme", "dark")
            or "dark"
        ).lower().strip()
        idx = self.theme_combo.findData(current_theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        else:
            self.theme_combo.setCurrentIndex(0)
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        t_layout.addRow("Application Theme Mode", self.theme_combo)

        # Quick Accent Swatches — codes/colors must come straight from
        # ACCENT_SCHEMES so clicks match the combo's itemData exactly.
        accent_swatches_row = QHBoxLayout()
        accent_swatches_row.setSpacing(10)
        accent_swatches_row.setContentsMargins(0, 4, 0, 8)
        accents = [
            ("ubuntu_orange", "Ubuntu Orange"),
            ("professional_blue", "Pro Blue"),
            ("emerald", "Emerald"),
            ("indigo", "Purple"),
            ("rose", "Crimson"),
            ("amber", "Amber"),
            ("graphite", "Slate"),
        ]
        self._accent_buttons = {}
        for code, label in accents:
            hex_color = ACCENT_SCHEMES.get(code, ("", "#3584E4"))[1]
            btn = QPushButton()
            btn.setFixedSize(30, 30)
            btn.setToolTip(f"{label} ({hex_color})")
            btn.setCursor(Qt.PointingHandCursor)

            def make_accent_clk(c=code):
                def _clk():
                    idx = self.accent_combo.findData(c)
                    if idx >= 0:
                        self.accent_combo.setCurrentIndex(idx)
                return _clk

            btn.clicked.connect(make_accent_clk(code))
            self._accent_buttons[code] = btn
            accent_swatches_row.addWidget(btn)

        accent_swatches_row.addStretch()
        t_layout.addRow("Accent Swatches", accent_swatches_row)

        self.accent_combo = ModernComboBox()
        for key, label in AppearanceService.known_accent_items():
            self.accent_combo.addItem(label, key)
        current_accent = str(
            self.settings_manager.get("accent_scheme", "")
            or ""
        ).lower()
        if current_accent not in ACCENT_SCHEMES:
            current_color = str(
                self.settings_manager.get(
                    "accent_color",
                    "#E95420",
                )
                or "#E95420"
            ).upper()
            for key, (_label, color) in ACCENT_SCHEMES.items():
                if color.upper() == current_color:
                    current_accent = key
                    break
        accent_idx = self.accent_combo.findData(current_accent)
        if accent_idx >= 0:
            self.accent_combo.setCurrentIndex(accent_idx)
        self.accent_combo.currentTextChanged.connect(self.on_accent_changed)
        t_layout.addRow("Accent / Color Scheme", self.accent_combo)

        self.btn_design_combo = ModernComboBox()
        btn_modes = [
            ("3D Raised / Glass", "3d_raised"),
            ("Flat Modern", "flat"),
            ("Executive Soft 3D", "executive_soft"),
            ("Neumorphic 3D", "neumorphic"),
            ("Glow Outline", "glow"),
        ]
        for b_lbl, b_val in btn_modes:
            self.btn_design_combo.addItem(b_lbl, b_val)
        curr_b_style = str(self.settings_manager.get("button_design_mode", "3d_raised"))
        b_idx = self.btn_design_combo.findData(curr_b_style)
        if b_idx >= 0:
            self.btn_design_combo.setCurrentIndex(b_idx)

        def on_btn_design_changed(idx):
            val = self.btn_design_combo.itemData(idx)
            if val:
                self.settings_manager.set("button_design_mode", str(val))
                app = self.window()
                if hasattr(app, "theme_controller") and app.theme_controller:
                    app.theme_controller.apply_theme(
                        button_style=str(val),
                    )
                else:
                    try:
                        mode = ButtonStyleDesign(str(val))
                        ModernButton.set_global_design_mode(mode)
                    except Exception:
                        pass

        self.btn_design_combo.currentIndexChanged.connect(on_btn_design_changed)
        t_layout.addRow("Button Style", self.btn_design_combo)

        self.density_combo = ModernComboBox()
        for label, value in [
            ("Compact", "compact"),
            ("Balanced", "balanced"),
            ("Spacious", "spacious"),
        ]:
            self.density_combo.addItem(label, value)
        cur_density = str(
            self.settings_manager.get("ui_density", "balanced")
            or "balanced"
        ).lower()
        d_idx = self.density_combo.findData(cur_density)
        if d_idx >= 0:
            self.density_combo.setCurrentIndex(d_idx)

        def on_density_changed(idx):
            val = str(
                self.density_combo.itemData(idx)
                or "balanced"
            )
            self.settings_manager.set("ui_density", val)
            app = self.window()
            if hasattr(app, "theme_controller") and app.theme_controller:
                app.theme_controller.apply_theme(density=val)

        self.density_combo.currentIndexChanged.connect(on_density_changed)
        t_layout.addRow("Density", self.density_combo)

        self.experience_combo = ModernComboBox()
        self.experience_combo.addItems([
            "Professional (Compact & Focused)",
            "Balanced (Standard Todo Bird)",
            "Personal (Vibrant & Expressive)"
        ])
        curr_exp = str(self.settings_manager.get("visual_experience_mode", "balanced")).lower()
        if "prof" in curr_exp:
            self.experience_combo.setCurrentIndex(0)
        elif "pers" in curr_exp:
            self.experience_combo.setCurrentIndex(2)
        else:
            self.experience_combo.setCurrentIndex(1)

        def on_experience_changed(text):
            if "prof" in text.lower():
                val = "professional"
            elif "pers" in text.lower():
                val = "personal"
            else:
                val = "balanced"
            self.settings_manager.set("visual_experience_mode", val)
            try:
                from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
                _GLOBAL_EVENT_BUS.experience_mode_changed.emit(val)
            except Exception:
                pass

        self.experience_combo.currentTextChanged.connect(on_experience_changed)
        t_layout.addRow("Experience & Visual Style", self.experience_combo)

        # Live Theme & Typography Preview Tile
        self.preview_card = self._build_live_ui_preview()
        t_layout.addRow(self.preview_card)

        # -------------------------------------------------
        # Phase 1F.6.1 — Navigation Workspace Personalization
        # -------------------------------------------------
        nav_heading = QLabel(
            "<b> Navigation & Workspace Dock</b>"
        )
        t_layout.addRow(nav_heading)

        nav_help = QLabel(
            "Choose where Todo Bird navigation lives and how it feels. "
            "Changes apply immediately and are remembered."
        )
        nav_help.setWordWrap(True)
        nav_help.setObjectName("SettingsHelperText")
        t_layout.addRow(nav_help)

        self.navigation_position_combo = QComboBox()
        self.navigation_position_combo.addItem(
            "Left Sidebar",
            "left",
        )
        self.navigation_position_combo.addItem(
            "Right Sidebar",
            "right",
        )
        self.navigation_position_combo.addItem(
            "Top Navigation Bar",
            "top",
        )
        self.navigation_position_combo.addItem(
            "Bottom Navigation Dock",
            "bottom",
        )

        nav_position = str(
            self.settings_manager.get(
                "navigation_position",
                "left",
            )
            or "left"
        )
        idx = self.navigation_position_combo.findData(
            nav_position
        )
        if idx >= 0:
            self.navigation_position_combo.setCurrentIndex(idx)

        self.navigation_position_combo.setToolTip(
            "Move Todo Bird navigation to the left, right, top or bottom."
        )
        t_layout.addRow(
            "Navigation Position",
            self.navigation_position_combo,
        )

        self.navigation_style_combo = QComboBox()
        self.navigation_style_combo.addItem(
            "Expanded — Icon + Label + Badge",
            "expanded",
        )
        self.navigation_style_combo.addItem(
            "Compact Rail — Icons Only",
            "rail",
        )
        self.navigation_style_combo.addItem(
            "Slim — Compact Icon + Label",
            "slim",
        )
        self.navigation_style_combo.addItem(
            "Tiles — Spacious Navigation Cards",
            "tiles",
        )
        self.navigation_style_combo.addItem(
            "Glass Dock — Modern Floating Feel",
            "glass",
        )
        self.navigation_style_combo.addItem(
            "Minimal — Quiet & Distraction-Free",
            "minimal",
        )

        nav_style = str(
            self.settings_manager.get(
                "navigation_style",
                "expanded",
            )
            or "expanded"
        )
        idx = self.navigation_style_combo.findData(
            nav_style
        )
        if idx >= 0:
            self.navigation_style_combo.setCurrentIndex(idx)

        self.navigation_style_combo.setToolTip(
            "Choose the visual density and personality of navigation."
        )
        t_layout.addRow(
            "Navigation Style",
            self.navigation_style_combo,
        )

        self.navigation_alignment_combo = QComboBox()
        self.navigation_alignment_combo.addItem(
            "Left",
            "left",
        )
        self.navigation_alignment_combo.addItem(
            "Center",
            "center",
        )
        self.navigation_alignment_combo.addItem(
            "Right",
            "right",
        )

        nav_alignment = str(
            self.settings_manager.get(
                "navigation_alignment",
                "left",
            )
            or "left"
        )
        idx = self.navigation_alignment_combo.findData(
            nav_alignment
        )
        if idx >= 0:
            self.navigation_alignment_combo.setCurrentIndex(idx)

        self.navigation_alignment_combo.setToolTip(
            "For top/bottom docks, place navigation at the left, center or right."
        )
        t_layout.addRow(
            "Top / Bottom Alignment",
            self.navigation_alignment_combo,
        )

        nav_reset_button = QPushButton(
            "Reset Navigation to Todo Bird Default"
        )
        nav_reset_button.setObjectName(
            "SecondaryButton"
        )
        t_layout.addRow(
            "Navigation Reset",
            nav_reset_button,
        )

        def _apply_navigation_settings():
            position = str(
                self.navigation_position_combo.currentData()
                or "left"
            )
            style = str(
                self.navigation_style_combo.currentData()
                or "expanded"
            )
            alignment = str(
                self.navigation_alignment_combo.currentData()
                or "left"
            )

            self.settings_manager.set(
                "navigation_position",
                position,
            )
            self.settings_manager.set(
                "navigation_style",
                style,
            )
            self.settings_manager.set(
                "navigation_alignment",
                alignment,
            )

            app_window = self.window()

            if hasattr(
                app_window,
                "apply_navigation_preferences",
            ):
                app_window.apply_navigation_preferences(
                    position,
                    style,
                    alignment,
                )

        self.navigation_position_combo.currentIndexChanged.connect(
            lambda _index:
            _apply_navigation_settings()
        )
        self.navigation_style_combo.currentIndexChanged.connect(
            lambda _index:
            _apply_navigation_settings()
        )
        self.navigation_alignment_combo.currentIndexChanged.connect(
            lambda _index:
            _apply_navigation_settings()
        )

        def _reset_navigation():
            controls = (
                (
                    self.navigation_position_combo,
                    "left",
                ),
                (
                    self.navigation_style_combo,
                    "expanded",
                ),
                (
                    self.navigation_alignment_combo,
                    "left",
                ),
            )

            for combo, value in controls:
                idx = combo.findData(value)
                combo.blockSignals(True)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                combo.blockSignals(False)

            app_window = self.window()
            if hasattr(app_window, "sidebar") and app_window.sidebar:
                app_window.sidebar.reset_navigation_order()

            _apply_navigation_settings()

        nav_reset_button.clicked.connect(
            _reset_navigation
        )

        # -------------------------------------------------
        # Application-wide typography — housed on the Typography tab where
        # users look for it (it used to be appended to the Appearance card).
        # -------------------------------------------------
        typography_card = QFrame()
        typography_card.setObjectName("CardWidget")
        typo_form = QFormLayout(typography_card)
        typo_card_title = QLabel(" Application Typography")
        TypographyService.set_relative_font_role(typo_card_title, delta_pt=4, weight="bold")
        typo_form.addRow(typo_card_title)
        typo_card_sub = QLabel("Font family, base size, weight, and Description editor defaults.")
        typo_card_sub.setObjectName("SettingsHelperText")
        typo_form.addRow(typo_card_sub)
        typography_layout.addWidget(typography_card)

        self.font_family_combo = QComboBox()
        self.font_family_combo.setEditable(False)
        self.font_family_combo.setMaxVisibleItems(22)

        installed_fonts = sorted(
            QFontDatabase.families(),
            key=lambda name: name.lower(),
        )
        self._font_family_model = QStringListModel(
            installed_fonts,
            self,
        )

        self.font_family_combo.setModel(self._font_family_model)

        current_font = str(
            self.settings_manager.get(
                "ui_font_family",
                QApplication.font().family(),
            )
        )

        font_idx = self.font_family_combo.findText(
            current_font
        )
        if font_idx >= 0:
            self.font_family_combo.setCurrentIndex(
                font_idx
            )

        self.font_family_combo.setToolTip(
            "All font families installed on this computer. "
            "The selected family is used across Todo Bird."
        )
        typo_form.addRow(
            "Application Font",
            self.font_family_combo,
        )

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 20)
        self.font_size_spin.setSingleStep(1)
        self.font_size_spin.setKeyboardTracking(True)
        self.font_size_spin.setSuffix(" pt")
        self.font_size_spin.setValue(
            int(
                self.settings_manager.get(
                    "ui_font_size",
                    10,
                )
            )
        )
        self.font_size_spin.setToolTip(
            "Base application font size. "
            "Some specialized headings keep their own relative emphasis."
        )
        typo_form.addRow(
            "Base Font Size",
            self.font_size_spin,
        )

        self.font_weight_combo = QComboBox()
        self.font_weight_combo.addItem(
            "Normal",
            "normal",
        )
        self.font_weight_combo.addItem(
            "Medium",
            "medium",
        )
        self.font_weight_combo.addItem(
            "Semi Bold",
            "semibold",
        )

        current_weight = str(
            self.settings_manager.get(
                "ui_font_weight",
                "normal",
            )
        )
        weight_idx = (
            self.font_weight_combo.findData(
                current_weight
            )
        )
        if weight_idx >= 0:
            self.font_weight_combo.setCurrentIndex(
                weight_idx
            )

        typo_form.addRow(
            "Default Font Weight",
            self.font_weight_combo,
        )

        self.font_preview = QLabel(
            "Todo Bird Preview — "
            "Project • Task • Gantt • 23% • Pin"
        )
        self.font_preview.setMinimumHeight(38)
        self.font_preview.setStyleSheet(
            """
            padding: 8px 10px;
            border: 1px solid palette(midlight);
            border-radius: 7px;
            """
        )
        typo_form.addRow(
            "Font Preview",
            self.font_preview,
        )

        # -------------------------------------------------
        # Description Editor customer defaults
        # -------------------------------------------------
        desc_defaults_box = QFrame()
        desc_defaults_box.setObjectName("SettingsSubPanel")
        desc_defaults_layout = QFormLayout(desc_defaults_box)

        desc_defaults_title = QLabel(" Description Editor Defaults")
        desc_defaults_title.setStyleSheet(
            "color: inherit; font-weight: 700;"
        )
        TypographyService.set_relative_font_role(desc_defaults_title, delta_pt=3, weight="bold")
        desc_defaults_layout.addRow(desc_defaults_title)

        desc_help = QLabel(
            "Sets the default style for new or unformatted Description text. "
            "Existing inline formatting is preserved."
        )
        desc_help.setWordWrap(True)
        desc_help.setObjectName("SettingsHelperText")
        desc_defaults_layout.addRow(desc_help)

        self.desc_use_app_default = QCheckBox(
            "Use Todo Bird application font as Description default"
        )
        self.desc_use_app_default.setChecked(
            bool(
                self.settings_manager.get(
                    "description_font_use_app_default",
                    True,
                )
            )
        )
        desc_defaults_layout.addRow(
            "Default Source",
            self.desc_use_app_default,
        )

        self.desc_font_family_combo = QComboBox()
        self.desc_font_family_combo.setEditable(False)
        self.desc_font_family_combo.setMaxVisibleItems(22)
        self.desc_font_family_combo.setModel(self._font_family_model)

        desc_family = str(
            self.settings_manager.get(
                "description_font_family",
                current_font,
            )
            or current_font
        )
        idx = self.desc_font_family_combo.findText(desc_family)
        if idx < 0:
            idx = self.desc_font_family_combo.findText(current_font)
        if idx >= 0:
            self.desc_font_family_combo.setCurrentIndex(idx)

        self.desc_font_family_combo.setToolTip(
            "Default family for new/unformatted Description text."
        )
        desc_defaults_layout.addRow(
            "Description Font",
            self.desc_font_family_combo,
        )

        self.desc_font_size_spin = QSpinBox()
        self.desc_font_size_spin.setRange(6, 96)
        self.desc_font_size_spin.setSingleStep(1)
        self.desc_font_size_spin.setSuffix(" pt")
        try:
            desc_size = int(
                self.settings_manager.get(
                    "description_font_size",
                    13,
                )
                or 13
            )
        except (TypeError, ValueError):
            desc_size = 13
        self.desc_font_size_spin.setValue(
            max(6, min(96, desc_size))
        )
        desc_defaults_layout.addRow(
            "Description Font Size",
            self.desc_font_size_spin,
        )

        desc_color_widget = QWidget()
        desc_color_layout = QHBoxLayout(desc_color_widget)
        desc_color_layout.setContentsMargins(0, 0, 0, 0)
        desc_color_layout.setSpacing(8)

        self.desc_color_mode_combo = QComboBox()
        self.desc_color_mode_combo.addItem(
            "Auto / Theme Text",
            "auto",
        )
        self.desc_color_mode_combo.addItem(
            "Custom Color",
            "custom",
        )

        current_desc_color_mode = str(
            self.settings_manager.get(
                "description_font_color_mode",
                "auto",
            )
            or "auto"
        ).lower()

        mode_idx = self.desc_color_mode_combo.findData(
            current_desc_color_mode
        )
        if mode_idx >= 0:
            self.desc_color_mode_combo.setCurrentIndex(mode_idx)

        self.desc_color_button = QPushButton("Choose Color…")
        self.desc_color_button.setObjectName("SecondaryButton")

        self.desc_color_swatch = QLabel()
        self.desc_color_swatch.setFixedSize(30, 22)

        def _update_desc_color_swatch():
            value = str(
                self.settings_manager.get(
                    "description_font_color",
                    "#0F172A",
                )
                or "#0F172A"
            )
            color = QColor(value)
            if not color.isValid():
                color = QColor("#0F172A")
            self.desc_color_swatch.setStyleSheet(
                "border-radius: 5px; "
                "border: 1px solid rgba(148,163,184,120); "
                f"background-color: {color.name()};"
            )
            is_custom = (
                self.desc_color_mode_combo.currentData()
                == "custom"
            )
            self.desc_color_button.setEnabled(is_custom)
            self.desc_color_swatch.setVisible(is_custom)

        def _notify_description_editors():
            app = QApplication.instance()
            if app is None:
                return
            try:
                from todo_bird_app.widgets.rich_text_editor import RichTextEditor
                for widget in app.allWidgets():
                    if isinstance(widget, RichTextEditor):
                        widget.refresh_description_defaults()
            except Exception:
                pass

        def _save_desc_defaults():
            use_app = self.desc_use_app_default.isChecked()

            self.settings_manager.set(
                "description_font_use_app_default",
                use_app,
            )
            self.settings_manager.set(
                "description_font_family",
                self.desc_font_family_combo.currentText(),
            )
            self.settings_manager.set(
                "description_font_size",
                int(self.desc_font_size_spin.value()),
            )
            self.settings_manager.set(
                "description_font_color_mode",
                str(
                    self.desc_color_mode_combo.currentData()
                    or "auto"
                ),
            )

            self.desc_font_family_combo.setEnabled(not use_app)
            self.desc_font_size_spin.setEnabled(not use_app)
            self.desc_color_mode_combo.setEnabled(not use_app)

            _update_desc_color_swatch()
            _notify_description_editors()
            _update_desc_preview()

        def _choose_desc_color():
            current = str(
                self.settings_manager.get(
                    "description_font_color",
                    "#0F172A",
                )
                or "#0F172A"
            )
            initial = QColor(current)
            if not initial.isValid():
                initial = QColor("#0F172A")

            dlg = QColorDialog(initial, self.window())
            dlg.setWindowTitle(
                "Choose Description Default Text Color"
            )
            dlg.setOption(
                QColorDialog.ShowAlphaChannel,
                False,
            )
            dlg.setOption(
                QColorDialog.DontUseNativeDialog,
                True,
            )

            if dlg.exec() == QColorDialog.Accepted:
                color = dlg.selectedColor()
                if color.isValid():
                    self.settings_manager.set(
                        "description_font_color",
                        color.name(),
                    )
                    self.settings_manager.set(
                        "description_font_color_mode",
                        "custom",
                    )
                    custom_idx = self.desc_color_mode_combo.findData(
                        "custom"
                    )
                    if custom_idx >= 0:
                        self.desc_color_mode_combo.blockSignals(True)
                        self.desc_color_mode_combo.setCurrentIndex(
                            custom_idx
                        )
                        self.desc_color_mode_combo.blockSignals(False)

                    _update_desc_color_swatch()
                    _notify_description_editors()
                    _update_desc_preview()

        self.desc_color_button.clicked.connect(
            _choose_desc_color
        )

        desc_color_layout.addWidget(
            self.desc_color_mode_combo,
            1,
        )
        desc_color_layout.addWidget(
            self.desc_color_swatch,
        )
        desc_color_layout.addWidget(
            self.desc_color_button,
        )
        desc_defaults_layout.addRow(
            "Default Text Color",
            desc_color_widget,
        )

        self.desc_preview = QLabel(
            "Description preview — customer-defined default style"
        )
        self.desc_preview.setMinimumHeight(42)
        self.desc_preview.setWordWrap(True)

        def _update_desc_preview():
            use_app = self.desc_use_app_default.isChecked()

            if use_app:
                family = self.font_family_combo.currentText()
                size = self.font_size_spin.value()
                color_mode = "auto"
                color_hex = ""
            else:
                family = self.desc_font_family_combo.currentText()
                size = self.desc_font_size_spin.value()
                color_mode = str(
                    self.desc_color_mode_combo.currentData()
                    or "auto"
                )
                color_hex = str(
                    self.settings_manager.get(
                        "description_font_color",
                        "#0F172A",
                    )
                    or "#0F172A"
                )

            font = QFont(family)
            font.setPointSize(int(size))
            self.desc_preview.setFont(font)

            color_css = (
                f"color: {color_hex};"
                if color_mode == "custom"
                else "color: inherit;"
            )

            self.desc_preview.setStyleSheet(
                "padding: 8px 10px; "
                "border: 1px solid rgba(148,163,184,80); "
                "border-radius: 7px; "
                + color_css
            )

            self.desc_preview.setText(
                f"Description Preview — {family} — {size} pt"
            )

        self.desc_use_app_default.toggled.connect(
            lambda _checked: _save_desc_defaults()
        )
        self.desc_font_family_combo.currentTextChanged.connect(
            lambda _text: _save_desc_defaults()
        )
        self.desc_font_size_spin.valueChanged.connect(
            lambda _value: _save_desc_defaults()
        )
        self.desc_color_mode_combo.currentIndexChanged.connect(
            lambda _index: _save_desc_defaults()
        )

        reset_desc_button = QPushButton(
            "Reset Description Defaults"
        )
        reset_desc_button.setObjectName("SecondaryButton")

        def _reset_desc_defaults():
            self.settings_manager.set(
                "description_font_use_app_default",
                True,
            )
            self.settings_manager.set(
                "description_font_family",
                QApplication.font().family(),
            )
            app_size = QApplication.font().pointSize()
            self.settings_manager.set(
                "description_font_size",
                app_size if app_size > 0 else 13,
            )
            self.settings_manager.set(
                "description_font_color_mode",
                "auto",
            )

            self.desc_use_app_default.blockSignals(True)
            self.desc_use_app_default.setChecked(True)
            self.desc_use_app_default.blockSignals(False)

            app_family = QApplication.font().family()
            idx = self.desc_font_family_combo.findText(app_family)
            if idx >= 0:
                self.desc_font_family_combo.blockSignals(True)
                self.desc_font_family_combo.setCurrentIndex(idx)
                self.desc_font_family_combo.blockSignals(False)

            app_size = QApplication.font().pointSize()
            self.desc_font_size_spin.blockSignals(True)
            self.desc_font_size_spin.setValue(
                app_size if app_size > 0 else 13
            )
            self.desc_font_size_spin.blockSignals(False)

            auto_idx = self.desc_color_mode_combo.findData("auto")
            if auto_idx >= 0:
                self.desc_color_mode_combo.blockSignals(True)
                self.desc_color_mode_combo.setCurrentIndex(auto_idx)
                self.desc_color_mode_combo.blockSignals(False)

            _save_desc_defaults()

        reset_desc_button.clicked.connect(
            _reset_desc_defaults
        )
        desc_defaults_layout.addRow(
            "Reset",
            reset_desc_button,
        )

        use_app = self.desc_use_app_default.isChecked()
        self.desc_font_family_combo.setEnabled(not use_app)
        self.desc_font_size_spin.setEnabled(not use_app)
        self.desc_color_mode_combo.setEnabled(not use_app)

        _update_desc_color_swatch()
        _update_desc_preview()

        typo_form.addRow(desc_defaults_box)

        # -------------------------------------------------
        # Pinned Priority appearance
        # -------------------------------------------------
        self.pinned_style_combo = QComboBox()
        self.pinned_style_combo.addItem(
            "Auto — Follow App Theme",
            "auto",
        )
        self.pinned_style_combo.addItem(
            "Light Cards",
            "light",
        )
        self.pinned_style_combo.addItem(
            "Dark Cards",
            "dark",
        )
        self.pinned_style_combo.addItem(
            "Glass / Translucent",
            "glass",
        )
        self.pinned_style_combo.addItem(
            "High Contrast",
            "high_contrast",
        )

        current_pin_style = str(
            self.settings_manager.get(
                "pinned_card_style",
                "auto",
            )
        )

        pin_style_idx = (
            self.pinned_style_combo.findData(
                current_pin_style
            )
        )
        if pin_style_idx >= 0:
            self.pinned_style_combo.setCurrentIndex(
                pin_style_idx
            )

        self.pinned_style_combo.setToolTip(
            "Controls only the Pinned Priorities cards. "
            "Auto follows Todo Bird Light/Dark mode."
        )
        t_layout.addRow(
            "Pinned Card Appearance",
            self.pinned_style_combo,
        )

        # -------------------------------------------------
        # Canonical Background controls
        # -------------------------------------------------
        t_layout.addRow(QLabel("<b>Background</b>"))
        self._background_form = t_layout
        self._loading_background_controls = False

        self.bg_apply_to_combo = ModernComboBox()
        self.bg_apply_to_combo.addItem("Entire App", "global")
        self.bg_apply_to_combo.addItem("Current View / Window", "view")
        self.bg_apply_to_combo.currentIndexChanged.connect(
            self.on_bg_apply_target_changed
        )
        t_layout.addRow("Apply Background To", self.bg_apply_to_combo)

        self.bg_current_view_label = QLabel("")
        self.bg_current_view_label.setStyleSheet("color: inherit;")
        t_layout.addRow("Customizing", self.bg_current_view_label)

        self.bg_mode_combo = ModernComboBox()
        self.bg_mode_combo.addItem("Theme Default", BACKGROUND_MODE_THEME_DEFAULT)
        self.bg_mode_combo.addItem("Solid Color", BACKGROUND_MODE_SOLID)
        self.bg_mode_combo.addItem("Image", BACKGROUND_MODE_IMAGE)
        self.bg_mode_combo.addItem("Transparent", BACKGROUND_MODE_TRANSPARENT)
        self.bg_mode_combo.currentIndexChanged.connect(self.on_bg_mode_changed)
        t_layout.addRow("Background Mode", self.bg_mode_combo)

        self.bg_color_combo = ModernComboBox()
        for _key, label, color in BackgroundService.color_preset_items():
            self.bg_color_combo.addItem(f"{label} ({color})", color)
        self.bg_color_combo.addItem("Custom Color...", "__custom__")
        self.bg_color_combo.currentIndexChanged.connect(self.on_bg_color_changed)
        t_layout.addRow("Background Color", self.bg_color_combo)

        self.bg_image_row_widget = QWidget()
        bg_img_row = QHBoxLayout(self.bg_image_row_widget)
        bg_img_row.setContentsMargins(0, 0, 0, 0)
        bg_img_row.setSpacing(8)
        self.bg_preview_label = QLabel()
        self.bg_preview_label.setFixedSize(64, 40)
        self.bg_preview_label.setStyleSheet(
            "border: 1px dashed #64748B; border-radius: 6px; "
            "background: rgba(0,0,0,0.04);"
        )
        self.bg_preview_label.setAlignment(Qt.AlignCenter)
        self.current_bg_path = ""

        self.btn_choose_bg = QPushButton("Choose Image")
        self.btn_remove_bg = QPushButton("Remove")
        self.btn_choose_bg.clicked.connect(self.on_choose_bg_image)
        self.btn_remove_bg.clicked.connect(self.on_remove_bg_image)

        bg_img_row.addWidget(self.bg_preview_label)
        bg_img_row.addWidget(self.btn_choose_bg)
        bg_img_row.addWidget(self.btn_remove_bg)
        bg_img_row.addStretch()
        t_layout.addRow("Image", self.bg_image_row_widget)

        self.bg_fit_combo = ModernComboBox()
        for label, value in [
            ("Fill", "fill"),
            ("Fit", "fit"),
            ("Stretch", "stretch"),
            ("Center", "center"),
            ("Tile", "tile"),
        ]:
            self.bg_fit_combo.addItem(label, value)
        self.bg_fit_combo.currentIndexChanged.connect(self.on_bg_fit_changed)
        t_layout.addRow("Fit Mode", self.bg_fit_combo)

        self.bg_opacity_row_widget = QWidget()
        bg_op_row = QHBoxLayout(self.bg_opacity_row_widget)
        bg_op_row.setContentsMargins(0, 0, 0, 0)
        bg_op_row.setSpacing(8)
        self.bg_opacity_slider = QSlider(Qt.Horizontal)
        self.bg_opacity_slider.setRange(0, 100)
        self.bg_opacity_label = QLabel("100%")
        self.bg_opacity_slider.valueChanged.connect(self.on_bg_opacity_changed)
        bg_op_row.addWidget(self.bg_opacity_slider)
        bg_op_row.addWidget(self.bg_opacity_label)
        t_layout.addRow("Opacity", self.bg_opacity_row_widget)

        self.bg_overlay_combo = ModernComboBox()
        self.bg_overlay_combo.addItem("Auto (Follows Theme)", "auto")
        self.bg_overlay_combo.addItem("Dark Translucent", "dark_translucent")
        self.bg_overlay_combo.addItem("Light Frosted", "light_frosted")
        self.bg_overlay_combo.currentIndexChanged.connect(self.on_bg_overlay_changed)
        t_layout.addRow("Image Overlay", self.bg_overlay_combo)

        bg_reset_row_widget = QWidget()
        bg_reset_row = QHBoxLayout(bg_reset_row_widget)
        bg_reset_row.setContentsMargins(0, 0, 0, 0)
        bg_reset_row.setSpacing(8)
        self.btn_reset_bg_view = QPushButton("Reset This View to Global Background")
        self.btn_reset_all_bg = QPushButton("Reset All Backgrounds")
        self.btn_reset_bg_view.clicked.connect(self.on_reset_current_view_background)
        self.btn_reset_all_bg.clicked.connect(self.on_reset_all_backgrounds)
        bg_reset_row.addWidget(self.btn_reset_bg_view)
        bg_reset_row.addWidget(self.btn_reset_all_bg)
        bg_reset_row.addStretch()
        t_layout.addRow("Reset", bg_reset_row_widget)

        self._load_background_controls()

        # Connect only after initial values are loaded.
        self.font_family_combo.currentTextChanged.connect(
            self.on_font_family_changed
        )
        self.font_size_spin.valueChanged.connect(
            self.on_font_size_changed
        )
        self.font_weight_combo.currentIndexChanged.connect(
            self.on_font_weight_changed
        )
        self.pinned_style_combo.currentIndexChanged.connect(
            self.on_pinned_style_changed
        )

        layout.addWidget(theme_card)

        # 1b. Per-View Typography Overrides Card (Batch 3.7)
        layout = typography_layout
        typo_card = QFrame()
        typo_card.setObjectName("CardWidget")
        typo_layout = QFormLayout(typo_card)
        typo_title = QLabel(" Per-View Typography Customization")
        typo_title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(typo_title, delta_pt=4, weight="bold")
        typo_layout.addRow(typo_title)

        self.area_typo_widgets = {}

        for area_key, area_title in AREAS:
            if area_key in ("reminder", "pinned_tasks"):
                continue
            area_box = QVBoxLayout()
            area_box.setSpacing(6)

            ctrl_row = QHBoxLayout()
            cb_override = QCheckBox("Override")
            is_over = bool(
                self.settings_manager.get(f"font_override_{area_key}", False)
                or self.settings_manager.get(f"{area_key}_font_override", False)
            )
            cb_override.setChecked(is_over)

            fam_combo = QComboBox()
            fam_combo.setModel(self._font_family_model)
            cur_fam = str(
                self.settings_manager.get(f"font_family_{area_key}")
                or self.settings_manager.get(f"{area_key}_font_family")
                or current_font
            )
            f_idx = fam_combo.findText(cur_fam)
            if f_idx >= 0:
                fam_combo.setCurrentIndex(f_idx)
            fam_combo.setEnabled(is_over)

            sz_spin = QSpinBox()
            sz_spin.setRange(8, 28)
            sz_spin.setSuffix(" pt")
            cur_sz = int(
                self.settings_manager.get(f"font_size_{area_key}")
                or self.settings_manager.get(f"{area_key}_font_size")
                or 10
            )
            sz_spin.setValue(cur_sz)
            sz_spin.setEnabled(is_over)

            wt_combo = QComboBox()
            wt_combo.addItems(["Normal", "Medium", "SemiBold", "Bold"])
            cur_wt = str(
                self.settings_manager.get(f"font_weight_{area_key}")
                or self.settings_manager.get(f"{area_key}_font_weight")
                or "Normal"
            ).capitalize()
            w_idx = wt_combo.findText(cur_wt)
            if w_idx >= 0:
                wt_combo.setCurrentIndex(w_idx)
            wt_combo.setEnabled(is_over)

            ctrl_row.addWidget(cb_override)
            ctrl_row.addWidget(fam_combo, 2)
            ctrl_row.addWidget(sz_spin, 1)
            ctrl_row.addWidget(wt_combo, 1)

            # Live Preview label using real resolved area font
            preview_lbl = QLabel("The quick brown fox — Todo Bird Preview")
            preview_lbl.setStyleSheet("color: #3584E4; padding: 4px 8px; background: rgba(53, 132, 228, 0.08); border-radius: 4px;")

            def update_preview(k=area_key, pl=preview_lbl):
                p_font = TypographyService.get_font_for_area(k, self.settings_manager)
                pl.setFont(p_font)
                c_color = TypographyService.get_font_color_for_area(k, self.settings_manager)
                if c_color:
                    pl.setStyleSheet(f"color: {c_color}; padding: 4px 8px; background: rgba(53, 132, 228, 0.08); border-radius: 4px;")
                else:
                    pl.setStyleSheet("color: #3584E4; padding: 4px 8px; background: rgba(53, 132, 228, 0.08); border-radius: 4px;")

            update_preview()

            def make_typo_handlers(k=area_key, cb=cb_override, fc=fam_combo, sz=sz_spin, wt=wt_combo, pl=preview_lbl):
                def on_toggle(checked):
                    fc.setEnabled(checked)
                    sz.setEnabled(checked)
                    wt.setEnabled(checked)
                    self.settings_manager.set(f"font_override_{k}", checked)
                    update_preview(k, pl)
                    TypographyService.notify_typography_changed()
                def on_fam_changed(txt):
                    self.settings_manager.set(f"font_family_{k}", txt)
                    update_preview(k, pl)
                    TypographyService.notify_typography_changed()
                def on_sz_changed(val):
                    self.settings_manager.set(f"font_size_{k}", val)
                    update_preview(k, pl)
                    TypographyService.notify_typography_changed()
                def on_wt_changed(txt):
                    self.settings_manager.set(f"font_weight_{k}", txt.lower())
                    update_preview(k, pl)
                    TypographyService.notify_typography_changed()

                cb.toggled.connect(on_toggle)
                fc.currentTextChanged.connect(on_fam_changed)
                sz.valueChanged.connect(on_sz_changed)
                wt.currentTextChanged.connect(on_wt_changed)

            make_typo_handlers()

            area_box.addLayout(ctrl_row)
            area_box.addWidget(preview_lbl)
            typo_layout.addRow(area_title, area_box)
            self.area_typo_widgets[area_key] = (cb_override, fam_combo, sz_spin, wt_combo, preview_lbl)

        layout.addWidget(typo_card)

        # 1b. Pinned Tasks Typography & Resizable Window Card (Batch 3.10G)
        pinned_card = QFrame()
        pinned_card.setObjectName("CardWidget")
        pinned_layout = QFormLayout(pinned_card)
        pinned_title = QLabel("Pinned Tasks Typography & Window")
        pinned_title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(pinned_title, delta_pt=4, weight="bold")
        pinned_layout.addRow(pinned_title)

        is_pinned_overridden = bool(
            self.settings_manager.get("font_override_pinned_tasks", False)
            or self.settings_manager.get("pinned_tasks_font_override", False)
        )
        self.cb_pinned_use_global = QCheckBox("Use global Todo Bird font")
        self.cb_pinned_use_global.setChecked(not is_pinned_overridden)
        pinned_layout.addRow(self.cb_pinned_use_global)

        # Font Family
        self.pinned_fam_combo = QComboBox()
        self.pinned_fam_combo.setModel(self._font_family_model)
        cur_pin_fam = str(
            self.settings_manager.get("font_family_pinned_tasks")
            or self.settings_manager.get("pinned_tasks_font_family")
            or current_font
        )
        pf_idx = self.pinned_fam_combo.findText(cur_pin_fam)
        if pf_idx >= 0:
            self.pinned_fam_combo.setCurrentIndex(pf_idx)
        self.pinned_fam_combo.setEnabled(is_pinned_overridden)
        pinned_layout.addRow("Font Family", self.pinned_fam_combo)

        # Font Size
        self.pinned_sz_spin = QSpinBox()
        self.pinned_sz_spin.setRange(8, 28)
        self.pinned_sz_spin.setSuffix(" pt")
        cur_pin_sz = int(
            self.settings_manager.get("font_size_pinned_tasks")
            or self.settings_manager.get("pinned_tasks_font_size")
            or 10
        )
        self.pinned_sz_spin.setValue(cur_pin_sz)
        self.pinned_sz_spin.setEnabled(is_pinned_overridden)
        pinned_layout.addRow("Font Size", self.pinned_sz_spin)

        # Font Weight
        self.pinned_wt_combo = QComboBox()
        self.pinned_wt_combo.addItems(["Normal", "Medium", "SemiBold", "Bold"])
        cur_pin_wt = str(
            self.settings_manager.get("font_weight_pinned_tasks")
            or self.settings_manager.get("pinned_tasks_font_weight")
            or "Normal"
        ).capitalize()
        pw_idx = self.pinned_wt_combo.findText(cur_pin_wt)
        if pw_idx >= 0:
            self.pinned_wt_combo.setCurrentIndex(pw_idx)
        self.pinned_wt_combo.setEnabled(is_pinned_overridden)
        pinned_layout.addRow("Font Weight", self.pinned_wt_combo)

        # Pinned Window Sizing Presets
        self.pinned_window_size_combo = QComboBox()
        self.pinned_window_size_combo.addItem("Compact (360 x 260)", "compact")
        self.pinned_window_size_combo.addItem("Standard (520 x 360)", "standard")
        self.pinned_window_size_combo.addItem("Large (740 x 500)", "large")
        self.pinned_window_size_combo.addItem("Custom", "custom")

        cur_pin_mode = str(self.settings_manager.get("pinned_window_size_mode", "standard") or "standard").lower().strip()
        pm_idx = self.pinned_window_size_combo.findData(cur_pin_mode)
        if pm_idx >= 0:
            self.pinned_window_size_combo.setCurrentIndex(pm_idx)
        pinned_layout.addRow("Window Size Preset", self.pinned_window_size_combo)

        # Custom Dimensions
        pin_dim_row = QHBoxLayout()
        self.pinned_w_spin = QSpinBox()
        self.pinned_w_spin.setRange(320, 3840)
        self.pinned_w_spin.setSingleStep(20)
        self.pinned_w_spin.setSuffix(" px")
        self.pinned_w_spin.setValue(int(self.settings_manager.get("pinned_window_width", 520) or 520))

        self.pinned_h_spin = QSpinBox()
        self.pinned_h_spin.setRange(220, 2160)
        self.pinned_h_spin.setSingleStep(20)
        self.pinned_h_spin.setSuffix(" px")
        self.pinned_h_spin.setValue(int(self.settings_manager.get("pinned_window_height", 360) or 360))

        pin_dim_row.addWidget(QLabel("W:"))
        pin_dim_row.addWidget(self.pinned_w_spin)
        pin_dim_row.addWidget(QLabel("H:"))
        pin_dim_row.addWidget(self.pinned_h_spin)
        pin_dim_row.addStretch()
        pinned_layout.addRow("Custom Dimensions", pin_dim_row)

        self.pinned_w_spin.setEnabled(cur_pin_mode == "custom")
        self.pinned_h_spin.setEnabled(cur_pin_mode == "custom")

        # Live Pinned Task Preview Card
        pinned_layout.addRow(QLabel("<b>Live Pinned Task Preview</b>"))
        self.pinned_preview_frame = QFrame()
        self.pinned_preview_frame.setObjectName("SettingsSubPanel")
        accent_preview = str(self.settings_manager.get("accent_color", "#E95420") or "#E95420")
        self.pinned_preview_frame.setStyleSheet(
            f"QFrame#SettingsSubPanel {{ border: 1px solid {accent_preview}; border-left: 6px solid {accent_preview}; border-radius: 10px; padding: 12px; }}"
        )
        pin_p_layout = QVBoxLayout(self.pinned_preview_frame)
        pin_p_layout.setSpacing(6)

        pin_p_title_row = QHBoxLayout()
        pin_icon = QLabel()
        from todo_bird_app.services.icon_service import IconService as _IS_pin
        pin_icon.setPixmap(_IS_pin.get_pixmap("pin", 14, "#E95420"))
        pin_icon.setStyleSheet("font-size: 16px;")
        pin_p_title_row.addWidget(pin_icon)
        self.pinned_preview_title = QLabel("Dealer Review")
        self.pinned_preview_title.setStyleSheet("font-weight: 700; color: inherit;")
        pin_p_title_row.addWidget(self.pinned_preview_title, 1)
        pin_p_layout.addLayout(pin_p_title_row)

        pin_p_btn_row = QHBoxLayout()
        pin_p_btn_row.setSpacing(4)
        btn_mock_left = QPushButton("◀ Left")
        btn_mock_left.setEnabled(False)
        btn_mock_right = QPushButton("Right ▶")
        btn_mock_right.setEnabled(False)
        btn_mock_unpin = QPushButton("✕ Unpin")
        btn_mock_unpin.setEnabled(False)
        pin_p_btn_row.addWidget(btn_mock_left)
        pin_p_btn_row.addWidget(btn_mock_right)
        pin_p_btn_row.addStretch()
        pin_p_btn_row.addWidget(btn_mock_unpin)
        pin_p_layout.addLayout(pin_p_btn_row)

        self.pinned_preview_meta = QLabel("Inbox   ▶ In Progress   60%")
        self.pinned_preview_meta.setObjectName("SettingsHelperText")
        pin_p_layout.addWidget(self.pinned_preview_meta)

        self.pinned_preview_sched = QLabel("Today   10:30–11:30   High")
        self.pinned_preview_sched.setObjectName("SettingsHelperText")
        pin_p_layout.addWidget(self.pinned_preview_sched)

        btn_mock_pin_open = QPushButton("Open Task")
        btn_mock_pin_open.setEnabled(False)
        btn_mock_pin_open.setStyleSheet(
            f"QPushButton {{ background-color: {accent_preview}; color: {text_color_on(accent_preview)};"
            f" border-radius: 6px; padding: 5px 10px; font-weight: 600; }}"
        )
        pin_p_layout.addWidget(btn_mock_pin_open)

        pinned_layout.addRow(self.pinned_preview_frame)

        def update_pinned_preview():
            p_font = TypographyService.get_font_for_area("pinned_tasks", self.settings_manager)
            t_font = QFont(p_font)
            t_font.setPointSize(max(8, p_font.pointSize() + 2))
            t_font.setWeight(p_font.weight())
            self.pinned_preview_title.setFont(t_font)
            m_font = QFont(p_font)
            m_font.setPointSize(max(7, p_font.pointSize() - 1))
            self.pinned_preview_meta.setFont(m_font)
            self.pinned_preview_sched.setFont(m_font)

            c_color = TypographyService.get_font_color_for_area("pinned_tasks", self.settings_manager)
            if c_color:
                self.pinned_preview_title.setStyleSheet(f"color: {c_color};")

        self.update_pinned_preview = update_pinned_preview
        update_pinned_preview()

        # Connect Pinned Tasks Handlers
        def on_pinned_use_global_toggled(checked):
            is_over = not checked
            self.settings_manager.set("font_override_pinned_tasks", is_over)
            self.pinned_fam_combo.setEnabled(is_over)
            self.pinned_sz_spin.setEnabled(is_over)
            self.pinned_wt_combo.setEnabled(is_over)
            update_pinned_preview()
            TypographyService.notify_typography_changed()

        def on_pinned_fam_changed(txt):
            self.settings_manager.set("font_family_pinned_tasks", txt)
            update_pinned_preview()
            TypographyService.notify_typography_changed()

        def on_pinned_sz_changed(val):
            self.settings_manager.set("font_size_pinned_tasks", val)
            update_pinned_preview()
            TypographyService.notify_typography_changed()

        def on_pinned_wt_changed(txt):
            self.settings_manager.set("font_weight_pinned_tasks", txt.lower())
            update_pinned_preview()
            TypographyService.notify_typography_changed()

        def on_pinned_preset_changed(idx):
            mode = self.pinned_window_size_combo.itemData(idx)
            self.settings_manager.set("pinned_window_size_mode", mode)
            is_custom = mode == "custom"
            self.pinned_w_spin.setEnabled(is_custom)
            self.pinned_h_spin.setEnabled(is_custom)
            if mode == "compact":
                self.pinned_w_spin.setValue(360)
                self.pinned_h_spin.setValue(260)
                self.settings_manager.set("pinned_window_width", 360)
                self.settings_manager.set("pinned_window_height", 260)
            elif mode == "standard":
                self.pinned_w_spin.setValue(520)
                self.pinned_h_spin.setValue(360)
                self.settings_manager.set("pinned_window_width", 520)
                self.settings_manager.set("pinned_window_height", 360)
            elif mode == "large":
                self.pinned_w_spin.setValue(740)
                self.pinned_h_spin.setValue(500)
                self.settings_manager.set("pinned_window_width", 740)
                self.settings_manager.set("pinned_window_height", 500)

        def on_pinned_w_changed(val):
            self.settings_manager.set("pinned_window_width", val)

        def on_pinned_h_changed(val):
            self.settings_manager.set("pinned_window_height", val)

        self.cb_pinned_use_global.toggled.connect(on_pinned_use_global_toggled)
        self.pinned_fam_combo.currentTextChanged.connect(on_pinned_fam_changed)
        self.pinned_sz_spin.valueChanged.connect(on_pinned_sz_changed)
        self.pinned_wt_combo.currentTextChanged.connect(on_pinned_wt_changed)
        self.pinned_window_size_combo.currentIndexChanged.connect(on_pinned_preset_changed)
        self.pinned_w_spin.valueChanged.connect(on_pinned_w_changed)
        self.pinned_h_spin.valueChanged.connect(on_pinned_h_changed)

        self.area_typo_widgets["pinned_tasks"] = (
            self.cb_pinned_use_global, self.pinned_fam_combo, self.pinned_sz_spin, self.pinned_wt_combo, self.pinned_preview_title
        )

        layout.addWidget(pinned_card)

        # 1c. Reminder Window Typography, Background & Capsule Card (Batch 3.10G)
        layout = reminders_layout
        from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
        rem_card = QFrame()
        rem_card.setObjectName("CardWidget")
        rem_layout = QFormLayout(rem_card)
        rem_title = QLabel("Reminder Window Typography & Experience")
        rem_title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(rem_title, delta_pt=4, weight="bold")
        rem_layout.addRow(rem_title)

        # Use Global Font Checkbox
        is_rem_overridden = bool(
            self.settings_manager.get("font_override_reminder", False)
            or self.settings_manager.get("reminder_font_override", False)
        )
        self.cb_rem_use_global = QCheckBox("Use global Todo Bird font")
        self.cb_rem_use_global.setChecked(not is_rem_overridden)
        rem_layout.addRow(self.cb_rem_use_global)

        # Font Family
        self.rem_fam_combo = QComboBox()
        self.rem_fam_combo.setModel(self._font_family_model)
        cur_rem_fam = str(
            self.settings_manager.get("font_family_reminder")
            or self.settings_manager.get("reminder_font_family")
            or current_font
        )
        rf_idx = self.rem_fam_combo.findText(cur_rem_fam)
        if rf_idx >= 0:
            self.rem_fam_combo.setCurrentIndex(rf_idx)
        self.rem_fam_combo.setEnabled(is_rem_overridden)
        rem_layout.addRow("Font Family", self.rem_fam_combo)

        # Font Size
        self.rem_sz_spin = QSpinBox()
        self.rem_sz_spin.setRange(8, 28)
        self.rem_sz_spin.setSuffix(" pt")
        cur_rem_sz = int(
            self.settings_manager.get("font_size_reminder")
            or self.settings_manager.get("reminder_font_size")
            or 10
        )
        self.rem_sz_spin.setValue(cur_rem_sz)
        self.rem_sz_spin.setEnabled(is_rem_overridden)
        rem_layout.addRow("Font Size", self.rem_sz_spin)

        # Font Weight
        self.rem_wt_combo = QComboBox()
        self.rem_wt_combo.addItems(["Normal", "Medium", "SemiBold", "Bold"])
        cur_rem_wt = str(
            self.settings_manager.get("font_weight_reminder")
            or self.settings_manager.get("reminder_font_weight")
            or "Normal"
        ).capitalize()
        rw_idx = self.rem_wt_combo.findText(cur_rem_wt)
        if rw_idx >= 0:
            self.rem_wt_combo.setCurrentIndex(rw_idx)
        self.rem_wt_combo.setEnabled(is_rem_overridden)
        rem_layout.addRow("Font Weight", self.rem_wt_combo)

        # Font Color Selection
        rem_color_box = QVBoxLayout()
        rem_color_box.setSpacing(6)

        color_radio_row = QHBoxLayout()
        self.rb_rem_color_auto = QRadioButton("Automatic / Theme")
        self.rb_rem_color_custom = QRadioButton("Custom")
        self.rem_color_btn_group = QButtonGroup(self)
        self.rem_color_btn_group.addButton(self.rb_rem_color_auto)
        self.rem_color_btn_group.addButton(self.rb_rem_color_custom)

        cur_color_mode = str(self.settings_manager.get("font_color_mode_reminder", "auto") or "auto").lower()
        cur_rem_color = str(self.settings_manager.get("font_color_reminder", "#3584E4") or "#3584E4")
        if cur_color_mode == "custom" or (cur_rem_color.startswith("#") and cur_color_mode != "auto"):
            self.rb_rem_color_custom.setChecked(True)
        else:
            self.rb_rem_color_auto.setChecked(True)

        color_radio_row.addWidget(self.rb_rem_color_auto)
        color_radio_row.addWidget(self.rb_rem_color_custom)
        color_radio_row.addStretch()
        rem_color_box.addLayout(color_radio_row)

        custom_color_row = QHBoxLayout()
        self.rem_color_swatch = QLabel()
        self.rem_color_swatch.setFixedSize(36, 24)
        self.rem_color_swatch.setCursor(Qt.PointingHandCursor)
        self.btn_choose_rem_color = QPushButton("Choose Color...")
        self.btn_choose_rem_color.setCursor(Qt.PointingHandCursor)
        self.btn_choose_rem_color.setEnabled(self.rb_rem_color_custom.isChecked())

        self.rem_contrast_warning = QLabel("Low contrast on current theme.")
        self.rem_contrast_warning.setStyleSheet("color: #F59E0B; font-weight: 600; font-size: 11px;")
        self.rem_contrast_warning.hide()

        custom_color_row.addWidget(self.rem_color_swatch)
        custom_color_row.addWidget(self.btn_choose_rem_color)
        custom_color_row.addWidget(self.rem_contrast_warning)
        custom_color_row.addStretch()
        rem_color_box.addLayout(custom_color_row)

        rem_layout.addRow("Font Color", rem_color_box)

        # ----------------------------------------------------
        # Background Image Settings (Batch 3.10G)
        # ----------------------------------------------------
        self.rem_bg_mode_combo = QComboBox()
        self.rem_bg_mode_combo.addItem("None", "none")
        self.rem_bg_mode_combo.addItem("Use Global Background", "global")
        self.rem_bg_mode_combo.addItem("Custom Image", "custom")

        cur_bg_mode = str(self.settings_manager.get("reminder_background_mode", "none") or "none").lower()
        bg_idx = self.rem_bg_mode_combo.findData(cur_bg_mode)
        if bg_idx >= 0:
            self.rem_bg_mode_combo.setCurrentIndex(bg_idx)
        rem_layout.addRow("Background Image", self.rem_bg_mode_combo)

        rem_img_row = QHBoxLayout()
        self.btn_choose_rem_img = QPushButton("Choose Image...")
        self.btn_choose_rem_img.setCursor(Qt.PointingHandCursor)
        self.btn_remove_rem_img = QPushButton("Remove")
        self.btn_remove_rem_img.setCursor(Qt.PointingHandCursor)

        cur_rem_img = str(self.settings_manager.get("reminder_background_image", "") or "")
        self.lbl_rem_img_path = QLabel(Path(cur_rem_img).name if cur_rem_img else "(No image selected)")
        self.lbl_rem_img_path.setObjectName("SettingsHelperText")
        self.btn_remove_rem_img.setEnabled(bool(cur_rem_img))

        rem_img_row.addWidget(self.btn_choose_rem_img)
        rem_img_row.addWidget(self.btn_remove_rem_img)
        rem_img_row.addWidget(self.lbl_rem_img_path)
        rem_img_row.addStretch()
        rem_layout.addRow("Custom Image File", rem_img_row)

        # Fit Mode
        self.rem_bg_fit_combo = QComboBox()
        self.rem_bg_fit_combo.addItem("Fill", "fill")
        self.rem_bg_fit_combo.addItem("Fit", "fit")
        self.rem_bg_fit_combo.addItem("Center", "center")
        self.rem_bg_fit_combo.addItem("Tile", "tile")
        cur_fit = str(self.settings_manager.get("reminder_background_fit", "fill") or "fill").lower()
        fit_idx = self.rem_bg_fit_combo.findData(cur_fit)
        if fit_idx >= 0:
            self.rem_bg_fit_combo.setCurrentIndex(fit_idx)
        rem_layout.addRow("Background Fit", self.rem_bg_fit_combo)

        # Opacity & Overlay Strength
        rem_slider_row = QHBoxLayout()
        self.rem_bg_opacity_spin = QSpinBox()
        self.rem_bg_opacity_spin.setRange(0, 100)
        self.rem_bg_opacity_spin.setSuffix("%")
        cur_op = int(float(self.settings_manager.get("reminder_background_opacity", 0.40) or 0.40) * 100)
        self.rem_bg_opacity_spin.setValue(cur_op)

        self.rem_bg_overlay_spin = QSpinBox()
        self.rem_bg_overlay_spin.setRange(0, 100)
        self.rem_bg_overlay_spin.setSuffix("%")
        cur_ov = int(float(self.settings_manager.get("reminder_background_overlay", 0.70) or 0.70) * 100)
        self.rem_bg_overlay_spin.setValue(cur_ov)

        rem_slider_row.setSpacing(8)
        rem_slider_row.addWidget(QLabel("Opacity:"))
        rem_slider_row.addWidget(self.rem_bg_opacity_spin)
        rem_slider_row.addWidget(QLabel("Legibility Overlay:"))
        rem_slider_row.addWidget(self.rem_bg_overlay_spin)
        rem_slider_row.addStretch()
        rem_layout.addRow("Image Blending", rem_slider_row)

        # ----------------------------------------------------
        # Window Shape & Capsule Style (Batch 3.10G)
        # ----------------------------------------------------
        rem_shape_row = QHBoxLayout()
        rem_shape_row.setSpacing(8)
        self.rem_corner_style_combo = QComboBox()
        self.rem_corner_style_combo.addItem("Soft Rounded (14px)", "soft")
        self.rem_corner_style_combo.addItem("Rounded (24px)", "rounded")
        self.rem_corner_style_combo.addItem("Capsule", "capsule")
        self.rem_corner_style_combo.addItem("Custom Radius", "custom")

        cur_corner = str(self.settings_manager.get("reminder_corner_style", "rounded") or "rounded").lower()
        cs_idx = self.rem_corner_style_combo.findData(cur_corner)
        if cs_idx >= 0:
            self.rem_corner_style_combo.setCurrentIndex(cs_idx)

        self.rem_custom_radius_spin = QSpinBox()
        self.rem_custom_radius_spin.setRange(8, 48)
        self.rem_custom_radius_spin.setSuffix(" px")
        self.rem_custom_radius_spin.setValue(int(self.settings_manager.get("reminder_corner_radius", 18) or 18))
        self.rem_custom_radius_spin.setEnabled(cur_corner == "custom")

        rem_shape_row.addWidget(self.rem_corner_style_combo, 2)
        rem_shape_row.addWidget(QLabel("Radius:"))
        rem_shape_row.addWidget(self.rem_custom_radius_spin, 1)
        rem_shape_row.addStretch()
        rem_layout.addRow("Window Shape", rem_shape_row)

        # ----------------------------------------------------
        # Window Size Presets & Custom Dimensions (Batch 3.10J Polish)
        # ----------------------------------------------------
        self.rem_window_size_combo = QComboBox()
        self.rem_window_size_combo.addItem("Compact (460 x 280)", "compact")
        self.rem_window_size_combo.addItem("Standard (540 x 340)", "standard")
        self.rem_window_size_combo.addItem("Large (680 x 440)", "large")
        self.rem_window_size_combo.addItem("Custom", "custom")

        cur_rem_mode = str(self.settings_manager.get("reminder_window_size_mode", "standard") or "standard").lower().strip()
        rm_idx = self.rem_window_size_combo.findData(cur_rem_mode)
        if rm_idx >= 0:
            self.rem_window_size_combo.setCurrentIndex(rm_idx)
        rem_layout.addRow("Window Size Preset", self.rem_window_size_combo)

        # Custom Dimensions
        rem_dim_row = QHBoxLayout()
        self.rem_w_spin = QSpinBox()
        self.rem_w_spin.setRange(360, 3840)
        self.rem_w_spin.setSingleStep(20)
        self.rem_w_spin.setSuffix(" px")
        self.rem_w_spin.setValue(int(self.settings_manager.get("reminder_window_width", 540) or 540))

        self.rem_h_spin = QSpinBox()
        self.rem_h_spin.setRange(220, 2160)
        self.rem_h_spin.setSingleStep(20)
        self.rem_h_spin.setSuffix(" px")
        self.rem_h_spin.setValue(int(self.settings_manager.get("reminder_window_height", 340) or 340))

        rem_dim_row.addWidget(QLabel("W:"))
        rem_dim_row.addWidget(self.rem_w_spin)
        rem_dim_row.addWidget(QLabel("H:"))
        rem_dim_row.addWidget(self.rem_h_spin)
        rem_dim_row.addStretch()
        rem_layout.addRow("Custom Dimensions", rem_dim_row)

        self.rem_w_spin.setEnabled(cur_rem_mode == "custom")
        self.rem_h_spin.setEnabled(cur_rem_mode == "custom")

        # Real Live Preview Card matching ReminderDialog
        rem_layout.addRow(QLabel("<b>Live Reminder Preview</b>"))
        self.rem_preview_frame = ReminderCardFrame(self.settings_manager, self)
        self.rem_preview_frame.setMinimumHeight(170)
        rem_p_layout = QVBoxLayout(self.rem_preview_frame)
        rem_p_layout.setContentsMargins(16, 14, 16, 14)
        rem_p_layout.setSpacing(8)

        rem_p_header = QHBoxLayout()
        rem_p_icon = QLabel("Reminder")
        rem_p_icon.setStyleSheet("font-weight: 700; color: #3584E4;")
        rem_p_badge = QLabel("10:30 AM")
        rem_p_badge.setStyleSheet(
            "background: rgba(53, 132, 228, 0.15); color: #3584E4; border-radius: 4px; padding: 2px 8px; font-weight: 600;"
        )
        rem_p_header.addWidget(rem_p_icon)
        rem_p_header.addStretch()
        rem_p_header.addWidget(rem_p_badge)
        rem_p_layout.addLayout(rem_p_header)

        self.rem_preview_title = QLabel("Dealer Review")
        self.rem_preview_title.setWordWrap(True)
        rem_p_layout.addWidget(self.rem_preview_title)

        self.rem_preview_sub = QLabel("Today • Project Green Parrot")
        self.rem_preview_sub.setObjectName("SettingsHelperText")
        rem_p_layout.addWidget(self.rem_preview_sub)

        self.rem_preview_desc = QLabel("Review pricing and dealer feedback before the business discussion.")
        self.rem_preview_desc.setWordWrap(True)
        self.rem_preview_desc.setObjectName("SettingsHelperText")
        rem_p_layout.addWidget(self.rem_preview_desc)

        # Mock Button Bar
        rem_p_btn_row = QHBoxLayout()
        rem_p_btn_row.setSpacing(6)
        btn_mock_complete = QPushButton("✓ Complete")
        btn_mock_complete.setEnabled(False)
        btn_mock_complete.setStyleSheet("background-color: #10B981; color: white; border-radius: 4px; padding: 4px 10px; font-weight: 600;")
        btn_mock_snooze = QPushButton("Snooze ▾")
        btn_mock_snooze.setEnabled(False)
        btn_mock_open = QPushButton(" Open Task")
        btn_mock_open.setEnabled(False)
        btn_mock_dismiss = QPushButton("Dismiss")
        btn_mock_dismiss.setEnabled(False)

        rem_p_btn_row.addWidget(btn_mock_complete)
        rem_p_btn_row.addWidget(btn_mock_snooze)
        rem_p_btn_row.addWidget(btn_mock_open)
        rem_p_btn_row.addStretch()
        rem_p_btn_row.addWidget(btn_mock_dismiss)
        rem_p_layout.addLayout(rem_p_btn_row)

        rem_layout.addRow(self.rem_preview_frame)

        # Live Preview & Contrast Evaluation Function
        def update_reminder_preview():
            p_font = TypographyService.get_font_for_area("reminder", self.settings_manager)
            title_f = QFont(p_font)
            title_f.setPointSize(max(10, p_font.pointSize() + 4))
            title_f.setWeight(p_font.weight())
            self.rem_preview_title.setFont(title_f)
            self.rem_preview_desc.setFont(p_font)

            cur_color_mode = str(self.settings_manager.get("font_color_mode_reminder", "auto") or "auto").lower()
            c_color = TypographyService.get_font_color_for_area("reminder", self.settings_manager)
            
            # Determine effective theme text colors for automatic preview & swatch
            cur_theme = str(self.settings_manager.get("theme", "dark") or "dark").lower()
            theme_fg = "#E5E7EB" if cur_theme == "dark" else "#111827"
            theme_bg = "#1E1E1E" if cur_theme == "dark" else "#FFFFFF"

            if cur_color_mode == "custom" and c_color:
                self.rem_preview_title.setStyleSheet(f"color: {c_color}; font-weight: 700;")
                self.rem_preview_desc.setStyleSheet(f"color: {c_color}; line-height: 1.4;")
                self.rem_color_swatch.setStyleSheet(
                    f"background-color: {c_color}; border: 2px solid #64748B; border-radius: 4px;"
                )
                self.rem_color_swatch.setToolTip(f"Custom Color: {c_color} (Click to change)")
                ratio = TypographyService.calculate_contrast_ratio(c_color, theme_bg)
                if ratio < 3.0:
                    self.rem_contrast_warning.show()
                else:
                    self.rem_contrast_warning.hide()
            else:
                self.rem_preview_title.setStyleSheet("color: inherit; font-weight: 700;")
                self.rem_preview_desc.setObjectName("SettingsHelperText")
                self.rem_contrast_warning.hide()
                self.rem_color_swatch.setStyleSheet(
                    f"background-color: {theme_fg}; border: 1px solid #64748B; border-radius: 4px;"
                )
                self.rem_color_swatch.setToolTip("Automatic (Theme contrast color)")

            self.rem_preview_frame.update()
            from todo_bird_app.services.window_registry import WindowRegistry
            WindowRegistry.notify_reminder_settings_changed()

        self.update_reminder_preview = update_reminder_preview
        update_reminder_preview()

        # Connect Reminder Typography Controls
        def on_rem_use_global_toggled(checked):
            is_over = not checked
            self.settings_manager.set("font_override_reminder", is_over)
            self.rem_fam_combo.setEnabled(is_over)
            self.rem_sz_spin.setEnabled(is_over)
            self.rem_wt_combo.setEnabled(is_over)
            update_reminder_preview()
            TypographyService.notify_typography_changed()

        def on_rem_fam_changed(txt):
            self.settings_manager.set("font_family_reminder", txt)
            update_reminder_preview()
            TypographyService.notify_typography_changed()

        def on_rem_sz_changed(val):
            self.settings_manager.set("font_size_reminder", val)
            update_reminder_preview()
            TypographyService.notify_typography_changed()

        def on_rem_wt_changed(txt):
            self.settings_manager.set("font_weight_reminder", txt.lower())
            update_reminder_preview()
            TypographyService.notify_typography_changed()

        def on_rem_color_mode_auto(checked):
            if checked:
                self.settings_manager.set("font_color_mode_reminder", "auto")
                self.btn_choose_rem_color.setEnabled(False)
                update_reminder_preview()
                TypographyService.notify_typography_changed()

        def on_rem_color_mode_custom(checked):
            if checked:
                cur_val = str(self.settings_manager.get("font_color_reminder", "") or "")
                if not cur_val.startswith("#"):
                    self.settings_manager.set("font_color_reminder", "#3584E4")
                self.settings_manager.set("font_color_mode_reminder", "custom")
                self.btn_choose_rem_color.setEnabled(True)
                update_reminder_preview()
                TypographyService.notify_typography_changed()

        def on_choose_color_clicked():
            cur_c = str(self.settings_manager.get("font_color_reminder", "#3584E4") or "#3584E4")
            if not cur_c.startswith("#"):
                cur_c = "#3584E4"

            initial = QColor(cur_c)
            if not initial.isValid():
                initial = QColor("#3584E4")

            dlg = QColorDialog(initial, self.window())
            dlg.setWindowTitle("Choose Reminder Font Color")
            dlg.setOption(QColorDialog.ShowAlphaChannel, False)
            dlg.setOption(QColorDialog.DontUseNativeDialog, True)

            if dlg.exec() == QColorDialog.Accepted:
                new_c = dlg.selectedColor()
                if new_c.isValid():
                    hex_val = new_c.name().upper()
                    self.settings_manager.set("font_color_reminder", hex_val)
                    self.settings_manager.set("font_color_mode_reminder", "custom")
                    self.rb_rem_color_custom.setChecked(True)
                    self.btn_choose_rem_color.setEnabled(True)
                    update_reminder_preview()
                    TypographyService.notify_typography_changed()

        def on_choose_reminder_bg():
            path, _ = QFileDialog.getOpenFileName(
                self.window(),
                "Select Reminder Background Image",
                "",
                "Image Files (*.png *.jpg *.jpeg *.bmp *.webp *.gif)",
            )
            if path:
                saved_rel = MediaService.import_media(path, category="reminders")
                self.settings_manager.set("reminder_background_image", saved_rel)
                self.settings_manager.set("reminder_background_mode", "custom")
                bg_c_idx = self.rem_bg_mode_combo.findData("custom")
                if bg_c_idx >= 0:
                    self.rem_bg_mode_combo.setCurrentIndex(bg_c_idx)
                self.lbl_rem_img_path.setText(Path(saved_rel).name)
                self.btn_remove_rem_img.setEnabled(True)
                update_reminder_preview()

        def on_remove_reminder_bg():
            self.settings_manager.set("reminder_background_image", "")
            self.lbl_rem_img_path.setText("(No image selected)")
            self.btn_remove_rem_img.setEnabled(False)
            update_reminder_preview()

        def on_rem_bg_mode_changed(idx):
            mode = self.rem_bg_mode_combo.itemData(idx)
            self.settings_manager.set("reminder_background_mode", mode)
            update_reminder_preview()

        def on_rem_bg_fit_changed(idx):
            fit = self.rem_bg_fit_combo.itemData(idx)
            self.settings_manager.set("reminder_background_fit", fit)
            update_reminder_preview()

        def on_rem_bg_opacity_changed(val):
            self.settings_manager.set("reminder_background_opacity", val / 100.0)
            update_reminder_preview()

        def on_rem_bg_overlay_changed(val):
            self.settings_manager.set("reminder_background_overlay", val / 100.0)
            update_reminder_preview()

        def on_rem_corner_style_changed(idx):
            style = self.rem_corner_style_combo.itemData(idx)
            self.settings_manager.set("reminder_corner_style", style)
            self.rem_custom_radius_spin.setEnabled(style == "custom")
            update_reminder_preview()

        def on_rem_custom_radius_changed(val):
            self.settings_manager.set("reminder_corner_radius", val)
            update_reminder_preview()

        def on_rem_window_size_preset_changed(idx):
            mode = self.rem_window_size_combo.itemData(idx)
            self.settings_manager.set("reminder_window_size_mode", mode)
            is_custom = (mode == "custom")
            self.rem_w_spin.setEnabled(is_custom)
            self.rem_h_spin.setEnabled(is_custom)

            REMINDER_PRESETS = {
                "compact": (460, 280),
                "standard": (540, 340),
                "large": (680, 440),
            }
            if mode in REMINDER_PRESETS:
                pw, ph = REMINDER_PRESETS[mode]
                self.rem_w_spin.blockSignals(True)
                self.rem_h_spin.blockSignals(True)
                self.rem_w_spin.setValue(pw)
                self.rem_h_spin.setValue(ph)
                self.rem_w_spin.blockSignals(False)
                self.rem_h_spin.blockSignals(False)
                self.settings_manager.set("reminder_window_width", pw)
                self.settings_manager.set("reminder_window_height", ph)

            update_reminder_preview()
            from todo_bird_app.services.window_registry import WindowRegistry
            WindowRegistry.notify_reminder_settings_changed()

        def on_rem_dim_changed(_val):
            self.settings_manager.set("reminder_window_width", self.rem_w_spin.value())
            self.settings_manager.set("reminder_window_height", self.rem_h_spin.value())
            self.settings_manager.set("reminder_window_size_mode", "custom")
            c_idx = self.rem_window_size_combo.findData("custom")
            if c_idx >= 0 and self.rem_window_size_combo.currentIndex() != c_idx:
                self.rem_window_size_combo.blockSignals(True)
                self.rem_window_size_combo.setCurrentIndex(c_idx)
                self.rem_window_size_combo.blockSignals(False)

            update_reminder_preview()
            from todo_bird_app.services.window_registry import WindowRegistry
            WindowRegistry.notify_reminder_settings_changed()

        def on_external_reminder_resized(w: int, h: int):
            self.rem_w_spin.blockSignals(True)
            self.rem_h_spin.blockSignals(True)
            self.rem_w_spin.setValue(w)
            self.rem_h_spin.setValue(h)
            self.rem_w_spin.blockSignals(False)
            self.rem_h_spin.blockSignals(False)

            cur_mode = str(self.settings_manager.get("reminder_window_size_mode", "custom") or "custom").lower()
            c_idx = self.rem_window_size_combo.findData(cur_mode)
            if c_idx >= 0 and self.rem_window_size_combo.currentIndex() != c_idx:
                self.rem_window_size_combo.blockSignals(True)
                self.rem_window_size_combo.setCurrentIndex(c_idx)
                self.rem_window_size_combo.blockSignals(False)
            self.rem_w_spin.setEnabled(cur_mode == "custom")
            self.rem_h_spin.setEnabled(cur_mode == "custom")
            self.rem_preview_frame.update()

        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.register_reminder_resize_listener(on_external_reminder_resized)
        self._reminder_resize_listener = on_external_reminder_resized

        self.on_choose_reminder_color = on_choose_color_clicked
        self.rem_color_swatch.mousePressEvent = lambda ev: on_choose_color_clicked()
        self.cb_rem_use_global.toggled.connect(on_rem_use_global_toggled)
        self.rem_fam_combo.currentTextChanged.connect(on_rem_fam_changed)
        self.rem_sz_spin.valueChanged.connect(on_rem_sz_changed)
        self.rem_wt_combo.currentTextChanged.connect(on_rem_wt_changed)
        self.rem_window_size_combo.currentIndexChanged.connect(on_rem_window_size_preset_changed)
        self.rem_w_spin.valueChanged.connect(on_rem_dim_changed)
        self.rem_h_spin.valueChanged.connect(on_rem_dim_changed)
        self.rb_rem_color_auto.toggled.connect(on_rem_color_mode_auto)
        self.rb_rem_color_custom.toggled.connect(on_rem_color_mode_custom)
        self.btn_choose_rem_color.clicked.connect(on_choose_color_clicked)

        self.btn_choose_rem_img.clicked.connect(on_choose_reminder_bg)
        self.btn_remove_rem_img.clicked.connect(on_remove_reminder_bg)
        self.rem_bg_mode_combo.currentIndexChanged.connect(on_rem_bg_mode_changed)
        self.rem_bg_fit_combo.currentIndexChanged.connect(on_rem_bg_fit_changed)
        self.rem_bg_opacity_spin.valueChanged.connect(on_rem_bg_opacity_changed)
        self.rem_bg_overlay_spin.valueChanged.connect(on_rem_bg_overlay_changed)
        self.rem_corner_style_combo.currentIndexChanged.connect(on_rem_corner_style_changed)
        self.rem_custom_radius_spin.valueChanged.connect(on_rem_custom_radius_changed)

        # Store in area_typo_widgets for test suite introspection compatibility
        self.area_typo_widgets["reminder"] = (
            self.cb_rem_use_global, self.rem_fam_combo, self.rem_sz_spin, self.rem_wt_combo, self.rem_preview_title
        )

        # When to Show Reminders (Trigger Mode)
        self.reminder_trigger_combo = QComboBox()
        for mode_key, mode_label in ReminderPolicyService.TRIGGER_MODES:
            self.reminder_trigger_combo.addItem(mode_label, mode_key)
        self.reminder_trigger_combo.setToolTip(
            "Controls automatic reminder popups. Task launch reminders use Todo Bird Startup unless you choose Computer Startup."
        )

        cur_trig = ReminderPolicyService.get_trigger_mode(self.settings_manager)
        t_idx = self.reminder_trigger_combo.findData(cur_trig)
        if t_idx >= 0:
            self.reminder_trigger_combo.setCurrentIndex(t_idx)

        self.reminder_trigger_combo.currentIndexChanged.connect(
            lambda idx: self.settings_manager.set(
                "reminder_trigger_mode", self.reminder_trigger_combo.itemData(idx)
            )
        )
        rem_layout.addRow("Startup reminder policy", self.reminder_trigger_combo)

        layout.addWidget(rem_card)

        # 2. Companion & Voice Personalization Card
        layout = companion_layout
        companion_card = QFrame()
        companion_card.setObjectName("CardWidget")
        c_layout = QFormLayout(companion_card)

        c_title = QLabel(" Companion & 30-Day Greeting Planner")
        c_title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(c_title, delta_pt=4, weight="bold")
        c_layout.addRow(c_title)

        self.cb_companion_enabled = QCheckBox("Enable Desktop Avocet Companion")
        self.cb_companion_enabled.setChecked(
            self.settings_manager.get("companion_enabled", True)
        )
        self.cb_companion_enabled.toggled.connect(
            lambda val: self.settings_manager.set("companion_enabled", val)
        )
        c_layout.addRow(self.cb_companion_enabled)

        # Companion Avatar Customization (Batch 3.5)
        c_layout.addRow(QLabel("<b> Companion Avatar Customization</b>"))

        self.companion_avatar_combo = QComboBox()
        self.companion_avatar_combo.addItems(["Default Bird", "Custom Image", "Disabled"])
        curr_av = str(self.settings_manager.get("companion_avatar_mode", "default")).lower()
        if curr_av == "custom":
            self.companion_avatar_combo.setCurrentText("Custom Image")
        elif curr_av == "disabled":
            self.companion_avatar_combo.setCurrentText("Disabled")
        else:
            self.companion_avatar_combo.setCurrentText("Default Bird")
        self.companion_avatar_combo.currentTextChanged.connect(self.on_avatar_mode_changed)
        c_layout.addRow("Companion Avatar", self.companion_avatar_combo)

        avatar_img_row = QHBoxLayout()
        self.avatar_preview_label = QLabel()
        self.avatar_preview_label.setFixedSize(48, 48)
        self.avatar_preview_label.setStyleSheet("border: 1px dashed #64748B; border-radius: 8px; background: rgba(0,0,0,0.04);")
        self.avatar_preview_label.setAlignment(Qt.AlignCenter)
        self.current_avatar_path = str(self.settings_manager.get("companion_custom_avatar_path", ""))

        self.btn_choose_avatar = QPushButton("Choose Custom Avatar")
        self.btn_remove_avatar = QPushButton("Restore Default")
        self.btn_choose_avatar.clicked.connect(self.on_choose_avatar_image)
        self.btn_remove_avatar.clicked.connect(self.on_remove_avatar_image)
        avatar_img_row.addWidget(self.avatar_preview_label)
        avatar_img_row.addWidget(self.btn_choose_avatar)
        avatar_img_row.addWidget(self.btn_remove_avatar)
        avatar_img_row.addStretch()
        c_layout.addRow("Avatar Image", avatar_img_row)
        self.update_avatar_preview()

        self.companion_activity_combo = QComboBox()
        self.companion_activity_combo.addItems(["Off", "Minimal", "Balanced", "Expressive"])
        curr_act = str(self.settings_manager.get("companion_activity_level", "balanced")).capitalize()
        self.companion_activity_combo.setCurrentText(curr_act if curr_act in ["Off", "Minimal", "Balanced", "Expressive"] else "Balanced")
        self.companion_activity_combo.currentTextChanged.connect(self.on_activity_level_changed)
        c_layout.addRow("Activity & Celebrations", self.companion_activity_combo)

        self.greeting_freq_combo = QComboBox()
        self.greeting_freq_combo.addItems(["Once per day", "Once per app launch", "Never"])
        curr_freq = str(self.settings_manager.get("companion_greeting_frequency", "once_per_day"))
        if curr_freq == "once_per_session":
            self.greeting_freq_combo.setCurrentText("Once per app launch")
        elif curr_freq == "never":
            self.greeting_freq_combo.setCurrentText("Never")
        else:
            self.greeting_freq_combo.setCurrentText("Once per day")
        self.greeting_freq_combo.currentTextChanged.connect(self.on_greeting_freq_changed)
        c_layout.addRow("Greeting Popup Frequency", self.greeting_freq_combo)

        self.greeting_schedule_combo = QComboBox()
        self.greeting_schedule_combo.addItems(["30-Day Cycle Planner", "Same Every Day", "Date-Specific"])
        curr_sched = str(self.settings_manager.get("companion_greeting_schedule_mode", "day_by_day"))
        if curr_sched == "same_every_day":
            self.greeting_schedule_combo.setCurrentText("Same Every Day")
        elif curr_sched == "date_specific":
            self.greeting_schedule_combo.setCurrentText("Date-Specific")
        else:
            self.greeting_schedule_combo.setCurrentText("30-Day Cycle Planner")
        self.greeting_schedule_combo.currentTextChanged.connect(self.on_greeting_schedule_mode_changed)
        c_layout.addRow("Greeting Schedule Mode", self.greeting_schedule_combo)

        # 30-Day Greeting Planner Table (Batch 3.5)
        c_layout.addRow(QLabel("<b>30-Day Greeting Planner</b>"))
        self.greetings_table = QTableWidget()
        self.greetings_table.setColumnCount(5)
        self.greetings_table.setHorizontalHeaderLabels(["Day", "Image", "Greeting Title", "Message / Quote", "Status"])
        self.greetings_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.greetings_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.greetings_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.greetings_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.greetings_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.greetings_table.setMinimumHeight(240)
        self.greetings_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.greetings_table.doubleClicked.connect(self.on_edit_selected_greeting)
        c_layout.addRow(self.greetings_table)

        planner_btn_row = QHBoxLayout()
        self.btn_edit_greeting = QPushButton("Edit Selected Day")
        self.btn_apply_selected = QPushButton("Apply to Selected Days")
        self.btn_duplicate_all = QPushButton("Duplicate to All 30 Days")
        self.btn_preview_today = QPushButton(" Preview Today's Greeting")
        self.btn_edit_greeting.clicked.connect(self.on_edit_selected_greeting)
        self.btn_apply_selected.clicked.connect(self.on_apply_greeting_to_selected_days)
        self.btn_duplicate_all.clicked.connect(self.on_duplicate_greeting_to_all)
        self.btn_preview_today.clicked.connect(self.on_preview_today_greeting)
        planner_btn_row.addWidget(self.btn_edit_greeting)
        planner_btn_row.addWidget(self.btn_apply_selected)
        planner_btn_row.addWidget(self.btn_duplicate_all)
        planner_btn_row.addWidget(self.btn_preview_today)
        planner_btn_row.addStretch()
        c_layout.addRow(planner_btn_row)

        self.load_greetings_table()

        self.cb_voice_enabled = QCheckBox("Enable Companion Voice")
        self.cb_voice_enabled.setChecked(
            self.settings_manager.get("voice_enabled", True)
        )
        self.cb_voice_enabled.toggled.connect(
            lambda val: self.settings_manager.set("voice_enabled", val)
        )
        c_layout.addRow(self.cb_voice_enabled)

        self.combo_greeting_mode = QComboBox()
        for label, value in (
            ("Once daily", "once_daily"),
            ("Every app startup", "every_startup"),
            ("Never speak at startup", "never"),
        ):
            self.combo_greeting_mode.addItem(label, value)
        curr_greeting_mode = str(
            self.settings_manager.get("greeting_mode", "once_daily")
            or "once_daily"
        )
        idx_greeting_mode = self.combo_greeting_mode.findData(curr_greeting_mode)
        if idx_greeting_mode >= 0:
            self.combo_greeting_mode.setCurrentIndex(idx_greeting_mode)
        self.combo_greeting_mode.currentIndexChanged.connect(
            self.on_startup_voice_frequency_changed
        )
        c_layout.addRow("Startup Voice Frequency", self.combo_greeting_mode)

        self.spin_companion_visible = QSpinBox()
        self.spin_companion_visible.setRange(5, 120)
        self.spin_companion_visible.setSuffix(" sec")
        self.spin_companion_visible.setValue(
            int(self.settings_manager.get("companion_visible_seconds", 24))
        )
        self.spin_companion_visible.valueChanged.connect(
            lambda val: self.settings_manager.set("companion_visible_seconds", val)
        )
        c_layout.addRow("Companion Visible Duration", self.spin_companion_visible)

        # Personalization & Durga Voice settings
        c_layout.addRow(QLabel("<b> Voice Persona & Greeting Delivery</b>"))

        from todo_bird_app.services.avocet_voice_service import AvocetVoiceService

        # Voice Profile Dropdown with Preview Button
        voice_profile_row = QHBoxLayout()
        self.combo_voice_profile = QComboBox()
        for vp_id, vp in AvocetVoiceService.VOICE_PROFILES.items():
            self.combo_voice_profile.addItem(vp["display_name"], vp_id)

        curr_vp = str(self.settings_manager.get("active_voice_profile", "durga"))
        idx_vp = self.combo_voice_profile.findData(curr_vp)
        if idx_vp != -1:
            self.combo_voice_profile.setCurrentIndex(idx_vp)
        self.combo_voice_profile.currentIndexChanged.connect(
            lambda: self.settings_manager.set("active_voice_profile", self.combo_voice_profile.currentData() or "durga")
        )

        self.btn_preview_voice = QPushButton(" Preview Voice")
        self.btn_preview_voice.setObjectName("PreviewVoiceButton")
        self.btn_preview_voice.setToolTip("Listen to a warm sample greeting in this voice profile")
        self.btn_preview_voice.clicked.connect(self.on_preview_voice)

        voice_profile_row.addWidget(self.combo_voice_profile, 1)
        voice_profile_row.addWidget(self.btn_preview_voice)
        c_layout.addRow("Voice Profile", voice_profile_row)

        audio_output_row = QHBoxLayout()
        self.combo_audio_output = QComboBox()
        self.btn_refresh_audio_outputs = QPushButton("Refresh")
        self.btn_refresh_audio_outputs.setToolTip("Refresh available audio output devices")
        self.btn_refresh_audio_outputs.clicked.connect(self.on_refresh_audio_outputs)
        audio_output_row.addWidget(self.combo_audio_output, 1)
        audio_output_row.addWidget(self.btn_refresh_audio_outputs)
        c_layout.addRow("Audio Output", audio_output_row)
        self.refresh_audio_output_options()
        self.combo_audio_output.currentIndexChanged.connect(
            self.on_audio_output_changed
        )

        # Tone Style Selection Dropdown
        self.combo_tone_style = QComboBox()
        for ts_id, ts in AvocetVoiceService.TONE_STYLES.items():
            self.combo_tone_style.addItem(ts["name"], ts_id)

        curr_ts = str(self.settings_manager.get("active_tone_style", "custom"))
        idx_ts = self.combo_tone_style.findData(curr_ts)
        if idx_ts != -1:
            self.combo_tone_style.setCurrentIndex(idx_ts)
        self.combo_tone_style.currentIndexChanged.connect(self.on_tone_style_changed)
        c_layout.addRow("Greeting Tone Style", self.combo_tone_style)

        self.edit_assistant_name = QLineEdit()
        self.edit_assistant_name.setText(
            self.settings_manager.get("assistant_name", "Durga")
        )
        self.edit_assistant_name.textChanged.connect(
            lambda text: self.settings_manager.set("assistant_name", text.strip())
        )
        c_layout.addRow("Assistant Name", self.edit_assistant_name)

        self.edit_user_salutation = QLineEdit()
        self.edit_user_salutation.setText(
            self.settings_manager.get("user_salutation", "friend")
        )
        self.edit_user_salutation.textChanged.connect(
            lambda text: self.settings_manager.set("user_salutation", text.strip())
        )
        c_layout.addRow("User Salutation", self.edit_user_salutation)

        # Time-period greeting gates
        periods_row = QHBoxLayout()
        self.cb_greet_morning = QCheckBox("Morning")
        self.cb_greet_morning.setChecked(self.settings_manager.get("greeting_morning_enabled", True))
        self.cb_greet_morning.toggled.connect(
            lambda val: self.settings_manager.set("greeting_morning_enabled", val)
        )

        self.cb_greet_afternoon = QCheckBox("Afternoon")
        self.cb_greet_afternoon.setChecked(self.settings_manager.get("greeting_afternoon_enabled", True))
        self.cb_greet_afternoon.toggled.connect(
            lambda val: self.settings_manager.set("greeting_afternoon_enabled", val)
        )

        self.cb_greet_evening = QCheckBox("Evening")
        self.cb_greet_evening.setChecked(self.settings_manager.get("greeting_evening_enabled", True))
        self.cb_greet_evening.toggled.connect(
            lambda val: self.settings_manager.set("greeting_evening_enabled", val)
        )

        self.cb_greet_night = QCheckBox("Night")
        self.cb_greet_night.setChecked(self.settings_manager.get("greeting_night_enabled", True))
        self.cb_greet_night.toggled.connect(
            lambda val: self.settings_manager.set("greeting_night_enabled", val)
        )

        periods_row.addWidget(self.cb_greet_morning)
        periods_row.addWidget(self.cb_greet_afternoon)
        periods_row.addWidget(self.cb_greet_evening)
        periods_row.addWidget(self.cb_greet_night)
        periods_row.addStretch()
        c_layout.addRow("Speak Greeting for Periods", periods_row)

        self.cb_devotional_intro = QCheckBox("Enable Morning Devotional Intro")
        self.cb_devotional_intro.setChecked(self.settings_manager.get("devotional_intro", True))
        self.cb_devotional_intro.toggled.connect(
            lambda val: self.settings_manager.set("devotional_intro", val)
        )
        c_layout.addRow("", self.cb_devotional_intro)

        # Customizable intro text (was a hardcoded mantra)
        from todo_bird_app.services.avocet_voice_service import AvocetVoiceService

        self.devotional_intro_edit = QLineEdit()
        self.devotional_intro_edit.setPlaceholderText(
            "e.g. Om Gam Ganapataye Namaha."
        )
        self.devotional_intro_edit.setText(
            str(
                self.settings_manager.get(
                    "devotional_intro_text",
                    AvocetVoiceService.DEVOTIONAL_PREFIX.strip(),
                )
                or ""
            ).strip()
        )
        self.devotional_intro_edit.setToolTip(
            "Spoken before the morning greeting when the devotional intro is enabled. Leave blank to use the default mantra."
        )

        def _save_devotional_text():
            self.settings_manager.set(
                "devotional_intro_text",
                self.devotional_intro_edit.text().strip(),
            )

        self.devotional_intro_edit.editingFinished.connect(_save_devotional_text)
        c_layout.addRow("Devotional Intro Text", self.devotional_intro_edit)

        # Custom Greeting Messages
        from todo_bird_app.services.avocet_voice_service import AvocetVoiceService

        self.morning_message_edit = QPlainTextEdit()
        self.morning_message_edit.setMinimumHeight(76)
        self.morning_message_edit.setPlainText(
            self.settings_manager.get(
                "custom_greeting_morning",
                AvocetVoiceService.DEFAULT_GREETINGS["morning"]
            )
        )
        self.morning_message_edit.textChanged.connect(
            lambda: self.settings_manager.set(
                "custom_greeting_morning",
                self.morning_message_edit.toPlainText().strip()
            )
        )
        c_layout.addRow("Morning Message", self.morning_message_edit)

        self.afternoon_message_edit = QPlainTextEdit()
        self.afternoon_message_edit.setMinimumHeight(76)
        self.afternoon_message_edit.setPlainText(
            self.settings_manager.get(
                "custom_greeting_afternoon",
                AvocetVoiceService.DEFAULT_GREETINGS["afternoon"]
            )
        )
        self.afternoon_message_edit.textChanged.connect(
            lambda: self.settings_manager.set(
                "custom_greeting_afternoon",
                self.afternoon_message_edit.toPlainText().strip()
            )
        )
        c_layout.addRow("Afternoon Message", self.afternoon_message_edit)

        self.evening_message_edit = QPlainTextEdit()
        self.evening_message_edit.setMinimumHeight(76)
        self.evening_message_edit.setPlainText(
            self.settings_manager.get(
                "custom_greeting_evening",
                AvocetVoiceService.DEFAULT_GREETINGS["evening"]
            )
        )
        self.evening_message_edit.textChanged.connect(
            lambda: self.settings_manager.set(
                "custom_greeting_evening",
                self.evening_message_edit.toPlainText().strip()
            )
        )
        c_layout.addRow("Evening Message", self.evening_message_edit)

        self.night_message_edit = QPlainTextEdit()
        self.night_message_edit.setMinimumHeight(76)
        self.night_message_edit.setPlainText(
            self.settings_manager.get(
                "custom_greeting_night",
                AvocetVoiceService.DEFAULT_GREETINGS["night"]
            )
        )
        self.night_message_edit.textChanged.connect(
            lambda: self.settings_manager.set(
                "custom_greeting_night",
                self.night_message_edit.toPlainText().strip()
            )
        )
        c_layout.addRow("Night Message", self.night_message_edit)

        # Audio Action and Troubleshooting Buttons
        action_btn_row = QHBoxLayout()
        self.btn_test_durga_voice = QPushButton("Test Durga Voice")
        self.btn_test_durga_voice.setObjectName("TestVoiceButton")
        self.btn_test_durga_voice.clicked.connect(self.on_test_durga_voice)

        self.btn_test_startup_greeting = QPushButton("Test Startup Greeting")
        self.btn_test_startup_greeting.setObjectName("TestGreetingButton")
        self.btn_test_startup_greeting.clicked.connect(self.on_test_startup_greeting)

        self.btn_reset_spoken_today = QPushButton("Reset Spoken Today")
        self.btn_reset_spoken_today.setObjectName("ResetSpokenButton")
        self.btn_reset_spoken_today.clicked.connect(self.on_reset_spoken_today)

        action_btn_row.addWidget(self.btn_test_durga_voice)
        action_btn_row.addWidget(self.btn_test_startup_greeting)
        action_btn_row.addWidget(self.btn_reset_spoken_today)
        action_btn_row.addStretch()
        c_layout.addRow("Audio Troubleshooting", action_btn_row)

        self.save_companion_btn = QPushButton(" Save Companion Settings")
        self.save_companion_btn.setObjectName("PrimaryButton")
        self.save_companion_btn.clicked.connect(
            self.save_companion_settings
        )
        c_layout.addRow(self.save_companion_btn)

        layout.addWidget(companion_card)

        # 3. Calendar & Working Week Card
        layout = planning_layout
        ww_card = QFrame()
        ww_card.setObjectName("CardWidget")
        ww_layout = QFormLayout(ww_card)
        ww_title = QLabel("Working Week & Resource Capacity")
        ww_title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(ww_title, delta_pt=4, weight="bold")
        ww_layout.addRow(ww_title)

        days_layout = QHBoxLayout()
        current_working_days = set(self.working_week_service.get_working_weekdays())
        for day_code, day_name in WEEKDAY_NAMES:
            cb = QCheckBox(day_name[:3])
            cb.setToolTip(f"Enable {day_name} as an active working day")
            cb.setChecked(day_code in current_working_days)
            cb.toggled.connect(self.on_working_days_changed)
            days_layout.addWidget(cb)
            self.day_checkboxes[day_code] = cb

        ww_layout.addRow("Active Working Days", days_layout)

        # Default Daily Capacity
        capacity_layout = QHBoxLayout()
        self.capacity_hours_spin = QSpinBox()
        self.capacity_hours_spin.setRange(0, 24)
        self.capacity_hours_spin.setSuffix("h")

        self.capacity_mins_spin = QSpinBox()
        self.capacity_mins_spin.setRange(0, 59)
        self.capacity_mins_spin.setSuffix("m")

        init_cap = int(self.settings_manager.get("default_daily_capacity_minutes", 480) or 480)
        self.capacity_hours_spin.setValue(init_cap // 60)
        self.capacity_mins_spin.setValue(init_cap % 60)

        self.capacity_hours_spin.valueChanged.connect(self.on_capacity_changed)
        self.capacity_mins_spin.valueChanged.connect(self.on_capacity_changed)

        capacity_layout.addWidget(self.capacity_hours_spin)
        capacity_layout.addWidget(self.capacity_mins_spin)
        capacity_layout.addWidget(QLabel("/ day"))
        capacity_layout.addStretch()
        ww_layout.addRow("Daily Resource Capacity", capacity_layout)

        self.ww_status_badge = QLabel("")
        self.ww_status_badge.setStyleSheet("color: #10B981; font-weight: 600; font-size: 12px;")
        ww_layout.addRow("", self.ww_status_badge)

        # Weekend Opacity & Shading
        self.cb_enable_shading = QCheckBox("Enable Weekend Shading Overlay")
        self.cb_enable_shading.setChecked(self.settings_manager.get("enable_weekend_shading", True))
        self.cb_enable_shading.toggled.connect(lambda val: self.settings_manager.set("enable_weekend_shading", val))
        ww_layout.addRow(self.cb_enable_shading)

        opacity_layout = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        curr_op = self.settings_manager.get("weekend_opacity", 30)
        self.opacity_slider.setValue(curr_op)
        self.opacity_label = QLabel(f"{curr_op}%")
        self.opacity_slider.valueChanged.connect(self.on_opacity_changed)
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_label)
        ww_layout.addRow("Weekend Shading Opacity", opacity_layout)

        layout.addWidget(ww_card)

        # 3. Gantt Appearance Customization Card
        gantt_card = QFrame()
        gantt_card.setObjectName("CardWidget")
        g_layout = QFormLayout(gantt_card)
        g_title = QLabel("Gantt Chart Theme & Custom Task Colors")
        g_title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(g_title, delta_pt=4, weight="bold")
        g_layout.addRow(g_title)

        self.gantt_mode_combo = QComboBox()
        self.gantt_mode_combo.addItems(["Follow Application Theme", "Light Gantt", "Dark Gantt", "High Contrast", "Custom"])
        self.gantt_mode_combo.currentTextChanged.connect(self.on_gantt_mode_changed)
        g_layout.addRow("Gantt Theme Mode", self.gantt_mode_combo)

        # Color Pickers
        colors_grid = QFormLayout()
        for key, label_text in COLOR_KEYS:
            c_val = self.custom_colors.get(key, DEFAULT_GANTT_COLORS.get(key, "#3584E4"))
            btn = QPushButton(c_val)
            btn.setStyleSheet(f"background-color: {c_val}; color: {text_color_on(c_val)}; font-weight: 600; border-radius: 6px; padding: 4px 12px;")
            btn.clicked.connect(lambda _, k=key, b=btn: self.pick_gantt_color(k, b))
            colors_grid.addRow(label_text, btn)
            self.color_buttons[key] = btn

        g_layout.addRow("Custom Colors", colors_grid)

        restore_btn = QPushButton("Restore Gantt Defaults")
        restore_btn.clicked.connect(self.restore_gantt_defaults)
        g_layout.addRow(restore_btn)

        layout.addWidget(gantt_card)

        # 3b. WBS & Project Planning Hierarchy Appearance Card
        self.wbs_custom_service = WBSCustomizationService(self.settings_manager)
        is_dark_pref = str(self.settings_manager.get("theme", "dark") or "dark").lower() not in ("light", "warm_paper")
        self.wbs_settings_widget = WBSSettingsWidget(self.wbs_custom_service, is_dark=is_dark_pref)
        layout.addWidget(self.wbs_settings_widget)

        # 4. UX Safety & Delete Confirmation Card
        layout = system_layout

        # ------------------------------------------------------------
        # Language & Region — first card on the System tab
        # ------------------------------------------------------------
        language_card = QFrame()
        language_card.setObjectName("CardWidget")
        lang_layout = QFormLayout(language_card)
        lang_t = LanguageService.instance().t
        lang_title = QLabel(" " + lang_t("Language & Region"))
        lang_title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(lang_title, delta_pt=4, weight="bold")
        lang_layout.addRow(lang_title)

        lang_help = QLabel(
            lang_t(
                "UI Language changes apply instantly to the navigation, "
                "header bar and menus. Restart Todo Bird to translate "
                "every window."
            )
        )
        lang_help.setWordWrap(True)
        lang_help.setObjectName("SettingsHelperText")
        lang_layout.addRow(lang_help)

        self.ui_language_combo = QComboBox()
        self._language_codes = []
        svc = LanguageService.instance()
        current_language = svc.current_language()
        for code, native, _english, flag, _rtl in LanguageService.available_languages():
            self.ui_language_combo.addItem(f"{flag}  {native}", code)
            self._language_codes.append(code)
        lang_idx = self._language_codes.index(current_language) if current_language in self._language_codes else 0
        self.ui_language_combo.setCurrentIndex(lang_idx)
        lang_layout.addRow(lang_t("UI Language"), self.ui_language_combo)

        def _on_ui_language_changed(index: int):
            code = self.ui_language_combo.itemData(index)
            if code:
                LanguageService.instance().set_language(str(code))

        self.ui_language_combo.currentIndexChanged.connect(_on_ui_language_changed)

        self.region_country_combo = QComboBox()
        self._region_codes = []
        self.region_country_combo.addItem("—", "")
        self._region_codes.append("")
        for code, name, flag in RegionService.available_countries():
            self.region_country_combo.addItem(f"{flag}  {name}", code)
            self._region_codes.append(code)
        saved_region = str(self.settings_manager.get("region_country", "") or "")
        region_idx = self._region_codes.index(saved_region) if saved_region in self._region_codes else 0
        self.region_country_combo.setCurrentIndex(region_idx)
        self.region_country_combo.setMinimumContentsLength(28)
        self.region_country_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        lang_layout.addRow(lang_t("Country / Region"), self.region_country_combo)

        def _on_region_changed(index: int):
            code = self.region_country_combo.itemData(index) or ""
            self.settings_manager.set("region_country", str(code))

        self.region_country_combo.currentIndexChanged.connect(_on_region_changed)

        self.region_defaults_button = QPushButton(lang_t("Apply Region Defaults"))
        self.region_defaults_button.setObjectName("SecondaryButton")
        self.region_defaults_button.setToolTip(
            lang_t(
                "Region defaults set the working week and 12/24-hour clock "
                "for the selected country."
            )
        )
        lang_layout.addRow("", self.region_defaults_button)

        def _apply_region_defaults():
            code = str(self.region_country_combo.currentData() or "")
            if not code:
                return
            RegionService.apply_region_defaults(self.settings_manager, code)
            profile = RegionService.profile_for(code)
            if hasattr(self, "day_checkboxes") and self.working_week_service:
                try:
                    current_days = set(self.working_week_service.get_working_weekdays())
                    for day_code, cb in self.day_checkboxes.items():
                        cb.blockSignals(True)
                        cb.setChecked(day_code in current_days)
                        cb.blockSignals(False)
                except Exception:
                    pass
            try:
                from todo_bird_app.widgets.toast_banner import ToastBanner
                ToastBanner.show_message(
                    self,
                    f"{RegionService.country_flag(code)} {RegionService.country_name(code)}",
                    "success",
                )
            except Exception:
                pass

        self.region_defaults_button.clicked.connect(_apply_region_defaults)

        layout.addWidget(language_card)

        safety_card = QFrame()
        safety_card.setObjectName("CardWidget")
        s_layout = QFormLayout(safety_card)
        s_title = QLabel(" UX Safety & Task Deletion Protection")
        s_title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(s_title, delta_pt=4, weight="bold")
        s_layout.addRow(s_title)

        self.cb_confirm_del = QCheckBox("Confirm before deleting tasks")
        self.cb_confirm_del.setChecked(self.settings_manager.get("confirm_delete_task", True))
        self.cb_confirm_del.toggled.connect(lambda val: self.settings_manager.set("confirm_delete_task", val))
        s_layout.addRow(self.cb_confirm_del)

        layout.addWidget(safety_card)

        # 5. Delay Intelligence Rules Card
        delay_card = QFrame()
        delay_card.setObjectName("CardWidget")
        d_layout = QFormLayout(delay_card)
        d_title = QLabel("⏳ Delay Intelligence & Threshold Rules")
        d_title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(d_title, delta_pt=4, weight="bold")
        d_layout.addRow(d_title)

        self.spin_tol = QSpinBox()
        self.spin_tol.setRange(0, 30)
        self.spin_tol.setValue(self.settings_manager.get("on_time_tolerance_minutes", 5))
        self.spin_tol.valueChanged.connect(lambda v: self.settings_manager.set("on_time_tolerance_minutes", v))
        d_layout.addRow("On-Time Tolerance (mins)", self.spin_tol)

        self.spin_slight = QSpinBox()
        self.spin_slight.setRange(1, 60)
        self.spin_slight.setValue(self.settings_manager.get("slight_delay_minutes", 15))
        self.spin_slight.valueChanged.connect(lambda v: self.settings_manager.set("slight_delay_minutes", v))
        d_layout.addRow("Slight Delay Threshold (mins)", self.spin_slight)

        self.spin_mod = QSpinBox()
        self.spin_mod.setRange(1, 120)
        self.spin_mod.setValue(self.settings_manager.get("moderate_delay_minutes", 30))
        self.spin_mod.valueChanged.connect(lambda v: self.settings_manager.set("moderate_delay_minutes", v))
        d_layout.addRow("Moderate Delay Threshold (mins)", self.spin_mod)

        self.spin_sev = QSpinBox()
        self.spin_sev.setRange(1, 300)
        self.spin_sev.setValue(self.settings_manager.get("severe_delay_minutes", 60))
        self.spin_sev.valueChanged.connect(lambda v: self.settings_manager.set("severe_delay_minutes", v))
        d_layout.addRow("Severe Delay Threshold (mins)", self.spin_sev)

        self.cb_req_sev = QCheckBox("Require Justification for Severe Delays")
        self.cb_req_sev.setChecked(self.settings_manager.get("require_justification_severe", True))
        self.cb_req_sev.toggled.connect(lambda chk: self.settings_manager.set("require_justification_severe", chk))
        d_layout.addRow(self.cb_req_sev)

        planning_layout.addWidget(delay_card)

        # 6. Behavioral Appreciation System Card
        apprec_card = QFrame()
        apprec_card.setObjectName("CardWidget")
        ap_layout = QFormLayout(apprec_card)
        ap_title = QLabel(" Positive Feedback & Appreciation System")
        ap_title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(ap_title, delta_pt=4, weight="bold")
        ap_layout.addRow(ap_title)

        self.cb_apprec = QCheckBox("Enable Positive Feedback & Appreciation")
        self.cb_apprec.setChecked(self.settings_manager.get("appreciation_enabled", True))
        self.cb_apprec.toggled.connect(lambda chk: self.settings_manager.set("appreciation_enabled", chk))
        ap_layout.addRow(self.cb_apprec)

        self.cb_voice_apprec = QCheckBox("Voice Speech Synthesis for Appreciation")
        self.cb_voice_apprec.setChecked(self.settings_manager.get("voice_appreciation_enabled", True))
        self.cb_voice_apprec.toggled.connect(lambda chk: self.settings_manager.set("voice_appreciation_enabled", chk))
        ap_layout.addRow(self.cb_voice_apprec)

        self.apprec_level_combo = QComboBox()
        self.apprec_level_combo.addItems(["Minimal", "Balanced", "Encouraging"])
        self.apprec_level_combo.setCurrentText(self.settings_manager.get("appreciation_level", "balanced").capitalize())
        self.apprec_level_combo.currentTextChanged.connect(lambda txt: self.settings_manager.set("appreciation_level", txt.lower()))
        ap_layout.addRow("Appreciation Frequency", self.apprec_level_combo)

        layout.addWidget(apprec_card)

        # 7. Linux Desktop Launcher Integration Card
        dt_card = QFrame()
        dt_card.setObjectName("CardWidget")
        dt_layout = QFormLayout(dt_card)
        dt_title = QLabel(" Ubuntu Desktop Launcher & Autostart")
        dt_title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(dt_title, delta_pt=4, weight="bold")
        dt_layout.addRow(dt_title)

        install_dt_btn = QPushButton("Install Desktop Application Launcher (.desktop)")
        install_dt_btn.setObjectName("PrimaryButton")
        install_dt_btn.clicked.connect(self.install_desktop_launchers)
        dt_layout.addRow(install_dt_btn)

        self.cb_autostart = QCheckBox("Launch Todo Bird automatically at login")
        self.cb_autostart.setChecked(self.settings_manager.get("autostart_at_login", False))
        self.cb_autostart.toggled.connect(self.toggle_autostart)
        dt_layout.addRow(self.cb_autostart)

        layout.addWidget(dt_card)

        # 8. Database Backup Card
        db_card = QFrame()
        db_card.setObjectName("CardWidget")
        db_layout = QHBoxLayout(db_card)
        db_lbl = QLabel(" SQLite Local Database Backup")
        db_lbl.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(db_lbl, delta_pt=3, weight="bold")
        backup_btn = QPushButton("Create Database Backup")
        backup_btn.setObjectName("PrimaryButton")
        backup_btn.clicked.connect(self.create_backup)

        db_layout.addWidget(db_lbl)
        db_layout.addStretch()
        db_layout.addWidget(backup_btn)
        layout.addWidget(db_card)

        for page_layout in self._settings_page_layouts:
            page_layout.addStretch(1)

        self.main_layout.addWidget(self.settings_tabs, 1)
        self._apply_settings_window_polish()
        self._sync_theme_accent_buttons()
        self.retranslate_ui()
        self.setUpdatesEnabled(True)

    def refresh_data(self):
        mode = str(self.settings_manager.get("theme", "dark") or "dark").lower().strip()
        if hasattr(self, "theme_combo"):
            self.theme_combo.blockSignals(True)
            idx = self.theme_combo.findData(mode)
            if idx >= 0:
                self.theme_combo.setCurrentIndex(idx)
            self.theme_combo.blockSignals(False)

        # Phase 1F.6.1 — keep navigation controls synchronized without
        # firing live-change handlers during refresh.
        for attr_name, setting_key, default in (
            (
                "navigation_position_combo",
                "navigation_position",
                "left",
            ),
            (
                "navigation_style_combo",
                "navigation_style",
                "expanded",
            ),
            (
                "navigation_alignment_combo",
                "navigation_alignment",
                "left",
            ),
        ):
            if hasattr(self, attr_name):
                combo = getattr(self, attr_name)
                value = str(
                    self.settings_manager.get(
                        setting_key,
                        default,
                    )
                    or default
                )
                idx = combo.findData(value)
                if idx >= 0:
                    combo.blockSignals(True)
                    combo.setCurrentIndex(idx)
                    combo.blockSignals(False)

        # Typography / pinned appearance persistence
        if hasattr(self, "theme_combo"):
            theme = str(
                self.settings_manager.get(
                    "theme",
                    "dark",
                )
                or "dark"
            ).lower().strip()
            self.theme_combo.blockSignals(True)
            idx = self.theme_combo.findData(theme)
            if idx >= 0:
                self.theme_combo.setCurrentIndex(idx)
            self.theme_combo.blockSignals(False)

        if hasattr(self, "accent_combo"):
            accent_scheme = str(
                self.settings_manager.get(
                    "accent_scheme",
                    "",
                )
                or ""
            ).lower()
            idx = self.accent_combo.findData(accent_scheme)
            if idx >= 0:
                self.accent_combo.blockSignals(True)
                self.accent_combo.setCurrentIndex(idx)
                self.accent_combo.blockSignals(False)

        if hasattr(self, "btn_design_combo"):
            btn_style = str(
                self.settings_manager.get(
                    "button_design_mode",
                    "3d_raised",
                )
                or "3d_raised"
            )
            idx = self.btn_design_combo.findData(btn_style)
            if idx >= 0:
                self.btn_design_combo.blockSignals(True)
                self.btn_design_combo.setCurrentIndex(idx)
                self.btn_design_combo.blockSignals(False)

        if hasattr(self, "density_combo"):
            density = str(
                self.settings_manager.get(
                    "ui_density",
                    "balanced",
                )
                or "balanced"
            )
            idx = self.density_combo.findData(density)
            if idx >= 0:
                self.density_combo.blockSignals(True)
                self.density_combo.setCurrentIndex(idx)
                self.density_combo.blockSignals(False)

        if hasattr(self, "font_family_combo"):
            family = str(
                self.settings_manager.get(
                    "ui_font_family",
                    QApplication.font().family(),
                )
            )
            idx = self.font_family_combo.findText(
                family
            )
            if idx >= 0:
                self.font_family_combo.blockSignals(True)
                self.font_family_combo.setCurrentIndex(idx)
                self.font_family_combo.blockSignals(False)

        if hasattr(self, "font_size_spin"):
            try:
                size = int(
                    self.settings_manager.get(
                        "ui_font_size",
                        10,
                    )
                )
            except (TypeError, ValueError):
                size = 10

            self.font_size_spin.blockSignals(True)
            self.font_size_spin.setValue(size)
            self.font_size_spin.blockSignals(False)

        if hasattr(self, "font_weight_combo"):
            weight = str(
                self.settings_manager.get(
                    "ui_font_weight",
                    "normal",
                )
            )
            idx = self.font_weight_combo.findData(
                weight
            )
            if idx >= 0:
                self.font_weight_combo.blockSignals(True)
                self.font_weight_combo.setCurrentIndex(idx)
                self.font_weight_combo.blockSignals(False)

        if hasattr(self, "pinned_style_combo"):
            pin_style = str(
                self.settings_manager.get(
                    "pinned_card_style",
                    "auto",
                )
            )
            idx = self.pinned_style_combo.findData(
                pin_style
            )
            if idx >= 0:
                self.pinned_style_combo.blockSignals(True)
                self.pinned_style_combo.setCurrentIndex(idx)
                self.pinned_style_combo.blockSignals(False)

        if hasattr(self, "bg_mode_combo"):
            self._load_background_controls()

        g_mode = self.settings_manager.get("gantt_theme_mode", "follow_app")
        mode_text = g_mode.replace("_", " ").title()
        self.gantt_mode_combo.setCurrentText(mode_text if mode_text != "Follow App" else "Follow Application Theme")

        current_working_days = set(self.working_week_service.get_working_weekdays())
        for code, cb in self.day_checkboxes.items():
            cb.blockSignals(True)
            cb.setChecked(code in current_working_days)
            cb.blockSignals(False)

        if hasattr(self, "capacity_hours_spin") and hasattr(self, "capacity_mins_spin"):
            cap_m = int(self.settings_manager.get("default_daily_capacity_minutes", 480) or 480)
            self.capacity_hours_spin.blockSignals(True)
            self.capacity_mins_spin.blockSignals(True)
            self.capacity_hours_spin.setValue(cap_m // 60)
            self.capacity_mins_spin.setValue(cap_m % 60)
            self.capacity_hours_spin.blockSignals(False)
            self.capacity_mins_spin.blockSignals(False)

        self._sync_theme_accent_buttons()

    def refresh_audio_output_options(self):
        if not hasattr(self, "combo_audio_output"):
            return

        from todo_bird_app.services.avocet_voice_service import AvocetVoiceService

        current = str(
            self.settings_manager.get("audio_output_device", "auto")
            or "auto"
        )
        self._loading_audio_output_options = True
        self.combo_audio_output.blockSignals(True)
        self.combo_audio_output.clear()
        self.combo_audio_output.addItem("Automatic audible device", "auto")
        self.combo_audio_output.addItem("System default sink", "system_default")

        system_default = AvocetVoiceService.get_default_audio_sink()
        for sink in AvocetVoiceService.list_audio_sinks():
            name = sink.get("name", "")
            if not name:
                continue
            desc = sink.get("description") or name
            active_port = sink.get("active_port") or ""
            suffix_parts = []
            if name == system_default:
                suffix_parts.append("system default")
            if active_port:
                suffix_parts.append(active_port)
            if sink.get("muted"):
                suffix_parts.append("muted")
            suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
            self.combo_audio_output.addItem(f"{desc}{suffix}", name)

        idx = self.combo_audio_output.findData(current)
        if idx < 0 and current not in ("auto", "system_default"):
            self.combo_audio_output.addItem(f"Configured sink unavailable: {current}", current)
            idx = self.combo_audio_output.findData(current)
        if idx >= 0:
            self.combo_audio_output.setCurrentIndex(idx)
        else:
            self.combo_audio_output.setCurrentIndex(0)

        self.combo_audio_output.blockSignals(False)
        self._loading_audio_output_options = False

    def on_audio_output_changed(self, _index: int = -1):
        if getattr(self, "_loading_audio_output_options", False):
            return
        if hasattr(self, "combo_audio_output"):
            self.settings_manager.set(
                "audio_output_device",
                self.combo_audio_output.currentData() or "auto"
            )

    def on_refresh_audio_outputs(self):
        self.refresh_audio_output_options()
        ToastBanner.show_message(
            self,
            "Audio output devices refreshed.",
            "info"
        )

    def on_startup_voice_frequency_changed(self, _index: int = -1):
        if hasattr(self, "combo_greeting_mode"):
            self.settings_manager.set(
                "greeting_mode",
                self.combo_greeting_mode.currentData() or "once_daily"
            )

    def save_companion_settings(self):
        if hasattr(self, "cb_companion_enabled"):
            self.settings_manager.set(
                "companion_enabled",
                self.cb_companion_enabled.isChecked()
            )
        if hasattr(self, "cb_voice_enabled"):
            self.settings_manager.set(
                "voice_enabled",
                self.cb_voice_enabled.isChecked()
            )
        if hasattr(self, "companion_avatar_combo"):
            av_text = self.companion_avatar_combo.currentText().lower()
            mode = "default"
            if "custom" in av_text:
                mode = "custom"
            elif "disabled" in av_text:
                mode = "disabled"
            self.settings_manager.set("companion_avatar_mode", mode)

        if hasattr(self, "current_avatar_path"):
            self.settings_manager.set(
                "companion_custom_avatar_path",
                self.current_avatar_path
            )

        if hasattr(self, "companion_activity_combo"):
            self.settings_manager.set(
                "companion_activity_level",
                self.companion_activity_combo.currentText().lower()
            )

        if hasattr(self, "greeting_freq_combo"):
            freq_text = self.greeting_freq_combo.currentText().lower()
            freq = "once_per_day"
            if "launch" in freq_text or "session" in freq_text:
                freq = "once_per_session"
            elif "never" in freq_text:
                freq = "never"
            self.settings_manager.set("companion_greeting_frequency", freq)

        if hasattr(self, "greeting_schedule_combo"):
            sched_text = self.greeting_schedule_combo.currentText().lower()
            sched = "day_by_day"
            if "same" in sched_text:
                sched = "same_every_day"
            elif "date" in sched_text:
                sched = "date_specific"
            self.settings_manager.set("companion_greeting_schedule_mode", sched)

        if hasattr(self, "combo_greeting_mode"):
            self.settings_manager.set(
                "greeting_mode",
                self.combo_greeting_mode.currentData() or "once_daily"
            )
        if hasattr(self, "spin_companion_visible"):
            self.settings_manager.set("companion_visible_seconds", self.spin_companion_visible.value())
        if hasattr(self, "edit_assistant_name"):
            self.settings_manager.set("assistant_name", self.edit_assistant_name.text().strip())
        if hasattr(self, "edit_user_salutation"):
            self.settings_manager.set("user_salutation", self.edit_user_salutation.text().strip())
        if hasattr(self, "cb_greet_morning"):
            self.settings_manager.set("greeting_morning_enabled", self.cb_greet_morning.isChecked())
        if hasattr(self, "cb_greet_afternoon"):
            self.settings_manager.set("greeting_afternoon_enabled", self.cb_greet_afternoon.isChecked())
        if hasattr(self, "cb_greet_evening"):
            self.settings_manager.set("greeting_evening_enabled", self.cb_greet_evening.isChecked())
        if hasattr(self, "cb_greet_night"):
            self.settings_manager.set("greeting_night_enabled", self.cb_greet_night.isChecked())
        if hasattr(self, "cb_devotional_intro"):
            self.settings_manager.set("devotional_intro", self.cb_devotional_intro.isChecked())
        if hasattr(self, "devotional_intro_edit"):
            self.settings_manager.set(
                "devotional_intro_text",
                self.devotional_intro_edit.text().strip(),
            )
        if hasattr(self, "morning_message_edit"):
            self.settings_manager.set("custom_greeting_morning", self.morning_message_edit.toPlainText().strip())
        if hasattr(self, "afternoon_message_edit"):
            self.settings_manager.set("custom_greeting_afternoon", self.afternoon_message_edit.toPlainText().strip())
        if hasattr(self, "evening_message_edit"):
            self.settings_manager.set("custom_greeting_evening", self.evening_message_edit.toPlainText().strip())
        if hasattr(self, "night_message_edit"):
            self.settings_manager.set("custom_greeting_night", self.night_message_edit.toPlainText().strip())

        if hasattr(self, "combo_voice_profile"):
            vp_id = self.combo_voice_profile.currentData() or "durga"
            self.settings_manager.set("active_voice_profile", vp_id)
        if hasattr(self, "combo_audio_output"):
            self.settings_manager.set(
                "audio_output_device",
                self.combo_audio_output.currentData() or "auto"
            )
        if hasattr(self, "combo_tone_style"):
            ts_id = self.combo_tone_style.currentData() or "custom"
            self.settings_manager.set("active_tone_style", ts_id)

        ToastBanner.show_message(
            self,
            "Companion settings saved successfully.",
            "success"
        )

    def on_test_durga_voice(self):
        from todo_bird_app.services.avocet_voice_service import AvocetVoiceService
        ToastBanner.show_message(self, "Playing Durga test voice...", "info")
        AvocetVoiceService.test_durga_voice(self.settings_manager)

    def on_test_startup_greeting(self):
        from todo_bird_app.services.avocet_voice_service import AvocetVoiceService
        ToastBanner.show_message(self, "Playing startup greeting test...", "info")
        AvocetVoiceService.test_startup_greeting(self.settings_manager)

    def on_reset_spoken_today(self):
        from todo_bird_app.services.avocet_voice_service import AvocetVoiceService
        AvocetVoiceService.reset_spoken_today(self.settings_manager)
        ToastBanner.show_message(self, "Spoken-today status reset for all time periods.", "success")

    def on_preview_voice(self):
        from todo_bird_app.services.avocet_voice_service import AvocetVoiceService
        voice_id = self.combo_voice_profile.currentData() or "durga"
        profile = AvocetVoiceService.VOICE_PROFILES.get(voice_id, {})
        display = profile.get("name", voice_id)
        ToastBanner.show_message(self, f"Playing sample greeting in {display}'s voice...", "info")
        AvocetVoiceService.preview_voice_profile(voice_id, self.settings_manager)

    def on_tone_style_changed(self):
        from todo_bird_app.services.avocet_voice_service import AvocetVoiceService
        ts_id = self.combo_tone_style.currentData() or "custom"
        self.settings_manager.set("active_tone_style", ts_id)

        # If user picked a curated tone style, populate the message boxes
        if ts_id in AvocetVoiceService.TONE_STYLES and ts_id != "custom":
            style = AvocetVoiceService.TONE_STYLES[ts_id]
            if hasattr(self, "morning_message_edit") and "morning" in style:
                self.morning_message_edit.setPlainText(style["morning"])
            if hasattr(self, "afternoon_message_edit") and "afternoon" in style:
                self.afternoon_message_edit.setPlainText(style["afternoon"])
            if hasattr(self, "evening_message_edit") and "evening" in style:
                self.evening_message_edit.setPlainText(style["evening"])
            if hasattr(self, "night_message_edit") and "night" in style:
                self.night_message_edit.setPlainText(style["night"])
            ToastBanner.show_message(self, f"Loaded {style['name']} greeting templates.", "info")

    def on_working_days_changed(self):
        selected_days = [code for code, cb in self.day_checkboxes.items() if cb.isChecked()]
        self.working_week_service.set_working_weekdays(selected_days)
        day_abbrs = [name[:3] for code, name in WEEKDAY_NAMES if code in selected_days]
        summary = ", ".join(day_abbrs) if day_abbrs else "None"
        if hasattr(self, "ww_status_badge"):
            self.ww_status_badge.setText(f"Work calendar active: {summary}")
    def on_capacity_changed(self):
        mins = self.capacity_hours_spin.value() * 60 + self.capacity_mins_spin.value()
        self.settings_manager.set("default_daily_capacity_minutes", mins)
        if hasattr(self, "ww_status_badge"):
            h = mins // 60
            m = mins % 60
            self.ww_status_badge.setText(f"Capacity saved ({h}h {m}m/day)")
    def on_opacity_changed(self, value: int):
        self.opacity_label.setText(f"{value}%")
        self.settings_manager.set("weekend_opacity", value)

    def pick_gantt_color(self, key: str, btn: QPushButton):
        curr_hex = self.custom_colors.get(key, DEFAULT_GANTT_COLORS.get(key, "#3584E4"))
        col = QColorDialog.getColor(initial=curr_hex, parent=self)
        if col.isValid():
            hex_val = col.name()
            self.custom_colors[key] = hex_val
            btn.setText(hex_val)
            btn.setStyleSheet(f"background-color: {hex_val}; color: {text_color_on(hex_val)}; font-weight: 600; border-radius: 6px; padding: 4px 12px;")
            self.settings_manager.set("gantt_custom_colors", self.custom_colors)
            self.settings_manager.set("gantt_theme_mode", "custom")
            self.gantt_mode_combo.setCurrentText("Custom")

    def on_gantt_mode_changed(self, text: str):
        mode = text.lower().replace(" ", "_")
        if mode == "follow_application_theme":
            mode = "follow_app"
        self.settings_manager.set("gantt_theme_mode", mode)

    def restore_gantt_defaults(self):
        self.custom_colors = dict(DEFAULT_GANTT_COLORS)
        self.settings_manager.set("gantt_custom_colors", self.custom_colors)
        self.settings_manager.set("gantt_theme_mode", "follow_app")
        self.gantt_mode_combo.setCurrentText("Follow Application Theme")

        for key, btn in self.color_buttons.items():
            val = DEFAULT_GANTT_COLORS.get(key, "#3584E4")
            btn.setText(val)
            btn.setStyleSheet(f"background-color: {val}; color: {text_color_on(val)}; font-weight: 600; border-radius: 6px; padding: 4px 12px;")

        self._update_font_preview()

    def _update_font_preview(self):
        if not hasattr(self, "font_preview"):
            return

        family = (
            self.font_family_combo.currentText()
            if hasattr(self, "font_family_combo")
            else QApplication.font().family()
        )

        size = (
            self.font_size_spin.value()
            if hasattr(self, "font_size_spin")
            else 10
        )

        weight_name = (
            self.font_weight_combo.currentData()
            if hasattr(self, "font_weight_combo")
            else "normal"
        ) or "normal"

        weight_map = {
            "normal": QFont.Weight.Normal,
            "medium": QFont.Weight.Medium,
            "semibold": QFont.Weight.DemiBold,
        }

        preview_font = QFont(family)
        preview_font.setPointSize(size)
        preview_font.setWeight(
            weight_map.get(
                weight_name,
                QFont.Weight.Normal,
            )
        )

        # Explicit font assignment means this preview does not
        # depend on application-theme inheritance.
        self.font_preview.setFont(preview_font)

        self.font_preview.setText(
            f"Todo Bird Preview — {family} — {size} pt  •  "
            "Project • Task • Gantt • 23% • Pin"
        )

    def _apply_live_appearance(self):
        self._update_font_preview()

        if getattr(self, "_appearance_apply_pending", False):
            return

        self._appearance_apply_pending = True
        QTimer.singleShot(0, self._flush_live_appearance)

    def _flush_live_appearance(self):
        self._appearance_apply_pending = False
        if getattr(self, "_base_cleaned_up", False):
            return

        app_window = self.window()

        if hasattr(app_window, "theme_controller"):
            app_window.theme_controller.apply_theme()

        # Repaint all existing pinned workspaces immediately.
        app = QApplication.instance()
        if app is not None:
            try:
                from todo_bird_app.widgets.pinned_priorities_widget import (
                    PinnedPrioritiesWidget,
                )

                for widget in app.allWidgets():
                    if isinstance(
                        widget,
                        PinnedPrioritiesWidget,
                    ):
                        widget.refresh_data()
            except Exception:
                pass

    def on_font_family_changed(self, family: str):
        if not family:
            return

        self.settings_manager.set(
            "ui_font_family",
            family,
        )

        self._apply_live_appearance()

    def on_font_size_changed(self, value: int):
        self.settings_manager.set(
            "ui_font_size",
            int(value),
        )

        self._apply_live_appearance()

    def on_font_weight_changed(self, _index: int):
        value = (
            self.font_weight_combo.currentData()
            or "normal"
        )

        self.settings_manager.set(
            "ui_font_weight",
            value,
        )

        self._apply_live_appearance()

    def on_pinned_style_changed(self, _index: int):
        value = (
            self.pinned_style_combo.currentData()
            or "auto"
        )

        self.settings_manager.set(
            "pinned_card_style",
            value,
        )

        # This does not need to rebuild the whole application
        # theme, but refreshing here also updates font preview.
        self._apply_live_appearance()

    def on_theme_changed(self, index_or_text=None):
        mode = str(self.theme_combo.currentData() or "").lower().strip()
        if mode not in THEME_MODES:
            raw_text = self.theme_combo.currentText()
            mode = "dark"
            for code, label in AppearanceService.known_theme_items():
                if label.lower() == raw_text.lower():
                    mode = code
                    break

        idx = self.theme_combo.findData(mode)
        if idx >= 0 and self.theme_combo.currentIndex() != idx:
            self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(idx)
            self.theme_combo.blockSignals(False)

        is_dark = mode in {"dark", "oled", "nord"}
        if mode == "system":
            is_dark = is_system_dark()

        if hasattr(self, "wbs_settings_widget"):
            accent = self.settings_manager.get("accent_color", "#3584E4")
            self.wbs_settings_widget.set_theme(is_dark=is_dark, accent_color=accent)

        app = self.window()
        if hasattr(app, "theme_controller") and app.theme_controller:
            app.theme_controller.apply_theme(mode=mode)
        else:
            self.settings_manager.set("theme", mode)
            self._apply_live_appearance()
        self._sync_theme_accent_buttons()

    def on_accent_changed(self, text: str):
        scheme = str(
            self.accent_combo.currentData()
            or ""
        ).lower()
        if scheme in ACCENT_SCHEMES:
            color = ACCENT_SCHEMES[scheme][1]
        else:
            color = "#E95420"

        if hasattr(self, "wbs_settings_widget"):
            is_dark = (str(self.settings_manager.get("theme", "dark")).lower() == "dark")
            self.wbs_settings_widget.set_theme(is_dark=is_dark, accent_color=color)

        app = self.window()
        if hasattr(app, "theme_controller") and app.theme_controller:
            app.theme_controller.apply_theme(
                accent_scheme=scheme,
                accent_color=color,
            )
        else:
            self.settings_manager.set("accent_scheme", scheme)
            self.settings_manager.set("color_scheme", scheme)
            self.settings_manager.set("accent_color", color)
            self._apply_live_appearance()
        self._sync_theme_accent_buttons()

    def install_desktop_launchers(self):
        success = get_platform_service().create_desktop_launcher()
        if success:
            msg = "Desktop launcher created"
        else:
            msg = "Failed to create launcher"
        if success:
            QMessageBox.information(self, "Launcher Created", msg)
        else:
            QMessageBox.critical(self, "Error Creating Launcher", msg)

    def toggle_autostart(self, enabled: bool):
        self.settings_manager.set("autostart_at_login", enabled)
        get_platform_service().create_autostart_entry(enabled)

    def create_backup(self):
        try:
            db_file = Path(self.db_manager.db_path)
            backup_file = db_file.parent / f"todo_bird_backup.db"
            shutil.copy(db_file, backup_file)
            QMessageBox.information(self, "Backup Successful", f"Database backed up to:\n{backup_file}")
        except Exception as e:
            QMessageBox.critical(self, "Backup Failed", str(e))

    # -------------------------------------------------
    # Canonical Background Handlers
    # -------------------------------------------------
    def _current_background_view_id(self) -> str:
        app_win = self.window()
        nav = getattr(app_win, "navigation_controller", None)
        view_id = getattr(nav, "current_section", None)
        return str(view_id or "settings").strip().lower()

    def _background_scope(self) -> str:
        if not hasattr(self, "bg_apply_to_combo"):
            return "global"
        return str(self.bg_apply_to_combo.currentData() or "global")

    def _background_target_config(self):
        if self._background_scope() == "view":
            return BackgroundService.effective_config(
                self.settings_manager,
                self._current_background_view_id(),
            )
        return BackgroundService.global_config(self.settings_manager)

    def _set_background_row_visible(self, field_widget, visible: bool):
        if field_widget is None:
            return
        field_widget.setVisible(visible)
        form = getattr(self, "_background_form", None)
        if form is not None:
            label = form.labelForField(field_widget)
            if label is not None:
                label.setVisible(visible)

    def _find_combo_data(self, combo, value):
        for idx in range(combo.count()):
            if combo.itemData(idx) == value:
                return idx
        return -1

    def _ensure_background_color_option(self, color_hex: str) -> int:
        color_hex = BackgroundService.normalize_color(color_hex)
        idx = self._find_combo_data(self.bg_color_combo, color_hex)
        if idx >= 0:
            return idx

        custom_idx = self._find_combo_data(self.bg_color_combo, "__custom__")
        insert_at = custom_idx if custom_idx >= 0 else self.bg_color_combo.count()
        self.bg_color_combo.insertItem(insert_at, f"Custom ({color_hex})", color_hex)
        return insert_at

    def _set_combo_data(self, combo, value):
        idx = self._find_combo_data(combo, value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _load_background_controls(self):
        if not hasattr(self, "bg_mode_combo"):
            return

        self._loading_background_controls = True
        try:
            view_id = self._current_background_view_id()
            scope = self._background_scope()
            config = self._background_target_config()

            view_label = BackgroundService.view_label(view_id)
            inherited = scope == "view" and config.inherited
            self.bg_current_view_label.setText(
                f"{view_label} (inherits global)"
                if inherited
                else (view_label if scope == "view" else "Entire App")
            )
            self.bg_current_view_label.setVisible(scope == "view")
            label = self._background_form.labelForField(self.bg_current_view_label)
            if label is not None:
                label.setVisible(scope == "view")

            self._set_combo_data(self.bg_mode_combo, config.mode)
            self._set_combo_data(self.bg_fit_combo, config.fit)
            self._set_combo_data(self.bg_overlay_combo, config.overlay_mode)

            color_idx = self._ensure_background_color_option(config.color)
            self.bg_color_combo.setCurrentIndex(color_idx)

            slider_value = int(round(config.opacity * 100))
            self.bg_opacity_slider.setValue(slider_value)
            self.bg_opacity_label.setText(f"{slider_value}%")
            self.current_bg_path = config.image

            self.btn_reset_bg_view.setEnabled(
                scope == "view"
                and BackgroundService.has_view_override(
                    self.settings_manager,
                    view_id,
                )
            )
            self.update_bg_preview()
            self._update_background_control_visibility(config.mode)
        finally:
            self._loading_background_controls = False

    def _update_background_control_visibility(self, mode: str):
        self._set_background_row_visible(
            self.bg_color_combo,
            mode == BACKGROUND_MODE_SOLID,
        )
        self._set_background_row_visible(
            self.bg_image_row_widget,
            mode == BACKGROUND_MODE_IMAGE,
        )
        self._set_background_row_visible(
            self.bg_fit_combo,
            mode == BACKGROUND_MODE_IMAGE,
        )
        self._set_background_row_visible(
            self.bg_overlay_combo,
            mode == BACKGROUND_MODE_IMAGE,
        )
        self._set_background_row_visible(
            self.bg_opacity_row_widget,
            mode
            in {
                BACKGROUND_MODE_SOLID,
                BACKGROUND_MODE_IMAGE,
                BACKGROUND_MODE_TRANSPARENT,
            },
        )

    def _write_background_changes(self, **changes):
        current = self._background_target_config()
        next_config = current.with_changes(**changes)
        if self._background_scope() == "view":
            BackgroundService.write_view_override(
                self.settings_manager,
                self._current_background_view_id(),
                next_config,
            )
        else:
            BackgroundService.write_global(self.settings_manager, next_config)
        self._load_background_controls()
        self._notify_bg_update()

    def update_bg_preview(self):
        if not hasattr(self, "bg_preview_label"):
            return
        config = self._background_target_config()
        self.bg_preview_label.clear()
        self.bg_preview_label.setPixmap(QPixmap())
        self.bg_preview_label.setStyleSheet(
            "border: 1px dashed #64748B; border-radius: 6px; "
            "background: rgba(0,0,0,0.04);"
        )

        if config.mode == BACKGROUND_MODE_IMAGE and config.image:
            pm = MediaService.load_pixmap(
                config.image,
                max_width=64,
                max_height=40,
                use_thumbnail=True,
            )
            if pm and not pm.isNull():
                self.bg_preview_label.setPixmap(pm)
                self.btn_remove_bg.setEnabled(True)
                return
            self.bg_preview_label.setText("Missing")
            self.btn_remove_bg.setEnabled(True)
            return

        if config.mode == BACKGROUND_MODE_SOLID:
            self.bg_preview_label.setText("")
            self.bg_preview_label.setStyleSheet(
                "border: 1px dashed #64748B; border-radius: 6px; "
                f"background-color: {config.color};"
            )
        elif config.mode == BACKGROUND_MODE_TRANSPARENT:
            self.bg_preview_label.setText(f"{int(config.opacity * 100)}%")
            self.bg_preview_label.setStyleSheet(
                "border: 1px dashed #64748B; border-radius: 6px; "
                "background: rgba(255,255,255,0.08);"
            )
        else:
            self.bg_preview_label.setText("Theme")
            self.bg_preview_label.setStyleSheet(
                "border: 1px dashed #64748B; border-radius: 6px; "
                "background: rgba(0,0,0,0.04);"
            )
        self.btn_remove_bg.setEnabled(False)

    def on_bg_apply_target_changed(self, _index: int):
        if getattr(self, "_loading_background_controls", False):
            return
        self._load_background_controls()
        self._notify_bg_update()

    def on_bg_mode_changed(self, _index: int):
        if getattr(self, "_loading_background_controls", False):
            return
        mode = str(self.bg_mode_combo.currentData() or BACKGROUND_MODE_THEME_DEFAULT)
        default_opacity = 0.22 if mode == BACKGROUND_MODE_TRANSPARENT else self._background_target_config().opacity
        self._write_background_changes(mode=mode, opacity=default_opacity)

    def on_bg_color_changed(self, _index: int):
        if getattr(self, "_loading_background_controls", False):
            return
        value = self.bg_color_combo.currentData()
        if value == "__custom__":
            current = self._background_target_config()
            color = QColorDialog.getColor(
                QColor(current.color),
                self,
                "Choose Background Color",
            )
            if not color.isValid():
                self._load_background_controls()
                return
            value = BackgroundService.normalize_color(color.name(QColor.NameFormat.HexArgb))
        self._write_background_changes(
            mode=BACKGROUND_MODE_SOLID,
            color=BackgroundService.normalize_color(value),
        )

    def on_choose_bg_image(self):
        f_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Application Background Image",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.svg)",
        )
        if f_path:
            meta = MediaService.import_media(
                f_path,
                category="backgrounds",
                db_manager=self.db_manager,
            )
            if meta:
                self.current_bg_path = meta["relative_path"]
                self._write_background_changes(
                    mode=BACKGROUND_MODE_IMAGE,
                    image=self.current_bg_path,
                )

    def on_remove_bg_image(self):
        self.current_bg_path = ""
        changes = {"image": ""}
        if self._background_target_config().mode == BACKGROUND_MODE_IMAGE:
            changes["mode"] = BACKGROUND_MODE_THEME_DEFAULT
        self._write_background_changes(**changes)

    def on_bg_fit_changed(self, _index: int):
        if getattr(self, "_loading_background_controls", False):
            return
        self._write_background_changes(
            fit=str(self.bg_fit_combo.currentData() or "fill")
        )

    def on_bg_opacity_changed(self, val: int):
        self.bg_opacity_label.setText(f"{val}%")
        if getattr(self, "_loading_background_controls", False):
            return
        self._write_background_changes(opacity=val / 100.0)

    def on_bg_overlay_changed(self, _index: int):
        if getattr(self, "_loading_background_controls", False):
            return
        self._write_background_changes(
            overlay_mode=str(self.bg_overlay_combo.currentData() or "auto")
        )

    def on_reset_current_view_background(self):
        BackgroundService.clear_view_override(
            self.settings_manager,
            self._current_background_view_id(),
        )
        self._load_background_controls()
        self._notify_bg_update()

    def on_reset_all_backgrounds(self):
        BackgroundService.reset_all(self.settings_manager)
        self._load_background_controls()
        self._notify_bg_update()

    def _notify_bg_update(self):
        try:
            from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
            from todo_bird_app.services.appearance_service import AppearanceService
            appearance = AppearanceService.read(self.settings_manager, app=QApplication.instance())
            _GLOBAL_EVENT_BUS.appearance_changed.emit(appearance)
        except Exception:
            pass
        app_win = self.window()
        if hasattr(app_win, "update_background_overlay"):
            app_win.update_background_overlay()

    # -------------------------------------------------
    # Companion Avatar & Greeting Handlers (Batch 3.5)
    # -------------------------------------------------
    def update_avatar_preview(self):
        mode = str(self.settings_manager.get("companion_avatar_mode", "default")).lower()
        if mode == "custom" and self.current_avatar_path:
            pm = MediaService.load_pixmap(self.current_avatar_path, max_width=48, max_height=48, use_thumbnail=True)
            if pm and not pm.isNull():
                self.avatar_preview_label.setPixmap(pm)
                self.btn_remove_avatar.setEnabled(True)
                return
        elif mode == "disabled":
            self.avatar_preview_label.setText("Off")
            self.btn_remove_avatar.setEnabled(True)
            return
        self.avatar_preview_label.setText(" Bird")
        self.btn_remove_avatar.setEnabled(False)

    def on_avatar_mode_changed(self, text: str):
        if "Custom" in text:
            mode = "custom"
        elif "Disabled" in text:
            mode = "disabled"
        else:
            mode = "default"
        self.settings_manager.set("companion_avatar_mode", mode)
        self.update_avatar_preview()

    def on_choose_avatar_image(self):
        f_path, _ = QFileDialog.getOpenFileName(self, "Choose Companion Avatar Image", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp *.svg)")
        if f_path:
            meta = MediaService.import_media(f_path, category="companion", db_manager=self.db_manager)
            if meta:
                self.current_avatar_path = meta["relative_path"]
                self.settings_manager.set("companion_custom_avatar_path", self.current_avatar_path)
                self.settings_manager.set("companion_avatar_mode", "custom")
                self.companion_avatar_combo.blockSignals(True)
                self.companion_avatar_combo.setCurrentText("Custom Image")
                self.companion_avatar_combo.blockSignals(False)
                self.update_avatar_preview()

    def on_remove_avatar_image(self):
        self.current_avatar_path = ""
        self.settings_manager.set("companion_custom_avatar_path", "")
        self.settings_manager.set("companion_avatar_mode", "default")
        self.companion_avatar_combo.blockSignals(True)
        self.companion_avatar_combo.setCurrentText("Default Bird")
        self.companion_avatar_combo.blockSignals(False)
        self.update_avatar_preview()

    def on_activity_level_changed(self, text: str):
        self.settings_manager.set("companion_activity_level", text.lower())

    def on_greeting_freq_changed(self, text: str):
        if "launch" in text:
            freq = "once_per_session"
        elif "Never" in text:
            freq = "never"
        else:
            freq = "once_per_day"
        self.settings_manager.set("companion_greeting_frequency", freq)

    def on_greeting_schedule_mode_changed(self, text: str):
        if "Same" in text:
            sched = "same_every_day"
        elif "Date" in text:
            sched = "date_specific"
        else:
            sched = "day_by_day"
        self.settings_manager.set("companion_greeting_schedule_mode", sched)

    def load_greetings_table(self):
        if not hasattr(self, "greetings_table") or self.db_manager is None:
            return
        greetings = self.db_manager.get_all_greetings()
        g_map = {g["cycle_day"]: g for g in greetings if g.get("cycle_day") is not None}

        self.greetings_table.setRowCount(30)
        for day in range(1, 31):
            row_idx = day - 1
            data = g_map.get(day, {"cycle_day": day, "title": f"Day {day} Focus", "message": "Execute with clarity.", "image_path": "", "enabled": 1})

            item_day = QTableWidgetItem(f"Day {day:02d}")
            item_day.setTextAlignment(Qt.AlignCenter)
            self.greetings_table.setItem(row_idx, 0, item_day)

            img_p = data.get("image_path", "")
            img_item = QTableWidgetItem(" Yes" if img_p else "—")
            img_item.setTextAlignment(Qt.AlignCenter)
            self.greetings_table.setItem(row_idx, 1, img_item)

            item_title = QTableWidgetItem(data.get("title", ""))
            self.greetings_table.setItem(row_idx, 2, item_title)

            item_msg = QTableWidgetItem(data.get("message", ""))
            self.greetings_table.setItem(row_idx, 3, item_msg)

            item_status = QTableWidgetItem("Active" if data.get("enabled", 1) else "Off")
            item_status.setTextAlignment(Qt.AlignCenter)
            self.greetings_table.setItem(row_idx, 4, item_status)

    def on_edit_selected_greeting(self):
        curr_row = self.greetings_table.currentRow()
        if curr_row < 0:
            curr_row = 0
        day = curr_row + 1
        data = self.db_manager.get_greeting_by_day(day) or {"cycle_day": day, "title": f"Day {day} Focus", "message": "Execute with clarity.", "image_path": "", "enabled": 1}
        dlg = GreetingEditDialog(self, cycle_day=day, greeting_data=data, db_manager=self.db_manager)
        if dlg.exec() == QDialog.Accepted:
            new_data = dlg.get_greeting_data()
            self.db_manager.upsert_greeting(
                cycle_day=day,
                title=new_data["title"],
                message=new_data["message"],
                image_path=new_data["image_path"],
                enabled=new_data["enabled"]
            )
            self.load_greetings_table()

    def on_apply_greeting_to_selected_days(self):
        curr_row = self.greetings_table.currentRow()
        if curr_row < 0:
            curr_row = 0
        day = curr_row + 1
        source = self.db_manager.get_greeting_by_day(day)
        if not source:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Apply Day {day} to Multiple Days")
        d_layout = QVBoxLayout(dlg)
        d_layout.addWidget(QLabel(f"Select days to copy greeting from Day {day} ({source.get('title', '')}):"))

        checks = []
        grid = QHBoxLayout()
        for d in range(1, 31):
            cb = QCheckBox(f"D{d:02d}")
            if d != day:
                cb.setChecked(True)
            checks.append((d, cb))

        sub_v1 = QVBoxLayout()
        sub_v2 = QVBoxLayout()
        sub_v3 = QVBoxLayout()
        for i, (d, cb) in enumerate(checks):
            if i < 10:
                sub_v1.addWidget(cb)
            elif i < 20:
                sub_v2.addWidget(cb)
            else:
                sub_v3.addWidget(cb)
        grid.addLayout(sub_v1)
        grid.addLayout(sub_v2)
        grid.addLayout(sub_v3)
        d_layout.addLayout(grid)

        btn_box = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(dlg.reject)
        btn_apply = QPushButton("Apply to Selected")
        btn_apply.setObjectName("PrimaryButton")
        btn_apply.clicked.connect(dlg.accept)
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_apply)
        d_layout.addLayout(btn_box)

        if dlg.exec() == QDialog.Accepted:
            for target_d, cb in checks:
                if cb.isChecked() and target_d != day:
                    self.db_manager.upsert_greeting(
                        cycle_day=target_d,
                        title=source.get("title", ""),
                        message=source.get("message", ""),
                        image_path=source.get("image_path", ""),
                        enabled=source.get("enabled", 1)
                    )
            self.load_greetings_table()
            QMessageBox.information(self, "Applied", f"Greeting from Day {day} copied to selected days.")

    def on_duplicate_greeting_to_all(self):
        curr_row = self.greetings_table.currentRow()
        if curr_row < 0:
            curr_row = 0
        day = curr_row + 1
        source = self.db_manager.get_greeting_by_day(day)
        if not source:
            return
        reply = QMessageBox.question(
            self, "Duplicate Greeting",
            f"Duplicate Day {day} ('{source.get('title', '')}') to all 30 days?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            for d in range(1, 31):
                self.db_manager.upsert_greeting(
                    cycle_day=d,
                    title=source.get("title", ""),
                    message=source.get("message", ""),
                    image_path=source.get("image_path", ""),
                    enabled=source.get("enabled", 1)
                )
            self.load_greetings_table()
            QMessageBox.information(self, "Success", "Greeting duplicated across all 30 days.")

    def on_preview_today_greeting(self):
        greeting = CompanionService.get_effective_greeting(self.db_manager, self.settings_manager)
        avatar_pm = CompanionService.get_companion_avatar_pixmap(self.settings_manager, max_dim=48)
        title = greeting.get("title", "Good Day!")
        msg = greeting.get("message", "Welcome back. Let's make progress today.")
        img_p = greeting.get("image_path", "")
        dlg = GreetingPreviewDialog(self, title=title, message=msg, image_path=img_p, companion_avatar_pm=avatar_pm)
        dlg.exec()

    def showEvent(self, event):
        super().showEvent(event)
        # Refresh reminder window size controls from settings
        if hasattr(self, "rem_w_spin") and hasattr(self, "rem_h_spin") and hasattr(self, "rem_window_size_combo") and self.settings_manager:
            w = int(self.settings_manager.get("reminder_window_width", 540) or 540)
            h = int(self.settings_manager.get("reminder_window_height", 340) or 340)
            mode = str(self.settings_manager.get("reminder_window_size_mode", "standard") or "standard").lower().strip()

            self.rem_w_spin.blockSignals(True)
            self.rem_h_spin.blockSignals(True)
            self.rem_w_spin.setValue(w)
            self.rem_h_spin.setValue(h)
            self.rem_w_spin.blockSignals(False)
            self.rem_h_spin.blockSignals(False)

            c_idx = self.rem_window_size_combo.findData(mode)
            if c_idx >= 0 and self.rem_window_size_combo.currentIndex() != c_idx:
                self.rem_window_size_combo.blockSignals(True)
                self.rem_window_size_combo.setCurrentIndex(c_idx)
                self.rem_window_size_combo.blockSignals(False)

            self.rem_w_spin.setEnabled(mode == "custom")
            self.rem_h_spin.setEnabled(mode == "custom")
            if hasattr(self, "update_reminder_preview"):
                self.update_reminder_preview()
