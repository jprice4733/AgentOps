import datetime
import io
import wave
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from botocore.exceptions import ClientError
from qdrant_client import QdrantClient

from wav_search_agent.catalog import Catalog
from wav_search_agent.s3_store import S3Store
from wav_search_agent.vector_store import VectorStore
from wav_search_agent.worker import IngestWorker, WorkerConfig, next_midnight

NOW = datetime.datetime(2026, 1, 1)


class FakeS3:
    """Minimal in-memory boto3 S3 client."""

    def __init__(self):
        self.objects = {}

    def add(self, key, data=b"audio", etag="v1"):
        self.objects[key] = {"data": data, "ETag": etag, "LastModified": NOW}

    def get_paginator(self, name):
        client = self

        class Paginator:
            def paginate(self, Bucket, Prefix):
                yield {"Contents": [{"Key": k, "Size": len(v["data"]), "ETag": v["ETag"],
                                     "LastModified": v["LastModified"]}
                                    for k, v in sorted(client.objects.items()) if k.startswith(Prefix)]}
        return Paginator()

    def get_object(self, Bucket, Key, **kwargs):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key]["data"])}

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[Key] = {"data": Body, "ETag": "x", "LastModified": NOW}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}


def transcriber(text="adjusted my neck", fail=None):
    client = Mock()
    seg = Mock(start=0.0, end=2.5, text=text)
    client.audio.transcriptions.create.return_value = Mock(text=text, segments=[seg])
    if fail:
        client.audio.transcriptions.create.side_effect = fail
    return client


class FakeEmbedder:
    def embed_documents(self, texts):
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


@pytest.fixture
def env(tmp_path):
    s3 = FakeS3()
    s3.add("calls/a.wav")
    store = S3Store(uri="s3://bucket/calls/", client=s3)
    catalog = Catalog(tmp_path / "catalog.sqlite")
    vectors = VectorStore(QdrantClient(":memory:"), vector_size=4)
    cfg = WorkerConfig(workers=2, max_attempts=3)

    def make(client=None):
        return IngestWorker(store, catalog, vectors, client or transcriber(), FakeEmbedder(), cfg)
    return s3, store, catalog, vectors, make


def test_end_to_end_index_is_searchable_and_persistent(env, tmp_path):
    s3, store, catalog, vectors, make = env
    report = make().run_once()
    assert report["done"] == 1 and report["scan"]["new"] == 1
    assert catalog.stats() == {"calls": {"done": 1}, "segments": 1}
    assert catalog.search_text("adjusting neck")[0]["file_path"] == "s3://bucket/calls/a.wav"
    assert vectors.count() == 1
    assert any(k.endswith(".json") for k in s3.objects)  # transcript saved to S3
    catalog.close()
    assert Catalog(tmp_path / "catalog.sqlite").stats()["segments"] == 1


def test_rerun_skips_unchanged_recordings(env):
    _, _, _, vectors, make = env
    client = transcriber()
    make(client).run_once()
    report = make(client).run_once()
    assert report["scan"]["unchanged"] == 1 and report["done"] == 0
    assert client.audio.transcriptions.create.call_count == 1
    assert vectors.count() == 1


def test_replaced_recording_replaces_old_segments_and_vectors(env):
    s3, _, catalog, vectors, make = env
    make().run_once()
    s3.add("calls/a.wav", data=b"new audio!", etag="v2")
    report = make(transcriber("knee pain")).run_once()
    assert report["scan"]["changed"] == 1 and report["done"] == 1
    assert catalog.search_text("neck") == []
    assert catalog.search_text("knee")
    assert vectors.count() == 1


def test_removed_recording_is_dropped(env):
    s3, _, catalog, vectors, make = env
    s3.add("calls/b.wav", etag="b1")
    make().run_once()
    assert vectors.count() == 2
    del s3.objects["calls/b.wav"]
    assert make().run_once()["scan"]["removed"] == 1
    assert vectors.count() == 1 and catalog.stats()["segments"] == 1


def test_empty_listing_never_wipes_the_index(env):
    s3, _, catalog, vectors, make = env
    make().run_once()
    s3.objects.clear()
    assert make().run_once()["scan"]["removed"] == 0
    assert vectors.count() == 1


def test_failure_backs_off_then_fails_permanently_and_others_continue(env):
    s3, store, catalog, vectors, make = env
    s3.add("calls/b.wav", etag="b1")
    bad = transcriber(fail=RuntimeError("API down"))
    good_then_bad = Mock()
    good = transcriber()

    def create(**kwargs):
        if kwargs["file"][0] == "a.wav":
            return bad.audio.transcriptions.create(**kwargs)
        return good.audio.transcriptions.create(**kwargs)
    good_then_bad.audio.transcriptions.create.side_effect = create
    worker = make(good_then_bad)
    report = worker.run_once()
    assert report["done"] == 1 and report["retrying"] == 1
    assert catalog.stats()["calls"] == {"done": 1, "pending": 1}
    # Backed off: not due again until the delay has passed.
    assert worker.run_once()["retrying"] == 0
    for attempt in (2, 3):
        jobs = catalog.claim(10, 900, 3, now=1e12 * attempt)
        assert len(jobs) == 1
        status = catalog.fail(jobs[0]["uri"], jobs[0]["fingerprint"], "API down", 3, now=1e12 * attempt)
    assert status == "failed"
    assert catalog.failures()[0]["last_error"] == "API down"
    assert catalog.requeue_failed() == 1


