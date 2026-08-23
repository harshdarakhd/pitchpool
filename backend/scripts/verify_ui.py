"""Local responsive acceptance check for the admin and match flows."""

import asyncio

from playwright.async_api import async_playwright


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 390, "height": 844})
        navigations: list[str] = []
        sockets: list[str] = []
        page.on("framenavigated", lambda frame: navigations.append(frame.url))
        page.on("websocket", lambda ws: sockets.append(ws.url))

        await page.goto("http://localhost:5173", wait_until="networkidle")
        await page.locator('input[type="email"]').fill("admin@pitchpool.local")
        await page.locator('input[type="password"]').fill("admin12345")
        await page.locator('button[type="submit"]').click()
        await page.wait_for_url("http://localhost:5173/")
        await page.wait_for_timeout(2000)

        assert await page.get_by_text("5,000 pts", exact=False).count()
        assert await page.locator("aside button.w-full").count() == 40

        await page.locator("aside button.w-full").first.click()
        await page.get_by_text("Back to matches", exact=False).wait_for()
        before = page.url
        nav_count = len(navigations)
        await page.wait_for_timeout(7000)
        assert page.url == before
        assert len(navigations) == nav_count

        await page.get_by_text("Back to matches", exact=False).click()
        await page.get_by_role("button", name="Open menu").click()
        await page.get_by_role("link", name="Admin").click()
        await page.wait_for_url("**/admin")
        await page.get_by_text("Big Bash League Season 5", exact=False).first.wait_for()
        assert await page.get_by_text("CricHeroes ID 2078243", exact=False).count()
        assert any("/ws" in url for url in sockets)

        print("mobile_match_count=40")
        print("selection_retained=true")
        print("admin_current_tournament=2078243")
        print("cookie_websocket_connected=true")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
