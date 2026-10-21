"""
TODO BIRD — Avocet / Durga Startup Welcome Voice & TTS Authority Test Suite
Mandatory 30 focused tests verifying:
1  voice enabled
2  voice disabled
3  companion enabled
4  morning enabled
5  morning disabled
6  afternoon enabled
7  evening enabled
8  already spoken today suppresses normal startup
9  test voice bypasses spoken-today
10 failed TTS does not mark spoken
11 successful playback marks spoken
12 devotional prefix enabled
13 devotional prefix disabled
14 no duplicate devotional prefix
15 morning greeting text
16 afternoon greeting text
17 evening greeting text
18 no startup "Good Night"
19 user salutation
20 assistant name Durga
21 Piper available
22 Piper unavailable handled
23 invalid voice model handled
24 audio backend failure handled
25 startup remains non-blocking
26 700 ms startup sequence preserved
27 settings persistence
28 Test Durga Voice button
29 Test Startup Greeting button
30 production DB unchanged
"""

import hashlib
import os
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from todo_bird_app.database import DatabaseManager
from todo_bird_app.services.avocet_voice_service import AvocetVoiceService
from todo_bird_app.services.window_registry import WindowRegistry
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
    db_file = tmp_path / "voice_test.db"
    db = DatabaseManager(str(db_file))
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    settings = SettingsManager(db, config_dir=config_dir)
    settings.set("custom_greeting_morning", AvocetVoiceService.DEFAULT_GREETINGS["morning"])
    settings.set("custom_greeting_afternoon", AvocetVoiceService.DEFAULT_GREETINGS["afternoon"])
    settings.set("custom_greeting_evening", AvocetVoiceService.DEFAULT_GREETINGS["evening"])
    settings.set("custom_greeting_night", AvocetVoiceService.DEFAULT_GREETINGS["night"])
    settings.set("user_salutation", AvocetVoiceService.DEFAULT_USER_SALUTATION)
    settings.set("assistant_name", AvocetVoiceService.DEFAULT_ASSISTANT_NAME)
    yield settings


