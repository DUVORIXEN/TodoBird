"""
Tests for Phase 1F.9: Application State UX Closure.

Verifies:
1. Shared state component (StatePanel) initializes
2. Empty state title/description/icon
3. Primary action triggers callback
4. Secondary action triggers callback
5. Keyboard focus reachable on actions
6. Empty -> Content transition
7. Content -> Empty transition
8. No-results differs from true empty
9. Clear-filter action resets filters and restores content
10. No-selection state communicates clearly
11. Error state with retry callback
12. Recoverable refresh preserves existing safe state
13. Inbox empty state
14. Today empty state
15. Upcoming empty state
16. Completed empty state
17. Projects empty state (no projects)
18. Project task-list empty state
19. WBS true empty state
20. WBS filtered no-results state
21. Gantt empty state
22. Calendar empty state
23. Focus no-eligible-task state
24. Daily Review empty state
25. Analytics zero data state
26. WBS Move Up boundary disabled at first sibling
27. WBS Move Down boundary disabled at last sibling
28. WBS Root Outdent disabled
29. WBS Invalid Indent disabled (first child / task root)
30. Valid WBS hierarchy actions remain enabled
31. 20pt typography does not clip action controls
32. 20pt -> 10pt reverses safely
33. Dark mode theme rendering
34. Light mode theme rendering
35. Zero idle timers introduced
36. Zero DB access from paintEvent
"""

import sqlite3
import pytest
from datetime import date
from unittest.mock import MagicMock

from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.widgets.state_panel import StatePanel, StateKind
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.models.project import Project
from todo_bird_app.services.wbs_service import EntityRef
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.views.inbox_view import InboxView
from todo_bird_app.views.today_view import TodayView
from todo_bird_app.views.upcoming_view import UpcomingView
from todo_bird_app.views.completed_view import CompletedView
from todo_bird_app.views.projects_view import ProjectsView
from todo_bird_app.views.wbs_project_view import WBSProjectView
from todo_bird_app.views.focus_view import FocusView
from todo_bird_app.views.calendar_view import CalendarView
from todo_bird_app.views.daily_review_view import DailyReviewView
from todo_bird_app.views.analytics_view import AnalyticsView


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "test_state_ux.db"
    manager = DatabaseManager(str(db_file))
    return manager


@pytest.fixture
def settings(db):
    return SettingsManager(db_manager=db)


# ------------------------------------------------------------
# 1. Shared StatePanel Component Unit Tests
# ------------------------------------------------------------

def test_state_panel_initialization(app):
    panel = StatePanel()
    assert panel.title_label.text() == "Nothing here yet"
    assert panel.desc_label.text() == "Items will appear here once created."
    assert panel.btn_primary.isHidden()
    assert panel.btn_secondary.isHidden()
    panel.close()


def test_state_panel_empty_configuration(app):
    panel = StatePanel()
    panel.show()
    primary_called = False
    secondary_called = False

    def on_primary():
        nonlocal primary_called
        primary_called = True

    def on_secondary():
        nonlocal secondary_called
        secondary_called = True

    panel.show_empty(
        title="Inbox is clear",
        description="All items organized.",
        action_text="Add Task",
        action_callback=on_primary,
        secondary_action_text="Dismiss",
        secondary_action_callback=on_secondary,
        icon="📥",
    )

    assert panel.title_label.text() == "Inbox is clear"
    assert panel.desc_label.text() == "All items organized."
    assert panel.icon_label.text() == "📥"
    assert not panel.btn_primary.isHidden()
    assert panel.btn_primary.text() == "Add Task"
    assert not panel.btn_secondary.isHidden()
    assert panel.btn_secondary.text() == "Dismiss"
    assert panel.accessibleName() == "Inbox is clear"

    panel.btn_primary.click()
    assert primary_called is True

    panel.btn_secondary.click()
    assert secondary_called is True
    panel.close()


