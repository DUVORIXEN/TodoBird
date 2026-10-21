"""
Tests for Batch 3.10H: Task Visibility Authority & Application Window Lifecycle Closure
Covers:
- Task Membership Authority (MEM01..MEM10)
- Window Lifecycle & Clean Shutdown (WIN01..WIN15)
- Realistic Soak Simulation (SOAK01)
"""

import os
import gc
import pytest
from datetime import datetime, date
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow, QWidget
from PySide6.QtCore import Qt, QCoreApplication, QEvent

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.task_controller import TaskController, _GLOBAL_EVENT_BUS
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.models.project import Project
from todo_bird_app.services.window_registry import WindowRegistry
from todo_bird_app.widgets.task_dialog import TaskDialog
from todo_bird_app.widgets.project_dialog import ProjectDialog
from todo_bird_app.widgets.confirm_delete_dialog import ConfirmDeleteDialog
from todo_bird_app.widgets.pinned_priorities_widget import PinnedPrioritiesWidget
from todo_bird_app.widgets.pinned_tasks_window import PinnedTasksWindow
from todo_bird_app.widgets.reminder_dialog import ReminderDialog
from todo_bird_app.widgets.desktop_companion import DesktopCompanion
from todo_bird_app.widgets.task_item_widget import TaskItemWidget
from todo_bird_app.views.main_window import MainWindow
from todo_bird_app.views.inbox_view import InboxView
from todo_bird_app.views.today_view import TodayView


def _is_widget_alive_and_visible(w: QWidget) -> bool:
    try:
        return w.isWidgetType() and w.isVisible()
    except (RuntimeError, AttributeError):
        return False


def _drain_qt_deletes(qapp, target=None, cycles: int = 3, broad: bool = False):
    for _ in range(cycles):
        qapp.processEvents()
        if broad:
            try:
                QCoreApplication.sendPostedEvents(
                    None,
                    QEvent.DeferredDelete,
                )
            except RuntimeError:
                pass
        elif target is not None:
            try:
                QCoreApplication.sendPostedEvents(
                    target,
                    QEvent.DeferredDelete,
                )
            except RuntimeError:
                pass
        try:
            qapp.processEvents()
        except (RuntimeError, Exception):
            pass


@pytest.fixture
def temp_env(tmp_path):
    db_file = tmp_path / "test_tb_310h.db"
    db = DatabaseManager(str(db_file))
    settings = SettingsManager(db)
    controller = TaskController(db)
    WindowRegistry.clear()
    yield db, settings, controller
    WindowRegistry.clear()


@pytest.fixture
def qapp():
    return QApplication.instance() or QApplication([])


# ============================================================
# PART 1: TASK MEMBERSHIP AUTHORITY (MEM01..MEM10)
# ============================================================

def test_mem01_unassigned_pinned(temp_env, qapp):
    """MEM01: Unassigned + pinned -> Inbox YES, Pin YES"""
    db, settings, controller = temp_env
    t = Task(title="Inbox Pinned Task", project_id=1, is_pinned=True, pin_position=1, status=TaskStatus.PLANNED)
    t_id = controller.add_task(t)

    inbox_tasks = controller.get_inbox_tasks()
    inbox_ids = [task.id for task in inbox_tasks]
    assert t_id in inbox_ids, "Unassigned pinned task MUST appear in Inbox"

    with db.get_connection() as conn:
        rows = conn.execute("SELECT id FROM tasks WHERE is_pinned = 1;").fetchall()
        pinned_ids = [r[0] for r in rows]
    assert t_id in pinned_ids, "Pinned task MUST appear in Pinned Tasks"


