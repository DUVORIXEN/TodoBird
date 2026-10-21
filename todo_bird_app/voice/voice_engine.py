import logging
import threading
from datetime import datetime
from typing import Optional
try:
    # pyrefly: ignore [missing-import]
    import pyttsx3
except ImportError:
    pyttsx3 = None

logger = logging.getLogger(__name__)

class VoiceEngine:
    """
    100% Offline TTS Voice Engine for TODO BIRD companion.
    Synthesizes respectful, soft South Indian style greetings.
    """
    def __init__(self, settings_manager):
        self.settings_manager = settings_manager
        self._engine = None
        self._init_tts()

    def _init_tts(self):
        if pyttsx3 is None:
            logger.info("pyttsx3 unavailable; using Avocet Piper voice service.")
            return

        try:
            self._engine = pyttsx3.init()
            # Set rate & volume
            rate = self.settings_manager.get("voice_rate", 150)
            self._engine.setProperty("rate", rate)
            self._engine.setProperty("volume", 0.9)

            # Try finding female Indian or soft voice
            voices = self._engine.getProperty("voices")
            for v in voices:
                if "female" in v.name.lower() or "hindi" in v.name.lower() or "india" in v.name.lower() or "ta" in v.id or "te" in v.id:
                    self._engine.setProperty("voice", v.id)
                    break
        except Exception as e:
            logger.warning(f"Unable to initialize pyttsx3 voice engine: {e}")

    def speak(self, text: str):
        if not self.settings_manager.get("voice_enabled", True):
            return

        try:
            from todo_bird_app.services.avocet_voice_service import AvocetVoiceService
            AvocetVoiceService.speak_async(
                text,
                settings_manager=self.settings_manager,
            )
            return
        except Exception as e:
            logger.debug(f"AvocetVoiceService speak_async fallback: {e}")

        def _run():
            try:
                if self._engine:
                    self._engine.say(text)
                    self._engine.runAndWait()
            except Exception as e:
                logger.error(f"Error in TTS speech synthesis: {e}")

        # Run speech synthesis in background thread to keep UI fluid
        threading.Thread(target=_run, daemon=True).start()

    def get_greeting(self, is_shutdown_workflow: bool = False) -> str:
        hour = datetime.now().hour
        salutation = self.settings_manager.get("user_salutation", "friend") or "friend"

        if is_shutdown_workflow:
            return f"{salutation}... Before you rest... Shall we lovingly prepare tomorrow's work?"

        if 5 <= hour < 12:
            return f"{salutation}... Good morning... With the blessings of Vighnavinashaka... May your work go smoothly today... Shall we begin?"
        elif 12 <= hour < 17:
            return "Good afternoon... Welcome back..."
        else:
            # Evening or Night startup (Strictly NEVER say Good Night at startup)
            return "Good evening... Welcome... Shall we continue today's work?"