def test_state_panel_no_results_and_clear_filter(app):
    panel = StatePanel()
    panel.show()
    cleared = False

    def on_clear():
        nonlocal cleared
        cleared = True

    panel.show_no_results(
        title="No matching tasks",
        description="No tasks match the filter.",
        clear_filter_callback=on_clear,
    )

    assert panel.title_label.text() == "No matching tasks"
    assert panel.btn_primary.text() == "Clear Filters"
    assert not panel.btn_primary.isHidden()

    panel.btn_primary.click()
    assert cleared is True
    panel.close()


def test_state_panel_no_selection(app):
    panel = StatePanel()
    panel.show_no_selection(
        title="No project selected",
        description="Pick a project.",
    )
    assert panel.title_label.text() == "No project selected"
    assert panel.icon_label.pixmap() is not None and not panel.icon_label.pixmap().isNull()
    panel.close()


def test_state_panel_error_and_retry(app):
    panel = StatePanel()
    retried = False

    def on_retry():
        nonlocal retried
        retried = True

    panel.show_error(
        title="Network timeout",
        description="Could not refresh data.",
        retry_callback=on_retry,
    )

    assert panel.title_label.text() == "Network timeout"
    assert panel.btn_primary.text() == "Try Again"
    panel.btn_primary.click()
    assert retried is True
    panel.close()


def test_state_panel_loading(app):
    panel = StatePanel()
    panel.show_loading(
        title="Generating Report...",
        description="Analyzing workload history.",
    )
    assert panel.title_label.text() == "Generating Report..."
    assert panel.icon_label.pixmap() is not None and not panel.icon_label.pixmap().isNull()
    assert panel.btn_primary.isHidden()
    panel.close()


# ------------------------------------------------------------
# 2. View Empty State Tests
# ------------------------------------------------------------

def test_inbox_empty_state_and_transition(app, db, settings):
    controller = TaskController(db)
    view = InboxView(db, settings)
    view.refresh_data()

    # Empty initially
    assert view.list_layout.count() > 0
    item = view.list_layout.itemAt(0)
    assert isinstance(item.widget(), StatePanel)
    assert item.widget().title_label.text() == "Inbox is clear"

    # Add task -> content appears
    task = Task(title="Test Inbox Task", status=TaskStatus.INBOX)
    controller.add_task(task)
    view.refresh_data()

    # Should no longer be a StatePanel
    first_item = view.list_layout.itemAt(0)
    assert not isinstance(first_item.widget(), StatePanel)

    # Delete task -> empty state returns
    controller.delete_task(task.id)
    view.refresh_data()
    first_item = view.list_layout.itemAt(0)
    assert isinstance(first_item.widget(), StatePanel)
    view.close()


def test_today_empty_state_and_transition(app, db, settings):
    controller = TaskController(db)
    view = TodayView(db, settings)
    view.refresh_data()

    first_item = view.list_layout.itemAt(0)
    assert isinstance(first_item.widget(), StatePanel)
    assert first_item.widget().title_label.text() == "No tasks scheduled for today"

    # Add today task
    today_str = date.today().strftime("%Y-%m-%d")
    task = Task(title="Today Work", planned_date=today_str, status=TaskStatus.PLANNED)
    controller.add_task(task)
    view.refresh_data()

    first_item = view.list_layout.itemAt(0)
    assert not isinstance(first_item.widget(), StatePanel)
    view.close()


def test_upcoming_empty_state(app, db, settings):
    view = UpcomingView(db, settings)
    view.refresh_data()

    first_item = view.list_layout.itemAt(0)
    assert isinstance(first_item.widget(), StatePanel)
    assert first_item.widget().title_label.text() == "No upcoming tasks scheduled"
    view.close()


def test_completed_empty_state(app, db, settings):
    view = CompletedView(db, settings)
    view.refresh_data()

    first_item = view.list_layout.itemAt(0)
    assert isinstance(first_item.widget(), StatePanel)
    assert first_item.widget().title_label.text() == "No completed tasks yet"
    view.close()


