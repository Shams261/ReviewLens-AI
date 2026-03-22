"""Deterministic Analytics Engine — answers common review questions without an LLM.

Serves two purposes:
1. Fast path: instant answers for simple/statistical queries (no API cost, <5ms).
2. Fallback: keeps the app functional when both LLM providers are down.
"""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from app.models.schemas import Review


@dataclass
class DeterministicResult:
    """Result from the deterministic engine."""
    matched: bool        # True if the engine could handle the query
    text: str = ""       # The response text (empty if not matched)
    matched_intent: str = ""       # Which intent pattern was matched
    confidence: float = 0.0        # 0-1 confidence in the result
    evidence_count: int = 0        # Number of reviews supporting the answer


# ---------------------------------------------------------------------------
# Keyword buckets — map common product aspects to search terms
# ---------------------------------------------------------------------------

_ASPECT_KEYWORDS: dict[str, list[str]] = {
    "battery": ["battery", "charge", "charging", "battery life", "dies", "drain"],
    "sound": ["sound", "audio", "bass", "treble", "music", "volume", "loud"],
    "noise cancellation": ["noise cancel", "anc", "noise reduction", "active noise"],
    "connectivity": ["connect", "bluetooth", "disconnect", "pair", "pairing", "drops"],
    "comfort": ["comfort", "fit", "ear tip", "ear tips", "falls out", "loose", "small ears", "hurts"],
    "call quality": ["call", "calls", "microphone", "mic", "voice"],
    "price": ["price", "expensive", "cheap", "cost", "value", "worth", "money"],
    "durability": ["broke", "broken", "durable", "durability", "lasted", "wear"],
    "wind noise": ["wind", "windy", "outdoor"],
}

# ---------------------------------------------------------------------------
# Query intent patterns — regex-based intent detection
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("top_complaints",     re.compile(r"(top|main|biggest|most common|major|worst)\s+(complaint|issue|problem|concern|gripe|negative)|what are the (issues|problems|complaints|negatives)|people complain(ing)? about", re.I)),
    ("top_praise",         re.compile(r"(top|main|biggest|most)\s+(praise|positive|liked|loved|strength|pro\b)|what do people (like|love|enjoy)|pros and cons|what are the (positives|strengths)", re.I)),
    ("rating_stats",       re.compile(r"(average|mean|overall)\s+(rating|score|star)", re.I)),
    ("rating_distribution",re.compile(r"(star|rating)\s+(distribution|breakdown|spread|count)", re.I)),
    ("count_stars",        re.compile(r"how many\s+(\d)[- ]star", re.I)),
    ("verified_stats",     re.compile(r"(verified|authentic)\s+(purchaser|buyer|review|purchase)", re.I)),
    ("review_count",       re.compile(r"how many\s+review", re.I)),
    ("mention_keyword",    re.compile(r"(how many|which|any|do any)\s+(reviews?\s+)?(mention|talk about|discuss|say about|complain about|report)\s+(.+)|feedback about\s+(.+)|people saying about\s+(.+)", re.I)),
    ("sentiment_summary",  re.compile(r"(overall|general)\s+(sentiment|opinion|feeling|consensus|impression)|what do (people|reviewers|users|customers) (think|feel)", re.I)),
    ("most_helpful",       re.compile(r"(most helpful|most voted|highest voted|top voted|most useful)\s+review", re.I)),
    ("recent_reviews",     re.compile(r"(recent|latest|newest|most recent)\s+review", re.I)),
    ("aspect_query",       re.compile(r"(what|how|tell me|feedback).{0,30}(battery|sound|audio|noise cancel|connect|bluetooth|comfort|fit|call quality|mic|price|cost|value|wind|durability)", re.I)),
]


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

def _normalize_query(text: str) -> str:
    """Expand contractions and collapse whitespace for better matching."""
    _CONTRACTIONS = {
        "what's": "what is", "how's": "how is", "where's": "where is",
        "who's": "who is", "that's": "that is", "there's": "there is",
        "it's": "it is", "don't": "do not", "doesn't": "does not",
        "didn't": "did not", "won't": "will not", "can't": "cannot",
        "couldn't": "could not", "shouldn't": "should not",
        "wouldn't": "would not", "isn't": "is not", "aren't": "are not",
        "wasn't": "was not", "weren't": "were not", "haven't": "have not",
        "hasn't": "has not", "hadn't": "had not",
    }
    t = text.lower().strip()
    for contraction, expansion in _CONTRACTIONS.items():
        t = t.replace(contraction, expansion)
    t = re.sub(r"\s+", " ", t)
    return t