def test_mem02_unassigned_unpinned(temp_env, qapp):
    """MEM02: Unassigned + unpinned -> Inbox YES, Pin NO"""
    db, settings, controller = temp_env
    t = Task(title="Inbox Unpinned Task", project_id=1, is_pinned=False, status=TaskStatus.PLANNED)
    t_id = controller.add_task(t)

    inbox_tasks = controller.get_inbox_tasks()
    inbox_ids = [task.id for task in inbox_tasks]
    assert t_id in inbox_ids, "Unassigned unpinned task MUST appear in Inbox"

    with db.get_connection() as conn:
        rows = conn.execute("SELECT id FROM tasks WHERE is_pinned = 1;").fetchall()
        pinned_ids = [r[0] for r in rows]
    assert t_id not in pinned_ids, "Unpinned task MUST NOT appear in Pinned Tasks"


def test_mem03_project_pinned(temp_env, qapp):
    """MEM03: Project + pinned -> Project YES, Pin YES, Inbox NO"""
    db, settings, controller = temp_env
    proj_id = db.insert_project({"name": "Project Alpha", "color": "#E95420", "icon": "folder", "description": "", "is_archived": 0})
    t = Task(title="Project Alpha Pinned Task", project_id=proj_id, is_pinned=True, pin_position=1, status=TaskStatus.PLANNED)
    t_id = controller.add_task(t)

    # Inbox check
    inbox_tasks = controller.get_inbox_tasks()
    inbox_ids = [task.id for task in inbox_tasks]
    assert t_id not in inbox_ids, "Project task MUST NOT appear in Inbox"

    # Project check
    proj_tasks = controller.get_project_tasks(proj_id)
    proj_task_ids = [task.id for task in proj_tasks]
    assert t_id in proj_task_ids, "Project task MUST appear in its Project"

    # Pinned check
    with db.get_connection() as conn:
        rows = conn.execute("SELECT id FROM tasks WHERE is_pinned = 1;").fetchall()
        pinned_ids = [r[0] for r in rows]
    assert t_id in pinned_ids, "Pinned task MUST appear in Pinned Priorities"


def test_mem04_project_unpinned(temp_env, qapp):
    """MEM04: Project + unpinned -> Project YES, Pin NO, Inbox NO"""
    db, settings, controller = temp_env
    proj_id = db.insert_project({"name": "Project Beta", "color": "#10B981", "icon": "folder", "description": "", "is_archived": 0})
    t = Task(title="Project Beta Unpinned Task", project_id=proj_id, is_pinned=False, status=TaskStatus.PLANNED)
    t_id = controller.add_task(t)

    inbox_tasks = controller.get_inbox_tasks()
    inbox_ids = [task.id for task in inbox_tasks]
    assert t_id not in inbox_ids, "Project task MUST NOT appear in Inbox"

    proj_tasks = controller.get_project_tasks(proj_id)
    proj_task_ids = [task.id for task in proj_tasks]
    assert t_id in proj_task_ids, "Project task MUST appear in its Project"

    with db.get_connection() as conn:
        rows = conn.execute("SELECT id FROM tasks WHERE is_pinned = 1;").fetchall()
        pinned_ids = [r[0] for r in rows]
    assert t_id not in pinned_ids, "Unpinned task MUST NOT appear in Pinned Priorities"


def test_mem05_unpin_changes_only_pinned_field(temp_env, qapp):
    """MEM05: Unpin changes only pinned field"""
    db, settings, controller = temp_env
    t = Task(
        title="Unpin Test Task",
        project_id=1,
        is_pinned=True,
        pin_position=2,
        status=TaskStatus.IN_PROGRESS,
        progress=45,
        planned_date="2026-08-20",
        due_date="2026-08-25",
        actual_start_date="2026-08-20",
        actual_start_time="09:00",
        estimated_duration=120,
    )
    t_id = controller.add_task(t)

    # Perform unpin
    widget = PinnedPrioritiesWidget(db, settings)
    widget.unpin_task(t_id)

    updated_row = db.get_task_by_id(t_id)
    assert bool(updated_row["is_pinned"]) is False
    assert updated_row["project_id"] == 1
    assert updated_row["status"] == "In Progress"
    assert updated_row["progress"] == 45
    assert updated_row["planned_date"] == "2026-08-20"
    assert updated_row["due_date"] == "2026-08-25"
    assert updated_row["estimated_duration"] == 120


