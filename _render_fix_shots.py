#!/usr/bin/env python3
"""Render post-fix verification shots: accent swatches + reminder dialog, both themes."""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.pop("TODO_BIRD_SYNC_APPEARANCE", None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

OUT = "/home/athidhi_onlg/todo_bird/ui_shots/fix_2026_09_25"
os.makedirs(OUT, exist_ok=True)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

app = QApplication(sys.argv)

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.views.settings_view import SettingsView
from todo_bird_app.widgets.reminder_dialog import ReminderDialog
from datetime import datetime

db = DatabaseManager(":memory:")
sm = SettingsManager(db, config_dir="/tmp/tb_fix_shots_cfg")
theme = ThemeController(sm)
tc = TaskController(db)

today = datetime.now().strftime("%Y-%m-%d")
tc.add_task(Task(title="Morning devotional mantra", status=TaskStatus.IN_PROGRESS,
                 planned_date=today, planned_start_time="07:00",
                 actual_start_date=today, actual_start_time="06:55",
                 startup_reminder=True, startup_reminder_mode="daily_first_open"))


def grab(widget, path):
    app.processEvents()
    widget.grab().save(path)
    print("saved", path)


def shot_appearance(mode, accent_code, tag):
    theme.apply_theme(mode=mode)
    sv = SettingsView(db, sm)
    sv.resize(1280, 880)
    sv.show()
    app.processEvents()
    idx = sv.accent_combo.findData(accent_code)
    sv.accent_combo.blockSignals(True)
    sv.accent_combo.setCurrentIndex(idx)
    sv.accent_combo.blockSignals(False)
    sv._sync_theme_accent_buttons()
    app.processEvents()
    grab(sv, f"{OUT}/appearance_{tag}.png")
    sv.close()


shot_appearance("dark", "ubuntu_orange", "dark_ubuntu_orange")
shot_appearance("light", "rose", "light_rose")
shot_appearance("dark", "graphite", "dark_graphite")

# Reminder dialog, both themes
task = tc.get_all_tasks()[0]
theme.apply_theme(mode="dark")
rd = ReminderDialog(task, task_controller=tc, settings_manager=sm, parent=None)
rd.resize(560, 420)
rd.show()
grab(rd, f"{OUT}/reminder_dark.png")
rd.close()
theme.apply_theme(mode="light")
rd2 = ReminderDialog(task, task_controller=tc, settings_manager=sm, parent=None)
rd2.resize(560, 420)
rd2.show()
grab(rd2, f"{OUT}/reminder_light.png")
rd2.close()

print("DONE")
