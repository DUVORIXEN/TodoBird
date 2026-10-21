import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QDate, QTime, Qt
from PySide6.QtWidgets import QApplication, QLabel

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.project import Project
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.services.cpm_scheduling_service import CPMSchedulingService
from todo_bird_app.services.schedule_calendar_service import (
    ScheduleCalendar,
    add_working_days_preserve_time,
    classify_calendar_date,
    effective_project_calendar_from_db,
    project_calendar_spec_from_source,
)
from todo_bird_app.services.schedule_constraint_service import (
    CalendarException,
    ProjectCalendarSpec,
)
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.widgets.project_calendar_dialog import ProjectCalendarDialog
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.work_effort_editor import WorkEffortEditor


APP_ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_DB = APP_ROOT / "data" / "todo_bird.db"
DAY_MINUTES = 1440
MON_FRI = (0, 1, 2, 3, 4)
MON_SAT = (0, 1, 2, 3, 4, 5)
SEVEN_DAY = (0, 1, 2, 3, 4, 5, 6)
WEEKEND_ONLY = (5, 6)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "calendar_live_authority.db"))
    yield db
    db.close()


@pytest.fixture
def temp_settings(temp_db, tmp_path):
    return SettingsManager(db_manager=temp_db, config_dir=tmp_path / "config")


def dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M")


def set_db_workdays(db, weekdays):
    db.set_setting("working_weekdays", json.dumps(list(weekdays)))


def project(db, *, name="SCHEDULING WITNESS FINAL", weekdays=None, exceptions=None):
    project_id = db.insert_project({"name": name})
    if weekdays is not None:
        db.set_project_calendar(
            project_id,
            working_weekdays=list(weekdays),
            calendar_exceptions=list(exceptions or []),
        )
    return project_id, Project.from_row(db.get_project(project_id))


def task(project_id, *, due_date=None, end_time=None, duration=0):
    return Task(
        title="Foundation",
        project_id=project_id,
        planned_date="2026-09-01",
        planned_start_time="09:00",
        due_date=due_date,
        planned_end_time=end_time,
        estimated_duration=duration,
        status=TaskStatus.PLANNED,
        show_in_gantt=True,
    )


def assert_dialog_target(dialog, expected: str):
    expected_dt = dt(expected)
    assert dialog.estimated_finish_label.text() == expected
    assert dialog.due_date_edit.date().toString("yyyy-MM-dd") == expected_dt.strftime("%Y-%m-%d")
    assert dialog.end_time_edit.time().toString("HH:mm") == expected_dt.strftime("%H:%M")


def close_widget(widget):
    cleanup = getattr(widget, "cleanup", None)
    if callable(cleanup):
        cleanup()
    widget.close()
    widget.deleteLater()


def status_for(editor, iso_date: str) -> str:
    start = datetime.strptime(editor.start_date_str, "%Y-%m-%d").date()
    target = datetime.strptime(iso_date, "%Y-%m-%d").date()
    row = (target - start).days + 1
    item = editor.grid_layout.itemAtPosition(row, 2)
    assert item is not None
    widget = item.widget()
    assert isinstance(widget, QLabel)
    return widget.text()


