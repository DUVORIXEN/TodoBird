# Beta Morning Reminder Startup Audit

**STATUS:** CONFIGURATION_ONLY_NO_CODE_DEFECT

After a forensic audit of the Todo Bird reminder engine (`app.py`, `main_window.py`, `reminder_policy_service.py`, `task_dialog.py`, and `settings_view.py`), no code defects were found. Todo Bird explicitly enforces a configuration contract for "missed" morning reminders.

## The Contract
1. **Does Todo Bird intentionally scan for due reminders immediately at application startup?**
   Yes, `ReminderPolicyService.evaluate_startup_reminders` is invoked immediately on startup.
2. **If yes, at what point after startup?**
   In `app.py` directly before `app.exec()` is called, immediately following desktop companion initialization.
3. **Is the first scan immediate or does it wait for the 2-second timer?**
   Immediate. The 2-second polling timer (`MainWindow._reminder_poll_timer`) handles active runtime checks, whereas the startup sweep uses a dedicated immediate execution block.
4. **Which reminder states are eligible to show at startup?**
   Uncompleted, non-snoozed, unacknowledged tasks. **Crucially**, tasks whose scheduled time passed while the app was closed are explicitly dropped *unless* they possess a valid startup trigger configuration.
5. **Does a reminder require an exact date + time?**
   No. If only a date is provided, it defaults internally to `00:00` (midnight local time).
6. **Is there a “startup”, “at login”, “morning”, or “on app open” trigger mode?**
   Yes. Globally: "Startup reminder policy" in Settings. Task-level: "Launch reminder" drop-down in Task Editor.
7. **If the app was closed when the reminder became due, should the reminder appear next time Todo Bird starts?**
   **Only** if the user explicitly configured the task with a "Launch reminder" (e.g., "First opening of the day") OR the global setting is changed from its default. By default ("Scheduled Time Only"), missed reminders are suppressed on launch to prevent bombardment.
8. **If the reminder was previously snoozed, dismissed, completed, or already shown, what happens?**
   It is skipped securely using persistent dictionaries (`_snoozed_until`, `_acknowledged_occurrences`, and `_daily_shown_dates`).
9. **Is duplicate suppression correctly preventing repeated display without suppressing genuinely due reminders forever?**
   Yes. `_shown_in_session` tracks active session dialogs to prevent the 2-second timer from spawning duplicates. Snoozing a dialog successfully purges this flag, allowing it to reappear cleanly upon snooze expiry.
10. **Are reminder dates/times interpreted in local system time?**
   Yes, `datetime.now()` (local unlocalized system time) is used across the board for all comparisons.

---

## User Configuration Guide

Todo Bird defaults to **"Scheduled Time Only"** to prevent users from being bombarded with popup windows when launching the app. Because of this, if your computer or Todo Bird was closed at the time your reminder was scheduled, the app will deliberately *not* show it when you later open the app. 

If you want a morning reminder to pop up retroactively on launch, you must enable this behavior.

### Option A: Configure a Single Task (Recommended)
Use this if you only want specific, important morning tasks to pop up if missed.
1. Open the task in the **Task Editor** by double-clicking it.
2. Set your **Planned Date** and **Start Time** (e.g., 08:00).
3. Find the **"Launch reminder"** dropdown in the form.
4. Change it from "Off" to **"First opening of the day"**.
5. Save the task.

### Option B: Change the Global Behavior (For all reminders)
Use this if you want *any* task whose time has passed to popup whenever you open the app.
1. Open the Todo Bird **Settings**.
2. Navigate to the **Reminders** tab.
3. Locate the **"Startup reminder policy"** dropdown.
4. Change it from "Scheduled Time Only (Default...)" to **"Todo Bird Startup + Due Reminders"**.

### General Reminder Behavior:
* **Snooze:** Clicking Snooze hides the reminder and schedules it to reappear after the selected minutes, even if you close and reopen the app.
* **Dismiss:** Clicking Dismiss prevents this specific scheduled occurrence from appearing again today.
* **Testing:** To safely test, set a task time for 2 minutes from now. Close Todo Bird. Wait 3 minutes, then open Todo Bird. If you configured it correctly using the guide above, it will pop up immediately.
