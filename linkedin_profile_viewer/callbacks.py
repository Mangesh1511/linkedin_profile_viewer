"""
Callback mechanisms for real-time progress logging and status reporting.
"""

import sys
import logging
from typing import Any, Optional, Dict

logger = logging.getLogger(__name__)


class ProgressCallback:
    """Base callback interface."""

    async def on_start(self, scraper_name: str, target: str) -> None:
        pass

    async def on_progress(self, message: str, percentage: int = 0, details: Optional[Dict[str, Any]] = None) -> None:
        pass

    async def on_complete(self, scraper_name: str, result: Any) -> None:
        pass

    async def on_error(self, error: Exception) -> None:
        pass


class ConsoleCallback(ProgressCallback):
    """Console progress callback logging to stdout."""

    async def on_start(self, scraper_name: str, target: str) -> None:
        logger.info(f"🚀 Starting {scraper_name} scraping: {target}")

    async def on_progress(self, message: str, percentage: int = 0, details: Optional[Dict[str, Any]] = None) -> None:
        bar = "█" * (percentage // 5) + "░" * (20 - percentage // 5)
        logger.info(f"[{bar}] {percentage}% - {message}")

    async def on_complete(self, scraper_name: str, result: Any) -> None:
        logger.info(f"✅ {scraper_name} completed successfully.")

    async def on_error(self, error: Exception) -> None:
        logger.error(f"❌ Error: {error}")


class SilentCallback(ProgressCallback):
    """Silent callback suppressing output."""
    pass