CALENDAR_SHAPE_CASES = [
    (
        "db_dict_list_weekdays",
        {"working_weekdays": list(MON_SAT), "calendar_exceptions": []},
        MON_SAT,
        (),
        (),
        "2026-09-05",
        True,
    ),
    (
        "db_dict_json_weekdays",
        {"working_weekdays": json.dumps(list(MON_SAT)), "calendar_exceptions": "[]"},
        MON_SAT,
        (),
        (),
        "2026-09-05",
        True,
    ),
    (
        "db_dict_working_exception",
        {"working_weekdays": list(MON_FRI), "calendar_exceptions": [{"date": "2026-09-05", "is_working": True}]},
        MON_FRI,
        (),
        ("2026-09-05",),
        "2026-09-05",
        True,
    ),
    (
        "db_dict_holiday_exception",
        {"working_weekdays": list(MON_SAT), "calendar_exceptions": [{"date": "2026-09-05", "is_working": False, "name": "Holiday"}]},
        MON_SAT,
        ("2026-09-05",),
        (),
        "2026-09-05",
        False,
    ),
    (
        "project_calendar_spec",
        ProjectCalendarSpec(working_weekdays=MON_SAT),
        MON_SAT,
        (),
        (),
        "2026-09-05",
        True,
    ),
    (
        "schedule_calendar",
        ScheduleCalendar(working_weekdays=MON_SAT),
        MON_SAT,
        (),
        (),
        "2026-09-05",
        True,
    ),
    (
        "project_model_calendar",
        Project(id=7, name="P", working_weekdays=list(MON_SAT), calendar_exceptions=[{"date": "2026-09-06", "is_working": True}]),
        MON_SAT,
        (),
        ("2026-09-06",),
        "2026-09-06",
        True,
    ),
    (
        "exception_date_key",
        {"working_weekdays": list(MON_FRI), "calendar_exceptions": [{"exception_date": "2026-09-05", "is_working": 1}]},
        MON_FRI,
        (),
        ("2026-09-05",),
        "2026-09-05",
        True,
    ),
    (
        "duplicate_last_non_working_wins",
        {"working_weekdays": list(MON_SAT), "calendar_exceptions": [{"date": "2026-09-05", "is_working": True}, {"date": "2026-09-05", "is_working": False}]},
        MON_SAT,
        ("2026-09-05",),
        (),
        "2026-09-05",
        False,
    ),
    (
        "duplicate_last_working_wins",
        {"working_weekdays": list(MON_FRI), "calendar_exceptions": [{"date": "2026-09-05", "is_working": False}, {"date": "2026-09-05", "is_working": True}]},
        MON_FRI,
        (),
        ("2026-09-05",),
        "2026-09-05",
        True,
    ),
    (
        "string_boolean_false",
        {"working_weekdays": list(MON_SAT), "calendar_exceptions": [{"date": "2026-09-05", "is_working": "false", "name": "Holiday"}]},
        MON_SAT,
        ("2026-09-05",),
        (),
        "2026-09-05",
        False,
    ),
    (
        "empty_weekdays_falls_back_to_default",
        {"working_weekdays": [], "calendar_exceptions": []},
        MON_FRI,
        (),
        (),
        "2026-09-05",
        False,
    ),
]


@pytest.mark.parametrize(
    "case_name,source,expected_weekdays,expected_holidays,expected_overrides,check_date,expected_working",
    CALENDAR_SHAPE_CASES,
)
def test_01_schedule_calendar_accepts_live_calendar_shapes(
    case_name,
    source,
    expected_weekdays,
    expected_holidays,
    expected_overrides,
    check_date,
    expected_working,
):
    calendar = ScheduleCalendar.from_project_calendar(source)
    assert calendar.working_weekdays == expected_weekdays, case_name
    assert calendar.holidays == frozenset(expected_holidays), case_name
    assert calendar.working_overrides == frozenset(expected_overrides), case_name
    assert calendar.is_working_day(check_date) is expected_working, case_name


STATUS_LABEL_CASES = [
    (ProjectCalendarSpec(working_weekdays=MON_SAT), "2026-09-05", "Working", True, "weekday_rule"),
    (ProjectCalendarSpec(working_weekdays=MON_FRI), "2026-09-05", "Non-working", False, "weekday_rule"),
    (ProjectCalendarSpec(working_weekdays=SEVEN_DAY), "2026-09-06", "Working", True, "weekday_rule"),
    (ProjectCalendarSpec(working_weekdays=MON_FRI, exceptions=(CalendarException("2026-09-05", True, "Saturday work"),)), "2026-09-05", "Working override", True, "calendar_exception"),
    (ProjectCalendarSpec(working_weekdays=MON_SAT, exceptions=(CalendarException("2026-09-05", False, "National Holiday"),)), "2026-09-05", "Holiday", False, "calendar_exception"),
    (ProjectCalendarSpec(working_weekdays=MON_SAT, exceptions=(CalendarException("2026-09-05", False, "Site shutdown"),)), "2026-09-05", "Non-working exception", False, "calendar_exception"),
    ({"working_weekdays": list(MON_FRI), "calendar_exceptions": [{"date": "2026-09-06", "is_working": True, "name": "Sunday work"}]}, "2026-09-06", "Working override", True, "calendar_exception"),
    ({"working_weekdays": list(MON_SAT), "calendar_exceptions": [{"date": "2026-09-05", "is_working": False, "name": ""}]}, "2026-09-05", "Non-working exception", False, "calendar_exception"),
    ({"working_weekdays": list(MON_SAT), "calendar_exceptions": [{"date": "2026-09-05", "is_working": True}, {"date": "2026-09-05", "is_working": False, "name": "Holiday"}]}, "2026-09-05", "Holiday", False, "calendar_exception"),
    ({"working_weekdays": list(MON_FRI), "calendar_exceptions": [{"date": "2026-09-05", "is_working": False}, {"date": "2026-09-05", "is_working": True}]}, "2026-09-05", "Working override", True, "calendar_exception"),
    (ScheduleCalendar(working_weekdays=MON_FRI, working_overrides=frozenset({"2026-09-05"})), "2026-09-05", "Working override", True, "calendar_exception"),
    (ScheduleCalendar(working_weekdays=MON_SAT, holidays=frozenset({"2026-09-05"})), "2026-09-05", "Holiday", False, "calendar_exception"),
]


