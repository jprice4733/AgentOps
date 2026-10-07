"""Synthetic load test for the ingestion worker, catalog and vector store.

Uses an in-memory fake S3 and fake OpenAI clients, so it measures this code's
overhead (catalog, Qdrant, threading), not network or API latency.

    python scripts/load_test.py --calls 5000 --workers 4
"""
import argparse
import datetime
import io
import json
import os
import random
import resource
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from qdrant_client import QdrantClient  # noqa: E402

from wav_search_agent.catalog import Catalog  # noqa: E402
from wav_search_agent.s3_store import S3Store  # noqa: E402
from wav_search_agent.vector_store import VectorStore  # noqa: E402
from wav_search_agent.worker import IngestWorker, WorkerConfig  # noqa: E402

FIRST = ["Doug", "Maria", "James", "Linda", "Robert", "Susan", "Kevin", "Angela", "Brian", "Karen"] * 2
LAST = ["Miers", "Garcia", "Smith", "Johnson", "Lee", "Brown", "Davis", "Wilson", "Moore", "Taylor"]
TEMPLATES = [
    "Hi this is {n} calling to reschedule my appointment for {d}.",
    "I have lower back pain and I would like to see the doctor.",
    "Do you accept {ins} insurance for adjustments?",
    "My neck has been stiff since the car accident last week.",
    "Can I move my visit from {d} to the afternoon please.",
    "I need a copy of my billing statement for my records.",
    "What time does the office open on {d}.",
    "Thank you, we will see you on {d}.",
    "The doctor recommended physical therapy for my shoulder.",
    "Please call me back at this number when you get a chance.",
]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
INSURERS = ["Aetna", "Cigna", "Blue Cross", "United", "Medicare"]
NOW = datetime.datetime(2026, 1, 1)


class FakeS3:
    def __init__(self):
        self.objects = {}

    def add(self, key, data=b"audio", etag="v1"):
        self.objects[key] = {"data": data, "ETag": etag, "LastModified": NOW}

    def get_paginator(self, name):
        client = self

        class Paginator:
            def paginate(self, Bucket, Prefix):
                keys = sorted(k for k in list(client.objects) if k.startswith(Prefix))
                for offset in range(0, len(keys), 1000):
                    yield {"Contents": [{"Key": k, "Size": len(client.objects[k]["data"]),
                                         "ETag": client.objects[k]["ETag"],
                                         "LastModified": client.objects[k]["LastModified"]}
                                        for k in keys[offset:offset + 1000]]}
        return Paginator()

    def get_object(self, Bucket, Key, **kwargs):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key]["data"])}

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[Key] = {"data": Body, "ETag": "x", "LastModified": NOW}


class FakeTranscriber:
    def __init__(self, latency):
        self.latency = latency
        self.audio = self.transcriptions = self

    def create(self, model, file, **kwargs):
        time.sleep(self.latency)
        rng = random.Random(file[0])
        segments, clock = [], 0.0
        for _ in range(rng.randint(25, 45)):  # about 3.5 minutes of speech
            text = rng.choice(TEMPLATES).format(
                n=f"{rng.choice(FIRST)} {rng.choice(LAST)}", d=rng.choice(DAYS), ins=rng.choice(INSURERS))
            end = clock + rng.uniform(3, 8)
            segments.append(SimpleNamespace(start=clock, end=end, text=text))
            clock = end
        return SimpleNamespace(text=" ".join(s.text for s in segments), segments=segments)


class FakeEmbedder:
    def __init__(self, latency):
        self.latency = latency

    def embed_documents(self, texts):
        time.sleep(self.latency)
        return np.random.default_rng().random((len(texts), 1536), dtype=np.float32).tolist()


class NullVectors:
    """Stands in for Qdrant to isolate the worker and SQLite catalog."""
    def __init__(self):
        self.client = SimpleNamespace(close=lambda: None)
        self.points = 0

    def replace_call(self, uri, fingerprint, segments, vectors):
        self.points += len(segments)

    def delete_call(self, uri):
        pass

    def search(self, vector, limit=5):
        return []

    def count(self):
        return self.points


