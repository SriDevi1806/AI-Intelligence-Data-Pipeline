
import asyncio
import calendar
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser
from bs4 import BeautifulSoup

from models import NewsModel
from database import init_db, get_session, News
from source_registry import get_sources
from http_client import HTTPClient
from logger import logger


# ============================================================
# CONFIGURATION
# ============================================================

FRESHNESS_HOURS = 24

MAX_ARTICLES_PER_SOURCE = 100

MAX_ARTICLE_TEXT_LENGTH = 30000


# ============================================================
# STATISTICS
# ============================================================

def create_stats():

    return {
        "api_records_received": 0,
        "recent_articles": 0,
        "records_saved": 0,
        "duplicates_skipped": 0,
        "invalid_records": 0,
        "failed_requests": 0,
        "old_articles_skipped": 0,
        "missing_dates": 0,
    }


stats = create_stats()


# ============================================================
# DATE PARSING
# ============================================================

def parse_publication_date(entry):

    for field in (
        "published_parsed",
        "updated_parsed"
    ):

        parsed = entry.get(field)

        if parsed:

            try:

                timestamp = calendar.timegm(parsed)

                return datetime.fromtimestamp(
                    timestamp,
                    tz=timezone.utc
                )

            except (ValueError, TypeError, OverflowError):
                pass

    for field in (
        "published",
        "updated",
        "created",
        "date"
    ):

        value = entry.get(field)

        if not value:
            continue

        try:

            parsed_date = parsedate_to_datetime(value)

            if parsed_date.tzinfo is None:

                parsed_date = parsed_date.replace(
                    tzinfo=timezone.utc
                )

            return parsed_date.astimezone(
                timezone.utc
            )

        except (ValueError, TypeError, OverflowError):

            try:

                parsed_date = datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                )

                if parsed_date.tzinfo is None:

                    parsed_date = parsed_date.replace(
                        tzinfo=timezone.utc
                    )

                return parsed_date.astimezone(
                    timezone.utc
                )

            except (ValueError, TypeError):
                continue

    return None


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(value):

    if not value:
        return None

    soup = BeautifulSoup(
        str(value),
        "html.parser"
    )

    text = soup.get_text(
        separator=" ",
        strip=True
    )

    return " ".join(text.split())


# ============================================================
# FETCH RSS FEED
# ============================================================

async def fetch_rss_feed(client, source):

    print(f"\nFetching: {source.name}")

    try:

        response = await client.get(
            source.url,
            headers={
                "Accept": (
                    "application/rss+xml,"
                    "application/xml,"
                    "text/xml,"
                    "*/*"
                )
            }
        )

        if response is None:

            stats["failed_requests"] += 1

            logger.error(
                "Unable to retrieve RSS feed: %s",
                source.name
            )

            return []

        if not isinstance(response, str):

            stats["failed_requests"] += 1

            logger.error(
                "Unexpected RSS response format: %s",
                source.name
            )

            return []

        feed = feedparser.parse(response)

        if feed.bozo and not feed.entries:

            stats["failed_requests"] += 1

            logger.error(
                "RSS parsing failed: %s",
                source.name
            )

            return []

        entries = feed.entries[
            :MAX_ARTICLES_PER_SOURCE
        ]

        stats["api_records_received"] += len(entries)

        print(
            f"RSS records received: {len(entries)}"
        )

        return entries

    except Exception as error:

        stats["failed_requests"] += 1

        logger.exception(
            "RSS fetching error for %s: %s",
            source.name,
            error
        )

        return []


# ============================================================
# FETCH FULL ARTICLE TEXT
# ============================================================

async def extract_article_text(client, article_url):

    if not article_url:
        return None

    try:

        response = await client.get(
            article_url,
            headers={
                "Accept": "text/html,application/xhtml+xml"
            }
        )

        if not isinstance(response, str):
            return None

        soup = BeautifulSoup(
            response,
            "lxml"
        )

        for element in soup([
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "form",
            "noscript"
        ]):

            element.decompose()

        article = soup.find("article")

        if article:

            text = article.get_text(
                separator=" ",
                strip=True
            )

        else:

            main = soup.find("main")

            if main:

                text = main.get_text(
                    separator=" ",
                    strip=True
                )

            else:

                text = soup.get_text(
                    separator=" ",
                    strip=True
                )

        text = " ".join(text.split())

        if not text:
            return None

        return text[:MAX_ARTICLE_TEXT_LENGTH]

    except Exception as error:

        logger.warning(
            "Full article extraction failed for %s: %s",
            article_url,
            error
        )

        return None


# ============================================================
# CONVERT RSS ENTRY INTO PYDANTIC MODEL
# ============================================================