def try_deterministic(query: str, reviews: list[Review], product_name: str) -> DeterministicResult:
    """Attempt to answer the query deterministically from review data.

    Returns DeterministicResult(matched=True, text=...) if handled,
    or DeterministicResult(matched=False) if the query needs an LLM.
    """
    q = _normalize_query(query)
    n = len(reviews)

    if n == 0:
        return DeterministicResult(matched=False)

    # --- Guard: skip complex multi-part queries ---
    word_count = len(q.split())
    _COMPLEX_MARKERS = re.compile(r"\b(and how|but also|as well as|in addition|compared with|along with|furthermore)\b", re.I)
    if word_count >= 15 and _COMPLEX_MARKERS.search(q):
        return DeterministicResult(matched=False)

    # --- Match intent ---
    for intent, pattern in _PATTERNS:
        m = pattern.search(q)
        if m:
            handler = _HANDLERS.get(intent)
            if handler:
                return handler(q, m, reviews, product_name)

    return DeterministicResult(matched=False)


# ---------------------------------------------------------------------------
# Intent handlers
# ---------------------------------------------------------------------------

def _handle_top_complaints(q: str, m: re.Match, reviews: list[Review], product_name: str) -> DeterministicResult:
    negative = [r for r in reviews if r.rating <= 2.0]
    if not negative:
        return DeterministicResult(
            matched=True,
            text=f"Out of {len(reviews)} reviews for {product_name}, none have ratings of 2 stars or below, "
                 f"so there are no major complaints to report.",
            matched_intent="top_complaints", confidence=0.95, evidence_count=0,
        )

    if len(negative) < 2:
        return DeterministicResult(
            matched=True,
            text=f"Only {len(negative)} negative review(s) found — not enough data to identify reliable complaint patterns.",
            matched_intent="top_complaints", confidence=0.4, evidence_count=len(negative),
        )

    aspects = _extract_aspects(negative)
    top = aspects.most_common(5)

    lines = [f"Based on {len(negative)} negative reviews (2 stars or below) out of {len(reviews)} total:\n"]
    for i, (aspect, count) in enumerate(top, 1):
        matching = [r for r in negative if _review_matches_aspect(r, aspect)]
        citations = " ".join(f"[Review #{r.id}]" for r in matching[:3])
        lines.append(f"{i}. **{aspect.title()}** — mentioned in {count} review(s) {citations}")

    lines.append(f"\n_This analysis was generated deterministically from the review data._")
    return DeterministicResult(
        matched=True, text="\n".join(lines),
        matched_intent="top_complaints", confidence=min(0.95, 0.6 + len(negative) * 0.02),
        evidence_count=len(negative),
    )


def _handle_top_praise(q: str, m: re.Match, reviews: list[Review], product_name: str) -> DeterministicResult:
    positive = [r for r in reviews if r.rating >= 4.0]
    if not positive:
        return DeterministicResult(
            matched=True,
            text=f"Out of {len(reviews)} reviews for {product_name}, none have ratings of 4 stars or above.",
            matched_intent="top_praise", confidence=0.95, evidence_count=0,
        )

    if len(positive) < 2:
        return DeterministicResult(
            matched=True,
            text=f"Only {len(positive)} positive review(s) found — not enough data to identify reliable praise patterns.",
            matched_intent="top_praise", confidence=0.4, evidence_count=len(positive),
        )

    aspects = _extract_aspects(positive)
    top = aspects.most_common(5)

    lines = [f"Based on {len(positive)} positive reviews (4 stars and above) out of {len(reviews)} total:\n"]
    for i, (aspect, count) in enumerate(top, 1):
        matching = [r for r in positive if _review_matches_aspect(r, aspect)]
        citations = " ".join(f"[Review #{r.id}]" for r in matching[:3])
        lines.append(f"{i}. **{aspect.title()}** — praised in {count} review(s) {citations}")

    lines.append(f"\n_This analysis was generated deterministically from the review data._")
    return DeterministicResult(
        matched=True, text="\n".join(lines),
        matched_intent="top_praise", confidence=min(0.95, 0.6 + len(positive) * 0.02),
        evidence_count=len(positive),
    )