def test_oversize_recording_fails_permanently_without_calling_api(env, monkeypatch):
    _, _, catalog, _, make = env
    monkeypatch.setattr("wav_search_agent.worker.WHISPER_MAX_BYTES", 0)
    client = transcriber()
    assert make(client).run_once()["failed"] == 1
    assert "25 MB" in catalog.failures()[0]["last_error"]
    client.audio.transcriptions.create.assert_not_called()


def test_expired_lease_is_reclaimed_and_poison_jobs_stop(env):
    _, _, catalog, _, make = env
    make().scan()
    assert len(catalog.claim(5, 10, 3, now=100)) == 1
    assert catalog.claim(5, 10, 3, now=105) == []           # still leased
    assert len(catalog.claim(5, 10, 3, now=200)) == 1       # lease expired, attempt 2
    assert len(catalog.claim(5, 10, 3, now=300)) == 1       # attempt 3
    assert catalog.claim(5, 10, 3, now=400) == []           # exhausted
    assert catalog.stats()["calls"] == {"failed": 1}


def test_empty_transcript_completes_without_vectors(env):
    s3, _, catalog, vectors, make = env
    client = Mock()
    client.audio.transcriptions.create.return_value = Mock(text="", segments=[])
    assert make(client).run_once()["done"] == 1
    assert vectors.count() == 0 and catalog.stats()["segments"] == 0


def test_local_vector_store_is_safe_under_concurrent_workers(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    vectors = VectorStore(QdrantClient(path=str(tmp_path / "vectors")), vector_size=4)
    segments = [{"idx": i, "start_time": 0.0, "end_time": 1.0, "text": "t"} for i in range(20)]

    def work(n):
        vectors.replace_call(f"s3://b/{n}.wav", "f", segments, [[1.0, 0.0, 0.0, 0.0]] * 20)
        vectors.search([1.0, 0.0, 0.0, 0.0], 3)
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(work, range(40)))
    assert vectors.count() == 40 * 20


def test_heartbeat_file_is_touched_while_running(env, tmp_path):
    _, store, catalog, vectors, _ = env
    beat = tmp_path / "worker.heartbeat"
    worker = IngestWorker(store, catalog, vectors, transcriber(), FakeEmbedder(),
                          WorkerConfig(workers=1, heartbeat_file=str(beat)))
    assert not beat.exists()
    worker.run_once()
    assert beat.exists()


def test_clips_backfill_and_retry_without_retranscribing(env):
    s3, store, catalog, vectors, make = env
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 80)
    s3.add("calls/a.wav", data=output.getvalue())
    client = transcriber()
    worker = make(client)
    worker.run_once()  # indexed before clip creation was enabled
    worker.config.create_clips = True
    report = worker.run_once()
    assert report["done"] == 0
    assert report["clips"] == {"created": 1, "existing": 0, "failed": 0}
    clip_key = next(k for k in s3.objects if k.startswith(store.clips_prefix))
    assert worker.run_once()["clips"] == {"created": 0, "existing": 1, "failed": 0}
    del s3.objects[clip_key]
    assert worker.run_once()["clips"]["created"] == 1
    assert client.audio.transcriptions.create.call_count == 1
    assert catalog.stats()["calls"] == {"done": 1}
    assert vectors.count() == 1


def test_clip_failure_retries_next_run_and_other_clips_continue(env, monkeypatch):
    s3, _, catalog, _, make = env
    s3.add("calls/b.wav", etag="b1")
    worker = make()
    worker.config.create_clips = True
    create = Mock(side_effect=[RuntimeError("S3 unavailable"), True, True, False])
    monkeypatch.setattr("wav_search_agent.worker.create_recording_clip", create)
    assert worker.run_once()["clips"] == {"created": 1, "existing": 0, "failed": 1}
    assert catalog.stats()["calls"] == {"done": 2}
    assert worker.run_once()["clips"] == {"created": 1, "existing": 1, "failed": 0}


@pytest.mark.parametrize("day,hours", [(datetime.date(2026, 3, 8), 23),
                                      (datetime.date(2026, 11, 1), 25)])
def test_midnight_schedule_observes_denver_dst(day, hours):
    zone = ZoneInfo("America/Denver")
    start = datetime.datetime.combine(day, datetime.time.min, tzinfo=zone)
    utc_start = start.astimezone(datetime.timezone.utc)
    scheduled = next_midnight(utc_start, zone)
    assert (scheduled - utc_start).total_seconds() == hours * 3600
    local = scheduled.astimezone(zone)
    assert local.date() == day + datetime.timedelta(days=1)
    assert local.hour == local.minute == 0


def test_daily_waits_until_midnight_and_runs_once(env, monkeypatch):
    _, _, _, _, make = env
    worker = make()
    before = datetime.datetime(2026, 10, 14, 5, 59, 40, tzinfo=datetime.timezone.utc)
    midnight = before + datetime.timedelta(seconds=20)
    clock = Mock(wraps=datetime.datetime)
    clock.now.side_effect = [before, before, midnight]
    monkeypatch.setattr("wav_search_agent.worker.datetime", clock)
    worker.stop.wait = Mock(return_value=False)
    worker.run_once = Mock(side_effect=worker.stop.set)
    worker.run_daily(ZoneInfo("America/Denver"))
    worker.stop.wait.assert_called_once_with(20)
    worker.run_once.assert_called_once_with()


def test_daily_wait_maintains_heartbeat_and_stops_without_processing(env, tmp_path):
    _, _, _, _, make = env
    worker = make()
    beat = tmp_path / "heartbeat"
    worker.config.heartbeat_file = str(beat)
    worker.stop.wait = Mock(side_effect=lambda timeout: worker.stop.set())
    worker.run_once = Mock()
    worker.run_daily(ZoneInfo("America/Denver"))
    assert beat.exists()
    worker.run_once.assert_not_called()
