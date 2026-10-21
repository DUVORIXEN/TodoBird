import hashlib
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QCoreApplication, QDate, QEvent, QTime, Qt
from PySide6.QtWidgets import QApplication

from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.project import Project
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.services.gantt_wbs_adapter import GanttWBSAdapter
from todo_bird_app.services.schedule_version_service import ScheduleVersionService
from todo_bird_app.services.wbs_rollup_service import WBSRollupService
from todo_bird_app.services.wbs_service import WBSService
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.widgets.task_dialog import TaskDialog


DAY_MINUTES = 1440
MON_FRI = (0, 1, 2, 3, 4)
MON_SAT = (0, 1, 2, 3, 4, 5)
SEVEN_DAY = (0, 1, 2, 3, 4, 5, 6)
PRODUCTION_DB = Path(__file__).resolve().parents[1] / "data" / "todo_bird.db"

RAW_SCHEDULE_FIELDS = (
    "planned_date",
    "due_date",
    "planned_start_time",
    "planned_end_time",
    "estimated_duration",
    "actual_start_date",
    "actual_end_date",
    "actual_start_time",
    "actual_end_time",
    "actual_duration",
    "planned_effort_minutes",
    "daily_dedication_minutes",
)


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "duration_roundtrip.db"))
    WBSRollupService.clear_cache()
    yield db
    WBSRollupService.clear_cache()
    db.close()


@pytest.fixture
def temp_settings(temp_db, tmp_path):
    return SettingsManager(db_manager=temp_db, config_dir=tmp_path / "config")


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _project(db, weekdays=MON_SAT, exceptions=None, name="SCHEDULING WITNESS FRESH"):
    project_id = db.insert_project({"name": name})
    db.set_project_calendar(
        project_id,
        working_weekdays=list(weekdays),
        calendar_exceptions=list(exceptions or []),
    )
    return project_id, Project.from_row(db.get_project(project_id))


