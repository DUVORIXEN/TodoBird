import os
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import QApplication

from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.project import Project
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.services.cpm_scheduling_service import CPMSchedulingService
from todo_bird_app.services.schedule_calendar_service import (
    add_working_days_preserve_time,
    subtract_working_days_preserve_time,
)
from todo_bird_app.services.schedule_constraint_service import (
    CalendarException,
    ProjectCalendarSpec,
)
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.widgets.task_dialog import TaskDialog


DAY_MINUTES = 1440
APP_ROOT = Path(__file__).resolve().parents[1]
MON_FRI = (0, 1, 2, 3, 4)
MON_SAT = (0, 1, 2, 3, 4, 5)
SEVEN_DAY = (0, 1, 2, 3, 4, 5, 6)
TUE_SAT = (1, 2, 3, 4, 5)
MON_TUE_THU_SAT = (0, 1, 3, 5)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "duration_authority.db"))
    yield db
    db.close()


@pytest.fixture
def temp_settings(temp_db, tmp_path):
    return SettingsManager(db_manager=temp_db, config_dir=tmp_path / "config")


def dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def _exceptions(items):
    return tuple(
        item
        if isinstance(item, CalendarException)
        else CalendarException.from_dict(item)
        for item in (items or ())
    )


def _spec(weekdays=MON_FRI, exceptions=(), project_id=1):
    return ProjectCalendarSpec(
        project_id=project_id,
        working_weekdays=tuple(weekdays),
        exceptions=_exceptions(exceptions),
    )


def _project(db, weekdays=MON_SAT, exceptions=None, name="SCHEDULING WITNESS FINAL"):
    project_id = db.insert_project({"name": name})
    db.set_project_calendar(
        project_id,
        working_weekdays=list(weekdays),
        calendar_exceptions=list(exceptions or []),
    )
    return project_id, Project.from_row(db.get_project(project_id))


def _task(project_id, *, start_date="2026-09-01", start_time="09:00", duration=0):
    return Task(
        title="Foundation",
        project_id=project_id,
        planned_date=start_date,
        planned_start_time=start_time,
        estimated_duration=duration,
        status=TaskStatus.PLANNED,
        show_in_gantt=True,
    )


def _dialog(db, settings, project, task):
    return TaskDialog(
        projects=[project],
        task=task,
        db_manager=db,
        settings_manager=settings,
    )


def _set_qdate(edit, iso_date: str):
    qdate = QDate.fromString(iso_date, "yyyy-MM-dd")
    assert qdate.isValid()
    edit.setDate(qdate)


def _set_qtime(edit, hhmm: str):
    qtime = QTime.fromString(hhmm, "HH:mm")
    assert qtime.isValid()
    edit.setTime(qtime)


def _assert_dialog_target(dialog, expected: str):
    expected_dt = dt(expected)
    assert dialog.estimated_finish_label.text() == expected
    assert dialog.due_date_edit.date().toString("yyyy-MM-dd") == expected_dt.strftime("%Y-%m-%d")
    assert dialog.end_time_edit.time().toString("HH:mm") == expected_dt.strftime("%H:%M")


def _cpm_task(task_id: int, duration: int, *, start="2026-09-01", clock="09:00", **extra):
    return Task(
        id=task_id,
        title=f"Task {task_id}",
        planned_date=start,
        planned_start_time=clock,
        estimated_duration=duration,
        status=TaskStatus.PLANNED,
        **extra,
    )


