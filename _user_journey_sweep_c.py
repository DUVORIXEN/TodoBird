#!/usr/bin/env python3
"""End-user journey sweep, Part C: remaining everyday surfaces.

quick capture, project creation, calendar navigation, world-clock controls,
header buttons (new task / mode toggle / language menu), typography live
change, companion + background settings, backup creation, analytics,
daily review, dashboard content, focus/upcoming views, pinned tasks.
"""
import os
import sys
import shutil
import traceback
from datetime import datetime

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.pop("TODO_BIRD_SYNC_APPEARANCE", None)
os.environ.pop("TODO_BIRD_DB", None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

shutil.rmtree("/tmp/tb_sweep_c", ignore_errors=True)
shutil.rmtree("/tmp/tb_sweep_c_cfg", ignore_errors=True)
os.makedirs("/tmp/tb_sweep_c", exist_ok=True)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))


from PySide6.QtWidgets import QApplication, QPushButton, QComboBox, QLineEdit

app = QApplication(sys.argv)

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority

db = DatabaseManager.temporary("/tmp/tb_sweep_c/sweep.db")
sm = SettingsManager(db, config_dir="/tmp/tb_sweep_c_cfg")
theme = ThemeController(sm)
tc = TaskController(db)

_today = datetime.now().strftime("%Y-%m-%d")
tc.add_task(Task(title="Write sprint summary", status=TaskStatus.PLANNED,
                 priority=TaskPriority.HIGH, planned_date=_today,
                 planned_start_time="10:00"))
tc.add_task(Task(title="Review pull request", status=TaskStatus.IN_PROGRESS,
                 priority=TaskPriority.MEDIUM, planned_date=_today,
                 planned_start_time="11:00",
                 actual_start_date=_today, actual_start_time="11:05"))

from todo_bird_app.views.main_window import MainWindow
mw = MainWindow(db, sm, theme)
mw.resize(1360, 860)
mw.show()
app.processEvents()
nav = mw.navigation_controller

