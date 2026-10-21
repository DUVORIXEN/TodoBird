import random
import logging
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QApplication,
    QFrame,
)
from PySide6.QtCore import (
    Qt,
    QTimer,
    QPoint,
    QPropertyAnimation,
    QSize,
    QRect,
)
from PySide6.QtGui import QMovie


BASE_DIR = Path(__file__).resolve().parent.parent.parent
ASSET_DIR = BASE_DIR / "assets" / "characters"
VOICE_DIR = BASE_DIR / "voice"

logger = logging.getLogger(__name__)


class _InactiveTimerHandle:
    def isActive(self):
        return False

    def stop(self):
        return None


def speak_lovely_async(
    text: str,
    voice_profile: Optional[str] = None,
    settings_manager=None,
    on_started=None,
    on_completed=None,
    on_failed=None,
):
    from todo_bird_app.services.avocet_voice_service import AvocetVoiceService
    return AvocetVoiceService.speak_async(
        text=text,
        voice_profile=voice_profile,
        settings_manager=settings_manager,
        on_started=on_started,
        on_completed=on_completed,
        on_failed=on_failed,
    )


class DesktopCompanion(QWidget):
    def __init__(
        self,
        greeting_text: str,
        parent=None,
        voice_profile: Optional[str] = None,
        settings_manager=None,
        on_speech_started=None,
        on_speech_completed=None,
        on_speech_failed=None,
    ):
        super().__init__(parent)

        self.greeting_text = greeting_text
        self.voice_profile = voice_profile
        self.settings_manager = settings_manager
        self.on_speech_started = on_speech_started
        self.on_speech_completed = on_speech_completed
        self.on_speech_failed = on_speech_failed
        self.movie = None
        self.blinking_enabled = False
        self.flight_timer = _InactiveTimerHandle()

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.register(self, role="companion")

        self.resize(520, 360)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(8)

        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setFixedSize(QSize(430, 270))
        root.addWidget(self.icon, alignment=Qt.AlignCenter)

        primary_screen = QApplication.primaryScreen()
        screen = primary_screen.availableGeometry() if primary_screen else QRect(0, 0, 1920, 1080)

        # Dramatic Avocet entrance from outside the right edge
        self.start_pos = QPoint(
            screen.right() + 420,
            screen.top() + 120,
        )

        # Fly well into the screen first
        self.path1 = QPoint(
            screen.left() + int(screen.width() * 0.72),
            screen.top() + 180,
        )

        # Sweep further toward the middle
        self.path2 = QPoint(
            screen.left() + int(screen.width() * 0.42),
            screen.top() + 90,
        )

        # Curve back and land near the upper-right
        self.land_pos = QPoint(
            screen.right() - self.width() - 40,
            screen.top() + 40,
        )

        self.exit_pos = QPoint(
            screen.right() + 180,
            screen.top() - 160,
        )

        self.move(self.start_pos)

    def asset(self, name: str) -> Path:
        return ASSET_DIR / name

    def set_movie(self, path: Path):
        if path.exists() and path.stat().st_size > 0:
            if self.movie:
                self.movie.stop()

            self.movie = QMovie(str(path))
            self.movie.setScaledSize(self.icon.size())
            self.icon.setMovie(self.movie)
            self.movie.start()
        else:
            self.icon.setText("")
            self.icon.setStyleSheet("font-size: 110px;")

    def start_sequence(self):
        self.show()
        self.raise_()

        self.set_movie(self.asset("avocet_fly.gif"))

        self.fly1 = QPropertyAnimation(self, b"pos")
        self.fly1.setDuration(1400)
        self.fly1.setStartValue(self.start_pos)
        self.fly1.setEndValue(self.path1)

        self.fly2 = QPropertyAnimation(self, b"pos")
        self.fly2.setDuration(1600)
        self.fly2.setStartValue(self.path1)
        self.fly2.setEndValue(self.path2)

        self.fly3 = QPropertyAnimation(self, b"pos")
        self.fly3.setDuration(1000)
        self.fly3.setStartValue(self.path2)
        self.fly3.setEndValue(self.land_pos)

        from todo_bird_app.services.window_interaction_service import PlatformCapabilities

        if not PlatformCapabilities.supports_manual_top_level_positioning():
            self.on_landed()
        else:
            self.fly1.finished.connect(self.fly2.start)
            self.fly2.finished.connect(self.fly3.start)
            self.fly3.finished.connect(self.on_landed)
            self.fly1.start()

        clean_greeting = " ".join(str(self.greeting_text or "").split())
        if not clean_greeting:
            logger.info("Desktop companion speech skipped: no startup greeting text selected.")
            return

        QTimer.singleShot(
            700,
            lambda: speak_lovely_async(
                clean_greeting,
                voice_profile=self.voice_profile,
                settings_manager=self.settings_manager,
                on_started=self.on_speech_started,
                on_completed=self.on_speech_completed,
                on_failed=self.on_speech_failed,
            ),
        )

    def on_landed(self):
        self.set_movie(self.asset("avocet_idle.gif"))
        self.blinking_enabled = True

        QTimer.singleShot(
            2200,
            self.schedule_blink,
        )

    def schedule_blink(self):
        if self.blinking_enabled:
            QTimer.singleShot(
                random.randint(3000, 5000),
                self.do_blink,
            )

    def do_blink(self):
        if not self.blinking_enabled:
            return

        self.set_movie(
            self.asset("avocet_blink.gif")
        )

        QTimer.singleShot(
            900,
            lambda: self.set_movie(
                self.asset("avocet_idle.gif")
            ),
        )

        self.schedule_blink()

    def exit_scene(self):
        self.blinking_enabled = False

        from todo_bird_app.services.window_interaction_service import PlatformCapabilities

        if not PlatformCapabilities.supports_manual_top_level_positioning():
            self.cleanup()
            return

        self.set_movie(
            self.asset("avocet_fly.gif")
        )

        self.exit_animation = QPropertyAnimation(
            self,
            b"pos",
        )

        self.exit_animation.setDuration(1200)
        self.exit_animation.setStartValue(self.pos())
        self.exit_animation.setEndValue(self.exit_pos)

        self.exit_animation.finished.connect(
            self.cleanup
        )

        self.exit_animation.start()

    def cleanup(self):
        """Stops animations, timers, movies and closes the companion widget cleanly."""
        if getattr(self, "_cleaning_up", False):
            return
        self._cleaning_up = True
        self.blinking_enabled = False
        if hasattr(self, "movie") and self.movie:
            try:
                self.movie.stop()
            except Exception:
                pass
        for anim in (getattr(self, "fly1", None), getattr(self, "fly2", None), getattr(self, "fly3", None), getattr(self, "exit_animation", None)):
            if anim:
                try:
                    anim.stop()
                except Exception:
                    pass
        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.unregister(self)
        self.close()
        self.deleteLater()

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)
