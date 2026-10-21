import os
from datetime import date, datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.project import Project
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.services.schedule_constraint_service import (
    CalendarException,
    ProjectCalendarSpec,
)
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.work_effort_editor import WorkEffortEditor


APP_ROOT = Path(__file__).resolve().parents[1]
MON_FRI = (0, 1, 2, 3, 4)
MON_SAT = (0, 1, 2, 3, 4, 5)
SEVEN_DAY = (0, 1, 2, 3, 4, 5, 6)
TUE_SAT = (1, 2, 3, 4, 5)
MON_WED_FRI = (0, 2, 4)
WEEKEND_ONLY = (5, 6)
MON_ONLY = (0,)


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "workload_calendar.db"))
    yield db
    db.close()


@pytest.fixture
def temp_settings(temp_db, tmp_path):
    return SettingsManager(db_manager=temp_db, config_dir=tmp_path / "config")


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


def _spec_from_db(db, project_id):
    data = db.get_project_calendar(project_id)
    return ProjectCalendarSpec(
        project_id=project_id,
        working_weekdays=tuple(data.get("working_weekdays") or MON_FRI),
        exceptions=tuple(
            CalendarException.from_dict(item)
            for item in data.get("calendar_exceptions", [])
        ),
    )


def _project(db, weekdays=MON_SAT, exceptions=None, name="Workload Project"):
    project_id = db.insert_project({"name": name})
    db.set_project_calendar(
        project_id,
        working_weekdays=list(weekdays),
        calendar_exceptions=list(exceptions or []),
    )
    return project_id, Project.from_row(db.get_project(project_id))


def _editor(
    *,
    weekdays=MON_FRI,
    exceptions=(),
    start="2026-09-07",
    due="2026-09-13",
    mode="fixed_daily",
    daily=240,
    planned=0,
    custom=None,
    provider=None,
    settings=None,
):
    return WorkEffortEditor(
        start_date=start,
        due_date=due,
        allocation_mode=mode,
        daily_dedication_minutes=daily,
        planned_effort_minutes=planned,
        custom_allocations=custom,
        settings_manager=settings,
        project_calendar_provider=provider,
        project_calendar=None if provider else _spec(weekdays, exceptions),
    )


def _close(editor):
    editor.cleanup()
    editor.close()
    editor.deleteLater()


def _summary(editor):
    return editor.effort_summary_label.text()


def _status_for(editor, iso_date: str):
    start = date.fromisoformat(editor.start_date_str)
    target = date.fromisoformat(iso_date)
    row = (target - start).days + 1
    item = editor.grid_layout.itemAtPosition(row, 2)
    assert item is not None
    widget = item.widget()
    assert isinstance(widget, QLabel)
    return widget.text()


