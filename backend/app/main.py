import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.database import init_db
from app.routers import chat, health, ingest, reviews

load_dotenv()

# ---------------------------------------------------------------------------
# Rate limiter — protects free-tier API credits (Groq, Gemini, RapidAPI)
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database tables on startup."""
    init_db()
    yield


app = FastAPI(
    title="ReviewLens AI",
    description="Review Intelligence Portal — Analyze product reviews with guardrailed AI",
    version="0.1.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration
cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router, prefix="/api")
app.include_router(ingest.router, prefix="/api")
app.include_router(reviews.router, prefix="/api")
app.include_router(chat.router, prefix="/api")

# Alias: GET /api/summary → /api/reviews/summary (matches planned API contract)
from fastapi import Query, Depends
from app.database import get_db
from sqlalchemy.orm import Session as DBSession
from app.routers.reviews import _assert_session_exists
from app.services.analytics import compute_summary


@app.get("/api/summary", tags=["reviews"])
async def summary_alias(
    session_id: str = Query(..., description="Session UUID"),
    db: DBSession = Depends(get_db),
):
    """Alias for /api/reviews/summary to match planned API contract."""
    session = _assert_session_exists(session_id, db)
    summary = compute_summary(session_id, db)
    return {
        "session_id": session_id,
        "product_name": session.product_name,
        "platform": session.platform,
        **summary,
    }
