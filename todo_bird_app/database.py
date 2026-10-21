import sqlite3
import os
import json
import logging
import shutil
import sys
from typing import List, Optional, Dict, Any
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 16

DEVELOPMENT_DB_PATH = (Path(__file__).resolve().parent / "data" / "todo_bird.db").resolve()
LEGACY_REPO_DB_PATH = DEVELOPMENT_DB_PATH
PRODUCTION_DB_PATH = DEVELOPMENT_DB_PATH
PRODUCTION_CONFIG_PATH = (Path(__file__).resolve().parent / "config" / "config.json").resolve()
DB_ENV_PRODUCTION = "production"
DB_ENV_TEST = "test"
DB_ENV_TEMPORARY = "temporary"
DB_ENV_READ_ONLY = "read_only"
DB_ENV_LIVE_READ_ONLY = "live_read_only"
DB_ENV_IMMUTABLE_SNAPSHOT_READ_ONLY = "immutable_snapshot_read_only"
_DB_ENVIRONMENTS = {
    DB_ENV_PRODUCTION,
    DB_ENV_TEST,
    DB_ENV_TEMPORARY,
    DB_ENV_READ_ONLY,
    DB_ENV_LIVE_READ_ONLY,
    DB_ENV_IMMUTABLE_SNAPSHOT_READ_ONLY,
}


class ProductionDatabaseAccessError(RuntimeError):
    """Raised when an unsafe writable production DB access is attempted."""


class ScheduleVersionGovernanceError(RuntimeError):
    """Raised when a schedule-version operation violates history governance."""


class ScheduleVersionImmutabilityError(ScheduleVersionGovernanceError):
    """Raised when code attempts to mutate an approved schedule snapshot."""


from todo_bird_app.services.execution_performance_service import (
    ExecutionPerformanceService,
    ExecutionStateInvariantError,
)


SCHEDULE_VERSION_ORIGINAL_BASELINE = "original_baseline"
SCHEDULE_VERSION_APPROVED_REVISION = "approved_revision"
_SCHEDULE_VERSION_TYPES = {
    SCHEDULE_VERSION_ORIGINAL_BASELINE,
    SCHEDULE_VERSION_APPROVED_REVISION,
}
_SCHEDULE_VERSION_ENTITY_TYPES = {"task", "subtask"}
_BASELINE_COLUMNS = (
    "baseline_start",
    "baseline_finish",
    "baseline_duration_minutes",
    "baseline_planned_effort_minutes",
)


def canonicalize_db_path(db_path: Any) -> Optional[Path]:
    if db_path is None:
        return None
    path_text = os.fspath(db_path)
    if path_text == ":memory:":
        return None
    if path_text.startswith("file:"):
        parsed = urlparse(path_text)
        if parsed.scheme != "file" or not parsed.path:
            return None
        path_text = unquote(parsed.path)
    return Path(path_text).expanduser().resolve(strict=False)


def is_production_db_path(db_path: Any) -> bool:
    resolved = canonicalize_db_path(db_path)
    return resolved is not None and resolved == PRODUCTION_DB_PATH


def is_pytest_running() -> bool:
    return (
        "PYTEST_CURRENT_TEST" in os.environ
        or "PYTEST_VERSION" in os.environ
        or "pytest" in sys.modules
    )

