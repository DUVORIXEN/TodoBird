import os
import sys
import logging
import tempfile
from pathlib import Path
from typing import Optional, Any

from todo_bird_app.services.runtime_environment import RuntimeEnvironment, RuntimeMode

logger = logging.getLogger(__name__)


class _PathResolverMethod:
    """Descriptor that allows a PathResolver method to be called on either the class or an instance."""
    def __init__(self, func):
        self.func = func

    def __get__(self, instance, owner):
        if instance is None:
            # Called as PathResolver.method(...)
            return lambda *args, **kwargs: self.func(owner(), *args, **kwargs)
        # Called as instance.method(...)
        return lambda *args, **kwargs: self.func(instance, *args, **kwargs)


class PathResolver:
    """
    Cross-platform path resolution service.
    Ensures clear separation of storage authority:
      - DEVELOPMENT_SOURCE: Repo-local DB (todo_bird_app/data/todo_bird.db) and repo config.
      - PACKAGED_INSTALLED: Standard OS user-data directory:
          - Linux:   ~/.local/share/TodoBird/
          - Windows: %LOCALAPPDATA%\\TodoBird\\
          - macOS:   ~/Library/Application Support/TodoBird/

    Environment variable precedence:
      1. Specific override: TODO_BIRD_DB, TODO_BIRD_CONFIG_DIR
      2. App data root:     TODO_BIRD_APP_DATA_DIR
      3. Runtime mode default (Packaged OS standard vs Development repo-local)
    """
    APP_DIR_NAME = "TodoBird"
    APP_DATA_ENV = "TODO_BIRD_APP_DATA_DIR"
    DB_NAME = "todo_bird.db"

    def __init__(self, runtime: Optional[RuntimeEnvironment] = None):
        self._runtime = runtime or RuntimeEnvironment.current()

    @property
    def runtime(self) -> RuntimeEnvironment:
        return self._runtime

    @staticmethod
    def _get_repo_root() -> Path:
        return Path(__file__).resolve().parent.parent

    @classmethod
    def get_development_db_path(cls) -> Path:
        return cls._get_repo_root() / "data" / cls.DB_NAME

    @classmethod
    def get_development_config_dir(cls) -> Path:
        return cls._get_repo_root() / "config"

    @classmethod
    def _ensure_dir(cls, path: Path) -> Path:
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except OSError as exc:
            fallback = Path(tempfile.gettempdir()) / cls.APP_DIR_NAME
            if path.name != cls.APP_DIR_NAME:
                fallback = fallback / path.name
            fallback.mkdir(parents=True, exist_ok=True)
            logger.warning(
                "Unable to create app data directory %s (%s); using %s",
                path,
                exc,
                fallback,
            )
            return fallback

    @classmethod
    def get_app_data_dir(cls) -> Path:
        env_dir = os.environ.get(cls.APP_DATA_ENV)
        if env_dir:
            return cls._ensure_dir(Path(env_dir).expanduser().resolve())

        if sys.platform == "win32":
            base = Path(
                os.environ.get(
                    "LOCALAPPDATA",
                    os.path.expanduser("~\\AppData\\Local"),
                )
            )
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            if os.environ.get("SNAP_USER_COMMON"):
                return cls._ensure_dir(Path(os.environ["SNAP_USER_COMMON"]) / cls.APP_DIR_NAME)
            base = Path(
                os.environ.get(
                    "XDG_DATA_HOME",
                    Path.home() / ".local" / "share",
                )
            )

        return cls._ensure_dir(base / cls.APP_DIR_NAME)

    @_PathResolverMethod
    def get_database_path(self, custom_db_name: Optional[str] = None) -> Path:
        # Precedence 1: Explicit DB environment variable override
        env_db = os.environ.get("TODO_BIRD_DB")
        if env_db:
            return Path(env_db).expanduser().resolve()

        db_filename = custom_db_name or self.DB_NAME

        # Precedence 2: Explicit APP_DATA_DIR override
        if os.environ.get(self.APP_DATA_ENV):
            return self.get_app_data_dir() / db_filename

        # Precedence 3: Runtime-mode default
        if self.runtime.is_packaged():
            return self.get_app_data_dir() / db_filename
        else:
            # Development source mode: use repo-local data directory
            return self._get_repo_root() / "data" / db_filename

    @_PathResolverMethod
    def get_config_dir(self) -> Path:
        # Precedence 1: Explicit CONFIG_DIR environment variable override
        env_config = os.environ.get("TODO_BIRD_CONFIG_DIR")
        if env_config:
            return self._ensure_dir(Path(env_config).expanduser().resolve())

        # Precedence 2: Explicit APP_DATA_DIR override
        if os.environ.get(self.APP_DATA_ENV):
            return self._ensure_dir(self.get_app_data_dir() / "config")

        # Precedence 3: Runtime-mode default
        if self.runtime.is_packaged():
            return self._ensure_dir(self.get_app_data_dir() / "config")
        else:
            return self._ensure_dir(self.get_development_config_dir())

    @_PathResolverMethod
    def get_backups_dir(self) -> Path:
        backup_dir = self.get_app_data_dir() / "backups"
        return self._ensure_dir(backup_dir)

    @_PathResolverMethod
    def get_exports_dir(self) -> Path:
        export_dir = self.get_app_data_dir() / "exports"
        return self._ensure_dir(export_dir)

    @_PathResolverMethod
    def get_logs_dir(self) -> Path:
        if os.environ.get(self.APP_DATA_ENV) or self.runtime.is_packaged():
            log_dir = self.get_app_data_dir() / "logs"
        else:
            log_dir = self._get_repo_root() / "logs"
        return self._ensure_dir(log_dir)

    @_PathResolverMethod
    def get_media_dir(self) -> Path:
        media_dir = self.get_app_data_dir() / "media"
        return self._ensure_dir(media_dir)

    @classmethod
    def ensure_database_migrated(cls, target_path: Path) -> Path:
        """
        Backward-compatible migration delegate.
        Calls StorageMigrationService for safe, integrity-verified migration.
        """
        from todo_bird_app.services.storage_migration_service import StorageMigrationService
        StorageMigrationService.migrate_database_file(
            source_path=cls.get_development_db_path(),
            target_path=target_path
        )
        return target_path
