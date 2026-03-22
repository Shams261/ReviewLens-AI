"""Scope Guard — Layer 2: Rule-based input classifier.

Runs before the LLM to catch obvious out-of-scope queries deterministically
(< 1ms). Saves LLM tokens and enforces hard boundaries.

Design choice: strict-first — favor blocking borderline queries rather than
passing them to the LLM. The LLM system prompt (Layer 1) and output
validation (Layer 3) are safety nets, but Layer 2 should catch as much as
possible to save tokens and reduce hallucination surface.
"""

import re
import unicodedata

# ---------------------------------------------------------------------------
# Text normalization — run once per query for consistent matching
# ---------------------------------------------------------------------------

# Zero-width and invisible unicode characters used for evasion
_INVISIBLE_CHARS = re.compile(
    r"[\u200b\u200c\u200d\u200e\u200f\u00ad\ufeff\u2060\u2061\u2062\u2063\u2064]"
)


def _normalize(text: str) -> str:
    """Normalize text for matching: unicode → ASCII, collapse whitespace/punctuation."""
    # Replace zero-width / invisible characters with spaces (preserves word boundaries)
    text = _INVISIBLE_CHARS.sub(" ", text)
    # Unicode normalize: NFKD decomposes accented chars (é → e + combining accent)
    text = unicodedata.normalize("NFKD", text)
    # Keep ASCII chars, replace non-ASCII with space (handles emoji, CJK, etc.)
    # Combining marks (category M) are stripped entirely (they were decomposed above)
    text = "".join(
        c if ord(c) < 128
        else "" if unicodedata.category(c).startswith("M")
        else " "
        for c in text
    )
    # Lowercase
    text = text.lower()
    # Collapse punctuation separators used for evasion (e.g., "ig.nore" → "ignore")
    # Keep spaces and alphanumeric, collapse everything else to single space
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Blocklist patterns — grouped by category for maintainability
# All compiled to regexes with word boundaries at module scope.
# ---------------------------------------------------------------------------

# Competitor brands — multi-word entries include singular/plural variants.
# "beats" is excluded as a standalone word (too common as a verb);
# instead, we match specific product lines.
_COMPETITOR_BRANDS = [
    "samsung", "galaxy bud", "galaxy buds",
    "sony", "bose", "jabra",
    "beats by dre", "beats headphones", "beats studio", "beats solo",
    "beats fit pro", "beats pill", "powerbeats",
    "sennheiser",
    "google pixel bud", "google pixel buds",
    "nothing ear",
    "jbl",
    "skullcandy",
    "anker", "soundcore",
    "oneplus bud", "oneplus buds",
    "huawei", "xiaomi", "oppo", "realme",
    "akg", "plantronics", "poly",
    "bang and olufsen", "b and o", "marshall",
    "libratone", "jaybird", "shure",
]

# External platforms — users should only analyze reviews from the ingested source.
_OTHER_PLATFORMS = [
    "yelp", "trustpilot", "g2", "capterra",
    "google map", "google maps", "google review", "google reviews",
    "tripadvisor", "glassdoor",
    "reddit", "subreddit",
    "twitter", "facebook", "instagram", "tiktok",
    "youtube", "linkedin", "quora", "threads",
    "walmart review", "walmart reviews",
    "target review", "target reviews",
    "best buy review", "best buy reviews",
    "bestbuy",
    "flipkart",
]

# General world knowledge — HARD BLOCK: always block regardless of review context.
# These terms are so unambiguously off-topic that review context words are irrelevant.
_GENERAL_KNOWLEDGE_HARD = [
    # Geography & politics
    "weather", "president", "capital of", "election", "prime minister",
    # Sports & entertainment
    "super bowl", "world cup", "who won the", "oscar", "grammy",
    "emmy", "golden globe", "world series", "olympic",
    # Finance
    "stock price", "stock market", "cryptocurrency", "bitcoin", "ethereum",
    "forex", "nasdaq", "dow jones",
    # News
    "news today", "breaking news",
    # Trivia / encyclopedic
    "what year", "population of", "distance between",
    "what time is it", "what day is it",
    # Cooking / recipes
    "recipe for", "how to cook", "how to bake",
    # Creative requests
    "tell me a joke", "write me a poem", "write a poem",
    "write a story", "tell me a story", "write an essay",
    # Math & science
    "what is the square root", "calculate", "solve for",
    "explain quantum", "explain physics", "explain chemistry",
    "what is photosynthesis",
    # Code generation
    "write python", "write javascript", "write code", "write a script",
    "generate code", "debug my", "fix my code",
    "write sql", "write html", "write css",
    # History
    "when did world war", "when was the",
]

