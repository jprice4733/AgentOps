import json
from pathlib import Path

from qdrant_client.models import PointStruct

from .config import JSON_DIR, AUDIO_DIR


def load_json_transcripts(embeddings, qdrant_client, collection_name: str):
    """Load transcript JSON files from storage/json and index their text segments."""
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    transcript_files = sorted(JSON_DIR.glob("*.json"))

    if not transcript_files:
        print(f"No transcript JSON files found in {JSON_DIR}")
        return []

    transcripts = []
    points = []
    point_id = 1

    for transcript_path in transcript_files:
        try:
            payload = json.loads(transcript_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Skipping invalid JSON file {transcript_path}: {exc}")
            continue

        if not isinstance(payload, dict):
            print(f"Skipping non-object JSON file {transcript_path}")
            continue

        file_path = payload.get("file_path") or str(AUDIO_DIR / transcript_path.stem)
        segments = payload.get("segments") or []
        transcript_record = {
            "file_path": file_path,
            "text": payload.get("text", ""),
            "segments": [],
        }

        for segment in segments:
            if not isinstance(segment, dict):
                continue

            start_time = float(segment.get("start", 0.0) or 0.0)
            end_time = float(segment.get("end", 0.0) or 0.0)
            text = str(segment.get("text", "")).strip()
            if not text:
                continue

            segment_record = {
                "file_path": file_path,
                "start_time": start_time,
                "end_time": end_time,
                "text": text,
            }
            transcript_record["segments"].append(segment_record)
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embeddings.embed_query(text),
                    payload=segment_record,
                )
            )
            point_id += 1

        transcripts.append(transcript_record)

    if points:
        qdrant_client.upsert(collection_name=collection_name, points=points)

    print(f"Indexed {len(points)} segment(s) from {len(transcripts)} JSON transcript(s)")
    return transcripts
