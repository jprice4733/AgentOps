from unittest.mock import Mock, AsyncMock
from io import BytesIO

from fastapi.testclient import TestClient
from pydub import AudioSegment
from qdrant_client import QdrantClient
import main
from wav_search_agent.catalog import Catalog
from wav_search_agent.vector_store import VectorStore


def add_call(catalog, key="calls/a.wav", segments=(("hello", 0, 1),), done=True):
    uri = f"s3://bucket/{key}"
    catalog.register([{"uri": uri, "key": key, "fingerprint": "f-" + key, "etag": "e",
                       "size": 1, "last_modified": "2026-01-01"}])
    if done:
        catalog.claim(10, 900, 5)
        catalog.complete(uri, "f-" + key, [
            {"idx": i, "start_time": float(start), "end_time": float(end), "text": text}
            for i, (text, start, end) in enumerate(segments)], 1.0)
    return uri


def configure(monkeypatch, tmp_path, segments=(("hello", 0, 1),), done=True):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CATALOG_PATH", str(tmp_path / "catalog.sqlite"))
    monkeypatch.setattr(main, "ROOT", tmp_path)
    catalog = Catalog(tmp_path / "catalog.sqlite")
    if segments is not None:
        add_call(catalog, segments=segments, done=done)
    store = Mock()
    store.bucket = "bucket"
    monkeypatch.setattr(main, "S3Store", lambda: store)
    vectors = VectorStore(QdrantClient(":memory:"))
    monkeypatch.setattr(main, "VectorStore", Mock(from_env=lambda: vectors))
    embeddings = Mock()
    monkeypatch.setattr(main, "OpenAIEmbeddings", lambda **kwargs: embeddings)
    monkeypatch.setattr(main, "ChatOpenAI", lambda **kwargs: Mock())
    captured = {"catalog": catalog, "vectors": vectors}
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
    store.audio_objects.assert_not_called()  # startup reads the catalog, not S3
    store.transcript.assert_not_called()
    embeddings.embed_documents.assert_not_called()
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
    assert all(path.name.startswith("catalog.sqlite") for path in tmp_path.iterdir())  # no local clips


def test_date_clarification_creates_clip_from_verified_quote(monkeypatch, tmp_path):
    from langchain_core.messages import AIMessage
    store, _, _ = configure(monkeypatch, tmp_path, segments=(("This call is coming from Doug's cell.", 0, 1),))
    wav = BytesIO()
    AudioSegment.silent(duration=2000).export(wav, format="wav")
    store.audio_stream.return_value = BytesIO(wav.getvalue())
    agent = Mock()
    agent.ainvoke = AsyncMock(return_value={"messages": [AIMessage(
        content="Call: s3://bucket/calls/a.wav. This call is coming from Doug's cell. Here is the clip:")]})
    monkeypatch.setattr(main, "create_agent", lambda *args, **kwargs: agent)
    client = TestClient(main.create_app())
    result = client.post("/api/chat", json={"message": "September 29", "history": [
        {"role": "user", "content": "Give me clips where Doug"},
        {"role": "assistant", "content": "Which date?"}]}).json()
    assert len(result["clips"]) == 1
    assert '<audio controls' in result["response"]
    store.save_clip.assert_called_once()


def test_empty_catalog_tells_user_to_run_worker(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path, segments=None)
    response = TestClient(main.create_app()).post("/api/chat", json={"message": "search"})
    assert "worker run --once" in response.json()["response"]


def test_missing_transcripts_returns_actionable_message(monkeypatch, tmp_path):
    store, embeddings, captured = configure(monkeypatch, tmp_path, done=False)
    main.create_app()
    tools = {tool.name: tool for tool in captured["tools"]}
    assert "no current transcript" in tools["read_call_transcript"].invoke({"file_path": "a.wav"})
    embeddings.embed_documents.assert_not_called()


def test_subject_tools_expose_only_selected_call(monkeypatch, tmp_path):
    store, _, captured = configure(monkeypatch, tmp_path)
    main.create_app()
    tools = {tool.name: tool for tool in captured["tools"]}
    assert "s3://bucket/calls/a.wav" in tools["list_calls"].invoke({})
    result = tools["read_call_transcript"].invoke({"file_path": "s3://bucket/calls/a.wav"})
    assert "hello" in result
    assert "Call not found" in tools["read_call_transcript"].invoke({"file_path": "other"})


