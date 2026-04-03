"""Photo endpoints (Section 14B) — placeholder router."""

from fastapi import APIRouter

router = APIRouter(prefix="/photos", tags=["photos"])


# TODO: POST /photos/upload
# TODO: GET  /photos/{contract_id}/{claim_id}
# TODO: GET  /photos/{storage_key}/status
# TODO: POST /photos/{storage_key}/ask
