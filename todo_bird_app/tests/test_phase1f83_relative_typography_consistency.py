
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QPushButton,
    QWidget,
    QVBoxLayout,
)

from todo_bird_app.services.typography_service import (
    TypographyService,
)


ROOT = Path("todo_bird_app")


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


def test_relative_role_tracks_base_font_change():
    _app()

    root = QWidget()
    layout = QVBoxLayout(root)

    heading = QLabel("Heading")
    layout.addWidget(heading)

    TypographyService.set_relative_font_role(
        heading,
        delta_pt=4,
        weight="bold",
    )

    TypographyService.apply_to_widget(
        root,
        "tasklist",
        _Settings(10),
    )

    assert heading.font().pointSize() == 14
    assert heading.font().bold()

    TypographyService.apply_to_widget(
        root,
        "tasklist",
        _Settings(18),
    )

    assert heading.font().pointSize() == 22
    assert heading.font().bold()


def test_relative_role_does_not_accumulate_delta():
    _app()

    root = QWidget()
    layout = QVBoxLayout(root)

    label = QLabel("Metric")
    layout.addWidget(label)

    TypographyService.set_relative_font_role(
        label,
        delta_pt=5,
    )

    for _ in range(5):
        TypographyService.apply_to_widget(
            root,
            "tasklist",
            _Settings(12),
        )

    assert label.font().pointSize() == 17


def test_relative_button_role_still_gets_geometry_safety():
    _app()

    root = QWidget()
    layout = QVBoxLayout(root)

    button = QPushButton("Large Action")
    button.setFixedHeight(32)

    TypographyService.set_relative_font_role(
        button,
        delta_pt=3,
        weight="bold",
    )

    layout.addWidget(button)

    TypographyService.apply_to_widget(
        root,
        "tasklist",
        _Settings(20),
    )

    assert button.font().pointSize() == 23
    assert button.minimumHeight() > 32


def test_wbs_has_no_absolute_10pt_status_or_progress_font():
    text = (
        ROOT
        / "views"
        / "wbs_tree_delegate.py"
    ).read_text()

    assert "f.setPointSize(10)" not in text
    assert "label_font" in text
    assert "base_pt - 1" in text


def test_wbs_status_pill_grows_from_font_metrics():
    text = (
        ROOT
        / "views"
        / "wbs_tree_delegate.py"
    ).read_text()

    assert "QFontMetricsF(label_font)" in text
    assert "float(fm.height()) + 6.0" in text


def test_focus_action_buttons_are_not_width_capped():
    text = (
        ROOT
        / "views"
        / "focus_view.py"
    ).read_text()

    assert "self.btn_toggle.setFixedWidth(145)" not in text
    assert "self.btn_end.setFixedWidth(135)" not in text
    assert "self.btn_complete.setFixedWidth(145)" not in text

    assert "self.btn_toggle.setMinimumWidth(145)" in text
    assert "self.btn_end.setMinimumWidth(135)" in text
    assert "self.btn_complete.setMinimumWidth(145)" in text


def test_reminder_buttons_do_not_force_12px_typography():
    text = (
        ROOT
        / "widgets"
        / "reminder_dialog.py"
    ).read_text()

    for button_marker in (
        'QPushButton { background: qlineargradient',
        'QPushButton { background: rgba(245, 158, 11',
        'QPushButton { background: rgba(53, 132, 228',
    ):
        assert button_marker in text

    assert "font-weight: 700; font-size: 12px;" not in text
    assert "font-weight: 600; font-size: 12px;" not in text


def test_shared_metric_card_uses_relative_kpi_role():
    text = (
        ROOT
        / "widgets"
        / "modern_card.py"
    ).read_text()

    assert "delta_pt=12" in text
    assert "font-size: 22px" not in text


def test_gantt_toolbar_reacts_to_typography_change():
    text = (
        ROOT
        / "views"
        / "gantt_view.py"
    ).read_text()

    assert "def _sync_gantt_toolbar_typography_height" in text
    assert (
        "_GLOBAL_EVENT_BUS.typography_changed.connect"
        in text
    )


def test_dashboard_headroom_does_not_override_metric_size():
    text = (
        ROOT
        / "views"
        / "dashboard_view.py"
    ).read_text()

    assert (
        'font-size: 20px; font-weight: 800; color: #10B981;'
        not in text
    )

    assert (
        'font-size: 16px; font-weight: 800; color: #EF4444;'
        not in text
    )


def test_projects_titles_have_relative_semantic_roles():
    text = (
        ROOT
        / "views"
        / "projects_view.py"
    ).read_text()

    assert (
        '"_todo_bird_font_delta_pt"'
        in text
    )

    assert (
        'font-size: 16px; font-weight: 700'
        not in text
    )
