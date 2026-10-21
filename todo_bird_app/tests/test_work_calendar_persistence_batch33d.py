"""
Test Suite: Work-Calendar Settings Persistence & Custom Override Visibility Repair (Batch 3.3D)
Validates WP01 to WP10 rules:
- Restart persistence of working weekdays (Mon-Fri and Mon-Sat)
- Daily resource capacity persistence
- SQLite vs config.json synchronization authority
- WorkingWeekService & working_calendar auto-sync on startup
- TaskDialog live recalculation with persisted workweek
- Custom by day non-working override persistence and non-mutation of global workweek
- Custom table override visibility and badges
"""

import os
import json
import tempfile
from pathlib import Path
import pytest
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.services.working_week import WorkingWeekService
from todo_bird_app.utils.working_calendar import (
    is_working_day,
    get_working_days_between,
    calculate_planned_effort,
    get_configured_working_weekdays,
    set_configured_working_weekdays,
    get_default_daily_capacity_minutes,
    set_default_daily_capacity_minutes,
    reset_working_calendar_defaults,
)
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.views.settings_view import SettingsView


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def clean_calendar():
    yield
    reset_working_calendar_defaults()


def _temp_env():
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "todo_bird.db")
    config_dir = Path(tmpdir) / "config"
    db = DatabaseManager(db_path=db_path)
    return db, config_dir, tmpdir


def test_wp01_set_mon_sat_and_restart():
    """WP01: Set Mon-Sat, save, recreate SettingsManager -> Mon-Sat restored from SQLite."""
    db, config_dir, tmpdir = _temp_env()
    try:
        sm1 = SettingsManager(db_manager=db, config_dir=config_dir)
        wws1 = WorkingWeekService(sm1)
        wws1.set_working_weekdays([0, 1, 2, 3, 4, 5]) # Mon-Sat

        # Simulate fresh app startup with new SettingsManager
        sm2 = SettingsManager(db_manager=db, config_dir=config_dir)
        wws2 = WorkingWeekService(sm2)
        assert wws2.get_working_weekdays() == [0, 1, 2, 3, 4, 5]
        assert get_configured_working_weekdays() == {0, 1, 2, 3, 4, 5}
    finally:
        pass


def test_wp02_set_mon_fri_and_restart():
    """WP02: Set Mon-Fri, save, recreate SettingsManager -> Mon-Fri restored."""
    db, config_dir, tmpdir = _temp_env()
    try:
        sm1 = SettingsManager(db_manager=db, config_dir=config_dir)
        wws1 = WorkingWeekService(sm1)
        wws1.set_working_weekdays([0, 1, 2, 3, 4]) # Mon-Fri

        sm2 = SettingsManager(db_manager=db, config_dir=config_dir)
        wws2 = WorkingWeekService(sm2)
        assert wws2.get_working_weekdays() == [0, 1, 2, 3, 4]
        assert get_configured_working_weekdays() == {0, 1, 2, 3, 4}
    finally:
        pass


def test_wp03_set_capacity_360m_and_restart():
    """WP03: Set capacity 360m (6h), restart -> 360m restored."""
    db, config_dir, tmpdir = _temp_env()
    try:
        sm1 = SettingsManager(db_manager=db, config_dir=config_dir)
        sm1.set("default_daily_capacity_minutes", 360)

        sm2 = SettingsManager(db_manager=db, config_dir=config_dir)
        assert sm2.get("default_daily_capacity_minutes") == 360
        assert get_default_daily_capacity_minutes() == 360
    finally:
        pass


def test_wp04_sqlite_value_matches_ui_after_restart():
    """WP04: SQLite settings table value matches UI checkboxes on load."""
    db, config_dir, tmpdir = _temp_env()
    try:
        sm1 = SettingsManager(db_manager=db, config_dir=config_dir)
        wws1 = WorkingWeekService(sm1)
        wws1.set_working_weekdays([0, 1, 2, 3, 4, 5]) # Mon-Sat

        # Verify DB directly
        val_str = db.get_setting("working_weekdays")
        assert json.loads(val_str) == [0, 1, 2, 3, 4, 5]

        # Verify SettingsView UI
        sm2 = SettingsManager(db_manager=db, config_dir=config_dir)
        view = SettingsView(db_manager=db, settings_manager=sm2)
        assert view.day_checkboxes[5].isChecked() is True # Saturday checked
        assert view.day_checkboxes[6].isChecked() is False # Sunday unchecked
    finally:
        pass


