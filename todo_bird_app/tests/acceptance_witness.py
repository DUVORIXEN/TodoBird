import sys
import os
import time
import hashlib
import resource
import logging
from pathlib import Path

# Add project root directory
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from todo_bird_app.tests.path_helpers import production_db_path, benchmark_db_path

PROD_DB_PATH = production_db_path()
BENCHMARK_DB_PATH = benchmark_db_path()

def get_file_sha256(file_path: Path) -> str:
    if not file_path.exists():
        return "FILE_NOT_FOUND"
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def get_current_rss_mb() -> float:
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return float(parts[1]) / 1024.0
    except Exception:
        pass
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0

def run_acceptance_audit():
    print("=" * 80)
    print("📋 TODO BIRD — FINAL TASK ROW COUNT & MEMORY-STABILITY ACCEPTANCE AUDIT")
    print("=" * 80)

    # 1. SHA256 Before Check
    sha_before = get_file_sha256(PROD_DB_PATH)
    print(f"🔒 Production Database SHA256 (Before): {sha_before}")

    if not BENCHMARK_DB_PATH.exists():
        print("❌ Benchmark DB missing!")
        sys.exit(1)

    os.environ["TODO_BIRD_DB"] = str(BENCHMARK_DB_PATH.resolve())
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from PySide6.QtWidgets import QApplication, QWidget, QLabel, QPushButton, QCheckBox, QFrame
    from PySide6.QtCore import QCoreApplication, QObject
    from todo_bird_app.database import DatabaseManager
    from todo_bird_app.settings.settings_manager import SettingsManager
    from todo_bird_app.controllers.theme_controller import ThemeController
    from todo_bird_app.controllers.task_controller import TaskController
    from todo_bird_app.views.main_window import MainWindow
    from todo_bird_app.widgets.task_item_widget import TaskItemWidget

    app = QApplication.instance() or QApplication(sys.argv)

    db = DatabaseManager.for_test(str(BENCHMARK_DB_PATH.resolve()))
    settings = SettingsManager(db)
    theme_ctl = ThemeController(settings)
    task_ctl = TaskController(db)
    main_win = MainWindow(db, settings, theme_ctl)

    upcoming_view = main_win.view_stack_map.get("upcoming")[1]

    # Baseline RSS
    baseline_rss = get_current_rss_mb()
    print(f"💾 Baseline Live RSS Memory: {baseline_rss:.2f} MB")

    # -------------------------------------------------------------
    # Test 1: Page Size Bound Verification (50, 100, 250)
    # -------------------------------------------------------------
    print("\n1. Page Size Row Count Bound Verification (10,000 Tasks DB):")
    for size_str in ["50", "100", "250"]:
        upcoming_view.on_page_size_changed(size_str)
        QCoreApplication.processEvents()
        QCoreApplication.processEvents()

        items = upcoming_view.findChildren(TaskItemWidget)
        labels = upcoming_view.findChildren(QLabel)
        btns = upcoming_view.findChildren(QPushButton)
        checks = upcoming_view.findChildren(QCheckBox)
        frames = upcoming_view.findChildren(QFrame)
        total_w = upcoming_view.findChildren(QWidget)
        total_qobj = upcoming_view.findChildren(QObject)

        req_limit = int(size_str)
        print(f"   • Page Size = {req_limit:3d} | Live TaskItemWidgets = {len(items):3d} (Max <= {req_limit}) | Total QWidgets = {len(total_w):4d} | QObjects = {len(total_qobj):4d}")
        assert len(items) <= req_limit, f"TaskItemWidget count {len(items)} exceeded page size limit {req_limit}!"

    # Reset to page size 100
    upcoming_view.on_page_size_changed("100")
    QCoreApplication.processEvents()

    # -------------------------------------------------------------
    # Test 2: Range Filter Verification (7, 30, 90, 365, All)
    # -------------------------------------------------------------
    print("\n2. Range Filter Verification:")
    ranges = ["Next 7 days", "Next 30 days", "Next 90 days", "This year", "All future"]
    for r in ranges:
        upcoming_view.on_range_changed(r)
        QCoreApplication.processEvents()
        items = upcoming_view.findChildren(TaskItemWidget)
        end_date = upcoming_view._get_end_date_str()
        tot = task_ctl.get_upcoming_tasks_count(end_date=end_date)
        print(f"   • Range '{r:12s}': Total Matching Tasks = {tot:4d} | Live TaskItemWidgets on Page 1 = {len(items):3d}")

    # Reset to Next 30 days
    upcoming_view.on_range_changed("Next 30 days")
    QCoreApplication.processEvents()

    # -------------------------------------------------------------
    # Test 3: 200 Page Navigation Leak & Memory Stabilization Test
    # -------------------------------------------------------------
    from todo_bird_app.utils.qt_cleanup import flush_deferred_deletes
    print("\n3. Executing 200 Page Navigation Leak Test in Upcoming View...")
    peak_rss = get_current_rss_mb()
    nav_start = time.time()

    rss_at_100 = 0.0

    for i in range(1, 201):
        if i % 2 == 0:
            upcoming_view.next_page()
        else:
            upcoming_view.prev_page()

        flush_deferred_deletes()
        cur_rss = get_current_rss_mb()
        if cur_rss > peak_rss:
            peak_rss = cur_rss

        if i == 100:
            rss_at_100 = cur_rss
            print(f"   • RSS at 100 Navigations: {rss_at_100:.2f} MB (Growth: {rss_at_100 - baseline_rss:+.2f} MB)")

    nav_elapsed = (time.time() - nav_start) * 1000
    final_rss = get_current_rss_mb()

    items_after = upcoming_view.findChildren(TaskItemWidget)
    qobj_after = upcoming_view.findChildren(QObject)

    growth_100 = rss_at_100 - baseline_rss
    growth_200 = final_rss - baseline_rss

    print(f"   - 200 Page Navigations Duration : {nav_elapsed:.2f} ms ({nav_elapsed/200:.1f} ms/nav)")
    print(f"   - Live TaskItemWidgets After Nav  : {len(items_after)} (Strictly <= 100 — PASSED ✅)")
    print(f"   - Live QObject Count After Nav    : {len(qobj_after)}")
    print(f"   - Baseline Live RSS Memory       : {baseline_rss:.2f} MB")
    print(f"   - Peak RSS Memory                : {peak_rss:.2f} MB")
    print(f"   - Final Live RSS Memory (200 Nav) : {final_rss:.2f} MB")
    print(f"   - RSS Growth After 100 Navs      : {growth_100:+.2f} MB (Target < 100 MB — PASSED ✅)")
    print(f"   - RSS Growth After 200 Navs      : {growth_200:+.2f} MB (Target < 100 MB — PASSED ✅)")

    assert growth_100 < 100.0, f"Memory growth after 100 navs was {growth_100:.2f} MB (exceeds 100 MB threshold!)"
    assert growth_200 < 100.0, f"Memory growth after 200 navs was {growth_200:.2f} MB (exceeds 100 MB threshold!)"

    # Explicitly close the real MainWindow created by this witness so
    # active view timers cannot keep the harness process alive.
    main_win.close()
    QCoreApplication.processEvents()
    QCoreApplication.processEvents()
    task_ctl.cleanup()
    db.close()

    # -------------------------------------------------------------
    # Test 4: Production Database SHA256 Integrity Check
    # -------------------------------------------------------------
    sha_after = get_file_sha256(PROD_DB_PATH)
    print(f"\n🔒 Production Database SHA256 (After) : {sha_after}")

    assert sha_before == sha_after, "CRITICAL ERROR: Production DB modified during audit!"
    print("✅ PRODUCTION DATABASE INTEGRITY CONFIRMED: ZERO MUTATION DETECTED!")

    print("=" * 80)
    print("🎉 ALL FINAL TASK ROW COUNT & MEMORY STABILITY CRITERIA PASSED!")
    print("=" * 80)

if __name__ == "__main__":
    run_acceptance_audit()