def _task(
    project_id,
    *,
    title="Foundation",
    start_date="2026-09-01",
    start_time="09:00",
    days=5,
    duration_minutes=None,
    due_date=None,
    end_time=None,
):
    duration = (
        int(duration_minutes)
        if duration_minutes is not None
        else int(round(float(days) * DAY_MINUTES))
    )
    return Task(
        title=title,
        project_id=project_id,
        planned_date=start_date,
        planned_start_time=start_time,
        due_date=due_date,
        planned_end_time=end_time,
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


def _close_dialog(dialog):
    if dialog is None:
        return
    if hasattr(dialog, "cleanup"):
        dialog.cleanup()
    dialog.close()
    dialog.deleteLater()
    app = QApplication.instance()
    if app is not None:
        for _ in range(3):
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


def _raw_task(db, task_id):
    row = db.get_task_by_id(task_id)
    assert row is not None
    return {field: row.get(field) for field in RAW_SCHEDULE_FIELDS}


def _raw_subtask(db, task_id, subtask_id):
    rows = db.get_all_subtasks_flat(task_id)
    row = next(row for row in rows if int(row["id"]) == int(subtask_id))
    return {field: row.get(field) for field in RAW_SCHEDULE_FIELDS}


def _parse_start(start_date, start_time):
    return datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")


def _exception_sets(exceptions):
    holidays = set()
    overrides = set()
    for item in exceptions or []:
        date_str = str(item.get("date") or item.get("exception_date") or "")[:10]
        if not date_str:
            continue
        if item.get("is_working") in (True, 1, "1", "true", "True"):
            overrides.add(date_str)
            holidays.discard(date_str)
        else:
            holidays.add(date_str)
            overrides.discard(date_str)
    return holidays, overrides


def _is_working_day(day, weekdays, exceptions=None):
    holidays, overrides = _exception_sets(exceptions)
    iso = day.strftime("%Y-%m-%d")
    if iso in overrides:
        return True
    if iso in holidays:
        return False
    return day.weekday() in set(weekdays)


def _expected_finish(start_date, start_time, days, weekdays, exceptions=None):
    start = _parse_start(start_date, start_time)
    if days <= 0:
        return start

    target_whole_days = int(round(float(days)))
    seen = 0
    current = start.date()
    for _ in range(1000):
        if _is_working_day(current, weekdays, exceptions):
            seen += 1
            if seen >= target_whole_days:
                return datetime.combine(current, start.time())
        current += timedelta(days=1)
    raise AssertionError("calendar oracle exceeded search bound")


def _set_qdate(edit, iso_date):
    qdate = QDate.fromString(iso_date, "yyyy-MM-dd")
    assert qdate.isValid()
    edit.setDate(qdate)


def _set_qtime(edit, hhmm):
    qtime = QTime.fromString(hhmm, "HH:mm")
    assert qtime.isValid()
    edit.setTime(qtime)


def _assert_target(dialog, expected_dt):
    expected_date = expected_dt.strftime("%Y-%m-%d")
    expected_time = expected_dt.strftime("%H:%M")
    assert dialog.estimated_finish_label.text() == f"{expected_date} {expected_time}"
    assert dialog.due_date_edit.date().toString("yyyy-MM-dd") == expected_date
    assert dialog.end_time_edit.time().toString("HH:mm") == expected_time


def _persist_from_dialog(db, dialog):
    dialog.on_save()
    controller = TaskController(db)
    task = dialog.get_task()
    if task.id is None:
        return controller.add_task(task)
    assert controller.update_task(task) is True
    return int(task.id)


def _insert_task(db, task):
    return TaskController(db).add_task(task)


def test_01_human_witness_fresh_task_create_save_reopen_roundtrip(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        _task(project_id, days=0, duration_minutes=0),
    )

    try:
        dialog.duration_days_spin.setValue(5.0)
        expected = _expected_finish("2026-09-01", "09:00", 5, MON_SAT)

        assert dialog.duration_spin.value() == 7200
        assert dialog.duration_days_spin.value() == pytest.approx(5.0)
        assert dialog.planned_finish_checkbox.isChecked() is True
        _assert_target(dialog, expected)

        task_id = _persist_from_dialog(temp_db, dialog)
    finally:
        _close_dialog(dialog)

    assert _raw_task(temp_db, task_id) == {
        "planned_date": "2026-09-01",
        "due_date": "2026-09-05",
        "planned_start_time": "09:00",
        "planned_end_time": "09:00",
        "estimated_duration": 7200,
        "actual_start_date": None,
        "actual_end_date": None,
        "actual_start_time": None,
        "actual_end_time": None,
        "actual_duration": 0,
        "planned_effort_minutes": 0,
        "daily_dedication_minutes": 0,
    }

    reopened = _dialog(
        temp_db,
        temp_settings,
        project,
        TaskController(temp_db).get_task(task_id),
    )
    try:
        assert reopened.task_source_path == "DatabaseManager.get_task_by_id"
        assert reopened.start_time_edit.time().toString("HH:mm") == "09:00"
        assert reopened.duration_spin.value() == 7200
        assert reopened.duration_days_spin.value() == pytest.approx(5.0)
        _assert_target(reopened, expected)

        before = _raw_task(temp_db, task_id)
        _persist_from_dialog(temp_db, reopened)
        assert _raw_task(temp_db, task_id) == before
    finally:
        _close_dialog(reopened)


def test_02_existing_five_day_finish_reopen_does_not_collapse_to_four_days(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    task_id = _insert_task(
        temp_db,
        _task(
            project_id,
            due_date="2026-09-05",
            end_time="09:00",
            duration_minutes=7200,
        ),
    )

    before = _raw_task(temp_db, task_id)
    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        TaskController(temp_db).get_task(task_id),
    )

    try:
        assert dialog.duration_days_spin.value() == pytest.approx(5.0)
        assert dialog.duration_spin.value() == 7200
        _persist_from_dialog(temp_db, dialog)
        assert _raw_task(temp_db, task_id) == before
    finally:
        _close_dialog(dialog)


def test_03_controller_insert_update_read_preserves_fresh_schedule_fields(temp_db):
    project_id, _project_model = _project(temp_db, MON_SAT)
    controller = TaskController(temp_db)
    task_id = controller.add_task(
        _task(
            project_id,
            due_date="2026-09-05",
            end_time="09:00",
            duration_minutes=7200,
        )
    )
    before = _raw_task(temp_db, task_id)

    loaded = controller.get_task(task_id)
    assert loaded is not None
    loaded.notes = "metadata-only edit"
    assert controller.update_task(loaded) is True

    assert _raw_task(temp_db, task_id) == before


@pytest.mark.parametrize(
    "weekdays,start_date,start_time,days",
    [
        (MON_FRI, "2026-09-01", "09:00", 1),
        (MON_FRI, "2026-09-01", "08:00", 2),
        (MON_FRI, "2026-09-01", "09:00", 5),
        (MON_FRI, "2026-09-01", "13:30", 6),
        (MON_FRI, "2026-09-01", "00:00", 7),
        (MON_FRI, "2026-09-01", "09:00", 10),
        (MON_SAT, "2026-09-01", "09:00", 1),
        (MON_SAT, "2026-09-01", "08:00", 2),
        (MON_SAT, "2026-09-01", "09:00", 5),
        (MON_SAT, "2026-09-01", "13:30", 6),
        (MON_SAT, "2026-09-01", "00:00", 7),
        (MON_SAT, "2026-09-01", "09:00", 10),
        (SEVEN_DAY, "2026-09-01", "09:00", 1),
        (SEVEN_DAY, "2026-09-01", "08:00", 2),
        (SEVEN_DAY, "2026-09-01", "09:00", 5),
        (SEVEN_DAY, "2026-09-01", "13:30", 6),
        (SEVEN_DAY, "2026-09-01", "00:00", 7),
        (SEVEN_DAY, "2026-09-01", "09:00", 10),
    ],
)
def test_04_calendar_day_duration_oracles_set_target_finish(
    qapp,
    temp_db,
    temp_settings,
    weekdays,
    start_date,
    start_time,
    days,
):
    project_id, project = _project(temp_db, weekdays)
    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        _task(
            project_id,
            start_date=start_date,
            start_time=start_time,
            days=0,
            duration_minutes=0,
        ),
    )

    try:
        dialog.duration_days_spin.setValue(float(days))
        expected = _expected_finish(start_date, start_time, days, weekdays)

        assert dialog.duration_spin.value() == days * DAY_MINUTES
        assert dialog.duration_days_spin.value() == pytest.approx(float(days))
        _assert_target(dialog, expected)
    finally:
        _close_dialog(dialog)


