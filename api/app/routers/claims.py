"""Claims endpoints (Section 14C).

GET /claims — paginated list with filters and risk sorting
GET /claims/{id} — single claim detail with photos, analysis, red flags
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user

router = APIRouter(prefix="/claims", tags=["claims"])


def _is_sqlite(db: Session) -> bool:
    """Return True if the session is backed by SQLite."""
    return db.bind.dialect.name == "sqlite"


def _derive_status(processed_at, risk_score) -> str:
    """Derive a display status from processed_at and risk_score."""
    if not processed_at:
        return "pending"
    if risk_score is not None and risk_score > 50:
        return "flagged"
    return "processed"


@router.get("")
def list_claims(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    risk_min: Optional[float] = Query(None, ge=0, le=100),
    risk_max: Optional[float] = Query(None, ge=0, le=100),
    contract_id: Optional[str] = None,
    tire_changed: Optional[bool] = None,
    has_web_match: Optional[bool] = None,
    sort_by: str = Query("risk_score", pattern="^(risk_score|claim_date|processed_at)$"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Paginated claims list with filters and risk sorting."""
    sqlite = _is_sqlite(db)
    conditions = []
    params: dict = {}

    if risk_min is not None:
        conditions.append("c.risk_score >= :risk_min")
        params["risk_min"] = risk_min
    if risk_max is not None:
        conditions.append("c.risk_score <= :risk_max")
        params["risk_max"] = risk_max
    if contract_id:
        conditions.append("c.contract_id = :contract_id")
        params["contract_id"] = contract_id
    if tire_changed is True:
        if sqlite:
            conditions.append("""
                json_extract(c.gemini_analysis, '$.tire_brands_detected.current')
                IS NOT json_extract(c.gemini_analysis, '$.tire_brands_detected.previous[0]')
            """)
        else:
            conditions.append("""
                (c.gemini_analysis->'tire_brands_detected'->>'current') IS DISTINCT FROM
                (c.gemini_analysis->'tire_brands_detected'->'previous'->>0)
            """)
    if has_web_match is True:
        if sqlite:
            conditions.append("""
                json_array_length(
                    COALESCE(json_extract(c.reverse_image_results, '$.full_matching_images'), '[]')
                ) > 0
            """)
        else:
            conditions.append("""
                jsonb_array_length(
                    COALESCE(c.reverse_image_results->'full_matching_images', '[]'::jsonb)
                ) > 0
            """)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Allowlisted sort columns
    sort_col_map = {
        "risk_score": "c.risk_score",
        "claim_date": "c.claim_date",
        "processed_at": "c.processed_at",
    }
    order_col = sort_col_map[sort_by]
    order_dir = "DESC" if sort_dir == "desc" else "ASC"
    # SQLite does not support NULLS LAST/FIRST; use a CASE expression instead
    if sqlite:
        nulls_prefix = f"CASE WHEN {order_col} IS NULL THEN 1 ELSE 0 END,"
        nulls_suffix = ""
    else:
        nulls_prefix = ""
        nulls_suffix = "NULLS LAST" if sort_dir == "desc" else "NULLS FIRST"

    # Count
    count_q = text(f"SELECT COUNT(*) FROM claims c {where}")
    total = db.execute(count_q, params).scalar()

    # Data
    offset = (page - 1) * per_page
    params["limit"] = per_page
    params["offset"] = offset

    if sqlite:
        # SQLite: use json_extract for JSON fields; these may be NULL if the
        # JSON columns are empty, which is fine for display purposes.
        data_q = text(f"""
            SELECT
                c.id,
                c.contract_id,
                c.claim_id,
                c.claim_date,
                c.reported_loss_date,
                c.service_drive_location,
                c.risk_score,
                c.red_flags,
                json_extract(c.gemini_analysis, '$.recommendation') AS recommendation,
                json_extract(c.gemini_analysis, '$.tire_brands_detected.current') AS current_tire_brand,
                json_extract(c.gemini_analysis, '$.vehicle_colors_detected.current') AS current_vehicle_color,
                json_array_length(
                    COALESCE(json_extract(c.reverse_image_results, '$.full_matching_images'), '[]')
                ) AS exact_web_matches,
                c.processed_at,
                COALESCE(json_array_length(c.photo_uris), 0) AS photo_count
            FROM claims c
            {where}
            ORDER BY {nulls_prefix} {order_col} {order_dir}
            LIMIT :limit OFFSET :offset
        """)
    else:
        data_q = text(f"""
            SELECT
                c.id,
                c.contract_id,
                c.claim_id,
                c.claim_date,
                c.reported_loss_date,
                c.service_drive_location,
                c.risk_score,
                c.red_flags,
                c.gemini_analysis->>'recommendation' AS recommendation,
                c.gemini_analysis->'tire_brands_detected'->>'current' AS current_tire_brand,
                c.gemini_analysis->'vehicle_colors_detected'->>'current' AS current_vehicle_color,
                jsonb_array_length(
                    COALESCE(c.reverse_image_results->'full_matching_images', '[]'::jsonb)
                ) AS exact_web_matches,
                c.processed_at,
                COALESCE(array_length(c.photo_uris, 1), 0) AS photo_count
            FROM claims c
            {where}
            ORDER BY {nulls_prefix} {order_col} {order_dir} {nulls_suffix}
            LIMIT :limit OFFSET :offset
        """)

    rows = db.execute(data_q, params).fetchall()

    claims = []
    for row in rows:
        claim_date_str = str(row[3]) if row[3] else None
        processed_at_str = str(row[12]) if row[12] else None
        claims.append({
            "id": row[0],
            "contract_id": row[1],
            "claim_id": row[2],
            "claim_date": claim_date_str,
            "submission_date": claim_date_str,
            "reported_loss_date": str(row[4]) if row[4] else None,
            "service_drive_location": row[5],
            "risk_score": row[6],
            "status": _derive_status(row[12], row[6]),
            "red_flags": row[7] or [],
            "recommendation": row[8],
            "current_tire_brand": row[9],
            "current_vehicle_color": row[10],
            "exact_web_matches": row[11],
            "processed_at": processed_at_str,
            "photo_count": row[13] or 0,
        })

    return {
        "items": claims,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }


