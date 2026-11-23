
import asyncio
import re
from datetime import datetime, timezone
from typing import Any

import aiohttp

import config
from database import init_db, get_session, Product
from models import ProductModel
from logger import logger


# ============================================================
# PRODUCT COLLECTOR
# Source: Public Hugging Face Spaces API
# ============================================================

BASE_URL = "https://huggingface.co/api/spaces"


SEARCH_TERMS = [
    "AI",
    "chatbot",
    "LLM",
    "AI agent",
    "image generation",
    "speech",
    "translation",
    "RAG",
    "text generation",
    "computer vision",
    "generative AI",
    "machine learning",
    "natural language processing",
    "text to image",
    "AI assistant",
    "voice assistant",
    "OCR",
    "document AI",
    "recommendation system",
    "AI automation",
    "video generation",
    "code generation",
]


TARGET_RECORDS = 1000


def normalize_name(value: str) -> str:
    """Create a deterministic name for duplicate detection."""
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def get_value(obj: Any, key: str, default=None):
    """Safely read a field from an API dictionary."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def extract_description(item: dict) -> str:
    """Extract a description only when the API provides one."""
    card_data = item.get("cardData") or {}

    if isinstance(card_data, dict):
        description = (
            card_data.get("short_description")
            or card_data.get("description")
        )

        if description:
            return str(description).strip()

    return ""


def build_product_data(item: dict) -> dict:
    """Convert an API result into product model input."""
    space_id = item.get("id")

    if not space_id:
        return {}

    product_url = f"https://huggingface.co/spaces/{space_id}"

    author = item.get("author")

    if isinstance(author, dict):
        author = author.get("name") or author.get("fullname")

    if not author and "/" in space_id:
        author = space_id.split("/", 1)[0]

    name = space_id.split("/", 1)[-1].replace("-", " ").replace("_", " ")

    description = extract_description(item)

    tags = item.get("tags") or []
    models = item.get("models") or []

    if not isinstance(tags, list):
        tags = []

    if not isinstance(models, list):
        models = []

    return {
        "name": name,
        "title": name,
        "product_name": name,
        "description": description,
        "url": product_url,
        "website": product_url,
        "source_url": product_url,
        "category": "AI application",
        "product_type": "Hugging Face Space",
        "company": author,
        "startup_name": author,
        "pricing_model": None,
        "source_name": "Hugging Face",
        "author": author,
        "likes": item.get("likes"),
        "sdk": item.get("sdk"),
        "tags": tags,
        "models": models,
        "last_modified": item.get("lastModified"),
        "raw_data": item,
        "normalized_name": normalize_name(name),
    }


def validate_product(data: dict):
    """
    Validate against the existing ProductModel.
    Only pass fields that the current model actually defines.
    """
    model_fields = ProductModel.model_fields

    candidate = {}

    aliases = {
        "name": ["name", "title", "product_name"],
        "description": ["description", "summary"],
        "url": ["url", "website", "source_url"],
        "website": ["website", "url", "source_url"],
        "source_url": ["source_url", "url", "website"],
        "category": ["category", "product_type"],
        "company": ["company", "startup_name", "author"],
        "startup_name": ["startup_name", "company", "author"],
        "pricing_model": ["pricing_model"],
        "normalized_name": ["normalized_name"],
        "raw_data": ["raw_data"],
        "source_name": ["source_name"],
    }

    for field_name in model_fields:
        possible_keys = aliases.get(field_name, [field_name])

        for key in possible_keys:
            if key in data and data[key] is not None:
                candidate[field_name] = data[key]
                break

    return ProductModel.model_validate(candidate)


def model_to_database(product_model):
    """
    Convert the validated Pydantic object into fields
    supported by the existing SQLAlchemy Product table.
    """
    model_data = product_model.model_dump(exclude_unset=True)

    table_columns = {
        column.name
        for column in Product.__table__.columns
    }

    database_data = {
        key: value
        for key, value in model_data.items()
        if key in table_columns
    }

    # Add normalized_name when the database supports it.
    if "normalized_name" in table_columns:
        name = (
            database_data.get("name")
            or database_data.get("title")
            or database_data.get("product_name")
        )

        if name:
            database_data["normalized_name"] = normalize_name(name)

    return database_data


async def fetch_spaces(session, search_term):
    """Fetch public Spaces for one search term."""
    params = {
        "search": search_term,
        "limit": 100,
        "sort": "likes",
    }

    timeout = aiohttp.ClientTimeout(
        total=getattr(config, "REQUEST_TIMEOUT", 30)
    )

    retries = getattr(config, "MAX_RETRIES", 5)

    for attempt in range(retries):
        try:
            async with session.get(
                BASE_URL,
                params=params,
                timeout=timeout,
            ) as response:

                if response.status == 200:
                    result = await response.json()

                    if isinstance(result, list):
                        return result

                    logger.warning(
                        "Unexpected API response for %s",
                        search_term,
                    )
                    return []

                if response.status == 429:
                    wait_time = min(2 ** attempt, 60)
                    logger.warning(
                        "Rate limited. Waiting %s seconds.",
                        wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue

                if response.status in (500, 502, 503, 504):
                    await asyncio.sleep(min(2 ** attempt, 30))
                    continue

                
            error_body = await response.text()

            logger.error(
                "Hugging Face returned HTTP %s for %s: %s",
                response.status,
                search_term,
                error_body[:1000],
            )

            return []


        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
        ) as error:
            logger.warning(
                "Request failed for '%s': %s",
                search_term,
                error,
            )
            await asyncio.sleep(min(2 ** attempt, 30))

    logger.error("Retries exhausted for '%s'", search_term)
    return []


async def collect_products():
    """Main product collection workflow."""

    print("\n" + "=" * 60)
    print("AI PRODUCT COLLECTION")
    print("=" * 60)

    init_db()

    total_received = 0
    saved = 0
    duplicates = 0
    invalid = 0
    failed = 0

    collected_ids = set()

    connector = aiohttp.TCPConnector(
        limit=5,
        enable_cleanup_closed=True,
    )

    headers = {
        "User-Agent": "AI-Intelligence-Pipeline/1.0"
    }

    async with aiohttp.ClientSession(
        connector=connector,
        headers=headers,
    ) as http_session:

        
        session_manager = get_session()
        session = session_manager.__enter__()

        try:
            for term in SEARCH_TERMS:

                if saved >= TARGET_RECORDS:
                    break

                print(f"\nSearching: {term}")

                records = await fetch_spaces(
                    http_session,
                    term,
                )

                total_received += len(records)

                print(f"API records received: {len(records)}")

                for item in records:

                    if saved >= TARGET_RECORDS:
                        break

                    try:
                        space_id = item.get("id")

                        if not space_id:
                            invalid += 1
                            continue

                        if space_id in collected_ids:
                            duplicates += 1
                            continue

                        collected_ids.add(space_id)

                        # Ignore private or disabled entries.
                        if item.get("private") is True:
                            continue

                        if item.get("disabled") is True:
                            continue

                        product_data = build_product_data(item)

                        if not product_data.get("source_url"):
                            invalid += 1
                            continue

                        product_model = validate_product(
                            product_data
                        )

                        database_data = model_to_database(
                            product_model
                        )

                        if not database_data:
                            invalid += 1
                            logger.warning(
                                "No matching database fields for %s",
                                space_id,
                            )
                            continue

                        # Check existing records by source URL.
                        table_columns = {
                            column.name
                            for column in Product.__table__.columns
                        }

                        existing = None

                        if "source_url" in table_columns:
                            existing = (
                                session.query(Product)
                                .filter_by(
                                    source_url=product_data["source_url"]
                                )
                                .first()
                            )

                        elif "url" in table_columns:
                            existing = (
                                session.query(Product)
                                .filter_by(
                                    url=product_data["source_url"]
                                )
                                .first()
                            )

                        elif "normalized_name" in table_columns:
                            existing = (
                                session.query(Product)
                                .filter_by(
                                    normalized_name=normalize_name(
                                        product_data["name"]
                                    )
                                )
                                .first()
                            )

                        if existing:
                            duplicates += 1
                            continue

                        db_product = Product(**database_data)

                        session.add(db_product)
                        session.commit()

                        saved += 1

                        if saved % 50 == 0:
                            print(
                                f"Saved {saved} products..."
                            )

                    except Exception as error:
                        session.rollback()
                        invalid += 1

                        logger.warning(
                            "Product record skipped: %s",
                            error,
                        )

        finally:
            session_manager.__exit__(None, None, None)


    print("\n" + "=" * 60)
    print("PRODUCT COLLECTION SUMMARY")
    print("=" * 60)

    print(f"API Records Received: {total_received}")
    print(f"Unique Space IDs: {len(collected_ids)}")
    print(f"Records Saved: {saved}")
    print(f"Duplicates Skipped: {duplicates}")
    print(f"Invalid Records: {invalid}")
    print(f"Failed Requests: {failed}")

    print(
        "Collection completed at:",
        datetime.now(timezone.utc).isoformat(),
    )

    print("\nSource: https://huggingface.co/spaces")
    print("API: https://huggingface.co/api/spaces")

    if saved < TARGET_RECORDS:
        print(
            f"\nNOTE: Target is {TARGET_RECORDS}; "
            f"only {saved} records were saved."
        )

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(collect_products())
