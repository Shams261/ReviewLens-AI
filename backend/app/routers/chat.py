import hashlib
import json
import re

from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session as DBSession

from app.database import get_db

limiter = Limiter(key_func=get_remote_address)
from app.models.schemas import ChatMessage, Review, Session
from app.services.scope_guard import classify_query, validate_output
from app.services.llm import build_system_prompt, call_llm, stream_llm
from app.services.deterministic import try_deterministic

router = APIRouter(prefix="/chat", tags=["chat"])

_CITATION_RE = re.compile(r"\[Review\s*#(\d+)\]", re.IGNORECASE)


def _hash_query(query: str, session_id: str) -> str:
    """SHA-256 hash of normalized query + session_id for cache key."""
    normalized = re.sub(r"\s+", " ", query.lower().strip())
    return hashlib.sha256(f"{session_id}:{normalized}".encode()).hexdigest()


class CitedReview(BaseModel):
    id: int
    rating: float
    title: str | None
    body: str
    author: str | None
    date: str | None
    verified: bool
    helpful_votes: int


class ChatRequest(BaseModel):
    session_id: str
    query: str


class ChatResponse(BaseModel):
    reply: str
    scope_status: str  # "in_scope", "out_of_scope"
    source: str        # "scope_guard", "deterministic", "groq", "gemini", or "cache"
    model: str = ""    # LLM model name when source is an LLM
    cited_reviews: list[CitedReview] = []
    cached: bool = False
    confidence: float = 0.0  # 0.0-1.0 confidence score


