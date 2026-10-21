import inspect
import json

import pytest

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task
from todo_bird_app.services.dependency_authoring_service import storage_dependency
from todo_bird_app.services.gantt_wbs_adapter import GanttWBSAdapter
from todo_bird_app.services.schedule_details_formatter import (
    ScheduleDetailsFormatter,
    ScheduleDetailsModel,
)
from todo_bird_app.services.wbs_service import EntityRef, WBSService


def _complete_plain_text():
    model = ScheduleDetailsModel(
        title="Cycle Task 9",
        entity_type="task",
        entity_id=9,
        depth=0,
        wbs_code="1.2.9",
        wbs_path="Project > Cycle Task 9",
        parent_path="Project",
        project_id=10,
        project_name="SCHEDULING WITNESS FINAL",
        status="Planned",
        priority="Medium",
        progress=25,
        planned_start="2026-09-02 09:00",
        planned_finish="2026-09-04 09:00",
        planned_duration_minutes=2880,
        planned_effort_minutes=480,
        daily_dedication_minutes=120,
        gantt_bar_start="2026-09-02 09:00",
        gantt_bar_finish="2026-09-04 09:00",
        gantt_bar_left_x=112.0,
        gantt_bar_right_x=256.0,
        has_cpm=True,
        cpm_analysis_status="analyzed",
        cpm_es="2026-09-02 09:00",
        cpm_ef="2026-09-04 09:00",
        cpm_ls="2026-09-03 09:00",
        cpm_lf="2026-09-05 09:00",
        cpm_tf=1440,
        cpm_ff=60,
        cpm_is_critical=False,
        predecessors=[
            "Project > Excavation Final | FS | Lag 0 min",
            "Project > Formwork | SS | Lag 120 min",
        ],
        successors=[
            "Project > Concrete Pour | FF | Lead 60 min",
            "Project > Handover | SF | Lag 0 min",
        ],
        constraint_type="SNET",
        constraint_datetime="2026-09-02 09:00",
        deadline_datetime="2026-09-10 17:00",
        calendar_name="Project Calendar #10",
        working_weekdays=(0, 1, 2, 3, 4),
        has_baseline=True,
        baseline_start="2026-09-01 09:00",
        baseline_finish="2026-09-03 09:00",
        baseline_start_variance_minutes=1440,
        baseline_variance_minutes=1440,
        has_revision=True,
        revision_name="Revision 1",
        revision_start="2026-09-02 09:00",
        revision_finish="2026-09-04 09:00",
        revision_variance_minutes=0,
        actual_state="in_progress",
        actual_start="2026-09-02 10:00",
        actual_duration_minutes=180,
        actual_elapsed_span_minutes=240,
        actual_variance_display="+1h Late Start",
    )
    return ScheduleDetailsFormatter.format_plain_text(model)


