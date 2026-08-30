"""
Browser lifecycle and session manager for Playwright Chromium.
"""

import os
import json
import logging
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)


class BrowserManager:
    """
    Manages Playwright browser instance, authenticated contexts, and session cookies.
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None

    async def start(self) -> None:
        """Start Playwright and launch Chromium browser."""
        if not self._browser:
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                ]
            )
            # Create default context with custom User-Agent
            self.context = await self._browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York'
            )
            logger.info("Playwright browser instance started successfully.")

    async def load_session(self, session_path: str) -> bool:
        """Load storage state / cookies from session file into context."""
        if not os.path.exists(session_path):
            logger.warning(f"Session file not found: {session_path}")
            return False

        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                storage_state = json.load(f)

            if self._browser:
                # Re-create context with loaded storage state
                await self.context.close()
                self.context = await self._browser.new_context(
                    storage_state=storage_state,
                    viewport={'width': 1280, 'height': 800},
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    locale='en-US',
                    timezone_id='America/New_York'
                )
                logger.info(f"Loaded browser session from: {session_path}")
                return True
        except Exception as e:
            logger.error(f"Failed to load browser session: {e}")
        return False

    async def save_session(self, session_path: str) -> None:
        """Save current context cookies & storage state to file."""
        if self.context:
            try:
                state = await self.context.storage_state()
                with open(session_path, 'w', encoding='utf-8') as f:
                    json.dump(state, f, indent=2)
                logger.info(f"Saved browser session state to: {session_path}")
            except Exception as e:
                logger.error(f"Failed to save browser session state: {e}")

    async def close(self) -> None:
        """Close context, browser, and playwright instance."""
        if self.context:
            await self.context.close()
            self.context = None
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        logger.info("Browser instance closed.")
