import os
import sys
import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from todo_bird_app.services.path_resolver import PathResolver
from todo_bird_app.__version__ import __version__

logger = logging.getLogger(__name__)


class PilotIssueLogger:
    """
    User Feedback, Sentiment Rating, Community Check-In & Issue Tracker Engine.
    Stores user feedback, star ratings, mood sentiment, user profile (name/role/country),
    and diagnostic details locally in pilot_issues.json, and supports direct delivery
    to the developer via GitHub Community Wall or HTTPS Webhook.
    """
    GITHUB_REPO = "DUVORIXEN/TodoBird"

    def __init__(self):
        self.issue_file = PathResolver.get_config_dir() / "pilot_issues.json"

    @staticmethod
    def detect_install_channel() -> str:
        """Detects which store or package channel the user downloaded Todo Bird from."""
        if os.environ.get("SNAP") or os.environ.get("SNAP_NAME"):
            return "Ubuntu Software (Snap Store)"
        if os.environ.get("FLATPAK_ID"):
            return "Linux Flatpak"
        exe_path = str(sys.executable or "").lower()
        if "windowsapps" in exe_path:
            return "Microsoft Store (MSIX)"
        if sys.platform == "win32":
            if getattr(sys, "frozen", False):
                return "Windows Installer / Portable (.exe)"
            return "Windows Desktop"
        if sys.platform == "darwin":
            return "macOS Desktop"
        if Path("/usr/bin/todo-bird").exists() or Path("/opt/todo-bird").exists():
            return "Ubuntu / Debian (.deb)"
        return "Linux Desktop"

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
        severity: str = "Medium",
        description: str = "",
        reproduction_steps: str = "",
        expected_result: str = "",
        actual_result: str = "",
        rating: int = 5,
        feeling: str = "🤩 Loving It!",
        category: str = "Appreciation & Review",
        user_name: str = "",
        user_role: str = "",
        user_country: str = "",
        user_email: str = "",
        install_channel: str = "",
    ) -> Dict[str, Any]:
        issues = self.get_all_issues()
        issue_id = f"FB-{len(issues) + 1:04d}"

        channel = install_channel or self.detect_install_channel()

        issue = {
            "issue_id": issue_id,
            "date": datetime.now().isoformat(),
            "os": sys.platform,
            "version": __version__,
            "install_channel": channel,
            "rating": int(max(1, min(5, int(rating or 5)))),
            "feeling": feeling,
            "category": category,
            "user_name": user_name.strip() or "Anonymous User",
            "user_role": user_role.strip(),
            "user_country": user_country.strip(),
            "user_email": user_email.strip(),
            "title": title,
            "severity": severity,
            "description": description,
            "reproduction_steps": reproduction_steps,
            "expected_result": expected_result,
            "actual_result": actual_result,
            "status": "Submitted",
        }

        issues.append(issue)
        try:
            self.issue_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.issue_file, "w", encoding="utf-8") as f:
                json.dump(issues, f, indent=2)
            logger.info(f"User feedback logged: {issue_id} — {title} ({feeling}, {rating}★)")
        except Exception as e:
            logger.error(f"Failed to save feedback: {e}")

        return issue

    def export_issue_report(self, export_path: Path) -> bool:
        issues = self.get_all_issues()
        try:
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(issues, f, indent=2)
            return True
        except Exception:
            return False

    @classmethod
    def build_github_feedback_url(cls, issue_data: Dict[str, Any]) -> str:
        """
        Builds a pre-filled HTTPS GitHub Issue URL on DUVORIXEN/TodoBird so users
        can submit their rating, feeling, name/country, and feedback directly to
        the developer with 1 click (zero backend server required).
        """
        stars_num = int(issue_data.get("rating", 5) or 5)
        stars_str = "⭐" * stars_num
        feeling = issue_data.get("feeling", "🤩 Loving It!")
        title_raw = issue_data.get("title", "User Feedback")
        user_name = issue_data.get("user_name", "Anonymous User")
        country = issue_data.get("user_country", "")
        loc_suffix = f" ({country})" if country else ""

        gh_title = f"[Feedback {stars_num}/5★ • {feeling}] {title_raw} — {user_name}{loc_suffix}"

        body_lines = [
            f"### 🐦 Todo Bird Community Feedback & User Check-In",
            "",
            "| Field | Details |",
            "| :--- | :--- |",
            f"| **Overall Rating** | {stars_str} (**{stars_num} / 5**) |",
            f"| **How I Feel** | **{feeling}** |",
            f"| **Category** | {issue_data.get('category', 'General Feedback')} |",
            f"| **User / Handle** | {user_name} |",
            f"| **Role / Profession** | {issue_data.get('user_role') or 'Not specified'} |",
            f"| **Country / Region** | {country or 'Not specified'} |",
            f"| **Downloaded From** | {issue_data.get('install_channel', cls.detect_install_channel())} |",
            f"| **App Version & OS** | `v{issue_data.get('version', __version__)}` on `{issue_data.get('os', sys.platform)}` |",
            f"| **Priority / Severity** | {issue_data.get('severity', 'Medium')} |",
            "",
            "---",
            "### 💬 Detailed Feedback / Message",
            issue_data.get("description") or "_No additional message provided._",
        ]
        if issue_data.get("user_email"):
            body_lines.extend(["", f"**Contact (Optional):** `{issue_data['user_email']}`"])

        body_str = "\n".join(body_lines)
        params = urllib.parse.urlencode({
            "title": gh_title,
            "body": body_str,
            "labels": "user-feedback",
        })
        return f"https://github.com/{cls.GITHUB_REPO}/issues/new?{params}"

    @classmethod
    def send_webhook_payload(cls, webhook_url: str, issue_data: Dict[str, Any], timeout: float = 5.0) -> Tuple[bool, str]:
        """
        Sends the feedback & user check-in payload directly via HTTPS POST to a
        configured Webhook URL (supports Discord, Slack, Formspree, Google Apps Script,
        or custom REST API endpoints).
        """
        url = str(webhook_url or "").strip()
        if not url.startswith("https://"):
            return False, "Webhook URL must start with https://"

        stars_num = int(issue_data.get("rating", 5) or 5)
        summary_text = (
            f"🐦 **New Todo Bird User Feedback ({stars_num}/5 ⭐ — {issue_data.get('feeling', '')})**\n"
            f"• **User:** {issue_data.get('user_name', 'Anonymous')} "
            f"({issue_data.get('user_role') or 'User'}, {issue_data.get('user_country') or 'Global'})\n"
            f"• **Channel:** {issue_data.get('install_channel', '')} (`v{issue_data.get('version', __version__)}` / `{issue_data.get('os', '')}`)\n"
            f"• **Title:** {issue_data.get('title', '')}\n"
            f"• **Message:** {issue_data.get('description', '')}"
        )

        # Compatible with Discord ('content'), Slack ('text'), and generic REST/Formspree JSON
        payload = {
            "content": summary_text,
            "text": summary_text,
            "feedback": issue_data,
        }

        try:
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data_bytes,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": f"TodoBird-Desktop/{__version__}",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status_code = getattr(resp, "status", 200)
                if 200 <= status_code < 300:
                    return True, f"Delivered to webhook (HTTP {status_code})"
                return False, f"Webhook returned HTTP {status_code}"
        except Exception as e:
            return False, str(e)

    @classmethod
    def fetch_github_release_downloads(cls, timeout: float = 5.0) -> Dict[str, Any]:
        """
        Queries the public GitHub Releases API for DUVORIXEN/TodoBird to retrieve
        live download counts across all releases and assets (MSIX, Setup.exe, etc.).
        """
        api_url = f"https://api.github.com/repos/{cls.GITHUB_REPO}/releases"
        try:
            req = urllib.request.Request(
                api_url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": f"TodoBird-Desktop/{__version__}",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                releases = json.loads(resp.read().decode("utf-8"))

            total_downloads = 0
            assets_breakdown = []
            latest_tag = "v1.0.1"
            if isinstance(releases, list):
                for rel in releases:
                    tag = rel.get("tag_name", "")
                    if tag and latest_tag == "v1.0.1":
                        latest_tag = tag
                    for asset in rel.get("assets", []):
                        dl = int(asset.get("download_count", 0) or 0)
                        total_downloads += dl
                        assets_breakdown.append({
                            "name": asset.get("name", ""),
                            "downloads": dl,
                            "size_mb": round(int(asset.get("size", 0) or 0) / (1024 * 1024), 1),
                            "updated_at": str(asset.get("updated_at", ""))[:10],
                        })

            return {
                "ok": True,
                "latest_tag": latest_tag,
                "total_downloads": total_downloads,
                "assets": assets_breakdown,
            }
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "latest_tag": f"v{__version__}",
                "total_downloads": 0,
                "assets": [],
            }