def _handle_rating_stats(q: str, m: re.Match, reviews: list[Review], product_name: str) -> DeterministicResult:
    avg = sum(r.rating for r in reviews) / len(reviews)
    verified = [r for r in reviews if r.verified]
    verified_avg = sum(r.rating for r in verified) / len(verified) if verified else 0

    text = (
        f"**{product_name}** — Rating Summary ({len(reviews)} reviews):\n\n"
        f"- Overall average: **{avg:.1f}/5**\n"
        f"- Verified purchaser average: **{verified_avg:.1f}/5** ({len(verified)} reviews)\n"
        f"\n_This analysis was generated deterministically from the review data._"
    )
    return DeterministicResult(
        matched=True, text=text,
        matched_intent="rating_stats", confidence=0.95, evidence_count=len(reviews),
    )


def _handle_rating_distribution(q: str, m: re.Match, reviews: list[Review], product_name: str) -> DeterministicResult:
    dist = Counter(int(r.rating) for r in reviews)
    lines = [f"**Star Distribution** ({len(reviews)} reviews):\n"]
    for star in range(5, 0, -1):
        count = dist.get(star, 0)
        pct = count / len(reviews) * 100
        bar = "█" * int(pct / 5) if pct > 0 else ""
        lines.append(f"{'⭐' * star}  {count} reviews ({pct:.0f}%) {bar}")

    lines.append(f"\n_This analysis was generated deterministically from the review data._")
    return DeterministicResult(
        matched=True, text="\n".join(lines),
        matched_intent="rating_distribution", confidence=0.95, evidence_count=len(reviews),
    )


def _handle_count_stars(q: str, m: re.Match, reviews: list[Review], product_name: str) -> DeterministicResult:
    target_star = int(m.group(1))
    matching = [r for r in reviews if int(r.rating) == target_star]
    citations = " ".join(f"[Review #{r.id}]" for r in matching[:5])

    text = (
        f"{len(matching)} out of {len(reviews)} reviews are {target_star}-star. {citations}\n"
        f"\n_This analysis was generated deterministically from the review data._"
    )
    return DeterministicResult(
        matched=True, text=text,
        matched_intent="count_stars", confidence=0.95, evidence_count=len(matching),
    )


def _handle_verified_stats(q: str, m: re.Match, reviews: list[Review], product_name: str) -> DeterministicResult:
    verified = [r for r in reviews if r.verified]
    pct = len(verified) / len(reviews) * 100
    avg_all = sum(r.rating for r in reviews) / len(reviews)
    avg_ver = sum(r.rating for r in verified) / len(verified) if verified else 0

    lines = [
        f"**Verified Purchaser Analysis** ({len(reviews)} total reviews):\n",
        f"- Verified purchases: **{len(verified)}** ({pct:.0f}%)",
        f"- Unverified: **{len(reviews) - len(verified)}**",
        f"- Verified avg rating: **{avg_ver:.1f}/5** vs overall **{avg_all:.1f}/5**",
    ]

    # Show a few verified review citations
    if verified:
        cites = " ".join(f"[Review #{r.id}]" for r in verified[:5])
        lines.append(f"\nVerified reviews: {cites}")

    lines.append(f"\n_This analysis was generated deterministically from the review data._")
    return DeterministicResult(
        matched=True, text="\n".join(lines),
        matched_intent="verified_stats", confidence=0.95, evidence_count=len(reviews),
    )


def _handle_review_count(q: str, m: re.Match, reviews: list[Review], product_name: str) -> DeterministicResult:
    text = (
        f"There are **{len(reviews)}** reviews loaded for {product_name}.\n"
        f"\n_This analysis was generated deterministically from the review data._"
    )
    return DeterministicResult(
        matched=True, text=text,
        matched_intent="review_count", confidence=1.0, evidence_count=len(reviews),
    )


