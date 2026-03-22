"""Unit tests for the chat module helpers."""

import pytest
import re
from app.routers.chat import _hash_query, _compute_confidence, _extract_citations, CitedReview
from tests.conftest import MockReview


class TestHashQuery:
    def test_same_query_same_hash(self):
        h1 = _hash_query("What are the complaints?", "session-1")
        h2 = _hash_query("What are the complaints?", "session-1")
        assert h1 == h2

    def test_normalized_whitespace(self):
        h1 = _hash_query("What  are   the   complaints?", "s1")
        h2 = _hash_query("What are the complaints?", "s1")
        assert h1 == h2

    def test_case_insensitive(self):
        h1 = _hash_query("WHAT ARE THE COMPLAINTS?", "s1")
        h2 = _hash_query("what are the complaints?", "s1")
        assert h1 == h2

    def test_different_session_different_hash(self):
        h1 = _hash_query("test query", "session-1")
        h2 = _hash_query("test query", "session-2")
        assert h1 != h2

    def test_hash_is_sha256_hex(self):
        h = _hash_query("test", "s1")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestComputeConfidence:
    def test_scope_guard_always_100(self):
        score = _compute_confidence("blocked", [], 10, "scope_guard")
        assert score == 1.0

    def test_deterministic_higher_than_llm(self):
        det = _compute_confidence("Some response [Review #1]", [1], 10, "deterministic")
        llm = _compute_confidence("Some response [Review #1]", [1], 10, "groq")
        assert det > llm

    def test_cache_bonus(self):
        cache = _compute_confidence("Some response", [], 10, "cache")
        llm = _compute_confidence("Some response", [], 10, "groq")
        assert cache > llm

    def test_citations_boost_confidence(self):
        no_cite = _compute_confidence("A response", [], 10, "groq")
        with_cite = _compute_confidence("A response [Review #1]", [1], 10, "groq")
        assert with_cite > no_cite

    def test_hedging_lowers_confidence(self):
        normal = _compute_confidence("The battery is good.", [1], 10, "groq")
        hedging = _compute_confidence("I'm not sure about this.", [1], 10, "groq")
        assert hedging < normal

    def test_short_reply_penalty(self):
        short = _compute_confidence("OK", [], 10, "groq")
        long = _compute_confidence("This is a detailed response about the product reviews.", [], 10, "groq")
        assert short <= long

    def test_confidence_bounded(self):
        # Even with worst case factors, should stay in [0, 1]
        score = _compute_confidence("i'm not sure unclear", [], 1, "groq")
        assert 0.0 <= score <= 1.0


class TestExtractCitations:
    def _make_reviews(self):
        return [
            MockReview(1, 5.0, "Great", "Amazing product"),
            MockReview(2, 3.0, "OK", "Decent but pricey"),
            MockReview(3, 1.0, "Bad", "Terrible quality"),
        ]

    def test_single_citation(self):
        ids, cards = _extract_citations("Great product [Review #1]", self._make_reviews())
        assert ids == [1]
        assert len(cards) == 1
        assert cards[0].id == 1

    def test_multiple_citations(self):
        ids, cards = _extract_citations("Issues [Review #1] and [Review #3]", self._make_reviews())
        assert ids == [1, 3]
        assert len(cards) == 2

    def test_duplicate_citations_deduped(self):
        ids, cards = _extract_citations("[Review #1] [Review #1] repeated", self._make_reviews())
        assert ids == [1]
        assert len(cards) == 1

    def test_no_citations(self):
        ids, cards = _extract_citations("No references here.", self._make_reviews())
        assert ids == []
        assert cards == []

    def test_invalid_citation_id_ignored(self):
        ids, cards = _extract_citations("See [Review #99]", self._make_reviews())
        assert ids == [99]
        assert cards == []  # ID 99 doesn't exist in reviews

    def test_citation_body_truncated(self):
        reviews = [MockReview(1, 5.0, "T", "x" * 500)]
        ids, cards = _extract_citations("[Review #1]", reviews)
        assert len(cards[0].body) == 300

    def test_case_insensitive_citation(self):
        ids, cards = _extract_citations("[review #2]", self._make_reviews())
        assert ids == [2]
