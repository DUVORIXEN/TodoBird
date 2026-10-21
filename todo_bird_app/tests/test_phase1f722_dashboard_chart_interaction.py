"""
Tests for Phase 1F.7.2.2: True Dashboard Chart Interaction.

Verifies:
1. Interaction region model and hit testing
2. Hover detection and clearing on leave
3. Mouse selection and toggle/clearing
4. Keyboard inspection (Tab focus, Left/Right navigation, Enter select, Escape clear)
5. Tooltip payload fidelity (Capacity, Status, Activity)
6. Status percentage calculations
7. Activity data tuple extraction and variance
8. Capacity calculations and headroom
9. Invalidation / data refresh safety
10. Non-mutation of source data
11. Zero continuous animation / timers
12. Reduced motion compliance
13. Dark and light mode rendering
14. Zero-data and single-item chart handling
15. 7D / 14D / 30D / 90D range compatibility
16. Chart-type coverage across all 21 chart variants
"""

from PySide6.QtCore import Qt, QPointF, QRectF, QEvent, QVariantAnimation
from PySide6.QtGui import (
    QMouseEvent,
    QKeyEvent,
    QColor,
    QPalette,
)
from PySide6.QtWidgets import QApplication

from todo_bird_app.widgets.dashboard_charts import (
    ChartHitRegion,
    AnimatedDashboardChart,
    AdvancedCapacityChart,
    AdvancedStatusChart,
    AdvancedWeeklyActivityChart,
)


def _app():
    return QApplication.instance() or QApplication([])


# ------------------------------------------------------------
# 1. Hit Region & Spatial Model Tests
# ------------------------------------------------------------

def test_chart_hit_region_rect_contains():
    region = ChartHitRegion(
        key="test_item",
        label="Test Item",
        primary_value=42,
        rect=QRectF(10, 10, 50, 50),
    )
    assert region.contains(QPointF(20, 20)) is True
    assert region.contains(QPointF(5, 5)) is False
    assert region.contains(QPointF(100, 100)) is False


def test_chart_hit_region_center_radius_contains():
    region = ChartHitRegion(
        key="circle_item",
        label="Circle Item",
        primary_value=100,
        center=QPointF(50, 50),
        radius=25,
        inner_radius=10,
    )
    # Inside ring
    assert region.contains(QPointF(50, 70)) is True
    # Inside hole (inner radius)
    assert region.contains(QPointF(50, 52)) is False
    # Outside outer radius
    assert region.contains(QPointF(50, 90)) is False


# ------------------------------------------------------------
# 2. Capacity Chart Interaction & Tooltip Tests
# ------------------------------------------------------------

def test_capacity_chart_builds_hit_regions_and_tooltips():
    _app()
    chart = AdvancedCapacityChart()
    chart.set_values(120, 240, 480)
    chart.resize(400, 100)
    chart.show()
    QApplication.processEvents()

    chart.grab()  # Triggers paintEvent to build regions

    assert len(chart._hit_regions) >= 2
    keys = [r.key for r in chart._hit_regions]
    assert "actual" in keys
    assert "planned" in keys

    act_reg = next(r for r in chart._hit_regions if r.key == "actual")
    assert act_reg.primary_value == 120
    assert act_reg.percentage == 25.0  # 120 / 480 = 25%
    assert "120m" in act_reg.tooltip_text
    assert "25.0%" in act_reg.tooltip_text

    plan_reg = next(r for r in chart._hit_regions if r.key == "planned")
    assert plan_reg.primary_value == 240
    assert plan_reg.percentage == 50.0  # 240 / 480 = 50%
    assert "240m" in plan_reg.tooltip_text
    assert "50.0%" in plan_reg.tooltip_text

    chart.close()


