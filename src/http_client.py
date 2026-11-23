
import asyncio
import random
import json

import aiohttp

from config import (
    MAX_CONCURRENT_REQUESTS,
    REQUEST_TIMEOUT,
    MAX_RETRIES
)

from logger import logger

from anti_bot import (
    detect_protection,
    get_fallback_strategy
)


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
    # RESPONSE FALLBACK HANDLER
    # --------------------------------------------------

    def handle_fallback(
        self,
        url,
        protection,
        status
    ):

        strategy = get_fallback_strategy(
            protection,
            status
        )

        logger.warning(
            "Fallback decision | URL=%s | Action=%s | Strategy=%s",
            url,
            strategy["action"],
            strategy["strategy"]
        )

        if strategy["action"] == "BROWSER_RENDER":

            logger.info(
                "Authorized JavaScript rendering may be considered: %s",
                url
            )

        elif strategy["action"] == "ALTERNATIVE_SOURCE":

            logger.warning(
                "Use an alternative authorized public source: %s",
                url
            )

        elif strategy["action"] == "MANUAL_REVIEW":

            logger.warning(
                "Manual review required. Do not bypass CAPTCHA: %s",
                url
            )

        return strategy

    # --------------------------------------------------
    # RESPONSE FORMATTER
    # --------------------------------------------------

    @staticmethod
    def format_response(status, body, return_status):

        if return_status:

            return {
                "status": status,
                "body": body
            }

        return None

    # --------------------------------------------------
    # ASYNC GET REQUEST
    # --------------------------------------------------

    async def get(
        self,
        url: str,
        params=None,
        headers=None,
        return_status=False
    ):

        if self.session is None or self.session.closed:
            await self.start()

        request_headers = {
            **self.headers,
            **(headers or {})
        }

        for attempt in range(MAX_RETRIES + 1):

            delay = None

            try:

                async with self.semaphore:

                    async with self.session.get(
                        url,
                        params=params,
                        headers=request_headers
                    ) as response:

                        status = response.status

                        response_headers = dict(
                            response.headers
                        )

                        # ----------------------------------
                        # SUCCESS RESPONSE
                        # ----------------------------------

                        if status == 200:

                            body = await response.text()

                            protection = detect_protection(
                                body,
                                status,
                                response_headers
                            )

                            if protection:

                                self.handle_fallback(
                                    url,
                                    protection,
                                    status
                                )

                                return self.format_response(
                                    status,
                                    body,
                                    return_status
                                )

                            content_type = response.headers.get(
                                "Content-Type",
                                ""
                            ).lower()

                            if "application/json" in content_type:

                                try:

                                    data = json.loads(body)

                                    if return_status:

                                        return {
                                            "status": status,
                                            "body": data
                                        }

                                    return data

                                except ValueError:

                                    logger.warning(
                                        "Invalid JSON response: %s",
                                        url
                                    )

                                    return None

                            if return_status:

                                return {
                                    "status": status,
                                    "body": body
                                }

                            return body

                        # ----------------------------------
                        # ACCESS DENIED
                        # ----------------------------------

                        if status in {401, 403}:

                            body = await response.text()

                            protection = detect_protection(
                                body,
                                status,
                                response_headers
                            )

                            self.handle_fallback(
                                url,
                                protection,
                                status
                            )

                            logger.error(
                                "Access denied: %s | HTTP %s",
                                url,
                                status
                            )

                            return self.format_response(
                                status,
                                body,
                                return_status
                            )

                        # ----------------------------------
                        # NOT FOUND
                        # ----------------------------------

                        elif status == 404:

                            logger.info(
                                "HTTP 404 returned: %s",
                                url
                            )

                            return self.format_response(
                                status,
                                None,
                                return_status
                            )

                        # ----------------------------------
                        # RETRYABLE RESPONSES
                        # ----------------------------------

                        elif status in {
                            408, 429, 500, 502, 503, 504
                        }:

                            strategy = self.handle_fallback(
                                url,
                                None,
                                status
                            )

                            if attempt == MAX_RETRIES:

                                logger.error(
                                    "Request failed after retries: %s (%s)",
                                    url,
                                    status
                                )

                                return self.format_response(
                                    status,
                                    None,
                                    return_status
                                )

                            retry_after = response.headers.get(
                                "Retry-After"
                            )

                            if (
                                retry_after
                                and retry_after.isdigit()
                            ):

                                delay = min(
                                    float(retry_after),
                                    60.0
                                )

                            else:

                                delay = min(
                                    strategy.get("delay")
                                    or (
                                        2 ** attempt
                                        + random.uniform(0, 1)
                                    ),
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

                            return self.format_response(
                                status,
                                None,
                                return_status
                            )

                # Sleep outside semaphore
                if delay is not None:

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

            # ----------------------------------
            # RETRY AFTER NETWORK ERRORS
            # ----------------------------------

            if attempt < MAX_RETRIES:

                if delay is None:

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
# LOCAL TEST ENTRY POINT
# --------------------------------------------------

async def main():

    print("=" * 55)
    print("ASYNC HTTP CLIENT TEST")
    print("=" * 55)

    client = HTTPClient()

    try:

        await client.start()

        result = await client.get(
            "https://httpbin.org/get"
        )

        if result:

            print("\nHTTP request successful!")

            if isinstance(result, dict):

                print("Response type: JSON")
                print("URL:", result.get("url"))

            else:

                print("Response received.")

        else:

            print("\nHTTP request did not return a response.")

    finally:

        await client.close()

    print("\nHTTP client test completed!")


if __name__ == "__main__":

    asyncio.run(main())
