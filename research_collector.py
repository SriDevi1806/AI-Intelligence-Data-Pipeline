
import asyncio
import re
import random
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from typing import Optional

import aiohttp

import config
from database import init_db, get_session, ResearchPaper
from models import ResearchPaperModel
from logger import logger


# ============================================================
# RESEARCH PAPER COLLECTOR
# Source: Public arXiv API
# ============================================================

BASE_URL = "https://export.arxiv.org/api/query"

TARGET_RECORDS = 1000
BATCH_SIZE = 100

# AI-related arXiv categories
SEARCH_QUERY = (
    "(cat:cs.AI OR "
    "cat:cs.LG OR "
    "cat:cs.CL OR "
    "cat:cs.CV OR "
    "cat:cs.RO OR "
    "cat:cs.NE OR "
    "cat:stat.ML)"
)

NAMESPACE = {
    "atom": "http://www.w3.org/2005/Atom"
}


# ============================================================
# DATE UTILITIES
# ============================================================

def parse_arxiv_date(value: Optional[str]):
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return parsed.astimezone(timezone.utc)

    except (ValueError, TypeError):
        return None


# ============================================================
# ARXIV ID EXTRACTION
# ============================================================

def extract_arxiv_id(paper_url: str) -> Optional[str]:
    if not paper_url:
        return None

    match = re.search(
        r"/abs/([^/?#]+)",
        paper_url
    )

    if not match:
        return None

    arxiv_id = match.group(1)

    # Remove version suffix, e.g. v1, v2
    arxiv_id = re.sub(r"v\d+$", "", arxiv_id)

    return arxiv_id


# ============================================================
# XML PARSING
# ============================================================

def get_element_text(entry, tag):
    element = entry.find(
        f"atom:{tag}",
        NAMESPACE
    )

    if element is not None and element.text:
        return element.text.strip()

    return None


def parse_arxiv_response(xml_content: str):
    try:
        root = ET.fromstring(xml_content)

    except ET.ParseError as error:
        logger.error(
            "Could not parse arXiv XML response: %s",
            error
        )
        return []

    entries = root.findall(
        "atom:entry",
        NAMESPACE
    )

    papers = []

    for entry in entries:

        try:
            paper_url = get_element_text(
                entry,
                "id"
            )

            if not paper_url:
                continue

            paper_url = paper_url.strip()

            arxiv_id = extract_arxiv_id(
                paper_url
            )

            if not arxiv_id:
                continue

            title = get_element_text(
                entry,
                "title"
            )

            if not title:
                continue

            title = re.sub(
                r"\s+",
                " ",
                title
            ).strip()

            abstract = get_element_text(
                entry,
                "summary"
            )

            if abstract:
                abstract = re.sub(
                    r"\s+",
                    " ",
                    abstract
                ).strip()

            authors = []

            for author in entry.findall(
                "atom:author",
                NAMESPACE
            ):

                name_element = author.find(
                    "atom:name",
                    NAMESPACE
                )

                if (
                    name_element is not None
                    and name_element.text
                ):
                    authors.append(
                        name_element.text.strip()
                    )

            published = parse_arxiv_date(
                get_element_text(
                    entry,
                    "published"
                )
            )

            updated = parse_arxiv_date(
                get_element_text(
                    entry,
                    "updated"
                )
            )

            categories = []

            for category in entry.findall(
                "atom:category",
                NAMESPACE
            ):

                category_name = category.attrib.get(
                    "term"
                )

                if category_name:
                    categories.append(
                        category_name
                    )

            # Preserve the actual arXiv source URL.
            raw_data = {
                "arxiv_id": arxiv_id,
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "published": (
                    published.isoformat()
                    if published else None
                ),
                "updated": (
                    updated.isoformat()
                    if updated else None
                ),
                "categories": categories,
                "paper_url": paper_url,
                "source": "arXiv"
            }

            papers.append({
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "published_date": published,
                "arxiv_id": arxiv_id,
                "paper_url": paper_url,
                "source_url": paper_url,
                "raw_data": raw_data
            })

        except Exception as error:

            logger.warning(
                "Skipping invalid arXiv entry: %s",
                error
            )

    return papers


# ============================================================
# FETCH PAPERS FROM ARXIV
# ============================================================

