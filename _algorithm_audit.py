#!/usr/bin/env python3
"""Algorithm audit: feed hand-computed cases to the math engines and verify.

Covers: CPM forward/backward pass (FS/SS/FF/SF, lag), cycle detection,
constraints, deadlines, working-day calendar arithmetic, WBS effort-weighted
rollups, schedule variance, execution elapsed math, world-clock timezone math,
dashboard aggregation.
Every expectation is computed by hand in the comment next to it.
"""
import os
import sys
from datetime import datetime, date, timedelta

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.pop("TODO_BIRD_DB", None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))


from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

from todo_bird_app.models.task import Task, TaskStatus
from todo_bird_app.services.cpm_scheduling_service import (
    CPMSchedulingService, DependencySpec, DependencyType,
)
from todo_bird_app.utils.time_math import combine_date_time

# Monday 2026-09-28
D = lambda d, hm: datetime(2026, 9, d, *(int(x) for x in hm.split(":")))


def mk(tid, dur, start_hm=None, pdate="2026-09-28", deps=None, **kw):
    t = Task(id=tid, title=f"T{tid}", project_id=1,
             planned_date=pdate,
             planned_start_time=start_hm,
             estimated_duration=dur,
             dependencies=deps or [])
    for k, v in kw.items():
        setattr(t, k, v)
    return t


def dt(d, hm):
    return D(d, hm)


# =====================================================================
print("=== 1. CPM: plain chain A->B->C (FS, no lag) ===")
# Hand: A 60m 09:00->10:00; B 120m 10:00->12:00; C 60m 12:00->13:00.
# Project finish 13:00. All TF=0 (single path), all critical.
r = CPMSchedulingService.calculate_schedule([
    mk(1, 60, "09:00"),
    mk(2, 120, "09:00", deps=[1]),
    mk(3, 60, "09:00", deps=[2]),
], project_id=1)
check("chain: no cycles", not r.has_cycles)
n1, n2, n3 = r.nodes[1], r.nodes[2], r.nodes[3]
check("chain A ES", n1.earliest_start == dt(28, "09:00"), str(n1.earliest_start))
check("chain A EF", n1.earliest_finish == dt(28, "10:00"), str(n1.earliest_finish))
check("chain B ES=EF(A)", n2.earliest_start == n1.earliest_finish, str(n2.earliest_start))
check("chain B EF", n2.earliest_finish == dt(28, "12:00"), str(n2.earliest_finish))
check("chain C ES", n3.earliest_start == dt(28, "12:00"), str(n3.earliest_start))
check("chain C EF", n3.earliest_finish == dt(28, "13:00"), str(n3.earliest_finish))
check("chain: all critical", set(r.critical_task_ids) == {1, 2, 3}, str(r.critical_task_ids))
check("chain: TF zero on all", all(r.nodes[i].total_float_minutes == 0 for i in (1, 2, 3)),
      str([r.nodes[i].total_float_minutes for i in (1, 2, 3)]))

# =====================================================================
print("=== 2. CPM: diamond — float on the short branch ===")
# A(60) -> B(120) -> D(60); A -> C(60) -> D.
# Path A-B-D = 240m; A-C-D = 180m => C has TF 60, others 0.
r = CPMSchedulingService.calculate_schedule([
    mk(1, 60, "09:00"),
    mk(2, 120, "09:00", deps=[1]),
    mk(3, 60, "09:00", deps=[1]),
    mk(4, 60, "09:00", deps=[2, 3]),
], project_id=1)
n = r.nodes
check("diamond: critical = A,B,D", set(r.critical_task_ids) == {1, 2, 4},
      str(r.critical_task_ids))
check("diamond: C TF=60", n[3].total_float_minutes == 60, str(n[3].total_float_minutes))
check("diamond: D ES pushed by B", n[4].earliest_start == dt(28, "12:00"), str(n[4].earliest_start))
check("diamond: project finish 13:00", r.project_finish == dt(28, "13:00"), str(r.project_finish))