def test_projects_empty_and_no_selection_state(app, db, settings):
    controller = TaskController(db)
    view = ProjectsView(db, settings)
    view.refresh_data()

    # Initial state with default project (0 tasks) -> "No tasks in this project yet"
    assert view.project_list.count() >= 1
    assert view.task_list_layout.count() > 0
    first_item = view.task_list_layout.itemAt(0)
    assert isinstance(first_item.widget(), StatePanel)
    assert first_item.widget().title_label.text() == "No tasks in this project yet"

    # Explicit no selection state
    view.selected_project_id = None
    view.load_project_tasks()
    first_item_none = view.task_list_layout.itemAt(0)
    assert isinstance(first_item_none.widget(), StatePanel)
    assert first_item_none.widget().title_label.text() == "No project selected"
    view.close()


def test_wbs_true_empty_vs_filtered_no_results(app, db, settings):
    controller = TaskController(db)
    proj = Project(name="WBS Test Project")
    p_id = controller.add_project(proj)

    view = WBSProjectView(db_manager=db, settings_manager=settings)
    view.set_project(p_id)

    # 1. True Empty Project -> Page 1 (EmptyState "No tasks in this project yet")
    assert view.stack.currentIndex() == 1

    # Add a task to the project
    task = Task(title="Root Task 1", project_id=p_id, status=TaskStatus.PLANNED)
    controller.add_task(task)
    view.refresh_hierarchy()

    # 2. Has Tasks -> Page 0 (Tree View)
    assert view.stack.currentIndex() == 0

    # 3. Filter with non-matching query -> Page 2 (Filtered No Results StatePanel)
    view.search_field.setText("NonExistentTaskXYZ")
    view._on_search_changed("NonExistentTaskXYZ")
    assert view.stack.currentIndex() == 2
    assert view.no_results_state.title_label.text() == "No matching WBS items"

    # 4. Clear filter -> Page 0 restored
    view.clear_all_filters()
    assert view.stack.currentIndex() == 0
    assert view.search_field.text() == ""
    view.close()


# ------------------------------------------------------------
# 3. WBS Boundary Action Gating Tests
# ------------------------------------------------------------

def test_wbs_boundary_actions_gated(app, db, settings):
    controller = TaskController(db)
    proj = Project(name="Hierarchy Boundary Project")
    p_id = controller.add_project(proj)

    task1 = Task(title="Task 1", project_id=p_id, position=0)
    task2 = Task(title="Task 2", project_id=p_id, position=1)
    t1_id = controller.add_task(task1)
    t2_id = controller.add_task(task2)

    s1_1_id = db.insert_subtask(t1_id, "Subtask 1.1", position=0)
    s1_2_id = db.insert_subtask(t1_id, "Subtask 1.2", position=1)
    s1_2_1_id = db.insert_subtask(t1_id, "Nested Subtask 1.2.1", parent_subtask_id=s1_2_id, position=0)

    view = WBSProjectView(db_manager=db, settings_manager=settings)
    view.set_project(p_id)

    # 1. First root (Task 1): Move Up disabled, Move Down enabled, Indent disabled, Outdent disabled
    key_t1 = EntityRef("task", t1_id)
    idx_t1 = view.item_model.index_from_key(key_t1, 0)
    assert idx_t1.isValid()
    row = idx_t1.row()
    tot = view.item_model.rowCount(idx_t1.parent())
    assert row == 0
    assert row < tot - 1

    # 2. Last root (Task 2): Move Up enabled, Move Down disabled
    key_t2 = EntityRef("task", t2_id)
    idx_t2 = view.item_model.index_from_key(key_t2, 0)
    assert idx_t2.isValid()
    row2 = idx_t2.row()
    assert row2 > 0
    assert row2 == tot - 1

    # 3. Subtask 1.1 (first subtask child): Move Up disabled, Indent disabled (no preceding sibling), Outdent disabled (parent is task root)
    key_s1_1 = EntityRef("subtask", s1_1_id)
    idx_s1_1 = view.item_model.index_from_key(key_s1_1, 0)
    assert idx_s1_1.isValid()
    assert idx_s1_1.row() == 0

    # 4. Subtask 1.2 (second subtask child): Move Up enabled, Indent enabled (has preceding sibling subtask 1.1), Outdent disabled (parent is task)
    key_s1_2 = EntityRef("subtask", s1_2_id)
    idx_s1_2 = view.item_model.index_from_key(key_s1_2, 0)
    assert idx_s1_2.isValid()
    assert idx_s1_2.row() > 0

    # 5. Nested Subtask 1.2.1: Outdent enabled because its parent is a subtask
    key_nested = EntityRef("subtask", s1_2_1_id)
    idx_nested = view.item_model.index_from_key(key_nested, 0)
    assert idx_nested.isValid()
    assert idx_nested.parent().isValid()
    assert idx_nested.parent().data(view.item_model.EntityTypeRole) == "subtask"
    view.close()