COMPLETE_CONTRACT_NEEDLES = [
    "Task: Cycle Task 9",
    "Type: Task",
    "Project: SCHEDULING WITNESS FINAL",
    "WBS Path / Parent: Project > Cycle Task 9",
    "WBS Code: 1.2.9",
    "Status: Planned",
    "Priority: Medium",
    "--- Planned Input ---",
    "Planned Start: 2026-09-02 09:00",
    "Planned/Target Finish: 2026-09-04 09:00",
    "Planned Finish: 2026-09-04 09:00",
    "Estimated Duration: 2.00 days",
    "Estimated Duration Minutes: 2880",
    "Planned Duration: 2d (2880 min)",
    "Planned Effort: 8h (480 min)",
    "Daily Dedication: 2h (120 min)",
    "Progress: 25%",
    "Gantt Bar Start: 2026-09-02 09:00",
    "Gantt Bar Finish: 2026-09-04 09:00",
    "Gantt Bar Left X: 112.00",
    "Gantt Bar Right X: 256.00",
    "--- Current Forecast / CPM ---",
    "CPM Status: Analyzed",
    "ES: 2026-09-02 09:00",
    "EF: 2026-09-04 09:00",
    "LS: 2026-09-03 09:00",
    "LF: 2026-09-05 09:00",
    "Total Float: 1d (1440 min)",
    "Free Float: 1h (60 min)",
    "Critical: No",
    "--- Dependencies ---",
    "Predecessors:",
    "Project > Excavation Final | FS | Lag 0 min",
    "Project > Formwork | SS | Lag 120 min",
    "Successors:",
    "Project > Concrete Pour | FF | Lead 60 min",
    "Project > Handover | SF | Lag 0 min",
    "--- Constraint / Deadline ---",
    "Constraint: SNET (2026-09-02 09:00)",
    "Constraint Type: SNET",
    "Constraint Date: 2026-09-02 09:00",
    "Deadline: 2026-09-10 17:00",
    "--- Calendar ---",
    "Effective Project Calendar: Project Calendar #10",
    "Working Weekdays: Mon, Tue, Wed, Thu, Fri",
    "--- Baseline / Revision ---",
    "Original Baseline: 2026-09-01 09:00",
    "Baseline Start: 2026-09-01 09:00",
    "Baseline Finish: 2026-09-03 09:00",
    "Approved Revision: Revision 1",
    "Revision Start: 2026-09-02 09:00",
    "Revision Finish: 2026-09-04 09:00",
    "Current Forecast Variance vs Baseline:",
    "Current Forecast Variance vs Revision:",
    "--- Actual ---",
    "Actual Tracking: In Progress",
    "Actual: 2026-09-02 10:00 -> In Progress (180 min logged)",
    "Actual Start: 2026-09-02 10:00",
    "Actual Finish: In Progress",
    "Actual Elapsed Span: 240 min",
    "Execution Variance: +1h Late Start",
]


@pytest.mark.parametrize("needle", COMPLETE_CONTRACT_NEEDLES)
def test_complete_schedule_details_plain_text_contract_exposes_field(needle):
    assert needle in _complete_plain_text()


NOT_ANALYZED_NEEDLES = [
    "CPM Status: Not analyzed",
    "ES: Not analyzed",
    "EF: Not analyzed",
    "LS: Not analyzed",
    "LF: Not analyzed",
    "Total Float: Not analyzed",
    "Free Float: Not analyzed",
    "Critical: Not analyzed",
    "Successors: None",
    "Constraint Type: None",
    "Constraint Date: None",
    "Deadline: None",
    "Original Baseline: Not Baselined",
    "Approved Revision: None",
    "Actual Tracking: Not Tracked",
]


@pytest.mark.parametrize("needle", NOT_ANALYZED_NEEDLES)
def test_missing_schedule_details_are_explicit_without_fabricated_values(needle):
    plain = ScheduleDetailsFormatter.format_plain_text(
        ScheduleDetailsModel(title="Unanalyzed")
    )
    assert needle in plain
    assert "2026-" not in plain