# =====================================================================
print("=== 3. CPM: FS lag, SS, FF edge math ===")
# FS lag+30: B starts EF(A)+30 => 10:30. dur B=60 -> EF 11:30.
r = CPMSchedulingService.calculate_schedule([
    mk(1, 60, "09:00"),
    mk(2, 60, "09:00", deps=[DependencySpec(1, 2, DependencyType.FS, 30)]),
], project_id=1)
check("FS lag: B ES = EF(A)+30", r.nodes[2].earliest_start == dt(28, "10:30"),
      str(r.nodes[2].earliest_start))

# SS lag 0: B(60) starts no earlier than A starts (09:00), runs parallel.
r = CPMSchedulingService.calculate_schedule([
    mk(1, 240, "09:00"),
    mk(2, 60, "09:00", deps=[DependencySpec(1, 2, DependencyType.SS, 0)]),
], project_id=1)
check("SS: B ES = A ES", r.nodes[2].earliest_start == dt(28, "09:00"),
      str(r.nodes[2].earliest_start))

# FF: B must finish no earlier than A finishes (13:00). B dur 60 -> ES 12:00.
r = CPMSchedulingService.calculate_schedule([
    mk(1, 240, "09:00"),
    mk(2, 60, "09:00", deps=[DependencySpec(1, 2, DependencyType.FF, 0)]),
], project_id=1)
check("FF: B EF = A EF", r.nodes[2].earliest_finish == dt(28, "13:00"),
      str(r.nodes[2].earliest_finish))

# Negative lag (lead): FS -30 -> B starts EF(A)-30 = 09:30.
r = CPMSchedulingService.calculate_schedule([
    mk(1, 60, "09:00"),
    mk(2, 60, "09:00", deps=[DependencySpec(1, 2, DependencyType.FS, -30)]),
], project_id=1)
check("FS lead(-30): B ES = EF(A)-30", r.nodes[2].earliest_start == dt(28, "09:30"),
      str(r.nodes[2].earliest_start))

# =====================================================================
print("=== 4. CPM: cycles, self-ref, deadlines, constraints ===")
r = CPMSchedulingService.calculate_schedule([
    mk(1, 60, "09:00", deps=[3]),
    mk(2, 60, "09:00", deps=[1]),
    mk(3, 60, "09:00", deps=[2]),
], project_id=1)
check("cycle detected A->B->C->A", r.has_cycles and set(r.cycle_task_ids) == {1, 2, 3},
      str(r.cycle_task_ids))
check("cycle: all unschedulable", all(not r.nodes[i].schedulable for i in (1, 2, 3)))

r = CPMSchedulingService.calculate_schedule([mk(1, 60, "09:00", deps=[1])], project_id=1)
codes = {c.code for c in r.diagnostics}
check("self-reference diagnosed", any("SELF" in str(c) for c in codes), str(codes))

# Deadline before forecast finish -> MISSED
r = CPMSchedulingService.calculate_schedule([
    mk(1, 120, "09:00", deadline_datetime="2026-09-28 10:00"),
], project_id=1)
codes = {c.code for c in r.diagnostics}
check("missed deadline diagnosed", any("DEADLINE" in str(c) for c in codes), str(codes))

# MSO (must start on) honored: pins ES to constraint even though planned start earlier.
r = CPMSchedulingService.calculate_schedule([
    mk(1, 60, "09:00", constraint_type="MSO", constraint_datetime="2026-09-28 11:00"),
], project_id=1)
check("MSO pins ES", r.nodes[1].earliest_start == dt(28, "11:00"), str(r.nodes[1].earliest_start))

