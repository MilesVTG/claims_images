"""Dashboard endpoints (Section 14D).

GET /dashboard/summary — totals, high-risk count, processing stats
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


def _is_sqlite(db: Session) -> bool:
    """Return True if the session is backed by SQLite."""
    return db.bind.dialect.name == "sqlite"


@router.get("/summary")
def dashboard_summary(db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    """Dashboard summary: totals, high-risk count, processing stats.

    Aggregates data across claims and processed_photos tables.
    """
    sqlite = _is_sqlite(db)

    # Overall claim stats — use SUM(CASE ...) for SQLite compat (no FILTER)
    if sqlite:
        claim_stats = db.execute(text("""
            SELECT
                COUNT(*) AS total_claims,
                SUM(CASE WHEN risk_score >= 70 THEN 1 ELSE 0 END) AS high_risk_count,
                SUM(CASE WHEN risk_score BETWEEN 40 AND 69 THEN 1 ELSE 0 END) AS medium_risk_count,
                SUM(CASE WHEN risk_score < 40 OR risk_score IS NULL THEN 1 ELSE 0 END) AS low_risk_count,
                ROUND(AVG(risk_score), 1) AS avg_risk_score,
                SUM(CASE WHEN json_array_length(
                    COALESCE(json_extract(reverse_image_results, '$.full_matching_images'), '[]')
                ) > 0 THEN 1 ELSE 0 END) AS claims_with_web_matches,
                SUM(CASE WHEN gemini_analysis IS NOT NULL THEN 1 ELSE 0 END) AS analyzed_count,
                SUM(CASE WHEN gemini_analysis IS NULL THEN 1 ELSE 0 END) AS pending_analysis_count
            FROM claims
        """)).fetchone()
    else:
        claim_stats = db.execute(text("""
            SELECT
                COUNT(*) AS total_claims,
                COUNT(*) FILTER (WHERE risk_score >= 70) AS high_risk_count,
                COUNT(*) FILTER (WHERE risk_score BETWEEN 40 AND 69) AS medium_risk_count,
                COUNT(*) FILTER (WHERE risk_score < 40 OR risk_score IS NULL) AS low_risk_count,
                ROUND(AVG(risk_score)::numeric, 1) AS avg_risk_score,
                COUNT(*) FILTER (WHERE
                    jsonb_array_length(
                        COALESCE(reverse_image_results->'full_matching_images', '[]'::jsonb)
                    ) > 0
                ) AS claims_with_web_matches,
                COUNT(*) FILTER (WHERE gemini_analysis IS NOT NULL) AS analyzed_count,
                COUNT(*) FILTER (WHERE gemini_analysis IS NULL) AS pending_analysis_count
            FROM claims
        """)).fetchone()

    # Photo processing stats
    if sqlite:
        photo_stats = db.execute(text("""
            SELECT
                COUNT(*) AS total_photos,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_photos,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) AS pending_photos,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_photos
            FROM processed_photos
        """)).fetchone()
    else:
        photo_stats = db.execute(text("""
            SELECT
                COUNT(*) AS total_photos,
                COUNT(*) FILTER (WHERE status = 'completed') AS completed_photos,
                COUNT(*) FILTER (WHERE status = 'pending') AS pending_photos,
                COUNT(*) FILTER (WHERE status = 'failed') AS failed_photos
            FROM processed_photos
        """)).fetchone()

    # Today's processing
    if sqlite:
        today_stats = db.execute(text("""
            SELECT
                COUNT(*) AS claims_today,
                SUM(CASE WHEN risk_score >= 70 THEN 1 ELSE 0 END) AS high_risk_today,
                ROUND(AVG(risk_score), 1) AS avg_risk_today
            FROM claims
            WHERE DATE(processed_at) = DATE('now')
        """)).fetchone()
    else:
        today_stats = db.execute(text("""
            SELECT
                COUNT(*) AS claims_today,
                COUNT(*) FILTER (WHERE risk_score >= 70) AS high_risk_today,
                ROUND(AVG(risk_score)::numeric, 1) AS avg_risk_today
            FROM claims
            WHERE DATE(processed_at) = CURRENT_DATE
        """)).fetchone()

    # Recent high-risk claims (top 5)
    recent_high_risk = db.execute(text("""
        SELECT id, contract_id, claim_id, risk_score, red_flags, processed_at
        FROM claims
        WHERE risk_score >= 70
        ORDER BY processed_at DESC
        LIMIT 5
    """)).fetchall()

    return {
        "claims": {
            "total": claim_stats[0],
            "high_risk": claim_stats[1] or 0,
            "medium_risk": claim_stats[2] or 0,
            "low_risk": claim_stats[3] or 0,
            "avg_risk_score": float(claim_stats[4]) if claim_stats[4] else None,
            "with_web_matches": claim_stats[5] or 0,
            "analyzed": claim_stats[6] or 0,
            "pending_analysis": claim_stats[7] or 0,
        },
        "photos": {
            "total": photo_stats[0],
            "completed": photo_stats[1] or 0,
            "pending": photo_stats[2] or 0,
            "failed": photo_stats[3] or 0,
        },
        "today": {
            "claims_processed": today_stats[0],
            "high_risk": today_stats[1] or 0,
            "avg_risk_score": float(today_stats[2]) if today_stats[2] else None,
        },
        "recent_high_risk": [
            {
                "id": r[0],
                "contract_id": r[1],
                "claim_id": r[2],
                "risk_score": r[3],
                "red_flags": r[4] or [],
                "processed_at": str(r[5]) if r[5] else None,
            }
            for r in recent_high_risk
        ],
    }
