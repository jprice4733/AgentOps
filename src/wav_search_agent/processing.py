"""Fill missing S3 transcript and full-recording clip outputs."""
from io import BytesIO
from pathlib import PurePosixPath

from openai import OpenAI
from pydub import AudioSegment


def transcribe_object(store, client, item):
    if store.transcript(item) is not None:
        return False
    kwargs = {"IfMatch": item["ETag"]} if item.get("ETag") else {}
    audio = store.read(item["Key"], **kwargs)
    client = client or OpenAI()
    transcription = client.audio.transcriptions.create(
        model="whisper-1", file=(PurePosixPath(item["Key"]).name, audio),
        response_format="verbose_json", timestamp_granularities=["segment"],
    )
    store.save_transcript(item, {
        "file_path": store.uri(item["Key"]), "text": transcription.text,
        "segments": [{"id": index, "start": float(segment.start),
                      "end": float(segment.end), "text": segment.text.strip()}
                     for index, segment in enumerate(transcription.segments or [])],
    })
    return True


def create_recording_clip(store, item):
    name = store.recording_clip_name(item)
    if store.clip_exists(name):
        return False
    kwargs = {"IfMatch": item["ETag"]} if item.get("ETag") else {}
    with BytesIO(store.read(item["Key"], **kwargs)) as source:
        audio = AudioSegment.from_file(source)
    with BytesIO() as output:
        audio.export(output, format="wav")
        store.save_clip(name, output.getvalue())
    return True


def sync_outputs(store, client=None, limit=None):
    """Process each output independently so one failed recording does not stop the rest."""
    report = {"recordings": 0, "transcripts_created": 0, "clips_created": 0, "errors": []}
    for item in store.audio_objects():
        report["recordings"] += 1
        for kind, operation in (
            ("transcripts", lambda: transcribe_object(store, client, item)),
            ("clips", lambda: create_recording_clip(store, item)),
        ):
            try:
                created = operation()
                report[kind + "_created"] += int(created)
                print(f"{kind}: {'created' if created else 'exists'}: {item['Key']}")
            except Exception as exc:
                error = f"{kind}: {item['Key']}: {exc}"
                report["errors"].append(error)
                print(f"Processing failed: {error}")
        if limit is not None and report["recordings"] >= limit:
            break
    return report