def _build_claim_detail(row, db: Session):
    """Shared detail builder used by both lookup-by-id and lookup-by-ids routes."""
    claim_date_str = str(row[3]) if row[3] else None
    photo_uris = row[7] or []

    # Fetch processed photos for this claim
    photos = db.execute(
        text("""
            SELECT storage_key, status, processed_at
            FROM processed_photos
            WHERE contract_id = :cid AND claim_id = :clid
            ORDER BY processed_at DESC
        """),
        {"cid": row[1], "clid": row[2]},
    ).fetchall()

    # Fetch contract history for context
    history = db.execute(
        text("""
            SELECT id, claim_id, claim_date, risk_score, red_flags, processed_at, photo_uris
            FROM claims
            WHERE contract_id = :cid AND id != :id
            ORDER BY claim_date DESC
            LIMIT 10
        """),
        {"cid": row[1], "id": row[0]},
    ).fetchall()

    return {
        "id": row[0],
        "contract_id": row[1],
        "claim_id": row[2],
        "claim_date": claim_date_str,
        "submission_date": claim_date_str,
        "reported_loss_date": str(row[4]) if row[4] else None,
        "service_drive_location": row[5],
        "service_drive_coords": row[6],
        "photo_uris": photo_uris,
        "photo_count": len(photo_uris),
        "status": _derive_status(row[13], row[11]),
        "extracted_metadata": row[8],
        "reverse_image_results": row[9],
        "gemini_analysis": row[10],
        "risk_score": row[11],
        "red_flags": row[12] or [],
        "processed_at": str(row[13]) if row[13] else None,
        "photos": [
            {
                "storage_key": p[0],
                "status": p[1],
                "processed_at": str(p[2]) if p[2] else None,
                "url": f"/api/photos/serve/{p[0]}",
            }
            for p in photos
        ],
        "contract_history": [
            {
                "id": h[0],
                "claim_id": h[1],
                "claim_date": str(h[2]) if h[2] else None,
                "submission_date": str(h[2]) if h[2] else None,
                "risk_score": h[3],
                "red_flags": h[4] or [],
                "status": _derive_status(h[5], h[3]),
                "photo_count": len(h[6]) if h[6] else 0,
            }
            for h in history
        ],
    }


_DETAIL_SQL = """
    SELECT
        c.id,
        c.contract_id,
        c.claim_id,
        c.claim_date,
        c.reported_loss_date,
        c.service_drive_location,
        c.service_drive_coords,
        c.photo_uris,
        c.extracted_metadata,
        c.reverse_image_results,
        c.gemini_analysis,
        c.risk_score,
        c.red_flags,
        c.processed_at
    FROM claims c
"""


@router.get("/{contract_id}/{claim_id}")
def get_claim_by_ids(
    contract_id: str,
    claim_id: str,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Claim detail looked up by contract_id + claim_id (used by dashboard)."""
    row = db.execute(
        text(_DETAIL_SQL + " WHERE c.contract_id = :cid AND c.claim_id = :clid"),
        {"cid": contract_id, "clid": claim_id},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Claim not found")

    return _build_claim_detail(row, db)


@router.get("/{claim_db_id}")
def get_claim_detail(
    claim_db_id: int,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Single claim detail by database ID."""
    row = db.execute(
        text(_DETAIL_SQL + " WHERE c.id = :id"),
        {"id": claim_db_id},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Claim not found")

    return _build_claim_detail(row, db)