# General world knowledge — SOFT BLOCK: block unless query also has review context.
# These are phrases that *could* appear in review-related queries.
_GENERAL_KNOWLEDGE_SOFT = [
    "how old is",  # "how old is the oldest review" is valid
    "translate",   # "translate review sentiments" is valid
]

# Comparative / external reference queries — seeks data beyond the review set.
_COMPARATIVE_EXTERNAL = [
    "compare to other", "compared to other", "compared to the",
    "vs other", "versus other",
    "other brands", "other products", "other earbuds", "other headphones",
    "the competition", "competitors",
    "industry average", "industry benchmark", "market average",
    "other sites", "other platforms", "elsewhere online",
    "what do experts say", "professional reviews", "expert reviews",
    "according to", "based on reports",
]

# Prompt injection patterns — attempts to override system instructions.
_PROMPT_INJECTION = [
    # Direct override
    "ignore your instructions", "ignore previous instructions",
    "ignore all instructions", "ignore the above",
    "ignore that",
    "forget your rules", "forget everything",
    "disregard your prompt", "disregard everything above",
    "disregard all previous",
    # Identity override
    "you are now", "act as", "pretend you", "roleplay as",
    "from now on respond as", "from now on you are",
    "simulate being",
    # Instruction manipulation
    "new instructions", "override your", "override instructions",
    "bypass your", "skip your", "circumvent your",
    "do not follow your rules", "do not follow your instructions",
    # System prompt extraction
    "system prompt", "reveal your prompt", "show me your instructions",
    "what are your instructions", "repeat your instructions",
    "output your prompt", "output your initial",
    "tell me your base instructions", "tell me your rules",
    "what is your prompt", "print your prompt",
    "repeat your system", "repeat back your",
    # Jailbreak patterns
    "jailbreak", "dan mode", "developer mode",
    "reset your context", "start a new conversation",
    "ignore safety", "remove restrictions",
    "unrestricted mode", "unfiltered mode",
]


def _build_word_boundary_re(terms: list[str]) -> re.Pattern:
    """Build a compiled regex that matches any term with word boundaries."""
    # Sort by length descending so longer phrases match first
    sorted_terms = sorted(terms, key=len, reverse=True)
    pattern = r"\b(?:" + "|".join(re.escape(t) for t in sorted_terms) + r")\b"
    return re.compile(pattern, re.IGNORECASE)


def _build_phrase_re(phrases: list[str]) -> re.Pattern:
    """Build a compiled regex for phrase matching (no word boundaries needed)."""
    sorted_phrases = sorted(phrases, key=len, reverse=True)
    pattern = "|".join(re.escape(p) for p in sorted_phrases)
    return re.compile(pattern, re.IGNORECASE)


# Pre-compiled regexes — built once at module load
_COMPETITOR_RE = _build_word_boundary_re(_COMPETITOR_BRANDS)
_PLATFORM_RE = _build_word_boundary_re(_OTHER_PLATFORMS)
_GENERAL_KNOWLEDGE_HARD_RE = _build_phrase_re(_GENERAL_KNOWLEDGE_HARD)
_GENERAL_KNOWLEDGE_SOFT_RE = _build_phrase_re(_GENERAL_KNOWLEDGE_SOFT)
_COMPARATIVE_RE = _build_phrase_re(_COMPARATIVE_EXTERNAL)
_INJECTION_RE = _build_phrase_re(_PROMPT_INJECTION)

# Entity patterns — catches non-review entity queries
_ENTITY_RE = re.compile(
    r"\b(who|where)\s+(is|are|was)\b|"
    r"\bhow\s+is\s+(the\s+)?(ceo|cto|cfo|founder|owner|manager|director|"
    r"president|company|brand|manufacturer|seller|vendor|headquarters)\b|"
    r"\b(ceo|cto|cfo|founder|owner|chairman|board|investors?|shareholders?|"
    r"employees?|staff|team)\b",
    re.I,
)

