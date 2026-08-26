from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

AUDIO_DIR = Path("storage/audio")
JSON_DIR = Path("storage/json")
LEGACY_TRANSCRIPTS_PATH = Path("storage/transcripts.json")
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".mp4", ".mpeg", ".mpga", ".webm"}


def save_existing_transcript(audio_path: Path, output_path: Path) -> bool:
    if not LEGACY_TRANSCRIPTS_PATH.exists():
        return False

    try:
        transcripts = json.loads(LEGACY_TRANSCRIPTS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False

    if not isinstance(transcripts, list):
        return False

    for transcript in transcripts:
        file_path = str(transcript.get("file_path", "")).strip()
        if file_path == str(audio_path) or Path(file_path).name == audio_path.name:
            output_path.write_text(json.dumps(transcript, indent=2), encoding="utf-8")
            print(f"Saved existing transcript for {audio_path.name} to {output_path}")
            return True

    return False


def main() -> None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found. Add it to the .env file before running transcription.")

    for proxy_var in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "HTTPS_PROXY",
        "GRPC_PROXY",
        "grpc_proxy",
        "FTP_PROXY",
        "ftp_proxy",
    ):
        os.environ.pop(proxy_var, None)

    JSON_DIR.mkdir(parents=True, exist_ok=True)
    client = OpenAI(api_key=api_key)

    audio_files = sorted(
        path for path in AUDIO_DIR.rglob("*")
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    )

    if not audio_files:
        print(f"No supported audio files found in {AUDIO_DIR}")
        return

    for audio_path in audio_files:
        output_path = JSON_DIR / f"{audio_path.stem}.json"
        if output_path.exists():
            print(f"Skipping {audio_path.name}: {output_path.name} already exists")
            continue

        if save_existing_transcript(audio_path, output_path):
            continue

        with audio_path.open("rb") as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        payload = {
            "file_name": audio_path.name,
            "file_path": str(audio_path),
            "text": transcription.text,
            "segments": [
                {
                    "id": idx,
                    "start": float(segment.start),
                    "end": float(segment.end),
                    "text": segment.text.strip(),
                }
                for idx, segment in enumerate(transcription.segments or [])
            ],
        }

        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Saved {output_path}")

    print(f"Finished. Transcripts are in {JSON_DIR}")


if __name__ == "__main__":
    main()

