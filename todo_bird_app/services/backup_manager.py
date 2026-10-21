import os
import sys
import shutil
import sqlite3
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Tuple

from todo_bird_app.services.path_resolver import PathResolver
from todo_bird_app.__version__ import __version__

logger = logging.getLogger(__name__)

class BackupManager:
    """
    Database Backup, Restore & Portable Cross-Platform Migration Manager.
    Supports:
      - Timestamped SQLite database backups
      - PRAGMA quick_check database integrity verification before restore
      - Backup retention policy (keeps last 10 backups)
      - Portable JSON archive Export/Import for migrating between Ubuntu 24.04 and Windows 11
    """
    def __init__(self, db_manager):
        self.db_manager = db_manager

    def create_automatic_backup(self) -> Path:
        """
        Creates an automatic timestamped backup in the user data backups directory.
        """
        return self.create_backup()

    def create_backup(self, backup_name: str = None) -> Path:
        backups_dir = PathResolver.get_backups_dir()
        if not backup_name:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"todo_bird_backup_{ts}.db"

        backup_file = backups_dir / backup_name
        src_db = Path(self.db_manager.db_path)

        if not src_db.exists():
            raise FileNotFoundError(f"Source database file not found: {src_db}")

        # Ensure WAL checkpoint before copy
        with self.db_manager.get_connection() as conn:
            conn.execute("PRAGMA wal_checkpoint(FULL);")

        shutil.copy2(src_db, backup_file)
        logger.info(f"Database backup created successfully: {backup_file}")
        self._enforce_retention_policy(backups_dir, max_backups=10)
        return backup_file

    @staticmethod
    def verify_database_integrity(db_file: Path) -> Tuple[bool, str]:
        """
        Executes PRAGMA quick_check to verify SQLite database integrity.
        """
        if not db_file.exists():
            return False, "File does not exist"

        try:
            conn = sqlite3.connect(str(db_file))
            cursor = conn.cursor()
            cursor.execute("PRAGMA quick_check;")
            row = cursor.fetchone()
            conn.close()
            if row and row[0] == "ok":
                return True, "Database integrity OK"
            return False, f"Integrity check failed: {row[0] if row else 'Unknown error'}"
        except Exception as e:
            return False, f"Database corruption error: {e}"

    def restore_database(self, backup_file: Path) -> bool:
        """
        Restores database from backup file after verifying integrity.
        """
        is_valid, msg = self.verify_database_integrity(backup_file)
        if not is_valid:
            logger.error(f"Cannot restore invalid backup: {msg}")
            return False

        # Create emergency safety backup before replacing
        self.create_backup("safety_pre_restore_backup.db")

        # Close active connection
        self.db_manager.close()
        dest_db = Path(self.db_manager.db_path)
        shutil.copy2(backup_file, dest_db)
        logger.info(f"Database restored successfully from: {backup_file}")
        return True

    def export_portable_archive(self, export_file_path: Path) -> bool:
        """
        Exports all tasks, projects, and settings into a portable cross-platform JSON archive file.
        """
        tasks = self.db_manager.get_all_tasks()
        projects = self.db_manager.get_all_projects()

        archive_data = {
            "version": __version__,
            "exported_at": datetime.now().isoformat(),
            "platform": sys.platform,
            "tasks": tasks,
            "projects": projects,
        }

        try:
            with open(export_file_path, "w", encoding="utf-8") as f:
                json.dump(archive_data, f, indent=2)
            logger.info(f"Exported portable pilot archive to: {export_file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to export portable archive: {e}")
            return False

    def import_portable_archive(self, import_file_path: Path) -> bool:
        """
        Imports tasks and projects from a portable cross-platform JSON archive file.
        """
        if not import_file_path.exists():
            return False

        try:
            with open(import_file_path, "r", encoding="utf-8") as f:
                archive_data = json.load(f)

            tasks = archive_data.get("tasks", [])
            projects = archive_data.get("projects", [])

            # Import Projects
            for p in projects:
                existing = self.db_manager.get_all_projects()
                if not any(x["name"] == p["name"] for x in existing):
                    self.db_manager.insert_project(p)

            # Import Tasks
            for t in tasks:
                t.pop("id", None)  # Generate new ID
                self.db_manager.insert_task(t)

            logger.info(f"Imported {len(tasks)} tasks and {len(projects)} projects from portable archive.")
            return True
        except Exception as e:
            logger.error(f"Failed to import portable archive: {e}")
            return False

    @staticmethod
    def _enforce_retention_policy(backups_dir: Path, max_backups: int = 10):
        backups = sorted(backups_dir.glob("todo_bird_backup_*.db"), key=os.path.getmtime)
        while len(backups) > max_backups:
            oldest = backups.pop(0)
            try:
                oldest.unlink()
                logger.info(f"Pruned old backup per retention policy: {oldest}")
            except Exception:
                pass