@router.post("/", response_model=ChatResponse)
@limiter.limit("10/minute")
async def send_message(
    request: Request,
    body: ChatRequest,
    db: DBSession = Depends(get_db),
):
    """Send a chat message and receive a guardrailed AI response."""

    # --- Validate session ---
    session = db.query(Session).filter(Session.id == body.session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    # --- Layer 2: Rule-based scope guard ---
    guard_result = classify_query(query, product_name=session.product_name)

    if guard_result.is_blocked:
        # Save both user message and the decline to chat history
        _save_message(db, session.id, "user", query, "out_of_scope")
        _save_message(db, session.id, "assistant", guard_result.reason, "out_of_scope")
        db.commit()

        return ChatResponse(
            reply=guard_result.reason,
            scope_status="out_of_scope",
            source="scope_guard",
            model="",
            confidence=1.0,
        )

    # --- Fetch reviews and build context ---
    reviews = (
        db.query(Review)
        .filter(Review.session_id == body.session_id)
        .order_by(Review.id)
        .all()
    )

    if not reviews:
        raise HTTPException(
            status_code=400,
            detail="No reviews found for this session. Ingest reviews first.",
        )

    # --- Cache lookup: check for a previous identical query in this session ---
    qhash = _hash_query(query, body.session_id)
    cached_msg = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == body.session_id,
            ChatMessage.query_hash == qhash,
            ChatMessage.role == "assistant",
            ChatMessage.scope_status == "in_scope",
        )
        .order_by(ChatMessage.id.desc())
        .first()
    )

    if cached_msg:
        # Cache hit — return the stored response without calling any LLM
        cited_ids_raw = json.loads(cached_msg.cited_reviews) if cached_msg.cited_reviews else []
        review_map = {r.id: r for r in reviews}
        cited_cards = [
            CitedReview(
                id=r.id, rating=r.rating, title=r.title, body=r.body[:300],
                author=r.author, date=r.date, verified=r.verified,
                helpful_votes=r.helpful_votes or 0,
            )
            for rid in cited_ids_raw if (r := review_map.get(rid))
        ]
        # Save the user message and a cached copy for history continuity
        _save_message(db, session.id, "user", query, "in_scope", query_hash=qhash)
        _save_message(
            db, session.id, "assistant", cached_msg.content, "in_scope",
            cited_ids=cited_ids_raw or None, query_hash=qhash, cached=True,
        )
        db.commit()

        return ChatResponse(
            reply=cached_msg.content,
            scope_status="in_scope",
            source="cache",
            model="",
            cited_reviews=cited_cards,
            cached=True,
            confidence=_compute_confidence(cached_msg.content, cited_ids_raw, len(reviews), "cache"),
        )

    # --- Deterministic fast path: answer simple queries without LLM ---
    det = try_deterministic(query, reviews, session.product_name)
    if det.matched:
        cited_ids, cited_cards = _extract_citations(det.text, reviews)
        _save_message(db, session.id, "user", query, "in_scope", query_hash=qhash)
        _save_message(db, session.id, "assistant", det.text, "in_scope", cited_ids, query_hash=qhash)
        db.commit()

        return ChatResponse(
            reply=det.text,
            scope_status="in_scope",
            source="deterministic",
            model="rule-engine",
            cited_reviews=cited_cards,
            confidence=det.confidence if det.confidence else _compute_confidence(det.text, cited_ids, len(reviews), "deterministic"),
        )

    # --- LLM path: build context and call with failover ---
    system_prompt = build_system_prompt(reviews, session.product_name, session.platform, user_query=query)

    # Load recent chat history for conversational context
    history_rows = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == body.session_id,
            ChatMessage.scope_status != "out_of_scope",
        )
        .order_by(ChatMessage.id)
        .all()
    )
    chat_history = [{"role": m.role, "content": m.content} for m in history_rows]

    try:
        llm_result = call_llm(system_prompt, query, chat_history)
    except RuntimeError:
        # --- Both LLMs failed: fall back to deterministic with relaxed matching ---
        fallback_text = _build_fallback_response(query, reviews, session.product_name)
        cited_ids, cited_cards = _extract_citations(fallback_text, reviews)
        _save_message(db, session.id, "user", query, "in_scope")
        # Do NOT store query_hash — prevents fallback from polluting the cache
        _save_message(db, session.id, "assistant", fallback_text, "in_scope", cited_ids)
        db.commit()

        return ChatResponse(
            reply=fallback_text,
            scope_status="in_scope",
            source="fallback",
            model="fallback",
            cited_reviews=cited_cards,
            confidence=_compute_confidence(fallback_text, cited_ids, len(reviews), "deterministic"),
        )

    # --- Layer 3: Output validation ---
    valid_review_ids = {r.id for r in reviews}
    output_check = validate_output(
        llm_result.text,
        product_name=session.product_name,
        review_ids=valid_review_ids,
    )

    if output_check.is_blocked:
        _save_message(db, session.id, "user", query, "out_of_scope")
        _save_message(db, session.id, "assistant", output_check.reason, "out_of_scope")
        db.commit()

        return ChatResponse(
            reply=output_check.reason,
            scope_status="out_of_scope",
            source="scope_guard",
            model="",
            confidence=1.0,
        )

    # --- Extract citations and save (with hash for future cache hits) ---
    cited_ids, cited_cards = _extract_citations(llm_result.text, reviews)
    _save_message(db, session.id, "user", query, "in_scope", query_hash=qhash)
    _save_message(db, session.id, "assistant", llm_result.text, "in_scope", cited_ids, query_hash=qhash)
    db.commit()

    return ChatResponse(
        reply=llm_result.text,
        scope_status="in_scope",
        source=llm_result.provider,
        model=llm_result.model,
        cited_reviews=cited_cards,
        confidence=_compute_confidence(llm_result.text, cited_ids, len(reviews), llm_result.provider),
    )


