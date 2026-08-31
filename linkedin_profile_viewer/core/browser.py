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
        logger.info("Starting Playwright browser (headless=%s)", self.headless)
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
        else:
            logger.info("Playwright browser was already running; reusing existing instance")

    async def load_session(self, session_path: str) -> bool:
        """Load storage state / cookies from session file into context."""
        if not os.path.exists(session_path):
            logger.warning("Session file not found: %s", os.path.abspath(session_path))
            return False

        try:
            logger.info("Reading browser session state from: %s", os.path.abspath(session_path))
            with open(session_path, 'r', encoding='utf-8') as f:
                storage_state = json.load(f)

            logger.info(
                "Session JSON parsed successfully (cookies=%d, origins=%d)",
                len(storage_state.get('cookies', [])),
                len(storage_state.get('origins', [])),
            )

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
            logger.error("Cannot load session because the browser is not running")
        except Exception as e:
            logger.error("Failed to load browser session: %s", e, exc_info=True)
        return False

    async def save_session(self, session_path: str) -> None:
        """Save current context cookies & storage state to file."""
        if self.context:
            try:
                state = await self.context.storage_state()
                logger.info(
                    "Collected browser session state (cookies=%d, origins=%d); writing to %s",
                    len(state.get('cookies', [])),
                    len(state.get('origins', [])),
                    os.path.abspath(session_path),
                )
                with open(session_path, 'w', encoding='utf-8') as f:
                    json.dump(state, f, indent=2)
                logger.info(
                    "Saved browser session state to: %s (size_bytes=%d)",
                    os.path.abspath(session_path),
                    os.path.getsize(session_path),
                )
            except Exception as e:
                logger.error("Failed to save browser session state: %s", e, exc_info=True)
        else:
            logger.error("Cannot save browser session because browser context is not available")

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
