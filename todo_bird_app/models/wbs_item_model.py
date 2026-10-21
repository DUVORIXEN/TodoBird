"""
TODO BIRD — WBS ITEM MODEL (QAbstractItemModel)
High-performance tree model adapting WBSHierarchySnapshot into a Qt item model.
Provides stable EntityRef mapping, custom data roles, O(1) index lookups,
and zero recursive SQL queries during paint/traversal.

Phase 1C: exposes derived parent rollups via WBSRollupService (leaf-only,
calendar elapsed, weighted progress). Summary nodes return rollup values;
leaf nodes return stored progress cache (child truth untouched). All lookups
are O(1) dict access — no DB query inside data()/paint path.
"""

from typing import Optional, List, Dict, Any
import logging

from PySide6.QtCore import QAbstractItemModel, QModelIndex, Qt

from todo_bird_app.services.wbs_service import (
    EntityRef,
    WBSNode,
    WBSHierarchySnapshot,
    WBSService,
)

logger = logging.getLogger(__name__)

# Lazy import friendly — RollupService is pure data, no cycle back to model
try:
    from todo_bird_app.services.wbs_rollup_service import WBSRollupService, RollupResult  # type: ignore
except Exception:  # pragma: no cover — import may fail in isolated tests
    WBSRollupService = None  # type: ignore
    RollupResult = None  # type: ignore

try:
    from todo_bird_app.services.cpm_scheduling_service import (
        CPMSchedulingService,
        SchedulingResult,
        ScheduleNodeResult,
        DiagnosticCode,
        format_float_duration,
        format_cpm_datetime,
    )
except Exception:  # pragma: no cover
    CPMSchedulingService = None  # type: ignore
    SchedulingResult = None  # type: ignore
    ScheduleNodeResult = None  # type: ignore
    DiagnosticCode = None  # type: ignore
    format_float_duration = lambda m: "—" if m is None else f"{m}m"  # type: ignore
    format_cpm_datetime = lambda dt: "—" if dt is None else str(dt)  # type: ignore

try:
    from todo_bird_app.services.wbs_cpm_adapter import (
        build_wbs_cpm_summary_by_key,
        calculate_wbs_cpm,
        cpm_key_in_cycles,
        cpm_node_for_key,
    )
except Exception:  # pragma: no cover
    build_wbs_cpm_summary_by_key = None  # type: ignore
    calculate_wbs_cpm = None  # type: ignore
    cpm_key_in_cycles = lambda _r, _k: False  # type: ignore
    cpm_node_for_key = lambda _r, _k: None  # type: ignore

try:
    from todo_bird_app.services.schedule_variance_service import (
        ScheduleVarianceService,
        TaskVarianceResult,
        ProjectVarianceSummary,
        VarianceStatus,
        format_variance_duration,
    )
except Exception:  # pragma: no cover
    ScheduleVarianceService = None  # type: ignore
    TaskVarianceResult = None  # type: ignore
    ProjectVarianceSummary = None  # type: ignore
    VarianceStatus = None  # type: ignore
    format_variance_duration = lambda m, zero_as_zero=True: "—" if m is None else ("0" if m == 0 and zero_as_zero else f"{m}m")  # type: ignore

try:
    from todo_bird_app.services.schedule_constraint_service import (
        ConstraintType,
        parse_constraint_datetime,
        format_deadline_variance,
        get_constraint_display_name,
    )
except Exception:  # pragma: no cover
    ConstraintType = None  # type: ignore
    parse_constraint_datetime = lambda v: None  # type: ignore
    format_deadline_variance = lambda m: "—"  # type: ignore
    get_constraint_display_name = lambda c: str(c)  # type: ignore


