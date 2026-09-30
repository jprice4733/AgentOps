"""Create missing transcripts and full-recording clips in S3."""
import argparse
from dotenv import load_dotenv
from s3_audio import ROOT
from wav_search_agent.s3_store import S3Store


from wav_search_agent.processing import transcribe_object, sync_outputs


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile")
    parser.add_argument("--uri")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    store = S3Store(args.uri, args.profile)
    report = sync_outputs(store, limit=args.limit)
    print(f"Processed {report['recordings']} recordings; created "
          f"{report['transcripts_created']} transcripts and {report['clips_created']} clips.")
    if report['errors']:
        raise SystemExit(f"{len(report['errors'])} output(s) failed; rerun to retry missing outputs.")



if __name__ == "__main__":
    main()
