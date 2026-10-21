import hashlib
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task
from todo_bird_app.models.wbs_item_model import WBSItemModel
from todo_bird_app.services.gantt_wbs_adapter import GanttWBSAdapter
from todo_bird_app.services.wbs_mutation_service import WBSMutationService
from todo_bird_app.services.wbs_rollup_service import WBSRollupService
from todo_bird_app.services.wbs_service import EntityRef, WBSService
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.views import gantt_view as gantt_view_module
from todo_bird_app.views.gantt_view import GanttView
from todo_bird_app.widgets.task_dialog import TaskDialog


RAW_SCHEDULE_FIELDS = (
    "planned_date",
    "due_date",
    "planned_start_time",
    "planned_end_time",
    "estimated_duration",
    "planned_effort_minutes",
    "daily_dedication_minutes",
)

TASK_SCHEDULE_SQL_FIELDS = (
    "planned_date",
    "due_date",
    "planned_start_time",
    "planned_end_time",
    "estimated_duration",
)

PRODUCTION_DB = Path(__file__).resolve().parents[1] / "data" / "todo_bird.db"


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def temp_db(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "wbs_human_failure.db"))
    WBSRollupService.clear_cache()
    yield db
    WBSRollupService.clear_cache()
    db.close()


class SqlWriteTrace:
    def __init__(self, db):
        self.db = db
        self.statements = []
        self.conn = None

    def __enter__(self):
        self.conn = self.db.get_connection()
        self.conn.set_trace_callback(self.statements.append)
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.conn is not None:
            self.conn.set_trace_callback(None)

    def task_schedule_updates(self):
        updates = []
        for statement in self.statements:
            normalized = " ".join(str(statement).lower().split())
            if "update tasks" not in normalized:
                continue
            if any(field in normalized for field in TASK_SCHEDULE_SQL_FIELDS):
                updates.append(statement)
        return updates


class _FakeGanttView:
    _gantt_schedule_payload_targets_summary = (
        GanttView._gantt_schedule_payload_targets_summary
    )

    def __init__(self, db, project_id):
        self.db_manager = db
        self.current_project_id = project_id
        self.messages = []

    def show_feedback_message(self, text):
        self.messages.append(text)


def _hash_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _raw_parent_schedule(db, task_id):
    row = db.get_task_by_id(task_id)
    return {field: row[field] for field in RAW_SCHEDULE_FIELDS}


def _task_objects_for_project(db, project_id):
    return [Task.from_row(row) for row in db.get_tasks_by_project(project_id)]


def _build_gantt_items(db, project_id):
    fake = _FakeGanttView(db, project_id)
    return GanttView._build_phase1d_wbs_gantt_items(
        fake,
        _task_objects_for_project(db, project_id),
    )


def _find_gantt_item(items, entity_type, entity_id):
    for item in items:
        if (
            getattr(item, "gantt_entity_type", None) == entity_type
            and int(getattr(item, "gantt_entity_id", 0)) == int(entity_id)
        ):
            return item
    raise AssertionError(f"Missing Gantt item {entity_type}:{entity_id}")


def _fresh_witness_project(db):
    project_id = db.insert_project({"name": "SCHEDULING WITNESS FRESH"})
    db.set_project_calendar(project_id, working_weekdays=[0, 1, 2, 3, 4, 5])
    parent_id = db.insert_task(
        {
            "project_id": project_id,
            "title": "Foundation",
            "status": "Planned",
            "planned_date": "2026-09-01",
            "planned_start_time": "09:00",
            "due_date": None,
            "planned_end_time": None,
            "estimated_duration": 7200,
            "planned_effort_minutes": 3000,
            "daily_dedication_minutes": 480,
            "show_in_gantt": 1,
        }
    )
    excavation_id = db.insert_subtask(
        parent_id,
        "Excavation",
        position=0,
        planned_date="2026-09-01",
        planned_start_time="09:00",
        due_date=None,
        planned_end_time=None,
        estimated_duration=2880,
        planned_effort_minutes=960,
        progress=50,
        show_in_gantt=True,
    )
    reinforcement_id = db.insert_subtask(
        parent_id,
        "Reinforcement",
        position=1,
        planned_date="2026-09-02",
        planned_start_time="09:00",
        due_date=None,
        planned_end_time=None,
        estimated_duration=4320,
        planned_effort_minutes=1440,
        progress=25,
        show_in_gantt=True,
    )
    return {
        "project_id": project_id,
        "parent_id": parent_id,
        "excavation_id": excavation_id,
        "reinforcement_id": reinforcement_id,
    }


