"""
Standard DOM-based Person profile scraper (v1).
"""

import logging
from typing import Optional, List
from playwright.async_api import Page

from .base import BaseScraper
from ..models import Person, Experience, Education, Accomplishment, Interest, Contact
from ..callbacks import ProgressCallback
from ..core.exceptions import ScrapingError

logger = logging.getLogger(__name__)


class PersonScraper(BaseScraper):
    """v1 DOM-based scraper for LinkedIn person profiles."""

    def __init__(self, page: Page, callback: Optional[ProgressCallback] = None):
        super().__init__(page, callback)

    async def scrape(self, linkedin_url: str) -> Person:
        """Scrape LinkedIn profile using standard DOM elements."""
        await self.callback.on_start("person", linkedin_url)

        try:
            await self.navigate_and_wait(linkedin_url)
            await self.callback.on_progress("Navigated to profile", 20)
            await self.ensure_logged_in()

            await self.scroll_page_to_half()
            await self.scroll_page_to_bottom()
            await self.click_all_see_more_buttons()

            # Extract basic info
            name = await self._get_text("h1") or "Unknown"
            headline = await self._get_text(".text-body-medium")
            location = await self._get_text(".text-body-small.inline")
            about = await self._get_text("section.summary .inline-show-more-text, #about ~ .display-flex .inline-show-more-text")
            
            # Profile picture
            img_el = self.page.locator("img.pv-top-card-profile-picture__image, .pv-top-card__photo img").first
            profile_pic = await img_el.get_attribute("src") if await img_el.count() > 0 else None

            # Open to work
            open_to_work = await self.page.locator("text=#OPEN_TO_WORK").count() > 0

            # Connections
            connections = await self._get_text(".pv-top-card--list-bullet li, span:has-text('connections')")

            # Experiences
            experiences = await self._scrape_experiences()
            
            # Educations
            educations = await self._scrape_educations()

            person = Person(
                linkedin_url=linkedin_url,
                name=name,
                headline=headline,
                location=location,
                profile_picture_url=profile_pic,
                connections=connections,
                about=about,
                open_to_work=open_to_work,
                experiences=experiences,
                educations=educations,
                interests=[],
                accomplishments=[],
                contacts=[],
            )

            await self.callback.on_progress("DOM Parsing complete", 100)
            await self.callback.on_complete("person", person)

            return person

        except Exception as e:
            await self.callback.on_error(e)
            raise ScrapingError(f"DOM Person scraping failed: {e}")

    async def _get_text(self, selector: str) -> Optional[str]:
        try:
            el = self.page.locator(selector).first
            if await el.count() > 0:
                txt = await el.inner_text()
                return txt.strip() if txt else None
        except Exception:
            pass
        return None

    async def _scrape_experiences(self) -> List[Experience]:
        experiences = []
        try:
            items = self.page.locator("#experience ~ .pvs-list__outer-container > ul > li, section:has(#experience) ul > li")
            count = await items.count()
            for i in range(min(count, 10)):
                item = items.nth(i)
                txt = await item.inner_text()
                lines = [l.strip() for l in txt.split("\n") if l.strip()]
                if len(lines) >= 2:
                    experiences.append(
                        Experience(
                            position_title=lines[0],
                            institution_name=lines[1],
                            description="\n".join(lines[2:]) if len(lines) > 2 else None
                        )
                    )
        except Exception as e:
            logger.debug(f"DOM Experience scrape notice: {e}")
        return experiences

    async def _scrape_educations(self) -> List[Education]:
        educations = []
        try:
            items = self.page.locator("#education ~ .pvs-list__outer-container > ul > li, section:has(#education) ul > li")
            count = await items.count()
            for i in range(min(count, 10)):
                item = items.nth(i)
                txt = await item.inner_text()
                lines = [l.strip() for l in txt.split("\n") if l.strip()]
                if len(lines) >= 1:
                    educations.append(
                        Education(
                            institution_name=lines[0],
                            degree=lines[1] if len(lines) > 1 else None,
                            description="\n".join(lines[2:]) if len(lines) > 2 else None
                        )
                    )
        except Exception as e:
            logger.debug(f"DOM Education scrape notice: {e}")
        return educations
