import hashlib
import os
import sqlite3
from pathlib import Path
from urllib.parse import quote

import pytest

import todo_bird_app.database as db_mod
from todo_bird_app.database import (
    DatabaseManager,
    ProductionDatabaseAccessError,
    is_production_db_path,
)


PROD_DB_PATH = DatabaseManager.production_db_path()
PROD_HASH_BEFORE = hashlib.sha256(PROD_DB_PATH.read_bytes()).hexdigest()


def _sqlite_uri(path: Path, query: str = "") -> str:
    uri = f"file:{quote(str(path.resolve()), safe='/')}"
    if query:
        uri += f"?{query}"
    return uri


def _hash_prod() -> str:
    return hashlib.sha256(PROD_DB_PATH.read_bytes()).hexdigest()


def _project_count(manager: DatabaseManager) -> int:
    with manager.get_connection() as conn:
        return int(conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0])


def _make_wal_db(path: Path):
    writer = sqlite3.connect(str(path))
    mode = writer.execute("PRAGMA journal_mode=WAL").fetchone()[0].lower()
    assert mode == "wal"
    writer.execute("CREATE TABLE witness (id INTEGER PRIMARY KEY, label TEXT NOT NULL)")
    writer.execute("INSERT INTO witness (label) VALUES ('committed-visible')")
    writer.commit()
    return writer


def test_live_read_only_uses_mode_ro_without_immutable_assumption():
    db = DatabaseManager.read_only(str(PROD_DB_PATH))
    assert db.environment == db_mod.DB_ENV_LIVE_READ_ONLY
    uri = db._build_read_only_uri()
    assert "mode=ro" in uri
    assert "immutable=1" not in uri


def test_wal_committed_data_visible_through_live_read_only(tmp_path):
    wal_db = tmp_path / "wal_visibility.db"
    writer = _make_wal_db(wal_db)
    try:
        assert wal_db.with_suffix(".db-wal").exists()
        db = DatabaseManager.read_only(str(wal_db))
        with db.get_connection() as conn:
            label = conn.execute("SELECT label FROM witness WHERE id = 1").fetchone()[0]
            assert label == "committed-visible"
    finally:
        writer.close()


def test_immutable_snapshot_mode_is_explicit_and_not_for_production(tmp_path):
    snapshot_db = tmp_path / "snapshot.db"
    writer = sqlite3.connect(str(snapshot_db))
    writer.execute("CREATE TABLE witness (label TEXT)")
    writer.execute("INSERT INTO witness (label) VALUES ('frozen-copy')")
    writer.commit()
    writer.close()

    db = DatabaseManager.immutable_snapshot_read_only(str(snapshot_db))
    assert db.environment == db_mod.DB_ENV_IMMUTABLE_SNAPSHOT_READ_ONLY
    assert "immutable=1" in db._build_read_only_uri()
    with db.get_connection() as conn:
        assert conn.execute("SELECT label FROM witness").fetchone()[0] == "frozen-copy"

    with pytest.raises(ProductionDatabaseAccessError):
        DatabaseManager.immutable_snapshot_read_only(str(PROD_DB_PATH))


def test_memory_sqlite_works_under_pytest():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (value TEXT)")
    conn.execute("INSERT INTO t VALUES ('ok')")
    assert conn.execute("SELECT value FROM t").fetchone()[0] == "ok"
    conn.close()


def test_temp_sqlite_db_works_under_pytest(tmp_path):
    temp_db = tmp_path / "plain_temp.db"
    conn = sqlite3.connect(str(temp_db))
    conn.execute("CREATE TABLE t (value TEXT)")
    conn.execute("INSERT INTO t VALUES ('ok')")
    conn.commit()
    conn.close()
    assert temp_db.exists()


def test_unrelated_sqlite_path_works_under_pytest(tmp_path):
    unrelated = tmp_path / "unrelated" / "library-cache.sqlite"
    unrelated.parent.mkdir()
    conn = sqlite3.connect(str(unrelated))
    conn.execute("CREATE TABLE cache (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO cache VALUES ('k', 'v')")
    conn.commit()
    assert conn.execute("SELECT value FROM cache WHERE key = 'k'").fetchone()[0] == "v"
    conn.close()


def test_01_test_db_requires_explicit_temp_path(monkeypatch):
    monkeypatch.delenv("TODO_BIRD_DB", raising=False)
    with pytest.raises(ProductionDatabaseAccessError):
        DatabaseManager()


def test_02_pytest_cannot_writable_open_production_db():
    with pytest.raises(ProductionDatabaseAccessError):
        DatabaseManager(str(PROD_DB_PATH))
    with pytest.raises(ProductionDatabaseAccessError):
        sqlite3.connect(str(PROD_DB_PATH))


def test_03_production_path_normalization_blocks_dot_path():
    dot_path = PROD_DB_PATH.parent / "." / PROD_DB_PATH.name
    assert is_production_db_path(dot_path)
    with pytest.raises(ProductionDatabaseAccessError):
        DatabaseManager.for_test(str(dot_path))


