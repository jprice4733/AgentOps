# WAV Search Agent

A small reusable Python project for transcribing audio files, creating and loading transcript JSON files, indexing transcript segments, and serving a FastAPI chat agent over them.

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

1. From the project root, create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
3. Install FFmpeg, which pydub uses when extracting audio clips. On Windows,
   run this in PowerShell and then open a new terminal:
   ```powershell
   winget install --id Gyan.FFmpeg.Essentials --exact
   ```
   On macOS, use `brew install ffmpeg`; on Debian/Ubuntu, use
   `sudo apt install ffmpeg`.
4. Copy `.env.example` to `.env` and set your `OPENAI_API_KEY`.
5. Start the app:
   ```bash
   python main.py
   ```

By default, extracted clips include 15 seconds of audio before and after the
matching transcript segment. Set `CLIP_CONTEXT_SECONDS` in `.env` to change
that amount, for example `CLIP_CONTEXT_SECONDS=30` for 30 seconds on each
side. Clip boundaries are automatically limited to the source audio.

> On macOS / zsh, use `python3` for the environment creation step if `python` is not on your PATH.
> If the venv is already created, you can activate it with:
> ```bash
> source .venv/bin/activate
> ```

## Data flow

- Place audio files in `storage/audio/`
- Generate one JSON transcript per audio file in `storage/json/`
- Run the app and ask questions through the chat UI at `http://localhost:8000/`

## Notes

- The project uses the existing transcript JSONs in `storage/json` as the canonical source.
- Existing JSON output is reused to avoid re-transcribing files that are already processed.
