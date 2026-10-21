#!/usr/bin/env python3
"""Wave 4b — offscreen UI render harness for visual verification.

Renders the real Settings view (every tab), the Today view, sample widgets
(checkbox/toggle/pills) and a dashboard chart in dark AND light themes,
grabbing PNGs for visual inspection.
"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("TODO_BIRD_DISABLE_SINGLE_INSTANCE", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

app = QApplication(sys.argv)

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority

OUT = "/home/athidhi_onlg/todo_bird/ui_shots"
os.makedirs(OUT, exist_ok=True)

db = DatabaseManager(":memory:")
settings = SettingsManager(db, config_dir="/tmp/tb_render_cfg")
theme = ThemeController(settings)

# Seed a couple of tasks so Today view has content
controller_tasks = []
try:
    from todo_bird_app.controllers.task_controller import TaskController
    tc = TaskController(db)
    t1 = Task(
        title="Quarterly systems engineering review with the platform team",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.HIGH,
    )
    t2 = Task(
        title="Small done task",
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.LOW,
    )
    for t in (t1, t2):
        try:
            tc.add_task(t)
        except Exception as e:
            print("seed task failed:", e)
    controller_tasks = tc
except Exception as e:
    print("task seeding unavailable:", e)


def render(mode: str, tag: str):
    theme.apply_theme(mode=mode, accent_color="#3584E4")
    shots = []

    # --- Settings view, every tab ---
    from todo_bird_app.views.settings_view import SettingsView
    sv = SettingsView(db, settings)
    sv.resize(1280, 880)
    sv.show()
    app.processEvents()

    for i in range(sv.settings_tabs.count()):
        sv.settings_tabs.setCurrentIndex(i)
        app.processEvents()
        QTimer.singleShot(0, lambda: None)
        app.processEvents()
        name = sv.settings_tabs.tabText(i).lower().replace(" ", "_")
        path = f"{OUT}/settings_{tag}_{i:02d}_{name}.png"
        sv.grab().save(path)
        shots.append(path)
    # Search-highlight state demo (Appearance tab)
    sv.settings_tabs.setCurrentIndex(0)
    if hasattr(sv, "settings_search_input"):
        sv.settings_search_input.setText("gantt")
        app.processEvents()
        path = f"{OUT}/settings_{tag}_90_search_highlight.png"
        sv.grab().save(path)
        shots.append(path)
        sv.settings_search_input.setText("")
        app.processEvents()
    sv.close()
    sv.deleteLater()

    # --- Today view ---
    try:
        from todo_bird_app.views.today_view import TodayView
        tv = TodayView(db, settings)
        tv.resize(1280, 880)
        tv.show()
        app.processEvents()
        path = f"{OUT}/today_{tag}.png"
        tv.grab().save(path)
        shots.append(path)
        tv.close()
        tv.deleteLater()
    except Exception as e:
        print("today view render failed:", e)

    # --- Sample widgets ---
    try:
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox
        from todo_bird_app.ui.components.modern_checkbox import ModernCheckBox
        from todo_bird_app.ui.components.toggle_switch import ToggleSwitch
        from todo_bird_app.ui.components.modern_combobox import SearchableComboBox
        from todo_bird_app.widgets.task_item_widget import TaskItemWidget

        panel = QWidget()
        panel.resize(760, 420)
        lay = QVBoxLayout(panel)
        lay.addWidget(QLabel("Plain QCheckBox (theme QSS tick)"))
        from PySide6.QtWidgets import QCheckBox
        cb1 = QCheckBox("Unchecked plain checkbox")
        cb2 = QCheckBox("Checked plain checkbox")
        cb2.setChecked(True)
        cb3 = QCheckBox("Partially checked")
        from PySide6.QtCore import Qt as _Qt; cb3.setCheckState(_Qt.CheckState.PartiallyChecked)
        lay.addWidget(cb1); lay.addWidget(cb2); lay.addWidget(cb3)
        lay.addWidget(QLabel("ModernCheckBox"))
        mcb = ModernCheckBox("Custom-painted modern checkbox", is_dark=(mode != "light"))
        mcb.setChecked(True)
        lay.addWidget(mcb)
        row = QHBoxLayout()
        row.addWidget(QLabel("Toggle:"))
        tg = ToggleSwitch(is_dark=(mode != "light"))
        row.addWidget(tg)
        row.addStretch()
        lay.addLayout(row)
        lay.addWidget(QLabel("SearchableComboBox (was double-painting)"))
        scb = SearchableComboBox(is_dark=(mode != "light"))
        scb.addItems(["Alpha", "Beta", "Gamma"])
        scb.setCurrentText("Alpha")
        lay.addWidget(scb)
        spin_row = QHBoxLayout()
        spin_row.addWidget(QLabel("Spin:"))
        sp = QSpinBox()
        spin_row.addWidget(sp)
        spin_row.addStretch()
        lay.addLayout(spin_row)
        lay.addWidget(QLabel("TaskItemWidget rows"))
        for t in (t1, t2):
            tiw = TaskItemWidget(t, project_name="Apollo Platform", settings_manager=settings)
            lay.addWidget(tiw)
        panel.show()
        app.processEvents()
        path = f"{OUT}/widgets_{tag}.png"
        panel.grab().save(path)
        shots.append(path)
        panel.close()
        panel.deleteLater()
    except Exception as e:
        print("widget render failed:", e)

    # --- Chart (weekly) ---
    try:
        from todo_bird_app.widgets.dashboard_charts import AdvancedWeeklyActivityChart
        chart = AdvancedWeeklyActivityChart()
        daily = [(f"Sep {d}", 3 + (d * 7) % 11, (d * 5) % 9) for d in range(1, 31)]
        try:
            chart.set_data(daily)
        except Exception:
            chart.daily_data = daily
        chart.resize(900, 380)
        chart.show()
        # Force animation completion so bars render fully
        chart._animation_progress = 1.0
        app.processEvents()
        path = f"{OUT}/chart_{tag}.png"
        chart.grab().save(path)
        shots.append(path)
        chart.close()
        chart.deleteLater()
    except Exception as e:
        print("chart render failed:", e)

    return shots


import shutil
shutil.rmtree(OUT, ignore_errors=True)
os.makedirs(OUT, exist_ok=True)

all_shots = []
all_shots += render("dark", "dark")
all_shots += render("light", "light")

print("\n".join(all_shots))
print("TOTAL:", len(all_shots))
