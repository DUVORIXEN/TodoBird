# Startup Presentation Contract

## Principles
The Todo Bird startup window budget must be protected against "window explosions". Multiple subsystems (database recovery, core application logic, reminders, support/onboarding) may have a legitimate reason to present UI upon application launch. To prevent collisions, focus stealing, and user frustration, Todo Bird strictly enforces the following presentation hierarchy.

## Startup Precedence (P0 - P4)

### P0 — CRITICAL DATA/RECOVERY ERROR
**Condition:** If the database `PRAGMA integrity_check` fails on startup.
**Action:** Present a modal recovery/error dialog.
**Consequence:** Normal startup is HALTED. `MainWindow` is NOT instantiated or shown. The user must resolve the integrity issue or restore a backup.

### P1 — MAIN WINDOW
**Condition:** P0 passes.
**Action:** The `MainWindow` is instantiated and presented as the primary application surface.
**Consequence:** This is the anchor surface for all subsequent startup logic.

### P2 — LEGITIMATE REMINDER
**Condition:** The user has tasks matching the `startup_reminder` criteria (e.g. `every_app_open`, `daily_first_open`) and `ReminderPolicyService` evaluates them as due.
**Action:** The `ReminderDialog` is presented non-blockingly above the `MainWindow`.
**Constraint:** 
- Due to frozen architecture, one dialog is presented per due task. The `task_id` is used to suppress duplicate windows for the identical task. 
- Reminders must NEVER call `raise_()` or `activateWindow()` that steals OS-level focus away from the user's active context.

### P3 — OPTIONAL NONBLOCKING COMPANION
**Condition:** The Avocet desktop companion is enabled via Settings.
**Action:** The companion widget is presented on the desktop background.
**Constraint:** 
- Avocet must remain click-through, non-modal, and must not block `MainWindow`.
- Avocet self-terminates after its configured visibility duration (default 24s).

### P4 — PRODUCT PROMPTS (e.g., "Support Todo Bird ❤️")
**Condition:** Product capability flags allow automatic presentation, AND usage thresholds are met, AND cooldown periods have elapsed.
**Action:** Disabled during Controlled Beta (`SUPPORT_AUTOMATIC_PROMPTS_ENABLED = False`).
**Constraint:**
- When enabled in the future, P4 prompts MUST yield to any active modal dialog (including P2 Reminders or any user-opened file dialog).
- P4 prompts MUST NEVER auto-open simultaneously with other marketing/support dialogues.

## The Collision & Focus Rule
No background product prompt or reminder shall call `raise_()` or `activateWindow()` during ordinary startup after the user has begun interacting with `MainWindow`. (Note: Second-instance IPC activation legitimately requests `MainWindow` activation and is exempt from this rule).