def _rollups(db, project_id):
    snapshot = WBSService.build_project_hierarchy(db, project_id=project_id)
    return snapshot, WBSRollupService.compute_all_rollups(snapshot, db)


def _open_parent_dialog(db, task_id, tmp_path=None):
    controller = TaskController(db)
    projects = controller.get_all_projects()
    settings = None
    if tmp_path is not None:
        settings = SettingsManager(db_manager=db, config_dir=tmp_path / "config")
    return TaskDialog(
        projects,
        controller.get_task(task_id),
        db_manager=db,
        settings_manager=settings,
    )


def test_01_fresh_parent_raw_duration_preserved_after_dialog_save(qapp, temp_db, tmp_path):
    ids = _fresh_witness_project(temp_db)
    before = _raw_parent_schedule(temp_db, ids["parent_id"])

    dialog = _open_parent_dialog(temp_db, ids["parent_id"], tmp_path)
    dialog.on_save()
    TaskController(temp_db).update_task(dialog.get_task())

    assert _raw_parent_schedule(temp_db, ids["parent_id"]) == before


def test_02_fresh_parent_raw_start_preserved(qapp, temp_db, tmp_path):
    ids = _fresh_witness_project(temp_db)

    dialog = _open_parent_dialog(temp_db, ids["parent_id"], tmp_path)

    assert dialog.planned_date_edit.date().toString("yyyy-MM-dd") == "2026-09-01"
    assert dialog.start_time_edit.time().toString("HH:mm") == "09:00"


def test_03_child_creation_causes_no_parent_schedule_update(temp_db):
    ids = _fresh_witness_project(temp_db)
    before = _raw_parent_schedule(temp_db, ids["parent_id"])

    with SqlWriteTrace(temp_db) as trace:
        result = WBSMutationService.create_child(
            temp_db,
            EntityRef.task(ids["parent_id"]),
            "New child",
        )

    assert result.success
    assert trace.task_schedule_updates() == []
    assert _raw_parent_schedule(temp_db, ids["parent_id"]) == before


def test_04_wbs_refresh_causes_no_parent_schedule_update(temp_db):
    ids = _fresh_witness_project(temp_db)
    before = _raw_parent_schedule(temp_db, ids["parent_id"])

    with SqlWriteTrace(temp_db) as trace:
        snapshot = WBSService.build_project_hierarchy(
            temp_db,
            project_id=ids["project_id"],
        )
        model = WBSItemModel(snapshot)
        model.set_db_manager(temp_db)
        model.rebuild_cpm_schedule()
        model.rebuild_rollups()

    assert trace.task_schedule_updates() == []
    assert _raw_parent_schedule(temp_db, ids["parent_id"]) == before


def test_05_gantt_refresh_causes_no_parent_schedule_update(temp_db):
    ids = _fresh_witness_project(temp_db)
    before = _raw_parent_schedule(temp_db, ids["parent_id"])

    with SqlWriteTrace(temp_db) as trace:
        _build_gantt_items(temp_db, ids["project_id"])

    assert trace.task_schedule_updates() == []
    assert _raw_parent_schedule(temp_db, ids["parent_id"]) == before


def test_06_real_gantt_open_path_uses_canonical_task_dialog(qapp, temp_db, tmp_path, monkeypatch):
    ids = _fresh_witness_project(temp_db)
    settings = SettingsManager(
        db_manager=temp_db,
        config_dir=tmp_path / "settings",
    )
    captured = []

    class SpyTaskDialog(TaskDialog):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            captured.append(self)

        def exec(self):
            return 0

    monkeypatch.setattr(gantt_view_module, "TaskDialog", SpyTaskDialog)
    view = GanttView(temp_db, settings_manager=settings)
    view.set_current_project(ids["project_id"])

    try:
        with SqlWriteTrace(temp_db) as trace:
            view.on_gantt_task_action("open", ids["parent_id"])
    finally:
        view.cleanup()
        view.close()

    assert trace.task_schedule_updates() == []
    assert len(captured) == 1
    dialog = captured[0]
    assert dialog.task_source_path == "DatabaseManager.get_task_by_id"
    assert dialog.task.id == ids["parent_id"]
    assert dialog.task.due_date is None
    assert dialog.task.planned_end_time is None
    assert dialog.task.estimated_duration == 7200


def test_07_task_dialog_displays_raw_duration(qapp, temp_db, tmp_path):
    ids = _fresh_witness_project(temp_db)

    dialog = _open_parent_dialog(temp_db, ids["parent_id"], tmp_path)

    assert dialog.duration_spin.value() == 7200
    assert dialog.duration_spin.isReadOnly() is False


