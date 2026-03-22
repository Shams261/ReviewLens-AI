"""Shared fixtures for the ReviewLens test suite."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.schemas import Session, Review, ChatMessage


@pytest.fixture
def db():
    """Create an in-memory SQLite database for each test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def sample_session(db):
    """Create a sample session with reviews."""
    s = Session(
        id="test-session-001",
        product_name="Apple AirPods Pro (2nd Gen)",
        platform="amazon",
    )
    db.add(s)
    db.commit()
    return s


@pytest.fixture
def sample_reviews(db, sample_session):
    """Insert 5 diverse reviews into the test session."""
    reviews = [
        Review(session_id=sample_session.id, rating=5.0, title="Amazing sound",
               body="Noise cancellation is incredible. Best earbuds.", author="User1",
               date="2024-03-12", verified=True, helpful_votes=35),
        Review(session_id=sample_session.id, rating=2.0, title="Battery degraded",
               body="After 18 months, battery barely lasts 2 hours.", author="User2",
               date="2024-06-15", verified=True, helpful_votes=98),
        Review(session_id=sample_session.id, rating=1.0, title="Connectivity issues",
               body="Random disconnects during calls. Very annoying.", author="User3",
               date="2024-05-20", verified=True, helpful_votes=45),
        Review(session_id=sample_session.id, rating=4.0, title="Great call quality",
               body="People say I sound crystal clear in coffee shops.", author="User4",
               date="2024-02-28", verified=True, helpful_votes=8),
        Review(session_id=sample_session.id, rating=3.0, title="Ear tips fall off",
               body="Silicone tips keep coming loose. Design flaw.", author="User5",
               date="2024-08-01", verified=False, helpful_votes=67),
    ]
    db.add_all(reviews)
    db.commit()
    return db.query(Review).filter(Review.session_id == sample_session.id).all()


class MockReview:
    """Lightweight stand-in for the SQLAlchemy Review model."""
    def __init__(self, id, rating, title, body, author="Anon", date="2024-01-01",
                 verified=True, helpful_votes=0):
        self.id = id
        self.rating = rating
        self.title = title
        self.body = body
        self.author = author
        self.date = date
        self.verified = verified
        self.helpful_votes = helpful_votes
