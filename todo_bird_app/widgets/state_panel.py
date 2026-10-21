"""
Todo Bird Shared Application State Panel — Phase 1F.9

Production-quality, consistent state-management UX for:
- Empty states
- Search/filter no-results states
- No-selection states
- Loading states
- Recoverable error states with retry
"""

from enum import Enum
from typing import Optional, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QSizePolicy,
)
from todo_bird_app.services.typography_service import TypographyService


class StateKind(str, Enum):
    EMPTY = "empty"
    NO_RESULTS = "no_results"
    NO_SELECTION = "no_selection"
    LOADING = "loading"
    ERROR = "error"
    DISABLED = "disabled"


class StatePanel(QFrame):
    """
    Standardized native Qt state panel presenting calm, actionable guidance.
    Never leaves an unexplained blank surface.
    """

    DEFAULT_ICONS = {
        StateKind.EMPTY: "inbox",
        StateKind.NO_RESULTS: "search",
        StateKind.NO_SELECTION: "target",
        StateKind.LOADING: "clock",
        StateKind.ERROR: "close",
        StateKind.DISABLED: "settings",
    }

    # Callers historically passed emoji; map the known ones to glyphs.
    _LEGACY_ICON_MAP = {
        "": "search",
        "": "target",
        "": "calendar",
        "": "inbox",
        "⏳": "clock",
        "🔒": "settings",
    }

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("WorkspaceStatePanel")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._kind = StateKind.EMPTY
        self._action_callback: Optional[Callable] = None
        self._secondary_action_callback: Optional[Callable] = None

        self._init_ui()

    def _apply_state_icon(self, spec: str):
        """Render a vector glyph when possible; fall back to plain text."""
        from todo_bird_app.services.icon_service import IconService

        name = self._LEGACY_ICON_MAP.get(spec, spec)
        if IconService.has_icon(name):
            self.icon_label.setPixmap(
                IconService.get_pixmap(name, 32, "#9AA6BD")
            )
        else:
            self.icon_label.setText(spec)

    def _init_ui(self):
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(24, 32, 24, 32)
        self._layout.setSpacing(12)
        self._layout.setAlignment(Qt.AlignCenter)

        # Icon
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent;")
        self._layout.addWidget(self.icon_label)
        self._apply_state_icon(self.DEFAULT_ICONS[StateKind.EMPTY])

        # Title
        self.title_label = QLabel("Nothing here yet")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setStyleSheet("font-weight: 700; background: transparent; color: inherit;")
        TypographyService.set_relative_font_role(
            self.title_label,
            delta_pt=4,
            weight="bold",
        )
        self._layout.addWidget(self.title_label)

        # Description
        self.desc_label = QLabel("Items will appear here once created.")
        self.desc_label.setAlignment(Qt.AlignCenter)
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #94A3B8; background: transparent;")
        TypographyService.set_relative_font_role(
            self.desc_label,
            delta_pt=0,
        )
        self._layout.addWidget(self.desc_label)

        # Actions Container
        self.action_box = QWidget()
        self.action_layout = QHBoxLayout(self.action_box)
        self.action_layout.setContentsMargins(0, 8, 0, 0)
        self.action_layout.setSpacing(10)
        self.action_layout.setAlignment(Qt.AlignCenter)

        self.btn_primary = QPushButton("Add Item")
        self.btn_primary.setObjectName("PrimaryButton")
        self.btn_primary.setFixedHeight(36)
        self.btn_primary.setMinimumWidth(120)
        self.btn_primary.setCursor(Qt.PointingHandCursor)
        self.btn_primary.clicked.connect(self._on_primary_clicked)
        self.action_layout.addWidget(self.btn_primary)

        self.btn_secondary = QPushButton("Cancel")
        self.btn_secondary.setObjectName("SecondaryButton")
        self.btn_secondary.setFixedHeight(36)
        self.btn_secondary.setMinimumWidth(100)
        self.btn_secondary.setCursor(Qt.PointingHandCursor)
        self.btn_secondary.clicked.connect(self._on_secondary_clicked)
        self.action_layout.addWidget(self.btn_secondary)

        self.btn_primary.hide()
        self.btn_secondary.hide()
        self.action_box.hide()

        self._layout.addWidget(self.action_box)
        self._apply_panel_style()

    def _apply_panel_style(self):
        self.setStyleSheet(
            "#WorkspaceStatePanel {"
            "  background: rgba(255, 255, 255, 0.02);"
            "  border: 1px dashed rgba(148, 163, 184, 0.25);"
            "  border-radius: 10px;"
            "}"
        )

    def _on_primary_clicked(self):
        if self._action_callback:
            self._action_callback()

    def _on_secondary_clicked(self):
        if self._secondary_action_callback:
            self._secondary_action_callback()

    def set_state(
        self,
        kind: StateKind = StateKind.EMPTY,
        title: str = "",
        description: str = "",
        action_text: Optional[str] = None,
        action_callback: Optional[Callable] = None,
        secondary_action_text: Optional[str] = None,
        secondary_action_callback: Optional[Callable] = None,
        icon: Optional[str] = None,
    ):
        self._kind = kind
        self._apply_state_icon(icon or self.DEFAULT_ICONS.get(kind, "inbox"))
        self.title_label.setText(title)
        self.desc_label.setText(description)

        self._action_callback = action_callback
        if action_text and action_callback:
            self.btn_primary.setText(action_text)
            self.btn_primary.show()
        else:
            self.btn_primary.hide()

        self._secondary_action_callback = secondary_action_callback
        if secondary_action_text and secondary_action_callback:
            self.btn_secondary.setText(secondary_action_text)
            self.btn_secondary.show()
        else:
            self.btn_secondary.hide()

        has_actions = bool((action_text and action_callback) or (secondary_action_text and secondary_action_callback))
        self.action_box.setVisible(has_actions)

        # Accessibility
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)

    def show_empty(
        self,
        title: str,
        description: str,
        action_text: Optional[str] = None,
        action_callback: Optional[Callable] = None,
        secondary_action_text: Optional[str] = None,
        secondary_action_callback: Optional[Callable] = None,
        icon: Optional[str] = None,
    ):
        self.set_state(
            kind=StateKind.EMPTY,
            title=title,
            description=description,
            action_text=action_text,
            action_callback=action_callback,
            secondary_action_text=secondary_action_text,
            secondary_action_callback=secondary_action_callback,
            icon=icon or "",
        )

    def show_no_results(
        self,
        title: str = "No matching items found",
        description: str = "Try adjusting or clearing your active filters.",
        clear_filter_callback: Optional[Callable] = None,
    ):
        self.set_state(
            kind=StateKind.NO_RESULTS,
            title=title,
            description=description,
            action_text="Clear Filters" if clear_filter_callback else None,
            action_callback=clear_filter_callback,
            icon="",
        )

    def show_no_selection(
        self,
        title: str = "No item selected",
        description: str = "Select an item from the list to view its details.",
        action_text: Optional[str] = None,
        action_callback: Optional[Callable] = None,
    ):
        self.set_state(
            kind=StateKind.NO_SELECTION,
            title=title,
            description=description,
            action_text=action_text,
            action_callback=action_callback,
            icon="",
        )

    def show_error(
        self,
        title: str = "Unable to load data",
        description: str = "An unexpected error occurred. Your existing data remains safe.",
        retry_callback: Optional[Callable] = None,
    ):
        self.set_state(
            kind=StateKind.ERROR,
            title=title,
            description=description,
            action_text="Try Again" if retry_callback else None,
            action_callback=retry_callback,
            )

    def show_loading(
        self,
        title: str = "Loading...",
        description: str = "Please wait while data is processed.",
    ):
        self.set_state(
            kind=StateKind.LOADING,
            title=title,
            description=description,
            icon="⏳",
        )
