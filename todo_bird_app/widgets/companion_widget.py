import logging
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout
from PySide6.QtCore import Qt, QPoint, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QPainter

from todo_bird_app.animations.companion_animator import CompanionAnimator
from todo_bird_app.voice.voice_engine import VoiceEngine

logger = logging.getLogger(__name__)

class SpeechBubble(QFrame):
    """
    Speech bubble overlay displaying companion text.
    """
    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("CardWidget")
        self.setStyleSheet("""
            #CardWidget {
                background-color: #242538;
                border: 2px solid #E95420;
                border-radius: 12px;
                padding: 10px 14px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("font-size: 13px; font-weight: 600; color: #F3F4F6;")
        layout.addWidget(self.label)

    def set_text(self, text: str):
        self.label.setText(text)


class CompanionWidget(QWidget):
    """
    Interactive Companion Widget displaying animated avatars & speech bubbles.
    """
    def __init__(self, settings_manager, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.voice_engine = VoiceEngine(settings_manager)

        companion_type = settings_manager.get("active_companion", "avocet")
        self.animator = CompanionAnimator(companion_type, self)
        self.animator.frame_updated.connect(self.update)

        self.setFixedSize(280, 200)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # Speech Bubble
        self.bubble = SpeechBubble("", self)
        self.bubble.setVisible(False)
        main_layout.addWidget(self.bubble)

        main_layout.addStretch()

    def update_companion_type(self):
        comp = self.settings_manager.get("active_companion", "avocet")
        self.animator.set_companion(comp)

    def trigger_greeting(self, is_shutdown: bool = False):
        text = self.voice_engine.get_greeting(is_shutdown_workflow=is_shutdown)
        self.bubble.set_text(text)
        self.bubble.setVisible(True)

        # Trigger voice synthesis
        self.voice_engine.speak(text)

        # Start animation sequence
        self.animator.start_flight_sequence()

        # Hide bubble after 10 seconds
        QTimer.singleShot(10000, lambda: self.bubble.setVisible(False))

    def paintEvent(self, event):
        painter = QPainter(self)
        self.animator.draw_companion(painter, self.width(), self.height())
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.trigger_greeting()