# Review context — if present alongside entity patterns, query is valid
_REVIEW_CONTEXT_RE = re.compile(
    r"\b(reviews?|ratings?|stars?|complaints?|helpful|verified|mention|"
    r"feedback|reviewer|sentiment|opinions?|experience|praised?|"
    r"recommend|buy|purchased?|quality)\b",
    re.I,
)

# Review signal words — used for short-query heuristic
_REVIEW_SIGNAL_RE = re.compile(
    r"\b(reviews?|ratings?|stars?|complaints?|issues?|problems?|"
    r"love|hate|features?|quality|battery|sound|noise|fit|comfort|"
    r"price|value|worth|recommend|buy|return|refund|broken|defect|"
    r"customers?|feedback|opinions?|experience|mention|say|think|feel|"
    r"complain|praise|positive|negative|sentiment|trends?|patterns?|"
    r"common|frequent|most|top|worst|best|average|verified|helpful|"
    r"recent|oldest|newest|durability|cancel|cancellation|tips?|ears?|"
    r"products?|pros?|cons|airpods?|summary|summarize|overall|"
    r"satisfaction|disappointed|impressed|liked|disliked)\b",
    re.I,
)


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------

class ScopeGuardResult:
    """Holds the classification result from the scope guard.

    Layer 2 returns two states:
    - "out_of_scope": blocked, do not send to LLM
    - "pass_to_llm": uncertain or in-scope, let LLM + Layer 3 decide

    Layer 3 (validate_output) returns:
    - "in_scope": output is clean
    - "out_of_scope": output contains scope leaks
    """

    __slots__ = ("status", "reason")

    def __init__(self, status: str, reason: str = ""):
        self.status = status   # "out_of_scope", "pass_to_llm", "in_scope"
        self.reason = reason

    @property
    def is_blocked(self) -> bool:
        return self.status == "out_of_scope"


# ---------------------------------------------------------------------------
# Layer 2: Input classification
# ---------------------------------------------------------------------------

def classify_query(query: str, product_name: str = "") -> ScopeGuardResult:
    """Classify a user query as out_of_scope or pass_to_llm.

    This is Layer 2 (rule-based). Layer 1 (system prompt) runs inside the LLM.
    Layer 3 (output validation) runs after the LLM responds.

    Design: strict-first — blocks borderline queries rather than letting
    them through. The LLM system prompt is the safety net for false negatives.
    """
    q = _normalize(query)

    if not q:
        return ScopeGuardResult("out_of_scope", "Empty query.")

    product_lower = _normalize(product_name)

    # --- Prompt injection attempts (phrase match — checked first, highest priority) ---
    if _INJECTION_RE.search(q):
        return ScopeGuardResult(
            "out_of_scope",
            "I can only answer questions about the ingested product reviews. "
            "This request is outside my scope.",
        )

    # --- Competitor brands (word boundary) ---
    match = _COMPETITOR_RE.search(q)
    if match and match.group(0).lower() not in product_lower:
        return ScopeGuardResult(
            "out_of_scope",
            f"I can only answer questions about {product_name} reviews. "
            f"I don't have data about other brands or products.",
        )

    # --- Other review platforms (word boundary) ---
    platform_match = _PLATFORM_RE.search(q)
    if platform_match:
        return ScopeGuardResult(
            "out_of_scope",
            f"I only have access to reviews from this product's source platform. "
            f"I can't comment on reviews from {platform_match.group(0).title()}.",
        )

    # --- General world knowledge: hard block (always block) ---
    if _GENERAL_KNOWLEDGE_HARD_RE.search(q):
        return ScopeGuardResult(
            "out_of_scope",
            "I can only answer questions about the ingested product reviews. "
            "General knowledge questions are outside my scope.",
        )

    # --- General world knowledge: soft block (block unless review context) ---
    if _GENERAL_KNOWLEDGE_SOFT_RE.search(q) and not _REVIEW_CONTEXT_RE.search(q):
        return ScopeGuardResult(
            "out_of_scope",
            "I can only answer questions about the ingested product reviews. "
            "General knowledge questions are outside my scope.",
        )

    # --- Comparative / external reference queries (phrase match) ---
    if _COMPARATIVE_RE.search(q):
        return ScopeGuardResult(
            "out_of_scope",
            f"I can only analyze the {product_name} reviews that have been loaded. "
            f"I don't have access to competitor data, external benchmarks, or other platforms.",
        )

    # --- Non-review entity queries (people, places, organizations) ---
    if _ENTITY_RE.search(q):
        # "who is the most helpful reviewer" is valid — check for review context
        if not _REVIEW_CONTEXT_RE.search(q):
            return ScopeGuardResult(
                "out_of_scope",
                "I can only answer questions about the ingested product reviews. "
                "General knowledge questions are outside my scope.",
            )

    # --- Quick heuristic: very short queries with no review-related words ---
    # If the query is short and has no review-adjacent words, let the LLM
    # decide with guardrails rather than blocking (avoid false positives)
    words = q.split()
    if len(words) <= 3 and not _REVIEW_SIGNAL_RE.search(q):
        return ScopeGuardResult("pass_to_llm")

    # Default: pass to LLM with guardrails (system prompt handles it)
    return ScopeGuardResult("pass_to_llm")


