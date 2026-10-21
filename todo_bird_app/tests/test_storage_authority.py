"""
Test Suite: Storage Authority & Migration Hardening Matrix
Validates the 16-point storage authority and migration contract:
1. Development mode with repo DB present -> uses repo DB
2. Development mode without repo DB -> documented deterministic behavior
3. Packaged Linux fresh install -> uses ~/.local/share/TodoBird/todo_bird.db
4. Packaged Windows fresh install -> uses %LOCALAPPDATA%/TodoBird/todo_bird.db
5. Packaged macOS fresh install -> uses ~/Library/Application Support/TodoBird/todo_bird.db
6. Packaged mode with legacy DB present and no user DB -> migrates once
7. Packaged mode with both legacy DB and user DB -> user DB wins -> legacy DB untouched
8. Corrupt legacy DB -> no unsafe migration
9. Copy interrupted -> no partially accepted target
10. Target integrity failure -> target rejected -> source preserved
11. Config migration -> copies only when target absent
12. Existing user config -> never overwritten
13. Environment override DB -> explicit path wins
14. Environment override config -> explicit path wins
15. App-data-root override -> DB/config/backups/logs consistently under override
16. Development mode remains exactly compatible with current Ubuntu 24 workflow
"""

import os
import sys
import json
import sqlite3
import hashlib
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from todo_bird_app.database import (
    DatabaseManager,
    DEVELOPMENT_DB_PATH,
    LEGACY_REPO_DB_PATH,
    PRODUCTION_DB_PATH,
)
from todo_bird_app.services.runtime_environment import RuntimeEnvironment, RuntimeMode
from todo_bird_app.services.path_resolver import PathResolver
from todo_bird_app.services.storage_migration_service import StorageMigrationService


def _create_sample_sqlite_db(path: Path, table_name: str = "items", value: str = "sample") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute(f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY, name TEXT);")
    conn.execute(f"INSERT INTO {table_name} (name) VALUES (?);", (value,))
    conn.commit()
    conn.close()
    return path


# 1. Development mode with repo DB present -> uses repo DB
def test_01_development_mode_with_repo_db_present(monkeypatch):
    monkeypatch.delenv("TODO_BIRD_DB", raising=False)
    monkeypatch.delenv("TODO_BIRD_CONFIG_DIR", raising=False)
    monkeypatch.delenv("TODO_BIRD_APP_DATA_DIR", raising=False)

    runtime = RuntimeEnvironment(RuntimeMode.DEVELOPMENT_SOURCE)
    paths = PathResolver(runtime)

    assert paths.get_database_path() == DEVELOPMENT_DB_PATH
    assert paths.get_config_dir() == PathResolver._get_repo_root() / "config"
    assert paths.runtime.is_development() is True
    assert paths.runtime.is_packaged() is False


# 2. Development mode without repo DB -> documented deterministic behavior
def test_02_development_mode_without_repo_db_deterministic(monkeypatch):
    monkeypatch.delenv("TODO_BIRD_DB", raising=False)
    monkeypatch.delenv("TODO_BIRD_CONFIG_DIR", raising=False)
    monkeypatch.delenv("TODO_BIRD_APP_DATA_DIR", raising=False)

    runtime = RuntimeEnvironment(RuntimeMode.DEVELOPMENT_SOURCE)
    paths = PathResolver(runtime)

    custom_name = "test_non_existent.db"
    resolved = paths.get_database_path(custom_name)
    assert resolved == PathResolver._get_repo_root() / "data" / custom_name


# 3. Packaged Linux fresh install -> uses ~/.local/share/TodoBird/todo_bird.db
def test_03_packaged_linux_fresh_install(monkeypatch, tmp_path):
    fake_share = tmp_path / "fake_local_share"
    fake_share.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("TODO_BIRD_DB", raising=False)
    monkeypatch.delenv("TODO_BIRD_CONFIG_DIR", raising=False)
    monkeypatch.delenv("TODO_BIRD_APP_DATA_DIR", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(fake_share))

    runtime = RuntimeEnvironment(RuntimeMode.PACKAGED_INSTALLED)
    with patch("sys.platform", "linux"):
        paths = PathResolver(runtime)
        assert paths.get_database_path() == fake_share / "TodoBird" / "todo_bird.db"
        assert paths.get_config_dir() == fake_share / "TodoBird" / "config"


