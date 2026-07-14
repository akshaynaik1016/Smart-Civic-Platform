#!/usr/bin/env python3
"""
setup_s3_bucket.py
====================
Idempotently creates and configures the S3 bucket this platform depends
on: CORS (for direct browser presigned-URL uploads from the dashboard),
lifecycle rules (storage-class transitions + incomplete multipart cleanup
+ report expiry), default encryption, and a public-access block.

This exists because the alternative — "here's a doc describing what the
bucket needs, go run the aws-cli commands yourself" — is exactly the kind
of manual step that gets skipped, or done once correctly and then
forgotten when the bucket is recreated in a new environment.

Usage:
    python scripts/setup_s3_bucket.py --bucket smart-civic-media --region ap-south-1

    # Dry run — show what would be done without making any AWS calls
    python scripts/setup_s3_bucket.py --bucket smart-civic-media --dry-run

Requires AWS credentials with s3:CreateBucket, s3:PutBucketCors,
s3:PutLifecycleConfiguration, s3:PutEncryptionConfiguration, and
s3:PutPublicAccessBlock on the target bucket.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_DEPLOY_AWS_DIR = _HERE.parent.parent / "deploy" / "aws"


def _load_json(filename: str) -> dict:
    path = _DEPLOY_AWS_DIR / filename
    if not path.exists():
        print(f"error: expected config file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text())


def ensure_bucket_exists(client, bucket: str, region: str, dry_run: bool) -> bool:
    """Returns True if the bucket already existed, False if newly created."""
    try:
        client.head_bucket(Bucket=bucket)
        print(f"Bucket '{bucket}' already exists.")
        return True
    except Exception:
        pass

    if dry_run:
        print(f"[dry-run] Would create bucket '{bucket}' in region '{region}'")
        return False

    create_kwargs: dict = {"Bucket": bucket}
    if region != "us-east-1":
        # us-east-1 is the one region that rejects an explicit
        # LocationConstraint matching itself — omit it there.
        create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}

    client.create_bucket(**create_kwargs)
    print(f"Created bucket '{bucket}' in region '{region}'.")
    return False


def apply_cors(client, bucket: str, dry_run: bool) -> None:
    config = _load_json("s3-cors-config.example.json")
    if dry_run:
        print(f"[dry-run] Would apply CORS config:\n{json.dumps(config, indent=2)}")
        return
    client.put_bucket_cors(Bucket=bucket, CORSConfiguration=config)
    print("Applied CORS configuration.")


def apply_lifecycle(client, bucket: str, dry_run: bool) -> None:
    config = _load_json("s3-lifecycle-policy.example.json")
    if dry_run:
        print(f"[dry-run] Would apply lifecycle policy:\n{json.dumps(config, indent=2)}")
        return
    client.put_bucket_lifecycle_configuration(Bucket=bucket, LifecycleConfiguration=config)
    print("Applied lifecycle policy.")


def apply_encryption(client, bucket: str, dry_run: bool) -> None:
    config = {
        "Rules": [
            {
                "ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"},
                "BucketKeyEnabled": True,
            }
        ]
    }
    if dry_run:
        print(f"[dry-run] Would apply default encryption:\n{json.dumps(config, indent=2)}")
        return
    client.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration=config)
    print("Applied default server-side encryption (AES256).")


def apply_public_access_block(client, bucket: str, dry_run: bool) -> None:
    """
    Block all public access at the bucket level. Individual objects can
    still be made public via an explicit ACL (used by upload_bytes(...,
    public=True) for avatars) UNLESS this block is on — so this is
    intentionally the stricter, safer default. If avatar public-read
    access is actually required in your deployment, this step should be
    skipped or adjusted; flagging that trade-off rather than silently
    picking one.
    """
    config = {
        "BlockPublicAcls": True,
        "IgnorePublicAcls": True,
        "BlockPublicPolicy": True,
        "RestrictPublicBuckets": True,
    }
    if dry_run:
        print(f"[dry-run] Would apply public access block:\n{json.dumps(config, indent=2)}")
        print(
            "[dry-run] NOTE: this blocks the ACL='public-read' path used by "
            "StorageService.upload_bytes(..., public=True) for avatars. "
            "If you need public avatar URLs without presigning, serve them "
            "through CloudFront (see app/storage/cloudfront_signer.py) "
            "instead of relying on bucket-level public ACLs."
        )
        return
    client.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration=config)
    print("Applied public access block (all public access blocked at bucket level).")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bucket", required=True, help="S3 bucket name (must match AWS_S3_BUCKET in .env)")
    parser.add_argument("--region", default="ap-south-1", help="AWS region (default: ap-south-1)")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without calling AWS")
    parser.add_argument(
        "--skip-public-access-block", action="store_true",
        help="Skip the public-access block step (only if you intentionally need public-read ACLs)",
    )
    args = parser.parse_args()

    if not args.dry_run:
        import boto3
        client = boto3.client("s3", region_name=args.region)
    else:
        client = None   # never touched in dry-run mode

    print(f"Configuring bucket '{args.bucket}' in '{args.region}'"
          + (" (DRY RUN — no AWS calls will be made)" if args.dry_run else ""))
    print()

    ensure_bucket_exists(client, args.bucket, args.region, args.dry_run)
    apply_cors(client, args.bucket, args.dry_run)
    apply_lifecycle(client, args.bucket, args.dry_run)
    apply_encryption(client, args.bucket, args.dry_run)

    if not args.skip_public_access_block:
        apply_public_access_block(client, args.bucket, args.dry_run)
    else:
        print("Skipped public access block (--skip-public-access-block was set).")

    print()
    print("Done." if not args.dry_run else "Dry run complete — no changes were made.")
    print(
        f"\nRemember to set in backend/.env (or push via "
        f"scripts/push_secrets_to_aws.py):\n"
        f"  AWS_S3_BUCKET={args.bucket}\n"
        f"  AWS_REGION={args.region}"
    )


if __name__ == "__main__":
    main()
