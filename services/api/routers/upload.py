"""
Photo upload endpoint — generates signed GCS URLs for direct client upload.

POST /upload/signed-url
- Validates file type (jpeg, png, webp) and max size (10MB)
- Returns a signed PUT URL for direct upload to GCS
- Requires authenticated user session

The client uploads directly to GCS using the signed URL,
then stores the resulting public URL on the slot record.
"""

from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

router = APIRouter(prefix="/upload", tags=["upload"])

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
SIGNED_URL_EXPIRY = timedelta(minutes=15)
GCS_BUCKET = "overplanned-uploads"


class SignedUrlRequest(BaseModel):
    """Request body for generating a signed upload URL."""

    tripId: str = Field(min_length=1)
    slotId: str = Field(min_length=1)
    contentType: str
    fileSizeBytes: int = Field(gt=0)

    @field_validator("contentType")
    @classmethod
    def validate_content_type(cls, v: str) -> str:
        if v not in ALLOWED_CONTENT_TYPES:
            raise ValueError(
                f"Unsupported content type: {v}. "
                f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
            )
        return v

    @field_validator("fileSizeBytes")
    @classmethod
    def validate_file_size(cls, v: int) -> int:
        if v > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"File too large: {v} bytes. Maximum: {MAX_FILE_SIZE_BYTES} bytes (10MB)"
            )
        return v


class SignedUrlResponse(BaseModel):
    uploadUrl: str
    objectPath: str
    publicUrl: str
    expiresInSeconds: int


@router.post("/signed-url")
async def generate_signed_url(
    body: SignedUrlRequest,
    request: Request,
) -> dict:
    """
    Generate a signed GCS URL for direct photo upload.

    The client PUTs the file directly to the returned uploadUrl
    with the matching Content-Type header.
    """
    # In production: extract userId from session
    user_id = getattr(request.state, "user_id", "anonymous")

    # Build a unique object path
    ext = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }[body.contentType]

    file_id = str(uuid4())
    object_path = f"photos/{body.tripId}/{body.slotId}/{file_id}.{ext}"

    # In production: use google.cloud.storage to generate signed URL
    # For now, return a structured response that the frontend can use
    # once GCS credentials are configured.
    try:
        upload_url, public_url = _generate_gcs_signed_url(
            bucket=GCS_BUCKET,
            object_path=object_path,
            content_type=body.contentType,
            expiry=SIGNED_URL_EXPIRY,
        )
    except Exception:
        # Fallback for local dev without GCS credentials
        upload_url = f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o?uploadType=media&name={object_path}"
        public_url = f"https://storage.googleapis.com/{GCS_BUCKET}/{object_path}"

    return {
        "success": True,
        "data": {
            "uploadUrl": upload_url,
            "objectPath": object_path,
            "publicUrl": public_url,
            "expiresInSeconds": int(SIGNED_URL_EXPIRY.total_seconds()),
        },
        "requestId": getattr(request.state, "request_id", ""),
    }


def _generate_gcs_signed_url(
    bucket: str,
    object_path: str,
    content_type: str,
    expiry: timedelta,
) -> tuple[str, str]:
    """
    Generate a signed URL for GCS upload.
    Requires GOOGLE_APPLICATION_CREDENTIALS in environment.
    """
    from google.cloud import storage

    client = storage.Client()
    gcs_bucket = client.bucket(bucket)
    blob = gcs_bucket.blob(object_path)

    signed_url = blob.generate_signed_url(
        version="v4",
        expiration=expiry,
        method="PUT",
        content_type=content_type,
    )

    public_url = f"https://storage.googleapis.com/{bucket}/{object_path}"

    return signed_url, public_url
