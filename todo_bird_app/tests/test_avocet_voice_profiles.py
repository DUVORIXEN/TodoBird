"""
TODO BIRD — Multi-Profile AI Voice Assistant & Tone Styles Library Test Suite
Validates:
1  All 9 voice profiles registered and valid
2  Female voice profiles (Serena, Nala, Elena, Maya, Durga)
3  Male voice profiles (Julian, Leo, Marcus, Oliver) with DSP filters
4  Tone styles library completeness
5  Tone style greeting text resolution
6  Custom greeting text override preservation
7  Preview voice profile execution non-blocking
8  Synthesis pipeline with acoustic parameter application
9  Male timbre DSP filter execution
10 SettingsView Voice Profile dropdown options and selection
11 SettingsView Preview Voice button trigger
12 SettingsView Tone Style dropdown selection and message prefill
13 Settings persistence for active_voice_profile and active_tone_style
14 DesktopCompanion voice_profile propagation
15 Production DB untouched
"""

import hashlib
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager
from todo_bird_app.services.avocet_voice_service import AvocetVoiceService
from todo_bird_app.settings.settings_manager import SettingsManager
from todo_bird_app.views.settings_view import SettingsView
from todo_bird_app.widgets.desktop_companion import DesktopCompanion

PROD_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "todo_bird.db"
INITIAL_PROD_DB_HASH = (
    hashlib.sha256(PROD_DB_PATH.read_bytes()).hexdigest()
    if PROD_DB_PATH.exists()
    else None
)


@pytest.fixture
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    yield app


@pytest.fixture
def temp_settings(tmp_path):
    db_file = tmp_path / "voice_profile_test.db"
    db = DatabaseManager(str(db_file))
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    settings = SettingsManager(db, config_dir=config_dir)
    settings.set("active_voice_profile", "serena")
    settings.set("active_tone_style", "affectionate_caring")
    settings.set("user_salutation", "Sudharshan garu")
    settings.set("assistant_name", "Durga")
    yield settings