def _handle_mention_keyword(q: str, m: re.Match, reviews: list[Review], product_name: str) -> DeterministicResult:
    # Try groups 4, 5, 6 (from original pattern and synonym alternations)
    keyword = (m.group(4) or m.group(5) or m.group(6) or "").strip().rstrip("?.")
    if not keyword:
        return DeterministicResult(matched=False)

    # Use word-boundary matching for single words to avoid "fit" matching "profit"
    if " " in keyword:
        matching = [r for r in reviews if keyword.lower() in (r.body or "").lower() or keyword.lower() in (r.title or "").lower()]
    else:
        kw_pattern = re.compile(r"\b" + re.escape(keyword.lower()) + r"\b")
        matching = [r for r in reviews if kw_pattern.search((r.body or "").lower()) or kw_pattern.search((r.title or "").lower())]

    if not matching:
        return DeterministicResult(
            matched=True,
            text=f"No reviews mention \"{keyword}\" out of {len(reviews)} total reviews for {product_name}."
                 f"\n\n_This analysis was generated deterministically from the review data._",
            matched_intent="mention_keyword", confidence=0.9, evidence_count=0,
        )

    citations = " ".join(f"[Review #{r.id}]" for r in matching[:5])
    avg_rating = sum(r.rating for r in matching) / len(matching)

    lines = [
        f"**{len(matching)}** out of {len(reviews)} reviews mention \"{keyword}\". {citations}\n",
        f"- Average rating of these reviews: **{avg_rating:.1f}/5**",
    ]
    lines.append(f"\n_This analysis was generated deterministically from the review data._")
    return DeterministicResult(
        matched=True, text="\n".join(lines),
        matched_intent="mention_keyword", confidence=0.9, evidence_count=len(matching),
    )


def _handle_sentiment_summary(q: str, m: re.Match, reviews: list[Review], product_name: str) -> DeterministicResult:
    avg = sum(r.rating for r in reviews) / len(reviews)
    positive = len([r for r in reviews if r.rating >= 4.0])
    negative = len([r for r in reviews if r.rating <= 2.0])
    neutral = len(reviews) - positive - negative
    pct_pos = positive / len(reviews) * 100

    if avg >= 4.0:
        sentiment = "overwhelmingly positive"
    elif avg >= 3.0:
        sentiment = "mixed but leaning positive"
    elif avg >= 2.0:
        sentiment = "mixed but leaning negative"
    else:
        sentiment = "overwhelmingly negative"

    text = (
        f"**Overall Sentiment for {product_name}** ({len(reviews)} reviews):\n\n"
        f"The sentiment is **{sentiment}** with an average rating of **{avg:.1f}/5**.\n\n"
        f"- Positive (4-5 stars): **{positive}** ({pct_pos:.0f}%)\n"
        f"- Neutral (3 stars): **{neutral}**\n"
        f"- Negative (1-2 stars): **{negative}**\n"
        f"\n_This analysis was generated deterministically from the review data._"
    )
    return DeterministicResult(
        matched=True, text=text,
        matched_intent="sentiment_summary", confidence=0.95, evidence_count=len(reviews),
    )


def _handle_most_helpful(q: str, m: re.Match, reviews: list[Review], product_name: str) -> DeterministicResult:
    sorted_reviews = sorted(reviews, key=lambda r: r.helpful_votes or 0, reverse=True)
    top = sorted_reviews[:3]

    lines = [f"**Most Helpful Reviews** for {product_name}:\n"]
    for r in top:
        stars = "⭐" * int(r.rating)
        lines.append(
            f"- [Review #{r.id}] {stars} — \"{r.title or '(no title)'}\" by {r.author or 'Anonymous'} "
            f"({r.helpful_votes or 0} helpful votes)\n  _{r.body[:120]}{'...' if len(r.body or '') > 120 else ''}_"
        )

    lines.append(f"\n_This analysis was generated deterministically from the review data._")
    return DeterministicResult(
        matched=True, text="\n".join(lines),
        matched_intent="most_helpful", confidence=0.95, evidence_count=len(top),
    )


def _handle_recent_reviews(q: str, m: re.Match, reviews: list[Review], product_name: str) -> DeterministicResult:
    dated = [r for r in reviews if r.date]
    if not dated:
        return DeterministicResult(
            matched=True,
            text=f"No date information is available for the {len(reviews)} reviews loaded.",
            matched_intent="recent_reviews",
            confidence=1.0,
            evidence_count=0,
        )

    def _parse_date(d: str) -> datetime:
        for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(d, fmt)
            except ValueError:
                continue
        return datetime.min  # unparseable dates sort to the bottom

    sorted_reviews = sorted(dated, key=lambda r: _parse_date(r.date), reverse=True)
    top = sorted_reviews[:3]

    lines = [f"**Most Recent Reviews** for {product_name}:\n"]
    for r in top:
        stars = "⭐" * int(r.rating)
        lines.append(
            f"- [Review #{r.id}] {stars} — \"{r.title or '(no title)'}\" ({r.date})\n"
            f"  _{r.body[:120]}{'...' if len(r.body or '') > 120 else ''}_"
        )

    lines.append(f"\n_This analysis was generated deterministically from the review data._")
    return DeterministicResult(
        matched=True, text="\n".join(lines),
        matched_intent="recent_reviews", confidence=0.9, evidence_count=len(top),
    )


