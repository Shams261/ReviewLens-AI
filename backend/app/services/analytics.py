"""Analytics engine — computes summary statistics from ingested reviews."""

import math
import re
from collections import Counter

from sqlalchemy.orm import Session as DBSession

from app.models.schemas import Review

# Stop words to exclude from keyword extraction
_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "i", "me", "my", "we", "our", "you", "your", "he", "she", "it",
    "they", "them", "his", "her", "its", "this", "that", "these", "those",
    "of", "in", "to", "for", "with", "on", "at", "from", "by", "about",
    "as", "into", "through", "during", "before", "after", "above",
    "and", "but", "or", "nor", "not", "so", "very", "just", "than",
    "too", "also", "if", "then", "because", "while", "where", "when",
    "what", "which", "who", "whom", "how", "all", "each", "every",
    "both", "few", "more", "most", "other", "some", "such", "no",
    "only", "same", "own", "up", "out", "one", "two", "much", "get",
    "got", "don", "didn", "doesn", "won", "ve", "re", "ll", "amp",
    "like", "even", "still", "well", "back", "really", "thing",
    "things", "going", "make", "made", "way", "use", "used", "using",
    "over", "any", "there", "here", "been", "after", "first", "last",
    # Common filler words that add noise
    "would", "could", "should", "much", "many", "come", "came",
    "take", "took", "great", "good", "nice", "pretty", "right",
    "little", "big", "long", "new", "old", "work", "works",
    "want", "wanted", "know", "never", "always", "tried", "try",
    "bought", "buy", "feel", "found", "sure", "said", "say",
    "lot", "time", "day", "days", "year", "years", "month", "months",
    "amazon", "product", "review", "item", "purchase", "purchased",
    "star", "stars", "rating",
}

# Simple plural → singular mapping for keyword merging
_PLURAL_SUFFIXES = [
    ("ies", "y"),     # batteries → battery
    ("ves", "f"),     # lives → life
    ("ses", "s"),     # cases → case
    ("es", "e"),      # issues → issue (only if base >= 3 chars)
    ("s", ""),        # earbuds → earbud
]


def _normalize_word(word: str) -> str:
    """Simple plural stripping to merge variants like battery/batteries."""
    if len(word) <= 3:
        return word
    for suffix, replacement in _PLURAL_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) + len(replacement) >= 3:
            return word[:-len(suffix)] + replacement
    return word


def compute_summary(session_id: str, db: DBSession) -> dict:
    """Build a full analytics summary for a given session.

    Returns a dict with: total_reviews, average_rating, star_distribution,
    date_range, verified stats, top keywords, and sentiment breakdown.
    """
    reviews = (
        db.query(Review).filter(Review.session_id == session_id).all()
    )

    if not reviews:
        return _empty_summary()

    ratings = [r.rating for r in reviews if r.rating is not None and 1.0 <= r.rating <= 5.0]
    total = len(ratings)

    if not total:
        return _empty_summary()
    avg = round(sum(ratings) / total, 1)

    star_dist = _star_distribution(ratings)
    date_range = _date_range(reviews)
    verified_stats = _verified_stats(reviews)
    top_keywords = _extract_keywords(reviews)
    sentiment = _sentiment_breakdown(reviews)

    return {
        "total_reviews": total,
        "average_rating": avg,
        "star_distribution": star_dist,
        "date_range": date_range,
        "verified": verified_stats,
        "top_keywords": top_keywords,
        "sentiment": sentiment,
    }


def _empty_summary() -> dict:
    return {
        "total_reviews": 0,
        "average_rating": 0.0,
        "star_distribution": {str(i): 0 for i in range(1, 6)},
        "date_range": {"earliest": None, "latest": None},
        "verified": {"count": 0, "percentage": 0.0},
        "top_keywords": [],
        "sentiment": {
            "positive": 0, "neutral": 0, "negative": 0,
            "positive_pct": 0.0, "neutral_pct": 0.0, "negative_pct": 0.0,
        },
    }


def _star_distribution(ratings: list[float]) -> dict:
    """Count reviews per star bucket (1-5). Fractional ratings are floored."""
    counts = Counter(int(math.floor(r)) for r in ratings)
    return {str(star): counts.get(star, 0) for star in range(1, 6)}


def _date_range(reviews: list[Review]) -> dict:
    """Find the earliest and latest review dates (O(n) via min/max)."""
    dates = [r.date for r in reviews if r.date]
    if not dates:
        return {"earliest": None, "latest": None}
    return {"earliest": min(dates), "latest": max(dates)}


def _verified_stats(reviews: list[Review]) -> dict:
    """Count and percentage of verified purchase reviews."""
    verified_count = sum(1 for r in reviews if r.verified)
    total = len(reviews)
    pct = round((verified_count / total) * 100, 1) if total else 0.0
    return {"count": verified_count, "percentage": pct}


def _extract_keywords(reviews: list[Review], top_n: int = 10) -> list[dict]:
    """Extract top keywords from review text with sentiment association.

    Returns list of {word, count, avg_rating} sorted by frequency.
    """
    word_counts: Counter = Counter()
    word_ratings: dict[str, list[float]] = {}

    for r in reviews:
        text = f"{r.title or ''} {r.body or ''}".lower()
        words = re.findall(r"[a-z]{3,}", text)
        seen = set()
        for w in words:
            if w in _STOP_WORDS or len(w) > 20:
                continue
            normalized = _normalize_word(w)
            if normalized in _STOP_WORDS:
                continue
            if normalized not in seen:
                word_counts[normalized] += 1
                word_ratings.setdefault(normalized, []).append(r.rating)
                seen.add(normalized)

    total_reviews = len(reviews)
    result = []
    for word, count in word_counts.most_common(top_n):
        ratings = word_ratings[word]
        avg = round(sum(ratings) / len(ratings), 1)
        pct = round(count / total_reviews * 100, 1) if total_reviews else 0.0
        result.append({
            "word": word,
            "count": count,
            "avg_rating": avg,
            "mention_pct": pct,
        })

    return result


def _sentiment_breakdown(reviews: list[Review]) -> dict:
    """Classify reviews into positive / neutral / negative by rating."""
    total = len(reviews)
    positive = sum(1 for r in reviews if r.rating >= 4.0)
    negative = sum(1 for r in reviews if r.rating <= 2.0)
    neutral = total - positive - negative

    return {
        "positive": positive,
        "neutral": neutral,
        "negative": negative,
        "positive_pct": round(positive / total * 100, 1) if total else 0.0,
        "neutral_pct": round(neutral / total * 100, 1) if total else 0.0,
        "negative_pct": round(negative / total * 100, 1) if total else 0.0,
        "sample_size": total,
    }
