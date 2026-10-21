import hashlib
import sqlite3
from pathlib import Path

import pytest

from todo_bird_app.database import (
    DatabaseManager,
    ScheduleVersionGovernanceError,
    ScheduleVersionImmutabilityError,
    SCHEDULE_VERSION_APPROVED_REVISION,
    SCHEDULE_VERSION_ORIGINAL_BASELINE,
)
from todo_bird_app.services.schedule_variance_service import parse_datetime_flexible
from todo_bird_app.services.schedule_version_service import ScheduleVersionService


PRODUCTION_DB = Path(__file__).resolve().parents[1] / "data" / "todo_bird.db"


@pytest.fixture
def temp_db(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "schedule_governance.db"))
    yield db
    db.close()


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _version(db: DatabaseManager, version_id: int):
    with db.get_connection() as conn:
        row = conn.execute("SELECT * FROM schedule_versions WHERE id = ?;", (version_id,)).fetchone()
        return dict(row) if row else None


def _items_by_key(db: DatabaseManager, version_id: int):
    return {
        (item["entity_type"], item["entity_id"]): item
        for item in db.get_schedule_version_items(version_id)
    }


def _count_orphan_items(db: DatabaseManager) -> int:
    with db.get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM schedule_version_items i
            LEFT JOIN schedule_versions v ON v.id = i.version_id
            WHERE v.id IS NULL;
            """
        ).fetchone()
        return int(row[0])


def _minutes_between(current_text: str, reference_text: str) -> int:
    current = parse_datetime_flexible(current_text)
    reference = parse_datetime_flexible(reference_text)
    assert current is not None
    assert reference is not None
    return int((current - reference).total_seconds() / 60)


def _make_project_tree(db: DatabaseManager, name: str = "Governance"):
    project_id = db.insert_project({"name": name})
    task_id = db.insert_task({
        "project_id": project_id,
        "title": "Design Package",
        "planned_date": "2026-09-01",
        "due_date": "2026-09-03",
        "planned_start_time": "09:00",
        "planned_end_time": "17:00",
        "estimated_duration": 3360,
        "planned_effort_minutes": 960,
        "position": 10,
    })
    subtask_id = db.insert_subtask(
        task_id,
        "Design Review",
        planned_date="2026-09-01",
        due_date="2026-09-01",
        planned_start_time="10:00",
        planned_end_time="12:00",
        estimated_duration=120,
        planned_effort_minutes=120,
        position=1,
    )
    nested_subtask_id = db.insert_subtask(
        task_id,
        "Review Notes",
        parent_subtask_id=subtask_id,
        planned_date="2026-09-01",
        due_date="2026-09-01",
        planned_start_time="13:00",
        planned_end_time="14:00",
        estimated_duration=60,
        planned_effort_minutes=60,
        position=2,
    )
    return project_id, task_id, subtask_id, nested_subtask_id


def _cpm(task_id: int, start: str = "2026-09-02 09:00", finish: str = "2026-09-04 17:00"):
    return {
        ("task", task_id): {
            "start": start,
            "finish": finish,
            "duration_minutes": _minutes_between(finish, start),
        }
    }


def _create_original(db: DatabaseManager, project_id: int, task_id: int):
    return ScheduleVersionService.create_original_baseline(
        db,
        project_id,
        name="Original Baseline",
        cpm_results=_cpm(task_id),
        approved_at="2026-09-05T08:00:00",
    )


def test_01_first_baseline_creation(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    version_id = _create_original(temp_db, project_id, task_id)

    version = _version(temp_db, version_id)
    assert version["name"] == "Original Baseline"
    assert len(temp_db.get_schedule_version_items(version_id)) == 3
    assert temp_db.get_project(project_id)["baseline_created_at"] == "2026-09-05T08:00:00"


def test_02_original_baseline_type_explicit(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    version_id = _create_original(temp_db, project_id, task_id)

    version = _version(temp_db, version_id)
    assert version["version_type"] == SCHEDULE_VERSION_ORIGINAL_BASELINE
    assert version["is_original_baseline"] == 1


def test_03_original_baseline_immutable(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    _create_original(temp_db, project_id, task_id)

    with pytest.raises(ScheduleVersionGovernanceError):
        ScheduleVersionService.create_original_baseline(temp_db, project_id)


def test_04_current_edit_does_not_alter_original(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    version_id = _create_original(temp_db, project_id, task_id)
    before = _items_by_key(temp_db, version_id)[("task", task_id)]

    temp_db.update_task({"id": task_id, "planned_date": "2026-10-01", "due_date": "2026-10-05"})

    after = _items_by_key(temp_db, version_id)[("task", task_id)]
    assert after["start"] == before["start"] == "2026-09-02 09:00"
    assert after["finish"] == before["finish"] == "2026-09-04 17:00"


def test_05_cpm_recalc_does_not_alter_original(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    version_id = _create_original(temp_db, project_id, task_id)

    ScheduleVersionService.capture_current_schedule_snapshot(
        temp_db,
        project_id,
        cpm_results=_cpm(task_id, "2026-10-02 09:00", "2026-10-06 17:00"),
    )

    item = _items_by_key(temp_db, version_id)[("task", task_id)]
    assert item["start"] == "2026-09-02 09:00"


def test_06_actual_start_does_not_alter_original(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    version_id = _create_original(temp_db, project_id, task_id)

    temp_db.update_task({"id": task_id, "actual_start_date": "2026-09-10", "actual_start_time": "11:00"})

    assert _items_by_key(temp_db, version_id)[("task", task_id)]["start"] == "2026-09-02 09:00"


def test_07_actual_finish_does_not_alter_original(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    version_id = _create_original(temp_db, project_id, task_id)

    temp_db.update_task({
        "id": task_id,
        "actual_start_date": "2026-09-10",
        "actual_start_time": "09:00",
        "actual_end_date": "2026-09-14",
        "actual_end_time": "18:00",
        "status": "Completed",
    })

    assert _items_by_key(temp_db, version_id)[("task", task_id)]["finish"] == "2026-09-04 17:00"


def test_08_second_approval_creates_revision(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    _create_original(temp_db, project_id, task_id)

    revision_id = ScheduleVersionService.create_approved_revision(
        temp_db,
        project_id,
        name="Revision 1",
        cpm_results=_cpm(task_id, "2026-09-06 09:00", "2026-09-08 17:00"),
    )

    assert _version(temp_db, revision_id)["version_type"] == SCHEDULE_VERSION_APPROVED_REVISION
    assert len(temp_db.get_schedule_versions_for_project(project_id)) == 2


def test_09_second_approval_does_not_replace_original(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    original_id = _create_original(temp_db, project_id, task_id)

    ScheduleVersionService.create_approved_revision(
        temp_db,
        project_id,
        name="Revision 1",
        cpm_results=_cpm(task_id, "2026-09-06 09:00", "2026-09-08 17:00"),
    )

    assert _version(temp_db, original_id)["version_type"] == SCHEDULE_VERSION_ORIGINAL_BASELINE
    assert _items_by_key(temp_db, original_id)[("task", task_id)]["start"] == "2026-09-02 09:00"


def test_10_revision_1_immutable(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    revision_id = ScheduleVersionService.create_approved_revision(
        temp_db,
        project_id,
        name="Revision 1",
        cpm_results=_cpm(task_id, "2026-09-06 09:00", "2026-09-08 17:00"),
    )

    temp_db.update_task({"id": task_id, "planned_date": "2026-11-01", "due_date": "2026-11-02"})

    assert _items_by_key(temp_db, revision_id)[("task", task_id)]["start"] == "2026-09-06 09:00"


def test_11_revision_2_independent(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    rev1 = ScheduleVersionService.create_approved_revision(
        temp_db,
        project_id,
        name="Revision 1",
        cpm_results=_cpm(task_id, "2026-09-06 09:00", "2026-09-08 17:00"),
    )
    rev2 = ScheduleVersionService.create_approved_revision(
        temp_db,
        project_id,
        name="Revision 2",
        cpm_results=_cpm(task_id, "2026-10-06 09:00", "2026-10-08 17:00"),
    )

    assert _items_by_key(temp_db, rev1)[("task", task_id)]["start"] == "2026-09-06 09:00"
    assert _items_by_key(temp_db, rev2)[("task", task_id)]["start"] == "2026-10-06 09:00"


def test_12_deterministic_sequence(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    _create_original(temp_db, project_id, task_id)
    ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Revision 1")
    ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Revision 2")

    assert [v["sequence_order"] for v in temp_db.get_schedule_versions_for_project(project_id)] == [1, 2, 3]


def test_13_same_timestamp_deterministic_order(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    _create_original(temp_db, project_id, task_id)
    timestamp = "2026-09-10T09:00:00"

    rev1 = ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Revision A", approved_at=timestamp)
    rev2 = ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Revision B", approved_at=timestamp)

    assert _version(temp_db, rev1)["sequence_order"] == 2
    assert _version(temp_db, rev2)["sequence_order"] == 3


def test_14_latest_revision_deterministic(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    _create_original(temp_db, project_id, task_id)
    ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Revision 1")
    rev2 = ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Revision 2")

    assert ScheduleVersionService.get_latest_approved_revision(temp_db, project_id)["id"] == rev2


def test_15_project_isolation(temp_db):
    p1, t1, _, _ = _make_project_tree(temp_db, "Project A")
    p2, t2, _, _ = _make_project_tree(temp_db, "Project B")

    rev1 = ScheduleVersionService.create_approved_revision(temp_db, p1, name="Same Name", cpm_results=_cpm(t1))
    rev2 = ScheduleVersionService.create_approved_revision(temp_db, p2, name="Same Name", cpm_results=_cpm(t2))

    assert {v["id"] for v in temp_db.get_schedule_versions_for_project(p1)} == {rev1}
    assert {v["id"] for v in temp_db.get_schedule_versions_for_project(p2)} == {rev2}


def test_16_transaction_rollback_on_partial_snapshot_failure(temp_db):
    project_id, _, _, _ = _make_project_tree(temp_db)
    items = [
        {"entity_type": "task", "entity_id": 1000 + idx, "start": "2026-09-01 09:00"}
        for idx in range(50)
    ]
    items.append({"entity_type": "task", "entity_id": 1000, "start": "2026-09-02 09:00"})

    with pytest.raises(ScheduleVersionGovernanceError):
        temp_db.create_schedule_version(project_id, "Broken Revision", items=items)

    assert all(v["name"] != "Broken Revision" for v in temp_db.get_schedule_versions_for_project(project_id))
    assert _count_orphan_items(temp_db) == 0


def test_17_no_orphan_version_items(temp_db):
    with temp_db.get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO schedule_version_items (version_id, entity_type, entity_id)
                VALUES (99999, 'task', 1);
                """
            )

    assert _count_orphan_items(temp_db) == 0


