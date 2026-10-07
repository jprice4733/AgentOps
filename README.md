# Audio File Search Agent

A FastAPI chat app that transcribes recordings from S3, searches call transcripts,
and creates playable audio clips. Source audio, transcript JSON, and generated
clips reside in S3. Local recordings and transcript files are ignored.

## Features

- Automatically creates missing transcripts and full-recording WAV clips at startup.
- Reuses existing outputs for unchanged recordings and retries missing outputs.
- Searches transcripts by topic, exact phrase, or person name.
- Offers first-name-only mentions as possible matches, with identity explicitly unconfirmed.
- Reads call transcripts with timestamps for summaries and excerpt selection.
- Remembers the selected call through the current browser conversation.
- Stores clips in S3 and plays them through signed URLs.
- Provides a responsive chat UI with suggested prompts, loading feedback, and a new-conversation action.
- Returns clip URLs separately from answer text and provides an audio player plus an "Open audio clip" link.
- Reports incomplete transcript coverage rather than implying all calls were searched.

## Setup

Run commands from the project root. On Windows, use the project interpreter directly
so the app uses the installed dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Install FFmpeg for audio decoding. On Windows:

```powershell
winget install --id Gyan.FFmpeg.Essentials --exact
```

Open a new terminal after installation. On macOS use `brew install ffmpeg`; on
Debian/Ubuntu use `sudo apt install ffmpeg`.

If `.env` does not already exist, copy `.env.example` to `.env` and configure:

```dotenv
OPENAI_API_KEY=your_openai_api_key
S3_AUDIO_URI=s3://denverit-demo-bucket/voip-telecom-system/
S3_JSON_PREFIX=voip-telecom-system/json/
S3_CLIPS_PREFIX=voip-telecom-system/clips/
CLIP_CONTEXT_SECONDS=15
AWS_DEFAULT_REGION=your_bucket_region
```

Use an existing AWS profile:

```dotenv
AWS_PROFILE=your_profile_name
```

For SSO profiles, sign in with `aws sso login --profile YOUR_PROFILE`. Alternatively,
configure credentials locally in `.env`:

```dotenv
AWS_ACCESS_KEY_ID=your_access_key_id
AWS_SECRET_ACCESS_KEY=your_secret_access_key
# Required only when using temporary credentials:
AWS_SESSION_TOKEN=your_session_token
```

Choose the credential method appropriate to your AWS setup. Keep secrets out of
source control; `.env` is ignored by Git.

## Start the app

```powershell
.\.venv\Scripts\python.exe main.py
```

Open **http://localhost:8000/** or **http://127.0.0.1:8000/**. The server listens
on `0.0.0.0`, but that address is not the browser destination. Leave the terminal
running. To restart, press Ctrl+C and run the command again.
After UI or backend updates, restart the app and hard-refresh the browser with
**Ctrl+F5** to load the latest version.

In VS Code, use **Python: Select Interpreter** and select
`.venv\Scripts\python.exe` so the Run button uses the project environment.

## S3 storage and processing

| Content | Location |
| --- | --- |
| Source recordings | `s3://denverit-demo-bucket/voip-telecom-system/` |
| Transcript JSON | `s3://denverit-demo-bucket/voip-telecom-system/json/` |
| WAV clips | `s3://denverit-demo-bucket/voip-telecom-system/clips/` |

Output prefixes are relative to the bucket, not to the source audio folder.
The scanner excludes both output folders from source recordings. Supported source
extensions are `.wav`, `.mp3`, `.m4a`, `.mp4`, `.mpeg`, `.mpga`, and `.webm`.

Recordings are ingested by the separate worker (see "Ingestion worker" below), not at
web app startup. The worker lists source recordings, transcribes any lacking a current
transcript (saving timestamped JSON to the configured JSON prefix), embeds the segments,
and records them in the catalog and Qdrant. Changed source metadata results in new
transcript filenames; older outputs are retained. Individual failures are retried with
backoff while other recordings continue. Ingestion sends audio to OpenAI and incurs API
usage. Full-recording WAV clips are optional (`WORKER_CREATE_CLIPS`).

Audio is processed in memory with no local media storage; the catalog and vector index are persisted (see `CATALOG_PATH`, `QDRANT_URL`).
Large recordings require sufficient memory and must fit the transcription service's
upload limits; automatic splitting is not implemented. FFmpeg may use temporary
processing files. Existing local files are not deleted or uploaded.

## Manual commands

List up to ten source recordings:

```powershell
.\.venv\Scripts\python.exe s3_audio.py --limit 10
```

Create all missing transcripts and full-recording clips:

```powershell
.\.venv\Scripts\python.exe transcribe_audio.py
```

Both commands accept `--profile YOUR_PROFILE`, `--uri s3://bucket/prefix/`, and
`--limit N`. The limit counts source recordings checked, including recordings
whose outputs already exist. The processing command exits with a failure status
if any output failed. This legacy script only writes S3 outputs; use the ingestion
worker to update the search index.

## Chat examples

- "Which calls are available?"
- "What was call 20260929_153431_I_3036413833_103.wav about?"
- "Play an audio clip from call 20260929_153431_I_3036413833_103.wav."
- "Give me clips where Joe Smith is mentioned."
- After selecting a call: "Play the part where they discuss September 29."

If the app asks for a date after a clip request, a short reply such as
"September 29" retains the recent clip-request context. Continue in the same conversation while clarifying. Select it from **Past chats**
to resume later; **New conversation** starts a separate chat.

Use **Enter** to send and **Shift+Enter** for a new line. Suggested prompts help
list calls, start a name search, or select a call to summarize.

