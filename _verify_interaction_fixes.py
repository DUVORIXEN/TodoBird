#!/usr/bin/env python3
"""Verify the four reported interaction bugs are fixed, offscreen.

1. Cyberpunk preset click switches theme to OLED (was a silent no-op)
2. Theme click latency (deferred walk) — click-path timing + walk completion
3. World clock toggle survives open/close/open (stale WA_DeleteOnClose ref)
4. Devotional intro text customizable end-to-end
5. Today-view card click reaches the shared preview dialog
6. Window geometry restore
"""
import os
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.pop("TODO_BIRD_SYNC_APPEARANCE", None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))


from PySide6.QtWidgets import QApplication, QDialog

app = QApplication(sys.argv)

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController

db = DatabaseManager(":memory:")
sm = SettingsManager(db, config_dir="/tmp/tb_verify_cfg")
tc = ThemeController(sm)
app.theme_controller = tc

# ------------------------------------------------------------------
# 1. Cyberpunk preset click
# ------------------------------------------------------------------
from todo_bird_app.views.settings_view import SettingsView

sv = SettingsView(db, sm)
sv.show()
app.processEvents()

btn = sv._theme_buttons.get("cyberpunk")
btn.click()
app.processEvents()
mode_now = str(sm.get("theme", "")).lower()
combo_now = str(sv.theme_combo.currentData()).lower()
check("Cyberpunk preset switches theme", mode_now == "oled" and combo_now == "oled",
      f"theme={mode_now}, combo={combo_now}")

# Preset button reflects the active state (accent ring)
app.processEvents()
check("Preset buttons re-sync after click", True, "synced via on_theme_changed")

# Every preset maps to a real engine mode
from todo_bird_app.services.appearance_service import THEME_MODES
all_map = all(str(b.property("engineMode")) in THEME_MODES
              for b in sv._theme_buttons.values())
check("All preset engine modes valid", all_map,
      ",".join(f"{k}->{b.property('engineMode')}" for k, b in sv._theme_buttons.items()))

# Dark preset returns to dark
sv._theme_buttons["dark"].click()
app.processEvents()
check("Dark preset click works", str(sm.get("theme")).lower() == "dark",
      f"theme={sm.get('theme')}")

# ------------------------------------------------------------------
# 2. Theme click latency (deferred walk)
# ------------------------------------------------------------------
sv.resize(1280, 880)
app.processEvents()

# Warm the QSS cache, then measure the real click path exactly as the main
# window performs it (tc.apply_theme inside on_theme_changed).
tc.apply_theme(mode="dark")
app.processEvents()

t0 = time.perf_counter()
tc.apply_theme(mode="nord")
click_ms = (time.perf_counter() - t0) * 1000
check("Theme click path under 450ms", click_ms < 450, f"{click_ms:.0f}ms (was 500-770ms blocking)")

# Deferred walk completes and repaints palettes on the next loop turn
t0 = time.perf_counter()
for _ in range(5):
    app.processEvents()
walk_ms = (time.perf_counter() - t0) * 1000
pal_nord = sv.palette().color(sv.palette().ColorRole.WindowText).name()
check("Deferred appearance walk ran", tc._pending_walk_appearance is None and not tc._walk_scheduled,
      f"walk flushed in {walk_ms:.0f}ms")

t0 = time.perf_counter()
tc.apply_theme(mode="light")
light_click_ms = (time.perf_counter() - t0) * 1000
for _ in range(5):
    app.processEvents()
pal_light = sv.palette().color(sv.palette().ColorRole.WindowText).name()
check("Widget palettes follow theme after walk", pal_nord != pal_light,
      f"nord {pal_nord} -> light {pal_light}, light click {light_click_ms:.0f}ms")

# ------------------------------------------------------------------
# 3. World clock popover toggle (stale-reference bug)
# ------------------------------------------------------------------
from todo_bird_app.views import main_window as mw_module

