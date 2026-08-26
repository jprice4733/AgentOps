import os


def test_create_app_handles_embedding_failure(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    import main

    class DummyEmbeddings:
        def embed_query(self, text):
            raise RuntimeError("Connection error")

    monkeypatch.setattr(main, "OpenAIEmbeddings", DummyEmbeddings)

    app = main.create_app()
    assert app is not None
    assert app.title == "WAV Chat Agent"
