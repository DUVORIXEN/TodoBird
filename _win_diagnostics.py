#!/usr/bin/env python3
"""TODO BIRD — Windows diagnostic run (checkbox / reminders / voice).

Run this on the Windows 11 machine with the SAME Python environment the app
uses, and paste the full output back:

    python _win_diagnostics.py

It prints a decision trace for each of the three open Windows issues:
  1. CHECKBOX  — stylesheet parse + tick rendering (verifies the QSS path fix).
  2. REMINDERS — exact per-task due/not-due decision trace, so "no reminder
                 was legitimately due" becomes distinguishable from a broken
                 reminder path.
  3. VOICE     — which playback path runs (Avocet player binary vs pyttsx3/
                 SAPI), and precisely where it stops being audible.
"""
import os
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TODO_BIRD_DISABLE_SINGLE_INSTANCE", "1")
os.environ.setdefault("TODO_BIRD_SYNC_APPEARANCE", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime

BAR = "=" * 72


def section(title):
    print(f"\n{BAR}\n  {title}\n{BAR}")


def main():
    # ------------------------------------------------------------------ app
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    from todo_bird_app.database import DatabaseManager
    from todo_bird_app.settings.settings_manager import SettingsManager
    from todo_bird_app.services.path_resolver import PathResolver

    db_path = PathResolver().get_database_path()
    print(f"database: {db_path}  (exists={db_path.exists()})")
    db = DatabaseManager.production(db_path)  # explicit read for diagnostics
    settings = SettingsManager(db)

    # ------------------------------------------------------- 1. CHECKBOX/QSS
    section("1. CHECKBOX / STYLESHEET (verifies the QSS path fix)")
    try:
        from pathlib import Path
        from PySide6.QtCore import qInstallMessageHandler
        from PySide6.QtWidgets import QCheckBox
        from todo_bird_app.services.appearance_service import AppearanceService

        appearance = AppearanceService.read(settings)
        tokens = AppearanceService.qss_tokens(appearance)
        print(f"CHECKMARK_IMAGE     = {tokens['CHECKMARK_IMAGE']}")
        print(f"INDETERMINATE_IMAGE = {tokens['INDETERMINATE_IMAGE']}")
        for key in ("CHECKMARK_IMAGE", "INDETERMINATE_IMAGE"):
            ok_posix = "\\" not in tokens[key]
            ok_exists = Path(tokens[key]).exists()
            print(f"  {key}: posix-safe={ok_posix}  file-exists={ok_exists}")

        raw = Path(
            Path(__file__).resolve().parent / "todo_bird_app" / "themes" / "dark.qss"
        ).read_text(encoding="utf-8")
        qss = raw
        for key, value in sorted(tokens.items(), key=lambda kv: len(kv[0]), reverse=True):
            qss = qss.replace(f"@{key}", value)

        warnings = []
        def handler(_mode, _ctx, message):
            text = str(message)
            if "parse" in text.lower() or "stylesheet" in text.lower():
                warnings.append(text)
        prev = qInstallMessageHandler(handler)
        try:
            probe = QCheckBox("probe")
            probe.setStyleSheet(qss)
            app.processEvents()
            probe.setStyleSheet("")
            probe.deleteLater()
        finally:
            qInstallMessageHandler(prev)
        print(f"stylesheet parse warnings: {len(warnings)}")
        for w in warnings[:3]:
            print(f"  ! {w}")

        # tick render check
        box = QCheckBox()
        box.setStyleSheet(qss)
        box.setChecked(True)
        box.resize(160, 28)
        box.show()
        app.processEvents()
        img = box.grab().toImage()
        from PySide6.QtCore import QRect
        colors = {
            img.pixelColor(x, y).name()
            for x in range(0, 18)
            for y in range(5, 23)
        }
        print(f"checked indicator distinct colors: {len(colors)} (>=3 means tick painted)")
        print(f"colors: {sorted(colors)[:6]}")
    except Exception:
        print("CHECKBOX DIAGNOSTIC ERROR:")
        traceback.print_exc()

    # -------------------------------------------------------- 2. REMINDERS
    section("2. REMINDERS (decision trace — why due / not due)")
    try:
        from todo_bird_app.controllers.task_controller import TaskController
        from todo_bird_app.models.task import TaskStatus
        from todo_bird_app.services.reminder_policy_service import ReminderPolicyService

        controller = TaskController(db)
        now = datetime.now()
        print(f"now                    = {now.isoformat()}")
        print(f"session_start_time     = {ReminderPolicyService._session_start_time.isoformat()}")
        print(f"  (a reminder only fires when its scheduled time is >= session start)")
        for key in (
            "reminder_policy",
            "startup_reminder",
            "startup_reminder_mode",
            "reminders_enabled",
            "reminder_lead_minutes",
        ):
            print(f"settings[{key!r:<24}] = {settings.get(key)!r}")

        tasks = controller.get_all_tasks()
        print(f"tasks total: {len(tasks)}")
        candidates = 0
        for t in tasks:
            if t.status in (TaskStatus.COMPLETED, TaskStatus.CANCELLED):
                continue
            has_rem = bool(
                getattr(t, "startup_reminder", False)
                or (getattr(t, "startup_reminder_mode", "off") not in ("off", "", None))
                or getattr(t, "planned_date", None)
                or getattr(t, "due_date", None)
            )
            if not has_rem:
                continue
            candidates += 1
            print(
                f"  #{t.id} [{t.status.value}] {t.title[:40]!r} "
                f"planned={t.planned_date} {t.planned_start_time or ''} "
                f"due={t.due_date or ''} {t.planned_end_time or ''} "
                f"startup_reminder={getattr(t, 'startup_reminder', False)} "
                f"mode={getattr(t, 'startup_reminder_mode', 'off')!r} "
                f"snoozed_until={getattr(t, 'snoozed_until', None)!r}"
            )
        if not candidates:
            print("  (no incomplete tasks carry any reminder-capable schedule)")

        due = ReminderPolicyService.get_due_reminders(
            controller, settings, current_dt=now, ignore_duplicate_guard=True
        )
        print(f"\nget_due_reminders() -> {len(due)} task(s) due RIGHT NOW:")
        for t in due:
            print(f"  #{t.id} {t.title[:50]!r}")

        shown = getattr(ReminderPolicyService, "_shown_in_session", set())
        print(f"shown-in-session duplicate guard: {sorted(shown)}")
        print(
            "\nINTERPRETATION:"
            "\n  - 0 tasks with reminder-capable schedule  -> nothing to remind (legit)"
            "\n  - scheduled time < session_start          -> missed-before-launch"
            " (by design, fires only for times inside this session)"
            "\n  - tasks present + in-window + due list empty -> REMINDER PATH BUG"
            " (copy this output)"
        )
    except Exception:
        print("REMINDER DIAGNOSTIC ERROR:")
        traceback.print_exc()

    # ------------------------------------------------------------- 3. VOICE
    section("3. VOICE (which playback path runs, where it stops)")
    try:
        print("--- pyttsx3 / SAPI direct ---")
        try:
            import pyttsx3
            print(f"pyttsx3 import OK: {pyttsx3.__version__ if hasattr(pyttsx3, '__version__') else 'unknown'}")
            engine = pyttsx3.init()
            print(f"engine init OK, driver={getattr(engine, 'driverName', '?')}")
            voices = engine.getProperty("voices") or []
            print(f"voices available: {len(voices)}")
            for v in voices[:6]:
                print(f"  - {v.name!r} id={getattr(v, 'id', '')!r}")
            engine.setProperty("rate", 165)
            engine.setProperty("volume", 1.0)
            print("speak test (MAIN thread — you should hear this):")
            engine.say("Todo Bird voice check. If you can hear this, SAPI works.")
            engine.runAndWait()
            print("  main-thread SAPI speak: finished without exception")
            engine.stop()
        except Exception:
            print("pyttsx3/SAPI FAILED:")
            traceback.print_exc()

        print("\n--- Avocet path (what the app actually calls first) ---")
        try:
            from todo_bird_app.services.avocet_voice_service import AvocetVoiceService
            player, device = AvocetVoiceService.get_audio_player_and_device()
            print(f"resolved audio player: {player!r} device: {device!r}")
            if not player:
                print(
                    "  !! NO PLAYER BINARY RESOLVED — AvocetVoiceService.speak_async "
                    "will no-op silently, and VoiceEngine.speak() returns WITHOUT "
                    "ever reaching pyttsx3. This is the most likely voice bug."
                )
        except Exception:
            print("Avocet player resolution failed:")
            traceback.print_exc()

        try:
            AvocetVoiceService.speak_async(
                "Todo Bird avocet voice path check.",
                settings_manager=settings,
            )
            print("speak_async() returned without exception (does NOT prove audio)")
        except Exception:
            print("speak_async() raised:")
            traceback.print_exc()
    except Exception:
        print("VOICE DIAGNOSTIC ERROR:")
        traceback.print_exc()

    print(f"\n{BAR}\nDONE — paste this entire output back for the next fix round.\n{BAR}")


if __name__ == "__main__":
    main()