def test_mem06_pin_changes_only_pinned_field(temp_env, qapp):
    """MEM06: Pin changes only pinned field"""
    db, settings, controller = temp_env
    proj_id = db.insert_project({"name": "Project Gamma", "color": "#8B5CF6", "icon": "folder", "description": "", "is_archived": 0})
    t = Task(
        title="Pin Test Task",
        project_id=proj_id,
        is_pinned=False,
        status=TaskStatus.BLOCKED,
        progress=20,
        planned_date="2026-08-18",
        due_date="2026-08-22",
    )
    t_id = controller.add_task(t)

    # Pin task
    controller.pin_task(t_id)

    updated_row = db.get_task_by_id(t_id)
    assert bool(updated_row["is_pinned"]) is True
    assert updated_row["project_id"] == proj_id
    assert updated_row["status"] == "Blocked"
    assert updated_row["progress"] == 20
    assert updated_row["planned_date"] == "2026-08-18"


def test_mem07_project_id_unchanged_after_unpin(temp_env, qapp):
    """MEM07: Project ID unchanged after unpin"""
    db, settings, controller = temp_env
    proj_id = db.insert_project({"name": "Special Project", "color": "#F59E0B", "icon": "folder", "description": "", "is_archived": 0})
    t = Task(title="Special Task", project_id=proj_id, is_pinned=True)
    t_id = controller.add_task(t)

    controller.unpin_task(t_id)
    task = controller.get_task(t_id)
    assert task.project_id == proj_id


def test_mem08_status_unchanged(temp_env, qapp):
    """MEM08: Status unchanged across pin/unpin"""
    db, settings, controller = temp_env
    t = Task(title="Status Task", project_id=1, is_pinned=True, status=TaskStatus.DELAYED)
    t_id = controller.add_task(t)

    controller.unpin_task(t_id)
    task = controller.get_task(t_id)
    assert task.status == TaskStatus.DELAYED

    controller.pin_task(t_id)
    task = controller.get_task(t_id)
    assert task.status == TaskStatus.DELAYED


def test_mem09_nested_hierarchy_unchanged(temp_env, qapp):
    """MEM09: Nested subtask hierarchy remains completely intact after pin/unpin"""
    db, settings, controller = temp_env
    t = Task(title="Parent Task", project_id=1, is_pinned=True)
    t_id = controller.add_task(t)

    sub_id = db.insert_subtask(t_id, "Child Subtask 1", is_completed=False, position=0)
    sub_sub_id = db.insert_subtask(t_id, "Grandchild Subtask 1.1", is_completed=False, position=0, parent_subtask_id=sub_id)

    controller.unpin_task(t_id)

    tree = db.get_subtask_tree(t_id)
    assert len(tree) == 1
    assert tree[0]["title"] == "Child Subtask 1"
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["title"] == "Grandchild Subtask 1.1"


