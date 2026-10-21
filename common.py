
from pathlib import Path
import json
import os
import subprocess

BASE_DIR = Path.home() / "todo_bird"
CONFIG_FILE = BASE_DIR / "config" / "settings.json"
PLAN_FILE = BASE_DIR / "data" / "day_plan.json"
STATE_FILE = BASE_DIR / "data" / "runtime_state.json"
VOICE_DIR = BASE_DIR / "voice"
PIPER_BIN = "/usr/local/bin/piper"
PIPER_MODEL = VOICE_DIR / "female_indian.onnx"
PIPER_CONFIG = VOICE_DIR / "female_indian.onnx.json"

DEFAULT_SETTINGS = {
    "selected_theme": "avocet",
    "voice_enabled": True,
    "open_planify": True,
    "devotional_intro": True,
    "greeting_mode": "once_daily",
    "night_shutdown_after": 21,
    "show_gantt_on_greeting": True,
    "companion_visible_seconds": 24
}

def load_json(path: Path, fallback):
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(fallback, dict) and isinstance(data, dict):
                merged = fallback.copy()
                merged.update(data)
                return merged
            return data
    except Exception:
        pass
    return fallback.copy() if isinstance(fallback, dict) else fallback

def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)

def load_settings():
    return load_json(CONFIG_FILE, DEFAULT_SETTINGS)

def save_settings(data):
    save_json(CONFIG_FILE, data)

def speak_async(text: str):
    clean = " ".join(str(text).split())
    if not clean:
        return
    if Path(PIPER_BIN).exists() and PIPER_MODEL.exists() and PIPER_CONFIG.exists():
        out = "/tmp/todo_bird_voice.wav"
        try:
            proc = subprocess.Popen(
                [
                    PIPER_BIN, "-m", str(PIPER_MODEL), "-c", str(PIPER_CONFIG),
                    "-f", out, "--sentence_silence", "0.55",
                    "--length_scale", "1.18", "--noise_scale", "0.50",
                    "--noise_w", "0.70", "--quiet"
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True
            )
            proc.communicate(clean)
            subprocess.Popen(["aplay", "-q", out],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return
        except Exception:
            pass
    try:
        subprocess.Popen(
            ["espeak-ng", "-s", "100", "-p", "45", "-a", "130", "-v", "en+f3", clean],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception:
        pass