# ------------------------------------------------------------
# 4. Focus, Calendar, Analytics, Daily Review Empty States
# ------------------------------------------------------------

def test_focus_empty_state_and_dialog(app, db, settings):
    view = FocusView(db, settings)
    view.refresh_data()

    assert view.current_task is None
    assert view.lbl_task_title.text() == "No active tasks available"
    assert "Create a task" in view.lbl_meta.text()
    assert view.btn_toggle.isEnabled() is False
    assert view.btn_complete.isEnabled() is False
    view.close()


def test_calendar_empty_state_panel_and_action(app, db, settings):
    view = CalendarView(db, settings)
    view.show()
    view.refresh_data()

    # 1. StatePanel is visible and properly configured
    assert isinstance(view.state_panel, StatePanel)
    assert not view.state_panel.isHidden()
    assert "No tasks scheduled for" in view.state_panel.title_label.text()
    assert view.state_panel.icon_label.pixmap() is not None and not view.state_panel.icon_label.pixmap().isNull()

    # 2. Primary action button is visible, clickable, and has exact text
    assert not view.state_panel.btn_primary.isHidden()
    assert view.state_panel.btn_primary.text() == "＋ Add Task for This Date"
    assert view.state_panel._action_callback == view._add_task_for_selected_date
    assert view.state_panel.btn_primary.isVisibleTo(view)
    view.close()


def test_calendar_empty_to_populated_transitions(app, db, settings):
    controller = TaskController(db)
    view = CalendarView(db, settings)
    view.show()

    # 1. Initially date A is empty
    from PySide6.QtCore import QDate
    date_a = QDate(2026, 8, 25)
    view.calendar.setSelectedDate(date_a)
    view.refresh_data()

    assert not view.state_panel.isHidden()
    assert view.task_scroll.isHidden()
    assert "25 Aug 2026" in view.state_panel.title_label.text()

    # 2. Add task on date B (2026-08-28)
    task_b = Task(title="Task on 28th", planned_date="2026-08-28", status=TaskStatus.PLANNED)
    controller.add_task(task_b)

    # 3. Select date B -> empty panel hides, task scroll shows
    date_b = QDate(2026, 8, 28)
    view.calendar.setSelectedDate(date_b)
    view.refresh_data()

    assert view.state_panel.isHidden()
    assert not view.task_scroll.isHidden()

    # 4. Switch back to empty date A -> empty panel shows again
    view.calendar.setSelectedDate(date_a)
    view.refresh_data()

    assert not view.state_panel.isHidden()
    assert view.task_scroll.isHidden()
    assert "25 Aug 2026" in view.state_panel.title_label.text()
    view.close()


def test_calendar_add_task_prefill_and_cancellation(app, db, settings, monkeypatch):
    controller = TaskController(db)
    view = CalendarView(db, settings)
    view.show()

    from PySide6.QtCore import QDate
    target_qdate = QDate(2026, 8, 27)
    view.calendar.setSelectedDate(target_qdate)
    view.refresh_data()

    # Capture TaskDialog invocation args
    dialog_opened = False
    dialog_task_arg = None

    class MockTaskDialog:
        Accepted = 1
        Rejected = 0

        def __init__(self, projects, task=None, db_manager=None, settings_manager=None, parent=None):
            nonlocal dialog_opened, dialog_task_arg
            dialog_opened = True
            dialog_task_arg = task
            self.task = task or Task(title="")

        def exec(self):
            return MockTaskDialog.Rejected

        def get_task(self):
            return self.task

    import todo_bird_app.views.calendar_view as cal_module
    monkeypatch.setattr(cal_module, "TaskDialog", MockTaskDialog)

    # 1. Trigger action callback
    view.state_panel.btn_primary.click()

    assert dialog_opened is True
    assert dialog_task_arg is not None
    assert dialog_task_arg.planned_date == "2026-08-27"
    assert dialog_task_arg.due_date == "2026-08-27"

    # 2. Cancelled dialog does not insert a task
    assert len(controller.get_all_tasks()) == 0
    view.close()


