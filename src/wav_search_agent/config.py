import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
AUDIO_DIR = BASE_DIR / "storage" / "audio"
JSON_DIR = BASE_DIR / "storage" / "json"
STATIC_DIR = BASE_DIR / "static"
CLIPS_DIR = STATIC_DIR / "clips"

AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".mp4", ".mpeg", ".mpga", ".webm"}


def ensure_directories() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)


def get_openai_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not found. Add it to your .env file.")
    return key
