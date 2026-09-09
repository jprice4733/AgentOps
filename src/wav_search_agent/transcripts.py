import json
from pathlib import Path

from qdrant_client.models import PointStruct

from .config import JSON_DIR, AUDIO_DIR, EMBEDDING_CACHE_FILE


def load_embedding_cache(cache_path=EMBEDDING_CACHE_FILE):
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(cached, dict):
                return cached
        except Exception:
            print(f"Ignoring unreadable embedding cache file {cache_path}")
    return {}


def save_embedding_cache(cache, cache_path=EMBEDDING_CACHE_FILE):
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"Unable to persist embedding cache {cache_path}: {exc}")


def _chunk_texts(texts, batch_size):
    batch_size = max(1, int(batch_size))
    for start in range(0, len(texts), batch_size):
        yield texts[start:start + batch_size]


def _embed_text_batch(embeddings, texts, batch_size):
    """Generate embeddings in small batches and fall back safely to single-query requests."""
    vectors = []
    for batch in _chunk_texts(texts, batch_size):
        try:
            if hasattr(embeddings, "embed_documents"):
                batch_vectors = embeddings.embed_documents(batch)
            else:
                batch_vectors = [embeddings.embed_query(text) for text in batch]
        except Exception:
            batch_vectors = [embeddings.embed_query(text) for text in batch]

        if isinstance(batch_vectors, list):
            vectors.extend(batch_vectors)
        else:
            vectors.extend(list(batch_vectors))

    return vectors


def load_json_transcripts(embeddings, qdrant_client, collection_name: str, embedding_cache=None, batch_size: int = 32):
    """Load transcript JSON files from storage/json and index their text segments.

    The loader accepts an optional embedding_cache mapping of text -> vector and uses
    batch embedding calls so repeated server startups do not have to re-embed every segment.
    """
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    transcript_files = sorted(JSON_DIR.glob("*.json"))

    if not transcript_files:
        print(f"No transcript JSON files found in {JSON_DIR}")
        return []

    if embedding_cache is None:
        embedding_cache = load_embedding_cache()

    transcripts = []
    segment_records = []

    # Parse every transcript file into a transcript structure and collect segment payloads.
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
            segment_records.append(segment_record)

        transcripts.append(transcript_record)

    # De-duplicate text inputs and generate vectors once per new phrase.
    unique_texts = []
    seen_texts = set()
    for segment in segment_records:
        text = segment["text"]
        if text in embedding_cache:
            continue
        if text not in seen_texts:
            unique_texts.append(text)
            seen_texts.add(text)

    vectors_by_text = {}
    if unique_texts:
        vectors = _embed_text_batch(embeddings, unique_texts, batch_size)
        for text, vector in zip(unique_texts, vectors):
            embedding_cache[text] = vector
            vectors_by_text[text] = vector

    # Turn the parsed payload records into Qdrant point payloads.
    points = []
    point_id = 1
    for segment in segment_records:
        text = segment["text"]
        vector = embedding_cache.get(text)
        if vector is None:
            try:
                vector = embeddings.embed_query(text)
            except Exception:
                print(f"Skipping embedding for segment text: {text[:80]}")
                continue
            embedding_cache[text] = vector

        points.append(
            PointStruct(
                id=point_id,
                vector=vector,
                payload=segment,
            )
        )
        point_id += 1

    if points:
        qdrant_client.upsert(collection_name=collection_name, points=points)

    save_embedding_cache(embedding_cache)

    print(f"Indexed {len(points)} segment(s) from {len(transcripts)} JSON transcript(s)")
    return transcripts
