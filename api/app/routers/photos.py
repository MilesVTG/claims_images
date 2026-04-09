"""Photo endpoints (Section 14B).

POST /photos/upload         — multipart upload to GCS
GET  /photos/{cid}/{clid}   — list photos for a claim
GET  /photos/status/{key}   — single photo processing status
GET  /photos/serve/{key}    — serve photo bytes from GCS
POST /photos/ask/{key}      — stub for future Q&A
"""

import mimetypes

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from fastapi.responses import Response
from google.cloud import storage as gcs
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user

router = APIRouter(prefix="/photos", tags=["photos"])

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def _get_bucket():
    client = gcs.Client()
    return client.bucket(settings.gcs_bucket)


@router.post("/upload")
async def upload_photo(
    file: UploadFile,
    contract_id: str = Form(...),
    claim_id: str = Form(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Upload a claim photo to GCS. Pipeline triggers automatically via OBJECT_FINALIZE."""
    # Validate extension
    filename = file.filename or ""
    ext = ""
    dot_idx = filename.rfind(".")
    if dot_idx >= 0:
        ext = filename[dot_idx:].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Read and validate size
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 20 MB limit")

    # Determine filename by counting existing blobs in the claim prefix
    bucket = _get_bucket()
    prefix = f"{contract_id}/{claim_id}/"
    existing = list(bucket.list_blobs(prefix=prefix))
    photo_num = len(existing) + 1
    new_filename = f"photo_{photo_num:03d}{ext}"
    storage_key = f"{contract_id}/{claim_id}/{new_filename}"

    # Upload to GCS
    blob = bucket.blob(storage_key)
    content_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    blob.upload_from_string(data, content_type=content_type)

    # Upsert claims row — append to photo_uris array (create row if new claim)
    is_sqlite = db.bind.dialect.name == "sqlite"
    if is_sqlite:
        db.execute(
            text("""
                INSERT INTO claims (contract_id, claim_id, photo_uris)
                VALUES (:cid, :clid, json_array(:key))
                ON CONFLICT (contract_id, claim_id) DO UPDATE
                SET photo_uris = json_insert(
                    COALESCE(claims.photo_uris, '[]'),
                    '$[#]', :key
                )
            """),
            {"cid": contract_id, "clid": claim_id, "key": storage_key},
        )
    else:
        db.execute(
            text("""
                INSERT INTO claims (contract_id, claim_id, photo_uris)
                VALUES (:cid, :clid, ARRAY[:key]::text[])
                ON CONFLICT (contract_id, claim_id) DO UPDATE
                SET photo_uris = array_append(
                    COALESCE(claims.photo_uris, ARRAY[]::text[]),
                    :key
                )
            """),
            {"cid": contract_id, "clid": claim_id, "key": storage_key},
        )
    db.commit()

    return {"storage_key": storage_key, "status": "uploaded"}


# -- Fixed-prefix routes BEFORE the parameterized /{contract_id}/{claim_id} --


@router.get("/status/{storage_key:path}")
def photo_status(
    storage_key: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Get processing status for a single photo."""
    row = db.execute(
        text("SELECT storage_key, status, processed_at FROM processed_photos WHERE storage_key = :key"),
        {"key": storage_key},
    ).fetchone()

    if not row:
        return {"storage_key": storage_key, "status": "pending", "processed_at": None}

    return {
        "storage_key": row[0],
        "status": row[1],
        "processed_at": str(row[2]) if row[2] else None,
    }


@router.get("/serve/{storage_key:path}")
def serve_photo(
    storage_key: str,
    _user: dict = Depends(get_current_user),
):
    """Serve photo bytes from GCS with appropriate content type."""
    bucket = _get_bucket()
    blob = bucket.blob(storage_key)

    if not blob.exists():
        raise HTTPException(status_code=404, detail="Photo not found")

    data = blob.download_as_bytes()
    content_type = blob.content_type or mimetypes.guess_type(storage_key)[0] or "application/octet-stream"

    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.post("/ask/{storage_key:path}")
def ask_photo(
    storage_key: str,
    _user: dict = Depends(get_current_user),
):
    """Stub for future photo Q&A feature."""
    return {"status": "not_implemented"}


# -- Parameterized route last to avoid capturing /status, /serve, /ask --


@router.get("/{contract_id}/{claim_id}")
def list_photos(
    contract_id: str,
    claim_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """List photos for a claim — blobs from GCS joined with processing status."""
    bucket = _get_bucket()
    prefix = f"{contract_id}/{claim_id}/"
    blobs = list(bucket.list_blobs(prefix=prefix))

    # Build a lookup of processed status
    rows = db.execute(
        text("""
            SELECT storage_key, status, processed_at
            FROM processed_photos
            WHERE contract_id = :cid AND claim_id = :clid
        """),
        {"cid": contract_id, "clid": claim_id},
    ).fetchall()
    status_map = {r[0]: {"status": r[1], "processed_at": str(r[2]) if r[2] else None} for r in rows}

    photos = []
    for blob in blobs:
        key = blob.name
        info = status_map.get(key, {"status": "pending", "processed_at": None})
        filename = key.rsplit("/", 1)[-1] if "/" in key else key
        photos.append({
            "storage_key": key,
            "filename": filename,
            "status": info["status"],
            "processed_at": info["processed_at"],
            "url": f"/api/photos/serve/{key}",
        })

    return photos