# MSO conflicting with predecessor: dep pushes 12:00 > MSO 11:00 -> conflict diagnostic, ES=12:00
r = CPMSchedulingService.calculate_schedule([
    mk(1, 180, "09:00"),
    mk(2, 60, "09:00", deps=[1], constraint_type="MSO", constraint_datetime="2026-09-28 11:00"),
], project_id=1)
codes = {c.code for c in r.diagnostics}
check("MSO conflict diagnosed", any("CONFLICT" in str(c) for c in codes), str(codes))
check("MSO conflict: dep wins", r.nodes[2].earliest_start == dt(28, "12:00"),
      str(r.nodes[2].earliest_start))

# SNET: start no earlier than 11:00 with no deps
r = CPMSchedulingService.calculate_schedule([
    mk(1, 60, "09:00", constraint_type="SNET", constraint_datetime="2026-09-28 11:00"),
], project_id=1)
check("SNET honors bound", r.nodes[1].earliest_start == dt(28, "11:00"),
      str(r.nodes[1].earliest_start))

# =====================================================================
print("=== 5. CPM: working-day calendar (Mon-Fri) ===")
from todo_bird_app.services.schedule_calendar_service import (
    ScheduleCalendar, add_working_minutes,
    next_working_datetime, working_minutes_between,
)
cal = ScheduleCalendar(working_weekdays=(0, 1, 2, 3, 4))  # Mon-Fri
# Canonical whole-day semantics (documented in schedule_calendar_service.py and
# enforced by test_working_calendar_cpm_authority.py): day 1 IS the start date.
# A 1-day task's finish day = its start day (EF instant == ES instant);
# a 2-day task starting Friday finishes Monday.
r = CPMSchedulingService.calculate_schedule([
    mk(1, 2880, "09:00", pdate="2026-10-02"),  # Fri Oct 2, 2 working days
], project_id=1, project_calendar=cal)
check("calendar: Fri 2-day finishes Mon Oct 5 09:00",
      r.nodes[1].earliest_finish == datetime(2026, 10, 5, 9, 0),
      str(r.nodes[1].earliest_finish))

r = CPMSchedulingService.calculate_schedule([
    mk(1, 1440, "09:00", pdate="2026-10-02"),  # Fri Oct 2, 1 working day
], project_id=1, project_calendar=cal)
check("calendar: 1-day task finish day = start day",
      r.nodes[1].earliest_finish == datetime(2026, 10, 2, 9, 0),
      str(r.nodes[1].earliest_finish))

r = CPMSchedulingService.calculate_schedule([
    mk(1, 60, "09:00", pdate="2026-10-03"),  # Saturday Oct 3
], project_id=1, project_calendar=cal)
codes = {c.code for c in r.diagnostics}
check("calendar: Saturday start conflicts",
      any("CALENDAR" in str(c) for c in codes), str(codes))

# raw helper checks (pure math) — a working day carries 1440 nominal minutes
mon9 = datetime(2026, 9, 28, 9, 0)
check("add_working_minutes 480m => 17:00 Mon",
      add_working_minutes(mon9, 480, cal) == datetime(2026, 9, 28, 17, 0),
      str(add_working_minutes(mon9, 480, cal)))
check("working_minutes_between Mon-Fri 09:00->Mon 09:00 = 7200m (5x1440)",
      working_minutes_between(mon9, datetime(2026, 10, 5, 9, 0), cal) == 7200,
      str(working_minutes_between(mon9, datetime(2026, 10, 5, 9, 0), cal)))

# =====================================================================
print("=== 6. Schedule variance: baseline vs current ===")
from todo_bird_app.services.schedule_variance_service import (
    ScheduleVarianceService, parse_datetime_flexible,
)
t = Task(id=1, title="Var", project_id=1,
         planned_date="2026-09-29", planned_start_time="10:00",
         planned_end_time="12:00",
         baseline_start="2026-09-29 10:00", baseline_finish="2026-09-29 11:00",
         baseline_duration_minutes=60)
