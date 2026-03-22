from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models.schemas import Review, Session
from app.services.analytics import compute_summary

limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.get("/")
@limiter.limit("30/minute")
async def get_reviews(
    request: Request,
    session_id: str = Query(..., description="Session UUID"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: DBSession = Depends(get_db),
):
    """Return paginated reviews for a session."""
    _assert_session_exists(session_id, db)

    offset = (page - 1) * limit
    reviews = (
        db.query(Review)
        .filter(Review.session_id == session_id)
        .order_by(Review.id)
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = db.query(Review).filter(Review.session_id == session_id).count()

    return {
        "reviews": [_serialize_review(r) for r in reviews],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/summary")
@limiter.limit("30/minute")
async def get_summary(
    request: Request,
    session_id: str = Query(..., description="Session UUID"),
    db: DBSession = Depends(get_db),
):
    """Return analytics summary for a session's reviews."""
    session = _assert_session_exists(session_id, db)
    summary = compute_summary(session_id, db)

    return {
        "session_id": session_id,
        "product_name": session.product_name,
        "platform": session.platform,
        **summary,
    }


def _assert_session_exists(session_id: str, db: DBSession) -> Session:
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")
    return session


def _serialize_review(r: Review) -> dict:
    return {
        "id": r.id,
        "rating": r.rating,
        "title": r.title,
        "body": r.body,
        "author": r.author,
        "date": r.date,
        "verified": r.verified,
        "helpful_votes": r.helpful_votes,
    }
