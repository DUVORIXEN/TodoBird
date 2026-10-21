import os
import sys
import logging
from pathlib import Path
from todo_bird_app.services.platform_service import PlatformService

logger = logging.getLogger(__name__)

class LinuxPlatformService(PlatformService):
    """
    Linux & Ubuntu 24.04 GNOME Desktop Platform Service.
    Handles .desktop file launcher creation, autostart, and libnotify system notifications.
    """
    def create_desktop_launcher(self) -> bool:
        if os.environ.get("SNAP") or os.environ.get("FLATPAK_ID") or os.path.exists("/.flatpak-info"):
            logger.info("Running under container sandbox (Snap/Flatpak); desktop launcher managed by host.")
            return True
        try:
            exec_path = f"{sys.executable} {Path(__file__).parent.parent / 'app.py'}"
            icon_path = str(Path(__file__).parent.parent / "assets" / "icons" / "todo-bird.png")
            apps_dir = Path.home() / ".local" / "share" / "applications"
            apps_dir.mkdir(parents=True, exist_ok=True)
            desktop_file = apps_dir / "todo-bird.desktop"

            content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=TODO BIRD
Comment=Offline Desktop Personal Assistant & Task Manager
Exec={exec_path}
Icon={icon_path}
Terminal=false
Categories=Utility;Office;ProjectManagement;
StartupWMClass=TODO BIRD
Keywords=todo;task;gantt;assistant;productivity;
StartupNotify=false
"""
            desktop_file.write_text(content, encoding="utf-8")
            os.chmod(desktop_file, 0o755)
            logger.info(f"Linux desktop launcher created at: {desktop_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to create Linux desktop launcher: {e}")
            return False

    # Autostart must reuse the launcher's desktop-file name: DEs key autostart
    # on that name, and a second filename (an older build wrote
    # todo-bird-autostart.desktop) would race the launcher or leave a stale
    # flagless entry behind that silently disables session-login detection.
    AUTOSTART_FILE = "todo-bird.desktop"
    _LEGACY_AUTOSTART_FILES = ("todo-bird-autostart.desktop",)

    def create_autostart_entry(self, enabled: bool) -> bool:
        if os.environ.get("SNAP") or os.environ.get("FLATPAK_ID") or os.path.exists("/.flatpak-info"):
            logger.info("Running under container sandbox (Snap/Flatpak); autostart managed by host.")
            return True
        try:
            autostart_dir = Path.home() / ".config" / "autostart"
            autostart_dir.mkdir(parents=True, exist_ok=True)
            auto_file = autostart_dir / self.AUTOSTART_FILE
            legacy_files = [autostart_dir / name for name in self._LEGACY_AUTOSTART_FILES]
            if enabled:
                exec_path = f"{sys.executable} {Path(__file__).parent.parent / 'app.py'} --autostart"
                content = f"[Desktop Entry]\nType=Application\nName=TODO BIRD\nExec={exec_path}\nHidden=false\nNoDisplay=false\nX-GNOME-Autostart-enabled=true\nStartupNotify=false\n"
                auto_file.write_text(content, encoding="utf-8")
                os.chmod(auto_file, 0o755)
                for legacy in legacy_files:
                    if legacy.exists() and legacy != auto_file:
                        legacy.unlink()
            else:
                for stale in [auto_file, *legacy_files]:
                    if stale.exists():
                        stale.unlink()
            return True
        except Exception as e:
            logger.error(f"Failed to configure Linux autostart: {e}")
            return False

    def send_system_notification(self, title: str, message: str) -> bool:
        try:
            import shutil
            import subprocess
            if not shutil.which("notify-send"):
                logger.info("notify-send utility not found on system; notification omitted.")
                return False
            res = subprocess.run(
                ["notify-send", str(title), str(message), "--icon=dialog-information"],
                capture_output=True,
                text=True,
                check=False
            )
            return res.returncode == 0
        except Exception as e:
            logger.error(f"Failed to send Linux notification: {e}")
            return False

    def register_app_user_model_id(self):
        pass  # Not required on Linux