def test_08_task_dialog_finish_none_semantics(qapp, temp_db, tmp_path):
    ids = _fresh_witness_project(temp_db)

    dialog = _open_parent_dialog(temp_db, ids["parent_id"], tmp_path)

    assert dialog.planned_finish_checkbox.isChecked() is False
    assert dialog.task.due_date is None
    assert dialog.task.planned_end_time is None


def test_09_wbs_summary_still_sep1_to_sep5(temp_db):
    ids = _fresh_witness_project(temp_db)
    _, rollups = _rollups(temp_db, ids["project_id"])
    summary = rollups[EntityRef.task(ids["parent_id"])]

    assert summary.planned_start.strftime("%Y-%m-%d %H:%M") == "2026-09-01 09:00"
    assert summary.planned_finish.strftime("%Y-%m-%d %H:%M") == "2026-09-05 09:00"
    assert summary.planned_elapsed_minutes == 5760


def test_10_gantt_summary_still_sep1_to_sep5(temp_db):
    ids = _fresh_witness_project(temp_db)
    foundation = _find_gantt_item(
        _build_gantt_items(temp_db, ids["project_id"]),
        "task",
        ids["parent_id"],
    )

    assert foundation.gantt_is_summary is True
    assert foundation.gantt_summary_planned_start.strftime("%Y-%m-%d %H:%M") == "2026-09-01 09:00"
    assert foundation.gantt_summary_planned_finish.strftime("%Y-%m-%d %H:%M") == "2026-09-05 09:00"
    assert foundation.gantt_summary_planned_elapsed_minutes == 5760


def test_11_summary_aliases_do_not_leak_into_task_dialog(qapp, temp_db, tmp_path):
    ids = _fresh_witness_project(temp_db)
    poisoned = Task(
        id=ids["parent_id"],
        title="Foundation",
        project_id=ids["project_id"],
        planned_date="2026-09-01",
        due_date="2026-09-05",
        planned_start_time="09:00",
        planned_end_time="09:00",
        estimated_duration=5760,
    )
    poisoned.gantt_is_summary = True
    poisoned.gantt_summary_planned_finish = "2026-09-05 09:00"
    poisoned.gantt_summary_planned_elapsed_minutes = 5760

    settings = SettingsManager(
        db_manager=temp_db,
        config_dir=tmp_path / "settings",
    )
    dialog = TaskDialog(
        TaskController(temp_db).get_all_projects(),
        poisoned,
        db_manager=temp_db,
        settings_manager=settings,
    )

    assert dialog.task_source_path == "DatabaseManager.get_task_by_id"
    assert dialog.planned_finish_checkbox.isChecked() is False
    assert dialog.task.due_date is None
    assert dialog.duration_spin.value() == 7200


def test_12_cache_invalidation_rebuilds_from_db_after_child_mutation(temp_db):
    ids = _fresh_witness_project(temp_db)
    snapshot, first_rollups = _rollups(temp_db, ids["project_id"])
    assert first_rollups[EntityRef.task(ids["parent_id"])].leaf_count == 2

    result = WBSMutationService.create_child(
        temp_db,
        EntityRef.task(ids["parent_id"]),
        "Third child",
    )
    assert result.success

    WBSRollupService.clear_cache()
    snapshot = WBSService.build_project_hierarchy(temp_db, project_id=ids["project_id"])
    second = WBSRollupService.compute_all_rollups(snapshot, temp_db)

    assert second[EntityRef.task(ids["parent_id"])].leaf_count == 3
    assert _raw_parent_schedule(temp_db, ids["parent_id"])["estimated_duration"] == 7200


def test_13_save_reopen_preserves_raw_inputs(qapp, temp_db, tmp_path):
    ids = _fresh_witness_project(temp_db)
    before = _raw_parent_schedule(temp_db, ids["parent_id"])

    first = _open_parent_dialog(temp_db, ids["parent_id"], tmp_path)
    first.on_save()
    TaskController(temp_db).update_task(first.get_task())
    reopened = _open_parent_dialog(temp_db, ids["parent_id"], tmp_path)

    assert _raw_parent_schedule(temp_db, ids["parent_id"]) == before
    assert reopened.duration_spin.value() == 7200
    assert reopened.planned_finish_checkbox.isChecked() is False


def test_14_app_restart_reopens_raw_inputs(qapp, tmp_path):
    db_path = tmp_path / "restart_witness.db"
    db = DatabaseManager.for_test(str(db_path))
    ids = _fresh_witness_project(db)
    before = _raw_parent_schedule(db, ids["parent_id"])
    db.close()

    restarted = DatabaseManager.for_test(str(db_path))
    try:
        dialog = _open_parent_dialog(restarted, ids["parent_id"], tmp_path)
        assert _raw_parent_schedule(restarted, ids["parent_id"]) == before
        assert dialog.task_source_path == "DatabaseManager.get_task_by_id"
        assert dialog.duration_spin.value() == 7200
        assert dialog.planned_finish_checkbox.isChecked() is False
    finally:
        restarted.close()