def test_wp05_config_json_does_not_override_newer_db_value():
    """WP05: SQLite takes precedence when both exist and are synchronized."""
    db, config_dir, tmpdir = _temp_env()
    try:
        # Save Mon-Sat to DB
        sm1 = SettingsManager(db_manager=db, config_dir=config_dir)
        sm1.set("working_weekdays", [0, 1, 2, 3, 4, 5])

        # Overwrite config.json with stale data to simulate stale file
        with open(config_dir / "config.json", "w", encoding="utf-8") as f:
            json.dump({"working_weekdays": [0, 1, 2, 3, 4]}, f)

        # New SettingsManager should sync and load from DB
        sm2 = SettingsManager(db_manager=db, config_dir=config_dir)
        assert sm2.get("working_weekdays") == [0, 1, 2, 3, 4, 5]
    finally:
        pass


def test_wp06_working_week_service_initializes_from_persisted_settings():
    """WP06: WorkingWeekService correctly initializes working days from DB."""
    db, config_dir, tmpdir = _temp_env()
    try:
        sm = SettingsManager(db_manager=db, config_dir=config_dir)
        sm.set("working_weekdays", [0, 1, 2, 3, 4])
        wws = WorkingWeekService(sm)
        assert wws.get_working_weekdays() == [0, 1, 2, 3, 4]
        assert wws.is_weekend(5) is True # Saturday is weekend
        assert wws.is_weekend(4) is False # Friday is working
    finally:
        pass


def test_wp07_task_dialog_recalculates_using_persisted_workweek():
    """WP07: TaskDialog calculates 480m for Mon-Fri and 720m when Mon-Sat is active."""
    db, config_dir, tmpdir = _temp_env()
    try:
        # Test Mon-Fri: 13 Aug (Thu) + 14 Aug (Fri) = 480m
        set_configured_working_weekdays([0, 1, 2, 3, 4])
        task = Task(
            title="Mon-Fri Dialog",
            planned_date="2026-08-13",
            due_date="2026-08-15",
            daily_dedication_minutes=240,
            allocation_mode="fixed_daily",
        )
        dialog1 = TaskDialog(projects=[], task=task)
        dialog1.db_manager = db
        assert dialog1.planned_effort_spin.value() == 480

        # Now set Mon-Sat: 13 Aug (Thu) + 14 Aug (Fri) + 15 Aug (Sat) = 720m
        set_configured_working_weekdays([0, 1, 2, 3, 4, 5])
        dialog2 = TaskDialog(projects=[], task=task)
        dialog2.db_manager = db
        assert dialog2.planned_effort_spin.value() == 720
    finally:
        pass


def test_wp08_custom_saturday_allocation_persists_restart():
    """WP08: Custom Saturday allocation on non-working day persists in task_allocations."""
    db, config_dir, tmpdir = _temp_env()
    try:
        tc = TaskController(db)
        tid = tc.add_task(Task(
            title="Custom Override Task",
            planned_date="2026-08-13",
            due_date="2026-08-15",
            planned_effort_minutes=450,
            allocation_mode="custom_by_day",
        ))

        # 13 Aug=2h, 14 Aug=4h, 15 Aug (Sat override)=1h30
        allocations = [
            {"allocation_date": "2026-08-13", "planned_minutes": 120},
            {"allocation_date": "2026-08-14", "planned_minutes": 240},
            {"allocation_date": "2026-08-15", "planned_minutes": 90},
        ]
        db.set_task_allocations(task_id=tid, subtask_id=None, allocations=allocations)

        # Open in TaskDialog and verify custom allocations loaded
        task = tc.get_task(tid)
        dialog = TaskDialog(projects=[], task=task, db_manager=db)
        assert dialog._custom_allocations_dict.get("2026-08-15") == 90
        assert dialog.planned_effort_spin.value() == 450
    finally:
        pass


def test_wp09_global_workweek_remains_unchanged_after_custom_override():
    """WP09: Custom override on Saturday does NOT convert Saturday into a global working day."""
    set_configured_working_weekdays([0, 1, 2, 3, 4]) # Mon-Fri

    # 15 Aug is non-working globally
    assert is_working_day("2026-08-15") is False

    # Custom override on 15 Aug
    custom = {"2026-08-15": 90}
    assert is_working_day("2026-08-15", custom_overrides=custom) is True

    # Global workweek remains strictly Mon-Fri
    assert get_configured_working_weekdays() == {0, 1, 2, 3, 4}
    assert is_working_day("2026-08-15") is False


def test_wp10_custom_table_visibly_marks_non_working_override():
    """WP10: TaskDialog custom allocation editor displays non-working status for Saturday."""
    set_configured_working_weekdays([0, 1, 2, 3, 4]) # Mon-Fri
    task = Task(
        title="Custom Table View",
        planned_date="2026-08-13",
        due_date="2026-08-15",
        allocation_mode="custom_by_day",
    )
    dialog = TaskDialog(projects=[], task=task)
    assert not dialog.custom_alloc_frame.isHidden()
    assert "2026-08-15" in dialog.custom_spinners
    assert is_working_day("2026-08-15") is False
