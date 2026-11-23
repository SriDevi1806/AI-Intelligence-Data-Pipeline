
import asyncio
import json
import re
from datetime import datetime, timezone, timedelta
from html import unescape
from typing import Optional

import aiohttp

from config import (
    JOB_FRESHNESS_HOURS,
    MAX_CONCURRENT_REQUESTS,
    REQUEST_TIMEOUT,
)
from database import Job, get_session
from logger import logger
from models import JobModel


# --------------------------------------------------
# EMPLOYER JOB BOARD CONFIGURATION
# --------------------------------------------------
# Add actual public employer board identifiers here.
#
# Greenhouse:
# {"company_name": "Company Name", "board_token": "board-token"}
#
# Lever:
# {"company_name": "Company Name", "site": "company-site"}
#
# Ashby:
# {"company_name": "Company Name", "board_name": "board-name"}

from job_sources import (
    GREENHOUSE_BOARDS,
    LEVER_BOARDS,
    ASHBY_BOARDS,
)


# --------------------------------------------------
# HELPERS
# --------------------------------------------------

def clean_text(value) -> str:
    if not value:
        return ""

    text = unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_datetime(value) -> Optional[datetime]:
    if value is None:
        return None

    try:
        if isinstance(value, (int, float)):
            timestamp = (
                value / 1000
                if value > 10_000_000_000
                else value
            )
            return datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            )

        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)

        if isinstance(value, str):
            parsed = datetime.fromisoformat(
                value.strip().replace("Z", "+00:00")
            )

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed.astimezone(timezone.utc)

    except (ValueError, TypeError, OverflowError, OSError):
        return None

    return None


def valid_url(url: str) -> bool:
    return (
        isinstance(url, str)
        and url.startswith(("https://", "http://"))
    )


# --------------------------------------------------
# JOB COLLECTOR
# --------------------------------------------------

