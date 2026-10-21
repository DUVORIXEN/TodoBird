import os
import sys
import logging
import subprocess
from pathlib import Path
from todo_bird_app.services.platform_service import PlatformService

logger = logging.getLogger(__name__)

class MacOSPlatformService(PlatformService):
    """
    Apple macOS Platform Service.
    Handles LaunchAgent autostart, native AppleScript system notifications,
    and desktop launcher creation.
    """
    LAUNCH_AGENT_LABEL = "com.todobird.desktop"

    def create_desktop_launcher(self) -> bool:
        """
        Creates a macOS desktop shortcut launcher script on the user's Desktop.
        """
        try:
            desktop_dir = Path.home() / "Desktop"
            if not desktop_dir.exists():
                return False

            shortcut_file = desktop_dir / "TODO BIRD.command"
            app_script = Path(__file__).parent.parent / "app.py"
            exec_path = sys.executable

            content = f"""#!/bin/bash
cd "{app_script.parent.parent}"
exec "{exec_path}" "{app_script}" "$@"
"""
            shortcut_file.write_text(content, encoding="utf-8")
            os.chmod(shortcut_file, 0o755)
            logger.info(f"macOS desktop shortcut created at: {shortcut_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to create macOS desktop launcher: {e}")
            return False

    def create_autostart_entry(self, enabled: bool) -> bool:
        """
        Configures autostart via macOS LaunchAgents plist.
        """
        try:
            launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
            launch_agents_dir.mkdir(parents=True, exist_ok=True)
            plist_file = launch_agents_dir / f"{self.LAUNCH_AGENT_LABEL}.plist"

            if enabled:
                app_script = Path(__file__).parent.parent / "app.py"
                python_exec = sys.executable

                content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{self.LAUNCH_AGENT_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_exec}</string>
        <string>{str(app_script.resolve())}</string>
        <string>--autostart</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
"""
                plist_file.write_text(content, encoding="utf-8")
                logger.info(f"macOS autostart LaunchAgent written to: {plist_file}")
            elif plist_file.exists():
                plist_file.unlink()
                logger.info(f"macOS autostart LaunchAgent removed from: {plist_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to configure macOS autostart: {e}")
            return False

    def send_system_notification(self, title: str, message: str) -> bool:
        """
        Sends native macOS notification via osascript.
        """
        try:
            import shutil
            if not shutil.which("osascript"):
                logger.info("osascript not found on system; macOS notification omitted.")
                return False
            safe_title = str(title).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", "")
            safe_msg = str(message).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")
            script = f'display notification "{safe_msg}" with title "{safe_title}"'
            res = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                check=False
            )
            return res.returncode == 0
        except Exception as e:
            logger.error(f"Failed to send macOS notification: {e}")
            return False

    def register_app_user_model_id(self):
        """Not applicable on macOS."""
        pass
