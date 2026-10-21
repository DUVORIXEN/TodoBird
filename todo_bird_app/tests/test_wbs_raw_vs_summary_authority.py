from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager
from todo_bird_app.gantt.gantt_chart import GanttChartWidget
from todo_bird_app.models.task import Task
from todo_bird_app.models.wbs_item_model import WBSItemModel
from todo_bird_app.services.gantt_wbs_adapter import GanttWBSAdapter
from todo_bird_app.services.wbs_mutation_service import WBSMutationService
from todo_bird_app.services.wbs_rollup_service import WBSRollupService
from todo_bird_app.services.wbs_service import EntityRef, WBSService
from todo_bird_app.views.gantt_view import GanttView


RAW_SCHEDULE_FIELDS = (
    "planned_date",
    "due_date",
    "planned_start_time",
    "planned_end_time",
    "estimated_duration",
    "planned_effort_minutes",
)


@pytest.fixture(scope="module", autouse=True)
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def temp_db(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "wbs_raw_summary.db"))
    WBSRollupService.clear_cache()
    yield db
    WBSRollupService.clear_cache()
    db.close()


def _raw_task_row(db, task_id):
    return db.get_task_by_id(task_id)


def _raw_parent_schedule(db, task_id):
    row = _raw_task_row(db, task_id)
    return {field: row[field] for field in RAW_SCHEDULE_FIELDS}


def _task_objects_for_project(db, project_id):
    return [Task.from_row(row) for row in db.get_tasks_by_project(project_id)]


def _fake_view(db, project_id):
    class FakeGanttView:
        _gantt_schedule_payload_targets_summary = (
            GanttView._gantt_schedule_payload_targets_summary
        )

        def __init__(self):
            self.db_manager = db
            self.current_project_id = project_id
            self.messages = []

        def show_feedback_message(self, text):
            self.messages.append(text)

    return FakeGanttView()


def _build_gantt_items(db, project_id):
    fake = _fake_view(db, project_id)
    return GanttView._build_phase1d_wbs_gantt_items(
        fake,
        _task_objects_for_project(db, project_id),
    )


def _find_item(items, entity_type, entity_id):
    for item in items:
        if (
            getattr(item, "gantt_entity_type", None) == entity_type
            and int(getattr(item, "gantt_entity_id", 0)) == int(entity_id)
        ):
            return item
    raise AssertionError(f"Missing Gantt item {entity_type}:{entity_id}")


