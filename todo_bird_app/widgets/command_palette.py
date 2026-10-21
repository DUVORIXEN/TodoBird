import logging
from typing import List, Dict, Any, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QLabel, QWidget, QHBoxLayout
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

logger = logging.getLogger(__name__)

class CommandPalette(QDialog):
    """
    High-speed, keyboard-driven Command Palette overlay (Ctrl+K).
    Supports fuzzy task search, quick view switching, system actions,
    and inline smart task creation syntax (@Project, !Priority).
    """
    action_triggered = Signal(str, object)  # (action_type, payload)

    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setWindowTitle("Command Palette (Ctrl + K)")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setModal(True)
        self.resize(650, 420)

        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.register(self, role="command_palette")

        self._init_ui()

    def done(self, r):
        super().done(r)
        self.deleteLater()

    def _init_ui(self):
        from todo_bird_app.services.appearance_service import AppearanceService
        from PySide6.QtWidgets import QApplication
        appearance = AppearanceService.read(None, app=QApplication.instance())
        tokens = appearance.tokens
        is_dark = appearance.is_dark

        bg_container = tokens.get("SURFACE_1", "#1E1E2E" if is_dark else "#FFFFFF")
        bg_input = tokens.get("SURFACE_2", "#181825" if is_dark else "#F1F5F9")
        border_container = tokens.get("BORDER_NORMAL", "#313244" if is_dark else "#CBD5E1")
        border_input = tokens.get("BORDER_SUBTLE", "#45475A" if is_dark else "#E2E8F0")
        text_color = tokens.get("TEXT_PRIMARY", "#CDD6F4" if is_dark else "#0F172A")
        muted_color = tokens.get("TEXT_MUTED", "#A6ADC8" if is_dark else "#64748B")
        accent_color = tokens.get("ACCENT", "#CBA6F7" if is_dark else "#3584E4")
        hover_item = tokens.get("SURFACE_2", "#313244" if is_dark else "#E2E8F0")
        selected_item = tokens.get("ACCENT", "#45475A" if is_dark else "#3584E4")
        selected_text = "#FFFFFF"

        container = QWidget(self)
        container.setObjectName("container")
        container.setStyleSheet(f"""
            QWidget#container {{
                background-color: {bg_container};
                border: 2px solid {border_container};
                border-radius: 12px;
            }}
            QLineEdit {{
                background-color: {bg_input};
                color: {text_color};
                border: 1px solid {border_input};
                border-radius: 8px;
                padding: 10px 14px;
                font-size: 14px;
            }}
            QListWidget {{
                background-color: transparent;
                border: none;
                color: {text_color};
                font-size: 13px;
            }}
            QListWidget::item {{
                padding: 10px 14px;
                border-radius: 6px;
                margin-bottom: 2px;
            }}
            QListWidget::item:hover {{
                background-color: {hover_item};
            }}
            QListWidget::item:selected {{
                background-color: {selected_item};
                color: {selected_text};
            }}
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header Title / Shortcut Label
        header_row = QHBoxLayout()
        title_label = QLabel(" Quick Actions & Task Search", container)
        title_label.setFont(QFont("Inter", 11, QFont.Bold))
        title_label.setStyleSheet(f"color: {accent_color};")

        hint_label = QLabel("ESC to exit • ↑↓ to navigate • ↵ to select", container)
        hint_label.setFont(QFont("Inter", 9))
        hint_label.setStyleSheet(f"color: {muted_color};")

        header_row.addWidget(title_label)
        header_row.addStretch()
        header_row.addWidget(hint_label)
        layout.addLayout(header_row)

        # Search Input Box
        self.search_input = QLineEdit(container)
        self.search_input.setPlaceholderText("Type a command or task title... (e.g. 'Go to Gantt' or 'Review report !High')")
        self.search_input.textChanged.connect(self._on_search_text_changed)
        layout.addWidget(self.search_input)

        # Results List Widget
        self.list_widget = QListWidget(container)
        self.list_widget.itemActivated.connect(self._on_item_selected)
        layout.addWidget(self.list_widget, 1)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(container)

        self._populate_default_actions()

    def showEvent(self, event):
        super().showEvent(event)
        self.search_input.clear()
        self._populate_default_actions()
        self.search_input.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
        elif event.key() in (Qt.Key_Down, Qt.Key_Up):
            self.list_widget.keyPressEvent(event)
        elif event.key() in (Qt.Key_Return, Qt.Key_Enter):
            curr_item = self.list_widget.currentItem()
            if curr_item:
                self._on_item_selected(curr_item)
            else:
                self._create_quick_task_from_input()
        else:
            super().keyPressEvent(event)

    def _populate_default_actions(self):
        self.list_widget.clear()

        # Map action codes to command_ids for shortcut lookup
        shortcut_map = {
            "action:create_task": "new_task",
            "action:toggle_theme": None,
            "action:export_pdf": None,
            "action:export_csv": None,
            "action:open_world_clock": "open_world_clock",
        }

        actions = [
            ("Create New Task...", "action:create_task", "Open task creation dialog"),
            ("Open World Clock", "action:open_world_clock", "View multi-country global clocks"),
            ("Go to World Clock View", "nav:world_clock", "View full world clock planner"),
            ("Go to Gantt View", "nav:gantt", "View Gantt timeline"),
            ("Go to Inbox View", "nav:inbox", "View inbox tasks"),
            ("Go to Today View", "nav:today", "View today's planned schedule"),
            ("Go to Focus View", "nav:focus", "Start active focus session"),
            ("Go to Analytics View", "nav:analytics", "View completion & delay reports"),
            (" Go to Daily Review", "nav:daily_review", "Conduct end-of-day review"),
            (" Export PDF Performance Report", "action:export_pdf", "Generate styled PDF report"),
            ("Export CSV Tasks Data", "action:export_csv", "Export task records to CSV"),
            (" Toggle Theme (Light/Dark)", "action:toggle_theme", "Switch UI theme"),
        ]

        # Try to get shortcut hints from CommandRegistry
        try:
            from todo_bird_app.services.command_registry import CommandRegistry
            registry = CommandRegistry()
        except Exception:
            registry = None

        for label, code, desc in actions:
            shortcut_hint = ""
            if registry:
                cmd_id = shortcut_map.get(code)
                if cmd_id:
                    shortcut_hint = registry.get_shortcut_text(cmd_id)
            suffix = f"  [{shortcut_hint}]" if shortcut_hint else ""
            item = QListWidgetItem(f"{label}  —  {desc}{suffix}")
            item.setData(Qt.UserRole, (code, label))
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _on_search_text_changed(self, text: str):
        query = text.strip()
        if not query:
            self._populate_default_actions()
            return

        self.list_widget.clear()

        # 1. Matching Built-in Commands
        default_commands = [
            ("Create New Task...", "action:create_task", "Open task creation dialog"),
            ("Open World Clock", "action:open_world_clock", "View multi-country global clocks"),
            ("Go to World Clock View", "nav:world_clock", "View full world clock planner"),
            ("Go to Gantt View", "nav:gantt", "View Gantt timeline"),
            ("Go to Inbox View", "nav:inbox", "View inbox tasks"),
            ("Go to Today View", "nav:today", "View today's planned schedule"),
            ("Go to Focus View", "nav:focus", "Start active focus session"),
            ("Go to Analytics View", "nav:analytics", "View completion & delay reports"),
            (" Go to Daily Review", "nav:daily_review", "Conduct end-of-day review"),
            (" Export PDF Performance Report", "action:export_pdf", "Generate styled PDF report"),
            ("Export CSV Tasks Data", "action:export_csv", "Export task records to CSV"),
            (" Toggle Theme (Light/Dark)", "action:toggle_theme", "Switch UI theme"),
        ]

        for label, code, desc in default_commands:
            if query.lower() in label.lower() or query.lower() in desc.lower():
                item = QListWidgetItem(f"{label}  —  {desc}")
                item.setData(Qt.UserRole, (code, label))
                self.list_widget.addItem(item)

        # 2. Matching Tasks from SQLite DB
        try:
            tasks = self.db_manager.search_tasks(query)
            for task_dict in tasks:
                t_title = task_dict.get("title", "")
                t_id = task_dict.get("id")
                t_status = task_dict.get("status", "Inbox")
                item = QListWidgetItem(f"Task #{t_id}: {t_title} [{t_status}]")
                item.setData(Qt.UserRole, (f"task:{t_id}", t_title))
                self.list_widget.addItem(item)
        except Exception as e:
            logger.error(f"Error searching tasks in command palette: {e}")

        # 3. Quick Create Option
        quick_item = QListWidgetItem(f"Quick Create Task: \"{query}\"")
        quick_item.setData(Qt.UserRole, ("action:quick_create", query))
        self.list_widget.addItem(quick_item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _on_item_selected(self, item: QListWidgetItem):
        data = item.data(Qt.UserRole)
        if not data:
            return

        code, payload = data
        self.accept()

        if code.startswith("nav:"):
            section = code.split(":")[1]
            self.action_triggered.emit("navigate", section)
        elif code.startswith("task:"):
            task_id = int(code.split(":")[1])
            self.action_triggered.emit("open_task", task_id)
        elif code == "action:quick_create":
            self.action_triggered.emit("quick_create", payload)
        else:
            self.action_triggered.emit("custom_action", code.replace("action:", ""))

    def _create_quick_task_from_input(self):
        text = self.search_input.text().strip()
        if text:
            self.accept()
            self.action_triggered.emit("quick_create", text)
