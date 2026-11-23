
import asyncio
import json
import re
import random
from datetime import datetime, timezone

import aiohttp

from config import REQUEST_TIMEOUT, MAX_RETRIES
from models import StartupModel
from database import init_db, get_session, Startup
from logger import logger


# Public Y Combinator AI-tagged company dataset
YC_AI_API = "https://yc-oss.github.io/api/tags/ai.json"

# Source documentation
YC_API_DOCUMENTATION = "https://github.com/yc-oss/api"


class StartupCollector:

    def __init__(self):

        self.stats = {
            "api_requests": 0,
            "total_records_received": 0,
            "valid_ai_companies": 0,
            "records_saved": 0,
            "duplicates_skipped": 0,
            "invalid_records": 0,
            "failed_requests": 0,
        }

        self.timeout = aiohttp.ClientTimeout(
            total=REQUEST_TIMEOUT
        )

    @staticmethod
    def normalize_name(name):

        name = name.lower().strip()

        name = re.sub(
            r"\b(incorporated|inc|limited|ltd|llc|corp|corporation)\b",
            "",
            name,
        )

        return re.sub(r"[^a-z0-9]", "", name)

    async def fetch_ai_companies(self):

        headers = {
            "User-Agent": "AI-Intelligence-Data-Pipeline/1.0",
            "Accept": "application/json",
        }

        async with aiohttp.ClientSession(
            timeout=self.timeout,
            headers=headers,
        ) as session:

            for attempt in range(MAX_RETRIES + 1):

                self.stats["api_requests"] += 1

                try:

                    logger.info(
                        "Downloading YC AI company dataset..."
                    )

                    async with session.get(YC_AI_API) as response:

                        if response.status == 200:

                            data = await response.json(
                                content_type=None
                            )

                            if not isinstance(data, list):

                                raise ValueError(
                                    "Expected a JSON array from YC API"
                                )

                            logger.info(
                                "Received %s AI company records",
                                len(data),
                            )

                            return data

                        if response.status == 429 or response.status >= 500:

                            if attempt < MAX_RETRIES:

                                retry_after = response.headers.get(
                                    "Retry-After"
                                )

                                try:
                                    delay = float(retry_after)
                                except (TypeError, ValueError):
                                    delay = min(
                                        2 ** attempt + random.random(),
                                        60,
                                    )

                                logger.warning(
                                    "HTTP %s. Retrying in %.2f seconds",
                                    response.status,
                                    delay,
                                )

                                await asyncio.sleep(delay)
                                continue

                        response.raise_for_status()

                except (
                    aiohttp.ClientError,
                    asyncio.TimeoutError,
                    ValueError,
                ) as exc:

                    if attempt >= MAX_RETRIES:

                        logger.exception(
                            "YC dataset download failed: %s",
                            exc,
                        )

                        self.stats["failed_requests"] += 1
                        return []

                    delay = min(
                        2 ** attempt + random.random(),
                        60,
                    )

                    logger.warning(
                        "Request failed. Retry %s/%s in %.2f seconds",
                        attempt + 1,
                        MAX_RETRIES,
                        delay,
                    )

                    await asyncio.sleep(delay)

        self.stats["failed_requests"] += 1
        return []

    def transform_record(self, company):

        name = company.get("name")

        if not isinstance(name, str) or not name.strip():
            return None

        normalized_name = self.normalize_name(name)

        if not normalized_name:
            return None

        tags = company.get("tags") or []

        if not isinstance(tags, list):
            tags = []

        # Keep only records explicitly tagged as AI.
        if not any(
            isinstance(tag, str) and tag.strip().lower() == "ai"
            for tag in tags
        ):
            return None

        profile_url = company.get("url")

        if not profile_url and company.get("slug"):
            profile_url = (
                "https://www.ycombinator.com/companies/"
                + company["slug"]
            )

        if not profile_url:
            return None

        description = (
            company.get("long_description")
            or company.get("one_liner")
        )

        locations = company.get("all_locations")

        payload = {
            "name": name.strip(),
            "normalized_name": normalized_name,
            "website": company.get("website"),
            "description": description,
            "industry": company.get("industry")
            or company.get("subindustry"),
            "headquarters": locations,
            "source_url": profile_url,
            "raw_data": company,
        }

        return payload

    def validate_record(self, payload):

        try:

            return StartupModel(**payload)

        except Exception as exc:

            logger.warning(
                "Invalid startup record %s: %s",
                payload.get("name"),
                exc,
            )

            self.stats["invalid_records"] += 1
            return None

    def save_record(self, record):

        with get_session() as session:

            existing = (
                session.query(Startup)
                .filter(
                    Startup.normalized_name
                    == record.normalized_name
                )
                .first()
            )

            if existing:
                return False

            startup = Startup(
                name=record.name,
                normalized_name=record.normalized_name,
                website=str(record.website)
                if record.website else None,
                description=record.description,
                industry=record.industry,
                headquarters=record.headquarters,
                source_url=str(record.source_url),
                raw_data=json.dumps(
                    record.raw_data or {},
                    ensure_ascii=False,
                    default=str,
                ),
            )

            session.add(startup)

        return True

    async def collect(self):

        init_db()

        print("\n" + "=" * 60)
        print("Y COMBINATOR AI STARTUP DATA COLLECTION")
        print("=" * 60)

        logger.info("Startup collection started")

        companies = await self.fetch_ai_companies()

        self.stats["total_records_received"] = len(companies)

        if not companies:

            logger.error(
                "No records received. Check API availability."
            )

            self.print_report()
            return

        for company in companies:

            try:

                payload = self.transform_record(company)

                if payload is None:
                    self.stats["invalid_records"] += 1
                    continue

                self.stats["valid_ai_companies"] += 1

                validated = self.validate_record(payload)

                if validated is None:
                    continue

                saved = self.save_record(validated)

                if saved:

                    self.stats["records_saved"] += 1

                    logger.info(
                        "Saved startup: %s",
                        validated.name,
                    )

                else:

                    self.stats["duplicates_skipped"] += 1

            except Exception:

                self.stats["invalid_records"] += 1

                logger.exception(
                    "Error processing company: %s",
                    company.get("name", "Unknown"),
                )

        self.print_report()

    def print_report(self):

        print("\n" + "=" * 60)
        print("STARTUP COLLECTION REPORT")
        print("=" * 60)

        for key, value in self.stats.items():

            print(
                f"{key.replace('_', ' ').title()}: {value}"
            )

        print("=" * 60)

        print("Dataset API:", YC_AI_API)
        print("Documentation:", YC_API_DOCUMENTATION)

        print(
            "Collection completed at:",
            datetime.now(timezone.utc).isoformat(),
        )

        print("=" * 60)


async def main():

    collector = StartupCollector()

    await collector.collect()


if __name__ == "__main__":

    asyncio.run(main())