@pytest.mark.parametrize("start_time", ["00:00", "08:00", "09:00", "13:30"])
def test_05_start_time_is_preserved_in_five_day_mon_sat_target(
    qapp,
    temp_db,
    temp_settings,
    start_time,
):
    project_id, project = _project(temp_db, MON_SAT)
    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        _task(project_id, start_time=start_time, days=0, duration_minutes=0),
    )

    try:
        dialog.duration_days_spin.setValue(5.0)
        expected = _expected_finish("2026-09-01", start_time, 5, MON_SAT)

        assert dialog.start_time_edit.time().toString("HH:mm") == start_time
        assert dialog.duration_spin.value() == 7200
        _assert_target(dialog, expected)
    finally:
        _close_dialog(dialog)


def test_06_weekend_start_moves_to_next_working_day_before_count(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_FRI)
    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        _task(
            project_id,
            start_date="2026-09-06",
            start_time="09:00",
            days=0,
            duration_minutes=0,
        ),
    )

    try:
        dialog.duration_days_spin.setValue(1.0)
        _assert_target(dialog, datetime(2026, 9, 7, 9, 0))
    finally:
        _close_dialog(dialog)


def test_07_holiday_exception_skips_nonworking_day(
    qapp,
    temp_db,
    temp_settings,
):
    exceptions = [{"date": "2026-09-03", "is_working": False, "name": "Holiday"}]
    project_id, project = _project(temp_db, MON_SAT, exceptions=exceptions)
    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        _task(project_id, days=0, duration_minutes=0),
    )

    try:
        dialog.duration_days_spin.setValue(5.0)
        expected = _expected_finish("2026-09-01", "09:00", 5, MON_SAT, exceptions)
        _assert_target(dialog, expected)
    finally:
        _close_dialog(dialog)


