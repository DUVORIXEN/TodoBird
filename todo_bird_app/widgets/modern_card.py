"""
Modern Shared Component Foundation (Batch 3.7)
Reusable UI components: ModernCard, SectionHeader, PrimaryButton, StatusChip,
ModernTooltip, MetricCard, and EmptyState.
"""

from typing import Optional
from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from todo_bird_app.services.typography_service import TypographyService
from todo_bird_app.services.appearance_service import semantic_tokens_for


def _is_app_accent_candidate(color_hex: str) -> bool:
    return str(color_hex or "").upper() in {
        "#3584E4",
        "#3B82F6",
        "#2563EB",
        "#E95420",
    }

class ModernCard(QFrame):
    """Clean surface card with subtle border, header, and standard padding."""
    def __init__(self, title: str = "", accent_color: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._accent_color = accent_color
        self._is_dark = True
        self.setObjectName("CardWidget")
        self.setStyleSheet("""
            QFrame#CardWidget {
                border-radius: 10px;
                padding: 12px;
            }
        """)
        self.card_layout = QVBoxLayout(self)
        self.card_layout.setContentsMargins(12, 12, 12, 12)
        self.card_layout.setSpacing(8)
        if title:
            self.header_label = QLabel(title)
            color_style = (
                f"color: {accent_color};"
                if accent_color
                else "color: inherit;"
            )
            self.header_label.setStyleSheet(
                f"font-weight: 700; {color_style}"
            )
            TypographyService.set_relative_font_role(
                self.header_label,
                delta_pt=4,
                weight="bold",
            )
            self.card_layout.addWidget(self.header_label)

    def add_layout(self, layout):
        self.card_layout.addLayout(layout)

    def add_widget(self, widget):
        self.card_layout.addWidget(widget)

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color and (
            not self._accent_color
            or _is_app_accent_candidate(self._accent_color)
        ):
            self._accent_color = accent_color
        if hasattr(self, "header_label"):
            color_style = (
                f"color: {self._accent_color};"
                if self._accent_color
                else "color: inherit;"
            )
            self.header_label.setStyleSheet(
                f"font-weight: 700; {color_style}"
            )
        self.update()

class SectionHeader(QWidget):
    """Prominent section header with icon and optional badge."""
    def __init__(self, title: str, icon: str = "", subtitle: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.setSpacing(2)

        top_row = QHBoxLayout()
        text = f"{icon} {title}".strip() if icon else title
        self.title_lbl = QLabel(text)
        self.title_lbl.setStyleSheet(
            "font-weight: 700; color: inherit;"
        )
        TypographyService.set_relative_font_role(
            self.title_lbl,
            delta_pt=5,
            weight="bold",
        )
        top_row.addWidget(self.title_lbl)
        top_row.addStretch()
        layout.addLayout(top_row)

        if subtitle:
            self.sub_lbl = QLabel(subtitle)
            self.sub_lbl.setStyleSheet(
                "color: #94A3B8;"
            )
            TypographyService.set_relative_font_role(
                self.sub_lbl,
                delta_pt=2,
            )
            layout.addWidget(self.sub_lbl)

class PrimaryButton(QPushButton):
    """High-contrast branded action button."""
    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setObjectName("PrimaryButton")
        self.setCursor(Qt.PointingHandCursor)
        self._is_dark = True
        self._accent_color = "#3584E4"
        self.set_theme(True, self._accent_color)

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        if accent_color:
            self._accent_color = accent_color
        accent = QColor(self._accent_color)
        hover = accent.lighter(113).name() if is_dark else accent.darker(112).name()
        pressed = accent.darker(120).name()
        self.setStyleSheet(f"""
            QPushButton#PrimaryButton {{
                background-color: {self._accent_color};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-weight: 600;
            }}
            QPushButton#PrimaryButton:hover {{
                background-color: {hover};
            }}
            QPushButton#PrimaryButton:pressed {{
                background-color: {pressed};
            }}
        """)

class StatusChip(QLabel):
    """Compact badge chip for status and priorities."""
    def __init__(self, text: str, color_hex: str = "#3584E4", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self._source_color = color_hex
        self._is_dark = True
        self.set_theme(True, color_hex)

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        color_hex = (
            accent_color
            if accent_color and _is_app_accent_candidate(self._source_color)
            else self._source_color
        )
        self.setStyleSheet(f"""
            background-color: {color_hex}22;
            color: {color_hex};
            border: 1px solid {color_hex}55;
            border-radius: 6px;
            padding: 2px 8px;
            font-weight: 600;
        """)

class MetricCard(QFrame):
    """Metric overview card displaying a key number and description."""
    clicked = Signal()

    def __init__(self, title: str, value: str, subtext: str = "", color_hex: str = "#3584E4", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("CardWidget")
        self._source_color = color_hex
        self._is_dark = True
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(80)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-weight: 600; font-size: 11px; color: #94A3B8; letter-spacing: 0.4px;")
        self.title_label.setWordWrap(True)

        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"color: {color_hex};")
        TypographyService.set_relative_font_role(self.value_label, delta_pt=12, weight="bold")
        self.value_label.setWordWrap(True)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        self.sub_label = QLabel(subtext)
        self.sub_label.setStyleSheet("font-size: 11px; color: #64748B;")
        self.sub_label.setWordWrap(True)
        layout.addWidget(self.sub_label)
        self.set_theme(True, color_hex)

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        self._is_dark = is_dark
        tokens = semantic_tokens_for(is_dark, accent_color or "#3584E4")
        metric_color = (
            tokens["ACCENT"]
            if _is_app_accent_candidate(self._source_color)
            else self._source_color
        )
        self.title_label.setStyleSheet(
            f"font-weight: 600; font-size: 11px; letter-spacing: 0.4px; color: {tokens['TEXT_MUTED']};"
        )
        self.value_label.setStyleSheet(
            f"color: {metric_color};"
        )
        TypographyService.set_relative_font_role(
            self.value_label, delta_pt=12, weight="bold"
        )
        self.sub_label.setStyleSheet(
            f"font-size: 11px; color: {tokens['TEXT_SECONDARY']};"
        )
        border = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.08)"
        bg = tokens.get("SURFACE_1", "#242538") if is_dark else "#FFFFFF"
        hover_border = tokens.get("ACCENT", "#3584E4")
        self.setStyleSheet(f"""
            QFrame#CardWidget {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 10px;
            }}
            QFrame#CardWidget:hover {{
                border: 1px solid {hover_border};
            }}
        """)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

class EmptyState(QWidget):
    """Polished empty state banner with icon, title, and action guide."""
    def __init__(self, icon: str, title: str, description: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(20, 40, 20, 40)
        layout.setSpacing(8)

        i_lbl = QLabel(icon)
        self.icon_label = i_lbl
        i_lbl.setAlignment(Qt.AlignCenter)
        i_lbl.setStyleSheet("font-size: 32px;")
        t_lbl = QLabel(title)
        self.title_label = t_lbl
        t_lbl.setAlignment(Qt.AlignCenter)
        t_lbl.setStyleSheet(
            "font-weight: 700; color: inherit;"
        )
        TypographyService.set_relative_font_role(
            t_lbl,
            delta_pt=6,
            weight="bold",
        )
        d_lbl = QLabel(description)
        self.desc_label = d_lbl
        d_lbl.setAlignment(Qt.AlignCenter)
        d_lbl.setStyleSheet(
            "color: palette(mid);"
        )
        TypographyService.set_relative_font_role(
            d_lbl,
            delta_pt=3,
        )

        layout.addWidget(i_lbl)
        layout.addWidget(t_lbl)
        layout.addWidget(d_lbl)

    def set_theme(self, is_dark: bool, accent_color: Optional[str] = None):
        tokens = semantic_tokens_for(is_dark, accent_color or "#3584E4")
        self.title_label.setStyleSheet(
            f"font-weight: 700; color: {tokens['TEXT_PRIMARY']};"
        )
        self.desc_label.setStyleSheet(
            f"color: {tokens['TEXT_SECONDARY']};"
        )
        self.update()
