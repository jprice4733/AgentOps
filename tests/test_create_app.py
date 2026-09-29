from unittest.mock import Mock
from io import BytesIO

from fastapi.testclient import TestClient
from pydub import AudioSegment
import main


def configure(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(main, "ROOT", tmp_path)
    store = Mock()
    store.audio_objects.return_value = [{"Key": "calls/a.wav"}]
    store.transcript.return_value = {
        "file_path": "s3://bucket/calls/a.wav",
        "segments": [{"start": 0, "end": 1, "text": "hello"}],
    }
    monkeypatch.setattr(main, "S3Store", lambda: store)
    embeddings = Mock()
    embeddings.embed_documents.return_value = [[0.1] * 1536]
    monkeypatch.setattr(main, "OpenAIEmbeddings", lambda **kwargs: embeddings)
    monkeypatch.setattr(main, "ChatOpenAI", lambda **kwargs: Mock())
    captured = {}
    def agent(llm, tools, **kwargs):
        captured["tools"] = tools
        return Mock()
    monkeypatch.setattr(main, "create_agent", agent)
    return store, embeddings, captured


def test_s3_index_and_persisted_clip(monkeypatch, tmp_path):
    store, embeddings, captured = configure(monkeypatch, tmp_path)
    app = main.create_app()
    client = TestClient(app)
    assert client.get("/").status_code == 200
    embeddings.embed_documents.assert_called_once_with(["hello"])
    wav = BytesIO()
    AudioSegment.silent(duration=2000).export(wav, format="wav")
    store.audio_stream.return_value = BytesIO(wav.getvalue())
    url = captured["tools"][1].invoke({"file_path": "s3://bucket/calls/a.wav", "start_time": 0, "end_time": 1})
    store.save_clip.assert_called_once()
    assert store.save_clip.call_args.args[1].startswith(b"RIFF")
    store.clip_url.return_value = "https://bucket.s3.amazonaws.com/clip?signature=test"
    response = client.get(url, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == store.clip_url.return_value
    store.clip_url.side_effect = ValueError("Invalid clip name")
    assert client.get("/api/clips/unknown.wav").status_code == 404
    assert not list(tmp_path.iterdir())


def test_s3_failure_has_no_local_fallback(monkeypatch, tmp_path):
    store, embeddings, _ = configure(monkeypatch, tmp_path)
    local = tmp_path / "storage" / "json"
    local.mkdir(parents=True)
    (local / "old.json").write_text('{"segments": [{"text": "local"}]}')
    store.audio_objects.side_effect = RuntimeError("No AWS credentials")
    app = main.create_app()
    embeddings.embed_documents.assert_not_called()
    response = TestClient(app).post("/api/chat", json={"message": "search"})
    assert "No AWS credentials" in response.json()["response"]
