
import os
os.environ["QT_QPA_PLATFORM"] = "xcb"

import sys
import json
import random
import subprocess
from datetime import datetime, date
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QDialog, QComboBox, QSpinBox, QCheckBox, QFormLayout, QLineEdit,
    QMessageBox, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QPoint, QSize, QRect
from PyQt5.QtGui import QMovie, QPainter, QPen, QBrush, QFont

from common import (
    BASE_DIR, PLAN_FILE, STATE_FILE, load_json, save_json,
    load_settings, save_settings, speak_async
)

PLANIFY_CMD = ["flatpak", "run", "io.github.alainm23.planify"]

THEMES = {
    "avocet": {"emoji": "🕊️", "title": "Avocet Companion"},
    "yoga_ganapathy": {"emoji": "🕉️", "title": "Yoga Ganapathy"},
    "lakshmi_ganapathy": {"emoji": "🌺", "title": "Lakshmi Ganapathy"},
    "lion": {"emoji": "🦁", "title": "Lion Companion"}
}

GREETING_LABELS = {
    "every_start": "Every system start",
    "once_daily": "First start of the day only",
    "morning_evening": "Once in morning and once in evening",
    "off": "No welcome greeting"
}

def open_planify():
    try:
        subprocess.Popen(PLANIFY_CMD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

def today_key():
    return date.today().isoformat()

def startup_period(hour):
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    return "evening"  # Never say good night on startup.

def should_greet(settings, state, period):
    mode = settings.get("greeting_mode", "once_daily")
    today = today_key()
    if mode == "off":
        return False
    if mode == "every_start":
        return True
    if mode == "once_daily":
        return state.get("last_daily_greeting") != today
    if mode == "morning_evening":
        if period == "morning":
            return state.get("last_morning_greeting") != today
        if period == "evening":
            return state.get("last_evening_greeting") != today
        return False
    return True

def mark_greeted(state, period):
    today = today_key()
    state["last_daily_greeting"] = today
    if period == "morning":
        state["last_morning_greeting"] = today
    if period == "evening":
        state["last_evening_greeting"] = today
    state["last_start_iso"] = datetime.now().astimezone().isoformat()
    save_json(STATE_FILE, state)

def load_today_plan():
    data = load_json(PLAN_FILE, {})
    return data if data.get("plan_date") == today_key() else {}

def build_startup_voice(period, plan):
    if period == "morning":
        base = (
            "Sudharshan garu, good morning. "
            "With Vighnavinashaka blessings, please begin peacefully. "
            "May your work move forward with clarity, confidence, and success."
        )
    elif period == "afternoon":
        base = (
            "Sudharshan garu, good afternoon. Welcome back. "
            "Please continue your work calmly and confidently. "
            "You are doing meaningful work."
        )
    else:
        base = (
            "Sudharshan garu, good evening. Welcome. "
            "Please begin your work with a fresh and peaceful mind. "
            "I am here to support you with affection and respect."
        )

    tasks = plan.get("tasks", [])
    if tasks:
        must = next((t.get("name") for t in tasks if t.get("priority") == "must"), tasks[0].get("name"))
        if must:
            base += f" Your most important task is {must}."
    return base

class GanttWidget(QWidget):
    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self.plan = plan
        self.setMinimumSize(760, 240)

    @staticmethod
    def to_minutes(value):
        try:
            h, m = map(int, value.split(":"))
            return h * 60 + m
        except Exception:
            return None

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QBrush(Qt.white))

        tasks = self.plan.get("tasks", [])
        left, right, top, row_h = 170, 20, 45, 48
        chart_w = max(100, self.width() - left - right)
        start_day, end_day = 6 * 60, 23 * 60
        span = end_day - start_day

        p.setPen(QPen(Qt.black))
        p.setFont(QFont("Sans", 10, QFont.Bold))
        p.drawText(15, 24, "Plan vs Actual — Today")

        p.setFont(QFont("Sans", 8))
        for hour in range(6, 24, 2):
            x = left + int((hour * 60 - start_day) / span * chart_w)
            p.setPen(QPen(Qt.lightGray))
            p.drawLine(x, top - 10, x, top + max(1, len(tasks)) * row_h)
            p.setPen(QPen(Qt.black))
            p.drawText(x - 15, top - 16, f"{hour:02d}:00")

        for i, task in enumerate(tasks):
            y = top + i * row_h
            name = task.get("name", f"Task {i+1}")
            p.setPen(QPen(Qt.black))
            p.drawText(10, y + 17, name[:24])

            ps = self.to_minutes(task.get("planned_start", ""))
            pe = self.to_minutes(task.get("planned_end", ""))
            if ps is not None and pe is not None and pe > ps:
                x1 = left + int((ps - start_day) / span * chart_w)
                x2 = left + int((pe - start_day) / span * chart_w)
                p.fillRect(QRect(x1, y + 4, max(3, x2 - x1), 13), QBrush(Qt.darkCyan))
                p.drawText(left - 42, y + 14, "Plan")

            actual_start = self.to_minutes(task.get("actual_start", ""))
            actual_end = self.to_minutes(task.get("actual_end", ""))
            if actual_start is not None:
                if actual_end is None:
                    actual_end = datetime.now().hour * 60 + datetime.now().minute
                if actual_end > actual_start:
                    x1 = left + int((actual_start - start_day) / span * chart_w)
                    x2 = left + int((actual_end - start_day) / span * chart_w)
                    p.fillRect(QRect(x1, y + 23, max(3, x2 - x1), 13), QBrush(Qt.darkGreen))
                    p.drawText(left - 42, y + 34, "Actual")

        p.end()

