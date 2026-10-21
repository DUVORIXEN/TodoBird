import gc
import os
import shutil
import sqlite3
import tempfile
from urllib.parse import parse_qs, urlparse

import pytest
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import (
    ProductionDatabaseAccessError,
    canonicalize_db_path,
    is_production_db_path,
)


_ORIGINAL_SQLITE_CONNECT = sqlite3.connect
_PYTEST_APP_DATA_DIR = None


def _is_read_only_sqlite_uri(database) -> bool:
    try:
        db_text = os.fspath(database)
    except TypeError:
        return False
    if not db_text.startswith("file:"):
        return False
    parsed = urlparse(db_text)
    query = parse_qs(parsed.query)
    return query.get("mode", [""])[0] == "ro"


def _guarded_sqlite_connect(database, *args, **kwargs):
    try:
        db_path = canonicalize_db_path(database)
    except Exception:
        db_path = None
    is_uri = bool(kwargs.get("uri"))
    if db_path is not None and is_production_db_path(db_path):
        if not (is_uri and _is_read_only_sqlite_uri(database)):
            raise ProductionDatabaseAccessError(
                "Writable sqlite3.connect() to the Todo Bird production database is blocked under pytest."
            )
    return _ORIGINAL_SQLITE_CONNECT(database, *args, **kwargs)


def pytest_configure(config):
    global _PYTEST_APP_DATA_DIR
    # Tests assert per-widget appearance state right after apply_theme();
    # the interactive deferred walk must not apply under pytest.
    os.environ.setdefault("TODO_BIRD_SYNC_APPEARANCE", "1")
    if not os.environ.get("TODO_BIRD_APP_DATA_DIR"):
        _PYTEST_APP_DATA_DIR = tempfile.mkdtemp(
            prefix=f"todo_bird_pytest_app_data_{os.getpid()}_"
        )
        os.environ["TODO_BIRD_APP_DATA_DIR"] = _PYTEST_APP_DATA_DIR
        
    if not os.environ.get("TODO_BIRD_CONFIG_DIR") and not os.environ.get("DISABLE_CONFIG_DIR_OVERRIDE"):
        config_dir = os.path.join(os.environ["TODO_BIRD_APP_DATA_DIR"], "config")
        os.makedirs(config_dir, exist_ok=True)
        os.environ["TODO_BIRD_CONFIG_DIR"] = config_dir
        
    sqlite3.connect = _guarded_sqlite_connect


def pytest_unconfigure(config):
    sqlite3.connect = _ORIGINAL_SQLITE_CONNECT
    global _PYTEST_APP_DATA_DIR
    if _PYTEST_APP_DATA_DIR:
        shutil.rmtree(_PYTEST_APP_DATA_DIR, ignore_errors=True)
        if os.environ.get("TODO_BIRD_APP_DATA_DIR") == _PYTEST_APP_DATA_DIR:
            os.environ.pop("TODO_BIRD_APP_DATA_DIR", None)
            os.environ.pop("TODO_BIRD_CONFIG_DIR", None)
        _PYTEST_APP_DATA_DIR = None

try:
    import shiboken6
except Exception:  # pragma: no cover - depends on PySide installation details
    shiboken6 = None


def _valid_widget(widget) -> bool:
    if widget is None:
        return False
    try:
        if shiboken6 is not None and not shiboken6.isValid(widget):
            return False
        return bool(widget.isWidgetType())
    except RuntimeError:
        return False


def _flush_deferred_deletes(app, cycles: int = 1) -> None:
    for _ in range(cycles):
        try:
            app.processEvents()
        except RuntimeError:
            return


def _cleanup_qt_test_state() -> None:
    app = QApplication.instance()
    if app is None:
        return

    try:
        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.close_all_on_shutdown()
    except Exception:
        WindowRegistry = None

    for widget in list(app.topLevelWidgets()):
        if not _valid_widget(widget):
            continue
        try:
            cleanup = getattr(widget, "cleanup", None)
            if callable(cleanup):
                cleanup()
        except Exception:
            pass
        try:
            if hasattr(widget, "reject"):
                widget.reject()
        except Exception:
            pass
        try:
            widget.close()
        except Exception:
            pass

    _flush_deferred_deletes(app)

    try:
        from todo_bird_app.widgets.toast_banner import ToastBanner
        ToastBanner._active_toast = None
    except Exception:
        pass

    if WindowRegistry is not None:
        try:
            WindowRegistry.clear()
        except Exception:
            pass

    pass


@pytest.fixture(autouse=True)
def _qt_test_hygiene():
    yield
    _cleanup_qt_test_state()
