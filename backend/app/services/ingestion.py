"""Ingestion service — CSV parsing and demo data generation."""

import csv
import io
import uuid
import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session as DBSession

from app.models.schemas import Session, Review


def create_session(
    db: DBSession,
    product_name: str,
    platform: str = "amazon",
    product_url: str | None = None,
) -> Session:
    """Create a new analysis session and return it."""
    session = Session(
        id=str(uuid.uuid4()),
        product_name=product_name,
        platform=platform,
        product_url=product_url,
    )
    db.add(session)
    db.flush()
    return session


def parse_csv_reviews(
    file_content: bytes,
    session_id: str,
    db: DBSession,
) -> int:
    """Parse a CSV file and insert reviews into the database.

    Expected columns (case-insensitive, flexible matching):
      Required: rating, text (or body or review)
      Optional: title, date, author, verified, helpful_votes

    Returns the number of reviews inserted.
    """
    try:
        text = file_content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = file_content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV file is empty or has no header row.")

    # Normalise header names so users can be flexible
    normalised = {h.strip().lower().replace(" ", "_"): h for h in reader.fieldnames}

    # Map logical names → actual CSV column names
    def _col(candidates: list[str]) -> str | None:
        for c in candidates:
            if c in normalised:
                return normalised[c]
        return None

    rating_col = _col(["rating", "star", "stars", "star_rating"])
    text_col = _col(["text", "body", "review", "review_text", "content", "review_body"])
    title_col = _col(["title", "review_title", "headline"])
    date_col = _col(["date", "review_date", "created_at"])
    author_col = _col(["author", "reviewer", "user", "name", "reviewer_name"])
    verified_col = _col(["verified", "verified_purchase"])
    helpful_col = _col(["helpful_votes", "helpful", "votes"])

    if rating_col is None:
        raise ValueError(
            "CSV must contain a 'rating' column. "
            f"Found columns: {list(reader.fieldnames)}"
        )
    if text_col is None:
        raise ValueError(
            "CSV must contain a 'text' (or 'body' / 'review') column. "
            f"Found columns: {list(reader.fieldnames)}"
        )

    count = 0
    errors: list[str] = []

    for row_num, row in enumerate(reader, start=2):  # row 1 = header
        raw_rating = (row.get(rating_col) or "").strip()
        raw_text = (row.get(text_col) or "").strip()

        if not raw_rating or not raw_text:
            errors.append(f"Row {row_num}: missing rating or text — skipped.")
            continue

        try:
            rating = float(raw_rating)
        except ValueError:
            errors.append(f"Row {row_num}: invalid rating '{raw_rating}' — skipped.")
            continue

        if not (1.0 <= rating <= 5.0):
            errors.append(f"Row {row_num}: rating {rating} out of range [1-5] — skipped.")
            continue

        verified = False
        if verified_col and row.get(verified_col):
            v = row[verified_col].strip().lower()
            verified = v in ("true", "1", "yes", "y")

        helpful = 0
        if helpful_col and row.get(helpful_col):
            try:
                helpful = int(row[helpful_col].strip())
            except ValueError:
                helpful = 0

        review = Review(
            session_id=session_id,
            rating=rating,
            title=(row.get(title_col) or "").strip() if title_col else "",
            body=raw_text,
            author=(row.get(author_col) or "").strip() if author_col else "",
            date=(row.get(date_col) or "").strip() if date_col else "",
            verified=verified,
            helpful_votes=helpful,
        )
        db.add(review)
        count += 1

    if count == 0:
        raise ValueError(
            "No valid reviews found in CSV. "
            + (" ".join(errors[:5]) if errors else "Check your file format.")
        )

    db.flush()
    return count


# ---------------------------------------------------------------------------
# Demo data — 50 realistic AirPods Pro reviews
# ---------------------------------------------------------------------------