def _sse_event(data: dict) -> str:
    """Format a dict as an SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


@router.post("/stream")
@limiter.limit("10/minute")
async def stream_message(
    request: Request,
    body: ChatRequest,
    db: DBSession = Depends(get_db),
):
    """SSE streaming chat endpoint.

    Sends scope_guard/deterministic/cache responses as instant single events.
    Streams LLM responses token-by-token, then sends a final metadata event.

    Event types:
      - {"type": "meta", ...}       → instant full response (scope_guard/deterministic/cache)
      - {"type": "token", "content": "..."}  → streaming LLM chunk
      - {"type": "done", ...}       → final metadata after stream (citations, confidence, etc.)
      - {"type": "error", "detail": "..."} → error event
    """

    # --- Validate session ---
    session = db.query(Session).filter(Session.id == body.session_id).first()
    if not session:
        async def error_gen():
            yield _sse_event({"type": "error", "detail": "Session not found."})
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    query = body.query.strip()
    if not query:
        async def error_gen():
            yield _sse_event({"type": "error", "detail": "Query cannot be empty."})
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    reviews = (
        db.query(Review)
        .filter(Review.session_id == body.session_id)
        .order_by(Review.id)
        .all()
    )

    qhash = _hash_query(query, body.session_id)

    # --- Layer 2: Scope guard (instant) ---
    guard_result = classify_query(query, product_name=session.product_name)
    if guard_result.is_blocked:
        _save_message(db, session.id, "user", query, "out_of_scope")
        _save_message(db, session.id, "assistant", guard_result.reason, "out_of_scope")
        db.commit()

        # Build SSE event BEFORE generator — no ORM access inside generator
        event = _sse_event({
            "type": "meta",
            "reply": guard_result.reason,
            "scope_status": "out_of_scope",
            "source": "scope_guard",
            "model": "",
            "cited_reviews": [],
            "cached": False,
            "confidence": 1.0,
        })
        async def scope_gen():
            yield event
        return StreamingResponse(scope_gen(), media_type="text/event-stream")

    if not reviews:
        event = _sse_event({"type": "error", "detail": "No reviews found for this session."})
        async def error_gen():
            yield event
        return StreamingResponse(error_gen(), media_type="text/event-stream")

    # --- Cache hit (instant) ---
    cached_msg = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == body.session_id,
            ChatMessage.query_hash == qhash,
            ChatMessage.role == "assistant",
            ChatMessage.scope_status == "in_scope",
        )
        .order_by(ChatMessage.id.desc())
        .first()
    )

    if cached_msg:
        # Eagerly extract ORM data before commit expires the objects
        cached_content = cached_msg.content
        cited_ids_raw = json.loads(cached_msg.cited_reviews) if cached_msg.cited_reviews else []
        review_map = {r.id: r for r in reviews}
        cited_cards = [
            _cited_review_dict(review_map[rid])
            for rid in cited_ids_raw if rid in review_map
        ]
        _save_message(db, session.id, "user", query, "in_scope", query_hash=qhash)
        _save_message(db, session.id, "assistant", cached_content, "in_scope",
                      cited_ids=cited_ids_raw or None, query_hash=qhash, cached=True)
        db.commit()

        event = _sse_event({
            "type": "meta",
            "reply": cached_content,
            "scope_status": "in_scope",
            "source": "cache",
            "model": "",
            "cited_reviews": cited_cards,
            "cached": True,
            "confidence": _compute_confidence(cached_content, cited_ids_raw, len(reviews), "cache"),
        })
        async def cache_gen():
            yield event
        return StreamingResponse(cache_gen(), media_type="text/event-stream")

    # --- Deterministic fast path (instant) ---
    det = try_deterministic(query, reviews, session.product_name)
    if det.matched:
        cited_ids, cited_cards_obj = _extract_citations(det.text, reviews)
        cited_cards = [_cited_review_dict_from_obj(c) for c in cited_cards_obj]
        _save_message(db, session.id, "user", query, "in_scope", query_hash=qhash)
        _save_message(db, session.id, "assistant", det.text, "in_scope", cited_ids, query_hash=qhash)
        db.commit()

        event = _sse_event({
            "type": "meta",
            "reply": det.text,
            "scope_status": "in_scope",
            "source": "deterministic",
            "model": "rule-engine",
            "cited_reviews": cited_cards,
            "cached": False,
            "confidence": det.confidence if det.confidence else _compute_confidence(det.text, cited_ids, len(reviews), "deterministic"),
        })
        async def det_gen():
            yield event
        return StreamingResponse(det_gen(), media_type="text/event-stream")

    # --- LLM streaming path ---
    # Eagerly extract all ORM data into plain Python objects BEFORE the async
    # generator starts. The DB session may close between yields, so we cannot
    # access ORM attributes (session.product_name, r.body, etc.) inside the
    # generator — that causes DetachedInstanceError.
    session_id = session.id
    product_name = session.product_name
    platform = session.platform
    review_count = len(reviews)
    valid_review_ids = {r.id for r in reviews}

    # Snapshot reviews as plain dicts for use inside the generator
    reviews_snapshot = [
        {
            "id": r.id, "rating": r.rating, "title": r.title,
            "body": r.body, "author": r.author, "date": r.date,
            "verified": r.verified, "helpful_votes": r.helpful_votes or 0,
        }
        for r in reviews
    ]

    system_prompt = build_system_prompt(reviews, product_name, platform, user_query=query)

    history_rows = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.session_id == body.session_id,
            ChatMessage.scope_status != "out_of_scope",
        )
        .order_by(ChatMessage.id)
        .all()
    )
    chat_history = [{"role": m.role, "content": m.content} for m in history_rows]

    # Save user message before streaming starts
    _save_message(db, session_id, "user", query, "in_scope", query_hash=qhash)
    db.commit()

    async def llm_stream_gen():
        full_text = ""
        model_name = ""
        provider = ""

        try:
            async for chunk_text, m, p in stream_llm(system_prompt, query, chat_history):
                full_text += chunk_text
                model_name = m
                provider = p
                yield _sse_event({"type": "token", "content": chunk_text})
        except RuntimeError:
            # Both LLMs failed — build fallback from snapshot data
            fallback = _build_fallback_from_snapshot(query, reviews_snapshot, product_name)
            cited_ids = _extract_citation_ids(fallback)
            cited_cards = _build_cited_cards_from_snapshot(cited_ids, reviews_snapshot)
            # Do NOT store query_hash — prevents fallback from polluting the cache
            _save_message(db, session_id, "assistant", fallback, "in_scope", cited_ids)
            db.commit()
            yield _sse_event({
                "type": "meta",
                "reply": fallback,
                "scope_status": "in_scope",
                "source": "fallback",
                "model": "fallback",
                "cited_reviews": cited_cards,
                "cached": False,
                "confidence": _compute_confidence(fallback, cited_ids, review_count, "deterministic"),
            })
            return

        # --- Layer 3: Output validation ---
        output_check = validate_output(full_text, product_name=product_name, review_ids=valid_review_ids)

        if output_check.is_blocked:
            _save_message(db, session_id, "assistant", output_check.reason, "out_of_scope")
            db.commit()
            yield _sse_event({
                "type": "done",
                "reply": output_check.reason,
                "scope_status": "out_of_scope",
                "source": "scope_guard",
                "model": "",
                "cited_reviews": [],
                "cached": False,
                "confidence": 1.0,
                "replaced": True,
            })
            return

        # Extract citations from snapshot and save
        cited_ids = _extract_citation_ids(full_text)
        cited_cards = _build_cited_cards_from_snapshot(cited_ids, reviews_snapshot)
        _save_message(db, session_id, "assistant", full_text, "in_scope", cited_ids, query_hash=qhash)
        db.commit()

        yield _sse_event({
            "type": "done",
            "scope_status": "in_scope",
            "source": provider,
            "model": model_name,
            "cited_reviews": cited_cards,
            "cached": False,
            "confidence": _compute_confidence(full_text, cited_ids, review_count, provider),
        })

    return StreamingResponse(llm_stream_gen(), media_type="text/event-stream")


def _cited_review_dict(r) -> dict:
    """Convert a Review ORM object to a citation dict for SSE."""
    return {
        "id": r.id, "rating": r.rating, "title": r.title,
        "body": (r.body or "")[:300], "author": r.author,
        "date": r.date, "verified": r.verified,
        "helpful_votes": r.helpful_votes or 0,
    }


def _cited_review_dict_from_obj(c: CitedReview) -> dict:
    """Convert a CitedReview pydantic model to a plain dict for JSON."""
    return {
        "id": c.id, "rating": c.rating, "title": c.title,
        "body": c.body, "author": c.author, "date": c.date,
        "verified": c.verified, "helpful_votes": c.helpful_votes,
    }


def _extract_citation_ids(text: str) -> list[int]:
    """Extract [Review #ID] citation IDs from text (no ORM needed)."""
    return sorted(set(int(m.group(1)) for m in _CITATION_RE.finditer(text)))


def _build_cited_cards_from_snapshot(cited_ids: list[int], reviews_snapshot: list[dict]) -> list[dict]:
    """Build citation card dicts from plain review snapshot dicts."""
    review_map = {r["id"]: r for r in reviews_snapshot}
    return [
        {**review_map[rid], "body": (review_map[rid]["body"] or "")[:300]}
        for rid in cited_ids if rid in review_map
    ]


def _build_fallback_from_snapshot(query: str, reviews_snapshot: list[dict], product_name: str) -> str:
    """Build fallback response from snapshot dicts (no ORM access needed)."""
    n = len(reviews_snapshot)
    avg = sum(r["rating"] for r in reviews_snapshot) / n if n else 0
    positive = len([r for r in reviews_snapshot if r["rating"] >= 4.0])
    negative = len([r for r in reviews_snapshot if r["rating"] <= 2.0])
    verified = len([r for r in reviews_snapshot if r["verified"]])

    pos_reviews = sorted([r for r in reviews_snapshot if r["rating"] >= 4.0], key=lambda r: r["helpful_votes"], reverse=True)
    neg_reviews = sorted([r for r in reviews_snapshot if r["rating"] <= 2.0], key=lambda r: r["helpful_votes"], reverse=True)

    lines = [
        f"I couldn't connect to the AI service to fully analyze your question, but here's what I can tell you from the data for {product_name} ({n} reviews):\n",
        f"- Average rating: {avg:.1f}/5",
        f"- Positive reviews (4-5 stars): {positive}/{n} ({positive/n*100:.0f}%)",
        f"- Negative reviews (1-2 stars): {negative}/{n} ({negative/n*100:.0f}%)",
        f"- Verified purchases: {verified}/{n} ({verified/n*100:.0f}%)\n",
    ]

    if pos_reviews:
        r = pos_reviews[0]
        body = (r["body"] or "")[:150]
        lines.append(f"Top positive review [Review #{r['id']}]: \"{r['title']}\" — {body}{'...' if len(r['body'] or '') > 150 else ''}\n")

    if neg_reviews:
        r = neg_reviews[0]
        body = (r["body"] or "")[:150]
        lines.append(f"Top negative review [Review #{r['id']}]: \"{r['title']}\" — {body}{'...' if len(r['body'] or '') > 150 else ''}\n")

    lines.append("Try asking again in a moment — AI-powered analysis will resume when services are restored.")
    return "\n".join(lines)


@router.get("/history")
@limiter.limit("30/minute")
async def get_chat_history(
    request: Request,
    session_id: str = Query(..., description="Session UUID"),
    db: DBSession = Depends(get_db),
):
    """Return full chat history for a session."""
    session = db.query(Session).filter(Session.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id)
        .all()
    )

    return {
        "session_id": session_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "scope_status": m.scope_status,
                "cited_reviews": json.loads(m.cited_reviews) if m.cited_reviews else [],
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    }


