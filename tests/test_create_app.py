import json

from fastapi.testclient import TestClient


def test_load_json_transcripts_accepts_embedding_cache_and_batching(monkeypatch, tmp_path):
    import wav_search_agent.transcripts as transcripts_module

    json_dir = tmp_path / "json"
    audio_dir = tmp_path / "audio"
    json_dir.mkdir(parents=True)
    audio_dir.mkdir(parents=True)

    sample_json = json_dir / "sample.json"
    sample_json.write_text(json.dumps({
        "file_path": str(audio_dir / "sample.wav"),
        "text": "A transcript",
        "segments": [
            {"start": 0.0, "end": 1.0, "text": "hello world"},
            {"start": 1.0, "end": 2.0, "text": "hello world"},
        ],
    }), encoding="utf-8")

    monkeypatch.setattr(transcripts_module, "JSON_DIR", json_dir)
    monkeypatch.setattr(transcripts_module, "AUDIO_DIR", audio_dir)

    class DummyEmbeddings:
        def __init__(self):
            self.calls = []

        def embed_documents(self, texts):
            self.calls.append(list(texts))
            return [[0.1, 0.2, 0.3] for _ in texts]

    class DummyQdrantClient:
        def __init__(self):
            self.points = None

        def upsert(self, collection_name, points):
            self.collection_name = collection_name
            self.points = points

    embeddings = DummyEmbeddings()
    qdrant = DummyQdrantClient()
    cache = {}

    transcripts_module.load_json_transcripts(
        embeddings,
        qdrant,
        "test_collection",
        embedding_cache=cache,
        batch_size=10,
    )

    assert len(embeddings.calls) == 1
    assert embeddings.calls[0] == ["hello world"]
    assert len(qdrant.points) == 2
    assert len(cache) == 1
    assert cache["hello world"] == [0.1, 0.2, 0.3]


def test_create_app_handles_embedding_failure(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    import main

    class DummyEmbeddings:
        def __init__(self, *args, **kwargs):
            pass

        def embed_query(self, text):
            raise RuntimeError("Connection error")

    monkeypatch.setattr(main, "OpenAIEmbeddings", DummyEmbeddings)

    app = main.create_app()
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<html" in response.text.lower()
    assert app.title == "WAV Chat Agent"


def test_main_indexes_all_embedding_batches_and_skips_unchanged_sources(monkeypatch, tmp_path):
    import main

    transcript_dir = tmp_path / "storage" / "json"
    transcript_dir.mkdir(parents=True)
    segments = [
        {"start": index, "end": index + 1, "text": f"segment {index}"}
        for index in range(65)
    ]
    (transcript_dir / "sample.json").write_text(json.dumps({
        "file_path": str(tmp_path / "storage" / "audio" / "sample.wav"),
        "segments": segments,
    }), encoding="utf-8")

    class DummyEmbeddings:
        calls = []

        def __init__(self, *args, **kwargs):
            pass

        def embed_documents(self, texts):
            self.calls.append(list(texts))
            return [[0.1] * 1536 for _ in texts]

    class DummyQdrant:
        exists = False
        points = []

        def __init__(self, *args, **kwargs):
            pass

        def collection_exists(self, name):
            return type(self).exists

        def create_collection(self, **kwargs):
            type(self).exists = True

        def delete_collection(self, name):
            type(self).exists = False

        def upsert(self, **kwargs):
            type(self).points = kwargs["points"]

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(main, "ROOT", tmp_path)
    monkeypatch.setattr(main, "OpenAIEmbeddings", DummyEmbeddings)
    monkeypatch.setattr(main, "QdrantClient", DummyQdrant)
    monkeypatch.setattr(main, "ChatOpenAI", lambda **kwargs: object())
    monkeypatch.setattr(main, "create_agent", lambda *args, **kwargs: object())

    main.create_app()
    assert [len(batch) for batch in DummyEmbeddings.calls] == [64, 1]
    assert len(DummyQdrant.points) == 65

    main.create_app()
    assert [len(batch) for batch in DummyEmbeddings.calls] == [64, 1]
