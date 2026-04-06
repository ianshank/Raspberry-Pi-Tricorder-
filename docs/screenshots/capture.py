"""Capture UI screenshots for README using Playwright (headless Chromium)."""
import asyncio
import time
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).parent
VIEWPORT = {"width": 1280, "height": 800}
WAIT_LIVE = 3000   # ms — time to let WS connect and first sensor data arrive
WAIT_NAV  = 1500   # ms — time after clicking a nav tile


async def _wait_for_status(page, text: str, timeout: int = 10_000) -> None:
    """Wait until the footer status indicator shows `text`."""
    await page.wait_for_function(
        f"document.getElementById('status-indicator')?.textContent?.includes('{text}')",
        timeout=timeout,
    )


async def _nav_to_panel(page, panel_id: str) -> None:
    """Click a nav tile by its data-panel-id attribute (camelCase dataset)."""
    tile = page.locator(f"[data-panel-id='{panel_id}']")
    await tile.wait_for(state="visible", timeout=5_000)
    await tile.click()
    await page.wait_for_timeout(WAIT_NAV)


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport=VIEWPORT)
        page = await ctx.new_page()

        print("Opening Tricorder UI…")
        await page.goto(f"{BASE}/ui/index.html", wait_until="domcontentloaded")

        # Wait for WebSocket to connect and show LIVE status
        try:
            await _wait_for_status(page, "LIVE", timeout=12_000)
            print("  ✓ Status: LIVE")
        except Exception:
            print("  ! Could not confirm LIVE status — continuing anyway")
        await page.wait_for_timeout(WAIT_LIVE)

        # 1. Full dashboard
        await page.screenshot(path=str(OUT / "dashboard-live.png"), full_page=False)
        print("  ✓ dashboard-live.png")

        # 2. Environmental panel
        try:
            await _nav_to_panel(page, "env")
            await page.screenshot(path=str(OUT / "env-panel.png"), full_page=False)
            print("  ✓ env-panel.png")
        except Exception as exc:
            print(f"  ! env panel: {exc}")

        # 3. Biosigns panel
        try:
            await _nav_to_panel(page, "bio")
            await page.screenshot(path=str(OUT / "bio-panel.png"), full_page=False)
            print("  ✓ bio-panel.png")
        except Exception as exc:
            print(f"  ! bio panel: {exc}")

        # 4. Engineering panel
        try:
            await _nav_to_panel(page, "eng")
            await page.screenshot(path=str(OUT / "eng-panel.png"), full_page=False)
            print("  ✓ eng-panel.png")
        except Exception as exc:
            print(f"  ! eng panel: {exc}")

        # 5. Agent chat panel
        try:
            await _nav_to_panel(page, "agent")
            await page.screenshot(path=str(OUT / "agent-chat.png"), full_page=False)
            print("  ✓ agent-chat.png")
        except Exception as exc:
            print(f"  ! agent panel: {exc}")

        # 6. Inject a fake anomaly alert card directly into the DOM, then screenshot.
        try:
            # Navigate back to bio so the sensor panel is visible behind the float
            await _nav_to_panel(page, "bio")
            await page.evaluate("""() => {
                const stack = document.querySelector('#alert-stack');
                if (!stack) return;
                const card = document.createElement('article');
                card.className = 'anomaly-alert-card severity-high';
                card.dataset.anomalyId = 'screenshot-demo-01';
                card.innerHTML = `
                  <h3 class="anomaly-alert-title">HIGH ALERT &nbsp; SCORE 0.987</h3>
                  <p class="anomaly-alert-time">UTC 2026-04-06 23:05:23</p>
                  <p class="anomaly-alert-sensors">MAX 30102 &nbsp;|&nbsp; MLX 90640</p>
                  <div class="anomaly-alert-controls">
                    <button type="button" class="anomaly-alert-ack">ACK</button>
                  </div>`;
                stack.prepend(card);
            }""")
            await page.wait_for_timeout(800)
        except Exception as exc:
            print(f"  ! anomaly inject: {exc}")
        await page.screenshot(path=str(OUT / "anomaly-alert.png"), full_page=False)
        print("  ✓ anomaly-alert.png")

        await browser.close()
        print("\nAll screenshots saved to", OUT)


asyncio.run(main())
