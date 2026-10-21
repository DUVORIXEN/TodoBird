import sys
import os
import argparse
import logging
from pathlib import Path

# Add project root directory to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QIcon

from todo_bird_app.database import DatabaseManager, PRODUCTION_DB_PATH
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.views.main_window import MainWindow
from todo_bird_app.services.platform_service import get_platform_service
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.widgets.startup_reminder_dialog import StartupReminderDialog
from todo_bird_app.widgets.desktop_companion import DesktopCompanion
from PySide6.QtCore import QTimer
from datetime import datetime

SINGLE_INSTANCE_SERVER_NAME = "todo_bird_single_instance_socket"

def setup_logging():
    from todo_bird_app.services.path_resolver import PathResolver
    log_dir = PathResolver.get_logs_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "todo_bird.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )

def main():
    parser = argparse.ArgumentParser(description="TODO BIRD - Offline Productivity Companion")
    parser.add_argument("--check-init", action="store_true", help="Initialize components and exit 0 (for testing)")
    parser.add_argument("--database", type=str, help="Path to custom SQLite database file")
    parser.add_argument("--autostart", action="store_true", help="Launch via system autostart sequence")
    args = parser.parse_args()

    if args.database:
        os.environ["TODO_BIRD_DB"] = str(Path(args.database).resolve())

    setup_logging()
    logger = logging.getLogger("todo_bird")
    logger.info("Starting TODO BIRD Desktop Application...")

    # Configure QPA platform: offscreen only if check-init, or on Unix/Linux without any graphical display
    if args.check_init:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
    elif "QT_QPA_PLATFORM" not in os.environ:
        if not (sys.platform == "win32" or sys.platform == "darwin"):
            if "DISPLAY" not in os.environ and "WAYLAND_DISPLAY" not in os.environ:
                os.environ["QT_QPA_PLATFORM"] = "offscreen"

    app = QApplication(sys.argv)
    app.setApplicationName("TODO BIRD")
    app.setOrganizationName("TodoBird")
    app.setDesktopFileName("todo-bird")

    icon_path = Path(__file__).parent / "assets" / "icons" / "todo-bird.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Load and register bundled Inter fonts for zero-drift cross-platform typography
    from todo_bird_app.services.typography_service import TypographyService
    TypographyService.initialize_application_fonts()

    # Check single-instance socket unless in check-init or offscreen mode
    is_offscreen = args.check_init or os.environ.get("QT_QPA_PLATFORM") == "offscreen"
    server = None

    if not is_offscreen:
        socket = QLocalSocket()
        socket.connectToServer(SINGLE_INSTANCE_SERVER_NAME)
        if socket.waitForConnected(500):
            logger.info("TODO BIRD is already running. Focus request sent to active instance.")
            socket.write(b"activate")
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            return 0

        # Create Single Instance Local Server
        server = QLocalServer()
        # Clean up stale socket file if exists
        QLocalServer.removeServer(SINGLE_INSTANCE_SERVER_NAME)
        server.listen(SINGLE_INSTANCE_SERVER_NAME)
        app._single_instance_server = server

    # Initialize Core Services & Controllers
    from todo_bird_app.services.runtime_environment import RuntimeEnvironment
    from todo_bird_app.services.path_resolver import PathResolver
    from todo_bird_app.services.storage_migration_service import StorageMigrationService

    runtime = RuntimeEnvironment.current()
    paths = PathResolver(runtime)

    db_path_override = os.environ.get("TODO_BIRD_DB")
    if db_path_override:
        target_db_path = Path(db_path_override).resolve()
    else:
        target_db_path = paths.get_database_path()

    config_dir = paths.get_config_dir()

    if runtime.is_packaged():
        StorageMigrationService.ensure_user_storage(paths=paths, runtime=runtime)
    
    # --- PHASE C: PRAGMA integrity_check on startup ---
    from todo_bird_app.services.backup_manager import BackupManager
    if target_db_path.exists():
        logger.info("Executing database integrity check...")
        is_valid, msg = BackupManager.verify_database_integrity(target_db_path)
        if not is_valid:
            logger.error(f"Database corruption detected at startup: {msg}")
            QMessageBox.critical(
                None,
                "Database Corruption Detected",
                f"Todo Bird cannot start safely because the database file appears to be corrupted.\n\n"
                f"Error: {msg}\n\n"
                f"Your data has not been overwritten. Please restore a backup from the backups directory."
            )
            return 1
            
    if db_path_override:
        db_manager = DatabaseManager.temporary(str(target_db_path))
    elif target_db_path == PRODUCTION_DB_PATH:
        db_manager = DatabaseManager.production()
    else:
        db_manager = DatabaseManager.production(str(target_db_path))
    settings_manager = SettingsManager(db_manager, config_dir=config_dir)
    theme_controller = ThemeController(settings_manager)

    # Apply initial theme
    theme_controller.apply_theme()

    # Create Main Window
    main_window = MainWindow(db_manager, settings_manager, theme_controller)

    # Connect server newConnection to focus window if active
    if server:
        def on_new_connection():
            conn = server.nextPendingConnection()
            if conn:
                conn.waitForReadyRead(500)
                main_window.show()
                main_window.raise_()
                main_window.activateWindow()

        server.newConnection.connect(on_new_connection)

    # Ensure desktop launchers exist
    get_platform_service().create_desktop_launcher()

    # Self-heal the autostart entry so the persisted toggle matches disk:
    # older builds wrote a flagless entry that made session-login launches
    # indistinguishable from manual ones (startup reminders never fired).
    if bool(settings_manager.get("autostart_at_login", False)):
        get_platform_service().create_autostart_entry(True)

    if args.check_init:
        logger.info("Check-init verification successful. Exiting clean.")
        return 0

    main_window.show()

    # Start desktop companion with local-time aware, once-per-period greeting.
    from todo_bird_app.services.avocet_voice_service import AvocetVoiceService

    logger.info("Startup voice path: app, settings, MainWindow and companion scheduler are ready.")
    gates = AvocetVoiceService.evaluate_startup_gates(settings_manager)
    should_speak = gates["should_speak"]
    greeting = gates["selected_greeting"]
    voice_profile = gates.get("active_voice_profile", "durga")
    last_spoken_key = gates["last_spoken_key"]
    today_key = gates["today_key"]

    if gates.get("companion_enabled", True):

        def _on_speech_started():
            logger.info(
                "Avocet voice playback process started; spoken-today marker "
                "will be written only after successful completion."
            )

        def _on_speech_completed():
            settings_manager.set(last_spoken_key, today_key)
            logger.info(
                f"Avocet voice playback completed — recorded {last_spoken_key} = {today_key}"
            )

        def _on_speech_failed(reason):
            logger.warning(
                f"Avocet voice unavailable: {reason}. "
                f"{last_spoken_key} was not recorded."
            )

        main_window.desktop_companion = DesktopCompanion(
            greeting if should_speak else "",
            voice_profile=voice_profile,
            settings_manager=settings_manager,
            on_speech_started=_on_speech_started if should_speak else None,
            on_speech_completed=_on_speech_completed if should_speak else None,
            on_speech_failed=_on_speech_failed if should_speak else None,
        )

        QTimer.singleShot(
            700,
            main_window.desktop_companion.start_sequence
        )

        visible_seconds = settings_manager.get(
            "companion_visible_seconds",
            24
        )
        try:
            visible_ms = max(5, int(visible_seconds)) * 1000
        except (TypeError, ValueError):
            visible_ms = 24000

        QTimer.singleShot(
            visible_ms,
            main_window.desktop_companion.exit_scene
        )
    else:
        logger.info("Desktop Avocet companion disabled; startup voice path stopped before widget creation.")

    from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
    ReminderPolicyService.evaluate_startup_reminders(
        main_window,
        main_window.task_controller,
        settings_manager=settings_manager,
        is_session_startup=args.autostart
    )

    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