def rss_mb():
    """Peak resident memory of this process (macOS reports bytes, Linux kilobytes)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1e6 if sys.platform == "darwin" else peak / 1e3


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * q))]


def timed(fn, repeat):
    samples = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return samples


def row(label, samples):
    print(f"  {label:<34} p50 {statistics.median(samples):8.1f} ms   p95 {pct(samples, .95):8.1f} ms"
          f"   max {max(samples):8.1f} ms")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--calls", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--api-latency", type=float, default=0.0, help="simulated seconds per API call")
    parser.add_argument("--qdrant-url", help="use a Qdrant server instead of a local path")
    parser.add_argument("--no-vectors", action="store_true", help="stub out Qdrant to isolate the catalog")
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()

    workdir = Path(tempfile.mkdtemp(prefix="wav-load-"))
    print(f"Workdir {workdir}; {args.calls} calls, {args.workers} workers, API latency {args.api_latency}s")
    s3 = FakeS3()
    for index in range(args.calls):
        s3.add(f"calls/{index:06d}.wav", etag=f"e{index}")
    store = S3Store(uri="s3://bucket/calls/", client=s3)

    def open_stores():
        catalog = Catalog(workdir / "catalog.sqlite")
        if args.no_vectors:
            return catalog, NullVectors()
        client = QdrantClient(url=args.qdrant_url) if args.qdrant_url else QdrantClient(path=str(workdir / "vectors"))
        return catalog, VectorStore(client)

    catalog, vectors = open_stores()
    worker = IngestWorker(store, catalog, vectors, FakeTranscriber(args.api_latency),
                          FakeEmbedder(args.api_latency), WorkerConfig(workers=args.workers))

    print(f"\n[1] Ingest {args.calls} new calls")
    start = time.perf_counter()
    report = worker.run_once()
    elapsed = time.perf_counter() - start
    print(f"  done={report['done']} failed={report['failed']} retrying={report['retrying']}"
          f" in {elapsed:.1f}s = {report['done'] / elapsed:.1f} calls/s ({elapsed / max(report['done'], 1) * 1000:.0f} ms/call)")
    stats = catalog.stats()
    print(f"  segments={stats['segments']} vectors={vectors.count()} rss={rss_mb():.0f} MB")

    print("\n[2] Steady-state rescan (nothing changed)")
    samples = timed(worker.scan, 3)
    row(f"scan {args.calls} objects", samples)

    print("\n[3] Query latency (idle)")
    rng = random.Random(1)
    queries = [f"{rng.choice(FIRST)} {rng.choice(LAST)}" for _ in range(100)]
    iterator = iter(queries * 5)
    row("full-text phrase (name)", timed(lambda: catalog.search_text(next(iterator), 500, phrase=True), 100))
    row("full-text terms (topic)", timed(lambda: catalog.search_text("lower back pain", 500), 100))
    row("list_calls page", timed(lambda: catalog.list_calls(25, rng.randint(0, args.calls - 25)), 100))
    row("find_calls by filename", timed(lambda: catalog.find_calls(f"{rng.randint(0, args.calls - 1):06d}.wav"), 100))
    row("call_segments", timed(lambda: catalog.call_segments(f"s3://bucket/calls/{rng.randint(0, args.calls - 1):06d}.wav"), 100))
    row("coverage", timed(catalog.coverage, 50))
    qvec = np.random.default_rng(3).random(1536, dtype=np.float32).tolist()
    row("vector search (top 10)", timed(lambda: vectors.search(qvec, 10), 30))

    print("\n[4] Web-app startup (fresh process: open catalog + vector store)")
    catalog.close()
    vectors.client.close()
    probe = (
        "import sys, time, resource\n"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parents[1] / 'src')!r})\n"
        "from qdrant_client import QdrantClient\n"
        f"no_vectors = {args.no_vectors!r}\n"
        "from wav_search_agent.catalog import Catalog\n"
        "from wav_search_agent.vector_store import VectorStore\n"
        "t = time.perf_counter()\n"
        f"c = Catalog({str(workdir / 'catalog.sqlite')!r}); c.coverage()\n"
        f"v = None if no_vectors else VectorStore(QdrantClient(url={args.qdrant_url!r}) if {args.qdrant_url!r} else QdrantClient(path={str(workdir / 'vectors')!r}))\n"
        "peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n"
        "print(f'{time.perf_counter() - t:.2f}s, peak RSS {peak / (1e6 if sys.platform == \"darwin\" else 1e3):.0f} MB')\n")
    print("  " + subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True).stdout.strip())
    catalog, vectors = open_stores()

    extra = max(args.calls // 10, 20)
    print(f"\n[5] Queries while the worker ingests {extra} more calls")
    for index in range(args.calls, args.calls + extra):
        s3.add(f"calls/{index:06d}.wav", etag=f"e{index}")
    worker = IngestWorker(store, catalog, vectors, FakeTranscriber(args.api_latency),
                          FakeEmbedder(args.api_latency), WorkerConfig(workers=args.workers))
    result = {}
    thread = threading.Thread(target=lambda: result.update(worker.run_once()))
    thread.start()
    during, errors = [], []
    while thread.is_alive():
        begin = time.perf_counter()
        try:
            catalog.search_text("lower back pain", 500)
            catalog.list_calls(25, 0)
        except Exception as exc:
            errors.append(repr(exc))
        during.append((time.perf_counter() - begin) * 1000)
        time.sleep(0.05)
    thread.join()
    print(f"  ingested {result.get('done')} calls; {len(during)} query rounds, {len(errors)} errors")
    if during:
        row("full-text + list while writing", during)
    print(f"  final: {catalog.stats()} vectors={vectors.count()} peak rss={rss_mb():.0f} MB")
    size = sum(p.stat().st_size for p in workdir.rglob("*") if p.is_file()) / 1e6
    print(f"  on-disk size: {size:.0f} MB")
    if not args.keep:
        subprocess.run(["rm", "-rf", str(workdir)])


if __name__ == "__main__":
    main()
