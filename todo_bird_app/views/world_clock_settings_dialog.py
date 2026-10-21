import uuid
from typing import List
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QComboBox, QCheckBox, QMessageBox, QWidget, QInputDialog
)
from PySide6.QtCore import Qt

from todo_bird_app.services.world_clock_service import WorldClockService, WorldClockItem


class WorldClockSettingsDialog(QDialog):
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.setWindowTitle("World Clock Settings")
        self.setMinimumSize(400, 500)
        
        # Load data
        self.clocks = WorldClockService.load_clocks(self.settings_manager)
        self._init_ui()
        self._populate_list()
        
    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # 1. Clocks List
        layout.addWidget(QLabel("<b>Your Clocks (Max 5)</b>"))
        
        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QListWidget.InternalMove)
        layout.addWidget(self.list_widget)
        
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Add Clock")
        self.btn_add.clicked.connect(self._on_add_clock)
        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.clicked.connect(self._on_remove_clock)
        
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_remove)
        layout.addLayout(btn_layout)
        
        # 2. Global Settings
        layout.addSpacing(15)
        layout.addWidget(QLabel("<b>Display Settings</b>"))
        
        self.cb_type = QComboBox()
        self.cb_type.addItems(["digital", "analog"])
        c_type = WorldClockService.get_clock_type(self.settings_manager)
        self.cb_type.setCurrentText(c_type)
        
        self.cb_theme = QComboBox()
        self.cb_theme.addItems(["minimal", "luxury", "cyberpunk", "retro_lcd", "solar"])
        c_theme = WorldClockService.get_clock_theme(self.settings_manager)
        self.cb_theme.setCurrentText(c_theme)
        
        self.chk_24h = QCheckBox("Use 24-hour time")
        self.chk_24h.setChecked(WorldClockService.get_use_24h(self.settings_manager))
        
        self.chk_seconds = QCheckBox("Show seconds (Requires more CPU)")
        self.chk_seconds.setChecked(bool(self.settings_manager.get("world_clock_show_seconds", False)))
        
        self.chk_compact = QCheckBox("Compact Size")
        self.chk_compact.setChecked(bool(self.settings_manager.get("world_clock_compact", True)))
        
        form_layout = QVBoxLayout()
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Style:"))
        h1.addWidget(self.cb_type)
        form_layout.addLayout(h1)
        
        h2 = QHBoxLayout()
        h2.addWidget(QLabel("Theme:"))
        h2.addWidget(self.cb_theme)
        form_layout.addLayout(h2)
        
        form_layout.addWidget(self.chk_24h)
        form_layout.addWidget(self.chk_seconds)
        form_layout.addWidget(self.chk_compact)
        layout.addLayout(form_layout)
        
        # Bottom Buttons
        bottom_layout = QHBoxLayout()
        btn_save = QPushButton("Save && Apply")
        btn_save.setStyleSheet("background-color: #2E8B57; color: white;")
        btn_save.clicked.connect(self._on_save)
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        
        bottom_layout.addStretch()
        bottom_layout.addWidget(btn_cancel)
        bottom_layout.addWidget(btn_save)
        layout.addLayout(bottom_layout)
        
    def _populate_list(self):
        self.list_widget.clear()
        for clock in self.clocks:
            item = QListWidgetItem(f"{clock.city}, {clock.country_name} ({clock.timezone})")
            item.setData(Qt.UserRole, clock)
            self.list_widget.addItem(item)
            
        self.btn_add.setEnabled(len(self.clocks) < 5)
            
    def _on_add_clock(self):
        if len(self.clocks) >= 5:
            return
            
        tz, ok = QInputDialog.getText(self, "Add Clock", "Enter Timezone (e.g. Europe/London):")
        if ok and tz:
            try:
                # Basic validation
                import zoneinfo
                zoneinfo.ZoneInfo(tz)
                
                parts = tz.split('/')
                city = parts[-1].replace('_', ' ')
                new_clock = WorldClockItem(
                    id=str(uuid.uuid4())[:8],
                    country_code="XX",
                    country_name="Custom",
                    city=city,
                    timezone=tz,
                )
                self.clocks.append(new_clock)
                self._populate_list()
            except Exception:
                QMessageBox.warning(self, "Error", f"Invalid timezone: {tz}")
                
    def _on_remove_clock(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            self.list_widget.takeItem(row)
            self.clocks.pop(row)
            self.btn_add.setEnabled(len(self.clocks) < 5)
            
    def _on_save(self):
        # Save clocks order from list widget
        ordered_clocks = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            ordered_clocks.append(item.data(Qt.UserRole))
            
        WorldClockService.save_clocks(self.settings_manager, ordered_clocks)
        WorldClockService.set_clock_type(self.settings_manager, self.cb_type.currentText())
        WorldClockService.set_clock_theme(self.settings_manager, self.cb_theme.currentText())
        WorldClockService.set_use_24h(self.settings_manager, self.chk_24h.isChecked())
        
        self.settings_manager.set("world_clock_show_seconds", self.chk_seconds.isChecked())
        self.settings_manager.set("world_clock_compact", self.chk_compact.isChecked())
        
        self.accept()