class ActualsDialog(QDialog):
    def __init__(self, plan, parent=None):
        super().__init__(parent)
        self.plan = plan
        self.setWindowTitle("Update Actual Work")
        self.resize(520, 360)
        form = QFormLayout(self)
        self.rows = []
        for task in self.plan.get("tasks", []):
            start = QLineEdit(task.get("actual_start", ""))
            end = QLineEdit(task.get("actual_end", ""))
            done = QCheckBox("Completed")
            done.setChecked(task.get("status") == "done")
            row = QHBoxLayout()
            row.addWidget(QLabel(task.get("name", "Task")))
            row.addWidget(QLabel("Start"))
            row.addWidget(start)
            row.addWidget(QLabel("End"))
            row.addWidget(end)
            row.addWidget(done)
            form.addRow(row)
            self.rows.append((task, start, end, done))
        save = QPushButton("Save Actuals")
        save.clicked.connect(self.save)
        form.addRow(save)

    def save(self):
        for task, start, end, done in self.rows:
            task["actual_start"] = start.text().strip()
            task["actual_end"] = end.text().strip()
            task["status"] = "done" if done.isChecked() else "open"
        save_json(PLAN_FILE, self.plan)
        self.accept()

class SettingsDialog(QDialog):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Todo Companion Settings")
        form = QFormLayout(self)

        self.mode = QComboBox()
        for key, label in GREETING_LABELS.items():
            self.mode.addItem(label, key)
        idx = self.mode.findData(settings.get("greeting_mode", "once_daily"))
        self.mode.setCurrentIndex(max(0, idx))

        self.night = QSpinBox()
        self.night.setRange(18, 23)
        self.night.setValue(int(settings.get("night_shutdown_after", 21)))

        self.voice = QCheckBox()
        self.voice.setChecked(bool(settings.get("voice_enabled", True)))
        self.planify = QCheckBox()
        self.planify.setChecked(bool(settings.get("open_planify", True)))
        self.gantt = QCheckBox()
        self.gantt.setChecked(bool(settings.get("show_gantt_on_greeting", True)))

        form.addRow("Welcome mode", self.mode)
        form.addRow("Night planning starts at", self.night)
        form.addRow("Voice", self.voice)
        form.addRow("Open Planify", self.planify)
        form.addRow("Show Gantt", self.gantt)

        save = QPushButton("Save Settings")
        save.clicked.connect(self.save)
        form.addRow(save)

    def save(self):
        self.settings["greeting_mode"] = self.mode.currentData()
        self.settings["night_shutdown_after"] = self.night.value()
        self.settings["voice_enabled"] = self.voice.isChecked()
        self.settings["open_planify"] = self.planify.isChecked()
        self.settings["show_gantt_on_greeting"] = self.gantt.isChecked()
        save_settings(self.settings)
        self.accept()

