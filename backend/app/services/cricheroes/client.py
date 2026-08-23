"""CricHeroes page fetch via Playwright.

cricheroes.com sits behind Cloudflare bot protection: a default Playwright
launch is served an "you have been blocked" interstitial. The launch flags,
realistic UA/viewport and the ``_STEALTH_JS`` init script below are what get a
normal page render, so change them only alongside a re-test.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

MATCH_TABS = ("/matches/past-matches", "/matches/upcoming-matches", "/matches/live-matches")

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
window.chrome = {runtime: {}};
"""

_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]

_BLOCKED_MARKERS = ("you have been blocked", "attention required", "cf-error-details")


def _looks_blocked(html: str) -> bool:
    lowered = html[:20000].lower()
    return any(marker in lowered for marker in _BLOCKED_MARKERS)


async def _click_load_more(page, max_clicks: int = 20) -> None:
    """Exhaust the 'Load more' pagination so every match card is in the DOM."""
    for _ in range(max_clicks):
        try:
            button = page.get_by_text("Load more", exact=False)
            if await button.count() == 0:
                return
            target = button.first
            if not await target.is_visible():
                return
            await target.scroll_into_view_if_needed(timeout=5000)
            await target.click(timeout=5000)
            await page.wait_for_timeout(1500)
        except Exception:
            return


async def fetch_tournament_html(
    base_url: str,
    path: str = "/matches/past-matches",
    *,
    headless: bool = True,
    load_all: bool = True,
) -> str:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not installed; returning empty HTML")
        return ""

    url = f"{base_url.rstrip('/')}{path}"
    html = ""

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=_LAUNCH_ARGS)
        context = await browser.new_context(
            user_agent=_UA,
            viewport={"width": 1440, "height": 900},
            locale="en-US",
            timezone_id="Asia/Kolkata",
        )
        await context.add_init_script(_STEALTH_JS)
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=90000)
            try:
                await page.wait_for_selector(
                    "[class*='matchContainer'], [class*='matchCard']", timeout=30000
                )
            except Exception:
                logger.warning("No match cards appeared for %s", url)
            if load_all:
                await _click_load_more(page)
            html = await page.content()
            if _looks_blocked(html):
                logger.error("CricHeroes returned a bot-protection page for %s", url)
                html = ""
        except Exception:
            logger.exception("Failed to fetch CricHeroes page %s", url)
            html = ""
        finally:
            await context.close()
            await browser.close()

    return html


async def fetch_all_match_tabs(base_url: str, *, headless: bool = True) -> list[str]:
    """Fetch every match tab. Returns one HTML document per tab.

    Kept as separate documents because an HTML parser would discard everything
    after the first ``</html>`` if these were concatenated.
    """
    pages: list[str] = []
    for path in MATCH_TABS:
        chunk = await fetch_tournament_html(base_url, path, headless=headless)
        if chunk:
            pages.append(chunk)
        await asyncio.sleep(1)
    return pages


def fetch_tournament_html_sync(base_url: str, path: str = "/matches/past-matches") -> str:
    return asyncio.run(fetch_tournament_html(base_url, path))
