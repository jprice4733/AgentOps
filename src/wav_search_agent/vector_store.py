"""Persistent Qdrant vector store with idempotent, per-call replacement."""
import os
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (Distance, FieldCondition, Filter, FilterSelector,
                                  MatchValue, PointStruct, VectorParams)

from .config import VECTOR_DIR

COLLECTION = "s3_audio_segments"
VECTOR_SIZE = 1536
UPSERT_BATCH = 256
_NAMESPACE = uuid.UUID("6f0f3f0e-3a55-4f0e-9d53-0c1f6a1d7a11")


def point_id(uri, fingerprint, idx):
    """Deterministic ID, so re-running a job overwrites rather than duplicates."""
    return str(uuid.uuid5(_NAMESPACE, f"{uri}|{fingerprint}|{idx}"))


class VectorStore:
    def __init__(self, client, collection=COLLECTION, vector_size=VECTOR_SIZE):
        self.client = client
        self.collection = collection
        self.vector_size = vector_size
        self._ensure_collection()

    @classmethod
    def from_env(cls):
        """Use QDRANT_URL (server, shareable by worker and web app) or a local path.

        Local path mode holds a file lock, so only one process can open it.
        """
        url = os.getenv("QDRANT_URL")
        if url:
            client = QdrantClient(url=url, api_key=os.getenv("QDRANT_API_KEY") or None)
        else:
            client = QdrantClient(path=os.getenv("QDRANT_PATH", str(VECTOR_DIR)))
        return cls(client)

    def _ensure_collection(self):
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE))
        try:
            self.client.create_payload_index(self.collection, "file_path", "keyword")
        except Exception:  # local mode does not support payload indexes
            pass

    def delete_call(self, uri):
        self.client.delete(
            collection_name=self.collection,
            points_selector=FilterSelector(filter=Filter(must=[
                FieldCondition(key="file_path", match=MatchValue(value=uri))])))

    def replace_call(self, uri, fingerprint, segments, vectors):
        """Replace every vector for a call. `segments` carry idx, start_time, end_time, text."""
        if len(segments) != len(vectors):
            raise ValueError("Each segment needs exactly one vector.")
        self.delete_call(uri)
        points = [PointStruct(
            id=point_id(uri, fingerprint, segment["idx"]), vector=vector,
            payload={"file_path": uri, "fingerprint": fingerprint,
                     "start_time": segment["start_time"], "end_time": segment["end_time"],
                     "text": segment["text"]})
            for segment, vector in zip(segments, vectors)]
        for offset in range(0, len(points), UPSERT_BATCH):
            self.client.upsert(collection_name=self.collection,
                               points=points[offset:offset + UPSERT_BATCH])

    def search(self, vector, limit=5):
        return self.client.query_points(
            collection_name=self.collection, query=vector, limit=limit).points

    def count(self):
        return self.client.count(collection_name=self.collection, exact=True).count
