import random
import logging
from typing import Optional
from todo_bird_app.controllers.delay_engine import TimingStatus

logger = logging.getLogger(__name__)

EARLY_MESSAGES = [
    "Excellent work, {salutation}. You completed this task before the planned time.",
    "Wonderful efficiency! You finished earlier than scheduled.",
    "Very impressive focus, {salutation}. Task completed early.",
]

ONTIME_MESSAGES = [
    "Well done, {salutation}. You completed this task on time.",
    "Great execution! Your planning and timing matched perfectly.",
    "Very good, {salutation}. Steady progress achieved on schedule.",
]

RECOVERED_MESSAGES = [
    "Well done. You recovered the delayed task and completed it successfully.",
    "Great resilience! The delay was handled cleanly.",
]

TOP3_MESSAGES = [
    "Wonderful work today. You completed your important priorities.",
    "Excellent milestone! All top priorities are complete.",
]

MUSTDO_MESSAGES = [
    "Your most important task is completed. That is a meaningful achievement.",
    "Priority task complete! Great focus, {salutation}.",
]

class AppreciationSystem:
    """
    Empathetic, respectful appreciation feedback generator.
    Rotates respectful messages and triggers offline speech synthesis.
    """
    def __init__(self, settings_manager, voice_engine=None):
        self.settings_manager = settings_manager
        self.voice_engine = voice_engine

    def get_appreciation(self, status: TimingStatus, is_must_do: bool = False, all_top3_done: bool = False) -> Optional[str]:
        if not self.settings_manager.get("appreciation_enabled", True):
            return None

        level = self.settings_manager.get("appreciation_level", "balanced")
        if level == "minimal" and not (is_must_do or all_top3_done):
            return None

        if all_top3_done:
            msg = random.choice(TOP3_MESSAGES)
        elif is_must_do:
            msg = random.choice(MUSTDO_MESSAGES)
        elif status == TimingStatus.COMPLETED_BEFORE_TIME:
            msg = random.choice(EARLY_MESSAGES)
        elif status == TimingStatus.COMPLETED_ON_TIME:
            msg = random.choice(ONTIME_MESSAGES)
        elif status in (TimingStatus.SLIGHT_DELAY, TimingStatus.MODERATE_DELAY):
            msg = random.choice(RECOVERED_MESSAGES)
        else:
            return None

        salutation = self.settings_manager.get("user_salutation", "friend") or "friend"
        msg = msg.replace("{salutation}", str(salutation))

        if self.voice_engine and self.settings_manager.get("voice_appreciation_enabled", True):
            self.voice_engine.speak(msg)

        return msg
