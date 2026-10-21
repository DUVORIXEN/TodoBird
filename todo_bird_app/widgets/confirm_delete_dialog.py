from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

class ConfirmDeleteDialog(QDialog):
    """
    Dedicated high-contrast Delete Task Confirmation Dialog.
    Guarantees readable text and buttons across Light, Dark, and High-Contrast themes.
    """
    def __init__(self, task_title: str, settings_manager=None, parent=None):
        super().__init__(parent)
        if settings_manager is None and parent is not None:
            settings_manager = getattr(parent, "settings_manager", None)
        self.settings_manager = settings_manager
        self.task_title = task_title
        self.setWindowTitle("Delete task?")
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.resize(400, 200)
        self.setMinimumSize(340, 180)
        self.setModal(True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._init_ui()

        from todo_bird_app.services.typography_service import TypographyService
        TypographyService.apply_to_widget(self, "dialogs", self.settings_manager)

        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.register(self, role="confirm_delete_dialog")

    def done(self, r):
        super().done(r)
        self.deleteLater()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Title Label
        title_label = QLabel("Delete task?")
        title_font = QFont("Inter", 15)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #EF4444;")
        layout.addWidget(title_label)

        # Body Message Label
        body_label = QLabel(f"Are you sure you want to delete “{self.task_title}”?")
        body_label.setWordWrap(True)
        body_label.setStyleSheet("line-height: 1.4;")
        layout.addWidget(body_label)

        # Buttons Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_row.addStretch()

        # Cancel Button (Default Focused)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("CancelButton")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setToolTip("Keep this task")
        self.cancel_btn.setAccessibleName("Cancel deletion")
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)

        # Delete Destructive Button
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setObjectName("DestructiveButton")
        self.delete_btn.setProperty("destructive", True)
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setToolTip("Permanently delete task")
        self.delete_btn.setAccessibleName("Confirm task deletion")
        self.delete_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.delete_btn)

        layout.addLayout(btn_row)

        # Keyboard Navigation Defaults
        self.cancel_btn.setFocus()