@pytest.fixture
def details_db(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "schedule_details.db"))
    with db.get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO projects
                (id, name, color, working_weekdays)
            VALUES
                (10, 'SCHEDULING WITNESS FINAL', '#2563EB', '[0,1,2,3,4]');
            """
        )
        conn.commit()

    pred_id = db.insert_task(
        Task(
            title="Excavation Final",
            project_id=10,
            planned_date="2026-09-01",
            due_date="2026-09-02",
            planned_start_time="09:00",
            planned_end_time="09:00",
            estimated_duration=1440,
            planned_effort_minutes=480,
            daily_dedication_minutes=240,
            show_in_gantt=True,
        ).to_dict()
    )
    cycle_id = db.insert_task(
        Task(
            title="Cycle Task 9",
            project_id=10,
            planned_date="2026-09-02",
            due_date="2026-09-04",
            planned_start_time="09:00",
            planned_end_time="09:00",
            estimated_duration=2880,
            planned_effort_minutes=720,
            daily_dedication_minutes=240,
            progress=10,
            show_in_gantt=True,
            baseline_start="2026-09-02 09:00",
            baseline_finish="2026-09-04 09:00",
            baseline_duration_minutes=2880,
            constraint_type="SNET",
            constraint_datetime="2026-09-02 09:00",
            deadline_datetime="2026-09-07 17:00",
        ).to_dict()
    )
    succ_id = db.insert_task(
        Task(
            title="Concrete Pour",
            project_id=10,
            planned_date="2026-09-04",
            due_date="2026-09-05",
            planned_start_time="09:00",
            planned_end_time="09:00",
            estimated_duration=1440,
            show_in_gantt=True,
        ).to_dict()
    )
    parent_id = db.insert_task(
        Task(
            title="Foundation",
            project_id=10,
            planned_date="2026-09-01",
            due_date="2026-09-06",
            planned_start_time="09:00",
            planned_end_time="09:00",
            estimated_duration=4320,
            show_in_gantt=True,
        ).to_dict()
    )
    sub_id = db.insert_subtask(
        parent_id,
        "Reinforcement Final",
        planned_date="2026-09-03",
        due_date="2026-09-04",
        planned_start_time="09:00",
        planned_end_time="09:00",
        estimated_duration=1440,
        planned_effort_minutes=480,
        daily_dedication_minutes=240,
        show_in_gantt=True,
        dependencies=[storage_dependency(EntityRef.task(pred_id), "SS", 120)],
    )
    qa_parent_id = db.insert_subtask(
        parent_id,
        "QA Parent",
        planned_date="2026-09-04",
        due_date="2026-09-04",
        planned_start_time="09:00",
        planned_end_time="17:00",
        estimated_duration=480,
        show_in_gantt=True,
    )
    nested_id = db.insert_subtask(
        parent_id,
        "Nested QA",
        parent_subtask_id=qa_parent_id,
        planned_date="2026-09-04",
        due_date="2026-09-04",
        planned_start_time="09:00",
        planned_end_time="17:00",
        estimated_duration=480,
        show_in_gantt=True,
    )

    with db.get_connection() as conn:
        conn.execute(
            "UPDATE tasks SET dependencies = ? WHERE id = ?;",
            (
                json.dumps(
                    [
                        storage_dependency(EntityRef.task(pred_id), "FS", 0),
                        storage_dependency(EntityRef.subtask(sub_id), "SS", 120),
                    ]
                ),
                cycle_id,
            ),
        )
        conn.execute(
            "UPDATE tasks SET dependencies = ? WHERE id = ?;",
            (
                json.dumps(
                    [
                        storage_dependency(EntityRef.task(cycle_id), "FF", -60),
                    ]
                ),
                succ_id,
            ),
        )
        conn.commit()

    version_id = db.create_schedule_version(
        project_id=10,
        name="Revision 1",
        version_type="approved_revision",
        approved_at="2026-09-02T12:00:00",
        items=[
            {
                "entity_type": "task",
                "entity_id": cycle_id,
                "title": "Cycle Task 9",
                "wbs_path": "Cycle Task 9",
                "sort_order": 1,
                "start": "2026-09-02 09:00",
                "finish": "2026-09-04 09:00",
                "duration_minutes": 2880,
                "planned_effort_minutes": 720,
            }
        ],
    )

    return {
        "db": db,
        "pred_id": pred_id,
        "cycle_id": cycle_id,
        "succ_id": succ_id,
        "parent_id": parent_id,
        "sub_id": sub_id,
        "qa_parent_id": qa_parent_id,
        "nested_id": nested_id,
        "version_id": version_id,
    }


def _rows(details_db):
    db = details_db["db"]
    snapshot = WBSService.build_project_hierarchy(db, project_id=10)
    return GanttWBSAdapter.build_project_rows(snapshot, db)


def _row_by_key(details_db, key):
    return next(row for row in _rows(details_db) if row.key == key)


def test_collector_populates_project_name_from_db_when_caller_passes_blank(details_db):
    db = details_db["db"]
    task = Task.from_row(db.get_task_by_id(details_db["cycle_id"]))

    model = ScheduleDetailsFormatter.build_from_entity(
        task,
        project_name="",
        db_manager=db,
    )

    assert model.project_name == "SCHEDULING WITNESS FINAL"


def test_cycle_task_gantt_row_exposes_planned_bar_dates(details_db):
    row = _row_by_key(details_db, EntityRef.task(details_db["cycle_id"]))
    model = ScheduleDetailsFormatter.build_from_entity(row, db_manager=details_db["db"])
    plain = ScheduleDetailsFormatter.format_plain_text(model)

    assert model.planned_start == model.gantt_bar_start
    assert model.planned_finish == model.gantt_bar_finish
    assert "Gantt Bar Start:" in plain
    assert "Gantt Bar Finish:" in plain


def test_dependency_predecessors_are_typed_and_named_by_wbs_path(details_db):
    row = _row_by_key(details_db, EntityRef.task(details_db["cycle_id"]))
    model = ScheduleDetailsFormatter.build_from_entity(row, db_manager=details_db["db"])

    assert any("Excavation Final | FS | Lag 0 min" in item for item in model.predecessors)
    assert any("Foundation > Reinforcement Final | SS | Lag 120 min" in item for item in model.predecessors)


def test_dependency_successors_are_exposed_from_project_snapshot(details_db):
    row = _row_by_key(details_db, EntityRef.task(details_db["cycle_id"]))
    model = ScheduleDetailsFormatter.build_from_entity(row, db_manager=details_db["db"])

    assert any("Concrete Pour | FF | Lead 60 min" in item for item in model.successors)


def test_task_subtask_nested_and_summary_types_are_distinguished(details_db):
    db = details_db["db"]
    task_row = _row_by_key(details_db, EntityRef.task(details_db["cycle_id"]))
    subtask_row = _row_by_key(details_db, EntityRef.subtask(details_db["sub_id"]))
    nested_row = _row_by_key(details_db, EntityRef.subtask(details_db["nested_id"]))
    summary_row = _row_by_key(details_db, EntityRef.task(details_db["parent_id"]))

    assert ScheduleDetailsFormatter.format_type_label(
        ScheduleDetailsFormatter.build_from_entity(task_row, db_manager=db)
    ) == "Task"
    assert ScheduleDetailsFormatter.format_type_label(
        ScheduleDetailsFormatter.build_from_entity(subtask_row, db_manager=db)
    ) == "Subtask"
    assert ScheduleDetailsFormatter.format_type_label(
        ScheduleDetailsFormatter.build_from_entity(nested_row, db_manager=db)
    ) == "Level 2 Subtask"
    summary_model = ScheduleDetailsFormatter.build_from_entity(summary_row, db_manager=db)
    assert ScheduleDetailsFormatter.format_type_label(summary_model) == "Summary"
    assert "Summary Source: Derived WBS summary values" in ScheduleDetailsFormatter.format_plain_text(summary_model)


def test_gantt_and_wbs_schedule_details_match_shared_fields(details_db):
    db = details_db["db"]
    row = _row_by_key(details_db, EntityRef.task(details_db["cycle_id"]))
    gantt_task = Task.from_row(db.get_task_by_id(details_db["cycle_id"]))
    gantt_task.gantt_entity_type = row.key.entity_type
    gantt_task.gantt_entity_id = row.key.entity_id
    gantt_task.gantt_item_type = row.key.entity_type
    gantt_task.gantt_wbs_key = str(row.key)
    gantt_task.gantt_wbs_code = row.wbs_code
    gantt_task.gantt_depth = row.depth
    gantt_task.gantt_planned_start = row.planned_start
    gantt_task.gantt_planned_finish = row.planned_finish
    gantt_task.cpm_earliest_start = row.cpm_earliest_start
    gantt_task.cpm_earliest_finish = row.cpm_earliest_finish
    gantt_task.cpm_latest_start = row.cpm_latest_start
    gantt_task.cpm_latest_finish = row.cpm_latest_finish
    gantt_task.cpm_total_float = row.cpm_total_float_minutes
    gantt_task.cpm_free_float = row.cpm_free_float_minutes
    gantt_task.cpm_is_critical = row.cpm_is_critical
    gantt_task.gantt_cpm_analysis_status = row.cpm_analysis_status
    gantt_task.source_payload = row.source_payload

    wbs_model = ScheduleDetailsFormatter.build_from_entity(row, db_manager=db)
    gantt_model = ScheduleDetailsFormatter.build_from_entity(gantt_task, db_manager=db)

    assert gantt_model.project_name == wbs_model.project_name
    assert gantt_model.planned_start == wbs_model.planned_start
    assert gantt_model.planned_finish == wbs_model.planned_finish
    assert gantt_model.cpm_es == wbs_model.cpm_es
    assert gantt_model.cpm_ef == wbs_model.cpm_ef
    assert gantt_model.cpm_tf == wbs_model.cpm_tf
    assert gantt_model.predecessors == wbs_model.predecessors


def test_calendar_and_revision_metadata_are_exposed_when_available(details_db):
    row = _row_by_key(details_db, EntityRef.task(details_db["cycle_id"]))
    model = ScheduleDetailsFormatter.build_from_entity(row, db_manager=details_db["db"])
    plain = ScheduleDetailsFormatter.format_plain_text(model)

    assert model.calendar_name == "Project Calendar #10"
    assert model.working_weekdays == (0, 1, 2, 3, 4)
    assert model.has_revision is True
    assert "Approved Revision: Revision 1" in plain


def test_finished_actual_state_exposes_finish_and_elapsed_span():
    model = ScheduleDetailsModel(
        title="Finished Actual",
        actual_state="completed",
        actual_start="2026-09-02 09:00",
        actual_finish="2026-09-02 17:00",
        actual_duration_minutes=360,
        actual_elapsed_span_minutes=480,
    )
    plain = ScheduleDetailsFormatter.format_plain_text(model)

    assert "Actual Tracking: Finished" in plain
    assert "Actual Finish: 2026-09-02 17:00" in plain
    assert "Actual Elapsed Span: 480 min" in plain


def test_formatter_does_not_call_cpm_or_dependency_solvers():
    from todo_bird_app.services import schedule_details_formatter

    source = inspect.getsource(schedule_details_formatter)
    assert "calculate_wbs_cpm" not in source
    assert "calculate_schedule" not in source
    assert "CPMSchedulingService" not in source
    assert "GanttDependencyEngine" not in source


def test_gantt_chart_attaches_rendered_x_coordinates_for_inspector():
    from todo_bird_app.gantt.gantt_chart import GanttChartWidget

    source = inspect.getsource(GanttChartWidget.rebuild_chart)
    assert "gantt_bar_left_x" in source
    assert "gantt_bar_right_x" in source


def test_wbs_project_view_uses_schedule_rich_row_for_details():
    from todo_bird_app.views.wbs_project_view import WBSProjectView

    source = inspect.getsource(WBSProjectView._schedule_details_entity_for_key)
    assert "GanttWBSAdapter.build_rows" in source
    assert "cpm_result" in source


def test_gantt_task_action_open_branch_stays_in_action_handler():
    from todo_bird_app.views.gantt_view import GanttView

    action_source = inspect.getsource(GanttView.on_gantt_task_action)
    helper_source = inspect.getsource(GanttView._schedule_details_project_name)

    assert 'action == "open"' in action_source
    assert 'action == "complete"' in action_source
    assert 'action == "open"' not in helper_source
    assert 'action == "complete"' not in helper_source


def test_wbs_schedule_details_project_name_does_not_require_project_attribute():
    from types import SimpleNamespace

    from todo_bird_app.views.wbs_project_view import WBSProjectView

    class ProjectDb:
        def get_project(self, project_id):
            assert project_id == 10
            return {"name": "SCHEDULING WITNESS FINAL"}

    view = SimpleNamespace(project_id=10, db_manager=ProjectDb())

    assert WBSProjectView._schedule_details_project_name(view) == "SCHEDULING WITNESS FINAL"
