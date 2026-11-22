
import asyncio
import random

import aiohttp

from config import (
    MAX_CONCURRENT_REQUESTS,
    REQUEST_TIMEOUT,
    MAX_RETRIES
)

from logger import logger


# --------------------------------------------------
# HTTP CLIENT
# --------------------------------------------------

class HTTPClient:

    def __init__(self):

        self.semaphore = asyncio.Semaphore(
            MAX_CONCURRENT_REQUESTS
        )

        self.timeout = aiohttp.ClientTimeout(
            total=REQUEST_TIMEOUT
        )

        self.session = None

        self.headers = {
            "User-Agent": (
                "AIIntelligenceDataPipeline/1.0 "
                "(Research and data collection)"
            ),
            "Accept": (
                "text/html,application/json,"
                "application/xml;q=0.9,*/*;q=0.8"
            )
        }

    # --------------------------------------------------
    # START SESSION
    # --------------------------------------------------

    async def start(self):

        if self.session is None or self.session.closed:

            connector = aiohttp.TCPConnector(
                limit=MAX_CONCURRENT_REQUESTS,
                enable_cleanup_closed=True
            )

            self.session = aiohttp.ClientSession(
                timeout=self.timeout,
                connector=connector,
                headers=self.headers
            )

            logger.info("HTTP client session started.")

    # --------------------------------------------------
    # CLOSE SESSION
    # --------------------------------------------------

    async def close(self):

        if self.session and not self.session.closed:

            await self.session.close()

            logger.info("HTTP client session closed.")

    # --------------------------------------------------
    # ASYNC GET REQUEST
    # --------------------------------------------------

    async def get(
        self,
        url: str,
        params=None,
        headers=None
    ):

        if self.session is None or self.session.closed:
            await self.start()

        request_headers = {
            **self.headers,
            **(headers or {})
        }

        for attempt in range(MAX_RETRIES + 1):

            try:

                async with self.semaphore:

                    async with self.session.get(
                        url,
                        params=params,
                        headers=request_headers
                    ) as response:

                        status = response.status

                        if status == 200:

                            content_type = response.headers.get(
                                "Content-Type", ""
                            )

                            if "application/json" in content_type:
                                return await response.json(
                                    content_type=None
                                )

                            return await response.text()

                        if status == 429 or status in {
                            408, 500, 502, 503, 504
                        }:

                            if attempt == MAX_RETRIES:

                                logger.error(
                                    "Request failed after retries: %s (%s)",
                                    url,
                                    status
                                )

                                return None

                            retry_after = response.headers.get(
                                "Retry-After"
                            )

                            if retry_after and retry_after.isdigit():

                                delay = min(
                                    float(retry_after),
                                    60.0
                                )

                            else:

                                delay = min(
                                    2 ** attempt + random.uniform(0, 1),
                                    60.0
                                )

                            logger.warning(
                                "HTTP %s. Retry %s/%s in %.2f seconds: %s",
                                status,
                                attempt + 1,
                                MAX_RETRIES,
                                delay,
                                url
                            )

                        else:

                            logger.error(
                                "HTTP request rejected: %s (%s)",
                                url,
                                status
                            )

                            return None

                await asyncio.sleep(delay)

            except asyncio.TimeoutError:

                logger.warning(
                    "Request timeout: %s",
                    url
                )

            except aiohttp.ClientError as error:

                logger.warning(
                    "HTTP client error for %s: %s",
                    url,
                    error
                )

            except Exception:

                logger.exception(
                    "Unexpected request error: %s",
                    url
                )

                return None

            if attempt < MAX_RETRIES:

                delay = min(
                    2 ** attempt + random.uniform(0, 1),
                    60.0
                )

                await asyncio.sleep(delay)

        logger.error(
            "Maximum retry attempts exceeded: %s",
            url
        )

        return None


# --------------------------------------------------
# TESTING
# --------------------------------------------------

async def main():

    print("=" * 55)
    print("ASYNC HTTP CLIENT TEST")
    print("=" * 55)

    client = HTTPClient()

    try:

        await client.start()

        # Public test endpoint
        result = await client.get(
            "https://httpbin.org/get"
        )

        if result:

            print("\nHTTP request successful!")

            if isinstance(result, dict):
                print("Response type: JSON")
                print(
                    "URL:",
                    result.get("url")
                )

            else:
                print("Response received.")

        else:

            print("\nHTTP request did not return a response.")

    finally:

        await client.close()

    print("\nHTTP client test completed!")


if __name__ == "__main__":

    asyncio.run(main())