_POSITIVE_REVIEWS = [
    ("Amazing sound quality", "The noise cancellation on these AirPods Pro is absolutely incredible. I use them on the subway every day and they block out almost all background noise. The sound quality is crisp and clear with great bass response.", 5.0),
    ("Best earbuds I've owned", "I've tried Sony, Bose, and Samsung earbuds. These AirPods Pro are by far the best for the Apple ecosystem. Seamless switching between my iPhone, iPad, and MacBook.", 5.0),
    ("Great for workouts", "They stay in my ears during intense HIIT workouts. The sweat resistance is legit. Sound quality doesn't suffer even when I'm running outdoors.", 5.0),
    ("Noise cancellation is a game changer", "Working from home with two kids, these are a lifesaver. Transparency mode lets me hear when they need me, ANC mode lets me focus on calls.", 5.0),
    ("Worth every penny", "I was hesitant about the price but these are genuinely worth it. The spatial audio feature watching movies on my iPad is like having a home theater.", 5.0),
    ("Comfortable for all-day wear", "I wear these 8+ hours a day for work calls. The silicone tips are so comfortable I forget they're in my ears. No ear fatigue at all.", 5.0),
    ("Incredible transparency mode", "Transparency mode sounds so natural. I can have a full conversation without taking them out. It's like they're not even there.", 5.0),
    ("Seamless Apple integration", "The instant pairing with my iPhone was magical. Switching between devices is flawless. Siri integration works perfectly for hands-free control.", 4.0),
    ("Great call quality", "People on the other end of my calls say I sound crystal clear even in noisy coffee shops. The microphone array really works well.", 4.0),
    ("Solid battery life", "I get about 5.5 hours on a single charge with ANC on. The case gives me multiple additional charges. More than enough for my daily commute.", 4.0),
    ("Love the adaptive audio", "The new adaptive audio feature automatically adjusts between noise cancellation and transparency based on my environment. Super smart.", 5.0),
    ("Perfect for travel", "Used these on a 12-hour flight. Noise cancellation blocked the engine noise completely. Battery lasted the whole flight with the case.", 5.0),
    ("Find My feature is clutch", "I lose things constantly. The Find My integration saved me twice already — found them in the couch cushions both times.", 4.0),
    ("Great upgrade from original AirPods", "Coming from the original AirPods, the Pro version is a massive upgrade. Better sound, better fit, and the noise cancellation is amazing.", 5.0),
    ("Music sounds phenomenal", "Listening to music on these is a completely different experience. The bass is deep without being muddy, and the highs are crystal clear.", 5.0),
    ("Compact and portable", "The case fits perfectly in my pocket. I carry these everywhere. The build quality feels premium and durable.", 4.0),
    ("Personalized spatial audio rocks", "The personalized spatial audio with head tracking makes watching movies an immersive experience. It's like surround sound in your ears.", 5.0),
    ("Easy to set up", "Literally opened the case near my iPhone and it was paired in seconds. No Bluetooth settings to fiddle with. Apple makes it so easy.", 5.0),
    ("Excellent for podcasts", "Voice clarity for podcasts and audiobooks is outstanding. I can hear every word even in busy environments with ANC on.", 4.0),
    ("MagSafe case is convenient", "The MagSafe charging case is a nice touch. I just place it on my charger and it snaps into place. No fumbling with cables.", 4.0),
]

_NEGATIVE_REVIEWS = [
    ("Battery degrades over time", "After 18 months, battery life dropped from 5.5 hours to barely 3 hours. Apple wants $89 per earbud to replace. That's almost the cost of new ones.", 2.0),
    ("Ear tips fall off", "The silicone ear tips keep coming loose and falling off. I've lost two sets already. They should clip on more securely.", 2.0),
    ("Too expensive for what you get", "At this price point, I expected longer battery life and better water resistance. Sony XM5 offers better value for money.", 2.0),
    ("ANC not as good as Bose", "Coming from Bose QC earbuds, the ANC on these is noticeably weaker. Still blocks some noise but Bose is in another league.", 3.0),
    ("Connectivity issues", "Sometimes they randomly disconnect from my iPhone during calls. Have to put them back in the case and reconnect. Happens 2-3 times a week.", 2.0),
    ("Stem is too long", "The stems sticking out make them look awkward. I wish Apple would make a more discreet design like the Galaxy Buds.", 3.0),
    ("Case scratches easily", "The glossy case picks up scratches within days. Mine looks beat up after just a month of pocket carry. Needs a case for the case.", 3.0),
    ("Not great for small ears", "Even with the smallest tips, these don't fit my ears well. They slowly slide out over 30 minutes. Not everyone has the same ear shape.", 2.0),
    ("No lossless audio support", "For the price, it's disappointing that these don't support lossless audio over Bluetooth. You're limited to AAC codec.", 3.0),
    ("Wind noise is terrible", "Using these outdoors on windy days is awful. The microphones pick up wind noise and ANC can't compensate. Basically unusable on bike rides.", 2.0),
]