@pytest.mark.parametrize(
    "source,check_date,expected_label,expected_working,expected_source",
    STATUS_LABEL_CASES,
)
def test_02_calendar_status_labels_distinguish_weekday_holiday_exception_and_override(
    source,
    check_date,
    expected_label,
    expected_working,
    expected_source,
):
    status = classify_calendar_date(source, check_date)
    assert status.label == expected_label
    assert status.is_working is expected_working
    assert status.source == expected_source


@pytest.mark.parametrize(
    "global_weekdays,expected_weekdays,expected_finish",
    [
        (MON_FRI, MON_FRI, "2026-09-07 09:00"),
        (MON_SAT, MON_SAT, "2026-09-05 09:00"),
        (SEVEN_DAY, SEVEN_DAY, "2026-09-05 09:00"),
        (WEEKEND_ONLY, WEEKEND_ONLY, "2026-09-19 09:00"),
        ((0, 2, 4), (0, 2, 4), "2026-09-11 09:00"),
        ((1, 3, 5), (1, 3, 5), "2026-09-10 09:00"),
    ],
)
def test_03_null_project_calendar_inherits_global_working_week(
    temp_db,
    global_weekdays,
    expected_weekdays,
    expected_finish,
):
    set_db_workdays(temp_db, global_weekdays)
    project_id, _project = project(temp_db, weekdays=None)

    spec = effective_project_calendar_from_db(temp_db, project_id)
    finish = add_working_days_preserve_time(dt("2026-09-01 09:00"), 5, spec)

    assert spec.working_weekdays == expected_weekdays
    assert finish == dt(expected_finish)


def test_04_explicit_project_calendar_overrides_global_setting(temp_db):
    set_db_workdays(temp_db, MON_SAT)
    project_id, _project = project(temp_db, weekdays=MON_FRI)

    spec = effective_project_calendar_from_db(temp_db, project_id)

    assert spec.working_weekdays == MON_FRI
    assert classify_calendar_date(spec, "2026-09-05").label == "Non-working"


def test_05_project_calendar_exceptions_survive_global_fallback(temp_db):
    set_db_workdays(temp_db, MON_SAT)
    project_id, _project = project(
        temp_db,
        weekdays=None,
        exceptions=None,
    )
    temp_db.add_project_calendar_exception(project_id, "2026-09-05", is_working=False, name="National Holiday")

    spec = effective_project_calendar_from_db(temp_db, project_id)

    assert spec.working_weekdays == MON_SAT
    status = classify_calendar_date(spec, "2026-09-05")
    assert status.label == "Holiday"
    assert status.is_working is False


def test_06_new_task_dialog_uses_global_fallback_when_project_calendar_is_null(
    qapp,
    temp_db,
    temp_settings,
):
    temp_settings.set("working_weekdays", list(MON_SAT))
    project_id, project_model = project(temp_db, weekdays=None)
    dialog = TaskDialog(
        projects=[project_model],
        task=task(project_id),
        db_manager=temp_db,
        settings_manager=temp_settings,
    )
    try:
        dialog.duration_days_spin.setValue(5.0)
        assert_dialog_target(dialog, "2026-09-05 09:00")
    finally:
        close_widget(dialog)


