#!/usr/bin/env python3
"""Render the upgraded surfaces: Gantt health ribbon + World Clock scrubber."""
import os
import sys
from datetime import datetime

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.pop("TODO_BIRD_SYNC_APPEARANCE", None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OUT = "/home/athidhi_onlg/todo_bird/ui_shots/upgrade_2026_09_25"
os.makedirs(OUT, exist_ok=True)

from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.views.main_window import MainWindow
from todo_bird_app.services.world_clock_service import WorldClockItem
from todo_bird_app.views.world_clock_view import WorldClockView

db = DatabaseManager(":memory:")
sm = SettingsManager(db, config_dir="/tmp/tb_upgrade_shots_cfg")
theme = ThemeController(sm)
tc = TaskController(db)
PID = db.insert_project({"name": "Upgrade Shots"})

# Chain with a near-critical branch and a missed deadline
today = datetime.now()
d1 = today.strftime("%Y-%m-%d")
d2 = (today.toordinal() and datetime.fromordinal(today.toordinal() + 1)).strftime("%Y-%m-%d")
tc.add_task(Task(id=1, title="Foundation", project_id=PID, planned_date=d1,
                 planned_start_time="09:00", estimated_duration=480,
                 actual_start_date=d1, actual_start_time="09:00", show_in_gantt=True))
tc.add_task(Task(id=2, title="Structure", project_id=PID, planned_date=d1,
                 planned_start_time="13:00", estimated_duration=480,
                 dependencies=[1], show_in_gantt=True,
                 deadline_datetime=f"{d1} 14:00"))
tc.add_task(Task(id=3, title="Short branch", project_id=PID, planned_date=d1,
                 planned_start_time="13:00", estimated_duration=60,
                 dependencies=[1], show_in_gantt=True))
tc.add_task(Task(id=4, title="Finish", project_id=PID, planned_date=d2,
                 planned_start_time="09:00", estimated_duration=120,
                 dependencies=[2, 3], show_in_gantt=True))

mw = MainWindow(db, sm, theme)
mw.resize(1360, 860)
mw.show()
app.processEvents()


def grab(widget, path):
    app.processEvents()
    widget.grab().save(path)
    print("saved", path)


from PySide6.QtWidgets import QApplication as QApp
for mode in ("dark", "light"):
    theme.apply_theme(mode=mode)
    mw.navigation_controller.set_active_section("gantt")
    for _ in range(6):
        app.processEvents()
    grab(mw, f"{OUT}/gantt_health_{mode}.png")

    # World clock with simulation active
    wcv = mw.world_clock_view
    wcv.clocks = [
        WorldClockItem(id="1", country_code="IN", country_name="India",
                       city="Hyderabad", timezone="Asia/Kolkata"),
        WorldClockItem(id="2", country_code="US", country_name="United States",
                       city="New York", timezone="America/New_York"),
        WorldClockItem(id="3", country_code="GB", country_name="United Kingdom",
                       city="London", timezone="Europe/London"),
    ]
    wcv._render_grid()
    mw.navigation_controller.set_active_section("world_clock")
    app.processEvents()
    wcv._on_slider_changed(14 * 60 + 30)
    app.processEvents()
    grab(mw, f"{OUT}/world_clock_sim_{mode}.png")
    wcv._reset_scrubber()

mw.close()
print("DONE")