def test_whole_call_clip_accepts_filename_without_timestamps(monkeypatch, tmp_path):
    store, _, captured = configure(monkeypatch, tmp_path)
    main.create_app()
    wav = BytesIO()
    AudioSegment.silent(duration=2000).export(wav, format="wav")
    store.audio_stream.return_value = BytesIO(wav.getvalue())
    tools = {tool.name: tool for tool in captured["tools"]}
    url = tools["extract_audio_clip"].invoke({"file_path": "a.wav"})
    assert url.startswith("/api/clips/")
    store.audio_stream.assert_called_once_with("s3://bucket/calls/a.wav")
    saved = store.save_clip.call_args.args[1]
    assert len(AudioSegment.from_file(BytesIO(saved), format="wav")) == 2000
    import json
    payload = json.loads(tools["read_call_transcript"].invoke({"file_path": "a.wav"}))
    assert payload["segments"][0]["end"] == 1


def test_followup_passes_history_without_sharing_between_requests(monkeypatch, tmp_path):
    configure(monkeypatch, tmp_path)
    agent = Mock()
    agent.ainvoke = AsyncMock(return_value={"messages": [Mock(content="Done")]})
    monkeypatch.setattr(main, "create_agent", lambda *args, **kwargs: agent)
    client = TestClient(main.create_app())
    history = [{"role": "user", "content": "Play a.wav"},
               {"role": "assistant", "content": "Playing a.wav"}]
    client.post("/api/chat", json={"message": "where discuss september 29", "history": history})
    assert agent.ainvoke.call_args.args[0]["messages"] == history + [
        {"role": "user", "content": "where discuss september 29"}]
    client.post("/api/chat", json={"message": "hello"})
    assert len(agent.ainvoke.call_args.args[0]["messages"]) == 1


def test_name_search_prioritizes_literal_match_and_reports_missing_calls(monkeypatch, tmp_path):
    import json
    store, embeddings, captured = configure(
        monkeypatch, tmp_path, segments=(("Please contact Doug Miers tomorrow.", 2, 5),))
    add_call(captured["catalog"], "calls/b.wav", done=False)
    main.create_app()
    tools = {tool.name: tool for tool in captured["tools"]}
    result = json.loads(tools["search_transcript_segments"].invoke({"topic_query": "doug miers"}))
    assert result["matches"][0]["start_time"] == 2
    assert result["match_type"] == "literal"
    assert result["coverage"]["missing_transcripts"] == ["s3://bucket/calls/b.wav"]
    assert result["coverage"]["missing_count"] == 1
    embeddings.embed_query.assert_not_called()


def test_semantic_search_uses_persisted_vectors(monkeypatch, tmp_path):
    import json
    _, embeddings, captured = configure(monkeypatch, tmp_path)
    segment = {"idx": 0, "start_time": 0.0, "end_time": 1.0, "text": "hello"}
    captured["vectors"].replace_call("s3://bucket/calls/a.wav", "f-calls/a.wav", [segment], [[0.1] * 1536])
    embeddings.embed_query.return_value = [0.1] * 1536
    main.create_app()
    tools = {tool.name: tool for tool in captured["tools"]}
    result = json.loads(tools["search_transcript_segments"].invoke({"topic_query": "greeting"}))
    assert result["match_type"] == "semantic_candidates"
    assert result["matches"][0]["file_path"] == "s3://bucket/calls/a.wav"


def test_startup_does_not_touch_s3_or_reembed(monkeypatch, tmp_path):
    store, embeddings, _ = configure(monkeypatch, tmp_path)
    main.create_app()
    assert store.method_calls == []
    embeddings.embed_documents.assert_not_called()


def test_list_calls_is_paged_and_filterable(monkeypatch, tmp_path):
    import json
    _, _, captured = configure(monkeypatch, tmp_path)
    for index in range(5):
        add_call(captured["catalog"], f"calls/extra{index}.wav", done=False)
    main.create_app()
    tools = {tool.name: tool for tool in captured["tools"]}
    page = json.loads(tools["list_calls"].invoke({"limit": 2}))
    assert page["total"] == 6 and len(page["calls"]) == 2
    filtered = json.loads(tools["list_calls"].invoke({"contains": "extra3"}))
    assert [c["file_path"] for c in filtered["calls"]] == ["s3://bucket/calls/extra3.wav"]
    assert filtered["calls"][0]["transcribed"] is False