def test_08_working_override_counts_weekend_day(
    qapp,
    temp_db,
    temp_settings,
):
    exceptions = [{"date": "2026-09-05", "is_working": True, "name": "Special work"}]
    project_id, project = _project(temp_db, MON_FRI, exceptions=exceptions)
    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        _task(project_id, days=0, duration_minutes=0),
    )

    try:
        dialog.duration_days_spin.setValue(5.0)
        expected = _expected_finish("2026-09-01", "09:00", 5, MON_FRI, exceptions)
        _assert_target(dialog, expected)
    finally:
        _close_dialog(dialog)


def test_09_explicit_finish_recalculates_inclusive_duration_when_duration_missing(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        _task(
            project_id,
            duration_minutes=0,
            due_date="2026-09-05",
            end_time="09:00",
        ),
    )

    try:
        assert dialog.planned_finish_checkbox.isChecked() is True
        assert dialog.duration_spin.value() == 7200
        assert dialog.duration_days_spin.value() == pytest.approx(5.0)
    finally:
        _close_dialog(dialog)


def test_10_explicit_finish_edit_recalculates_duration_only_in_finish_mode(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        _task(project_id, days=0, duration_minutes=0),
    )

    try:
        dialog.planned_finish_checkbox.setChecked(True)
        _set_qdate(dialog.due_date_edit, "2026-09-04")
        _set_qtime(dialog.end_time_edit, "09:00")

        assert dialog.duration_spin.value() == 5760
        assert dialog.duration_days_spin.value() == pytest.approx(4.0)
    finally:
        _close_dialog(dialog)