class WBSItemModel(QAbstractItemModel):
    """
    Hierarchical QAbstractItemModel backed by WBSHierarchySnapshot.

    Rollup integration:
    - set_snapshot() clears rollup cache (snapshot is immutable source)
    - set_db_manager() + rebuild_rollups() precomputes Dict[EntityRef, RollupResult]
      via WBSRollupService.compute_all_rollups() — single post-order O(n) pass
    - load_project() wires both in one call
    - data() for summary nodes returns rollup values (progress/effort/dates)
      via O(1) dict lookup; leaf nodes use stored cache (no mutation)
    - Parent DB fields are never overwritten (no update_task in this model)
    """

    # Custom Qt Data Roles — keep original 1..16 stable (Phase 1A/1B frozen)
    NodeKeyRole = Qt.UserRole + 1
    WBSCodeRole = Qt.UserRole + 2
    TitleRole = Qt.UserRole + 3
    StatusRole = Qt.UserRole + 4
    ProgressRole = Qt.UserRole + 5
    DepthRole = Qt.UserRole + 6
    HasChildrenRole = Qt.UserRole + 7
    IsMilestoneRole = Qt.UserRole + 8
    ProjectIdRole = Qt.UserRole + 9
    EntityTypeRole = Qt.UserRole + 10
    StableEntityIdRole = Qt.UserRole + 11
    PlannedStartRole = Qt.UserRole + 12
    PlannedFinishRole = Qt.UserRole + 13
    PlannedEffortRole = Qt.UserRole + 14
    ActualEffortRole = Qt.UserRole + 15
    NodeObjectRole = Qt.UserRole + 16

    # Phase 1C rollup-explicit roles (new, non-clashing 17..24) — synonyms for
    # the legacy roles above, plus whole-object access. Delegate may use either.
    RollupProgressRole = Qt.UserRole + 17
    RollupPlannedEffortRole = Qt.UserRole + 18
    RollupActualEffortRole = Qt.UserRole + 19
    RollupPlannedStartRole = Qt.UserRole + 20
    RollupPlannedFinishRole = Qt.UserRole + 21
    RollupActualStartRole = Qt.UserRole + 22
    RollupActualFinishRole = Qt.UserRole + 23
    RollupResultRole = Qt.UserRole + 24

    # Phase 1C summary metadata.
    # Keep role numbering stable for existing delegate/test contracts.
    RollupLeafCountRole = Qt.UserRole + 25
    RollupDataRole = Qt.UserRole + 26

    # Phase 2B Schedule Intelligence Roles (27..36)
    CPMTotalFloatRole = Qt.UserRole + 27
    CPMFreeFloatRole = Qt.UserRole + 28
    CPMCriticalRole = Qt.UserRole + 29
    CPMEarliestStartRole = Qt.UserRole + 30
    CPMEarliestFinishRole = Qt.UserRole + 31
    CPMLatestStartRole = Qt.UserRole + 32
    CPMLatestFinishRole = Qt.UserRole + 33
    CPMDiagnosticsRole = Qt.UserRole + 34
    CPMSchedulableRole = Qt.UserRole + 35
    CPMNodeResultRole = Qt.UserRole + 36
    CPMSummaryResultRole = Qt.UserRole + 50

    # Phase 2D Schedule Baseline & Variance Roles (37..44)
    BaselineStartRole = Qt.UserRole + 37
    BaselineFinishRole = Qt.UserRole + 38
    StartVarianceRole = Qt.UserRole + 39
    FinishVarianceRole = Qt.UserRole + 40
    DurationVarianceRole = Qt.UserRole + 41
    BaselineEffortRole = Qt.UserRole + 42
    EffortVarianceRole = Qt.UserRole + 43
    VarianceResultRole = Qt.UserRole + 44

    # Phase 2E Schedule Constraints & Deadlines Roles (45..49)
    ConstraintTypeRole = Qt.UserRole + 45
    ConstraintDateRole = Qt.UserRole + 46
    DeadlineDateRole = Qt.UserRole + 47
    DeadlineVarianceRole = Qt.UserRole + 48
    ConstraintStatusRole = Qt.UserRole + 49

    # Columns
    COL_WBS = 0
    COL_TITLE = 1
    COL_STATUS = 2
    COL_PROGRESS = 3
    COL_CRITICAL = 4
    COL_TOTAL_FLOAT = 5
    COL_FREE_FLOAT = 6
    COL_ES = 7
    COL_EF = 8
    COL_LS = 9
    COL_LF = 10
    COL_DIAGNOSTICS = 11
    COL_BASELINE_START = 12
    COL_BASELINE_FINISH = 13
    COL_START_VARIANCE = 14
    COL_FINISH_VARIANCE = 15
    COL_DURATION_VARIANCE = 16
    COL_CONSTRAINT = 17
    COL_CONSTRAINT_DATE = 18
    COL_DEADLINE = 19
    COL_DEADLINE_VARIANCE = 20
    COL_CONSTRAINT_STATUS = 21
    COLUMN_COUNT = 22

    HEADERS = [
        "WBS",
        "Task Name",
        "Status",
        "Progress",
        "Critical",
        "Total Float",
        "Free Float",
        "Earliest Start",
        "Earliest Finish",
        "Latest Start",
        "Latest Finish",
        "Schedule Health",
        "Baseline Start",
        "Baseline Finish",
        "Start Variance",
        "Finish Variance",
        "Duration Variance",
        "Constraint Type",
        "Constraint Date",
        "Deadline",
        "Deadline Variance",
        "Constraint Status",
    ]

    def __init__(self, snapshot: Optional[WBSHierarchySnapshot] = None, parent=None):
        super().__init__(parent)
        self._snapshot: WBSHierarchySnapshot = snapshot or WBSHierarchySnapshot(
            project_id=None,
            nodes_by_key={},
            children_by_parent={},
            root_keys=[],
            orphaned_keys=[],
            total_nodes=0,
            max_depth=0,
            revision=1,
        )
        self._progress_cache: Dict[EntityRef, int] = {}

        # Phase 1F.2:
        # EntityRef -> row within its canonical sibling scope.
        # Built once per snapshot so parent()/index_from_key()
        # never repeatedly scan Python sibling lists.
        self._row_by_key: Dict[EntityRef, int] = {}

        # Phase 1C rollup state — precomputed, O(1) lookup in data()
        self._rollups: Dict[Any, Any] = {}
        self._db_manager: Optional[Any] = None
        self._snapshot_rollup_valid: bool = False

        # Phase 2B schedule intelligence result — precomputed, O(1) lookup in data()
        self._cpm_result: Optional[Any] = None
        self._summary_cpm_by_key: Dict[EntityRef, Any] = {}

        # Phase 2D schedule baseline & variance state — precomputed, O(1) lookup in data()
        self._variance_by_key: Dict[EntityRef, Any] = {}
        self._summary_variance_by_key: Dict[EntityRef, Dict[str, Any]] = {}
        self._project_variance_summary: Optional[Any] = None

        # Build initial structural/display caches.
        self._rebuild_row_cache()
        self._rebuild_progress_cache()
        self.rebuild_cpm_schedule()

    @property
    def snapshot(self) -> WBSHierarchySnapshot:
        return self._snapshot

    # ------------------------------------------------------------------
    # Snapshot / DB wiring
    # ------------------------------------------------------------------

    def set_snapshot(
        self,
        snapshot: WBSHierarchySnapshot,
        db_manager: Optional[Any] = None,
    ):
        """Replaces the active snapshot and emits model reset. Clears rollups."""
        if db_manager is not None:
            self._db_manager = db_manager

        self.beginResetModel()
        self._snapshot = snapshot
        self._rollups = {}
        self._snapshot_rollup_valid = False
        self._variance_by_key = {}
        self._summary_variance_by_key = {}
        self._project_variance_summary = None
        self._summary_cpm_by_key = {}
        self._rebuild_row_cache()
        self._rebuild_progress_cache()
        self.endResetModel()

        self.rebuild_cpm_schedule()
        self.rebuild_rollups()

    def set_db_manager(self, db_manager: Any) -> None:
        """Store DB handle for rollup precomputation; triggers rebuild."""
        self._db_manager = db_manager
        self.rebuild_cpm_schedule()
        self.rebuild_rollups()

    @property
    def cpm_result(self) -> Optional[Any]:
        """Returns the precomputed SchedulingResult or None."""
        return self._cpm_result

    def set_cpm_result(self, cpm_result: Optional[Any]) -> None:
        """Explicitly assigns CPM result (used in unit tests / mocks)."""
        self._cpm_result = cpm_result
        self._rebuild_summary_cpm()

    def get_variance(self, key: EntityRef) -> Optional[Any]:
        """Returns precomputed TaskVarianceResult for key (O(1))."""
        return self._variance_by_key.get(key)

    def get_summary_variance(self, key: EntityRef) -> Optional[Dict[str, Any]]:
        """Returns precomputed summary variance dict for parent key (O(1))."""
        return self._summary_variance_by_key.get(key)

    def get_project_variance_summary(self) -> Optional[Any]:
        """Returns precomputed ProjectVarianceSummary for active project (O(1))."""
        return self._project_variance_summary

    def _cpm_node_for_key(self, key: EntityRef) -> Optional[Any]:
        """Typed CPM lookup. Prevents task/subtask integer ID collisions."""
        if self._cpm_result is None:
            return None
        try:
            return cpm_node_for_key(self._cpm_result, key)
        except Exception:
            return None

    def _cpm_key_in_cycles(self, key: EntityRef) -> bool:
        if self._cpm_result is None:
            return False
        try:
            return bool(cpm_key_in_cycles(self._cpm_result, key))
        except Exception:
            return False

    def rebuild_cpm_schedule(self) -> None:
        """
        Precomputes professional CPM schedule and baseline variance results for current project tasks.
        O(V + E) single pass. Cached in self._cpm_result, self._variance_by_key, self._summary_variance_by_key.
        No DB queries during view rendering or paintEvent.
        """
        self._variance_by_key.clear()
        self._summary_variance_by_key.clear()
        self._project_variance_summary = None
        self._task_cache = {}

        if CPMSchedulingService is None:
            self._cpm_result = None
            self._summary_cpm_by_key = {}
            return

        tasks: List[Any] = []
        if self._db_manager is None or self._snapshot.project_id is None:
            # Fallback for mock snapshots: synthesize tasks from snapshot nodes
            if self._snapshot.nodes_by_key:
                from todo_bird_app.models.task import Task
                for n in self._snapshot.nodes_by_key.values():
                    if n.key.entity_type == "task":
                        t = Task(
                            id=n.key.entity_id,
                            project_id=self._snapshot.project_id,
                            title=n.title,
                            status=n.status,
                            planned_date=getattr(n, "planned_date", None),
                            due_date=getattr(n, "due_date", None),
                            planned_start_time=getattr(n, "planned_start_time", None),
                            planned_end_time=getattr(n, "planned_end_time", None),
                            estimated_duration=getattr(n, "estimated_duration", 0),
                            dependencies=getattr(n, "dependencies", []),
                            baseline_start=getattr(n, "baseline_start", None),
                            baseline_finish=getattr(n, "baseline_finish", None),
                            baseline_duration_minutes=getattr(n, "baseline_duration_minutes", None),
                            baseline_planned_effort_minutes=getattr(n, "baseline_planned_effort_minutes", None),
                            constraint_type=getattr(n, "constraint_type", "ASAP") or "ASAP",
                            constraint_datetime=getattr(n, "constraint_datetime", None),
                            deadline_datetime=getattr(n, "deadline_datetime", None),
                        )
                        tasks.append(t)
                try:
                    self._task_cache = {int(t.id): t for t in tasks if t.id is not None}
                    self._cpm_result = CPMSchedulingService.calculate_schedule(tasks, project_id=self._snapshot.project_id)
                except Exception as e:
                    logger.debug(f"rebuild_cpm_schedule fallback failed: {e}")
                    self._cpm_result = None
            else:
                self._cpm_result = None
                self._summary_cpm_by_key = {}
        else:
            try:
                raw_tasks = self._db_manager.get_tasks_by_project(self._snapshot.project_id)
                from todo_bird_app.models.task import Task
                for item in raw_tasks:
                    if isinstance(item, Task):
                        tasks.append(item)
                    elif isinstance(item, dict):
                        try:
                            tasks.append(Task.from_row(item))
                        except Exception:
                            tasks.append(Task(
                                id=item.get("id"),
                                project_id=item.get("project_id"),
                                title=item.get("title", ""),
                                status=item.get("status", "Planned"),
                                planned_date=item.get("planned_date"),
                                due_date=item.get("due_date"),
                                planned_start_time=item.get("planned_start_time"),
                                planned_end_time=item.get("planned_end_time"),
                                estimated_duration=item.get("estimated_duration", 0),
                                dependencies=item.get("dependencies", []),
                                baseline_start=item.get("baseline_start"),
                                baseline_finish=item.get("baseline_finish"),
                                baseline_duration_minutes=item.get("baseline_duration_minutes"),
                                baseline_planned_effort_minutes=item.get("baseline_planned_effort_minutes"),
                                constraint_type=item.get("constraint_type", "ASAP") or "ASAP",
                                constraint_datetime=item.get("constraint_datetime"),
                                deadline_datetime=item.get("deadline_datetime"),
                            ))
                self._task_cache = {int(t.id): t for t in tasks if t.id is not None}

                proj_cal = None
                if hasattr(self._db_manager, "get_project_calendar") and self._snapshot.project_id:
                    from todo_bird_app.services.schedule_calendar_service import (
                        effective_project_calendar_from_db,
                    )
                    proj_cal = effective_project_calendar_from_db(
                        self._db_manager,
                        self._snapshot.project_id,
                    )

                if calculate_wbs_cpm is not None:
                    self._cpm_result = calculate_wbs_cpm(
                        self._snapshot,
                        self._db_manager,
                        project_calendar=proj_cal,
                    )
                else:
                    self._cpm_result = CPMSchedulingService.calculate_schedule(
                        tasks, project_id=self._snapshot.project_id, project_calendar=proj_cal
                    )
            except Exception as e:
                logger.warning(f"WBSItemModel rebuild_cpm_schedule failed: {e}")
                self._cpm_result = None

        self._rebuild_summary_cpm()

        # Phase 2D: Compute schedule baseline variances
        if ScheduleVarianceService is not None and tasks:
            try:
                proj_obj = None
                if self._db_manager is not None and hasattr(self._db_manager, "get_project") and self._snapshot.project_id:
                    from todo_bird_app.models.project import Project
                    p_raw = self._db_manager.get_project(self._snapshot.project_id)
                    if p_raw:
                        proj_obj = Project.from_row(p_raw) if isinstance(p_raw, dict) else p_raw

                var_map, summary = ScheduleVarianceService.calculate_project_variance(
                    tasks,
                    cpm_result=self._cpm_result,
                    project=proj_obj,
                )
                self._project_variance_summary = summary
                for tid, var_res in var_map.items():
                    self._variance_by_key[EntityRef("task", tid)] = var_res

                # Compute variance for subtask leaves
                if self._db_manager is not None:
                    wanted_subtasks = [
                        k.entity_id for k in self._snapshot.nodes_by_key
                        if k.entity_type == "subtask"
                    ]
                    if wanted_subtasks:
                        with self._db_manager.get_connection() as conn:
                            cur = conn.cursor()
                            placeholders = ",".join("?" for _ in wanted_subtasks)
                            cur.execute(f"SELECT * FROM subtasks WHERE id IN ({placeholders});", tuple(wanted_subtasks))
                            for s_row in cur.fetchall():
                                sid = s_row["id"]
                                row_keys = s_row.keys() if hasattr(s_row, "keys") else []
                                stask = Task(
                                    id=sid,
                                    title=s_row["title"] or "",
                                    planned_date=s_row["planned_date"] if "planned_date" in row_keys else None,
                                    due_date=s_row["due_date"] if "due_date" in row_keys else None,
                                    planned_start_time=s_row["planned_start_time"] if "planned_start_time" in row_keys else None,
                                    planned_end_time=s_row["planned_end_time"] if "planned_end_time" in row_keys else None,
                                    estimated_duration=s_row["estimated_duration"] if "estimated_duration" in row_keys else 0,
                                    baseline_start=s_row["baseline_start"] if "baseline_start" in row_keys else None,
                                    baseline_finish=s_row["baseline_finish"] if "baseline_finish" in row_keys else None,
                                    baseline_duration_minutes=s_row["baseline_duration_minutes"] if "baseline_duration_minutes" in row_keys else None,
                                    baseline_planned_effort_minutes=s_row["baseline_planned_effort_minutes"] if "baseline_planned_effort_minutes" in row_keys else None,
                                )
                                s_var = ScheduleVarianceService.calculate_task_variance(stask, None)
                                self._variance_by_key[EntityRef.subtask(sid)] = s_var

                self._rebuild_summary_variances()
            except Exception as e:
                logger.warning(f"WBSItemModel baseline variance calculation failed: {e}")

    def _rebuild_summary_cpm(self) -> None:
        """Precompute derived CPM summary envelopes for WBS parent rows."""
        if build_wbs_cpm_summary_by_key is None or self._cpm_result is None:
            self._summary_cpm_by_key = {}
            return
        try:
            self._summary_cpm_by_key = build_wbs_cpm_summary_by_key(
                self._snapshot,
                self._cpm_result,
            )
        except Exception as exc:
            logger.debug("WBSItemModel summary CPM rebuild failed: %s", exc)
            self._summary_cpm_by_key = {}

    @staticmethod
    def _summary_health_text(summary_cpm: Any, rollup: Any = None) -> str:
        if summary_cpm is None:
            return "N/A (Summary)"
        if getattr(summary_cpm, "contains_cycle", False):
            return "Blocked (Cycle)"
        missing = int(getattr(rollup, "missing_schedule_count", 0) or 0) if rollup is not None else 0
        blocked = int(getattr(summary_cpm, "blocked_leaf_count", 0) or 0)
        if missing > 0:
            return f"At Risk ({missing} unscheduled)"
        if blocked > 0:
            return "At Risk"
        if int(getattr(summary_cpm, "schedulable_leaf_count", 0) or 0) > 0:
            return "Healthy"
        return "N/A (Summary)"

    def _rebuild_summary_variances(self) -> None:
        """
        Precompute summary baseline start, finish, and variances for parent WBS nodes (O(n)).
        Summary baseline start = min(child baseline starts).
        Summary baseline finish = max(child baseline finishes).
        """
        self._summary_variance_by_key.clear()
        if not self._snapshot.nodes_by_key:
            return

        sorted_nodes = sorted(
            self._snapshot.nodes_by_key.values(),
            key=lambda n: n.depth,
            reverse=True,
        )

        for node in sorted_nodes:
            if not node.has_children:
                continue
            child_keys = self._snapshot.children_by_parent.get(node.key, [])
            b_starts = []
            b_finishes = []
            for ck in child_keys:
                c_node = self._snapshot.nodes_by_key.get(ck)
                if not c_node:
                    continue
                if c_node.has_children:
                    s_data = self._summary_variance_by_key.get(ck)
                    if s_data and s_data.get("baseline_start") and s_data.get("baseline_finish"):
                        b_starts.append(s_data["baseline_start"])
                        b_finishes.append(s_data["baseline_finish"])
                else:
                    t_var = self._variance_by_key.get(ck)
                    if t_var and t_var.has_baseline and t_var.baseline_start and t_var.baseline_finish:
                        b_starts.append(t_var.baseline_start)
                        b_finishes.append(t_var.baseline_finish)

            if b_starts and b_finishes:
                s_b_start = min(b_starts)
                s_b_finish = max(b_finishes)
                rollup = self._rollups.get(node.key)
                s_curr_start = rollup.planned_start if rollup else None
                s_curr_finish = rollup.planned_finish if rollup else None
                s_start_var = int((s_curr_start - s_b_start).total_seconds() / 60) if (s_curr_start and s_b_start) else None
                s_finish_var = int((s_curr_finish - s_b_finish).total_seconds() / 60) if (s_curr_finish and s_b_finish) else None
                self._summary_variance_by_key[node.key] = {
                    "baseline_start": s_b_start,
                    "baseline_finish": s_b_finish,
                    "start_variance_minutes": s_start_var,
                    "finish_variance_minutes": s_finish_var,
                }

    def rebuild_rollups(self) -> None:
        """
        Precompute rollups for current snapshot via central authority.
        O(n) post-order single pass, cached by (project_id, revision, data_revision).
        No DB mutation. Safe to call repeatedly — uses WBSRollupService cache.
        """
        if WBSRollupService is None:
            logger.debug("WBSItemModel: WBSRollupService unavailable, rollups empty")
            self._rollups = {}
            self._snapshot_rollup_valid = False
            return
        if self._db_manager is None:
            self._rollups = {}
            self._snapshot_rollup_valid = False
            return
        if not self._snapshot.nodes_by_key:
            self._rollups = {}
            self._snapshot_rollup_valid = True
            return
        try:
            rollups = WBSRollupService.compute_all_rollups(
                self._snapshot, self._db_manager, cpm_result=self._cpm_result
            )
            self._rollups = dict(rollups) if rollups else {}
            self._snapshot_rollup_valid = True
            self._rebuild_summary_variances()
        except Exception as e:  # pragma: no cover — defensive
            logger.warning(f"WBSItemModel rebuild_rollups failed: {e}")
            self._rollups = {}
            self._snapshot_rollup_valid = False

    def load_project(self, db_manager: Any, project_id: Optional[int] = None):
        """Loads the snapshot via WBSService and rebuilds rollups."""
        self._db_manager = db_manager
        snap = WBSService.build_project_hierarchy(db_manager, project_id=project_id)
        # set_snapshot clears rollups and rebuilds progress cache; then we rebuild rollups
        self.beginResetModel()
        self._snapshot = snap
        self._rollups = {}
        self._snapshot_rollup_valid = False
        self._rebuild_row_cache()
        self._rebuild_progress_cache()
        self.endResetModel()
        self.rebuild_cpm_schedule()
        self.rebuild_rollups()
        # Optional: wire invalidation signals if TaskController is available
        try:
            if WBSRollupService is not None and hasattr(WBSRollupService, "wire_signals"):
                # Attempt to find a controller singleton — non-fatal if absent
                import importlib

                for mod_name in ("todo_bird_app.controllers.task_controller", "todo_bird_app.services.task_controller"):
                    try:
                        mod = importlib.import_module(mod_name)
                        ctrl = getattr(mod, "TaskController", None)
                        if ctrl is not None:
                            # singleton accessor may be get_instance() or instance
                            inst = None
                            if hasattr(ctrl, "get_instance"):
                                try:
                                    inst = ctrl.get_instance()
                                except Exception:
                                    inst = None
                            if inst is not None:
                                WBSRollupService.wire_signals(self._snapshot, inst)
                                break
                    except Exception:
                        continue
        except Exception:
            pass

    def _rebuild_row_cache(self) -> None:
        """
        Precompute canonical sibling row for every WBS EntityRef.

        Root rows come from snapshot.root_keys.
        Nested rows come from snapshot.children_by_parent.

        Complexity:
            rebuild: O(n)
            lookup:  O(1)

        Presentation/indexing metadata only — no DB mutation.
        """
        self._row_by_key.clear()

        for row, key in enumerate(
            self._snapshot.root_keys
        ):
            self._row_by_key[key] = row

        for sibling_keys in (
            self._snapshot.children_by_parent.values()
        ):
            for row, key in enumerate(
                sibling_keys
            ):
                self._row_by_key[key] = row

    def _rebuild_progress_cache(self):
        """Precomputes simple progress values without DB overhead."""
        self._progress_cache.clear()
        for key, node in self._snapshot.nodes_by_key.items():
            if node.is_completed:
                self._progress_cache[key] = 100
            elif node.status and node.status.strip().lower() in {"in progress", "in_progress"}:
                # DB rows store the canonical value "In Progress"; the old
                # exact "in_progress" comparison never matched, so every
                # in-progress leaf rendered 0%.
                self._progress_cache[key] = 50
            else:
                self._progress_cache[key] = 0

    def get_progress(self, key: EntityRef) -> int:
        """
        Returns display progress for key.
        For summary nodes with available rollup, returns rolled weight;
        otherwise returns stored leaf cache (child truth untouched).
        """
        node = self._snapshot.nodes_by_key.get(key)
        if node is not None and node.has_children and key in self._rollups:
            try:
                return int(self._rollups[key].progress_percent)
            except Exception:
                pass
        return self._progress_cache.get(key, 0)

    # ------------------------------------------------------------------
    # Rollup accessors (stable API for Phase 1D Gantt/Dashboard)
    # ------------------------------------------------------------------

    def get_rollup(self, key: EntityRef) -> Optional[Any]:
        """Returns RollupResult for key or None (O(1)). Never queries DB."""
        return self._rollups.get(key)

    def get_all_rollups(self) -> Dict[Any, Any]:
        """Returns shallow copy of precomputed rollups dict (O(1) access)."""
        return dict(self._rollups)

    def get_project_rollup(self) -> Optional[Any]:
        """Project-level aggregate via central authority (no duplicate calc)."""
        if WBSRollupService is None or self._db_manager is None:
            return None
        try:
            return WBSRollupService.get_project_rollup(self._snapshot, self._db_manager)
        except Exception as e:
            logger.debug(f"get_project_rollup failed: {e}")
            return None

    # ------------------------------------------------------------------
    # QAbstractItemModel Invariants
    # ------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            if parent.column() != 0:
                return 0
            parent_node: WBSNode = parent.internalPointer()
            if not parent_node:
                return 0
            children = self._snapshot.children_by_parent.get(parent_node.key, [])
            return len(children)
        else:
            return len(self._snapshot.root_keys)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return self.COLUMN_COUNT

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if parent.isValid():
            parent_node: WBSNode = parent.internalPointer()
            children = self._snapshot.children_by_parent.get(parent_node.key, [])
            if 0 <= row < len(children):
                child_key = children[row]
                child_node = self._snapshot.nodes_by_key.get(child_key)
                if child_node:
                    return self.createIndex(row, column, child_node)
        else:
            if 0 <= row < len(self._snapshot.root_keys):
                root_key = self._snapshot.root_keys[row]
                root_node = self._snapshot.nodes_by_key.get(root_key)
                if root_node:
                    return self.createIndex(row, column, root_node)

        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()

        node: WBSNode = index.internalPointer()
        if not node or node.parent_key is None:
            return QModelIndex()

        parent_node = self._snapshot.nodes_by_key.get(node.parent_key)
        if not parent_node:
            return QModelIndex()

        # Phase 1F.2:
        # Parent row is precomputed from canonical snapshot order.
        row = self._row_by_key.get(
            parent_node.key
        )

        if row is None:
            return QModelIndex()

        return self.createIndex(
            row,
            0,
            parent_node,
        )

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None

        node: WBSNode = index.internalPointer()
        if not node:
            return None

        col = index.column()
        key = node.key

        # 1. Custom Roles — rollup-aware
        if role == self.NodeKeyRole:
            return node.key
        elif role == self.WBSCodeRole:
            return node.wbs_code
        elif role == self.TitleRole:
            return node.title
        elif role == self.StatusRole:
            return node.status or "planned"
        elif role == self.ProgressRole:
            # Summary: rolled weighted progress; leaf: stored cache
            if node.has_children and key in self._rollups:
                try:
                    return int(self._rollups[key].progress_percent)
                except Exception:
                    return self.get_progress(key)
            return self.get_progress(key)
        elif role == self.DepthRole:
            return node.depth
        elif role == self.HasChildrenRole:
            return node.has_children
        elif role == self.IsMilestoneRole:
            return node.is_milestone
        elif role == self.ProjectIdRole:
            return node.project_id
        elif role == self.EntityTypeRole:
            return node.key.entity_type
        elif role == self.StableEntityIdRole:
            return node.key.entity_id
        elif role == self.NodeObjectRole:
            return node

        # Planned/Actual rollup roles — wired to derived rollups, not DB mutation
        # For O(1) paint path, all read from precomputed _rollups dict.
        elif role == self.PlannedStartRole:
            r = self._rollups.get(key)
            if r is not None and r.planned_start is not None:
                try:
                    return r.planned_start.isoformat()
                except Exception:
                    return str(r.planned_start)
            return None
        elif role == self.PlannedFinishRole:
            r = self._rollups.get(key)
            if r is not None and r.planned_finish is not None:
                try:
                    return r.planned_finish.isoformat()
                except Exception:
                    return str(r.planned_finish)
            return None
        elif role == self.PlannedEffortRole:
            r = self._rollups.get(key)
            if r is not None:
                return int(r.planned_effort_minutes)
            # leaf fallback: no rollup yet — return 0 (child truth untouched)
            return 0 if not node.has_children else 0
        elif role == self.ActualEffortRole:
            r = self._rollups.get(key)
            if r is not None:
                return int(r.actual_effort_minutes)
            return 0

        # Explicit rollup synonym roles (Phase 1C new, for delegate clarity)
        elif role == self.RollupProgressRole:
            r = self._rollups.get(key)
            if r is not None:
                return int(r.progress_percent)
            return self.get_progress(key)
        elif role == self.RollupPlannedEffortRole:
            r = self._rollups.get(key)
            return int(r.planned_effort_minutes) if r is not None else 0
        elif role == self.RollupActualEffortRole:
            r = self._rollups.get(key)
            return int(r.actual_effort_minutes) if r is not None else 0
        elif role == self.RollupPlannedStartRole:
            r = self._rollups.get(key)
            if r is not None and r.planned_start is not None:
                try:
                    return r.planned_start.isoformat()
                except Exception:
                    return str(r.planned_start)
            return None
        elif role == self.RollupPlannedFinishRole:
            r = self._rollups.get(key)
            if r is not None and r.planned_finish is not None:
                try:
                    return r.planned_finish.isoformat()
                except Exception:
                    return str(r.planned_finish)
            return None
        elif role == self.RollupActualStartRole:
            r = self._rollups.get(key)
            if r is not None and r.actual_start is not None:
                try:
                    return r.actual_start.isoformat()
                except Exception:
                    return str(r.actual_start)
            return None
        elif role == self.RollupActualFinishRole:
            r = self._rollups.get(key)
            if r is not None and r.actual_finish is not None:
                try:
                    return r.actual_finish.isoformat()
                except Exception:
                    return str(r.actual_finish)
            return None
        elif role == self.RollupResultRole:
            return self._rollups.get(key)
        elif role == self.RollupLeafCountRole:
            r = self._rollups.get(key)
            return int(r.leaf_count) if r is not None else 0
        elif role == self.RollupDataRole:
            return self._rollups.get(key)

        # 1c. Phase 2B Schedule Intelligence Roles (O(1) dictionary access)
        cpm_node = self._cpm_node_for_key(node.key)
        cpm_in_cycle = self._cpm_key_in_cycles(node.key)
        summary_cpm = self._summary_cpm_by_key.get(key) if node.has_children else None

        if role == self.CPMTotalFloatRole:
            if summary_cpm is not None:
                return None
            return cpm_node.total_float_minutes if cpm_node else None
        elif role == self.CPMFreeFloatRole:
            if summary_cpm is not None:
                return None
            return cpm_node.free_float_minutes if cpm_node else None
        elif role == self.CPMCriticalRole:
            if summary_cpm is not None:
                return bool(getattr(summary_cpm, "contains_critical", False))
            return cpm_node.is_critical if cpm_node else False
        elif role == self.CPMEarliestStartRole:
            if summary_cpm is not None:
                return getattr(summary_cpm, "earliest_start", None)
            return cpm_node.earliest_start if cpm_node else None
        elif role == self.CPMEarliestFinishRole:
            if summary_cpm is not None:
                return getattr(summary_cpm, "earliest_finish", None)
            return cpm_node.earliest_finish if cpm_node else None
        elif role == self.CPMLatestStartRole:
            if summary_cpm is not None:
                return getattr(summary_cpm, "latest_start", None)
            return cpm_node.latest_start if cpm_node else None
        elif role == self.CPMLatestFinishRole:
            if summary_cpm is not None:
                return getattr(summary_cpm, "latest_finish", None)
            return cpm_node.latest_finish if cpm_node else None
        elif role == self.CPMDiagnosticsRole:
            if summary_cpm is not None:
                return [
                    getattr(code, "value", str(code))
                    for code in getattr(summary_cpm, "diagnostic_codes", ()) or ()
                ]
            return [d.value for d in cpm_node.diagnostic_codes] if cpm_node else []
        elif role == self.CPMSchedulableRole:
            if summary_cpm is not None:
                return bool(getattr(summary_cpm, "schedulable", False))
            return cpm_node.schedulable if cpm_node else False
        elif role == self.CPMNodeResultRole:
            if summary_cpm is not None:
                return None
            return cpm_node
        elif role == self.CPMSummaryResultRole:
            return summary_cpm

        # 1d. Phase 2D Schedule Baseline & Variance Roles (O(1) dictionary access)
        var_res = self._variance_by_key.get(key)
        sum_var = self._summary_variance_by_key.get(key)

        if role == self.BaselineStartRole:
            if node.has_children and sum_var and sum_var.get("baseline_start"):
                return sum_var["baseline_start"].isoformat()
            if var_res and var_res.has_baseline and var_res.baseline_start:
                return var_res.baseline_start.isoformat()
            return None
        elif role == self.BaselineFinishRole:
            if node.has_children and sum_var and sum_var.get("baseline_finish"):
                return sum_var["baseline_finish"].isoformat()
            if var_res and var_res.has_baseline and var_res.baseline_finish:
                return var_res.baseline_finish.isoformat()
            return None
        elif role == self.StartVarianceRole:
            if node.has_children and sum_var:
                return sum_var.get("start_variance_minutes")
            if var_res and var_res.has_baseline:
                return var_res.start_variance_minutes
            return None
        elif role == self.FinishVarianceRole:
            if node.has_children and sum_var:
                return sum_var.get("finish_variance_minutes")
            if var_res and var_res.has_baseline:
                return var_res.finish_variance_minutes
            return None
        elif role == self.DurationVarianceRole:
            if var_res and var_res.has_baseline:
                return var_res.duration_variance_minutes
            return None
        elif role == self.BaselineEffortRole:
            if var_res and var_res.has_baseline:
                return var_res.baseline_planned_effort_minutes
            return None
        elif role == self.EffortVarianceRole:
            if var_res and var_res.has_baseline:
                return var_res.effort_variance_minutes
            return None
        elif role == self.VarianceResultRole:
            return var_res

        # 1e. Phase 2E Schedule Constraints & Deadlines Roles
        task_obj = None
        if self._db_manager and node.key.entity_type == "task":
            # Direct access if available in snapshot or node
            task_obj = getattr(node, "_task_obj", None)
            if task_obj is None and hasattr(self, "_task_cache") and node.key.entity_id in self._task_cache:
                task_obj = self._task_cache[node.key.entity_id]

        c_type_val = getattr(task_obj, "constraint_type", "ASAP") if task_obj else "ASAP"
        c_dt_val = getattr(task_obj, "constraint_datetime", None) if task_obj else None
        d_dt_val = getattr(task_obj, "deadline_datetime", None) if task_obj else None

        if role == self.ConstraintTypeRole:
            return c_type_val
        elif role == self.ConstraintDateRole:
            return c_dt_val
        elif role == self.DeadlineDateRole:
            return d_dt_val
        elif role == self.DeadlineVarianceRole:
            if d_dt_val and cpm_node and cpm_node.earliest_finish:
                d_parsed = parse_constraint_datetime(d_dt_val)
                if d_parsed:
                    return int((cpm_node.earliest_finish - d_parsed).total_seconds() // 60)
            return None
        elif role == self.ConstraintStatusRole:
            if cpm_node and cpm_node.diagnostic_codes:
                if DiagnosticCode and DiagnosticCode.CONSTRAINT_CONFLICT in cpm_node.diagnostic_codes:
                    return "Conflicted"
                if DiagnosticCode and DiagnosticCode.CONSTRAINT_DATE_MISSING in cpm_node.diagnostic_codes:
                    return "Missing Date"
                if DiagnosticCode and DiagnosticCode.DEADLINE_MISSED in cpm_node.diagnostic_codes:
                    return "Deadline Missed"
                if DiagnosticCode and DiagnosticCode.DEADLINE_AT_RISK in cpm_node.diagnostic_codes:
                    return "Deadline At Risk"
            return "OK" if c_type_val != "ASAP" or d_dt_val else "—"

        # 2. Display Role
        if role == Qt.DisplayRole:
            if col == self.COL_WBS:
                return node.wbs_code
            elif col == self.COL_TITLE:
                return node.title
            elif col == self.COL_STATUS:
                return (node.status or "planned").replace("_", " ").title()
            elif col == self.COL_PROGRESS:
                return f"{self.get_progress(node.key)}%"
            elif col == self.COL_CRITICAL:
                if node.has_children:
                    return getattr(summary_cpm, "critical_label", "N/A (Summary)")
                if not cpm_node or not cpm_node.schedulable or cpm_in_cycle:
                    return "Blocked (Cycle)" if cpm_in_cycle else "Not analyzed"
                return "● Critical" if cpm_node.is_critical else "Non-critical"
            elif col == self.COL_TOTAL_FLOAT:
                if node.has_children:
                    return "N/A (Summary)"
                if not cpm_node or not cpm_node.schedulable:
                    return "—"
                return format_float_duration(cpm_node.total_float_minutes)
            elif col == self.COL_FREE_FLOAT:
                if node.has_children:
                    return "N/A (Summary)"
                if not cpm_node or not cpm_node.schedulable:
                    return "—"
                return format_float_duration(cpm_node.free_float_minutes)
            elif col == self.COL_ES:
                if node.has_children:
                    value = getattr(summary_cpm, "earliest_start", None)
                    return format_cpm_datetime(value) if value is not None else "N/A (Summary)"
                return format_cpm_datetime(cpm_node.earliest_start) if cpm_node and cpm_node.schedulable else "—"
            elif col == self.COL_EF:
                if node.has_children:
                    value = getattr(summary_cpm, "earliest_finish", None)
                    return format_cpm_datetime(value) if value is not None else "N/A (Summary)"
                return format_cpm_datetime(cpm_node.earliest_finish) if cpm_node and cpm_node.schedulable else "—"
            elif col == self.COL_LS:
                if node.has_children:
                    value = getattr(summary_cpm, "latest_start", None)
                    return format_cpm_datetime(value) if value is not None else "N/A (Summary)"
                return format_cpm_datetime(cpm_node.latest_start) if cpm_node and cpm_node.schedulable else "—"
            elif col == self.COL_LF:
                if node.has_children:
                    value = getattr(summary_cpm, "latest_finish", None)
                    return format_cpm_datetime(value) if value is not None else "N/A (Summary)"
                return format_cpm_datetime(cpm_node.latest_finish) if cpm_node and cpm_node.schedulable else "—"
            elif col == self.COL_DIAGNOSTICS:
                if node.has_children:
                    return self._summary_health_text(summary_cpm, self._rollups.get(key))
                if cpm_in_cycle:
                    return "Cycle"
                if not cpm_node:
                    return "—"
                if not cpm_node.schedulable:
                    if DiagnosticCode and (DiagnosticCode.UNSCHEDULED_NO_START in cpm_node.diagnostic_codes or DiagnosticCode.UNSCHEDULED_NO_DURATION in cpm_node.diagnostic_codes):
                        return "Unscheduled"
                    if DiagnosticCode and (DiagnosticCode.INVALID_DURATION in cpm_node.diagnostic_codes):
                        return "Invalid Duration"
                    if DiagnosticCode and (DiagnosticCode.MISSING_TASK_REFERENCE in cpm_node.diagnostic_codes):
                        return "Missing Ref"
                    return "Not analyzed"
                if cpm_node.diagnostic_codes:
                    return ", ".join(d.value.replace("_", " ").title() for d in cpm_node.diagnostic_codes)
                return "Healthy"
            elif col == self.COL_BASELINE_START:
                if node.has_children:
                    return format_cpm_datetime(sum_var["baseline_start"]) if (sum_var and sum_var.get("baseline_start")) else "—"
                if not var_res or not var_res.has_baseline:
                    return "Not Baselined"
                return format_cpm_datetime(var_res.baseline_start) if var_res.baseline_start else "—"
            elif col == self.COL_BASELINE_FINISH:
                if node.has_children:
                    return format_cpm_datetime(sum_var["baseline_finish"]) if (sum_var and sum_var.get("baseline_finish")) else "—"
                if not var_res or not var_res.has_baseline:
                    return "—"
                return format_cpm_datetime(var_res.baseline_finish) if var_res.baseline_finish else "—"
            elif col == self.COL_START_VARIANCE:
                if node.has_children:
                    return format_variance_duration(sum_var.get("start_variance_minutes")) if sum_var else "—"
                if not var_res or not var_res.has_baseline:
                    return "—"
                return format_variance_duration(var_res.start_variance_minutes)
            elif col == self.COL_FINISH_VARIANCE:
                if node.has_children:
                    return format_variance_duration(sum_var.get("finish_variance_minutes")) if sum_var else "—"
                if not var_res or not var_res.has_baseline:
                    return "—"
                return format_variance_duration(var_res.finish_variance_minutes)
            elif col == self.COL_DURATION_VARIANCE:
                if node.has_children:
                    return "—"
                if not var_res or not var_res.has_baseline:
                    return "—"
                return format_variance_duration(var_res.duration_variance_minutes)
            elif col == self.COL_CONSTRAINT:
                if node.has_children:
                    return "—"
                return str(c_type_val)
            elif col == self.COL_CONSTRAINT_DATE:
                if node.has_children:
                    return "—"
                return str(c_dt_val) if c_dt_val else "—"
            elif col == self.COL_DEADLINE:
                if node.has_children:
                    return "—"
                return str(d_dt_val) if d_dt_val else "—"
            elif col == self.COL_DEADLINE_VARIANCE:
                if node.has_children or not d_dt_val or not cpm_node or not cpm_node.earliest_finish:
                    return "—"
                d_p = parse_constraint_datetime(d_dt_val)
                if d_p:
                    v_m = int((cpm_node.earliest_finish - d_p).total_seconds() // 60)
                    return format_deadline_variance(v_m)
                return "—"
            elif col == self.COL_CONSTRAINT_STATUS:
                if node.has_children:
                    return "—"
                if cpm_node and cpm_node.diagnostic_codes:
                    if DiagnosticCode and DiagnosticCode.CONSTRAINT_CONFLICT in cpm_node.diagnostic_codes:
                        return "Conflicted"
                    if DiagnosticCode and DiagnosticCode.CONSTRAINT_DATE_MISSING in cpm_node.diagnostic_codes:
                        return "Missing Date"
                    if DiagnosticCode and DiagnosticCode.DEADLINE_MISSED in cpm_node.diagnostic_codes:
                        return "Missed"
                return "Satisfied" if c_type_val != "ASAP" or d_dt_val else "—"

        # Tooltip Role
        if role == Qt.ToolTipRole:
            if not node.has_children and cpm_node:
                if not cpm_node.schedulable or cpm_in_cycle:
                    diag_str = "Dependency cycle detected" if cpm_in_cycle else (
                        ", ".join(d.value.replace("_", " ").title() for d in cpm_node.diagnostic_codes) or "Missing planned dates/duration"
                    )
                    return (
                        f"<b>{node.title}</b><br/>"
                        f"📊 Schedule: <i>Not analyzed / Blocked</i><br/>"
                        f"⚠️ Reason: {diag_str}"
                    )
                crit_str = "Yes (True Critical)" if cpm_node.is_critical else "No"
                tf_str = format_float_duration(cpm_node.total_float_minutes)
                ff_str = format_float_duration(cpm_node.free_float_minutes)
                es_str = format_cpm_datetime(cpm_node.earliest_start)
                ef_str = format_cpm_datetime(cpm_node.earliest_finish)
                ls_str = format_cpm_datetime(cpm_node.latest_start)
                lf_str = format_cpm_datetime(cpm_node.latest_finish)
                b_str = "Not Baselined"
                if var_res and var_res.has_baseline:
                    b_s = format_cpm_datetime(var_res.baseline_start)
                    b_f = format_cpm_datetime(var_res.baseline_finish)
                    v_f = format_variance_duration(var_res.finish_variance_minutes)
                    b_str = f"{b_s} → {b_f} (Var: {v_f})"
                return (
                    f"<b>{node.title}</b><br/>"
                    f"🎯 Critical: <b>{crit_str}</b><br/>"
                    f"⏳ Total Float: {tf_str} | Free Float: {ff_str}<br/>"
                    f"⏱️ ES: {es_str} | EF: {ef_str}<br/>"
                    f"⏱️ LS: {ls_str} | LF: {lf_str}<br/>"
                    f"📐 Baseline 1: {b_str}"
                )

        # Accessible Text Role
        if role in (Qt.AccessibleTextRole, Qt.AccessibleDescriptionRole):
            if not node.has_children and cpm_node:
                if cpm_node.is_critical:
                    return f"Critical task {node.title}. Total float zero."
                elif cpm_node.schedulable:
                    return f"Task {node.title}. Total float {format_float_duration(cpm_node.total_float_minutes)}."
                else:
                    return f"Task {node.title}. Schedule not analyzed."

        # 3. Text Alignment Role
        if role == Qt.TextAlignmentRole:
            if col in (self.COL_WBS, self.COL_TITLE, self.COL_STATUS, self.COL_CRITICAL, self.COL_DIAGNOSTICS, self.COL_BASELINE_START, self.COL_BASELINE_FINISH):
                return int(Qt.AlignVCenter | Qt.AlignLeft)
            elif col in (self.COL_PROGRESS, self.COL_TOTAL_FLOAT, self.COL_FREE_FLOAT, self.COL_ES, self.COL_EF, self.COL_LS, self.COL_LF, self.COL_START_VARIANCE, self.COL_FINISH_VARIANCE, self.COL_DURATION_VARIANCE):
                return int(Qt.AlignVCenter | Qt.AlignRight)

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        # Non-editable snapshot model.
        #
        # Phase 1E.4:
        # Items may START a drag, but this model deliberately exposes
        # no ItemIsDropEnabled flag and no dropMimeData()/moveRows().
        # Persistent hierarchy mutation belongs to WBSMutationService.
        return (
            Qt.ItemIsEnabled
            | Qt.ItemIsSelectable
            | Qt.ItemIsDragEnabled
        )

    # ------------------------------------------------------------------
    # Helper APIs
    # ------------------------------------------------------------------

    def node_from_index(self, index: QModelIndex) -> Optional[WBSNode]:
        if index.isValid():
            return index.internalPointer()
        return None

    def index_from_key(self, key: Any, column: int = 0) -> QModelIndex:
        """
        Fast ancestor path traversal to resolve QModelIndex for an EntityRef in O(depth).
        """
        if isinstance(key, str):
            try:
                key = EntityRef.from_string(key)
            except Exception:
                return QModelIndex()

        node = self._snapshot.nodes_by_key.get(key)
        if not node:
            return QModelIndex()

        # Build path from target node up to root
        chain: List[WBSNode] = []
        curr: Optional[WBSNode] = node
        while curr is not None:
            chain.append(curr)
            if curr.parent_key is None:
                break
            curr = self._snapshot.nodes_by_key.get(curr.parent_key)

        chain.reverse()  # root first, target last

        # Descend tree model indices.
        #
        # Phase 1F.2:
        # Every sibling row is an O(1) _row_by_key lookup.
        parent_idx = QModelIndex()

        for depth_node in chain:
            row = self._row_by_key.get(
                depth_node.key
            )

            if row is None:
                return QModelIndex()

            target_col = (
                column
                if depth_node.key == key
                else 0
            )

            parent_idx = self.index(
                row,
                target_col,
                parent_idx,
            )

            if not parent_idx.isValid():
                return QModelIndex()

        return parent_idx
