"""Error logs query endpoints — no auth required.

GET /errors       — paginated list with filters, newest first
GET /errors/stats — aggregate counts by error_type and pipeline_stage
"""

from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import Depends

from app.database import get_db

router = APIRouter(prefix="/errors", tags=["errors"])


@router.get("")
def list_errors(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    service: Optional[str] = None,
    error_type: Optional[str] = None,
    pipeline_stage: Optional[str] = None,
    since: Optional[str] = Query(None, description="ISO date/datetime, e.g. 2026-04-01"),
    until: Optional[str] = Query(None, description="ISO date/datetime, e.g. 2026-04-10"),
    db: Session = Depends(get_db),
):
    """Paginated error logs, newest first. No auth — for scripts and Claude Code."""
    conditions = []
    params: dict = {}

    if service:
        conditions.append("e.service = :service")
        params["service"] = service
    if error_type:
        conditions.append("e.error_type = :error_type")
        params["error_type"] = error_type
    if pipeline_stage:
        conditions.append("e.pipeline_stage = :pipeline_stage")
        params["pipeline_stage"] = pipeline_stage
    if since:
        conditions.append("e.timestamp >= :since")
        params["since"] = since
    if until:
        conditions.append("e.timestamp <= :until")
        params["until"] = until

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    total = db.execute(text(f"SELECT COUNT(*) FROM error_logs e {where}"), params).scalar()

    offset = (page - 1) * per_page
    params["limit"] = per_page
    params["offset"] = offset

    rows = db.execute(
        text(f"""
            SELECT
                e.id, e.timestamp, e.service, e.endpoint, e.method,
                e.status_code, e.error_type, e.message, e.traceback,
                e.request_id, e.pipeline_stage
            FROM error_logs e
            {where}
            ORDER BY e.timestamp DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    ).fetchall()

    items = []
    for r in rows:
        items.append({
            "id": r[0],
            "timestamp": str(r[1]) if r[1] else None,
            "service": r[2],
            "endpoint": r[3],
            "method": r[4],
            "status_code": r[5],
            "error_type": r[6],
            "message": r[7],
            "traceback": r[8],
            "request_id": r[9],
            "pipeline_stage": r[10],
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page if total else 0,
    }


@router.get("/stats")
def error_stats(
    service: Optional[str] = None,
    since: Optional[str] = Query(None, description="ISO date/datetime"),
    db: Session = Depends(get_db),
):
    """Aggregate error counts by error_type and pipeline_stage."""
    conditions = []
    params: dict = {}

    if service:
        conditions.append("e.service = :service")
        params["service"] = service
    if since:
        conditions.append("e.timestamp >= :since")
        params["since"] = since

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    # By error_type
    by_type = db.execute(
        text(f"""
            SELECT e.error_type, COUNT(*) AS cnt
            FROM error_logs e {where}
            GROUP BY e.error_type
            ORDER BY cnt DESC
        """),
        params,
    ).fetchall()

    # By pipeline_stage (only non-null)
    stage_conditions = list(conditions) + ["e.pipeline_stage IS NOT NULL"]
    stage_where = "WHERE " + " AND ".join(stage_conditions)

    by_stage = db.execute(
        text(f"""
            SELECT e.pipeline_stage, COUNT(*) AS cnt
            FROM error_logs e {stage_where}
            GROUP BY e.pipeline_stage
            ORDER BY cnt DESC
        """),
        params,
    ).fetchall()

    # By service
    by_service = db.execute(
        text(f"""
            SELECT e.service, COUNT(*) AS cnt
            FROM error_logs e {where}
            GROUP BY e.service
            ORDER BY cnt DESC
        """),
        params,
    ).fetchall()

    total = db.execute(text(f"SELECT COUNT(*) FROM error_logs e {where}"), params).scalar()

    return {
        "total": total,
        "by_error_type": [{"error_type": r[0], "count": r[1]} for r in by_type],
        "by_pipeline_stage": [{"pipeline_stage": r[0], "count": r[1]} for r in by_stage],
        "by_service": [{"service": r[0], "count": r[1]} for r in by_service],
    }
