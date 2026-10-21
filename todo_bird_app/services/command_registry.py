"""
Command Registry Service (Batch 3.10J)
Centralized keyboard shortcut and command management for Todo Bird.
Provides a singleton registry of named commands with key sequences,
supporting global shortcuts (bound to MainWindow) and context-local
shortcuts (documented for per-widget binding).
"""

import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


@dataclass
class CommandInfo:
    """Descriptor for a registered command."""
    command_id: str
    display_name: str
    shortcut: Optional[str] = None
    scope: str = "global"  # "global" or "local"
    tooltip: str = ""
    callback: Optional[Callable] = field(default=None, repr=False)


class CommandRegistry:
    """
    Singleton registry for application-wide keyboard commands.

    Global commands are automatically bound as QShortcut on the parent widget.
    Local commands are registered for documentation/tooltip purposes only;
    individual widgets create their own QShortcut instances.
    """
    _instance: Optional["CommandRegistry"] = None
    _commands: Dict[str, CommandInfo] = {}
    _shortcuts: Dict[str, QShortcut] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._commands = {}
            cls._instance._shortcuts = {}
            cls._instance.ensure_standard_commands()
        return cls._instance

    def ensure_standard_commands(self, parent: Optional[QWidget] = None, callbacks: Optional[Dict[str, Callable]] = None):
        """Ensures that all standard Todo Bird keyboard commands are registered."""
        callbacks = callbacks or {}

        defaults = [
            ("new_task", "Create New Task", "Ctrl+N", "global", "Open the new task creation dialog"),
            ("open_command_palette", "Command Palette", "Ctrl+K", "global", "Open the quick command palette"),
            ("open_settings", "Settings", "Ctrl+,", "global", "Navigate to application settings"),
            ("quit_application", "Quit Application", "Ctrl+Q", "global", "Close Todo Bird"),
            ("format_bold", "Bold", "Ctrl+B", "local", "Toggle bold formatting in rich text editor"),
            ("format_italic", "Italic", "Ctrl+I", "local", "Toggle italic formatting in rich text editor"),
            ("format_underline", "Underline", "Ctrl+U", "local", "Toggle underline formatting in rich text editor"),
        ]

        for cmd_id, name, shortcut, scope, tooltip in defaults:
            cb = callbacks.get(cmd_id, lambda: None)
            if cmd_id not in self._commands or (parent is not None and scope == "global" and cmd_id in callbacks):
                self.register(
                    command_id=cmd_id,
                    display_name=name,
                    callback=cb,
                    shortcut=shortcut,
                    scope=scope,
                    tooltip=tooltip,
                    parent=parent if scope == "global" else None,
                    allow_override=True,
                )

    def clear_shortcuts(self):
        """Disables and removes active QShortcut bindings without clearing command metadata."""
        for qs in list(self._shortcuts.values()):
            try:
                qs.setEnabled(False)
                qs.deleteLater()
            except RuntimeError:
                pass
        self._shortcuts.clear()

    def clear(self):
        """
        Clears all registered commands and shortcuts.
        Useful for tests and application restart.
        """
        self.clear_shortcuts()
        self._commands.clear()

    def register(
        self,
        command_id: str,
        display_name: str,
        callback: Callable,
        shortcut: Optional[str] = None,
        scope: str = "global",
        tooltip: str = "",
        parent: Optional[QWidget] = None,
        allow_override: bool = False,
    ):
        """
        Register a named command.

        Args:
            command_id: Unique identifier (e.g. "new_task").
            display_name: Human-readable name (e.g. "Create New Task").
            callback: Function to call when triggered.
            shortcut: Key sequence string (e.g. "Ctrl+N"). None for no shortcut.
            scope: "global" (auto-bound on parent) or "local" (documentation only).
            tooltip: Optional tooltip description.
            parent: QWidget to bind global shortcut to. Required when scope="global".
            allow_override: If True, existing command with same ID is replaced.

        Raises:
            ValueError: If command_id is already registered and allow_override is False.
        """
        if command_id in self._commands:
            if allow_override:
                self.unregister(command_id)
            else:
                raise ValueError(
                    f"CommandRegistry: Duplicate command_id '{command_id}'. "
                    f"Already registered as '{self._commands[command_id].display_name}'."
                )

        info = CommandInfo(
            command_id=command_id,
            display_name=display_name,
            shortcut=shortcut,
            scope=scope,
            tooltip=tooltip,
            callback=callback,
        )
        self._commands[command_id] = info

        # Bind global shortcut
        if scope == "global" and shortcut and parent is not None:
            try:
                qs = QShortcut(QKeySequence(shortcut), parent)
                qs.activated.connect(callback)
                self._shortcuts[command_id] = qs
                logger.debug(
                    f"CommandRegistry: Bound global shortcut {shortcut} → {command_id}"
                )
            except Exception as e:
                logger.error(
                    f"CommandRegistry: Failed to bind shortcut {shortcut} "
                    f"for {command_id}: {e}"
                )

        logger.debug(f"CommandRegistry: Registered command '{command_id}' ({scope})")

    def unregister(self, command_id: str):
        """Remove a command and its shortcut binding."""
        self._commands.pop(command_id, None)
        qs = self._shortcuts.pop(command_id, None)
        if qs is not None:
            try:
                qs.setEnabled(False)
                qs.deleteLater()
            except RuntimeError:
                pass

    def get_shortcut_text(self, command_id: str) -> str:
        """
        Returns the shortcut key sequence string for a command, or empty string.
        Useful for appending to menu labels and tooltips.
        """
        info = self._commands.get(command_id)
        if info and info.shortcut:
            return info.shortcut
        return ""

    def get_command(self, command_id: str) -> Optional[CommandInfo]:
        """Returns CommandInfo for a given command_id, or None."""
        return self._commands.get(command_id)

    def get_all_commands(self) -> List[CommandInfo]:
        """Returns all registered commands."""
        return list(self._commands.values())

    def clear(self):
        """
        Clears all registered commands and shortcuts.
        Useful for tests and application restart.
        """
        for qs in self._shortcuts.values():
            try:
                qs.setEnabled(False)
                qs.deleteLater()
            except RuntimeError:
                pass
        self._commands.clear()
        self._shortcuts.clear()

    @classmethod
    def reset_instance(cls):
        """Reset singleton (for tests)."""
        if cls._instance is not None:
            cls._instance.clear()
        cls._instance = None
