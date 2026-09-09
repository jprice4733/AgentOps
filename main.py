import json
import os
import sys
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel
from pydub import AudioSegment
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


def create_app():
    load_dotenv()

    AUDIO_DIR = ROOT / "storage" / "audio"
    JSON_DIR = ROOT / "storage" / "json"
    CLIPS_DIR = ROOT / "static" / "clips"
    QDRANT_DIR = ROOT / "storage" / "qdrant"
    COLLECTION_NAME = "wav_search_agent_segments"
    EMBEDDING_CACHE_FILE = JSON_DIR / "embedding_cache.json"
    INDEX_STATE_FILE = QDRANT_DIR / "index_state.json"
    clip_context_seconds = max(0.0, float(os.getenv("CLIP_CONTEXT_SECONDS", "15")))

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    JSON_DIR.mkdir(parents=True, exist_ok=True)
    CLIPS_DIR.mkdir(parents=True, exist_ok=True)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY not found. AI features will be disabled until a valid key is added to .env.")
    os.environ["OPENAI_API_KEY"] = api_key or ""

    QDRANT_DIR.mkdir(parents=True, exist_ok=True)

    qdrant_client = QdrantClient(path=str(QDRANT_DIR))
    embeddings = OpenAIEmbeddings(api_key=api_key) if api_key else None

    try:
        if not qdrant_client.collection_exists(COLLECTION_NAME):
            qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )
    except Exception as exc:
        print(f"Qdrant collection setup failed during startup: {exc}")

    def safe_embed_query(text: str):
        if embeddings is None:
            return None
        try:
            return embeddings.embed_query(text)
        except Exception as exc:  # pragma: no cover - depends on external API connectivity
            print(f"OpenAI embedding request failed: {exc}")
            return None

    @tool
    def search_transcript_segments(topic_query: str) -> str:
        """Search transcript segments by semantic similarity."""
        query_vector = safe_embed_query(topic_query)
        if query_vector is None:
            return "OpenAI embeddings are unavailable right now. Check your API key and network access."
        search_results = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=5,
        ).points

        if not search_results:
            return "No matching transcript segments found."

        results = []
        for hit in search_results:
            results.append({
                "text": hit.payload["text"],
                "start_time": hit.payload["start_time"],
                "end_time": hit.payload["end_time"],
                "file_path": hit.payload["file_path"],
            })
        return json.dumps(results)

    @tool
    def extract_audio_clip(file_path: str, start_time: float, end_time: float) -> str:
        """Cut a transcript segment with surrounding context and return the clip URL."""
        clip_key = f"{Path(file_path).resolve()}|{start_time:.3f}|{end_time:.3f}|{clip_context_seconds:.3f}"
        output_filename = f"clip_{sha256(clip_key.encode()).hexdigest()[:16]}.wav"
        output_path = CLIPS_DIR / output_filename

        if output_path.exists():
            return f"/static/clips/{output_filename}"

        audio = AudioSegment.from_file(file_path)
        start_ms = max(0, int((start_time - clip_context_seconds) * 1000))
        end_ms = min(len(audio), int((end_time + clip_context_seconds) * 1000))
        clipped = audio[start_ms:end_ms]
        clipped.export(output_path, format="wav")
        return f"/static/clips/{output_filename}"

    def load_json_transcripts(batch_size: int = 64) -> list[dict]:
        """Index transcripts only when their source files have changed."""
        transcript_files = sorted(JSON_DIR.glob("*.json"))
        source_state = [
            (path.name, path.stat().st_size, path.stat().st_mtime_ns)
            for path in transcript_files
            if path != EMBEDDING_CACHE_FILE
        ]
        fingerprint = sha256(json.dumps(source_state).encode()).hexdigest()

        try:
            cached_state = json.loads(INDEX_STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached_state = {}

        collection_exists = qdrant_client.collection_exists(COLLECTION_NAME)
        if collection_exists and cached_state.get("fingerprint") == fingerprint:
            print("Transcript index is current; skipping re-indexing.")
            return []

        try:
            embedding_cache = json.loads(EMBEDDING_CACHE_FILE.read_text(encoding="utf-8"))
            if not isinstance(embedding_cache, dict):
                embedding_cache = {}
        except (OSError, json.JSONDecodeError):
            embedding_cache = {}

        transcripts, segments = [], []
        for transcript_path in transcript_files:
            if transcript_path == EMBEDDING_CACHE_FILE:
                continue
            try:
                payload = json.loads(transcript_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                print(f"Skipping invalid JSON file {transcript_path}: {exc}")
                continue
            if not isinstance(payload, dict):
                print(f"Skipping non-object JSON file {transcript_path}")
                continue

            record = {"file_path": payload.get("file_path") or str(AUDIO_DIR / transcript_path.stem),
                      "text": payload.get("text", ""), "segments": []}
            for item in payload.get("segments") or []:
                if not isinstance(item, dict) or not str(item.get("text", "")).strip():
                    continue
                segment = {"file_path": record["file_path"], "start_time": float(item.get("start", 0) or 0),
                           "end_time": float(item.get("end", 0) or 0), "text": str(item["text"]).strip()}
                record["segments"].append(segment)
                segments.append(segment)
            transcripts.append(record)

        if embeddings is None:
            print("No transcript segments were indexed because OpenAI embeddings are unavailable.")
            return transcripts

        missing_texts = list({segment["text"] for segment in segments if segment["text"] not in embedding_cache})
        try:
            for offset in range(0, len(missing_texts), max(1, batch_size)):
                texts = missing_texts[offset:offset + max(1, batch_size)]
                vectors = embeddings.embed_documents(texts)
                embedding_cache.update(zip(texts, vectors))
        except Exception as exc:
            print(f"Skipping Qdrant indexing because embeddings failed: {exc}")
            return transcripts

        points = [
            PointStruct(
                id=int(sha256(f"{item['file_path']}|{item['start_time']}|{item['end_time']}|{item['text']}".encode()).hexdigest()[:15], 16),
                vector=embedding_cache[item["text"]],
                payload=item,
            )
            for item in segments
        ]

        try:
            if collection_exists:
                qdrant_client.delete_collection(COLLECTION_NAME)
            qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
            )
            if points:
                qdrant_client.upsert(collection_name=COLLECTION_NAME, points=points)
            EMBEDDING_CACHE_FILE.write_text(json.dumps(embedding_cache), encoding="utf-8")
            INDEX_STATE_FILE.write_text(json.dumps({"fingerprint": fingerprint}), encoding="utf-8")
            print(f"Indexed {len(points)} segment(s) from {len(transcripts)} JSON transcript(s).")
        except Exception as exc:
            print(f"Skipping Qdrant indexing due to startup error: {exc}")
        return transcripts

    load_json_transcripts()

    app = FastAPI(title="WAV Chat Agent")
    app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")

    llm = ChatOpenAI(model="gpt-4o", temperature=0, api_key=api_key) if api_key else None
    agent_executor = None
    if llm is not None:
        agent_executor = create_agent(
            llm,
            [search_transcript_segments, extract_audio_clip],
            system_prompt=(
                "You are an audio intelligence agent. "
                "Search transcript segments and use the exact timestamps with extract_audio_clip. "
                "Return the matching transcript text and an HTML5 audio tag."
            ),
        )

    class ChatRequest(BaseModel):
        message: str

    class ChatResponse(BaseModel):
        response: str

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat_endpoint(request: ChatRequest):
        if llm is None or agent_executor is None:
            return ChatResponse(response="OpenAI API key is missing. Add OPENAI_API_KEY to your .env file to enable chat responses.")

        try:
            result = await agent_executor.ainvoke({
                "messages": [{"role": "user", "content": request.message}]
            })
            final_message = result["messages"][-1]
            response_text = final_message.content
            if not isinstance(response_text, str):
                response_text = str(response_text)
            return ChatResponse(response=response_text)
        except Exception as error:
            return ChatResponse(response=f"Chat request failed: {error}")

    @app.get("/", response_class=HTMLResponse)
    async def get_chat_ui():
        return """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>Audio File Search Agent</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 820px; margin: 40px auto; padding: 0 20px; background: #f7f9fc; }
                .chat-box { background: white; border: 1px solid #dfe3ea; border-radius: 10px; padding: 20px; min-height: 420px; max-height: 520px; overflow-y: auto; box-shadow: 0 2px 10px rgba(0,0,0,0.04); }
                .msg { margin-bottom: 14px; padding: 12px 14px; border-radius: 8px; line-height: 1.5; }
                .user { background: #e8f1ff; color: #123; margin-left: 20%; }
                .agent { background: #f3f4f6; color: #1b1f23; margin-right: 20%; }
                input { width: calc(100% - 90px); padding: 12px; border: 1px solid #cfd7df; border-radius: 8px; }
                button { padding: 12px 18px; border: none; border-radius: 8px; background: #0b57d0; color: white; cursor: pointer; }
                audio { display: block; width: 100%; max-width: 420px; margin-top: 8px; }
            </style>
        </head>
        <body>
            <h2>WAV Search Agent</h2>
            <div class="chat-box" id="chatBox">
                <div class="msg agent">Hello! Ask me to search the transcripts from your audio files.</div>
            </div>
            <div style="margin-top: 16px; display: flex; gap: 10px;">
                <input id="userInput" placeholder="Ask about the audio transcripts" onkeydown="if(event.key === 'Enter') sendMessage()">
                <button onclick="sendMessage()">Send</button>
            </div>
            <script>
                async function sendMessage() {
                    const input = document.getElementById('userInput');
                    const chatBox = document.getElementById('chatBox');
                    const text = input.value.trim();
                    if (!text) return;

                    chatBox.innerHTML += `<div class="msg user">${escapeHtml(text)}</div>`;
                    input.value = '';
                    chatBox.scrollTop = chatBox.scrollHeight;

                    const response = await fetch('/api/chat', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ message: text })
                    });
                    const data = await response.json();
                    chatBox.innerHTML += `<div class="msg agent">${data.response}</div>`;
                    chatBox.scrollTop = chatBox.scrollHeight;
                }

                function escapeHtml(str) {
                    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                }
            </script>
        </body>
        </html>
        """

    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
