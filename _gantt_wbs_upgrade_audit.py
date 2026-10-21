#!/usr/bin/env python3
"""Probes for the Gantt/CPM upgrades: lag-aware auto-shift, near-critical
detection, schedule-health summary, meeting-overlap scrubber."""
import os
import sys
from datetime import datetime, timedelta

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.pop("TODO_BIRD_DB", None)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), str(detail)))
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" — {detail}" if detail else ""))


from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

from todo_bird_app.models.task import Task
from todo_bird_app.gantt.gantt_dependency_engine import GanttDependencyEngine


def mk(tid, title, date, start, end=None, dur=None, deps=None, **kw):
    return Task(id=tid, title=title, project_id=1,
                planned_date=date, planned_start_time=start,
                planned_end_time=end,
                estimated_duration=dur or 0,
                dependencies=deps or [], **kw)


print("=== 1. Lag-aware shift_successors ===")
# FS lag 0 (regression): pred Mon 09:00-12:00; succ starts 10:00 -> shifted to 12:00
tasks = [mk(1, "P", "2026-09-28", "09:00", "12:00", 180),
         mk(2, "S", "2026-09-28", "10:00", "13:00", 180, deps=[1])]
changed, cyc = GanttDependencyEngine.shift_successors(tasks, 1)
check("FS0: successor shifted", any(t.id == 2 for t in changed))
s = next(t for t in tasks if t.id == 2)
check("FS0: new start 12:00", s.planned_start_time == "12:00", str(s.planned_start_time))
check("FS0: duration preserved", s.planned_end_time == "15:00", str(s.planned_end_time))

# FS lag +1d: anchor = Mon 12:00 + 1440m = Tue 12:00
tasks = [mk(1, "P", "2026-09-28", "09:00", "12:00", 180),
         mk(2, "S", "2026-09-28", "09:00", "12:00", 180,
            deps=[{"predecessor_id": 1, "type": "FS", "lag_minutes": 1440}])]
changed, _ = GanttDependencyEngine.shift_successors(tasks, 1)
s = next(t for t in tasks if t.id == 2)
check("FS+1d: shifted to Tue 12:00",
      s.planned_date == "2026-09-29" and s.planned_start_time == "12:00",
      f"{s.planned_date} {s.planned_start_time}")

# FS lead -60: anchor = Mon 12:00 - 60m = Mon 11:00; succ at 11:30 -> NOT violated
tasks = [mk(1, "P", "2026-09-28", "09:00", "12:00", 180),
         mk(2, "S", "2026-09-28", "11:30", "14:30", 180,
            deps=[{"predecessor_id": 1, "type": "FS", "lag_minutes": -60}])]
changed, _ = GanttDependencyEngine.shift_successors(tasks, 1)
check("FS lead(-60): already satisfied, no shift", not changed)

# SS lag 120: succ must start >= pred start + 2h = 11:00; succ starts 08:00 -> shift
tasks = [mk(1, "P", "2026-09-28", "09:00", "17:00", 480),
         mk(2, "S", "2026-09-28", "08:00", "12:00", 240,
            deps=[{"predecessor_id": 1, "type": "SS", "lag_minutes": 120}])]
changed, _ = GanttDependencyEngine.shift_successors(tasks, 1)
s = next(t for t in tasks if t.id == 2)
check("SS+2h: start anchored 11:00", s.planned_start_time == "11:00",
      str(s.planned_start_time))
check("SS+2h: duration preserved (end 15:00)", s.planned_end_time == "15:00",
      str(s.planned_end_time))

# FF lag 0: succ must finish >= pred finish 12:00; succ finishes 10:00 (start 09:00, 60m)
# -> time-based: new_start = 12:00 - 60m = 11:00, new finish 12:00
tasks = [mk(1, "P", "2026-09-28", "09:00", "12:00", 180),
         mk(2, "S", "2026-09-28", "09:00", "10:00", 60,
            deps=[{"predecessor_id": 1, "type": "FF", "lag_minutes": 0}])]
changed, _ = GanttDependencyEngine.shift_successors(tasks, 1)
s = next(t for t in tasks if t.id == 2)
check("FF: finish anchored at pred finish 12:00", s.planned_end_time == "12:00",
      str(s.planned_end_time))
