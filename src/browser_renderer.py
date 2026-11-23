
import asyncio

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError
)

from logger import logger


class BrowserRenderer:

    def __init__(
        self,
        timeout=30000,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    ):

        self.timeout = timeout
        self.user_agent = user_agent

        self.playwright = None
        self.browser = None

        self.lock = asyncio.Lock()

    # --------------------------------------------------
    # START BROWSER
    # --------------------------------------------------

    async def start(self):

        async with self.lock:

            if self.browser is not None:
                return

            try:

                self.playwright = await async_playwright().start()

                self.browser = await self.playwright.chromium.launch(
                    headless=True
                )

                logger.info(
                    "Browser renderer started successfully"
                )

            except Exception:

                logger.exception(
                    "Unable to start browser renderer"
                )

                if self.playwright:

                    await self.playwright.stop()

                self.playwright = None
                self.browser = None

                raise

    # --------------------------------------------------
    # RENDER PAGE
    # --------------------------------------------------

    async def render(self, url):

        if self.browser is None:

            await self.start()

        page = None

        try:

            page = await self.browser.new_page(
                user_agent=self.user_agent
            )

            page.set_default_timeout(
                self.timeout
            )

            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.timeout
            )

            status = (
                response.status
                if response is not None
                else None
            )

            # Wait for JavaScript-generated content.
            # Do not use networkidle because many sites
            # maintain persistent network connections.

            await page.wait_for_timeout(2000)

            title = await page.title()

            html = await page.content()

            result = {
                "url": url,
                "title": title,
                "html": html,
                "status": status,
                "success": True
            }

            logger.info(
                "Browser rendering successful: %s",
                url
            )

            return result

        except PlaywrightTimeoutError:

            logger.warning(
                "Browser rendering timed out: %s",
                url
            )

        except Exception:

            logger.exception(
                "Browser rendering failed: %s",
                url
            )

        finally:

            if page:

                await page.close()

        return {
            "url": url,
            "title": "",
            "html": "",
            "status": None,
            "success": False
        }

    # --------------------------------------------------
    # CLOSE BROWSER
    # --------------------------------------------------

    async def close(self):

        async with self.lock:

            if self.browser:

                await self.browser.close()

                self.browser = None

            if self.playwright:

                await self.playwright.stop()

                self.playwright = None

            logger.info(
                "Browser renderer closed"
            )


# --------------------------------------------------
# TESTING
# --------------------------------------------------

async def main():

    print("=" * 55)
    print("BROWSER RENDERER TEST")
    print("=" * 55)

    renderer = BrowserRenderer()

    try:

        await renderer.start()

        result = await renderer.render(
            "https://example.com"
        )

        print(
            "\nRendering successful:",
            result["success"]
        )

        print(
            "HTTP status:",
            result["status"]
        )

        if result["success"]:

            print(
                "Page title:",
                result["title"]
            )

            print(
                "HTML length:",
                len(result["html"])
            )

    finally:

        await renderer.close()

    print("\nBrowser renderer test completed!")


if __name__ == "__main__":

    asyncio.run(main())
