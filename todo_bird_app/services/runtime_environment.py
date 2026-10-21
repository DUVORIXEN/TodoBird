"""
TODO BIRD — Application Runtime Environment & Mode Authority
Canonical authority for detecting and declaring runtime execution modes:
- DEVELOPMENT_SOURCE: running from a source repository checkout.
- PACKAGED_INSTALLED: running as a frozen standalone package (PyInstaller/AppImage/MSI/DMG/etc.)

Provides clean test seams and explicit environment overrides.
Never detects packaged mode by guessing from /usr or /opt path substrings.
"""

import os
import sys
from enum import Enum
from typing import Optional


class RuntimeMode(str, Enum):
    DEVELOPMENT_SOURCE = "development_source"
    PACKAGED_INSTALLED = "packaged_installed"

    # Convenience aliases
    DEVELOPMENT = "development_source"
    PACKAGED = "packaged_installed"


class RuntimeEnvironment:
    """
    Canonical authority for application runtime mode.
    Do NOT scatter `if getattr(sys, 'frozen', False)` across components.
    Query this authority instead.
    """
    ENV_RUNTIME_MODE = "TODO_BIRD_RUNTIME_MODE"
    ENV_PACKAGED = "TODO_BIRD_PACKAGED"

    def __init__(self, mode: Optional[RuntimeMode] = None):
        self._mode = mode

    @property
    def mode(self) -> RuntimeMode:
        if self._mode is not None:
            return self._mode
        return self._detect_runtime_mode()

    @classmethod
    def _detect_runtime_mode(cls) -> RuntimeMode:
        # 1. Explicit environment variable overrides (highest precedence, useful for tests/qualification)
        env_mode = os.environ.get(cls.ENV_RUNTIME_MODE, "").strip().lower()
        if env_mode in ("packaged", "packaged_installed", "1", "true", "yes"):
            return RuntimeMode.PACKAGED_INSTALLED
        if env_mode in ("development", "development_source", "0", "false", "no"):
            return RuntimeMode.DEVELOPMENT_SOURCE

        env_pkg = os.environ.get(cls.ENV_PACKAGED, "").strip().lower()
        if env_pkg in ("1", "true", "yes"):
            return RuntimeMode.PACKAGED_INSTALLED
        if env_pkg in ("0", "false", "no"):
            return RuntimeMode.DEVELOPMENT_SOURCE

        # 2. PyInstaller / cx_Freeze / py2exe frozen process signal
        if getattr(sys, "frozen", False):
            return RuntimeMode.PACKAGED_INSTALLED

        # 3. PyInstaller extraction directory
        if hasattr(sys, "_MEIPASS"):
            return RuntimeMode.PACKAGED_INSTALLED

        # 4. Linux sandboxed packages (Flatpak, Snap)
        if (
            os.environ.get("FLATPAK_ID")
            or os.environ.get("SNAP")
            or os.path.exists("/.flatpak-info")
        ):
            return RuntimeMode.PACKAGED_INSTALLED

        # Default fallback: development source checkout
        return RuntimeMode.DEVELOPMENT_SOURCE

    def is_packaged(self) -> bool:
        return self.mode == RuntimeMode.PACKAGED_INSTALLED

    def is_development(self) -> bool:
        return self.mode == RuntimeMode.DEVELOPMENT_SOURCE

    def storage_mode(self) -> str:
        return "packaged" if self.is_packaged() else "development"

    @classmethod
    def current(cls) -> "RuntimeEnvironment":
        return cls()

    @classmethod
    def development(cls) -> "RuntimeEnvironment":
        return cls(mode=RuntimeMode.DEVELOPMENT_SOURCE)

    @classmethod
    def packaged(cls) -> "RuntimeEnvironment":
        return cls(mode=RuntimeMode.PACKAGED_INSTALLED)
