import os
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class ResourceManager:
    """
    Application-relative and PyInstaller-compatible resource resolver.
    Resolves assets (icons, SVGs, QSS files, Avocet images, GIFs, audio) cleanly
    whether running from Python source or compiled as a PyInstaller executable (`sys._MEIPASS`).
    """
    @staticmethod
    def get_base_dir() -> Path:
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            return Path(sys._MEIPASS)
        return Path(__file__).parent.parent.resolve()

    @classmethod
    def get_asset_path(cls, relative_path: str) -> Path:
        base = cls.get_base_dir()
        path = base / relative_path
        if not path.exists():
            logger.debug(f"Resource path not found: {path}")
        return path

    @classmethod
    def get_icon_path(cls, icon_name: str) -> str:
        if not icon_name.endswith((".png", ".svg")):
            icon_name = f"{icon_name}.png"
        path = cls.get_asset_path(f"assets/icons/{icon_name}")
        return str(path)

    @classmethod
    def get_theme_path(cls, theme_name: str) -> str:
        if not theme_name.endswith(".qss"):
            theme_name = f"{theme_name}.qss"
        path = cls.get_asset_path(f"themes/{theme_name}")
        return str(path)

    @classmethod
    def get_avocet_image(cls, image_name: str) -> str:
        path = cls.get_asset_path(f"assets/avocet/{image_name}")
        return str(path)
