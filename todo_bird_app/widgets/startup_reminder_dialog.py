"""
Compatibility wrapper for legacy StartupReminderDialog imports.
Delegates directly to modern ReminderDialog.
"""

from todo_bird_app.widgets.reminder_dialog import ReminderDialog

class StartupReminderDialog(ReminderDialog):
    """
    Backwards compatibility alias for ReminderDialog.
    """
    pass