class TestAvocetDurgaVoiceAuthority:
    """30-test authority suite for Avocet / Durga Voice and Startup Flow."""

    # -------------------------------------------------------------------------
    # 1. Voice Enabled
    # -------------------------------------------------------------------------
    def test_01_voice_enabled(self, temp_settings):
        temp_settings.set("voice_enabled", True)
        temp_settings.set("companion_enabled", True)
        temp_settings.set("greeting_morning_enabled", True)
        temp_settings.set("last_greeting_morning_date", "")

        gates = AvocetVoiceService.evaluate_startup_gates(
            temp_settings, dt=datetime(2026, 9, 4, 9, 0)
        )
        assert gates["voice_enabled"] is True
        assert gates["should_speak"] is True

    # -------------------------------------------------------------------------
    # 2. Voice Disabled
    # -------------------------------------------------------------------------
    def test_02_voice_disabled(self, temp_settings):
        temp_settings.set("voice_enabled", False)
        temp_settings.set("companion_enabled", True)
        temp_settings.set("greeting_morning_enabled", True)
        temp_settings.set("last_greeting_morning_date", "")

        gates = AvocetVoiceService.evaluate_startup_gates(
            temp_settings, dt=datetime(2026, 9, 4, 9, 0)
        )
        assert gates["voice_enabled"] is False
        assert gates["should_speak"] is False

    # -------------------------------------------------------------------------
    # 3. Companion Enabled vs Disabled
    # -------------------------------------------------------------------------
    def test_03_companion_enabled(self, temp_settings):
        temp_settings.set("voice_enabled", True)
        temp_settings.set("companion_enabled", False)
        gates_disabled = AvocetVoiceService.evaluate_startup_gates(
            temp_settings, dt=datetime(2026, 9, 4, 9, 0)
        )
        assert gates_disabled["companion_enabled"] is False
        assert gates_disabled["should_speak"] is False

        temp_settings.set("companion_enabled", True)
        gates_enabled = AvocetVoiceService.evaluate_startup_gates(
            temp_settings, dt=datetime(2026, 9, 4, 9, 0)
        )
        assert gates_enabled["companion_enabled"] is True
        assert gates_enabled["should_speak"] is True

    # -------------------------------------------------------------------------
    # 4. Morning Enabled
    # -------------------------------------------------------------------------
    def test_04_morning_enabled(self, temp_settings):
        temp_settings.set("voice_enabled", True)
        temp_settings.set("greeting_morning_enabled", True)
        gates = AvocetVoiceService.evaluate_startup_gates(
            temp_settings, dt=datetime(2026, 9, 4, 8, 30)
        )
        assert gates["period"] == "morning"
        assert gates["period_enabled"] is True
        assert gates["should_speak"] is True

    # -------------------------------------------------------------------------
    # 5. Morning Disabled
    # -------------------------------------------------------------------------
    def test_05_morning_disabled(self, temp_settings):
        temp_settings.set("voice_enabled", True)
        temp_settings.set("greeting_morning_enabled", False)
        gates = AvocetVoiceService.evaluate_startup_gates(
            temp_settings, dt=datetime(2026, 9, 4, 8, 30)
        )
        assert gates["period"] == "morning"
        assert gates["period_enabled"] is False
        assert gates["should_speak"] is False

    # -------------------------------------------------------------------------
    # 6. Afternoon Enabled
    # -------------------------------------------------------------------------
    def test_06_afternoon_enabled(self, temp_settings):
        temp_settings.set("voice_enabled", True)
        temp_settings.set("greeting_afternoon_enabled", True)
        gates = AvocetVoiceService.evaluate_startup_gates(
            temp_settings, dt=datetime(2026, 9, 4, 14, 15)
        )
        assert gates["period"] == "afternoon"
        assert gates["period_enabled"] is True
        assert gates["should_speak"] is True

        temp_settings.set("greeting_afternoon_enabled", False)
        gates2 = AvocetVoiceService.evaluate_startup_gates(
            temp_settings, dt=datetime(2026, 9, 4, 14, 15)
        )
        assert gates2["period_enabled"] is False
        assert gates2["should_speak"] is False

    # -------------------------------------------------------------------------
    # 7. Evening Enabled
    # -------------------------------------------------------------------------
    def test_07_evening_enabled(self, temp_settings):
        temp_settings.set("voice_enabled", True)
        temp_settings.set("greeting_evening_enabled", True)
        gates = AvocetVoiceService.evaluate_startup_gates(
            temp_settings, dt=datetime(2026, 9, 4, 18, 45)
        )
        assert gates["period"] == "evening"
        assert gates["period_enabled"] is True
        assert gates["should_speak"] is True

        temp_settings.set("greeting_evening_enabled", False)
        gates2 = AvocetVoiceService.evaluate_startup_gates(
            temp_settings, dt=datetime(2026, 9, 4, 18, 45)
        )
        assert gates2["period_enabled"] is False
        assert gates2["should_speak"] is False

    # -------------------------------------------------------------------------
    # 8. Already Spoken Today Suppresses Normal Startup
    # -------------------------------------------------------------------------
    def test_08_already_spoken_today_suppresses_normal_startup(self, temp_settings):
        temp_settings.set("voice_enabled", True)
        temp_settings.set("greeting_morning_enabled", True)
        temp_settings.set("last_greeting_morning_date", "2026-09-04")

        gates = AvocetVoiceService.evaluate_startup_gates(
            temp_settings, dt=datetime(2026, 9, 4, 9, 30)
        )
        assert gates["already_spoken_today"] is True
        assert gates["should_speak"] is False

    # -------------------------------------------------------------------------
    # 9. Test Voice Bypasses Spoken Today
    # -------------------------------------------------------------------------
    def test_09_test_voice_bypasses_spoken_today(self, temp_settings):
        # Spoken today is True and all periods disabled
        temp_settings.set("last_greeting_morning_date", "2026-09-04")
        temp_settings.set("greeting_morning_enabled", False)
        temp_settings.set("voice_enabled", False)

        with patch.object(AvocetVoiceService, "speak_async") as mock_speak:
            AvocetVoiceService.test_durga_voice(temp_settings)
            assert mock_speak.called
            called_text = mock_speak.call_args[1]["text"]
            assert "Your Todo Bird voice is working" in called_text
            assert "Durga" in called_text

    # -------------------------------------------------------------------------
    # 10. Failed TTS Does Not Mark Spoken
    # -------------------------------------------------------------------------
    def test_10_failed_tts_does_not_mark_spoken(self, temp_settings):
        temp_settings.set("last_greeting_morning_date", "")

        on_started_mock = MagicMock()

        # Simulate synthesis failure
        with patch.object(AvocetVoiceService, "get_piper_binary", return_value=None):
            success = AvocetVoiceService.synthesize_and_play(
                text="Test greeting",
                on_started=on_started_mock,
            )
            assert success is False
            assert not on_started_mock.called
            assert temp_settings.get("last_greeting_morning_date", "") == ""

    # -------------------------------------------------------------------------
    # 11. Successful Playback Marks Spoken
    # -------------------------------------------------------------------------
    def test_11_successful_playback_marks_spoken(self, temp_settings):
        today_key = "2026-09-04"
        last_spoken_key = "last_greeting_morning_date"

        def _on_speech_completed():
            temp_settings.set(last_spoken_key, today_key)

        synth_proc = MagicMock()
        synth_proc.communicate.return_value = ("", "")
        synth_proc.returncode = 0

        play_proc = MagicMock()
        play_proc.communicate.return_value = (b"", b"")
        play_proc.returncode = 0

        def _fake_popen(cmd, *args, **kwargs):
            if any("piper" in str(c) for c in cmd):
                return synth_proc
            return play_proc

        with patch("subprocess.Popen", side_effect=_fake_popen), \
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

            success = AvocetVoiceService.synthesize_and_play(
                text="Test greeting",
                on_completed=_on_speech_completed,
            )
            assert success is True
            assert temp_settings.get(last_spoken_key, "") == today_key

    def test_11b_playback_failure_does_not_mark_spoken(self, temp_settings):
        last_spoken_key = "last_greeting_morning_date"
        completed_cb = MagicMock(
            side_effect=lambda: temp_settings.set(last_spoken_key, "2026-09-04")
        )
        failed_cb = MagicMock()

        synth_proc = MagicMock()
        synth_proc.communicate.return_value = ("", "")
        synth_proc.returncode = 0

        play_proc = MagicMock()
        play_proc.communicate.return_value = (b"", b"mock playback failure")
        play_proc.returncode = 1

        def _fake_popen(cmd, *args, **kwargs):
            if any("piper" in str(c) for c in cmd):
                return synth_proc
            return play_proc

        with patch("subprocess.Popen", side_effect=_fake_popen), \
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

            success = AvocetVoiceService.synthesize_and_play(
                text="Test greeting",
                on_completed=completed_cb,
                on_failed=failed_cb,
            )

        assert success is False
        assert not completed_cb.called
        assert failed_cb.called
        assert temp_settings.get(last_spoken_key, "") == ""

    # -------------------------------------------------------------------------
    # 12. Devotional Prefix Enabled
    # -------------------------------------------------------------------------
    def test_12_devotional_prefix_enabled(self, temp_settings):
        temp_settings.set("devotional_intro", True)
        text = AvocetVoiceService.build_greeting_text("morning", temp_settings)
        assert text.startswith("Om Gam Ganapataye Namaha.")

    # -------------------------------------------------------------------------
    # 13. Devotional Prefix Disabled
    # -------------------------------------------------------------------------
    def test_13_devotional_prefix_disabled(self, temp_settings):
        temp_settings.set("devotional_intro", False)
        text = AvocetVoiceService.build_greeting_text("morning", temp_settings)
        assert not text.startswith("Om Gam Ganapataye Namaha.")
        assert text.startswith("Hi friend, I am Durga.")

    # -------------------------------------------------------------------------
    # 14. No Duplicate Devotional Prefix
    # -------------------------------------------------------------------------
    def test_14_no_duplicate_devotional_prefix(self, temp_settings):
        temp_settings.set("devotional_intro", True)
        temp_settings.set(
            "custom_greeting_morning",
            "Om Gam Ganapataye Namaha. Good morning everyone."
        )
        text = AvocetVoiceService.build_greeting_text("morning", temp_settings)
        assert text.count("Om Gam Ganapataye Namaha") == 1

    # -------------------------------------------------------------------------
    # 15. Morning Greeting Text
    # -------------------------------------------------------------------------
    def test_15_morning_greeting_text(self, temp_settings):
        temp_settings.set("devotional_intro", False)
        text = AvocetVoiceService.build_greeting_text("morning", temp_settings)
        assert "Good morning" in text
        assert "Wishing you a peaceful, confident and successful day" in text
        assert "Let us begin with clarity, positivity and focus" in text

    # -------------------------------------------------------------------------
    # 16. Afternoon Greeting Text
    # -------------------------------------------------------------------------
    def test_16_afternoon_greeting_text(self, temp_settings):
        text = AvocetVoiceService.build_greeting_text("afternoon", temp_settings)
        assert "Good afternoon" in text
        assert "Wishing you a focused and productive rest of the day" in text

    # -------------------------------------------------------------------------
    # 17. Evening Greeting Text
    # -------------------------------------------------------------------------
    def test_17_evening_greeting_text(self, temp_settings):
        text = AvocetVoiceService.build_greeting_text("evening", temp_settings)
        assert "Good evening" in text
        assert "Welcome back" in text
        assert "Let us close the day calmly and with clarity" in text

    # -------------------------------------------------------------------------
    # 18. No Startup "Good Night"
    # -------------------------------------------------------------------------
    def test_18_no_startup_good_night(self, temp_settings):
        # Even if customized with "Good night", night startup must never say Good night
        temp_settings.set(
            "custom_greeting_night",
            "Hi {salutation}, I am {assistant}. Good night. Rest well."
        )
        text = AvocetVoiceService.build_greeting_text("night", temp_settings)
        assert "Good night" not in text
        assert "Good Night" not in text
        assert "Good evening" in text

    # -------------------------------------------------------------------------
    # 19. User Salutation Customization
    # -------------------------------------------------------------------------
    def test_19_user_salutation(self, temp_settings):
        temp_settings.set("devotional_intro", False)
        temp_settings.set("user_salutation", "Rao garu")
        text = AvocetVoiceService.build_greeting_text("morning", temp_settings)
        assert "Hi Rao garu, I am Durga" in text

    # -------------------------------------------------------------------------
    # 20. Assistant Name Durga
    # -------------------------------------------------------------------------
    def test_20_assistant_name_durga(self, temp_settings):
        temp_settings.set("devotional_intro", False)
        temp_settings.set("assistant_name", "Durga")
        text = AvocetVoiceService.build_greeting_text("morning", temp_settings)
        assert "I am Durga" in text

    # -------------------------------------------------------------------------
    # 21. Piper Available
    # -------------------------------------------------------------------------
    def test_21_piper_available(self):
        piper_bin = AvocetVoiceService.get_piper_binary()
        assert piper_bin is not None
        assert os.path.exists(piper_bin)

    # -------------------------------------------------------------------------
    # 22. Piper Unavailable Handled
    # -------------------------------------------------------------------------
    def test_22_piper_unavailable_handled(self):
        failed_cb = MagicMock()
        with patch.object(AvocetVoiceService, "get_piper_binary", return_value=None):
            result = AvocetVoiceService.synthesize_and_play(
                text="Test text",
                on_failed=failed_cb,
            )
            assert result is False
            assert failed_cb.called
            assert "Piper binary not found" in failed_cb.call_args[0][0]

    # -------------------------------------------------------------------------
    # 23. Invalid Voice Model Handled
    # -------------------------------------------------------------------------
    def test_23_invalid_voice_model_handled(self):
        failed_cb = MagicMock()
        with patch.object(AvocetVoiceService, "get_voice_model_paths", return_value=(None, None)):
            result = AvocetVoiceService.synthesize_and_play(
                text="Test text",
                on_failed=failed_cb,
            )
            assert result is False
            assert failed_cb.called
            assert "Voice model or config missing" in failed_cb.call_args[0][0]

    # -------------------------------------------------------------------------
    # 24. Audio Backend Failure Handled
    # -------------------------------------------------------------------------
    def test_24_audio_backend_failure_handled(self):
        failed_cb = MagicMock()
        with patch.object(
            AvocetVoiceService,
            "resolve_audio_output",
            return_value={
                "player": None,
                "device": "none",
                "mode": "auto",
                "system_default_sink": None,
                "sinks": [],
                "selection_reason": "test no player",
            },
        ):
            result = AvocetVoiceService.synthesize_and_play(
                text="Test text",
                on_failed=failed_cb,
            )
            assert result is False
            assert failed_cb.called
            assert "No audio player" in failed_cb.call_args[0][0]

    # -------------------------------------------------------------------------
    # 25. Startup Remains Non-Blocking
    # -------------------------------------------------------------------------
    def test_25_startup_remains_non_blocking(self):
        def _slow_synth(*args, **kwargs):
            time.sleep(0.5)
            return True

        with patch.object(AvocetVoiceService, "synthesize_and_play", side_effect=_slow_synth):
            t0 = time.perf_counter()
            th = AvocetVoiceService.speak_async("Quick start check")
            t_elapsed = time.perf_counter() - t0

            # Must return in under 50ms without blocking main thread
            assert t_elapsed < 0.05
            assert isinstance(th, threading.Thread)
            assert th.is_alive()
            th.join(timeout=2.0)

    # -------------------------------------------------------------------------
    # 26. 700 ms Startup Sequence Preserved
    # -------------------------------------------------------------------------
    def test_26_700ms_startup_sequence_preserved(self, qapp):
        companion = DesktopCompanion("Greeting Test")
        with patch.object(QTimer, "singleShot") as mock_timer:
            companion.start_sequence()
            calls = [call for call in mock_timer.call_args_list if call[0][0] == 700]
            assert len(calls) >= 1
        companion.close()

    # -------------------------------------------------------------------------
    # 27. Settings Persistence
    # -------------------------------------------------------------------------
    def test_27_settings_persistence(self, qapp, temp_settings):
        view = SettingsView(
            db_manager=temp_settings.db_manager,
            settings_manager=temp_settings,
        )

        view.cb_companion_enabled.setChecked(True)
        view.cb_voice_enabled.setChecked(True)
        view.spin_companion_visible.setValue(30)
        view.edit_assistant_name.setText("Durga")
        view.edit_user_salutation.setText("Sudharshan garu")
        view.cb_greet_morning.setChecked(True)
        view.cb_greet_afternoon.setChecked(True)
        view.cb_greet_evening.setChecked(True)
        view.cb_greet_night.setChecked(True)
        view.cb_devotional_intro.setChecked(True)

        view.save_companion_settings()

        assert temp_settings.get("companion_enabled") is True
        assert temp_settings.get("voice_enabled") is True
        assert temp_settings.get("companion_visible_seconds") == 30
        assert temp_settings.get("assistant_name") == "Durga"
        assert temp_settings.get("user_salutation") == "Sudharshan garu"
        assert temp_settings.get("greeting_mode") == "once_daily"
        assert temp_settings.get("audio_output_device") == "auto"
        assert temp_settings.get("greeting_morning_enabled") is True
        assert temp_settings.get("greeting_afternoon_enabled") is True
        assert temp_settings.get("greeting_evening_enabled") is True
        assert temp_settings.get("greeting_night_enabled") is True
        assert temp_settings.get("devotional_intro") is True
        view.close()

    # -------------------------------------------------------------------------
    # 28. Test Durga Voice Button
    # -------------------------------------------------------------------------
    def test_28_test_durga_voice_button(self, qapp, temp_settings):
        view = SettingsView(
            db_manager=temp_settings.db_manager,
            settings_manager=temp_settings,
        )
        with patch.object(AvocetVoiceService, "test_durga_voice") as mock_test_voice:
            view.btn_test_durga_voice.click()
            assert mock_test_voice.called
            assert mock_test_voice.call_args[0][0] == temp_settings
        view.close()

    # -------------------------------------------------------------------------
    # 29. Test Startup Greeting Button
    # -------------------------------------------------------------------------
    def test_29_test_startup_greeting_button(self, qapp, temp_settings):
        view = SettingsView(
            db_manager=temp_settings.db_manager,
            settings_manager=temp_settings,
        )
        with patch.object(AvocetVoiceService, "test_startup_greeting") as mock_test_greet:
            view.btn_test_startup_greeting.click()
            assert mock_test_greet.called
            assert mock_test_greet.call_args[0][0] == temp_settings
        view.close()

    # -------------------------------------------------------------------------
    # 30. Production DB Unchanged
    # -------------------------------------------------------------------------
    def test_30_production_db_unchanged(self):
        if PROD_DB_PATH.exists() and INITIAL_PROD_DB_HASH:
            current_hash = hashlib.sha256(PROD_DB_PATH.read_bytes()).hexdigest()
            assert current_hash == INITIAL_PROD_DB_HASH, (
                f"Production database modified! Expected {INITIAL_PROD_DB_HASH}, got {current_hash}"
            )

    def test_31_auto_audio_prefers_speaker_over_hdmi_default(self, temp_settings):
        temp_settings.set("audio_output_device", "auto")
        sinks = [
            {
                "name": "alsa_output.pci-0000_65_00.1.hdmi-surround71",
                "description": "HDA NVidia Digital Surround 7.1 (HDMI)",
                "state": "SUSPENDED",
                "muted": False,
                "volume_percent": 99,
                "active_port": "hdmi-output-0",
                "active_port_description": "HDMI / DisplayPort available",
                "active_port_unavailable": False,
            },
            {
                "name": "alsa_output.pci-0000_66_00.6.analog-stereo",
                "description": "Family 17h/19h HD Audio Controller Analog Stereo",
                "state": "SUSPENDED",
                "muted": False,
                "volume_percent": 99,
                "active_port": "analog-output-speaker",
                "active_port_description": "Speakers availability unknown",
                "active_port_unavailable": False,
            },
        ]
        with patch("shutil.which", return_value="/usr/bin/paplay"), \
             patch.object(
                 AvocetVoiceService,
                 "get_default_audio_sink",
                 return_value="alsa_output.pci-0000_65_00.1.hdmi-surround71",
             ), \
             patch.object(AvocetVoiceService, "list_audio_sinks", return_value=sinks):
            resolved = AvocetVoiceService.resolve_audio_output(temp_settings)

        assert resolved["system_default_sink"] == "alsa_output.pci-0000_65_00.1.hdmi-surround71"
        assert resolved["device"] == "alsa_output.pci-0000_66_00.6.analog-stereo"
        assert "automatic audible sink selected" in resolved["selection_reason"]

    def test_32_system_default_audio_mode_respects_default_sink(self, temp_settings):
        temp_settings.set("audio_output_device", "system_default")
        with patch("shutil.which", return_value="/usr/bin/paplay"), \
             patch.object(
                 AvocetVoiceService,
                 "get_default_audio_sink",
                 return_value="alsa_output.pci-0000_65_00.1.hdmi-surround71",
             ), \
             patch.object(AvocetVoiceService, "list_audio_sinks", return_value=[]):
            resolved = AvocetVoiceService.resolve_audio_output(temp_settings)

        assert resolved["device"] == "alsa_output.pci-0000_65_00.1.hdmi-surround71"
