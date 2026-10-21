
from pathlib import Path

from PySide6.QtGui import QFont, QFontMetricsF
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem

from todo_bird_app.views.wbs_tree_delegate import (
    WBSTreeItemDelegate,
)


def _app():
    return QApplication.instance() or QApplication([])


class _Density:
    row_height = 28
    font_size = 9
    indent_px = 16


class _Custom:
    def get_density_metrics(self):
        return _Density()

    def get_preference(self, key, default=None):
        return default


class _Settings:
    def __init__(self, size):
        self.size = size

    def get(self, key, default=None):
        values = {
            "ui_font_family": "DejaVu Sans",
            "ui_font_size": self.size,
            "ui_font_weight": "normal",
            "font_override_tasklist": False,
        }
        return values.get(key, default)


def test_delegate_uses_typography_service():
    text = Path(
        "todo_bird_app/views/wbs_tree_delegate.py"
    ).read_text()

    assert "TypographyService.get_font_for_area" in text
    assert '"tasklist"' in text


def test_density_no_longer_sets_painter_font_size():
    text = Path(
        "todo_bird_app/views/wbs_tree_delegate.py"
    ).read_text()

    assert "font_size = metrics.font_size" not in text
    assert "font.setPointSize(font_size)" not in text


def test_large_font_expands_row_beyond_compact_density():
    _app()

    delegate = WBSTreeItemDelegate(
        custom_service=_Custom(),
        settings_manager=_Settings(20),
    )

    option = QStyleOptionViewItem()
    option.font = QFont("DejaVu Sans", 20)

    row_h = delegate._effective_row_height(option)

    font = delegate._resolved_font(option)
    required = int(
        QFontMetricsF(font).height() + 12
    )

    assert row_h >= required
    assert row_h > 28


def test_small_font_keeps_density_preference():
    _app()

    delegate = WBSTreeItemDelegate(
        custom_service=_Custom(),
        settings_manager=_Settings(8),
    )

    option = QStyleOptionViewItem()
    option.font = QFont("DejaVu Sans", 8)

    assert (
        delegate._effective_row_height(option)
        >= 28
    )


def test_row_height_monotonically_grows_with_large_fonts():
    _app()

    heights = []

    for size in (8, 10, 12, 14, 16, 18, 20):
        delegate = WBSTreeItemDelegate(
            custom_service=_Custom(),
            settings_manager=_Settings(size),
        )

        option = QStyleOptionViewItem()
        option.font = QFont(
            "DejaVu Sans",
            size,
        )

        heights.append(
            delegate._effective_row_height(option)
        )

    assert heights == sorted(heights)
    assert heights[-1] > heights[0]


def test_density_is_minimum_not_absolute_height():
    text = Path(
        "todo_bird_app/views/wbs_tree_delegate.py"
    ).read_text()

    assert "max(" in text
    assert "density_height" in text
    assert "text_minimum" in text


def test_no_structural_wbs_mutation_added():
    text = Path(
        "todo_bird_app/views/wbs_tree_delegate.py"
    ).read_text()

    for forbidden in (
        "insert_subtask",
        "update_subtask",
        "delete_subtask",
        "reparent_subtask",
        "drag_drop_move",
    ):
        assert forbidden not in text
