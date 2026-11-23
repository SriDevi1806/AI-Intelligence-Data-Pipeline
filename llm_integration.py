
import asyncio
import json
import logging
from typing import Any, Optional

from pydantic import ValidationError

from llm_fallback import generate
from models import (
    StartupModel,
    ProductModel,
    ResearchPaperModel,
    JobModel,
    NewsModel,
)
from entity_resolver import resolve_entity, save_entity_mapping

logger = logging.getLogger("AI_Intelligence_Pipeline")


# ============================================================
# MODEL REGISTRY
# ============================================================

MODEL_REGISTRY = {
    "startup": StartupModel,
    "product": ProductModel,
    "research_paper": ResearchPaperModel,
    "job": JobModel,
    "news": NewsModel,
}


# ============================================================
# EXTRACTION PROMPTS
# ============================================================

def build_extraction_prompt(
    entity_type: str,
    source_text: str,
    source_url: Optional[str] = None,
) -> str:

    if entity_type not in MODEL_REGISTRY:
        raise ValueError(
            f"Unsupported entity type: {entity_type}"
        )

    source_reference = source_url or "Not provided"

    return f"""
You are a precise information extraction system.

Extract structured information from the supplied source.

ENTITY TYPE: {entity_type}

SOURCE URL:
{source_reference}

RULES:
1. Use only information explicitly supported by the source.
2. Never invent company names, dates, URLs, authors or descriptions.
3. Use null for missing optional fields.
4. Use an empty list for missing list fields.
5. Return exactly one JSON object.
6. Do not include Markdown code fences.
7. Do not include explanations outside the JSON object.
8. Preserve original source information.
9. Do not claim that a record is verified unless the source supports it.

EXPECTED JSON FIELDS:

startup:
name, normalized_name, website, description,
industry, headquarters, source_url, raw_data

product:
name, company_name, description, category,
website, source_url, raw_data

research_paper:
title, authors, abstract, published_date,
arxiv_id, github_url, github_stars,
paper_url, source_url, raw_data

job:
title, company_name, location, job_type,
description, published_at, verified_last_24_hours,
job_url, source_name, raw_data

news:
title, source_name, description, full_text,
published_at, verified_last_24_hours,
article_url, raw_data

SOURCE TEXT:
{source_text}
"""


# ============================================================
# JSON EXTRACTION
# ============================================================

def parse_json_response(response: str) -> dict:

    if not response or not response.strip():
        raise ValueError("LLM returned an empty response")

    cleaned = response.strip()

    if cleaned.startswith("```"):
        lines = cleaned.splitlines()

        if lines and lines[0].startswith("```"):
            lines = lines[1:]

        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        cleaned = "\n".join(lines).strip()

    try:
        data = json.loads(cleaned)

    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start == -1 or end <= start:
            raise ValueError(
                "No valid JSON object found in LLM response"
            )

        data = json.loads(cleaned[start:end + 1])

    if not isinstance(data, dict):
        raise ValueError(
            "LLM response must be a JSON object"
        )

    return data


# ============================================================
# COMPANY NAME RESOLUTION
# ============================================================

def resolve_company_fields(
    entity_type: str,
    data: dict
) -> dict:

    if entity_type == "startup":
        name = data.get("name")

    elif entity_type in {"product", "job"}:
        name = data.get("company_name")

    else:
        name = None

    if name:
        result = resolve_entity(name)

        if result.get("resolved"):
            if entity_type == "startup":
                data["normalized_name"] = (
                    result["canonical_name"]
                )
            else:
                data["company_name"] = (
                    result["canonical_name"]
                )

    return data


# ============================================================
# ENTITY MAPPING LOGGING
# ============================================================

def log_entity_mapping(
    entity_type: str,
    original_name: Optional[str],
    source_url: Optional[str] = None
) -> bool:

    if not original_name:
        return False

    if entity_type not in {"startup", "product", "job"}:
        return False

    result = resolve_entity(original_name)

    if not result.get("resolved"):
        logger.warning(
            "Entity not resolved: %s",
            original_name
        )
        return False

    return save_entity_mapping(
        result,
        entity_type=entity_type,
        source_url=source_url
    )


