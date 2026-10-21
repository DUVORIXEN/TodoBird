from __future__ import annotations

import json
from datetime import datetime, timedelta, time
from typing import Dict, List, Set, Tuple, Optional, Any

from todo_bird_app.models.task import Task, TaskStatus, TaskPriority, TaskCategory


class GanttDependencyEngine:
    """
    Single authority for Gantt dependency intelligence.

    Current relationship type:
        Finish -> Start (FS)

    No database schema is required because Task.dependencies already
    contains predecessor task IDs.

    Transient task attributes produced by annotate():
        gantt_dependency_violation
        gantt_dependency_cycle
        gantt_critical_path
        gantt_dependency_predecessors
        gantt_dependency_successors
    """

    CLOSED_STATUSES = {
        TaskStatus.CANCELLED,
    }

    @staticmethod
    def _parse_date(value):
        if not value:
            return None

        try:
            return datetime.strptime(
                str(value),
                "%Y-%m-%d",
            ).date()
        except Exception:
            return None

    @staticmethod
    def _parse_time(value):
        if not value:
            return None

        try:
            return datetime.strptime(
                str(value),
                "%H:%M",
            ).time()
        except Exception:
            return None

    @classmethod
    def planned_start(
        cls,
        task: Task,
    ) -> Optional[datetime]:
        day = cls._parse_date(
            task.planned_date
        )

        if day is None:
            return None

        clock = cls._parse_time(
            task.planned_start_time
        )

        if clock is None:
            clock = time(0, 0)

        return datetime.combine(
            day,
            clock,
        )

    @classmethod
    def planned_finish(
        cls,
        task: Task,
    ) -> Optional[datetime]:
        """
        Operational planned finish authority.

        Priority:
          1. due date + explicit planned end time
          2. planned date + explicit planned end time
          3. start + estimated duration
          4. due date end-of-day
          5. planned date end-of-day
        """
        planned_day = cls._parse_date(
            task.planned_date
        )

        due_day = cls._parse_date(
            task.due_date
        )

        end_clock = cls._parse_time(
            task.planned_end_time
        )

        if due_day and end_clock:
            finish = datetime.combine(
                due_day,
                end_clock,
            )

            start = cls.planned_start(
                task
            )

            # Same-day clock schedules should not accidentally become
            # multi-day merely because an unrelated Due Date is later.
            if (
                start
                and planned_day
                and due_day != planned_day
                and int(
                    task.estimated_duration
                    or 0
                ) <= 24 * 60
            ):
                same_day = datetime.combine(
                    planned_day,
                    end_clock,
                )

                if same_day > start:
                    return same_day

            return finish

        if planned_day and end_clock:
            start = cls.planned_start(
                task
            )

            finish = datetime.combine(
                planned_day,
                end_clock,
            )

            # Explicit end earlier than start means crossing midnight.
            if start and finish <= start:
                finish += timedelta(
                    days=1
                )

            return finish

        start = cls.planned_start(
            task
        )

        duration = max(
            0,
            int(
                task.estimated_duration
                or 0
            ),
        )

        if start and duration > 0:
            return (
                start
                + timedelta(
                    minutes=duration
                )
            )

        if due_day:
            return datetime.combine(
                due_day,
                time(23, 59),
            )

        if planned_day:
            return datetime.combine(
                planned_day,
                time(23, 59),
            )

        return None

    @classmethod
    def duration_minutes(
        cls,
        task: Task,
    ) -> int:
        explicit = int(
            task.estimated_duration
            or 0
        )

        if explicit > 0:
            return explicit

        start = cls.planned_start(
            task
        )

        finish = cls.planned_finish(
            task
        )

        if start and finish and finish > start:
            return max(
                1,
                int(
                    (
                        finish
                        - start
                    ).total_seconds()
                    / 60
                ),
            )

        return 1

    @classmethod
    def main_task_map(
        cls,
        tasks: List[Task],
    ) -> Dict[int, Task]:
        result = {}

        for task in tasks:
            if task.id is None:
                continue

            if getattr(
                task,
                "gantt_item_type",
                "task",
            ) != "task":
                continue

            result[
                int(task.id)
            ] = task

        return result

    @staticmethod
    def normalize_dependencies(raw_dependencies, task_id: Optional[int] = None):
        from todo_bird_app.services.cpm_scheduling_service import parse_dependency_specs
        specs = parse_dependency_specs(raw_dependencies, successor_id=task_id)
        if isinstance(raw_dependencies, (list, tuple, set)) and any(isinstance(x, dict) for x in raw_dependencies):
            return specs
        return [s.predecessor_id for s in specs]

    @classmethod
    def legacy_dependency_issues(
        cls,
        tasks: List[Task],
    ) -> List[Dict[str, object]]:
        """Read-only analysis of all graph cycles in the current task set."""
        task_map = cls.main_task_map(tasks)
        if not task_map:
            return []

        _, predecessors, successors = cls.graph(tasks)
        cycle_nodes = cls.find_cycle_nodes(task_map, successors)
        if not cycle_nodes:
            return []

        issues = []
        for task_id in sorted(cycle_nodes):
            issues.append(
                {
                    "task_id": task_id,
                    "cycle_nodes": sorted(cycle_nodes),
                }
            )

        return issues

    @classmethod
    def _build_cycle_path(cls, task_id: int, task_map: Dict[int, Task], seen=None, path=None) -> List[int]:
        if seen is None:
            seen = set()
        if path is None:
            path = []

        # `path` is the live recursion stack: revisiting one of its members is
        # a genuine back-edge (a cycle). `seen` holds nodes already proven
        # cycle-free — reaching one again via a different branch is legal
        # (diamond DAGs) and must not be reported as a cycle.
        if task_id in path:
            idx = path.index(task_id)
            return path[idx:] + [task_id]
        if task_id in seen:
            return []

        seen.add(task_id)
        path.append(task_id)

        task = task_map.get(task_id)
        if task is None:
            return []

        from todo_bird_app.services.cpm_scheduling_service import parse_dependency_specs
        specs = parse_dependency_specs(task.dependencies, successor_id=task_id)
        try:
            for spec in specs:
                dep_id = spec.predecessor_id
                if dep_id not in task_map:
                    continue
                cycle_path = cls._build_cycle_path(dep_id, task_map, seen, path)
                if cycle_path:
                    return cycle_path
        finally:
            path.pop()

        return []

    @classmethod
    def validate_proposed_dependencies(
        cls,
        task_id: Optional[int],
        candidate_ids,
        tasks: List[Task],
    ) -> Dict[str, object]:
        task_map = {int(task.id): task for task in tasks if task.id is not None}

        if task_id is None:
            return {
                "valid": False,
                "normalized_dependencies": [],
                "missing_ids": [],
                "self_reference": False,
                "cycle_nodes": [],
                "message": "Task ID is required to validate dependencies.",
            }

        from todo_bird_app.services.cpm_scheduling_service import parse_dependency_specs, DependencySpec

        # Check self-reference in raw inputs
        raw_list = candidate_ids if isinstance(candidate_ids, (list, tuple, set)) else ([candidate_ids] if candidate_ids is not None else [])
        for item in raw_list:
            if isinstance(item, DependencySpec) and item.predecessor_id == task_id:
                return {
                    "valid": False,
                    "normalized_dependencies": [],
                    "missing_ids": [],
                    "self_reference": True,
                    "cycle_nodes": [task_id],
                    "message": f"Task {task_id} cannot depend on itself.",
                }
            elif isinstance(item, dict):
                pid = int(item.get("predecessor_id") or item.get("id") or item.get("task_id") or 0)
                if pid == task_id:
                    return {
                        "valid": False,
                        "normalized_dependencies": [],
                        "missing_ids": [],
                        "self_reference": True,
                        "cycle_nodes": [task_id],
                        "message": f"Task {task_id} cannot depend on itself.",
                    }
            elif isinstance(item, (int, str)):
                try:
                    if int(item) == task_id:
                        return {
                            "valid": False,
                            "normalized_dependencies": [],
                            "missing_ids": [],
                            "self_reference": True,
                            "cycle_nodes": [task_id],
                            "message": f"Task {task_id} cannot depend on itself.",
                        }
                except (TypeError, ValueError):
                    continue

        parsed_specs = parse_dependency_specs(candidate_ids, successor_id=task_id)
        pred_ids = [s.predecessor_id for s in parsed_specs]

        # Check if candidate_ids was passed as simple ints or dicts/specs
        return_specs = isinstance(candidate_ids, (list, tuple, set)) and any(isinstance(x, (dict, DependencySpec)) for x in candidate_ids)
        normalized_return = parsed_specs if return_specs else pred_ids

        if task_id in pred_ids:
            return {
                "valid": False,
                "normalized_dependencies": normalized_return,
                "missing_ids": [],
                "self_reference": True,
                "cycle_nodes": [task_id],
                "message": f"Task {task_id} cannot depend on itself.",
            }

        if task_id not in task_map:
            task_map[task_id] = Task(id=task_id, title=f"Task {task_id}")

        missing = [dep_id for dep_id in pred_ids if dep_id not in task_map]
        if missing:
            return {
                "valid": False,
                "normalized_dependencies": normalized_return,
                "missing_ids": missing,
                "self_reference": False,
                "cycle_nodes": [],
                "cross_project_nodes": [],
                "message": (
                    "Dependency task "
                    + ", ".join(str(dep_id) for dep_id in missing)
                    + " no longer exists. Refresh the task list or remove that dependency."
                ),
            }

        # Phase 2C.1: Defense-in-depth same-project validation
        cross_project_nodes = []
        if task_id in task_map:
            current_project_id = getattr(task_map[task_id], "project_id", None)
            for dep_id in pred_ids:
                if dep_id in task_map:
                    pred_project_id = getattr(task_map[dep_id], "project_id", None)
                    if pred_project_id != current_project_id:
                        cross_project_nodes.append(dep_id)

        if cross_project_nodes:
            return {
                "valid": False,
                "normalized_dependencies": normalized_return,
                "missing_ids": [],
                "self_reference": False,
                "cycle_nodes": [],
                "cross_project_nodes": cross_project_nodes,
                "error_code": "CROSS_PROJECT_DEPENDENCY",
                "message": "Dependencies can currently be created only between tasks in the same project.",
            }

        cycle_nodes = []
        for dep_id in pred_ids:
            current_map = {
                task_id_n: Task(
                    id=task_id_n,
                    title=task.title,
                    project_id=task.project_id,
                    priority=task.priority,
                    tags=list(task.tags),
                    category=task.category,
                    description=task.description,
                    planned_date=task.planned_date,
                    due_date=task.due_date,
                    planned_start_time=task.planned_start_time,
                    planned_end_time=task.planned_end_time,
                    actual_start_time=task.actual_start_time,
                    actual_end_time=task.actual_end_time,
                    estimated_duration=task.estimated_duration,
                    actual_duration=task.actual_duration,
                    progress=task.progress,
                    notes=task.notes,
                    recurring=task.recurring,
                    dependencies=list(task.dependencies),
                    status=task.status,
                    show_in_gantt=task.show_in_gantt,
                    startup_reminder=task.startup_reminder,
                )
                for task_id_n, task in task_map.items()
            }

            current_map[task_id] = Task(
                id=task_id,
                title=current_map[task_id].title if task_id in current_map else f"Task {task_id}",
                project_id=current_map[task_id].project_id if task_id in current_map else None,
                priority=current_map[task_id].priority if task_id in current_map else TaskPriority.MEDIUM,
                tags=list(current_map[task_id].tags) if task_id in current_map else [],
                category=current_map[task_id].category if task_id in current_map else TaskCategory.WORK,
                description=current_map[task_id].description if task_id in current_map else "",
                planned_date=current_map[task_id].planned_date if task_id in current_map else None,
                due_date=current_map[task_id].due_date if task_id in current_map else None,
                planned_start_time=current_map[task_id].planned_start_time if task_id in current_map else None,
                planned_end_time=current_map[task_id].planned_end_time if task_id in current_map else None,
                actual_start_time=current_map[task_id].actual_start_time if task_id in current_map else None,
                actual_end_time=current_map[task_id].actual_end_time if task_id in current_map else None,
                estimated_duration=current_map[task_id].estimated_duration if task_id in current_map else 0,
                actual_duration=current_map[task_id].actual_duration if task_id in current_map else 0,
                progress=current_map[task_id].progress if task_id in current_map else 0,
                notes=current_map[task_id].notes if task_id in current_map else "",
                recurring=current_map[task_id].recurring if task_id in current_map else None,
                dependencies=list(pred_ids),
                status=current_map[task_id].status if task_id in current_map else TaskStatus.INBOX,
                show_in_gantt=current_map[task_id].show_in_gantt if task_id in current_map else False,
                startup_reminder=current_map[task_id].startup_reminder if task_id in current_map else False,
            )

            cycle = cls._build_cycle_path(dep_id, current_map)
            if cycle:
                cycle_nodes.extend(cycle[:-1])

        unique_cycle_nodes = []
        seen = set()
        for node in cycle_nodes:
            if node not in seen:
                seen.add(node)
                unique_cycle_nodes.append(node)

        if unique_cycle_nodes:
            ordered = sorted(unique_cycle_nodes)
            cycle_text = " -> ".join(str(node) for node in ordered)
            return {
                "valid": False,
                "normalized_dependencies": normalized_return,
                "missing_ids": [],
                "self_reference": False,
                "cycle_nodes": ordered,
                "message": (
                    "Circular dependency detected.\n\n"
                    f"{cycle_text}\n\nRemove one dependency before saving."
                ),
            }

        return {
            "valid": True,
            "normalized_dependencies": normalized_return,
            "missing_ids": [],
            "self_reference": False,
            "cycle_nodes": [],
            "message": "Dependency graph is valid.",
        }

    @classmethod
    def graph(
        cls,
        tasks: List[Task],
    ):
        task_map = cls.main_task_map(
            tasks
        )

        predecessors = {
            task_id: set()
            for task_id in task_map
        }

        successors = {
            task_id: set()
            for task_id in task_map
        }

        from todo_bird_app.services.cpm_scheduling_service import parse_dependency_specs
        for successor_id, task in task_map.items():
            specs = parse_dependency_specs(task.dependencies, successor_id=successor_id)
            for spec in specs:
                predecessor_id = spec.predecessor_id
                if (
                    predecessor_id not in task_map
                    or predecessor_id == successor_id
                ):
                    continue

                predecessors[successor_id].add(predecessor_id)
                successors[predecessor_id].add(successor_id)

        return (
            task_map,
            predecessors,
            successors,
        )

    @classmethod
    def find_cycle_nodes(
        cls,
        task_map,
        successors,
    ) -> Set[int]:
        """
        DFS cycle detection.

        We mark all nodes participating in, or directly discovered
        inside, a dependency cycle.
        """
        WHITE = 0
        GRAY = 1
        BLACK = 2

        state = {
            task_id: WHITE
            for task_id in task_map
        }

        cycle_nodes = set()
        # Iterative DFS: dependency chains can exceed Python's recursion limit
        # (a >1000-task chain previously raised RecursionError inside annotate).
        for root in task_map:
            if state[root] != WHITE:
                continue
            stack = [(root, iter(sorted(successors.get(root, set()))))]
            state[root] = GRAY
            path = [root]

            while stack:
                node, children = stack[-1]
                advanced = False
                for child in children:
                    if state[child] == WHITE:
                        state[child] = GRAY
                        path.append(child)
                        stack.append((child, iter(sorted(successors.get(child, set())))))
                        advanced = True
                        break
                    elif state[child] == GRAY:
                        try:
                            index = path.index(child)
                            cycle_nodes.update(path[index:])
                        except ValueError:
                            cycle_nodes.add(child)
                if advanced:
                    continue
                stack.pop()
                if path:
                    path.pop()
                state[node] = BLACK

        return cycle_nodes

    @classmethod
    def edge_violation(
        cls,
        predecessor: Task,
        successor: Task,
        spec: Optional[Any] = None,
    ) -> bool:
        from todo_bird_app.services.cpm_scheduling_service import parse_dependency_specs, DependencyType
        if spec is None:
            specs = parse_dependency_specs(successor.dependencies, successor_id=successor.id)
            spec = next((s for s in specs if s.predecessor_id == predecessor.id), None)

        dtype = spec.dependency_type if spec else DependencyType.FS
        lag = timedelta(minutes=spec.lag_minutes if spec else 0)

        p_start = cls.planned_start(predecessor)
        p_finish = cls.planned_finish(predecessor)
        s_start = cls.planned_start(successor)
        s_finish = cls.planned_finish(successor)

        if dtype == DependencyType.FS:
            if p_finish is None or s_start is None:
                return False
            return s_start < p_finish + lag
        elif dtype == DependencyType.SS:
            if p_start is None or s_start is None:
                return False
            return s_start < p_start + lag
        elif dtype == DependencyType.FF:
            if p_finish is None or s_finish is None:
                return False
            return s_finish < p_finish + lag
        elif dtype == DependencyType.SF:
            if p_start is None or s_finish is None:
                return False
            return s_finish < p_start + lag
        return False

    @classmethod
    def critical_path_nodes(
        cls,
        tasks,
        task_map,
        predecessors,
        successors,
        cycle_nodes,
    ) -> Set[int]:
        """
        Longest dependency path by planned effort, evaluated per
        project. This gives a practical critical-path indicator
        without inventing a project deadline.

        Isolated tasks are not marked critical.
        """
        critical = set()

        by_project = {}

        for task_id, task in task_map.items():
            by_project.setdefault(
                task.project_id,
                set(),
            ).add(
                task_id
            )

        for project_nodes in by_project.values():
            project_nodes = (
                set(project_nodes)
                - set(cycle_nodes)
            )

            if len(project_nodes) < 2:
                continue

            indegree = {}

            for node in project_nodes:
                indegree[node] = len(
                    [
                        pred
                        for pred
                        in predecessors.get(
                            node,
                            set(),
                        )
                        if pred
                        in project_nodes
                    ]
                )

            queue = sorted(
                [
                    node
                    for node, degree
                    in indegree.items()
                    if degree == 0
                ]
            )

            topo = []

            while queue:
                node = queue.pop(0)
                topo.append(node)

                for child in successors.get(
                    node,
                    set(),
                ):
                    if child not in project_nodes:
                        continue

                    indegree[child] -= 1

                    if indegree[child] == 0:
                        queue.append(
                            child
                        )

            if len(topo) != len(
                project_nodes
            ):
                continue

            longest = {}
            best_pred = {}

            for node in topo:
                own_duration = cls.duration_minutes(
                    task_map[node]
                )

                candidates = [
                    pred
                    for pred
                    in predecessors.get(
                        node,
                        set(),
                    )
                    if pred
                    in project_nodes
                ]

                if not candidates:
                    longest[node] = (
                        own_duration
                    )
                    best_pred[node] = None
                    continue

                pred = max(
                    candidates,
                    key=lambda p:
                        longest.get(
                            p,
                            0,
                        ),
                )

                longest[node] = (
                    longest.get(
                        pred,
                        0,
                    )
                    + own_duration
                )

                best_pred[node] = pred

            if not longest:
                continue

            endpoint = max(
                longest,
                key=longest.get,
            )

            chain = []

            node = endpoint

            while node is not None:
                chain.append(node)
                node = best_pred.get(
                    node
                )

            # Critical path is meaningful only when an actual
            # dependency chain exists.
            if len(chain) >= 2:
                critical.update(
                    chain
                )

        return critical

    @classmethod
    def annotate(
        cls,
        tasks: List[Task],
    ):
        (
            task_map,
            predecessors,
            successors,
        ) = cls.graph(
            tasks
        )

        cycle_nodes = (
            cls.find_cycle_nodes(
                task_map,
                successors,
            )
        )

        critical_nodes = (
            cls.critical_path_nodes(
                tasks,
                task_map,
                predecessors,
                successors,
                cycle_nodes,
            )
        )

        # Compute professional CPM schedule results (Phase 2A)
        from todo_bird_app.services.cpm_scheduling_service import CPMSchedulingService
        cpm_result = CPMSchedulingService.calculate_schedule(tasks)

        for task in tasks:
            task.gantt_dependency_violation = False
            task.gantt_dependency_cycle = False
            task.gantt_critical_path = False
            task.gantt_dependency_predecessors = []
            task.gantt_dependency_successors = []
            # Phase 2A CPM fields
            task.cpm_total_float = None
            task.cpm_free_float = None
            task.cpm_is_critical = False
            task.cpm_earliest_start = None
            task.cpm_earliest_finish = None
            task.cpm_latest_start = None
            task.cpm_latest_finish = None
            task.cpm_diagnostics = []

        for task_id, task in task_map.items():
            task.gantt_dependency_cycle = (
                task_id
                in cycle_nodes
            )

            task.gantt_critical_path = (
                task_id
                in critical_nodes
            )

            cpm_node = cpm_result.get_node(task_id)
            if cpm_node:
                task.cpm_total_float = cpm_node.total_float_minutes
                task.cpm_free_float = cpm_node.free_float_minutes
                task.cpm_is_critical = cpm_node.is_critical
                task.cpm_earliest_start = cpm_node.earliest_start
                task.cpm_earliest_finish = cpm_node.earliest_finish
                task.cpm_latest_start = cpm_node.latest_start
                task.cpm_latest_finish = cpm_node.latest_finish
                task.cpm_diagnostics = [d.value for d in cpm_node.diagnostic_codes]

            task.gantt_dependency_predecessors = sorted(
                predecessors.get(
                    task_id,
                    set(),
                )
            )

            task.gantt_dependency_successors = sorted(
                successors.get(
                    task_id,
                    set(),
                )
            )

        for successor_id, pred_ids in predecessors.items():
            successor = task_map[
                successor_id
            ]

            for predecessor_id in pred_ids:
                predecessor = task_map[
                    predecessor_id
                ]

                if cls.edge_violation(
                    predecessor,
                    successor,
                ):
                    predecessor.gantt_dependency_violation = True
                    successor.gantt_dependency_violation = True

        for task in tasks:
            cls._apply_canonical_wbs_cpm_metadata(task)

        return {
            "task_map": task_map,
            "predecessors": predecessors,
            "successors": successors,
            "cycle_nodes": cycle_nodes,
            "critical_nodes": critical_nodes,
            "cpm_result": cpm_result,
        }

    @classmethod
    def compute_cpm_schedule(cls, tasks: List[Task], project_id: Optional[int] = None):
        """Phase 2A canonical CPM scheduling calculation."""
        from todo_bird_app.services.cpm_scheduling_service import CPMSchedulingService
        return CPMSchedulingService.calculate_schedule(tasks, project_id=project_id)

    @classmethod
    def schedule_health_summary(cls, tasks: List[Task]) -> Optional[Dict[str, Any]]:
        """
        Distills the CPM engine's schedule intelligence into a compact,
        UI-facing digest for the Gantt health ribbon.

        Additive and read-only. Definitions:
        - critical: zero total float — these tasks drive the project finish
        - near_critical: 0 < total float <= 1440m (one working day of slack)
        - negative float / missed deadlines / calendar conflicts / cycles:
          straight counts of the engine's own diagnostics
        - health_score: 100 minus weighted penalties per finding
          (cycle 15, missed deadline 12, negative float 10, unschedulable 5,
          calendar conflict 4), clamped to 0..100. Verdict thresholds:
          >=80 healthy, >=55 watch, else risk.
        """
        if not tasks:
            return None

        analysis = cls.annotate(tasks)
        cpm_result = analysis["cpm_result"]
        cycle_ids = set(analysis.get("cycle_nodes", set()))

        critical = 0
        near_critical = 0
        negative_float = 0
        deadline_missed = 0
        calendar_conflict = 0
        unschedulable = 0
        near_critical_ids: List[int] = []
        negative_float_ids: List[int] = []
        deadline_missed_ids: List[int] = []

        for task in tasks:
            node = cpm_result.get_node(task.id) if task.id is not None else None
            if node is None:
                continue
            if not node.schedulable:
                unschedulable += 1
                continue
            if node.is_critical:
                critical += 1
            tf = node.total_float_minutes
            if tf is not None and 0 < tf <= 1440:
                near_critical += 1
                near_critical_ids.append(task.id)
            codes = {d.value for d in node.diagnostic_codes}
            if "NEGATIVE_FLOAT" in codes:
                negative_float += 1
                negative_float_ids.append(task.id)
            if "DEADLINE_MISSED" in codes:
                deadline_missed += 1
                deadline_missed_ids.append(task.id)
            if "CALENDAR_CONFLICT" in codes:
                calendar_conflict += 1

        score = 100
        score -= 15 * len(cycle_ids)
        score -= 12 * deadline_missed
        score -= 10 * negative_float
        score -= 5 * unschedulable
        score -= 4 * calendar_conflict
        if unschedulable >= len(tasks):
            score = min(score, 40)
        score = max(0, min(100, score))
        if score >= 80:
            verdict = "healthy"
        elif score >= 55:
            verdict = "watch"
        else:
            verdict = "risk"

        span_minutes = None
        if cpm_result.project_start and cpm_result.project_finish:
            span_minutes = int(
                (cpm_result.project_finish - cpm_result.project_start).total_seconds() // 60
            )

        return {
            "task_count": len(tasks),
            "critical": critical,
            "near_critical": near_critical,
            "near_critical_ids": sorted(near_critical_ids),
            "negative_float": negative_float,
            "negative_float_ids": sorted(negative_float_ids),
            "deadline_missed": deadline_missed,
            "deadline_missed_ids": sorted(deadline_missed_ids),
            "calendar_conflict": calendar_conflict,
            "cycles": len(cycle_ids),
            "cycle_ids": sorted(cycle_ids),
            "unschedulable": unschedulable,
            "project_start": cpm_result.project_start,
            "project_finish": cpm_result.project_finish,
            "span_minutes": span_minutes,
            "health_score": score,
            "verdict": verdict,
        }

    @staticmethod
    def _apply_canonical_wbs_cpm_metadata(task: Task) -> None:
        metadata = getattr(task, "gantt_cpm_metadata", None)
        if not isinstance(metadata, dict):
            return

        diagnostics = list(metadata.get("diagnostics") or [])
        task.cpm_total_float = metadata.get("total_float")
        task.cpm_free_float = metadata.get("free_float")
        task.cpm_is_critical = bool(metadata.get("is_critical", False))
        task.cpm_earliest_start = metadata.get("earliest_start")
        task.cpm_earliest_finish = metadata.get("earliest_finish")
        task.cpm_latest_start = metadata.get("latest_start")
        task.cpm_latest_finish = metadata.get("latest_finish")
        task.cpm_diagnostics = diagnostics
        task.gantt_cpm_analysis_status = metadata.get(
            "analysis_status",
            "not_analyzed",
        )
        task.gantt_dependency_summary = metadata.get(
            "dependency_summary",
            "",
        )

        if bool(metadata.get("schedulable", False)):
            task.gantt_critical_path = task.cpm_is_critical

        if "DEPENDENCY_CYCLE" in diagnostics:
            task.gantt_dependency_cycle = True

    @classmethod
    def shift_successors(
        cls,
        tasks: List[Task],
        changed_task_id: int,
    ) -> Tuple[List[Task], Set[int]]:
        """
        Dependency-safe automatic successor shift.

        Only violations are shifted.
        Task duration and due-date span are preserved.
        Cycles are never shifted automatically.

        Returns:
            (changed successor Task objects, cycle_nodes)
        """
        (
            task_map,
            predecessors,
            successors,
        ) = cls.graph(
            tasks
        )

        cycle_nodes = cls.find_cycle_nodes(
            task_map,
            successors,
        )

        changed_task_id = int(
            changed_task_id
        )

        if (
            changed_task_id
            not in task_map
            or changed_task_id
            in cycle_nodes
        ):
            return [], cycle_nodes

        changed = []
        changed_ids = set()

        queue = [
            changed_task_id
        ]

        visited_edges = set()

        while queue:
            predecessor_id = queue.pop(
                0
            )

            predecessor = task_map.get(
                predecessor_id
            )

            if predecessor is None:
                continue

            predecessor_finish = cls.planned_finish(
                predecessor
            )
            predecessor_start = cls.planned_start(
                predecessor
            )

            for successor_id in sorted(
                successors.get(
                    predecessor_id,
                    set(),
                )
            ):
                edge = (
                    predecessor_id,
                    successor_id,
                )

                if edge in visited_edges:
                    continue

                visited_edges.add(
                    edge
                )

                if successor_id in cycle_nodes:
                    continue

                successor = task_map.get(
                    successor_id
                )

                if successor is None:
                    continue

                successor_start = cls.planned_start(
                    successor
                )

                if successor_start is None:
                    continue

                # Resolve the real edge type + lag. The walk used to assume
                # plain FS with zero lag, so lag-bearing edges either never
                # shifted or were shifted to a still-violating date.
                from todo_bird_app.services.cpm_scheduling_service import (
                    DependencyType as _DepType,
                    parse_dependency_specs as _parse_specs,
                )
                spec = next(
                    (
                        s
                        for s in _parse_specs(
                            successor.dependencies,
                            successor_id=successor_id,
                        )
                        if s.predecessor_id == predecessor_id
                    ),
                    None,
                )
                dtype = spec.dependency_type if spec else _DepType.FS
                lag = timedelta(
                    minutes=int(spec.lag_minutes or 0)
                    if spec
                    else 0
                )

                if dtype == _DepType.FS:
                    if predecessor_finish is None:
                        continue
                    anchor = predecessor_finish + lag
                    violated = successor_start < anchor
                elif dtype == _DepType.SS:
                    if predecessor_start is None:
                        continue
                    anchor = predecessor_start + lag
                    violated = successor_start < anchor
                elif dtype == _DepType.FF:
                    successor_finish = cls.planned_finish(successor)
                    if predecessor_finish is None or successor_finish is None:
                        continue
                    anchor = predecessor_finish + lag
                    violated = successor_finish < anchor
                else:  # SF
                    successor_finish = cls.planned_finish(successor)
                    if predecessor_start is None or successor_finish is None:
                        continue
                    anchor = predecessor_start + lag
                    violated = successor_finish < anchor

                if not violated:
                    queue.append(
                        successor_id
                    )
                    continue

                if dtype in (_DepType.FF, _DepType.SF):
                    # The successor's FINISH is pinned by the edge: pull its
                    # start back so the finish lands on the anchor.
                    duration = max(
                        0,
                        int(
                            successor.estimated_duration
                            or 0
                        ),
                    )
                    old_span = (
                        cls._parse_date(successor.due_date)
                        - cls._parse_date(successor.planned_date)
                        if cls._parse_date(successor.due_date)
                        and cls._parse_date(successor.planned_date)
                        else timedelta(days=0)
                    )
                    if old_span < timedelta(days=0):
                        old_span = timedelta(days=0)
                    new_start = (
                        anchor - timedelta(minutes=duration)
                        if duration > 0
                        else anchor - old_span
                    )
                else:
                    new_start = anchor

                old_planned_day = cls._parse_date(
                    successor.planned_date
                )

                old_due_day = cls._parse_date(
                    successor.due_date
                )

                old_start_clock = cls._parse_time(
                    successor.planned_start_time
                )

                old_end_clock = cls._parse_time(
                    successor.planned_end_time
                )

                old_finish = cls.planned_finish(
                    successor
                )

                # Preserve date span when Due Date is meaningful.
                date_span_days = 0

                if (
                    old_planned_day
                    and old_due_day
                ):
                    date_span_days = max(
                        0,
                        (
                            old_due_day
                            - old_planned_day
                        ).days,
                    )

                successor.planned_date = (
                    new_start.date()
                    .strftime(
                        "%Y-%m-%d"
                    )
                )

                if old_start_clock is not None:
                    successor.planned_start_time = (
                        new_start.strftime(
                            "%H:%M"
                        )
                    )

                # Time-based task: preserve duration precisely.
                duration = max(
                    0,
                    int(
                        successor.estimated_duration
                        or 0
                    ),
                )

                if (
                    old_start_clock is not None
                    and duration > 0
                ):
                    new_finish = (
                        new_start
                        + timedelta(
                            minutes=duration
                        )
                    )

                    successor.planned_end_time = (
                        new_finish.strftime(
                            "%H:%M"
                        )
                    )

                    successor.due_date = (
                        new_finish.date()
                        .strftime(
                            "%Y-%m-%d"
                        )
                    )

                elif old_finish is not None:
                    # Date-span task.
                    successor.due_date = (
                        (
                            new_start.date()
                            + timedelta(
                                days=date_span_days
                            )
                        )
                        .strftime(
                            "%Y-%m-%d"
                        )
                    )

                    if old_end_clock is not None:
                        successor.planned_end_time = (
                            old_end_clock.strftime(
                                "%H:%M"
                            )
                        )

                if successor_id not in changed_ids:
                    changed.append(
                        successor
                    )
                    changed_ids.add(
                        successor_id
                    )

                queue.append(
                    successor_id
                )

        return changed, cycle_nodes
