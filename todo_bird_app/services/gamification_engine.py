import logging
from datetime import date, datetime, timedelta
from typing import Dict, Any, List

from todo_bird_app.utils.time_math import utc_timestamp_to_local_date

logger = logging.getLogger(__name__)

class GamificationEngine:
    """
    100% Offline Productivity Gamification & Streak Engine for TODO BIRD.
    Calculates user XP, level, rank titles, streak streaks, and reward badges.
    """
    RANKS = [
        (0, "Fledgling Planner 🐣"),
        (100, "Novice Strategist 🌿"),
        (300, "Focus Apprentice 🎯"),
        (600, "Task Master 🦅"),
        (1000, "Gantt Architect 📐"),
        (1500, "Productivity Legend 👑"),
    ]

    def __init__(self, db_manager):
        self.db_manager = db_manager

    def calculate_stats(self) -> Dict[str, Any]:
        tasks = self.db_manager.get_all_tasks()
        completed_tasks = [t for t in tasks if t.get("status") == "Completed"]
        
        # XP Calculation: 10 XP per completed task + 15 bonus XP for on-time completion
        total_xp = 0
        for t in completed_tasks:
            total_xp += 10
            if (t.get("delay_minutes") or 0) <= 0:
                total_xp += 15

        # Level & Rank
        level = 1 + (total_xp // 100)
        rank_title = "Fledgling Planner 🐣"
        for xp_threshold, title in self.RANKS:
            if total_xp >= xp_threshold:
                rank_title = title

        # Streak Calculation. updated_at is a UTC SQLite timestamp — map it to
        # the local calendar date, else completions between local midnight and
        # the UTC offset land on the wrong day and silently break the streak.
        completed_dates = set()
        for t in completed_tasks:
            raw = t.get("updated_at")
            if raw:
                d = utc_timestamp_to_local_date(raw)
            else:
                d = utc_timestamp_to_local_date(t.get("planned_date"))
            if d:
                completed_dates.add(d)

        current_streak = 0
        check_date = date.today()
        while check_date in completed_dates or (check_date == date.today() and (check_date - timedelta(days=1)) in completed_dates):
            if check_date in completed_dates:
                current_streak += 1
                check_date -= timedelta(days=1)
            elif check_date == date.today():
                check_date -= timedelta(days=1)
            else:
                break

        return {
            "total_xp": total_xp,
            "level": level,
            "rank_title": rank_title,
            "current_streak": current_streak,
            "completed_count": len(completed_tasks),
            "total_count": len(tasks),
        }