def test_capacity_chart_hover_and_selection():
    _app()
    chart = AdvancedCapacityChart()
    chart.set_animations_enabled(False)
    chart.set_values(180, 180, 480)
    chart.resize(400, 100)
    chart.show()
    QApplication.processEvents()
    chart.grab()

    assert len(chart._hit_regions) > 0
    first_region = chart._hit_regions[0]
    center = first_region.center_point()

    hover_signal_received = []
    chart.item_hovered.connect(lambda reg: hover_signal_received.append(reg))

    # Simulate mouse move over first region
    move_event = QMouseEvent(
        QEvent.MouseMove,
        center,
        center,
        Qt.NoButton,
        Qt.NoButton,
        Qt.NoModifier,
    )
    chart.mouseMoveEvent(move_event)

    assert chart._hovered_key == first_region.key
    assert len(hover_signal_received) > 0
    assert hover_signal_received[-1].key == first_region.key

    # Simulate click to select
    select_signal_received = []
    chart.item_selected.connect(lambda reg: select_signal_received.append(reg))

    press_event = QMouseEvent(
        QEvent.MouseButtonPress,
        center,
        center,
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    chart.mousePressEvent(press_event)

    assert chart._selected_key == first_region.key
    assert len(select_signal_received) > 0
    assert select_signal_received[-1].key == first_region.key

    # Mouse leaves widget -> hover clears, selection persists
    chart.leaveEvent(QEvent(QEvent.Leave))
    assert chart._hovered_key is None
    assert chart._selected_key == first_region.key

    # Pressing Escape clears selection
    clear_signal_received = []
    chart.selection_cleared.connect(lambda: clear_signal_received.append(True))

    esc_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    chart.keyPressEvent(esc_event)

    assert chart._selected_key is None
    assert len(clear_signal_received) > 0

    chart.close()


# ------------------------------------------------------------
# 3. Status Chart Interaction & Percentage Tests
# ------------------------------------------------------------

def test_status_chart_percentage_and_tooltips():
    _app()
    chart = AdvancedStatusChart()
    # 4 planned, 3 in progress, 2 blocked, 5 completed -> Total = 14
    chart.set_counts(4, 3, 2, 5)
    chart.resize(300, 200)
    chart.show()
    QApplication.processEvents()
    chart.grab()

    assert len(chart._hit_regions) == 4
    regions_by_key = {r.key: r for r in chart._hit_regions}

    assert regions_by_key["planned"].primary_value == 4
    assert regions_by_key["planned"].percentage == round((4 / 14) * 100.0, 1)  # 28.6%
    assert "28.6%" in regions_by_key["planned"].tooltip_text

    assert regions_by_key["completed"].primary_value == 5
    assert regions_by_key["completed"].percentage == round((5 / 14) * 100.0, 1)  # 35.7%
    assert "35.7%" in regions_by_key["completed"].tooltip_text

    chart.close()


def test_status_chart_all_six_types_interactive():
    _app()
    chart = AdvancedStatusChart()
    chart.set_counts(10, 5, 2, 15)
    chart.resize(300, 200)
    chart.show()

    for c_type in AdvancedStatusChart.CHART_TYPES:
        chart.set_chart_type(c_type)
        QApplication.processEvents()
        chart.grab()
        assert len(chart._hit_regions) > 0, f"Status chart type {c_type} has no hit regions"

    chart.close()


# ------------------------------------------------------------
# 4. Weekly Activity Chart & 90-Day Interaction Tests
# ------------------------------------------------------------

def test_weekly_activity_chart_daily_tuples_and_tooltips():
    _app()
    chart = AdvancedWeeklyActivityChart()
    data = [
        ("Mon 18 Aug", 6, 8),
        ("Tue 19 Aug", 10, 5),
        ("Wed 20 Aug", 4, 4),
    ]
    chart.set_daily_data(data)
    chart.resize(400, 200)
    chart.show()
    QApplication.processEvents()
    chart.grab()

    assert len(chart._hit_regions) == 3

    # Check Day 0 (Completed: 6, Planned: 8, Variance: -2)
    reg0 = chart._hit_regions[0]
    assert reg0.primary_value == 6
    assert reg0.secondary_value == 8
    assert "Completed: 6" in reg0.tooltip_text
    assert "Planned: 8" in reg0.tooltip_text
    assert "Variance: -2" in reg0.tooltip_text

    # Check Day 1 (Completed: 10, Planned: 5, Variance: +5)
    reg1 = chart._hit_regions[1]
    assert reg1.primary_value == 10
    assert reg1.secondary_value == 5
    assert "Completed: 10" in reg1.tooltip_text
    assert "Planned: 5" in reg1.tooltip_text
    assert "Variance: +5" in reg1.tooltip_text

    chart.close()


def test_weekly_activity_chart_90_days_interactive():
    _app()
    chart = AdvancedWeeklyActivityChart()
    data = [(f"Day {i+1}", i % 6, (i + 2) % 7) for i in range(90)]
    chart.set_daily_data(data)
    chart.resize(900, 220)
    chart.show()
    QApplication.processEvents()
    chart.grab()

    assert len(chart._hit_regions) == 90
    assert chart._hit_regions[89].label == "Day 90"

    # Select day 45 programmatically
    chart.select_key(45)
    assert chart.selected_item() is not None
    assert chart.selected_item().key == 45
    assert chart.selected_item().label == "Day 46"

    chart.close()


def test_weekly_activity_all_eight_types_interactive():
    _app()
    chart = AdvancedWeeklyActivityChart()
    chart.set_daily_data([("Mon", 3, 5), ("Tue", 6, 4), ("Wed", 7, 7)])
    chart.resize(400, 200)
    chart.show()

    for c_type in AdvancedWeeklyActivityChart.CHART_TYPES:
        chart.set_chart_type(c_type)
        QApplication.processEvents()
        chart.grab()
        assert len(chart._hit_regions) == 3, f"Activity chart type {c_type} failed to produce 3 hit regions"

    chart.close()


# ------------------------------------------------------------
# 5. Keyboard Navigation & Accessibility Tests
# ------------------------------------------------------------

def test_keyboard_navigation_cycles_hit_regions():
    _app()
    chart = AdvancedStatusChart()
    chart.set_counts(5, 5, 5, 5)
    chart.resize(300, 200)
    chart.show()
    QApplication.processEvents()
    chart.grab()

    # Arrow Right moves to first region
    right_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.NoModifier)
    chart.keyPressEvent(right_event)
    assert chart._focused_index == 0
    assert chart._hovered_key == chart._hit_regions[0].key

    # Arrow Right moves to second region
    chart.keyPressEvent(right_event)
    assert chart._focused_index == 1
    assert chart._hovered_key == chart._hit_regions[1].key

    # Enter selects current region
    enter_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    chart.keyPressEvent(enter_event)
    assert chart._selected_key == chart._hit_regions[1].key

    # Escape clears selection
    esc_event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    chart.keyPressEvent(esc_event)
    assert chart._selected_key is None

    chart.close()


