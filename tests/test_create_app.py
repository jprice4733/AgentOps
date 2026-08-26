from fastapi.testclient import TestClient


def test_create_app_handles_embedding_failure(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    import main

    class DummyEmbeddings:
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
