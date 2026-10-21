from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QPushButton, QColorDialog,
    QScrollArea, QWidget, QFrame
)
from PySide6.QtCore import Qt
from todo_bird_app.models.project import Project
from todo_bird_app.widgets.rich_text_editor import RichTextEditor

class ProjectDialog(QDialog):
    """
    Dialog for creating and editing Projects.
    """
    def __init__(self, project: Project = None, settings_manager=None, parent=None):
        super().__init__(parent)
        if settings_manager is None and parent is not None:
            settings_manager = getattr(parent, "settings_manager", None)
        self.settings_manager = settings_manager
        self.project = project or Project()
        self.setWindowTitle("Edit Project" if project and project.id else "New Project")
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.setMinimumSize(340, 280)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.register(self, role="project_dialog")

        self._restore_geometry()
        self._init_ui()
        
        from todo_bird_app.services.typography_service import TypographyService
        TypographyService.apply_to_widget(self, "dialogs", self.settings_manager)

    def done(self, r):
        self._save_geometry()
        super().done(r)
        self.deleteLater()

    def _restore_geometry(self):
        if self.settings_manager:
            w = self.settings_manager.get("project_dialog_width", 400)
            h = self.settings_manager.get("project_dialog_height", 320)
            self.resize(int(w), int(h))
        else:
            self.resize(400, 320)

    def _save_geometry(self):
        if self.settings_manager:
            w = self.width()
            h = self.height()
            if self.settings_manager.get("project_dialog_width") != w:
                self.settings_manager.set("project_dialog_width", w)
            if self.settings_manager.get("project_dialog_height") != h:
                self.settings_manager.set("project_dialog_height", h)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        from todo_bird_app.services.typography_service import TypographyService
        title = QLabel("Project Details")
        title.setStyleSheet("color: inherit; font-weight: 700;")
        TypographyService.set_relative_font_role(title, delta_pt=6, weight="bold")
        layout.addWidget(title)

        # Scrollable Content Area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_widget = QWidget()
        form_layout = QVBoxLayout(scroll_widget)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(10)

        # Name
        form_layout.addWidget(QLabel("Project Name *"))
        self.name_input = QLineEdit(self.project.name)
        self.name_input.setPlaceholderText("e.g. Work, Personal, Side Hustle")
        form_layout.addWidget(self.name_input)

        # Color
        form_layout.addWidget(QLabel("Color Accent"))
        color_layout = QHBoxLayout()
        self.color_preview = QLabel(self.project.color)
        self.color_preview.setStyleSheet(f"background-color: {self.project.color}; border-radius: 6px; padding: 4px 12px; color: white;")

        color_btn = QPushButton("Choose Color...")
        color_btn.clicked.connect(self.choose_color)
        color_layout.addWidget(self.color_preview)
        color_layout.addWidget(color_btn)
        color_layout.addStretch()
        form_layout.addLayout(color_layout)

        # Description
        form_layout.addWidget(QLabel("Description"))
        self.desc_input = RichTextEditor(parent=self, settings_manager=self.settings_manager)
        self.desc_input.setHtml(self.project.description)
        form_layout.addWidget(self.desc_input)

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save Project")
        save_btn.setObjectName("PrimaryButton")
        save_btn.clicked.connect(self.on_save)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        layout.addLayout(btn_layout)

    def choose_color(self):
        col = QColorDialog.getColor(initial=self.project.color, parent=self)
        if col.isValid():
            self.project.color = col.name()
            self.color_preview.setText(self.project.color)
            self.color_preview.setStyleSheet(f"background-color: {self.project.color}; border-radius: 6px; padding: 4px 12px; color: white;")

    def on_save(self):
        name = self.name_input.text().strip()
        if not name:
            self.name_input.setFocus()
            return

        self.project.name = name
        self.project.description = self.desc_input.toHtml().strip()
        self.accept()

    def get_project(self) -> Project:
        return self.project