# ============================================================
# STRUCTURED EXTRACTION
# ============================================================

async def extract_record(
    entity_type: str,
    source_text: str,
    source_url: Optional[str] = None,
) -> dict[str, Any]:

    if entity_type not in MODEL_REGISTRY:
        return {
            "success": False,
            "entity_type": entity_type,
            "record": None,
            "error": "Unsupported entity type",
        }

    if not source_text or not source_text.strip():
        return {
            "success": False,
            "entity_type": entity_type,
            "record": None,
            "error": "Source text is empty",
        }

    try:
        prompt = build_extraction_prompt(
            entity_type,
            source_text,
            source_url
        )

        llm_result = await generate(prompt)

        if not llm_result.get("success"):
            return {
                "success": False,
                "entity_type": entity_type,
                "record": None,
                "error": llm_result.get("error"),
            }

        extracted_data = parse_json_response(
            llm_result["response"]
        )

        # Preserve the original company name for mapping.
        if entity_type == "startup":
            original_entity_name = extracted_data.get("name")
        elif entity_type in {"product", "job"}:
            original_entity_name = extracted_data.get("company_name")
        else:
            original_entity_name = None

        extracted_data = resolve_company_fields(
            entity_type,
            extracted_data
        )

        # Preserve the actual source URL.
        if source_url:
            extracted_data["source_url"] = source_url

        model_class = MODEL_REGISTRY[entity_type]

        # Validate before saving mapping.
        validated_record = model_class.model_validate(
            extracted_data
        )

        # Save only after successful validation.
        if original_entity_name:
            try:
                log_entity_mapping(
                    entity_type=entity_type,
                    original_name=original_entity_name,
                    source_url=source_url
                )
            except Exception:
                # Mapping logging must not discard a valid record.
                logger.exception(
                    "Entity mapping logging failed for %s",
                    original_entity_name
                )

        logger.info(
            "Successfully extracted and validated %s",
            entity_type
        )

        return {
            "success": True,
            "entity_type": entity_type,
            "provider": llm_result.get("provider"),
            "record": validated_record.model_dump(
                mode="json"
            ),
            "error": None,
        }

    except ValidationError as exc:
        logger.error(
            "Pydantic validation failed: %s",
            exc
        )

        return {
            "success": False,
            "entity_type": entity_type,
            "record": None,
            "error": str(exc),
        }

    except Exception as exc:
        logger.exception(
            "Extraction failed for %s",
            entity_type
        )

        return {
            "success": False,
            "entity_type": entity_type,
            "record": None,
            "error": str(exc),
        }


# ============================================================
# SYNCHRONOUS WRAPPER
# ============================================================

def extract_record_sync(
    entity_type: str,
    source_text: str,
    source_url: Optional[str] = None,
) -> dict[str, Any]:

    try:
        asyncio.get_running_loop()

    except RuntimeError:
        return asyncio.run(
            extract_record(
                entity_type,
                source_text,
                source_url
            )
        )

    raise RuntimeError(
        "An event loop is already running. "
        "Use await extract_record(...) instead."
    )


# ============================================================
# LOCAL VALIDATION TEST
# ============================================================

def main():

    print("=" * 60)
    print("LLM INTEGRATION MODULE")
    print("=" * 60)

    print("\nRegistered extraction models:")

    for entity_type, model_class in MODEL_REGISTRY.items():
        print(
            f"{entity_type} -> {model_class.__name__}"
        )

    print("\nJSON parsing test:")

    sample = """
    {
        "name": "OpenAI",
        "website": "https://openai.com",
        "description": "Artificial intelligence company",
        "source_url": "https://openai.com"
    }
    """

    parsed = parse_json_response(sample)

    validated = StartupModel.model_validate(parsed)

    print("Validated startup:", validated.name)

    print("\nEntity resolution test:")

    result = resolve_entity("Open AI")

    print("Original:", result["original_name"])
    print("Canonical:", result["canonical_name"])
    print("Resolved:", result["resolved"])

    print("\nLLM integration initialization successful!")
    print("=" * 60)


if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )

    main()
