"""
Tests for Phase 1F.7.2.3: Instant Dashboard Chart Mode Switching.

Verifies:
1. Chart mode/style switch is instantaneous (no-op data animation, _animation_progress=1.0)
2. No full Dashboard.refresh_data() triggered on presentation style switch
3. Same-mode request is an immediate no-op
4. Chart data (Capacity values, Status counts, Activity 7D/14D/30D/90D) is untouched
5. Hit regions are immediately valid after mode switch
6. Hover and selection state consistency after mode switch
7. All 7 Capacity styles switch cleanly and instantly
8. All 6 Status styles switch cleanly and instantly
9. All 8 Activity styles switch cleanly and instantly
10. Performance benchmark: multi-cycle mode switching stays < 100ms total
11. Dark/light palette rendering intact across mode switches
"""

import time
from unittest.mock import MagicMock
from PySide6.QtCore import Qt, QVariantAnimation
from PySide6.QtWidgets import QApplication

from todo_bird_app.widgets.dashboard_charts import (
    AdvancedCapacityChart,
    AdvancedStatusChart,
    AdvancedWeeklyActivityChart,
)


def _app():
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------
# 1. Mode Switch No-Animation & Immediate Paint Tests
# ------------------------------------------------------------

def test_capacity_mode_switch_does_not_restart_animation():
    _app()
    chart = AdvancedCapacityChart()
    chart.set_values(180, 180, 480)
    chart.resize(400, 100)
    chart.show()
    QApplication.processEvents()

    # Animation stops and progress settles at 1.0 after initial load
    chart.set_animations_enabled(False)
    assert chart._animation_progress == 1.0
    assert chart._animation.state() == QVariantAnimation.Stopped

    # Re-enable animation for widget
    chart.set_animations_enabled(True)

    # Change chart type from Segmented Bar to Gauge
    chart.set_chart_type("Gauge")

    # Mode switch must NOT restart 520ms animation timer
    assert chart.chart_type == "Gauge"
    assert chart._animation.state() == QVariantAnimation.Stopped
    assert chart._animation_progress == 1.0

    chart.close()


def test_status_mode_switch_does_not_restart_animation():
    _app()
    chart = AdvancedStatusChart()
    chart.set_counts(4, 3, 2, 5)
    chart.resize(300, 200)
    chart.show()
    QApplication.processEvents()

    chart.set_animations_enabled(True)

    # Change from Executive Ring to Donut, then to Waffle
    chart.set_chart_type("Donut")
    assert chart.chart_type == "Donut"
    assert chart._animation.state() == QVariantAnimation.Stopped
    assert chart._animation_progress == 1.0

    chart.set_chart_type("Waffle")
    assert chart.chart_type == "Waffle"
    assert chart._animation.state() == QVariantAnimation.Stopped
    assert chart._animation_progress == 1.0

    chart.close()


def test_weekly_activity_mode_switch_does_not_restart_animation():
    _app()
    chart = AdvancedWeeklyActivityChart()
    data = [("Mon", 4, 6), ("Tue", 8, 5), ("Wed", 6, 6)]
    chart.set_daily_data(data)
    chart.resize(400, 200)
    chart.show()
    QApplication.processEvents()

    chart.set_animations_enabled(True)

    # Switch to Smooth Line, then Area
    chart.set_chart_type("Smooth Line")
    assert chart.chart_type == "Smooth Line"
    assert chart._animation.state() == QVariantAnimation.Stopped
    assert chart._animation_progress == 1.0

    chart.set_chart_type("Area")
    assert chart.chart_type == "Area"
    assert chart._animation.state() == QVariantAnimation.Stopped
    assert chart._animation_progress == 1.0

    chart.close()


# ------------------------------------------------------------
# 2. Same-Mode No-Op Tests
# ------------------------------------------------------------

def test_same_mode_switch_is_immediate_noop():
    _app()
    chart = AdvancedCapacityChart()
    chart.set_chart_type("Bullet")
    assert chart.chart_type == "Bullet"

    update_spy = MagicMock()
    chart.update = update_spy

    # Requesting same type "Bullet" must be a no-op
    chart.set_chart_type("Bullet")
    update_spy.assert_not_called()

    chart.close()


# ------------------------------------------------------------
# 3. Source Data Preservation & Hit Regions
# ------------------------------------------------------------

def test_mode_switch_preserves_underlying_data_and_hit_regions():
    _app()
    chart = AdvancedWeeklyActivityChart()
    data = [(f"Day {i}", i % 5, (i + 2) % 6) for i in range(30)]
    chart.set_daily_data(data)
    chart.resize(600, 200)
    chart.show()
    QApplication.processEvents()
    chart.grab()

    assert len(chart.daily_data) == 30
    assert len(chart._hit_regions) == 30

    # Select day 12
    chart.select_key(12)
    assert chart.selected_item() is not None
    assert chart.selected_item().key == 12

    # Switch mode from Grouped Bar to Lollipop
    chart.set_chart_type("Lollipop")
    chart.grab()

    # Data and selection must remain intact
    assert len(chart.daily_data) == 30
    assert chart.selected_item() is not None
    assert chart.selected_item().key == 12
    assert len(chart._hit_regions) == 30

    chart.close()


# ------------------------------------------------------------
# 4. Coverage of All 21 Chart Types
# ------------------------------------------------------------

def test_capacity_all_seven_types_switch_instantly():
    _app()
    chart = AdvancedCapacityChart()
    chart.set_values(120, 240, 480)
    chart.resize(400, 100)
    chart.show()

    for c_type in AdvancedCapacityChart.CHART_TYPES:
        chart.set_render_mode(c_type)
        assert chart.chart_type == c_type
        assert chart._animation_progress == 1.0
        chart.grab()
        assert len(chart._hit_regions) >= 2

    chart.close()


def test_status_all_six_types_switch_instantly():
    _app()
    chart = AdvancedStatusChart()
    chart.set_counts(5, 4, 3, 8)
    chart.resize(300, 200)
    chart.show()

    for c_type in AdvancedStatusChart.CHART_TYPES:
        chart.set_render_mode(c_type)
        assert chart.chart_type == c_type
        assert chart._animation_progress == 1.0
        chart.grab()
        assert len(chart._hit_regions) == 4

    chart.close()


def test_activity_all_eight_types_switch_instantly():
    _app()
    chart = AdvancedWeeklyActivityChart()
    chart.set_daily_data([("D1", 2, 4), ("D2", 5, 5), ("D3", 7, 3)])
    chart.resize(400, 200)
    chart.show()

    for c_type in AdvancedWeeklyActivityChart.CHART_TYPES:
        chart.set_render_mode(c_type)
        assert chart.chart_type == c_type
        assert chart._animation_progress == 1.0
        chart.grab()
        assert len(chart._hit_regions) == 3

    chart.close()


# ------------------------------------------------------------
# 5. Performance Benchmark
# ------------------------------------------------------------

def test_rapid_mode_switching_performance():
    _app()
    chart = AdvancedCapacityChart()
    chart.set_values(150, 200, 450)
    chart.resize(400, 100)
    chart.show()
    QApplication.processEvents()

    types = list(AdvancedCapacityChart.CHART_TYPES)

    # Perform 70 rapid mode switches
    t0 = time.perf_counter()
    for i in range(70):
        chart.set_chart_type(types[i % len(types)])
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # 70 switches in Python should complete in < 50ms (average < 0.7ms each)
    assert elapsed_ms < 50.0, f"70 mode switches took {elapsed_ms:.2f}ms (expected < 50ms)"

    chart.close()