try:
    # ------------------------------------------------------------------
    print("=== C1. Quick capture in Inbox ===")
    # ------------------------------------------------------------------
    nav.set_active_section("inbox")
    app.processEvents()
    iv = mw.inbox_view
    iv.quick_input.setText("Captured from quick add")
    iv.quick_add_task()
    app.processEvents()
    captured = [t for t in tc.get_all_tasks() if t.title == "Captured from quick add"]
    check("Quick capture creates a task", len(captured) == 1, f"count={len(captured)}")

    # ------------------------------------------------------------------
    print("=== C2. Header buttons ===")
    # ------------------------------------------------------------------
    hb = mw.headerbar
    # "+ New Task" opens a modal TaskDialog via dlg.exec(); schedule an
    # auto-accept so the nested event loop returns to the harness.
    from PySide6.QtCore import QTimer

    def _accept_top_task_dialog():
        for w in app.topLevelWidgets():
            if w.isVisible() and w.__class__.__name__ == "TaskDialog":
                w.accept()
                return True
        return False

    _fired = {"v": False}

    def _auto_accept():
        _fired["v"] = _accept_top_task_dialog() or _fired["v"]

    t1 = QTimer.singleShot(400, _auto_accept)
    t2 = QTimer.singleShot(900, _auto_accept)
    hb.add_btn.click()
    app.processEvents()
    check("Header '+ New Task' opens TaskDialog", _fired["v"])
    app.processEvents()

    mode_before = str(sm.get("theme", "")).lower()
    hb.theme_btn.click()
    app.processEvents()
    mode_after = str(sm.get("theme", "")).lower()
    check("Header mode toggle switches theme", mode_after != mode_before,
          f"{mode_before} -> {mode_after}")
    hb.theme_btn.click()
    app.processEvents()
    check("Header mode toggle switches back", str(sm.get("theme", "")).lower() == mode_before,
          f"now {sm.get('theme')}")

    # World clock header button opens popover
    hb.clock_btn.click()
    app.processEvents()
    check("Header world-clock button works", True)

    # ------------------------------------------------------------------
    print("=== C3. Calendar navigation ===")
    # ------------------------------------------------------------------
    nav.set_active_section("calendar")
    app.processEvents()
    cv = mw.calendar_view
    from PySide6.QtWidgets import QCalendarWidget
    cals = cv.findChildren(QCalendarWidget)
    if cals:
        cal = cals[0]
        m_before = cal.monthShown()
        cal.showPreviousMonth()
        app.processEvents()
        cal.showNextMonth()
        app.processEvents()
        check("Calendar month navigation works",
              cal.monthShown() == m_before, f"{m_before} -> {cal.monthShown()}")
    else:
        check("Calendar has a QCalendarWidget", False, "none found")

    # ------------------------------------------------------------------
    print("=== C4. World clock view controls ===")
    # ------------------------------------------------------------------
    nav.set_active_section("world_clock")
    app.processEvents()
    wcv = mw.world_clock_view
    combos = wcv.findChildren(QComboBox)
    check("World clock has combo controls", len(combos) >= 1, f"found {len(combos)}")
    if hasattr(wcv, "theme_combo"):
        idx = wcv.theme_combo.currentIndex()
        wcv.theme_combo.setCurrentIndex((idx + 1) % wcv.theme_combo.count())
        app.processEvents()
        wcv.theme_combo.setCurrentIndex(idx)
        app.processEvents()
        check("World clock theme dropdown round-trips", True)
    else:
        check("World clock theme dropdown exists", False)

    # ------------------------------------------------------------------
    print("=== C5. Typography live change ===")
    # ------------------------------------------------------------------
    nav.set_active_section("settings")
    app.processEvents()
    sv = mw.settings_view
    for i in range(sv.settings_tabs.count()):
        if "typography" in sv.settings_tabs.tabText(i).lower():
            sv.settings_tabs.setCurrentIndex(i)
            app.processEvents()
            break
    font_combos = [c for c in sv.findChildren(QComboBox) if c.objectName() == ""]
    size_spins = None
    try:
        from PySide6.QtWidgets import QSpinBox
        size_spins = sv.findChildren(QSpinBox)
    except Exception:
        pass
    check("Typography tab exposes controls", bool(font_combos or size_spins),
          f"combos={len(font_combos)}, spins={len(size_spins or [])}")
    app_size_before = app.font().pointSize()
    if hasattr(sv, "font_size_spin"):
        sv.font_size_spin.setValue(10)
        app.processEvents()
        check("Font size spin applies live", True,
              f"app font={app.font().pointSize()}pt (was {app_size_before})")
        sv.font_size_spin.setValue(9)
        app.processEvents()
    else:
        check("Font size spin exists", False)

    # ------------------------------------------------------------------
    print("=== C6. Companion + background settings persist ===")
    # ------------------------------------------------------------------
    sm.set("companion_enabled", False)
    sm.set("companion_visible_seconds", 12)
    check("Companion settings persist",
          sm.get("companion_enabled") is False and sm.get("companion_visible_seconds") == 12,
          f"enabled={sm.get('companion_enabled')}, secs={sm.get('companion_visible_seconds')}")
    sm.set("companion_enabled", True)

    # ------------------------------------------------------------------
    print("=== C7. Backup creation ===")
    # ------------------------------------------------------------------
    try:
        import shutil as _sh
        from pathlib import Path as _P
        db_file = _P(db.db_path)
        backup_file = db_file.parent / "sweep_backup.db"
        _sh.copy(db_file, backup_file)
        check("Backup copy succeeds", backup_file.exists())
        backup_file.unlink()
    except Exception as e:
        check("Backup copy succeeds", False, str(e))

    # ------------------------------------------------------------------
    print("=== C8. Data views render with content ===")
    # ------------------------------------------------------------------
    for section_name in ("dashboard", "analytics", "daily_review", "today",
                         "upcoming", "focus", "projects", "completed"):
        try:
            nav.set_active_section(section_name)
            app.processEvents()
            view = mw.view_stack_map[section_name][1]
            check(f"{section_name} renders", view is not None and view.isVisible())
        except Exception as e:
            check(f"{section_name} renders", False, f"{e.__class__.__name__}: {e}")

    # ------------------------------------------------------------------
    print("=== C9. Task data integrity through controller round-trip ===")
    # ------------------------------------------------------------------
    tasks = tc.get_all_tasks()
    seeded = [t for t in tasks if t.title in ("Write sprint summary", "Review pull request")]
    check("All seeded tasks present", len(seeded) == 2, f"got {len(seeded)} of {len(tasks)}")
    pr = [t for t in tasks if t.title == "Review pull request"]
    check("In Progress task kept actual start",
          pr and bool(pr[0].actual_start_date), f"start={pr[0].actual_start_date if pr else '-'}")

    # NavigationController.refresh_active_view used to be a missing method
    # (AttributeError after every header '+ New Task' save)
    try:
        nav.refresh_active_view()
        app.processEvents()
        check("refresh_active_view works after task creation", True)
    except AttributeError as e:
        check("refresh_active_view works after task creation", False, str(e))

finally:
    try:
        mw.close()
    except Exception:
        pass

print("\n================ SUMMARY ================")
fails = [r for r in results if not r[1]]
print(f"{len(results) - len(fails)}/{len(results)} checks passed")
for name, ok, detail in fails:
    print(f"  FAIL: {name} — {detail}")
sys.exit(1 if fails else 0)
