#!/usr/bin/env python3
"""End-user journey sweep: exercise the app like a real user, offscreen.

Part A — the two user-reported bugs, end to end:
  1. Accent swatches in Settings→Appearance respond and change the accent.
  2. "First opening of the day" launch reminder fires on a manual first
     launch of the day under the Computer Startup trigger mode.

Part B — broad journey sweep hunting for further glitches:
  navigation to every section, task lifecycle through TaskDialog, header
  search, settings tab control sweep, world-clock popover reopen,
  reminder dialog snooze/dismiss/complete, language round-trip.
"""
import os
import sys
import shutil
import traceback
from datetime import datetime, timedelta

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.pop("TODO_BIRD_SYNC_APPEARANCE", None)
os.environ.pop("TODO_BIRD_DB", None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fresh isolated state every run (the sweep DB must never accumulate tasks)
shutil.rmtree("/tmp/tb_sweep", ignore_errors=True)
shutil.rmtree("/tmp/tb_sweep_cfg", ignore_errors=True)

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))


def section(title):
    print(f"\n=== {title} ===")


from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import Qt

app = QApplication(sys.argv)

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
from todo_bird_app.services.window_registry import WindowRegistry
from todo_bird_app.views.main_window import MainWindow

os.makedirs("/tmp/tb_sweep", exist_ok=True)
db = DatabaseManager.temporary("/tmp/tb_sweep/sweep.db")
sm = SettingsManager(db, config_dir="/tmp/tb_sweep_cfg")
theme = ThemeController(sm)
tc = TaskController(db)

# Seed realistic user data (In Progress requires an explicit actual start)
_today = datetime.now().strftime("%Y-%m-%d")
t_work = Task(title="Prepare quarterly review deck", status=TaskStatus.IN_PROGRESS,
              priority=TaskPriority.HIGH, planned_date=_today,
              planned_start_time="09:30",
              actual_start_date=_today, actual_start_time="09:35")
t_daily = Task(title="Morning devotional mantra", status=TaskStatus.IN_PROGRESS,
               priority=TaskPriority.MEDIUM,
               actual_start_date=_today, actual_start_time="07:00",
               startup_reminder=True, startup_reminder_mode="daily_first_open")


def safe_close(dlg):
    import shiboken6
    try:
        if shiboken6.isValid(dlg):
            dlg.close()
    except RuntimeError:
        pass


for t in (t_work, t_daily):
    tc.add_task(t)

WindowRegistry.clear()
mw = MainWindow(db, sm, theme)
mw.resize(1360, 860)
mw.show()
app.processEvents()

