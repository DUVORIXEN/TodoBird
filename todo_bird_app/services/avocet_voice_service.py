"""
TODO BIRD — Avocet Companion & Durga Offline Voice Service
Authority for:
- Piper Offline TTS speech synthesis
- PipeWire / PulseAudio / ALSA audio backend routing
- Time-period aware personalized greetings (Morning, Afternoon, Evening, Night)
- Devotional intro gating ("Om Gam Ganapataye Namaha.")
- "Already Spoken Today" gate tracking with failure-safe semantics
- Non-blocking asynchronous audio delivery
- Diagnostic logging across all startup boundaries
"""

import logging
import os
import sys
import re
import shutil
import subprocess
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple, Any

logger = logging.getLogger("todo_bird.audio")


class AvocetVoiceService:
    """Offline Voice Service for Avocet / Durga startup greetings."""

    DEFAULT_ASSISTANT_NAME = "Durga"
    DEFAULT_USER_SALUTATION = "friend"
    DEVOTIONAL_PREFIX = "Om Gam Ganapataye Namaha. "
    DEFAULT_AUDIO_OUTPUT_DEVICE = "auto"
    _speech_lock = threading.Lock()

    DEFAULT_GREETINGS = {
        "morning": (
            "Hi {salutation}, I am {assistant}. Good morning. "
            "Wishing you a peaceful, confident and successful day. "
            "Let us begin with clarity, positivity and focus."
        ),
        "afternoon": (
            "Hi {salutation}, I am {assistant}. Good afternoon. "
            "Wishing you a focused and productive rest of the day."
        ),
        "evening": (
            "Hi {salutation}, I am {assistant}. Good evening. Welcome back. "
            "Let us close the day calmly and with clarity."
        ),
        "night": (
            "Hi {salutation}, I am {assistant}. Good evening. Welcome back. "
            "Let us close the day calmly and with clarity."
        ),
    }

    VOICE_PROFILES = {
        "serena": {
            "id": "serena",
            "name": "Serena",
            "display_name": "Serena (Warm & Affectionate)",
            "gender": "female",
            "tone": "Warm & Affectionate",
            "description": "Soft, smooth, deeply caring, and intimate.",
            "length_scale": 1.12,
            "noise_scale": 0.55,
            "noise_w": 0.90,
            "sentence_silence": 0.35,
            "audio_filter": "volume=1.05,equalizer=f=300:t=q:w=1:g=2",
            "preview_text": "Good morning! Just a reminder that you are deeply appreciated today. Take your time, breathe easy, and take care of yourself.",
        },
        "nala": {
            "id": "nala",
            "name": "Nala",
            "display_name": "Nala (Bright & Uplifting)",
            "gender": "female",
            "tone": "Bright & Uplifting",
            "description": "Cheerful, energetic, encouraging, and smiling tone.",
            "length_scale": 0.92,
            "noise_scale": 0.70,
            "noise_w": 0.85,
            "sentence_silence": 0.20,
            "audio_filter": "volume=1.08,equalizer=f=2500:t=q:w=1:g=2.5",
            "preview_text": "Rise and shine! Today is full of fresh possibilities, and you've got everything it takes to make the most of it.",
        },
        "elena": {
            "id": "elena",
            "name": "Elena",
            "display_name": "Elena (Calm & Grounded)",
            "gender": "female",
            "tone": "Calm & Grounded",
            "description": "Velvety, reassuring, steady, and peaceful.",
            "length_scale": 1.18,
            "noise_scale": 0.45,
            "noise_w": 0.80,
            "sentence_silence": 0.40,
            "audio_filter": "volume=1.02,equalizer=f=200:t=q:w=1:g=3",
            "preview_text": "A soft, peaceful morning to you. Start today with a calm breath, let go of yesterday, and focus on the present moment.",
        },
        "maya": {
            "id": "maya",
            "name": "Maya",
            "display_name": "Maya (Friendly & Conversational)",
            "gender": "female",
            "tone": "Friendly & Conversational",
            "description": "Natural, engaging, relatable, and breezy.",
            "length_scale": 1.00,
            "noise_scale": 0.65,
            "noise_w": 0.80,
            "sentence_silence": 0.25,
            "audio_filter": None,
            "preview_text": "Morning! I hope you had a restful night. Let's take today step-by-step and make wonderful things happen together.",
        },
        "julian": {
            "id": "julian",
            "name": "Julian",
            "display_name": "Julian (Warm & Affectionate - Male)",
            "gender": "male",
            "tone": "Warm & Affectionate",
            "description": "Deep, comforting, gentle, and emotionally resonant.",
            "length_scale": 1.10,
            "noise_scale": 0.55,
            "noise_w": 0.85,
            "sentence_silence": 0.35,
            "audio_filter": "asetrate=22050*0.80,aresample=22050,atempo=1.25,bass=g=4:f=160",
            "preview_text": "Good morning. I'm right here with you today. Remember to be gentle with yourself as you take on the day.",
        },
        "leo": {
            "id": "leo",
            "name": "Leo",
            "display_name": "Leo (Bright & Uplifting - Male)",
            "gender": "male",
            "tone": "Bright & Uplifting",
            "description": "Dynamic, encouraging, clear, and motivational.",
            "length_scale": 0.94,
            "noise_scale": 0.68,
            "noise_w": 0.82,
            "sentence_silence": 0.20,
            "audio_filter": "asetrate=22050*0.84,aresample=22050,atempo=1.19,treble=g=2:f=2800",
            "preview_text": "Rise and shine! Today is packed with fresh opportunities, and I know you're ready to do amazing things.",
        },
        "marcus": {
            "id": "marcus",
            "name": "Marcus",
            "display_name": "Marcus (Calm & Grounded - Male)",
            "gender": "male",
            "tone": "Calm & Grounded",
            "description": "Rich, steady, meditative, and protective.",
            "length_scale": 1.20,
            "noise_scale": 0.48,
            "noise_w": 0.80,
            "sentence_silence": 0.40,
            "audio_filter": "asetrate=22050*0.75,aresample=22050,atempo=1.33,bass=g=5:f=140",
            "preview_text": "A quiet and peaceful morning to you. Steady your thoughts, take a deep breath, and let clarity guide your day.",
        },
        "oliver": {
            "id": "oliver",
            "name": "Oliver",
            "display_name": "Oliver (Friendly & Conversational - Male)",
            "gender": "male",
            "tone": "Friendly & Conversational",
            "description": "Casual, lighthearted, warm, and approachable.",
            "length_scale": 1.02,
            "noise_scale": 0.65,
            "noise_w": 0.80,
            "sentence_silence": 0.25,
            "audio_filter": "asetrate=22050*0.82,aresample=22050,atempo=1.22,bass=g=2:f=200",
            "preview_text": "Good morning! Great to see you today. Let's tackle what matters most and keep things nice and smooth.",
        },
        "durga": {
            "id": "durga",
            "name": "Durga",
            "display_name": "Durga (Heritage / Companion Default)",
            "gender": "female",
            "tone": "Calm & Respectful",
            "description": "Soft South Indian English companion persona.",
            "length_scale": 1.05,
            "noise_scale": 0.60,
            "noise_w": 0.80,
            "sentence_silence": 0.30,
            "audio_filter": None,
            "preview_text": "Hi friend, I am Durga. Wishing you a peaceful, confident and successful day. Let us begin with clarity, positivity and focus.",
        },
    }

    TONE_STYLES = {
        "affectionate_caring": {
            "id": "affectionate_caring",
            "name": "Affectionate & Caring",
            "description": "Soft, smooth, deeply caring, and intimate wishes.",
            "morning": "Good morning! Just a reminder that you are deeply appreciated today. Take your time, breathe easy, and take care of yourself.",
            "afternoon": "Good afternoon! You have been doing wonderful work today. Remember to take a mindful pause and hydrate.",
            "evening": "Good evening. Welcome back. Let us close today with kindness toward yourself and prepare a peaceful evening.",
            "night": "Good evening. Welcome back. You did enough today. Let us unwind with peace and gratitude.",
        },
        "energetic_inspiring": {
            "id": "energetic_inspiring",
            "name": "Energetic & Inspiring",
            "description": "Upbeat, motivational, dynamic, and action-oriented.",
            "morning": "Rise and shine! Today is full of fresh possibilities, and you've got everything it takes to make the most of it.",
            "afternoon": "Keep that great momentum going! You are making meaningful progress, and the afternoon is yours to conquer.",
            "evening": "Great effort today! Celebrate the wins you achieved and let us wrap up the day with energy and pride.",
            "night": "Good evening. Welcome back. Fantastic effort today! Let us finalize what is essential and finish strong.",
        },
        "peaceful_mindful": {
            "id": "peaceful_mindful",
            "name": "Peaceful & Mindful",
            "description": "Serene, meditative, grounded, and calming.",
            "morning": "A soft, peaceful morning to you. Start today with a calm breath, let go of yesterday, and focus on the present moment.",
            "afternoon": "Slow down for just a moment. Take a gentle breath in, let your shoulders drop, and continue with calm focus.",
            "evening": "Evening has arrived. Release the busyness of the day and allow your mind to settle into quiet serenity.",
            "night": "Good evening. Welcome back. Settle into quiet serenity, letting go of all rush and tension.",
        },
        "custom": {
            "id": "custom",
            "name": "Custom Messages",
            "description": "Personalized messages configured per time period.",
        },
    }

    @classmethod
    def get_base_dir(cls) -> Path:
        """Returns the project base directory containing voice/ and assets/."""
        # Check standard repo locations
        here = Path(__file__).resolve().parent
        for candidate in [
            here.parent,          # todo_bird_app
            here.parent.parent,   # todo_bird
        ]:
            if (candidate / "voice" / "female_indian.onnx").exists():
                return candidate
        return here.parent.parent

    @classmethod
    def get_piper_binary(cls) -> Optional[str]:
        """Locates the piper executable on the system."""
        import platform
        candidates = [
            shutil.which("piper"),
        ]
        
        # If running in a bundled or portable context, one might add path logic here.
        # But for system-installed piper, shutil.which is the correct portable method.
        for c in candidates:
            if c and Path(c).is_file() and os.access(c, os.X_OK):
                return c
        return None

    @classmethod
    def get_voice_model_paths(cls) -> Tuple[Optional[Path], Optional[Path]]:
        """Locates the female_indian ONNX model and config."""
        base_dir = cls.get_base_dir()
        model_path = base_dir / "voice" / "female_indian.onnx"
        config_path = base_dir / "voice" / "female_indian.onnx.json"
        if not model_path.exists() or not config_path.exists():
            # Check inside todo_bird_app
            alt_base = Path(__file__).resolve().parent.parent
            if (alt_base / "voice" / "female_indian.onnx").exists():
                model_path = alt_base / "voice" / "female_indian.onnx"
                config_path = alt_base / "voice" / "female_indian.onnx.json"

        m = model_path if model_path.exists() else None
        c = config_path if config_path.exists() else None
        return m, c

    @classmethod
    def get_default_audio_sink(cls) -> Optional[str]:
        """Returns the current PulseAudio / PipeWire default sink name, when available."""
        try:
            pactl = shutil.which("pactl")
            if pactl:
                res = subprocess.run(
                    [pactl, "get-default-sink"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip()
        except Exception as exc:
            logger.debug(f"Unable to read default audio sink: {exc}")
        return None

    @classmethod
    def list_audio_sinks(cls) -> List[Dict[str, Any]]:
        """Returns available PulseAudio / PipeWire sinks with enough metadata for routing."""
        pactl = shutil.which("pactl")
        if not pactl:
            return []

        try:
            res = subprocess.run(
                [pactl, "list", "sinks"],
                capture_output=True,
                text=True,
                timeout=3,
            )
        except Exception as exc:
            logger.debug(f"Unable to enumerate audio sinks: {exc}")
            return []

        if res.returncode != 0:
            logger.debug(f"pactl list sinks failed: {res.stderr.strip()}")
            return []

        return cls._parse_pactl_sinks(res.stdout)

    @classmethod
    def _parse_pactl_sinks(cls, output: str) -> List[Dict[str, Any]]:
        sinks: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None
        in_ports = False

        def finish_current():
            if current and current.get("name"):
                active_port = current.get("active_port", "")
                ports = current.get("ports", {})
                active_desc = ports.get(active_port, "")
                current["active_port_description"] = active_desc
                current["active_port_unavailable"] = "not available" in active_desc.lower()
                sinks.append(current)

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if line.startswith("Sink #"):
                finish_current()
                current = {
                    "id": line.replace("Sink #", "").strip(),
                    "state": "",
                    "name": "",
                    "description": "",
                    "muted": False,
                    "volume_percent": None,
                    "active_port": "",
                    "active_port_description": "",
                    "active_port_unavailable": False,
                    "ports": {},
                }
                in_ports = False
                continue

            if current is None:
                continue

            if line.startswith("State:"):
                current["state"] = line.split(":", 1)[1].strip()
                in_ports = False
            elif line.startswith("Name:"):
                current["name"] = line.split(":", 1)[1].strip()
                in_ports = False
            elif line.startswith("Description:"):
                current["description"] = line.split(":", 1)[1].strip()
                in_ports = False
            elif line.startswith("Mute:"):
                current["muted"] = line.split(":", 1)[1].strip().lower() == "yes"
                in_ports = False
            elif line.startswith("Volume:") and current.get("volume_percent") is None:
                match = re.search(r"/\s*(\d+)%", line)
                if match:
                    current["volume_percent"] = int(match.group(1))
                in_ports = False
            elif line.startswith("Ports:"):
                in_ports = True
            elif line.startswith("Active Port:"):
                current["active_port"] = line.split(":", 1)[1].strip()
                in_ports = False
            elif line.startswith("Formats:"):
                in_ports = False
            elif in_ports and ":" in line:
                port, desc = line.split(":", 1)
                current["ports"][port.strip()] = desc.strip()

        finish_current()
        return sinks

    @classmethod
    def _sink_score(cls, sink: Dict[str, Any], system_default_sink: Optional[str]) -> int:
        text = " ".join(
            str(sink.get(key, ""))
            for key in (
                "name",
                "description",
                "active_port",
                "active_port_description",
            )
        ).lower()
        score = 0
        if sink.get("name") == system_default_sink:
            score += 10
        state = str(sink.get("state", "")).lower()
        if state == "running":
            score += 35
        elif state == "suspended":
            # PipeWire keeps idle but valid speakers suspended; do not penalize them.
            score += 15
        if sink.get("muted"):
            score -= 150
        volume = sink.get("volume_percent")
        if volume == 0:
            score -= 120
        elif isinstance(volume, int) and volume > 0:
            score += min(volume, 100) // 10
        if sink.get("active_port_unavailable"):
            score -= 150

        if "speaker" in text:
            score += 80
        if "headphone" in text:
            score += 45
        if "analog" in text or "realtek" in text or "alc" in text:
            score += 55
        if "hdmi" in text or "displayport" in text or "nvidia" in text:
            score -= 65
        if "pro-output" in text or "digital surround" in text:
            score -= 35
        return score

    @classmethod
    def choose_audible_sink(
        cls,
        sinks: List[Dict[str, Any]],
        system_default_sink: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Chooses the most likely audible sink without hardcoding a machine-specific name."""
        if not sinks:
            return None
        return max(
            sinks,
            key=lambda sink: cls._sink_score(sink, system_default_sink),
        )

    @classmethod
    def resolve_audio_output(cls, settings_manager: Any = None) -> Dict[str, Any]:
        """
        Resolves playback command and sink.

        audio_output_device settings:
        - auto: choose the most likely audible local sink, preferring speakers/headphones
        - system_default: use the current PulseAudio / PipeWire default sink
        - any concrete sink name: use that operator-selected sink if still present
        """
        candidates = []
        if sys.platform == "darwin":
            candidates.extend(["afplay"])
        elif sys.platform == "win32":
            candidates.extend(["powershell.exe", "powershell"])
        candidates.extend(["paplay", "pw-play", "aplay"])

        for cmd in candidates:
            bin_path = shutil.which(cmd)
            if bin_path:
                audio_player = bin_path
                break

        system_default_sink = cls.get_default_audio_sink()
        sinks = cls.list_audio_sinks()
        configured = cls.DEFAULT_AUDIO_OUTPUT_DEVICE
        if settings_manager is not None:
            configured = str(
                settings_manager.get(
                    "audio_output_device",
                    cls.DEFAULT_AUDIO_OUTPUT_DEVICE,
                )
                or cls.DEFAULT_AUDIO_OUTPUT_DEVICE
            )

        selected_sink = system_default_sink or "default"
        selection_reason = "system default sink"

        if configured == "system_default":
            selected_sink = system_default_sink or "default"
            selection_reason = "operator selected system default sink"
        elif configured and configured not in ("auto", "system_default"):
            names = {sink.get("name") for sink in sinks}
            if not sinks or configured in names:
                selected_sink = configured
                selection_reason = "operator selected explicit sink"
            else:
                audible = cls.choose_audible_sink(sinks, system_default_sink)
                selected_sink = (
                    audible.get("name")
                    if audible
                    else system_default_sink or "default"
                )
                selection_reason = (
                    f"configured sink '{configured}' unavailable; using automatic audible sink"
                )
        else:
            audible = cls.choose_audible_sink(sinks, system_default_sink)
            selected_sink = (
                audible.get("name")
                if audible
                else system_default_sink or "default"
            )
            if audible and audible.get("name") != system_default_sink:
                selection_reason = (
                    "automatic audible sink selected instead of system default"
                )
            elif audible:
                selection_reason = "automatic audible sink matches system default"
            else:
                selection_reason = "audio sink list unavailable; using system default"

        return {
            "player": audio_player,
            "device": selected_sink,
            "mode": configured,
            "system_default_sink": system_default_sink,
            "sinks": sinks,
            "selection_reason": selection_reason,
        }

    @classmethod
    def get_audio_player_and_device(
        cls,
        settings_manager: Any = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Compatibility wrapper returning only playback utility and selected sink."""
        resolved = cls.resolve_audio_output(settings_manager)
        return resolved.get("player"), resolved.get("device")

    @classmethod
    def determine_period(cls, dt: Optional[datetime] = None) -> str:
        """Determines time period from hour: morning, afternoon, evening, night."""
        now = dt or datetime.now()
        hour = now.hour
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 20:
            return "evening"
        else:
            return "night"

    @classmethod
    def build_greeting_text(
        cls,
        period: str,
        settings_manager: Any,
        include_devotional: Optional[bool] = None,
    ) -> str:
        """Constructs personalized greeting text for the specified period."""
        salutation = settings_manager.get("user_salutation", cls.DEFAULT_USER_SALUTATION)
        assistant = settings_manager.get("assistant_name", cls.DEFAULT_ASSISTANT_NAME)

        tone_style = settings_manager.get("active_tone_style", "custom")
        message_key = f"custom_greeting_{period}"

        # If user selected a curated tone style preset, use the preset's message
        uses_curated_tone = tone_style in cls.TONE_STYLES and tone_style != "custom"
        if tone_style in cls.TONE_STYLES and tone_style != "custom":
            template = cls.TONE_STYLES[tone_style].get(period, "")
        else:
            template = settings_manager.get(message_key, cls.DEFAULT_GREETINGS.get(period, ""))

        if not template:
            template = cls.DEFAULT_GREETINGS.get(period, "")

        try:
            greeting = template.format(salutation=salutation, assistant=assistant)
        except (KeyError, IndexError):
            greeting = template

        if uses_curated_tone:
            opener = f"Hi {salutation}, I am {assistant}. "
            lowered = greeting.lower().strip()
            if "i am " not in lowered and not lowered.startswith("hi "):
                greeting = opener + greeting

        # STRICT: At night startup, never say "Good Night"
        if period == "night":
            greeting = greeting.replace("Good night", "Good evening").replace("Good Night", "Good evening")

        # Devotional intro logic (Morning only)
        if period == "morning":
            dev_enabled = (
                include_devotional
                if include_devotional is not None
                else settings_manager.get("devotional_intro", True)
            )
            if dev_enabled:
                # Customizable intro text (Settings → Companion); falls back
                # to the canonical mantra when blank.
                custom_prefix = str(
                    settings_manager.get("devotional_intro_text", "")
                    or ""
                ).strip()
                prefix = custom_prefix or cls.DEVOTIONAL_PREFIX.strip()
                # Duplicate guard generalized to the prefix's opening words,
                # so a custom mantra also can't stack on itself.
                head = " ".join(prefix.lower().split()[:2])
                clean_lower = greeting.lower().strip()
                if not clean_lower.startswith(head):
                    terminator = "" if prefix.endswith((".", "!", "?")) else "."
                    greeting = f"{prefix}{terminator} {greeting}"

        return " ".join(greeting.split())

    @classmethod
    def evaluate_startup_gates(
        cls,
        settings_manager: Any,
        dt: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Evaluates all startup gates and logs each boundary thoroughly.
        Returns a dictionary with complete gate evaluation details.
        """
        now = dt or datetime.now()
        period = cls.determine_period(now)
        today_key = now.strftime("%Y-%m-%d")

        voice_enabled = bool(settings_manager.get("voice_enabled", True))
        companion_enabled = bool(settings_manager.get("companion_enabled", True))
        greeting_mode = str(settings_manager.get("greeting_mode", "once_daily"))

        enabled_key = f"greeting_{period}_enabled"
        period_enabled = bool(settings_manager.get(enabled_key, True))

        last_spoken_key = f"last_greeting_{period}_date"
        last_spoken_val = settings_manager.get(last_spoken_key, "")
        already_spoken_today = (last_spoken_val == today_key)

        devotional_enabled = bool(settings_manager.get("devotional_intro", True))

        selected_greeting = cls.build_greeting_text(period, settings_manager)

        piper_bin = cls.get_piper_binary()
        model_path, config_path = cls.get_voice_model_paths()
        tts_available = bool(piper_bin and model_path and config_path)

        audio_output = cls.resolve_audio_output(settings_manager)
        audio_player = audio_output.get("player")
        audio_device = audio_output.get("device")
        audio_available = bool(audio_player)

        active_voice_profile = settings_manager.get("active_voice_profile", "durga")
        active_tone_style = settings_manager.get("active_tone_style", "custom")

        greeting_mode_suppresses = greeting_mode == "never"
        spoken_today_suppresses = (
            greeting_mode in ("once_daily", "once_per_day")
            and already_spoken_today
        )

        should_speak = (
            voice_enabled
            and companion_enabled
            and period_enabled
            and not greeting_mode_suppresses
            and not spoken_today_suppresses
            and tts_available
            and audio_available
        )

        logger.info(
            f"[Startup Voice Forensics] Gate Audit:\n"
            f"  • companion_enabled: {companion_enabled}\n"
            f"  • voice_enabled: {voice_enabled}\n"
            f"  • greeting_mode: {greeting_mode}\n"
            f"  • current_period: {period} (at {now.strftime('%H:%M:%S')})\n"
            f"  • period_greeting_enabled ({enabled_key}): {period_enabled}\n"
            f"  • devotional_intro: {devotional_enabled}\n"
            f"  • already_spoken_today: {already_spoken_today} (last: '{last_spoken_val}', today: '{today_key}')\n"
            f"  • spoken_today_suppresses: {spoken_today_suppresses}\n"
            f"  • should_speak: {should_speak}\n"
            f"  • selected_greeting: \"{selected_greeting}\"\n"
            f"  • TTS engine (piper): {piper_bin} (available={tts_available})\n"
            f"  • selected_voice_model: {model_path}\n"
            f"  • audio_player: {audio_player}\n"
            f"  • audio_device: {audio_device}\n"
            f"  • audio_output_mode: {audio_output.get('mode')}\n"
            f"  • system_default_sink: {audio_output.get('system_default_sink')}\n"
            f"  • audio_selection_reason: {audio_output.get('selection_reason')}"
        )

        return {
            "period": period,
            "today_key": today_key,
            "voice_enabled": voice_enabled,
            "companion_enabled": companion_enabled,
            "greeting_mode": greeting_mode,
            "period_enabled": period_enabled,
            "devotional_enabled": devotional_enabled,
            "already_spoken_today": already_spoken_today,
            "spoken_today_suppresses": spoken_today_suppresses,
            "last_spoken_key": last_spoken_key,
            "selected_greeting": selected_greeting,
            "active_voice_profile": active_voice_profile,
            "active_tone_style": active_tone_style,
            "piper_bin": piper_bin,
            "model_path": model_path,
            "config_path": config_path,
            "audio_player": audio_player,
            "audio_device": audio_device,
            "audio_available": audio_available,
            "audio_output_mode": audio_output.get("mode"),
            "system_default_sink": audio_output.get("system_default_sink"),
            "audio_selection_reason": audio_output.get("selection_reason"),
            "should_speak": should_speak,
        }

    @classmethod
    def synthesize_and_play(
        cls,
        text: str,
        voice_profile: Optional[str] = None,
        settings_manager: Any = None,
        on_started: Optional[Callable[[], None]] = None,
        on_completed: Optional[Callable[[], None]] = None,
        on_failed: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        Synthesizes speech using Piper Offline TTS and plays via default audio sink.
        Applies profile-specific acoustic parameters and optional DSP timbre filter.
        Executes synchronously (intended to be called inside background worker thread).
        """
        clean_text = " ".join(str(text).split())
        if not clean_text:
            msg = "Empty speech text provided."
            logger.warning(f"Avocet voice unavailable: {msg}")
            if on_failed:
                on_failed(msg)
            return False

        profile_key = voice_profile or "durga"
        profile = cls.VOICE_PROFILES.get(profile_key, cls.VOICE_PROFILES.get("durga", {}))
        length_scale = profile.get("length_scale", 1.05)
        noise_scale = profile.get("noise_scale", 0.60)
        noise_w = profile.get("noise_w", 0.80)
        sentence_silence = profile.get("sentence_silence", 0.30)
        audio_filter = profile.get("audio_filter")

        piper_bin = cls.get_piper_binary()
        model_path, config_path = cls.get_voice_model_paths()

        if not piper_bin:
            msg = "Piper binary not found on system."
            logger.error(f"Avocet voice unavailable: {msg}")
            if on_failed:
                on_failed(msg)
            return False

        if not model_path or not config_path:
            msg = f"Voice model or config missing (model={model_path}, config={config_path})."
            logger.error(f"Avocet voice unavailable: {msg}")
            if on_failed:
                on_failed(msg)
            return False

        audio_output = cls.resolve_audio_output(settings_manager)
        audio_player = audio_output.get("player")
        audio_device = audio_output.get("device")
        if not audio_player:
            msg = "No audio player (paplay, pw-play, aplay, afplay, powershell) found on system."
            logger.error(f"Avocet voice unavailable: {msg}")
            if on_failed:
                on_failed(msg)
            return False

        wav_handle = tempfile.NamedTemporaryFile(
            prefix=f"todo_bird_voice_{os.getpid()}_",
            suffix=".wav",
            delete=False,
        )
        wav_path = wav_handle.name
        wav_handle.close()
        temp_paths = [wav_path]

        logger.info(f"Speech request submitted ({profile_key}): \"{clean_text}\" -> {wav_path}")
        logger.info(
            "Audio output resolved: "
            f"mode={audio_output.get('mode')}, "
            f"system_default={audio_output.get('system_default_sink')}, "
            f"selected={audio_device}, "
            f"reason={audio_output.get('selection_reason')}"
        )

        # Step 1: Synthesis with Piper
        try:
            proc = subprocess.Popen(
                [
                    piper_bin,
                    "-m", str(model_path),
                    "-c", str(config_path),
                    "-f", wav_path,
                    "--sentence_silence", str(sentence_silence),
                    "--length_scale", str(length_scale),
                    "--noise_scale", str(noise_scale),
                    "--noise_w", str(noise_w),
                    "--quiet",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                stdout, stderr = proc.communicate(clean_text, timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                _, stderr = proc.communicate()
                msg = "Piper synthesis timed out after 30 seconds."
                logger.error(f"Avocet voice unavailable: {msg}")
                if on_failed:
                    on_failed(msg)
                cls._cleanup_temp_audio_files(temp_paths)
                return False
            if proc.returncode != 0:
                msg = f"Piper synthesis failed with code {proc.returncode}: {stderr.strip()}"
                logger.error(f"Avocet voice unavailable: {msg}")
                if on_failed:
                    on_failed(msg)
                cls._cleanup_temp_audio_files(temp_paths)
                return False
        except Exception as e:
            msg = f"Piper synthesis exception: {e}"
            logger.error(f"Avocet voice unavailable: {msg}", exc_info=True)
            if on_failed:
                on_failed(msg)
            cls._cleanup_temp_audio_files(temp_paths)
            return False

        if not os.path.exists(wav_path) or os.path.getsize(wav_path) == 0:
            msg = "Synthesized WAV file is empty or missing."
            logger.error(f"Avocet voice unavailable: {msg}")
            if on_failed:
                on_failed(msg)
            cls._cleanup_temp_audio_files(temp_paths)
            return False

        # Step 1.5: Optional DSP Timbre & Formant Filter via ffmpeg
        wav_to_play = wav_path
        if audio_filter and shutil.which("ffmpeg"):
            filtered_wav = wav_path.replace(".wav", "_filtered.wav")
            temp_paths.append(filtered_wav)
            try:
                filter_cmd = [
                    shutil.which("ffmpeg"),
                    "-y",
                    "-i", wav_path,
                    "-af", audio_filter,
                    filtered_wav,
                ]
                fproc = subprocess.run(
                    filter_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=8,
                )
                if fproc.returncode == 0 and os.path.exists(filtered_wav) and os.path.getsize(filtered_wav) > 0:
                    wav_to_play = filtered_wav
            except Exception as fe:
                logger.debug(f"Audio filter execution fallback: {fe}")
                wav_to_play = wav_path

        # Step 2: Playback
        player_name = os.path.basename(audio_player).lower()
        if "powershell" in player_name:
            escaped_wav = wav_to_play.replace("'", "''")
            player_cmd = [
                audio_player,
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                f"(New-Object Media.SoundPlayer '{escaped_wav}').PlaySync()",
            ]
        elif player_name == "afplay":
            player_cmd = [audio_player, wav_to_play]
        else:
            player_cmd = [audio_player]
            if player_name == "paplay":
                if audio_device and audio_device != "default":
                    player_cmd.extend(["-d", audio_device])
            elif player_name == "pw-play":
                if audio_device and audio_device != "default":
                    player_cmd.extend(["--target", audio_device])
            elif player_name == "aplay":
                player_cmd.append("-q")
                if (
                    audio_device
                    and audio_device != "default"
                    and not str(audio_device).startswith("alsa_output.")
                ):
                    player_cmd.extend(["-D", audio_device])
            player_cmd.append(wav_to_play)

        try:
            play_proc = subprocess.Popen(
                player_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            logger.info(f"Speech playback started using {audio_player} on device '{audio_device}'")
            if on_started:
                try:
                    on_started()
                except Exception as e:
                    logger.warning(f"Error in on_started callback: {e}")

            try:
                _, play_stderr = play_proc.communicate(timeout=60)
            except subprocess.TimeoutExpired:
                play_proc.kill()
                _, play_stderr = play_proc.communicate()
                msg = "Audio playback timed out after 60 seconds."
                logger.error(f"Avocet voice unavailable: {msg}")
                if on_failed:
                    on_failed(msg)
                return False
            if play_proc.returncode != 0:
                err_str = play_stderr.decode("utf-8", errors="replace").strip() if play_stderr else ""
                msg = f"Audio playback command '{audio_player}' failed with code {play_proc.returncode}: {err_str}"
                logger.error(f"Avocet voice unavailable: {msg}")
                if on_failed:
                    on_failed(msg)
                return False

            logger.info("Speech playback completed successfully.")
            if on_completed:
                try:
                    on_completed()
                except Exception as e:
                    logger.warning(f"Error in on_completed callback: {e}")
            return True

        except Exception as e:
            msg = f"Audio playback exception: {e}"
            logger.error(f"Avocet voice unavailable: {msg}", exc_info=True)
            if on_failed:
                on_failed(msg)
            return False
        finally:
            cls._cleanup_temp_audio_files(temp_paths)

    @staticmethod
    def _cleanup_temp_audio_files(paths: List[str]):
        for path in paths:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception as exc:
                logger.debug(f"Unable to remove temporary voice file {path}: {exc}")

    @classmethod
    def speak_async(
        cls,
        text: str,
        voice_profile: Optional[str] = None,
        settings_manager: Any = None,
        on_started: Optional[Callable[[], None]] = None,
        on_completed: Optional[Callable[[], None]] = None,
        on_failed: Optional[Callable[[str], None]] = None,
    ) -> threading.Thread:
        """Spawns background daemon thread to synthesize and play speech without blocking Qt."""
        def _worker():
            with cls._speech_lock:
                cls.synthesize_and_play(
                    text=text,
                    voice_profile=voice_profile,
                    settings_manager=settings_manager,
                    on_started=on_started,
                    on_completed=on_completed,
                    on_failed=on_failed,
                )

        thread = threading.Thread(target=_worker, name="AvocetVoiceWorker", daemon=True)
        thread.start()
        return thread

    @classmethod
    def preview_voice_profile(
        cls,
        voice_id: str,
        settings_manager: Any,
        on_started: Optional[Callable[[], None]] = None,
        on_completed: Optional[Callable[[], None]] = None,
        on_failed: Optional[Callable[[str], None]] = None,
    ) -> threading.Thread:
        """Plays a sample morning greeting in the requested voice profile asynchronously."""
        profile = cls.VOICE_PROFILES.get(voice_id, cls.VOICE_PROFILES.get("serena", {}))
        preview_text = profile.get(
            "preview_text",
            "Good morning! Just a reminder that you are deeply appreciated today. Take your time and breathe easy."
        )
        logger.info(f"[Voice Preview Action] Playing profile '{voice_id}': '{preview_text}'")
        return cls.speak_async(
            text=preview_text,
            voice_profile=voice_id,
            settings_manager=settings_manager,
            on_started=on_started,
            on_completed=on_completed,
            on_failed=on_failed,
        )

    @classmethod
    def test_durga_voice(
        cls,
        settings_manager: Any,
        on_started: Optional[Callable[[], None]] = None,
        on_completed: Optional[Callable[[], None]] = None,
        on_failed: Optional[Callable[[str], None]] = None,
    ) -> threading.Thread:
        """
        Immediately speaks test confirmation string:
        'Hi {salutation}, I am {assistant}. Your Todo Bird voice is working.'
        Bypasses already_spoken_today and period suppression gates.
        """
        salutation = settings_manager.get("user_salutation", cls.DEFAULT_USER_SALUTATION)
        assistant = settings_manager.get("assistant_name", cls.DEFAULT_ASSISTANT_NAME)
        test_text = f"Hi {salutation}, I am {assistant}. Your Todo Bird voice is working."
        logger.info(f"[Test Voice Action] Triggered: '{test_text}'")
        return cls.speak_async(
            text=test_text,
            voice_profile="durga",
            settings_manager=settings_manager,
            on_started=on_started,
            on_completed=on_completed,
            on_failed=on_failed,
        )

    @classmethod
    def test_startup_greeting(
        cls,
        settings_manager: Any,
        on_started: Optional[Callable[[], None]] = None,
        on_completed: Optional[Callable[[], None]] = None,
        on_failed: Optional[Callable[[str], None]] = None,
    ) -> threading.Thread:
        """
        Immediately plays current period greeting for verification.
        Bypasses already_spoken_today gate, but does NOT mark today as spoken.
        """
        period = cls.determine_period()
        greeting_text = cls.build_greeting_text(period, settings_manager)
        logger.info(f"[Test Startup Greeting Action] Triggered for period '{period}': '{greeting_text}'")
        voice_profile = settings_manager.get("active_voice_profile", "durga")
        return cls.speak_async(
            text=greeting_text,
            voice_profile=voice_profile,
            settings_manager=settings_manager,
            on_started=on_started,
            on_completed=on_completed,
            on_failed=on_failed,
        )

    @classmethod
    def reset_spoken_today(cls, settings_manager: Any, period: Optional[str] = None):
        """Resets the 'last_greeting_{period}_date' setting to allow re-testing startup greeting."""
        periods = [period] if period else ["morning", "afternoon", "evening", "night"]
        for p in periods:
            key = f"last_greeting_{p}_date"
            settings_manager.set(key, "")
        logger.info(f"[Reset Spoken Today] Cleared last greeting date for periods: {periods}")