def test_07_reopened_task_normalizes_stale_saved_finish_from_effective_calendar(
    qapp,
    temp_db,
    temp_settings,
):
    temp_settings.set("working_weekdays", list(MON_SAT))
    project_id, project_model = project(temp_db, weekdays=None)
    task_id = temp_db.insert_task(
        task(
            project_id,
            due_date="2026-09-07",
            end_time="09:00",
            duration=5 * DAY_MINUTES,
        ).to_dict()
    )
    dialog = TaskDialog(
        projects=[project_model],
        task=Task.from_row(temp_db.get_task_by_id(task_id)),
        db_manager=temp_db,
        settings_manager=temp_settings,
    )
    try:
        assert_dialog_target(dialog, "2026-09-05 09:00")
        dialog.on_save()
        saved = dialog.get_task()
    finally:
        close_widget(dialog)

    assert saved.due_date == "2026-09-05"
    assert saved.planned_end_time == "09:00"
    assert saved.estimated_duration == 5 * DAY_MINUTES


def test_08_open_dialog_recalculates_when_project_calendar_changes(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project_model = project(temp_db, weekdays=MON_FRI)
    dialog = TaskDialog(
        projects=[project_model],
        task=task(project_id),
        db_manager=temp_db,
        settings_manager=temp_settings,
    )
    try:
        dialog.duration_days_spin.setValue(5.0)
        assert_dialog_target(dialog, "2026-09-07 09:00")
        temp_db.set_project_calendar(project_id, list(MON_SAT), [])
        QApplication.processEvents()
        assert_dialog_target(dialog, "2026-09-05 09:00")
    finally:
        close_widget(dialog)


def test_09_open_dialog_recalculates_when_global_calendar_changes_for_null_project(
    qapp,
    temp_db,
    temp_settings,
):
    temp_settings.set("working_weekdays", list(MON_FRI))
    project_id, project_model = project(temp_db, weekdays=None)
    dialog = TaskDialog(
        projects=[project_model],
        task=task(project_id),
        db_manager=temp_db,
        settings_manager=temp_settings,
    )
    try:
        dialog.duration_days_spin.setValue(5.0)
        assert_dialog_target(dialog, "2026-09-07 09:00")
        temp_settings.set("working_weekdays", list(MON_SAT))
        QApplication.processEvents()
        assert_dialog_target(dialog, "2026-09-05 09:00")
    finally:
        close_widget(dialog)


def test_10_dialog_opened_after_global_calendar_change_uses_new_setting(
    qapp,
    temp_db,
    temp_settings,
):
    temp_settings.set("working_weekdays", list(MON_SAT))
    project_id, project_model = project(temp_db, weekdays=None)
    dialog = TaskDialog(
        projects=[project_model],
        task=task(project_id),
        db_manager=temp_db,
        settings_manager=temp_settings,
    )
    try:
        dialog.duration_days_spin.setValue(5.0)
        assert_dialog_target(dialog, "2026-09-05 09:00")
    finally:
        close_widget(dialog)


def test_11_task_dialog_work_effort_uses_same_global_fallback_calendar(
    qapp,
    temp_db,
    temp_settings,
):
    temp_settings.set("working_weekdays", list(MON_SAT))
    project_id, project_model = project(temp_db, weekdays=None)
    dialog = TaskDialog(
        projects=[project_model],
        task=task(project_id),
        db_manager=temp_db,
        settings_manager=temp_settings,
    )
    try:
        dialog.duration_days_spin.setValue(5.0)
        dialog.daily_hours_spin.setValue(4)
        assert dialog.planned_effort_spin.value() == 1200
        assert "Tue, Wed, Thu, Fri, Sat" in dialog.effort_summary_label.text()
    finally:
        close_widget(dialog)


WORK_EFFORT_LABEL_CASES = [
    ("2026-09-01", "Working"),
    ("2026-09-05", "Working"),
    ("2026-09-06", "Non-working"),
    ("2026-09-07", "Holiday"),
    ("2026-09-13", "Working override"),
]


@pytest.mark.parametrize("iso_date,expected_label", WORK_EFFORT_LABEL_CASES)
def test_12_work_effort_editor_calendar_status_labels_are_not_generic_holidays(
    qapp,
    iso_date,
    expected_label,
):
    spec = ProjectCalendarSpec(
        working_weekdays=MON_SAT,
        exceptions=(
            CalendarException("2026-09-07", False, "National Holiday"),
            CalendarException("2026-09-13", True, "Sunday pour"),
        ),
    )
    editor = WorkEffortEditor(
        start_date="2026-09-01",
        due_date="2026-09-13",
        allocation_mode="custom_by_day",
        project_calendar=spec,
    )
    try:
        assert status_for(editor, iso_date) == expected_label
    finally:
        close_widget(editor)


@pytest.mark.parametrize(
    "combo_working,name,expected_saved",
    [
        (False, "National Holiday", False),
        (True, "Saturday work", True),
    ],
)
def test_13_project_calendar_dialog_saves_exception_type_from_boolean_role(
    qapp,
    temp_db,
    combo_working,
    name,
    expected_saved,
):
    project_id, _project = project(temp_db, weekdays=MON_SAT)
    dialog = ProjectCalendarDialog(project_id=project_id, project_name="Witness", db_manager=temp_db)
    try:
        idx = dialog.type_combo.findData(combo_working)
        assert idx >= 0
        dialog.type_combo.setCurrentIndex(idx)
        dialog.date_input.setDate(QDate(2026, 9, 5))
        dialog.name_input.setText(name)
        dialog._on_add_exception()
        assert dialog.table.item(0, 1).data(Qt.UserRole) is combo_working
        dialog._on_save()
    finally:
        close_widget(dialog)

    exceptions = temp_db.get_project_calendar(project_id)["calendar_exceptions"]
    assert len(exceptions) == 1
    assert exceptions[0]["is_working"] is expected_saved


@pytest.mark.parametrize(
    "relative_path,required",
    [
        ("widgets/task_dialog.py", "effective_project_calendar_from_db"),
        ("services/schedule_version_service.py", "effective_project_calendar_from_db"),
        ("models/wbs_item_model.py", "effective_project_calendar_from_db"),
        ("services/wbs_rollup_service.py", "effective_project_calendar_from_db"),
        ("widgets/work_effort_editor.py", "classify_calendar_date"),
    ],
)
def test_14_runtime_consumers_use_common_calendar_authority(relative_path, required):
    source = (APP_ROOT / relative_path).read_text(encoding="utf-8")
    assert required in source
    assert "weekday() < 5" not in source
    assert "range(5)" not in source


@pytest.mark.parametrize(
    "calendar_dict,expected_finish",
    [
        ({"working_weekdays": list(MON_SAT), "calendar_exceptions": []}, "2026-09-05 09:00"),
        ({"working_weekdays": list(MON_FRI), "calendar_exceptions": []}, "2026-09-07 09:00"),
        ({"working_weekdays": list(MON_FRI), "calendar_exceptions": [{"date": "2026-09-05", "is_working": True}]}, "2026-09-05 09:00"),
        ({"working_weekdays": list(MON_SAT), "calendar_exceptions": [{"date": "2026-09-05", "is_working": False, "name": "Holiday"}]}, "2026-09-07 09:00"),
    ],
)
def test_15_cpm_accepts_database_calendar_dict_without_mon_fri_reversion(
    calendar_dict,
    expected_finish,
):
    spec = project_calendar_spec_from_source(calendar_dict, project_id=99)
    result = CPMSchedulingService.calculate_schedule(
        [
            Task(
                id=1,
                title="Foundation",
                project_id=99,
                planned_date="2026-09-01",
                planned_start_time="09:00",
                estimated_duration=5 * DAY_MINUTES,
            )
        ],
        project_id=99,
        project_calendar=spec,
    )

    assert result.nodes[1].earliest_finish == dt(expected_finish)


def test_16_production_witness_project_is_read_only_and_resolves_saturday_from_global_setting():
    before = hashlib.sha256(PRODUCTION_DB.read_bytes()).hexdigest()
    with sqlite3.connect(f"file:{PRODUCTION_DB}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        raw_project = conn.execute(
            "SELECT id, working_weekdays FROM projects WHERE name = ?",
            ("SCHEDULING WITNESS FINAL",),
        ).fetchone()
        raw_setting = conn.execute(
            "SELECT value FROM settings WHERE key = 'working_weekdays'"
        ).fetchone()

    assert raw_project is not None
    assert raw_project["working_weekdays"] is None
    assert raw_setting is not None
    assert 5 in json.loads(raw_setting["value"])

    db = DatabaseManager.read_only(str(PRODUCTION_DB))
    try:
        spec = effective_project_calendar_from_db(db, int(raw_project["id"]))
        finish = add_working_days_preserve_time(dt("2026-09-01 09:00"), 5, spec)
    finally:
        db.close()

    after = hashlib.sha256(PRODUCTION_DB.read_bytes()).hexdigest()
    assert spec.working_weekdays == MON_SAT
    assert classify_calendar_date(spec, "2026-09-05").label == "Working"
    assert finish == dt("2026-09-05 09:00")
    assert before == after