def test_15_nested_wbs_parent_raw_duration_preserved(temp_db):
    ids = _fresh_witness_project(temp_db)
    nested = temp_db.insert_subtask(
        ids["parent_id"],
        "Nested shell",
        position=2,
        planned_date="2026-09-10",
        planned_start_time="10:30",
        due_date=None,
        planned_end_time=None,
        estimated_duration=111,
        show_in_gantt=True,
    )
    temp_db.insert_subtask(
        ids["parent_id"],
        "Nested leaf",
        parent_subtask_id=nested,
        position=0,
        planned_date="2026-09-11",
        planned_start_time="09:00",
        due_date=None,
        planned_end_time=None,
        estimated_duration=60,
        show_in_gantt=True,
    )

    _rollups(temp_db, ids["project_id"])

    assert _raw_parent_schedule(temp_db, ids["parent_id"])["estimated_duration"] == 7200


def test_16_edit_child_preserves_parent_duration(temp_db):
    ids = _fresh_witness_project(temp_db)
    before = _raw_parent_schedule(temp_db, ids["parent_id"])

    temp_db.update_subtask(
        ids["excavation_id"],
        title="Excavation revised",
        is_completed=False,
        position=0,
        planned_date="2026-09-01",
        planned_start_time="08:00",
        due_date=None,
        planned_end_time=None,
        estimated_duration=3000,
        progress=60,
        show_in_gantt=True,
    )

    assert _raw_parent_schedule(temp_db, ids["parent_id"]) == before


def test_17_delete_child_preserves_parent_duration(temp_db):
    ids = _fresh_witness_project(temp_db)
    before = _raw_parent_schedule(temp_db, ids["parent_id"])

    assert temp_db.delete_subtask(ids["reinforcement_id"]) is True

    assert _raw_parent_schedule(temp_db, ids["parent_id"]) == before


def test_18_indent_preserves_parent_duration(temp_db):
    ids = _fresh_witness_project(temp_db)
    before = _raw_parent_schedule(temp_db, ids["parent_id"])

    result = WBSMutationService.indent(
        temp_db,
        EntityRef.subtask(ids["reinforcement_id"]),
    )

    assert result.success
    assert _raw_parent_schedule(temp_db, ids["parent_id"]) == before


def test_19_outdent_preserves_parent_duration(temp_db):
    ids = _fresh_witness_project(temp_db)
    before = _raw_parent_schedule(temp_db, ids["parent_id"])

    assert WBSMutationService.indent(
        temp_db,
        EntityRef.subtask(ids["reinforcement_id"]),
    ).success
    assert WBSMutationService.outdent(
        temp_db,
        EntityRef.subtask(ids["reinforcement_id"]),
    ).success

    assert _raw_parent_schedule(temp_db, ids["parent_id"]) == before


def test_20_production_db_hash_unchanged_by_forensic_temp_flow(qapp, tmp_path):
    before = _hash_file(PRODUCTION_DB)
    db = DatabaseManager.for_test(str(tmp_path / "prod_hash_witness.db"))
    try:
        ids = _fresh_witness_project(db)
        dialog = _open_parent_dialog(db, ids["parent_id"], tmp_path)
        dialog.on_save()
        TaskController(db).update_task(dialog.get_task())
        _build_gantt_items(db, ids["project_id"])
    finally:
        db.close()

    assert _hash_file(PRODUCTION_DB) == before


def test_21_contaminated_legacy_record_is_not_silently_repaired(qapp, temp_db, tmp_path):
    ids = _fresh_witness_project(temp_db)
    temp_db.update_task(
        {
            "due_date": "2026-09-05",
            "planned_end_time": "09:00",
            "estimated_duration": 5760,
        },
        ids["parent_id"],
    )

    dialog = _open_parent_dialog(temp_db, ids["parent_id"], tmp_path)

    assert dialog.task_source_path == "DatabaseManager.get_task_by_id"
    assert dialog.planned_finish_checkbox.isChecked() is True
    assert dialog.due_date_edit.date().toString("yyyy-MM-dd") == "2026-09-05"
    assert dialog.end_time_edit.time().toString("HH:mm") == "09:00"
    assert dialog.duration_spin.value() == 5760
    assert temp_db.get_task_by_id(ids["parent_id"])["estimated_duration"] == 5760
