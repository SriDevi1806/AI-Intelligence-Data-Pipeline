
import asyncio
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from http_client import HTTPClient
from logger import logger
from anti_bot import detect_protection, get_fallback_strategy
from browser_renderer import BrowserRenderer


class AsyncCrawler:

    def __init__(self):
        self.client = HTTPClient()

        self.visited_urls = set()
        self.in_progress_urls = set()
        self.visited_lock = asyncio.Lock()

        self.domain_locks = {}
        self.domain_last_request = {}

        self.robots_cache = {}
        self.robots_locks = {}
        self.robots_cache_ttl = 3600

        self.crawl_delay = 1.0
        self.user_agent = "AIIntelligenceDataPipeline/1.0"

        # Browser renderer is initialized only when needed.
        self.browser_renderer = None
        self.browser_lock = asyncio.Lock()

    @staticmethod
    def get_domain(url):
        return urlparse(url).netloc.lower()

    async def is_allowed(self, url):

        parsed = urlparse(url)
        domain = self.get_domain(url)

        robots_url = (
            f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        )

        loop = asyncio.get_running_loop()

        cached = self.robots_cache.get(domain)

        if cached is not None:
            expiry, parser = cached

            if loop.time() < expiry:
                if parser is False:
                    return False

                return parser.can_fetch(self.user_agent, url)

        if domain not in self.robots_locks:
            self.robots_locks[domain] = asyncio.Lock()

        async with self.robots_locks[domain]:

            cached = self.robots_cache.get(domain)

            if cached is not None:
                expiry, parser = cached

                if loop.time() < expiry:
                    if parser is False:
                        return False

                    return parser.can_fetch(self.user_agent, url)

            try:
                response = await self.client.get(
                    robots_url,
                    return_status=True
                )

                if (
                    isinstance(response, dict)
                    and response.get("status") == 404
                ):
                    parser = RobotFileParser()
                    parser.set_url(robots_url)
                    parser.parse([])

                    self.robots_cache[domain] = (
                        loop.time() + self.robots_cache_ttl,
                        parser
                    )

                    return parser.can_fetch(self.user_agent, url)

                if (
                    not isinstance(response, dict)
                    or response.get("status") != 200
                    or not isinstance(response.get("body"), str)
                ):
                    logger.warning(
                        "Cannot verify robots.txt; failing closed: %s",
                        robots_url
                    )

                    self.robots_cache[domain] = (
                        loop.time() + self.robots_cache_ttl,
                        False
                    )

                    return False

                parser = RobotFileParser()
                parser.set_url(robots_url)
                parser.parse(response["body"].splitlines())

                self.robots_cache[domain] = (
                    loop.time() + self.robots_cache_ttl,
                    parser
                )

                return parser.can_fetch(self.user_agent, url)

            except Exception:
                logger.exception(
                    "Robots.txt check failed: %s",
                    robots_url
                )

                self.robots_cache[domain] = (
                    loop.time() + self.robots_cache_ttl,
                    False
                )

                return False

    async def wait_for_domain(self, domain):

        if domain not in self.domain_locks:
            self.domain_locks[domain] = asyncio.Lock()

        async with self.domain_locks[domain]:

            loop = asyncio.get_running_loop()

            previous = self.domain_last_request.get(domain)

            if previous is not None:
                elapsed = loop.time() - previous
                remaining = self.crawl_delay - elapsed

                if remaining > 0:
                    await asyncio.sleep(remaining)

            self.domain_last_request[domain] = loop.time()

    @staticmethod
    def extract_content(html):

        soup = BeautifulSoup(html, "lxml")

        for element in soup([
            "script",
            "style",
            "noscript",
            "svg",
            "iframe"
        ]):
            element.decompose()

        title = (
            soup.title.get_text(strip=True)
            if soup.title else ""
        )

        text = soup.get_text(
            separator=" ",
            strip=True
        )

        return {
            "title": title,
            "text": text
        }

    async def render_with_browser(self, url):

        async with self.browser_lock:

            if self.browser_renderer is None:
                self.browser_renderer = BrowserRenderer()

            try:
                result = await self.browser_renderer.render(url)

                if not isinstance(result, dict):
                    return None

                html = result.get("html", "")
                status = result.get("status")

                if status != 200 or not isinstance(html, str):
                    logger.warning(
                        "Browser rendering unsuccessful: %s",
                        url
                    )
                    return None

                protection = detect_protection(
                    html=html,
                    status_code=status
                )

                if protection:
                    logger.warning(
                        "Protection remains after browser rendering: %s",
                        protection
                    )
                    return None

                return html

            except Exception:
                logger.exception(
                    "Browser rendering failed: %s",
                    url
                )
                return None

    async def fetch_page(self, url):

        response = await self.client.get(
            url,
            return_status=True
        )

        if not isinstance(response, dict):
            logger.warning(
                "HTTP request failed or returned no status: %s",
                url
            )
            return None

        status = response.get("status")
        body = response.get("body")

        if status != 200 or not isinstance(body, str):
            logger.warning(
                "HTTP response status %s for %s",
                status,
                url
            )
            return None

        protection = detect_protection(
            html=body,
            status_code=status
        )

        if protection:

            strategy = get_fallback_strategy(
                protection=protection,
                status_code=status
            )

            action = strategy.get("action")

            logger.warning(
                "Protection detected: %s | Strategy: %s | URL: %s",
                protection,
                action,
                url
            )

            if (
                protection.lower() == "cloudflare"
                and action == "BROWSER_RENDER"
            ):
                logger.info(
                    "Attempting authorized JavaScript rendering: %s",
                    url
                )

                return await self.render_with_browser(url)

            # Do not bypass DataDome or CAPTCHA.
            logger.warning(
                "Manual review or alternative source required: %s",
                url
            )

            return None

        return body

    async def crawl_url(self, url):

        parsed = urlparse(url)

        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
        ):
            logger.warning("Invalid URL rejected: %s", url)
            return None

        async with self.visited_lock:

            if (
                url in self.visited_urls
                or url in self.in_progress_urls
            ):
                logger.info("Skipping duplicate URL: %s", url)
                return None

            self.in_progress_urls.add(url)

        try:

            if not await self.is_allowed(url):
                logger.warning(
                    "URL disallowed or robots.txt unverified: %s",
                    url
                )
                return None

            domain = self.get_domain(url)

            await self.wait_for_domain(domain)

            logger.info("Crawling: %s", url)

            html = await self.fetch_page(url)

            if not isinstance(html, str):
                return None

            content = self.extract_content(html)

            if not content["text"]:
                logger.warning("No extracted text: %s", url)
                return None

            result = {
                "url": url,
                "title": content["title"],
                "text": content["text"],
                "success": True
            }

            async with self.visited_lock:
                self.visited_urls.add(url)

            return result

        except Exception:
            logger.exception("Crawler failed: %s", url)
            return None

        finally:
            async with self.visited_lock:
                self.in_progress_urls.discard(url)

    async def crawl_many(self, urls):

        tasks = [
            self.crawl_url(url)
            for url in urls
        ]

        results = await asyncio.gather(
            *tasks,
            return_exceptions=True
        )

        successful = []
        failed = []

        for url, result in zip(urls, results):

            if isinstance(result, Exception) or result is None:
                failed.append(url)
            else:
                successful.append(result)

        logger.info(
            "Crawl complete | Success: %s | Failed: %s",
            len(successful),
            len(failed)
        )

        return {
            "successful": successful,
            "failed": failed
        }

    async def close(self):

        try:
            if self.browser_renderer is not None:
                await self.browser_renderer.close()
        finally:
            await self.client.close()


async def main():

    print("=" * 55)
    print("ASYNC CRAWLER INTEGRATION TEST")
    print("=" * 55)

    crawler = AsyncCrawler()

    try:
        await crawler.client.start()

        results = await crawler.crawl_many([
            "https://example.com",
            "https://www.iana.org"
        ])

        for page in results["successful"]:
            print("\nURL:", page["url"])
            print("Title:", page["title"])
            print("Text:", page["text"][:200])

        print("\nSuccessful:", len(results["successful"]))
        print("Failed:", len(results["failed"]))

    finally:
        await crawler.close()


if __name__ == "__main__":
    asyncio.run(main())
