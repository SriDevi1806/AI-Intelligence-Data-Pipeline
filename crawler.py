
import asyncio
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from http_client import HTTPClient
from logger import logger


class AsyncCrawler:

    def __init__(self):

        self.client = HTTPClient()

        self.visited_urls = set()
        self.domain_locks = {}
        self.domain_last_request = {}

        self.crawl_delay = 1.0

        self.user_agent = (
            "AIIntelligenceDataPipeline/1.0"
        )

    # --------------------------------------------------
    # DOMAIN EXTRACTION
    # --------------------------------------------------

    @staticmethod
    def get_domain(url):

        return urlparse(url).netloc.lower()

    # --------------------------------------------------
    # ROBOTS.TXT CHECK
    # --------------------------------------------------

    async def is_allowed(self, url):

        parsed = urlparse(url)

        robots_url = (
            f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        )

        try:

            response = await self.client.get(robots_url)

            if response is None:

                logger.warning(
                    "Unable to verify robots.txt: %s",
                    robots_url
                )

                # Fail closed when robots.txt cannot be checked.
                return False

            if not isinstance(response, str):

                logger.warning(
                    "Unexpected robots.txt response: %s",
                    robots_url
                )

                return False

            parser = RobotFileParser()

            parser.set_url(robots_url)
            parser.parse(response.splitlines())

            return parser.can_fetch(
                self.user_agent,
                url
            )

        except Exception:

            logger.exception(
                "Robots.txt check failed: %s",
                robots_url
            )

            return False

    # --------------------------------------------------
    # DOMAIN RATE LIMITING
    # --------------------------------------------------

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

    # --------------------------------------------------
    # HTML EXTRACTION
    # --------------------------------------------------

    @staticmethod
    def extract_content(html):

        soup = BeautifulSoup(
            html,
            "lxml"
        )

        # Remove non-content elements
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
            if soup.title
            else ""
        )

        text = soup.get_text(
            separator=" ",
            strip=True
        )

        return {
            "title": title,
            "text": text
        }

    # --------------------------------------------------
    # SINGLE URL CRAWLER
    # --------------------------------------------------

    async def crawl_url(self, url):

        if url in self.visited_urls:

            logger.info(
                "Skipping duplicate URL: %s",
                url
            )

            return None

        parsed = urlparse(url)

        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
        ):

            logger.warning(
                "Invalid URL rejected: %s",
                url
            )

            return None

        self.visited_urls.add(url)

        allowed = await self.is_allowed(url)

        if not allowed:

            logger.warning(
                "Crawling disallowed or unverified by robots.txt: %s",
                url
            )

            return None

        domain = self.get_domain(url)

        await self.wait_for_domain(domain)

        logger.info(
            "Crawling: %s",
            url
        )

        html = await self.client.get(url)

        if not isinstance(html, str):

            logger.warning(
                "No HTML content received: %s",
                url
            )

            return None

        content = self.extract_content(html)

        return {
            "url": url,
            "title": content["title"],
            "text": content["text"],
            "success": True
        }

    # --------------------------------------------------
    # MULTIPLE URL CRAWLER
    # --------------------------------------------------

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

            if isinstance(result, Exception):

                logger.error(
                    "Crawl exception for %s: %s",
                    url,
                    result
                )

                failed.append(url)

            elif result is None:

                failed.append(url)

            else:

                successful.append(result)

        logger.info(
            "Crawl completed. Success: %s | Failed: %s",
            len(successful),
            len(failed)
        )

        return {
            "successful": successful,
            "failed": failed
        }

    # --------------------------------------------------
    # CLOSE CRAWLER
    # --------------------------------------------------

    async def close(self):

        await self.client.close()


# --------------------------------------------------
# TESTING
# --------------------------------------------------

async def main():

    print("=" * 55)
    print("ASYNC WEB CRAWLER TEST")
    print("=" * 55)

    crawler = AsyncCrawler()

    test_urls = [
        "https://example.com",
        "https://www.iana.org"
    ]

    try:

        await crawler.client.start()

        results = await crawler.crawl_many(
            test_urls
        )

        print("\nSuccessful pages:")

        for page in results["successful"]:

            print("\nURL:", page["url"])
            print("Title:", page["title"])
            print("Text preview:", page["text"][:200])

        print(
            "\nSuccessful:",
            len(results["successful"])
        )

        print(
            "Failed:",
            len(results["failed"])
        )

    finally:

        await crawler.close()

    print("\nCrawler test completed!")


if __name__ == "__main__":

    asyncio.run(main())