# 4. Packaged Windows fresh install -> uses %LOCALAPPDATA%/TodoBird/todo_bird.db
def test_04_packaged_windows_fresh_install(monkeypatch, tmp_path):
    fake_localappdata = tmp_path / "AppData" / "Local"
    fake_localappdata.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("TODO_BIRD_DB", raising=False)
    monkeypatch.delenv("TODO_BIRD_CONFIG_DIR", raising=False)
    monkeypatch.delenv("TODO_BIRD_APP_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(fake_localappdata))

    runtime = RuntimeEnvironment(RuntimeMode.PACKAGED_INSTALLED)
    with patch("sys.platform", "win32"):
        paths = PathResolver(runtime)
        expected_db = fake_localappdata / "TodoBird" / "todo_bird.db"
        assert str(paths.get_database_path()).replace("\\", "/") == str(expected_db).replace("\\", "/")
        expected_cfg = fake_localappdata / "TodoBird" / "config"
        assert str(paths.get_config_dir()).replace("\\", "/") == str(expected_cfg).replace("\\", "/")


# 5. Packaged macOS fresh install -> uses ~/Library/Application Support/TodoBird/todo_bird.db
def test_05_packaged_macos_fresh_install(monkeypatch):
    monkeypatch.delenv("TODO_BIRD_DB", raising=False)
    monkeypatch.delenv("TODO_BIRD_CONFIG_DIR", raising=False)
    monkeypatch.delenv("TODO_BIRD_APP_DATA_DIR", raising=False)

    runtime = RuntimeEnvironment(RuntimeMode.PACKAGED_INSTALLED)
    with patch("sys.platform", "darwin"):
        paths = PathResolver(runtime)
        expected_db = Path.home() / "Library" / "Application Support" / "TodoBird" / "todo_bird.db"
        assert paths.get_database_path() == expected_db
        expected_cfg = Path.home() / "Library" / "Application Support" / "TodoBird" / "config"
        assert paths.get_config_dir() == expected_cfg


# 6. Packaged mode with legacy DB present and no user DB -> migrates once
def test_06_packaged_mode_with_legacy_db_present_and_no_user_db_migrates_once(tmp_path):
    legacy_db = _create_sample_sqlite_db(tmp_path / "legacy" / "todo_bird.db", value="legacy_record")
    target_db = tmp_path / "user_data" / "todo_bird.db"
    assert not target_db.exists()

    result1 = StorageMigrationService.migrate_database_file(legacy_db, target_db)
    assert result1["status"] == "migrated"
    assert target_db.exists()

    # Verify content in target
    conn = sqlite3.connect(str(target_db))
    val = conn.execute("SELECT name FROM items").fetchone()[0]
    conn.close()
    assert val == "legacy_record"

    # Verify source was not deleted
    assert legacy_db.exists()

    # Second call must be idempotent and not re-copy
    result2 = StorageMigrationService.migrate_database_file(legacy_db, target_db)
    assert result2["status"] == "skipped"
    assert result2["reason"] == "target_exists"


# 7. Packaged mode with both legacy DB and user DB -> user DB wins -> legacy DB untouched
def test_07_packaged_mode_with_both_legacy_and_user_db_user_db_wins(tmp_path):
    legacy_db = _create_sample_sqlite_db(tmp_path / "legacy" / "todo_bird.db", value="legacy_val")
    target_db = _create_sample_sqlite_db(tmp_path / "user_data" / "todo_bird.db", value="user_authority_val")

    legacy_hash_before = hashlib.sha256(legacy_db.read_bytes()).hexdigest()
    target_hash_before = hashlib.sha256(target_db.read_bytes()).hexdigest()

    result = StorageMigrationService.migrate_database_file(legacy_db, target_db)
    assert result["status"] == "skipped"
    assert result["reason"] == "target_exists"

    # Verify target untouched
    assert hashlib.sha256(target_db.read_bytes()).hexdigest() == target_hash_before
    # Verify legacy untouched
    assert hashlib.sha256(legacy_db.read_bytes()).hexdigest() == legacy_hash_before

    conn = sqlite3.connect(str(target_db))
    assert conn.execute("SELECT name FROM items").fetchone()[0] == "user_authority_val"
    conn.close()


# 8. Corrupt legacy DB -> no unsafe migration
def test_08_corrupt_legacy_db_rejected(tmp_path):
    corrupt_db = tmp_path / "legacy" / "corrupt.db"
    corrupt_db.parent.mkdir(parents=True, exist_ok=True)
    corrupt_db.write_bytes(b"This is not a SQLite database file header at all!")

    target_db = tmp_path / "user_data" / "todo_bird.db"

    result = StorageMigrationService.migrate_database_file(corrupt_db, target_db)
    assert result["status"] == "rejected"
    assert "source_corrupt" in result["reason"]
    assert not target_db.exists()


# 9. Copy interrupted -> no partially accepted target
def test_09_copy_interrupted_no_partial_target(tmp_path):
    legacy_db = _create_sample_sqlite_db(tmp_path / "legacy" / "todo_bird.db")
    target_db = tmp_path / "user_data" / "todo_bird.db"

    real_connect = sqlite3.connect

    class FailingBackupConn:
        def __init__(self, real):
            self._real = real

        def backup(self, dst):
            raise OSError("Simulated crash/interruption during SQLite backup")

        def __getattr__(self, name):
            return getattr(self._real, name)

    def fake_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        return FailingBackupConn(conn)

    with patch("sqlite3.connect", side_effect=fake_connect):
        result = StorageMigrationService.migrate_database_file(legacy_db, target_db)
        assert result["status"] == "rejected"
        assert "copy_failed" in result["reason"]
        assert not target_db.exists()
        assert not target_db.with_suffix(".tmp_migrating").exists()


# 10. Target integrity failure -> target rejected -> source preserved
def test_10_target_integrity_failure_rejected(tmp_path):
    legacy_db = _create_sample_sqlite_db(tmp_path / "legacy" / "todo_bird.db")
    target_db = tmp_path / "user_data" / "todo_bird.db"

    original_verify = StorageMigrationService.verify_sqlite_integrity

    def mock_verify(path: Path):
        # Allow source to pass, but fail target
        if "tmp_migrating" in str(path):
            return False, "Simulated post-copy corrupt target block"
        return original_verify(path)

    with patch.object(StorageMigrationService, "verify_sqlite_integrity", side_effect=mock_verify):
        result = StorageMigrationService.migrate_database_file(legacy_db, target_db)
        assert result["status"] == "rejected"
        assert "target_integrity_failed" in result["reason"]
        assert not target_db.exists()
        assert not target_db.with_suffix(".tmp_migrating").exists()
        assert legacy_db.exists()


# 11. Config migration -> copies only when target absent
def test_11_config_migration_copies_only_when_target_absent(tmp_path):
    legacy_cfg = tmp_path / "legacy_config" / "config.json"
    legacy_cfg.parent.mkdir(parents=True, exist_ok=True)
    legacy_cfg.write_text(json.dumps({"theme": "dark", "accent_color": "#2563EB"}), encoding="utf-8")

    target_cfg = tmp_path / "user_config" / "config.json"
    assert not target_cfg.exists()

    result = StorageMigrationService.migrate_config_file(legacy_cfg, target_cfg)
    assert result["status"] == "migrated"
    assert target_cfg.exists()

    with open(target_cfg, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["theme"] == "dark"
    assert data["accent_color"] == "#2563EB"


# 12. Existing user config -> never overwritten
def test_12_existing_user_config_never_overwritten(tmp_path):
    legacy_cfg = tmp_path / "legacy_config" / "config.json"
    legacy_cfg.parent.mkdir(parents=True, exist_ok=True)
    legacy_cfg.write_text(json.dumps({"theme": "light"}), encoding="utf-8")

    target_cfg = tmp_path / "user_config" / "config.json"
    target_cfg.parent.mkdir(parents=True, exist_ok=True)
    target_cfg.write_text(json.dumps({"theme": "dark_custom"}), encoding="utf-8")

    result = StorageMigrationService.migrate_config_file(legacy_cfg, target_cfg)
    assert result["status"] == "skipped"
    assert result["reason"] == "target_exists"

    with open(target_cfg, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["theme"] == "dark_custom"


# 13. Environment override DB -> explicit path wins
def test_13_environment_override_db_explicit_path_wins(monkeypatch, tmp_path):
    explicit_db = tmp_path / "custom_override.db"
    monkeypatch.setenv("TODO_BIRD_DB", str(explicit_db))

    for mode in [RuntimeMode.DEVELOPMENT_SOURCE, RuntimeMode.PACKAGED_INSTALLED]:
        runtime = RuntimeEnvironment(mode)
        paths = PathResolver(runtime)
        assert paths.get_database_path() == explicit_db.resolve()


# 14. Environment override config -> explicit path wins
def test_14_environment_override_config_explicit_path_wins(monkeypatch, tmp_path):
    explicit_cfg = tmp_path / "custom_config_dir"
    monkeypatch.setenv("TODO_BIRD_CONFIG_DIR", str(explicit_cfg))

    for mode in [RuntimeMode.DEVELOPMENT_SOURCE, RuntimeMode.PACKAGED_INSTALLED]:
        runtime = RuntimeEnvironment(mode)
        paths = PathResolver(runtime)
        assert paths.get_config_dir() == explicit_cfg.resolve()


# 15. App-data-root override -> DB/config/backups/logs consistently under override
def test_15_app_data_root_override_consistent(monkeypatch, tmp_path):
    override_root = tmp_path / "custom_app_data_root"
    monkeypatch.delenv("TODO_BIRD_DB", raising=False)
    monkeypatch.delenv("TODO_BIRD_CONFIG_DIR", raising=False)
    monkeypatch.setenv("TODO_BIRD_APP_DATA_DIR", str(override_root))

    runtime = RuntimeEnvironment(RuntimeMode.PACKAGED_INSTALLED)
    paths = PathResolver(runtime)

    assert paths.get_app_data_dir() == override_root.resolve()
    assert paths.get_database_path() == override_root.resolve() / "todo_bird.db"
    assert paths.get_config_dir() == override_root.resolve() / "config"
    assert paths.get_backups_dir() == override_root.resolve() / "backups"
    assert paths.get_logs_dir() == override_root.resolve() / "logs"
    assert paths.get_exports_dir() == override_root.resolve() / "exports"
    assert paths.get_media_dir() == override_root.resolve() / "media"


# 16. Development mode remains exactly compatible with current Ubuntu 24 workflow
def test_16_development_mode_remains_compatible(monkeypatch):
    monkeypatch.delenv("TODO_BIRD_DB", raising=False)
    monkeypatch.delenv("TODO_BIRD_CONFIG_DIR", raising=False)
    monkeypatch.delenv("TODO_BIRD_APP_DATA_DIR", raising=False)
    monkeypatch.delenv("TODO_BIRD_RUNTIME_MODE", raising=False)
    monkeypatch.delenv("TODO_BIRD_PACKAGED", raising=False)

    runtime = RuntimeEnvironment.current()
    assert runtime.is_development() is True
    assert runtime.is_packaged() is False

    paths = PathResolver(runtime)
    assert paths.get_database_path() == DEVELOPMENT_DB_PATH
    assert paths.get_config_dir() == PathResolver._get_repo_root() / "config"

    # Migration must be completely skipped in development mode
    migration_result = StorageMigrationService.ensure_user_storage(paths=paths, runtime=runtime)
    assert migration_result["status"] == "skipped"
    assert migration_result["reason"] == "development_mode"