@pytest.mark.parametrize(
    "weekdays,expected_days,expected_effort,shown,hidden",
    [
        (MON_FRI, 5, 1200, ("Mon", "Tue", "Wed", "Thu", "Fri"), ("Sat", "Sun")),
        (MON_SAT, 6, 1440, ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat"), ("Sun",)),
        (SEVEN_DAY, 7, 1680, ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"), ()),
        (TUE_SAT, 5, 1200, ("Tue", "Wed", "Thu", "Fri", "Sat"), ("Mon", "Sun")),
        (MON_WED_FRI, 3, 720, ("Mon", "Wed", "Fri"), ("Tue", "Thu", "Sat", "Sun")),
        (WEEKEND_ONLY, 2, 480, ("Sat", "Sun"), ("Mon", "Tue", "Wed", "Thu", "Fri")),
        (MON_ONLY, 1, 240, ("Mon",), ("Tue", "Wed", "Thu", "Fri", "Sat", "Sun")),
    ],
)
def test_01_fixed_daily_uses_selected_project_calendar_weekdays(
    qapp,
    weekdays,
    expected_days,
    expected_effort,
    shown,
    hidden,
):
    editor = _editor(weekdays=weekdays)
    try:
        assert editor._active_working_days() == set(weekdays)
        assert editor.planned_effort_spin.value() == expected_effort
        text = _summary(editor)
        assert f"{expected_days} working days" in text
        for day_name in shown:
            assert day_name in text
        for day_name in hidden:
            assert day_name not in text
    finally:
        _close(editor)


@pytest.mark.parametrize(
    "weekdays,exceptions,expected_effort,working_dates,nonworking_dates",
    [
        (MON_SAT, [{"date": "2026-09-12", "is_working": False}], 1200, ("2026-09-11",), ("2026-09-12",)),
        (MON_FRI, [{"date": "2026-09-12", "is_working": True}], 1440, ("2026-09-12",), ("2026-09-13",)),
        (MON_FRI, [{"date": "2026-09-13", "is_working": True}], 1440, ("2026-09-13",), ("2026-09-12",)),
        (SEVEN_DAY, [{"date": "2026-09-13", "is_working": False}], 1440, ("2026-09-12",), ("2026-09-13",)),
        (TUE_SAT, [{"date": "2026-09-09", "is_working": False}], 960, ("2026-09-12",), ("2026-09-09",)),
        (MON_ONLY, [{"date": "2026-09-12", "is_working": True}], 480, ("2026-09-12",), ("2026-09-10",)),
    ],
)
def test_02_fixed_daily_honors_project_holidays_and_working_day_exceptions(
    qapp,
    weekdays,
    exceptions,
    expected_effort,
    working_dates,
    nonworking_dates,
):
    editor = _editor(weekdays=weekdays, exceptions=exceptions, mode="custom_by_day")
    try:
        editor.allocation_mode_combo.setCurrentIndex(
            editor.allocation_mode_combo.findData("fixed_daily")
        )
        assert editor.planned_effort_spin.value() == expected_effort
        for iso in working_dates:
            assert _status_for(editor, iso) in {"Working", "Working override"}
        for iso in nonworking_dates:
            assert _status_for(editor, iso) in {"Holiday", "Non-working", "Non-working exception"}
    finally:
        _close(editor)


@pytest.mark.parametrize(
    "initial_weekdays,next_weekdays,kept_date,kept_minutes",
    [
        (MON_SAT, MON_FRI, "2026-09-12", 120),
        (MON_FRI, MON_SAT, "2026-09-12", 120),
        (SEVEN_DAY, MON_FRI, "2026-09-13", 45),
        (MON_FRI, SEVEN_DAY, "2026-09-13", 45),
        (TUE_SAT, MON_WED_FRI, "2026-09-09", 90),
        (MON_WED_FRI, TUE_SAT, "2026-09-11", 30),
    ],
)
def test_03_custom_by_day_saved_effort_survives_calendar_reclassification(
    qapp,
    initial_weekdays,
    next_weekdays,
    kept_date,
    kept_minutes,
):
    custom = {
        "2026-09-07": 60,
        "2026-09-09": 90,
        "2026-09-11": 30,
        "2026-09-12": 120,
        "2026-09-13": 45,
    }
    editor = _editor(weekdays=initial_weekdays, mode="custom_by_day", custom=custom)
    try:
        before = editor.get_data()["custom_allocations"]
        assert before[kept_date] == kept_minutes
        editor.set_project_calendar(_spec(next_weekdays))
        after = editor.get_data()["custom_allocations"]
        assert after == before
        assert after[kept_date] == kept_minutes
        assert editor.planned_effort_spin.value() == sum(custom.values())
    finally:
        _close(editor)


@pytest.mark.parametrize(
    "new_weekdays,expected_effort,expected_summary_day",
    [
        (MON_SAT, 1440, "Sat"),
        (SEVEN_DAY, 1680, "Sun"),
        (MON_WED_FRI, 720, "Wed"),
    ],
)
def test_04_live_project_calendar_change_recalculates_provider_editor(
    qapp,
    temp_db,
    new_weekdays,
    expected_effort,
    expected_summary_day,
):
    project_id, _project_model = _project(temp_db, MON_FRI)
    editor = _editor(provider=lambda: _spec_from_db(temp_db, project_id))
    try:
        assert editor.planned_effort_spin.value() == 1200
        temp_db.set_project_calendar(project_id, list(new_weekdays), [])
        QApplication.processEvents()
        assert editor._active_working_days() == set(new_weekdays)
        assert editor.planned_effort_spin.value() == expected_effort
        assert expected_summary_day in _summary(editor)
    finally:
        _close(editor)


def test_05_task_dialog_workload_follows_estimated_duration_target_calendar(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    dialog = TaskDialog(
        projects=[project],
        task=Task(
            title="Foundation",
            project_id=project_id,
            planned_date="2026-09-01",
            planned_start_time="09:00",
            estimated_duration=0,
            status=TaskStatus.PLANNED,
        ),
        db_manager=temp_db,
        settings_manager=temp_settings,
    )
    try:
        dialog.duration_days_spin.setValue(5.0)
        dialog.daily_hours_spin.setValue(4)
        assert dialog.due_date_edit.date().toString("yyyy-MM-dd") == "2026-09-05"
        assert dialog.end_time_edit.time().toString("HH:mm") == "09:00"
        assert dialog.planned_effort_spin.value() == 1200
        assert "Tue, Wed, Thu, Fri, Sat" in dialog.effort_summary_label.text()
    finally:
        dialog.close()


def test_06_project_calendar_overrides_global_workweek_for_workload(
    qapp,
    temp_db,
    temp_settings,
):
    temp_settings.set("working_weekdays", list(MON_FRI))
    editor = _editor(weekdays=MON_SAT, settings=temp_settings)
    try:
        assert editor._active_working_days() == set(MON_SAT)
        assert editor.planned_effort_spin.value() == 1440
        assert "Sat" in _summary(editor)
    finally:
        _close(editor)


def test_07_set_project_calendar_replaces_static_calendar_without_restarting_editor(qapp):
    editor = _editor(weekdays=MON_FRI)
    try:
        assert editor.planned_effort_spin.value() == 1200
        editor.set_project_calendar(_spec(MON_SAT))
        assert editor._active_working_days() == set(MON_SAT)
        assert editor.planned_effort_spin.value() == 1440
        assert "Sat" in _summary(editor)
    finally:
        _close(editor)


def test_08_task_and_subtask_workload_editors_share_project_calendar_authority(qapp):
    main_editor = _editor(weekdays=MON_SAT)
    subtask_editor = _editor(weekdays=MON_SAT)
    try:
        assert main_editor._active_working_days() == subtask_editor._active_working_days()
        assert main_editor.planned_effort_spin.value() == subtask_editor.planned_effort_spin.value()
        assert _summary(main_editor) == _summary(subtask_editor)
    finally:
        _close(main_editor)
        _close(subtask_editor)


def test_09_workload_source_guard_for_selected_project_calendar_authority():
    source = (APP_ROOT / "widgets" / "work_effort_editor.py").read_text(encoding="utf-8")
    task_dialog = (APP_ROOT / "widgets" / "task_dialog.py").read_text(encoding="utf-8")
    assert "project_calendar_provider" in source
    assert "ScheduleCalendar.from_project_calendar" in source
    assert "_active_calendar_parts" in source
    assert "get_configured_working_weekdays(self.settings_manager)" in source
    assert "project_calendar_provider=self._current_project_calendar_spec" in task_dialog
    assert "weekday() < 5" not in source
