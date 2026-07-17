"""
S3 storage for judgment PDFs (Stage 5: "uploaded to S3").

Uses boto3's default credential chain -- no keys are read or passed
explicitly in this file. Set the standard env vars and boto3 picks them
up automatically:

    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_DEFAULT_REGION

(or an instance/role profile if this ever runs on EC2/ECS -- same code
path, no changes needed.)

Bucket is expected to allow public GetObject via bucket policy (judgment
PDFs are public court records), so uploaded_url is a stable, permanent
link -- not a presigned URL that expires. If your bucket must stay
private, set S3_USE_PRESIGNED_URL=true and tune S3_PRESIGNED_EXPIRY_SECONDS,
but note that citations/pdf_url values stored in Weaviate/MongoDB will
go stale once the signature expires.
"""

import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME", "")
S3_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
S3_KEY_PREFIX = os.getenv("S3_KEY_PREFIX", "judgments")

S3_USE_PRESIGNED_URL = os.getenv("S3_USE_PRESIGNED_URL", "false").lower() == "true"
S3_PRESIGNED_EXPIRY_SECONDS = int(os.getenv("S3_PRESIGNED_EXPIRY_SECONDS", "604800"))  # 7 days, SigV4 max

_s3_client = None


def _get_client():
    global _s3_client

    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=S3_REGION)

    return _s3_client


def _object_key(filename: str) -> str:
    return f"{S3_KEY_PREFIX.rstrip('/')}/{filename}"


def _object_exists(key: str) -> bool:
    client = _get_client()

    try:
        client.head_object(Bucket=S3_BUCKET_NAME, Key=key)
        return True
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def get_object_url(key: str) -> str:
    if S3_USE_PRESIGNED_URL:
        client = _get_client()
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": S3_BUCKET_NAME, "Key": key},
            ExpiresIn=S3_PRESIGNED_EXPIRY_SECONDS,
        )

    return f"https://{S3_BUCKET_NAME}.s3.{S3_REGION}.amazonaws.com/{key}"


def upload_to_s3(file_path: str) -> str:
    """
    Upload a PDF to S3.

    If an object with the same filename already exists under the
    configured prefix, returns its URL instead of re-uploading (mirrors
    the idempotency behavior the old upload_to_drive() had).
    """

    if not S3_BUCKET_NAME:
        raise RuntimeError(
            "S3_BUCKET_NAME is not set -- add it to your .env before calling upload_to_s3()"
        )

    if not os.path.exists(file_path):
        raise FileNotFoundError(file_path)

    filename = os.path.basename(file_path)
    key = _object_key(filename)

    if _object_exists(key):
        logger.info("✓ Already exists on S3")
        return get_object_url(key)

    client = _get_client()

    client.upload_file(
        file_path,
        S3_BUCKET_NAME,
        key,
        ExtraArgs={"ContentType": "application/pdf"},
    )

    logger.info("✓ Uploaded to S3")

    return get_object_url(key)