def _witness_project(db):
    project_id = db.insert_project({"name": "SCHEDULING WITNESS"})
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
            "priority": "High",
            "category": "Work",
            "description": "Parent raw plan must remain operator input.",
        }
    )
    excavation_id = db.insert_subtask(
        parent_id,
        "Excavation",
        position=0,
        planned_date="2026-09-01",
        planned_start_time="09:00",
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


def _nested_summary_project(db):
    ids = _witness_project(db)
    shell_id = db.insert_subtask(
        ids["parent_id"],
        "Concrete Package",
        position=2,
        planned_date="2026-09-10",
        planned_start_time="10:30",
        estimated_duration=111,
        planned_effort_minutes=222,
        progress=10,
        show_in_gantt=True,
    )
    child_id = db.insert_subtask(
        ids["parent_id"],
        "Pour Slab",
        position=0,
        parent_subtask_id=shell_id,
        planned_date="2026-09-11",
        planned_start_time="09:00",
        estimated_duration=60,
        planned_effort_minutes=60,
        progress=80,
        show_in_gantt=True,
    )
    ids["shell_id"] = shell_id
    ids["shell_child_id"] = child_id
    return ids


def _summary_rollup(db, project_id, key):
    snapshot = WBSService.build_project_hierarchy(db, project_id=project_id)
    return WBSRollupService.compute_all_rollups(snapshot, db)[key]


def _attempt_summary_schedule_write(db, project_id, task_id, payload=None):
    fake = _fake_view(db, project_id)
    write_payload = {
        "item_type": "task",
        "task_id": task_id,
        "title": "Foundation",
        "planned_date": "2026-09-09",
        "due_date": "2026-09-12",
        "planned_start_time": "11:00",
        "planned_end_time": "17:00",
        "estimated_duration": 999,
        "zoom_mode": "daily",
        "delta_days": 8,
    }
    if payload:
        write_payload.update(payload)
    GanttView.on_gantt_schedule_change(fake, write_payload)
    return fake


def test_human_witness_foundation_summary_no_longer_replaces_parent_raw_inputs(temp_db):
    ids = _witness_project(temp_db)
    before = _raw_parent_schedule(temp_db, ids["parent_id"])

    foundation = _find_item(
        _build_gantt_items(temp_db, ids["project_id"]),
        "task",
        ids["parent_id"],
    )

    assert foundation.gantt_is_summary is True
    assert foundation.gantt_read_only is True
    assert foundation.planned_date == "2026-09-01"
    assert foundation.planned_start_time == "09:00"
    assert foundation.due_date is None
    assert foundation.planned_end_time is None
    assert foundation.estimated_duration == 7200
    assert foundation.planned_effort_minutes == 3000
    assert foundation.gantt_summary_planned_start.strftime("%Y-%m-%d %H:%M") == "2026-09-01 09:00"
    assert foundation.gantt_summary_planned_finish.strftime("%Y-%m-%d %H:%M") == "2026-09-05 09:00"
    assert foundation.gantt_summary_planned_elapsed_minutes == 5760
    assert foundation.gantt_planned_finish.strftime("%Y-%m-%d %H:%M") == "2026-09-05 09:00"
    assert _raw_parent_schedule(temp_db, ids["parent_id"]) == before


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("planned_date", "2026-09-01"),
        ("due_date", None),
        ("planned_start_time", "09:00"),
        ("planned_end_time", None),
        ("estimated_duration", 7200),
        ("planned_effort_minutes", 3000),
        ("daily_dedication_minutes", 480),
        ("description", "Parent raw plan must remain operator input."),
    ],
)
def test_summary_presentation_uses_parent_raw_field_matrix(temp_db, field, expected):
    ids = _witness_project(temp_db)
    foundation = _find_item(
        _build_gantt_items(temp_db, ids["project_id"]),
        "task",
        ids["parent_id"],
    )

    assert getattr(foundation, field) == expected


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("gantt_summary_planned_start", "2026-09-01 09:00"),
        ("gantt_summary_planned_finish", "2026-09-05 09:00"),
        ("gantt_summary_planned_elapsed_minutes", 5760),
        ("gantt_rollup_planned_effort", 2400),
        ("gantt_rollup_leaf_count", 2),
        ("gantt_rollup_progress", 35),
        ("gantt_rollup_confidence", "full"),
    ],
)
def test_summary_derived_values_live_in_gantt_metadata_matrix(temp_db, field, expected):
    ids = _witness_project(temp_db)
    foundation = _find_item(
        _build_gantt_items(temp_db, ids["project_id"]),
        "task",
        ids["parent_id"],
    )
    actual = getattr(foundation, field)
    if hasattr(actual, "strftime"):
        actual = actual.strftime("%Y-%m-%d %H:%M")

    assert actual == expected


@pytest.mark.parametrize(
    ("raw_field", "derived_field"),
    [
        ("due_date", "gantt_summary_planned_finish"),
        ("planned_end_time", "gantt_summary_planned_finish"),
        ("estimated_duration", "gantt_summary_planned_elapsed_minutes"),
        ("planned_effort_minutes", "gantt_rollup_planned_effort"),
        ("progress", "gantt_rollup_progress"),
    ],
)
def test_rollup_values_are_distinct_from_parent_raw_authority_matrix(temp_db, raw_field, derived_field):
    ids = _witness_project(temp_db)
    foundation = _find_item(
        _build_gantt_items(temp_db, ids["project_id"]),
        "task",
        ids["parent_id"],
    )

    raw_value = getattr(foundation, raw_field)
    derived_value = getattr(foundation, derived_field)
    if hasattr(derived_value, "strftime"):
        derived_value = derived_value.strftime("%Y-%m-%d")

    assert raw_value != derived_value


