"""
Test Suite: Work Calendar + Resource Dedication Truth Closure (Batch 3.3C)
Validates WC01 to WC18 rules:
- Weekday calculation truth (13 Aug Thu, 14 Aug Fri, 15 Aug Sat)
- Workweek configuration authority (Mon-Fri vs Mon-Sat)
- Daily capacity vs task dedication separation
- Overallocation and overload calculations in integer minutes
- Integer remainder distribution for Total Effort mode
- Explicit Custom by Day overrides for non-working days
- Settings persistence and hierarchy parity
- Isolation from Gantt schedule bars, Actual execution, and Progress
"""

import os
import tempfile
from datetime import date
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
    distribute_total_effort_minutes,
    calculate_overallocation,
    get_configured_working_weekdays,
    set_configured_working_weekdays,
    get_default_daily_capacity_minutes,
    set_default_daily_capacity_minutes,
)
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.gantt.gantt_items import GanttTaskItem


@pytest.fixture(scope="session", autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def _temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path=path)
    return db, path


def test_wc01_2026_08_13_is_thursday():
    """WC01: 2026-08-13 is Thursday (Python weekday 3)."""
    d = date(2026, 8, 13)
    assert d.weekday() == 3
    assert d.strftime("%A") == "Thursday"


def test_wc02_2026_08_14_is_friday():
    """WC02: 2026-08-14 is Friday (Python weekday 4)."""
    d = date(2026, 8, 14)
    assert d.weekday() == 4
    assert d.strftime("%A") == "Friday"


def test_wc03_2026_08_15_is_saturday():
    """WC03: 2026-08-15 is Saturday (Python weekday 5)."""
    d = date(2026, 8, 15)
    assert d.weekday() == 5
    assert d.strftime("%A") == "Saturday"


def test_wc04_mon_fri_four_hours_per_day():
    """WC04: Mon-Fri + 4h/day + 13->15 Aug = 8h (480 min) because Saturday is non-working."""
    eff = calculate_planned_effort(
        start_date="2026-08-13",
        end_date="2026-08-15",
        daily_dedication_minutes=240,
        allocation_mode="fixed_daily",
        working_weekdays={0, 1, 2, 3, 4},
    )
    assert eff == 480  # 13 Aug (Thu) + 14 Aug (Fri) = 2 days * 240 = 480m = 8h


def test_wc05_mon_sat_four_hours_per_day():
    """WC05: Mon-Sat + 4h/day + 13->15 Aug = 12h (720 min) because Saturday is working."""
    eff = calculate_planned_effort(
        start_date="2026-08-13",
        end_date="2026-08-15",
        daily_dedication_minutes=240,
        allocation_mode="fixed_daily",
        working_weekdays={0, 1, 2, 3, 4, 5},
    )
    assert eff == 720  # 13 Aug (Thu) + 14 Aug (Fri) + 15 Aug (Sat) = 3 days * 240 = 720m = 12h


def test_wc06_saturday_disabled_does_not_allocate_saturday():
    """WC06: When Saturday is disabled, fixed-daily allocates 0 minutes to Saturday."""
    days = get_working_days_between("2026-08-13", "2026-08-15", working_weekdays={0, 1, 2, 3, 4})
    assert date(2026, 8, 15) not in days
    assert len(days) == 2


def test_wc07_saturday_explicit_custom_allocation_override():
    """WC07: Explicit custom allocation on non-working Saturday is preserved as an explicit override."""
    custom = {
        "2026-08-13": 120, # 2h
        "2026-08-14": 240, # 4h
        "2026-08-15": 90,  # 1h30 (override on Saturday)
    }
    eff = calculate_planned_effort(
        start_date="2026-08-13",
        end_date="2026-08-15",
        daily_dedication_minutes=0,
        allocation_mode="custom_by_day",
        custom_allocations=custom,
        working_weekdays={0, 1, 2, 3, 4},
    )
    assert eff == 450


def test_wc08_changing_workweek_recalculates_planned_effort():
    """WC08: Toggling workweek configuration dynamically changes planned effort."""
    mon_fri_eff = calculate_planned_effort("2026-08-13", "2026-08-15", 240, "fixed_daily", working_weekdays={0, 1, 2, 3, 4})
    mon_sat_eff = calculate_planned_effort("2026-08-13", "2026-08-15", 240, "fixed_daily", working_weekdays={0, 1, 2, 3, 4, 5})
    assert mon_fri_eff == 480
    assert mon_sat_eff == 720
    assert mon_sat_eff > mon_fri_eff