def _handle_aspect_query(q: str, m: re.Match, reviews: list[Review], product_name: str) -> DeterministicResult:
    aspect_hit = m.group(2).lower()
    # Find which aspect bucket matches
    matched_aspect = None
    for aspect, keywords in _ASPECT_KEYWORDS.items():
        if any(k in aspect_hit for k in keywords) or aspect_hit in aspect:
            matched_aspect = aspect
            break

    if not matched_aspect:
        return DeterministicResult(matched=False)

    keywords = _ASPECT_KEYWORDS[matched_aspect]
    matching = [r for r in reviews if _review_matches_aspect(r, matched_aspect)]

    if not matching:
        return DeterministicResult(
            matched=True,
            text=f"No reviews mention {matched_aspect} out of {len(reviews)} total reviews."
                 f"\n\n_This analysis was generated deterministically from the review data._",
            matched_intent="aspect_query", confidence=0.85, evidence_count=0,
        )

    if len(matching) < 2:
        return DeterministicResult(
            matched=True,
            text=f"Only {len(matching)} review mentions {matched_aspect} — not enough data for a reliable aspect summary.",
            matched_intent="aspect_query", confidence=0.4, evidence_count=len(matching),
        )

    avg = sum(r.rating for r in matching) / len(matching)
    citations = " ".join(f"[Review #{r.id}]" for r in matching[:5])
    positive = len([r for r in matching if r.rating >= 4.0])
    negative = len([r for r in matching if r.rating <= 2.0])

    lines = [
        f"**{matched_aspect.title()}** — mentioned in {len(matching)} of {len(reviews)} reviews {citations}\n",
        f"- Average rating of these reviews: **{avg:.1f}/5**",
        f"- Positive mentions: {positive} | Negative mentions: {negative}",
    ]

    # Show a snippet from the most helpful matching review
    best = max(matching, key=lambda r: r.helpful_votes or 0)
    lines.append(f"\nMost helpful mention [Review #{best.id}]: \"{best.body[:150]}{'...' if len(best.body or '') > 150 else ''}\"")

    lines.append(f"\n_This analysis was generated deterministically from the review data._")
    return DeterministicResult(
        matched=True, text="\n".join(lines),
        matched_intent="aspect_query", confidence=min(0.95, 0.6 + len(matching) * 0.03),
        evidence_count=len(matching),
    )


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_HANDLERS = {
    "top_complaints": _handle_top_complaints,
    "top_praise": _handle_top_praise,
    "rating_stats": _handle_rating_stats,
    "rating_distribution": _handle_rating_distribution,
    "count_stars": _handle_count_stars,
    "verified_stats": _handle_verified_stats,
    "review_count": _handle_review_count,
    "mention_keyword": _handle_mention_keyword,
    "sentiment_summary": _handle_sentiment_summary,
    "most_helpful": _handle_most_helpful,
    "recent_reviews": _handle_recent_reviews,
    "aspect_query": _handle_aspect_query,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _keyword_in_text(keyword: str, text: str) -> bool:
    """Check if keyword appears in text using word-boundary for single words."""
    if " " in keyword:
        return keyword in text
    return bool(re.search(r"\b" + re.escape(keyword) + r"\b", text))


def _extract_aspects(reviews: list[Review]) -> Counter:
    """Count which aspect keywords appear across a set of reviews."""
    counts: Counter = Counter()
    for r in reviews:
        text = f"{r.title or ''} {r.body or ''}".lower()
        for aspect, keywords in _ASPECT_KEYWORDS.items():
            if any(_keyword_in_text(k, text) for k in keywords):
                counts[aspect] += 1
    return counts


def _review_matches_aspect(review: Review, aspect: str) -> bool:
    """Check if a review mentions a specific aspect."""
    text = f"{review.title or ''} {review.body or ''}".lower()
    keywords = _ASPECT_KEYWORDS.get(aspect, [])
    return any(_keyword_in_text(k, text) for k in keywords)
