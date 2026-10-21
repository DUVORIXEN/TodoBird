import os
import subprocess
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

SERVICE_TEMPLATE = """[Unit]
Description=TODO BIRD Offline Systemd Night Shutdown Guard
Documentation=https://github.com/todobird/todo_bird
After=graphical-session.target

[Service]
Type=simple
ExecStart={python_exec} {app_script} --shutdown-guard-daemon
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=default.target
"""

class SystemdServiceInstaller:
    """
    Installs systemd user service for TODO BIRD shutdown guard on Ubuntu 24.04.
    """
    @staticmethod
    def install_user_service() -> bool:
        try:
            user_service_dir = Path.home() / ".config" / "systemd" / "user"
            user_service_dir.mkdir(parents=True, exist_ok=True)

            service_file = user_service_dir / "todo-bird-shutdown-guard.service"

            python_exec = Path(__file__).parent.parent.parent / "venv" / "bin" / "python"
            app_script = Path(__file__).parent.parent / "app.py"

            content = SERVICE_TEMPLATE.format(
                python_exec=str(python_exec.resolve()),
                app_script=str(app_script.resolve())
            )

            with open(service_file, "w", encoding="utf-8") as f:
                f.write(content)

            logger.info(f"Systemd user service written to {service_file}")

            # Reload systemd user daemon
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
            return True
        except Exception as e:
            logger.error(f"Error installing systemd user service: {e}")
            return False
