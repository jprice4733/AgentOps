"""Ingestion worker: scan S3, transcribe, embed, and persist call segments.

    python -m wav_search_agent.worker run --once      # process everything due, then exit
    python -m wav_search_agent.worker run --interval 60
    python -m wav_search_agent.worker status
    python -m wav_search_agent.worker retry-failed
"""
import argparse
import logging
import os
import signal
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .catalog import Catalog
from .config import CATALOG_FILE
from .processing import create_recording_clip, transcribe_and_save
from .s3_store import S3Store
from .vector_store import VectorStore

log = logging.getLogger("wav_search_agent.worker")

WHISPER_MAX_BYTES = 25 * 1024 * 1024


class PermanentError(Exception):
    """A failure that retrying cannot fix."""


@dataclass
class WorkerConfig:
    workers: int = 4
    max_attempts: int = 5
    lease_seconds: int = 900
    embed_batch: int = 64
    create_clips: bool = False
    heartbeat_file: str | None = None

    @classmethod
    def from_env(cls):
        return cls(
            workers=int(os.getenv("WORKER_CONCURRENCY", "4")),
            heartbeat_file=os.getenv("WORKER_HEARTBEAT_FILE") or None,
            max_attempts=int(os.getenv("WORKER_MAX_ATTEMPTS", "5")),
            create_clips=os.getenv("WORKER_CREATE_CLIPS", "false").lower() in ("true", "1", "yes"))


def segments_from_payload(payload):
    segments = []
    for index, segment in enumerate(payload.get("segments") or []):
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text", "")).strip()
        if text:
            segments.append({"idx": index, "start_time": float(segment.get("start", 0)),
                             "end_time": float(segment.get("end", 0)), "text": text})
    return segments


class IngestWorker:
    def __init__(self, store, catalog, vectors, transcriber=None, embedder=None,
                 config=None, stop_event=None):
        self.store, self.catalog, self.vectors = store, catalog, vectors
        self.transcriber, self.embedder = transcriber, embedder
        self.config = config or WorkerConfig()
        self.stop = stop_event or threading.Event()

    def _beat(self):
        """Touch the heartbeat file so a supervisor can tell the worker is making progress."""
        if self.config.heartbeat_file:
            Path(self.config.heartbeat_file).touch()

    def scan(self):
        """Compare S3 against the catalog; queue new or replaced recordings."""
        items = [{"uri": self.store.uri(item["Key"]), "key": item["Key"],
                  "fingerprint": self.store.fingerprint(item), "etag": item.get("ETag"),
                  "size": item["Size"], "last_modified": str(item.get("LastModified"))}
                 for item in self.store.audio_objects()]
        counts = self.catalog.register(items)
        removed = self.catalog.mark_removed({item["uri"] for item in items})
        for uri in removed:
            self.vectors.delete_call(uri)
        counts["removed"] = len(removed)
        log.info("Scan: %s", counts)
        return counts

    def _embed(self, texts):
        vectors = []
        for offset in range(0, len(texts), self.config.embed_batch):
            vectors.extend(self.embedder.embed_documents(texts[offset:offset + self.config.embed_batch]))
        return vectors

    def process(self, job):
        item = {"Key": job["key"], "ETag": job["etag"], "Size": job["size"],
                "LastModified": job["last_modified"]}
        if self.store.fingerprint(item) != job["fingerprint"]:
            raise PermanentError("Catalog entry does not match its S3 fingerprint.")
        payload = self.store.transcript(item)
        if payload is None:
            if job["size"] > WHISPER_MAX_BYTES:
                raise PermanentError(f"Recording is {job['size']} bytes; transcription limit is 25 MB.")
            payload = transcribe_and_save(self.store, self.transcriber, item)
        segments = segments_from_payload(payload)
        if segments:
            if self.embedder is None:
                raise PermanentError("No embedder configured; set OPENAI_API_KEY.")
            self.vectors.replace_call(job["uri"], job["fingerprint"], segments,
                                      self._embed([s["text"] for s in segments]))
        else:
            self.vectors.delete_call(job["uri"])
        duration = max((s["end_time"] for s in segments), default=0.0)
        if not self.catalog.complete(job["uri"], job["fingerprint"], segments, duration):
            log.info("Recording changed during processing; it will be re-queued: %s", job["uri"])
            return "stale"
        if self.config.create_clips:
            try:
                create_recording_clip(self.store, item)
            except Exception as exc:  # a missing full-recording clip must not fail indexing
                log.warning("Full-recording clip failed for %s: %s", job["uri"], exc)
        return "done"

    def _run_job(self, job):
        try:
            result = self.process(job)
            log.info("%s: %s", result, job["uri"])
            return result
        except Exception as exc:
            status = self.catalog.fail(job["uri"], job["fingerprint"], f"{type(exc).__name__}: {exc}",
                                       self.config.max_attempts, permanent=isinstance(exc, PermanentError))
            log.warning("%s (attempt %s): %s: %s", status, job["attempts"], job["uri"], exc)
            return status

    def run_once(self):
        """Scan, then process every job that is due. Backed-off retries wait for the next run."""
        self._beat()
        report = {"scan": self.scan(), "done": 0, "retrying": 0, "failed": 0, "stale": 0}
        with ThreadPoolExecutor(max_workers=self.config.workers) as pool:
            while not self.stop.is_set():
                self._beat()
                jobs = self.catalog.claim(self.config.workers * 2, self.config.lease_seconds,
                                          self.config.max_attempts)
                if not jobs:
                    break
                for result in pool.map(self._run_job, jobs):
                    report[{"pending": "retrying"}.get(result, result)] += 1
        log.info("Run complete: %s", report)
        return report

    def run_forever(self, interval):
        while not self.stop.is_set():
            try:
                self.run_once()
            except Exception:
                log.exception("Ingestion run failed; will retry")
            self.stop.wait(interval)


def build_worker(args):
    store = S3Store(args.uri, args.profile)
    config = WorkerConfig.from_env()
    if args.workers:
        config.workers = args.workers
    transcriber = embedder = None
    if os.getenv("OPENAI_API_KEY"):
        from langchain_openai import OpenAIEmbeddings
        from openai import OpenAI
        transcriber = OpenAI(max_retries=5)
        embedder = OpenAIEmbeddings()
    else:
        log.warning("OPENAI_API_KEY is not set; only already-transcribed empty recordings can be processed.")
    return IngestWorker(store, Catalog(os.getenv("CATALOG_PATH", str(CATALOG_FILE))),
                        VectorStore.from_env(), transcriber, embedder, config)


def main(argv=None):
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--uri")
    parser.add_argument("--profile")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    run.add_argument("--once", action="store_true", help="exit when nothing is due")
    run.add_argument("--interval", type=int, default=60, help="seconds between scans")
    run.add_argument("--workers", type=int)
    commands.add_parser("status")
    commands.add_parser("retry-failed")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.command in ("status", "retry-failed"):
        catalog = Catalog(os.getenv("CATALOG_PATH", str(CATALOG_FILE)))
        if args.command == "retry-failed":
            print(f"Re-queued {catalog.requeue_failed()} failed recording(s).")
        else:
            print(catalog.stats())
            for failure in catalog.failures():
                print(f"FAILED {failure['uri']} (attempts {failure['attempts']}): {failure['last_error']}")
        return 0

    worker = build_worker(args)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: worker.stop.set())
    if args.once:
        report = worker.run_once()
        return 1 if report["failed"] else 0
    worker.run_forever(args.interval)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
