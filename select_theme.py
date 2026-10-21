import os
os.environ["QT_QPA_PLATFORM"] = "wayland"

import json
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QDialog, QVBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt
import sys

BASE_DIR = Path.home() / "todo_bird"
CONFIG_FILE = BASE_DIR / "config" / "settings.json"

DEFAULT_SETTINGS = {
    "selected_theme": "avocet",
    "play_intro": True,
    "voice_enabled": True,
    "open_planify": True,
    "message": "Good morning. Your tasks are waiting in Planify."
}

THEMES = {
    "avocet": "🕊️  Avocet Companion",
    "yoga_ganapathy": "🕉️  Yoga Ganapathy",
    "lakshmi_ganapathy": "🌺  Lakshmi Ganapathy",
    "lion": "🦁  Lion Companion"
}

def load_settings():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        s = DEFAULT_SETTINGS.copy()
        s.update(data)
        return s
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(settings, f, indent=2)

class Selector(QDialog):
    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.setWindowTitle("Select Todo Bird Companion")
        self.resize(340, 300)

        layout = QVBoxLayout()
        title = QLabel("Choose your default companion")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:18px; font-weight:bold;")
        layout.addWidget(title)

        for key, label in THEMES.items():
            btn = QPushButton(label)
            btn.clicked.connect(lambda _, k=key: self.choose(k))
            layout.addWidget(btn)

        self.setLayout(layout)

    def choose(self, theme):
        self.settings["selected_theme"] = theme
        save_settings(self.settings)
        self.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dlg = Selector()
    dlg.exec_()
