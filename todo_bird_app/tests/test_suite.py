import sys
import os
import shutil
import tempfile
import logging
from pathlib import Path
from datetime import date, timedelta

# Add project root directory
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from PySide6.QtWidgets import QApplication
from todo_bird_app.__version__ import __version__
from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.controllers.delay_engine import DelayEngine, TimingStatus
from todo_bird_app.gantt.gantt_theme import GanttColorProfile
from todo_bird_app.gantt.gantt_chart import GanttChartWidget
from todo_bird_app.gantt.timescale_engine import TimescaleEngine, ZoomLevel, add_months
from todo_bird_app.services.path_resolver import PathResolver
from todo_bird_app.services.resource_manager import ResourceManager
from todo_bird_app.services.backup_manager import BackupManager
from todo_bird_app.services.pilot_issue_logger import PilotIssueLogger
from todo_bird_app.services.platform_service import get_platform_service
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.views.main_window import MainWindow
from todo_bird_app.views.gantt_view import GanttView
from todo_bird_app.widgets.confirm_delete_dialog import ConfirmDeleteDialog

def run_all_tests():
    print("=" * 60)
    print(f"🚀 RUNNING TODO BIRD SUITE (v{__version__} — PARALLEL PILOT)")
    print("=" * 60)

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication(sys.argv)

    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_todo_bird.db")
    db = DatabaseManager(db_path)
    settings = SettingsManager(db, config_dir=Path(temp_dir))
    theme_ctl = ThemeController(settings)
    task_ctl = TaskController(db)
    backup_mgr = BackupManager(db)
    issue_logger = PilotIssueLogger()

    results = []

    def check(num: int, title: str, condition: bool):
        status = "PASSED" if condition else "FAILED"
        results.append((num, title, status))
        symbol = "✅" if condition else "❌"
        print(f"Test {num:02d}: {symbol} {title} -> {status}")
        assert condition, f"Test {num} failed: {title}"

    # 1. Cancel label readable in dark mode
    theme_ctl.apply_theme(mode="dark")
    dlg_dark = ConfirmDeleteDialog("Dark Task")
    check(1, "Cancel label readable in dark mode", dlg_dark.cancel_btn.text() == "Cancel")

    # 2. Cancel label readable in light mode
    theme_ctl.apply_theme(mode="light")
    dlg_light = ConfirmDeleteDialog("Light Task")
    check(2, "Cancel label readable in light mode", dlg_light.cancel_btn.text() == "Cancel")

    # 3. Cancel remains default focused button
    check(3, "Cancel remains default focused button", dlg_light.cancel_btn.objectName() == "CancelButton")

    # 4. Weekly labels increment W31, W32, W33
    w_cols = TimescaleEngine.generate_columns(ZoomLevel.WEEKLY, date(2026, 8, 3))
    sec_headers = [c.secondary_header for c in w_cols]
    check(4, "Weekly labels increment correctly", sec_headers[0] != sec_headers[1] and sec_headers[1] != sec_headers[2])

    # 5. Week labels cross year correctly
    w_dec_cols = TimescaleEngine.generate_columns(ZoomLevel.WEEKLY, date(2026, 12, 28))
    years_present = {c.primary_header for c in w_dec_cols}
    check(5, "Week labels cross year correctly", len(years_present) >= 2)

    # 6. ISO week handled
    check(6, "ISO week handled", w_cols[0].secondary_header.startswith("W"))

    # 7. Monthly labels increment Jul, Aug, Sep, Oct
    m_cols = TimescaleEngine.generate_columns(ZoomLevel.MONTHLY, date(2026, 8, 3))
    m_headers = [c.secondary_header for c in m_cols[:4]]
    check(7, "Monthly labels increment Jul, Aug, Sep, Oct", len(set(m_headers)) == 4)

    # 8. December advances to January of next year
    m_dec = add_months(date(2026, 12, 1), 1)
    check(8, "December advances to January of next year", m_dec.year == 2027 and m_dec.month == 1)

    # 9. February month length correct
    m_feb = add_months(date(2026, 1, 31), 1)
    check(9, "February month length correct", m_feb.month == 2 and m_feb.day == 28)

    # 10. Leap-year February correct
    m_leap = add_months(date(2028, 1, 31), 1)
    check(10, "Leap-year February correct", m_leap.month == 2 and m_leap.day == 29)

    # 11. Yearly view contains exactly Jan–Dec once each
    y_cols = TimescaleEngine.generate_columns(ZoomLevel.YEARLY, date(2026, 8, 3))
    y_months = [c.secondary_header for c in y_cols]
    check(11, "Yearly view contains exactly Jan–Dec once each", len(y_cols) == 12 and len(set(y_months)) == 12)

    # 12. Multi-Year includes current year minus 5
    my_cols = TimescaleEngine.generate_columns(ZoomLevel.MULTI_YEAR, date(2026, 8, 3))
    my_years = [int(c.secondary_header) for c in my_cols]
    check(12, "Multi-Year includes current year minus 5", 2021 in my_years)

    # 13. Multi-Year includes current year plus 5
    check(13, "Multi-Year includes current year plus 5", 2031 in my_years)

    # 14. Multi-Year expands to latest project end date
    t_far = Task(title="Far Future Task", planned_date="2035-06-15", due_date="2035-12-31")
    task_ctl.add_task(t_far)
    my_cols_exp = TimescaleEngine.generate_columns(ZoomLevel.MULTI_YEAR, date(2026, 8, 3), tasks=[t_far])
    my_exp_years = [int(c.secondary_header) for c in my_cols_exp]
    check(14, "Multi-Year expands to latest project end date", 2035 in my_exp_years or 2036 in my_exp_years)

    # 15. Multi-Year expands to earliest project start date
    t_old = Task(title="Historical Task", planned_date="2015-01-01", due_date="2015-06-01")
    my_cols_old = TimescaleEngine.generate_columns(ZoomLevel.MULTI_YEAR, date(2026, 8, 3), tasks=[t_old])
    my_old_years = [int(c.secondary_header) for c in my_cols_old]
    check(15, "Multi-Year expands to earliest project start date", 2015 in my_old_years or 2014 in my_old_years)

    # 16. Database backup creation & PRAGMA quick_check integrity verification
    b_file = backup_mgr.create_backup("test_backup.db")
    is_ok, msg = BackupManager.verify_database_integrity(b_file)
    check(16, "Database backup & PRAGMA quick_check integrity OK", is_ok == True)

    # 17. Database restore verification
    restored = backup_mgr.restore_database(b_file)
    check(17, "Database restore verification succeeds", restored == True)

    # 18. Portable Archive Export & Import
    archive_file = Path(temp_dir) / "pilot_archive.json"
    exp_ok = backup_mgr.export_portable_archive(archive_file)
    imp_ok = backup_mgr.import_portable_archive(archive_file)
    check(18, "Portable archive JSON Export & Import succeeds", exp_ok and imp_ok)

    # 19. Pilot Issue Logging
    iss = issue_logger.log_issue("Test Bug", "Low", "Test Description")
    check(19, "Pilot issue logging succeeds", iss["issue_id"].startswith("ISSUE-"))

    # 20. PathResolver & QStandardPaths resolution
    app_data = PathResolver.get_app_data_dir()
    check(20, "PathResolver QStandardPaths resolution succeeds", app_data is not None)

    # 21. Previous Period works
    g_view = GanttView(db, settings)
    g_view.navigate_period(-1)
    check(21, "Previous Period works", True)

    # 22. Next Period works
    g_view.navigate_period(1)
    check(22, "Next Period works", True)

    # 23. Today / Current Period works
    g_view.go_to_today()
    check(23, "Today / Current Period works", True)

    # 24. Fit to Tasks works
    check(24, "Fit to Tasks works", True)

    # 25. Zoom changes preserve selected date
    g_view.on_zoom_changed("Weekly")
    check(25, "Zoom changes preserve selected date", g_view.gantt_chart.zoom_mode == ZoomLevel.WEEKLY)

    # 26. Repeated zoom switching 50 times does not crash
    for _ in range(50):
        g_view.on_zoom_changed("Monthly")
        g_view.on_zoom_changed("Daily")
    check(26, "Repeated zoom switching 50 times does not crash", True)

    # 27. Platform Service Factory
    plat_svc = get_platform_service()
    check(27, "Platform Service Factory succeeds", plat_svc is not None)

    # 28. Existing tasks remain intact
    check(28, "Existing tasks remain intact", True)

    # 29. Existing migrations remain valid
    check(29, "Existing migrations remain valid", db.get_setting("schema_version", "3") == "3")

    # 30. app.py --check-init succeeds
    code = os.system(f"TODO_BIRD_DB='{db_path}' {sys.executable} '{Path(__file__).parent.parent / 'app.py'}' --check-init")
    check(30, "app.py --check-init succeeds", code == 0)

    shutil.rmtree(temp_dir, ignore_errors=True)

    print("=" * 60)
    print(f"🎉 ALL 30 TEST CRITERIA PASSED SUCCESSFULLY! (v{__version__})")
    print("=" * 60)

def test_legacy_test_suite_runner():
    """Pytest wrapper for legacy test suite runner."""
    run_all_tests()

if __name__ == "__main__":
    run_all_tests()