check("FF: start backed out to 11:00", s.planned_start_time == "11:00",
      str(s.planned_start_time))

# FF on date-span task (no start clock semantics): span 2 days; pred finish 12:00;
# succ due Thu, planned Tue -> finish Thu 23:59? planned_finish = due+end? use end time none
# succ: planned Tue 2026-09-29 -> Thu 2026-10-01 (span 2d), FF anchor Mon 12:00 Sep 28
# succ finish (planned_finish) = Oct 1 (end of day?) — engine planned_finish uses
# planned_end_time or due date midnight. Mon 12:00 anchor < Oct 1 finish -> satisfied.
tasks = [mk(1, "P", "2026-09-28", "09:00", "12:00", 180),
         mk(2, "S", "2026-09-29", None, None, 0,
            deps=[{"predecessor_id": 1, "type": "FF", "lag_minutes": 0}])]
s = tasks[1]
s.due_date = "2026-10-01"
changed, _ = GanttDependencyEngine.shift_successors(tasks, 1)
check("FF date-span: satisfied finish, no shift", not changed)

# SF: succ must finish >= pred start + lag. Pred starts Mon 09:00, lag 0.
# succ finishes Mon 08:00 (start 07:00, 60m) -> violated: new_start = 08:00 - 60m = 07:00? no:
# anchor = 09:00; duration 60 -> new_start = 08:00. finish = 09:00.
tasks = [mk(1, "P", "2026-09-28", "09:00", "17:00", 480),
         mk(2, "S", "2026-09-28", "07:00", "08:00", 60,
            deps=[{"predecessor_id": 1, "type": "SF", "lag_minutes": 0}])]
changed, _ = GanttDependencyEngine.shift_successors(tasks, 1)
s = next(t for t in tasks if t.id == 2)
check("SF: finish anchored at pred start 09:00", s.planned_end_time == "09:00",
      str(s.planned_end_time))
check("SF: start backed out to 08:00", s.planned_start_time == "08:00",
      str(s.planned_start_time))

# Cascade with lag: P(1)->S(2) FS+1440; S(2)->T(3) FS0.
# P Mon 09:00-12:00. S planned Mon 10:00 (violated: anchor Tue 12:00) -> Tue 12:00.
# T planned Tue 11:00 -> violated by S's new finish 15:00 -> 15:00.
tasks = [mk(1, "P", "2026-09-28", "09:00", "12:00", 180),
         mk(2, "S", "2026-09-28", "10:00", "13:00", 180,
            deps=[{"predecessor_id": 1, "type": "FS", "lag_minutes": 1440}]),
         mk(3, "T", "2026-09-29", "11:00", "14:00", 180, deps=[2])]
changed, _ = GanttDependencyEngine.shift_successors(tasks, 1)
s2 = next(t for t in tasks if t.id == 2)
s3 = next(t for t in tasks if t.id == 3)
check("cascade: S shifted to Tue 12:00",
      s2.planned_date == "2026-09-29" and s2.planned_start_time == "12:00",
      f"{s2.planned_date} {s2.planned_start_time}")
check("cascade: T followed to Tue 15:00",
      s3.planned_date == "2026-09-29" and s3.planned_start_time == "15:00",
      f"{s3.planned_date} {s3.planned_start_time}")

print("\n=== 2. Schedule health summary (CPM insights panel) ===")
from todo_bird_app.gantt.gantt_dependency_engine import GanttDependencyEngine as GDE

# Healthy chain: A(60) -> B(120) on Mon, no deadlines — all critical, score 100.
tasks = [mk(1, "A", "2026-09-28", "09:00", None, 60),
         mk(2, "B", "2026-09-28", "09:00", None, 120, deps=[1])]
h = GDE.schedule_health_summary(tasks)
check("health: critical = 2 (chain)", h["critical"] == 2, str(h))
check("health: score 100 healthy", h["health_score"] == 100 and h["verdict"] == "healthy",
      f"{h['health_score']} {h['verdict']}")
check("health: project finish Sep 28 12:00", h["project_finish"] == datetime(2026, 9, 28, 12, 0),
      str(h["project_finish"]))

