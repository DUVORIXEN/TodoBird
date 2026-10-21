import sys
import os
import argparse
import random
import time
from datetime import date, timedelta
from pathlib import Path

# Add project root directory
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from todo_bird_app.database import DatabaseManager
from todo_bird_app.models.task import Task, TaskPriority, TaskStatus

CATEGORIES = ["Work", "Personal", "Health", "Finance", "Learning", "Projects"]
PRIORITIES = [TaskPriority.LOW, TaskPriority.MEDIUM, TaskPriority.HIGH, TaskPriority.URGENT]
STATUSES = [TaskStatus.INBOX, TaskStatus.PLANNED, TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED, TaskStatus.DELAYED]

def generate_dataset(num_tasks: int, num_projects: int, db_path: str):
    print(f"🚀 Generating {num_tasks} benchmark tasks across {num_projects} projects into: {db_path}")

    # Remove existing benchmark DB if present
    if os.path.exists(db_path):
        os.remove(db_path)

    db = DatabaseManager(db_path)
    conn = db.get_connection()
    cursor = conn.cursor()

    # 1. Create Projects
    proj_ids = []
    for i in range(1, num_projects + 1):
        cursor.execute(
            "INSERT INTO projects (name, color, description) VALUES (?, ?, ?);",
            (f"Project Alpha-{i}", random.choice(["#E95420", "#3584E4", "#10B981", "#8B5CF6"]), f"Benchmark Project {i}")
        )
        proj_ids.append(cursor.lastrowid)

    # 2. Bulk Insert Tasks with SQL Transaction
    today = date.today()
    start_time = time.time()

    for i in range(1, num_tasks + 1):
        # Date spread across past 5 years and future 5 years
        day_offset = random.randint(-1825, 1825)
        p_date = today + timedelta(days=day_offset)
        est_dur = random.choice([15, 30, 45, 60, 90, 120, 240, 480])
        act_dur = est_dur + random.choice([-15, 0, 15, 30, 60]) if random.random() > 0.3 else 0
        prio = random.choice(PRIORITIES).value
        stat = random.choice(STATUSES).value
        proj = random.choice(proj_ids)

        cursor.execute("""
            INSERT INTO tasks (
                title, project_id, priority, tags, category, description,
                planned_date, due_date, estimated_duration, actual_duration,
                progress, status, delay_minutes, delay_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            f"Benchmark Task #{i:05d}",
            proj,
            prio,
            '["benchmark"]',
            random.choice(CATEGORIES),
            f"Automated benchmark test task entry description for task {i}.",
            p_date.strftime("%Y-%m-%d"),
            (p_date + timedelta(days=random.randint(1, 14))).strftime("%Y-%m-%d"),
            est_dur,
            max(0, act_dur),
            100 if stat == "Completed" else random.randint(0, 80),
            stat,
            max(0, act_dur - est_dur),
            "Meeting or phone call" if act_dur > est_dur else ""
        ))

    conn.commit()
    elapsed = time.time() - start_time

    print(f"✅ Successfully inserted {num_tasks} tasks in {elapsed:.3f} seconds ({num_tasks/elapsed:.1f} tasks/sec).")

    # Benchmark Quick Queries
    q_start = time.time()
    cursor.execute("SELECT COUNT(*) FROM tasks;")
    total_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM tasks WHERE planned_date = ?;", (today.strftime("%Y-%m-%d"),))
    today_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'Completed';")
    comp_count = cursor.fetchone()[0]
    q_elapsed = time.time() - q_start

    print(f"📊 Query Verification Benchmark:")
    print(f"   - Total Task Count: {total_count}")
    print(f"   - Today Task Count: {today_count}")
    print(f"   - Completed Count: {comp_count}")
    print(f"   - SQL Benchmark Query Time: {q_elapsed*1000:.2f} ms")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TODO BIRD Large Dataset Generator")
    parser.add_argument("--tasks", type=int, default=1000, help="Number of tasks to generate (default 1000)")
    parser.add_argument("--projects", type=int, default=20, help="Number of projects (default 20)")
    args = parser.parse_args()

    db_dir = Path(__file__).parent.parent / "data"
    db_dir.mkdir(parents=True, exist_ok=True)
    benchmark_db = str(db_dir / "benchmark_test.db")

    generate_dataset(args.tasks, args.projects, benchmark_db)
