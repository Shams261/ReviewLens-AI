"""Unit tests for the deterministic analytics engine."""

import pytest
from tests.conftest import MockReview
from app.services.deterministic import try_deterministic


PRODUCT = "Apple AirPods Pro (2nd Gen)"


def _make_reviews():
    return [
        MockReview(1, 5.0, "Amazing sound", "Noise cancellation is incredible. Best earbuds.", helpful_votes=35),
        MockReview(2, 2.0, "Battery degraded", "After 18 months, battery barely lasts 2 hours.", helpful_votes=98),
        MockReview(3, 1.0, "Connectivity issues", "Random disconnects during calls.", helpful_votes=45),
        MockReview(4, 4.0, "Great call quality", "Crystal clear in coffee shops.", helpful_votes=8),
        MockReview(5, 3.0, "Ear tips fall off", "Silicone tips keep coming loose.", verified=False, helpful_votes=67),
    ]


class TestDeterministicMatching:
    def test_top_complaints_matches(self):
        result = try_deterministic("What are the top complaints?", _make_reviews(), PRODUCT)
        assert result.matched
        assert "negative review" in result.text.lower() or "2 stars or below" in result.text.lower()

    def test_top_praise_matches(self):
        result = try_deterministic("What are the most praised features?", _make_reviews(), PRODUCT)
        assert result.matched
        assert "positive review" in result.text.lower() or "4 stars" in result.text.lower()

    def test_average_rating_matches(self):
        result = try_deterministic("What is the average rating?", _make_reviews(), PRODUCT)
        assert result.matched
        assert "/5" in result.text

    def test_rating_distribution_matches(self):
        result = try_deterministic("Show the star distribution", _make_reviews(), PRODUCT)
        assert result.matched
        assert "distribution" in result.text.lower() or "reviews" in result.text.lower()

    def test_count_stars_matches(self):
        result = try_deterministic("How many 1-star reviews?", _make_reviews(), PRODUCT)
        assert result.matched
        assert "1" in result.text  # at least review #3 is 1-star

    def test_verified_stats_matches(self):
        result = try_deterministic("What do verified purchasers say?", _make_reviews(), PRODUCT)
        assert result.matched
        assert "verified" in result.text.lower()

    def test_review_count_matches(self):
        result = try_deterministic("How many reviews are there?", _make_reviews(), PRODUCT)
        assert result.matched
        assert "5" in result.text

    def test_mention_keyword_matches(self):
        result = try_deterministic("Do any mention battery?", _make_reviews(), PRODUCT)
        assert result.matched
        assert "battery" in result.text.lower()

    def test_sentiment_summary_matches(self):
        result = try_deterministic("What is the overall sentiment?", _make_reviews(), PRODUCT)
        assert result.matched
        assert "sentiment" in result.text.lower()

    def test_most_helpful_matches(self):
        result = try_deterministic("What is the most helpful review?", _make_reviews(), PRODUCT)
        assert result.matched
        assert "helpful" in result.text.lower()

    def test_recent_reviews_matches(self):
        result = try_deterministic("Show the most recent reviews", _make_reviews(), PRODUCT)
        assert result.matched

    def test_aspect_battery_matches(self):
        result = try_deterministic("How is the battery life?", _make_reviews(), PRODUCT)
        assert result.matched
        assert "battery" in result.text.lower()


class TestDeterministicNoMatch:
    def test_complex_query_not_matched(self):
        result = try_deterministic("Summarize the themes across all categories with a timeline", _make_reviews(), PRODUCT)
        assert not result.matched

    def test_open_ended_not_matched(self):
        result = try_deterministic("Tell me everything interesting", _make_reviews(), PRODUCT)
        assert not result.matched

    def test_pros_and_cons_now_matched(self):
        """Synonym expansion means 'pros and cons' is handled deterministically."""
        result = try_deterministic("Compare the pros and cons across all categories", _make_reviews(), PRODUCT)
        assert result.matched


class TestDeterministicEmptyReviews:
    def test_empty_reviews_not_matched(self):
        result = try_deterministic("What are the top complaints?", [], PRODUCT)
        assert not result.matched

    def test_empty_reviews_rating(self):
        result = try_deterministic("What is the average rating?", [], PRODUCT)
        assert not result.matched

    def test_empty_reviews_count(self):
        result = try_deterministic("How many reviews?", [], PRODUCT)
        assert not result.matched


class TestDeterministicCitations:
    def test_complaints_include_citations(self):
        result = try_deterministic("What are the top complaints?", _make_reviews(), PRODUCT)
        assert result.matched
        assert "[Review #" in result.text

    def test_count_stars_includes_citations(self):
        result = try_deterministic("How many 5-star reviews?", _make_reviews(), PRODUCT)
        assert result.matched
        assert "[Review #" in result.text

    def test_mention_keyword_includes_citations(self):
        result = try_deterministic("Do any mention battery?", _make_reviews(), PRODUCT)
        assert result.matched
        assert "[Review #" in result.text


class TestContractionNormalization:
    def test_whats_the_average(self):
        result = try_deterministic("What's the average rating?", _make_reviews(), PRODUCT)
        assert result.matched
        assert "/5" in result.text

    def test_dont_contraction(self):
        result = try_deterministic("What's the overall sentiment?", _make_reviews(), PRODUCT)
        assert result.matched


