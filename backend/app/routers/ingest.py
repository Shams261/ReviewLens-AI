import json
import os

from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session as DBSession

from app.database import get_db

limiter = Limiter(key_func=get_remote_address)
from app.models.schemas import Review
from app.services.ingestion import (
    create_session,
    generate_demo_reviews,
    parse_csv_reviews,
)
from app.services.scraper import (
    validate_amazon_url,
    extract_product_name,
    scrape_amazon_reviews,
    scrape_with_rapidapi,
)

router = APIRouter(prefix="/ingest", tags=["ingestion"])


class UrlRequest(BaseModel):
    url: str
    max_reviews: int = 200


@router.post("/url")
@limiter.limit("3/minute")
async def ingest_from_url(
    request: Request,
    body: UrlRequest,
    db: DBSession = Depends(get_db),
):
    """Scrape reviews from an Amazon product URL.

    Tries Scrapingdog API first, falls back to direct scrape.
    Returns session_id and review count on success.
    """
    # Validate URL and extract ASIN + domain
    try:
        asin, domain = validate_amazon_url(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    product_name = extract_product_name(body.url)

    # Scrape reviews
    try:
        raw_reviews = await scrape_amazon_reviews(asin, domain=domain)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not raw_reviews:
        raise HTTPException(
            status_code=422,
            detail="No reviews found for this product. Try uploading a CSV instead.",
        )

    # Cap review count
    raw_reviews = raw_reviews[: body.max_reviews]

    # Create session and store reviews
    session = create_session(
        db, product_name=product_name, platform="amazon", product_url=body.url
    )

    for r in raw_reviews:
        db.add(
            Review(
                session_id=session.id,
                rating=r["rating"],
                title=r.get("title", ""),
                body=r["body"],
                author=r.get("author", ""),
                date=r.get("date", ""),
                verified=r.get("verified", False),
                helpful_votes=r.get("helpful_votes", 0),
            )
        )

    db.commit()

    return {
        "session_id": session.id,
        "product_name": session.product_name,
        "platform": session.platform,
        "review_count": len(raw_reviews),
        "source": "url_scrape",
        "asin": asin,
    }


@router.post("/url/stream")
@limiter.limit("3/minute")
async def ingest_from_url_stream(
    request: Request,
    body: UrlRequest,
    db: DBSession = Depends(get_db),
):
    """Scrape reviews with SSE progress updates.

    Events:
      {"type": "progress", "page": 1, "reviews_found": 10, "max_pages": 5}
      {"type": "done", "session_id": "...", "product_name": "...", "review_count": 40, ...}
      {"type": "error", "detail": "..."}
    """
    import asyncio

    # Validate URL synchronously before streaming
    try:
        asin, domain = validate_amazon_url(body.url)
    except ValueError as exc:
        event = f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"
        async def err():
            yield event
        return StreamingResponse(err(), media_type="text/event-stream")

    product_name = extract_product_name(body.url)

    if not os.getenv("RAPIDAPI_KEY"):
        event = f"data: {json.dumps({'type': 'error', 'detail': 'RAPIDAPI_KEY not configured. Upload a CSV or use demo data.'})}\n\n"
        async def err():
            yield event
        return StreamingResponse(err(), media_type="text/event-stream")

    # Use asyncio.Queue so progress events are yielded in real-time
    queue: asyncio.Queue = asyncio.Queue()

    async def on_progress(page: int, total: int, max_pages: int):
        await queue.put(json.dumps({
            "type": "progress",
            "page": page,
            "reviews_found": total,
            "max_pages": max_pages,
        }))

    async def scrape_task():
        """Run scraping in background, push events to queue."""
        try:
            raw_reviews = await scrape_with_rapidapi(
                asin, domain=domain, on_progress=on_progress,
            )
            await queue.put(("result", raw_reviews))
        except RuntimeError as exc:
            await queue.put(("error", str(exc)))
        except Exception as exc:
            await queue.put(("error", str(exc)))

    async def stream_gen():
        # Start scraping as a concurrent task
        task = asyncio.create_task(scrape_task())

        # Send initial event
        yield f"data: {json.dumps({'type': 'progress', 'page': 0, 'reviews_found': 0, 'max_pages': 5, 'message': 'Validating URL and starting scrape...'})}\n\n"

        # Stream progress events as they arrive
        while True:
            item = await queue.get()

            # Progress string events
            if isinstance(item, str):
                yield f"data: {item}\n\n"
                continue

            # Final result tuple
            kind, payload = item
            if kind == "error":
                yield f"data: {json.dumps({'type': 'error', 'detail': payload})}\n\n"
                return

            # kind == "result"
            raw_reviews = payload
            break

        await task  # ensure task is done

        if not raw_reviews:
            yield f"data: {json.dumps({'type': 'error', 'detail': 'No reviews found for this product. Try uploading a CSV instead.'})}\n\n"
            return

        # Cap reviews
        raw_reviews = raw_reviews[: body.max_reviews]

        # Saving to DB event
        yield f"data: {json.dumps({'type': 'progress', 'page': -1, 'reviews_found': len(raw_reviews), 'max_pages': 0, 'message': 'Saving reviews to database...'})}\n\n"

        # Store in DB
        session = create_session(
            db, product_name=product_name, platform="amazon", product_url=body.url
        )
        session_id = session.id
        session_product_name = session.product_name
        session_platform = session.platform

        for r in raw_reviews:
            db.add(Review(
                session_id=session_id,
                rating=r["rating"],
                title=r.get("title", ""),
                body=r["body"],
                author=r.get("author", ""),
                date=r.get("date", ""),
                verified=r.get("verified", False),
                helpful_votes=r.get("helpful_votes", 0),
            ))

        db.commit()

        yield f"data: {json.dumps({'type': 'done', 'session_id': session_id, 'product_name': session_product_name, 'platform': session_platform, 'review_count': len(raw_reviews), 'source': 'url_scrape', 'asin': asin})}\n\n"

    return StreamingResponse(stream_gen(), media_type="text/event-stream")


@router.post("/csv")
@limiter.limit("5/minute")
async def ingest_from_csv(
    request: Request,
    file: UploadFile = File(...),
    product_name: str = "Unknown Product",
    db: DBSession = Depends(get_db),
):
    """Upload a CSV file containing product reviews.

    Expected columns (flexible naming):
      Required: rating, text (or body/review)
      Optional: title, date, author, verified, helpful_votes
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="File must be a .csv file.",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Cap file size at 5 MB
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5 MB.")

    session = create_session(
        db, product_name=product_name, platform="amazon", product_url="csv_upload"
    )

    try:
        count = parse_csv_reviews(content, session.id, db)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))

    db.commit()

    return {
        "session_id": session.id,
        "product_name": session.product_name,
        "platform": session.platform,
        "review_count": count,
        "source": "csv_upload",
    }


@router.post("/demo")
@limiter.limit("5/minute")
async def ingest_demo(request: Request, db: DBSession = Depends(get_db)):
    """Load 50 pre-built AirPods Pro reviews for instant demo."""
    session = create_session(
        db,
        product_name="Apple AirPods Pro (2nd Gen)",
        platform="amazon",
        product_url="demo",
    )

    count = generate_demo_reviews(session.id, db)
    db.commit()

    return {
        "session_id": session.id,
        "product_name": session.product_name,
        "platform": session.platform,
        "review_count": count,
        "source": "demo",
    }
