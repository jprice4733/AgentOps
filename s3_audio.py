"""List S3 audio without saving local files."""

import argparse
import os
import sys
from pathlib import Path

from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_URI = "s3://denverit-demo-bucket/voip-telecom-system/"


from wav_search_agent.s3_store import S3Store


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri", default=os.getenv("S3_AUDIO_URI", DEFAULT_URI))
    parser.add_argument("--profile", help="AWS profile (otherwise use the standard AWS credential chain)")
    parser.add_argument("--limit", type=int, help="Maximum number of audio files to list")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    try:
        store = S3Store(args.uri, args.profile)
        bucket = store.bucket
        count = 0
        for item in store.audio_objects():
            print(f"s3://{bucket}/{item['Key']} ({item['Size']} bytes)")
            count += 1
            if args.limit is not None and count >= args.limit:
                break
        print(f"Found {count} supported audio file(s).")
        return 0
    except (BotoCoreError, ClientError, ValueError, OSError) as exc:
        print(f"S3 access failed: {exc}", file=sys.stderr)
        print("Check your AWS credentials/profile and s3:ListBucket / s3:GetObject permissions.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
