
import os
os.environ["QT_QPA_PLATFORM"] = "wayland"

import sys
import asyncio
from datetime import datetime, timedelta, date
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QMessageBox, QScrollArea
)
from PyQt5.QtCore import Qt
from dbus_next.aio import MessageBus
from dbus_next import BusType

from common import PLAN_FILE, load_json, save_json, load_settings, speak_async
from main import GanttWidget

def tomorrow_key():
    return (date.today() + timedelta(days=1)).isoformat()

def plan_already_saved_for_tomorrow():
    data = load_json(PLAN_FILE, {})
    return data.get("plan_date") == tomorrow_key() and bool(data.get("tasks"))

class Planner(QWidget):
    def __init__(self, release):
        super().__init__()
        self.release = release
        self.settings = load_settings()
        self.setWindowTitle("Plan Tomorrow")
        self.setWindowFlags(Qt.WindowStaysOnTopHint)
        self.resize(820, 680)

        root = QVBoxLayout(self)
        title = QLabel("🌙 Sudharshan garu, before you rest, shall we prepare tomorrow peacefully?")
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:20px;font-weight:bold;padding:14px;")
        root.addWidget(title)

        current = load_json(PLAN_FILE, {})
        if current.get("plan_date") == date.today().isoformat():
            root.addWidget(GanttWidget(current))

        self.rows = []
        for i in range(3):
            row = QHBoxLayout()
            name = QLineEdit()
            name.setPlaceholderText(f"Task {i+1}")
            start = QLineEdit()
            start.setPlaceholderText("09:00")
            end = QLineEdit()
            end.setPlaceholderText("11:00")
            row.addWidget(name, 3)
            row.addWidget(start, 1)
            row.addWidget(end, 1)
            root.addLayout(row)
            self.rows.append((name, start, end))

        save = QPushButton("Save Tomorrow Plan and Continue Shutdown")
        save.clicked.connect(self.save)
        root.addWidget(save)

    def save(self):
        tasks = []
        for i, (name, start, end) in enumerate(self.rows):
            n = name.text().strip()
            if n:
                tasks.append({
                    "name": n,
                    "priority": "must" if i == 0 else "normal",
                    "planned_start": start.text().strip(),
                    "planned_end": end.text().strip(),
                    "actual_start": "",
                    "actual_end": "",
                    "status": "open"
                })
        if not tasks:
            QMessageBox.warning(self, "Plan Required", "Please add at least one task for tomorrow.")
            return
        save_json(PLAN_FILE, {
            "plan_date": tomorrow_key(),
            "created_at": datetime.now().astimezone().isoformat(),
            "tasks": tasks
        })
        speak_async("Thank you, Sudharshan garu. Tomorrow is prepared. Please rest peacefully. Good night.")
        self.release()
        self.close()

async def run():
    app = QApplication(sys.argv)
    settings = load_settings()
    bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
    intro = await bus.introspect("org.freedesktop.login1", "/org/freedesktop/login1")
    obj = bus.get_proxy_object("org.freedesktop.login1", "/org/freedesktop/login1", intro)
    manager = obj.get_interface("org.freedesktop.login1.Manager")

    fd = await manager.call_inhibit(
        "shutdown", "Todo Companion", "Night planning before shutdown", "block"
    )
    released = False
    window = None

    def release():
        nonlocal released
        if not released:
            try:
                fd.close()
            except Exception:
                pass
            released = True

    def on_shutdown(start):
        nonlocal window
        if not start or released:
            return
        hour = datetime.now().astimezone().hour
        threshold = int(settings.get("night_shutdown_after", 21))
        # Daytime shutdown/restart: never interrupt.
        if hour < threshold:
            release()
            return
        # Nighttime: ask only once, and only if tomorrow is not planned.
        if plan_already_saved_for_tomorrow():
            release()
            return
        window = Planner(release)
        window.show()
        window.raise_()
        window.activateWindow()
        speak_async(
            "Sudharshan garu, good night. Before shutting down, "
            "shall we lovingly prepare tomorrow's important work?"
        )

    manager.on_prepare_for_shutdown(on_shutdown)

    while True:
        app.processEvents()
        await asyncio.sleep(0.15)

if __name__ == "__main__":
    asyncio.run(run())
