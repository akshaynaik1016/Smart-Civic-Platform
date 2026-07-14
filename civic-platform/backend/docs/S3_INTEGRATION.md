# AWS S3 File Storage Integration

## What was already in place vs. what this adds

`app/services/storage_service.py` already handled the day-to-day complaint
photo workflow well: SHA-256 + perceptual hashing for duplicate detection,
image compression/thumbnailing, magic-byte content-type sniffing, and a
local-filesystem fallback for development. What it didn't have:

| Gap | Fixed by |
|---|---|
| Every boto3 call could raise a raw, unhandled `ClientError` straight into a 500 | `app/storage/s3_errors.py` |
| No retry on transient throttling (S3 `SlowDown`) | `app/storage/s3_errors.py::with_s3_retry` |
| S3 client built inline with no timeout/pool config | `app/storage/s3_client.py` |
| No support for files above a few hundred KB | `app/storage/multipart.py` |
| Presigned URLs bypass any CDN, exposing the raw bucket hostname | `app/storage/cloudfront_signer.py` |
| No documented/applied bucket CORS, lifecycle, or encryption | `deploy/aws/*.example.json` + `scripts/setup_s3_bucket.py` |
| No least-privilege IAM policy for the app's own S3 access | `deploy/aws/s3-iam-policy.example.json` |

## Architecture

```
app/services/storage_service.py   <- unchanged public API (upload_complaint_image,
                                      presigned_url, delete_object, etc.) - every
                                      existing caller keeps working unmodified
        |
        +--> app/storage/s3_client.py        single client, retry/timeout config
        +--> app/storage/s3_errors.py        error translation + retry decorator
        +--> app/storage/cloudfront_signer.py  CDN-aware URLs, opt-in

app/storage/multipart.py            <- new capability, not yet wired into any
                                        endpoint - see "Where multipart isn't
                                        used yet" below
```

`storage_service.py` itself was *refactored*, not replaced: `_s3_upload`,
`presigned_url`, and `delete_object` now route through `with_s3_retry` /
`translate_s3_error` instead of calling boto3 directly with no error
handling. Every existing call site (`ComplaintService.upload_image`,
the avatar upload in `UserService`, the AI re-analysis endpoint) gets this
for free with no changes on their end.

## One-time setup

```bash
# 1. Create and configure the bucket (idempotent - safe to re-run)
python backend/scripts/setup_s3_bucket.py \
  --bucket smart-civic-media \
  --region ap-south-1 \
  --dry-run                      # review first

python backend/scripts/setup_s3_bucket.py \
  --bucket smart-civic-media \
  --region ap-south-1

# 2. Grant the application's runtime IAM role the policy in
#    deploy/aws/s3-iam-policy.example.json (scoped to just this bucket -
#    no wildcard resource access)

# 3. Set in backend/.env (or push via scripts/push_secrets_to_aws.py):
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=ap-south-1
AWS_S3_BUCKET=smart-civic-media
```

CloudFront is optional - leave `CLOUDFRONT_DOMAIN` /
`CLOUDFRONT_KEY_PAIR_ID` / `CLOUDFRONT_PRIVATE_KEY` blank to keep using
direct S3 presigned URLs, which work fine for a single-region deployment
without heavy read traffic. Add CloudFront when image-view traffic
justifies CDN edge caching.

## What `setup_s3_bucket.py` actually applies

- **CORS** (`s3-cors-config.example.json`) - required for the dashboard to
  do direct browser-side presigned PUT uploads, if that flow is ever added
  (currently all uploads proxy through the FastAPI backend, so this is
  forward-looking, but costs nothing to apply now).
- **Lifecycle** (`s3-lifecycle-policy.example.json`) - transitions
  complaint/resolution photos to `STANDARD_IA` after 90 days and
  `GLACIER_IR` after 365; expires generated reports after 90 days;
  **aborts incomplete multipart uploads after 3 days** - this last rule
  matters specifically because of the new `multipart.py` capability: a
  request that dies mid-upload would otherwise leave orphaned, silently
  billed parts forever.
- **Default encryption** - AES256 server-side encryption on every object,
  with S3 Bucket Keys enabled to reduce KMS request costs (using AES256
  rather than KMS-managed keys here, since this is the simpler/cheaper
  default; switch to `aws:kms` in the script if a compliance requirement
  demands customer-managed keys).
- **Public access block** - on by default. This intentionally conflicts
  with `StorageService.upload_bytes(..., public=True)`'s `ACL=public-read`
  path (used for avatars) - that ACL will silently have no effect with the
  block on. Either run with `--skip-public-access-block`, or serve avatars
  through CloudFront signed URLs instead. The script prints this trade-off
  explicitly in dry-run mode rather than silently picking a side.

## Where multipart upload isn't wired in yet

`app/storage/multipart.py::upload_large_file` exists and is tested in
isolation, but nothing currently calls it - every existing upload path
(complaint photos, avatars) goes through compression first, which keeps
them well under the 8MB multipart threshold by design. This is forward
capacity for:
- A future PDF report-generation feature writing directly to S3
- Officer "before/after" resolution photo sets at full camera resolution,
  if compression is ever made optional for evidentiary purposes
- Bulk CSV/Excel exports too large to hold in a single `put_object` call

Wiring it in is a one-line call from whichever service eventually needs
it - `await upload_large_file(key, data, content_type)` - not a design
decision that needs to be made now.

## Testing

```bash
cd backend
pytest tests/storage/test_s3_errors.py -v
```

These tests construct fake botocore-shaped exceptions rather than mocking
boto3 itself or making real AWS calls - they verify the *mapping* logic
(which error codes become which app exceptions, which are retried) is
correct, independent of whether boto3/AWS is reachable. They run
automatically in `backend-ci.yml`.

## Files in this module

| File | Purpose |
|---|---|
| `backend/app/storage/s3_client.py` | Singleton boto3 client, retry/timeout/pool config |
| `backend/app/storage/s3_errors.py` | Error code -> app exception translation, retry decorator |
| `backend/app/storage/multipart.py` | Multipart upload/download for large files (not yet wired into an endpoint) |
| `backend/app/storage/cloudfront_signer.py` | Optional CDN-aware signed URLs |
| `backend/app/services/storage_service.py` | Existing service, refactored to use the above |
| `backend/scripts/setup_s3_bucket.py` | Idempotent bucket creation + CORS/lifecycle/encryption setup |
| `backend/tests/storage/test_s3_errors.py` | Error translation + retry test coverage |
| `deploy/aws/s3-cors-config.example.json` | CORS rules applied by the setup script |
| `deploy/aws/s3-lifecycle-policy.example.json` | Lifecycle rules applied by the setup script |
| `deploy/aws/s3-iam-policy.example.json` | Least-privilege IAM policy for the app's runtime role |
| `backend/.env.example` | Documents the new `CLOUDFRONT_*` fields |
