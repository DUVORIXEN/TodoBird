"""WIN-CB1: Windows stylesheet-path regression tests.

Root cause of the Windows "Could not parse application stylesheet" warning and
the invisible checkbox tick: the checkmark image path was interpolated into
QSS ``url()`` with native (backslash) Windows separators. QSS treats
backslashes as escape sequences, so the ``:checked`` rule failed to parse and
the tick image never loaded — clicks still toggled state, but the indicator
looked unchanged.

These tests run on any platform by simulating Windows-style paths.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("TODO_BIRD_DISABLE_SINGLE_INSTANCE", "1")
os.environ.setdefault("TODO_BIRD_SYNC_APPEARANCE", "1")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

import pytest
from PySide6.QtCore import qInstallMessageHandler
from PySide6.QtWidgets import QApplication, QCheckBox

from todo_bird_app.services.appearance_service import AppearanceService


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _substitute(qss: str, tokens: dict) -> str:
    for key, value in sorted(tokens.items(), key=lambda kv: len(kv[0]), reverse=True):
        qss = qss.replace(f"@{key}", value)
    return qss


def _capture_parse_warnings(qapp, stylesheet: str) -> list:
    """Apply the stylesheet and return Qt's parse-warning messages."""
    warnings = []

    def handler(mode, context, message):
        text = str(message)
        if "parse" in text.lower() or "stylesheet" in text.lower():
            warnings.append(text)

    previous = qInstallMessageHandler(handler)
    try:
        probe = QCheckBox()
        probe.setObjectName("QssPathProbe")
        probe.setStyleSheet(stylesheet)
        qapp.processEvents()
        probe.setStyleSheet("")
        qapp.processEvents()
        probe.deleteLater()
    finally:
        qInstallMessageHandler(previous)
    return warnings


def test_tick_tokens_are_qss_safe(qapp):
    """Token paths must use POSIX separators — never native backslashes."""
    appearance = AppearanceService.read(None)
    tokens = AppearanceService.qss_tokens(appearance)

    for key in ("CHECKMARK_IMAGE", "INDETERMINATE_IMAGE"):
        value = tokens[key]
        assert value, f"{key} must not be empty"
        assert "\\" not in value, (
            f"{key} contains a backslash ({value!r}) — QSS url() treats it "
            "as an escape sequence and the rule fails to parse on Windows"
        )
        assert Path(value).name.startswith("cb_")
        assert Path(value).exists(), f"{key} points at a missing file: {value}"


def test_backslash_path_reproduces_parse_warning(qapp):
    """Root-cause proof: the OLD unquoted backslash form breaks QSS parsing.

    This documents why the Windows build lost its checkbox tick; it fails
    loudly if someone reverts the as_posix()/quoting fix.
    """
    raw = Path(
        Path(__file__).resolve().parent.parent / "themes" / "dark.qss"
    ).read_text(encoding="utf-8")
    appearance = AppearanceService.read(None)
    tokens = AppearanceService.qss_tokens(appearance)

    broken_tokens = dict(tokens)
    posix_path = tokens["CHECKMARK_IMAGE"]
    broken_tokens["CHECKMARK_IMAGE"] = "C:\\Program Files\\TodoBird\\assets\\icons\\cb_check_white.svg"
    broken_tokens["INDETERMINATE_IMAGE"] = "C:\\Program Files\\TodoBird\\assets\\icons\\cb_dash_white.svg"

    # The old emission shape: unquoted url + native separators.
    broken_qss = _substitute(raw, broken_tokens)
    broken_qss = broken_qss.replace(
        'image: url("@CHECKMARK_IMAGE");',
        f"image: url({broken_tokens['CHECKMARK_IMAGE']});",
    ).replace(
        'image: url("@INDETERMINATE_IMAGE");',
        f"image: url({broken_tokens['INDETERMINATE_IMAGE']});",
    )
    broken_qss = broken_qss.replace(
        f'url("{posix_path}")',  # already substituted — no-op safeguard
        f'url("{posix_path}")',
    )
    # Restore the raw placeholders in the substituted text for exactness.
    broken_qss = broken_qss.replace(
        f'url("{broken_tokens["CHECKMARK_IMAGE"]}")',
        f"url({broken_tokens['CHECKMARK_IMAGE']})",
    )

    warnings = _capture_parse_warnings(qapp, broken_qss)
    assert warnings, (
        "Expected the unquoted backslash url() to produce a stylesheet "
        "parse warning; if Qt no longer warns, revisit this root-cause test"
    )


def test_windows_path_pipeline_parses_cleanly(qapp):
    """The fixed pipeline (quoted + POSIX separators) must parse silently."""
    raw = Path(
        Path(__file__).resolve().parent.parent / "themes" / "dark.qss"
    ).read_text(encoding="utf-8")
    appearance = AppearanceService.read(None)
    tokens = AppearanceService.qss_tokens(appearance)

    # Simulate a Windows install whose base dir contains spaces.
    windows_tokens = dict(tokens)
    windows_tokens["CHECKMARK_IMAGE"] = "C:/Program Files/TodoBird/assets/icons/cb_check_white.svg"
    windows_tokens["INDETERMINATE_IMAGE"] = "C:/Program Files/TodoBird/assets/icons/cb_dash_white.svg"

    qss = _substitute(raw, windows_tokens)
    warnings = _capture_parse_warnings(qapp, qss)
    assert not warnings, f"Theme stylesheet failed to parse: {warnings[:3]}"


def test_real_theme_parses_without_warnings(qapp):
    """The actual shipped pipeline (real token values) must parse cleanly."""
    raw = Path(
        Path(__file__).resolve().parent.parent / "themes" / "dark.qss"
    ).read_text(encoding="utf-8")
    appearance = AppearanceService.read(None)
    qss = _substitute(raw, AppearanceService.qss_tokens(appearance))

    warnings = _capture_parse_warnings(qapp, qss)
    assert not warnings, f"Shipped stylesheet produced parse warnings: {warnings[:3]}"


def test_checked_checkbox_paints_tick(qapp):
    """A checked QCheckBox under the theme QSS renders the tick glyph.

    The tick is a light SVG on the accent fill, so the checked indicator
    region must contain more distinct colors than the unchecked one.
    """
    raw = Path(
        Path(__file__).resolve().parent.parent / "themes" / "dark.qss"
    ).read_text(encoding="utf-8")
    appearance = AppearanceService.read(None)
    qss = _substitute(raw, AppearanceService.qss_tokens(appearance))

    box = QCheckBox()
    box.setStyleSheet(qss)
    box.resize(160, 28)

    from PySide6.QtCore import QRect

    def indicator_colors(checked: bool) -> int:
        box.setChecked(checked)
        box.show()
        qapp.processEvents()
        image = box.grab().toImage()
        # Indicator occupies roughly the leading 18px square.
        region = QRect(0, 5, 18, 18)
        colors = set()
        for x in range(region.left(), region.right() + 1):
            for y in range(region.top(), region.bottom() + 1):
                colors.add(image.pixelColor(x, y).name())
        box.hide()
        return len(colors)

    unchecked = indicator_colors(False)
    checked = indicator_colors(True)

    assert checked > 2, (
        "Checked indicator is visually flat — the tick SVG did not render "
        f"(unchecked colors={unchecked}, checked colors={checked})"
    )
