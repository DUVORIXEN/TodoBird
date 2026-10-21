"""
TODO BIRD — Storage Migration Service
Manages one-time, idempotent, safe migration from development/legacy storage to OS user-data storage.

Rules:
1. ONLY executes in PACKAGED_INSTALLED mode.
2. If target already exists, NEVER overwrites it (target is the authority).
3. Verifies source database integrity (PRAGMA quick_check) before migration.
4. Uses SQLite backup API into a temporary file to prevent partial/interrupted state.
5. Verifies target database integrity before atomic rename.
6. Never automatically deletes the legacy source database.
7. Coherently migrates both database and config.json.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

from todo_bird_app.services.runtime_environment import RuntimeEnvironment
from todo_bird_app.services.path_resolver import PathResolver

logger = logging.getLogger(__name__)


class StorageMigrationService:
    """Canonical service for one-time safe storage migration."""

    @classmethod
    def verify_sqlite_integrity(cls, db_path: Path) -> Tuple[bool, str]:
        """Runs PRAGMA quick_check to ensure SQLite file integrity."""
        if not db_path.exists():
            return False, "File does not exist"
        if db_path.stat().st_size == 0:
            return False, "File is zero bytes"

        try:
            conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute("PRAGMA quick_check;")
            row = cursor.fetchone()
            conn.close()
            if row and row[0] == "ok":
                return True, "Database integrity OK"
            return False, f"Integrity check failed: {row[0] if row else 'empty result'}"
        except Exception as exc:
            return False, f"Cannot open SQLite file: {exc}"

    @classmethod
    def migrate_database_file(
        cls,
        source_path: Path,
        target_path: Path,
    ) -> Dict[str, Any]:
        """
        Safely copies source SQLite database to target_path using SQLite backup API.
        Never overwrites existing target.
        Verifies both source and target integrity.
        """
        if target_path.exists():
            return {"status": "skipped", "reason": "target_exists", "path": str(target_path)}

        if not source_path.exists() or source_path.stat().st_size == 0:
            return {"status": "skipped", "reason": "source_missing_or_empty", "path": str(source_path)}

        # 1. Verify source integrity
        valid_src, msg_src = cls.verify_sqlite_integrity(source_path)
        if not valid_src:
            logger.warning("Source database at %s failed integrity check: %s. Aborting migration.", source_path, msg_src)
            return {"status": "rejected", "reason": f"source_corrupt: {msg_src}"}

        # 2. Create target directory
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_target = target_path.with_suffix(".tmp_migrating")
        if temp_target.exists():
            try:
                temp_target.unlink()
            except OSError:
                pass

        # 3. Perform SQLite-safe backup
        try:
            src_uri = f"file:{source_path.resolve()}?mode=ro"
            src_conn = sqlite3.connect(src_uri, uri=True)
            dst_conn = sqlite3.connect(str(temp_target))
            try:
                src_conn.backup(dst_conn)
            finally:
                dst_conn.close()
                src_conn.close()
        except Exception as exc:
            if temp_target.exists():
                try:
                    temp_target.unlink()
                except OSError:
                    pass
            logger.error("Database migration copy failed: %s", exc)
            return {"status": "rejected", "reason": f"copy_failed: {exc}"}

        # 4. Verify target integrity
        valid_dst, msg_dst = cls.verify_sqlite_integrity(temp_target)
        if not valid_dst:
            if temp_target.exists():
                try:
                    temp_target.unlink()
                except OSError:
                    pass
            logger.error("Migrated target database failed integrity check: %s. Aborting.", msg_dst)
            return {"status": "rejected", "reason": f"target_integrity_failed: {msg_dst}"}

        # 5. Atomically promote target
        temp_target.replace(target_path)
        logger.info("Successfully migrated database from %s to %s", source_path, target_path)
        return {"status": "migrated", "source": str(source_path), "target": str(target_path)}

    @classmethod
    def migrate_config_file(
        cls,
        source_config: Path,
        target_config: Path,
    ) -> Dict[str, Any]:
        """
        Safely copies JSON configuration file to target_config.
        Never overwrites existing target.
        """
        if target_config.exists():
            return {"status": "skipped", "reason": "target_exists", "path": str(target_config)}

        if not source_config.exists() or source_config.stat().st_size == 0:
            return {"status": "skipped", "reason": "source_missing", "path": str(source_config)}

        try:
            with open(source_config, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {"status": "rejected", "reason": "invalid_json_structure"}
        except Exception as exc:
            return {"status": "rejected", "reason": f"invalid_json: {exc}"}

        target_config.parent.mkdir(parents=True, exist_ok=True)
        temp_config = target_config.with_suffix(".tmp_migrating")
        try:
            with open(temp_config, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_config.replace(target_config)
            logger.info("Successfully migrated configuration from %s to %s", source_config, target_config)
            return {"status": "migrated", "source": str(source_config), "target": str(target_config)}
        except Exception as exc:
            if temp_config.exists():
                try:
                    temp_config.unlink()
                except OSError:
                    pass
            return {"status": "rejected", "reason": f"config_write_failed: {exc}"}

    @classmethod
    def ensure_user_storage(
        cls,
        paths: Optional[PathResolver] = None,
        runtime: Optional[RuntimeEnvironment] = None,
    ) -> Dict[str, Any]:
        """
        Canonical entry point to ensure user storage is prepared and migrated if necessary.
        Strictly a NO-OP in DEVELOPMENT_SOURCE mode.
        """
        paths = paths or PathResolver()
        runtime = runtime or paths.runtime

        if runtime.is_development():
            logger.debug("Development mode active; skipping user storage migration.")
            return {
                "status": "skipped",
                "reason": "development_mode",
                "db": {"status": "skipped", "reason": "development_mode"},
                "config": {"status": "skipped", "reason": "development_mode"},
            }

        target_db = paths.get_database_path()
        target_config = paths.get_config_dir() / "config.json"

        # 1. Resolve source candidates for database
        source_candidates = [
            paths.get_development_db_path(),
            paths.get_app_data_dir() / "todo_bird_ubuntu_pilot.db",
            paths.get_app_data_dir() / "todo_bird_windows_pilot.db",
            paths.get_app_data_dir() / "todo_bird_macos_pilot.db",
        ]
        source_db: Optional[Path] = None
        for candidate in source_candidates:
            if candidate.exists() and candidate.stat().st_size > 0:
                source_db = candidate
                break

        db_result = {"status": "fresh_install_no_source"}
        if source_db:
            db_result = cls.migrate_database_file(source_db, target_db)
        elif target_db.exists():
            db_result = {"status": "skipped", "reason": "target_exists", "path": str(target_db)}

        # 2. Resolve source for config
        source_config = paths.get_development_config_dir() / "config.json"
        config_result = {"status": "fresh_install_no_source"}
        if source_config.exists():
            config_result = cls.migrate_config_file(source_config, target_config)
        elif target_config.exists():
            config_result = {"status": "skipped", "reason": "target_exists", "path": str(target_config)}

        return {
            "status": "completed",
            "db": db_result,
            "config": config_result,
        }
