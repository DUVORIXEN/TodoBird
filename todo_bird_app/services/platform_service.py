import sys
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

class PlatformService(ABC):
    """
    Abstract platform service interface separating OS-specific launcher,
    autostart, notifications, and desktop shortcuts.
    """
    @abstractmethod
    def create_desktop_launcher(self) -> bool:
        pass

    @abstractmethod
    def create_autostart_entry(self, enabled: bool) -> bool:
        pass

    @abstractmethod
    def send_system_notification(self, title: str, message: str) -> bool:
        pass

    @abstractmethod
    def register_app_user_model_id(self):
        pass

def get_platform_service() -> PlatformService:
    if sys.platform == "win32":
        from todo_bird_app.services.windows_platform_service import WindowsPlatformService
        return WindowsPlatformService()
    elif sys.platform == "darwin":
        from todo_bird_app.services.macos_platform_service import MacOSPlatformService
        return MacOSPlatformService()
    else:
        from todo_bird_app.services.linux_platform_service import LinuxPlatformService
        return LinuxPlatformService()
