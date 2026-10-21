import os
import sys
import logging
import subprocess
from pathlib import Path
from todo_bird_app.services.platform_service import PlatformService

logger = logging.getLogger(__name__)

class WindowsPlatformService(PlatformService):
    """
    Windows 11 Platform Service.
    Handles AppUserModelID registration (for clean Windows taskbar grouping & notifications),
    Start Menu shortcut, and Windows Registry autostart.
    """
    APP_ID = "TodoBird.App.1.0.0"

    def register_app_user_model_id(self):
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(self.APP_ID)
                logger.info(f"Registered Windows AppUserModelID: {self.APP_ID}")
            except Exception as e:
                logger.error(f"Failed to register AppUserModelID: {e}")

    def create_desktop_launcher(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            try:
                import winshell
                from win32com.client import Dispatch
            except ImportError as ie:
                logger.warning(
                    "Optional Windows shortcut dependencies ('winshell' or 'pywin32') not found (%s). "
                    "Shortcut creation skipped. Install via: pip install pywin32 winshell",
                    ie
                )
                return False

            desktop = Path(winshell.desktop())
            shortcut_path = str(desktop / "TODO BIRD.lnk")

            target = sys.executable if getattr(sys, 'frozen', False) else f"{sys.executable}"
            args = "" if getattr(sys, 'frozen', False) else f'"{Path(__file__).parent.parent / "app.py"}"'

            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.Targetpath = target
            shortcut.Arguments = args
            shortcut.WorkingDirectory = str(Path(__file__).parent.parent)
            shortcut.save()
            logger.info(f"Windows desktop shortcut created at: {shortcut_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to create Windows desktop shortcut: {e}")
        return False

    def create_autostart_entry(self, enabled: bool) -> bool:
        try:
            if sys.platform == "win32":
                import winreg
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
                if enabled:
                    cmd = f'"{sys.executable}"' if getattr(sys, 'frozen', False) else f'"{sys.executable}" "{Path(__file__).parent.parent / "app.py"}"'
                    winreg.SetValueEx(key, "TodoBird", 0, winreg.REG_SZ, cmd)
                else:
                    try:
                        winreg.DeleteValue(key, "TodoBird")
                    except FileNotFoundError:
                        pass
                winreg.CloseKey(key)
                return True
        except Exception as e:
            logger.error(f"Failed to configure Windows autostart: {e}")
        return False

    def send_system_notification(self, title: str, message: str) -> bool:
        logger.info(f"Windows Notification [{title}]: {message}")
        if sys.platform == "win32":
            try:
                safe_title = str(title).replace("'", "''").replace('"', '`"')
                safe_msg = str(message).replace("'", "''").replace('"', '`"')
                cmd = [
                    "powershell", "-NoProfile", "-NonInteractive", "-Command",
                    f"[reflection.assembly]::loadwithpartialname('System.Windows.Forms') | Out-Null; "
                    f"$notify = New-Object System.Windows.Forms.NotifyIcon; "
                    f"$notify.Icon = [System.Drawing.SystemIcons]::Information; "
                    f"$notify.Visible = $True; "
                    f"$notify.ShowBalloonTip(5000, '{safe_title}', '{safe_msg}', [System.Windows.Forms.ToolTipIcon]::Info)"
                ]
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception as e:
                logger.debug(f"PowerShell notification fallback: {e}")
        return True
