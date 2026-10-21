"""
TODO BIRD — SCHEDULE DETAILS & COPY INTERACTION TEST SUITE
Validates structured schedule details extraction, formatting, copyable popover,
clipboard content, and keyboard shortcuts without disturbing CPM math or production DB.
"""

import pytest
from datetime import datetime, date, time
from typing import Dict, Any

from PySide6.QtCore import Qt, QPoint, QDate, QTime
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QKeyEvent

from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.services.schedule_details_formatter import (
    ScheduleDetailsFormatter,
    ScheduleDetailsModel,
)
from todo_bird_app.ui.components.schedule_details_popover import ScheduleDetailsPopover


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_01_task_details_model_build(qapp):
    """TEST 01: Main task model correctly built with canonical fields."""
    task = Task(
        id=101,
        title="Foundation Excavation",
        project_id=1,
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.HIGH,
        planned_date="2026-09-01",
        due_date="2026-09-05",
        planned_start_time="08:00",
        planned_end_time="17:00",
        estimated_duration=2400,
        progress=40,
    )
    task.cpm_earliest_start = "2026-09-01 08:00"
    task.cpm_earliest_finish = "2026-09-05 17:00"
    task.cpm_latest_start = "2026-09-01 08:00"
    task.cpm_latest_finish = "2026-09-05 17:00"
    task.cpm_total_float = 0
    task.cpm_free_float = 0
    task.cpm_is_critical = True

    model = ScheduleDetailsFormatter.build_from_entity(task, project_name="Metro Station Alpha")
    assert model.title == "Foundation Excavation"
    assert model.entity_type == "task"
    assert model.project_name == "Metro Station Alpha"
    assert model.status == "In Progress"
    assert model.priority == "High"
    assert model.progress == 40
    assert model.cpm_is_critical is True
    assert model.cpm_tf == 0
    assert model.cpm_ff == 0


def test_02_subtask_details_model_build(qapp):
    """TEST 02: Subtask model correctly built and identifies as Subtask."""
    subtask = {
        "id": 201,
        "task_id": 101,
        "title": "Soil Compaction",
        "depth": 1,
        "entity_type": "subtask",
        "status": "Planned",
        "priority": "Medium",
        "planned_date": "2026-09-02",
        "due_date": "2026-09-03",
        "estimated_duration": 480,
    }
    model = ScheduleDetailsFormatter.build_from_entity(subtask, project_name="Metro Station Alpha")
    assert model.title == "Soil Compaction"
    assert model.entity_type == "subtask"
    assert ScheduleDetailsFormatter.format_type_label(model) == "Subtask"


def test_03_nested_subtask_details_model_build(qapp):
    """TEST 03: Deeply nested subtask (depth=2) labeled as Level 2 Subtask."""
    nested = {
        "id": 301,
        "task_id": 101,
        "title": "Reinforcement Final",
        "depth": 2,
        "entity_type": "subtask",
        "status": "Planned",
        "priority": "Urgent",
        "planned_date": "2026-09-03",
        "estimated_duration": 240,
    }
    model = ScheduleDetailsFormatter.build_from_entity(nested, project_name="Metro Station Alpha")
    assert model.depth == 2
    assert ScheduleDetailsFormatter.format_type_label(model) == "Level 2 Subtask"


def test_04_summary_row_details_model_build(qapp):
    """TEST 04: Summary row clearly classified as Summary without fabricated fields."""
    summary = {
        "id": 401,
        "title": "Civil Works Phase 1",
        "is_summary": True,
        "depth": 0,
        "status": "In Progress",
    }
    model = ScheduleDetailsFormatter.build_from_entity(summary, project_name="Metro Station Alpha")
    assert model.is_summary is True
    assert ScheduleDetailsFormatter.format_type_label(model) == "Summary"


def test_05_milestone_task_details_build(qapp):
    """TEST 05: Milestone row correctly identified."""
    ms = {
        "id": 501,
        "title": "Tunnel Breakthrough",
        "is_milestone": True,
        "depth": 1,
        "estimated_duration": 0,
    }
    model = ScheduleDetailsFormatter.build_from_entity(ms, project_name="Metro Station Alpha")
    assert model.is_milestone is True
    assert ScheduleDetailsFormatter.format_type_label(model) == "Milestone"