def test_mem10_restart_preserves_correct_memberships(temp_env, qapp):
    """MEM10: Restart preserves correct memberships for unassigned and project tasks"""
    db, settings, controller = temp_env
    proj_id = db.insert_project({"name": "Project Delta", "color": "#EC4899", "icon": "folder", "description": "", "is_archived": 0})

    t_inbox = Task(title="Restart Inbox Task", project_id=1, is_pinned=False, status=TaskStatus.PLANNED)
    t_inbox_pinned = Task(title="Restart Inbox Pinned Task", project_id=1, is_pinned=True, status=TaskStatus.PLANNED)
    t_proj = Task(title="Restart Project Task", project_id=proj_id, is_pinned=False, status=TaskStatus.PLANNED)
    t_proj_pinned = Task(title="Restart Project Pinned Task", project_id=proj_id, is_pinned=True, status=TaskStatus.PLANNED)

    id_inbox = controller.add_task(t_inbox)
    id_inbox_p = controller.add_task(t_inbox_pinned)
    id_proj = controller.add_task(t_proj)
    id_proj_p = controller.add_task(t_proj_pinned)

    # Re-instantiate database manager to simulate application restart
    db2 = DatabaseManager(db.db_path)
    ctrl2 = TaskController(db2)

    inbox_tasks = [t.id for t in ctrl2.get_inbox_tasks()]
    assert id_inbox in inbox_tasks
    assert id_inbox_p in inbox_tasks
    assert id_proj not in inbox_tasks
    assert id_proj_p not in inbox_tasks

    proj_tasks = [t.id for t in ctrl2.get_project_tasks(proj_id)]
    assert id_proj in proj_tasks
    assert id_proj_p in proj_tasks
    assert id_inbox not in proj_tasks
    assert id_inbox_p not in proj_tasks


# ============================================================
# PART 2: WINDOW LIFECYCLE & CLEAN SHUTDOWN (WIN01..WIN15)
# ============================================================

def test_win01_task_dialog_no_zombie_growth(temp_env, qapp):
    """WIN01: Open/close TaskDialog 20 times -> no growing zombie count"""
    db, settings, controller = temp_env
    projects = controller.get_all_projects()

    initial_dialogs = sum(1 for w in QApplication.topLevelWidgets() if isinstance(w, TaskDialog))

    for _ in range(20):
        dlg = TaskDialog(projects, db_manager=db, settings_manager=settings)
        dlg.accept()
        dlg.deleteLater()
        _drain_qt_deletes(qapp, dlg)

    gc.collect()
    _drain_qt_deletes(qapp)

    final_dialogs = sum(1 for w in QApplication.topLevelWidgets() if isinstance(w, TaskDialog))
    assert final_dialogs <= initial_dialogs


def test_win02_subtask_dialog_no_leak(temp_env, qapp):
    """WIN02: Open/close subtask details dialog repeatedly -> no leaks"""
    db, settings, controller = temp_env
    projects = controller.get_all_projects()
    dlg = TaskDialog(projects, db_manager=db, settings_manager=settings)

    initial_top_levels = len(QApplication.topLevelWidgets())

    for i in range(10):
        sub_dlg = QDialog(dlg)
        sub_dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        sub_dlg.accept()
        sub_dlg.deleteLater()
        _drain_qt_deletes(qapp, sub_dlg)

    gc.collect()
    _drain_qt_deletes(qapp)

    dlg.reject()
    dlg.deleteLater()
    _drain_qt_deletes(qapp, dlg)

    final_top_levels = len(QApplication.topLevelWidgets())
    assert final_top_levels <= initial_top_levels


def test_win03_project_dialog_no_leak(temp_env, qapp):
    """WIN03: Open/close ProjectDialog 20 times -> clean deletion"""
    db, settings, controller = temp_env
    initial_top_levels = len(QApplication.topLevelWidgets())

    for _ in range(20):
        dlg = ProjectDialog(settings_manager=settings)
        dlg.reject()
        dlg.deleteLater()
        _drain_qt_deletes(qapp, dlg)

    gc.collect()
    _drain_qt_deletes(qapp)

    final_top_levels = len(QApplication.topLevelWidgets())
    assert final_top_levels <= initial_top_levels + 1


def test_win04_pinned_window_one_instance(temp_env, qapp):
    """WIN06: PinnedTasksWindow single instance behavior"""
    db, settings, controller = temp_env
    w1 = PinnedTasksWindow.get_or_open(db, settings)
    assert _is_widget_alive_and_visible(w1)

    w2 = PinnedTasksWindow.get_or_open(db, settings)
    assert w1 is w2, "PinnedTasksWindow MUST reuse existing instance"

    w1.close()
    qapp.processEvents()
    qapp.processEvents()


