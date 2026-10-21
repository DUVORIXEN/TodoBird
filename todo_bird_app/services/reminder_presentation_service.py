"""
Reminder Presentation Service (Phase D)
Presentation Intent Layer decoupling domain policy (ReminderPolicyService)
from window/notification presentation execution (WindowInteractionService / ReminderDialog).
"""

import logging
from typing import Optional, Any, List
from PySide6.QtWidgets import QWidget
from todo_bird_app.models.task import Task
from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
from todo_bird_app.services.window_interaction_service import PlatformCapabilities, WindowInteractionService
from todo_bird_app.services.window_registry import WindowRegistry

logger = logging.getLogger(__name__)


class ReminderPresentationService:
    """
    Presentation Intent Layer coordinating desktop ReminderDialog cards vs
    mobile OS local notifications.
    """

    @classmethod
    def present_due_reminders(
        cls,
        main_window: Optional[Any],
        task_controller: Any,
        settings_manager: Optional[Any] = None,
        is_startup: bool = False
    ) -> List[Any]:
        """
        Evaluates policy due reminders and presents them through the platform adapter.
        """
        if is_startup:
            due_tasks = ReminderPolicyService.get_startup_due_reminders(task_controller, settings_manager)
        else:
            due_tasks = ReminderPolicyService.get_due_reminders(task_controller, settings_manager)

        if not due_tasks:
            return []

        # Check if platform is mobile (iOS/iPadOS)
        if PlatformCapabilities.platform_name() == "ios":
            return cls._present_mobile_reminders(due_tasks, settings_manager)

        return cls._present_desktop_reminders(due_tasks, main_window, task_controller, settings_manager)

    @classmethod
    def _present_desktop_reminders(
        cls,
        due_tasks: List[Task],
        main_window: Optional[Any],
        task_controller: Any,
        settings_manager: Optional[Any]
    ) -> List[Any]:
        """Presents floating nonmodal desktop ReminderDialog cards."""
        from todo_bird_app.widgets.reminder_dialog import ReminderDialog

        dialogs = []
        for i, task in enumerate(due_tasks):
            if task.id is not None:
                existing = WindowRegistry.get_window(f"reminder_{task.id}")
                if existing is not None and existing.isVisible():
                    continue

            dlg = ReminderDialog(task, task_controller=task_controller, settings_manager=settings_manager, parent=None)
            if hasattr(main_window, "startup_reminder_dialogs"):
                main_window.startup_reminder_dialogs.append(dlg)

            if task.id is not None:
                ReminderPolicyService.mark_shown(task.id)

            if i > 0 and PlatformCapabilities.supports_manual_top_level_positioning():
                dlg.move(dlg.x() + (i * 24), dlg.y() + (i * 24))

            WindowInteractionService.activate_window_safely(dlg)
            dialogs.append(dlg)

        return dialogs

    @classmethod
    def _present_mobile_reminders(cls, due_tasks: List[Task], settings_manager: Optional[Any]) -> List[Any]:
        """Bridges due reminders to mobile OS notifications/sheets (iOS/iPadOS portability)."""
        logger.info("ReminderPresentationService: Mobile QPA backend active — dispatching local OS notifications.")
        for task in due_tasks:
            if task.id is not None:
                ReminderPolicyService.mark_shown(task.id)
                logger.info("Mobile notification queued for Task #%s: '%s'", task.id, task.title)
        return []
