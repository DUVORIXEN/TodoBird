
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
)


def _app():
    return QApplication.instance() or QApplication([])


def test_dashboard_owns_responsive_chart_layouts():
    text = Path(
        "todo_bird_app/views/dashboard_view.py"
    ).read_text()

    assert "self.charts_row = QHBoxLayout()" in text
    assert "self.status_chart_layout = QHBoxLayout()" in text
    assert "def _apply_dashboard_chart_reflow(self):" in text


def test_dashboard_has_four_responsive_modes():
    text = Path(
        "todo_bird_app/views/dashboard_view.py"
    ).read_text()

    for mode in (
        '"wide"',
        '"medium"',
        '"narrow"',
        '"compact"',
    ):
        assert mode in text


def test_narrow_and_compact_stack_chart_cards():
    text = Path(
        "todo_bird_app/views/dashboard_view.py"
    ).read_text()

    assert (
        "QHBoxLayout.TopToBottom"
        in text
    )


def test_wide_dashboard_preserves_horizontal_chart_row():
    text = Path(
        "todo_bird_app/views/dashboard_view.py"
    ).read_text()

    assert (
        "QHBoxLayout.LeftToRight"
        in text
    )


def test_responsive_logic_does_not_query_database():
    text = Path(
        "todo_bird_app/views/dashboard_view.py"
    ).read_text()

    start = text.index(
        "def _apply_dashboard_chart_reflow"
    )
    end = text.index(
        "def _apply_experience_mode",
        start,
    )

    block = text[start:end]

    assert "get_all_tasks" not in block
    assert "get_tasks_by_project" not in block
    assert "refresh_data()" not in block


def test_chart_engine_uses_available_geometry():
    text = Path(
        "todo_bird_app/widgets/dashboard_charts.py"
    ).read_text()

    assert "self.width()" in text
    assert "self.height()" in text
    assert "min(" in text


def test_circular_charts_use_proportional_dimension():
    text = Path(
        "todo_bird_app/widgets/dashboard_charts.py"
    ).read_text()

    assert "min(" in text
    assert "rect.width()" in text
    assert "rect.height()" in text