class DatabaseManager:
    """
    SQLite Database Manager for TODO BIRD.
    Ensures 100% offline local storage with migration support and WAL mode.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        *,
        environment: Optional[str] = None,
        read_only: bool = False,
        immutable_snapshot: bool = False,
        allow_production_write: bool = False,
    ):
        source = "argument"
        if db_path is None:
            env_db_path = os.environ.get("TODO_BIRD_DB", None)
            if env_db_path:
                db_path = env_db_path
                source = "environment"
            else:
                db_path = str(PRODUCTION_DB_PATH)
                source = "default_production"

        self.db_path = os.fspath(db_path)
        self.resolved_db_path = canonicalize_db_path(self.db_path)
        self.is_production_db = is_production_db_path(self.db_path)
        self.environment = self._resolve_environment(
            environment=environment,
            read_only=read_only,
            immutable_snapshot=immutable_snapshot,
            source=source,
        )
        self.immutable_snapshot = (
            immutable_snapshot
            or self.environment == DB_ENV_IMMUTABLE_SNAPSHOT_READ_ONLY
        )
        self.read_only = read_only or self.environment in {
            DB_ENV_READ_ONLY,
            DB_ENV_LIVE_READ_ONLY,
            DB_ENV_IMMUTABLE_SNAPSHOT_READ_ONLY,
        }
        self._allow_production_write = (
            bool(allow_production_write)
            or os.environ.get("TODO_BIRD_ALLOW_PRODUCTION_WRITE") == "1"
        )
        self._pre_migration_backup_created = False
        self._enforce_environment_policy(source)
        self._conn = None
        if not self.read_only:
            self._init_db()

    @classmethod
    def production(cls, db_path: Optional[str] = None) -> "DatabaseManager":
        if db_path is None:
            from todo_bird_app.services.path_resolver import PathResolver
            db_path = str(PathResolver.get_database_path())
        return cls(
            db_path,
            environment=DB_ENV_PRODUCTION,
            allow_production_write=True,
        )

    @classmethod
    def for_test(cls, db_path: str) -> "DatabaseManager":
        if not db_path:
            raise ValueError("Test database path is required.")
        return cls(db_path, environment=DB_ENV_TEST)

    @classmethod
    def temporary(cls, db_path: str) -> "DatabaseManager":
        if not db_path:
            raise ValueError("Temporary database path is required.")
        return cls(db_path, environment=DB_ENV_TEMPORARY)

    @classmethod
    def read_only(cls, db_path: str) -> "DatabaseManager":
        if not db_path:
            raise ValueError("Read-only database path is required.")
        return cls(db_path, environment=DB_ENV_LIVE_READ_ONLY, read_only=True)

    @classmethod
    def immutable_snapshot_read_only(cls, db_path: str) -> "DatabaseManager":
        if not db_path:
            raise ValueError("Immutable snapshot database path is required.")
        return cls(
            db_path,
            environment=DB_ENV_IMMUTABLE_SNAPSHOT_READ_ONLY,
            read_only=True,
            immutable_snapshot=True,
        )

    @staticmethod
    def production_db_path() -> Path:
        return PRODUCTION_DB_PATH

    def _resolve_environment(
        self,
        *,
        environment: Optional[str],
        read_only: bool,
        immutable_snapshot: bool,
        source: str,
    ) -> str:
        if environment is not None:
            env = str(environment).strip().lower()
            if env not in _DB_ENVIRONMENTS:
                raise ValueError(f"Unsupported database environment: {environment}")
            return env
        if immutable_snapshot:
            return DB_ENV_IMMUTABLE_SNAPSHOT_READ_ONLY
        if read_only:
            return DB_ENV_LIVE_READ_ONLY
        if self.is_production_db:
            return DB_ENV_PRODUCTION
        if is_pytest_running():
            return DB_ENV_TEST
        if source in {"argument", "environment"}:
            return DB_ENV_TEMPORARY
        return DB_ENV_PRODUCTION

    def _enforce_environment_policy(self, source: str) -> None:
        if self.read_only:
            if self.immutable_snapshot and self.is_production_db:
                raise ProductionDatabaseAccessError(
                    "Immutable snapshot read-only mode is blocked for the live production database. "
                    "Use DatabaseManager.read_only(path) for live witnesses or copy the DB first."
                )
            return

        if is_pytest_running() and self.is_production_db:
            raise ProductionDatabaseAccessError(
                "Writable access to the Todo Bird production database is blocked while pytest is running. "
                "Use DatabaseManager.for_test(temp_path) or DatabaseManager.read_only(path)."
            )

        if self.is_production_db and (
            self.environment != DB_ENV_PRODUCTION
            or source == "default_production"
            or not self._allow_production_write
        ):
            raise ProductionDatabaseAccessError(
                "Writable production DB access must be explicit. "
                "Use DatabaseManager.production() only from production runtime, "
                "or pass a temporary/test DB path."
            )

    def _build_read_only_uri(self) -> str:
        if self.resolved_db_path is None:
            raise ValueError("Read-only database requires a filesystem path.")
        uri_path = quote(str(self.resolved_db_path), safe="/")
        uri = f"file:{uri_path}?mode=ro"
        if self.immutable_snapshot:
            uri += "&immutable=1"
        return uri

    def get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            if self.read_only:
                uri = self._build_read_only_uri()
                self._conn = sqlite3.connect(
                    uri,
                    uri=True,
                    check_same_thread=False,
                )
                self._conn.row_factory = sqlite3.Row
                self._conn.execute("PRAGMA foreign_keys = ON;")
                self._conn.execute("PRAGMA query_only = ON;")
                return self._conn

            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.execute("PRAGMA journal_mode = WAL;")
        return self._conn

    def close(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _init_db(self):
        logger.info(f"Initializing database at {self.db_path}")
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Schema version table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Check current version
            cursor.execute("SELECT MAX(version) FROM schema_version;")
            row = cursor.fetchone()
            current_ver = row[0] if row and row[0] is not None else 0

            if (
                self.environment == DB_ENV_PRODUCTION
                and self.is_production_db
                and 0 < current_ver < CURRENT_SCHEMA_VERSION
            ):
                self._create_pre_migration_backup(conn, current_ver)

            if current_ver < 1:
                self._apply_v1_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (1);")

            if current_ver < 2:
                self._apply_v2_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (2);")

            if current_ver < 3:
                self._apply_v3_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (3);")

            if current_ver < 4:
                self._apply_v4_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (4);")

            if current_ver < 5:
                self._apply_v5_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (5);")

            if current_ver < 6:
                self._apply_v6_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (6);")

            if current_ver < 7:
                self._apply_v7_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (7);")

            if current_ver < 8:
                self._apply_v8_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (8);")

            if current_ver < 9:
                self._apply_v9_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (9);")

            if current_ver < 10:
                self._apply_v10_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (10);")

            if current_ver < 11:
                self._apply_v11_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (11);")

            if current_ver < 12:
                self._apply_v12_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (12);")

            if current_ver < 13:
                self._apply_v13_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (13);")

            if current_ver < 14:
                self._apply_v14_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (14);")

            if current_ver < 15:
                self._apply_v15_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (15);")

            if current_ver < 16:
                self._apply_v16_schema(cursor)
                cursor.execute("INSERT INTO schema_version (version) VALUES (16);")

            self._ensure_subtask_workflow_schema(cursor)
            self._ensure_schedule_governance_schema(cursor)
            conn.commit()

    def _create_pre_migration_backup(self, conn: sqlite3.Connection, current_ver: int) -> None:
        if self._pre_migration_backup_created or self.resolved_db_path is None:
            return
        if not self.resolved_db_path.exists():
            return

        backup_dir = self.resolved_db_path.parent / "pre_migration_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = (
            backup_dir
            / f"todo_bird_pre_migration_v{current_ver}_to_v{CURRENT_SCHEMA_VERSION}_{ts}.db"
        )
        conn.execute("PRAGMA wal_checkpoint(FULL);")
        shutil.copy2(self.resolved_db_path, backup_path)
        self._pre_migration_backup_created = True
        logger.info("Pre-migration production database backup created: %s", backup_path)

    def _apply_v1_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 1")

        # Projects Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                color TEXT DEFAULT '#E95420',
                icon TEXT DEFAULT 'folder',
                description TEXT DEFAULT '',
                is_archived INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Insert Default Inbox Project
        cursor.execute("""
            INSERT OR IGNORE INTO projects (id, name, color, icon, description)
            VALUES (1, 'Inbox', '#3584E4', 'inbox', 'Default inbox project');
        """)

        # Tasks Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                project_id INTEGER DEFAULT 1,
                priority TEXT DEFAULT 'Medium',
                tags TEXT DEFAULT '[]',
                category TEXT DEFAULT 'Work',
                description TEXT DEFAULT '',
                planned_date TEXT,
                due_date TEXT,
                planned_start_time TEXT,
                planned_end_time TEXT,
                actual_start_time TEXT,
                actual_end_time TEXT,
                estimated_duration INTEGER DEFAULT 0,
                actual_duration INTEGER DEFAULT 0,
                progress INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                recurring TEXT,
                dependencies TEXT DEFAULT '[]',
                status TEXT DEFAULT 'Inbox',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE SET NULL
            );
        """)

        # Settings Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

    def _apply_v2_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 2: Delay tracking & justification columns")
        new_cols = [
            ("delay_minutes", "INTEGER DEFAULT 0"),
            ("delay_percentage", "REAL DEFAULT 0.0"),
            ("delay_category", "TEXT DEFAULT ''"),
            ("delay_reason", "TEXT DEFAULT ''"),
            ("delay_notes", "TEXT DEFAULT ''"),
            ("delay_recorded_at", "TEXT"),
            ("completion_rating", "INTEGER DEFAULT 5"),
            ("completed_before_plan", "INTEGER DEFAULT 0"),
        ]

        # Check existing columns in tasks
        cursor.execute("PRAGMA table_info(tasks);")
        existing_cols = {row[1] for row in cursor.fetchall()}

        for col_name, col_def in new_cols:
            if col_name not in existing_cols:
                cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_def};")
                logger.info(f"Added column {col_name} to tasks table")

    def _apply_v3_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 3: Performance indexes for 1,000+ to 100,000+ tasks scalability")
        indexes = [
            ("idx_tasks_planned_date", "CREATE INDEX IF NOT EXISTS idx_tasks_planned_date ON tasks(planned_date);"),
            ("idx_tasks_due_date", "CREATE INDEX IF NOT EXISTS idx_tasks_due_date ON tasks(due_date);"),
            ("idx_tasks_status", "CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);"),
            ("idx_tasks_project_id", "CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);"),
            ("idx_tasks_priority", "CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);"),
            ("idx_tasks_created_at", "CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at);"),
            ("idx_tasks_delay_category", "CREATE INDEX IF NOT EXISTS idx_tasks_delay_category ON tasks(delay_category);"),
            ("idx_tasks_planned_status", "CREATE INDEX IF NOT EXISTS idx_tasks_planned_status ON tasks(planned_date, status);"),
            ("idx_tasks_status_planned", "CREATE INDEX IF NOT EXISTS idx_tasks_status_planned ON tasks(status, planned_date);"),
            ("idx_tasks_project_planned", "CREATE INDEX IF NOT EXISTS idx_tasks_project_planned ON tasks(project_id, planned_date);"),
        ]
        for name, sql in indexes:
            cursor.execute(sql)
            logger.info(f"Created performance index: {name}")

    def _apply_v4_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 4: Subtasks & Checklists support")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subtasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                is_completed INTEGER DEFAULT 0,
                position INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_subtasks_task_id ON subtasks(task_id);")

    def _apply_v5_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 5: Optional Gantt visibility per task")

        cursor.execute("PRAGMA table_info(tasks);")
        existing_cols = {row[1] for row in cursor.fetchall()}

        if "show_in_gantt" not in existing_cols:
            cursor.execute(
                "ALTER TABLE tasks ADD COLUMN show_in_gantt INTEGER DEFAULT 0;"
            )
            logger.info("Added show_in_gantt column to tasks table")

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_show_in_gantt "
            "ON tasks(show_in_gantt);"
        )

    def _apply_v6_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 6: Daily startup reminder support")

        cursor.execute("PRAGMA table_info(tasks);")
        existing_cols = {row[1] for row in cursor.fetchall()}

        if "startup_reminder" not in existing_cols:
            cursor.execute(
                "ALTER TABLE tasks ADD COLUMN startup_reminder INTEGER DEFAULT 0;"
            )
            logger.info("Added startup_reminder column to tasks table")

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_startup_reminder "
            "ON tasks(startup_reminder);"
        )

    def _apply_v7_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 7: Recursive subtask hierarchy")

        cursor.execute("PRAGMA table_info(subtasks);")
        existing_cols = {row[1] for row in cursor.fetchall()}

        new_cols = [
            (
                "parent_subtask_id",
                "INTEGER REFERENCES subtasks(id) ON DELETE CASCADE"
            ),
            ("description", "TEXT DEFAULT ''"),
            ("planned_date", "TEXT"),
            ("due_date", "TEXT"),
            ("planned_start_time", "TEXT"),
            ("planned_end_time", "TEXT"),
            ("estimated_duration", "INTEGER DEFAULT 0"),
            ("priority", "TEXT DEFAULT 'Medium'"),
            ("progress", "INTEGER DEFAULT 0"),
            ("show_in_gantt", "INTEGER DEFAULT 0"),
            ("dependencies", "TEXT DEFAULT '[]'"),
            ("icon", "TEXT DEFAULT ''"),
            ("image_path", "TEXT DEFAULT ''"),
        ]

        for col_name, col_def in new_cols:
            if col_name not in existing_cols:
                cursor.execute(
                    f"ALTER TABLE subtasks ADD COLUMN {col_name} {col_def};"
                )
                logger.info(f"Added {col_name} column to subtasks table")

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_subtasks_parent "
            "ON subtasks(parent_subtask_id);"
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_subtasks_task_parent "
            "ON subtasks(task_id, parent_subtask_id, position);"
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_subtasks_show_in_gantt "
            "ON subtasks(show_in_gantt);"
        )

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_subtasks_planned_date "
            "ON subtasks(planned_date);"
        )

    def _apply_v8_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 8: Persistent colored pinning")

        pin_columns = [
            ("is_pinned", "INTEGER DEFAULT 0"),
            ("pin_color", "TEXT DEFAULT '#E95420'"),
            ("pin_position", "INTEGER DEFAULT 0"),
        ]

        # Main tasks
        cursor.execute("PRAGMA table_info(tasks);")
        task_cols = {row[1] for row in cursor.fetchall()}

        for col_name, col_def in pin_columns:
            if col_name not in task_cols:
                cursor.execute(
                    f"ALTER TABLE tasks ADD COLUMN {col_name} {col_def};"
                )
                logger.info(f"Added {col_name} column to tasks table")

        # Recursive subtasks
        cursor.execute("PRAGMA table_info(subtasks);")
        subtask_cols = {row[1] for row in cursor.fetchall()}

        for col_name, col_def in pin_columns:
            if col_name not in subtask_cols:
                cursor.execute(
                    f"ALTER TABLE subtasks ADD COLUMN {col_name} {col_def};"
                )
                logger.info(f"Added {col_name} column to subtasks table")

        # Fast pinned-item lookup and ordered rendering
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_pinned "
            "ON tasks(is_pinned, pin_position);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_subtasks_pinned "
            "ON subtasks(is_pinned, pin_position);"
        )

    def _apply_v9_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 9: Subtask actual execution timing parity")

        actual_columns = [
            ("actual_start_date", "TEXT"),
            ("actual_end_date", "TEXT"),
            ("actual_start_time", "TEXT"),
            ("actual_end_time", "TEXT"),
            ("actual_duration", "INTEGER DEFAULT 0"),
        ]

        # Main tasks (ensure actual_start_date and actual_end_date exist)
        cursor.execute("PRAGMA table_info(tasks);")
        task_cols = {row[1] for row in cursor.fetchall()}
        for col_name, col_def in actual_columns:
            if col_name not in task_cols:
                cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_def};")
                logger.info(f"Added {col_name} column to tasks table")

        # Subtasks
        cursor.execute("PRAGMA table_info(subtasks);")
        subtask_cols = {row[1] for row in cursor.fetchall()}
        for col_name, col_def in actual_columns:
            if col_name not in subtask_cols:
                cursor.execute(f"ALTER TABLE subtasks ADD COLUMN {col_name} {col_def};")
                logger.info(f"Added {col_name} column to subtasks table")

    def _apply_v10_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 10: Planned effort & daily dedication foundation")

        effort_columns = [
            ("planned_effort_minutes", "INTEGER DEFAULT 0"),
            ("daily_dedication_minutes", "INTEGER DEFAULT 0"),
            ("allocation_mode", "TEXT DEFAULT 'fixed_daily'"),
        ]

        # Main tasks
        cursor.execute("PRAGMA table_info(tasks);")
        task_cols = {row[1] for row in cursor.fetchall()}
        for col_name, col_def in effort_columns:
            if col_name not in task_cols:
                cursor.execute(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_def};")
                logger.info(f"Added {col_name} column to tasks table")

        # Subtasks
        cursor.execute("PRAGMA table_info(subtasks);")
        subtask_cols = {row[1] for row in cursor.fetchall()}
        for col_name, col_def in effort_columns:
            if col_name not in subtask_cols:
                cursor.execute(f"ALTER TABLE subtasks ADD COLUMN {col_name} {col_def};")
                logger.info(f"Added {col_name} column to subtasks table")

        # Child allocation table for custom by day and resource leveling
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NULL,
                subtask_id INTEGER NULL,
                resource_id TEXT NULL,
                allocation_date TEXT NOT NULL,
                planned_minutes INTEGER DEFAULT 0,
                actual_minutes INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE,
                FOREIGN KEY (subtask_id) REFERENCES subtasks (id) ON DELETE CASCADE
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_allocations_task ON task_allocations(task_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_allocations_subtask ON task_allocations(subtask_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_allocations_date ON task_allocations(allocation_date);")

    def _apply_v11_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 11: Media assets & 30-day companion greeting planner")

        # 1. Media assets table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS media_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_type TEXT NOT NULL DEFAULT 'task_image',
                relative_path TEXT NOT NULL,
                thumbnail_path TEXT NULL,
                mime_type TEXT NULL,
                width INTEGER DEFAULT 0,
                height INTEGER DEFAULT 0,
                file_size INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_type ON media_assets(asset_type);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_path ON media_assets(relative_path);")

        # 2. Companion greetings table (Day 1 to 30 + date-specific)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS companion_greetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_day INTEGER NULL,
                schedule_date TEXT NULL,
                image_path TEXT DEFAULT '',
                title TEXT DEFAULT '',
                message TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_greetings_cycle_day ON companion_greetings(cycle_day);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_greetings_schedule_date ON companion_greetings(schedule_date);")

        # 3. Ensure image_path column on tasks & subtasks
        cursor.execute("PRAGMA table_info(tasks);")
        task_cols = {row[1] for row in cursor.fetchall()}
        if "image_path" not in task_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN image_path TEXT DEFAULT '';")
            logger.info("Added image_path column to tasks table")

        cursor.execute("PRAGMA table_info(subtasks);")
        subtask_cols = {row[1] for row in cursor.fetchall()}
        if "image_path" not in subtask_cols:
            cursor.execute("ALTER TABLE subtasks ADD COLUMN image_path TEXT DEFAULT '';")
            logger.info("Added image_path column to subtasks table")

        # 4. Seed default 30-day greeting planner rows if table is empty
        cursor.execute("SELECT COUNT(*) FROM companion_greetings;")
        cnt = cursor.fetchone()[0]
        if cnt == 0:
            default_greetings = [
                (1, "Ready to launch your day!", "Focus on one high-impact goal first."),
                (2, "Great morning ahead!", "Consistent small steps create massive progress."),
                (3, "Energized & focused!", "Clear the runway and tackle your priority."),
                (4, "Steady pace wins!", "Quality over quantity today."),
                (5, "Welcome back!", "Review your planned effort and stay aligned."),
                (6, "Weekend or weekday?", "Give your best dedication to what matters."),
                (7, "Week reflection & momentum!", "Celebrate your completed wins."),
                (8, "New cycle, fresh focus!", "Start with clarity and calm confidence."),
                (9, "Momentum in motion!", "Protect your deep focus blocks."),
                (10, "Double-digit milestone!", "You are building unstoppable habits."),
                (11, "Clarity over chaos!", "Check your timeline and prioritize."),
                (12, "Deep work day!", "One focused hour beats five distracted hours."),
                (13, "Thriving & delivering!", "Keep your milestones in sight."),
                (14, "Two weeks of consistency!", "Outstanding dedication."),
                (15, "Mid-cycle strength!", "Halfway through the month with purpose."),
                (16, "Refine & conquer!", "Eliminate friction, focus on results."),
                (17, "Stay in the flow!", "Every completed task brings calm."),
                (18, "Unstoppable drive!", "Execute with precision today."),
                (19, "Calm and capable!", "You have the capacity to handle today."),
                (20, "20 days of progress!", "Excellence is becoming your standard."),
                (21, "Three weeks strong!", "Your focus discipline is paying off."),
                (22, "Climbing higher!", "Stay disciplined with your daily dedication."),
                (23, "Master your craft!", "High focus, low distraction."),
                (24, "Peak execution!", "Make today another milestone day."),
                (25, "Quarter-century mark!", "25 days of purposeful productivity."),
                (26, "Finishing strong!", "Keep the rhythm steady."),
                (27, "Sharp and decisive!", "Close open loops and celebrate wins."),
                (28, "Four weeks mastered!", "Consistency creates champions."),
                (29, "Penultimate day!", "Prepare the runway for the next summit."),
                (30, "Day 30 Master Achievement!", "A full 30 days of excellence. Inspiring work!"),
            ]
            for day_num, title, msg in default_greetings:
                cursor.execute("""
                    INSERT INTO companion_greetings (cycle_day, image_path, title, message, enabled)
                    VALUES (?, '', ?, ?, 1);
                """, (day_num, title, msg))

    def _apply_v12_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 12: Canonical task position / WBS ordering authority")
        cursor.execute("PRAGMA table_info(tasks);")
        task_cols = {row[1] for row in cursor.fetchall()}
        if "position" not in task_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN position INTEGER DEFAULT 0;")
            logger.info("Added position column to tasks table")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_project_pos "
            "ON tasks(project_id, position, id);"
        )

    def _apply_v13_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 13: Task-level startup reminder modes (off, daily_first_open, every_app_open)")
        cursor.execute("PRAGMA table_info(tasks);")
        task_cols = {row[1] for row in cursor.fetchall()}
        if "startup_reminder_mode" not in task_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN startup_reminder_mode TEXT DEFAULT 'off';")
            logger.info("Added startup_reminder_mode column to tasks table")
            # Non-destructive data migration:
            # existing startup_reminder = 1 -> 'daily_first_open', 0 -> 'off'
            cursor.execute("""
                UPDATE tasks SET startup_reminder_mode = CASE
                    WHEN startup_reminder = 1 THEN 'daily_first_open'
                    ELSE 'off'
                END
                WHERE startup_reminder_mode IS NULL OR startup_reminder_mode = '' OR startup_reminder_mode = 'off';
            """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_startup_reminder_mode "
            "ON tasks(startup_reminder_mode);"
        )

    def _apply_v14_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 14: Schedule Baseline 1 (Phase 2D)")
        cursor.execute("PRAGMA table_info(tasks);")
        task_cols = {row[1] for row in cursor.fetchall()}
        if "baseline_start" not in task_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN baseline_start TEXT;")
            logger.info("Added baseline_start column to tasks table")
        if "baseline_finish" not in task_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN baseline_finish TEXT;")
            logger.info("Added baseline_finish column to tasks table")
        if "baseline_duration_minutes" not in task_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN baseline_duration_minutes INTEGER;")
            logger.info("Added baseline_duration_minutes column to tasks table")
        if "baseline_planned_effort_minutes" not in task_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN baseline_planned_effort_minutes INTEGER;")
            logger.info("Added baseline_planned_effort_minutes column to tasks table")
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_project_baseline "
            "ON tasks(project_id, baseline_start);"
        )

        cursor.execute("PRAGMA table_info(projects);")
        proj_cols = {row[1] for row in cursor.fetchall()}
        if "baseline_created_at" not in proj_cols:
            cursor.execute("ALTER TABLE projects ADD COLUMN baseline_created_at TEXT;")
            logger.info("Added baseline_created_at column to projects table")
        if "baseline_name" not in proj_cols:
            cursor.execute("ALTER TABLE projects ADD COLUMN baseline_name TEXT DEFAULT 'Baseline 1';")
            logger.info("Added baseline_name column to projects table")

        cursor.execute("PRAGMA table_info(subtasks);")
        subtask_cols = {row[1] for row in cursor.fetchall()}
        if "baseline_start" not in subtask_cols:
            cursor.execute("ALTER TABLE subtasks ADD COLUMN baseline_start TEXT;")
            logger.info("Added baseline_start column to subtasks table")
        if "baseline_finish" not in subtask_cols:
            cursor.execute("ALTER TABLE subtasks ADD COLUMN baseline_finish TEXT;")
            logger.info("Added baseline_finish column to subtasks table")
        if "baseline_duration_minutes" not in subtask_cols:
            cursor.execute("ALTER TABLE subtasks ADD COLUMN baseline_duration_minutes INTEGER;")
            logger.info("Added baseline_duration_minutes column to subtasks table")
        if "baseline_planned_effort_minutes" not in subtask_cols:
            cursor.execute("ALTER TABLE subtasks ADD COLUMN baseline_planned_effort_minutes INTEGER;")
            logger.info("Added baseline_planned_effort_minutes column to subtasks table")

    def _apply_v15_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 15: Schedule Constraints, Deadlines & Project Calendar (Phase 2E)")
        cursor.execute("PRAGMA table_info(tasks);")
        task_cols = {row[1] for row in cursor.fetchall()}
        if "constraint_type" not in task_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN constraint_type TEXT DEFAULT 'ASAP';")
            logger.info("Added constraint_type column to tasks table")
        if "constraint_datetime" not in task_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN constraint_datetime TEXT;")
            logger.info("Added constraint_datetime column to tasks table")
        if "deadline_datetime" not in task_cols:
            cursor.execute("ALTER TABLE tasks ADD COLUMN deadline_datetime TEXT;")
            logger.info("Added deadline_datetime column to tasks table")

        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_constraint "
            "ON tasks(constraint_type, constraint_datetime);"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_tasks_deadline "
            "ON tasks(deadline_datetime);"
        )

        cursor.execute("PRAGMA table_info(projects);")
        proj_cols = {row[1] for row in cursor.fetchall()}
        if "working_weekdays" not in proj_cols:
            cursor.execute("ALTER TABLE projects ADD COLUMN working_weekdays TEXT;")
            logger.info("Added working_weekdays column to projects table")
        if "calendar_exceptions" not in proj_cols:
            cursor.execute("ALTER TABLE projects ADD COLUMN calendar_exceptions TEXT DEFAULT '[]';")
            logger.info("Added calendar_exceptions column to projects table")

        cursor.execute("PRAGMA table_info(subtasks);")
        subtask_cols = {row[1] for row in cursor.fetchall()}
        if "constraint_type" not in subtask_cols:
            cursor.execute("ALTER TABLE subtasks ADD COLUMN constraint_type TEXT DEFAULT 'ASAP';")
            logger.info("Added constraint_type column to subtasks table")
        if "constraint_datetime" not in subtask_cols:
            cursor.execute("ALTER TABLE subtasks ADD COLUMN constraint_datetime TEXT;")
            logger.info("Added constraint_datetime column to subtasks table")
        if "deadline_datetime" not in subtask_cols:
            cursor.execute("ALTER TABLE subtasks ADD COLUMN deadline_datetime TEXT;")
            logger.info("Added deadline_datetime column to subtasks table")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS project_calendar_exceptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                exception_date TEXT NOT NULL,
                is_working INTEGER NOT NULL DEFAULT 0,
                name TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
            );
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_proj_cal_ex "
            "ON project_calendar_exceptions(project_id, exception_date);"
        )

    def _apply_v16_schema(self, cursor: sqlite3.Cursor):
        logger.info("Applying schema version 16: Schedule Versions & Approved Revisions (Phase 2E)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedule_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                version_type TEXT NOT NULL DEFAULT 'approved_revision',
                created_at TEXT NOT NULL,
                approved_at TEXT,
                notes TEXT,
                is_original_baseline INTEGER NOT NULL DEFAULT 0,
                sequence_order INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY (project_id) REFERENCES projects (id) ON DELETE CASCADE
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedule_version_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version_id INTEGER NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                title TEXT,
                task_id INTEGER,
                parent_subtask_id INTEGER,
                wbs_path TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                start TEXT,
                finish TEXT,
                duration_minutes INTEGER,
                planned_effort_minutes INTEGER,
                FOREIGN KEY (version_id) REFERENCES schedule_versions (id) ON DELETE CASCADE
            );
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_versions_project ON schedule_versions(project_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_version_items_ver ON schedule_version_items(version_id);")

    def _ensure_subtask_workflow_schema(self, cursor: sqlite3.Cursor):
        logger.info("Ensuring subtask status blocker/delay workflow parity")

        cursor.execute("PRAGMA table_info(subtasks);")
        subtask_cols = {row[1] for row in cursor.fetchall()}
        for col_name, col_def in (
            ("status", "TEXT DEFAULT 'Planned'"),
            ("delay_category", "TEXT DEFAULT ''"),
            ("delay_reason", "TEXT DEFAULT ''"),
            ("delay_notes", "TEXT DEFAULT ''"),
            ("delay_recorded_at", "TEXT"),
        ):
            if col_name not in subtask_cols:
                cursor.execute(
                    f"ALTER TABLE subtasks ADD COLUMN {col_name} {col_def};"
                )
                logger.info("Added %s column to subtasks table", col_name)

        cursor.execute("PRAGMA table_info(subtasks);")
        subtask_cols = {row[1] for row in cursor.fetchall()}
        completed_terms = []
        if "is_completed" in subtask_cols:
            completed_terms.append("COALESCE(is_completed, 0) = 1")
        if "progress" in subtask_cols:
            completed_terms.append("COALESCE(progress, 0) >= 100")
        completed_when = " OR ".join(completed_terms)
        if completed_when:
            cursor.execute(
                f"""
                UPDATE subtasks
                SET status = CASE
                    WHEN {completed_when} THEN 'Completed'
                    ELSE 'Planned'
                END
                WHERE status IS NULL OR status = '';
                """
            )
        else:
            cursor.execute(
                """
                UPDATE subtasks
                SET status = 'Planned'
                WHERE status IS NULL OR status = '';
                """
            )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_subtasks_status ON subtasks(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_subtasks_delay_category ON subtasks(delay_category);")

    def _ensure_schedule_governance_schema(self, cursor: sqlite3.Cursor):
        cursor.execute("PRAGMA table_info(schedule_versions);")
        version_cols = {row[1] for row in cursor.fetchall()}
        if not version_cols:
            return

        cursor.execute("PRAGMA table_info(schedule_version_items);")
        item_cols = {row[1] for row in cursor.fetchall()}
        for col_name, col_def in (
            ("title", "TEXT"),
            ("task_id", "INTEGER"),
            ("parent_subtask_id", "INTEGER"),
            ("wbs_path", "TEXT"),
            ("sort_order", "INTEGER NOT NULL DEFAULT 0"),
        ):
            if col_name not in item_cols:
                cursor.execute(f"ALTER TABLE schedule_version_items ADD COLUMN {col_name} {col_def};")
                logger.info("Added %s column to schedule_version_items table", col_name)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_versions_project ON schedule_versions(project_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_versions_project_type ON schedule_versions(project_id, version_type);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_version_items_ver ON schedule_version_items(version_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_schedule_version_items_entity ON schedule_version_items(entity_type, entity_id);")

        for sql, label in (
            (
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ux_schedule_versions_one_original_per_project
                ON schedule_versions(project_id)
                WHERE is_original_baseline = 1 OR version_type = 'original_baseline';
                """,
                "one original baseline per project",
            ),
            (
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ux_schedule_versions_project_sequence
                ON schedule_versions(project_id, sequence_order);
                """,
                "unique schedule version sequence per project",
            ),
            (
                """
                CREATE UNIQUE INDEX IF NOT EXISTS ux_schedule_version_items_entity_per_version
                ON schedule_version_items(version_id, entity_type, entity_id);
                """,
                "unique entity snapshot per version",
            ),
        ):
            try:
                cursor.execute(sql)
            except sqlite3.IntegrityError as exc:
                logger.warning("Skipped schedule governance index (%s): %s", label, exc)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_schedule_versions_no_update
            BEFORE UPDATE ON schedule_versions
            BEGIN
                SELECT RAISE(ABORT, 'schedule_versions are immutable; create a new approved revision');
            END;
        """)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS trg_schedule_version_items_no_update
            BEFORE UPDATE ON schedule_version_items
            BEGIN
                SELECT RAISE(ABORT, 'schedule_version_items are immutable; create a new approved revision');
            END;
        """)

    # -----------------------------
    # Schedule Version Operations
    # -----------------------------
    def _normalize_schedule_version_type(self, version_type: str, is_original_baseline: bool) -> tuple[str, bool]:
        normalized = str(version_type or "").strip().lower()
        if is_original_baseline:
            normalized = SCHEDULE_VERSION_ORIGINAL_BASELINE
        if normalized not in _SCHEDULE_VERSION_TYPES:
            raise ScheduleVersionGovernanceError(
                f"Unsupported schedule version type: {version_type!r}"
            )
        return normalized, normalized == SCHEDULE_VERSION_ORIGINAL_BASELINE

    def _get_original_baseline_row(
        self,
        cursor: sqlite3.Cursor,
        project_id: int,
    ) -> Optional[sqlite3.Row]:
        cursor.execute(
            """
            SELECT *
            FROM schedule_versions
            WHERE project_id = ?
              AND (is_original_baseline = 1 OR version_type = ?)
            ORDER BY sequence_order ASC, id ASC
            LIMIT 1;
            """,
            (project_id, SCHEDULE_VERSION_ORIGINAL_BASELINE),
        )
        return cursor.fetchone()

    def _project_has_legacy_baseline(self, cursor: sqlite3.Cursor, project_id: int) -> bool:
        cursor.execute(
            "SELECT baseline_created_at FROM projects WHERE id = ?;",
            (project_id,),
        )
        project_row = cursor.fetchone()
        if not project_row:
            return False
        if project_row["baseline_created_at"]:
            return True

        task_where, task_params = self._task_project_filter(project_id, table_alias="")
        cursor.execute(
            f"""
            SELECT 1
            FROM tasks
            WHERE {task_where}
              AND (
                baseline_start IS NOT NULL
                OR baseline_finish IS NOT NULL
                OR baseline_duration_minutes IS NOT NULL
                OR baseline_planned_effort_minutes IS NOT NULL
              )
            LIMIT 1;
            """,
            task_params,
        )
        if cursor.fetchone():
            return True

        subtask_where, subtask_params = self._task_project_filter(project_id, table_alias="t")
        cursor.execute(
            f"""
            SELECT 1
            FROM subtasks s
            JOIN tasks t ON t.id = s.task_id
            WHERE {subtask_where}
              AND (
                s.baseline_start IS NOT NULL
                OR s.baseline_finish IS NOT NULL
                OR s.baseline_duration_minutes IS NOT NULL
                OR s.baseline_planned_effort_minutes IS NOT NULL
              )
            LIMIT 1;
            """,
            subtask_params,
        )
        return cursor.fetchone() is not None

    def _task_project_filter(self, project_id: int, table_alias: str = "") -> tuple[str, tuple[Any, ...]]:
        prefix = f"{table_alias}." if table_alias else ""
        if project_id in (1, 0, None):
            return f"({prefix}project_id IS NULL OR {prefix}project_id = 1 OR {prefix}project_id = 0)", ()
        return f"{prefix}project_id = ?", (project_id,)

    def _next_schedule_version_sequence(self, cursor: sqlite3.Cursor, project_id: int) -> int:
        cursor.execute(
            "SELECT COALESCE(MAX(sequence_order), 0) + 1 FROM schedule_versions WHERE project_id = ?;",
            (project_id,),
        )
        row = cursor.fetchone()
        return int(row[0] if row else 1)

    def _normalize_schedule_version_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        entity_type = str(item.get("entity_type") or "task").strip().lower()
        if entity_type not in _SCHEDULE_VERSION_ENTITY_TYPES:
            raise ScheduleVersionGovernanceError(
                f"Unsupported schedule version entity type: {entity_type!r}"
            )
        entity_id = item.get("entity_id")
        if entity_id is None:
            raise ScheduleVersionGovernanceError("Schedule version item requires entity_id.")
        try:
            entity_id = int(entity_id)
        except (TypeError, ValueError) as exc:
            raise ScheduleVersionGovernanceError("Schedule version item entity_id must be an integer.") from exc

        def _optional_int(key: str) -> Optional[int]:
            value = item.get(key)
            if value is None or value == "":
                return None
            return int(value)

        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "title": item.get("title"),
            "task_id": _optional_int("task_id"),
            "parent_subtask_id": _optional_int("parent_subtask_id"),
            "wbs_path": item.get("wbs_path"),
            "sort_order": int(item.get("sort_order") or 0),
            "start": item.get("start"),
            "finish": item.get("finish"),
            "duration_minutes": _optional_int("duration_minutes"),
            "planned_effort_minutes": _optional_int("planned_effort_minutes"),
        }

    def _insert_schedule_version(
        self,
        cursor: sqlite3.Cursor,
        *,
        project_id: int,
        name: str,
        version_type: str,
        created_at: str,
        approved_at: Optional[str],
        notes: Optional[str],
        is_original_baseline: bool,
        sequence_order: Optional[int],
        items: Optional[List[Dict[str, Any]]],
    ) -> int:
        normalized_type, original = self._normalize_schedule_version_type(
            version_type,
            is_original_baseline,
        )
        cursor.execute("SELECT 1 FROM projects WHERE id = ?;", (project_id,))
        if cursor.fetchone() is None:
            raise ScheduleVersionGovernanceError(f"Project {project_id} does not exist.")

        if original:
            existing = self._get_original_baseline_row(cursor, project_id)
            if existing is not None:
                raise ScheduleVersionImmutabilityError(
                    "Original Baseline already exists and cannot be overwritten."
                )
            sequence = 1
        else:
            sequence = sequence_order if sequence_order is not None else self._next_schedule_version_sequence(cursor, project_id)
            if int(sequence) < 1:
                raise ScheduleVersionGovernanceError("Schedule version sequence must be positive.")

        cursor.execute(
            """
            INSERT INTO schedule_versions (
                project_id, name, version_type, created_at, approved_at, notes, is_original_baseline, sequence_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                project_id,
                name,
                normalized_type,
                created_at,
                approved_at,
                notes or "",
                1 if original else 0,
                int(sequence),
            ),
        )
        version_id = int(cursor.lastrowid)

        seen_items: set[tuple[str, int]] = set()
        for raw_item in items or []:
            item = self._normalize_schedule_version_item(raw_item)
            key = (item["entity_type"], item["entity_id"])
            if key in seen_items:
                raise ScheduleVersionGovernanceError(
                    f"Duplicate schedule snapshot item for {key[0]} {key[1]}."
                )
            seen_items.add(key)
            cursor.execute(
                """
                INSERT INTO schedule_version_items (
                    version_id, entity_type, entity_id, title, task_id,
                    parent_subtask_id, wbs_path, sort_order, start, finish,
                    duration_minutes, planned_effort_minutes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    version_id,
                    item["entity_type"],
                    item["entity_id"],
                    item["title"],
                    item["task_id"],
                    item["parent_subtask_id"],
                    item["wbs_path"],
                    item["sort_order"],
                    item["start"],
                    item["finish"],
                    item["duration_minutes"],
                    item["planned_effort_minutes"],
                ),
            )
        return version_id

    def get_schedule_versions_for_project(self, project_id: int) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM schedule_versions WHERE project_id = ? ORDER BY sequence_order ASC, id ASC;",
                (project_id,)
            )
            return [dict(r) for r in cursor.fetchall()]

    def create_schedule_version(
        self,
        project_id: int,
        name: str,
        version_type: str = "approved_revision",
        created_at: Optional[str] = None,
        approved_at: Optional[str] = None,
        notes: Optional[str] = None,
        is_original_baseline: bool = False,
        sequence_order: Optional[int] = None,
        items: Optional[List[Dict[str, Any]]] = None,
    ) -> int:
        from datetime import datetime
        if not created_at:
            created_at = datetime.now().isoformat()

        with self.get_connection() as conn:
            cursor = conn.cursor()
            version_id = self._insert_schedule_version(
                cursor,
                project_id=project_id,
                name=name,
                version_type=version_type,
                created_at=created_at,
                approved_at=approved_at,
                notes=notes,
                is_original_baseline=is_original_baseline,
                sequence_order=sequence_order,
                items=items,
            )
            conn.commit()
            return version_id

    def get_schedule_version_items(self, version_id: int) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM schedule_version_items WHERE version_id = ?;",
                (version_id,)
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_original_schedule_version(self, project_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            row = self._get_original_baseline_row(cursor, project_id)
            return dict(row) if row else None

    def get_latest_approved_revision(self, project_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT *
                FROM schedule_versions
                WHERE project_id = ?
                  AND version_type = ?
                  AND is_original_baseline = 0
                ORDER BY sequence_order DESC, id DESC
                LIMIT 1;
                """,
                (project_id, SCHEDULE_VERSION_APPROVED_REVISION),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def has_original_baseline(self, project_id: int, include_legacy: bool = True) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if self._get_original_baseline_row(cursor, project_id) is not None:
                return True
            return include_legacy and self._project_has_legacy_baseline(cursor, project_id)

    def delete_schedule_version(self, version_id: int, *, confirm_historical_delete: bool = False) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM schedule_versions WHERE id = ?;", (version_id,))
            row = cursor.fetchone()
            if row is None:
                return False
            if row["is_original_baseline"] or row["version_type"] == SCHEDULE_VERSION_ORIGINAL_BASELINE:
                raise ScheduleVersionImmutabilityError(
                    "Original Baseline cannot be deleted through the schedule version API."
                )
            if not confirm_historical_delete:
                raise ScheduleVersionGovernanceError(
                    "Approved revision deletion requires confirm_historical_delete=True."
                )
            cursor.execute("DELETE FROM schedule_versions WHERE id = ?;", (version_id,))
            conn.commit()
            return cursor.rowcount > 0

    # -----------------------------
    # Task Operations
    # -----------------------------
    def insert_task(self, task_dict: Any) -> int:
        if hasattr(task_dict, "to_dict"):
            task_dict = task_dict.to_dict()
        full_dict = {
            "id": None, "title": "", "project_id": None, "priority": "Medium",
            "tags": "[]", "category": "General", "description": "",
            "planned_date": None, "due_date": None, "planned_start_time": None,
            "planned_end_time": None, "actual_start_date": None, "actual_end_date": None,
            "actual_start_time": None, "actual_end_time": None, "estimated_duration": 0,
            "actual_duration": 0, "progress": 0, "notes": "", "recurring": "none",
            "dependencies": "[]", "status": "inbox", "delay_minutes": 0,
            "delay_percentage": 0.0, "delay_category": "none", "delay_reason": "",
            "delay_notes": "", "delay_recorded_at": None, "completion_rating": None,
            "completed_before_plan": 0, "show_in_gantt": 1, "startup_reminder": 0,
            "startup_reminder_mode": "off",
            "is_pinned": 0, "pin_color": "#E95420", "pin_position": 0,
            "position": 0,
            "planned_effort_minutes": 0, "daily_dedication_minutes": 0, "allocation_mode": "fixed_daily",
            "image_path": "",
            "baseline_start": None, "baseline_finish": None,
            "baseline_duration_minutes": None, "baseline_planned_effort_minutes": None,
            "constraint_type": "ASAP", "constraint_datetime": None, "deadline_datetime": None,
        }
        full_dict.update(task_dict)
        ExecutionPerformanceService.assert_valid_execution_state(full_dict)
        explicit_id = full_dict.get("id")
        if explicit_id is not None:
            query = """
                INSERT INTO tasks (
                    id, title, project_id, priority, tags, category, description,
                    planned_date, due_date, planned_start_time, planned_end_time,
                    actual_start_date, actual_end_date, actual_start_time, actual_end_time,
                    estimated_duration, actual_duration, progress, notes, recurring,
                    dependencies, status, delay_minutes, delay_percentage, delay_category,
                    delay_reason, delay_notes, delay_recorded_at, completion_rating,
                    completed_before_plan, show_in_gantt, startup_reminder, startup_reminder_mode,
                    is_pinned, pin_color, pin_position, position,
                    planned_effort_minutes, daily_dedication_minutes, allocation_mode,
                    image_path, baseline_start, baseline_finish,
                    baseline_duration_minutes, baseline_planned_effort_minutes,
                    constraint_type, constraint_datetime, deadline_datetime
                ) VALUES (
                    :id, :title, :project_id, :priority, :tags, :category, :description,
                    :planned_date, :due_date, :planned_start_time, :planned_end_time,
                    :actual_start_date, :actual_end_date, :actual_start_time, :actual_end_time,
                    :estimated_duration, :actual_duration, :progress, :notes, :recurring,
                    :dependencies, :status, :delay_minutes, :delay_percentage, :delay_category,
                    :delay_reason, :delay_notes, :delay_recorded_at, :completion_rating,
                    :completed_before_plan, :show_in_gantt, :startup_reminder, :startup_reminder_mode,
                    :is_pinned, :pin_color, :pin_position, :position,
                    :planned_effort_minutes, :daily_dedication_minutes, :allocation_mode,
                    :image_path, :baseline_start, :baseline_finish,
                    :baseline_duration_minutes, :baseline_planned_effort_minutes,
                    :constraint_type, :constraint_datetime, :deadline_datetime
                );
            """
        else:
            query = """
                INSERT INTO tasks (
                    title, project_id, priority, tags, category, description,
                    planned_date, due_date, planned_start_time, planned_end_time,
                    actual_start_date, actual_end_date, actual_start_time, actual_end_time,
                    estimated_duration, actual_duration, progress, notes, recurring,
                    dependencies, status, delay_minutes, delay_percentage, delay_category,
                    delay_reason, delay_notes, delay_recorded_at, completion_rating,
                    completed_before_plan, show_in_gantt, startup_reminder, startup_reminder_mode,
                    is_pinned, pin_color, pin_position, position,
                    planned_effort_minutes, daily_dedication_minutes, allocation_mode,
                    image_path, baseline_start, baseline_finish,
                    baseline_duration_minutes, baseline_planned_effort_minutes,
                    constraint_type, constraint_datetime, deadline_datetime
                ) VALUES (
                    :title, :project_id, :priority, :tags, :category, :description,
                    :planned_date, :due_date, :planned_start_time, :planned_end_time,
                    :actual_start_date, :actual_end_date, :actual_start_time, :actual_end_time,
                    :estimated_duration, :actual_duration, :progress, :notes, :recurring,
                    :dependencies, :status, :delay_minutes, :delay_percentage, :delay_category,
                    :delay_reason, :delay_notes, :delay_recorded_at, :completion_rating,
                    :completed_before_plan, :show_in_gantt, :startup_reminder, :startup_reminder_mode,
                    :is_pinned, :pin_color, :pin_position, :position,
                    :planned_effort_minutes, :daily_dedication_minutes, :allocation_mode,
                    :image_path, :baseline_start, :baseline_finish,
                    :baseline_duration_minutes, :baseline_planned_effort_minutes,
                    :constraint_type, :constraint_datetime, :deadline_datetime
                );
            """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, full_dict)
            conn.commit()
            return cursor.lastrowid if explicit_id is None else explicit_id

    def update_task(self, task_dict: Any, task_id: Optional[int] = None) -> bool:
        if isinstance(task_dict, int) and task_id is not None:
            the_id = task_dict
            the_dict = task_id
        else:
            the_dict = task_dict
            the_id = task_id

        if hasattr(the_dict, "to_dict"):
            the_dict = the_dict.to_dict()

        if the_id is None and isinstance(the_dict, dict):
            the_id = the_dict.get("id")

        if the_id is None:
            return False

        existing = self.get_task_by_id(the_id)
        if existing and isinstance(the_dict, dict):
            baseline_changes = []
            for col in _BASELINE_COLUMNS:
                if col in the_dict and the_dict.get(col) != existing.get(col):
                    baseline_changes.append(col)
            if baseline_changes:
                project_id = existing.get("project_id")
                if self.has_original_baseline(1 if project_id in (None, 0) else int(project_id)):
                    raise ScheduleVersionImmutabilityError(
                        "Task baseline cache columns cannot be changed after Original Baseline approval. "
                        "Create an Approved Revision instead."
                    )
        if existing:
            full_dict = dict(existing)
        else:
            full_dict = {
                "title": "", "project_id": None, "priority": "Medium",
                "tags": "[]", "category": "General", "description": "",
                "planned_date": None, "due_date": None, "planned_start_time": None,
                "planned_end_time": None, "actual_start_date": None, "actual_end_date": None,
                "actual_start_time": None, "actual_end_time": None, "estimated_duration": 0,
                "actual_duration": 0, "progress": 0, "notes": "", "recurring": "none",
                "dependencies": "[]", "status": "inbox", "delay_minutes": 0,
                "delay_percentage": 0.0, "delay_category": "none", "delay_reason": "",
                "delay_notes": "", "delay_recorded_at": None, "completion_rating": None,
                "completed_before_plan": 0, "show_in_gantt": 1, "startup_reminder": 0,
                "startup_reminder_mode": "off",
                "is_pinned": 0, "pin_color": "#E95420", "pin_position": 0,
                "position": 0,
                "planned_effort_minutes": 0, "daily_dedication_minutes": 0, "allocation_mode": "fixed_daily",
                "image_path": "",
                "baseline_start": None, "baseline_finish": None,
                "baseline_duration_minutes": None, "baseline_planned_effort_minutes": None,
                "constraint_type": "ASAP", "constraint_datetime": None, "deadline_datetime": None,
            }
        full_dict.update(the_dict)
        full_dict["id"] = the_id
        ExecutionPerformanceService.assert_valid_execution_state(full_dict)
        query = """
            UPDATE tasks SET
                title = :title,
                project_id = :project_id,
                priority = :priority,
                tags = :tags,
                category = :category,
                description = :description,
                planned_date = :planned_date,
                due_date = :due_date,
                planned_start_time = :planned_start_time,
                planned_end_time = :planned_end_time,
                actual_start_date = :actual_start_date,
                actual_end_date = :actual_end_date,
                actual_start_time = :actual_start_time,
                actual_end_time = :actual_end_time,
                estimated_duration = :estimated_duration,
                actual_duration = :actual_duration,
                progress = :progress,
                notes = :notes,
                recurring = :recurring,
                dependencies = :dependencies,
                status = :status,
                delay_minutes = :delay_minutes,
                delay_percentage = :delay_percentage,
                delay_category = :delay_category,
                delay_reason = :delay_reason,
                delay_notes = :delay_notes,
                delay_recorded_at = :delay_recorded_at,
                completion_rating = :completion_rating,
                completed_before_plan = :completed_before_plan,
                show_in_gantt = :show_in_gantt,
                startup_reminder = :startup_reminder,
                startup_reminder_mode = :startup_reminder_mode,
                is_pinned = :is_pinned,
                pin_color = :pin_color,
                pin_position = :pin_position,
                position = :position,
                planned_effort_minutes = :planned_effort_minutes,
                daily_dedication_minutes = :daily_dedication_minutes,
                allocation_mode = :allocation_mode,
                image_path = :image_path,
                baseline_start = :baseline_start,
                baseline_finish = :baseline_finish,
                baseline_duration_minutes = :baseline_duration_minutes,
                baseline_planned_effort_minutes = :baseline_planned_effort_minutes,
                constraint_type = :constraint_type,
                constraint_datetime = :constraint_datetime,
                deadline_datetime = :deadline_datetime,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id;
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, full_dict)
            conn.commit()
            return cursor.rowcount > 0

    def delete_task(self, task_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM tasks WHERE id = ?;", (task_id,))
            conn.commit()
            return cursor.rowcount > 0

    def get_task_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?;", (task_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_tasks(self, status: Optional[str] = None, planned_date: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT * FROM tasks WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if planned_date:
            query += " AND planned_date = ?"
            params.append(planned_date)

        query += " ORDER BY id DESC;"

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def search_tasks(self, search_term: str) -> List[Dict[str, Any]]:
        pattern = f"%{search_term}%"
        query = """
            SELECT * FROM tasks
            WHERE title LIKE ? OR description LIKE ? OR notes LIKE ? OR tags LIKE ?
            ORDER BY id DESC LIMIT 100;
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (pattern, pattern, pattern, pattern))
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_upcoming_tasks_range(self, start_date: str, end_date: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        if end_date:
            query = """
                SELECT * FROM tasks
                WHERE LOWER(status) NOT IN ('completed', 'cancelled')
                AND (
                    (planned_date > ? AND planned_date <= ?)
                    OR (due_date > ? AND due_date <= ?)
                    OR (planned_date <= ? AND due_date > ? AND due_date <= ?)
                )
                ORDER BY COALESCE(NULLIF(planned_date, ''), due_date) ASC, priority DESC, id ASC
                LIMIT ? OFFSET ?;
            """
            # Spanning tasks are bounded by the window end: a task due next
            # year is ongoing, not "upcoming within N days".
            params = [start_date, end_date, start_date, end_date, start_date, start_date, end_date, limit, offset]
        else:
            query = """
                SELECT * FROM tasks
                WHERE LOWER(status) NOT IN ('completed', 'cancelled')
                AND (planned_date > ? OR due_date > ?)
                ORDER BY COALESCE(NULLIF(planned_date, ''), due_date) ASC, priority DESC, id ASC
                LIMIT ? OFFSET ?;
            """
            params = [start_date, start_date, limit, offset]

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def get_upcoming_tasks_count(self, start_date: str, end_date: Optional[str] = None) -> int:
        if end_date:
            query = """
                SELECT COUNT(*) FROM tasks
                WHERE LOWER(status) NOT IN ('completed', 'cancelled')
                AND (
                    (planned_date > ? AND planned_date <= ?)
                    OR (due_date > ? AND due_date <= ?)
                    OR (planned_date <= ? AND due_date > ?)
                );
            """
            params = [start_date, end_date, start_date, end_date, start_date, start_date]
        else:
            query = """
                SELECT COUNT(*) FROM tasks
                WHERE LOWER(status) NOT IN ('completed', 'cancelled')
                AND (planned_date > ? OR due_date > ?);
            """
            params = [start_date, start_date]

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_inbox_tasks(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        query = """
            SELECT * FROM tasks
            WHERE (project_id IS NULL OR project_id = 1 OR project_id = 0)
              AND LOWER(status) NOT IN ('completed', 'cancelled', 'archived')
            ORDER BY id DESC
            LIMIT ? OFFSET ?;
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (limit, offset))
            return [dict(r) for r in cursor.fetchall()]

    def get_inbox_tasks_count(self) -> int:
        query = """
            SELECT COUNT(*) FROM tasks
            WHERE (project_id IS NULL OR project_id = 1 OR project_id = 0)
              AND LOWER(status) NOT IN ('completed', 'cancelled', 'archived');
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            row = cursor.fetchone()
            return row[0] if row else 0

    def get_completed_tasks(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        query = "SELECT * FROM tasks WHERE LOWER(status) = 'completed' ORDER BY COALESCE(NULLIF(actual_end_date, ''), planned_date, '') DESC, id DESC LIMIT ? OFFSET ?;"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, (limit, offset))
            return [dict(r) for r in cursor.fetchall()]

    def get_tasks_by_project(self, project_id: int) -> List[Dict[str, Any]]:
        if project_id in (1, 0, None):
            query = """
                SELECT * FROM tasks
                WHERE (project_id IS NULL OR project_id = 1 OR project_id = 0)
                  AND LOWER(status) NOT IN ('completed', 'cancelled', 'archived')
                ORDER BY id DESC;
            """
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query)
                return [dict(r) for r in cursor.fetchall()]
        else:
            query = """
                SELECT * FROM tasks
                WHERE project_id = ?
                  AND LOWER(status) NOT IN ('completed', 'cancelled', 'archived')
                ORDER BY id DESC;
            """
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (project_id,))
                return [dict(r) for r in cursor.fetchall()]

    def get_completed_tasks_count(self) -> int:
        query = "SELECT COUNT(*) FROM tasks WHERE LOWER(status) = 'completed';"
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            row = cursor.fetchone()
            return row[0] if row else 0

    # -----------------------------
    # Project Operations
    # -----------------------------
    def get_all_projects(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects ORDER BY name ASC;")
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def insert_project(self, project_dict: Dict[str, Any]) -> int:
        query = """
            INSERT INTO projects (name, color, icon, description, is_archived, baseline_created_at, baseline_name, working_weekdays, calendar_exceptions)
            VALUES (:name, :color, :icon, :description, :is_archived, :baseline_created_at, :baseline_name, :working_weekdays, :calendar_exceptions);
        """
        full_dict = {
            "name": "", "color": "#E95420", "icon": "folder",
            "description": "", "is_archived": 0,
            "baseline_created_at": None, "baseline_name": None,
            "working_weekdays": None, "calendar_exceptions": "[]",
        }
        if hasattr(project_dict, "to_dict"):
            project_dict = project_dict.to_dict()
        full_dict.update(project_dict)
        if isinstance(full_dict.get("working_weekdays"), (list, tuple)):
            import json
            full_dict["working_weekdays"] = json.dumps(full_dict["working_weekdays"])
        if isinstance(full_dict.get("calendar_exceptions"), (list, tuple, dict)):
            import json
            full_dict["calendar_exceptions"] = json.dumps(full_dict["calendar_exceptions"])
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, full_dict)
            conn.commit()
            return cursor.lastrowid

    def get_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM projects WHERE id = ?;", (project_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_project(self, project_dict: Dict[str, Any], project_id: Optional[int] = None) -> bool:
        if hasattr(project_dict, "to_dict"):
            project_dict = project_dict.to_dict()
        pid = project_id or project_dict.get("id")
        if pid is None:
            return False
        full_dict = {
            "name": "", "color": "#E95420", "icon": "folder",
            "description": "", "is_archived": 0,
            "baseline_created_at": None, "baseline_name": None,
            "working_weekdays": None, "calendar_exceptions": "[]",
        }
        full_dict.update(project_dict)
        full_dict["id"] = pid
        if isinstance(full_dict.get("working_weekdays"), (list, tuple)):
            import json
            full_dict["working_weekdays"] = json.dumps(full_dict["working_weekdays"])
        if isinstance(full_dict.get("calendar_exceptions"), (list, tuple, dict)):
            import json
            full_dict["calendar_exceptions"] = json.dumps(full_dict["calendar_exceptions"])
        query = """
            UPDATE projects SET
                name = :name,
                color = :color,
                icon = :icon,
                description = :description,
                is_archived = :is_archived,
                baseline_created_at = :baseline_created_at,
                baseline_name = :baseline_name,
                working_weekdays = :working_weekdays,
                calendar_exceptions = :calendar_exceptions
            WHERE id = :id;
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, full_dict)
            conn.commit()
            return cursor.rowcount > 0

    def get_project_calendar(self, project_id: int) -> Dict[str, Any]:
        """
        Returns working weekdays and calendar exceptions for a project.
        """
        import json

        def parse_weekdays(raw_value, fallback):
            if raw_value in (None, ""):
                return list(fallback)
            try:
                days = json.loads(raw_value) if isinstance(raw_value, str) else list(raw_value)
                clean_days = sorted({int(day) for day in days if 0 <= int(day) <= 6})
                return clean_days or list(fallback)
            except Exception:
                return list(fallback)

        global_work_days = parse_weekdays(
            self.get_setting("working_weekdays", ""),
            [0, 1, 2, 3, 4],
        )

        proj = self.get_project(project_id)
        if not proj:
            return {
                "working_weekdays": global_work_days,
                "calendar_exceptions": [],
            }
        raw_work = proj.get("working_weekdays")
        work_days = parse_weekdays(raw_work, global_work_days)

        # Fetch exceptions from DB table or fallback to JSON column
        exceptions = []
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, exception_date, is_working, name
                FROM project_calendar_exceptions
                WHERE project_id = ?
                ORDER BY exception_date ASC;
            """, (project_id,))
            rows = cursor.fetchall()
            if rows:
                for r in rows:
                    exceptions.append({
                        "id": r[0],
                        "date": r[1],
                        "is_working": bool(r[2]),
                        "name": r[3] or "",
                    })
            else:
                raw_ex = proj.get("calendar_exceptions")
                if raw_ex:
                    try:
                        exceptions = json.loads(raw_ex) if isinstance(raw_ex, str) else list(raw_ex)
                    except Exception:
                        exceptions = []

        return {
            "working_weekdays": work_days,
            "calendar_exceptions": exceptions,
        }

    def set_project_calendar(
        self,
        project_id: int,
        working_weekdays: List[int],
        calendar_exceptions: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Sets working weekdays and exceptions for a project atomically.
        """
        import json
        if calendar_exceptions is None:
            calendar_exceptions = []
        ww_json = json.dumps(working_weekdays)
        ex_json = json.dumps(calendar_exceptions)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE projects
                SET working_weekdays = ?, calendar_exceptions = ?
                WHERE id = ?;
            """, (ww_json, ex_json, project_id))

            # Sync table project_calendar_exceptions
            cursor.execute("DELETE FROM project_calendar_exceptions WHERE project_id = ?;", (project_id,))
            for ex in calendar_exceptions:
                d_str = str(ex.get("date") or ex.get("exception_date") or "")
                is_w = 1 if (ex.get("is_working") is True or ex.get("is_working") == 1) else 0
                name = str(ex.get("name") or "")
                if d_str:
                    cursor.execute("""
                        INSERT INTO project_calendar_exceptions (project_id, exception_date, is_working, name)
                        VALUES (?, ?, ?, ?);
                    """, (project_id, d_str, is_w, name))
            conn.commit()
            try:
                from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
                _GLOBAL_EVENT_BUS.working_calendar_changed.emit()
            except Exception:
                pass
            return True

    def add_project_calendar_exception(
        self,
        project_id: int,
        exception_date: str,
        is_working: bool = False,
        name: str = ""
    ) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO project_calendar_exceptions (project_id, exception_date, is_working, name)
                VALUES (?, ?, ?, ?);
            """, (project_id, exception_date, 1 if is_working else 0, name))
            ex_id = cursor.lastrowid

            cursor.execute("""
                SELECT id, exception_date, is_working, name
                FROM project_calendar_exceptions
                WHERE project_id = ?
                ORDER BY exception_date ASC;
            """, (project_id,))
            rows = cursor.fetchall()
            exs = [{"id": r[0], "date": r[1], "is_working": bool(r[2]), "name": r[3] or ""} for r in rows]
            import json
            cursor.execute("""
                UPDATE projects SET calendar_exceptions = ? WHERE id = ?;
            """, (json.dumps(exs), project_id))
            conn.commit()
            return ex_id

    def delete_project_calendar_exception(self, exception_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT project_id FROM project_calendar_exceptions WHERE id = ?;", (exception_id,))
            row = cursor.fetchone()
            if not row:
                return False
            pid = row[0]
            cursor.execute("DELETE FROM project_calendar_exceptions WHERE id = ?;", (exception_id,))

            cursor.execute("""
                SELECT id, exception_date, is_working, name
                FROM project_calendar_exceptions
                WHERE project_id = ?
                ORDER BY exception_date ASC;
            """, (pid,))
            rows = cursor.fetchall()
            exs = [{"id": r[0], "date": r[1], "is_working": bool(r[2]), "name": r[3] or ""} for r in rows]
            import json
            cursor.execute("""
                UPDATE projects SET calendar_exceptions = ? WHERE id = ?;
            """, (json.dumps(exs), pid))
            conn.commit()
            return True

    def _collect_legacy_baseline_version_items(
        self,
        cursor: sqlite3.Cursor,
        project_id: int,
    ) -> List[Dict[str, Any]]:
        task_where, task_params = self._task_project_filter(project_id, table_alias="")
        cursor.execute(
            f"""
            SELECT id, title, position, baseline_start, baseline_finish,
                   baseline_duration_minutes, baseline_planned_effort_minutes
            FROM tasks
            WHERE {task_where}
              AND (
                baseline_start IS NOT NULL
                OR baseline_finish IS NOT NULL
                OR baseline_duration_minutes IS NOT NULL
                OR baseline_planned_effort_minutes IS NOT NULL
              )
            ORDER BY position ASC, id ASC;
            """,
            task_params,
        )
        items: List[Dict[str, Any]] = []
        for row in cursor.fetchall():
            task_id = int(row["id"])
            items.append({
                "entity_type": "task",
                "entity_id": task_id,
                "title": row["title"],
                "task_id": task_id,
                "parent_subtask_id": None,
                "wbs_path": f"task:{task_id}",
                "sort_order": row["position"] or 0,
                "start": row["baseline_start"],
                "finish": row["baseline_finish"],
                "duration_minutes": row["baseline_duration_minutes"],
                "planned_effort_minutes": row["baseline_planned_effort_minutes"],
            })

        subtask_where, subtask_params = self._task_project_filter(project_id, table_alias="t")
        cursor.execute(
            f"""
            SELECT s.id, s.task_id, s.parent_subtask_id, s.title, s.position,
                   s.baseline_start, s.baseline_finish,
                   s.baseline_duration_minutes, s.baseline_planned_effort_minutes
            FROM subtasks s
            JOIN tasks t ON t.id = s.task_id
            WHERE {subtask_where}
            ORDER BY t.position ASC, t.id ASC, s.parent_subtask_id ASC, s.position ASC, s.id ASC;
            """,
            subtask_params,
        )
        subtask_rows = [dict(row) for row in cursor.fetchall()]
        subtasks_by_id = {int(row["id"]): row for row in subtask_rows}

        def _subtask_wbs_path(subtask_id: int) -> str:
            row = subtasks_by_id.get(subtask_id)
            if not row:
                return f"subtask:{subtask_id}"
            task_id = int(row["task_id"])
            parts = [f"subtask:{subtask_id}"]
            parent_id = row.get("parent_subtask_id")
            seen = {subtask_id}
            while parent_id is not None:
                try:
                    parent_id_int = int(parent_id)
                except (TypeError, ValueError):
                    break
                if parent_id_int in seen:
                    break
                seen.add(parent_id_int)
                parts.append(f"subtask:{parent_id_int}")
                parent_row = subtasks_by_id.get(parent_id_int)
                parent_id = parent_row.get("parent_subtask_id") if parent_row else None
            return f"task:{task_id}/" + "/".join(reversed(parts))

        for row in subtask_rows:
            has_baseline = any(row.get(col) is not None for col in _BASELINE_COLUMNS)
            if not has_baseline:
                continue
            subtask_id = int(row["id"])
            items.append({
                "entity_type": "subtask",
                "entity_id": subtask_id,
                "title": row["title"],
                "task_id": row["task_id"],
                "parent_subtask_id": row["parent_subtask_id"],
                "wbs_path": _subtask_wbs_path(subtask_id),
                "sort_order": row["position"] or 0,
                "start": row["baseline_start"],
                "finish": row["baseline_finish"],
                "duration_minutes": row["baseline_duration_minutes"],
                "planned_effort_minutes": row["baseline_planned_effort_minutes"],
            })

        return items

    def set_project_baseline(
        self,
        project_id: int,
        baseline_name: str = "Baseline 1",
        task_baselines: Optional[Dict[int, Dict[str, Any]]] = None,
        subtask_baselines: Optional[Dict[int, Dict[str, Any]]] = None,
        created_at: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Atomically creates the one allowed Original Baseline for project_id.

        The schedule_versions row is the canonical historical record. The
        legacy task/subtask baseline columns are maintained only as a display
        compatibility cache and migration source for older databases.
        """
        from datetime import datetime
        now_iso = created_at or datetime.now().isoformat()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT 1 FROM projects WHERE id = ?;", (project_id,))
                if cursor.fetchone() is None:
                    return False
                if self._get_original_baseline_row(cursor, project_id) is not None:
                    raise ScheduleVersionImmutabilityError(
                        "Original Baseline already exists and cannot be overwritten."
                    )
                if self._project_has_legacy_baseline(cursor, project_id):
                    raise ScheduleVersionImmutabilityError(
                        "Original Baseline already exists in legacy baseline fields. "
                        "Migrate it before creating approved revisions."
                    )

                cursor.execute("""
                    UPDATE projects
                    SET baseline_created_at = ?, baseline_name = ?
                    WHERE id = ?;
                """, (now_iso, baseline_name, project_id))

                if task_baselines is not None:
                    for task_id, b_data in task_baselines.items():
                        cursor.execute("""
                            UPDATE tasks SET
                                baseline_start = :baseline_start,
                                baseline_finish = :baseline_finish,
                                baseline_duration_minutes = :baseline_duration_minutes,
                                baseline_planned_effort_minutes = :baseline_planned_effort_minutes
                            WHERE id = :id AND (project_id = :project_id OR (project_id IS NULL AND :project_id IN (0, 1)));
                        """, {
                            "id": task_id,
                            "project_id": project_id,
                            "baseline_start": b_data.get("baseline_start"),
                            "baseline_finish": b_data.get("baseline_finish"),
                            "baseline_duration_minutes": b_data.get("baseline_duration_minutes"),
                            "baseline_planned_effort_minutes": b_data.get("baseline_planned_effort_minutes", 0),
                        })

                    for subtask_id, b_data in (subtask_baselines or {}).items():
                        cursor.execute("""
                            UPDATE subtasks SET
                                baseline_start = :baseline_start,
                                baseline_finish = :baseline_finish,
                                baseline_duration_minutes = :baseline_duration_minutes,
                                baseline_planned_effort_minutes = :baseline_planned_effort_minutes
                            WHERE id = :id AND task_id IN (
                                SELECT id FROM tasks
                                WHERE project_id = :project_id OR (project_id IS NULL AND :project_id IN (0, 1))
                            );
                        """, {
                            "id": subtask_id,
                            "project_id": project_id,
                            "baseline_start": b_data.get("baseline_start"),
                            "baseline_finish": b_data.get("baseline_finish"),
                            "baseline_duration_minutes": b_data.get("baseline_duration_minutes"),
                            "baseline_planned_effort_minutes": b_data.get("baseline_planned_effort_minutes", 0),
                        })
                else:
                    # Capture directly from current planned schedule
                    cursor.execute("""
                        UPDATE tasks SET
                            baseline_start = COALESCE(NULLIF(planned_date || ' ' || COALESCE(NULLIF(planned_start_time, ''), '00:00'), ' '), planned_date),
                            baseline_finish = COALESCE(NULLIF(COALESCE(due_date, planned_date) || ' ' || COALESCE(NULLIF(planned_end_time, ''), '23:59'), ' '), due_date, planned_date),
                            baseline_duration_minutes = estimated_duration,
                            baseline_planned_effort_minutes = planned_effort_minutes
                        WHERE project_id = ? OR (project_id IS NULL AND ? IN (0, 1));
                    """, (project_id, project_id))

                    cursor.execute("""
                        UPDATE subtasks SET
                            baseline_start = COALESCE(NULLIF(planned_date || ' ' || COALESCE(NULLIF(planned_start_time, ''), '00:00'), ' '), planned_date),
                            baseline_finish = COALESCE(NULLIF(COALESCE(due_date, planned_date) || ' ' || COALESCE(NULLIF(planned_end_time, ''), '23:59'), ' '), due_date, planned_date),
                            baseline_duration_minutes = estimated_duration,
                            baseline_planned_effort_minutes = planned_effort_minutes
                        WHERE task_id IN (
                            SELECT id FROM tasks WHERE project_id = ? OR (project_id IS NULL AND ? IN (0, 1))
                        );
                    """, (project_id, project_id))

                items = self._collect_legacy_baseline_version_items(cursor, project_id)
                self._insert_schedule_version(
                    cursor,
                    project_id=project_id,
                    name=baseline_name,
                    version_type=SCHEDULE_VERSION_ORIGINAL_BASELINE,
                    created_at=now_iso,
                    approved_at=now_iso,
                    notes=notes or "Original Baseline approval",
                    is_original_baseline=True,
                    sequence_order=1,
                    items=items,
                )
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                logger.error("Failed to set project baseline: %s", e)
                raise

    def clear_project_baseline(self, project_id: int) -> bool:
        """
        Baseline clearing is not an ordinary planning operation in Phase 2E.

        Once any historical Original Baseline evidence exists, the operation is
        blocked to avoid destroying the schedule reference. Beta deliberately
        provides no casual reset path.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                if (
                    self._get_original_baseline_row(cursor, project_id) is not None
                    or self._project_has_legacy_baseline(cursor, project_id)
                ):
                    raise ScheduleVersionImmutabilityError(
                        "Original Baseline cannot be cleared in Phase 2E. "
                        "This removes historical schedule reference."
                    )
                cursor.execute("""
                    UPDATE projects
                    SET baseline_created_at = NULL, baseline_name = NULL
                    WHERE id = ?;
                """, (project_id,))

                cursor.execute("""
                    UPDATE tasks SET
                        baseline_start = NULL,
                        baseline_finish = NULL,
                        baseline_duration_minutes = NULL,
                        baseline_planned_effort_minutes = NULL
                    WHERE project_id = ? OR (project_id IS NULL AND ? IN (0, 1));
                """, (project_id, project_id))

                cursor.execute("""
                    UPDATE subtasks SET
                        baseline_start = NULL,
                        baseline_finish = NULL,
                        baseline_duration_minutes = NULL,
                        baseline_planned_effort_minutes = NULL
                    WHERE task_id IN (
                        SELECT id FROM tasks WHERE project_id = ? OR (project_id IS NULL AND ? IN (0, 1))
                    );
                """, (project_id, project_id))

                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                logger.error("Failed to clear project baseline: %s", e)
                raise

    # -----------------------------
    # Settings Operations
    # -----------------------------
    def get_setting(self, key: str, default: str = "") -> str:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?;", (key,))
            row = cursor.fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value;
            """, (key, value))
            conn.commit()

    # -----------------------------
    # Subtask Operations
    # -----------------------------
    def get_subtasks(
        self,
        task_id: int,
        parent_subtask_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if parent_subtask_id is None:
                cursor.execute(
                    """
                    SELECT * FROM subtasks
                    WHERE task_id = ? AND parent_subtask_id IS NULL
                    ORDER BY position ASC, id ASC;
                    """,
                    (task_id,)
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM subtasks
                    WHERE task_id = ? AND parent_subtask_id = ?
                    ORDER BY position ASC, id ASC;
                    """,
                    (task_id, parent_subtask_id)
                )

            return [dict(r) for r in cursor.fetchall()]

    def get_subtask_by_id(self, subtask_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single subtask by its primary key id."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM subtasks WHERE id = ?;", (int(subtask_id),))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_subtasks_flat(self, task_id: int) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM subtasks
                WHERE task_id = ?
                ORDER BY parent_subtask_id, position ASC, id ASC;
                """,
                (task_id,)
            )
            return [dict(r) for r in cursor.fetchall()]

    def get_subtask_tree(self, task_id: int) -> List[Dict[str, Any]]:
        rows = self.get_all_subtasks_flat(task_id)

        by_parent: Dict[Optional[int], List[Dict[str, Any]]] = {}

        for row in rows:
            row = dict(row)
            row["children"] = []
            sub_id = row.get("id")
            if sub_id is not None:
                allocs = self.get_task_allocations(task_id=task_id, subtask_id=sub_id)
                row["custom_allocations"] = {
                    a["allocation_date"]: int(a["planned_minutes"] or 0)
                    for a in allocs
                }
            else:
                row["custom_allocations"] = {}

            parent_id = row.get("parent_subtask_id")
            by_parent.setdefault(parent_id, []).append(row)

        def attach_children(parent_id: Optional[int]):
            children = by_parent.get(parent_id, [])
            for child in children:
                child["children"] = attach_children(child["id"])
            return children

        return attach_children(None)

    def insert_subtask(
        self,
        task_id: int,
        title: str,
        is_completed: bool = False,
        position: int = 0,
        parent_subtask_id: Optional[int] = None,
        description: str = "",
        planned_date: Optional[str] = None,
        due_date: Optional[str] = None,
        planned_start_time: Optional[str] = None,
        planned_end_time: Optional[str] = None,
        estimated_duration: int = 0,
        priority: str = "Medium",
        progress: int = 0,
        status: str = "Planned",
        delay_category: str = "",
        delay_reason: str = "",
        delay_notes: str = "",
        delay_recorded_at: Optional[str] = None,
        show_in_gantt: bool = False,
        dependencies: Optional[List[int]] = None,
        icon: str = "",
        image_path: str = "",
        is_pinned: bool = False,
        pin_color: str = "#E95420",
        pin_position: int = 0,
        actual_start_date: Optional[str] = None,
        actual_end_date: Optional[str] = None,
        actual_start_time: Optional[str] = None,
        actual_end_time: Optional[str] = None,
        actual_duration: int = 0,
        planned_effort_minutes: int = 0,
        daily_dedication_minutes: int = 0,
        allocation_mode: str = "fixed_daily",
    ) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO subtasks (
                    task_id,
                    parent_subtask_id,
                    title,
                    description,
                    is_completed,
                    position,
                    planned_date,
                    due_date,
                    planned_start_time,
                    planned_end_time,
                    estimated_duration,
                    priority,
                    progress,
                    status,
                    delay_category,
                    delay_reason,
                    delay_notes,
                    delay_recorded_at,
                    show_in_gantt,
                    dependencies,
                    icon,
                    image_path,
                    is_pinned,
                    pin_color,
                    pin_position,
                    actual_start_date,
                    actual_end_date,
                    actual_start_time,
                    actual_end_time,
                    actual_duration,
                    planned_effort_minutes,
                    daily_dedication_minutes,
                    allocation_mode
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    task_id,
                    parent_subtask_id,
                    title,
                    description,
                    1 if is_completed else 0,
                    position,
                    planned_date,
                    due_date,
                    planned_start_time,
                    planned_end_time,
                    estimated_duration,
                    priority,
                    progress,
                    status,
                    delay_category,
                    delay_reason,
                    delay_notes,
                    delay_recorded_at,
                    1 if show_in_gantt else 0,
                    json.dumps(dependencies or []),
                    icon,
                    image_path,
                    1 if is_pinned else 0,
                    pin_color,
                    pin_position,
                    actual_start_date,
                    actual_end_date,
                    actual_start_time,
                    actual_end_time,
                    actual_duration,
                    planned_effort_minutes,
                    daily_dedication_minutes,
                    allocation_mode,
                )
            )

            conn.commit()
            return cursor.lastrowid

    def update_subtask(
        self,
        subtask_id: int,
        title: str,
        is_completed: bool,
        position: int = 0,
        parent_subtask_id: Optional[int] = None,
        description: str = "",
        planned_date: Optional[str] = None,
        due_date: Optional[str] = None,
        planned_start_time: Optional[str] = None,
        planned_end_time: Optional[str] = None,
        estimated_duration: int = 0,
        priority: str = "Medium",
        progress: int = 0,
        status: Optional[str] = None,
        delay_category: Optional[str] = None,
        delay_reason: Optional[str] = None,
        delay_notes: Optional[str] = None,
        delay_recorded_at: Optional[str] = None,
        show_in_gantt: bool = False,
        dependencies: Optional[List[int]] = None,
        icon: Optional[str] = None,
        image_path: Optional[str] = None,
        is_pinned: Optional[bool] = None,
        pin_color: Optional[str] = None,
        pin_position: Optional[int] = None,
        actual_start_date: Optional[str] = None,
        actual_end_date: Optional[str] = None,
        actual_start_time: Optional[str] = None,
        actual_end_time: Optional[str] = None,
        actual_duration: Optional[int] = None,
        planned_effort_minutes: Optional[int] = None,
        daily_dedication_minutes: Optional[int] = None,
        allocation_mode: Optional[str] = None,
        baseline_start: Optional[str] = None,
        baseline_finish: Optional[str] = None,
        baseline_duration_minutes: Optional[int] = None,
        baseline_planned_effort_minutes: Optional[int] = None,
        constraint_type: Optional[str] = None,
        constraint_datetime: Optional[str] = None,
        deadline_datetime: Optional[str] = None,
    ) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("PRAGMA table_info(subtasks);")
            cols = {row[1] for row in cursor.fetchall()}

            current_cols = [
                "dependencies",
                "icon",
                "image_path",
                "is_pinned",
                "pin_color",
                "pin_position",
                "actual_start_date",
                "actual_end_date",
                "actual_start_time",
                "actual_end_time",
                "actual_duration",
                "planned_effort_minutes",
                "daily_dedication_minutes",
                "allocation_mode",
            ]
            for workflow_col in (
                "status",
                "delay_category",
                "delay_reason",
                "delay_notes",
                "delay_recorded_at",
            ):
                if workflow_col in cols:
                    current_cols.append(workflow_col)

            cursor.execute(
                f"SELECT {', '.join(current_cols)} FROM subtasks WHERE id = ?;",
                (subtask_id,)
            )
            current = cursor.fetchone()

            if not current:
                return False

            def current_value(name: str, default=None):
                try:
                    if name in current.keys():
                        return current[name]
                except Exception:
                    pass
                return default

            if dependencies is None:
                dependencies_json = current["dependencies"] or "[]"
            else:
                dependencies_json = json.dumps(dependencies)

            if icon is None:
                icon = current["icon"] or ""

            if image_path is None:
                image_path = current["image_path"] or ""

            if is_pinned is None:
                is_pinned = bool(current["is_pinned"])

            if pin_color is None:
                pin_color = current["pin_color"] or "#E95420"

            if pin_position is None:
                pin_position = int(current["pin_position"] or 0)

            if actual_duration is None:
                actual_duration = int(current["actual_duration"] or 0)

            if planned_effort_minutes is None:
                planned_effort_minutes = int(current["planned_effort_minutes"] or 0)

            if daily_dedication_minutes is None:
                daily_dedication_minutes = int(current["daily_dedication_minutes"] or 0)

            if allocation_mode is None:
                allocation_mode = current["allocation_mode"] or "fixed_daily"

            if status is None:
                status = current_value(
                    "status",
                    "Completed" if is_completed else "Planned",
                ) or ("Completed" if is_completed else "Planned")
            if delay_category is None:
                delay_category = current_value("delay_category", "") or ""
            if delay_reason is None:
                delay_reason = current_value("delay_reason", "") or ""
            if delay_notes is None:
                delay_notes = current_value("delay_notes", "") or ""
            if delay_recorded_at is None:
                delay_recorded_at = current_value("delay_recorded_at")

            set_clauses = [
                "parent_subtask_id = ?",
                "title = ?",
                "description = ?",
                "is_completed = ?",
                "position = ?",
                "planned_date = ?",
                "due_date = ?",
                "planned_start_time = ?",
                "planned_end_time = ?",
                "estimated_duration = ?",
                "priority = ?",
                "progress = ?",
                "show_in_gantt = ?",
                "dependencies = ?",
                "icon = ?",
                "image_path = ?",
                "is_pinned = ?",
                "pin_color = ?",
                "pin_position = ?",
                "actual_start_date = ?",
                "actual_end_date = ?",
                "actual_start_time = ?",
                "actual_end_time = ?",
                "actual_duration = ?",
                "planned_effort_minutes = ?",
                "daily_dedication_minutes = ?",
                "allocation_mode = ?",
            ]
            params = [
                parent_subtask_id,
                title,
                description,
                1 if is_completed else 0,
                position,
                planned_date,
                due_date,
                planned_start_time,
                planned_end_time,
                estimated_duration,
                priority,
                progress,
                1 if show_in_gantt else 0,
                dependencies_json,
                icon,
                image_path,
                1 if is_pinned else 0,
                pin_color,
                pin_position,
                actual_start_date,
                actual_end_date,
                actual_start_time,
                actual_end_time,
                actual_duration,
                planned_effort_minutes,
                daily_dedication_minutes,
                allocation_mode,
            ]

            if "status" in cols:
                set_clauses.append("status = ?")
                params.append(status)
            if "delay_category" in cols:
                set_clauses.append("delay_category = ?")
                params.append(delay_category)
            if "delay_reason" in cols:
                set_clauses.append("delay_reason = ?")
                params.append(delay_reason)
            if "delay_notes" in cols:
                set_clauses.append("delay_notes = ?")
                params.append(delay_notes)
            if "delay_recorded_at" in cols:
                set_clauses.append("delay_recorded_at = ?")
                params.append(delay_recorded_at)

            if "baseline_start" in cols and baseline_start is not None:
                set_clauses.append("baseline_start = ?")
                params.append(baseline_start)
            if "baseline_finish" in cols and baseline_finish is not None:
                set_clauses.append("baseline_finish = ?")
                params.append(baseline_finish)
            if "baseline_duration_minutes" in cols and baseline_duration_minutes is not None:
                set_clauses.append("baseline_duration_minutes = ?")
                params.append(baseline_duration_minutes)
            if "baseline_planned_effort_minutes" in cols and baseline_planned_effort_minutes is not None:
                set_clauses.append("baseline_planned_effort_minutes = ?")
                params.append(baseline_planned_effort_minutes)
            if "constraint_type" in cols and constraint_type is not None:
                set_clauses.append("constraint_type = ?")
                params.append(constraint_type)
            if "constraint_datetime" in cols and constraint_datetime is not None:
                set_clauses.append("constraint_datetime = ?")
                params.append(constraint_datetime)
            if "deadline_datetime" in cols and deadline_datetime is not None:
                set_clauses.append("deadline_datetime = ?")
                params.append(deadline_datetime)

            params.append(subtask_id)
            sql = f"UPDATE subtasks SET {', '.join(set_clauses)} WHERE id = ?;"
            cursor.execute(sql, tuple(params))
            conn.commit()
            return cursor.rowcount > 0

    def set_task_allocations(
        self,
        task_id: Optional[int],
        subtask_id: Optional[int],
        allocations: List[Dict[str, Any]],
    ):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if subtask_id is not None:
                cursor.execute("DELETE FROM task_allocations WHERE subtask_id = ?;", (subtask_id,))
            elif task_id is not None:
                cursor.execute("DELETE FROM task_allocations WHERE task_id = ? AND subtask_id IS NULL;", (task_id,))

            for alloc in allocations:
                cursor.execute(
                    """
                    INSERT INTO task_allocations (
                        task_id, subtask_id, resource_id, allocation_date, planned_minutes, actual_minutes
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (
                        task_id,
                        subtask_id,
                        alloc.get("resource_id"),
                        alloc.get("allocation_date"),
                        int(alloc.get("planned_minutes", 0) or 0),
                        int(alloc.get("actual_minutes", 0) or 0),
                    )
                )
            conn.commit()

    def get_task_allocations(
        self,
        task_id: Optional[int] = None,
        subtask_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if subtask_id is not None:
                cursor.execute(
                    "SELECT * FROM task_allocations WHERE subtask_id = ? ORDER BY allocation_date ASC;",
                    (subtask_id,)
                )
            elif task_id is not None:
                cursor.execute(
                    "SELECT * FROM task_allocations WHERE task_id = ? AND subtask_id IS NULL ORDER BY allocation_date ASC;",
                    (task_id,)
                )
            else:
                cursor.execute("SELECT * FROM task_allocations ORDER BY allocation_date ASC;")
            return [dict(r) for r in cursor.fetchall()]

    def delete_subtask(self, subtask_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM subtasks WHERE id = ?;", (subtask_id,))
            conn.commit()
            return cursor.rowcount > 0

    def delete_subtasks_for_task(self, task_id: int) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM subtasks WHERE task_id = ?;", (task_id,))
            conn.commit()
            return cursor.rowcount > 0

    # -----------------------------
    # Companion Greetings & Media
    # -----------------------------
    def get_all_greetings(self) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM companion_greetings ORDER BY cycle_day ASC, id ASC;")
            return [dict(r) for r in cursor.fetchall()]

    def get_greeting_by_day(self, cycle_day: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM companion_greetings WHERE cycle_day = ? LIMIT 1;", (cycle_day,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_greeting_by_date(self, schedule_date: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM companion_greetings WHERE schedule_date = ? LIMIT 1;", (schedule_date,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def upsert_greeting(
        self,
        cycle_day: Optional[int] = None,
        schedule_date: Optional[str] = None,
        title: str = "",
        message: str = "",
        image_path: str = "",
        enabled: bool = True,
    ) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if cycle_day is not None:
                cursor.execute("SELECT id FROM companion_greetings WHERE cycle_day = ?;", (cycle_day,))
                row = cursor.fetchone()
                if row:
                    cursor.execute("""
                        UPDATE companion_greetings
                        SET title = ?, message = ?, image_path = ?, enabled = ?
                        WHERE id = ?;
                    """, (title, message, image_path, 1 if enabled else 0, row[0]))
                    conn.commit()
                    return row[0]
                else:
                    cursor.execute("""
                        INSERT INTO companion_greetings (cycle_day, title, message, image_path, enabled)
                        VALUES (?, ?, ?, ?, ?);
                    """, (cycle_day, title, message, image_path, 1 if enabled else 0))
                    conn.commit()
                    return cursor.lastrowid
            elif schedule_date is not None:
                cursor.execute("SELECT id FROM companion_greetings WHERE schedule_date = ?;", (schedule_date,))
                row = cursor.fetchone()
                if row:
                    cursor.execute("""
                        UPDATE companion_greetings
                        SET title = ?, message = ?, image_path = ?, enabled = ?
                        WHERE id = ?;
                    """, (title, message, image_path, 1 if enabled else 0, row[0]))
                    conn.commit()
                    return row[0]
                else:
                    cursor.execute("""
                        INSERT INTO companion_greetings (schedule_date, title, message, image_path, enabled)
                        VALUES (?, ?, ?, ?, ?);
                    """, (schedule_date, title, message, image_path, 1 if enabled else 0))
                    conn.commit()
                    return cursor.lastrowid
            return 0

    def insert_media_asset(
        self,
        relative_path: str,
        asset_type: str = "task_image",
        thumbnail_path: Optional[str] = None,
        mime_type: Optional[str] = None,
        width: int = 0,
        height: int = 0,
        file_size: int = 0,
    ) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO media_assets (
                    asset_type, relative_path, thumbnail_path, mime_type, width, height, file_size
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (asset_type, relative_path, thumbnail_path, mime_type, width, height, file_size))
            conn.commit()
            return cursor.lastrowid

    def get_media_asset_by_path(self, relative_path: str) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM media_assets WHERE relative_path = ? LIMIT 1;", (relative_path,))
            row = cursor.fetchone()
            return dict(row) if row else None
