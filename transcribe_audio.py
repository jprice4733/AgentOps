"""Read recordings from S3 and save transcripts in S3."""
import argparse
import os
from pathlib import PurePosixPath
from dotenv import load_dotenv
from openai import OpenAI
from s3_audio import ROOT
from wav_search_agent.s3_store import S3Store


def transcribe_object(store, client, item):
    if store.transcript(item) is not None:
        return False
    kwargs = {"IfMatch": item["ETag"]} if item.get("ETag") else {}
    audio = store.read(item["Key"], **kwargs)
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


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile")
    parser.add_argument("--uri")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY in .env before transcribing.")
    store, client = S3Store(args.uri, args.profile), OpenAI()
    for count, item in enumerate(store.audio_objects(), 1):
        created = transcribe_object(store, client, item)
        print(f"{'Transcribed' if created else 'Already transcribed'}: {store.uri(item['Key'])}")
        if args.limit is not None and count >= args.limit:
            break


if __name__ == "__main__":
    main()
