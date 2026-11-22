import asyncio
import logging
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional

import aiohttp

from config import (
    GEMINI_API_KEY,
    GROQ_API_KEY,
    DEEPSEEK_API_KEY,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
)

logger = logging.getLogger("AI_Intelligence_Pipeline")

MAX_CHUNK_CHARS = 12000
MIN_CHUNK_CHARS = 500

RETRYABLE_STATUS_CODES = {
    408, 425, 429, 500, 502, 503, 504
}


class ProviderError(Exception):
    pass


class ChunkingError(Exception):
    pass


def get_providers():

    providers = []

    if GEMINI_API_KEY:
        providers.append({
            "name": "Gemini Flash",
            "url": (
                "https://generativelanguage.googleapis.com/"
                "v1beta/models/gemini-2.5-flash:generateContent"
            ),
            "key": GEMINI_API_KEY,
            "type": "gemini"
        })

    if GROQ_API_KEY:
        providers.append({
            "name": "Groq Llama 3",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "key": GROQ_API_KEY,
            "type": "openai",
            "model": "llama-3.3-70b-versatile"
        })

    if DEEPSEEK_API_KEY:
        providers.append({
            "name": "DeepSeek",
            "url": "https://api.deepseek.com/chat/completions",
            "key": DEEPSEEK_API_KEY,
            "type": "openai",
            "model": "deepseek-chat"
        })

    return providers


def get_retry_after(value: Optional[str]) -> Optional[float]:

    if not value:
        return None

    try:
        return max(0, float(value))
    except (ValueError, TypeError):
        pass

    try:
        retry_time = parsedate_to_datetime(value)

        if retry_time.tzinfo is None:
            retry_time = retry_time.replace(tzinfo=timezone.utc)

        seconds = (
            retry_time - datetime.now(timezone.utc)
        ).total_seconds()

        return max(0, seconds)

    except (TypeError, ValueError, OverflowError):
        return None


async def retry_delay(attempt, retry_after=None):

    exponential = min(60, 2 ** attempt)
    jitter = random.uniform(0, 1)
    delay = exponential + jitter

    if retry_after is not None:
        delay = max(delay, retry_after)

    logger.warning("Retrying after %.2f seconds", delay)
    await asyncio.sleep(delay)


def extract_response(data, provider_type):

    try:
        if provider_type == "gemini":

            candidates = data.get("candidates", [])

            if not candidates:
                raise ProviderError("Gemini returned no candidates")

            parts = (
                candidates[0]
                .get("content", {})
                .get("parts", [])
            )

            result = "".join(
                part.get("text", "")
                for part in parts
            )

        else:

            choices = data.get("choices", [])

            if not choices:
                raise ProviderError("Provider returned no choices")

            result = (
                choices[0]
                .get("message", {})
                .get("content", "")
            )

        if not isinstance(result, str) or not result.strip():
            raise ProviderError("Provider returned empty response")

        return result.strip()

    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(
            f"Invalid provider response: {exc}"
        ) from exc


async def call_provider(provider, prompt, session):

    headers = {
        "Content-Type": "application/json"
    }

    if provider["type"] == "gemini":

        headers["x-goog-api-key"] = provider["key"]

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 4096
            }
        }

    else:

        headers["Authorization"] = f"Bearer {provider['key']}"

        payload = {
            "model": provider["model"],
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.2,
            "max_tokens": 4096
        }

    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    for attempt in range(MAX_RETRIES):

        try:

            async with session.post(
                provider["url"],
                headers=headers,
                json=payload,
                timeout=timeout
            ) as response:

                if response.status == 413:
                    raise ChunkingError(
                        "HTTP 413: Request entity too large"
                    )

                if response.status in RETRYABLE_STATUS_CODES:

                    retry_after = get_retry_after(
                        response.headers.get("Retry-After")
                    )

                    if attempt == MAX_RETRIES - 1:
                        raise ProviderError(
                            f"HTTP {response.status}: Retry limit reached"
                        )

                    await response.read()
                    await retry_delay(attempt, retry_after)
                    continue

                if response.status >= 400:

                    error_text = await response.text()

                    raise ProviderError(
                        f"HTTP {response.status}: {error_text[:500]}"
                    )

                data = await response.json()

                return extract_response(
                    data,
                    provider["type"]
                )

        except (ChunkingError, ProviderError):
            raise

        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            ValueError
        ) as exc:

            if attempt == MAX_RETRIES - 1:
                raise ProviderError(
                    f"Request failed: {exc}"
                ) from exc

            await retry_delay(attempt)

    raise ProviderError("All retry attempts failed")