vr = ScheduleVarianceService.calculate_task_variance(t)
# Current dur 120 vs baseline 60 => finish 60m later than baseline => behind.
check("variance: duration variance +60",
      getattr(vr, "duration_variance_minutes", None) == 60
      or getattr(vr, "finish_variance_minutes", None) == 60,
      str(vr))
check("variance: status behind", bool(vr.is_behind), f"status={vr.status}")

t2 = Task(id=2, title="Var2", project_id=1,
          planned_date="2026-09-29", planned_start_time="10:00",
          planned_end_time="11:00",
          baseline_start="2026-09-29 10:00", baseline_finish="2026-09-29 12:00",
          baseline_duration_minutes=120)
vr2 = ScheduleVarianceService.calculate_task_variance(t2)
check("variance: ahead when shorter than baseline", bool(vr2.is_ahead), f"status={vr2.status}")

check("parse_datetime_flexible date-only",
      parse_datetime_flexible("2026-09-29") == datetime(2026, 9, 29, 0, 0),
      str(parse_datetime_flexible("2026-09-29")))

# =====================================================================
print("=== 7. WBS rollups: effort-weighted progress ===")
from todo_bird_app.database import DatabaseManager
from todo_bird_app.controllers.task_controller import TaskController
from todo_bird_app.services.wbs_service import WBSService, EntityRef
from todo_bird_app.services.wbs_rollup_service import WBSRollupService
import shutil

shutil.rmtree("/tmp/tb_alg", ignore_errors=True)
os.makedirs("/tmp/tb_alg", exist_ok=True)
db = DatabaseManager.temporary("/tmp/tb_alg/alg.db")
tc = TaskController(db)

# Projects table row must exist (tasks carry an FK to projects)
PID = db.insert_project({"name": "Audit Project"})

# Parent task P with two SUBTASKS: S1 (60m planned effort, 100%) and
# S2 (180m planned effort, 0%). Effort-weighted => (100*60 + 0*180)/240 = 25%.
parent = Task(id=101, title="Parent", project_id=PID, planned_date="2026-09-29",
              planned_start_time="09:00")
tc.add_task(parent)
s1_id = db.insert_subtask(
    101, "S1", planned_date="2026-09-29", planned_start_time="09:00",
    planned_end_time="10:00", estimated_duration=60, progress=100,
    status="Completed", is_completed=True,
)
s2_id = db.insert_subtask(
    101, "S2", planned_date="2026-09-29", planned_start_time="10:00",
    planned_end_time="11:00", estimated_duration=60, progress=0,
)
# planned effort lives on subtask rows; set it through the same authority the UI uses
import sqlite3
with db.get_connection() as conn:
    conn.execute("UPDATE subtasks SET planned_effort_minutes=60 WHERE id=?", (s1_id,))
    conn.execute("UPDATE subtasks SET planned_effort_minutes=180 WHERE id=?", (s2_id,))
    conn.commit()

snap = WBSService.build_project_hierarchy(db, PID)
roll = WBSRollupService.compute_all_rollups(snap, db)
pk = EntityRef.task(101)
pr = roll.get(pk)
check("rollup: parent exists", pr is not None)
if pr:
    check("rollup: leaf_count=2", pr.leaf_count == 2, str(pr.leaf_count))
    check("rollup: effort-weighted progress 25%", pr.progress == 25, str(pr.progress))
    check("rollup: planned effort 240", pr.planned_effort_minutes == 240,
          str(pr.planned_effort_minutes))
    check("rollup: planned_start = min(children)",
          pr.planned_start is not None and pr.planned_start.strftime("%H:%M") == "09:00",
          str(pr.planned_start))

# Complete S2 => whole subtree 100
with db.get_connection() as conn:
    conn.execute("UPDATE subtasks SET progress=100, status='Completed', is_completed=1, "
                 "actual_start_date='2026-09-29', actual_start_time='10:00', "
                 "actual_end_date='2026-09-29', actual_end_time='12:00' WHERE id=?", (s2_id,))
    conn.commit()