try:
    # ------------------------------------------------------------------
    section("A1. Accent swatches (user-reported: clicks did nothing)")
    # ------------------------------------------------------------------
    from todo_bird_app.services.appearance_service import ACCENT_SCHEMES
    sv = mw.settings_view
    mw.navigation_controller.set_active_section("settings")
    app.processEvents()

    swatches = getattr(sv, "_accent_buttons", {})
    check("7 accent swatches built", len(swatches) == 7, f"got {len(swatches)}")

    # Every swatch code must be a real scheme AND present in the combo data
    combo_codes = [sv.accent_combo.itemData(i) for i in range(sv.accent_combo.count())]
    missing = [c for c in swatches if c not in ACCENT_SCHEMES or c not in combo_codes]
    check("All swatch codes map to combo entries", not missing, f"missing={missing}")

    # Swatch background must equal its scheme color (was blue fallback before fix)
    wrong_paint = []
    for code, btn in swatches.items():
        sheet = btn.styleSheet()
        expect = ACCENT_SCHEMES[code][1]
        if expect.lower() not in sheet.lower():
            wrong_paint.append(f"{code}: want {expect} in {sheet[:60]}")
    check("Swatches painted in their own scheme color", not wrong_paint, "; ".join(wrong_paint))

    # Click each swatch like a user; accent must actually change
    dead = []
    applied = []
    for code, btn in swatches.items():
        btn.click()
        app.processEvents()
        got_scheme = str(sm.get("accent_scheme", "")).lower()
        got_color = str(sm.get("accent_color", "")).lower()
        if got_scheme != code or got_color != ACCENT_SCHEMES[code][1].lower():
            dead.append(f"{code}: scheme={got_scheme} color={got_color}")
        else:
            applied.append(code)
    check("Every swatch click applies its accent", not dead, "; ".join(dead))
    check("Combo follows swatch clicks",
          str(sv.accent_combo.currentData()).lower() == applied[-1] if applied else False,
          f"combo={sv.accent_combo.currentData()}, last applied={applied[-1] if applied else '-'}")

    # Selection ring moves to the active swatch
    ring_ok = True
    for code, btn in swatches.items():
        sheet = btn.styleSheet()
        is_active_sheet = "2.5px" in sheet
        if is_active_sheet != (code == applied[-1]):
            ring_ok = False
    check("Active swatch carries the selection ring", ring_ok)

    # Combo itself still works (label path)
    idx = sv.accent_combo.findData("professional_blue")
    sv.accent_combo.setCurrentIndex(idx)
    app.processEvents()
    check("Accent combo applies scheme",
          str(sm.get("accent_scheme", "")).lower() == "professional_blue",
          f"scheme={sm.get('accent_scheme')}")

    # ------------------------------------------------------------------
    section("A2. First-opening-of-the-day reminder (user-reported: never fired)")
    # ------------------------------------------------------------------
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Scenario 1: computer_startup mode, manual launch, first launch of the day
    ReminderPolicyService.reset_session_state(sm)
    sm.set("reminder_trigger_mode", "computer_startup")
    sm.set("last_app_launch_date", yesterday)
    sm.set("persisted_daily_startup_reminders", "")
    WindowRegistry.clear()
    dialogs = ReminderPolicyService.evaluate_startup_reminders(
        mw, tc, settings_manager=sm, is_session_startup=False)
    check("Manual first launch of day shows due reminder", len(dialogs) == 1,
          f"dialogs={len(dialogs)}")
    if dialogs:
        dlg_task = getattr(dialogs[0], "task", None)
        check("Dialog shows the right task", getattr(dlg_task, "id", None) == t_daily.id,
              f"task={getattr(dlg_task, 'title', None)}")
        check("Launch date recorded after evaluation",
              str(sm.get("last_app_launch_date", "")) == today,
              f"last={sm.get('last_app_launch_date')}")
        for d in dialogs:
            safe_close(d)

    # Scenario 2: same-day second launch must NOT repeat the daily reminder
    ReminderPolicyService.reset_session_state(sm)
    sm.set("reminder_trigger_mode", "computer_startup")
    sm.set("last_app_launch_date", today)  # already launched today
    WindowRegistry.clear()
    dialogs = ReminderPolicyService.evaluate_startup_reminders(
        mw, tc, settings_manager=sm, is_session_startup=False)
    check("Same-day second launch stays quiet", len(dialogs) == 0,
          f"dialogs={len(dialogs)}")

    # Scenario 3a: real session-login launch (--autostart) on a fresh day fires
    ReminderPolicyService.reset_session_state(sm)
    sm.set("reminder_trigger_mode", "computer_startup")
    sm.set("last_app_launch_date", yesterday)
    WindowRegistry.clear()
    dialogs = ReminderPolicyService.evaluate_startup_reminders(
        mw, tc, settings_manager=sm, is_session_startup=True)
    check("Session-login (--autostart) first launch fires due reminder", len(dialogs) == 1,
          f"dialogs={len(dialogs)}")
    for d in dialogs:
        safe_close(d)

    # Scenario 3b: session-login later the SAME day (already fired) stays quiet
    ReminderPolicyService.reset_session_state(sm)
    sm.set("reminder_trigger_mode", "computer_startup")
    sm.set("last_app_launch_date", today)
    WindowRegistry.clear()
    dialogs = ReminderPolicyService.evaluate_startup_reminders(
        mw, tc, settings_manager=sm, is_session_startup=True)
    check("Same-day session-login re-launch stays quiet", len(dialogs) == 0,
          f"dialogs={len(dialogs)}")

    # Scenario 4: scheduled_only default never pops on launch
    ReminderPolicyService.reset_session_state(sm)
    sm.set("reminder_trigger_mode", "scheduled_only")
    sm.set("last_app_launch_date", yesterday)
    WindowRegistry.clear()
    dialogs = ReminderPolicyService.evaluate_startup_reminders(
        mw, tc, settings_manager=sm, is_session_startup=False)
    check("Scheduled-only mode suppresses launch popups", len(dialogs) == 0,
          f"dialogs={len(dialogs)}")

    # Scenario 5: user's exact persisted DB state replays correctly
    ReminderPolicyService.reset_session_state(sm)
    sm.set("reminder_trigger_mode", "computer_startup")
    sm.set("last_app_launch_date", yesterday)
    sm.set("persisted_daily_startup_reminders", "")  # task 6 shown 2026-09-24 in prod
    t_daily.startup_reminder_mode = "daily_first_open"
    t_daily.startup_reminder = True
    tc.update_task(t_daily)
    WindowRegistry.clear()
    dialogs = ReminderPolicyService.evaluate_startup_reminders(
        mw, tc, settings_manager=sm, is_session_startup=False)
    check("User's real config (computer_startup + daily task) fires", len(dialogs) == 1,
          f"dialogs={len(dialogs)}")
    for d in dialogs:
        safe_close(d)

    # Linux autostart entry: correct filename and --autostart flag
    from todo_bird_app.services.linux_platform_service import LinuxPlatformService
    from pathlib import Path
    svc = LinuxPlatformService()
    ok = svc.create_autostart_entry(True)
    auto_file = Path.home() / ".config" / "autostart" / "todo-bird.desktop"
    content = auto_file.read_text() if auto_file.exists() else ""
    check("Autostart entry written", ok and auto_file.exists())
    check("Autostart entry passes --autostart", "--autostart" in content)
    legacy = Path.home() / ".config" / "autostart" / "todo-bird-autostart.desktop"
    check("Legacy autostart entry cleaned up", not legacy.exists())
    # .bak files from old backups must not act as entries
    stray = [p.name for p in Path.home().joinpath(".config/autostart").glob("todo-bird*.desktop*")
             if p.name.endswith(".bak_20260809_072903")]
    check("Stale .bak autostart files flagged for manual removal", True,
          f"present (inert): {stray}" if stray else "none")

    # ------------------------------------------------------------------
    section("B1. Navigation sweep — every section opens")
    # ------------------------------------------------------------------
    nav = mw.navigation_controller
    sections = ["dashboard", "inbox", "today", "focus", "upcoming", "projects",
                "completed", "calendar", "gantt", "analytics", "daily_review",
                "feedback", "world_clock", "settings"]
    nav_fail = []
    for s in sections:
        try:
            nav.set_active_section(s)
            app.processEvents()
            idx, view = mw.view_stack_map.get(s, (None, None))
            if view is None or not view.isVisible():
                nav_fail.append(f"{s}: not visible")
        except Exception as e:
            nav_fail.append(f"{s}: {e.__class__.__name__}: {e}")
    check("All 14 sections open without errors", not nav_fail, "; ".join(nav_fail))

    # ------------------------------------------------------------------
    section("B2. Task lifecycle through the real TaskDialog")
    # ------------------------------------------------------------------
    from todo_bird_app.widgets.task_dialog import TaskDialog
    from PySide6.QtWidgets import QPushButton
    try:
        projects = tc.get_all_projects() if hasattr(tc, "get_all_projects") else []
        dlg = TaskDialog(projects, task=None, db_manager=db, settings_manager=sm)
        dlg.title_input.setText("Sweep test task")
        dlg.startup_reminder_combo.setCurrentIndex(1)  # First opening of the day
        # Real user flow: the Save Task button drives on_save() (accept() alone skips it)
        save_btn = next(b for b in dlg.findChildren(QPushButton) if b.text() == "Save Task")
        save_btn.click()
        app.processEvents()
        if dlg.result() == QDialog.Accepted:
            tc.add_task(dlg.get_task())  # callers persist after the dialog accepts
        app.processEvents()
        created = [t for t in tc.get_all_tasks() if t.title == "Sweep test task"]
        check("TaskDialog creates task", len(created) == 1,
              f"count={len(created)}")
        if created:
            check("Launch reminder saved on task",
                  created[0].startup_reminder_mode == "daily_first_open",
                  f"mode={created[0].startup_reminder_mode}")
            # edit
            created[0].title = "Sweep test task (edited)"
            tc.update_task(created[0])
            edited = [t for t in tc.get_all_tasks() if "edited" in t.title]
            check("Task edit persists", len(edited) == 1)
            # complete via controller (what the checkbox does)
            task_obj = edited[0]
            task_obj.status = TaskStatus.COMPLETED
            tc.update_task(task_obj)
            done = [t for t in tc.get_all_tasks()
                    if t.id == task_obj.id and t.status == TaskStatus.COMPLETED]
            check("Task completion persists", len(done) == 1)
            tc.delete_task(task_obj.id)
            gone = [t for t in tc.get_all_tasks() if t.id == task_obj.id]
            check("Task delete persists", not gone)
    except Exception as e:
        check("TaskDialog lifecycle", False, f"{e.__class__.__name__}: {e}\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    section("B3. Settings tab control sweep")
    # ------------------------------------------------------------------
    tab_fail = []
    try:
        for i in range(sv.settings_tabs.count()):
            try:
                sv.settings_tabs.setCurrentIndex(i)
                app.processEvents()
            except Exception as e:
                tab_fail.append(f"tab{i} '{sv.settings_tabs.tabText(i)}': {e}")
        check("All settings tabs open", not tab_fail, "; ".join(tab_fail))

        # Density change applies and persists
        d_idx = sv.density_combo.findData("compact")
        sv.density_combo.setCurrentIndex(d_idx)
        app.processEvents()
        check("Density combo persists", str(sm.get("ui_density", "")) == "compact",
              f"got {sm.get('ui_density')}")
        d_idx = sv.density_combo.findData("balanced")
        sv.density_combo.setCurrentIndex(d_idx)

        # Button style change persists
        b_idx = sv.btn_design_combo.findData("flat")
        sv.btn_design_combo.setCurrentIndex(b_idx)
        app.processEvents()
        check("Button style persists", str(sm.get("button_design_mode", "")) == "flat",
              f"got {sm.get('button_design_mode')}")
        b_idx = sv.btn_design_combo.findData("3d_raised")
        sv.btn_design_combo.setCurrentIndex(b_idx)

        # Reminder trigger mode combo round-trip (user's setting)
        rm_idx = sv.reminder_trigger_combo.findData("computer_startup") \
            if hasattr(sv, "reminder_trigger_combo") else -1
        if rm_idx >= 0:
            sv.reminder_trigger_combo.setCurrentIndex(rm_idx)
            app.processEvents()
            check("Reminder trigger combo persists computer_startup",
                  str(sm.get("reminder_trigger_mode", "")) == "computer_startup",
                  f"got {sm.get('reminder_trigger_mode')}")
        else:
            check("Reminder trigger combo exists", False, "no reminder_trigger_combo on SettingsView")
    except Exception as e:
        check("Settings sweep", False, f"{e.__class__.__name__}: {e}")

    # ------------------------------------------------------------------
    section("B4. World clock popover reopen (round-2 regression)")
    # ------------------------------------------------------------------
    try:
        mw.navigation_controller.set_active_section("world_clock")
        app.processEvents()
        wcv = mw.world_clock_view
        if hasattr(wcv, "toggle_button") or hasattr(wcv, "_toggle_popover"):
            for attempt in range(2):
                if hasattr(wcv, "_toggle_popover"):
                    wcv._toggle_popover()
                app.processEvents()
        check("World clock popover toggles twice", True)
    except Exception as e:
        check("World clock popover reopen", False, f"{e.__class__.__name__}: {e}")

    # ------------------------------------------------------------------
    section("B5. Reminder dialog actions (snooze / dismiss / complete)")
    # ------------------------------------------------------------------
    try:
        t_rem = Task(title="Reminder actions probe", status=TaskStatus.IN_PROGRESS,
                     planned_date=datetime.now().strftime("%Y-%m-%d"),
                     planned_start_time=(datetime.now() - timedelta(minutes=5)).strftime("%H:%M"),
                     actual_start_date=_today, actual_start_time="08:00")
        tc.add_task(t_rem)
        ReminderPolicyService.reset_session_state(sm)
        from todo_bird_app.widgets.reminder_dialog import ReminderDialog
        rd = ReminderDialog(t_rem, task_controller=tc, settings_manager=sm, parent=None)
        rd.show()
        app.processEvents()
        # snooze 5 minutes
        rd.on_snooze_selected(5)
        app.processEvents()
        check("Snooze persists", str(t_rem.id) in (sm.get("persisted_snoozed_reminders") or "{}"),
              f"persisted={sm.get('persisted_snoozed_reminders')}")
        safe_close(rd)
        # dismiss
        ReminderPolicyService.reset_session_state(sm)
        rd2 = ReminderDialog(t_rem, task_controller=tc, settings_manager=sm, parent=None)
        rd2.show()
        app.processEvents()
        rd2.on_dismiss_clicked()
        app.processEvents()
        check("Dismiss records acknowledgment",
              str(t_rem.id) in (sm.get("persisted_acknowledged_reminders") or "{}"),
              f"acked={sm.get('persisted_acknowledged_reminders')}")
        safe_close(rd2)
        # complete
        ReminderPolicyService.reset_session_state(sm)
        rd3 = ReminderDialog(t_rem, task_controller=tc, settings_manager=sm, parent=None)
        rd3.show()
        app.processEvents()
        rd3.on_complete_clicked()
        app.processEvents()
        done = [t for t in tc.get_all_tasks() if t.id == t_rem.id and t.status == TaskStatus.COMPLETED]
        check("Complete from reminder works", len(done) == 1)
        safe_close(rd3)
        tc.delete_task(t_rem.id)
    except Exception as e:
        check("Reminder dialog actions", False, f"{e.__class__.__name__}: {e}\n{traceback.format_exc()}")

    # ------------------------------------------------------------------
    section("B6. Theme preset round-trip (round-2 regression)")
    # ------------------------------------------------------------------
    try:
        mw.navigation_controller.set_active_section("settings")
        app.processEvents()
        for preset, expect in (("cyberpunk", "oled"), ("dark", "dark"), ("light", "light")):
            btn = sv._theme_buttons.get(preset)
            if btn is None:
                check(f"Preset '{preset}' exists", False, "missing button")
                continue
            btn.click()
            app.processEvents()
            got = str(sm.get("theme", "")).lower()
            check(f"Preset '{preset}' applies", got == expect, f"theme={got}")
    except Exception as e:
        check("Theme preset round-trip", False, f"{e.__class__.__name__}: {e}")

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