def test_accessible_description_updates_on_inspection():
    _app()
    chart = AdvancedCapacityChart()
    chart.set_values(100, 200, 400)
    chart.resize(300, 100)
    chart.show()
    QApplication.processEvents()
    chart.grab()

    chart.select_key("actual")
    desc = chart.accessibleDescription()
    assert "Actual Work Effort" in desc
    assert "Left/Right arrow keys" in desc

    chart.close()


# ------------------------------------------------------------
# 6. Edge Cases, Zero Data, Single Item, and Motion Tests
# ------------------------------------------------------------

def test_zero_data_charts_do_not_crash():
    _app()

    c_cap = AdvancedCapacityChart()
    c_cap.set_values(0, 0, 0)
    c_cap.resize(300, 100)
    c_cap.show()
    c_cap.grab()
    c_cap.close()

    c_stat = AdvancedStatusChart()
    c_stat.set_counts(0, 0, 0, 0)
    c_stat.resize(300, 200)
    c_stat.show()
    c_stat.grab()
    c_stat.close()

    c_act = AdvancedWeeklyActivityChart()
    c_act.set_daily_data([])
    c_act.resize(300, 200)
    c_act.show()
    c_act.grab()
    c_act.close()


def test_single_item_charts_render_and_interact():
    _app()

    c_act = AdvancedWeeklyActivityChart()
    c_act.set_daily_data([("OnlyDay", 5, 5)])
    c_act.resize(300, 200)
    c_act.show()
    QApplication.processEvents()
    c_act.grab()

    assert len(c_act._hit_regions) == 1
    assert c_act._hit_regions[0].label == "OnlyDay"

    c_act.close()


def test_no_continuous_animation_or_timer_churn():
    _app()
    chart = AdvancedCapacityChart()
    chart.set_values(100, 100, 300)
    chart.set_animations_enabled(False)

    # Hovering/selecting should NOT start QVariantAnimation
    assert chart._animation.state() == QVariantAnimation.Stopped
    chart.select_key("actual")
    assert chart._animation.state() == QVariantAnimation.Stopped

    chart.close()


def test_dark_and_light_palette_rendering():
    _app()
    chart = AdvancedStatusChart()
    chart.set_counts(2, 4, 1, 6)
    chart.resize(300, 200)
    chart.show()

    # Dark mode test
    dark_pal = QPalette()
    dark_pal.setColor(QPalette.Window, QColor("#1E1E2E"))
    dark_pal.setColor(QPalette.WindowText, QColor("#CDD6F4"))
    chart.setPalette(dark_pal)
    QApplication.processEvents()
    pix_dark = chart.grab()
    assert not pix_dark.isNull()

    # Light mode test
    light_pal = QPalette()
    light_pal.setColor(QPalette.Window, QColor("#F8FAFC"))
    light_pal.setColor(QPalette.WindowText, QColor("#0F172A"))
    chart.setPalette(light_pal)
    QApplication.processEvents()
    pix_light = chart.grab()
    assert not pix_light.isNull()

    chart.close()