def _build_fallback_response(query: str, reviews: list, product_name: str) -> str:
    """Build a useful response when both LLMs are unavailable.

    Provides a general review summary so the user still gets value.
    """
    n = len(reviews)
    avg = sum(r.rating for r in reviews) / n if n else 0
    positive = len([r for r in reviews if r.rating >= 4.0])
    negative = len([r for r in reviews if r.rating <= 2.0])
    verified = len([r for r in reviews if r.verified])

    # Find the most helpful positive and negative reviews
    pos_reviews = sorted([r for r in reviews if r.rating >= 4.0], key=lambda r: r.helpful_votes or 0, reverse=True)
    neg_reviews = sorted([r for r in reviews if r.rating <= 2.0], key=lambda r: r.helpful_votes or 0, reverse=True)

    lines = [
        f"I couldn't connect to the AI service to fully analyze your question, but here's what I can tell you from the data for {product_name} ({n} reviews):\n",
        f"- Average rating: {avg:.1f}/5",
        f"- Positive reviews (4-5 stars): {positive}/{n} ({positive/n*100:.0f}%)",
        f"- Negative reviews (1-2 stars): {negative}/{n} ({negative/n*100:.0f}%)",
        f"- Verified purchases: {verified}/{n} ({verified/n*100:.0f}%)\n",
    ]

    if pos_reviews:
        r = pos_reviews[0]
        body = (r.body or "")[:150]
        lines.append(f"Top positive review [Review #{r.id}]: \"{r.title}\" — {body}{'...' if len(r.body or '') > 150 else ''}\n")

    if neg_reviews:
        r = neg_reviews[0]
        body = (r.body or "")[:150]
        lines.append(f"Top negative review [Review #{r.id}]: \"{r.title}\" — {body}{'...' if len(r.body or '') > 150 else ''}\n")

    lines.append("Try asking again in a moment — AI-powered analysis will resume when services are restored.")
    return "\n".join(lines)


