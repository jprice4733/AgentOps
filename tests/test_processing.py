from io import BytesIO
from unittest.mock import Mock

from botocore.exceptions import ClientError
from pydub import AudioSegment
import pytest

from s3_audio import S3Store
from wav_search_agent.processing import sync_outputs


def setup_store():
    store = Mock()
    store.audio_objects.return_value = [{"Key": "calls/a.wav", "ETag": "v1"}]
    store.recording_clip_name.return_value = "a" * 64 + ".wav"
    output = BytesIO()
    AudioSegment.silent(duration=1000).export(output, format="wav")
    store.read.return_value = output.getvalue()
    return store


def test_existing_outputs_are_not_recreated():
    store = setup_store()
    store.transcript.return_value = {"text": "existing"}
    store.clip_exists.return_value = True
    client = Mock()
    report = sync_outputs(store, client)
    assert report == {"recordings": 1, "transcripts_created": 0, "clips_created": 0, "errors": []}
    store.read.assert_not_called()
    store.save_clip.assert_not_called()
    client.audio.transcriptions.create.assert_not_called()


def test_missing_clip_created_without_retranscribing():
    store = setup_store()
    store.transcript.return_value = {"text": "existing"}
    store.clip_exists.return_value = False
    report = sync_outputs(store, Mock())
    assert report["clips_created"] == 1
    assert report["transcripts_created"] == 0
    data = store.save_clip.call_args.args[1]
    assert len(AudioSegment.from_file(BytesIO(data), format="wav")) == 1000


def test_missing_transcript_created_without_recreating_clip():
    store = setup_store()
    store.transcript.return_value = None
    store.clip_exists.return_value = True
    client = Mock()
    client.audio.transcriptions.create.return_value = Mock(text="hello", segments=[])
    report = sync_outputs(store, client)
    assert report["transcripts_created"] == 1
    assert report["clips_created"] == 0
    store.save_transcript.assert_called_once()


def test_transcription_failure_still_creates_clip_and_processes_next_recording():
    store = setup_store()
    store.audio_objects.return_value *= 2
    store.transcript.return_value = None
    store.clip_exists.return_value = False
    client = Mock()
    client.audio.transcriptions.create.side_effect = RuntimeError("API unavailable")
    report = sync_outputs(store, client)
    assert report["recordings"] == 2
    assert report["clips_created"] == 2
    assert len(report["errors"]) == 2


def test_clip_missing_vs_access_denied_and_source_version():
    client = Mock()
    store = S3Store(client=client)
    item = {"Key": "calls/a.wav", "Size": 5, "ETag": "v1"}
    name = store.recording_clip_name(item)
    assert name != store.recording_clip_name(dict(item, ETag="v2"))
    client.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadObject")
    assert not store.clip_exists(name)
    client.head_object.side_effect = ClientError({"Error": {"Code": "403"}}, "HeadObject")
    with pytest.raises(ClientError):
        store.clip_exists(name)
