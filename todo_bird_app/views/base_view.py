from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

class BaseView(QWidget):
    """
    Base view class for all TODO BIRD section views.
    """
    def __init__(self, db_manager, settings_manager, title: str = "", subtitle: str = "", parent=None, typography_area: str = ""):
        super().__init__(parent)
        self.db_manager = db_manager
        self.settings_manager = settings_manager
        self.title = title
        self.subtitle = subtitle
        self.typography_area = typography_area
        self._base_cleaned_up = False
        self._base_typography_connected = False
        self._base_appearance_connected = False
        self._task_controller_signal_connections = []

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(24, 24, 24, 24)
        self.main_layout.setSpacing(16)
        
        try:
            from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
            _GLOBAL_EVENT_BUS.typography_changed.connect(self.apply_typography)
            self._base_typography_connected = True
            _GLOBAL_EVENT_BUS.appearance_changed.connect(self.apply_appearance)
            self._base_appearance_connected = True
        except Exception:
            pass

        if self.typography_area:
            self.apply_typography()

    def apply_typography(self):
        if self.typography_area:
            from todo_bird_app.services.typography_service import TypographyService
            TypographyService.apply_to_widget(self, self.typography_area, self.settings_manager)

    def apply_appearance(self, appearance=None):
        self.apply_typography()
        on_appearance_changed = getattr(
            self,
            "on_appearance_changed",
            None,
        )
        if callable(on_appearance_changed):
            try:
                on_appearance_changed(appearance)
            except TypeError:
                on_appearance_changed()
        self.updateGeometry()
        self.update()

    def refresh_data(self):
        """
        Called when the view is navigated to or when database updates occur.
        Override in child views.
        """
        if self.typography_area:
            self.apply_typography()

    def open_task_preview(self, task_id: int):
        """Shared quick-preview editor for task cards (single-click on card body).

        Lived in InboxView only; task cards elsewhere (Today) emitted
        preview_requested with no listener, so card clicks silently did
        nothing. Every view with a task_controller now shares this.
        """
        from PySide6.QtWidgets import (
            QDialog,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QPushButton,
        )

        task_controller = getattr(self, "task_controller", None)
        if task_controller is None:
            return
        task = task_controller.get_task(task_id)
        if not task:
            return

        from todo_bird_app.widgets.rich_text_editor import RichTextEditor

        dlg = QDialog(self)
        dlg.setWindowTitle(task.title or "Task")
        dlg.resize(520, 380)
        dlg.setMinimumSize(380, 280)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        from todo_bird_app.services.typography_service import TypographyService

        title_label = QLabel("Task Name")
        title_label.setProperty("secondary", True)
        layout.addWidget(title_label)
        title_edit = QLineEdit(task.title)
        title_edit.setMinimumHeight(34)
        TypographyService.set_relative_font_role(
            title_edit, delta_pt=2, weight="600"
        )
        layout.addWidget(title_edit)

        desc_label = QLabel("Description")
        desc_label.setProperty("secondary", True)
        layout.addWidget(desc_label)
        desc_edit = RichTextEditor(settings_manager=self.settings_manager)
        desc_edit.setHtml(task.description or "")
        desc_edit.setPlaceholderText("Add task description...")
        layout.addWidget(desc_edit)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("PrimaryButton")
        save_btn.setDefault(True)

        def save_preview():
            new_title = title_edit.text().strip()
            if not new_title:
                title_edit.setFocus()
                return

            task.title = new_title
            task.description = desc_edit.toHtml().strip()
            task_controller.update_task(task)
            dlg.accept()

        save_btn.clicked.connect(save_preview)

        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        layout.addLayout(buttons)

        dlg.exec()

    def _connect_task_controller_signal(self, signal_name, slot):
        """Connect and remember an owned TaskController signal subscription."""
        task_controller = getattr(self, "task_controller", None)
        if task_controller is None:
            return

        signal = getattr(task_controller, signal_name, None)
        if signal is None:
            return

        signal.connect(slot)
        self._task_controller_signal_connections.append(
            (signal_name, slot)
        )

    def cleanup(self):
        """Release global signal subscriptions and owned controllers."""
        if getattr(self, "_base_cleaned_up", False):
            return
        self._base_cleaned_up = True

        try:
            from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
            if getattr(self, "_base_typography_connected", False):
                try:
                    _GLOBAL_EVENT_BUS.typography_changed.disconnect(
                        self.apply_typography
                    )
                except Exception:
                    pass
                self._base_typography_connected = False
            if getattr(self, "_base_appearance_connected", False):
                try:
                    _GLOBAL_EVENT_BUS.appearance_changed.disconnect(
                        self.apply_appearance
                    )
                except Exception:
                    pass
                self._base_appearance_connected = False
        except Exception:
            pass

        task_controller = getattr(self, "task_controller", None)
        if task_controller is not None:
            for signal_name, slot in list(
                getattr(
                    self,
                    "_task_controller_signal_connections",
                    [],
                )
            ):
                signal = getattr(task_controller, signal_name, None)
                if signal is None:
                    continue
                try:
                    signal.disconnect(slot)
                except Exception:
                    pass
            self._task_controller_signal_connections = []

            if getattr(self, "_owns_task_controller", True):
                try:
                    task_controller.cleanup()
                except Exception:
                    pass

        for child in self.findChildren(QWidget):
            cleanup = getattr(child, "cleanup", None)
            if callable(cleanup):
                try:
                    cleanup()
                except Exception:
                    pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def deleteLater(self):
        self.cleanup()
        super().deleteLater()