class Companion(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.state = load_json(STATE_FILE, {})
        self.period = startup_period(datetime.now().astimezone().hour)
        self.plan = load_today_plan()
        self.greet_now = should_greet(self.settings, self.state, self.period)
        self.movie = None
        self.blinking_enabled = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(820 if self.settings.get("show_gantt_on_greeting", True) else 520, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)

        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setFixedSize(QSize(430, 270))
        root.addWidget(self.icon, alignment=Qt.AlignCenter)

        button_row = QHBoxLayout()
        self.planify_btn = QPushButton("Open Planify")
        self.planify_btn.clicked.connect(open_planify)
        self.actual_btn = QPushButton("Update Actuals")
        self.actual_btn.clicked.connect(self.update_actuals)
        self.settings_btn = QPushButton("Settings")
        self.settings_btn.clicked.connect(self.open_settings)
        button_row.addWidget(self.planify_btn)
        button_row.addWidget(self.actual_btn)
        button_row.addWidget(self.settings_btn)
        root.addLayout(button_row)

        if self.settings.get("show_gantt_on_greeting", True) and self.plan:
            self.gantt = GanttWidget(self.plan)
            root.addWidget(self.gantt)
        else:
            self.gantt = None

        screen = QApplication.primaryScreen().availableGeometry()
        self.start_pos = QPoint(screen.right() + 40, screen.top() - 100)
        self.path1 = QPoint(screen.right() - 260, screen.top() + 60)
        self.path2 = QPoint(screen.right() - 500, screen.top() + 40)
        self.land_pos = QPoint(screen.right() - self.width() + 10, screen.top() + 20)
        self.exit_pos = QPoint(screen.right() + 150, screen.top() - 150)
        self.move(self.start_pos)

        if not self.greet_now:
            QTimer.singleShot(0, QApplication.instance().quit)
            return

        mark_greeted(self.state, self.period)
        self.show()
        self.start_sequence()

    def asset(self, name):
        return BASE_DIR / "assets" / "characters" / name

    def set_movie(self, path):
        if path.exists() and path.stat().st_size > 0:
            if self.movie:
                self.movie.stop()
            self.movie = QMovie(str(path))
            self.movie.setScaledSize(self.icon.size())
            self.icon.setMovie(self.movie)
            self.movie.start()
        else:
            self.icon.setText("🕊️")
            self.icon.setStyleSheet("font-size: 110px;")

    def start_sequence(self):
        self.set_movie(self.asset("avocet_fly.gif"))
        self.fly1 = QPropertyAnimation(self, b"pos")
        self.fly1.setDuration(800)
        self.fly1.setStartValue(self.start_pos)
        self.fly1.setEndValue(self.path1)

        self.fly2 = QPropertyAnimation(self, b"pos")
        self.fly2.setDuration(900)
        self.fly2.setStartValue(self.path1)
        self.fly2.setEndValue(self.path2)

        self.fly3 = QPropertyAnimation(self, b"pos")
        self.fly3.setDuration(550)
        self.fly3.setStartValue(self.path2)
        self.fly3.setEndValue(self.land_pos)

        self.fly1.finished.connect(self.fly2.start)
        self.fly2.finished.connect(self.fly3.start)
        self.fly3.finished.connect(self.on_landed)
        self.fly1.start()

        voice = build_startup_voice(self.period, self.plan)
        if self.settings.get("voice_enabled", True):
            if self.settings.get("devotional_intro", True) and self.period == "morning":
                QTimer.singleShot(1800, lambda: speak_async("Om Gam Ganapataye Namaha."))
                QTimer.singleShot(5200, lambda: speak_async(voice))
            else:
                QTimer.singleShot(2600, lambda: speak_async(voice))

        if self.settings.get("open_planify", True):
            QTimer.singleShot(6500, open_planify)

        visible_ms = int(self.settings.get("companion_visible_seconds", 24)) * 1000
        QTimer.singleShot(visible_ms, self.exit_scene)

    def on_landed(self):
        self.set_movie(self.asset("avocet_idle.gif"))
        self.blinking_enabled = True
        QTimer.singleShot(2200, self.schedule_blink)

    def schedule_blink(self):
        if self.blinking_enabled:
            QTimer.singleShot(random.randint(3000, 5000), self.do_blink)

    def do_blink(self):
        if not self.blinking_enabled:
            return
        self.set_movie(self.asset("avocet_blink.gif"))
        QTimer.singleShot(900, lambda: self.set_movie(self.asset("avocet_idle.gif")))
        self.schedule_blink()

    def update_actuals(self):
        if not self.plan:
            QMessageBox.information(self, "No Plan", "No plan is saved for today.")
            return
        dlg = ActualsDialog(self.plan, self)
        if dlg.exec_():
            self.plan = load_today_plan()
            if self.gantt:
                self.gantt.plan = self.plan
                self.gantt.update()

    def open_settings(self):
        SettingsDialog(self.settings, self).exec_()

    def exit_scene(self):
        self.blinking_enabled = False
        self.set_movie(self.asset("avocet_fly.gif"))
        self.exit1 = QPropertyAnimation(self, b"pos")
        self.exit1.setDuration(1200)
        self.exit1.setStartValue(self.pos())
        self.exit1.setEndValue(self.exit_pos)
        self.exit1.finished.connect(QApplication.instance().quit)
        self.exit1.start()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Companion()
    sys.exit(app.exec_())
