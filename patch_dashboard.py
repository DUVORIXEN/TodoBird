import re

with open('todo_bird_app/views/dashboard_view.py', 'r') as f:
    content = f.read()

# Add imports for WorldClockService and QTimer
if "WorldClockService" not in content:
    content = content.replace(
        "from todo_bird_app.views.base_view import BaseView",
        "from todo_bird_app.views.base_view import BaseView\nfrom todo_bird_app.services.world_clock_service import WorldClockService\nfrom PySide6.QtCore import QTimer\n"
    )

# 1. Update _init_ui layout structure
# Find the greeting row
greet_clocks = """
        greet_vbox = QVBoxLayout()
        greet_vbox.addWidget(self.greeting_text)
        greet_vbox.addWidget(self.date_text)
        greet_layout.addLayout(greet_vbox)
        greet_layout.addStretch()
        
        self.clock_strip_layout = QHBoxLayout()
        self.clock_strip_layout.setSpacing(16)
        greet_layout.addLayout(self.clock_strip_layout)
        greet_layout.addStretch()

        self.scope_selector = QComboBox()
"""
content = re.sub(r'        greet_vbox = QVBoxLayout\(\).*?        self\.scope_selector = QComboBox\(\)', greet_clocks, content, flags=re.DOTALL)

# Add timer initialization to __init__
if "self.clock_timer" not in content:
    content = content.replace("        self.refresh_data()", "        self._init_clock_timer()\n        self.refresh_data()")

init_clock_timer_method = """
    def _init_clock_timer(self):
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clocks_display)
        self.clock_timer.start(60000)
        self._update_clocks_display()

    def _update_clocks_display(self):
        from todo_bird_app.utils.qt_cleanup import clear_layout
        from datetime import datetime
        try:
            import pytz
        except ImportError:
            pytz = None
            
        clear_layout(self.clock_strip_layout)
        clock_ids = self.settings_manager.get("dashboard_world_clocks", [])
        if not clock_ids:
            btn = QPushButton("➕ Add World Clocks")
            btn.setStyleSheet("background: transparent; color: #3584E4; border: 1px dashed #3584E4; border-radius: 6px; padding: 4px 12px; font-weight: bold;")
            btn.setCursor(Qt.PointingHandCursor)
            self.clock_strip_layout.addWidget(btn)
            return

        service = WorldClockService()
        for i, cid in enumerate(clock_ids):
            item = None
            if type(cid) is dict:
                item = cid
            else:
                clock_item = service.get_clock_by_id(cid)
                if clock_item: item = clock_item.to_dict()
                if not item:
                    for dc in WorldClockService.DEFAULT_CLOCKS:
                        if dc["id"] == cid:
                            item = dc
                            break
            if item:
                tz_name = item["timezone"]
                city = item["city"]
                dt = datetime.now()
                if pytz:
                    dt = datetime.now(pytz.timezone(tz_name))
                
                clock_widget = QWidget()
                clock_lyt = QVBoxLayout(clock_widget)
                clock_lyt.setContentsMargins(0, 0, 0, 0)
                clock_lyt.setSpacing(0)
                
                city_lbl = QLabel(city)
                city_lbl.setStyleSheet("font-weight: 600; font-size: 11px; color: #94A3B8;")
                
                time_lbl = QLabel(dt.strftime("%H:%M"))
                time_lbl.setStyleSheet("font-weight: 800; font-size: 14px; color: #E2E8F0;")
                
                clock_lyt.addWidget(city_lbl, alignment=Qt.AlignCenter)
                clock_lyt.addWidget(time_lbl, alignment=Qt.AlignCenter)
                
                self.clock_strip_layout.addWidget(clock_widget)
                
                if i < len(clock_ids) - 1:
                    div = QLabel(" · ")
                    div.setStyleSheet("color: #475569; font-size: 16px; font-weight: bold;")
                    self.clock_strip_layout.addWidget(div)
                    
        # Apply current theme colors to text dynamically
        is_dark = str(self.settings_manager.get("theme", "dark")).lower() == "dark"
        primary_color = "#E2E8F0" if is_dark else "#1E293B"
        for i in range(self.clock_strip_layout.count()):
            widget = self.clock_strip_layout.itemAt(i).widget()
            if widget and widget.layout():
                if widget.layout().count() == 2:
                    val_lbl = widget.layout().itemAt(1).widget()
                    if isinstance(val_lbl, QLabel):
                        val_lbl.setStyleSheet(f"font-weight: 800; font-size: 14px; color: {primary_color};")
"""
if "_init_clock_timer" not in content:
    content = content.replace("    def _init_ui(self):", init_clock_timer_method + "\n    def _init_ui(self):")


with open('todo_bird_app/views/dashboard_view.py', 'w') as f:
    f.write(content)

