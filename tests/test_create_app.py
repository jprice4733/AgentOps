from unittest.mock import Mock, AsyncMock
from io import BytesIO

from fastapi.testclient import TestClient
from pydub import AudioSegment
import main


def configure(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("S3_AUTO_PROCESS", "false")
    monkeypatch.setattr(main, "ROOT", tmp_path)
    store = Mock()
    store.bucket = "bucket"
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


def test_date_clarification_creates_clip_from_verified_quote(monkeypatch, tmp_path):
    from langchain_core.messages import AIMessage
    store, _, _ = configure(monkeypatch, tmp_path)
    store.transcript.return_value["segments"] = [{"start": 0, "end": 1,
        "text": "This call is coming from Doug's cell."}]
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


def test_missing_transcripts_returns_actionable_message(monkeypatch, tmp_path):
    store, embeddings, captured = configure(monkeypatch, tmp_path)
    store.transcript.return_value = None
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
    store, embeddings, captured = configure(monkeypatch, tmp_path)
    store.audio_objects.return_value = [{"Key": "calls/a.wav"}, {"Key": "calls/b.wav"}]
    store.transcript.side_effect = [
        {"file_path": "s3://bucket/calls/a.wav", "segments": [
            {"start": 2, "end": 5, "text": "Please contact Doug Miers tomorrow."}]}, None]
    main.create_app()
    tools = {tool.name: tool for tool in captured["tools"]}
    result = json.loads(tools["search_transcript_segments"].invoke({"topic_query": "doug miers"}))
    assert result["matches"][0]["start_time"] == 2
    assert result["match_type"] == "literal"
    assert result["coverage"]["missing_transcripts"] == ["s3://bucket/calls/b.wav"]
    embeddings.embed_query.assert_not_called()


def test_startup_syncs_before_loading_transcripts(monkeypatch, tmp_path):
    store, _, _ = configure(monkeypatch, tmp_path)
    monkeypatch.setenv("S3_AUTO_PROCESS", "true")
    events = []
    monkeypatch.setattr(main, "sync_outputs", lambda source: events.append("sync") or {})
    payload = store.transcript.return_value
    store.transcript.side_effect = lambda item: events.append("load") or payload
    main.create_app()
    assert events == ["sync", "load"]


def test_name_search_labels_partial_mentions_without_claiming_identity(monkeypatch, tmp_path):
    import json
    store, _, captured = configure(monkeypatch, tmp_path)
    store.transcript.return_value["segments"] = [
        {"start": 0, "end": 2, "text": "Doug's cell called."},
        {"start": 2, "end": 4, "text": "Doug Miers called."},
        {"start": 4, "end": 6, "text": "Douglas called."},
    ]
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