def test_win05_companion_cleanup(temp_env, qapp):
    """WIN07: Companion single instance & clean shutdown"""
    companion = DesktopCompanion("Hello")
    companion.show()
    assert _is_widget_alive_and_visible(companion)

    companion.cleanup()
    qapp.processEvents()
    qapp.processEvents()
    assert not _is_widget_alive_and_visible(companion)


def test_win06_reminder_clean_lifecycle(temp_env, qapp):
    """WIN05: Reminder opens and closes cleanly"""
    db, settings, controller = temp_env
    t = Task(id=99, title="Reminder Test", startup_reminder=True)
    dlg = ReminderDialog(t, settings_manager=settings)
    dlg.show()
    assert _is_widget_alive_and_visible(dlg)

    dlg.on_dismiss_clicked()
    qapp.processEvents()
    qapp.processEvents()
    assert not _is_widget_alive_and_visible(dlg)


def test_win07_closing_mainwindow_closes_pinned_window(temp_env, qapp):
    """WIN08: Closing MainWindow closes PinnedTasksWindow"""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)
    main_win = MainWindow(db, settings, theme_ctrl)
    main_win.show()

    pin_win = PinnedTasksWindow.get_or_open(db, settings, parent=main_win)
    pin_win.show()
    assert _is_widget_alive_and_visible(pin_win)

    main_win.close()
    qapp.processEvents()
    qapp.processEvents()

    assert not _is_widget_alive_and_visible(pin_win)
    assert not _is_widget_alive_and_visible(main_win)


def test_win08_closing_mainwindow_closes_reminders(temp_env, qapp):
    """WIN09: Closing MainWindow closes reminder dialogs"""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)
    main_win = MainWindow(db, settings, theme_ctrl)
    main_win.show()

    t = Task(id=101, title="Shutdown Reminder", startup_reminder=True)
    rem_dlg = ReminderDialog(t, settings_manager=settings, parent=main_win)
    rem_dlg.show()
    main_win.startup_reminder_dialogs = [rem_dlg]

    main_win.close()
    qapp.processEvents()
    qapp.processEvents()

    assert not _is_widget_alive_and_visible(rem_dlg)


def test_win09_window_registry_close_all_on_shutdown(temp_env, qapp):
    """WIN10..13: WindowRegistry shuts down all registered windows cleanly"""
    db, settings, controller = temp_env
    pin_win = PinnedTasksWindow(db, settings)
    pin_win.show()

    t = Task(id=102, title="Registry Task")
    rem_dlg = ReminderDialog(t, settings_manager=settings)
    rem_dlg.show()

    companion = DesktopCompanion("Bye")
    companion.show()

    assert len(WindowRegistry.get_open_windows()) >= 3

    WindowRegistry.close_all_on_shutdown()
    qapp.processEvents()
    qapp.processEvents()

    assert len(WindowRegistry.get_open_windows()) == 0


def test_win10_save_cancel_release_dialog(temp_env, qapp):
    """WIN14: Save and Cancel both release dialog cleanly"""
    db, settings, controller = temp_env
    dlg1 = ProjectDialog(settings_manager=settings)
    dlg1.name_input.setText("New Proj")
    dlg1.on_save()
    qapp.processEvents()
    qapp.processEvents()
    assert not _is_widget_alive_and_visible(dlg1)

    dlg2 = ProjectDialog(settings_manager=settings)
    dlg2.reject()
    qapp.processEvents()
    qapp.processEvents()
    assert not _is_widget_alive_and_visible(dlg2)


def test_win11_restart_after_normal_shutdown(temp_env, qapp):
    """WIN15: Normal shutdown and restart works without hung state"""
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)
    main_win1 = MainWindow(db, settings, theme_ctrl)
    main_win1.show()
    main_win1.close()
    qapp.processEvents()

    # Restart
    main_win2 = MainWindow(db, settings, theme_ctrl)
    main_win2.show()
    assert _is_widget_alive_and_visible(main_win2)
    main_win2.close()
    qapp.processEvents()


