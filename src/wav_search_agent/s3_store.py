"""S3 storage for recordings and transcripts."""
import json
import os
import re
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from .config import AUDIO_EXTENSIONS

DEFAULT_URI = "s3://denverit-demo-bucket/voip-telecom-system/"


def parse_location(uri):
    location = urlsplit(uri)
    if location.scheme != "s3" or not location.netloc or location.query or location.fragment:
        raise ValueError("Expected s3://bucket/prefix/.")
    prefix = location.path.lstrip("/")
    return location.netloc, prefix.rstrip("/") + "/" if prefix else ""


def list_audio(client, bucket, prefix):
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=prefix):
        for item in page.get("Contents", []):
            if PurePosixPath(item["Key"]).suffix.lower() in AUDIO_EXTENSIONS:
                yield item


class S3Store:
    def __init__(self, uri=None, profile=None, client=None):
        self.bucket, self.prefix = parse_location(uri or os.getenv("S3_AUDIO_URI", DEFAULT_URI))
        self.json_prefix = os.getenv("S3_JSON_PREFIX", "~./json/").strip("/") + "/"
        self.clips_prefix = os.getenv("S3_CLIPS_PREFIX", "~./clips/").strip("/") + "/"
        self.client = client or boto3.Session(profile_name=profile).client(
            "s3", config=Config(signature_version="s3v4"))

    def audio_objects(self):
        return (item for item in list_audio(self.client, self.bucket, self.prefix)
                if not item["Key"].startswith((self.json_prefix, self.clips_prefix)))

    def uri(self, key):
        return f"s3://{self.bucket}/{key}"

    def audio_key(self, uri):
        base = f"s3://{self.bucket}/"
        if not uri.startswith(base):
            raise ValueError("Audio must be in the configured S3 bucket.")
        key = uri[len(base):]
        if not key.startswith(self.prefix) or PurePosixPath(key).suffix.lower() not in AUDIO_EXTENSIONS:
            raise ValueError("Audio must be under the configured S3 prefix.")
        return key

    def read(self, key, **kwargs):
        body = self.client.get_object(Bucket=self.bucket, Key=key, **kwargs)["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def audio_stream(self, uri):
        return BytesIO(self.read(self.audio_key(uri)))

    def transcript_key(self, item):
        identity = json.dumps([item["Key"], item.get("ETag"), str(item.get("LastModified")), item["Size"]])
        return self.json_prefix + sha256(identity.encode()).hexdigest() + ".json"

    def transcript(self, item):
        try:
            payload = json.loads(self.read(self.transcript_key(item)))
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
                return None
            raise
        if not isinstance(payload, dict) or payload.get("file_path") != self.uri(item["Key"]):
            raise ValueError("Invalid S3 transcript audio reference.")
        return payload

    def save_transcript(self, item, payload):
        self.client.put_object(Bucket=self.bucket, Key=self.transcript_key(item),
                               Body=json.dumps(payload).encode(), ContentType="application/json")

    def clip_key(self, name):
        if not re.fullmatch(r"[0-9a-f]{64}\.wav", name):
            raise ValueError("Invalid clip name.")
        return self.clips_prefix + name

    def save_clip(self, name, data):
        self.client.put_object(Bucket=self.bucket, Key=self.clip_key(name),
                               Body=data, ContentType="audio/wav")

    def clip_url(self, name):
        return self.client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": self.clip_key(name)},
            ExpiresIn=3600,
        )
