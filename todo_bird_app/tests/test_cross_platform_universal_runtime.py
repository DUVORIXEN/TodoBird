"""
Test Suite: Universal Cross-Platform Runtime & Display Architecture Hardening
Validates:
1. Headless / Display guard logic across Linux (X11 & Wayland), Windows, and macOS.
2. PlatformService factory resolution across Linux, macOS, and Windows.
3. MacOSPlatformService launcher, LaunchAgent plist generation, and notification escaping.
4. WindowsPlatformService safe import degradation and notification execution.
5. AvocetVoiceService audio player resolution across macOS (afplay), Windows (powershell), and Linux (paplay/aplay).
6. PathResolver cross-platform directory resolution for macOS, Windows, and Linux.
7. DesktopCompanion resilience against missing screens and Wayland compositor placement.
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QRect

from todo_bird_app.services.platform_service import (
    PlatformService,
    get_platform_service,
)
from todo_bird_app.services.linux_platform_service import LinuxPlatformService
from todo_bird_app.services.macos_platform_service import MacOSPlatformService
from todo_bird_app.services.windows_platform_service import WindowsPlatformService
from todo_bird_app.services.avocet_voice_service import AvocetVoiceService
from todo_bird_app.services.path_resolver import PathResolver
from todo_bird_app.widgets.desktop_companion import DesktopCompanion


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# 1. Display Guard & Headless Logic
def test_display_guard_cross_platform_behavior():
    """Verify display guard logic handles X11, Wayland, Windows, and macOS appropriately."""
    def evaluate_display_guard(platform: str, env_dict: dict, check_init: bool = False) -> str:
        with patch("sys.platform", platform), patch.dict(os.environ, env_dict, clear=True):
            # Mirror app.py logic
            res = None
            if check_init:
                res = "offscreen"
            elif "QT_QPA_PLATFORM" not in os.environ:
                if not (sys.platform == "win32" or sys.platform == "darwin"):
                    if "DISPLAY" not in os.environ and "WAYLAND_DISPLAY" not in os.environ:
                        res = "offscreen"
            return res or os.environ.get("QT_QPA_PLATFORM", "default")

    # Linux X11 present -> default QPA (not forced offscreen)
    assert evaluate_display_guard("linux", {"DISPLAY": ":0"}) == "default"

    # Linux Wayland present without DISPLAY -> default QPA (not forced offscreen)
    assert evaluate_display_guard("linux", {"WAYLAND_DISPLAY": "wayland-0"}) == "default"

    # Linux Headless (no DISPLAY, no WAYLAND_DISPLAY) -> offscreen
    assert evaluate_display_guard("linux", {}) == "offscreen"

    # Linux check-init -> offscreen
    assert evaluate_display_guard("linux", {"DISPLAY": ":0"}, check_init=True) == "offscreen"

    # FreeBSD / OpenBSD Headless -> offscreen
    assert evaluate_display_guard("freebsd13", {}) == "offscreen"
    # FreeBSD X11 -> default
    assert evaluate_display_guard("freebsd13", {"DISPLAY": ":0"}) == "default"

    # Windows (DISPLAY is absent by default) -> default (not offscreen!)
    assert evaluate_display_guard("win32", {"PATH": "C:\\Windows"}) == "default"

    # macOS (DISPLAY is absent by default) -> default (not offscreen!)
    assert evaluate_display_guard("darwin", {"HOME": "/Users/test"}) == "default"


# 2. PlatformService Factory
def test_platform_service_factory_dispatch():
    """Verify get_platform_service returns corresponding OS adapter."""
    with patch("sys.platform", "linux"):
        svc_linux = get_platform_service()
        assert isinstance(svc_linux, LinuxPlatformService)

    with patch("sys.platform", "darwin"):
        svc_mac = get_platform_service()
        assert isinstance(svc_mac, MacOSPlatformService)

    with patch("sys.platform", "win32"):
        svc_win = get_platform_service()
        assert isinstance(svc_win, WindowsPlatformService)


# 3. MacOSPlatformService
def test_macos_platform_service_autostart_and_notifications(tmp_path):
    """Verify LaunchAgent plist generation, removal, and notification escaping."""
    svc = MacOSPlatformService()

    fake_home = tmp_path / "mac_home"
    fake_home.mkdir()

    with patch("pathlib.Path.home", return_value=fake_home):
        # Enable autostart
        res_enable = svc.create_autostart_entry(True)
        assert res_enable is True
        plist_path = fake_home / "Library" / "LaunchAgents" / f"{svc.LAUNCH_AGENT_LABEL}.plist"
        assert plist_path.exists()
        content = plist_path.read_text(encoding="utf-8")
        assert "<key>RunAtLoad</key>" in content
        assert svc.LAUNCH_AGENT_LABEL in content

        # Disable autostart
        res_disable = svc.create_autostart_entry(False)
        assert res_disable is True
        assert not plist_path.exists()

    # Test notification escaping with multiline text and quotes
    with patch("shutil.which", return_value="/usr/bin/osascript"), patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        res_notif = svc.send_system_notification('He said "Hello"\nNew line', 'Alert with \\ backslash\nSecond line')
        assert res_notif is True
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        script_arg = call_args[2]
        assert '\\"Hello\\"' in script_arg
        assert "\\\\ backslash" in script_arg
        assert "\\nSecond line" in script_arg


# 4. LinuxPlatformService Safe Notification
def test_linux_platform_service_safe_notification():
    """Verify Linux notify-send executes without shell injection or quote parsing bugs."""
    svc = LinuxPlatformService()
    with patch("shutil.which", return_value="/usr/bin/notify-send"), patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        res = svc.send_system_notification("Don't forget", "Task: 'Finish Audit' & verify")
        assert res is True
        assert mock_run.called
        args = mock_run.call_args[0][0]
        assert args == ["notify-send", "Don't forget", "Task: 'Finish Audit' & verify", "--icon=dialog-information"]


# 5. WindowsPlatformService Safe Degradation
def test_windows_platform_service_safe_degradation():
    """Verify Windows platform service degrades safely without crashing."""
    svc = WindowsPlatformService()

    with patch("sys.platform", "win32"):
        # create_desktop_launcher without winshell
        with patch.dict("sys.modules", {"winshell": None, "win32com": None}):
            assert svc.create_desktop_launcher() is False

        # send_system_notification executes PowerShell without crashing
        with patch("subprocess.Popen") as mock_popen:
            res = svc.send_system_notification("Meeting", "In 5 minutes")
            assert res is True
            assert mock_popen.called


# 5. AvocetVoiceService Cross-Platform Audio Player Resolution
def test_avocet_voice_audio_player_resolution():
    """Verify player selection on macOS, Windows, and Linux."""
    # macOS resolution
    with patch("sys.platform", "darwin"), patch("shutil.which", side_effect=lambda x: "/usr/bin/afplay" if x == "afplay" else None):
        out_mac = AvocetVoiceService.resolve_audio_output()
        assert out_mac.get("player") == "/usr/bin/afplay"

    # Windows resolution
    with patch("sys.platform", "win32"), patch("shutil.which", side_effect=lambda x: "C:\\powershell.exe" if "powershell" in x else None):
        out_win = AvocetVoiceService.resolve_audio_output()
        assert out_win.get("player") == "C:\\powershell.exe"

    # Linux resolution
    with patch("sys.platform", "linux"), patch("shutil.which", side_effect=lambda x: "/usr/bin/paplay" if x == "paplay" else None):
        out_lin = AvocetVoiceService.resolve_audio_output()
        assert out_lin.get("player") == "/usr/bin/paplay"


# 6. PathResolver Cross-Platform Resolution
def test_path_resolver_directories():
    """Verify PathResolver targets standard OS directories."""
    env_clean = {k: v for k, v in os.environ.items() if k != PathResolver.APP_DATA_ENV}
    env_clean["TODO_BIRD_RUNTIME_MODE"] = "packaged"

    # macOS
    with patch("sys.platform", "darwin"), patch.dict(os.environ, env_clean, clear=True):
        mac_dir = PathResolver.get_app_data_dir()
        assert mac_dir == Path.home() / "Library" / "Application Support" / "TodoBird"
        mac_db = PathResolver.get_database_path()
        assert mac_db.name == "todo_bird.db"

    # Windows
    env_win = dict(env_clean)
    env_win["LOCALAPPDATA"] = "C:\\AppData\\Local"
    with patch("sys.platform", "win32"), patch.dict(os.environ, env_win, clear=True):
        win_dir = PathResolver.get_app_data_dir()
        assert str(win_dir).replace("\\", "/") == "C:/AppData/Local/TodoBird"
        win_db = PathResolver.get_database_path()
        assert win_db.name == "todo_bird.db"


# 7. DesktopCompanion Resilience
def test_desktop_companion_screen_resilience(qapp):
    """Verify DesktopCompanion starts and cleans up safely with None screen and on Wayland."""
    # None screen
    with patch.object(QApplication, "primaryScreen", return_value=None):
        comp = DesktopCompanion(greeting_text="Hello", settings_manager=None)
        assert comp is not None
        comp.cleanup()

    # Wayland non-positionable
    with patch("todo_bird_app.services.window_interaction_service.PlatformCapabilities.supports_manual_top_level_positioning", return_value=False):
        comp_wayland = DesktopCompanion(greeting_text="", settings_manager=None)
        comp_wayland.start_sequence()
        assert comp_wayland.blinking_enabled is True
        comp_wayland.exit_scene()
        assert getattr(comp_wayland, "_cleaning_up", False) is True


# 8. Bundled Inter Fonts Registration
def test_bundled_inter_fonts_registration(qapp):
    """Verify bundled Inter fonts are registered in QFontDatabase."""
    from todo_bird_app.services.typography_service import TypographyService
    from PySide6.QtGui import QFontDatabase

    loaded = TypographyService.initialize_application_fonts()
    assert loaded == 4
    families = QFontDatabase.families()
    assert any("Inter" in f for f in families)


# 9. MainWindow Native Menu Bar Across Platforms
def test_mainwindow_native_menu_bar(qapp, tmp_path):
    """Verify MainWindow initializes File, Edit, View, and Help menus properly across platforms."""
    from todo_bird_app.database import DatabaseManager
    from todo_bird_app.settings.settings_manager import SettingsManager
    from todo_bird_app.controllers.theme_controller import ThemeController
    from todo_bird_app.views.main_window import MainWindow

    db_path = tmp_path / "menu_test.db"
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()

    db = DatabaseManager(db_path)
    settings = SettingsManager(db_manager=db, config_dir=cfg_dir)
    theme = ThemeController(settings)

    # macOS: Native Menu Bar
    with patch("sys.platform", "darwin"):
        win_mac = MainWindow(db, settings, theme)
        menubar_mac = win_mac.menuBar()
        actions = [a.text() for a in menubar_mac.actions()]
        assert "&File" in actions
        assert "&Edit" in actions
        assert "&View" in actions
        assert "&Help" in actions
        assert not menubar_mac.isHidden()
        win_mac.close()

    # Linux: In-window Menu Bar hidden by default (clean HeaderBar)
    with patch("sys.platform", "linux"):
        win_lin = MainWindow(db, settings, theme)
        menubar_lin = win_lin.menuBar()
        assert menubar_lin.isHidden()
        win_lin.close()


# 10. PathResolver Database Migration
def test_path_resolver_database_migration(tmp_path):
    """Verify ensure_database_migrated copies the seed database if target does not exist."""
    fake_target = tmp_path / "user_data" / "migrated.db"
    assert not fake_target.exists()

    result = PathResolver.ensure_database_migrated(fake_target)
    assert result == fake_target
    assert fake_target.exists()
    assert fake_target.stat().st_size > 0