def test_04_symlink_protection_blocks_production_target(tmp_path):
    link_path = tmp_path / "looks_temporary.db"
    link_path.symlink_to(PROD_DB_PATH)
    assert is_production_db_path(link_path)
    with pytest.raises(ProductionDatabaseAccessError):
        DatabaseManager.for_test(str(link_path))


def test_05_relative_path_protection_blocks_production_target():
    rel_path = os.path.relpath(PROD_DB_PATH, Path.cwd())
    assert is_production_db_path(rel_path)
    with pytest.raises(ProductionDatabaseAccessError):
        DatabaseManager.temporary(rel_path)


def test_parent_relative_path_protection_blocks_production_target():
    from_parent = Path("..") / Path.cwd().name / os.path.relpath(PROD_DB_PATH, Path.cwd())
    assert is_production_db_path(from_parent)
    with pytest.raises(ProductionDatabaseAccessError):
        DatabaseManager.for_test(str(from_parent))


def test_06_read_only_production_witness_can_select():
    db = DatabaseManager.read_only(str(PROD_DB_PATH))
    with db.get_connection() as conn:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name LIMIT 1").fetchone()
        assert row is not None


def test_07_read_only_witness_cannot_insert():
    db = DatabaseManager.read_only(str(PROD_DB_PATH))
    with db.get_connection() as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("INSERT INTO settings (key, value) VALUES ('phase2e_ro_insert', 'blocked')")


def test_08_read_only_witness_cannot_update():
    db = DatabaseManager.read_only(str(PROD_DB_PATH))
    with db.get_connection() as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE settings SET value = value WHERE key = 'theme'")


def test_09_read_only_witness_cannot_delete():
    db = DatabaseManager.read_only(str(PROD_DB_PATH))
    with db.get_connection() as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM settings WHERE key = 'phase2e_ro_delete'")


def test_writable_sqlite_uri_production_path_rejected():
    base_uri = _sqlite_uri(PROD_DB_PATH)
    for uri in [
        base_uri,
        _sqlite_uri(PROD_DB_PATH, "mode=rw"),
        _sqlite_uri(PROD_DB_PATH, "mode=rwc"),
        _sqlite_uri(PROD_DB_PATH, "immutable=1"),
    ]:
        with pytest.raises(ProductionDatabaseAccessError):
            sqlite3.connect(uri, uri=True)


def test_production_read_only_sqlite_uri_permitted():
    conn = sqlite3.connect(_sqlite_uri(PROD_DB_PATH, "mode=ro"), uri=True)
    try:
        row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name LIMIT 1").fetchone()
        assert row is not None
    finally:
        conn.close()


def test_10_test_migration_uses_temp_db(tmp_path):
    temp_db = tmp_path / "migration_temp.db"
    db = DatabaseManager.for_test(str(temp_db))
    with db.get_connection() as conn:
        assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == db_mod.CURRENT_SCHEMA_VERSION
    assert _hash_prod() == PROD_HASH_BEFORE


def test_11_production_schema_not_touched_by_tests():
    before = _hash_prod()
    db = DatabaseManager.read_only(str(PROD_DB_PATH))
    with db.get_connection() as conn:
        assert conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0] == db_mod.CURRENT_SCHEMA_VERSION
    assert _hash_prod() == before == PROD_HASH_BEFORE


def test_12_fixture_isolation_with_explicit_temp_paths(tmp_path):
    db_one = DatabaseManager.for_test(str(tmp_path / "one.db"))
    db_two = DatabaseManager.for_test(str(tmp_path / "two.db"))
    db_one.insert_project({"name": "Only One", "color": "#3584E4"})
    names_two = [p["name"] for p in db_two.get_all_projects()]
    assert "Only One" not in names_two


def test_13_concurrent_temp_test_dbs_are_isolated(tmp_path):
    db_one = DatabaseManager.for_test(str(tmp_path / "concurrent_one.db"))
    db_two = DatabaseManager.for_test(str(tmp_path / "concurrent_two.db"))
    before_one = _project_count(db_one)
    before_two = _project_count(db_two)
    db_one.insert_project({"name": "Concurrent One", "color": "#3584E4"})
    db_two.insert_project({"name": "Concurrent Two", "color": "#10B981"})
    assert _project_count(db_one) == before_one + 1
    assert _project_count(db_two) == before_two + 1


def test_14_direct_database_manager_test_fallback_protected(monkeypatch):
    monkeypatch.delenv("TODO_BIRD_DB", raising=False)
    with pytest.raises(ProductionDatabaseAccessError):
        DatabaseManager()


def test_15_explicit_production_runtime_still_works_for_declared_runtime(tmp_path):
    fake_prod = (tmp_path / "declared_runtime.db").resolve()
    db = DatabaseManager.production(str(fake_prod))
    assert db.environment == db_mod.DB_ENV_PRODUCTION
    db.insert_project({"name": "Declared Runtime", "color": "#3584E4"})
    assert _project_count(db) >= 1


def test_application_production_construction_remains_explicit():
    app_source = Path("todo_bird_app/app.py").read_text()
    assert "DatabaseManager.production()" in app_source
    assert "DatabaseManager()" not in app_source


def test_16_production_db_hash_unchanged_after_safety_tests():
    assert _hash_prod() == PROD_HASH_BEFORE