@pytest.mark.parametrize(
    "operation",
    [
        "build_hierarchy",
        "compute_rollups",
        "get_project_rollup",
        "adapter_rows",
        "gantt_items",
        "wbs_model_rollup_roles",
        "clear_cache_recompute",
        "create_blank_child",
        "blocked_parent_schedule_payload",
        "flagged_parent_schedule_payload",
    ],
)
def test_read_only_operations_do_not_rewrite_parent_raw_schedule_matrix(temp_db, operation):
    ids = _witness_project(temp_db)
    before = _raw_parent_schedule(temp_db, ids["parent_id"])
    snapshot = WBSService.build_project_hierarchy(temp_db, project_id=ids["project_id"])

    if operation == "build_hierarchy":
        WBSService.build_project_hierarchy(temp_db, project_id=ids["project_id"])
    elif operation == "compute_rollups":
        WBSRollupService.compute_all_rollups(snapshot, temp_db)
    elif operation == "get_project_rollup":
        WBSRollupService.get_project_rollup(snapshot, temp_db)
    elif operation == "adapter_rows":
        GanttWBSAdapter.build_project_rows(snapshot, temp_db)
    elif operation == "gantt_items":
        _build_gantt_items(temp_db, ids["project_id"])
    elif operation == "wbs_model_rollup_roles":
        model = WBSItemModel(snapshot)
        model.set_db_manager(temp_db)
        idx = model.index(0, 0)
        assert model.data(idx, WBSItemModel.RollupPlannedFinishRole) is not None
    elif operation == "clear_cache_recompute":
        WBSRollupService.clear_cache()
        WBSRollupService.compute_all_rollups(snapshot, temp_db)
    elif operation == "create_blank_child":
        WBSMutationService.create_child(
            temp_db,
            EntityRef.task(ids["parent_id"]),
            "New unscheduled child",
        )
    elif operation == "blocked_parent_schedule_payload":
        _attempt_summary_schedule_write(temp_db, ids["project_id"], ids["parent_id"])
    elif operation == "flagged_parent_schedule_payload":
        _attempt_summary_schedule_write(
            temp_db,
            ids["project_id"],
            ids["parent_id"],
            {"gantt_is_summary": True},
        )

    assert _raw_parent_schedule(temp_db, ids["parent_id"]) == before


@pytest.mark.parametrize(
    "payload",
    [
        {"gantt_is_summary": True},
        {"is_summary": True},
        {"gantt_read_only": True},
        {"read_only": True},
        {},
        {"item_type": "task"},
        {"zoom_mode": "hourly"},
        {"edit_kind": "resize"},
    ],
)
def test_schedule_change_guard_blocks_summary_payload_matrix(temp_db, payload):
    ids = _witness_project(temp_db)
    before = _raw_parent_schedule(temp_db, ids["parent_id"])

    fake = _attempt_summary_schedule_write(
        temp_db,
        ids["project_id"],
        ids["parent_id"],
        payload,
    )

    assert _raw_parent_schedule(temp_db, ids["parent_id"]) == before
    assert fake.messages == ["WBS summary schedules are derived from children."]


