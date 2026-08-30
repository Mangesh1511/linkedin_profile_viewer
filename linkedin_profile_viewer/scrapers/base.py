"""
Base scraper class for Playwright-based LinkedIn scraping.
"""

import asyncio
import logging
from typing import Optional
from playwright.async_api import Page

from ..callbacks import ProgressCallback, SilentCallback
from ..core.auth import load_credentials_from_env
from ..core.utils import detect_rate_limit, scroll_page, click_see_more_buttons
from ..core.exceptions import ScrapingError, AuthenticationError

logger = logging.getLogger(__name__)


class BaseScraper:
    """Base scraper providing navigation, authentication, and page interaction helpers."""

    def __init__(self, page: Page, callback: Optional[ProgressCallback] = None):
        self.page = page
        self.callback = callback or SilentCallback()

    async def ensure_logged_in(self, return_url: Optional[str] = None) -> None:
        """Verify if current page is logged into LinkedIn; attempt automated login if not."""
        from ..core.auth import is_logged_in, login_with_credentials
        
        if await is_logged_in(self.page):
            return

        target_url = return_url or self.page.url
        logger.info("🔐 Not logged into LinkedIn. Performing automated login using credentials from .env...")
        try:
            await login_with_credentials(self.page)
            # Save valid session cookies for future requests
            if self.page.context:
                import json
                state = await self.page.context.storage_state()
                with open("linkedin_session.json", "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2)
                logger.info("💾 Saved authenticated session cookies to linkedin_session.json")

            if target_url and "login" not in target_url:
                logger.info(f"Navigating back to target URL after login: {target_url}")
                await self.page.goto(target_url, wait_until="domcontentloaded")
        except Exception as e:
            logger.warning(f"Automated login attempt notice: {e}")

    async def navigate_and_wait(self, url: str, timeout: int = 15000) -> None:
        """Navigate to URL, detect rate limits, and wait for DOM load."""
        logger.info(f"Navigating to: {url}")
        await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        await detect_rate_limit(self.page)

    async def scroll_page_to_bottom(self, pause_time: float = 0.5, max_scrolls: int = 5) -> None:
        """Scroll page to bottom to load all dynamic content."""
        await scroll_page(self.page, pause_time=pause_time, max_scrolls=max_scrolls, half_scroll=False)

    async def scroll_page_to_half(self, pause_time: float = 0.5) -> None:
        """Scroll halfway down the page."""
        await scroll_page(self.page, pause_time=pause_time, half_scroll=True)

    async def click_all_see_more_buttons(self, max_attempts: int = 5) -> None:
        """Expand all see more text buttons."""
        await click_see_more_buttons(self.page, max_attempts)

    async def wait_and_focus(self, seconds: float = 1.0) -> None:
        """Pause execution for specified duration."""
        await asyncio.sleep(seconds)
