import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel
from pydub import AudioSegment
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from .config import BASE_DIR, CLIPS_DIR, STATIC_DIR, ensure_directories, get_openai_api_key
from .transcripts import load_json_transcripts


@tool
def search_transcript_segments(topic_query: str) -> str:
    """Search transcript segments by semantic similarity."""
    query_vector = embeddings.embed_query(topic_query)
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
    return str(results)


@tool
def extract_audio_clip(file_path: str, start_time: float, end_time: float) -> str:
    """Cut an audio file between start_time and end_time and return the clip URL."""
    start_ms = int(start_time * 1000)
    end_ms = int(end_time * 1000)
    output_filename = f"clip_{os.path.splitext(os.path.basename(file_path))[0]}_{start_time:.1f}_{end_time:.1f}.wav"
    output_path = CLIPS_DIR / output_filename

    audio = AudioSegment.from_file(file_path)
    clipped = audio[start_ms:end_ms]
    clipped.export(output_path, format="wav")
    return f"/static/clips/{output_filename}"


def create_app():
    load_dotenv()
    ensure_directories()
    os.environ["OPENAI_API_KEY"] = get_openai_api_key()

    app = FastAPI(title="WAV Search Agent")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # keep the same global references the tools need
    global embeddings, qdrant_client, COLLECTION_NAME
    embeddings = OpenAIEmbeddings()
    qdrant_client = QdrantClient(":memory:")
    COLLECTION_NAME = "wav_search_agent_segments"

    if qdrant_client.collection_exists(COLLECTION_NAME):
        qdrant_client.delete_collection(COLLECTION_NAME)

    qdrant_client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
    )

    load_json_transcripts(embeddings, qdrant_client, COLLECTION_NAME)

    llm = ChatOpenAI(model="gpt-4o", temperature=0)
    tools = [search_transcript_segments, extract_audio_clip]
    agent_executor = create_agent(
        llm,
        tools,
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

    @app.get("/")
    async def get_chat_ui():
        return """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>WAV Search Agent</title>
            <style>
                body { font-family: sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; }
                .chat-box { border: 1px solid #ddd; border-radius: 8px; padding: 20px; max-height: 500px; overflow-y: auto; }
                .msg { margin-bottom: 15px; }
                .user { color: #0b57d0; }
                .agent { color: #111; }
                input { width: calc(100% - 90px); padding: 10px; }
                button { padding: 10px 16px; }
            </style>
        </head>
        <body>
            <h2>WAV Search Agent</h2>
            <div class="chat-box" id="chatBox">
                <div class="msg agent">Ask a question about the audio transcript.</div>
            </div>
            <div style="margin-top: 15px;">
                <input id="userInput" placeholder="Ask about the audio..." onkeydown="if(event.key==='Enter') sendMessage()">
                <button onclick="sendMessage()">Send</button>
            </div>
            <script>
                async function sendMessage() {
                    const text = document.getElementById('userInput').value.trim();
                    if (!text) return;
                    const chatBox = document.getElementById('chatBox');
                    chatBox.innerHTML += '<div class="msg user">' + text + '</div>';
                    document.getElementById('userInput').value = '';
                    const response = await fetch('/api/chat', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ message: text })
                    });
                    const data = await response.json();
                    chatBox.innerHTML += '<div class="msg agent">' + data.response + '</div>';
                    chatBox.scrollTop = chatBox.scrollHeight;
                }
            </script>
        </body>
        </html>
        """

    return app