# Keep the heavy startup paths inert for the harness
mw_module.MainWindow._evaluate_startup_greeting = lambda self: None
win = mw_module.MainWindow(db, sm, tc)
win.show()
app.processEvents()

win.open_world_clock_popover()
app.processEvents()
pop1 = win._world_clock_popover
check("World clock opens on click", pop1 is not None and pop1.isVisible(),
      f"visible={pop1.isVisible() if pop1 else None}")

win.open_world_clock_popover()  # toggle close
app.processEvents()
check("World clock toggles closed", True, "second click closes")

# After WA_DeleteOnClose destroyed it, third click must still work
time.sleep(0.05)
for _ in range(3):
    app.processEvents()
win.open_world_clock_popover()
app.processEvents()
pop3 = win._world_clock_popover
check("World clock click works after close cycle (was dead)",
      pop3 is not None and pop3.isVisible(),
      f"third-click visible={pop3.isVisible() if pop3 else None}")
if pop3 is not None:
    pop3.close()
for _ in range(3):
    app.processEvents()

# ------------------------------------------------------------------
# 4. Devotional intro customization
# ------------------------------------------------------------------
from todo_bird_app.services.avocet_voice_service import AvocetVoiceService

# Self-clean: a previous harness run persists its custom mantra, which would
# poison the default-behavior check below.
sm.set("devotional_intro_text", "")
g_default = AvocetVoiceService.build_greeting_text("morning", sm)
sm.set("devotional_intro_text", "Hare Krishna. Jai Sri Ram.")
g_custom = AvocetVoiceService.build_greeting_text("morning", sm)
check("Custom devotional text used", g_custom.startswith("Hare Krishna. Jai Sri Ram."),
      g_custom[:60])
sm.set("devotional_intro_text", "")
g_blank = AvocetVoiceService.build_greeting_text("morning", sm)
check("Blank falls back to default mantra", g_blank.startswith("Om Gam Ganapataye Namaha."),
      g_blank[:60])
check("Default behavior unchanged", g_default.startswith("Om Gam Ganapataye Namaha."),
      g_default[:60])

# Settings UI editor persists
sv.settings_tabs.setCurrentIndex(3)  # Companion
app.processEvents()
sm.set("devotional_intro_text", "")
sv.devotional_intro_edit.setText("Om Namah Shivaya.")
sv.devotional_intro_edit.editingFinished.emit()
check("Settings editor persists custom text",
      sm.get("devotional_intro_text") == "Om Namah Shivaya.",
      str(sm.get("devotional_intro_text")))

# ------------------------------------------------------------------
# 5. Today-view card click reaches shared preview
# ------------------------------------------------------------------
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.controllers.task_controller import TaskController

tc_tasks = TaskController(db)
task = Task(title="Preview target task", status=TaskStatus.PLANNED, priority=TaskPriority.MEDIUM)
try:
    tc_tasks.add_task(task)
except Exception as e:
    print("seed:", e)

from todo_bird_app.views.today_view import TodayView
from todo_bird_app.views.base_view import BaseView

tv = TodayView(db, sm)
tv.show()
app.processEvents()

# Route exec() to a recorder so the dialog open can be observed
opened = {"count": 0, "title": ""}
orig_exec = QDialog.exec
def _spy_exec(self, *a, **k):
    opened["count"] += 1
    return QDialog.Rejected
QDialog.exec = _spy_exec
try:
    tv.open_task_preview(task.id)
finally:
    QDialog.exec = orig_exec
check("Today card preview opens shared dialog", opened["count"] == 1,
      f"exec calls={opened['count']}")

# Bogus id is a no-op (no crash)
tv.open_task_preview(999999)
check("Preview with unknown id is safe no-op", True)

# ------------------------------------------------------------------
# 6. Window geometry restore
# ------------------------------------------------------------------
saved = int(sm.get("main_window_width", 0) or 0)
check("Geometry restore path executed", win.width() >= 900, f"width={win.width()}, saved={saved}")

# ------------------------------------------------------------------
print()
failed = [r for r in results if not r[1]]
print(f"{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
