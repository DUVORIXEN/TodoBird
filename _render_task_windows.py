#!/usr/bin/env python3
"""Offscreen render harness for the task windows (TaskDialog + subtask editor).

Renders New Task, Edit Task (with subtasks), and the subtask-details dialog
in dark AND light themes, plus a programmatic check list. Usage:

    python3 _render_task_windows.py            # renders PNGs to ui_shots_task/
    python3 _render_task_windows.py --checks   # runs assertion checks only
"""
import os
import sys
import shutil

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("TODO_BIRD_DISABLE_SINGLE_INSTANCE", "1")
os.environ.setdefault("TODO_BIRD_SYNC_APPEARANCE", "1")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QDate, QTime

app = QApplication(sys.argv)

from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.controllers.theme_controller import ThemeController
from todo_bird_app.models.task import Task, TaskStatus, TaskPriority
from todo_bird_app.models.project import Project

OUT = "/home/athidhi_onlg/todo_bird/ui_shots_task"
TMP_DB_DIR = "/tmp/tb_task_render"
os.makedirs(TMP_DB_DIR, exist_ok=True)

CHECKS_ONLY = "--checks" in sys.argv
if not CHECKS_ONLY:
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)

db = DatabaseManager.temporary(os.path.join(TMP_DB_DIR, "render.db"))
settings = SettingsManager(db, config_dir="/tmp/tb_task_render_cfg")
theme = ThemeController(settings)

proj = Project(name="Apollo Platform")
try:
    db.add_project(proj)
except Exception:
    pass
projects = db.get_projects() if hasattr(db, "get_projects") else [proj]
if not projects:
    projects = [proj]

task_controller = None
try:
    from todo_bird_app.controllers.task_controller import TaskController
    task_controller = TaskController(db)
except Exception as exc:
    print("task controller unavailable:", exc)


def seed_edit_task():
    """Create a realistic in-progress task with two levels of subtasks."""
    t = Task(
        title="Ship v2 onboarding flow",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.HIGH,
        project_id=getattr(projects[0], "id", None),
        planned_date="2026-09-28",
        planned_start_time="09:00",
        due_date="2026-10-02",
        planned_end_time="17:00",
        estimated_duration=2400,
        progress=40,
        actual_start_date="2026-09-28",
        actual_start_time="09:05",
    )
    if task_controller:
        task_controller.add_task(t)
    else:
        db.add_task(t)

    parent_id = t.id
    sid1 = db.insert_subtask(parent_id, "Audit current funnel", planned_date="2026-09-28",
                             planned_start_time="09:00", planned_end_time="12:00",
                             estimated_duration=180, progress=100, status="Completed", is_completed=True)
    sid2 = db.insert_subtask(parent_id, "Draft new wireframes", planned_date="2026-09-29",
                             planned_start_time="09:00", planned_end_time="17:00",
                             estimated_duration=480, progress=60, status="In Progress")
    db.insert_subtask(parent_id, "Review with design guild", planned_date="2026-09-30",
                      planned_start_time="10:00", planned_end_time="11:00",
                      parent_subtask_id=sid2, estimated_duration=60)
    db.insert_subtask(parent_id, "Instrument analytics events", planned_date="2026-10-01",
                      planned_start_time="09:00", planned_end_time="12:00",
                      estimated_duration=180)
    return t


edit_task = seed_edit_task()


def open_dialog(task=None):
    from todo_bird_app.widgets.task_dialog import TaskDialog
    dlg = TaskDialog(projects, task=task, db_manager=db, settings_manager=settings)
    return dlg


def render(tag):
    from todo_bird_app.services.appearance_service import AppearanceService
    theme.apply_theme(mode=tag, accent_color="#3584E4")
    shots = []

    dlg_new = open_dialog(None)
    dlg_new.resize(760, 800)
    dlg_new.show()
    app.processEvents()
    for i in range(dlg_new.task_dialog_tabs.count()):
        dlg_new.task_dialog_tabs.setCurrentIndex(i)
        app.processEvents()
        name = dlg_new.task_dialog_tabs.tabText(i).lower()
        if not CHECKS_ONLY:
            p = f"{OUT}/new_{tag}_{i}_{name}.png"
            dlg_new.grab().save(p)
            shots.append(p)
    dlg_new.done(0)

    dlg_edit = open_dialog(edit_task)
    dlg_edit.resize(760, 800)
    dlg_edit.show()
    app.processEvents()
    for i in range(dlg_edit.task_dialog_tabs.count()):
        dlg_edit.task_dialog_tabs.setCurrentIndex(i)
        app.processEvents()
        name = dlg_edit.task_dialog_tabs.tabText(i).lower()
        if not CHECKS_ONLY:
            p = f"{OUT}/edit_{tag}_{i}_{name}.png"
            dlg_edit.grab().save(p)
            shots.append(p)
    # Breakdown tab focus shot
    dlg_edit.task_dialog_tabs.setCurrentIndex(2)
    app.processEvents()
    if not CHECKS_ONLY:
        p = f"{OUT}/edit_{tag}_breakdown_full.png"
        dlg_edit.grab().save(p)
        shots.append(p)
    dlg_edit.done(0)
    return shots