WBSRollupService.clear_cache()
snap2 = WBSService.build_project_hierarchy(db, PID)
roll2 = WBSRollupService.compute_all_rollups(snap2, db)
check("rollup: complete subtree => 100%", roll2[pk].progress == 100,
      str(roll2[pk].progress))
check("rollup: actual_finish = max(child actual finishes)",
      roll2[pk].actual_finish is not None
      and roll2[pk].actual_finish.strftime("%H:%M") == "12:00",
      str(roll2[pk].actual_finish))

# =====================================================================
print("=== 8. Execution elapsed math ===")
from todo_bird_app.services.execution_performance_service import ExecutionPerformanceService

t = Task(id=1, title="e", actual_start_date="2026-09-28", actual_start_time="09:00",
         actual_end_date="2026-09-28", actual_end_time="10:30")
check("elapsed same-day 90m", ExecutionPerformanceService.calculate_actual_elapsed(t) == 90,
      str(ExecutionPerformanceService.calculate_actual_elapsed(t)))

t2 = Task(id=2, title="e2", actual_start_date="2026-09-28", actual_start_time="23:00",
          actual_end_date="2026-09-29", actual_end_time="01:00")
check("elapsed cross-midnight 120m",
      ExecutionPerformanceService.calculate_actual_elapsed(t2) == 120,
      str(ExecutionPerformanceService.calculate_actual_elapsed(t2)))

t3 = Task(id=3, title="e3", actual_start_date="2026-09-28", actual_start_time="09:00",
          actual_end_date="2026-09-29", actual_end_time="09:00")
check("elapsed multi-day 1440m",
      ExecutionPerformanceService.calculate_actual_elapsed(t3) == 1440,
      str(ExecutionPerformanceService.calculate_actual_elapsed(t3)))

t4 = Task(id=4, title="e4", actual_start_date="2026-09-28", actual_start_time="16:00",
          actual_end_date="2026-09-28", actual_end_time=None)
# missing end time defaults to 17:00 => 60m (documented canonical fallback)
check("elapsed missing end uses 17:00 fallback => 60m",
      ExecutionPerformanceService.calculate_actual_elapsed(t4) == 60,
      str(ExecutionPerformanceService.calculate_actual_elapsed(t4)))

# =====================================================================
print("=== 9. World clock timezone math ===")
from todo_bird_app.services.world_clock_service import WorldClockService

utc_noon = datetime(2026, 7, 1, 12, 0)  # naive treated as? pass aware UTC
from datetime import timezone as tzmod
base = utc_noon.replace(tzinfo=tzmod.utc)

info = WorldClockService.get_time_info("Asia/Kolkata", base_time=base)
check("IST offset string UTC+05:30", info["utc_offset"] == "UTC+05:30", info["utc_offset"])
check("IST time 17:30", info["time_24h_short"] == "17:30", info["time_24h_short"])

info_ny = WorldClockService.get_time_info("America/New_York", base_time=base)
check("NY July (DST) offset UTC-04:00", info_ny["utc_offset"] == "UTC-04:00", info_ny["utc_offset"])

info_ny_w = WorldClockService.get_time_info("America/New_York",
                                            base_time=datetime(2026, 1, 15, 12, 0, tzinfo=tzmod.utc))
check("NY January (standard) offset UTC-05:00", info_ny_w["utc_offset"] == "UTC-05:00",
      info_ny_w["utc_offset"])

# day-relative: compare target zone against the MACHINE's local zone (the app
# compares against local_dt.date() — correct user-facing semantics)
base_evening = datetime(2026, 9, 29, 20, 30, tzinfo=tzmod.utc)  # 02:00 IST next day
info_ist = WorldClockService.get_time_info("Asia/Kolkata", base_time=base_evening)
local_now = base_evening.astimezone()
if local_now.date() < info_ist["datetime"].date():
    expected_rel = "Tomorrow"
elif local_now.date() > info_ist["datetime"].date():
    expected_rel = "Yesterday"
