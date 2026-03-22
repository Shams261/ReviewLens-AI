"""Amazon review scraper — RapidAPI (Real-Time Amazon Data) primary, CSV upload fallback."""

import os
import re
import logging
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# URL validation & ASIN extraction
# ---------------------------------------------------------------------------

_AMAZON_PATTERN = re.compile(
    r"amazon\.(com|co\.uk|ca|com\.au|in|de|fr|es|it|co\.jp)"
)
_ASIN_PATTERN = re.compile(r"/(?:dp|product|gp/product)/([A-Z0-9]{10})")

# Map Amazon domain suffix → RapidAPI country code
_DOMAIN_TO_COUNTRY = {
    "com": "US", "ca": "CA", "co.uk": "GB", "com.au": "AU",
    "in": "IN", "de": "DE", "fr": "FR", "es": "ES",
    "it": "IT", "co.jp": "JP",
}


def validate_amazon_url(url: str) -> tuple[str, str]:
    """Validate and extract ASIN and domain from an Amazon product URL.

    Returns (asin, domain) tuple — e.g. ("B0C1QNRGHC", "ca").
    Raises ValueError if the URL is not a valid Amazon product page.
    """
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    parsed = urlparse(url)
    host = parsed.hostname or ""

    domain_match = _AMAZON_PATTERN.search(host)
    if not domain_match:
        raise ValueError(
            "URL must be an Amazon product page "
            "(e.g., https://www.amazon.com/dp/B0D1XD1ZV3)."
        )

    asin_match = _ASIN_PATTERN.search(parsed.path)
    if not asin_match:
        raise ValueError(
            "Could not find a product ID (ASIN) in the URL. "
            "Please use a direct product link like https://www.amazon.com/dp/B0D1XD1ZV3."
        )

    domain = domain_match.group(1)
    return asin_match.group(1), domain


def extract_product_name(url: str) -> str:
    """Try to extract a human-readable product name from the URL slug."""
    parsed = urlparse(url)
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 2 and parts[-2] == "dp":
        slug = parts[0] if parts[0] != "dp" else ""
        if slug:
            return slug.replace("-", " ").title()[:80]
    return "Amazon Product"


# ---------------------------------------------------------------------------
# RapidAPI — Real-Time Amazon Data
# Docs: https://rapidapi.com/letscrape-6bRBa3QguO5/api/real-time-amazon-data
# ---------------------------------------------------------------------------

RAPIDAPI_HOST = "real-time-amazon-data.p.rapidapi.com"


async def scrape_with_rapidapi(
    asin: str,
    domain: str = "com",
    max_pages: int = 5,
    on_progress=None,
) -> list[dict]:
    """Fetch reviews via RapidAPI Real-Time Amazon Data endpoint.

    Args:
        on_progress: Optional async callback(page, total_so_far, max_pages)
                     called after each page fetch for live progress updates.
    """
    api_key = os.getenv("RAPIDAPI_KEY")
    if not api_key:
        raise RuntimeError("RAPIDAPI_KEY not configured")

    country = _DOMAIN_TO_COUNTRY.get(domain, "US")
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": RAPIDAPI_HOST,
    }

    all_reviews: list[dict] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for page in range(1, max_pages + 1):
            params = {
                "asin": asin,
                "country": country,
                "page": str(page),
            }

            try:
                resp = await client.get(
                    f"https://{RAPIDAPI_HOST}/product-reviews",
                    params=params,
                    headers=headers,
                )

                if resp.status_code == 401:
                    raise RuntimeError("Invalid RapidAPI key.")
                if resp.status_code == 403:
                    raise RuntimeError(
                        "RapidAPI subscription required. Please subscribe to the "
                        "'Real-Time Amazon Data' API on RapidAPI (free tier available)."
                    )
                if resp.status_code == 429:
                    logger.warning("RapidAPI rate limited on page %d", page)
                    break
                if resp.status_code != 200:
                    logger.warning(
                        "RapidAPI returned %d on page %d: %s",
                        resp.status_code, page, resp.text[:200],
                    )
                    break

                data = resp.json()

                if not data.get("status") == "OK":
                    logger.warning("RapidAPI status not OK: %s", data.get("status"))
                    break

                reviews = data.get("data", {}).get("reviews", [])

                if not reviews:
                    break

                for r in reviews:
                    parsed = _parse_rapidapi_review(r)
                    if parsed:
                        all_reviews.append(parsed)

                # Report progress after each page
                if on_progress:
                    await on_progress(page, len(all_reviews), max_pages)

            except httpx.TimeoutException:
                logger.warning("RapidAPI timeout on page %d", page)
                break
            except RuntimeError:
                raise
            except Exception as exc:
                logger.warning("RapidAPI error on page %d: %s", page, exc)
                break

    return all_reviews