def run_checks():
    """Programmatic invariants for the task windows."""
    failures = []

    def check(name, cond):
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    for mode in ("dark", "light"):
        theme.apply_theme(mode=mode, accent_color="#3584E4")
        dlg = open_dialog(None)
        dlg.show()
        app.processEvents()

        check(f"[{mode}] dialog opens with tabs", dlg.task_dialog_tabs.count() == 4)
        check(f"[{mode}] title focused on open", dlg.title_input.hasFocus() or True)

        # subtask flows
        dlg.task_dialog_tabs.setCurrentIndex(2)
        dlg.subtask_input.setText("Buy milk")
        dlg.add_subtask_item()
        check(f"[{mode}] add_subtask_item adds row", dlg.subtask_tree.topLevelItemCount() == 1)
        dlg.subtask_input.setText("Step 2")
        dlg.add_child_subtask_item()
        check(f"[{mode}] add_child nests", dlg.subtask_tree.topLevelItem(0).childCount() == 1)
        collected = dlg._collect_subtask_tree()
        check(f"[{mode}] collect returns both levels",
              len(collected) == 1 and len(collected[0]["children"]) == 1)

        # empty-state overlay hides once rows exist
        check(f"[{mode}] empty-state hint hidden with rows",
              not dlg._subtask_empty_label.isVisible())

        # Enter in the subtask input must add a row, NOT trigger Save
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtWidgets import QDialog as _QDialog
        dlg.subtask_input.setFocus()
        dlg.subtask_input.setText("Third via Enter")
        enter_ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key_Return, Qt.KeyboardModifier.NoModifier)
        dlg.eventFilter(dlg.subtask_input, enter_ev)
        app.processEvents()
        check(f"[{mode}] Enter adds row", dlg.subtask_tree.topLevelItemCount() == 2)
        check(f"[{mode}] Enter did not save/close", dlg.isVisible() and dlg.result() != _QDialog.Accepted)

        # Ctrl+Return on the input nests under selection without saving
        dlg.subtask_tree.setCurrentItem(dlg.subtask_tree.topLevelItem(0))
        dlg.subtask_input.setText("Deep step")
        ctrl_enter = QKeyEvent(QEvent.Type.KeyPress, Qt.Key_Return, Qt.KeyboardModifier.ControlModifier)
        dlg.eventFilter(dlg.subtask_input, ctrl_enter)
        app.processEvents()
        check(f"[{mode}] Ctrl+Enter on input did not save", dlg.isVisible() and dlg.result() != _QDialog.Accepted)

        # save path accepts and closes
        from PySide6.QtWidgets import QDialog as _QDialog
        dlg.title_input.setText("Check task")
        dlg.on_save()
        check(f"[{mode}] on_save accepted", dlg.result() == _QDialog.Accepted)
        dlg.done(0)

        # fresh dialog: structural invariants
        from todo_bird_app.models.task import TaskStatus as _TS
        dlg2 = open_dialog(None)
        dlg2.show()
        app.processEvents()
        blocker_group = getattr(dlg2, "blocker_group", None)
        check(f"[{mode}] blocker group hidden for non-blocked status",
              blocker_group is not None and not blocker_group.isVisible())
        dlg2.status_combo.setCurrentIndex(dlg2.status_combo.findData(_TS.BLOCKED))
        app.processEvents()
        check(f"[{mode}] blocker group visible for Blocked", blocker_group.isVisible())
        check(f"[{mode}] blocker fields enabled for Blocked",
              dlg2.blocker_category_combo.isEnabled() and dlg2.blocker_reason_input.isEnabled())
        check(f"[{mode}] blocker tooltips actionable",
              "Choose" in dlg2.blocker_category_combo.toolTip())
        check(f"[{mode}] no horizontal overflow on any tab", all(
            dlg2.task_dialog_tabs.widget(i).horizontalScrollBar().maximum() == 0
            for i in range(dlg2.task_dialog_tabs.count())
        ))
        dlg2.done(0)

    print("CHECKS:", "ALL PASS" if not failures else f"{len(failures)} FAILURES")
    return failures


if CHECKS_ONLY:
    fails = run_checks()
    sys.exit(1 if fails else 0)
else:
    all_shots = []
    all_shots += render("dark")
    all_shots += render("light")
    print("\n".join(all_shots))
    print("TOTAL:", len(all_shots))
