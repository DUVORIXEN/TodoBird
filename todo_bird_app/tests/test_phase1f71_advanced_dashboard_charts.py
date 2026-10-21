
from pathlib import Path

from PySide6.QtWidgets import QApplication

from todo_bird_app.widgets.dashboard_charts import (
    AdvancedCapacityChart,
    AdvancedStatusChart,
    AdvancedWeeklyActivityChart,
)


def _app():
    return QApplication.instance() or QApplication([])


def test_capacity_chart_library_is_expanded():
    assert AdvancedCapacityChart.CHART_TYPES == (
        "Segmented Bar",
        "Stacked Bar",
        "Bullet",
        "Gauge",
        "Semi Gauge",
        "Donut",
        "Radial Progress",
    )


def test_status_chart_library_is_expanded():
    assert AdvancedStatusChart.CHART_TYPES == (
        "Executive Ring",
        "Donut",
        "Pie",
        "Waffle",
        "Stacked Bar",
        "Radial Rings",
    )


def test_weekly_chart_library_is_expanded():
    assert AdvancedWeeklyActivityChart.CHART_TYPES == (
        "Grouped Bar",
        "Stacked Bar",
        "Line",
        "Smooth Line",
        "Area",
        "Lollipop",
        "Step Line",
        "Combo",
    )


def test_capacity_widget_preserves_existing_data_contract():
    _app()
    chart = AdvancedCapacityChart()

    chart.set_values(
        120,
        240,
        480,
    )

    assert chart.actual_m == 120
    assert chart.planned_m == 240
    assert chart.capacity_m == 480

    chart.close()


def test_status_widget_preserves_existing_data_contract():
    _app()
    chart = AdvancedStatusChart()

    chart.set_counts(
        4,
        3,
        2,
        5,
    )

    assert chart.counts == {
        "planned": 4,
        "in_progress": 3,
        "blocked": 2,
        "completed": 5,
    }

    chart.close()


def test_weekly_widget_preserves_existing_data_contract():
    _app()
    chart = AdvancedWeeklyActivityChart()

    data = [
        ("Mon", 2, 4),
        ("Tue", 3, 5),
        ("Wed", 4, 4),
    ]

    chart.set_daily_data(data)

    assert chart.daily_data == data

    chart.close()


def test_every_chart_type_can_be_selected_without_error():
    _app()

    capacity = AdvancedCapacityChart()
    status = AdvancedStatusChart()
    weekly = AdvancedWeeklyActivityChart()

    for chart_type in capacity.CHART_TYPES:
        capacity.set_chart_type(chart_type)
        assert capacity.chart_type == chart_type

    for chart_type in status.CHART_TYPES:
        status.set_chart_type(chart_type)
        assert status.chart_type == chart_type

    for chart_type in weekly.CHART_TYPES:
        weekly.set_chart_type(chart_type)
        assert weekly.chart_type == chart_type

    capacity.close()
    status.close()
    weekly.close()


def test_animation_can_be_disabled():
    _app()
    chart = AdvancedWeeklyActivityChart()

    chart.set_animations_enabled(False)
    chart.set_daily_data([
        ("Mon", 1, 2),
        ("Tue", 2, 3),
    ])

    assert chart._animation_progress == 1.0

    chart.close()


def test_dashboard_wires_advanced_widgets():
    text = Path(
        "todo_bird_app/views/dashboard_view.py"
    ).read_text()

    assert "AdvancedCapacityChart()" in text
    assert "AdvancedStatusChart()" in text
    assert "AdvancedWeeklyActivityChart()" in text


def test_dashboard_exposes_expanded_chart_choices():
    text = Path(
        "todo_bird_app/views/dashboard_view.py"
    ).read_text()

    for label in (
        "Segmented Bar",
        "Bullet",
        "Semi Gauge",
        "Radial Progress",
        "Executive Ring",
        "Waffle",
        "Radial Rings",
        "Smooth Line",
        "Lollipop",
        "Step Line",
        "Combo",
    ):
        assert label in text


def test_chart_can_render_offscreen():
    app = _app()

    widgets = [
        AdvancedCapacityChart(),
        AdvancedStatusChart(),
        AdvancedWeeklyActivityChart(),
    ]

    widgets[0].set_values(
        120,
        180,
        480,
    )
    widgets[1].set_counts(
        3,
        2,
        1,
        4,
    )
    widgets[2].set_daily_data([
        ("Mon", 2, 3),
        ("Tue", 4, 5),
        ("Wed", 3, 4),
        ("Thu", 5, 5),
        ("Fri", 4, 6),
        ("Sat", 2, 2),
        ("Sun", 3, 4),
    ])

    for widget in widgets:
        widget.resize(
            480,
            max(
                180,
                widget.minimumHeight(),
            ),
        )
        widget.show()
        app.processEvents()

        pixmap = widget.grab()

        assert not pixmap.isNull()
        assert pixmap.width() > 0
        assert pixmap.height() > 0

        widget.close()