DAY_PLACEMENT_CASES = [
    ("mon_sat_human_witness", MON_SAT, (), "2026-09-01 09:00", 5, "2026-09-05 09:00"),
    ("mon_fri_same_input", MON_FRI, (), "2026-09-01 09:00", 5, "2026-09-07 09:00"),
    ("mon_fri_monday_start", MON_FRI, (), "2026-09-07 09:00", 5, "2026-09-11 09:00"),
    ("mon_sat_monday_start", MON_SAT, (), "2026-09-07 09:00", 6, "2026-09-12 09:00"),
    ("seven_day", SEVEN_DAY, (), "2026-09-01 09:00", 5, "2026-09-05 09:00"),
    ("tue_sat", TUE_SAT, (), "2026-09-01 09:00", 5, "2026-09-05 09:00"),
    ("custom_weekdays", MON_TUE_THU_SAT, (), "2026-09-01 09:00", 4, "2026-09-07 09:00"),
    (
        "mon_sat_holiday",
        MON_SAT,
        (CalendarException("2026-09-03", False, "Holiday"),),
        "2026-09-01 09:00",
        5,
        "2026-09-07 09:00",
    ),
    (
        "mon_fri_working_saturday",
        MON_FRI,
        (CalendarException("2026-09-05", True, "Saturday work"),),
        "2026-09-01 09:00",
        5,
        "2026-09-05 09:00",
    ),
    (
        "mon_sat_working_sunday",
        MON_SAT,
        (CalendarException("2026-09-06", True, "Sunday work"),),
        "2026-09-01 09:00",
        6,
        "2026-09-06 09:00",
    ),
    ("weekend_start_mon_fri", MON_FRI, (), "2026-09-06 09:00", 1, "2026-09-07 09:00"),
    ("weekend_start_seven_day", SEVEN_DAY, (), "2026-09-06 09:00", 1, "2026-09-06 09:00"),
    (
        "saturday_override_start",
        MON_FRI,
        (CalendarException("2026-09-05", True, "Saturday work"),),
        "2026-09-05 09:00",
        1,
        "2026-09-05 09:00",
    ),
    ("zero_days", MON_SAT, (), "2026-09-01 09:00", 0, "2026-09-01 09:00"),
    ("ten_day_mon_sat", MON_SAT, (), "2026-09-01 09:00", 10, "2026-09-11 09:00"),
    ("preserves_1330_clock", MON_SAT, (), "2026-09-01 13:30", 5, "2026-09-05 13:30"),
]


@pytest.mark.parametrize(
    "case_name,weekdays,exceptions,start,days,expected",
    DAY_PLACEMENT_CASES,
)
def test_01_add_working_days_preserves_project_calendar_endpoint(
    case_name,
    weekdays,
    exceptions,
    start,
    days,
    expected,
):
    spec = _spec(weekdays, exceptions)
    actual = add_working_days_preserve_time(dt(start), days, spec)
    assert actual == dt(expected), case_name
    if case_name == "mon_sat_human_witness":
        assert actual != dt("2026-09-07 09:00")


SUBTRACT_CASES = [
    ("mon_sat_human_witness", MON_SAT, (), "2026-09-05 09:00", 5, "2026-09-01 09:00"),
    ("mon_fri_same_input", MON_FRI, (), "2026-09-07 09:00", 5, "2026-09-01 09:00"),
    ("mon_fri_monday_finish", MON_FRI, (), "2026-09-11 09:00", 5, "2026-09-07 09:00"),
    ("seven_day", SEVEN_DAY, (), "2026-09-05 09:00", 5, "2026-09-01 09:00"),
    ("tue_sat", TUE_SAT, (), "2026-09-05 09:00", 5, "2026-09-01 09:00"),
    ("custom_weekdays", MON_TUE_THU_SAT, (), "2026-09-07 09:00", 4, "2026-09-01 09:00"),
    (
        "mon_sat_holiday",
        MON_SAT,
        (CalendarException("2026-09-03", False, "Holiday"),),
        "2026-09-07 09:00",
        5,
        "2026-09-01 09:00",
    ),
    (
        "mon_fri_working_saturday",
        MON_FRI,
        (CalendarException("2026-09-05", True, "Saturday work"),),
        "2026-09-05 09:00",
        5,
        "2026-09-01 09:00",
    ),
    (
        "mon_sat_working_sunday",
        MON_SAT,
        (CalendarException("2026-09-06", True, "Sunday work"),),
        "2026-09-06 09:00",
        6,
        "2026-09-01 09:00",
    ),
    ("one_day_mon_fri", MON_FRI, (), "2026-09-07 09:00", 1, "2026-09-07 09:00"),
    ("one_day_seven_day", SEVEN_DAY, (), "2026-09-06 09:00", 1, "2026-09-06 09:00"),
    ("zero_days", MON_SAT, (), "2026-09-01 09:00", 0, "2026-09-01 09:00"),
]