_MIXED_REVIEWS = [
    ("Good but not perfect", "Sound quality is excellent and ANC works well for the price. But the battery life could be better and the ear tips don't stay put during workouts.", 3.0),
    ("Decent upgrade", "They're better than the previous gen but not a revolutionary upgrade. If you have the AirPods Pro 1, probably not worth upgrading yet.", 3.0),
    ("Great for Apple users only", "If you're in the Apple ecosystem, these are fantastic. But if you also use Android devices, the experience is significantly worse. Very locked in.", 3.0),
    ("Good sound, mediocre fit", "The sound quality and ANC are top-notch. But I struggle to find a comfortable fit. After an hour my ears start to ache. YMMV.", 3.0),
    ("Overrated but still good", "They're good earbuds but the hype makes them seem better than they are. For $250, I expected mind-blowing, and got just 'really good.'", 3.0),
    ("Love-hate relationship", "When they work, they're amazing. But I've had firmware updates break features, random disconnects, and ear detection issues. Inconsistent.", 3.0),
    ("Fine for casual listening", "For casual music listening and calls, these are great. But audiophiles will be disappointed — they can't compete with wired IEMs at this price.", 3.0),
    ("Improved but still has issues", "USB-C is a welcome change. Sound and ANC improved. But they still don't have multipoint Bluetooth and the case is still scratch-prone.", 4.0),
    ("Good product, bad value", "The product itself is well-made and sounds great. But Apple charging $250 when competitors offer similar features for $150 feels greedy.", 3.0),
    ("Solid for calls, average for music", "Call quality is genuinely the best I've tested in wireless earbuds. But for pure music listening, the Sony WF-1000XM5 edges them out.", 4.0),
    ("Reliable daily driver", "Nothing flashy but they just work every day. Pop them in, they connect instantly, sound is good, ANC does its job. That reliability is worth something.", 4.0),
    ("Better than expected", "I was a skeptic coming from Android. But the AirPods Pro won me over with the ANC quality and how seamlessly they work with my new iPhone.", 4.0),
    ("Comfortable but pricey", "Most comfortable earbuds I've worn. I can sleep with them. But replacing the battery costs almost as much as a new pair, which is frustrating.", 4.0),
    ("Great for commuting", "My daily subway commute is so much better with ANC. I can actually enjoy music without cranking the volume. Transparency mode for announcements is perfect.", 4.0),
    ("Mixed feelings after 6 months", "First 3 months were perfect. Now I notice battery drain is faster, ANC seems weaker, and one earbud occasionally cuts out. Build quality concerns me.", 3.0),
    ("Gifts well", "Bought these as a gift for my daughter. She absolutely loves them. The personalization with engraving was a nice touch from Apple.", 4.0),
    ("Does what it says", "Noise cancellation works. Sound quality is good. They fit comfortably. Nothing more, nothing less. Solid product if you can afford it.", 4.0),
    ("Apple tax is real", "You're paying 30% more for the Apple logo. The tech is good but Samsung and Sony offer comparable products for significantly less.", 3.0),
    ("Perfect for focused work", "As a programmer, I need to block out office noise. These are perfect for that. The ANC lets me enter deep focus mode instantly.", 5.0),
    ("Second pair purchase", "My first pair lasted 2 years before the battery gave out. Liked them enough to buy again. That says something about the product quality.", 4.0),
]


def generate_demo_reviews(session_id: str, db: DBSession) -> int:
    """Insert 50 curated AirPods Pro reviews into the database."""
    all_reviews = _POSITIVE_REVIEWS + _NEGATIVE_REVIEWS + _MIXED_REVIEWS
    base_date = datetime(2024, 1, 15)

    authors = [
        "TechGuru42", "MusicLover99", "DailyCommuter", "FitnessFan2024",
        "AppleEcoSystem", "AudiophileJohn", "BusyMomSarah", "StudentAlex",
        "RemoteWorkerPat", "TravelBloggerKim", "PodcastAddict", "GamerDave",
        "MinimalistMike", "NursePractitioner", "FreelanceDesigner", "RetiredTeacher",
        "YogaInstructor", "CoffeeShopRegular", "SubwayRider_NYC", "WFH_Dad",
        "GradStudent2024", "MarathonRunner", "BookwormBeth", "DigitalNomad",
        "ITManager_Corp", "SoundEngineer", "PilotJones", "TeacherMs_K",
        "ChefAtHome", "DogWalkerPro", "LibrarianQuiet", "PhotographerAnna",
        "StartupFounder", "MedStudent_Rx", "ParentOfThree", "CommuterBill",
        "FitnessCoach", "RetailWorker_J", "ArchitectSam", "MusicProducer_LA",
        "NightShiftRN", "HikerTrailMix", "DataScientist", "WriterInBrooklyn",
        "BaristaLife", "ProjectManager", "RealtorRick", "PhDCandidate",
        "VetTechEmily", "WeekendWarrior",
    ]

    random.seed(42)  # Deterministic for consistent demo

    for i, (title, body, rating) in enumerate(all_reviews):
        days_offset = random.randint(0, 300)
        review = Review(
            session_id=session_id,
            rating=rating,
            title=title,
            body=body,
            author=authors[i % len(authors)],
            date=(base_date + timedelta(days=days_offset)).strftime("%Y-%m-%d"),
            verified=random.random() > 0.3,
            helpful_votes=random.randint(0, 120),
        )
        db.add(review)

    db.flush()
    return len(all_reviews)