def split_text(text, max_chars):

    chunks = []
    remaining = text.strip()

    while remaining:

        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        split_at = remaining.rfind("\n", 0, max_chars)

        if split_at < max_chars // 2:
            split_at = remaining.rfind(". ", 0, max_chars)

        if split_at < max_chars // 2:
            split_at = max_chars
        else:
            split_at += 1

        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    return [chunk for chunk in chunks if chunk]


async def process_with_chunking(
    provider,
    prompt,
    session,
    depth=0
):

    if depth > 8:
        raise ChunkingError("Maximum chunking depth exceeded")

    try:
        return await call_provider(
            provider,
            prompt,
            session
        )

    except ChunkingError:

        if len(prompt) <= MIN_CHUNK_CHARS:
            raise ChunkingError(
                "Prompt is too small to split further"
            )

        new_size = max(
            MIN_CHUNK_CHARS,
            len(prompt) // 2
        )

        chunks = split_text(prompt, new_size)

        if len(chunks) < 2:
            raise ChunkingError("Unable to split oversized prompt")

        logger.warning(
            "HTTP 413 detected. Splitting into %s chunks",
            len(chunks)
        )

        results = []

        for index, chunk in enumerate(chunks, start=1):

            logger.info(
                "Processing chunk %s/%s",
                index,
                len(chunks)
            )

            result = await process_with_chunking(
                provider,
                chunk,
                session,
                depth + 1
            )

            results.append(result)

        return "\n\n".join(results)


async def generate(prompt: str) -> dict[str, Any]:

    if not isinstance(prompt, str) or not prompt.strip():
        return {
            "success": False,
            "provider": None,
            "response": None,
            "error": "Prompt cannot be empty"
        }

    providers = get_providers()

    if not providers:
        return {
            "success": False,
            "provider": None,
            "response": None,
            "error": "No LLM API keys configured"
        }

    timeout = aiohttp.ClientTimeout(
        total=None,
        connect=REQUEST_TIMEOUT
    )

    async with aiohttp.ClientSession(timeout=timeout) as session:

        errors = []

        for provider in providers:

            logger.info(
                "Trying provider: %s",
                provider["name"]
            )

            try:

                response = await process_with_chunking(
                    provider,
                    prompt,
                    session
                )

                logger.info(
                    "Successful response from %s",
                    provider["name"]
                )

                return {
                    "success": True,
                    "provider": provider["name"],
                    "response": response,
                    "error": None
                }

            except Exception as exc:

                errors.append(
                    f"{provider['name']}: {exc}"
                )

                logger.error(
                    "Provider failed: %s",
                    exc
                )

        return {
            "success": False,
            "provider": None,
            "response": None,
            "error": " | ".join(errors)
        }


async def main():

    print("=" * 60)
    print("LLM FALLBACK SYSTEM")
    print("=" * 60)

    providers = get_providers()

    print("\nCONFIGURED PROVIDERS")

    if providers:
        for index, provider in enumerate(providers, start=1):
            print(f"{index}. {provider['name']}")
    else:
        print("No API keys configured.")

    print("\nCHUNKING TEST")

    sample = "Artificial intelligence research.\n" * 2000

    chunks = split_text(sample, MAX_CHUNK_CHARS)

    print(f"Original characters: {len(sample)}")
    print(f"Chunks generated: {len(chunks)}")

    print(
        "All chunks within size limit:",
        all(len(chunk) <= MAX_CHUNK_CHARS for chunk in chunks)
    )

    print("\nRETRY-AFTER TEST")
    print("Numeric Retry-After:", get_retry_after("5"))

    print("\nLLM FALLBACK INITIALIZATION SUCCESSFUL")
    print("=" * 60)


if __name__ == "__main__":

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )

    asyncio.run(main())
