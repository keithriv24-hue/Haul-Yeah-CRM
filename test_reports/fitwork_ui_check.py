import asyncio
from playwright.async_api import async_playwright

URL = "https://haul-yeah-staging.preview.emergentagent.com"

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await b.new_page(viewport={"width": 1920, "height": 900})
        await page.goto(URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)
        if await page.locator('input[type="password"]').count():
            await page.locator("form input").first.fill("HaulYeahAdmin")
            await page.fill('input[type="password"]', "HaulYeah2026!")
            await page.locator('[data-testid="login-submit-button"]').click()
            await page.wait_for_timeout(3500)
        await page.goto(URL + "/scope-calculator", wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)
        await page.locator('[data-testid="scope-custom-add-btn"]').click()
        await page.wait_for_timeout(400)
        await page.select_option('[data-testid="scope-custom-band-select"]', "w500_799")
        await page.select_option('[data-testid="scope-custom-fitwork-select"]', "both")
        await page.wait_for_timeout(600)
        print("fitwork hours note:", await page.locator('[data-testid="scope-custom-fitwork-hours"]').inner_text())
        print("mode indicator:", await page.locator('[data-testid="scope-mode-indicator"]').inner_text())
        print("cap note present:", await page.locator('[data-testid="scope-handling-cap-note"]').count())
        opts = await page.locator('[data-testid="scope-custom-fitwork-select"] option').all_inner_texts()
        print("fitwork options:", opts)
        await page.locator('[data-testid="scope-custom-items-card"]').scroll_into_view_if_needed()
        await page.screenshot(path="/app/test_reports/fitwork_ui.png")
        await b.close()

asyncio.run(main())