def test_11_changing_start_date_moves_target_without_duration_loss(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    dialog = _dialog(temp_db, temp_settings, project, _task(project_id))

    try:
        _set_qdate(dialog.planned_date_edit, "2026-09-02")
        expected = _expected_finish("2026-09-02", "09:00", 5, MON_SAT)

        assert dialog.duration_spin.value() == 7200
        assert dialog.duration_days_spin.value() == pytest.approx(5.0)
        _assert_target(dialog, expected)
    finally:
        _close_dialog(dialog)


def test_12_changing_start_time_moves_target_without_duration_loss(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    dialog = _dialog(temp_db, temp_settings, project, _task(project_id))

    try:
        _set_qtime(dialog.start_time_edit, "13:30")
        expected = _expected_finish("2026-09-01", "13:30", 5, MON_SAT)

        assert dialog.duration_spin.value() == 7200
        assert dialog.duration_days_spin.value() == pytest.approx(5.0)
        _assert_target(dialog, expected)
    finally:
        _close_dialog(dialog)


def test_13_minute_duration_edit_syncs_days_and_target(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        _task(project_id, days=0, duration_minutes=0),
    )

    try:
        dialog.duration_spin.setValue(2880)

        assert dialog.duration_days_spin.value() == pytest.approx(2.0)
        _assert_target(dialog, _expected_finish("2026-09-01", "09:00", 2, MON_SAT))
    finally:
        _close_dialog(dialog)


def test_14_day_duration_edit_syncs_minutes_and_target(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        _task(project_id, days=0, duration_minutes=0),
    )

    try:
        dialog.duration_days_spin.setValue(6.0)

        assert dialog.duration_spin.value() == 8640
        _assert_target(dialog, _expected_finish("2026-09-01", "09:00", 6, MON_SAT))
    finally:
        _close_dialog(dialog)


def test_15_toggling_target_finish_off_preserves_duration(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    task_id = _insert_task(
        temp_db,
        _task(
            project_id,
            duration_minutes=7200,
            due_date="2026-09-05",
            end_time="09:00",
        ),
    )
    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        TaskController(temp_db).get_task(task_id),
    )

    try:
        dialog.planned_finish_checkbox.setChecked(False)
        assert dialog.duration_spin.value() == 7200
        _persist_from_dialog(temp_db, dialog)
    finally:
        _close_dialog(dialog)

    after = _raw_task(temp_db, task_id)
    assert after["estimated_duration"] == 7200
    assert after["due_date"] is None
    assert after["planned_end_time"] is None


def test_16_untouched_save_preserves_no_finish_row(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    task_id = _insert_task(temp_db, _task(project_id, due_date=None, end_time=None))
    before = _raw_task(temp_db, task_id)
    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        TaskController(temp_db).get_task(task_id),
    )

    try:
        assert dialog.planned_finish_checkbox.isChecked() is False
        assert dialog.duration_spin.value() == 7200
        _assert_target(dialog, _expected_finish("2026-09-01", "09:00", 5, MON_SAT))
        _persist_from_dialog(temp_db, dialog)
        assert _raw_task(temp_db, task_id) == before
    finally:
        _close_dialog(dialog)


def test_17_untouched_save_preserves_with_finish_row(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    task_id = _insert_task(
        temp_db,
        _task(
            project_id,
            due_date="2026-09-05",
            end_time="09:00",
            duration_minutes=7200,
        ),
    )
    before = _raw_task(temp_db, task_id)
    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        TaskController(temp_db).get_task(task_id),
    )

    try:
        _persist_from_dialog(temp_db, dialog)
        assert _raw_task(temp_db, task_id) == before
    finally:
        _close_dialog(dialog)


def test_18_actual_tracking_save_does_not_mutate_planned_schedule(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    task_id = _insert_task(
        temp_db,
        _task(
            project_id,
            due_date="2026-09-05",
            end_time="09:00",
            duration_minutes=7200,
        ),
    )
    before = _raw_task(temp_db, task_id)
    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        TaskController(temp_db).get_task(task_id),
    )

    try:
        dialog.actual_enabled_check.setChecked(True)
        _set_qdate(dialog.actual_start_date_edit, "2026-09-02")
        _set_qtime(dialog.actual_start_edit, "10:30")
        idx = dialog.status_combo.findData(TaskStatus.IN_PROGRESS)
        if idx >= 0:
            dialog.status_combo.setCurrentIndex(idx)
        _persist_from_dialog(temp_db, dialog)
    finally:
        _close_dialog(dialog)

    after = _raw_task(temp_db, task_id)
    for field in (
        "planned_date",
        "due_date",
        "planned_start_time",
        "planned_end_time",
        "estimated_duration",
        "planned_effort_minutes",
        "daily_dedication_minutes",
    ):
        assert after[field] == before[field]
    assert after["actual_start_date"] == "2026-09-02"
    assert after["actual_start_time"] == "10:30"


def test_19_schedule_snapshot_capture_reads_without_rewriting_raw_schedule(temp_db):
    project_id, _project_model = _project(temp_db, MON_SAT)
    task_id = _insert_task(
        temp_db,
        _task(
            project_id,
            due_date="2026-09-05",
            end_time="09:00",
            duration_minutes=7200,
        ),
    )
    before = _raw_task(temp_db, task_id)

    snapshot = ScheduleVersionService.capture_current_schedule_snapshot(
        temp_db,
        project_id,
    )

    assert _raw_task(temp_db, task_id) == before
    task_item = next(
        item
        for item in snapshot
        if item["entity_type"] == "task" and int(item["entity_id"]) == task_id
    )
    assert task_item["duration_minutes"] == 7200


def test_20_original_baseline_creation_does_not_rewrite_raw_schedule(temp_db):
    project_id, _project_model = _project(temp_db, MON_SAT)
    task_id = _insert_task(
        temp_db,
        _task(
            project_id,
            due_date="2026-09-05",
            end_time="09:00",
            duration_minutes=7200,
        ),
    )
    before = _raw_task(temp_db, task_id)

    version_id = ScheduleVersionService.create_original_baseline(
        temp_db,
        project_id,
        name="Duration Roundtrip Baseline",
        approved_at="2026-09-01T09:00:00",
    )

    assert version_id > 0
    assert _raw_task(temp_db, task_id) == before
    assert temp_db.get_task_by_id(task_id)["baseline_duration_minutes"] == 7200


def test_21_wbs_rollup_reads_without_rewriting_leaf_raw_schedule(temp_db):
    project_id, _project_model = _project(temp_db, MON_SAT)
    task_id = _insert_task(
        temp_db,
        _task(
            project_id,
            due_date="2026-09-05",
            end_time="09:00",
            duration_minutes=7200,
        ),
    )
    before = _raw_task(temp_db, task_id)

    snapshot = WBSService.build_project_hierarchy(temp_db, project_id=project_id)
    rollups = WBSRollupService.compute_all_rollups(snapshot, temp_db)

    assert rollups
    assert _raw_task(temp_db, task_id) == before


def test_22_gantt_wbs_adapter_reads_without_rewriting_leaf_raw_schedule(temp_db):
    project_id, _project_model = _project(temp_db, MON_SAT)
    task_id = _insert_task(
        temp_db,
        _task(
            project_id,
            due_date="2026-09-05",
            end_time="09:00",
            duration_minutes=7200,
        ),
    )
    before = _raw_task(temp_db, task_id)

    snapshot = WBSService.build_project_hierarchy(temp_db, project_id=project_id)
    rows = GanttWBSAdapter.build_project_rows(snapshot, temp_db)

    assert rows
    assert _raw_task(temp_db, task_id) == before


def test_23_reopen_resolves_database_task_over_stale_summary_payload(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    task_id = _insert_task(
        temp_db,
        _task(
            project_id,
            due_date="2026-09-05",
            end_time="09:00",
            duration_minutes=7200,
        ),
    )
    stale_summary = _task(
        project_id,
        start_date="2026-09-01",
        start_time="00:00",
        duration_minutes=5760,
        due_date="2026-09-04",
        end_time="00:00",
    )
    stale_summary.id = task_id

    dialog = _dialog(temp_db, temp_settings, project, stale_summary)
    try:
        assert dialog.task_source_path == "DatabaseManager.get_task_by_id"
        assert dialog.start_time_edit.time().toString("HH:mm") == "09:00"
        assert dialog.duration_spin.value() == 7200
        assert dialog.duration_days_spin.value() == pytest.approx(5.0)
        _assert_target(dialog, datetime(2026, 9, 5, 9, 0))
    finally:
        _close_dialog(dialog)


def test_24_subtask_tree_reopen_preserves_five_day_schedule_metadata(
    qapp,
    temp_db,
    temp_settings,
):
    project_id, project = _project(temp_db, MON_SAT)
    task_id = _insert_task(temp_db, _task(project_id, title="Parent"))
    subtask_id = temp_db.insert_subtask(
        task_id=task_id,
        title="Foundation child",
        planned_date="2026-09-01",
        planned_start_time="09:00",
        due_date="2026-09-05",
        planned_end_time="09:00",
        estimated_duration=7200,
        show_in_gantt=True,
    )
    before = _raw_subtask(temp_db, task_id, subtask_id)

    dialog = _dialog(
        temp_db,
        temp_settings,
        project,
        TaskController(temp_db).get_task(task_id),
    )
    try:
        item = dialog.subtask_tree.topLevelItem(0)
        metadata = item.data(0, Qt.UserRole + 1)

        assert metadata["planned_start_time"] == "09:00"
        assert metadata["planned_end_time"] == "09:00"
        assert metadata["estimated_duration"] == 7200
        assert dialog._collect_subtask_tree()[0]["estimated_duration"] == 7200

        _persist_from_dialog(temp_db, dialog)
        assert _raw_subtask(temp_db, task_id, subtask_id) == before
    finally:
        _close_dialog(dialog)


def test_25_subtask_insert_update_read_preserves_five_day_schedule(temp_db):
    project_id, _project_model = _project(temp_db, MON_SAT)
    task_id = _insert_task(temp_db, _task(project_id, title="Parent"))
    subtask_id = temp_db.insert_subtask(
        task_id=task_id,
        title="Foundation child",
        planned_date="2026-09-01",
        planned_start_time="09:00",
        due_date="2026-09-05",
        planned_end_time="09:00",
        estimated_duration=7200,
        show_in_gantt=True,
    )
    before = _raw_subtask(temp_db, task_id, subtask_id)

    assert temp_db.update_subtask(
        subtask_id=subtask_id,
        title="Foundation child renamed",
        is_completed=False,
        planned_date="2026-09-01",
        planned_start_time="09:00",
        due_date="2026-09-05",
        planned_end_time="09:00",
        estimated_duration=7200,
        show_in_gantt=True,
    )
    after = _raw_subtask(temp_db, task_id, subtask_id)

    assert after["planned_date"] == before["planned_date"]
    assert after["due_date"] == before["due_date"]
    assert after["planned_start_time"] == before["planned_start_time"]
    assert after["planned_end_time"] == before["planned_end_time"]
    assert after["estimated_duration"] == before["estimated_duration"]


def test_26_source_recalculation_guard_preserves_existing_task_duration():
    source = Path("todo_bird_app/widgets/task_dialog.py").read_text()

    assert "should_recalculate_from_finish = bool(" in source
    assert "not int(self.task.estimated_duration or 0)" in source


def test_27_source_recalculation_guard_preserves_existing_subtask_duration():
    source = Path("todo_bird_app/widgets/task_dialog.py").read_text()

    assert "should_recalculate_sub_from_finish = bool(" in source
    assert "not int(metadata.get(\"estimated_duration\") or 0)" in source


def test_28_source_has_no_task_dialog_dot_days_truncation():
    source = Path("todo_bird_app/widgets/task_dialog.py").read_text()

    assert ".days" not in source


def test_29_source_uses_shared_scheduled_duration_authority_for_subtasks():
    source = Path("todo_bird_app/widgets/task_dialog.py").read_text()
    subtask_editor_source = source.split(
        "def edit_selected_subtask_details",
        1,
    )[1]

    assert "_scheduled_duration_between(" in subtask_editor_source
    assert (
        "from todo_bird_app.utils.time_math import duration_between"
        not in subtask_editor_source
    )
    assert (
        "duration_between("
        not in subtask_editor_source.replace("_scheduled_duration_between(", "")
    )


def test_30_production_db_hash_read_only_probe_does_not_mutate():
    if not PRODUCTION_DB.exists():
        pytest.skip("production DB not present in this checkout")

    before = _hash_file(PRODUCTION_DB)
    uri = f"file:{PRODUCTION_DB}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.execute("SELECT COUNT(*) FROM tasks;").fetchone()
        conn.execute("SELECT COUNT(*) FROM projects;").fetchone()
    after = _hash_file(PRODUCTION_DB)

    assert after == before