# ============================================================
# PART 3: REALISTIC SOAK SIMULATION
# ============================================================

def test_soak_realistic_session_cycles(temp_env, qapp):
    """
    SOAK TEST: Simulate 10 realistic operator session cycles:
    Inbox -> Task Editor -> Save -> Project -> Project Editor -> Cancel ->
    Settings -> Pinned Tasks -> Reminder -> Open Task -> Close Editor ->
    Dashboard -> Gantt -> Close Todo Bird.
    """
    db, settings, controller = temp_env
    theme_ctrl = ThemeController(settings)

    initial_top_level_count = len(QApplication.topLevelWidgets())

    for cycle in range(10):
        # 1. Open MainWindow
        main_win = MainWindow(db, settings, theme_ctrl)
        main_win.show()
        _drain_qt_deletes(qapp)

        # 2. Navigate to Inbox
        main_win.navigation_controller.set_active_section("inbox")
        _drain_qt_deletes(qapp)

        # 3. Create task in Inbox
        t = Task(title=f"Soak Task Cycle {cycle}", project_id=1, is_pinned=(cycle % 2 == 0))
        t_id = controller.add_task(t)

        # 4. Open Project and Project Editor
        main_win.navigation_controller.set_active_section("projects")
        proj_dlg = ProjectDialog(settings_manager=settings, parent=main_win)
        proj_dlg.reject()
        proj_dlg.deleteLater()
        _drain_qt_deletes(qapp, proj_dlg)

        # 5. Open Pinned Tasks Window
        pin_win = PinnedTasksWindow.get_or_open(db, settings, parent=main_win)
        _drain_qt_deletes(qapp)

        # 6. Reminder Dialog
        rem_dlg = ReminderDialog(t, task_controller=controller, settings_manager=settings, parent=main_win)
        rem_dlg.show()
        _drain_qt_deletes(qapp)
        rem_dlg.on_dismiss_clicked()
        _drain_qt_deletes(qapp, rem_dlg)

        # 7. Navigate Dashboard & Gantt
        main_win.navigation_controller.set_active_section("dashboard")
        _drain_qt_deletes(qapp)
        main_win.navigation_controller.set_active_section("gantt")
        _drain_qt_deletes(qapp)

        # 8. Close Main Window
        main_win.close()
        main_win.deleteLater()
        _drain_qt_deletes(qapp, main_win)
        _drain_qt_deletes(qapp, broad=True)
        gc.collect()
        _drain_qt_deletes(qapp, broad=True)

    final_top_level_count = len(QApplication.topLevelWidgets())
    assert final_top_level_count <= initial_top_level_count + 1


def test_win12_today_view_large_scope_is_render_bounded(temp_env, qapp):
    """WIN12: TodayView keeps full metrics but renders only one bounded page."""
    db, settings, controller = temp_env
    today_iso = date.today().strftime("%Y-%m-%d")

    for i in range(150):
        controller.add_task(
            Task(
                title=f"Large Today Task {i}",
                planned_date=today_iso,
                status=TaskStatus.PLANNED,
            )
        )

    view = TodayView(db, settings)
    qapp.processEvents()

    rendered = view.findChildren(TaskItemWidget)
    assert len(rendered) == 100
    assert "0 / 150 Completed" in view.stat_label.text()
    assert view.lbl_count_info.text() == "Showing 1–100 of 150 tasks"

    view.next_page()
    qapp.processEvents()

    rendered = view.findChildren(TaskItemWidget)
    assert len(rendered) == 50
    assert "0 / 150 Completed" in view.stat_label.text()
    assert view.lbl_count_info.text() == "Showing 101–150 of 150 tasks"

    view.cleanup()
    view.deleteLater()
    _drain_qt_deletes(qapp, view)