else:
    expected_rel = "Today"
check("day-relative matches local-zone comparison", info_ist["day_relative"] == expected_rel,
      f"got {info_ist['day_relative']}, expected {expected_rel}")

# =====================================================================
print("=== 10. Dashboard aggregation ===")
from todo_bird_app.services.dashboard_data_service import DashboardDataService

db2 = DatabaseManager.temporary("/tmp/tb_alg/alg2.db")
tc2 = TaskController(db2)
today = date.today()
yest = today - timedelta(days=1)
tom = today + timedelta(days=1)
tc2.add_task(Task(id=1, title="done today", status=TaskStatus.COMPLETED,
                  planned_date=today.strftime("%Y-%m-%d"),
                  actual_start_date=today.strftime("%Y-%m-%d"), actual_start_time="09:00",
                  actual_end_date=today.strftime("%Y-%m-%d"), actual_end_time="10:00"))
tc2.add_task(Task(id=2, title="overdue", status=TaskStatus.IN_PROGRESS,
                  planned_date=yest.strftime("%Y-%m-%d"),
                  actual_start_date=yest.strftime("%Y-%m-%d"), actual_start_time="09:00"))
tc2.add_task(Task(id=3, title="upcoming", status=TaskStatus.PLANNED,
                  planned_date=tom.strftime("%Y-%m-%d")))
try:
    from todo_bird_app.settings.settings_manager import SettingsManager
    dsm = SettingsManager(db2, config_dir='/tmp/tb_alg_cfg')
    data = DashboardDataService.build(db2, dsm)
    # Probe generic totals without assuming exact key names
    keys = set(data.keys()) if isinstance(data, dict) else dir(data)
    check("dashboard build returns data", bool(keys), str(sorted(keys)[:8]))
except Exception as e:
    check("dashboard build", False, f"{e.__class__.__name__}: {e}")

# =====================================================================
print("=== 11. Regression probes for fixed algorithm bugs ===")
# 11a. Gantt dependency validator: legal diamond must pass, real cycle must fail
from todo_bird_app.gantt.gantt_dependency_engine import GanttDependencyEngine
_tasks = [
    Task(id=4, title="Z", dependencies=[]),
    Task(id=2, title="P1", dependencies=[4]),
    Task(id=3, title="P2", dependencies=[4]),
    Task(id=1, title="Mid", dependencies=[2, 3]),
    Task(id=9, title="X", dependencies=[1]),
]
_v = GanttDependencyEngine.validate_proposed_dependencies(9, [1], _tasks)
check("validator: diamond DAG accepted", _v["valid"], _v["message"][:60])
_cyc = [Task(id=1, title="A", dependencies=[2]), Task(id=2, title="B", dependencies=[1])]
_v2 = GanttDependencyEngine.validate_proposed_dependencies(2, [1], _cyc)
check("validator: real cycle still rejected", not _v2["valid"])

# 11b. format_duration_human keeps minutes when days and hours are present
from todo_bird_app.services.execution_performance_service import format_duration_human
check("duration format 1590m = '1d 2h 30m'",
      format_duration_human(1590) == "1d 2h 30m", format_duration_human(1590))

# 11c. UTC timestamp -> local date helper (IST +5:30: 2026-09-24 20:00 UTC = Sep 25 local)
from todo_bird_app.utils.time_math import utc_timestamp_to_local_date
check("utc ts maps to next local day in IST",
      utc_timestamp_to_local_date("2026-09-24 20:00:00") == date(2026, 9, 25),
      str(utc_timestamp_to_local_date("2026-09-24 20:00:00")))
check("bare date passes through",
      utc_timestamp_to_local_date("2026-09-24") == date(2026, 9, 24),
      str(utc_timestamp_to_local_date("2026-09-24")))

