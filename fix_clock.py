import re

with open('todo_bird_app/views/dashboard_view.py', 'r') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if "self._init_clock_timer()" in line:
        continue
    new_lines.append(line)

content = "".join(new_lines)

# Find end of __init__
init_end_idx = content.find("def cleanup(self):")
if init_end_idx != -1:
    before = content[:init_end_idx]
    after = content[init_end_idx:]
    # insert before cleanup
    before = before.rstrip() + "\n        self._init_clock_timer()\n        self.refresh_data()\n\n    "
    content = before + after

method_code = """
    def _init_clock_timer(self):
        from PySide6.QtCore import QTimer
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self._update_clocks_display)
        self.clock_timer.start(60000)
        self._update_clocks_display()

    def _update_clocks_display(self):
        from todo_bird_app.utils.qt_cleanup import clear_layout
        from todo_bird_app.services.world_clock_service import WorldClockService
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
"""

content = content.replace("    def _init_ui(self):", method_code + "\n    def _init_ui(self):")

with open('todo_bird_app/views/dashboard_view.py', 'w') as f:
    f.write(content)