async def convert_entry_to_model(
    client,
    entry,
    source
):

    title = clean_text(
        entry.get("title")
    )

    article_url = entry.get("link")

    if not title or not article_url:

        stats["invalid_records"] += 1

        return None

    published_at = parse_publication_date(
        entry
    )

    if published_at is None:

        stats["missing_dates"] += 1

        logger.warning(
            "Publication date missing: %s",
            title
        )

        return None

    now = datetime.now(timezone.utc)

    freshness_limit = now - timedelta(
        hours=FRESHNESS_HOURS
    )

    if published_at < freshness_limit:

        stats["old_articles_skipped"] += 1

        return None

    if published_at > now:

        stats["invalid_records"] += 1

        logger.warning(
            "Future publication date skipped: %s",
            title
        )

        return None

    stats["recent_articles"] += 1

    description = clean_text(
        entry.get("summary")
        or entry.get("description")
    )

    full_text = None

    content_items = entry.get("content", [])

    if content_items:

        full_text = clean_text(
            content_items[0].get("value")
        )

    if not full_text or len(full_text) < 500:

        extracted_text = await extract_article_text(
            client,
            article_url
        )

        if extracted_text:

            full_text = extracted_text

    if not full_text:

        full_text = description

    raw_data = {

        "rss_source": source.name,

        "feed_url": source.url,

        "article_url": article_url,

        "rss_id": entry.get("id"),

        "published_original": entry.get("published"),

        "updated_original": entry.get("updated"),

        "author": entry.get("author"),

    }

    try:

        record = NewsModel(

            title=title,

            source_name=source.name,

            description=description,

            full_text=full_text,

            published_at=published_at,

            verified_last_24_hours=True,

            article_url=article_url,

            raw_data=raw_data

        )

        return record

    except Exception as error:

        stats["invalid_records"] += 1

        logger.warning(
            "News validation failed for %s: %s",
            title,
            error
        )

        return None


# ============================================================
# SAVE RECORDS TO DATABASE
# ============================================================

def save_news_records(records):

    seen_urls = set()

    with get_session() as session:

        for record in records:

            article_url = record.article_url

            if not article_url:

                stats["invalid_records"] += 1

                continue

            if article_url in seen_urls:

                stats["duplicates_skipped"] += 1

                continue

            seen_urls.add(article_url)

            existing = session.query(News).filter(
                News.article_url == article_url
            ).first()

            if existing:

                stats["duplicates_skipped"] += 1

                continue

            db_record = News(

                title=record.title,

                source_name=record.source_name,

                description=record.description,

                full_text=record.full_text,

                published_at=record.published_at,

                verified_last_24_hours=(
                    record.verified_last_24_hours
                ),

                article_url=record.article_url,

                raw_data=record.raw_data

            )

            session.add(db_record)

            stats["records_saved"] += 1

            if stats["records_saved"] % 10 == 0:

                print(
                    f"Saved {stats['records_saved']} news articles..."
                )

    print(
        f"Database save completed. "
        f"Saved {stats['records_saved']} articles."
    )


# ============================================================
# MAIN NEWS COLLECTION
# ============================================================

async def collect_news():

    global stats

    stats = create_stats()

    print("=" * 60)

    print("AI NEWS COLLECTION")

    print("=" * 60)

    init_db()

    news_sources = get_sources("news")

    if not news_sources:

        print("No enabled news sources found.")

        return

    print(
        f"\nConfigured news sources: {len(news_sources)}"
    )

    client = HTTPClient()

    all_records = []

    try:

        await client.start()

        for source in news_sources:

            entries = await fetch_rss_feed(
                client,
                source
            )

            for entry in entries:

                record = await convert_entry_to_model(
                    client,
                    entry,
                    source
                )

                if record:

                    all_records.append(record)

            # Be polite to publishers.
            await asyncio.sleep(2)

        print(
            "\nValidated recent articles:",
            len(all_records)
        )

        if all_records:

            save_news_records(all_records)

    finally:

        await client.close()

    # ========================================================
    # SUMMARY
    # ========================================================

    print("\n" + "=" * 60)

    print("AI NEWS COLLECTION SUMMARY")

    print("=" * 60)

    print(
        "RSS Records Received:",
        stats["api_records_received"]
    )

    print(
        "Articles Within Last 24 Hours:",
        stats["recent_articles"]
    )

    print(
        "Records Saved:",
        stats["records_saved"]
    )

    print(
        "Duplicates Skipped:",
        stats["duplicates_skipped"]
    )

    print(
        "Old Articles Skipped:",
        stats["old_articles_skipped"]
    )

    print(
        "Missing Publication Dates:",
        stats["missing_dates"]
    )

    print(
        "Invalid Records:",
        stats["invalid_records"]
    )

    print(
        "Failed Requests:",
        stats["failed_requests"]
    )

    print(
        "Collection completed at:",
        datetime.now(timezone.utc).isoformat()
    )

    print("\nSources:")

    for source in news_sources:

        print(
            "-",
            source.name,
            ":",
            source.url
        )

    print("=" * 60)


# ============================================================
# EXECUTION
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(collect_news())

    except KeyboardInterrupt:

        print("\nCollection stopped by user.")

    except Exception as error:

        logger.exception(
            "News collection failed: %s",
            error
        )

        raise
