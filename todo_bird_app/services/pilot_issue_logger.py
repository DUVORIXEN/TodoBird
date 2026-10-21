import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from todo_bird_app.services.path_resolver import PathResolver
from todo_bird_app.__version__ import __version__

logger = logging.getLogger(__name__)

class PilotIssueLogger:
    """
    Pilot Feedback & Issue Tracker Engine.
    Stores user feedback, bug reports, and diagnostic details locally in pilot_issues.json.
    """
    def __init__(self):
        self.issue_file = PathResolver.get_config_dir() / "pilot_issues.json"

    def get_all_issues(self) -> List[Dict[str, Any]]:
        if not self.issue_file.exists():
            return []
        try:
            with open(self.issue_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read pilot issues: {e}")
            return []

    def log_issue(
        self,
        title: str,
        severity: str,
        description: str,
        reproduction_steps: str = "",
        expected_result: str = "",
        actual_result: str = ""
    ) -> Dict[str, Any]:
        issues = self.get_all_issues()
        issue_id = f"ISSUE-{len(issues) + 1:04d}"

        issue = {
            "issue_id": issue_id,
            "date": datetime.now().isoformat(),
            "os": sys.platform,
            "version": __version__,
            "title": title,
            "severity": severity,
            "description": description,
            "reproduction_steps": reproduction_steps,
            "expected_result": expected_result,
            "actual_result": actual_result,
            "status": "Open"
        }

        issues.append(issue)
        try:
            with open(self.issue_file, "w", encoding="utf-8") as f:
                json.dump(issues, f, indent=2)
            logger.info(f"Pilot issue logged: {issue_id} — {title}")
        except Exception as e:
            logger.error(f"Failed to save pilot issue: {e}")

        return issue

    def export_issue_report(self, export_path: Path) -> bool:
        issues = self.get_all_issues()
        try:
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(issues, f, indent=2)
            return True
        except Exception:
            return False