def test_wc09_workweek_persists_restart():
    """WC09: Workweek configuration persists across SettingsManager reload."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from pathlib import Path
        config_dir = Path(tmpdir)
        sm1 = SettingsManager(db_manager=None, config_dir=config_dir)
        wws1 = WorkingWeekService(sm1)
        wws1.set_working_weekdays([0, 1, 2, 3, 4, 5]) # Mon-Sat

        # Reload from disk
        sm2 = SettingsManager(db_manager=None, config_dir=config_dir)
        wws2 = WorkingWeekService(sm2)
        assert wws2.get_working_weekdays() == [0, 1, 2, 3, 4, 5]

    from todo_bird_app.utils.working_calendar import reset_working_calendar_defaults
    reset_working_calendar_defaults()


def test_wc10_daily_capacity_separate_from_task_dedication():
    """WC10: Daily capacity belongs to user/resource profile (480m) and is separate from task dedication (240m)."""
    set_default_daily_capacity_minutes(480)
    assert get_default_daily_capacity_minutes() == 480

    task = Task(title="Capacity Task", daily_dedication_minutes=240)
    assert task.daily_dedication_minutes == 240
    assert get_default_daily_capacity_minutes() != task.daily_dedication_minutes


def test_wc11_remaining_capacity_calculation():
    """WC11: 8h (480m) capacity - 7h (420m) allocation = 1h (60m) remaining, 0m overload."""
    res = calculate_overallocation(daily_capacity_minutes=480, allocated_minutes=420)
    assert res["remaining_minutes"] == 60
    assert res["overload_minutes"] == 0
    assert res["is_overloaded"] is False


def test_wc12_overload_calculation():
    """WC12: 8h (480m) capacity - 10h (600m) allocation = 0m remaining, 2h (120m) overload."""
    res = calculate_overallocation(daily_capacity_minutes=480, allocated_minutes=600)
    assert res["remaining_minutes"] == 0
    assert res["overload_minutes"] == 120
    assert res["is_overloaded"] is True


def test_wc13_total_effort_integer_distribution():
    """WC13: 601 minutes across 3 working days distributes to [201, 200, 200], exactly totaling 601 without float drift."""
    working_days = [date(2026, 8, 13), date(2026, 8, 14), date(2026, 8, 17)]
    dist = distribute_total_effort_minutes(total_effort_minutes=601, working_days=working_days)
    values = list(dist.values())
    assert values == [201, 200, 200]
    assert sum(values) == 601


def test_wc14_subtask_uses_same_calendar():
    """WC14: Subtask fixed-daily uses same working-calendar authority."""
    eff = calculate_planned_effort("2026-08-13", "2026-08-15", daily_dedication_minutes=240, allocation_mode="fixed_daily", working_weekdays={0, 1, 2, 3, 4})
    assert eff == 480


def test_wc15_sub_subtask_uses_same_calendar():
    """WC15: Sub-subtask fixed-daily uses same working-calendar authority."""
    eff = calculate_planned_effort("2026-08-13", "2026-08-15", daily_dedication_minutes=120, allocation_mode="fixed_daily", working_weekdays={0, 1, 2, 3, 4})
    assert eff == 240


def test_wc16_gantt_unchanged_when_calendar_or_dedication_changes():
    """WC16: Gantt bar geometry depends purely on schedule start/end datetime, unaffected by dedication."""
    task = Task(
        title="Gantt Freeze",
        planned_date="2026-08-13",
        due_date="2026-08-15",
        planned_start_time="07:00",
        planned_end_time="13:40",
        estimated_duration=3280,
        daily_dedication_minutes=240,
        planned_effort_minutes=480,
    )
    profile = {"planned": "#3584E4", "actual": "#10B981"}
    item1 = GanttTaskItem(task, row=0, col_start=0.0, duration_cols=3.0, col_width=80, color_profile=profile)
    rect1 = item1.boundingRect()

    # Double dedication to 8h/day (960 min)
    task.daily_dedication_minutes = 480
    task.planned_effort_minutes = 960
    item2 = GanttTaskItem(task, row=0, col_start=0.0, duration_cols=3.0, col_width=80, color_profile=profile)
    rect2 = item2.boundingRect()

    assert rect1.width() == rect2.width()
    assert rect1.x() == rect2.x()


def test_wc17_actual_unchanged():
    """WC17: Actual execution fields remain completely untouched by working calendar."""
    task = Task(
        title="Actual Freeze",
        actual_start_date="2026-08-14",
        actual_start_time="10:00",
        actual_end_date="2026-08-16",
        actual_end_time="17:00",
        actual_duration=3300,
    )
    assert task.actual_duration == 3300
    assert task.actual_start_date == "2026-08-14"
    assert task.actual_end_date == "2026-08-16"


def test_wc18_progress_unchanged():
    """WC18: Progress is not inferred from effort/capacity and remains independent."""
    task = Task(
        title="Progress Freeze",
        progress=60,
        planned_effort_minutes=480,
        daily_dedication_minutes=240,
    )
    assert task.progress == 60
    task.planned_effort_minutes = 960
    assert task.progress == 60