def _parse_rapidapi_review(raw: dict) -> dict | None:
    """Normalise a single review from RapidAPI Real-Time Amazon Data response."""
    body = raw.get("review_comment") or raw.get("review") or raw.get("body") or ""
    body = body.strip()
    if not body:
        return None

    rating_raw = raw.get("review_star_rating") or raw.get("rating") or "0"
    rating = _extract_rating(str(rating_raw))
    if rating == 0:
        return None

    # Verified: field is "Verified Purchase" string or bool
    verified_raw = raw.get("is_verified_purchase") or raw.get("verified_purchase") or False
    if isinstance(verified_raw, str):
        verified = verified_raw.lower() in ("true", "verified purchase", "yes")
    else:
        verified = bool(verified_raw)

    return {
        "rating": rating,
        "title": (raw.get("review_title") or raw.get("title") or "").strip(),
        "body": body,
        "author": (raw.get("review_author") or raw.get("author") or "").strip(),
        "date": (raw.get("review_date") or raw.get("date") or "").strip(),
        "verified": verified,
        "helpful_votes": _extract_helpful(
            raw.get("helpful_vote_statement") or raw.get("helpful_votes") or ""
        ),
    }


# ---------------------------------------------------------------------------
# Unified scrape function
# Tier 1: RapidAPI → Tier 2: CSV Upload (user action) → Tier 3: Demo
# ---------------------------------------------------------------------------

async def scrape_amazon_reviews(asin: str, domain: str = "com") -> list[dict]:
    """Try RapidAPI to fetch reviews. Returns list of parsed review dicts.

    Scraping tiers:
    - Tier 1 (Primary): RapidAPI Real-Time Amazon Data
    - Tier 2 (Fallback): CSV Upload (requires user action — guided via error message)
    - Tier 3 (Demo): Pre-loaded mock data (available via /ingest/demo)

    Raises RuntimeError if scraping fails or returns no reviews.
    """
    if os.getenv("RAPIDAPI_KEY"):
        try:
            reviews = await scrape_with_rapidapi(asin, domain=domain)
            if reviews:
                logger.info("RapidAPI returned %d reviews for %s (country=%s)",
                            len(reviews), asin, _DOMAIN_TO_COUNTRY.get(domain, "US"))
                return reviews
            logger.warning("RapidAPI returned 0 reviews for %s", asin)
        except RuntimeError:
            raise
        except Exception as exc:
            logger.warning("RapidAPI failed for %s: %s", asin, exc)

    if not os.getenv("RAPIDAPI_KEY"):
        raise RuntimeError(
            "URL scraping is not configured (RAPIDAPI_KEY missing). "
            "Please upload a CSV file or use the demo data instead."
        )
    raise RuntimeError(
        "Could not fetch reviews for this product. The product may have no reviews, "
        "or the Amazon region may not be supported. "
        "Please try uploading a CSV file instead, or use the demo data."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_rating(text: str) -> float:
    """Extract numeric rating from text like '4.0 out of 5 stars' or '4.0'."""
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if match:
        val = float(match.group(1))
        if 1.0 <= val <= 5.0:
            return val
    return 0.0


def _extract_helpful(text) -> int:
    """Extract helpful vote count from text like '42 people found this helpful'."""
    if isinstance(text, (int, float)):
        return int(text)
    text = str(text)
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else 0
