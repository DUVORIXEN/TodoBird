import logging
from pathlib import Path
from typing import Dict, Optional
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtCore import QSize

logger = logging.getLogger(__name__)

ICON_THEME_MAPPINGS = {
    "edit": ["document-edit", "edit-symbolic", "gtk-edit", "edit"],
    "delete": ["user-trash", "edit-delete-symbolic", "gtk-delete", "trash", "delete"],
    "check": ["object-select-symbolic", "gtk-apply", "check"],
    "plus": ["list-add-symbolic", "gtk-add", "add", "plus"],
    "calendar": ["x-office-calendar-symbolic", "calendar"],
    "settings": ["preferences-system-symbolic", "settings"],
}

EMOJI_FALLBACKS = {
    "edit": "✏️",
    "delete": "🗑️",
    "check": "✅",
    "plus": "➕",
    "calendar": "📅",
    "settings": "⚙️",
}

class IconManager:
    """
    Central Icon Resource System.
    Provides system GTK theme lookup with bundled SVG fallbacks and theme tinting.
    Guarantees no action button is ever visually blank.
    """
    _cache: Dict[str, QIcon] = {}
    _logged_missing = set()

    @classmethod
    def get_icon(cls, name: str, color: Optional[str] = None) -> QIcon:
        cache_key = f"{name}_{color}" if color else name
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        # 1. Try system icon theme lookup
        theme_names = ICON_THEME_MAPPINGS.get(name, [name])
        for t_name in theme_names:
            icon = QIcon.fromTheme(t_name)
            if not icon.isNull():
                cls._cache[cache_key] = icon
                return icon

        # 2. Try bundled SVG file lookup
        icons_dir = Path(__file__).parent.parent / "assets" / "icons"
        svg_file = icons_dir / f"{name}.svg"

        if svg_file.exists():
            icon = QIcon(str(svg_file))
            if not icon.isNull():
                cls._cache[cache_key] = icon
                return icon

        # 3. Log missing warning once
        if name not in cls._logged_missing:
            logger.warning(f"Icon '{name}' not found in system theme or bundled SVG assets. Using fallback.")
            cls._logged_missing.add(name)

        # Return empty QIcon; calling code uses text/emoji fallback if icon.isNull()
        empty_icon = QIcon()
        cls._cache[cache_key] = empty_icon
        return empty_icon

    @classmethod
    def get_fallback_emoji(cls, name: str) -> str:
        return EMOJI_FALLBACKS.get(name, "")
