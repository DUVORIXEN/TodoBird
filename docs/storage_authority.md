# TODO BIRD — Storage Authority & Runtime Contract Specification

## Overview

This specification establishes the authoritative contract governing application runtime modes, database and configuration storage locations, migration guarantees, and environment variable overrides across all supported desktop platforms (Linux, Windows, macOS).

---

## 1. Runtime Modes

The application distinguishes two mutually exclusive runtime modes via the canonical `RuntimeEnvironment` authority (`todo_bird_app/services/runtime_environment.py`):

1. **`DEVELOPMENT_SOURCE` (`"development_source"`):**
   - Active when executing directly from a local repository checkout (e.g., `python -m todo_bird_app.app` from `~/todo_bird`).
   - Signals: Not frozen (`getattr(sys, 'frozen', False) == False`), no `_MEIPASS`, and neither `TODO_BIRD_RUNTIME_MODE=packaged` nor `TODO_BIRD_PACKAGED=1` is set.
   - Purpose: Day-to-day software development, automated test execution, and safe local experimentation without polluting user-data directories.

2. **`PACKAGED_INSTALLED` (`"packaged_installed"`):**
   - Active when executing as a frozen standalone package (e.g., PyInstaller, cx_Freeze, AppImage, MSI, DMG, system package).
   - Signals: `getattr(sys, 'frozen', False) == True`, `hasattr(sys, '_MEIPASS') == True`, or explicit environment override `TODO_BIRD_RUNTIME_MODE=packaged` / `TODO_BIRD_PACKAGED=1`.
   - Never detects packaged mode by scanning for arbitrary filesystem substrings such as `"/usr"` or `"/opt"`.

---

## 2. Storage Authority Matrix

| Storage Category | `DEVELOPMENT_SOURCE` Mode | `PACKAGED_INSTALLED` Mode | Override Precedence |
| :--- | :--- | :--- | :--- |
| **Database Authority** | Repo-local: `todo_bird_app/data/todo_bird.db` | User-data OS path: `<APP_DATA_DIR>/todo_bird.db` | 1. `TODO_BIRD_DB`<br>2. `TODO_BIRD_APP_DATA_DIR`<br>3. Runtime Default |
| **Config Authority** | Repo-local: `todo_bird_app/config/config.json` | User-data OS path: `<APP_DATA_DIR>/config/config.json` | 1. `TODO_BIRD_CONFIG_DIR`<br>2. `TODO_BIRD_APP_DATA_DIR`<br>3. Runtime Default |
| **Backups** | `<APP_DATA_DIR>/backups/` | `<APP_DATA_DIR>/backups/` | 1. `TODO_BIRD_APP_DATA_DIR`/backups<br>2. Runtime Default |
| **Logs** | Repo-local: `todo_bird_app/logs/todo_bird.log` | User-data OS path: `<APP_DATA_DIR>/logs/todo_bird.log` | 1. `TODO_BIRD_APP_DATA_DIR`/logs<br>2. Runtime Default |
| **Exports** | `<APP_DATA_DIR>/exports/` | `<APP_DATA_DIR>/exports/` | 1. `TODO_BIRD_APP_DATA_DIR`/exports<br>2. Runtime Default |
| **Media Assets** | `<APP_DATA_DIR>/media/` | `<APP_DATA_DIR>/media/` | 1. `TODO_BIRD_APP_DATA_DIR`/media<br>2. Runtime Default |

---

## 3. Platform Paths (`<APP_DATA_DIR>`)

When no environment overrides are present, `<APP_DATA_DIR>` resolves to:

- **Linux / BSD:**
  `$XDG_DATA_HOME/TodoBird` (defaults to `~/.local/share/TodoBird`)
- **Windows:**
  `%LOCALAPPDATA%\TodoBird` (defaults to `C:\Users\<User>\AppData\Local\TodoBird`)
- **macOS:**
  `~/Library/Application Support/TodoBird`

### Canonical Database Filename
The canonical cross-platform database filename is `todo_bird.db` across all operating systems. Legacy platform-specific pilot filenames (`todo_bird_windows_pilot.db`, `todo_bird_macos_pilot.db`, `todo_bird_ubuntu_pilot.db`) are retained solely as read-only migration sources for existing early installations.

---

## 4. Environment Variable Precedence

The resolution order for storage paths is strictly hierarchical:

```
[Explicit Path Override: TODO_BIRD_DB / TODO_BIRD_CONFIG_DIR]
                           │
                           ▼ (if not set)
           [App Data Root: TODO_BIRD_APP_DATA_DIR]
                           │
                           ▼ (if not set)
                 [Runtime Mode Default]
                 ┌─────────┴─────────┐
                 ▼                   ▼
     (DEVELOPMENT_SOURCE)    (PACKAGED_INSTALLED)
       Repo-local paths       OS User-Data paths
```

When `TODO_BIRD_APP_DATA_DIR` is defined (e.g. during sandboxed test execution), database, config, backups, logs, exports, and media directories are consistently grouped under that custom root.

---

## 5. Safe Idempotent Storage Migration (`StorageMigrationService`)

The migration subsystem (`todo_bird_app/services/storage_migration_service.py`) coordinates safe first-run data initialization under the following rules:

1. **Strict Runtime Mode Gate:**
   - In `DEVELOPMENT_SOURCE` mode, migration is completely skipped. Development data in the repository is never moved or overwritten.
2. **User Data Authority Protection:**
   - If the target user database or config already exists, it is accepted as authority. It is never overwritten by legacy files.
3. **Coherent Transition:**
   - Database and configuration migrate together on first launch in packaged mode.
4. **Pre-flight Integrity Verification:**
   - The source database undergoes SQLite integrity verification (`PRAGMA quick_check`) prior to any copy operation. Corrupt sources are rejected.
5. **Atomic SQLite Backup API:**
   - Copies are staged into a temporary file (`.tmp_migrating`) via `sqlite3.Connection.backup()`. If the process is terminated or fails midway, no partial target file remains.
6. **Post-copy Target Verification:**
   - The staged file is verified for integrity prior to atomic replacement (`Path.replace()`).
7. **Source Preservation:**
   - The legacy source file is never deleted automatically.

---

## 6. Application Startup Protocol (`app.py`)

During application bootstrap:
1. `RuntimeEnvironment.current()` determines the operational context.
2. `PathResolver(runtime)` computes canonical database and configuration paths.
3. If `runtime.is_packaged()`, `StorageMigrationService.ensure_user_storage(paths, runtime)` executes.
4. Startup integrity check validates the active database via `BackupManager.verify_database_integrity()`.
5. `DatabaseManager.production(str(target_db_path))` initializes SQLite authority.
6. `SettingsManager(db_manager, config_dir=config_dir)` binds configuration to the resolved storage location.
7. `setup_logging()` directs diagnostic logs to `PathResolver.get_logs_dir()`, avoiding read-only installation directory writes.
