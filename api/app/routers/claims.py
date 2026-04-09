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
        conditions.append("""
            (c.gemini_analysis->'tire_brands_detected'->>'current') IS DISTINCT FROM
            (c.gemini_analysis->'tire_brands_detected'->'previous'->>0)
        """)
    if has_web_match is True:
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
    nulls = "NULLS LAST" if sort_dir == "desc" else "NULLS FIRST"

    # Count
    count_q = text(f"SELECT COUNT(*) FROM claims c {where}")
    total = db.execute(count_q, params).scalar()

    # Data
    offset = (page - 1) * per_page
    params["limit"] = per_page
    params["offset"] = offset

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
            c.processed_at
        FROM claims c
        {where}
        ORDER BY {order_col} {order_dir} {nulls}
        LIMIT :limit OFFSET :offset
    """)

    rows = db.execute(data_q, params).fetchall()

    claims = []
    for row in rows:
        claims.append({
            "id": row[0],
            "contract_id": row[1],
            "claim_id": row[2],
            "claim_date": str(row[3]) if row[3] else None,
            "reported_loss_date": str(row[4]) if row[4] else None,
            "service_drive_location": row[5],
            "risk_score": row[6],
            "red_flags": row[7] or [],
            "recommendation": row[8],
            "current_tire_brand": row[9],
            "current_vehicle_color": row[10],
            "exact_web_matches": row[11],
            "processed_at": str(row[12]) if row[12] else None,
        })

    return {
        "items": claims,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }


@router.get("/{claim_db_id}")
def get_claim_detail(
    claim_db_id: int,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    """Single claim detail with photos, full analysis, and red flags."""
    row = db.execute(
        text("""
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
            WHERE c.id = :id
        """),
        {"id": claim_db_id},
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Claim not found")

    # Also fetch processed photos for this claim
    photos = db.execute(
        text("""
            SELECT storage_key, status, processed_at
            FROM processed_photos
            WHERE contract_id = :cid AND claim_id = :clid
            ORDER BY processed_at DESC
        """),
        {"cid": row[1], "clid": row[2]},
    ).fetchall()

    # Also fetch contract history for context
    history = db.execute(
        text("""
            SELECT id, claim_id, claim_date, risk_score, red_flags
            FROM claims
            WHERE contract_id = :cid AND id != :id
            ORDER BY claim_date DESC
            LIMIT 10
        """),
        {"cid": row[1], "id": claim_db_id},
    ).fetchall()

    return {
        "id": row[0],
        "contract_id": row[1],
        "claim_id": row[2],
        "claim_date": str(row[3]) if row[3] else None,
        "reported_loss_date": str(row[4]) if row[4] else None,
        "service_drive_location": row[5],
        "service_drive_coords": row[6],
        "photo_uris": row[7] or [],
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
            }
            for p in photos
        ],
        "contract_history": [
            {
                "id": h[0],
                "claim_id": h[1],
                "claim_date": str(h[2]) if h[2] else None,
                "risk_score": h[3],
                "red_flags": h[4] or [],
            }
            for h in history
        ],
    }