def _compute_confidence(
    reply: str,
    cited_ids: list[int],
    total_reviews: int,
    source: str,
) -> float:
    """Compute a 0.0-1.0 confidence score for a response.

    Factors:
    - Citation density: more valid citations → higher confidence
    - Source reliability: deterministic > cache > LLM
    - Response hedging: uncertainty phrases lower confidence
    - Review coverage: citing more of the total pool → higher confidence
    """
    if source == "scope_guard":
        return 1.0  # Scope guard decisions are deterministic

    score = 0.5  # Base confidence

    # Citation density bonus (up to +0.3)
    if cited_ids:
        citation_ratio = min(len(cited_ids) / max(total_reviews, 1), 1.0)
        score += citation_ratio * 0.3
    else:
        score -= 0.1  # No citations = less trustworthy

    # Source bonus
    if source == "deterministic":
        score += 0.2  # Pure data, no hallucination risk
    elif source == "cache":
        score += 0.15  # Previously validated response

    # Hedging penalty
    reply_lower = reply.lower()
    hedging_phrases = [
        "i don't have enough data",
        "could you rephrase",
        "not enough information",
        "unclear",
        "i'm not sure",
        "cannot determine",
        "difficult to say",
    ]
    if any(phrase in reply_lower for phrase in hedging_phrases):
        score -= 0.15

    # Short reply penalty (very short = likely low quality)
    if len(reply) < 50 and source not in ("scope_guard", "deterministic"):
        score -= 0.1

    return round(max(0.0, min(1.0, score)), 2)


def _extract_citations(text: str, reviews: list[Review]) -> tuple[list[int], list[CitedReview]]:
    """Parse [Review #ID] citations from text and return matching review data."""
    cited_ids = sorted(set(int(m.group(1)) for m in _CITATION_RE.finditer(text)))
    review_map = {r.id: r for r in reviews}

    cited = []
    for rid in cited_ids:
        r = review_map.get(rid)
        if r:
            cited.append(CitedReview(
                id=r.id,
                rating=r.rating,
                title=r.title,
                body=r.body[:300],  # truncate for payload size
                author=r.author,
                date=r.date,
                verified=r.verified,
                helpful_votes=r.helpful_votes or 0,
            ))
    return cited_ids, cited


def _save_message(
    db: DBSession,
    session_id: str,
    role: str,
    content: str,
    scope_status: str,
    cited_ids: list[int] | None = None,
    query_hash: str | None = None,
    cached: bool = False,
) -> None:
    db.add(
        ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            scope_status=scope_status,
            cited_reviews=json.dumps(cited_ids) if cited_ids else None,
            query_hash=query_hash,
            cached=cached,
        )
    )
