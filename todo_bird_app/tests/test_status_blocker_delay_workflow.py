import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit, QMessageBox

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.project import Project
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.widgets.task_dialog import TaskDialog


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app


@pytest.fixture
def status_db(tmp_path):
    db = DatabaseManager.for_test(str(tmp_path / "status_blocker_delay.db"))
    with db.get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO projects (id, name, color) VALUES (1, 'Workflow Project', '#2563EB')"
        )
        conn.commit()
    return db


def _project():
    return Project(id=1, name="Workflow Project", color="#2563EB")


def _dialog(status_db, *, status=TaskStatus.PLANNED, **overrides):
    task = Task(
        title=overrides.pop("title", "Workflow Task"),
        project_id=1,
        planned_date="2026-09-01",
        planned_start_time="09:00",
        estimated_duration=1440,
        status=status,
        delay_category=overrides.pop("delay_category", ""),
        delay_reason=overrides.pop("delay_reason", ""),
        delay_notes=overrides.pop("delay_notes", ""),
        progress=overrides.pop("progress", 0),
        **overrides,
    )
    task_id = status_db.insert_task(task.to_dict())
    return TaskDialog(
        projects=[_project()],
        task=Task.from_row(status_db.get_task_by_id(task_id)),
        db_manager=status_db,
    )


def _set_status(dialog: TaskDialog, status: TaskStatus):
    idx = dialog.status_combo.findData(status)
    assert idx >= 0
    dialog.status_combo.setCurrentIndex(idx)


def _warning_recorder(monkeypatch):
    calls = []

    def record(_parent, title, message, *args, **kwargs):
        calls.append((title, message))
        return QMessageBox.Ok

    monkeypatch.setattr(QMessageBox, "warning", record)
    return calls


STATUS_GATE_CASES = [
    (TaskStatus.INBOX, False),
    (TaskStatus.PLANNED, False),
    (TaskStatus.IN_PROGRESS, False),
    (TaskStatus.BLOCKED, True),
    (TaskStatus.DELAYED, True),
    (TaskStatus.MOVED, False),
    (TaskStatus.COMPLETED, False),
    (TaskStatus.CANCELLED, False),
]


@pytest.mark.parametrize("status,expected_enabled", STATUS_GATE_CASES)
def test_status_selection_immediately_gates_blocker_delay_controls(
    qapp, status_db, status, expected_enabled
):
    dialog = _dialog(status_db)

    _set_status(dialog, status)
    qapp.processEvents()

    assert dialog.blocker_category_combo.isEnabled() is expected_enabled
    assert dialog.blocker_reason_input.isEnabled() is expected_enabled
    assert dialog.blocker_notes_input.isEnabled() is expected_enabled


@pytest.mark.parametrize(
    "status",
    [
        TaskStatus.INBOX,
        TaskStatus.PLANNED,
        TaskStatus.IN_PROGRESS,
        TaskStatus.MOVED,
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
    ],
)
def test_non_blocker_status_selection_persists_without_blocker_fields(
    qapp, status_db, status
):
    dialog = _dialog(status_db, progress=0)

    _set_status(dialog, status)
    if status == TaskStatus.IN_PROGRESS:
        dialog.actual_enabled_check.setChecked(True)
    dialog.on_save()

    assert dialog.result() == TaskDialog.Accepted
    assert dialog.task.status == status
    if status == TaskStatus.COMPLETED:
        assert dialog.task.progress == 100


@pytest.mark.parametrize("status", [TaskStatus.BLOCKED, TaskStatus.DELAYED])
def test_blocker_delay_save_requires_non_none_category(
    qapp, status_db, monkeypatch, status
):
    dialog = _dialog(status_db)
    warnings = _warning_recorder(monkeypatch)

    _set_status(dialog, status)
    dialog.blocker_reason_input.setText("Waiting for owner")
    dialog.on_save()

    assert dialog.result() != TaskDialog.Accepted
    assert warnings
    assert "Category Required" in warnings[0][0]
    assert dialog.blocker_category_combo.isEnabled()


@pytest.mark.parametrize("status", [TaskStatus.BLOCKED, TaskStatus.DELAYED])
def test_blocker_delay_save_requires_reason(qapp, status_db, monkeypatch, status):
    dialog = _dialog(status_db)
    warnings = _warning_recorder(monkeypatch)

    _set_status(dialog, status)
    dialog.blocker_category_combo.setCurrentText("Dependency")
    dialog.blocker_reason_input.clear()
    dialog.on_save()

    assert dialog.result() != TaskDialog.Accepted
    assert warnings
    assert "Reason Required" in warnings[0][0]
    assert dialog.blocker_reason_input.isEnabled()


CATEGORY_CASES = [
    "Dependency",
    "Decision / Approval",
    "Resource / Manpower",
    "Technical Issue",
    "Material / Parts",
    "Budget / Commercial",
    "Customer / Stakeholder",
    "External Agency",
    "Information / Input",
]


