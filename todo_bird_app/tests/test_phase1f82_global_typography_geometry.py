
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QPushButton,
    QComboBox,
    QLineEdit,
    QProgressBar,
)

from todo_bird_app.services.typography_service import (
    TypographyService,
)


def _app():
    return QApplication.instance() or QApplication([])


class _Settings:
    def __init__(self, size):
        self.size = size

    def get(self, key, default=None):
        values = {
            "ui_font_family": "DejaVu Sans",
            "ui_font_size": self.size,
            "ui_font_weight": "normal",
        }
        return values.get(key, default)


def _host():
    root = QWidget()
    layout = QVBoxLayout(root)

    button = QPushButton("Complete Task")
    button.setFixedHeight(32)

    combo = QComboBox()
    combo.addItems(["One", "Two"])
    combo.setFixedHeight(36)

    line = QLineEdit()
    line.setFixedHeight(30)

    decorative = QProgressBar()
    decorative.setFixedHeight(10)

    for widget in (
        button,
        combo,
        line,
        decorative,
    ):
        layout.addWidget(widget)

    return (
        root,
        button,
        combo,
        line,
        decorative,
    )


def test_large_font_expands_fixed_text_controls():
    _app()

    root, button, combo, line, _ = _host()

    TypographyService.apply_to_widget(
        root,
        "tasklist",
        _Settings(20),
    )

    assert button.height() >= 32
    assert button.minimumHeight() > 32

    assert combo.minimumHeight() >= 36
    assert line.minimumHeight() >= 30


def test_fixed_semantics_are_preserved_dynamically():
    _app()

    root, button, combo, line, _ = _host()

    TypographyService.apply_to_widget(
        root,
        "tasklist",
        _Settings(20),
    )

    assert (
        button.minimumHeight()
        == button.maximumHeight()
    )

    assert (
        combo.minimumHeight()
        == combo.maximumHeight()
    )

    assert (
        line.minimumHeight()
        == line.maximumHeight()
    )


def test_large_then_small_font_returns_to_original_baseline():
    _app()

    root, button, combo, line, _ = _host()

    TypographyService.apply_to_widget(
        root,
        "tasklist",
        _Settings(20),
    )

    enlarged_button = button.minimumHeight()

    TypographyService.apply_to_widget(
        root,
        "tasklist",
        _Settings(8),
    )

    assert button.minimumHeight() <= enlarged_button
    assert button.minimumHeight() >= 32

    assert combo.minimumHeight() >= 36
    assert line.minimumHeight() >= 30


def test_decorative_progress_bar_height_is_untouched():
    _app()

    root, _, _, _, decorative = _host()

    TypographyService.apply_to_widget(
        root,
        "tasklist",
        _Settings(20),
    )

    assert decorative.minimumHeight() == 10
    assert decorative.maximumHeight() == 10


def test_original_geometry_is_recorded_once():
    _app()

    root, button, _, _, _ = _host()

    TypographyService.apply_to_widget(
        root,
        "tasklist",
        _Settings(20),
    )

    assert (
        button.property(
            "_todo_bird_typography_original_min_height"
        )
        == 32
    )

    assert (
        button.property(
            "_todo_bird_typography_original_max_height"
        )
        == 32
    )

    TypographyService.apply_to_widget(
        root,
        "tasklist",
        _Settings(18),
    )

    assert (
        button.property(
            "_todo_bird_typography_original_min_height"
        )
        == 32
    )


def test_wbs_settings_panel_is_not_height_capped():
    text = Path(
        "todo_bird_app/widgets/"
        "wbs_settings_widget.py"
    ).read_text()

    assert "self.setFixedHeight(150)" not in text
    assert "self.setMinimumHeight(150)" in text


def test_geometry_safety_does_not_target_labels_or_charts():
    text = Path(
        "todo_bird_app/services/"
        "typography_service.py"
    ).read_text()

    start = text.index(
        "geometry_types = ("
    )
    end = text.index(
        "for target_type in geometry_types:",
        start,
    )

    geometry_block = text[start:end]

    assert "QLabel" not in geometry_block
    assert "QProgressBar" not in geometry_block
    assert "QWidget," not in geometry_block
