import re

with open('todo_bird_app/views/settings_view.py', 'r') as f:
    content = f.read()

# Add import
import_stmt = "from todo_bird_app.widgets.add_world_clock_dialog import AddWorldClockDialog\nfrom todo_bird_app.services.world_clock_service import WorldClockService\nfrom todo_bird_app.widgets.digital_clock_widget import DigitalClockWidget\n"
if "AddWorldClockDialog" not in content:
    content = content.replace("from todo_bird_app.ui.components.modern_button import ModernButton, ButtonStyleDesign, ButtonVariant",
                              "from todo_bird_app.ui.components.modern_button import ModernButton, ButtonStyleDesign, ButtonVariant\n" + import_stmt)

# Add dashboard layout tab
dashboard_tab = """        system_layout = self._make_settings_page(
            self.settings_tabs,
            "System",
        )
        dashboard_layout = self._make_settings_page(
            self.settings_tabs,
            "Dashboard",
        )
        self._settings_page_layouts = (
            appearance_layout,
            typography_layout,
            reminders_layout,
            companion_layout,
            planning_layout,
            system_layout,
            dashboard_layout,
        )
"""
content = re.sub(
    r'        system_layout = self._make_settings_page\(\s*self.settings_tabs,\s*"System",\s*\)\s*self._settings_page_layouts = \([\s\S]*?system_layout,\s*\)',
    dashboard_tab,
    content
)

# Add _populate_dashboard_settings call
content = content.replace("        self._settings_tabs_container.addWidget(self.settings_tabs)",
                          "        self._populate_dashboard_settings(dashboard_layout)\n        self._settings_tabs_container.addWidget(self.settings_tabs)")

# Add _populate_dashboard_settings method definition
method_code = """
    def _populate_dashboard_settings(self, layout: QVBoxLayout):
        card = QFrame()
        card.setObjectName("SettingsSubPanel")
        vbox = QVBoxLayout(card)
        
        lbl = QLabel("🌍 World Clocks (Good Morning Strip)")
        lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        vbox.addWidget(lbl)
        
        desc = QLabel("Select up to 5 world clocks to display in the Dashboard header.")
        desc.setStyleSheet("color: #64748B;")
        vbox.addWidget(desc)
        
        self.clocks_list_widget = QListWidget()
        self.clocks_list_widget.setFixedHeight(160)
        vbox.addWidget(self.clocks_list_widget)
        
        btn_row = QHBoxLayout()
        btn_add = QPushButton("➕ Add World Clock")
        btn_del = QPushButton("🗑 Remove Selected")
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        vbox.addLayout(btn_row)
        
        layout.addWidget(card)
        layout.addStretch()
        
        def refresh_clocks():
            self.clocks_list_widget.clear()
            clock_ids = self.settings_manager.get("dashboard_world_clocks", [])
            service = WorldClockService()
            for cid in clock_ids:
                if type(cid) is dict:
                    item = WorldClockItem.from_dict(cid)
                else:
                    item = service.get_clock_by_id(cid)
                    if not item:
                        # Fallback to check default clocks
                        for dc in WorldClockService.DEFAULT_CLOCKS:
                            if dc["id"] == cid:
                                item = WorldClockItem.from_dict(dc)
                                break
                if item:
                    list_item = QListWidgetItem(f"{item.city} ({item.timezone})")
                    list_item.setData(Qt.UserRole, cid if type(cid) is not dict else item.id)
                    self.clocks_list_widget.addItem(list_item)
                    
        def add_clock():
            clock_ids = self.settings_manager.get("dashboard_world_clocks", [])
            if len(clock_ids) >= 5:
                QMessageBox.warning(self, "Limit Reached", "You can only add up to 5 world clocks.")
                return
            is_dark = str(self.settings_manager.get("theme", "dark")).lower() == "dark"
            accent = str(self.settings_manager.get("accent_color", "#3584E4"))
            dlg = AddWorldClockDialog(is_dark=is_dark, accent_color=accent, parent=self)
            def on_created(item):
                cids = self.settings_manager.get("dashboard_world_clocks", [])
                if item.id not in cids and item.to_dict() not in cids:
                    cids.append(item.to_dict())
                    self.settings_manager.set("dashboard_world_clocks", cids)
                    refresh_clocks()
            dlg.clock_created.connect(on_created)
            dlg.exec()
            
        def del_clock():
            sel = self.clocks_list_widget.currentItem()
            if not sel: return
            cid_to_del = sel.data(Qt.UserRole)
            clock_ids = self.settings_manager.get("dashboard_world_clocks", [])
            new_cids = []
            for cid in clock_ids:
                if type(cid) is dict:
                    if cid.get("id") != cid_to_del: new_cids.append(cid)
                else:
                    if cid != cid_to_del: new_cids.append(cid)
            self.settings_manager.set("dashboard_world_clocks", new_cids)
            refresh_clocks()
            
        btn_add.clicked.connect(add_clock)
        btn_del.clicked.connect(del_clock)
        refresh_clocks()
"""
if "_populate_dashboard_settings" not in content:
    content = content.replace("    def _init_ui(self):", method_code + "\n    def _init_ui(self):")

with open('todo_bird_app/views/settings_view.py', 'w') as f:
    f.write(content)

