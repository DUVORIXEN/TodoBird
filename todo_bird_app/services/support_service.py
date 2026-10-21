import logging
from typing import Dict, Any, Tuple
from datetime import datetime, timedelta

from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.database import DatabaseManager
from todo_bird_app.__version__ import SUPPORT_AUTOMATIC_PROMPTS_ENABLED

logger = logging.getLogger(__name__)

class SupportService:
    """
    Manages the 'Support Todo Bird' functionality, enforcing cooldowns,
    eligibility thresholds, and safely resolving the canonical external URL.
    """
    
    # Canonical external hosted payment/support page
    SUPPORT_URL = "https://razorpay.me/@duvorixen"
    
    MIN_ACTIVE_DAYS = 7
    MIN_COMPLETED_TASKS = 30
    COOLDOWN_DAYS = 30
    
    def __init__(self, settings_manager: SettingsManager, db_manager: DatabaseManager):
        self.settings = settings_manager
        self.db = db_manager

    def get_support_url(self) -> str:
        """Returns the canonical HTTPS URL for supporting Todo Bird."""
        return self.SUPPORT_URL

    def record_support_prompt_shown(self):
        """Records the timestamp of the last automatic prompt."""
        self.settings.set("last_support_prompt_date", datetime.now().isoformat())
        count = self.settings.get("support_prompt_count", 0)
        self.settings.set("support_prompt_count", count + 1)

    def disable_automatic_prompts(self):
        """Permanently disables automatic prompts ('Don't ask me again')."""
        self.settings.set("support_prompt_dismissed_permanently", True)

    def is_eligible_for_automatic_prompt(self) -> bool:
        """
        Determines if the user meets usage thresholds AND is not in a cooldown period.
        """
        if not SUPPORT_AUTOMATIC_PROMPTS_ENABLED:
            return False

        if not self.settings.get("support_prompt_enabled", True):
            return False

        if self.settings.get("support_prompt_dismissed_permanently", False):
            return False

        # Check cooldown
        last_prompt_str = self.settings.get("last_support_prompt_date")
        if last_prompt_str:
            try:
                last_prompt = datetime.fromisoformat(last_prompt_str)
                if datetime.now() - last_prompt < timedelta(days=self.COOLDOWN_DAYS):
                    return False
            except ValueError:
                pass # Corrupt date, allow prompt

        # Check eligibility: active days OR completed tasks
        # Active days proxy: distance between first task created and now
        # If we had a specific "first_launch" date, we'd use that.
        tasks = self.db.get_all_tasks()
        
        completed_count = sum(1 for t in tasks if t.get("status") == "Completed")
        if completed_count >= self.MIN_COMPLETED_TASKS:
            return True
            
        if tasks:
            try:
                first_task = min(
                    datetime.fromisoformat(t["created_at"]) 
                    for t in tasks if t.get("created_at")
                )
                if datetime.now() - first_task >= timedelta(days=self.MIN_ACTIVE_DAYS):
                    return True
            except (ValueError, TypeError):
                pass
                
        return False