# ---------------------------------------------------------------------------
# Layer 3: Output validation — runs AFTER the LLM responds
# ---------------------------------------------------------------------------

_HALLUCINATION_RE = re.compile(
    r"\[Review\s*#(\d+)\]",
    re.IGNORECASE,
)

_EXTERNAL_MARKERS = [
    "according to my training",
    "based on my knowledge",
    "as of my last update",
    "i don't have access to the reviews",
    "i cannot access",
    "as an ai language model",
    "as a large language model",
    "in my training data",
    "outside my training",
    "i was trained",
    "my knowledge cutoff",
]
_EXTERNAL_MARKER_RE = _build_phrase_re(_EXTERNAL_MARKERS)

# Platform leak detection in output — LLM should not reference external platforms
_OUTPUT_PLATFORM_RE = _build_word_boundary_re(
    _OTHER_PLATFORMS + ["amazon", "amazon reviews"]
)


def validate_output(
    llm_text: str,
    product_name: str,
    review_ids: set[int],
) -> ScopeGuardResult:
    """Layer 3: Validate LLM output for scope leaks, hallucinated citations,
    competitor mentions, and platform references that slipped past the system prompt.

    Args:
        llm_text: The raw text returned by the LLM.
        product_name: The tracked product name (to exempt from competitor check).
        review_ids: Set of valid review IDs in this session.

    Returns:
        ScopeGuardResult with status "in_scope" if clean, or "out_of_scope"
        with a reason describing what was caught.
    """
    if not llm_text.strip():
        return ScopeGuardResult("in_scope")

    text_lower = llm_text.lower()
    product_lower = product_name.lower()

    # --- Check for competitor brand leaks (word boundary) ---
    for match in _COMPETITOR_RE.finditer(text_lower):
        brand = match.group(0).lower()
        if brand not in product_lower:
            return ScopeGuardResult(
                "out_of_scope",
                f"I can only answer questions about {product_name} reviews. "
                f"I don't have data about other brands or products.",
            )

    # --- Check for external platform references in output ---
    platform_match = _OUTPUT_PLATFORM_RE.search(text_lower)
    if platform_match:
        # Allow if platform is contextually relevant (e.g., "Amazon" when reviews are from Amazon)
        matched_platform = platform_match.group(0).lower()
        if matched_platform not in product_lower:
            return ScopeGuardResult(
                "out_of_scope",
                f"I can only answer questions about {product_name} reviews from "
                f"the loaded data. This question is outside my scope.",
            )

    # --- Check for hallucinated review citations ---
    cited_ids = {int(m.group(1)) for m in _HALLUCINATION_RE.finditer(llm_text)}
    bad_ids = cited_ids - review_ids
    if bad_ids:
        return ScopeGuardResult(
            "out_of_scope",
            "I found an issue with my previous response — it referenced reviews "
            "that don't exist in the loaded data. Let me try again. "
            "Could you please rephrase your question?",
        )

    # --- Check for fabricated external data markers ---
    if _EXTERNAL_MARKER_RE.search(text_lower):
        return ScopeGuardResult(
            "out_of_scope",
            f"I can only answer questions about {product_name} reviews from "
            f"the loaded data. This question is outside my scope.",
        )

    return ScopeGuardResult("in_scope")