def test_06_copy_button_sets_clipboard(qapp):
    """TEST 06: [Copy Details] button writes formatted plain text to clipboard."""
    model = ScheduleDetailsModel(
        title="Reinforcement Final",
        entity_type="subtask",
        depth=1,
        project_name="SCHEDULING WITNESS FINAL",
        status="Planned",
        planned_start="2026-09-02 09:00",
        planned_finish="2026-09-03 09:00",
        has_cpm=True,
        cpm_es="2026-09-02 09:00",
        cpm_ef="2026-09-03 09:00",
        cpm_ls="2026-09-02 09:00",
        cpm_lf="2026-09-03 09:00",
        cpm_tf=0,
        cpm_ff=0,
        cpm_is_critical=True,
        predecessors=["Excavation Final | FS | Lag 0"],
    )

    popover = ScheduleDetailsPopover(model)
    popover.copy_details()

    clipboard_text = QApplication.clipboard().text()
    assert "Task: Reinforcement Final" in clipboard_text
    assert "Type: Subtask" in clipboard_text
    assert "Project: SCHEDULING WITNESS FINAL" in clipboard_text
    assert "ES: 2026-09-02 09:00" in clipboard_text
    assert "Total Float: 0 min" in clipboard_text
    assert "Critical: Yes" in clipboard_text
    popover.close()


def test_07_cpm_es_copied(qapp):
    """TEST 07: ES is accurately formatted in plain text output."""
    model = ScheduleDetailsModel(
        title="Piling Test",
        cpm_es="2026-09-10 14:30",
        has_cpm=True,
    )
    plain = ScheduleDetailsFormatter.format_plain_text(model)
    assert "ES: 2026-09-10 14:30" in plain


def test_08_cpm_ef_copied(qapp):
    """TEST 08: EF is accurately formatted in plain text output."""
    model = ScheduleDetailsModel(
        title="Piling Test",
        cpm_ef="2026-09-12 18:00",
        has_cpm=True,
    )
    plain = ScheduleDetailsFormatter.format_plain_text(model)
    assert "EF: 2026-09-12 18:00" in plain


def test_09_cpm_ls_copied(qapp):
    """TEST 09: LS is accurately formatted in plain text output."""
    model = ScheduleDetailsModel(
        title="Piling Test",
        cpm_ls="2026-09-15 09:00",
        has_cpm=True,
    )
    plain = ScheduleDetailsFormatter.format_plain_text(model)
    assert "LS: 2026-09-15 09:00" in plain


def test_10_cpm_lf_copied(qapp):
    """TEST 10: LF is accurately formatted in plain text output."""
    model = ScheduleDetailsModel(
        title="Piling Test",
        cpm_lf="2026-09-17 17:00",
        has_cpm=True,
    )
    plain = ScheduleDetailsFormatter.format_plain_text(model)
    assert "LF: 2026-09-17 17:00" in plain


def test_11_total_float_canonical_minutes(qapp):
    """TEST 11: Total Float includes canonical minutes (e.g. 1d (1440 min) or 0 min)."""
    # 0 min
    m0 = ScheduleDetailsModel(title="Critical Item", cpm_tf=0, has_cpm=True)
    assert "Total Float: 0 min" in ScheduleDetailsFormatter.format_plain_text(m0)

    # 1440 min = 1d (1440 min)
    m1 = ScheduleDetailsModel(title="Float Item", cpm_tf=1440, has_cpm=True)
    assert "Total Float: 1d (1440 min)" in ScheduleDetailsFormatter.format_plain_text(m1)

    # 480 min = 8h (480 min)
    m2 = ScheduleDetailsModel(title="Hours Float", cpm_tf=480, has_cpm=True)
    assert "Total Float: 8h (480 min)" in ScheduleDetailsFormatter.format_plain_text(m2)


def test_12_free_float_canonical_minutes(qapp):
    """TEST 12: Free Float includes canonical minutes."""
    m = ScheduleDetailsModel(title="Free Float Item", cpm_ff=1440, has_cpm=True)
    assert "Free Float: 1d (1440 min)" in ScheduleDetailsFormatter.format_plain_text(m)