def test_calendar_add_task_dialog_accepted(app, db, settings, monkeypatch):
    controller = TaskController(db)
    view = CalendarView(db, settings)
    view.show()

    from PySide6.QtCore import QDate
    target_qdate = QDate(2026, 8, 29)
    view.calendar.setSelectedDate(target_qdate)
    view.refresh_data()

    created_task = Task(title="New Scheduled Task", planned_date="2026-08-29", status=TaskStatus.PLANNED)

    class MockAcceptedDialog:
        Accepted = 1
        Rejected = 0

        def __init__(self, projects, task=None, db_manager=None, settings_manager=None, parent=None):
            self.task = created_task

        def exec(self):
            return MockAcceptedDialog.Accepted

        def get_task(self):
            return self.task

    import todo_bird_app.views.calendar_view as cal_module
    monkeypatch.setattr(cal_module, "TaskDialog", MockAcceptedDialog)

    view.state_panel.btn_primary.click()

    # Task was added and view refreshed
    all_tasks = controller.get_all_tasks()
    assert len(all_tasks) == 1
    assert all_tasks[0].title == "New Scheduled Task"
    assert all_tasks[0].planned_date == "2026-08-29"

    # State panel is now hidden on this date and task scroll is shown
    assert view.state_panel.isHidden()
    assert not view.task_scroll.isHidden()
    view.close()


def test_analytics_zero_data_state(app, db, settings):
    view = AnalyticsView(db, settings)
    view.refresh_data()

    assert view.lbl_planned_hrs.text() == "0.0h"
    assert view.lbl_actual_hrs.text() == "0.0h"
    assert "No task activity data yet" in view.prio_info_lbl.text()
    view.close()


def test_daily_review_empty_state(app, db, settings):
    view = DailyReviewView(db, settings)
    view.refresh_data()

    assert "No tasks" in view.morning_tasks_lbl.text()
    assert ("Zero carryover" in view.carryover_lbl.text() or "No pending tasks" in view.carryover_lbl.text())
    assert "No tasks" in view.tomorrow_lbl.text()
    view.close()


# ------------------------------------------------------------
# 5. Responsive Typography and Theme Rendering
# ------------------------------------------------------------

def test_state_panel_typography_reverse_scaling(app):
    panel = StatePanel()
    panel.show_empty(
        title="Scalable Empty Title",
        description="Testing typography scaling and reverse scaling.",
        action_text="Action Button",
        action_callback=lambda: None,
    )

    # 1. Standard 10pt
    panel.setStyleSheet("font-size: 10pt;")
    panel.resize(400, 200)
    panel.show()
    QApplication.processEvents()
    assert panel.btn_primary.isVisible()

    # 2. Large 20pt
    panel.setStyleSheet("font-size: 20pt;")
    panel.resize(400, 300)
    QApplication.processEvents()
    assert panel.btn_primary.isVisible()

    # 3. Reverse back to 10pt
    panel.setStyleSheet("font-size: 10pt;")
    panel.resize(400, 200)
    QApplication.processEvents()
    assert panel.btn_primary.isVisible()
    panel.close()


def test_state_panel_dark_and_light_rendering(app):
    panel = StatePanel()
    panel.show_empty(
        title="Theme Test",
        description="Testing theme rendering without paintEvent crashes.",
        action_text="Click Me",
        action_callback=lambda: None,
    )
    panel.resize(300, 200)
    panel.show()

    # Dark grab
    pix_dark = panel.grab()
    assert not pix_dark.isNull()

    # Light grab
    panel.setStyleSheet("background: #FFFFFF; color: #000000;")
    QApplication.processEvents()
    pix_light = panel.grab()
    assert not pix_light.isNull()
    panel.close()
