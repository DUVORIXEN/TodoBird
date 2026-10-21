"""
TODO BIRD — MODERN SCROLLBAR STYLING
Provides slim, theme-aware scrollbars with subtle hover expansion and comfortable grab areas.
"""

from typing import Optional
from todo_bird_app.ui.design_tokens import DesignTokens


class ModernScrollBarStyle:
    """Generates theme-aware modern QScrollBar stylesheet strings."""

    @staticmethod
    def get_qss(is_dark: bool = True, accent_color: str = DesignTokens.COLOR_ACCENT) -> str:
        track_bg = "transparent"
        thumb_bg = "#45475A" if is_dark else "#CBD5E1"
        thumb_hover = accent_color
        thumb_pressed = "#585B70" if is_dark else "#94A3B8"

        return f"""
            QScrollBar:vertical {{
                background: {track_bg};
                width: 8px;
                margin: 2px 0 2px 0;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {thumb_bg};
                min-height: 24px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {thumb_hover};
            }}
            QScrollBar::handle:vertical:pressed {{
                background: {thumb_pressed};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}

            QScrollBar:horizontal {{
                background: {track_bg};
                height: 8px;
                margin: 0 2px 0 2px;
                border-radius: 4px;
            }}
            QScrollBar::handle:horizontal {{
                background: {thumb_bg};
                min-width: 24px;
                border-radius: 4px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {thumb_hover};
            }}
            QScrollBar::handle:horizontal:pressed {{
                background: {thumb_pressed};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
                background: none;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}
        """