def test_13_critical_flag_copied(qapp):
    """TEST 13: Critical flag is copied as Yes or No."""
    crit_yes = ScheduleDetailsModel(title="Crit", cpm_is_critical=True, has_cpm=True)
    assert "Critical: Yes" in ScheduleDetailsFormatter.format_plain_text(crit_yes)

    crit_no = ScheduleDetailsModel(title="NonCrit", cpm_is_critical=False, has_cpm=True)
    assert "Critical: No" in ScheduleDetailsFormatter.format_plain_text(crit_no)


def test_14_dependencies_copied(qapp):
    """TEST 14: Predecessors list copied with dependency type and lag."""
    m = ScheduleDetailsModel(
        title="Concrete Pour",
        predecessors=[
            "Rebar Placement | FS | Lag 0",
            "Formwork Inspection | SS | Lag 120",
        ],
    )
    plain = ScheduleDetailsFormatter.format_plain_text(m)
    assert "Predecessors:" in plain
    assert "- Rebar Placement | FS | Lag 0" in plain
    assert "- Formwork Inspection | SS | Lag 120" in plain


def test_15_missing_values_not_fabricated(qapp):
    """TEST 15: Missing analytical values are explicit and NEVER fabricated."""
    bare = ScheduleDetailsModel(
        title="Unscheduled Task",
        has_cpm=False,
        has_baseline=False,
        actual_state="not_started",
        predecessors=[],
    )
    plain = ScheduleDetailsFormatter.format_plain_text(bare)
    assert "CPM Status: Not analyzed" in plain
    assert "ES: Not analyzed" in plain
    assert "EF: Not analyzed" in plain
    assert "Total Float: Not analyzed" in plain
    assert "2026-" not in plain
    assert "Predecessors: None" in plain
    assert "Baseline: Not Baselined" in plain
    assert "Actual: Not Tracked" in plain


def test_16_popover_remains_open_for_interaction(qapp):
    """TEST 16: Popover is interactive and does not disappear during mouse movement."""
    model = ScheduleDetailsModel(title="Test Popover")
    popover = ScheduleDetailsPopover(model)
    popover.show()
    assert popover.isVisible()
    assert popover.browser.textInteractionFlags() & Qt.TextSelectableByMouse
    assert popover.btn_copy_details.isEnabled()
    popover.close()


def test_17_esc_key_closes_popover(qapp):
    """TEST 17: Pressing Esc closes the popover cleanly."""
    model = ScheduleDetailsModel(title="Escape Test")
    popover = ScheduleDetailsPopover(model)
    popover.show()
    assert popover.isVisible()

    event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    popover.keyPressEvent(event)
    assert not popover.isVisible()


def test_18_ctrl_c_shortcut_copies_details(qapp):
    """TEST 18: Pressing Ctrl+C inside popover triggers copy_details."""
    model = ScheduleDetailsModel(title="Ctrl C Test", project_name="Shortcuts Project")
    popover = ScheduleDetailsPopover(model)
    popover.show()

    event = QKeyEvent(QKeyEvent.KeyPress, Qt.Key_C, Qt.ControlModifier)
    popover.keyPressEvent(event)

    clipboard_text = QApplication.clipboard().text()
    assert "Task: Ctrl C Test" in clipboard_text
    assert "Project: Shortcuts Project" in clipboard_text
    popover.close()


def test_19_dependency_cycle_diagnostics_handled(qapp):
    """TEST 19: Dependency cycle is prominently noted and does not cause crash."""
    m = ScheduleDetailsModel(
        title="Cyclic Task",
        has_cycle=True,
    )
    plain = ScheduleDetailsFormatter.format_plain_text(m)
    assert "CPM: Not analyzed (Dependency Cycle detected)" in plain

    html = ScheduleDetailsFormatter.format_html(m)
    assert "Dependency Cycle detected" in html


def test_20_html_rich_formatting(qapp):
    """TEST 20: HTML output contains semantic badges and readable hierarchy."""
    m = ScheduleDetailsModel(
        title="Deck Waterproofing",
        entity_type="subtask",
        depth=1,
        wbs_code="1.2.3",
        project_name="Bridge Reconstruction",
        status="Planned",
        has_cpm=True,
        cpm_tf=0,
        cpm_ff=0,
        cpm_is_critical=True,
    )
    html = ScheduleDetailsFormatter.format_html(m, is_dark=True)
    assert "Deck Waterproofing" in html
    assert "Subtask" in html
    assert "1.2.3" in html
    assert "Bridge Reconstruction" in html
    assert "Total Float:" in html
    assert "Critical:" in html
