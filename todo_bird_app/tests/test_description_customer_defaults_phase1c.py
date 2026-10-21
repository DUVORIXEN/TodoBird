
import pytest

from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import QApplication

from todo_bird_app.widgets.rich_text_editor import RichTextEditor


class FakeSettings:
    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    return app


def custom_settings():
    return FakeSettings({
        "description_font_use_app_default": False,
        "description_font_family": "DejaVu Sans",
        "description_font_size": 18,
        "description_font_color_mode": "custom",
        "description_font_color": "#8E44AD",
    })


def test_desc_default_family_and_size(qapp):
    e = RichTextEditor(settings_manager=custom_settings())
    f = e.editor.document().defaultFont()
    assert f.family() == "DejaVu Sans"
    assert int(round(f.pointSizeF())) == 18


def test_desc_default_typing_color(qapp):
    e = RichTextEditor(settings_manager=custom_settings())
    cf = e.editor.currentCharFormat()
    c = cf.foreground().color()
    assert c.isValid()
    assert c.name().upper() == "#8E44AD"


def test_desc_explicit_existing_html_not_restyled(qapp):
    e = RichTextEditor(settings_manager=custom_settings())
    e.setHtml(
        '<p><span style="font-family:\'Courier New\'; '
        'font-size:24pt; color:#ff0000;">Existing</span></p>'
    )

    cursor = e.editor.document().find("Existing")
    assert not cursor.isNull()
    fmt = cursor.charFormat()

    assert int(round(fmt.fontPointSize())) == 24
    assert fmt.foreground().color().name().upper() == "#FF0000"


def test_desc_auto_mode_uses_no_forced_foreground(qapp):
    s = FakeSettings({
        "description_font_use_app_default": False,
        "description_font_family": "DejaVu Sans",
        "description_font_size": 14,
        "description_font_color_mode": "auto",
    })
    e = RichTextEditor(settings_manager=s)
    # Auto remains theme-driven. We verify configuration resolution.
    family, size, mode, _color = e._description_default_values()
    assert family == "DejaVu Sans"
    assert size == 14
    assert mode == "auto"


def test_desc_size_clamps_low(qapp):
    s = FakeSettings({
        "description_font_use_app_default": False,
        "description_font_size": 1,
    })
    e = RichTextEditor(settings_manager=s)
    assert e._description_default_values()[1] == 6


def test_desc_size_clamps_high(qapp):
    s = FakeSettings({
        "description_font_use_app_default": False,
        "description_font_size": 300,
    })
    e = RichTextEditor(settings_manager=s)
    assert e._description_default_values()[1] == 96


def test_desc_inline_format_survives_html_roundtrip(qapp):
    s = custom_settings()
    e = RichTextEditor(settings_manager=s)
    e.setHtml(
        '<p>Normal <span style="font-size:28pt; '
        'font-weight:700; color:#008000;">Special</span></p>'
    )
    html = e.toHtml()

    e2 = RichTextEditor(settings_manager=s)
    e2.setHtml(html)

    assert "Normal" in e2.toPlainText()
    assert "Special" in e2.toPlainText()

    cursor = e2.editor.document().find("Special")
    fmt = cursor.charFormat()
    assert int(round(fmt.fontPointSize())) == 28
    assert fmt.foreground().color().name().upper() == "#008000"


def test_desc_plain_text_search_authority(qapp):
    e = RichTextEditor(settings_manager=custom_settings())
    e.setHtml('<p><span style="color:#ff0000;">Critical customer note</span></p>')
    assert e.toPlainText() == "Critical customer note"


def test_desc_use_app_default(qapp):
    s = FakeSettings({
        "description_font_use_app_default": True,
        "description_font_family": "Courier New",
        "description_font_size": 48,
        "description_font_color_mode": "custom",
        "description_font_color": "#FF0000",
    })
    e = RichTextEditor(settings_manager=s)

    family, size, mode, _color = e._description_default_values()

    assert family == QApplication.font().family()
    assert size == (
        QApplication.font().pointSize()
        if QApplication.font().pointSize() > 0
        else 13
    )
    assert mode == "auto"