@pytest.mark.parametrize("status", [TaskStatus.BLOCKED, TaskStatus.DELAYED])
@pytest.mark.parametrize("category", CATEGORY_CASES)
def test_blocker_delay_category_dropdown_selection_persists(
    qapp, status_db, status, category
):
    dialog = _dialog(status_db)

    _set_status(dialog, status)
    dialog.blocker_category_combo.setCurrentText(category)
    dialog.blocker_reason_input.setText("Concrete recovery action")
    dialog.blocker_notes_input.setHtml("Owner: PM. Resolution: unblock today.")
    dialog.on_save()

    assert dialog.result() == TaskDialog.Accepted
    assert dialog.task.status == status
    assert dialog.task.delay_category == category
    assert dialog.task.delay_reason == "Concrete recovery action"
    assert "Owner: PM" in dialog.task.delay_notes
    assert dialog.task.delay_recorded_at


@pytest.mark.parametrize("stored", ["none", "None", "", "null"])
def test_lowercase_or_empty_none_category_is_normalized(qapp, status_db, stored):
    dialog = _dialog(status_db, delay_category=stored)

    assert dialog.blocker_category_combo.currentText() == "None"
    assert "none" not in [
        dialog.blocker_category_combo.itemText(index)
        for index in range(dialog.blocker_category_combo.count())
    ]


@pytest.mark.parametrize("progress", [0, 35, 100])
def test_task_done_checkbox_drives_status_combo_without_double_save(
    qapp, status_db, progress
):
    dialog = _dialog(status_db, progress=progress)

    dialog.task_done_checkbox.setChecked(True)
    qapp.processEvents()
    assert dialog.status_combo.currentData() == TaskStatus.COMPLETED

    dialog.task_done_checkbox.setChecked(False)
    qapp.processEvents()
    expected = TaskStatus.IN_PROGRESS if progress > 0 else TaskStatus.PLANNED
    assert dialog.status_combo.currentData() == expected


COMBO_ATTRS = [
    "project_combo",
    "prio_combo",
    "cat_combo",
    "status_combo",
    "constraint_type_combo",
    "recurring_combo",
    "startup_reminder_combo",
    "blocker_category_combo",
    "pin_color_combo",
]


@pytest.mark.parametrize("attr", COMBO_ATTRS)
def test_task_dialog_dropdown_models_are_populated_and_focusable(
    qapp, status_db, attr
):
    dialog = _dialog(status_db)
    combo = getattr(dialog, attr)

    assert isinstance(combo, QComboBox)
    assert combo.count() > 0
    assert combo.focusPolicy() != Qt.NoFocus
    assert combo.currentIndex() >= 0


@pytest.mark.parametrize("status", [TaskStatus.INBOX, TaskStatus.PLANNED])
def test_disabled_blocker_delay_controls_explain_the_gate(qapp, status_db, status):
    dialog = _dialog(status_db)

    _set_status(dialog, status)
    qapp.processEvents()

    assert dialog.blocker_category_combo.isEnabled() is False
    assert "Blocked or Delayed" in dialog.blocker_category_combo.toolTip()
    assert "Blocked or Delayed" in dialog.blocker_reason_input.toolTip()
    assert "Blocked or Delayed" in dialog.blocker_notes_input.toolTip()


@pytest.mark.parametrize("status", [TaskStatus.BLOCKED, TaskStatus.DELAYED])
def test_enabled_blocker_delay_controls_have_actionable_tooltips(
    qapp, status_db, status
):
    dialog = _dialog(status_db)

    _set_status(dialog, status)
    qapp.processEvents()

    assert dialog.blocker_category_combo.isEnabled() is True
    assert "Choose" in dialog.blocker_category_combo.toolTip()
    assert "Record" in dialog.blocker_reason_input.toolTip()


def test_status_combo_contains_supported_state_machine_values(qapp, status_db):
    dialog = _dialog(status_db)

    values = {
        dialog.status_combo.itemData(index)
        for index in range(dialog.status_combo.count())
    }

    assert {
        TaskStatus.INBOX,
        TaskStatus.PLANNED,
        TaskStatus.IN_PROGRESS,
        TaskStatus.BLOCKED,
        TaskStatus.DELAYED,
        TaskStatus.MOVED,
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
    }.issubset(values)


def test_blocker_category_does_not_allow_lowercase_none_to_bypass_validation(
    qapp, status_db, monkeypatch
):
    dialog = _dialog(status_db, delay_category="none")
    warnings = _warning_recorder(monkeypatch)

    _set_status(dialog, TaskStatus.BLOCKED)
    dialog.blocker_reason_input.setText("Waiting")
    dialog.on_save()

    assert dialog.result() != TaskDialog.Accepted
    assert warnings
    assert dialog.task.delay_category.lower() in {"", "none"}


def test_reason_text_entry_remains_editable_after_delayed_status(qapp, status_db):
    dialog = _dialog(status_db)

    _set_status(dialog, TaskStatus.DELAYED)
    dialog.blocker_reason_input.setText("Vendor delivery slipped")

    assert isinstance(dialog.blocker_reason_input, QLineEdit)
    assert dialog.blocker_reason_input.text() == "Vendor delivery slipped"
    assert dialog.blocker_reason_input.isReadOnly() is False