# 11d. time_math day segmentation no longer crashes on invalid end time
from todo_bird_app.utils.time_math import segment_interval_by_day as segment_task_duration
try:
    segs = segment_task_duration("2026-09-28", "09:00", "2026-09-28", "25:99")
    check("segmenting survives invalid end time", True, f"segments={len(segs)}")
except TypeError as e:
    check("segmenting survives invalid end time", False, str(e))

# 11e. gamification streak uses local dates (UTC ts after midnight IST counts as today)
from todo_bird_app.services.gamification_engine import GamificationEngine
import shutil as _sh
_sh.rmtree("/tmp/tb_alg2", ignore_errors=True)
os.makedirs("/tmp/tb_alg2", exist_ok=True)
db3 = DatabaseManager.temporary("/tmp/tb_alg2/g.db")
tc3 = TaskController(db3)
_p = db3.insert_project({"name": "G"})
now_local = datetime.now()
tc3.add_task(Task(id=1, title="g1", project_id=_p, status=TaskStatus.COMPLETED,
                  planned_date=now_local.strftime("%Y-%m-%d"),
                  actual_start_date=now_local.strftime("%Y-%m-%d"), actual_start_time="09:00",
                  actual_end_date=now_local.strftime("%Y-%m-%d"), actual_end_time="10:00"))
tc3.add_task(Task(id=2, title="g2", project_id=_p, status=TaskStatus.COMPLETED,
                  planned_date=(now_local - timedelta(days=1)).strftime("%Y-%m-%d"),
                  actual_start_date=(now_local - timedelta(days=1)).strftime("%Y-%m-%d"),
                  actual_start_time="09:00",
                  actual_end_date=(now_local - timedelta(days=1)).strftime("%Y-%m-%d"),
                  actual_end_time="10:00"))
# Backdate updated_at directly (insert stamps it with "now"):
# task 1 at 20:00 UTC YESTERDAY -> 01:30 IST TODAY local (old code bucketed it as yesterday)
# task 2 at 12:00 UTC yesterday -> 17:30 IST yesterday local
_today_utc = (now_local - timedelta(days=1)).strftime("%Y-%m-%d") + " 20:00:00"
_yest_utc = (now_local - timedelta(days=1)).strftime("%Y-%m-%d") + " 12:00:00"
with db3.get_connection() as conn:
    conn.execute("UPDATE tasks SET updated_at=? WHERE id=1", (_today_utc,))
    conn.execute("UPDATE tasks SET updated_at=? WHERE id=2", (_yest_utc,))
    conn.commit()
stats = GamificationEngine(db3).calculate_stats()
check("streak maps UTC timestamps to local days (2-day streak)",
      stats.get("current_streak") == 2, str(stats.get("current_streak")))

# 11f. review controller effort dedupe
from todo_bird_app.controllers.review_controller import ReviewController
db4 = DatabaseManager.temporary("/tmp/tb_alg2/r.db")
db4.insert_project({"name": "R"})
tc4 = TaskController(db4)
tc4.add_task(Task(id=1, title="rev", project_id=1, planned_date=now_local.strftime("%Y-%m-%d"),
                  status=TaskStatus.COMPLETED, estimated_duration=60,
                  actual_duration=60,
                  actual_start_date=now_local.strftime("%Y-%m-%d"), actual_start_time="09:00",
                  actual_end_date=now_local.strftime("%Y-%m-%d"), actual_end_time="10:00"))
rc = ReviewController(db4, None)
summary = rc.get_daily_review_summary(now_local.date().isoformat())
check("review actual effort not double-counted (60 not 120)",
      summary.get("act_duration_total") == 60, str(summary.get("act_duration_total")))

# =====================================================================
print("\n================ ALGORITHM AUDIT SUMMARY ================")
fails = [r for r in results if not r[1]]
print(f"{len(results) - len(fails)}/{len(results)} checks passed")
for name, ok, detail in fails:
    print(f"  FAIL: {name} — {detail}")
sys.exit(1 if fails else 0)