class TestAvocetVoiceProfiles:
    """Authority test suite for selectable voice profiles, tone styles, and settings parity."""

    # 1. All 9 voice profiles registered
    def test_01_all_nine_profiles_registered(self):
        expected_ids = {
            "serena", "nala", "elena", "maya",
            "julian", "leo", "marcus", "oliver",
            "durga",
        }
        actual_ids = set(AvocetVoiceService.VOICE_PROFILES.keys())
        assert expected_ids.issubset(actual_ids)
        assert len(actual_ids) >= 9

    # 2. Female voice profiles
    def test_02_female_voice_profiles(self):
        females = ["serena", "nala", "elena", "maya", "durga"]
        for fid in females:
            p = AvocetVoiceService.VOICE_PROFILES[fid]
            assert p["gender"] == "female"
            assert "name" in p and p["name"]
            assert "display_name" in p
            assert "preview_text" in p
            assert 0.8 <= p["length_scale"] <= 1.3
            assert 0.3 <= p["noise_scale"] <= 0.9

    # 3. Male voice profiles with DSP filters
    def test_03_male_voice_profiles_with_dsp(self):
        males = ["julian", "leo", "marcus", "oliver"]
        for mid in males:
            p = AvocetVoiceService.VOICE_PROFILES[mid]
            assert p["gender"] == "male"
            assert p["audio_filter"] is not None
            assert "asetrate" in p["audio_filter"]
            assert "preview_text" in p

    # 4. Tone styles library completeness
    def test_04_tone_styles_library_completeness(self):
        expected_tones = ["affectionate_caring", "energetic_inspiring", "peaceful_mindful", "custom"]
        for tid in expected_tones:
            assert tid in AvocetVoiceService.TONE_STYLES
            style = AvocetVoiceService.TONE_STYLES[tid]
            assert "name" in style
            if tid != "custom":
                assert "morning" in style and len(style["morning"]) > 10
                assert "afternoon" in style and len(style["afternoon"]) > 10
                assert "evening" in style and len(style["evening"]) > 10

    # 5. Tone style greeting text resolution
    def test_05_tone_style_greeting_text_resolution(self, temp_settings):
        temp_settings.set("active_tone_style", "affectionate_caring")
        text = AvocetVoiceService.build_greeting_text("morning", temp_settings, include_devotional=False)
        assert "deeply appreciated today" in text
        assert "breathe easy" in text

        temp_settings.set("active_tone_style", "energetic_inspiring")
        text2 = AvocetVoiceService.build_greeting_text("morning", temp_settings, include_devotional=False)
        assert "Rise and shine" in text2

        temp_settings.set("active_tone_style", "peaceful_mindful")
        text3 = AvocetVoiceService.build_greeting_text("morning", temp_settings, include_devotional=False)
        assert "Hi Sudharshan garu, I am Durga" in text3
        assert "soft, peaceful morning" in text3

    # 6. Custom greeting text override preservation
    def test_06_custom_greeting_text_override_preservation(self, temp_settings):
        temp_settings.set("active_tone_style", "custom")
        temp_settings.set("custom_greeting_morning", "Custom crafted morning greeting for {salutation}.")
        text = AvocetVoiceService.build_greeting_text("morning", temp_settings, include_devotional=False)
        assert text == "Custom crafted morning greeting for Sudharshan garu."

    # 7. Preview voice profile execution non-blocking
    def test_07_preview_voice_profile_non_blocking(self, temp_settings):
        with patch.object(AvocetVoiceService, "synthesize_and_play", return_value=True):
            t0 = time.perf_counter()
            th = AvocetVoiceService.preview_voice_profile("serena", temp_settings)
            t_elapsed = time.perf_counter() - t0

            assert t_elapsed < 0.05
            assert isinstance(th, threading.Thread)
            th.join(timeout=1.0)

    # 8. Synthesis pipeline with acoustic parameter application
    def test_08_synthesis_acoustic_parameter_application(self):
        piper_called_args = []

        def _mock_popen(cmd, *args, **kwargs):
            piper_called_args.extend(cmd)
            proc = MagicMock()
            proc.communicate.return_value = ("", "")
            proc.returncode = 0
            return proc

        with patch("subprocess.Popen", side_effect=_mock_popen), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=1024), \
             patch.object(
                 AvocetVoiceService,
                 "resolve_audio_output",
                 return_value={
                     "player": "/usr/bin/paplay",
                     "device": "default",
                     "mode": "auto",
                     "system_default_sink": "default",
                     "sinks": [],
                     "selection_reason": "test default",
                 },
             ):

            # Test Serena's custom length_scale (1.12)
            AvocetVoiceService.synthesize_and_play(
                text="Test morning greeting",
                voice_profile="serena",
            )
            assert "--length_scale" in piper_called_args
            idx = piper_called_args.index("--length_scale")
            assert piper_called_args[idx + 1] == "1.12"

    # 9. Male timbre DSP filter execution
    def test_09_male_timbre_dsp_filter_execution(self):
        ffmpeg_called = []

        def _mock_run(cmd, *args, **kwargs):
            ffmpeg_called.extend(cmd)
            res = MagicMock()
            res.returncode = 0
            return res

        def _mock_popen(cmd, *args, **kwargs):
            proc = MagicMock()
            proc.communicate.return_value = ("", "")
            proc.returncode = 0
            return proc

        with patch("subprocess.run", side_effect=_mock_run), \
             patch("subprocess.Popen", side_effect=_mock_popen), \
             patch("os.path.exists", return_value=True), \
             patch("os.path.getsize", return_value=1024), \
             patch.object(
                 AvocetVoiceService,
                 "resolve_audio_output",
                 return_value={
                     "player": "/usr/bin/paplay",
                     "device": "default",
                     "mode": "auto",
                     "system_default_sink": "default",
                     "sinks": [],
                     "selection_reason": "test default",
                 },
             ):

            AvocetVoiceService.synthesize_and_play(
                text="Good morning, Julian here.",
                voice_profile="julian",
            )
            # Verify ffmpeg was invoked with Julian's audio filter
            assert any("ffmpeg" in str(c) for c in ffmpeg_called)
            assert any("asetrate" in str(c) for c in ffmpeg_called)

    # 10. SettingsView Voice Profile dropdown options and selection
    def test_10_settings_view_voice_profile_dropdown(self, qapp, temp_settings):
        view = SettingsView(
            db_manager=temp_settings.db_manager,
            settings_manager=temp_settings,
        )
        assert hasattr(view, "combo_voice_profile")
        assert view.combo_voice_profile.count() >= 9

        # Verify we can select Leo
        idx = view.combo_voice_profile.findData("leo")
        assert idx != -1
        view.combo_voice_profile.setCurrentIndex(idx)
        assert temp_settings.get("active_voice_profile") == "leo"
        view.close()

    # 11. SettingsView Preview Voice button trigger
    def test_11_settings_view_preview_voice_button(self, qapp, temp_settings):
        view = SettingsView(
            db_manager=temp_settings.db_manager,
            settings_manager=temp_settings,
        )
        with patch.object(AvocetVoiceService, "preview_voice_profile") as mock_preview:
            view.btn_preview_voice.click()
            assert mock_preview.called
        view.close()

    # 12. SettingsView Tone Style dropdown selection and message prefill
    def test_12_settings_view_tone_style_dropdown_prefill(self, qapp, temp_settings):
        view = SettingsView(
            db_manager=temp_settings.db_manager,
            settings_manager=temp_settings,
        )
        idx = view.combo_tone_style.findData("energetic_inspiring")
        assert idx != -1
        view.combo_tone_style.setCurrentIndex(idx)

        assert "Rise and shine" in view.morning_message_edit.toPlainText()
        assert temp_settings.get("active_tone_style") == "energetic_inspiring"
        view.close()

    # 13. Settings persistence for active_voice_profile and active_tone_style
    def test_13_settings_persistence(self, qapp, temp_settings):
        view = SettingsView(
            db_manager=temp_settings.db_manager,
            settings_manager=temp_settings,
        )
        idx_vp = view.combo_voice_profile.findData("elena")
        view.combo_voice_profile.setCurrentIndex(idx_vp)

        idx_ts = view.combo_tone_style.findData("peaceful_mindful")
        view.combo_tone_style.setCurrentIndex(idx_ts)

        view.save_companion_settings()

        assert temp_settings.get("active_voice_profile") == "elena"
        assert temp_settings.get("active_tone_style") == "peaceful_mindful"
        view.close()

    # 14. DesktopCompanion voice_profile propagation
    def test_14_desktop_companion_voice_profile_propagation(self, qapp):
        companion = DesktopCompanion(
            greeting_text="Hello friend",
            voice_profile="marcus",
        )
        assert companion.voice_profile == "marcus"

        with patch("todo_bird_app.widgets.desktop_companion.speak_lovely_async") as mock_speak:
            with patch.object(QTimer, "singleShot", side_effect=lambda ms, cb: cb()):
                companion.start_sequence()
                assert mock_speak.called
                assert mock_speak.call_args[1]["voice_profile"] == "marcus"
        companion.close()

    # 15. Production DB untouched
    def test_15_production_db_untouched(self):
        if PROD_DB_PATH.exists() and INITIAL_PROD_DB_HASH:
            current_hash = hashlib.sha256(PROD_DB_PATH.read_bytes()).hexdigest()
            assert current_hash == INITIAL_PROD_DB_HASH, (
                f"Production DB modified! Baseline: {INITIAL_PROD_DB_HASH}, current: {current_hash}"
            )