class JobCollector:

    def __init__(self):
        self.semaphore = asyncio.Semaphore(
            MAX_CONCURRENT_REQUESTS
        )

        self.timeout = aiohttp.ClientTimeout(
            total=REQUEST_TIMEOUT
        )

        self.stats = {
            "sources_checked": 0,
            "records_received": 0,
            "recent_jobs": 0,
            "saved": 0,
            "duplicates": 0,
            "old_jobs_skipped": 0,
            "missing_dates": 0,
            "invalid": 0,
            "failed_requests": 0,
        }

    # --------------------------------------------------
    # HTTP REQUEST
    # --------------------------------------------------

    async def fetch_json(self, session, url):

        async with self.semaphore:
            try:
                async with session.get(url) as response:

                    if response.status != 200:
                        logger.warning(
                            "HTTP %s from %s",
                            response.status,
                            url,
                        )
                        self.stats["failed_requests"] += 1
                        return None

                    return await response.json(
                        content_type=None
                    )

            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                ValueError,
            ) as error:

                logger.error(
                    "Request failed for %s: %s",
                    url,
                    error,
                )

                self.stats["failed_requests"] += 1
                return None

    # --------------------------------------------------
    # GREENHOUSE
    # --------------------------------------------------

    async def collect_greenhouse(self, session, board):

        company = board["company_name"]
        token = board["board_token"]

        url = (
            "https://boards-api.greenhouse.io/v1/boards/"
            f"{token}/jobs?content=true"
        )

        data = await self.fetch_json(session, url)

        if not isinstance(data, dict):
            return []

        records = []

        for item in data.get("jobs", []):

            records.append({
                "title": item.get("title"),
                "company_name": company,
                "location": (
                    item.get("location", {}).get("name", "")
                    if isinstance(item.get("location"), dict)
                    else ""
                ),
                "job_type": "",
                "description": item.get("content", ""),
                # Only accept an explicit first-publication date.
                "published_at": item.get("first_published"),
                "job_url": item.get("absolute_url"),
                "source_name": "Greenhouse",
                "raw_data": item,
            })

        return records

    # --------------------------------------------------
    # LEVER
    # --------------------------------------------------

    async def collect_lever(self, session, board):

        company = board["company_name"]
        site = board["site"]

        url = (
            f"https://api.lever.co/v0/postings/{site}"
            "?mode=json"
        )

        data = await self.fetch_json(session, url)

        if not isinstance(data, list):
            return []

        records = []

        for item in data:

            categories = item.get("categories") or {}

            records.append({
                "title": item.get("text"),
                "company_name": company,
                "location": categories.get("location", ""),
                "job_type": categories.get("commitment", ""),
                "description": item.get("descriptionPlain", ""),
                "published_at": item.get("createdAt"),
                "job_url": item.get("hostedUrl"),
                "source_name": "Lever",
                "raw_data": item,
            })

        return records

    # --------------------------------------------------
    # ASHBY
    # --------------------------------------------------

    async def collect_ashby(self, session, board):

        company = board["company_name"]
        board_name = board["board_name"]

        url = (
            "https://api.ashbyhq.com/posting-api/job-board/"
            f"{board_name}"
        )

        data = await self.fetch_json(session, url)

        if not isinstance(data, dict):
            return []

        records = []

        for item in data.get("jobs", []):

            records.append({
                "title": item.get("title"),
                "company_name": company,
                "location": item.get("location", ""),
                "job_type": item.get("employmentType", ""),
                "description": item.get("descriptionPlain", ""),
                "published_at": item.get("publishedAt"),
                "job_url": item.get("jobUrl"),
                "source_name": "Ashby",
                "raw_data": item,
            })

        return records

    # --------------------------------------------------
    # VALIDATE AND NORMALIZE
    # --------------------------------------------------

    def normalize_job(self, item):

        title = clean_text(item.get("title"))
        company = clean_text(item.get("company_name"))
        job_url = item.get("job_url")

        if not title or not company or not valid_url(job_url):
            self.stats["invalid"] += 1
            return None

        published_at = parse_datetime(
            item.get("published_at")
        )

        if published_at is None:
            self.stats["missing_dates"] += 1
            return None

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(
            hours=JOB_FRESHNESS_HOURS
        )

        if published_at < cutoff or published_at > now:
            self.stats["old_jobs_skipped"] += 1
            return None

        try:
            job = JobModel(
                title=title,
                company_name=company,
                location=clean_text(item.get("location")),
                job_type=clean_text(item.get("job_type")),
                description=clean_text(item.get("description")),
                published_at=published_at,
                verified_last_24_hours=True,
                job_url=job_url,
                source_name=item.get("source_name"),
                raw_data=item.get("raw_data", {}),
            )

            self.stats["recent_jobs"] += 1
            return job

        except Exception as error:

            logger.warning(
                "Validation failed for %s: %s",
                title,
                error,
            )

            self.stats["invalid"] += 1
            return None

    # --------------------------------------------------
    # SAVE TO DATABASE
    # --------------------------------------------------

    def save_jobs(self, jobs):

        with get_session() as db:

            for job in jobs:

                existing = (
                    db.query(Job)
                    .filter(Job.job_url == job.job_url)
                    .first()
                )

                if existing:
                    self.stats["duplicates"] += 1
                    continue

                record = Job(
                    title=job.title,
                    company_name=job.company_name,
                    location=job.location,
                    job_type=job.job_type,
                    description=job.description,
                    published_at=job.published_at,
                    verified_last_24_hours=(
                        job.verified_last_24_hours
                    ),
                    job_url=job.job_url,
                    source_name=job.source_name,
                    raw_data=job.raw_data,
                )

                db.add(record)
                self.stats["saved"] += 1

    # --------------------------------------------------
    # MAIN COLLECTION
    # --------------------------------------------------

    async def run(self):

        headers = {
            "User-Agent": (
                "AI-Intelligence-Data-Pipeline/1.0"
            ),
            "Accept": "application/json",
        }

        boards = (
            [(self.collect_greenhouse, b) for b in GREENHOUSE_BOARDS]
            + [(self.collect_lever, b) for b in LEVER_BOARDS]
            + [(self.collect_ashby, b) for b in ASHBY_BOARDS]
        )

        self.stats["sources_checked"] = len(boards)

        if not boards:
            logger.warning(
                "No employer job boards configured. "
                "Add real public board identifiers first."
            )
            return self.stats

        async with aiohttp.ClientSession(
            timeout=self.timeout,
            headers=headers,
        ) as session:

            tasks = [
                collector(session, board)
                for collector, board in boards
            ]

            responses = await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

        all_records = []

        for response in responses:

            if isinstance(response, Exception):
                logger.error(
                    "Job collection error: %s",
                    response,
                )
                self.stats["failed_requests"] += 1
                continue

            if response:
                all_records.extend(response)

        self.stats["records_received"] = len(all_records)

        validated_jobs = []

        for item in all_records:

            job = self.normalize_job(item)

            if job is not None:
                validated_jobs.append(job)

        if validated_jobs:
            self.save_jobs(validated_jobs)

        return self.stats


# --------------------------------------------------
# EXECUTION
# --------------------------------------------------

async def main():

    print("\n" + "=" * 55)
    print("AI INTELLIGENCE DATA PIPELINE")
    print("JOB COLLECTION")
    print("=" * 55)

    collector = JobCollector()
    stats = await collector.run()

    print("\nJOB COLLECTION SUMMARY")
    print("-" * 55)

    for key, value in stats.items():
        print(f"{key.replace('_', ' ').title():25}: {value}")

    print("-" * 55)

    if stats["sources_checked"] == 0:
        print("No job boards configured.")
        print("Add public employer board identifiers and run again.")
    else:
        print("Job collection process finished.")

    print("=" * 55)


if __name__ == "__main__":
    asyncio.run(main())