# Diamond: short branch has float 60 -> near-critical (<= 1440)
tasks = [mk(1, "A", "2026-09-28", "09:00", None, 60),
         mk(2, "B", "2026-09-28", "09:00", None, 120, deps=[1]),
         mk(3, "C", "2026-09-28", "09:00", None, 60, deps=[1]),
         mk(4, "D", "2026-09-28", "09:00", None, 60, deps=[2, 3])]
h = GDE.schedule_health_summary(tasks)
check("health: near_critical counts the short branch", h["near_critical"] == 1,
      str(h["near_critical_ids"]))
check("health: critical = A,B,D", h["critical"] == 3, str(h["critical"]))

# Missed deadline: -12 penalty
tasks = [mk(1, "A", "2026-09-28", "09:00", None, 120,
            deadline_datetime="2026-09-28 10:00")]
h = GDE.schedule_health_summary(tasks)
check("health: missed deadline penalizes 12",
      h["health_score"] == 88 and h["deadline_missed"] == 1,
      f"{h['health_score']} dl={h['deadline_missed']}")

# Cycle: -15 and flagged
tasks = [mk(1, "A", "2026-09-28", "09:00", None, 60, deps=[2]),
         mk(2, "B", "2026-09-28", "09:00", None, 60, deps=[1])]
h = GDE.schedule_health_summary(tasks)
# Both tasks are in the cycle -> both unschedulable -> the "nothing
# schedulable" cap floors the score at 40 (verdict risk), which is the
# honest reading for a plan whose entire chain is circular.
check("health: all-cycle plan capped at risk",
      h["health_score"] == 40 and h["verdict"] == "risk" and h["cycles"] == 2,
      f"{h['health_score']} {h['verdict']} cycles={h['cycles']}")

# Empty -> None
check("health: empty returns None", GDE.schedule_health_summary([]) is None)

print("\n================ SUMMARY ================")
print("\n=== 3. World Clock meeting-overlap scrubber ===")
import shutil
from todo_bird_app.database import DatabaseManager
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.services.world_clock_service import WorldClockItem

shutil.rmtree("/tmp/tb_gantt_cfg", ignore_errors=True)
wdb = DatabaseManager(":memory:")
wsm = SettingsManager(wdb, config_dir="/tmp/tb_gantt_cfg")

from todo_bird_app.views.world_clock_view import WorldClockView
wcv = WorldClockView(db_manager=wdb, settings_manager=wsm)
wcv.clocks = [
    WorldClockItem(id="1", country_code="IN", country_name="India",
                   city="Hyderabad", timezone="Asia/Kolkata"),
    WorldClockItem(id="2", country_code="US", country_name="United States",
                   city="New York", timezone="America/New_York"),
]
wcv._render_grid()
app.processEvents()
check("world clock: two cards built", len(wcv.cards) == 2, str(len(wcv.cards)))

# 14:30 local IST -> Hyderabad 14:30 (work), New York ~04:30 (off)
wcv._on_slider_changed(14 * 60 + 30)
app.processEvents()
lbl_hyd = wcv.cards[0].sim_lbl.text()
lbl_ny = wcv.cards[1].sim_lbl.text()
check("scrubber: Hyderabad shows 2:30 PM work hours", "02:30 PM" in lbl_hyd and "Work" in lbl_hyd, lbl_hyd)
check("scrubber: New York shows off hours", "Off" in lbl_ny, lbl_ny)
check("scrubber: summary counts work hours", "1/2 in work hours" in wcv.slider_val_lbl.text(),
      wcv.slider_val_lbl.text())

wcv._find_best_overlap()
app.processEvents()
check("scrubber: best-overlap search completes", "Best Overlap" in wcv.slider_val_lbl.text(),
      wcv.slider_val_lbl.text())

wcv._reset_scrubber()
app.processEvents()
check("scrubber: reset hides sim labels",
      (not wcv.cards[0].sim_lbl.isVisible())
      and "Live Current Time" in wcv.slider_val_lbl.text())

fails = [r for r in results if not r[1]]
print(f"{len(results) - len(fails)}/{len(results)} checks passed")
for name, ok, detail in fails:
    print(f"  FAIL: {name} — {detail}")
sys.exit(1 if fails else 0)