@pytest.mark.parametrize(
    "case_name,weekdays,exceptions,finish,days,expected",
    SUBTRACT_CASES,
)
def test_02_subtract_working_days_preserves_project_calendar_endpoint(
    case_name,
    weekdays,
    exceptions,
    finish,
    days,
    expected,
):
    spec = _spec(weekdays, exceptions)
    actual = subtract_working_days_preserve_time(dt(finish), days, spec)
    assert actual == dt(expected), case_name


@pytest.mark.parametrize(
    "days,minutes,expected",
    [
        (0.5, 720, "2026-09-01 21:00"),
        (1.0, 1440, "2026-09-01 09:00"),
        (1.5, 2160, "2026-09-02 21:00"),
        (2.0, 2880, "2026-09-02 09:00"),
        (5.0, 7200, "2026-09-05 09:00"),
    ],
)
def test_03_task_dialog_fractional_and_whole_day_duration_semantics(
    qapp,
    temp_db,
    temp_settings,
    days,
    minutes,
    expected,
):
    project_id, project = _project(temp_db, MON_SAT)
    dialog = _dialog(temp_db, temp_settings, project, _task(project_id))
    try:
        dialog.duration_days_spin.setValue(days)
        assert dialog.duration_spin.value() == minutes
        _assert_dialog_target(dialog, expected)
    finally:
        dialog.close()


def test_04_human_witness_create_save_reopen_keeps_five_day_mon_sat_target(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    dialog = _dialog(temp_db, temp_settings, project, _task(project_id))
    controller = TaskController(temp_db)
    try:
        dialog.duration_days_spin.setValue(5.0)
        dialog.daily_hours_spin.setValue(4)
        _assert_dialog_target(dialog, "2026-09-05 09:00")
        assert dialog.duration_spin.value() == 7200
        assert dialog.planned_effort_spin.value() == 1200
        assert "Tue, Wed, Thu, Fri, Sat" in dialog.effort_summary_label.text()
        assert "Sep 7" not in dialog.estimated_finish_label.text()

        dialog.on_save()
        task_id = controller.add_task(dialog.get_task())
    finally:
        dialog.close()

    row = temp_db.get_task_by_id(task_id)
    assert row["due_date"] == "2026-09-05"
    assert row["planned_end_time"] == "09:00"
    assert row["estimated_duration"] == 7200
    assert row["planned_effort_minutes"] == 1200

    reopened = _dialog(temp_db, temp_settings, project, controller.get_task(task_id))
    try:
        assert reopened.duration_days_spin.value() == pytest.approx(5.0)
        assert reopened.duration_spin.value() == 7200
        _assert_dialog_target(reopened, "2026-09-05 09:00")
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "case_name,calendar,start,duration,expected",
    [
        ("mon_sat_human_witness", _spec(MON_SAT), "2026-09-01", 7200, "2026-09-05 09:00"),
        ("mon_fri_same_input", _spec(MON_FRI), "2026-09-01", 7200, "2026-09-07 09:00"),
        ("seven_day", _spec(SEVEN_DAY), "2026-09-01", 7200, "2026-09-05 09:00"),
        (
            "mon_sat_holiday",
            _spec(MON_SAT, (CalendarException("2026-09-03", False, "Holiday"),)),
            "2026-09-01",
            7200,
            "2026-09-07 09:00",
        ),
        (
            "mon_fri_working_saturday",
            _spec(MON_FRI, (CalendarException("2026-09-05", True, "Saturday work"),)),
            "2026-09-01",
            7200,
            "2026-09-05 09:00",
        ),
        ("one_day_same_working_date", _spec(MON_SAT), "2026-09-01", 1440, "2026-09-01 09:00"),
        ("two_days_second_working_date", _spec(MON_SAT), "2026-09-01", 2880, "2026-09-02 09:00"),
        ("fractional_stays_minute_based", _spec(MON_SAT), "2026-09-01", 2160, "2026-09-02 21:00"),
        ("weekend_start_normalized", _spec(MON_FRI), "2026-09-06", 1440, "2026-09-07 09:00"),
        ("no_calendar_raw_elapsed_legacy_path", None, "2026-09-01", 7200, "2026-09-06 09:00"),
    ],
)
def test_05_cpm_task_duration_matches_project_calendar_day_authority(
    case_name,
    calendar,
    start,
    duration,
    expected,
):
    task = _cpm_task(1, duration, start=start)
    result = CPMSchedulingService.calculate_schedule([task], project_calendar=calendar)
    node = result.nodes[1]
    assert node.schedulable is True
    assert node.earliest_finish == dt(expected), case_name
    if case_name == "mon_sat_human_witness":
        assert node.earliest_finish != dt("2026-09-07 09:00")


