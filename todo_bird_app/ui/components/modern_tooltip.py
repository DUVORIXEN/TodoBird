"""
TODO BIRD — MODERN TOOLTIP UTILITY
Provides formatted tooltips featuring action titles and keyboard shortcut badges.
"""

from typing import Optional


class ModernTooltip:
    """Helper to generate HTML formatted tooltips with shortcut badges."""

    @staticmethod
    def format(title: str, shortcut: Optional[str] = None, description: Optional[str] = None, is_dark: bool = True) -> str:
        shortcut_bg = "#313244" if is_dark else "#E2E8F0"
        shortcut_fg = "#CDD6F4" if is_dark else "#475569"
        text_fg = "#CDD6F4" if is_dark else "#1E293B"
        desc_fg = "#A6ADC8" if is_dark else "#64748B"

        html = f"""<div style="font-family: system-ui, sans-serif; font-size: 12px; color: {text_fg};">
            <span style="font-weight: 600;">{title}</span>"""

        if shortcut:
            html += f"""&nbsp;&nbsp;<span style="background-color: {shortcut_bg}; color: {shortcut_fg}; padding: 2px 5px; border-radius: 4px; font-size: 10px; font-family: monospace;">{shortcut}</span>"""

        if description:
            html += f"""<div style="color: {desc_fg}; font-size: 11px; margin-top: 3px;">{description}</div>"""

        html += "</div>"
        return html