def test_name_search_labels_partial_mentions_without_claiming_identity(monkeypatch, tmp_path):
    import json
    store, _, captured = configure(monkeypatch, tmp_path, segments=(
        ("Doug's cell called.", 0, 2), ("Doug Miers called.", 2, 4), ("Douglas called.", 4, 6)))
    main.create_app()
    tools = {tool.name: tool for tool in captured["tools"]}
    result = json.loads(tools["search_name_mentions"].invoke({"name": "Doug Miers"}))
    assert [item["match_type"] for item in result["matches"]] == ["exact_name", "first_name_only"]
    assert result["matches"][1]["text"] == "Doug's cell called."
    assert "not confirmed" in result["matches"][1]["caveat"]


def test_clip_result_survives_missing_model_audio_markup(monkeypatch, tmp_path):
    from langchain_core.messages import AIMessage, ToolMessage
    configure(monkeypatch, tmp_path)
    url = "/api/clips/" + "a" * 64 + ".wav"
    agent = Mock()
    agent.ainvoke = AsyncMock(return_value={"messages": [
        ToolMessage(content=url, name="extract_audio_clip", tool_call_id="1"),
        ToolMessage(content=url, name="extract_audio_clip", tool_call_id="2"),
        ToolMessage(content="/api/clips/" + "b" * 64 + ".wav",
                    name="extract_audio_clip", tool_call_id="3", status="error"),
        AIMessage(content="Here is the audio clip:"),
    ]})
    monkeypatch.setattr(main, "create_agent", lambda *args, **kwargs: agent)
    result = TestClient(main.create_app()).post("/api/chat", json={"message": "Give me clips"}).json()
    assert result["clips"] == [url]
    assert result["response"].startswith("Here is the audio clip:")
    assert '<audio controls' in result["response"]


def test_clip_request_extracts_name_match_when_agent_only_describes_it(monkeypatch, tmp_path):
    import json
    from langchain_core.messages import AIMessage, ToolMessage
    store, _, _ = configure(monkeypatch, tmp_path)
    wav = BytesIO()
    AudioSegment.silent(duration=2000).export(wav, format="wav")
    store.audio_stream.return_value = BytesIO(wav.getvalue())
    agent = Mock()
    agent.ainvoke = AsyncMock(return_value={"messages": [
        ToolMessage(content=json.dumps({"matches": [{
            "file_path": "s3://bucket/calls/a.wav", "start_time": 0, "end_time": 1,
            "text": "Doug's cell", "match_type": "exact_name"}]}),
            name="search_name_mentions", tool_call_id="1"),
        AIMessage(content="Here is the audio clip:"),
    ]})
    monkeypatch.setattr(main, "create_agent", lambda *args, **kwargs: agent)
    result = TestClient(main.create_app()).post("/api/chat", json={"message": "Give me clips where doug"}).json()
    assert len(result["clips"]) == 1
    assert '<audio controls' in result["response"]
    store.save_clip.assert_called_once()


def test_search_results_include_labeled_clips_without_asking(monkeypatch, tmp_path):
    import json
    from langchain_core.messages import AIMessage, ToolMessage
    store, _, _ = configure(monkeypatch, tmp_path)
    wav = BytesIO()
    AudioSegment.silent(duration=2000).export(wav, format="wav")
    store.audio_stream.side_effect = lambda uri: BytesIO(wav.getvalue())
    agent = Mock()
    agent.ainvoke = AsyncMock(return_value={"messages": [
        ToolMessage(content=json.dumps({"matches": [{
            "file_path": "s3://bucket/calls/a.wav", "start_time": 1, "end_time": 2,
            "text": "Doug Miers", "match_type": "exact_name"}]}),
            name="search_name_mentions", tool_call_id="1"),
        AIMessage(content="Found one call."),
    ]})
    monkeypatch.setattr(main, "create_agent", lambda *args, **kwargs: agent)
    client = TestClient(main.create_app())
    result = client.post("/api/chat", json={"message": "give me calls that mention doug miers"}).json()
    assert len(result["clips"]) == 1
    assert "a.wav at 0:01" in result["response"] and "<audio controls" in result["response"]
    opted_out = client.post("/api/chat", json={"message": "calls that mention doug miers, no audio"}).json()
    assert opted_out["clips"] == []
