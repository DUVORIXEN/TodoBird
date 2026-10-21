"""
TODO BIRD — ADD WORLD CLOCK DIALOG
Searchable country and city picker for adding new world clocks.
Supports live search, country filter, popular presets, and custom labels.
"""

from typing import Optional, Dict, Any, List

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from todo_bird_app.services.world_clock_service import (
    WorldClockItem,
    WorldClockService,
    country_code_to_flag,
    CLOCK_STYLES,
)


class AddWorldClockDialog(QDialog):
    """
    Modal dialog to search, preview, and add a world clock from any country.
    """

    clock_created = Signal(object)  # WorldClockItem

    def __init__(self, is_dark: bool = True, accent_color: str = "#2563EB", parent=None, region_country: str = ""):
        super().__init__(parent)
        self.is_dark = is_dark
        self.accent_color = accent_color
        self.created_clock: Optional[WorldClockItem] = None

        self.setWindowTitle("Add World Clock")
        self.setModal(True)
        self.resize(480, 520)

        self._all_countries = WorldClockService.get_all_countries()
        self._region_country = str(region_country or "").upper().strip()
        self._init_ui()
        self._populate_results()
        # A configured home region pre-seeds the search so the user's
        # country's cities are one click away.
        if self._region_country:
            region_name = ""
            for meta in self._all_countries:
                if str(meta.get("code", "")).upper() == self._region_country:
                    region_name = str(meta.get("name", ""))
                    break
            if region_name:
                self.search_edit.setText(region_name)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header Title
        title_lbl = QLabel("Add World Clock", self)
        title_lbl.setFont(QFont("Inter", 14, QFont.Bold))
        layout.addWidget(title_lbl)

        desc_lbl = QLabel("Search any country, city, or timezone across 249 nations.", self)
        desc_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(desc_lbl)

        # Search Box
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Search city or country (e.g. Tokyo, London, India, Brazil)...")
        self.search_edit.textChanged.connect(self._on_search_changed)
        layout.addWidget(self.search_edit)

        # Quick preset buttons row
        preset_box = QHBoxLayout()
        preset_box.setSpacing(6)
        preset_lbl = QLabel("Quick:", self)
        preset_lbl.setStyleSheet("font-size: 11px; color: #94A3B8; font-weight: bold;")
        preset_box.addWidget(preset_lbl)

        for p in WorldClockService.POPULAR_PRESETS[:5]:
            flag = country_code_to_flag(p["country_code"])
            btn = QPushButton(f"{flag} {p['city']}", self)
            btn.setObjectName("btn_quick_preset")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, item=p: self._select_preset(item))
            preset_box.addWidget(btn)
        preset_box.addStretch()
        layout.addLayout(preset_box)

        # Results List Widget
        self.results_list = QListWidget(self)
        self.results_list.setObjectName("results_list")
        self.results_list.itemClicked.connect(self._on_result_clicked)
        self.results_list.itemDoubleClicked.connect(lambda item: self._on_confirm_add())
        layout.addWidget(self.results_list, 1)

        # Selected City Preview Card
        self.preview_frame = QFrame(self)
        self.preview_frame.setObjectName("preview_frame")
        preview_layout = QHBoxLayout(self.preview_frame)
        preview_layout.setContentsMargins(12, 10, 12, 10)

        self.preview_flag_lbl = QLabel("", self.preview_frame)
        self.preview_flag_lbl.setStyleSheet("font-size: 24px;")
        preview_layout.addWidget(self.preview_flag_lbl)

        prev_text_layout = QVBoxLayout()
        self.preview_title_lbl = QLabel("Select a location above", self.preview_frame)
        self.preview_title_lbl.setFont(QFont("Inter", 11, QFont.Bold))
        self.preview_time_lbl = QLabel("--:-- --", self.preview_frame)
        self.preview_time_lbl.setStyleSheet("color: #94A3B8; font-size: 11px;")
        prev_text_layout.addWidget(self.preview_title_lbl)
        prev_text_layout.addWidget(self.preview_time_lbl)
        preview_layout.addLayout(prev_text_layout, 1)

        layout.addWidget(self.preview_frame)

        # Custom Label / Alias (Optional)
        label_box = QHBoxLayout()
        lbl_text = QLabel("Custom Label (Optional):", self)
        lbl_text.setStyleSheet("font-size: 11px;")
        self.custom_label_edit = QLineEdit(self)
        self.custom_label_edit.setPlaceholderText("e.g. Remote Team, Client HQ, Home")
        label_box.addWidget(lbl_text)
        label_box.addWidget(self.custom_label_edit, 1)
        layout.addLayout(label_box)

        # Clock Style Selector
        style_box = QHBoxLayout()
        style_lbl = QLabel("Clock Style:", self)
        style_lbl.setStyleSheet("font-size: 11px;")
        self.style_combo = QComboBox(self)
        for style_id, style_info in CLOCK_STYLES.items():
            self.style_combo.addItem(f"{style_info['name']} - {style_info['description']}", style_id)
        self.style_combo.setCurrentText("Compact Digital - Minimal digital display, small footprint")
        style_box.addWidget(style_lbl)
        style_box.addWidget(self.style_combo, 1)
        layout.addLayout(style_box)

        # Footer Action Buttons
        footer = QHBoxLayout()
        footer.addStretch()

        self.btn_cancel = QPushButton("Cancel", self)
        self.btn_cancel.clicked.connect(self.reject)
        footer.addWidget(self.btn_cancel)

        self.btn_add = QPushButton("+ Add Clock", self)
        self.btn_add.setObjectName("btn_add_clock")
        self.btn_add.setEnabled(False)
        self.btn_add.clicked.connect(self._on_confirm_add)
        footer.addWidget(self.btn_add)

        layout.addLayout(footer)
        self._apply_theme()

    def _populate_results(self, query: str = ""):
        self.results_list.clear()
        results = WorldClockService.search_locations(query)
        for item in results:
            flag = country_code_to_flag(item["country_code"])
            city = item["city"]
            country = item["country_name"]
            tz = item["timezone"]

            list_item = QListWidgetItem(f"{flag}  {city}, {country}  ({tz})")
            list_item.setData(Qt.UserRole, item)
            self.results_list.addItem(list_item)

        if self.results_list.count() > 0:
            self.results_list.setCurrentRow(0)
            self._on_result_clicked(self.results_list.item(0))

    def _on_search_changed(self, text: str):
        self._populate_results(text)

    def _select_preset(self, preset: Dict[str, Any]):
        self._set_selected_location(preset)

    def _on_result_clicked(self, item: QListWidgetItem):
        if not item:
            return
        data = item.data(Qt.UserRole)
        if data:
            self._set_selected_location(data)

    def _set_selected_location(self, loc_data: Dict[str, Any]):
        self._selected_data = loc_data
        flag = country_code_to_flag(loc_data["country_code"])
        city = loc_data["city"]
        country = loc_data["country_name"]
        tz = loc_data["timezone"]

        info = WorldClockService.get_time_info(tz)
        self.preview_flag_lbl.setText(flag)
        self.preview_title_lbl.setText(f"{city}, {country}")
        self.preview_time_lbl.setText(f"Current: {info['time_12h']} • {info['relative_str']} • {info['utc_offset']}")
        self.btn_add.setEnabled(True)

    def _on_confirm_add(self):
        if not hasattr(self, "_selected_data") or not self._selected_data:
            return

        import uuid
        custom_label = self.custom_label_edit.text().strip() or None
        style_id = self.style_combo.currentData()
        clock = WorldClockItem(
            id=str(uuid.uuid4())[:8],
            country_code=self._selected_data["country_code"],
            country_name=self._selected_data["country_name"],
            city=self._selected_data["city"],
            timezone=self._selected_data["timezone"],
            custom_label=custom_label,
            style=style_id,
        )
        self.created_clock = clock
        self.clock_created.emit(clock)
        self.accept()

    def _apply_theme(self):
        bg = "#1E1E2E" if self.is_dark else "#FFFFFF"
        surface = "#242538" if self.is_dark else "#F8FAFC"
        border = "#3D3F56" if self.is_dark else "#CBD5E1"
        text = "#F4F7FB" if self.is_dark else "#0F172A"
        accent = self.accent_color

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg};
                color: {text};
            }}
            QLineEdit {{
                background-color: {surface};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 8px 12px;
                color: {text};
                font-size: 13px;
            }}
            QPushButton#btn_quick_preset {{
                background-color: {surface};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                color: {text};
            }}
            QPushButton#btn_quick_preset:hover {{
                border-color: {accent};
            }}
            QListWidget#results_list {{
                background-color: {surface};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 6px;
                color: {text};
                font-size: 12px;
            }}
            QListWidget#results_list::item {{
                padding: 8px 10px;
                border-radius: 6px;
            }}
            QListWidget#results_list::item:selected {{
                background-color: {accent};
                color: #FFFFFF;
            }}
            QFrame#preview_frame {{
                background-color: {surface};
                border: 1.5px solid {border};
                border-radius: 8px;
            }}
            QPushButton#btn_add_clock {{
                background-color: {accent};
                color: #FFFFFF;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
            }}
            QPushButton#btn_add_clock:disabled {{
                background-color: #475569;
                color: #94A3B8;
            }}
        """)