async def fetch_papers(
    http_session,
    start: int
):
    params = {
        "search_query": SEARCH_QUERY,
        "start": start,
        "max_results": BATCH_SIZE,
        "sortBy": "submittedDate",
        "sortOrder": "descending"
    }

    timeout = aiohttp.ClientTimeout(
        total=getattr(
            config,
            "REQUEST_TIMEOUT",
            30
        )
    )

    retries = getattr(
        config,
        "MAX_RETRIES",
        5
    )

    for attempt in range(retries):

        try:

            async with http_session.get(
                BASE_URL,
                params=params,
                timeout=timeout
            ) as response:

                if response.status == 200:

                    xml_content = await response.text()

                    return parse_arxiv_response(
                        xml_content
                    )

                if response.status == 429:

                    wait_time = min(
                        2 ** attempt + random.random(),
                        60
                    )

                    logger.warning(
                        "arXiv rate limit. Waiting %.2f seconds.",
                        wait_time
                    )

                    await asyncio.sleep(wait_time)
                    continue

                if response.status in (
                    500,
                    502,
                    503,
                    504
                ):

                    wait_time = min(
                        2 ** attempt + random.random(),
                        30
                    )

                    logger.warning(
                        "arXiv server error %s. Retrying.",
                        response.status
                    )

                    await asyncio.sleep(wait_time)
                    continue

                error_body = await response.text()

                logger.error(
                    "arXiv HTTP %s: %s",
                    response.status,
                    error_body[:500]
                )

                return None

        except (
            aiohttp.ClientError,
            asyncio.TimeoutError
        ) as error:

            logger.warning(
                "arXiv request failed: %s",
                error
            )

            await asyncio.sleep(
                min(
                    2 ** attempt + random.random(),
                    30
                )
            )

    logger.error(
        "arXiv retries exhausted at offset %s",
        start
    )

    return None


# ============================================================
# VALIDATE PAPER
# ============================================================

def validate_paper(data: dict):

    return ResearchPaperModel.model_validate(
        data
    )


# ============================================================
# DATABASE DUPLICATE CHECK
# ============================================================

def paper_exists(session, arxiv_id, paper_url):

    existing = session.query(
        ResearchPaper
    ).filter(
        (
            ResearchPaper.arxiv_id == arxiv_id
        ) |
        (
            ResearchPaper.paper_url == paper_url
        )
    ).first()

    return existing is not None


# ============================================================
# SAVE PAPER
# ============================================================

def save_paper(session, paper_model):

    paper_data = paper_model.model_dump(
        exclude_unset=True
    )

    db_paper = ResearchPaper(
        **paper_data
    )

    session.add(db_paper)

    # Flush detects database constraint problems.
    session.flush()

    # Commit this record safely.
    session.commit()


# ============================================================
# MAIN COLLECTION WORKFLOW
# ============================================================

async def collect_research_papers():

    print("\n" + "=" * 60)
    print("AI RESEARCH PAPER COLLECTION")
    print("=" * 60)

    init_db()

    saved = 0
    duplicates = 0
    invalid = 0
    failed = 0
    total_received = 0

    start = 0

    headers = {
        "User-Agent": (
            "AI-Intelligence-Pipeline/1.0 "
            "(research metadata collection)"
        )
    }

    connector = aiohttp.TCPConnector(
        limit=2,
        enable_cleanup_closed=True
    )

    async with aiohttp.ClientSession(
        connector=connector,
        headers=headers
    ) as http_session:

        with get_session() as db_session:

            while saved < TARGET_RECORDS:

                print(
                    f"\nFetching arXiv batch: "
                    f"offset {start}"
                )

                records = await fetch_papers(
                    http_session,
                    start
                )

                if records is None:
                    failed += 1
                    break

                if not records:
                    print(
                        "No more research papers returned."
                    )
                    break

                received = len(records)

                total_received += received

                print(
                    f"API records received: {received}"
                )

                for item in records:

                    if saved >= TARGET_RECORDS:
                        break

                    try:

                        paper_model = validate_paper(
                            item
                        )

                        if paper_exists(
                            db_session,
                            paper_model.arxiv_id,
                            paper_model.paper_url
                        ):

                            duplicates += 1
                            continue

                        save_paper(
                            db_session,
                            paper_model
                        )

                        saved += 1

                        if saved % 50 == 0:

                            print(
                                f"Saved {saved} research papers..."
                            )

                    except Exception as error:

                        db_session.rollback()

                        invalid += 1

                        logger.warning(
                            "Research paper skipped: %s",
                            error
                        )

                # Move to the next page using the
                # number of entries actually received.
                start += received

                if received < BATCH_SIZE:
                    print(
                        "Reached the end of available results."
                    )
                    break

                # Respect arXiv API request frequency.
                if saved < TARGET_RECORDS:
                    await asyncio.sleep(3.5)

    # ========================================================
    # COLLECTION SUMMARY
    # ========================================================

    print("\n" + "=" * 60)
    print("RESEARCH PAPER COLLECTION SUMMARY")
    print("=" * 60)

    print(
        f"API Records Received: {total_received}"
    )

    print(
        f"Records Saved: {saved}"
    )

    print(
        f"Duplicates Skipped: {duplicates}"
    )

    print(
        f"Invalid Records: {invalid}"
    )

    print(
        f"Failed Requests: {failed}"
    )

    print(
        "Collection completed at:",
        datetime.now(timezone.utc).isoformat()
    )

    print(
        "\nSource: https://arxiv.org"
    )

    print(
        "API: https://export.arxiv.org/api/query"
    )

    if saved < TARGET_RECORDS:

        print(
            f"\nNOTE: Target is {TARGET_RECORDS}; "
            f"this run saved {saved} new records."
        )

    print("=" * 60)


# ============================================================
# EXECUTION
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        collect_research_papers()
    )
