import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit,
    QComboBox, QDateEdit, QTimeEdit, QSpinBox, QSlider, QPushButton,
    QFormLayout, QGroupBox, QScrollArea, QWidget, QCheckBox,
    QTreeWidget, QTreeWidgetItem, QMessageBox, QFrame, QFileDialog,
    QTabWidget, QSizePolicy, QDoubleSpinBox, QHeaderView
)
from todo_bird_app.widgets.rich_text_editor import RichTextEditor
from PySide6.QtCore import Qt, QDate, QTime, QRect
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut

from todo_bird_app.gantt.gantt_dependency_engine import GanttDependencyEngine
from todo_bird_app.models.task import Task, TaskPriority, TaskStatus, TaskCategory
from todo_bird_app.models.project import Project
from todo_bird_app.widgets.work_effort_editor import WorkEffortEditor
from todo_bird_app.services.dependency_authoring_service import (
    DependencyAuthoringService,
    DependencyAuthoringSpec,
    parse_authoring_dependency_specs,
    raw_dependency_list,
)
from todo_bird_app.services.experience_profile import ExperienceProfileService
from todo_bird_app.services.typography_service import TypographyService
from todo_bird_app.services.schedule_constraint_service import (
    CalendarException,
    ConstraintType,
    ProjectCalendarSpec,
    get_constraint_display_name,
    get_constraint_tooltip,
    is_date_required,
    parse_constraint_datetime,
)
from todo_bird_app.services.reminder_policy_service import ReminderPolicyService
from todo_bird_app.services.wbs_service import EntityRef


WORKFLOW_STATUS_OPTIONS = [
    ("Not Started", TaskStatus.INBOX),
    ("Planned", TaskStatus.PLANNED),
    ("In Progress", TaskStatus.IN_PROGRESS),
    ("Blocked", TaskStatus.BLOCKED),
    ("Delayed", TaskStatus.DELAYED),
    ("Moved", TaskStatus.MOVED),
    ("Completed", TaskStatus.COMPLETED),
    ("Cancelled", TaskStatus.CANCELLED),
]

BLOCKER_CATEGORY_OPTIONS = [
    "None",
    "Dependency",
    "Decision / Approval",
    "Resource / Manpower",
    "Technical Issue",
    "Material / Parts",
    "Budget / Commercial",
    "Customer / Stakeholder",
    "External Agency",
    "Information / Input",
    "Other",
]


def _coerce_task_status(value: Any, default: TaskStatus = TaskStatus.PLANNED) -> TaskStatus:
    if isinstance(value, TaskStatus):
        return value
    text = str(value or "").strip()
    if not text:
        return default
    for status in TaskStatus:
        if text == status.value or text.upper() == status.name:
            return status
    return default


def _dot_icon(color: str, diameter: int = 10) -> QIcon:
    """Small filled color dot used as a combo-item swatch (emoji-free)."""
    pixmap = QPixmap(diameter, diameter)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(1, 1, diameter - 2, diameter - 2)
    painter.end()
    return QIcon(pixmap)


