# TODO BIRD 🐦

**TODO BIRD** is a premium, 100% offline desktop companion application for Ubuntu 24.04 built with Python 3.12, PySide6 (Qt6), SQLite, Piper Offline TTS, and Systemd User Services.

## Core Features
- **100% Offline**: Zero cloud, zero telemetry, zero subscriptions.
- **MVC Architecture**: Fully modular design with clean separation of models, views, and controllers.
- **GNOME Adwaita & Yaru Aesthetics**: Responsive sidebar, custom cards, dark/light mode toggle, dynamic accent colors.
- **Comprehensive Task Model**: Includes priorities, tags, categories, dependencies, recurring rules, planned vs. actual timestamps, and durations.
- **SQLite Database System**: Direct SQLite storage with WAL mode, foreign key enforcement, and versioned schema migrations.
- **Interactive Gantt Timeline & Plan vs Actual Tracker**: Timeline visualizations, milestone comparisons, and daily execution metrics.
- **Animated Offline Companion**: Avocet Bird, Yoga Ganapathy, Lakshmi Ganapathy, Male Lion.
- **Piper Offline TTS Voice Integration**: Warm, respectful South Indian voice companion.
- **Systemd Shutdown Guard**: Native Linux systemd service preventing unreviewed end-of-day shutdowns after 9 PM.

## Directory Structure
```
todo_bird_app/
├── app.py
├── database.py
├── requirements.txt
├── README.md
├── models/
├── views/
├── controllers/
├── widgets/
├── animations/
├── voice/
├── settings/
├── services/
├── shutdown/
├── gantt/
├── assets/
├── themes/
├── config/
├── logs/
└── data/
```

## Running the Application
```bash
venv/bin/python todo_bird_app/app.py
```