@pytest.mark.parametrize(
    "constraint_type,calendar,constraint_dt,expected_start,expected_finish",
    [
        ("MFO", _spec(MON_SAT), "2026-09-05 09:00", "2026-09-01 09:00", "2026-09-05 09:00"),
        ("FNET", _spec(MON_SAT), "2026-09-05 09:00", "2026-09-01 09:00", "2026-09-05 09:00"),
        (
            "MFO",
            _spec(MON_FRI, (CalendarException("2026-09-05", True, "Saturday work"),)),
            "2026-09-05 09:00",
            "2026-09-01 09:00",
            "2026-09-05 09:00",
        ),
        (
            "FNET",
            _spec(MON_SAT, (CalendarException("2026-09-03", False, "Holiday"),)),
            "2026-09-07 09:00",
            "2026-09-01 09:00",
            "2026-09-07 09:00",
        ),
    ],
)
def test_06_cpm_backward_constraints_use_same_nominal_day_authority(
    constraint_type,
    calendar,
    constraint_dt,
    expected_start,
    expected_finish,
):
    task = _cpm_task(
        1,
        7200,
        constraint_type=constraint_type,
        constraint_datetime=constraint_dt,
    )
    result = CPMSchedulingService.calculate_schedule([task], project_calendar=calendar)
    node = result.nodes[1]
    assert node.schedulable is True
    assert node.earliest_start == dt(expected_start)
    assert node.earliest_finish == dt(expected_finish)


def test_07_dialog_switching_selected_project_recalculates_target_from_project_calendar(
    qapp,
    temp_db,
    temp_settings,
):
    mon_fri_id, mon_fri_project = _project(temp_db, MON_FRI, name="Mon Fri Project")
    mon_sat_id, mon_sat_project = _project(temp_db, MON_SAT, name="Mon Sat Project")
    dialog = TaskDialog(
        projects=[mon_fri_project, mon_sat_project],
        task=_task(mon_fri_id),
        db_manager=temp_db,
        settings_manager=temp_settings,
    )
    try:
        dialog.duration_days_spin.setValue(5.0)
        _assert_dialog_target(dialog, "2026-09-07 09:00")

        idx = dialog.project_combo.findData(mon_sat_id)
        assert idx >= 0
        dialog.project_combo.setCurrentIndex(idx)
        _assert_dialog_target(dialog, "2026-09-05 09:00")

        _set_qdate(dialog.planned_date_edit, "2026-09-07")
        _set_qtime(dialog.start_time_edit, "09:00")
        _assert_dialog_target(dialog, "2026-09-11 09:00")
    finally:
        dialog.close()


def test_08_duration_authority_source_guard():
    task_dialog = (APP_ROOT / "widgets" / "task_dialog.py").read_text(encoding="utf-8")
    cpm = (APP_ROOT / "services" / "cpm_scheduling_service.py").read_text(encoding="utf-8")
    assert "add_working_days_preserve_time" in task_dialog
    assert "add_working_days_preserve_time" in cpm
    assert "subtract_working_days_preserve_time" in cpm
    assert "clean_duration - self.ESTIMATED_DAY_MINUTES" not in task_dialog
    assert "calendar_enabled and is_nominal_whole_day_duration" in cpm
