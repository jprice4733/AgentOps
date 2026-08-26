# WAV Search Agent

A small reusable Python project for loading WAV transcript JSON files, indexing transcript segments, and serving a FastAPI chat agent over them.

## Features

- Reads transcript JSON files from `storage/json`
- Indexes segment text into a local Qdrant in-memory collection
- Searches transcript segments semantically
- Extracts audio clips from matched transcript segments
- Serves a minimal chat UI with FastAPI

## Project structure

- `main.py` - app entry point
- `src/wav_search_agent/` - reusable Python package
- `storage/audio/` - audio input directory
- `storage/json/` - transcript JSON output directory
- `static/clips/` - extracted audio clips

## Setup

1. Create a virtual environment.
2. Install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and set your `OPENAI_API_KEY`.
4. Start the app:
   ```bash
   python main.py
   ```

## Data flow

- Place audio files in `storage/audio/`
- Generate one JSON transcript per audio file in `storage/json/`
- Run the app and ask questions through the chat UI at `http://localhost:8000/`

## Notes

- The project uses the existing transcript JSONs in `storage/json` as the canonical source.
- Existing JSON output is reused to avoid re-transcribing files that are already processed.