class TestConfidenceMetadata:
    def test_deterministic_has_confidence(self):
        result = try_deterministic("What is the average rating?", _make_reviews(), PRODUCT)
        assert result.matched
        assert result.confidence > 0.0
        assert result.matched_intent == "rating_stats"
        assert result.evidence_count == 5

    def test_count_stars_intent(self):
        result = try_deterministic("How many 5-star reviews?", _make_reviews(), PRODUCT)
        assert result.matched_intent == "count_stars"
        assert result.confidence >= 0.9

    def test_low_evidence_complaint(self):
        # Only 1 negative review — should show low confidence
        reviews = [
            MockReview(1, 5.0, "Great", "Love it"),
            MockReview(2, 5.0, "Perfect", "Amazing"),
            MockReview(3, 1.0, "Bad battery", "Battery dies fast"),
        ]
        result = try_deterministic("What are the top complaints?", reviews, PRODUCT)
        assert result.matched
        assert result.confidence <= 0.5  # Low confidence for 1 negative review

    def test_unmatched_has_zero_confidence(self):
        result = try_deterministic("Tell me everything", _make_reviews(), PRODUCT)
        assert not result.matched
        assert result.confidence == 0.0


class TestMixedDateFormats:
    def test_iso_dates_sorted(self):
        reviews = [
            MockReview(1, 5.0, "Old", "Old review", date="2023-01-15"),
            MockReview(2, 4.0, "New", "New review", date="2024-06-20"),
            MockReview(3, 3.0, "Mid", "Mid review", date="2024-01-01"),
        ]
        result = try_deterministic("Show the most recent reviews", reviews, PRODUCT)
        assert result.matched
        # Most recent should be listed first — review #2 (June 2024)
        assert result.text.index("Review #2") < result.text.index("Review #1")

    def test_english_date_format(self):
        reviews = [
            MockReview(1, 5.0, "Old", "Old review", date="January 1, 2023"),
            MockReview(2, 4.0, "New", "New review", date="December 25, 2024"),
        ]
        result = try_deterministic("Show the latest reviews", reviews, PRODUCT)
        assert result.matched
        assert result.text.index("Review #2") < result.text.index("Review #1")


class TestWordBoundaryMatching:
    def test_fit_does_not_match_profit(self):
        reviews = [
            MockReview(1, 5.0, "Profitable", "This was a profitable purchase overall"),
        ]
        result = try_deterministic("Do any reviews mention fit?", reviews, PRODUCT)
        assert result.matched
        assert "0" in result.text or "No reviews" in result.text

    def test_exact_word_matches(self):
        reviews = [
            MockReview(1, 5.0, "Good fit", "The fit is perfect for my ears"),
        ]
        result = try_deterministic("Do any reviews mention fit?", reviews, PRODUCT)
        assert result.matched
        assert "1" in result.text


class TestOverlappingIntentPhrases:
    def test_star_distribution_not_count_stars(self):
        result = try_deterministic("Show the star distribution", _make_reviews(), PRODUCT)
        assert result.matched
        assert result.matched_intent == "rating_distribution"

    def test_how_many_5_star_is_count(self):
        result = try_deterministic("How many 5-star reviews?", _make_reviews(), PRODUCT)
        assert result.matched
        assert result.matched_intent == "count_stars"


class TestEmptyTitleBody:
    def test_empty_body(self):
        reviews = [
            MockReview(1, 5.0, "Good", "", helpful_votes=10),
            MockReview(2, 3.0, None, "Some text"),
        ]
        result = try_deterministic("What is the most helpful review?", reviews, PRODUCT)
        assert result.matched
        assert "Review #1" in result.text

    def test_none_fields(self):
        reviews = [
            MockReview(1, 5.0, None, None),
            MockReview(2, 3.0, None, None),
        ]
        result = try_deterministic("What is the average rating?", reviews, PRODUCT)
        assert result.matched
        assert "/5" in result.text


class TestLongQueryGuardrail:
    def test_complex_multipart_query_rejected(self):
        q = "What are the main complaints about battery life and how do they compare to sound quality issues across different rating levels"
        result = try_deterministic(q, _make_reviews(), PRODUCT)
        assert not result.matched

    def test_short_query_still_works(self):
        result = try_deterministic("What are the top complaints?", _make_reviews(), PRODUCT)
        assert result.matched


class TestSynonymExpansion:
    def test_what_are_the_issues(self):
        result = try_deterministic("What are the issues?", _make_reviews(), PRODUCT)
        assert result.matched

    def test_what_do_people_like(self):
        result = try_deterministic("What do people like?", _make_reviews(), PRODUCT)
        assert result.matched

    def test_feedback_about_keyword(self):
        result = try_deterministic("feedback about battery", _make_reviews(), PRODUCT)
        assert result.matched
        assert "battery" in result.text.lower()

    def test_what_do_reviewers_think(self):
        result = try_deterministic("What do reviewers think?", _make_reviews(), PRODUCT)
        assert result.matched


class TestMinimumEvidenceThreshold:
    def test_single_negative_shows_low_evidence(self):
        reviews = [
            MockReview(1, 5.0, "Great sound", "Noise cancellation is incredible"),
            MockReview(2, 5.0, "Amazing", "Best earbuds ever"),
            MockReview(3, 1.0, "Bad", "Battery dies fast"),
        ]
        result = try_deterministic("What are the top complaints?", reviews, PRODUCT)
        assert result.matched
        assert "not enough" in result.text.lower()

    def test_sufficient_negative_shows_full_analysis(self):
        reviews = [
            MockReview(1, 1.0, "Bad battery", "Battery dies in 1 hour", helpful_votes=10),
            MockReview(2, 2.0, "Poor sound", "Sound quality is terrible", helpful_votes=5),
            MockReview(3, 1.0, "Connectivity", "Keeps disconnecting from phone", helpful_votes=3),
        ]
        result = try_deterministic("What are the top complaints?", reviews, PRODUCT)
        assert result.matched
        assert "not enough" not in result.text.lower()