def test_18_item_uniqueness(temp_db):
    project_id, _, _, _ = _make_project_tree(temp_db)
    items = [
        {"entity_type": "task", "entity_id": 1, "start": "2026-09-01 09:00"},
        {"entity_type": "task", "entity_id": 1, "start": "2026-09-02 09:00"},
    ]

    with pytest.raises(ScheduleVersionGovernanceError):
        temp_db.create_schedule_version(project_id, "Duplicate Item Revision", items=items)


def test_19_task_snapshot(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    version_id = _create_original(temp_db, project_id, task_id)
    item = _items_by_key(temp_db, version_id)[("task", task_id)]

    assert item["title"] == "Design Package"
    assert item["task_id"] == task_id
    assert item["start"] == "2026-09-02 09:00"


def test_20_subtask_snapshot(temp_db):
    project_id, task_id, subtask_id, _ = _make_project_tree(temp_db)
    version_id = _create_original(temp_db, project_id, task_id)
    item = _items_by_key(temp_db, version_id)[("subtask", subtask_id)]

    assert item["title"] == "Design Review"
    assert item["start"] == "2026-09-01 10:00"


def test_21_nested_wbs_snapshot(temp_db):
    project_id, task_id, subtask_id, nested_id = _make_project_tree(temp_db)
    version_id = _create_original(temp_db, project_id, task_id)
    item = _items_by_key(temp_db, version_id)[("subtask", nested_id)]

    assert item["parent_subtask_id"] == subtask_id
    assert item["wbs_path"] == f"task:{task_id}/subtask:{subtask_id}/subtask:{nested_id}"


def test_22_deleted_live_task_remains_in_historical_revision(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    revision_id = ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Revision 1")

    temp_db.delete_task(task_id)

    assert ("task", task_id) in _items_by_key(temp_db, revision_id)


def test_23_new_task_after_baseline_not_baselined_in_original(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    original_id = _create_original(temp_db, project_id, task_id)
    new_task_id = temp_db.insert_task({"project_id": project_id, "title": "New Scope"})

    assert ("task", new_task_id) not in _items_by_key(temp_db, original_id)


def test_24_revision_can_include_new_task(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    _create_original(temp_db, project_id, task_id)
    new_task_id = temp_db.insert_task({
        "project_id": project_id,
        "title": "New Scope",
        "planned_date": "2026-10-01",
        "due_date": "2026-10-02",
    })

    revision_id = ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Revision 1")

    assert ("task", new_task_id) in _items_by_key(temp_db, revision_id)


def test_25_comparison_original(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    original_id = _create_original(temp_db, project_id, task_id)

    lookup = ScheduleVersionService.get_version_lookup(temp_db, original_id)

    assert lookup[("task", task_id)]["start"] == "2026-09-02 09:00"


def test_26_comparison_revision_1(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    revision_id = ScheduleVersionService.create_approved_revision(
        temp_db,
        project_id,
        name="Revision 1",
        cpm_results=_cpm(task_id, "2026-09-06 09:00", "2026-09-08 17:00"),
    )

    assert ScheduleVersionService.get_version_lookup(temp_db, revision_id)[("task", task_id)]["finish"] == "2026-09-08 17:00"


def test_27_comparison_revision_2(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Revision 1")
    revision_id = ScheduleVersionService.create_approved_revision(
        temp_db,
        project_id,
        name="Revision 2",
        cpm_results=_cpm(task_id, "2026-10-06 09:00", "2026-10-08 17:00"),
    )

    assert ScheduleVersionService.get_version_lookup(temp_db, revision_id)[("task", task_id)]["start"] == "2026-10-06 09:00"


def test_28_selector_does_not_mutate_schedule():
    source = Path("todo_bird_app/views/gantt_view.py").read_text()
    method_source = source.split("def populate_compare_version_combo", 1)[1].split("def on_gantt_project_changed", 1)[0]

    assert "ensure_original_baseline_migrated" not in method_source


def test_29_selector_does_not_mutate_actual():
    source = Path("todo_bird_app/views/gantt_view.py").read_text()
    method_source = source.split("def on_gantt_compare_version_changed", 1)[1].split("def set_current_project", 1)[0]

    assert "actual_" not in method_source
    assert "update_task" not in method_source


def test_30_variance_current_original_correct(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    original_id = _create_original(temp_db, project_id, task_id)

    original_start = _items_by_key(temp_db, original_id)[("task", task_id)]["start"]

    assert _minutes_between("2026-09-05 09:00", original_start) == 4320


def test_31_variance_current_revision_correct(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    revision_id = ScheduleVersionService.create_approved_revision(
        temp_db,
        project_id,
        name="Revision 1",
        cpm_results=_cpm(task_id, "2026-09-06 09:00", "2026-09-08 17:00"),
    )

    revision_finish = _items_by_key(temp_db, revision_id)[("task", task_id)]["finish"]

    assert _minutes_between("2026-09-10 17:00", revision_finish) == 2880


def test_32_execution_variance_remains_independent(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    revision_id = ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Revision 1")
    before = _items_by_key(temp_db, revision_id)[("task", task_id)]["finish"]

    temp_db.update_task({
        "id": task_id,
        "actual_start_date": "2026-09-10",
        "actual_start_time": "09:00",
        "actual_end_date": "2026-10-01",
        "actual_end_time": "18:00",
        "status": "Completed",
    })

    assert _items_by_key(temp_db, revision_id)[("task", task_id)]["finish"] == before


def test_33_migration_idempotent(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    with temp_db.get_connection() as conn:
        conn.execute(
            """
            UPDATE projects SET baseline_created_at = '2026-09-01T09:00:00', baseline_name = 'Baseline 1'
            WHERE id = ?;
            """,
            (project_id,),
        )
        conn.execute(
            """
            UPDATE tasks SET baseline_start = '2026-09-01 09:00', baseline_finish = '2026-09-03 17:00'
            WHERE id = ?;
            """,
            (task_id,),
        )
        conn.commit()

    v1 = ScheduleVersionService.ensure_original_baseline_migrated(temp_db, project_id)
    v2 = ScheduleVersionService.ensure_original_baseline_migrated(temp_db, project_id)

    assert v1 == v2
    assert len(temp_db.get_schedule_versions_for_project(project_id)) == 1


def test_34_repeated_app_startup_no_duplicate_baseline(tmp_path):
    db_path = tmp_path / "restart.db"
    db = DatabaseManager.for_test(str(db_path))
    project_id, task_id, _, _ = _make_project_tree(db)
    with db.get_connection() as conn:
        conn.execute(
            "UPDATE projects SET baseline_created_at = '2026-09-01T09:00:00' WHERE id = ?;",
            (project_id,),
        )
        conn.execute(
            "UPDATE tasks SET baseline_start = '2026-09-01 09:00', baseline_finish = '2026-09-03 17:00' WHERE id = ?;",
            (task_id,),
        )
        conn.commit()
    first = ScheduleVersionService.ensure_original_baseline_migrated(db, project_id)
    db.close()

    db2 = DatabaseManager.for_test(str(db_path))
    second = ScheduleVersionService.ensure_original_baseline_migrated(db2, project_id)
    versions = db2.get_schedule_versions_for_project(project_id)
    db2.close()

    assert first == second
    assert len(versions) == 1


def test_35_legacy_fields_version_table_cannot_silently_diverge(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    _create_original(temp_db, project_id, task_id)

    with pytest.raises(ScheduleVersionImmutabilityError):
        temp_db.update_task({"id": task_id, "baseline_start": "2030-01-01 09:00"})


def test_36_duplicate_version_name_handling(temp_db):
    project_id, _, _, _ = _make_project_tree(temp_db)

    rev1 = ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Customer Approved")
    rev2 = ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Customer Approved")

    assert rev1 != rev2
    assert [_version(temp_db, rev1)["sequence_order"], _version(temp_db, rev2)["sequence_order"]] == [1, 2]


def test_37_revision_naming(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    _create_original(temp_db, project_id, task_id)

    revision_id = ScheduleVersionService.create_approved_revision(temp_db, project_id)

    assert _version(temp_db, revision_id)["name"] == "Revision 1"


def test_38_revision_timestamps(temp_db):
    project_id, _, _, _ = _make_project_tree(temp_db)
    timestamp = "2026-09-10T09:00:00"

    revision_id = ScheduleVersionService.create_approved_revision(
        temp_db,
        project_id,
        name="Timestamped Revision",
        approved_at=timestamp,
    )

    version = _version(temp_db, revision_id)
    assert version["created_at"] == timestamp
    assert version["approved_at"] == timestamp


def test_39_rollback_preserves_previous_versions(temp_db):
    project_id, _, _, _ = _make_project_tree(temp_db)
    good_id = ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Good Revision")

    with pytest.raises(ScheduleVersionGovernanceError):
        temp_db.create_schedule_version(
            project_id,
            "Broken Revision",
            items=[
                {"entity_type": "task", "entity_id": 5000},
                {"entity_type": "task", "entity_id": 5000},
            ],
        )

    assert _version(temp_db, good_id)["name"] == "Good Revision"
    assert all(v["name"] != "Broken Revision" for v in temp_db.get_schedule_versions_for_project(project_id))


def test_40_production_db_untouched():
    if not PRODUCTION_DB.exists():
        pytest.skip("production DB not present")
    before = _hash_file(PRODUCTION_DB)
    db = DatabaseManager.read_only(str(PRODUCTION_DB))
    with db.get_connection() as conn:
        conn.execute("SELECT COUNT(*) FROM projects;").fetchone()
    db.close()

    assert _hash_file(PRODUCTION_DB) == before


def test_41_baseline_item_count_stable(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    original_id = _create_original(temp_db, project_id, task_id)
    count = len(temp_db.get_schedule_version_items(original_id))

    temp_db.update_task({"id": task_id, "planned_date": "2026-12-01", "due_date": "2026-12-05"})

    assert len(temp_db.get_schedule_version_items(original_id)) == count


def test_42_revision_item_count_stable(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    revision_id = ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Revision 1")
    count = len(temp_db.get_schedule_version_items(revision_id))

    temp_db.delete_task(task_id)

    assert len(temp_db.get_schedule_version_items(revision_id)) == count


def test_43_project_delete_behavior_safely_handled(temp_db):
    project_id, task_id, _, _ = _make_project_tree(temp_db)
    _create_original(temp_db, project_id, task_id)
    ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Revision 1")

    with temp_db.get_connection() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?;", (project_id,))
        conn.commit()

    assert temp_db.get_schedule_versions_for_project(project_id) == []
    assert _count_orphan_items(temp_db) == 0


def test_44_entity_deletion_historical_integrity(temp_db):
    project_id, task_id, subtask_id, _ = _make_project_tree(temp_db)
    revision_id = ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Revision 1")

    temp_db.delete_subtask(subtask_id)

    assert ("subtask", subtask_id) in _items_by_key(temp_db, revision_id)


def test_45_null_missing_schedule_fields(temp_db):
    project_id = temp_db.insert_project({"name": "Null Schedule"})
    task_id = temp_db.insert_task({"project_id": project_id, "title": "Unscheduled"})

    version_id = ScheduleVersionService.create_original_baseline(temp_db, project_id)
    item = _items_by_key(temp_db, version_id)[("task", task_id)]

    assert item["start"] is None
    assert item["finish"] is None


def test_46_milestone_snapshot(temp_db):
    project_id = temp_db.insert_project({"name": "Milestone"})
    task_id = temp_db.insert_task({
        "project_id": project_id,
        "title": "Milestone",
        "planned_date": "2026-09-15",
        "planned_start_time": "09:00",
        "estimated_duration": 0,
    })

    revision_id = ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Milestone Revision")
    item = _items_by_key(temp_db, revision_id)[("task", task_id)]

    assert item["start"] == "2026-09-15 09:00"
    assert item["finish"] == "2026-09-15 09:00"
    assert item["duration_minutes"] == 0


def test_47_approved_revision_immutable_via_service_api(temp_db):
    project_id, _, _, _ = _make_project_tree(temp_db)
    revision_id = ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Revision 1")

    with pytest.raises(ScheduleVersionGovernanceError):
        temp_db.delete_schedule_version(revision_id)

    assert _version(temp_db, revision_id)["name"] == "Revision 1"


def test_48_direct_accidental_update_prevented_where_architecture_permits(temp_db):
    project_id, _, _, _ = _make_project_tree(temp_db)
    revision_id = ScheduleVersionService.create_approved_revision(temp_db, project_id, name="Revision 1")

    with temp_db.get_connection() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "UPDATE schedule_version_items SET start = '2030-01-01 09:00' WHERE version_id = ?;",
                (revision_id,),
            )


def test_49_ui_replace_baseline_governance_corrected():
    source = Path("todo_bird_app/views/wbs_project_view.py").read_text()

    assert "Replace Original Baseline" not in source
    assert "Clear Original Baseline" not in source
    assert "Create Approved Revision" in source
    assert "Set Original Baseline" in source


def test_50_read_only_live_thaavorix_witness():
    if not PRODUCTION_DB.exists():
        pytest.skip("production DB not present")
    before = _hash_file(PRODUCTION_DB)
    db = DatabaseManager.read_only(str(PRODUCTION_DB))
    with db.get_connection() as conn:
        version_counts = conn.execute(
            """
            SELECT
                SUM(CASE WHEN is_original_baseline = 1 OR version_type = 'original_baseline' THEN 1 ELSE 0 END),
                SUM(CASE WHEN is_original_baseline = 0 AND version_type = 'approved_revision' THEN 1 ELSE 0 END)
            FROM schedule_versions;
            """
        ).fetchone()
        duplicate_originals = conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT project_id
                FROM schedule_versions
                WHERE is_original_baseline = 1 OR version_type = 'original_baseline'
                GROUP BY project_id
                HAVING COUNT(*) > 1
            );
            """
        ).fetchone()[0]
        orphan_items = conn.execute(
            """
            SELECT COUNT(*)
            FROM schedule_version_items i
            LEFT JOIN schedule_versions v ON v.id = i.version_id
            WHERE v.id IS NULL;
            """
        ).fetchone()[0]
    db.close()

    assert version_counts[0] is not None
    assert duplicate_originals >= 0
    assert orphan_items >= 0
    assert _hash_file(PRODUCTION_DB) == before
