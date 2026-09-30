import json
import unittest
from io import BytesIO
from unittest.mock import Mock
from botocore.exceptions import ClientError
from s3_audio import S3Store
from wav_search_agent.s3_store import list_audio, parse_location
from transcribe_audio import transcribe_object


class S3AudioTests(unittest.TestCase):
    def test_json_and_clips_use_requested_bucket_prefixes(self):
        client = Mock()
        store = S3Store("s3://bucket/calls/", client=client)
        item = {"Key": "calls/a.wav", "Size": 5}
        store.save_transcript(item, {"text": "hello"})
        args = client.put_object.call_args.kwargs
        self.assertEqual(args["Bucket"], "bucket")
        self.assertTrue(args["Key"].startswith("voip-telecom-system/json/"))
        self.assertEqual(json.loads(args["Body"]), {"text": "hello"})
        name = "a" * 64 + ".wav"
        store.save_clip(name, b"RIFF")
        client.put_object.assert_called_with(Bucket="bucket", Key="voip-telecom-system/clips/" + name,
                                             Body=b"RIFF", ContentType="audio/wav")
        store.clip_url(name)
        client.generate_presigned_url.assert_called_with(
            "get_object", Params={"Bucket": "bucket", "Key": "voip-telecom-system/clips/" + name}, ExpiresIn=3600)
        with self.assertRaises(ValueError):
            store.clip_url("../secret.wav")

    def test_paginated_listing(self):
        self.assertEqual(parse_location("s3://bucket/calls"), ("bucket", "calls/"))
        client = Mock()
        client.get_paginator.return_value.paginate.return_value = [
            {}, {"Contents": [{"Key": "calls/info.txt"}, {"Key": "calls/a.WAV"}]},
            {"Contents": [{"Key": "calls/nested/b.mp3"}]},
        ]
        self.assertEqual([x["Key"] for x in list_audio(client, "bucket", "calls/")],
                         ["calls/a.WAV", "calls/nested/b.mp3"])

    def test_rejects_local_and_outside_audio(self):
        store = S3Store("s3://bucket/calls/", client=Mock())
        for uri in ["storage/audio/a.wav", "s3://other/calls/a.wav", "s3://bucket/else/a.wav"]:
            with self.assertRaises(ValueError):
                store.audio_stream(uri)
        store.client.get_object.assert_not_called()

    def test_audio_reads_and_closes_s3_body(self):
        body = BytesIO(b"audio")
        client = Mock()
        client.get_object.return_value = {"Body": body}
        store = S3Store("s3://bucket/calls/", client=client)
        self.assertEqual(store.audio_stream("s3://bucket/calls/a.wav").read(), b"audio")
        self.assertTrue(body.closed)

    def test_missing_transcript_and_access_denied_differ(self):
        client = Mock()
        store = S3Store("s3://bucket/calls/", client=client)
        item = {"Key": "calls/a.wav", "Size": 5, "ETag": "a"}
        client.get_object.side_effect = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        self.assertIsNone(store.transcript(item))
        client.get_object.side_effect = ClientError({"Error": {"Code": "AccessDenied"}}, "GetObject")
        with self.assertRaises(ClientError):
            store.transcript(item)
        self.assertNotEqual(store.transcript_key(item), store.transcript_key(dict(item, ETag="b")))

    def test_transcription_uses_s3_bytes_and_saves_to_s3(self):
        store, client = Mock(), Mock()
        store.transcript.return_value = None
        store.read.return_value = b"audio"
        store.uri.return_value = "s3://bucket/calls/a.wav"
        client.audio.transcriptions.create.return_value = Mock(text="hello", segments=[])
        item = {"Key": "calls/a.wav", "ETag": "etag"}
        self.assertTrue(transcribe_object(store, client, item))
        store.read.assert_called_once_with("calls/a.wav", IfMatch="etag")
        self.assertEqual(client.audio.transcriptions.create.call_args.kwargs["file"], ("a.wav", b"audio"))
        self.assertEqual(store.save_transcript.call_args.args[1]["file_path"], "s3://bucket/calls/a.wav")
        store.transcript.return_value = {"text": "hello"}
        self.assertFalse(transcribe_object(store, client, item))