A named playback request without a topic or timestamps defaults to the full call.
Requested excerpts include 15 seconds of surrounding context by default, controlled
by `CLIP_CONTEXT_SECONDS` and limited to the recording boundaries. Short recordings
can therefore produce clips containing the entire call.

Name searches distinguish exact full-name matches from first-name-only candidates.
For example, "Doug's cell" can be offered as a possible match for "Doug Miers," but
it does not confirm the surname or identity. The app does not guarantee phonetic
or alternate-spelling matching. Missing transcripts are excluded from search and
reported in coverage notices.

Completed conversations are saved in browser local storage and listed in the
**Past chats** sidebar, newest first. Select a chat to reopen its messages and audio
players, or use its delete button to remove the saved conversation. The active chat
is restored after a refresh. Only the most recent 20 messages from the selected
chat are sent with each request. Chats are specific to this browser and site address
(`localhost` and `127.0.0.1` have separate storage); they are not synchronized to S3
or other devices. Clearing browser storage removes saved chats. If browser storage
is unavailable or full, a notice appears and changes remain only in memory. Deleting
a chat does not delete its audio files from S3. Generated clips remain
in S3; the playback endpoint creates a fresh signed URL with a requested one-hour
lifetime, subject to the signing credentials remaining valid.

## Clip delivery

The chat API returns `response` text and a `clips` list of application playback
URLs, such as `/api/clips/<hash>.wav`. Successful extraction results populate this
list independently of the model's HTML. The server also appends audio markup for
compatibility, while the UI avoids duplicate players for the same URL.

If the agent describes a match but skips extraction, a fallback can create clips
from exact-name, possible first-name, or literal search matches. For short
clarification replies it also checks recent clip-request context. A quoted result
can be recovered only when its filename and text match a loaded transcript;
arbitrary semantic candidates are not automatically converted to clips. The
fallback processes up to ten candidates per request.

Each displayed player includes an **Open audio clip** link that opens playback in
a separate tab. Both the player and link use the app endpoint, which redirects to
a signed S3 URL. No public bucket access is required. A text statement such as
"Here is the clip" alone is not proof that audio was created.

## AWS permissions

The configured AWS identity needs:

- `s3:ListBucket` on `denverit-demo-bucket`.
- `s3:GetObject` for source audio and the JSON and clip prefixes, including checks
  for existing clip objects.
- `s3:PutObject` on `voip-telecom-system/json/*` and
  `voip-telecom-system/clips/*`.

Customer-managed KMS encryption may require additional key permissions. Objects
under former output prefixes are not migrated automatically.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `No module named dotenv` | Run with `.\.venv\Scripts\python.exe` and install `requirements.txt` in that environment. |
| `ERR_ADDRESS_INVALID` at `0.0.0.0` | Open `http://localhost:8000/`. |
| AWS credentials unavailable or expired | Configure `.env` or your AWS profile; refresh temporary credentials or SSO login. |
| Missing transcripts or incomplete search coverage | Run `python -m wav_search_agent.worker status` for failures, check credentials, permissions, and OpenAI access, then `retry-failed`. |
| A name is not found | Inspect coverage and transcript wording; a partial name is not a confirmed full-name match. |
| Clip generation or playback fails | Check FFmpeg, S3 read/write permissions, and valid AWS signing credentials. |
| Answer says "Here is the clip" but no player appears | Restart the app and press Ctrl+F5. Retry the request; check `/api/chat` in browser developer tools for a nonempty `clips` list. |
| Player appears but audio does not load | Try **Open audio clip**. Check the playback request and signed S3 response for access or credential errors. |
| A date-only reply loses context | Reopen the appropriate conversation from Past chats, or repeat the full request with the name and date. |
| Code changes do not appear | Restart the app and hard-refresh the browser with Ctrl+F5. |

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest tests -q
```

The test suite uses mocked external services. It covers missing-output processing,
S3 paths and error handling, clip generation, transcript coverage, name matching,
conversation history, structured clip delivery, omitted-extraction recovery, and
date clarification follow-ups. Passing these tests does not verify live AWS or OpenAI
credentials.

## Ingestion worker

For production volumes, run ingestion separately from the web app. The worker scans
S3, transcribes new or replaced recordings in parallel, embeds the segments, and
persists them to a SQLite catalog (job state and full-text search) and a Qdrant
collection. Rerunning is safe: unchanged recordings are skipped and point IDs are
deterministic, so retries never duplicate vectors.

```bash
python -m wav_search_agent.worker run --once        # process everything due, then exit
python -m wav_search_agent.worker run --interval 60 # keep scanning every 60 seconds
python -m wav_search_agent.worker status            # counts by state, plus failures
python -m wav_search_agent.worker retry-failed      # re-queue permanently failed calls
```

- Failed recordings retry with exponential backoff (1, 2, 4... minutes, capped at an
  hour) up to `WORKER_MAX_ATTEMPTS`, then show as `failed` in `status`.
- A job leased by a crashed worker is reclaimed automatically after its lease expires.
- Recordings deleted from S3 are removed from the catalog and Qdrant. An empty
  listing never deletes anything.
- Set `QDRANT_URL` to share one Qdrant server between the worker and web app. Local
  path mode holds a file lock, so only one process can open it.
- Full-recording WAV clips are off by default (`WORKER_CREATE_CLIPS`); the chat app
  still creates clips on demand.
- The web app reads the catalog and Qdrant instead of S3. It no longer transcribes or
  embeds at startup, so run the worker first (or alongside it).
- Chat search tools use the catalog's full-text index and Qdrant filters; `list_calls`
  is paged (`offset`, `limit`, `contains`) so the model never receives every call.
