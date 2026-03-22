"""Unit tests for the analytics engine."""

import pytest
from app.services.analytics import (
    _star_distribution,
    _date_range,
    _verified_stats,
    _extract_keywords,
    _sentiment_breakdown,
    _empty_summary,
)
from tests.conftest import MockReview


class TestStarDistribution:
    def test_basic_distribution(self):
        ratings = [5.0, 4.0, 3.0, 2.0, 1.0]
        dist = _star_distribution(ratings)
        assert dist == {"1": 1, "2": 1, "3": 1, "4": 1, "5": 1}

    def test_all_same_rating(self):
        ratings = [5.0, 5.0, 5.0]
        dist = _star_distribution(ratings)
        assert dist["5"] == 3
        assert dist["1"] == 0

    def test_fractional_ratings_floored(self):
        ratings = [4.5, 4.9, 3.1]
        dist = _star_distribution(ratings)
        assert dist["4"] == 2
        assert dist["3"] == 1


class TestDateRange:
    def test_with_dates(self):
        reviews = [
            MockReview(1, 5.0, "T", "B", date="2024-01-15"),
            MockReview(2, 3.0, "T", "B", date="2024-06-20"),
            MockReview(3, 4.0, "T", "B", date="2024-03-01"),
        ]
        dr = _date_range(reviews)
        assert dr["earliest"] == "2024-01-15"
        assert dr["latest"] == "2024-06-20"

    def test_no_dates(self):
        reviews = [
            MockReview(1, 5.0, "T", "B", date=None),
            MockReview(2, 3.0, "T", "B", date=None),
        ]
        dr = _date_range(reviews)
        assert dr["earliest"] is None
        assert dr["latest"] is None

    def test_partial_dates(self):
        reviews = [
            MockReview(1, 5.0, "T", "B", date="2024-01-01"),
            MockReview(2, 3.0, "T", "B", date=None),
        ]
        dr = _date_range(reviews)
        assert dr["earliest"] == "2024-01-01"
        assert dr["latest"] == "2024-01-01"


class TestVerifiedStats:
    def test_all_verified(self):
        reviews = [MockReview(i, 5.0, "T", "B", verified=True) for i in range(1, 4)]
        stats = _verified_stats(reviews)
        assert stats["count"] == 3
        assert stats["percentage"] == 100.0

    def test_none_verified(self):
        reviews = [MockReview(i, 5.0, "T", "B", verified=False) for i in range(1, 4)]
        stats = _verified_stats(reviews)
        assert stats["count"] == 0
        assert stats["percentage"] == 0.0

    def test_mixed(self):
        reviews = [
            MockReview(1, 5.0, "T", "B", verified=True),
            MockReview(2, 3.0, "T", "B", verified=False),
        ]
        stats = _verified_stats(reviews)
        assert stats["count"] == 1
        assert stats["percentage"] == 50.0


class TestSentimentBreakdown:
    def test_all_positive(self):
        reviews = [MockReview(i, 5.0, "T", "B") for i in range(1, 4)]
        sent = _sentiment_breakdown(reviews)
        assert sent["positive"] == 3
        assert sent["neutral"] == 0
        assert sent["negative"] == 0
        assert sent["positive_pct"] == 100.0

    def test_mixed_sentiment(self):
        reviews = [
            MockReview(1, 5.0, "T", "B"),
            MockReview(2, 3.0, "T", "B"),
            MockReview(3, 1.0, "T", "B"),
        ]
        sent = _sentiment_breakdown(reviews)
        assert sent["positive"] == 1
        assert sent["neutral"] == 1
        assert sent["negative"] == 1

    def test_boundary_ratings(self):
        reviews = [
            MockReview(1, 4.0, "T", "B"),  # positive boundary
            MockReview(2, 2.0, "T", "B"),  # negative boundary
        ]
        sent = _sentiment_breakdown(reviews)
        assert sent["positive"] == 1
        assert sent["negative"] == 1
        assert sent["neutral"] == 0


class TestExtractKeywords:
    def test_extracts_common_words(self):
        reviews = [
            MockReview(1, 5.0, "Great battery", "The battery life is amazing", verified=True),
            MockReview(2, 4.0, "Good battery", "Battery lasts all day long", verified=True),
            MockReview(3, 2.0, "Bad sound", "Sound quality is poor", verified=True),
        ]
        keywords = _extract_keywords(reviews, top_n=5)
        words = [kw["word"] for kw in keywords]
        assert "battery" in words

    def test_stops_words_excluded(self):
        reviews = [
            MockReview(1, 5.0, "Good", "The product is very good and nice", verified=True),
        ]
        keywords = _extract_keywords(reviews, top_n=10)
        words = [kw["word"] for kw in keywords]
        assert "the" not in words
        assert "and" not in words

    def test_keyword_avg_rating(self):
        reviews = [
            MockReview(1, 5.0, "Battery", "Great battery life", verified=True),
            MockReview(2, 1.0, "Battery", "Battery is terrible", verified=True),
        ]
        keywords = _extract_keywords(reviews, top_n=5)
        battery_kw = next((kw for kw in keywords if kw["word"] == "battery"), None)
        assert battery_kw is not None
        assert battery_kw["avg_rating"] == 3.0
        assert battery_kw["count"] == 2

    def test_keyword_mention_pct(self):
        reviews = [
            MockReview(1, 5.0, "Battery", "Great battery life", verified=True),
            MockReview(2, 1.0, "Battery", "Battery is terrible", verified=True),
            MockReview(3, 3.0, "Sound", "Sound quality decent", verified=True),
            MockReview(4, 4.0, "Comfort", "Very comfortable fit", verified=True),
        ]
        keywords = _extract_keywords(reviews, top_n=5)
        battery_kw = next((kw for kw in keywords if kw["word"] == "battery"), None)
        assert battery_kw is not None
        assert battery_kw["mention_pct"] == 50.0  # 2 out of 4 reviews

    def test_plural_normalization(self):
        reviews = [
            MockReview(1, 5.0, "Batteries", "Love the batteries", verified=True),
            MockReview(2, 4.0, "Battery", "Battery is solid", verified=True),
        ]
        keywords = _extract_keywords(reviews, top_n=5)
        # "batteries" should normalize to "battery", merging counts
        battery_kw = next((kw for kw in keywords if kw["word"] == "battery"), None)
        assert battery_kw is not None
        assert battery_kw["count"] == 2


class TestSentimentSampleSize:
    def test_sample_size_included(self):
        reviews = [MockReview(i, 5.0, "T", "B") for i in range(1, 6)]
        sent = _sentiment_breakdown(reviews)
        assert sent["sample_size"] == 5


class TestEmptySummary:
    def test_empty_summary_structure(self):
        summary = _empty_summary()
        assert summary["total_reviews"] == 0
        assert summary["average_rating"] == 0.0
        assert summary["star_distribution"] == {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
        assert summary["date_range"]["earliest"] is None
        assert summary["verified"]["count"] == 0
        assert summary["top_keywords"] == []
        assert summary["sentiment"]["positive"] == 0
