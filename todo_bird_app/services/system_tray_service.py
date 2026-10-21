import logging
from pathlib import Path
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from PySide6.QtGui import QIcon, QAction

logger = logging.getLogger(__name__)

class SystemTrayService:
    """
    Manages system tray icon integration, quick tray menu, and global window toggling.
    """
    def __init__(self, main_window):
        self.main_window = main_window
        self.tray_icon = None
        self.setup_tray()

    def setup_tray(self):
        icon_path = Path(__file__).parent.parent / "assets" / "icons" / "todo-bird.png"
        if not icon_path.exists():
            return

        icon = QIcon(str(icon_path.resolve()))
        self.tray_icon = QSystemTrayIcon(icon, self.main_window)
        self.tray_icon.setToolTip("TODO BIRD — Offline Productivity Companion")

        tray_menu = QMenu()

        act_palette = QAction("⚡ Open Command Palette (Ctrl+K)", self.main_window)
        act_palette.triggered.connect(self.main_window.open_command_palette)
        tray_menu.addAction(act_palette)

        act_add = QAction("➕ Quick Add Task", self.main_window)
        act_add.triggered.connect(lambda: self.main_window.open_quick_add_dialog())
        tray_menu.addAction(act_add)

        act_gantt = QAction("📊 Open Gantt Timeline", self.main_window)
        act_gantt.triggered.connect(lambda: self.main_window.navigation_controller.set_active_section("gantt"))
        tray_menu.addAction(act_gantt)

        tray_menu.addSeparator()

        act_show = QAction("👁️ Show/Hide MainWindow", self.main_window)
        act_show.triggered.connect(self.toggle_window)
        tray_menu.addAction(act_show)

        act_exit = QAction("❌ Exit", self.main_window)
        act_exit.triggered.connect(self.main_window.close)
        tray_menu.addAction(act_exit)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()
        logger.info("System tray service initialized successfully.")

    def toggle_window(self):
        if self.main_window.isVisible():
            self.main_window.hide()
        else:
            self.main_window.show()
            self.main_window.raise_()
            self.main_window.activateWindow()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:  # Single click / tap
            self.toggle_window()
