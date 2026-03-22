"""Unit tests for database models and schema integrity."""

import pytest
from app.models.schemas import Session, Review, ChatMessage


class TestSessionModel:
    def test_create_session(self, db):
        s = Session(id="test-1", product_name="Test Product", platform="amazon")
        db.add(s)
        db.commit()
        fetched = db.query(Session).filter(Session.id == "test-1").first()
        assert fetched is not None
        assert fetched.product_name == "Test Product"
        assert fetched.platform == "amazon"

    def test_session_default_id(self, db):
        s = Session(product_name="Test", platform="amazon")
        db.add(s)
        db.commit()
        assert s.id is not None
        assert len(s.id) == 36  # UUID format


class TestReviewModel:
    def test_create_review(self, db, sample_session):
        r = Review(
            session_id=sample_session.id, rating=4.5, title="Good",
            body="Nice product", author="Tester", date="2024-01-01",
            verified=True, helpful_votes=10,
        )
        db.add(r)
        db.commit()
        assert r.id is not None
        assert r.rating == 4.5
        assert r.verified is True

    def test_review_cascade_delete(self, db, sample_session, sample_reviews):
        assert db.query(Review).count() == 5
        db.delete(sample_session)
        db.commit()
        assert db.query(Review).count() == 0


class TestChatMessageModel:
    def test_create_message(self, db, sample_session):
        msg = ChatMessage(
            session_id=sample_session.id, role="user",
            content="Hello", scope_status="in_scope",
        )
        db.add(msg)
        db.commit()
        assert msg.id is not None
        assert msg.cached is False

    def test_message_with_cache_fields(self, db, sample_session):
        msg = ChatMessage(
            session_id=sample_session.id, role="assistant",
            content="Response", scope_status="in_scope",
            cited_reviews='[1, 2, 3]', query_hash="abc123", cached=True,
        )
        db.add(msg)
        db.commit()
        fetched = db.query(ChatMessage).filter(ChatMessage.id == msg.id).first()
        assert fetched.cached is True
        assert fetched.query_hash == "abc123"
        assert fetched.cited_reviews == '[1, 2, 3]'

    def test_message_cascade_delete(self, db, sample_session):
        db.add(ChatMessage(
            session_id=sample_session.id, role="user",
            content="Test", scope_status="in_scope",
        ))
        db.commit()
        assert db.query(ChatMessage).count() == 1
        db.delete(sample_session)
        db.commit()
        assert db.query(ChatMessage).count() == 0
