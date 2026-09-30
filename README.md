# Audio File Search Agent

A Python app for transcribing S3 audio, storing transcripts in S3, and searching them through a FastAPI chat agent.

## Features

- Reads audio and transcript JSON from S3
- Searches transcript segments with an in-memory Qdrant index
- Extracts and serves clips on demand
- Uses no persistent local audio, transcript, or index files

## Setup

1. From the project root, create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```
   Windows:
   ```
   py -m venv .venv                                                       
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```
Windows:
```
py -m pip install -r requirements.txt
```

3. Install FFmpeg, which pydub uses when extracting audio clips. On Windows,
   run this in PowerShell and then open a new terminal:
   ```powershell
   winget install --id Gyan.FFmpeg.Essentials --exact
   ```
   On macOS, use `brew install ffmpeg`; on Debian/Ubuntu, use
   `sudo apt install ffmpeg`.
4. Copy `.env.example` to `.env` and set your `OPENAI_API_KEY`.  Note:  need to have you own OPENAI API key
5. Start the app:
   ```bash
   python main.py
   ```
   Windows:
```
py main.py
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

## S3 workflow

On startup the app scans all supported source recordings and creates any missing
transcripts and full-recording WAV clips before indexing. Transcription sends audio
to OpenAI using the configured API key; outputs stay in the configured S3 JSON and
clips folders. Startup can take longer while processing new recordings.

Existing outputs for the same source version are reused. Transcript and clip
creation are checked separately, and failures are logged while other recordings
continue processing. Rerun to retry failed outputs. Set `S3_AUTO_PROCESS=false` in
`.env` to disable startup processing. Run `python transcribe_audio.py` to sync both
output types manually (`--limit N` limits the number of source recordings checked).
The app scans on each startup, not continuously; restart after adding recordings.
Full-recording clips use source-version-based filenames; requested excerpts remain
separate clips. Previously generated excerpts do not replace the full-recording clip.

All data resides in `denverit-demo-bucket`:

- Source audio: `voip-telecom-system/`
- Transcript JSON: `voip-telecom-system/json/`
- Generated WAV clips: `voip-telecom-system/clips/`

The app ignores local recordings, local JSON transcripts, and old local indexes.
It builds its search index in memory and uploads generated clips to S3.
Playback redirects to a fresh one-hour presigned S3 URL. Clips persist across
app restarts; restarting rebuilds embeddings. Audio is read
into memory on demand; large recordings require sufficient RAM. FFmpeg may use
its own temporary processing files for compressed formats.

Set `AWS_PROFILE` in `.env` to your AWS profile, or use standard AWS environment
credentials / an IAM role. For SSO, run `aws sso login --profile YOUR_PROFILE`.
Set `S3_AUDIO_URI` to change the source bucket/prefix. `S3_JSON_PREFIX` and
`S3_CLIPS_PREFIX` configure output prefixes within that same bucket.

```powershell
python s3_audio.py --limit 10
python transcribe_audio.py --limit 1
python main.py
```

Transcription sends S3 audio to OpenAI and writes JSON to `voip-telecom-system/json/` in S3. Omit `--limit` to process all recordings. Unchanged objects with
existing transcripts are skipped; changed objects receive new transcript keys.
Only transcripts for current S3 recordings are indexed. Restart the app after
transcription. No existing local files are deleted or uploaded.

AWS permissions: `s3:ListBucket` on the bucket, `s3:GetObject` for the configured
audio prefix and both output prefixes, and `s3:PutObject` on `voip-telecom-system/json/*` and
`voip-telecom-system/clips/*`. Existing objects under the former `_transcripts/` prefix are not
moved automatically; new transcription runs use the configured JSON prefix.
Customer-managed KMS encryption may also require key permissions.

AWS references: [listing objects](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/paginator/ListObjectsV2.html).
