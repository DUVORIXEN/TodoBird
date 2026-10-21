
from pathlib import Path

from PySide6.QtWidgets import QApplication

from todo_bird_app.widgets.dashboard_charts import (
    AdvancedWeeklyActivityChart,
)


def _app():
    return QApplication.instance() or QApplication([])


def test_dashboard_has_four_execution_ranges():
    text = Path(
        "todo_bird_app/views/dashboard_view.py"
    ).read_text()

    for label, days in (
        ('("7D", 7)', 7),
        ('("14D", 14)', 14),
        ('("30D", 30)', 30),
        ('("90D", 90)', 90),
    ):
        assert label in text


def test_range_selection_persists():
    text = Path(
        "todo_bird_app/views/dashboard_view.py"
    ).read_text()

    assert (
        '"dashboard_activity_range_days"'
        in text
    )
    assert (
        "def _on_activity_range_changed"
        in text
    )


def test_range_changes_refresh_same_dashboard_authority():
    text = Path(
        "todo_bird_app/views/dashboard_view.py"
    ).read_text()

    start = text.index(
        "def _on_activity_range_changed"
    )
    end = text.index(
        "def _on_capacity_chart_changed",
        start,
    )

    block = text[start:end]

    assert "self.refresh_data()" in block


def test_kpi_animation_is_finite():
    text = Path(
        "todo_bird_app/views/dashboard_view.py"
    ).read_text()

    assert "QVariantAnimation" in text
    assert "setDuration(420)" in text
    assert "setDuration(460)" in text
    assert "QEasingCurve.OutCubic" in text


def test_kpi_animation_respects_reduced_motion():
    text = Path(
        "todo_bird_app/views/dashboard_view.py"
    ).read_text()

    assert (
        "def _metric_animations_enabled"
        in text
    )
    assert '"reduce_motion"' in text


def test_weekly_chart_accepts_90_daily_observations():
    _app()

    chart = AdvancedWeeklyActivityChart()

    data = [
        (
            f"D{i + 1}",
            i % 5,
            (i + 2) % 7,
        )
        for i in range(90)
    ]

    chart.set_animations_enabled(False)
    chart.set_daily_data(data)

    assert len(chart.daily_data) == 90

    chart.resize(800, 230)
    chart.show()

    QApplication.processEvents()

    pixmap = chart.grab()

    assert not pixmap.isNull()
    assert pixmap.width() > 0

    chart.close()


def test_axis_label_density_is_visual_only():
    text = Path(
        "todo_bird_app/widgets/dashboard_charts.py"
    ).read_text()

    assert "max_visible_labels" in text
    # Label selection is now a precomputed shown-index list (with the
    # crowded end-label predecessor dropped); the mechanism is visual-only.
    assert "shown_idxs" in text

    # Data series is still indexed from the complete daily_data list.
    assert "len(self.daily_data)" in text


def test_existing_advanced_chart_types_remain():
    chart_text = Path(
        "todo_bird_app/widgets/dashboard_charts.py"
    ).read_text()

    for name in (
        "Grouped Bar",
        "Stacked Bar",
        "Line",
        "Smooth Line",
        "Area",
        "Lollipop",
        "Step Line",
        "Combo",
    ):
        assert name in chart_text