class TaskDialog(QDialog):
    """
    Planify-style Task Creation and Editing Dialog.
    """
    ESTIMATED_DAY_MINUTES = 1440

    def __init__(
        self,
        projects: List[Project],
        task: Optional[Task] = None,
        db_manager=None,
        settings_manager=None,
        parent=None
    ):
        super().__init__(parent)
        self.projects = projects
        self.db_manager = db_manager
        if settings_manager is None and parent is not None:
            settings_manager = getattr(parent, "settings_manager", None)
        self.settings_manager = settings_manager
        self.task = self._resolve_canonical_raw_task(task)
        self._raw_planned_effort_at_open = int(
            getattr(self.task, "planned_effort_minutes", 0) or 0
        )
        self._raw_daily_dedication_at_open = int(
            getattr(self.task, "daily_dedication_minutes", 0) or 0
        )
        self._raw_allocation_mode_at_open = (
            getattr(self.task, "allocation_mode", "fixed_daily")
            or "fixed_daily"
        )
        self._work_effort_user_touched = False
        self._syncing_duration_controls = False
        self._global_working_calendar_connected = False

        from todo_bird_app.services.window_registry import WindowRegistry
        WindowRegistry.register(self, role="task_dialog")

        self.subtasks_data = []
        if self.db_manager is not None and self.task.id is not None:
            self.subtasks_data = self.db_manager.get_subtask_tree(self.task.id)

        self.setWindowTitle("Edit Task" if task and task.id else "New Task")
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        self.setMinimumSize(480, 500)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._restore_geometry()
        self._init_ui()
        try:
            from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
            _GLOBAL_EVENT_BUS.working_calendar_changed.connect(
                self._on_global_working_calendar_changed
            )
            self._global_working_calendar_connected = True
        except Exception:
            pass
        
        from todo_bird_app.services.typography_service import TypographyService
        TypographyService.apply_to_widget(self, "dialogs", self.settings_manager)

    def _resolve_canonical_raw_task(self, task: Optional[Any]) -> Task:
        self.task_source_path = "new_task"
        if task is None:
            return Task()

        candidate = Task.from_row(task) if isinstance(task, dict) else task
        self.task_source_path = type(candidate).__name__

        task_id = getattr(candidate, "id", None)
        try:
            numeric_id = int(task_id)
        except (TypeError, ValueError):
            numeric_id = 0

        if (
            numeric_id > 0
            and self.db_manager is not None
            and hasattr(self.db_manager, "get_task_by_id")
        ):
            row = self.db_manager.get_task_by_id(numeric_id)
            if row:
                self.task_source_path = "DatabaseManager.get_task_by_id"
                return Task.from_row(row)

        return candidate if isinstance(candidate, Task) else Task.from_row(candidate)

    def _duration_days_from_minutes(self, minutes: int) -> float:
        try:
            clean_minutes = max(0, int(minutes or 0))
        except (TypeError, ValueError):
            clean_minutes = 0
        return round(clean_minutes / self.ESTIMATED_DAY_MINUTES, 2)

    def _duration_minutes_from_days(self, days: float) -> int:
        try:
            clean_days = max(0.0, float(days or 0.0))
        except (TypeError, ValueError):
            clean_days = 0.0
        return int(round(clean_days * self.ESTIMATED_DAY_MINUTES))

    def _current_project_id(self) -> Optional[int]:
        project_id = None
        if hasattr(self, "project_combo"):
            project_id = self.project_combo.currentData()
        if project_id is None:
            project_id = getattr(self.task, "project_id", None)
        try:
            return int(project_id) if project_id is not None else None
        except (TypeError, ValueError):
            return None

    def _current_project_calendar_spec(self) -> Optional[ProjectCalendarSpec]:
        from todo_bird_app.services.schedule_calendar_service import (
            effective_project_calendar_from_db,
        )

        return effective_project_calendar_from_db(
            self.db_manager,
            self._current_project_id(),
        )

    def _dependency_successor_key(self) -> Optional[EntityRef]:
        task_id = getattr(self.task, "id", None)
        try:
            task_id = int(task_id)
        except (TypeError, ValueError):
            return None
        if task_id <= 0:
            return None
        return EntityRef.task(task_id)

    def _dependency_candidates_by_id(self, candidates) -> Dict[int, Tuple[EntityRef, ...]]:
        refs: Dict[int, List[EntityRef]] = {}
        for candidate in candidates:
            refs.setdefault(candidate.key.entity_id, []).append(candidate.key)
        return {key: tuple(value) for key, value in refs.items()}

    def _legacy_external_dependency_candidates(
        self,
        current_specs: Sequence[DependencyAuthoringSpec],
        existing_keys: set,
    ):
        if self.db_manager is None:
            return []
        external = []
        try:
            rows = {
                int(row.get("id")): row
                for row in self.db_manager.get_all_tasks()
                if row.get("id") is not None
            }
        except Exception:
            rows = {}
        for spec in current_specs:
            key = spec.predecessor_key
            if key in existing_keys or key.entity_type != "task":
                continue
            row = rows.get(key.entity_id)
            if not row:
                continue
            status = row.get("status") or "Inbox"
            visible_status = "Not Started" if status == "Inbox" else str(status)
            external.append(
                {
                    "key": key,
                    "title": row.get("title") or f"Task {key.entity_id}",
                    "display_title": (
                        f"[External Project #{key.entity_id}] "
                        f"{row.get('title') or f'Task {key.entity_id}'}"
                    ),
                    "status": f"{visible_status} (Legacy External)",
                    "raw_status": status,
                    "project_id": row.get("project_id"),
                }
            )
        return external

    def _populate_dependency_tree(
        self,
        tree: QTreeWidget,
        *,
        successor_key: Optional[EntityRef],
        raw_dependencies: Any,
        include_legacy_external: bool = False,
    ):
        from todo_bird_app.services.cpm_scheduling_service import (
            DependencyType,
            format_lag_duration,
        )

        tree.clear()
        tree.setHeaderLabels(
            ["Dependency Task", "Type", "Lag / Lead", "Current Status"]
        )

        if successor_key is None:
            tree.setEnabled(False)
            tree.setToolTip(
                "Save this task once before adding dependencies; a stable database ID is required."
            )
            return []

        candidates = list(
            DependencyAuthoringService.build_candidates(
                self.db_manager,
                project_id=self._current_project_id(),
                successor_key=successor_key,
            )
        )
        candidate_keys = {candidate.key for candidate in candidates}
        candidates_by_id = self._dependency_candidates_by_id(candidates)
        current_specs = parse_authoring_dependency_specs(
            raw_dependencies,
            fallback_entity_type=successor_key.entity_type,
            candidates_by_id=candidates_by_id,
        )
        current_specs_map = {spec.predecessor_key: spec for spec in current_specs}

        display_rows: List[Dict[str, Any]] = [
            {
                "key": candidate.key,
                "title": candidate.title,
                "display_title": candidate.display_title,
                "status": candidate.status,
                "raw_status": candidate.status,
                "project_id": candidate.project_id,
            }
            for candidate in candidates
        ]
        if include_legacy_external:
            display_rows.extend(
                self._legacy_external_dependency_candidates(
                    current_specs,
                    candidate_keys,
                )
            )

        for row_data in display_rows:
            key = row_data["key"]
            active_spec = current_specs_map.get(key)
            active_type = (
                active_spec.dependency_type.value
                if active_spec
                else DependencyType.FS.value
            )
            active_lag = (
                format_lag_duration(active_spec.lag_minutes)
                if active_spec and active_spec.lag_minutes != 0
                else "0m"
            )
            status_display = row_data.get("status") or "Planned"

            dep_item = QTreeWidgetItem(
                [
                    row_data.get("display_title") or row_data.get("title") or str(key),
                    "",
                    "",
                    status_display,
                ]
            )
            dep_item.setFlags(
                dep_item.flags()
                | Qt.ItemIsUserCheckable
                | Qt.ItemIsEnabled
                | Qt.ItemIsSelectable
            )
            dep_item.setCheckState(
                0,
                Qt.Checked if active_spec is not None else Qt.Unchecked,
            )
            dep_item.setData(0, Qt.UserRole, key.entity_id)
            dep_item.setData(0, Qt.UserRole + 2, key.entity_type)
            dep_item.setData(0, Qt.UserRole + 3, str(key))
            dep_item.setData(3, Qt.UserRole, row_data.get("raw_status") or status_display)
            tree.addTopLevelItem(dep_item)

            type_combo = QComboBox(tree)
            type_combo.setObjectName(f"dep_type_combo_{key.entity_type}_{key.entity_id}")
            type_combo.setAccessibleName(f"Dependency Type {key}")
            type_combo.addItem("FS (Finish-to-Start)", "FS")
            type_combo.addItem("SS (Start-to-Start)", "SS")
            type_combo.addItem("FF (Finish-to-Finish)", "FF")
            type_combo.addItem("SF (Start-to-Finish)", "SF")
            type_idx = type_combo.findData(active_type)
            if type_idx >= 0:
                type_combo.setCurrentIndex(type_idx)
            tree.setItemWidget(dep_item, 1, type_combo)

            lag_edit = QLineEdit(active_lag, tree)
            lag_edit.setObjectName(f"dep_lag_edit_{key.entity_type}_{key.entity_id}")
            lag_edit.setAccessibleName(f"Dependency Lag {key}")
            lag_edit.setPlaceholderText("+1d, -2h, 0m")
            tree.setItemWidget(dep_item, 2, lag_edit)

        # Fixed comfortable widths for the widget columns; the task-name
        # column absorbs the rest so the tree never grows a horizontal
        # scrollbar inside the tab.
        header = tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column, width in ((1, 168), (2, 84), (3, 112)):
            header.setSectionResizeMode(column, QHeaderView.Interactive)
            tree.setColumnWidth(column, width)
        for row_index in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(row_index)
            item.setToolTip(0, item.text(0))
            item.setToolTip(3, item.text(3))
        tree.setEnabled(True)
        tree.setToolTip(
            "Check predecessor rows or use Add Dependency. Edit type and lag directly in the table."
        )
        return candidates

    def _wire_dependency_add_controls(
        self,
        layout: QVBoxLayout,
        *,
        tree: QTreeWidget,
        candidates,
        object_prefix: str,
    ):
        from todo_bird_app.services.cpm_scheduling_service import (
            DependencyType,
            parse_lag_duration,
        )

        row = QHBoxLayout()
        row.setSpacing(8)
        predecessor_combo = QComboBox()
        predecessor_combo.setObjectName(f"{object_prefix}_predecessor_combo")
        predecessor_combo.setAccessibleName("Select dependency predecessor")
        predecessor_combo.setToolTip("Choose an open leaf task or subtask in this project.")
        for candidate in candidates:
            predecessor_combo.addItem(candidate.display_title, str(candidate.key))

        type_combo = QComboBox()
        type_combo.setObjectName(f"{object_prefix}_type_combo")
        type_combo.setAccessibleName("Dependency type")
        for label, value in (
            ("FS", "FS"),
            ("SS", "SS"),
            ("FF", "FF"),
            ("SF", "SF"),
        ):
            type_combo.addItem(label, value)

        lag_edit = QLineEdit("0m")
        lag_edit.setObjectName(f"{object_prefix}_lag_edit")
        lag_edit.setAccessibleName("Dependency lag or lead")
        lag_edit.setPlaceholderText("0m, +2h, -1d")
        lag_edit.setFixedWidth(96)

        add_btn = QPushButton("Add")
        add_btn.setObjectName(f"{object_prefix}_add_button")
        add_btn.setToolTip("Add the selected predecessor to the dependency table.")

        remove_btn = QPushButton("Remove")
        remove_btn.setObjectName(f"{object_prefix}_remove_button")
        remove_btn.setToolTip("Uncheck the selected dependency row. Save to persist the change.")

        status_label = QLabel("")
        status_label.setObjectName(f"{object_prefix}_status_label")
        status_label.setWordWrap(True)

        def find_item_for_key(key_text: str):
            for index in range(tree.topLevelItemCount()):
                item = tree.topLevelItem(index)
                if item.data(0, Qt.UserRole + 3) == key_text:
                    return item
            return None

        def add_dependency():
            key_text = predecessor_combo.currentData()
            if not key_text:
                status_label.setText("No eligible predecessor is available.")
                predecessor_combo.setFocus()
                return

            parsed_lag = parse_lag_duration(lag_edit.text())
            if parsed_lag is None:
                status_label.setText("Enter lag/lead as 0m, +2h, -1d, or another supported duration.")
                lag_edit.setFocus()
                return

            item = find_item_for_key(str(key_text))
            if item is None:
                status_label.setText("Dependency candidate is stale. Refresh this task and try again.")
                return
            if item.checkState(0) == Qt.Checked:
                status_label.setText("This dependency is already listed; edit the existing row below.")
                tree.setCurrentItem(item)
                return

            item.setCheckState(0, Qt.Checked)
            item_type_combo = tree.itemWidget(item, 1)
            item_lag_edit = tree.itemWidget(item, 2)
            if isinstance(item_type_combo, QComboBox):
                idx = item_type_combo.findData(type_combo.currentData() or DependencyType.FS.value)
                if idx >= 0:
                    item_type_combo.setCurrentIndex(idx)
            if isinstance(item_lag_edit, QLineEdit):
                item_lag_edit.setText(lag_edit.text().strip() or "0m")
            tree.setCurrentItem(item)
            status_label.setText("Dependency added. Save the task to persist it.")

        def remove_selected():
            item = tree.currentItem()
            if item is None:
                status_label.setText("Select a dependency row to remove.")
                tree.setFocus()
                return
            item.setCheckState(0, Qt.Unchecked)
            status_label.setText("Dependency removed from this edit. Save the task to persist it.")

        add_btn.clicked.connect(add_dependency)
        remove_btn.clicked.connect(remove_selected)

        predecessor_combo.setEnabled(bool(candidates))
        add_btn.setEnabled(bool(candidates))
        if not candidates:
            predecessor_combo.setToolTip(
                "No eligible predecessor is available. Save/create another open leaf task or subtask first."
            )
            add_btn.setToolTip(
                "No eligible predecessor is available. Save/create another open leaf task or subtask first."
            )

        # Two stacked rows keep every control reachable at narrow widths —
        # a single row overflowed into a horizontal scrollbar (default size).
        picker_row = QHBoxLayout()
        picker_row.setSpacing(8)
        picker_label = QLabel("Predecessor")
        picker_row.addWidget(picker_label)
        picker_row.addWidget(predecessor_combo, 1)
        layout.addLayout(picker_row)

        row.addWidget(QLabel("Type"))
        row.addWidget(type_combo)
        row.addWidget(QLabel("Lag / Lead"))
        row.addWidget(lag_edit)
        row.addWidget(add_btn)
        row.addWidget(remove_btn)
        row.addStretch()
        layout.addLayout(row)
        layout.addWidget(status_label)

        if object_prefix == "task_dependency":
            self.dependency_predecessor_combo = predecessor_combo
            self.dependency_type_combo = type_combo
            self.dependency_lag_edit = lag_edit
            self.dependency_add_button = add_btn
            self.dependency_remove_button = remove_btn
            self.dependency_status_label = status_label

        return {
            "predecessor_combo": predecessor_combo,
            "type_combo": type_combo,
            "lag_edit": lag_edit,
            "add_button": add_btn,
            "remove_button": remove_btn,
            "status_label": status_label,
        }

    def _dependency_specs_from_tree(
        self,
        tree: QTreeWidget,
        *,
        successor_key: EntityRef,
    ) -> Tuple[Optional[List[DependencyAuthoringSpec]], List[str], Optional[str], Optional[QWidget]]:
        from todo_bird_app.services.cpm_scheduling_service import (
            DependencyType,
            parse_lag_duration,
        )

        selected: List[DependencyAuthoringSpec] = []
        incomplete: List[str] = []
        seen: set[EntityRef] = set()
        for row in range(tree.topLevelItemCount()):
            dep_item = tree.topLevelItem(row)
            if dep_item.checkState(0) != Qt.Checked:
                continue

            key_text = dep_item.data(0, Qt.UserRole + 3)
            try:
                pred_key = EntityRef.from_string(str(key_text))
            except Exception:
                return None, [], "Dependency row has no stable predecessor identity. Refresh and try again.", tree

            if pred_key in seen:
                return None, [], "This dependency is already listed. Remove the duplicate row before saving.", tree
            seen.add(pred_key)

            type_widget = tree.itemWidget(dep_item, 1)
            lag_widget = tree.itemWidget(dep_item, 2)

            dep_type_str = "FS"
            if isinstance(type_widget, QComboBox):
                dep_type_str = str(type_widget.currentData() or "FS").upper()
            try:
                dep_type = DependencyType(dep_type_str)
            except ValueError:
                dep_type = DependencyType.FS

            lag_minutes = 0
            if isinstance(lag_widget, QLineEdit):
                parsed_lag = parse_lag_duration(lag_widget.text())
                if parsed_lag is None:
                    return (
                        None,
                        [],
                        "Enter lag/lead as 0m, +2h, -1d, or another supported duration.",
                        lag_widget,
                    )
                lag_minutes = parsed_lag

            selected.append(
                DependencyAuthoringSpec(
                    predecessor_key=pred_key,
                    dependency_type=dep_type,
                    lag_minutes=lag_minutes,
                )
            )

            dep_status = dep_item.data(3, Qt.UserRole) or dep_item.text(3)
            if str(dep_status).strip().lower() != TaskStatus.COMPLETED.value.lower():
                incomplete.append(dep_item.text(0))

        return selected, incomplete, None, None

    def _dependency_storage_from_specs(
        self,
        specs: Sequence[DependencyAuthoringSpec],
        *,
        successor_key: EntityRef,
    ) -> List[Dict[str, Any]]:
        force_typed = successor_key.entity_type == "subtask"
        return [
            spec.to_storage_dict(
                typed=force_typed or spec.predecessor_key.entity_type != "task"
            )
            for spec in specs
        ]

    def _schedule_start_datetime(self) -> Optional[datetime]:
        if not hasattr(self, "planned_date_edit") or not hasattr(self, "start_time_edit"):
            return None
        from todo_bird_app.utils.time_math import combine_date_time

        return combine_date_time(
            self.planned_date_edit.date().toString("yyyy-MM-dd"),
            self.start_time_edit.time().toString("HH:mm"),
        )

    def _schedule_finish_datetime(self) -> Optional[datetime]:
        if not hasattr(self, "due_date_edit") or not hasattr(self, "end_time_edit"):
            return None
        from todo_bird_app.utils.time_math import combine_date_time

        return combine_date_time(
            self.due_date_edit.date().toString("yyyy-MM-dd"),
            self.end_time_edit.time().toString("HH:mm"),
        )

    def _finish_from_start_and_duration(
        self,
        start_dt: Optional[datetime],
        duration_minutes: int,
    ) -> Optional[datetime]:
        if start_dt is None:
            return None

        from todo_bird_app.services.schedule_calendar_service import (
            add_working_days_preserve_time,
            add_working_minutes,
        )

        try:
            clean_duration = max(0, int(duration_minutes or 0))
        except (TypeError, ValueError):
            clean_duration = 0

        calendar = self._current_project_calendar_spec()
        if (
            clean_duration > 0
            and clean_duration % self.ESTIMATED_DAY_MINUTES == 0
        ):
            try:
                return add_working_days_preserve_time(
                    start_dt,
                    clean_duration // self.ESTIMATED_DAY_MINUTES,
                    calendar,
                )
            except Exception:
                return start_dt + timedelta(
                    days=(clean_duration // self.ESTIMATED_DAY_MINUTES) - 1
                )

        try:
            return add_working_minutes(
                start_dt,
                clean_duration,
                calendar,
            )
        except Exception:
            return start_dt + timedelta(minutes=clean_duration)

    def _estimated_finish_from_duration(self, duration_minutes: int) -> Optional[datetime]:
        return self._finish_from_start_and_duration(
            self._schedule_start_datetime(),
            duration_minutes,
        )

    def _default_mon_fri_finish_from_duration(
        self,
        duration_minutes: int,
    ) -> Optional[datetime]:
        start_dt = self._schedule_start_datetime()
        if start_dt is None:
            return None

        from todo_bird_app.services.schedule_calendar_service import (
            ScheduleCalendar,
            add_working_days_preserve_time,
            add_working_minutes,
        )

        try:
            clean_duration = max(0, int(duration_minutes or 0))
        except (TypeError, ValueError):
            clean_duration = 0

        default_calendar = ScheduleCalendar()
        if (
            clean_duration > 0
            and clean_duration % self.ESTIMATED_DAY_MINUTES == 0
        ):
            return add_working_days_preserve_time(
                start_dt,
                clean_duration // self.ESTIMATED_DAY_MINUTES,
                default_calendar,
            )
        return add_working_minutes(start_dt, clean_duration, default_calendar)

    def _scheduled_duration_between(
        self,
        start_dt: Optional[datetime],
        finish_dt: Optional[datetime],
    ) -> int:
        if start_dt is None or finish_dt is None:
            return 0

        calendar = self._current_project_calendar_spec()
        if calendar is not None:
            from todo_bird_app.services.schedule_calendar_service import working_minutes_between

            elapsed = max(0, working_minutes_between(start_dt, finish_dt, calendar))
            if (
                finish_dt >= start_dt
                and finish_dt.time() == start_dt.time()
                and calendar.is_working_day(finish_dt)
            ):
                return elapsed + self.ESTIMATED_DAY_MINUTES
            return elapsed

        from todo_bird_app.utils.time_math import duration_between

        elapsed = max(
            0,
            duration_between(
                start_dt.date(),
                start_dt.time(),
                finish_dt.date(),
                finish_dt.time(),
            ),
        )
        if finish_dt >= start_dt and finish_dt.time() == start_dt.time():
            return elapsed + self.ESTIMATED_DAY_MINUTES
        return elapsed

    def _duration_from_schedule_finish(self) -> int:
        return self._scheduled_duration_between(
            self._schedule_start_datetime(),
            self._schedule_finish_datetime(),
        )

    def _set_schedule_finish_widgets_from_datetime(
        self,
        finish_dt: Optional[datetime],
    ) -> None:
        if not hasattr(self, "estimated_finish_label"):
            return
        if finish_dt is None:
            self.estimated_finish_label.setText("Not available")
            return
        self.estimated_finish_label.setText(finish_dt.strftime("%Y-%m-%d %H:%M"))
        if hasattr(self, "due_date_edit") and hasattr(self, "end_time_edit"):
            old_due = self.due_date_edit.blockSignals(True)
            old_end = self.end_time_edit.blockSignals(True)
            self.due_date_edit.setDate(
                QDate(finish_dt.year, finish_dt.month, finish_dt.day)
            )
            self.end_time_edit.setTime(QTime(finish_dt.hour, finish_dt.minute))
            self.due_date_edit.blockSignals(old_due)
            self.end_time_edit.blockSignals(old_end)

    def _sync_work_effort_after_calendar_change(self) -> None:
        editor = getattr(self, "work_effort_editor", None)
        if editor is None:
            return
        try:
            editor.set_project_calendar(
                project_calendar_provider=self._current_project_calendar_spec,
            )
            p_date = self.planned_date_edit.date().toString("yyyy-MM-dd")
            d_date = (
                self.due_date_edit.date().toString("yyyy-MM-dd")
                if self.planned_finish_checkbox.isChecked()
                else p_date
            )
            editor.set_dates(p_date, d_date)
        except Exception:
            pass

    def _refresh_schedule_from_project_calendar(self) -> None:
        if getattr(self, "_cleaned_up", False) or not hasattr(self, "duration_spin"):
            return
        finish_dt = self._estimated_finish_from_duration(self.duration_spin.value())
        self._set_schedule_finish_widgets_from_datetime(finish_dt)
        self._sync_work_effort_after_calendar_change()

    def _on_global_working_calendar_changed(self) -> None:
        self._refresh_schedule_from_project_calendar()

    def cleanup(self):
        if getattr(self, "_cleaned_up", False):
            return
        self._cleaned_up = True
        try:
            from todo_bird_app.controllers.task_controller import _GLOBAL_EVENT_BUS
            if getattr(self, "_global_working_calendar_connected", False):
                try:
                    _GLOBAL_EVENT_BUS.working_calendar_changed.disconnect(
                        self._on_global_working_calendar_changed
                    )
                except Exception:
                    pass
                self._global_working_calendar_connected = False
        except Exception:
            pass
        editor = getattr(self, "work_effort_editor", None)
        if editor is not None and hasattr(editor, "cleanup"):
            try:
                editor.cleanup()
            except Exception:
                pass
        try:
            from todo_bird_app.services.window_registry import WindowRegistry
            WindowRegistry.unregister(self)
        except Exception:
            pass

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def deleteLater(self):
        self.cleanup()
        super().deleteLater()

    def done(self, r):
        self._save_geometry()
        self.cleanup()
        super().done(r)
        super().deleteLater()

    def _restore_geometry(self):
        """Restore dialog geometry from settings."""
        default_size = (760, 800)
        if self.settings_manager:
            w = int(self.settings_manager.get("task_dialog_width", default_size[0]) or default_size[0])
            h = int(self.settings_manager.get("task_dialog_height", default_size[1]) or default_size[1])
            saved_x = self.settings_manager.get("task_dialog_x")
            saved_y = self.settings_manager.get("task_dialog_y")
            if saved_x is not None and saved_y is not None:
                from todo_bird_app.services.window_interaction_service import WindowInteractionService, PlatformCapabilities
                try:
                    target_rect = QRect(int(saved_x), int(saved_y), w, h)
                    clamped_rect = WindowInteractionService.ensure_window_on_screen(target_rect, target_widget=self, min_width=480, min_height=500)
                    if PlatformCapabilities.supports_manual_top_level_positioning():
                        self.setGeometry(clamped_rect)
                    else:
                        self.resize(clamped_rect.width(), clamped_rect.height())
                    return
                except Exception:
                    pass
            self.resize(w, h)
        else:
            self.resize(*default_size)

    def _save_geometry(self):
        """Persist dialog geometry to settings."""
        if self.settings_manager:
            w = self.width()
            h = self.height()
            if self.settings_manager.get("task_dialog_width") != w:
                self.settings_manager.set("task_dialog_width", w)
            if self.settings_manager.get("task_dialog_height") != h:
                self.settings_manager.set("task_dialog_height", h)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # Header Title
        dlg_title = QLabel("Edit Task" if self.task.id else "New Task")
        dlg_title.setStyleSheet("font-weight: 700;")
        TypographyService.set_relative_font_role(dlg_title, delta_pt=6, weight="bold")
        
        header_layout = QHBoxLayout()
        header_layout.addWidget(dlg_title)
        header_layout.addStretch()
        
        reminder_pill = QFrame()
        reminder_pill.setObjectName("TaskDialogReminderPill")
        reminder_pill.setStyleSheet("""
            QFrame#TaskDialogReminderPill {
                background-color: rgba(128, 128, 128, 0.08);
                border: 1px solid rgba(128, 128, 128, 0.20);
                border-radius: 8px;
                padding: 2px 6px;
            }
        """)
        pill_layout = QHBoxLayout(reminder_pill)
        pill_layout.setContentsMargins(4, 2, 4, 2)
        pill_layout.setSpacing(8)

        self.facade_reminder_checkbox = QCheckBox("Reminder")
        self.facade_reminder_checkbox.setToolTip("Show this task on Todo Bird startup.")
        self.facade_reminder_checkbox.setCursor(Qt.PointingHandCursor)
        self.facade_reminder_checkbox.setStyleSheet("""
            QCheckBox { font-weight: 600; }
        """)
        pill_layout.addWidget(self.facade_reminder_checkbox)
        
        self.facade_reminder_combo = QComboBox()
        self.facade_reminder_combo.addItem("First opening of the day", "daily_first_open")
        self.facade_reminder_combo.addItem("Every app opening", "every_app_open")
        self.facade_reminder_combo.setEnabled(False)
        self.facade_reminder_combo.setToolTip("Select when the launch reminder should trigger.")
        self.facade_reminder_combo.setStyleSheet("QComboBox { font-weight: 500; }")
        pill_layout.addWidget(self.facade_reminder_combo)
        
        header_layout.addWidget(reminder_pill)
        main_layout.addLayout(header_layout)


        self.task_dialog_tabs = QTabWidget(self)
        self.task_dialog_tabs.setObjectName("TaskDialogTabs")
        self.task_dialog_tabs.setDocumentMode(True)
        self.task_dialog_tabs.setUsesScrollButtons(True)
        self.task_dialog_tabs.setMovable(False)
        self.task_dialog_tabs.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding,
        )

        def make_tab(title: str, tooltip: str) -> tuple:
            tab_scroll = QScrollArea()
            tab_scroll.setWidgetResizable(True)
            tab_scroll.setFrameShape(QFrame.NoFrame)
            tab_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")

            tab_content = QWidget()
            tab_form = QFormLayout(tab_content)
            tab_form.setContentsMargins(8, 10, 8, 10)
            tab_form.setHorizontalSpacing(14)
            tab_form.setVerticalSpacing(12)
            tab_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
            tab_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

            tab_scroll.setWidget(tab_content)
            tab_index = self.task_dialog_tabs.addTab(tab_scroll, title)
            self.task_dialog_tabs.setTabToolTip(tab_index, tooltip)
            return tab_form, tab_scroll

        basics_form, _basics_scroll = make_tab("Basics", "Task identity, project, priority, notes, and task cover.")
        schedule_form, _schedule_scroll = make_tab("Schedule", "Planned schedule, duration, workload, constraints, and actuals.")
        breakdown_form, _breakdown_scroll = make_tab("Breakdown", "Subtasks and nested work breakdown items.")
        status_form, self._status_tab_scroll = make_tab("Status", "Status, dependencies, progress, reminders, Gantt, and pinned priority.")
        form_layout = basics_form

        # 1. Task Title (hero field — the single most important input)
        self.title_input = QLineEdit(self.task.title)
        self.title_input.setPlaceholderText("What needs to be done?")
        self.title_input.setMinimumHeight(38)
        self.title_input.setToolTip("Give the task a clear, actionable name.")
        TypographyService.set_relative_font_role(
            self.title_input, delta_pt=3, weight="600"
        )
        form_layout.addRow("Task title *", self.title_input)

        # 2. Project Selector
        self.project_combo = QComboBox()
        for proj in self.projects:
            self.project_combo.addItem(proj.name, proj.id)
        if self.task.project_id:
            idx = self.project_combo.findData(self.task.project_id)
            if idx >= 0:
                self.project_combo.setCurrentIndex(idx)
        form_layout.addRow("Project", self.project_combo)

        # 3. Priority & Category
        prio_cat_layout = QHBoxLayout()
        prio_cat_layout.setSpacing(8)
        self.prio_combo = QComboBox()
        from todo_bird_app.widgets.task_item_widget import PRIORITY_COLORS
        for p in TaskPriority:
            self.prio_combo.addItem(
                _dot_icon(PRIORITY_COLORS.get(p, "#9CA3AF")),
                p.value,
                p,
            )
        idx = self.prio_combo.findData(self.task.priority)
        if idx >= 0:
            self.prio_combo.setCurrentIndex(idx)

        self.cat_combo = QComboBox()
        for c in TaskCategory:
            self.cat_combo.addItem(c.value, c)
        idx = self.cat_combo.findData(self.task.category)
        if idx >= 0:
            self.cat_combo.setCurrentIndex(idx)

        prio_cat_layout.addWidget(self.prio_combo)
        prio_cat_layout.addWidget(self.cat_combo)
        form_layout.addRow("Priority and type", prio_cat_layout)

        # 3b. Task Cover / Image (Batch 3.5)
        profile = ExperienceProfileService.get_active_profile(self.settings_manager)
        thumb_size = profile.get("thumbnail_size", 56)
        thumb_vis = profile.get("thumbnail_visible", True)
        
        cover_layout = QHBoxLayout()
        self.cover_preview_label = QLabel()
        self.cover_preview_label.setFixedSize(thumb_size, thumb_size)
        self.cover_preview_label.setAlignment(Qt.AlignCenter)
        self.cover_preview_label.setStyleSheet(
            "QLabel {"
            " border: 1px dashed #94A3B8;"
            " border-radius: 10px;"
            " background: rgba(127,127,127,0.06);"
            " color: #94A3B8;"
            " font-size: 9px;"
            " }"
        )
        self.cover_preview_label.setProperty(
            "todoBirdAllowFixedTextColor", True
        )
        self.current_image_path = getattr(self.task, "image_path", "") or ""

        self.btn_choose_cover = QPushButton("Choose Image")
        self.btn_remove_cover = QPushButton("Remove")

        def update_main_cover_preview():
            from todo_bird_app.services.media_service import MediaService
            if self.current_image_path:
                pm = MediaService.load_pixmap(self.current_image_path, max_width=thumb_size, max_height=thumb_size, use_thumbnail=True)
                if pm and not pm.isNull():
                    self.cover_preview_label.setPixmap(pm)
                    self.btn_remove_cover.setEnabled(True)
                    return
            self.cover_preview_label.setText("No image")
            self.btn_remove_cover.setEnabled(False)

        def on_choose_main_cover():
            from PySide6.QtWidgets import QFileDialog
            from todo_bird_app.services.media_service import MediaService
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select Task Cover Image", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp *.svg)"
            )
            if file_path:
                meta = MediaService.import_media(file_path, category="tasks", db_manager=self.db_manager)
                if meta:
                    self.current_image_path = meta["relative_path"]
                    update_main_cover_preview()

        def on_remove_main_cover():
            self.current_image_path = ""
            update_main_cover_preview()

        self.btn_choose_cover.clicked.connect(on_choose_main_cover)
        self.btn_remove_cover.clicked.connect(on_remove_main_cover)
        cover_layout.addWidget(self.cover_preview_label)
        cover_layout.addWidget(self.btn_choose_cover)
        cover_layout.addWidget(self.btn_remove_cover)
        cover_layout.addStretch()
        
        self.cover_row_widget = QWidget()
        self.cover_row_layout = QHBoxLayout(self.cover_row_widget)
        self.cover_row_layout.setContentsMargins(0,0,0,0)
        self.cover_row_layout.addLayout(cover_layout)
        
        form_layout.addRow("Cover image", self.cover_row_widget)
        
        if not thumb_vis:
            self.cover_row_widget.setVisible(False)
            
        update_main_cover_preview()

        form_layout = schedule_form
        planned_schedule_group = QGroupBox("Planned Schedule")
        planned_schedule_form = QFormLayout(planned_schedule_group)
        planned_schedule_form.setHorizontalSpacing(14)
        planned_schedule_form.setVerticalSpacing(10)
        planned_schedule_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        planned_schedule_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form_layout.addRow(planned_schedule_group)
        form_layout = planned_schedule_form

        # 4. Dates (planned start & optional explicit finish)
        self.planned_date_edit = QDateEdit(self)
        self.planned_date_edit.setCalendarPopup(True)
        self.planned_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.planned_date_edit.setKeyboardTracking(False)
        planned_qdate = (
            QDate.fromString(self.task.planned_date, "yyyy-MM-dd")
            if self.task.planned_date
            else QDate.currentDate()
        )
        if not planned_qdate.isValid():
            planned_qdate = QDate.currentDate()
        self.planned_date_edit.setDate(planned_qdate)

        self.due_date_edit = QDateEdit(self)
        self.due_date_edit.setCalendarPopup(True)
        self.due_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.due_date_edit.setKeyboardTracking(False)
        due_qdate = (
            QDate.fromString(self.task.due_date, "yyyy-MM-dd")
            if self.task.due_date
            else planned_qdate
        )
        if not due_qdate.isValid():
            due_qdate = planned_qdate
        self.due_date_edit.setDate(due_qdate)

        self.planned_finish_checkbox = QCheckBox("Save target finish")
        self.planned_finish_checkbox.setChecked(
            bool(self.task.due_date or self.task.planned_end_time)
        )

        # 5. Planned Times & Duration
        self.start_time_edit = QTimeEdit(self)
        self.start_time_edit.setDisplayFormat("HH:mm")
        if self.task.planned_start_time:
            self.start_time_edit.setTime(QTime.fromString(self.task.planned_start_time, "HH:mm"))

        self.end_time_edit = QTimeEdit(self)
        self.end_time_edit.setDisplayFormat("HH:mm")
        if self.task.planned_end_time:
            self.end_time_edit.setTime(QTime.fromString(self.task.planned_end_time, "HH:mm"))

        self.duration_spin = QSpinBox(self)
        self.duration_spin.setRange(0, 1000000)
        self.duration_spin.setSuffix(" mins")
        self.duration_spin.setValue(int(self.task.estimated_duration or 0))

        self.duration_days_spin = QDoubleSpinBox(self)
        self.duration_days_spin.setObjectName("EstimatedDurationDaysSpin")
        self.duration_days_spin.setRange(0.0, 10000.0)
        self.duration_days_spin.setDecimals(2)
        self.duration_days_spin.setSingleStep(0.5)
        self.duration_days_spin.setSuffix(" days")
        self.duration_days_spin.setValue(
            self._duration_days_from_minutes(self.duration_spin.value())
        )
        self.duration_days_spin.setToolTip(
            "Estimated working days. Updating this fills the target finish from the project calendar."
        )

        self.estimated_finish_label = QLabel("")
        self.estimated_finish_label.setObjectName("EstimatedFinishLabel")
        self.estimated_finish_label.setStyleSheet(
            "color: palette(highlight); font-weight: 700;"
        )
        self.estimated_finish_label.setMinimumWidth(160)

        start_layout = QHBoxLayout()
        start_layout.setSpacing(8)
        start_layout.addWidget(self.planned_date_edit)
        start_layout.addWidget(self.start_time_edit)
        start_layout.addStretch()
        form_layout.addRow("Start", start_layout)

        duration_layout = QHBoxLayout()
        duration_layout.setSpacing(8)
        duration_layout.addWidget(self.duration_days_spin)
        duration_layout.addWidget(self.duration_spin)
        duration_layout.addStretch()
        form_layout.addRow("Estimated duration", duration_layout)

        target_layout = QHBoxLayout()
        target_layout.setSpacing(8)
        target_layout.addWidget(self.estimated_finish_label)
        target_layout.addStretch()
        form_layout.addRow("Calculated target", target_layout)

        finish_layout = QHBoxLayout()
        finish_layout.setSpacing(8)
        finish_layout.addWidget(self.planned_finish_checkbox)
        finish_layout.addWidget(self.due_date_edit)
        finish_layout.addWidget(self.end_time_edit)
        finish_layout.addStretch()
        form_layout.addRow("Target finish", finish_layout)

        def sync_days_from_minutes(minutes: int):
            old = self.duration_days_spin.blockSignals(True)
            self.duration_days_spin.setValue(
                self._duration_days_from_minutes(minutes)
            )
            self.duration_days_spin.blockSignals(old)

        def set_duration_minutes_silently(minutes: int):
            old = self.duration_spin.blockSignals(True)
            self.duration_spin.setValue(max(0, int(minutes or 0)))
            self.duration_spin.blockSignals(old)
            sync_days_from_minutes(self.duration_spin.value())

        def set_target_label_from_datetime(finish_dt: Optional[datetime]):
            if finish_dt is None:
                self.estimated_finish_label.setText("Not available")
            else:
                self.estimated_finish_label.setText(
                    finish_dt.strftime("%Y-%m-%d %H:%M")
                )

        def refresh_work_effort_dates():
            if not hasattr(self, "work_effort_editor"):
                return
            p_date = self.planned_date_edit.date().toString("yyyy-MM-dd")
            d_date = (
                self.due_date_edit.date().toString("yyyy-MM-dd")
                if self.planned_finish_checkbox.isChecked()
                else p_date
            )
            self.work_effort_editor.set_dates(p_date, d_date)

        def set_finish_widgets_from_estimate(activate_finish: bool = False):
            finish_dt = self._estimated_finish_from_duration(
                self.duration_spin.value()
            )
            if finish_dt is None:
                set_target_label_from_datetime(None)
                return

            set_target_label_from_datetime(finish_dt)
            old_due = self.due_date_edit.blockSignals(True)
            old_end = self.end_time_edit.blockSignals(True)
            self.due_date_edit.setDate(
                QDate(finish_dt.year, finish_dt.month, finish_dt.day)
            )
            self.end_time_edit.setTime(QTime(finish_dt.hour, finish_dt.minute))
            self.due_date_edit.blockSignals(old_due)
            self.end_time_edit.blockSignals(old_end)

            if activate_finish and not self.planned_finish_checkbox.isChecked():
                old_finish = self.planned_finish_checkbox.blockSignals(True)
                self.planned_finish_checkbox.setChecked(True)
                self.planned_finish_checkbox.blockSignals(old_finish)
                set_planned_finish_enabled(True, recalculate=False)
            refresh_work_effort_dates()

        def update_main_duration():
            from todo_bird_app.utils.time_math import format_duration_display
            if not self.planned_finish_checkbox.isChecked():
                sync_days_from_minutes(self.duration_spin.value())
                set_finish_widgets_from_estimate(False)
                disp = format_duration_display(self.duration_spin.value())
                self.duration_spin.setToolTip(
                    f"Estimated duration: {self.duration_spin.value()} mins ({disp})"
                )
                refresh_work_effort_dates()
                return

            dur = self._duration_from_schedule_finish()
            set_duration_minutes_silently(dur)
            disp = format_duration_display(dur)
            self.duration_spin.setToolTip(
                f"Automatically calculated: {dur} mins ({disp})"
            )
            set_target_label_from_datetime(self._schedule_finish_datetime())
            refresh_work_effort_dates()

        def set_planned_finish_enabled(checked: bool, recalculate: bool = True):
            self.due_date_edit.setEnabled(checked)
            self.end_time_edit.setEnabled(checked)
            self.duration_spin.setReadOnly(False)
            self.duration_days_spin.setReadOnly(False)
            self.duration_spin.setButtonSymbols(QSpinBox.UpDownArrows)
            self.duration_days_spin.setButtonSymbols(QDoubleSpinBox.UpDownArrows)
            if checked:
                self.duration_spin.setToolTip(
                    "Estimated duration. Changing it recalculates the target finish."
                )
                if recalculate:
                    update_main_duration()
            else:
                update_main_duration()

        def schedule_anchor_changed():
            set_finish_widgets_from_estimate(False)
            refresh_work_effort_dates()

        def on_duration_minutes_changed(value: int):
            if self._syncing_duration_controls:
                return
            self._syncing_duration_controls = True
            try:
                sync_days_from_minutes(value)
                set_finish_widgets_from_estimate(True)
            finally:
                self._syncing_duration_controls = False

        def on_duration_days_changed(value: float):
            if self._syncing_duration_controls:
                return
            self._syncing_duration_controls = True
            try:
                minutes = self._duration_minutes_from_days(value)
                old = self.duration_spin.blockSignals(True)
                self.duration_spin.setValue(minutes)
                self.duration_spin.blockSignals(old)
                set_finish_widgets_from_estimate(True)
            finally:
                self._syncing_duration_controls = False

        self.planned_date_edit.dateChanged.connect(
            lambda _date: schedule_anchor_changed()
        )
        self.due_date_edit.dateChanged.connect(
            lambda _date: update_main_duration()
        )
        self.start_time_edit.timeChanged.connect(
            lambda _time: schedule_anchor_changed()
        )
        self.end_time_edit.timeChanged.connect(
            lambda _time: update_main_duration()
        )
        self.duration_spin.valueChanged.connect(
            on_duration_minutes_changed
        )
        self.duration_days_spin.valueChanged.connect(
            on_duration_days_changed
        )
        self.project_combo.currentIndexChanged.connect(
            lambda _idx: schedule_anchor_changed()
        )
        self.planned_finish_checkbox.toggled.connect(
            lambda checked: set_planned_finish_enabled(
                checked,
                recalculate=False,
            )
        )

        # Recalculate existing scheduled tasks so stored duration stays correct.
        should_recalculate_from_finish = bool(
            self.task.planned_start_time
            and self.task.planned_end_time
            and not int(self.task.estimated_duration or 0)
        )
        if should_recalculate_from_finish:
            update_main_duration()
        elif self.planned_finish_checkbox.isChecked():
            sync_days_from_minutes(self.duration_spin.value())
            calendar_finish = self._estimated_finish_from_duration(
                self.duration_spin.value()
            )
            stored_finish = self._schedule_finish_datetime()
            default_finish = self._default_mon_fri_finish_from_duration(
                self.duration_spin.value()
            )
            if (
                int(self.duration_spin.value() or 0) > 0
                and calendar_finish is not None
                and stored_finish != calendar_finish
                and stored_finish == default_finish
            ):
                set_finish_widgets_from_estimate(False)
            else:
                set_target_label_from_datetime(stored_finish)
        else:
            sync_days_from_minutes(self.duration_spin.value())
            set_finish_widgets_from_estimate(False)
        set_planned_finish_enabled(
            self.planned_finish_checkbox.isChecked(),
            recalculate=False,
        )

        # 5b. Schedule Baseline 1 (Frozen Snapshot)
        schedule_rules_group = QGroupBox("Rules and Deadlines")
        schedule_rules_form = QFormLayout(schedule_rules_group)
        schedule_rules_form.setHorizontalSpacing(14)
        schedule_rules_form.setVerticalSpacing(10)
        schedule_rules_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        schedule_rules_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        schedule_form.addRow(schedule_rules_group)
        form_layout = schedule_rules_form

        baseline_row_widget = QWidget()
        baseline_layout = QHBoxLayout(baseline_row_widget)
        baseline_layout.setContentsMargins(0, 0, 0, 0)
        b_start = getattr(self.task, "baseline_start", None)
        b_finish = getattr(self.task, "baseline_finish", None)
        b_dur = getattr(self.task, "baseline_duration_minutes", None)

        if b_start and b_finish:
            from todo_bird_app.services.schedule_variance_service import parse_datetime_flexible
            bs_dt = parse_datetime_flexible(b_start)
            bf_dt = parse_datetime_flexible(b_finish)
            bs_str = bs_dt.strftime("%Y-%m-%d %H:%M") if bs_dt else str(b_start)
            bf_str = bf_dt.strftime("%Y-%m-%d %H:%M") if bf_dt else str(b_finish)
            dur_str = f"{b_dur}m" if b_dur is not None else ""
            b_lbl = QLabel(f"{bs_str} → {bf_str} ({dur_str})" if dur_str else f"{bs_str} → {bf_str}")
            b_lbl.setStyleSheet("color: palette(mid); font-weight: 500;")
            baseline_layout.addWidget(b_lbl)
        else:
            b_lbl = QLabel("Not Baselined")
            b_lbl.setStyleSheet("color: palette(mid); font-style: italic;")
            baseline_layout.addWidget(b_lbl)

        form_layout.addRow("Baseline 1", baseline_row_widget)
        # Read-only provenance info: hide the row entirely until a baseline
        # exists (label included — QFormLayout keeps labels for hidden fields).
        baseline_row_widget.setVisible(bool(b_start and b_finish))
        baseline_row_label = form_layout.labelForField(baseline_row_widget)
        if baseline_row_label is not None:
            baseline_row_label.setVisible(bool(b_start and b_finish))

        # 5c. Schedule Constraints & Deadlines (Phase 2E)
        constraint_vbox = QVBoxLayout()
        constraint_vbox.setSpacing(6)

        c_row1 = QHBoxLayout()
        self.constraint_type_combo = QComboBox(self)
        for ct in ConstraintType:
            self.constraint_type_combo.addItem(f"{ct.value} — {get_constraint_display_name(ct)}", ct.value)
        self.constraint_type_combo.setMinimumWidth(190)
        self.constraint_type_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents
        )

        current_ctype = getattr(self.task, "constraint_type", "ASAP") or "ASAP"
        idx = self.constraint_type_combo.findData(current_ctype)
        if idx >= 0:
            self.constraint_type_combo.setCurrentIndex(idx)

        self.constraint_date_edit = QDateEdit(self)
        self.constraint_date_edit.setCalendarPopup(True)
        self.constraint_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.constraint_time_edit = QTimeEdit(self)
        self.constraint_time_edit.setDisplayFormat("HH:mm")

        c_dt_str = getattr(self.task, "constraint_datetime", None)
        c_dt_parsed = parse_constraint_datetime(c_dt_str)
        if c_dt_parsed:
            self.constraint_date_edit.setDate(QDate(c_dt_parsed.year, c_dt_parsed.month, c_dt_parsed.day))
            self.constraint_time_edit.setTime(QTime(c_dt_parsed.hour, c_dt_parsed.minute))
        else:
            self.constraint_date_edit.setDate(QDate.currentDate())
            self.constraint_time_edit.setTime(QTime(9, 0))

        c_row1.addWidget(self.constraint_type_combo, 1)
        constraint_vbox.addLayout(c_row1)

        c_row2 = QHBoxLayout()
        c_row2.addWidget(QLabel("Date / time"), 0)
        c_row2.addWidget(self.constraint_date_edit, 1)
        c_row2.addWidget(self.constraint_time_edit)
        constraint_vbox.addLayout(c_row2)

        def update_constraint_fields_state():
            chosen_ct = self.constraint_type_combo.currentData() or "ASAP"
            req = is_date_required(chosen_ct)
            self.constraint_date_edit.setEnabled(req)
            self.constraint_time_edit.setEnabled(req)
            self.constraint_type_combo.setToolTip(get_constraint_tooltip(chosen_ct))

        self.constraint_type_combo.currentIndexChanged.connect(lambda _: update_constraint_fields_state())
        update_constraint_fields_state()

        d_row = QHBoxLayout()
        self.deadline_check = QCheckBox("Target Deadline:")
        self.deadline_check.setToolTip("Optional analytical commitment deadline. Does not move CPM schedule or alter logic.")
        self.deadline_date_edit = QDateEdit(self)
        self.deadline_date_edit.setCalendarPopup(True)
        self.deadline_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.deadline_time_edit = QTimeEdit(self)
        self.deadline_time_edit.setDisplayFormat("HH:mm")

        d_dt_str = getattr(self.task, "deadline_datetime", None)
        d_dt_parsed = parse_constraint_datetime(d_dt_str)
        if d_dt_parsed:
            self.deadline_check.setChecked(True)
            self.deadline_date_edit.setDate(QDate(d_dt_parsed.year, d_dt_parsed.month, d_dt_parsed.day))
            self.deadline_time_edit.setTime(QTime(d_dt_parsed.hour, d_dt_parsed.minute))
        else:
            self.deadline_check.setChecked(False)
            self.deadline_date_edit.setDate(QDate.currentDate())
            self.deadline_time_edit.setTime(QTime(17, 0))

        def update_deadline_fields_state(checked):
            self.deadline_date_edit.setEnabled(checked)
            self.deadline_time_edit.setEnabled(checked)

        self.deadline_check.toggled.connect(update_deadline_fields_state)
        update_deadline_fields_state(self.deadline_check.isChecked())

        d_row.addWidget(self.deadline_check)
        d_row.addStretch()
        constraint_vbox.addLayout(d_row)

        d_row2 = QHBoxLayout()
        d_row2.addWidget(self.deadline_date_edit, 1)
        d_row2.addWidget(self.deadline_time_edit)
        constraint_vbox.addLayout(d_row2)

        form_layout.addRow("Scheduling rules", constraint_vbox)

        # 5d. Actual Execution Time
        actual_group = QGroupBox("Actual Tracking")
        actual_form = QFormLayout(actual_group)
        actual_form.setHorizontalSpacing(14)
        actual_form.setVerticalSpacing(10)
        actual_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        actual_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        schedule_form.addRow(actual_group)
        form_layout = actual_form

        actual_container = QWidget()
        actual_main_vbox = QVBoxLayout(actual_container)
        actual_main_vbox.setContentsMargins(0, 0, 0, 0)
        actual_main_vbox.setSpacing(6)

        # Row 1: Track Actual Execution Toggle
        self.actual_enabled_check = QCheckBox("Track Actual Execution")
        self.actual_enabled_check.setToolTip("Enable to track actual work execution start date and time")
        actual_main_vbox.addWidget(self.actual_enabled_check)

        # Row 2: Actual Start Date & Time
        actual_start_layout = QHBoxLayout()
        actual_start_layout.setSpacing(8)
        self.actual_start_label = QLabel("Actual Start:")
        self.actual_start_label.setMinimumWidth(85)
        self.actual_start_date_edit = QDateEdit(self)
        self.actual_start_date_edit.setCalendarPopup(True)
        self.actual_start_date_edit.setDisplayFormat("yyyy-MM-dd")
        act_start_str = getattr(self.task, "actual_start_date", None) or self.task.planned_date
        if act_start_str:
            try:
                ad = datetime.strptime(act_start_str, "%Y-%m-%d").date()
                self.actual_start_date_edit.setDate(QDate(ad.year, ad.month, ad.day))
            except Exception:
                self.actual_start_date_edit.setDate(QDate.currentDate())
        else:
            self.actual_start_date_edit.setDate(QDate.currentDate())

        self.actual_start_edit = QTimeEdit(self)
        self.actual_start_edit.setDisplayFormat("HH:mm")
        if self.task.actual_start_time:
            try:
                ash, asm = map(int, str(self.task.actual_start_time).split(":")[:2])
                self.actual_start_edit.setTime(QTime(ash, asm))
            except Exception:
                self.actual_start_edit.setTime(QTime(8, 0))
        else:
            self.actual_start_edit.setTime(QTime(8, 0))

        actual_start_layout.addWidget(self.actual_start_label)
        actual_start_layout.addWidget(self.actual_start_date_edit)
        actual_start_layout.addWidget(self.actual_start_edit)
        actual_start_layout.addStretch()
        actual_main_vbox.addLayout(actual_start_layout)

        # Row 3: Finished & Actual Finish Date & Time
        actual_finish_layout = QHBoxLayout()
        actual_finish_layout.setSpacing(8)
        self.actual_finish_check = QCheckBox("Finished")
        self.actual_finish_check.setToolTip("Check if task execution is complete and set actual finish date & time")

        self.actual_not_finished_label = QLabel("[ Not finished ]")
        self.actual_not_finished_label.setStyleSheet("color: palette(mid); font-style: italic; font-weight: 500;")

        self.actual_end_date_edit = QDateEdit(self)
        self.actual_end_date_edit.setCalendarPopup(True)
        self.actual_end_date_edit.setDisplayFormat("yyyy-MM-dd")
        act_end_str = getattr(self.task, "actual_end_date", None)
        if act_end_str:
            try:
                ed = datetime.strptime(act_end_str, "%Y-%m-%d").date()
                self.actual_end_date_edit.setDate(QDate(ed.year, ed.month, ed.day))
            except Exception:
                self.actual_end_date_edit.setDate(QDate.currentDate())
        else:
            self.actual_end_date_edit.setDate(QDate.currentDate())

        self.actual_end_edit = QTimeEdit(self)
        self.actual_end_edit.setDisplayFormat("HH:mm")
        if self.task.actual_end_time:
            try:
                aeh, aem = map(int, str(self.task.actual_end_time).split(":")[:2])
                self.actual_end_edit.setTime(QTime(aeh, aem))
            except Exception:
                self.actual_end_edit.setTime(QTime(9, 0))
        else:
            self.actual_end_edit.setTime(QTime(9, 0))

        actual_finish_layout.addWidget(self.actual_finish_check)
        actual_finish_layout.addWidget(self.actual_not_finished_label)
        actual_finish_layout.addWidget(self.actual_end_date_edit)
        actual_finish_layout.addWidget(self.actual_end_edit)
        actual_finish_layout.addStretch()
        actual_main_vbox.addLayout(actual_finish_layout)

        # Row 4: Metrics (Actual Work Effort & Actual Elapsed Span) — two
        # compact rows so the block never forces a horizontal scrollbar.
        actual_metrics_layout = QHBoxLayout()
        actual_metrics_layout.setSpacing(10)

        actual_metrics_layout.addWidget(QLabel("Actual Work Effort:"))
        self.actual_duration_spin = QSpinBox(self)
        self.actual_duration_spin.setRange(0, 100000)
        self.actual_duration_spin.setSuffix(" mins")
        self.actual_duration_spin.setValue(int(self.task.actual_duration or 0))
        self.actual_duration_label = QLabel("0h 00m (0 mins)")
        self.actual_duration_label.setStyleSheet("color: #10B981; font-weight: 700; font-size: 11px;")
        actual_metrics_layout.addWidget(self.actual_duration_spin)
        actual_metrics_layout.addWidget(self.actual_duration_label)
        actual_metrics_layout.addStretch()
        actual_main_vbox.addLayout(actual_metrics_layout)

        actual_elapsed_layout = QHBoxLayout()
        actual_elapsed_layout.setSpacing(10)
        actual_elapsed_layout.addWidget(QLabel("Actual Elapsed:"))
        self.actual_elapsed_label = QLabel("0h 00m (0 mins)")
        self.actual_elapsed_label.setStyleSheet("color: #10B981; font-weight: 600; font-size: 11px;")
        actual_elapsed_layout.addWidget(self.actual_elapsed_label)
        actual_elapsed_layout.addStretch()
        actual_main_vbox.addLayout(actual_elapsed_layout)

        # Row 5: Execution Performance Variance
        actual_perf_layout = QHBoxLayout()
        actual_perf_layout.setSpacing(10)
        actual_perf_layout.addWidget(QLabel("Execution Performance:"))
        self.actual_perf_label = QLabel("Not tracked")
        self.actual_perf_label.setStyleSheet("color: #38BDF8; font-weight: 600; font-size: 11px;")
        actual_perf_layout.addWidget(self.actual_perf_label)
        actual_perf_layout.addStretch()
        actual_main_vbox.addLayout(actual_perf_layout)

        has_actual_start = bool(getattr(self.task, "actual_start_date", None) or (self.task.actual_start_time and self.task.actual_start_time != "00:00"))
        has_actual_finish = bool((getattr(self.task, "actual_end_date", None) or (getattr(self.task, "actual_end_time", None) and self.task.status == TaskStatus.COMPLETED)) and has_actual_start)

        def update_actual_effort_display(val):
            from todo_bird_app.utils.time_math import format_duration_display
            disp = format_duration_display(val)
            self.actual_duration_spin.setToolTip(f"Actual Work Effort: {val} mins ({disp})")
            if hasattr(self, "actual_duration_label"):
                self.actual_duration_label.setText(f"{disp} ({val} mins)")

        self.actual_duration_spin.valueChanged.connect(update_actual_effort_display)
        update_actual_effort_display(self.actual_duration_spin.value())

        def update_actual_span():
            from todo_bird_app.utils.time_math import calculate_actual_elapsed_minutes, format_duration_display, get_current_datetime
            from todo_bird_app.services.execution_performance_service import ExecutionPerformanceService
            if not self.actual_enabled_check.isChecked():
                if hasattr(self, "actual_elapsed_label"):
                    self.actual_elapsed_label.setText("0h 00m (0 mins)")
                    self.actual_elapsed_label.setToolTip("Actual Execution is not tracked.")
                if hasattr(self, "actual_perf_label"):
                    self.actual_perf_label.setText("Not tracked")
                return

            sd = self.actual_start_date_edit.date().toString("yyyy-MM-dd")
            st = self.actual_start_edit.time().toString("HH:mm")
            ed = self.actual_end_date_edit.date().toString("yyyy-MM-dd")
            et = self.actual_end_edit.time().toString("HH:mm")

            cur_task_payload = {
                "planned_date": self.planned_date_edit.date().toString("yyyy-MM-dd"),
                "planned_start_time": self.planned_time_edit.time().toString("HH:mm") if hasattr(self, "planned_time_edit") else "08:00",
                "due_date": self.due_date_edit.date().toString("yyyy-MM-dd"),
                "actual_start_date": sd if self.actual_enabled_check.isChecked() else None,
                "actual_start_time": st if self.actual_enabled_check.isChecked() else None,
                "actual_end_date": ed if self.actual_enabled_check.isChecked() and self.actual_finish_check.isChecked() else None,
                "actual_end_time": et if self.actual_enabled_check.isChecked() and self.actual_finish_check.isChecked() else None,
                "actual_duration": self.actual_duration_spin.value(),
                "status": "Completed" if self.actual_finish_check.isChecked() else "In Progress",
            }
            res = ExecutionPerformanceService.analyze_task_execution(cur_task_payload)

            if not self.actual_finish_check.isChecked():
                now = get_current_datetime()
                now_d = now.strftime("%Y-%m-%d")
                now_t = now.strftime("%H:%M")
                dur = calculate_actual_elapsed_minutes(sd, st, now_d, now_t)
                disp = format_duration_display(dur)
                if hasattr(self, "actual_elapsed_label"):
                    self.actual_elapsed_label.setText(f"{disp} — In Progress")
                    self.actual_elapsed_label.setToolTip(f"Actual Execution is currently open. Live calendar elapsed: {disp} ({dur} mins)")
                if hasattr(self, "actual_perf_label"):
                    self.actual_perf_label.setText(f"{res.start_variance_display} (Start)")
                    self.actual_perf_label.setToolTip(f"Execution Start Performance vs Planned Start: {res.start_variance_display}")
                return

            dur = calculate_actual_elapsed_minutes(sd, st, ed, et)
            disp = format_duration_display(dur)
            if hasattr(self, "actual_elapsed_label"):
                self.actual_elapsed_label.setText(f"{disp} ({dur} mins)")
                self.actual_elapsed_label.setToolTip(f"Actual Elapsed Span (Full calendar time): {dur} mins ({disp})")
            if hasattr(self, "actual_perf_label"):
                self.actual_perf_label.setText(f"{res.finish_variance_display} (Finish)")
                self.actual_perf_label.setToolTip(f"Execution Finish Performance vs Planned Due: {res.finish_variance_display}")

        def update_actual_widgets_state(enabled):
            self.actual_start_date_edit.setEnabled(enabled)
            self.actual_start_edit.setEnabled(enabled)
            self.actual_finish_check.setEnabled(enabled)

            is_finished = enabled and self.actual_finish_check.isChecked()
            self.actual_not_finished_label.setVisible(not is_finished)
            if not enabled:
                self.actual_not_finished_label.setText("[ Not tracked ]")
            else:
                self.actual_not_finished_label.setText("[ Not finished ]")

            self.actual_end_date_edit.setVisible(is_finished)
            self.actual_end_edit.setVisible(is_finished)
            self.actual_end_date_edit.setEnabled(is_finished)
            self.actual_end_edit.setEnabled(is_finished)

            # Actual effort is always editable independently
            self.actual_duration_spin.setEnabled(True)
            update_actual_span()

        def _on_actual_finish_edited():
            if not self.actual_finish_check.isChecked() and self.actual_enabled_check.isChecked():
                self.actual_finish_check.setChecked(True)
            update_actual_span()

        self.actual_start_date_edit.dateChanged.connect(lambda _d: update_actual_span())
        self.actual_start_edit.timeChanged.connect(lambda _t: update_actual_span())
        self.actual_end_date_edit.dateChanged.connect(lambda _d: _on_actual_finish_edited())
        self.actual_end_edit.timeChanged.connect(lambda _t: _on_actual_finish_edited())
        self.actual_enabled_check.toggled.connect(update_actual_widgets_state)
        self.actual_finish_check.toggled.connect(update_actual_widgets_state)

        self.actual_enabled_check.setChecked(has_actual_start)
        self.actual_finish_check.setChecked(has_actual_finish)
        update_actual_widgets_state(has_actual_start)

        form_layout.addRow("Actuals", actual_container)

        # 5c. Work Effort & Daily Dedication (Unified WorkEffortEditor - Batch 3.4 & 3.8)
        workload_group = QGroupBox("Workload Planning")
        workload_form = QFormLayout(workload_group)
        workload_form.setHorizontalSpacing(14)
        workload_form.setVerticalSpacing(10)
        workload_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        workload_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        schedule_form.addRow(workload_group)
        form_layout = workload_form

        def current_effort_date_bounds():
            p_date = self.planned_date_edit.date().toString("yyyy-MM-dd")
            d_date = (
                self.due_date_edit.date().toString("yyyy-MM-dd")
                if self.planned_finish_checkbox.isChecked()
                else p_date
            )
            return p_date, d_date

        p_date_str, d_date_str = current_effort_date_bounds()
        cur_mode = getattr(self.task, "allocation_mode", "fixed_daily") or "fixed_daily"
        init_dedication = int(getattr(self.task, "daily_dedication_minutes", 0) or 0)
        init_effort = int(getattr(self.task, "planned_effort_minutes", 0) or 0)

        self._custom_allocations_dict = {}
        self._custom_actual_allocations_dict = {}
        if self.task.id is not None and self.db_manager is not None:
            try:
                allocs = self.db_manager.get_task_allocations(task_id=self.task.id)
                self._custom_allocations_dict = {
                    a["allocation_date"]: int(a.get("planned_minutes", 0) or 0)
                    for a in allocs
                }
                self._custom_actual_allocations_dict = {
                    a["allocation_date"]: int(a.get("actual_minutes", 0) or 0)
                    for a in allocs
                }
            except Exception:
                self._custom_allocations_dict = {}
                self._custom_actual_allocations_dict = {}

        self.work_effort_editor = WorkEffortEditor(
            start_date=p_date_str,
            due_date=d_date_str,
            allocation_mode=cur_mode,
            daily_dedication_minutes=init_dedication,
            planned_effort_minutes=init_effort,
            custom_allocations=self._custom_allocations_dict,
            custom_actual_allocations=self._custom_actual_allocations_dict,
            settings_manager=self.settings_manager,
            project_calendar_provider=self._current_project_calendar_spec,
        )

        self.work_effort_editor.actualEffortChanged.connect(
            lambda val: self.actual_duration_spin.setValue(val)
        )

        # Direct property proxies for backwards-compatibility
        self.allocation_mode_combo = self.work_effort_editor.allocation_mode_combo
        self.daily_hours_spin = self.work_effort_editor.daily_hours_spin
        self.daily_mins_spin = self.work_effort_editor.daily_mins_spin
        self.planned_effort_spin = self.work_effort_editor.planned_effort_spin
        self.effort_summary_label = self.work_effort_editor.effort_summary_label
        self.custom_alloc_frame = self.work_effort_editor.custom_alloc_frame
        self.custom_spinners = self.work_effort_editor.custom_spinners

        def mark_work_effort_touched(*_args):
            self._work_effort_user_touched = True

        self.allocation_mode_combo.currentIndexChanged.connect(
            mark_work_effort_touched
        )
        self.daily_hours_spin.valueChanged.connect(mark_work_effort_touched)
        self.daily_mins_spin.valueChanged.connect(mark_work_effort_touched)
        self.planned_effort_spin.valueChanged.connect(mark_work_effort_touched)

        self.planned_date_edit.dateChanged.connect(
            lambda _d: self.work_effort_editor.set_dates(*current_effort_date_bounds())
        )
        self.due_date_edit.dateChanged.connect(
            lambda _d: self.work_effort_editor.set_dates(*current_effort_date_bounds())
        )
        self.planned_finish_checkbox.toggled.connect(
            lambda _checked: self.work_effort_editor.set_dates(*current_effort_date_bounds())
        )

        form_layout.addRow("Workload", self.work_effort_editor)

        # 6. Description
        form_layout = basics_form
        self.desc_input = RichTextEditor(settings_manager=self.settings_manager)
        self.desc_input.setPlaceholderText("Detailed task description...")
        self.desc_input.setHtml(self.task.description)
        form_layout.addRow("Notes", self.desc_input)

        # 7. Hierarchical Subtasks
        form_layout = breakdown_form
        subtasks_group = QGroupBox("Task Breakdown")
        subtasks_layout = QVBoxLayout(subtasks_group)
        subtasks_layout.setSpacing(8)

        self.subtask_tree = QTreeWidget()
        self.subtask_tree.setObjectName("TaskBreakdownTree")
        self.subtask_tree.setHeaderLabels(["Subtask", "Date", "Time", "Gantt", "Remove"])
        self.subtask_tree.setMinimumHeight(180)
        self.subtask_tree.setAlternatingRowColors(True)
        self.subtask_tree.setUniformRowHeights(True)
        self.subtask_tree.setAnimated(True)
        self.subtask_tree.setWordWrap(False)
        self.subtask_tree.setRootIsDecorated(True)

        subtask_header = self.subtask_tree.header()
        subtask_header.setStretchLastSection(False)
        subtask_header.setSectionResizeMode(0, QHeaderView.Stretch)
        subtask_header.setSectionResizeMode(1, QHeaderView.Interactive)
        subtask_header.setSectionResizeMode(2, QHeaderView.Interactive)
        subtask_header.setSectionResizeMode(3, QHeaderView.Interactive)
        subtask_header.setSectionResizeMode(4, QHeaderView.Interactive)
        self.subtask_tree.setColumnWidth(1, 96)
        self.subtask_tree.setColumnWidth(2, 100)
        self.subtask_tree.setColumnWidth(3, 62)
        self.subtask_tree.setColumnWidth(4, 70)
        subtask_header_item = self.subtask_tree.headerItem()
        subtask_header_item.setToolTip(0, "Name. Check = done; double-click (or F2) to rename in place.")
        subtask_header_item.setToolTip(1, "Planned date — edit via Edit Details.")
        subtask_header_item.setToolTip(2, "Planned start–end time.")
        subtask_header_item.setToolTip(3, "Show this subtask on the Gantt timeline.")
        subtask_header_item.setToolTip(4, "Check rows to delete, then press Remove Checked (or Del).")

        self._subtask_empty_label = QLabel(
            "No subtasks yet.\nType a step below and press Enter to add it — "
            "select a row and use Add Child to nest deeper."
        )
        self._subtask_empty_label.setAlignment(Qt.AlignCenter)
        self._subtask_empty_label.setWordWrap(True)
        self._subtask_empty_label.setProperty("secondary", True)
        self._subtask_empty_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._subtask_empty_label.setStyleSheet("QLabel { color: palette(mid); font-style: italic; }")

        def _update_subtask_empty_state():
            empty = self.subtask_tree.topLevelItemCount() == 0
            self._subtask_empty_label.setVisible(empty)

        self._update_subtask_empty_state = _update_subtask_empty_state
        self._subtask_empty_label.setParent(self.subtask_tree.viewport())
        self._subtask_empty_label.setGeometry(
            12, 34,
            max(120, self.subtask_tree.viewport().width() - 24),
            56,
        )
        self.subtask_tree.viewport().installEventFilter(self)

        def add_existing(parent_item, subtask):
            item = QTreeWidgetItem([subtask.get("title", "")])
            item.setFlags(
                item.flags()
                | Qt.ItemIsUserCheckable
                | Qt.ItemIsEditable
                | Qt.ItemIsSelectable
                | Qt.ItemIsEnabled
            )
            item.setCheckState(
                0,
                Qt.Checked if subtask.get("is_completed") else Qt.Unchecked
            )

            if bool(subtask.get("is_pinned", 0)):
                item.setText(
                    0,
                    "⚑ " + item.text(0).removeprefix("⚑ "),
                )
            item.setText(1, subtask.get("planned_date") or "—")

            start_time = subtask.get("planned_start_time") or ""
            end_time = subtask.get("planned_end_time") or ""
            time_text = (
                f"{start_time}–{end_time}"
                if start_time or end_time
                else "—"
            )
            item.setText(2, time_text)

            item.setCheckState(
                3,
                Qt.Checked if subtask.get("show_in_gantt") else Qt.Unchecked
            )
            item.setCheckState(4, Qt.Unchecked)
            item.setData(0, Qt.UserRole, subtask.get("id"))
            item.setData(
                0,
                Qt.UserRole + 1,
                {
                    "description": subtask.get("description", ""),
                    "planned_date": subtask.get("planned_date"),
                    "due_date": subtask.get("due_date"),
                    "planned_start_time": subtask.get("planned_start_time"),
                    "planned_end_time": subtask.get("planned_end_time"),
                    "estimated_duration": int(subtask.get("estimated_duration") or 0),
                    "priority": subtask.get("priority") or "Medium",
                    "progress": int(subtask.get("progress") or 0),
                    "status": _coerce_task_status(
                        subtask.get("status"),
                        (
                            TaskStatus.COMPLETED
                            if subtask.get("is_completed") or int(subtask.get("progress") or 0) >= 100
                            else TaskStatus.PLANNED
                        ),
                    ).value,
                    "delay_category": subtask.get("delay_category", "") or "",
                    "delay_reason": subtask.get("delay_reason", "") or "",
                    "delay_notes": subtask.get("delay_notes", "") or "",
                    "delay_recorded_at": subtask.get("delay_recorded_at"),
                    "dependencies": raw_dependency_list(
                        subtask.get("dependencies")
                    ),

                    # Migration v8 nested pin metadata
                    "is_pinned": bool(
                        subtask.get("is_pinned", 0)
                    ),
                    "pin_color": (
                        subtask.get("pin_color")
                        or "#E95420"
                    ),
                    "pin_position": int(
                        subtask.get("pin_position") or 0
                    ),

                    # Migration v9 actual execution parity
                    "actual_start_date": subtask.get("actual_start_date"),
                    "actual_end_date": subtask.get("actual_end_date"),
                    "actual_start_time": subtask.get("actual_start_time"),
                    "actual_end_time": subtask.get("actual_end_time"),
                    "actual_duration": int(subtask.get("actual_duration") or 0),

                    # Migration v10 planned effort parity & Batch 3.4 custom allocations
                    "planned_effort_minutes": int(subtask.get("planned_effort_minutes") or 0),
                    "daily_dedication_minutes": int(subtask.get("daily_dedication_minutes") or 0),
                    "allocation_mode": subtask.get("allocation_mode", "fixed_daily") or "fixed_daily",
                    "custom_allocations": dict(subtask.get("custom_allocations") or {}),
                }
            )

            if parent_item is None:
                self.subtask_tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)

            for child in subtask.get("children", []):
                add_existing(item, child)

            item.setExpanded(True)

        for subtask in self.subtasks_data:
            add_existing(None, subtask)

        self.subtask_tree.expandAll()
        self.subtask_tree.itemDoubleClicked.connect(
            lambda _item, _col: self.edit_selected_subtask_details()
        )
        _update_subtask_empty_state()

        subtasks_layout.addWidget(self.subtask_tree)

        subtask_add_row = QHBoxLayout()
        subtask_add_row.setSpacing(6)

        self.subtask_input = QLineEdit()
        self.subtask_input.setPlaceholderText("Add a subtask… (Enter to add)")
        self.subtask_input.returnPressed.connect(self.add_subtask_item)
        # Swallow physical Enter so it cannot also trigger the dialog's
        # default Save button; the line edit's returnPressed still covers
        # programmatic emissions.
        self.subtask_input.installEventFilter(self)

        add_subtask_btn = QPushButton("Add")
        add_subtask_btn.setObjectName("TaskBreakdownAddButton")
        add_subtask_btn.setToolTip("Add the typed text as a top-level subtask (Enter).")
        add_subtask_btn.clicked.connect(self.add_subtask_item)

        add_child_btn = QPushButton("Add Nested")
        add_child_btn.setToolTip(
            "Add a sub-subtask below the currently selected row (Ctrl+Enter)."
        )
        add_child_btn.clicked.connect(self.add_child_subtask_item)

        edit_subtask_btn = QPushButton("Edit Details")
        edit_subtask_btn.setToolTip(
            "Edit schedule, description, priority and progress for the selected hierarchy item (double-click a row)."
        )
        edit_subtask_btn.clicked.connect(self.edit_selected_subtask_details)

        remove_subtask_btn = QPushButton("Remove Checked")
        remove_subtask_btn.setToolTip(
            "Remove only rows checked in the Remove column. "
            "Changes are committed only when Save Task is pressed."
        )
        remove_subtask_btn.clicked.connect(self.remove_selected_subtask)

        subtask_add_row.addWidget(self.subtask_input, 1)
        subtask_add_row.addWidget(add_subtask_btn)
        subtask_add_row.addWidget(add_child_btn)
        subtask_add_row.addWidget(edit_subtask_btn)
        subtask_add_row.addWidget(remove_subtask_btn)

        subtasks_layout.addLayout(subtask_add_row)
        form_layout.addRow(subtasks_group)
        self._subtask_add_child_btn = add_child_btn

        # Keyboard-first breakdown editing:
        #   Enter   — add typed subtask (event filter on the input)
        #   Ctrl+Enter — nest under the selected row (event filter)
        #   Delete  — remove rows checked in the Remove column
        subtask_delete_shortcut = QShortcut(QKeySequence(Qt.Key_Delete), self.subtask_tree)
        subtask_delete_shortcut.setContext(Qt.WidgetShortcut)
        subtask_delete_shortcut.activated.connect(self.remove_selected_subtask)
        subtask_edit_shortcut = QShortcut(QKeySequence(Qt.Key_F2), self.subtask_tree)
        subtask_edit_shortcut.setContext(Qt.WidgetShortcut)
        subtask_edit_shortcut.activated.connect(self.edit_selected_subtask_details)

        # 8. Program Management / Execution Workflow
        form_layout = status_form
        workflow_group = QGroupBox("Status and Dependencies")
        workflow_layout = QVBoxLayout(workflow_group)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)

        self.status_combo = QComboBox(self)
        self.status_combo.setObjectName("task_status_combo")
        self.status_combo.setAccessibleName("Task status")
        self.status_combo.setFocusPolicy(Qt.StrongFocus)

        from todo_bird_app.widgets.task_item_widget import STATUS_COLORS
        self._status_dot_colors = dict(STATUS_COLORS)
        self._status_dot_colors.setdefault(TaskStatus.BLOCKED, "#EF4444")

        for label, status in WORKFLOW_STATUS_OPTIONS:
            self.status_combo.addItem(
                _dot_icon(self._status_dot_colors.get(status, "#9CA3AF")),
                label,
                status,
            )
        self.status_combo.view().setObjectName("task_status_combo_popup_view")

        status_index = self.status_combo.findData(self.task.status)
        if status_index >= 0:
            self.status_combo.setCurrentIndex(status_index)

        self.task_done_checkbox = QCheckBox("Task done")
        self.task_done_checkbox.setChecked(
            self.task.status == TaskStatus.COMPLETED
        )
        self.task_done_checkbox.setToolTip(
            "Marks this task completed and sets progress to 100%."
        )

        status_row.addWidget(QLabel("Status:"))
        status_row.addWidget(self.status_combo, 1)
        status_row.addWidget(self.task_done_checkbox)
        workflow_layout.addLayout(status_row)

        # Dependency selector
        dependency_label = QLabel(
            "Dependencies — tasks that must be completed before this task can finish"
        )
        dependency_label.setProperty("secondary", True)
        dependency_label.setWordWrap(True)
        workflow_layout.addWidget(dependency_label)

        self.dependency_tree = QTreeWidget()
        self.dependency_tree.setHeaderLabels(
            ["Dependency Task", "Type", "Lag / Lead", "Current Status"]
        )
        self.dependency_tree.setMinimumHeight(150)
        self.dependency_tree.setAlternatingRowColors(True)

        task_successor_key = self._dependency_successor_key()
        dependency_candidates = self._populate_dependency_tree(
            self.dependency_tree,
            successor_key=task_successor_key,
            raw_dependencies=self.task.dependencies,
            include_legacy_external=True,
        )
        self._wire_dependency_add_controls(
            workflow_layout,
            tree=self.dependency_tree,
            candidates=dependency_candidates,
            object_prefix="task_dependency",
        )
        workflow_layout.addWidget(self.dependency_tree)

        # Blocker management — hidden entirely unless the status demands it
        # (previously always visible but disabled, eating Status-tab space).
        blocker_group = QGroupBox("Blocker / Delay Management")
        blocker_form = QFormLayout(blocker_group)

        self.blocker_category_combo = QComboBox(blocker_group)
        self.blocker_category_combo.setObjectName("blocker_category_combo")
        self.blocker_category_combo.setAccessibleName("Blocker or delay category")
        self.blocker_category_combo.setFocusPolicy(Qt.StrongFocus)
        self.blocker_category_combo.addItems(BLOCKER_CATEGORY_OPTIONS)
        self.blocker_category_combo.view().setObjectName("blocker_category_combo_popup_view")

        existing_category = (self.task.delay_category or "None").strip()
        if existing_category.lower() in {"", "none", "null"}:
            existing_category = "None"
        idx = self.blocker_category_combo.findText(
            existing_category,
            Qt.MatchFixedString,
        )
        if idx < 0 and existing_category:
            self.blocker_category_combo.addItem(existing_category)
            idx = self.blocker_category_combo.findText(
                existing_category,
                Qt.MatchFixedString,
            )
        if idx >= 0:
            self.blocker_category_combo.setCurrentIndex(idx)

        self.blocker_reason_input = QLineEdit(
            self.task.delay_reason or ""
        )
        self.blocker_reason_input.setObjectName("blocker_reason_input")
        self.blocker_reason_input.setAccessibleName("Blocker or delay reason")
        self.blocker_reason_input.setPlaceholderText(
            "What is stopping or delaying this task?"
        )

        self.blocker_notes_input = RichTextEditor(settings_manager=self.settings_manager)
        self.blocker_notes_input.setObjectName("blocker_notes_input")
        self.blocker_notes_input.setAccessibleName("Blocker recovery notes")
        self.blocker_notes_input.setHtml(
            self.task.delay_notes or ""
        )
        self.blocker_notes_input.setPlaceholderText(
            "Owner, action required, expected resolution, decision needed..."
        )

        blocker_form.addRow(
            "Category",
            self.blocker_category_combo
        )
        blocker_form.addRow(
            "Reason",
            self.blocker_reason_input
        )
        blocker_form.addRow(
            "Recovery / Notes",
            self.blocker_notes_input
        )

        workflow_layout.addWidget(blocker_group)
        self.blocker_group = blocker_group

        self.workflow_hint = QLabel()
        self.workflow_hint.setWordWrap(True)
        self.workflow_hint.setStyleSheet(
            "font-size: 11px; opacity: 0.85;"
        )
        workflow_layout.addWidget(self.workflow_hint)

        def update_workflow_ui():
            status = self.status_combo.currentData()

            is_completed = status == TaskStatus.COMPLETED
            is_blocked_or_delayed = status in (
                TaskStatus.BLOCKED,
                TaskStatus.DELAYED,
            )

            self.task_done_checkbox.blockSignals(True)
            self.task_done_checkbox.setChecked(is_completed)
            self.task_done_checkbox.blockSignals(False)

            if hasattr(self, "blocker_group"):
                self.blocker_group.setVisible(is_blocked_or_delayed)
            self.blocker_category_combo.setEnabled(
                is_blocked_or_delayed
            )
            self.blocker_reason_input.setEnabled(
                is_blocked_or_delayed
            )
            self.blocker_notes_input.setEnabled(
                is_blocked_or_delayed
            )
            if is_blocked_or_delayed:
                category_tip = (
                    "Choose what is blocking or delaying this task before saving."
                )
                reason_tip = (
                    "Record the concrete reason and immediate recovery action."
                )
                notes_tip = (
                    "Optional owner, decision, impact, and recovery details."
                )
            else:
                category_tip = (
                    "Available only when Status is Blocked or Delayed."
                )
                reason_tip = (
                    "Available only when Status is Blocked or Delayed."
                )
                notes_tip = (
                    "Available only when Status is Blocked or Delayed."
                )
            self.blocker_category_combo.setToolTip(category_tip)
            self.blocker_reason_input.setToolTip(reason_tip)
            self.blocker_notes_input.setToolTip(notes_tip)

            if status == TaskStatus.INBOX:
                hint = (
                    "○ Not Started: work has not begun. "
                    "Only the planned schedule should appear in Gantt."
                )
            elif status == TaskStatus.PLANNED:
                hint = (
                    "Planned: task is scheduled but execution "
                    "has not started."
                )
            elif status == TaskStatus.IN_PROGRESS:
                hint = (
                    "▶ In Progress: progress represents real execution. "
                    "Gantt will show Planned + Actual progress."
                )
            elif status == TaskStatus.BLOCKED:
                hint = (
                    "Blocked: identify exactly what prevents progress. "
                    "A blocker reason will be required when saving."
                )
            elif status == TaskStatus.DELAYED:
                hint = (
                    "Delayed: work can continue, but it is behind "
                    "plan. Record the reason and recovery action."
                )
            elif status == TaskStatus.COMPLETED:
                hint = (
                    "Completed: Todo Bird will enforce 100% "
                    "progress when this task is saved."
                )
            elif status == TaskStatus.CANCELLED:
                hint = (
                    "Cancelled: task is intentionally stopped."
                )
            else:
                hint = (
                    "↪ Moved: task has been rescheduled or shifted."
                )

            self.workflow_hint.setText(hint)

            # If the status requires blocker/delay data, navigate to the Status
            # tab and scroll to the Blocker section so the user can see and
            # interact with it immediately (fixes the live "do not respond" S1
            # failure where the section was below the visible scroll viewport).
            if is_blocked_or_delayed:
                try:
                    # Switch to the Status tab (index 3 — Basics/Schedule/Breakdown/Status).
                    status_tab_index = 3
                    if self.task_dialog_tabs.currentIndex() != status_tab_index:
                        self.task_dialog_tabs.setCurrentIndex(status_tab_index)
                except Exception:
                    pass
                try:
                    scroll = getattr(self, "_status_tab_scroll", None)
                    if scroll is not None:
                        # Scroll the Status tab QScrollArea to show the blocker group.
                        scroll.ensureWidgetVisible(self.blocker_category_combo, 0, 20)
                except Exception:
                    pass

        def task_done_changed(checked):
            if checked:
                idx = self.status_combo.findData(
                    TaskStatus.COMPLETED
                )
                if idx >= 0:
                    self.status_combo.setCurrentIndex(idx)
            elif self.status_combo.currentData() == TaskStatus.COMPLETED:
                idx = self.status_combo.findData(
                    TaskStatus.IN_PROGRESS
                    if self.task.progress > 0
                    else TaskStatus.PLANNED
                )
                if idx >= 0:
                    self.status_combo.setCurrentIndex(idx)

        self._status_blocker_delay_handler_count = 0
        self._status_blocker_delay_signal_log = []

        def status_runtime_changed(*_args):
            self._status_blocker_delay_handler_count += 1
            self._status_blocker_delay_signal_log.append(
                (
                    self.status_combo.currentIndex(),
                    self.status_combo.currentText(),
                    self.status_combo.currentData(),
                )
            )
            update_workflow_ui()

        self._update_status_blocker_delay_ui = update_workflow_ui
        self._on_status_blocker_delay_runtime_changed = status_runtime_changed
        self.status_combo.currentIndexChanged.connect(status_runtime_changed)
        self.status_combo.currentTextChanged.connect(status_runtime_changed)
        self.status_combo.activated.connect(status_runtime_changed)
        self.task_done_checkbox.toggled.connect(
            task_done_changed
        )

        update_workflow_ui()

        form_layout.addRow(workflow_group)

        # 8. Progress — precise numeric entry + synchronized slider
        details_group = QGroupBox("Details and Tracking")
        details_form = QFormLayout(details_group)
        details_form.setHorizontalSpacing(14)
        details_form.setVerticalSpacing(10)
        details_form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        details_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form_layout = details_form

        progress_layout = QHBoxLayout()

        self.progress_slider = QSlider(Qt.Horizontal, self)
        self.progress_slider.setRange(0, 100)
        self.progress_slider.setValue(int(self.task.progress or 0))

        self.progress_spin = QSpinBox(self)
        self.progress_spin.setRange(0, 100)
        self.progress_spin.setSuffix("%")
        self.progress_spin.setValue(int(self.task.progress or 0))
        self.progress_spin.setMinimumWidth(90)
        self.progress_spin.setToolTip(
            "Enter exact task progress from 0% to 100%."
        )

        self.progress_slider.valueChanged.connect(
            self.progress_spin.setValue
        )
        self.progress_spin.valueChanged.connect(
            self.progress_slider.setValue
        )

        progress_layout.addWidget(self.progress_slider, 1)
        progress_layout.addWidget(self.progress_spin)

        form_layout.addRow("Progress", progress_layout)

        # 8. Tags & Recurring
        self.tags_input = QLineEdit(", ".join(self.task.tags))
        self.tags_input.setPlaceholderText("e.g. urgent, backend, design")
        form_layout.addRow("Tags", self.tags_input)

        self.recurring_combo = QComboBox(self)
        self.recurring_combo.addItems(["None", "Daily", "Weekly", "Monthly"])
        if self.task.recurring:
            idx = self.recurring_combo.findText(self.task.recurring.capitalize())
            if idx >= 0:
                self.recurring_combo.setCurrentIndex(idx)
        form_layout.addRow("Recurring", self.recurring_combo)

        self.show_in_gantt_checkbox = QCheckBox("Show this task in Gantt")
        self.show_in_gantt_checkbox.setChecked(bool(self.task.show_in_gantt))
        self.show_in_gantt_checkbox.setToolTip(
            "Enable only for tasks that should appear on the Gantt timeline."
        )
        form_layout.addRow("Gantt", self.show_in_gantt_checkbox)

        self.startup_reminder_combo = QComboBox()
        self.startup_reminder_combo.addItem("Off", "off")
        self.startup_reminder_combo.addItem("First opening of the day", "daily_first_open")
        self.startup_reminder_combo.addItem("Every app opening", "every_app_open")

        current_mode = getattr(self.task, "startup_reminder_mode", None)
        if not current_mode:
            current_mode = "daily_first_open" if getattr(self.task, "startup_reminder", False) else "off"

        idx = self.startup_reminder_combo.findData(current_mode)
        if idx >= 0:
            self.startup_reminder_combo.setCurrentIndex(idx)
        else:
            self.startup_reminder_combo.setCurrentIndex(0)

        self.startup_reminder_combo.setToolTip(
            "Off: Only normal scheduled reminders are shown.\n"
            "First opening of the day: Show this reminder on the first Todo Bird launch each day.\n"
            "Every app opening: Show this reminder whenever Todo Bird is newly opened.\n"
            "Saving a launch reminder enables the Todo Bird startup reminder policy."
        )
        form_layout.addRow("Launch reminder", self.startup_reminder_combo)

        # Synchronize facade checkbox with combo box
        self.facade_reminder_checkbox.setChecked(current_mode != "off")
        if current_mode != "off":
            self.facade_reminder_combo.setEnabled(True)
            idx = self.facade_reminder_combo.findData(current_mode)
            if idx >= 0:
                self.facade_reminder_combo.setCurrentIndex(idx)
        
        def _on_facade_toggled(checked):
            self.facade_reminder_combo.setEnabled(checked)
            if checked:
                facade_mode = self.facade_reminder_combo.currentData()
                idx = self.startup_reminder_combo.findData(facade_mode)
                if idx >= 0:
                    self.startup_reminder_combo.setCurrentIndex(idx)
            else:
                idx = self.startup_reminder_combo.findData("off")
                if idx >= 0:
                    self.startup_reminder_combo.setCurrentIndex(idx)
                    
        def _on_facade_combo_changed(idx):
            if self.facade_reminder_checkbox.isChecked():
                facade_mode = self.facade_reminder_combo.itemData(idx)
                inner_idx = self.startup_reminder_combo.findData(facade_mode)
                if inner_idx >= 0:
                    self.startup_reminder_combo.setCurrentIndex(inner_idx)
                    
        def _on_combo_changed(idx):
            mode = self.startup_reminder_combo.itemData(idx)
            self.facade_reminder_checkbox.blockSignals(True)
            self.facade_reminder_combo.blockSignals(True)
            
            self.facade_reminder_checkbox.setChecked(mode != "off")
            self.facade_reminder_combo.setEnabled(mode != "off")
            
            if mode != "off":
                f_idx = self.facade_reminder_combo.findData(mode)
                if f_idx >= 0:
                    self.facade_reminder_combo.setCurrentIndex(f_idx)
                    
            self.facade_reminder_combo.blockSignals(False)
            self.facade_reminder_checkbox.blockSignals(False)
            
        self.facade_reminder_checkbox.toggled.connect(_on_facade_toggled)
        self.facade_reminder_combo.currentIndexChanged.connect(_on_facade_combo_changed)
        self.startup_reminder_combo.currentIndexChanged.connect(_on_combo_changed)

        # Persistent colored pinning
        pin_row = QHBoxLayout()
        pin_row.setSpacing(8)

        self.pin_checkbox = QCheckBox("Pin this task")
        self.pin_checkbox.setChecked(bool(getattr(self.task, "is_pinned", False)))
        self.pin_checkbox.setToolTip(
            "Keep this task pinned for fast visual priority access."
        )

        self.pin_color_combo = QComboBox()
        self.pin_color_combo.setObjectName("pin_color_combo")
        self.pin_color_combo.setAccessibleName("Task pin color")
        self.pin_color_combo.setToolTip(
            "Choose the pin color after enabling Pin this task."
        )
        pin_colors = [
            ("Orange", "#E95420"),
            ("Blue", "#3584E4"),
            ("Purple", "#8B5CF6"),
            ("Green", "#10B981"),
            ("Amber", "#F59E0B"),
            ("Red", "#DC2626"),
            ("Graphite", "#374151"),
        ]

        for label, color in pin_colors:
            self.pin_color_combo.addItem(_dot_icon(color, 12), label, color)

        current_pin_color = getattr(self.task, "pin_color", "#E95420") or "#E95420"
        pin_index = self.pin_color_combo.findData(current_pin_color)
        if pin_index >= 0:
            self.pin_color_combo.setCurrentIndex(pin_index)

        self.pin_color_combo.setEnabled(self.pin_checkbox.isChecked())
        self.pin_checkbox.toggled.connect(self.pin_color_combo.setEnabled)

        pin_row.addWidget(self.pin_checkbox)
        pin_row.addWidget(QLabel("Color:"))
        pin_row.addWidget(self.pin_color_combo)
        pin_row.addStretch()

        form_layout.addRow("Pinned priority", pin_row)

        # Everything above lives inside the Details and Tracking card.
        status_form.addRow(details_group)

        if has_actual_start:
            self.task_dialog_tabs.setCurrentIndex(1)

        main_layout.addWidget(self.task_dialog_tabs, 1)

        # Buttons Row
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)

        save_btn = QPushButton("Save Task")
        save_btn.setObjectName("PrimaryButton")
        save_btn.setDefault(True)
        save_btn.setToolTip("Save this task and close (Ctrl+S or Ctrl+Return).")
        save_btn.clicked.connect(self.on_save)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)

        main_layout.addLayout(btn_layout)

        # Power-user shortcuts: save, and Ctrl+1..4 to jump between tabs.
        save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        save_shortcut.setContext(Qt.WindowShortcut)
        save_shortcut.activated.connect(self.on_save)
        save_enter_shortcut = QShortcut(QKeySequence("Ctrl+Return"), self)
        save_enter_shortcut.setContext(Qt.WindowShortcut)
        save_enter_shortcut.activated.connect(self.on_save)
        for tab_idx in range(self.task_dialog_tabs.count()):
            tab_shortcut = QShortcut(
                QKeySequence(f"Ctrl+{tab_idx + 1}"), self
            )
            tab_shortcut.setContext(Qt.WindowShortcut)
            tab_shortcut.activated.connect(
                lambda _checked=False, idx=tab_idx: self.task_dialog_tabs.setCurrentIndex(idx)
            )

    def eventFilter(self, watched, event):
        if watched is self.subtask_tree.viewport() and event.type() == event.Type.Resize:
            self._subtask_empty_label.setGeometry(
                12, 34,
                max(120, self.subtask_tree.viewport().width() - 24),
                56,
            )
        elif (
            watched is getattr(self, "subtask_input", None)
            and event.type() == event.Type.ShortcutOverride
            and event.key() in (Qt.Key_Return, Qt.Key_Enter)
        ):
            # Claim Enter/Ctrl+Enter while typing in the subtask box so the
            # dialog-level Ctrl+Return save shortcut does not steal them.
            event.accept()
            return True
        elif (
            watched is getattr(self, "subtask_input", None)
            and event.type() == event.Type.KeyPress
            and event.key() in (Qt.Key_Return, Qt.Key_Enter)
        ):
            if event.modifiers() & Qt.ControlModifier:
                self.add_child_subtask_item()
            else:
                self.add_subtask_item()
            return True
        return super().eventFilter(watched, event)

    def _new_subtask_tree_item(self, title: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([title])
        item.setFlags(
            item.flags()
            | Qt.ItemIsUserCheckable
            | Qt.ItemIsEditable
            | Qt.ItemIsSelectable
            | Qt.ItemIsEnabled
        )
        item.setCheckState(0, Qt.Unchecked)

        item.setText(
            1,
            self.task.planned_date or "—"
        )

        start_time = self.task.planned_start_time or ""
        end_time = self.task.planned_end_time or ""
        item.setText(
            2,
            f"{start_time}–{end_time}" if start_time or end_time else "—"
        )

        item.setCheckState(3, Qt.Unchecked)
        item.setCheckState(4, Qt.Unchecked)
        item.setData(0, Qt.UserRole, None)

        item.setData(
            0,
            Qt.UserRole + 1,
            {
                "description": "",
                "planned_date": self.task.planned_date,
                "due_date": self.task.due_date,
                "planned_start_time": self.task.planned_start_time,
                "planned_end_time": self.task.planned_end_time,
                "estimated_duration": int(self.task.estimated_duration or 0),
                "priority": (
                    self.task.priority.value
                    if hasattr(self.task.priority, "value")
                    else str(self.task.priority)
                ),
                "progress": 0,
                "status": TaskStatus.PLANNED.value,
                "delay_category": "",
                "delay_reason": "",
                "delay_notes": "",
                "delay_recorded_at": None,
                "dependencies": [],

                # Migration v8 nested pin defaults
                "is_pinned": False,
                "pin_color": "#E95420",
                "pin_position": 0,
            }
        )

        return item

    def add_subtask_item(self):
        title = self.subtask_input.text().strip()
        if not title:
            self.subtask_input.setFocus()
            return

        item = self._new_subtask_tree_item(title)
        self.subtask_tree.addTopLevelItem(item)
        self.subtask_tree.setCurrentItem(item)
        self.subtask_input.clear()
        self.subtask_input.setFocus()
        self._update_subtask_empty_state()

    def add_child_subtask_item(self):
        title = self.subtask_input.text().strip()
        parent_item = self.subtask_tree.currentItem()
        if not title or parent_item is None:
            if not title:
                self.subtask_input.setFocus()
            else:
                self._subtask_add_child_btn.setToolTip(
                    "Select a row in the tree first, then click to nest the typed text under it."
                )
                self.subtask_input.setFocus()
            return

        item = self._new_subtask_tree_item(title)
        parent_item.addChild(item)
        parent_item.setExpanded(True)
        self.subtask_tree.setCurrentItem(item)
        self.subtask_input.clear()
        self.subtask_input.setFocus()
        self._update_subtask_empty_state()

    def edit_selected_subtask_details(self):
        item = self.subtask_tree.currentItem()
        if item is None:
            return

        metadata = item.data(0, Qt.UserRole + 1) or {}
        sub_id = item.data(0, Qt.UserRole)

        dlg = QDialog(self)
        dlg.setWindowTitle("Edit Subtask Details")
        dlg.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint)
        dlg.setMinimumSize(460, 480)
        dlg.resize(720, 740)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)

        main_vbox = QVBoxLayout(dlg)
        main_vbox.setContentsMargins(14, 14, 14, 14)
        main_vbox.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll_content = QWidget()

        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        title_edit = QLineEdit(item.text(0))
        form.addRow("Name", title_edit)

        description_edit = RichTextEditor(settings_manager=self.settings_manager)
        description_edit.setHtml(
            metadata.get("description", "")
        )
        form.addRow("Description", description_edit)

        planned_date_edit = QDateEdit()
        planned_date_edit.setCalendarPopup(True)
        planned_date_edit.setDisplayFormat("yyyy-MM-dd")
        planned_value = metadata.get("planned_date")
        planned_qdate = (
            QDate.fromString(planned_value, "yyyy-MM-dd")
            if planned_value
            else QDate.currentDate()
        )
        if not planned_qdate.isValid():
            planned_qdate = QDate.currentDate()
        planned_date_edit.setDate(planned_qdate)
        form.addRow("Planned date", planned_date_edit)

        sub_finish_checkbox = QCheckBox("Planned finish")
        sub_finish_checkbox.setChecked(
            bool(metadata.get("due_date") or metadata.get("planned_end_time"))
        )

        due_date_edit = QDateEdit()
        due_date_edit.setCalendarPopup(True)
        due_date_edit.setDisplayFormat("yyyy-MM-dd")
        due_value = metadata.get("due_date")
        due_qdate = (
            QDate.fromString(due_value, "yyyy-MM-dd")
            if due_value
            else planned_qdate
        )
        if not due_qdate.isValid():
            due_qdate = planned_qdate
        due_date_edit.setDate(due_qdate)

        sub_finish_row = QHBoxLayout()
        sub_finish_row.addWidget(sub_finish_checkbox)
        sub_finish_row.addWidget(due_date_edit)
        form.addRow("Finish date", sub_finish_row)

        start_time_edit = QTimeEdit()
        start_time_edit.setDisplayFormat("HH:mm")
        start_value = metadata.get("planned_start_time")
        if start_value:
            start_time_edit.setTime(
                QTime.fromString(start_value, "HH:mm")
            )
        form.addRow("Start time", start_time_edit)

        end_time_edit = QTimeEdit()
        end_time_edit.setDisplayFormat("HH:mm")
        end_value = metadata.get("planned_end_time")
        if end_value:
            end_time_edit.setTime(
                QTime.fromString(end_value, "HH:mm")
            )
        form.addRow("End time", end_time_edit)

        duration_spin = QSpinBox()
        duration_spin.setRange(0, 1000000)
        duration_spin.setSuffix(" mins")
        duration_spin.setValue(
            int(metadata.get("estimated_duration") or 0)
        )

        duration_days_spin = QDoubleSpinBox()
        duration_days_spin.setObjectName("SubtaskEstimatedDurationDaysSpin")
        duration_days_spin.setRange(0.0, 10000.0)
        duration_days_spin.setDecimals(2)
        duration_days_spin.setSingleStep(0.5)
        duration_days_spin.setSuffix(" days")
        duration_days_spin.setValue(
            self._duration_days_from_minutes(duration_spin.value())
        )

        syncing_sub_duration = [False]

        def nested_start_dt():
            from todo_bird_app.utils.time_math import combine_date_time

            return combine_date_time(
                planned_date_edit.date().toString("yyyy-MM-dd"),
                start_time_edit.time().toString("HH:mm"),
            )

        def nested_finish_dt():
            from todo_bird_app.utils.time_math import combine_date_time

            return combine_date_time(
                due_date_edit.date().toString("yyyy-MM-dd"),
                end_time_edit.time().toString("HH:mm"),
            )

        def sync_nested_days_from_minutes(minutes: int):
            old = duration_days_spin.blockSignals(True)
            duration_days_spin.setValue(
                self._duration_days_from_minutes(minutes)
            )
            duration_days_spin.blockSignals(old)

        def set_nested_duration_minutes_silently(minutes: int):
            old = duration_spin.blockSignals(True)
            duration_spin.setValue(max(0, int(minutes or 0)))
            duration_spin.blockSignals(old)
            sync_nested_days_from_minutes(duration_spin.value())

        def set_nested_finish_from_duration():
            finish_dt = self._finish_from_start_and_duration(
                nested_start_dt(),
                duration_spin.value(),
            )
            if finish_dt is None:
                return
            old_due = due_date_edit.blockSignals(True)
            old_end = end_time_edit.blockSignals(True)
            due_date_edit.setDate(
                QDate(finish_dt.year, finish_dt.month, finish_dt.day)
            )
            end_time_edit.setTime(QTime(finish_dt.hour, finish_dt.minute))
            due_date_edit.blockSignals(old_due)
            end_time_edit.blockSignals(old_end)

        def update_nested_duration():
            from todo_bird_app.utils.time_math import format_duration_display
            if not sub_finish_checkbox.isChecked():
                sync_nested_days_from_minutes(duration_spin.value())
                disp = format_duration_display(duration_spin.value())
                duration_spin.setToolTip(
                    f"Estimated duration: {duration_spin.value()} mins ({disp})"
                )
                return

            dur = self._scheduled_duration_between(
                nested_start_dt(),
                nested_finish_dt(),
            )
            set_nested_duration_minutes_silently(dur)
            disp = format_duration_display(dur)
            duration_spin.setToolTip(
                f"Automatically calculated: {dur} mins ({disp})"
            )

        def set_sub_finish_enabled(checked: bool, recalculate: bool = True):
            due_date_edit.setEnabled(checked)
            end_time_edit.setEnabled(checked)
            duration_spin.setReadOnly(False)
            duration_days_spin.setReadOnly(False)
            duration_spin.setButtonSymbols(QSpinBox.UpDownArrows)
            duration_days_spin.setButtonSymbols(QDoubleSpinBox.UpDownArrows)
            if checked:
                duration_spin.setToolTip(
                    "Estimated duration. Changing it recalculates the target finish."
                )
                if recalculate:
                    update_nested_duration()
            else:
                update_nested_duration()

        def on_nested_anchor_changed():
            set_nested_finish_from_duration()

        def on_nested_duration_minutes_changed(value: int):
            if syncing_sub_duration[0]:
                return
            syncing_sub_duration[0] = True
            try:
                sync_nested_days_from_minutes(value)
                set_nested_finish_from_duration()
            finally:
                syncing_sub_duration[0] = False

        def on_nested_duration_days_changed(value: float):
            if syncing_sub_duration[0]:
                return
            syncing_sub_duration[0] = True
            try:
                minutes = self._duration_minutes_from_days(value)
                old = duration_spin.blockSignals(True)
                duration_spin.setValue(minutes)
                duration_spin.blockSignals(old)
                set_nested_finish_from_duration()
            finally:
                syncing_sub_duration[0] = False

        planned_date_edit.dateChanged.connect(
            lambda _date: on_nested_anchor_changed()
        )
        due_date_edit.dateChanged.connect(
            lambda _date: update_nested_duration()
        )
        start_time_edit.timeChanged.connect(
            lambda _time: on_nested_anchor_changed()
        )
        end_time_edit.timeChanged.connect(
            lambda _time: update_nested_duration()
        )
        duration_spin.valueChanged.connect(
            on_nested_duration_minutes_changed
        )
        duration_days_spin.valueChanged.connect(
            on_nested_duration_days_changed
        )
        sub_finish_checkbox.toggled.connect(
            lambda checked: set_sub_finish_enabled(checked, recalculate=False)
        )

        should_recalculate_sub_from_finish = bool(
            start_value
            and end_value
            and not int(metadata.get("estimated_duration") or 0)
        )
        if should_recalculate_sub_from_finish:
            update_nested_duration()
        else:
            sync_nested_days_from_minutes(duration_spin.value())
            set_nested_finish_from_duration()
        set_sub_finish_enabled(
            sub_finish_checkbox.isChecked(),
            recalculate=False,
        )

        sub_duration_row = QHBoxLayout()
        sub_duration_row.addWidget(duration_days_spin)
        sub_duration_row.addWidget(duration_spin)
        sub_duration_row.addStretch()
        form.addRow("Duration", sub_duration_row)

        priority_combo = QComboBox()
        for p in TaskPriority:
            priority_combo.addItem(p.value)
        priority_value = metadata.get("priority", "Medium")
        idx = priority_combo.findText(priority_value)
        if idx >= 0:
            priority_combo.setCurrentIndex(idx)
        form.addRow("Priority", priority_combo)

        progress_spin = QSpinBox()
        progress_spin.setRange(0, 100)
        progress_spin.setSuffix("%")
        progress_spin.setValue(int(metadata.get("progress", 0)))
        form.addRow("Progress", progress_spin)

        subtask_workflow_group = QGroupBox("Status and Blocker / Delay Management", dlg)
        subtask_workflow_form = QFormLayout(subtask_workflow_group)

        subtask_status_combo = QComboBox(subtask_workflow_group)
        subtask_status_combo.setObjectName("subtask_status_combo")
        subtask_status_combo.setAccessibleName("Subtask status")
        subtask_status_combo.setFocusPolicy(Qt.StrongFocus)
        for label, status in WORKFLOW_STATUS_OPTIONS:
            subtask_status_combo.addItem(label, status)
        subtask_status_combo.view().setObjectName("subtask_status_combo_popup_view")

        default_subtask_status = (
            TaskStatus.COMPLETED
            if item.checkState(0) == Qt.Checked or int(metadata.get("progress") or 0) >= 100
            else TaskStatus.PLANNED
        )
        subtask_status = _coerce_task_status(
            metadata.get("status"),
            default_subtask_status,
        )
        status_idx = subtask_status_combo.findData(subtask_status)
        if status_idx >= 0:
            subtask_status_combo.setCurrentIndex(status_idx)

        subtask_blocker_category_combo = QComboBox(subtask_workflow_group)
        subtask_blocker_category_combo.setObjectName("subtask_blocker_category_combo")
        subtask_blocker_category_combo.setAccessibleName("Subtask blocker or delay category")
        subtask_blocker_category_combo.setFocusPolicy(Qt.StrongFocus)
        subtask_blocker_category_combo.addItems(BLOCKER_CATEGORY_OPTIONS)
        subtask_blocker_category_combo.view().setObjectName(
            "subtask_blocker_category_combo_popup_view"
        )

        existing_sub_category = (metadata.get("delay_category") or "None").strip()
        if existing_sub_category.lower() in {"", "none", "null"}:
            existing_sub_category = "None"
        sub_category_idx = subtask_blocker_category_combo.findText(
            existing_sub_category,
            Qt.MatchFixedString,
        )
        if sub_category_idx < 0 and existing_sub_category:
            subtask_blocker_category_combo.addItem(existing_sub_category)
            sub_category_idx = subtask_blocker_category_combo.findText(
                existing_sub_category,
                Qt.MatchFixedString,
            )
        if sub_category_idx >= 0:
            subtask_blocker_category_combo.setCurrentIndex(sub_category_idx)

        subtask_blocker_reason_input = QLineEdit(
            metadata.get("delay_reason", "") or "",
            subtask_workflow_group,
        )
        subtask_blocker_reason_input.setObjectName("subtask_blocker_reason_input")
        subtask_blocker_reason_input.setAccessibleName("Subtask blocker or delay reason")
        subtask_blocker_reason_input.setPlaceholderText(
            "What is stopping or delaying this subtask?"
        )

        subtask_blocker_notes_input = RichTextEditor(settings_manager=self.settings_manager)
        subtask_blocker_notes_input.setObjectName("subtask_blocker_notes_input")
        subtask_blocker_notes_input.setAccessibleName("Subtask blocker recovery notes")
        subtask_blocker_notes_input.setHtml(metadata.get("delay_notes", "") or "")
        subtask_blocker_notes_input.setPlaceholderText(
            "Owner, action required, expected resolution, decision needed..."
        )

        subtask_workflow_hint = QLabel()
        subtask_workflow_hint.setObjectName("subtask_workflow_hint")
        subtask_workflow_hint.setWordWrap(True)
        subtask_workflow_hint.setStyleSheet("font-size: 11px; opacity: 0.85;")

        subtask_workflow_form.addRow("Status", subtask_status_combo)
        subtask_workflow_form.addRow("Category", subtask_blocker_category_combo)
        subtask_workflow_form.addRow("Reason", subtask_blocker_reason_input)
        subtask_workflow_form.addRow("Recovery / Notes", subtask_blocker_notes_input)
        subtask_workflow_form.addRow("", subtask_workflow_hint)

        dlg._status_blocker_delay_handler_count = 0
        dlg._status_blocker_delay_signal_log = []

        def update_subtask_workflow_ui(*_args):
            dlg._status_blocker_delay_handler_count += 1
            dlg._status_blocker_delay_signal_log.append(
                (
                    subtask_status_combo.currentIndex(),
                    subtask_status_combo.currentText(),
                    subtask_status_combo.currentData(),
                )
            )
            status = subtask_status_combo.currentData()
            is_blocked_or_delayed = status in (
                TaskStatus.BLOCKED,
                TaskStatus.DELAYED,
            )
            subtask_blocker_category_combo.setEnabled(is_blocked_or_delayed)
            subtask_blocker_reason_input.setEnabled(is_blocked_or_delayed)
            subtask_blocker_notes_input.setEnabled(is_blocked_or_delayed)
            if status == TaskStatus.BLOCKED:
                hint = "Blocked: choose a category and record the reason before saving."
            elif status == TaskStatus.DELAYED:
                hint = "Delayed: capture the cause and recovery action before saving."
            elif status == TaskStatus.IN_PROGRESS:
                hint = "In Progress: progress represents real execution."
            elif status == TaskStatus.COMPLETED:
                hint = "Completed: saving will mark this subtask done."
            else:
                hint = "Blocker and delay fields enable only for Blocked or Delayed status."
            subtask_workflow_hint.setText(hint)

        dlg._update_status_blocker_delay_ui = update_subtask_workflow_ui
        subtask_status_combo.currentIndexChanged.connect(update_subtask_workflow_ui)
        subtask_status_combo.currentTextChanged.connect(update_subtask_workflow_ui)
        subtask_status_combo.activated.connect(update_subtask_workflow_ui)
        update_subtask_workflow_ui()

        form.addRow("Workflow", subtask_workflow_group)

        gantt_checkbox = QCheckBox("Show in Gantt")
        gantt_checkbox.setChecked(
            item.checkState(3) == Qt.Checked
        )
        form.addRow("Gantt", gantt_checkbox)

        sub_dependency_group = QGroupBox("Dependencies")
        sub_dependency_group.setToolTip(
            "Add predecessor tasks or subtasks that must happen before this subtask."
        )
        sub_dependency_layout = QVBoxLayout(sub_dependency_group)
        sub_dependency_tree = QTreeWidget(sub_dependency_group)
        sub_dependency_tree.setObjectName("subtask_dependency_tree")
        sub_dependency_tree.setMinimumHeight(140)
        sub_dependency_tree.setAlternatingRowColors(True)
        sub_dependency_tree.setAccessibleName("Subtask dependency editor")

        sub_dependency_candidates = []
        sub_successor_key = None
        if sub_id is not None and self.db_manager is not None:
            try:
                sub_successor_key = EntityRef.subtask(int(sub_id))
                sub_dependency_candidates = self._populate_dependency_tree(
                    sub_dependency_tree,
                    successor_key=sub_successor_key,
                    raw_dependencies=metadata.get("dependencies", []),
                    include_legacy_external=False,
                )
                self._wire_dependency_add_controls(
                    sub_dependency_layout,
                    tree=sub_dependency_tree,
                    candidates=sub_dependency_candidates,
                    object_prefix="subtask_dependency",
                )
                sub_dependency_layout.addWidget(sub_dependency_tree)
            except Exception as exc:
                sub_dependency_tree.setEnabled(False)
                sub_dependency_layout.addWidget(
                    QLabel(f"Dependency editor could not load: {exc}")
                )
                sub_dependency_layout.addWidget(sub_dependency_tree)
        else:
            sub_dependency_tree.setEnabled(False)
            sub_dependency_tree.setToolTip(
                "Save the task once before adding dependencies to a new subtask."
            )
            help_label = QLabel(
                "Save this task once before adding dependencies to this new subtask."
            )
            help_label.setWordWrap(True)
            sub_dependency_layout.addWidget(help_label)
            sub_dependency_layout.addWidget(sub_dependency_tree)

        form.addRow("Dependencies", sub_dependency_group)

        # Migration v11 Subtask cover image
        sub_img_row = QHBoxLayout()
        sub_img_lbl = QLabel("None")
        sub_img_lbl.setStyleSheet("color: #6B7280; font-size: 11px;")
        sub_img_path = [metadata.get("image_path", "") or ""]
        if sub_img_path[0]:
            sub_img_lbl.setStyleSheet("color: #10B981; font-weight: bold; font-size: 11px;")

        sub_browse_btn = QPushButton("Cover Image…")
        sub_clear_btn = QPushButton("✕")
        sub_clear_btn.setToolTip("Remove subtask cover image")

        def on_sub_browse():
            chosen, _ = QFileDialog.getOpenFileName(
                dlg,
                "Select Subtask Cover Image",
                "",
                "Image Files (*.png *.jpg *.jpeg *.webp *.bmp *.gif)",
            )
            if chosen:
                try:
                    from todo_bird_app.services.media_service import MediaService
                    imported_meta = MediaService.import_media(
                        chosen,
                        category="tasks",
                        db_manager=self.db_manager,
                    )
                    sub_img_path[0] = imported_meta["relative_path"]
                    sub_img_lbl.setText("Attached")
                    sub_img_lbl.setStyleSheet("color: #10B981; font-weight: bold; font-size: 11px;")
                except Exception as e:
                    QMessageBox.warning(dlg, "Image Import Error", f"Could not import image: {e}")

        def on_sub_clear():
            sub_img_path[0] = ""
            sub_img_lbl.setText("None")
            sub_img_lbl.setStyleSheet("color: #6B7280; font-size: 11px;")

        sub_browse_btn.clicked.connect(on_sub_browse)
        sub_clear_btn.clicked.connect(on_sub_clear)
        sub_img_row.addWidget(sub_browse_btn)
        sub_img_row.addWidget(sub_img_lbl)
        sub_img_row.addWidget(sub_clear_btn)
        sub_img_row.addStretch()
        form.addRow("Cover Image", sub_img_row)

        # Migration v8 nested pin controls
        nested_pin_row = QHBoxLayout()
        nested_pin_checkbox = QCheckBox("Pin this item")
        nested_pin_checkbox.setChecked(
            bool(metadata.get("is_pinned", False))
        )
        nested_pin_checkbox.setToolTip(
            "Pin this subtask / sub-subtask to prioritize it visually in parent lists and focus views."
        )

        nested_pin_color_combo = QComboBox()
        nested_pin_color_combo.setObjectName("nested_pin_color_combo")
        nested_pin_color_combo.setAccessibleName("Subtask pin color")
        nested_pin_color_combo.setToolTip(
            "Choose the pin color after enabling Pin this item."
        )
        pin_colors = [
            ("Orange", "#E95420"),
            ("Blue", "#3584E4"),
            ("Purple", "#8B5CF6"),
            ("Green", "#10B981"),
            ("Amber", "#F59E0B"),
            ("Red", "#DC2626"),
            ("Graphite", "#374151"),
        ]
        for p_label, p_col in pin_colors:
            nested_pin_color_combo.addItem(_dot_icon(p_col, 12), p_label, p_col)

        sub_pin_color = metadata.get("pin_color", "#E95420") or "#E95420"
        p_idx = nested_pin_color_combo.findData(sub_pin_color)
        if p_idx >= 0:
            nested_pin_color_combo.setCurrentIndex(p_idx)

        nested_pin_color_combo.setEnabled(
            nested_pin_checkbox.isChecked()
        )
        nested_pin_checkbox.toggled.connect(
            nested_pin_color_combo.setEnabled
        )

        nested_pin_row.addWidget(nested_pin_checkbox)
        nested_pin_row.addWidget(QLabel("Color:"))
        nested_pin_row.addWidget(nested_pin_color_combo)
        nested_pin_row.addStretch()

        # -------------------------------------------------
        # Migration v9 actual execution parity
        # -------------------------------------------------
        actual_sub_container = QWidget()
        actual_sub_vbox = QVBoxLayout(actual_sub_container)
        actual_sub_vbox.setContentsMargins(0, 0, 0, 0)
        actual_sub_vbox.setSpacing(4)

        actual_sub_check = QCheckBox("Tracked")
        actual_sub_check.setChecked(
            bool(metadata.get("actual_start_date"))
        )

        actual_sub_start_date = QDateEdit()
        actual_sub_start_date.setCalendarPopup(True)
        actual_sub_start_date.setDisplayFormat("yyyy-MM-dd")
        act_s_val = metadata.get("actual_start_date") or metadata.get("planned_date")
        if act_s_val:
            try:
                ad = datetime.strptime(act_s_val, "%Y-%m-%d").date()
                actual_sub_start_date.setDate(QDate(ad.year, ad.month, ad.day))
            except Exception:
                actual_sub_start_date.setDate(QDate.currentDate())
        else:
            actual_sub_start_date.setDate(QDate.currentDate())

        actual_sub_start = QTimeEdit()
        actual_sub_start.setDisplayFormat("HH:mm")
        if metadata.get("actual_start_time"):
            try:
                sh, sm = map(int, str(metadata.get("actual_start_time")).split(":")[:2])
                actual_sub_start.setTime(QTime(sh, sm))
            except Exception:
                actual_sub_start.setTime(QTime(8, 0))
        else:
            actual_sub_start.setTime(QTime(8, 0))

        actual_sub_end_date = QDateEdit()
        actual_sub_end_date.setCalendarPopup(True)
        actual_sub_end_date.setDisplayFormat("yyyy-MM-dd")
        act_e_val = metadata.get("actual_end_date")
        if act_e_val:
            try:
                ed = datetime.strptime(act_e_val, "%Y-%m-%d").date()
                actual_sub_end_date.setDate(QDate(ed.year, ed.month, ed.day))
            except Exception:
                actual_sub_end_date.setDate(QDate.currentDate())
        else:
            actual_sub_end_date.setDate(QDate.currentDate())

        actual_sub_end = QTimeEdit()
        actual_sub_end.setDisplayFormat("HH:mm")
        if metadata.get("actual_end_time"):
            try:
                eh, em = map(int, str(metadata.get("actual_end_time")).split(":")[:2])
                actual_sub_end.setTime(QTime(eh, em))
            except Exception:
                actual_sub_end.setTime(QTime(9, 0))
        else:
            actual_sub_end.setTime(QTime(9, 0))

        actual_sub_elapsed_lbl = QLabel("0h 00m (0 mins)")
        actual_sub_elapsed_lbl.setStyleSheet("color: #10B981; font-weight: 600; font-size: 11px;")

        actual_sub_dur = QSpinBox()
        actual_sub_dur.setRange(0, 100000)
        actual_sub_dur.setSuffix(" mins")
        actual_sub_dur.setValue(int(metadata.get("actual_duration") or 0))

        def update_sub_actual_state(enabled):
            actual_sub_start_date.setEnabled(enabled)
            actual_sub_start.setEnabled(enabled)
            actual_sub_end_date.setEnabled(enabled)
            actual_sub_end.setEnabled(enabled)
            actual_sub_dur.setEnabled(enabled)
            update_sub_actual_span()

        def update_sub_actual_span():
            from todo_bird_app.utils.time_math import calculate_actual_elapsed_minutes, format_duration_display
            if not actual_sub_check.isChecked():
                actual_sub_elapsed_lbl.setText("0h 00m (0 mins)")
                return
            sd = actual_sub_start_date.date().toString("yyyy-MM-dd")
            st = actual_sub_start.time().toString("HH:mm")
            ed = actual_sub_end_date.date().toString("yyyy-MM-dd")
            et = actual_sub_end.time().toString("HH:mm")
            d = calculate_actual_elapsed_minutes(sd, st, ed, et)
            disp = format_duration_display(d)
            actual_sub_elapsed_lbl.setText(f"{disp} ({d} mins)")

        actual_sub_start_date.dateChanged.connect(lambda _d: update_sub_actual_span())
        actual_sub_start.timeChanged.connect(lambda _t: update_sub_actual_span())
        actual_sub_end_date.dateChanged.connect(lambda _d: update_sub_actual_span())
        actual_sub_end.timeChanged.connect(lambda _t: update_sub_actual_span())
        actual_sub_check.toggled.connect(update_sub_actual_state)
        update_sub_actual_state(actual_sub_check.isChecked())

        # Sub row 1: Dates & Times
        act_sub_r1 = QHBoxLayout()
        act_sub_r1.setSpacing(6)
        act_sub_r1.addWidget(actual_sub_check)
        act_sub_r1.addWidget(actual_sub_start_date)
        act_sub_r1.addWidget(actual_sub_start)
        act_sub_r1.addWidget(QLabel("to"))
        act_sub_r1.addWidget(actual_sub_end_date)
        act_sub_r1.addWidget(actual_sub_end)
        act_sub_r1.addStretch()
        actual_sub_vbox.addLayout(act_sub_r1)

        # Sub row 2: Span & Effort
        act_sub_r2 = QHBoxLayout()
        act_sub_r2.setSpacing(10)
        act_sub_r2.addWidget(QLabel("Actual Span:"))
        act_sub_r2.addWidget(actual_sub_elapsed_lbl)
        act_sub_r2.addWidget(QLabel("Actual Effort:"))
        actual_sub_dur_lbl = QLabel("0h 00m (0 mins)")
        actual_sub_dur_lbl.setStyleSheet("color: #10B981; font-weight: 700; font-size: 11px;")
        act_sub_r2.addWidget(actual_sub_dur)
        act_sub_r2.addWidget(actual_sub_dur_lbl)
        act_sub_r2.addStretch()
        actual_sub_vbox.addLayout(act_sub_r2)

        def update_sub_actual_effort_display(val):
            from todo_bird_app.utils.time_math import format_duration_display
            disp = format_duration_display(val)
            actual_sub_dur.setToolTip(f"Actual Work Effort: {val} mins ({disp})")
            actual_sub_dur_lbl.setText(f"{disp} ({val} mins)")

        actual_sub_dur.valueChanged.connect(update_sub_actual_effort_display)
        update_sub_actual_effort_display(actual_sub_dur.value())

        form.addRow("Actual", actual_sub_container)

        # -------------------------------------------------
        # Migration v10 & Batch 3.4 & 3.8 — Unified Subtask WorkEffortEditor
        # -------------------------------------------------
        def current_sub_effort_date_bounds():
            p_date = planned_date_edit.date().toString("yyyy-MM-dd")
            d_date = (
                due_date_edit.date().toString("yyyy-MM-dd")
                if sub_finish_checkbox.isChecked()
                else p_date
            )
            return p_date, d_date

        sub_p_date, sub_d_date = current_sub_effort_date_bounds()
        cur_sub_mode = metadata.get("allocation_mode", "fixed_daily") or "fixed_daily"
        init_sub_ded = int(metadata.get("daily_dedication_minutes") or 0)
        init_sub_eff = int(metadata.get("planned_effort_minutes") or 0)
        sub_custom_allocs = dict(metadata.get("custom_allocations", {}))
        sub_custom_act_allocs = dict(metadata.get("custom_actual_allocations", {}))

        if sub_id is not None and self.db_manager is not None and not sub_custom_allocs:
            try:
                allocs = self.db_manager.get_task_allocations(subtask_id=sub_id)
                sub_custom_allocs = {a["allocation_date"]: int(a.get("planned_minutes", 0) or 0) for a in allocs}
                sub_custom_act_allocs = {a["allocation_date"]: int(a.get("actual_minutes", 0) or 0) for a in allocs}
            except Exception:
                pass

        sub_effort_editor = WorkEffortEditor(
            start_date=sub_p_date,
            due_date=sub_d_date,
            allocation_mode=cur_sub_mode,
            daily_dedication_minutes=init_sub_ded,
            planned_effort_minutes=init_sub_eff,
            custom_allocations=sub_custom_allocs,
            custom_actual_allocations=sub_custom_act_allocs,
            settings_manager=self.settings_manager,
            project_calendar_provider=self._current_project_calendar_spec,
        )

        sub_effort_editor.actualEffortChanged.connect(
            lambda val: actual_sub_dur.setValue(val)
        )

        planned_date_edit.dateChanged.connect(
            lambda _d: sub_effort_editor.set_dates(*current_sub_effort_date_bounds())
        )
        due_date_edit.dateChanged.connect(
            lambda _d: sub_effort_editor.set_dates(*current_sub_effort_date_bounds())
        )
        sub_finish_checkbox.toggled.connect(
            lambda _checked: sub_effort_editor.set_dates(*current_sub_effort_date_bounds())
        )

        form.addRow("Work Effort", sub_effort_editor)

        form.addRow(
            "Pin",
            nested_pin_row,
        )

        layout.addLayout(form)
        scroll.setWidget(scroll_content)
        main_vbox.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()

        cancel_btn = QPushButton("Cancel")
        save_btn = QPushButton("Save Details")
        save_btn.setObjectName("PrimaryButton")
        save_btn.setDefault(True)

        buttons.addWidget(cancel_btn)
        buttons.addWidget(save_btn)
        main_vbox.addLayout(buttons)

        cancel_btn.clicked.connect(dlg.reject)

        def save_details():
            try:
                from todo_bird_app.widgets.toast_banner import ToastBanner
                title = title_edit.text().strip()
                if not title:
                    ToastBanner.show_message(dlg, "Subtask title cannot be empty", status="warning")
                    title_edit.setFocus()
                    return

                clean_title = title.removeprefix("⚑ ").removeprefix("↳ ").strip()
                if not clean_title:
                    clean_title = title

                item.setText(0, clean_title)

                final_progress = progress_spin.value()
                selected_subtask_status = subtask_status_combo.currentData()
                if selected_subtask_status == TaskStatus.COMPLETED:
                    final_progress = 100
                    progress_spin.setValue(100)
                elif (
                    selected_subtask_status in (TaskStatus.INBOX, TaskStatus.PLANNED)
                    and 0 < final_progress < 100
                ):
                    selected_subtask_status = TaskStatus.IN_PROGRESS
                    idx = subtask_status_combo.findData(TaskStatus.IN_PROGRESS)
                    if idx >= 0:
                        subtask_status_combo.setCurrentIndex(idx)
                elif final_progress >= 100:
                    selected_subtask_status = TaskStatus.COMPLETED
                    idx = subtask_status_combo.findData(TaskStatus.COMPLETED)
                    if idx >= 0:
                        subtask_status_combo.setCurrentIndex(idx)

                subtask_is_completed = selected_subtask_status == TaskStatus.COMPLETED
                item.setCheckState(
                    0,
                    Qt.Checked if subtask_is_completed else Qt.Unchecked,
                )

                sub_delay_category = subtask_blocker_category_combo.currentText().strip()
                sub_delay_reason = subtask_blocker_reason_input.text().strip()
                sub_delay_notes = subtask_blocker_notes_input.toHtml().strip()
                sub_delay_recorded_at = metadata.get("delay_recorded_at")
                if selected_subtask_status in (TaskStatus.BLOCKED, TaskStatus.DELAYED):
                    if sub_delay_category.lower() in {"", "none", "null"}:
                        QMessageBox.warning(
                            dlg,
                            "Blocker Category Required",
                            "Please select what is blocking or delaying this subtask.",
                        )
                        subtask_blocker_category_combo.setFocus()
                        return
                    if not sub_delay_reason:
                        QMessageBox.warning(
                            dlg,
                            "Blocker Reason Required",
                            "Please record the reason this subtask is blocked or delayed.",
                        )
                        subtask_blocker_reason_input.setFocus()
                        return
                    sub_delay_recorded_at = datetime.now().isoformat(timespec="seconds")

                sub_dependencies_value = raw_dependency_list(
                    metadata.get("dependencies")
                )
                if sub_successor_key is not None:
                    (
                        selected_sub_dependencies,
                        incomplete_sub_dependencies,
                        dependency_error,
                        dependency_focus,
                    ) = self._dependency_specs_from_tree(
                        sub_dependency_tree,
                        successor_key=sub_successor_key,
                    )
                    if dependency_error:
                        QMessageBox.warning(
                            dlg,
                            "Invalid Dependency",
                            dependency_error,
                        )
                        if dependency_focus is not None:
                            dependency_focus.setFocus()
                        return

                    validation = DependencyAuthoringService.validate_dependencies(
                        self.db_manager,
                        successor_key=sub_successor_key,
                        raw_dependencies=self._dependency_storage_from_specs(
                            selected_sub_dependencies or [],
                            successor_key=sub_successor_key,
                        ),
                        project_id=self._current_project_id(),
                    )
                    if not validation.valid:
                        QMessageBox.warning(
                            dlg,
                            "Invalid Dependency",
                            validation.message,
                        )
                        sub_dependency_tree.setFocus()
                        return

                    if final_progress >= 100 and incomplete_sub_dependencies:
                        QMessageBox.warning(
                            dlg,
                            "Cannot Complete Subtask",
                            "This subtask still has unfinished dependencies:\n\n"
                            + "\n".join(
                                f"• {name}"
                                for name in incomplete_sub_dependencies
                            )
                            + "\n\nComplete or remove those dependencies first.",
                        )
                        sub_dependency_tree.setFocus()
                        return

                    sub_dependencies_value = self._dependency_storage_from_specs(
                        selected_sub_dependencies or [],
                        successor_key=sub_successor_key,
                    )

                planned_date_value = planned_date_edit.date().toString("yyyy-MM-dd")
                start_time_value = start_time_edit.time().toString("HH:mm")
                if sub_finish_checkbox.isChecked():
                    due_date_value = due_date_edit.date().toString("yyyy-MM-dd")
                    end_time_value = end_time_edit.time().toString("HH:mm")
                else:
                    due_date_value = None
                    end_time_value = None

                if actual_sub_check.isChecked():
                    act_s_date = actual_sub_start_date.date().toString("yyyy-MM-dd")
                    act_e_date = actual_sub_end_date.date().toString("yyyy-MM-dd")
                    act_s_time = actual_sub_start.time().toString("HH:mm")
                    act_e_time = actual_sub_end.time().toString("HH:mm")
                else:
                    act_s_date = None
                    act_e_date = None
                    act_s_time = None
                    act_e_time = None

                # Actual effort is always preserved from actual_sub_dur or custom allocations
                act_dur_val = actual_sub_dur.value()
                sub_effort_data = sub_effort_editor.get_data()
                if sub_effort_data.get("actual_effort_minutes", 0) > 0:
                    act_dur_val = int(sub_effort_data["actual_effort_minutes"])

                item.setData(
                    0,
                    Qt.UserRole + 1,
                    {
                        "description": description_edit.toHtml().strip(),
                        "planned_date": planned_date_value,
                        "due_date": due_date_value,
                        "planned_start_time": start_time_value,
                        "planned_end_time": end_time_value,
                        "estimated_duration": duration_spin.value(),
                        "priority": priority_combo.currentText(),
                        "progress": final_progress,
                        "status": selected_subtask_status.value,
                        "delay_category": (
                            sub_delay_category
                            if sub_delay_category and sub_delay_category != "None"
                            else metadata.get("delay_category", "") or ""
                        ),
                        "delay_reason": sub_delay_reason or metadata.get("delay_reason", "") or "",
                        "delay_notes": sub_delay_notes or metadata.get("delay_notes", "") or "",
                        "delay_recorded_at": sub_delay_recorded_at,
                        "dependencies": sub_dependencies_value,

                        # Migration v8 pin fields
                        "is_pinned": (
                            nested_pin_checkbox.isChecked()
                        ),
                        "pin_color": (
                            nested_pin_color_combo.currentData()
                            or "#E95420"
                        ),
                        "pin_position": int(
                            metadata.get("pin_position")
                            or 0
                        ),

                        # Migration v9 actual execution parity
                        "actual_start_date": act_s_date,
                        "actual_end_date": act_e_date,
                        "actual_start_time": act_s_time,
                        "actual_end_time": act_e_time,
                        "actual_duration": act_dur_val,

                        # Migration v10 planned effort parity & Batch 3.4 & 3.8 custom allocations
                        "planned_effort_minutes": sub_effort_data["planned_effort_minutes"],
                        "daily_dedication_minutes": sub_effort_data["daily_dedication_minutes"],
                        "allocation_mode": sub_effort_data["allocation_mode"],
                        "custom_allocations": sub_effort_data["custom_allocations"],
                        "custom_actual_allocations": sub_effort_data.get("custom_actual_allocations", {}),

                        # Migration v11 Subtask cover image
                        "image_path": sub_img_path[0],
                    }
                )

                item.setText(1, planned_date_value)
                item.setText(
                    2,
                    (
                        f"{start_time_value}–{end_time_value}"
                        if end_time_value
                        else (start_time_value or "—")
                    ),
                )
                item.setCheckState(3, Qt.Checked if gantt_checkbox.isChecked() else Qt.Unchecked)

                # Make nested pinning visible immediately in hierarchy.
                if nested_pin_checkbox.isChecked():
                    item.setForeground(0, QColor(nested_pin_color_combo.currentData() or "#E95420"))
                else:
                    item.setText(0, clean_title)
                    item.setForeground(0, QColor("#D1D5DB"))

                dlg.accept()
            except Exception as e:
                import traceback
                traceback.print_exc()
                QMessageBox.critical(dlg, "Save Details Error", f"Could not save subtask details: {str(e)}")

        save_btn.clicked.connect(save_details)

        from todo_bird_app.services.typography_service import TypographyService
        TypographyService.apply_to_widget(dlg, "dialogs", self.settings_manager)

        dlg.exec()

    def remove_selected_subtask(self):
        def remove_checked_children(parent_item):
            for index in range(parent_item.childCount() - 1, -1, -1):
                child = parent_item.child(index)

                remove_checked_children(child)

                if child.checkState(4) == Qt.Checked:
                    parent_item.takeChild(index)

        for row in range(self.subtask_tree.topLevelItemCount() - 1, -1, -1):
            item = self.subtask_tree.topLevelItem(row)

            remove_checked_children(item)

            if item.checkState(4) == Qt.Checked:
                self.subtask_tree.takeTopLevelItem(row)

        self._update_subtask_empty_state()

    def _collect_subtask_tree(self):
        def collect_item(item, position):
            metadata = item.data(0, Qt.UserRole + 1) or {}

            progress = max(
                0,
                min(int(metadata.get("progress") or 0), 100)
            )
            status = _coerce_task_status(
                metadata.get("status"),
                TaskStatus.COMPLETED if progress >= 100 else TaskStatus.PLANNED,
            )
            if status == TaskStatus.COMPLETED:
                progress = 100
            is_completed = status == TaskStatus.COMPLETED

            # Keep visible checkbox synchronized with persisted truth.
            item.setCheckState(
                0,
                Qt.Checked if is_completed else Qt.Unchecked
            )

            data = {
                "id": item.data(0, Qt.UserRole),
                "title": (
                    item.text(0)
                    .strip()
                ),
                "description": metadata.get("description", ""),
                "planned_date": metadata.get("planned_date"),
                "due_date": metadata.get("due_date"),
                "planned_start_time": metadata.get("planned_start_time"),
                "planned_end_time": metadata.get("planned_end_time"),
                "estimated_duration": int(
                    metadata.get("estimated_duration") or 0
                ),
                "priority": metadata.get("priority") or "Medium",
                "progress": progress,
                "status": status.value,
                "delay_category": metadata.get("delay_category", "") or "",
                "delay_reason": metadata.get("delay_reason", "") or "",
                "delay_notes": metadata.get("delay_notes", "") or "",
                "delay_recorded_at": metadata.get("delay_recorded_at"),
                "dependencies": raw_dependency_list(
                    metadata.get("dependencies")
                ),
                "is_completed": is_completed,
                "show_in_gantt": item.checkState(3) == Qt.Checked,
                "position": position,

                # Migration v8 nested pin fields
                "is_pinned": bool(
                    metadata.get("is_pinned", False)
                ),
                "pin_color": (
                    metadata.get("pin_color")
                    or "#E95420"
                ),
                "pin_position": int(
                    metadata.get("pin_position")
                    or 0
                ),

                # Migration v9 actual execution parity
                "actual_start_date": metadata.get("actual_start_date"),
                "actual_end_date": metadata.get("actual_end_date"),
                "actual_start_time": metadata.get("actual_start_time"),
                "actual_end_time": metadata.get("actual_end_time"),
                "actual_duration": int(metadata.get("actual_duration") or 0),

                # Migration v10 planned effort parity & Batch 3.4 custom allocations
                "planned_effort_minutes": int(metadata.get("planned_effort_minutes") or 0),
                "daily_dedication_minutes": int(metadata.get("daily_dedication_minutes") or 0),
                "allocation_mode": metadata.get("allocation_mode", "fixed_daily") or "fixed_daily",
                "custom_allocations": dict(metadata.get("custom_allocations") or {}),

                # Migration v11 Cover Image
                "image_path": metadata.get("image_path", "") or "",

                "children": [],
            }

            for child_index in range(item.childCount()):
                child = item.child(child_index)
                child_data = collect_item(child, child_index)
                if child_data["title"]:
                    data["children"].append(child_data)

            return data

        result = []

        for row in range(self.subtask_tree.topLevelItemCount()):
            item = self.subtask_tree.topLevelItem(row)
            data = collect_item(item, row)

            if data["title"]:
                result.append(data)

        return result

    def on_save(self):
        title = self.title_input.text().strip()
        if not title:
            self.title_input.setFocus()
            return

        self.task.title = title
        self.task.project_id = self.project_combo.currentData()
        self.task.priority = self.prio_combo.currentData()
        self.task.category = self.cat_combo.currentData()
        self.task.planned_date = self.planned_date_edit.date().toString("yyyy-MM-dd")
        self.task.planned_start_time = self.start_time_edit.time().toString("HH:mm")
        if self.planned_finish_checkbox.isChecked():
            self.task.due_date = self.due_date_edit.date().toString("yyyy-MM-dd")
            self.task.planned_end_time = self.end_time_edit.time().toString("HH:mm")
        else:
            self.task.due_date = None
            self.task.planned_end_time = None
        self.task.estimated_duration = self.duration_spin.value()
        self.task.description = self.desc_input.toHtml().strip()
        self.task.progress = self.progress_spin.value()

        tags_str = self.tags_input.text().strip()
        self.task.tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []

        rec = self.recurring_combo.currentText()
        self.task.recurring = rec.lower() if rec != "None" else None

        self.task.show_in_gantt = self.show_in_gantt_checkbox.isChecked()
        chosen_startup_mode = self.startup_reminder_combo.currentData() or "off"
        self.task.startup_reminder_mode = chosen_startup_mode
        self.task.startup_reminder = (chosen_startup_mode != "off")
        ReminderPolicyService.ensure_startup_trigger_enabled_for_launch_reminder(
            self.settings_manager,
            chosen_startup_mode,
        )

        self.task.is_pinned = self.pin_checkbox.isChecked()
        self.task.pin_color = self.pin_color_combo.currentData() or "#E95420"

        # Preserve existing ordering for now.
        self.task.pin_position = int(
            getattr(self.task, "pin_position", 0) or 0
        )

        main_effort_data = {}
        if hasattr(self, "work_effort_editor"):
            main_effort_data = self.work_effort_editor.get_data()
            if (
                not self.planned_finish_checkbox.isChecked()
                and not self._work_effort_user_touched
            ):
                self.task.planned_effort_minutes = self._raw_planned_effort_at_open
                self.task.daily_dedication_minutes = self._raw_daily_dedication_at_open
                self.task.allocation_mode = self._raw_allocation_mode_at_open
            else:
                self.task.planned_effort_minutes = int(main_effort_data.get("planned_effort_minutes", 0) or 0)
                self.task.daily_dedication_minutes = int(main_effort_data.get("daily_dedication_minutes", 0) or 0)
                self.task.allocation_mode = main_effort_data.get("allocation_mode", "fixed_daily") or "fixed_daily"
        elif hasattr(self, "planned_effort_spin"):
            self.task.planned_effort_minutes = self.planned_effort_spin.value()
            if hasattr(self, "daily_hours_spin") and hasattr(self, "daily_mins_spin"):
                self.task.daily_dedication_minutes = self.daily_hours_spin.value() * 60 + self.daily_mins_spin.value()
            if hasattr(self, "allocation_mode_combo"):
                self.task.allocation_mode = self.allocation_mode_combo.currentData() or "fixed_daily"

        self.task.image_path = getattr(self, "current_image_path", "") or ""

        # Schedule Constraints & Deadlines (Phase 2E)
        chosen_ctype = self.constraint_type_combo.currentData() or "ASAP"
        self.task.constraint_type = chosen_ctype
        if is_date_required(chosen_ctype):
            raw_cd = self.constraint_date_edit.lineEdit().text().strip() if self.constraint_date_edit.lineEdit() else ""
            parsed_cd = parse_constraint_datetime(raw_cd)
            if parsed_cd:
                c_d = parsed_cd.strftime("%Y-%m-%d")
            else:
                c_d = self.constraint_date_edit.date().toString("yyyy-MM-dd")
            c_t = self.constraint_time_edit.time().toString("HH:mm")
            self.task.constraint_datetime = f"{c_d} {c_t}"
        else:
            self.task.constraint_datetime = None

        if self.deadline_check.isChecked():
            raw_dd = self.deadline_date_edit.lineEdit().text().strip() if self.deadline_date_edit.lineEdit() else ""
            parsed_dd = parse_constraint_datetime(raw_dd)
            if parsed_dd:
                d_d = parsed_dd.strftime("%Y-%m-%d")
            else:
                d_d = self.deadline_date_edit.date().toString("yyyy-MM-dd")
            d_t = self.deadline_time_edit.time().toString("HH:mm")
            self.task.deadline_datetime = f"{d_d} {d_t}"
        else:
            self.task.deadline_datetime = None

        # -------------------------------------------------
        # Program-management workflow state
        # -------------------------------------------------
        selected_status = self.status_combo.currentData()
        task_successor_key = self._dependency_successor_key()
        selected_dependencies = []
        incomplete_dependencies = []

        if task_successor_key is not None:
            (
                selected_dependency_specs,
                incomplete_dependencies,
                dependency_error,
                dependency_focus,
            ) = self._dependency_specs_from_tree(
                self.dependency_tree,
                successor_key=task_successor_key,
            )
            if dependency_error:
                QMessageBox.warning(
                    self,
                    "Invalid Dependency",
                    dependency_error,
                )
                if dependency_focus is not None:
                    dependency_focus.setFocus()
                return

            selected_dependencies = self._dependency_storage_from_specs(
                selected_dependency_specs or [],
                successor_key=task_successor_key,
            )
            orig_specs = parse_authoring_dependency_specs(
                self.task.dependencies,
                fallback_entity_type="task",
            )
            if tuple(selected_dependency_specs or []) != orig_specs:
                validation = DependencyAuthoringService.validate_dependencies(
                    self.db_manager,
                    successor_key=task_successor_key,
                    raw_dependencies=selected_dependencies,
                    project_id=self._current_project_id(),
                )
                if not validation.valid:
                    QMessageBox.warning(
                        self,
                        "Invalid Dependency",
                        validation.message,
                    )
                    self.dependency_tree.setFocus()
                    return

        self.task.dependencies = selected_dependencies

        # Progress between 1-99% means execution has actually started.
        if (
            selected_status in (TaskStatus.INBOX, TaskStatus.PLANNED)
            and 0 < self.progress_spin.value() < 100
        ):
            selected_status = TaskStatus.IN_PROGRESS

        # Completion is explicit. 100% progress by itself does NOT
        # silently complete a task.
        if selected_status == TaskStatus.COMPLETED:
            if incomplete_dependencies:
                QMessageBox.warning(
                    self,
                    "Cannot Complete Task",
                    "This task still has unfinished dependencies:\n\n"
                    + "\n".join(
                        f"• {name}"
                        for name in incomplete_dependencies
                    )
                    + "\n\nComplete or remove those dependencies first."
                )
                self.dependency_tree.setFocus()
                return

            self.task.progress = 100
            self.progress_slider.setValue(100)

        elif selected_status == TaskStatus.IN_PROGRESS:
            # Respect the user's progress slider.
            self.task.progress = self.progress_spin.value()

        elif selected_status in (
            TaskStatus.BLOCKED,
            TaskStatus.DELAYED,
        ):
            blocker_category = self.blocker_category_combo.currentText().strip()
            blocker_reason = self.blocker_reason_input.text().strip()

            if blocker_category.lower() in {"", "none", "null"}:
                QMessageBox.warning(
                    self,
                    "Blocker Category Required",
                    "Please select what is blocking or delaying this task."
                )
                self.blocker_category_combo.setFocus()
                return

            if not blocker_reason:
                QMessageBox.warning(
                    self,
                    "Blocker Reason Required",
                    "Please record the reason this task is blocked or delayed."
                )
                self.blocker_reason_input.setFocus()
                return

            self.task.delay_category = blocker_category
            self.task.delay_reason = blocker_reason
            self.task.delay_notes = (
                self.blocker_notes_input.toHtml().strip()
            )
            self.task.delay_recorded_at = datetime.now().isoformat(
                timespec="seconds"
            )

            self.task.progress = self.progress_spin.value()

        else:
            self.task.progress = self.progress_spin.value()

        # Preserve entered blocker/recovery information even after the task
        # later resumes or completes, so the latest issue remains traceable.
        if selected_status not in (
            TaskStatus.BLOCKED,
            TaskStatus.DELAYED,
        ):
            category_text = self.blocker_category_combo.currentText().strip()
            reason_text = self.blocker_reason_input.text().strip()
            notes_text = self.blocker_notes_input.toHtml().strip()

            if category_text and category_text != "None":
                self.task.delay_category = category_text
            if reason_text:
                self.task.delay_reason = reason_text
            if notes_text:
                self.task.delay_notes = notes_text

        # Actual Execution fields & Validation
        # Actual Effort is preserved from actual_duration_spin or custom allocations
        if hasattr(self, "actual_duration_spin"):
            self.task.actual_duration = self.actual_duration_spin.value()
        if hasattr(self, "work_effort_editor"):
            eff_data = self.work_effort_editor.get_data()
            if eff_data.get("actual_effort_minutes", 0) > 0:
                self.task.actual_duration = int(eff_data["actual_effort_minutes"])

        # Actual Start/End timestamps
        if hasattr(self, "actual_enabled_check") and self.actual_enabled_check.isChecked():
            act_s_d = self.actual_start_date_edit.date().toString("yyyy-MM-dd")
            act_s_t = self.actual_start_edit.time().toString("HH:mm")
            self.task.actual_start_date = act_s_d
            self.task.actual_start_time = act_s_t

            if hasattr(self, "actual_finish_check") and self.actual_finish_check.isChecked():
                act_e_d = self.actual_end_date_edit.date().toString("yyyy-MM-dd")
                act_e_t = self.actual_end_edit.time().toString("HH:mm")

                if act_s_d > act_e_d or (act_s_d == act_e_d and act_s_t > act_e_t):
                    QMessageBox.warning(
                        self,
                        "Invalid Actual Execution Timeline",
                        "Actual End date/time cannot be earlier than Actual Start date/time."
                    )
                    self.actual_end_edit.setFocus()
                    return

                self.task.actual_end_date = act_e_d
                self.task.actual_end_time = act_e_t
            else:
                self.task.actual_end_date = None
                self.task.actual_end_time = None
        elif hasattr(self, "actual_enabled_check") and not self.actual_enabled_check.isChecked():
            self.task.actual_start_date = None
            self.task.actual_end_date = None
            self.task.actual_start_time = None
            self.task.actual_end_time = None
        self.task.status = selected_status

        # Validate execution state invariants using canonical authority
        from todo_bird_app.services.execution_performance_service import ExecutionPerformanceService
        violations = ExecutionPerformanceService.validate_execution_invariants(self.task)
        if violations:
            _code, msg = violations[0]
            QMessageBox.warning(
                self,
                "Invalid Execution State",
                msg,
            )
            return

        self.pending_subtasks = self._collect_subtask_tree()

        if self.task.id is not None and self.db_manager is not None:
            existing_rows = self.db_manager.get_all_subtasks_flat(self.task.id)
            existing_ids = {
                row.get("id")
                for row in existing_rows
                if row.get("id") is not None
            }

            current_ids = set()

            def collect_existing_ids(nodes):
                for node in nodes:
                    if node.get("id") is not None:
                        current_ids.add(node["id"])
                    collect_existing_ids(node.get("children", []))

            collect_existing_ids(self.pending_subtasks)

            # Delete removed branches only when Save Task is pressed.
            for subtask_id in existing_ids - current_ids:
                self.db_manager.delete_subtask(subtask_id)

            def save_nodes(nodes, parent_subtask_id=None):
                for position, subtask in enumerate(nodes):
                    if subtask["id"] is None:
                        subtask["id"] = self.db_manager.insert_subtask(
                            task_id=self.task.id,
                            title=subtask["title"],
                            is_completed=subtask["is_completed"],
                            position=position,
                            parent_subtask_id=parent_subtask_id,
                            description=subtask["description"],
                            planned_date=subtask["planned_date"],
                            due_date=subtask["due_date"],
                            planned_start_time=subtask["planned_start_time"],
                            planned_end_time=subtask["planned_end_time"],
                            estimated_duration=subtask["estimated_duration"],
                            priority=subtask["priority"],
                            progress=subtask["progress"],
                            status=subtask.get("status", TaskStatus.PLANNED.value),
                            delay_category=subtask.get("delay_category", "") or "",
                            delay_reason=subtask.get("delay_reason", "") or "",
                            delay_notes=subtask.get("delay_notes", "") or "",
                            delay_recorded_at=subtask.get("delay_recorded_at"),
                            show_in_gantt=subtask["show_in_gantt"],
                            dependencies=subtask.get("dependencies", []),

                            # Migration v8 nested pin fields
                            is_pinned=subtask.get(
                                "is_pinned",
                                False,
                            ),
                            pin_color=subtask.get(
                                "pin_color",
                                "#E95420",
                            ),
                            pin_position=subtask.get(
                                "pin_position",
                                0,
                            ),

                            # Migration v9 actual execution parity
                            actual_start_date=subtask.get("actual_start_date"),
                            actual_end_date=subtask.get("actual_end_date"),
                            actual_start_time=subtask.get("actual_start_time"),
                            actual_end_time=subtask.get("actual_end_time"),
                            actual_duration=int(subtask.get("actual_duration") or 0),

                            # Migration v10 planned effort parity
                            planned_effort_minutes=int(subtask.get("planned_effort_minutes") or 0),
                            daily_dedication_minutes=int(subtask.get("daily_dedication_minutes") or 0),
                            allocation_mode=subtask.get("allocation_mode", "fixed_daily") or "fixed_daily",

                            # Migration v11 Cover image
                            image_path=subtask.get("image_path", "") or "",
                        )
                    else:
                        self.db_manager.update_subtask(
                            subtask_id=subtask["id"],
                            title=subtask["title"],
                            is_completed=subtask["is_completed"],
                            position=position,
                            parent_subtask_id=parent_subtask_id,
                            description=subtask["description"],
                            planned_date=subtask["planned_date"],
                            due_date=subtask["due_date"],
                            planned_start_time=subtask["planned_start_time"],
                            planned_end_time=subtask["planned_end_time"],
                            estimated_duration=subtask["estimated_duration"],
                            priority=subtask["priority"],
                            progress=subtask["progress"],
                            status=subtask.get("status", TaskStatus.PLANNED.value),
                            delay_category=subtask.get("delay_category", "") or "",
                            delay_reason=subtask.get("delay_reason", "") or "",
                            delay_notes=subtask.get("delay_notes", "") or "",
                            delay_recorded_at=subtask.get("delay_recorded_at"),
                            show_in_gantt=subtask["show_in_gantt"],
                            dependencies=subtask.get("dependencies", []),

                            # Migration v8 nested pin fields
                            is_pinned=subtask.get(
                                "is_pinned",
                                False,
                            ),
                            pin_color=subtask.get(
                                "pin_color",
                                "#E95420",
                            ),
                            pin_position=subtask.get(
                                "pin_position",
                                0,
                            ),

                            # Migration v9 actual execution parity
                            actual_start_date=subtask.get("actual_start_date"),
                            actual_end_date=subtask.get("actual_end_date"),
                            actual_start_time=subtask.get("actual_start_time"),
                            actual_end_time=subtask.get("actual_end_time"),
                            actual_duration=int(subtask.get("actual_duration") or 0),

                            # Migration v10 planned effort parity
                            planned_effort_minutes=int(subtask.get("planned_effort_minutes") or 0),
                            daily_dedication_minutes=int(subtask.get("daily_dedication_minutes") or 0),
                            allocation_mode=subtask.get("allocation_mode", "fixed_daily") or "fixed_daily",

                            # Migration v11 Cover image
                            image_path=subtask.get("image_path", "") or "",
                        )

                    sub_id = subtask["id"]
                    sub_p_allocs = subtask.get("custom_allocations", {}) if subtask.get("allocation_mode") == "custom_by_day" else {}
                    sub_a_allocs = subtask.get("custom_actual_allocations", {})
                    all_sub_dates = set(sub_p_allocs.keys()) | set(sub_a_allocs.keys())
                    if all_sub_dates or subtask.get("allocation_mode") == "custom_by_day":
                        sub_allocs = [
                            {
                                "allocation_date": d,
                                "planned_minutes": sub_p_allocs.get(d, 0),
                                "actual_minutes": sub_a_allocs.get(d, 0),
                            }
                            for d in sorted(list(all_sub_dates))
                        ]
                        self.db_manager.set_task_allocations(
                            task_id=self.task.id,
                            subtask_id=sub_id,
                            allocations=sub_allocs
                        )

                    save_nodes(
                        subtask.get("children", []),
                        subtask["id"]
                    )

            save_nodes(self.pending_subtasks)

            main_p_allocs = main_effort_data.get("custom_allocations", {}) if self.task.allocation_mode == "custom_by_day" else {}
            main_a_allocs = main_effort_data.get("custom_actual_allocations", {})
            all_main_dates = set(main_p_allocs.keys()) | set(main_a_allocs.keys())
            if all_main_dates or self.task.allocation_mode == "custom_by_day":
                allocations = [
                    {
                        "allocation_date": d,
                        "planned_minutes": main_p_allocs.get(d, 0),
                        "actual_minutes": main_a_allocs.get(d, 0),
                    }
                    for d in sorted(list(all_main_dates))
                ]
                self.db_manager.set_task_allocations(task_id=self.task.id, subtask_id=None, allocations=allocations)

        self.accept()

    def get_task(self) -> Task:
        return self.task

    def get_pending_subtasks(self):
        return getattr(self, "pending_subtasks", [])
