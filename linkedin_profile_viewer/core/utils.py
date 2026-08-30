"""
Utility functions for Playwright page interaction, rate limit detection, and scrolling.
"""

import asyncio
import logging
from typing import Optional
from playwright.async_api import Page
from .exceptions import RateLimitError, AuthenticationError

logger = logging.getLogger(__name__)


async def detect_rate_limit(page: Page) -> None:
    """Check if current page displays a LinkedIn rate limit or security checkpoint message."""
    try:
        url = page.url
        if "checkpoint" in url or "challenge" in url or "captcha" in url:
            raise RateLimitError("LinkedIn security challenge/CAPTCHA detected.")

        visible_text = await page.locator('body').inner_text(timeout=1000)
        low_text = visible_text.lower()
        if "you’ve reached the monthly limit" in low_text or "commercial use limit" in low_text:
            raise RateLimitError("LinkedIn commercial search rate limit reached.")
        if "please try again later" in low_text and "sign in" in low_text:
            raise AuthenticationError("Session expired or authentication challenge triggered.")
    except (RateLimitError, AuthenticationError):
        raise
    except Exception:
        pass


async def scroll_page(
    page: Page,
    pause_time: float = 0.5,
    max_scrolls: int = 5,
    half_scroll: bool = False
) -> None:
    """Smooth scroll page to trigger dynamic content loading."""
    try:
        if half_scroll:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            await asyncio.sleep(pause_time)
            return

        last_height = await page.evaluate("document.body.scrollHeight")
        for _ in range(max_scrolls):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(pause_time)
            new_height = await page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height
    except Exception as e:
        logger.debug(f"Scroll page helper notice: {e}")


async def click_see_more_buttons(page: Page, max_attempts: int = 5) -> None:
    """Click all visible 'See more' or 'Show more' expander buttons on the page."""
    for _ in range(max_attempts):
        try:
            see_more = page.locator('button:has-text("See more"), button:has-text("Show more"), button:has-text("show all")').first
            if await see_more.count() > 0 and await see_more.is_visible():
                await see_more.click(timeout=1500)
                await asyncio.sleep(0.3)
            else:
                break
        except Exception:
            break