@pytest.mark.parametrize(
    ("item_type", "schedule_payload", "expected_table", "expected_id_key"),
    [
        (
            "task",
            {
                "planned_date": "2026-10-01",
                "due_date": "2026-10-01",
                "planned_start_time": "08:00",
                "planned_end_time": "10:00",
                "estimated_duration": 120,
            },
            "tasks",
            "task_id",
        ),
        (
            "task",
            {
                "planned_date": "2026-10-02",
                "due_date": None,
                "planned_start_time": "09:30",
                "planned_end_time": None,
                "estimated_duration": 300,
            },
            "tasks",
            "task_id",
        ),
        (
            "subtask",
            {
                "planned_date": "2026-10-03",
                "due_date": "2026-10-03",
                "planned_start_time": "13:00",
                "planned_end_time": "14:00",
                "estimated_duration": 60,
            },
            "subtasks",
            "source_subtask_id",
        ),
        (
            "subtask",
            {
                "planned_date": "2026-10-04",
                "due_date": None,
                "planned_start_time": "07:45",
                "planned_end_time": None,
                "estimated_duration": 75,
            },
            "subtasks",
            "source_subtask_id",
        ),
    ],
)
def test_schedule_change_guard_allows_leaf_payload_matrix(
    temp_db,
    item_type,
    schedule_payload,
    expected_table,
    expected_id_key,
):
    project_id = temp_db.insert_project({"name": "Leaf Schedule Edits"})
    task_id = temp_db.insert_task(
        {
            "project_id": project_id,
            "title": "Leaf",
            "status": "Planned",
            "show_in_gantt": 1,
        }
    )
    source_subtask_id = None
    if item_type == "subtask":
        source_subtask_id = temp_db.insert_subtask(
            task_id,
            "Leaf Subtask",
            show_in_gantt=True,
        )

    fake = _fake_view(temp_db, project_id)
    fake._hourly_conflicts = lambda _payload: []
    fake._apply_dependency_auto_shift = lambda _task_id: (0, set())
    fake.refresh_data = lambda: None
    payload = {
        "item_type": item_type,
        "task_id": -source_subtask_id if item_type == "subtask" else task_id,
        "source_subtask_id": source_subtask_id,
        "title": "Leaf",
        "zoom_mode": "daily",
        "delta_days": 1,
    }
    payload.update(schedule_payload)

    GanttView.on_gantt_schedule_change(fake, payload)

    if expected_table == "tasks":
        row = temp_db.get_task_by_id(payload[expected_id_key])
    else:
        with temp_db.get_connection() as conn:
            row = dict(
                conn.execute(
                    "SELECT * FROM subtasks WHERE id = ?;",
                    (payload[expected_id_key],),
                ).fetchone()
            )
    for field, expected in schedule_payload.items():
        assert row[field] == expected


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("planned_date", "2026-09-10"),
        ("planned_start_time", "10:30"),
        ("estimated_duration", 111),
        ("planned_effort_minutes", 222),
        ("gantt_summary_planned_start", "2026-09-11 09:00"),
        ("gantt_summary_planned_elapsed_minutes", 60),
    ],
)
def test_nested_subtask_summary_keeps_own_raw_fields_matrix(temp_db, field, expected):
    ids = _nested_summary_project(temp_db)
    shell = _find_item(
        _build_gantt_items(temp_db, ids["project_id"]),
        "subtask",
        ids["shell_id"],
    )
    actual = getattr(shell, field)
    if hasattr(actual, "strftime"):
        actual = actual.strftime("%Y-%m-%d %H:%M")

    assert actual == expected


@pytest.mark.parametrize(
    ("method_name", "source_text"),
    [
        ("_build_schedule_payload", '"gantt_is_summary"'),
        ("_build_schedule_payload", '"gantt_read_only"'),
        ("_build_resize_payload", '"gantt_is_summary"'),
        ("_build_resize_payload", '"gantt_read_only"'),
    ],
)
def test_chart_payloads_are_self_describing_for_summary_guard_matrix(method_name, source_text):
    import inspect

    source = inspect.getsource(getattr(GanttChartWidget, method_name))

    assert source_text in source


def test_chart_apply_payload_noops_for_summary_task():
    task = Task(
        id=1,
        title="Summary",
        planned_date="2026-09-01",
        due_date=None,
        planned_start_time="09:00",
        planned_end_time=None,
        estimated_duration=7200,
    )
    task.gantt_is_summary = True
    item = SimpleNamespace(task=task)

    GanttChartWidget._apply_payload_to_task(
        SimpleNamespace(),
        item,
        {
            "planned_date": "2026-09-05",
            "due_date": "2026-09-05",
            "planned_start_time": "09:00",
            "planned_end_time": "09:00",
            "estimated_duration": 5760,
        },
    )

    assert task.planned_date == "2026-09-01"
    assert task.due_date is None
    assert task.planned_start_time == "09:00"
    assert task.planned_end_time is None
    assert task.estimated_duration == 7200


def test_wbs_rollup_service_and_adapter_remain_sql_read_only():
    import inspect
    import re

    rollup_source = inspect.getsource(WBSRollupService)
    adapter_source = inspect.getsource(GanttWBSAdapter)

    write_pattern = r"\b(INSERT|UPDATE|DELETE|REPLACE|DROP|ALTER)\b"
    assert re.search(write_pattern, rollup_source, re.IGNORECASE) is None
    assert re.search(write_pattern, adapter_source, re.IGNORECASE) is None
    assert ".commit(" not in rollup_source
    assert ".commit(" not in adapter_source


def test_task_dialog_schedule_widgets_are_bound_to_task_raw_fields():
    source = __import__(
        "inspect"
    ).getsource(__import__("todo_bird_app.widgets.task_dialog", fromlist=["TaskDialog"]).TaskDialog)

    assert "self.task.planned_date" in source
    assert "self.task.due_date" in source
    assert "self.task.planned_start_time" in source
    assert "self.task.planned_end_time" in source
    assert "self.task.estimated_duration" in source
    assert "gantt_summary_planned" not in source
