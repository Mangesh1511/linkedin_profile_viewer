"""
Vision-based Person profile scraper (v2) using Gemini API & in-memory browser screenshots.
"""

import os
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin
from playwright.async_api import Page

from .base import BaseScraper
from ..models import Person, Experience, Education, Accomplishment, Interest, Contact
from ..callbacks import ProgressCallback, SilentCallback
from ..core.exceptions import ScrapingError
from ..core.gemini import GeminiClient, GeminiError

logger = logging.getLogger(__name__)


VISION_EXTRACTION_PROMPT = """
You are an expert data extraction AI. You are provided with one or more screenshots of a LinkedIn profile (including the main profile page and optional subpages like experience details, education details, and contact info overlay).

Combine and analyze all provided screenshots to extract the person's profile details into a single strict structured JSON object matching this schema:

{
  "name": "Full name of the person (or null if not visible)",
  "headline": "Professional headline below name (or null)",
  "location": "Location (city, country, etc.) (or null)",
  "connections": "Connections or followers count (e.g. '500+ connections') (or null)",
  "about": "Complete text of the About / Bio section (or null)",
  "open_to_work": true/false (true if '#OPEN_TO_WORK' banner or indicator is present),
  "experiences": [
    {
      "position_title": "Job title / role",
      "institution_name": "Company name",
      "from_date": "Start date/year (e.g. Jan 2020) (or null)",
      "to_date": "End date/year or Present (or null)",
      "duration": "Duration (e.g. 2 yrs 3 mos) (or null)",
      "location": "Job location (or null)",
      "description": "Job description summary (or null)"
    }
  ],
  "educations": [
    {
      "institution_name": "School / University / Institution name",
      "degree": "Degree / Field of study (or null)",
      "from_date": "Start date/year (or null)",
      "to_date": "End date/year (or null)",
      "description": "Additional education description (or null)"
    }
  ],
  "interests": [
    {
      "name": "Interest or company name",
      "category": "Category if known or General"
    }
  ],
  "accomplishments": [
    {
      "category": "Certification / Honor / Publication / Award / etc.",
      "title": "Title of accomplishment",
      "issuer": "Issuing organization (or null)"
    }
  ],
  "contacts": [
    {
      "type": "Email / Phone / Website / Twitter / LinkedIn / etc.",
      "value": "Contact detail value"
    }
  ]
}

Return ONLY valid JSON matching this schema without additional explanatory text.
"""


class VisionPersonScraper(BaseScraper):
    """
    Scraper for LinkedIn person profiles using Gemini Multimodal Vision API
    and in-memory browser screenshots.
    """

    def __init__(
        self,
        page: Page,
        callback: Optional[ProgressCallback] = None,
        gemini_api_key: Optional[str] = None,
        model: Optional[str] = None,
        include_subpages: bool = True,
        save_screenshots: bool = True,
        debug_dir: str = "debug_screenshots",
    ):
        super().__init__(page, callback)
        self.gemini_client = GeminiClient(api_key=gemini_api_key, model=model)
        self.include_subpages = include_subpages
        env_override = os.getenv("SAVE_SCREENSHOTS", "").lower()
        if env_override in ("false", "0", "no"):
            self.save_screenshots = False
        else:
            self.save_screenshots = save_screenshots or True
        self.debug_dir = debug_dir

    def _save_debug_image(self, image_bytes: bytes, filename: str) -> None:
        """Helper to save a copy of screenshot bytes to debug_dir on disk."""
        if not self.save_screenshots:
            return
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
            filepath = os.path.join(self.debug_dir, filename)
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            logger.info(f"💾 Saved debug screenshot file: {filepath}")
        except Exception as err:
            logger.warning(f"Could not save debug screenshot {filename}: {err}")

    async def scrape(
        self,
        linkedin_url: str,
        gemini_api_key: Optional[str] = None,
    ) -> Person:
        """Scrape LinkedIn profile using in-memory screenshots & Gemini API."""
        await self.callback.on_start("vision_person", linkedin_url)

        try:
            screenshots_list: List[bytes] = []

            # Step 1: Navigate to main profile page
            await self.navigate_and_wait(linkedin_url)
            await self.callback.on_progress("Navigated to main profile", 15)

            await self.ensure_logged_in()

            try:
                await self.page.wait_for_selector("main", timeout=10000)
            except Exception:
                pass
            await self.wait_and_focus(1.0)

            await self.click_all_see_more_buttons(max_attempts=5)
            await self.scroll_page_to_half()
            await self.scroll_page_to_bottom(pause_time=0.5, max_scrolls=3)
            await self.page.evaluate("window.scrollTo(0, 0)")
            await self.wait_and_focus(0.5)

            # Capture main profile screenshot
            await self.callback.on_progress("Capturing main profile screenshot in RAM", 30)
            main_screenshot = await self.page.screenshot(type="jpeg", full_page=True, quality=85)
            screenshots_list.append(main_screenshot)
            logger.info(f"📸 Captured screenshot of main profile in memory ({len(main_screenshot):,} bytes)")
            self._save_debug_image(main_screenshot, "1_main_profile.jpg")

            profile_picture_url = await self._get_profile_picture_url_fallback()

            # Step 2: Subpages (Experience, Education, Contact Info)
            if self.include_subpages:
                base_url = linkedin_url.rstrip("/") + "/"
                subpages = [
                    ("experience", "Experience", urljoin(base_url, "details/experience")),
                    ("education", "Education", urljoin(base_url, "details/education")),
                    ("contact", "Contact Info", urljoin(base_url, "overlay/contact-info/")),
                ]

                for idx, (slug, label, sub_url) in enumerate(subpages, start=2):
                    try:
                        await self.callback.on_progress(f"Capturing {label} subpage screenshot", 45)
                        await self.page.goto(sub_url, wait_until="domcontentloaded", timeout=10000)
                        await self.wait_and_focus(1.0)
                        await self.scroll_page_to_bottom(pause_time=0.3, max_scrolls=3)

                        sub_bytes = await self.page.screenshot(type="jpeg", full_page=True, quality=85)
                        screenshots_list.append(sub_bytes)
                        logger.info(f"📸 Captured screenshot of {label} subpage in memory ({len(sub_bytes):,} bytes)")
                        self._save_debug_image(sub_bytes, f"{idx}_{slug}.jpg")
                    except Exception as sub_err:
                        logger.debug(f"Subpage screenshot skipped for {label}: {sub_err}")

            # Step 3: Send images to Gemini Vision API
            await self.callback.on_progress(f"Analyzing {len(screenshots_list)} screenshot(s) with Gemini Vision API", 70)
            logger.info(f"🤖 Sending {len(screenshots_list)} in-memory screenshot(s) to Gemini Vision API...")

            raw_data = self.gemini_client.analyze_images(
                images_bytes_list=screenshots_list,
                prompt=VISION_EXTRACTION_PROMPT,
                mime_type="image/jpeg",
                api_key=gemini_api_key,
            )

            await self.callback.on_progress("Parsing Gemini Vision JSON response", 90)

            person = self._build_person_model(linkedin_url, raw_data, profile_picture_url)

            await self.callback.on_progress("Vision scraping complete", 100)
            await self.callback.on_complete("vision_person", person)

            return person

        except GeminiError as e:
            await self.callback.on_error(e)
            raise
        except Exception as e:
            await self.callback.on_error(e)
            raise ScrapingError(f"Vision person scraping failed: {e}")

    async def _get_profile_picture_url_fallback(self) -> Optional[str]:
        """Attempt to extract profile image URL directly from DOM."""
        try:
            for sel in [
                "img.pv-top-card-profile-picture__image",
                "img[alt*='profile']",
                ".pv-top-card__photo img",
                "section img"
            ]:
                el = self.page.locator(sel).first
                if await el.count() > 0:
                    src = await el.get_attribute("src")
                    if src and ("licdn.com" in src or "data:image" in src):
                        return src
            return None
        except Exception:
            return None

    def _build_person_model(
        self,
        linkedin_url: str,
        data: Dict[str, Any],
        profile_picture_url: Optional[str] = None
    ) -> Person:
        """Convert dictionary returned by Gemini into validated Person Pydantic object."""
        experiences = [
            Experience(
                position_title=exp.get("position_title", "Unknown"),
                institution_name=exp.get("institution_name", "Unknown"),
                from_date=exp.get("from_date"),
                to_date=exp.get("to_date"),
                duration=exp.get("duration"),
                location=exp.get("location"),
                description=exp.get("description"),
            )
            for exp in data.get("experiences", [])
            if isinstance(exp, dict)
        ]

        educations = [
            Education(
                institution_name=edu.get("institution_name", "Unknown"),
                degree=edu.get("degree"),
                from_date=edu.get("from_date"),
                to_date=edu.get("to_date"),
                description=edu.get("description"),
            )
            for edu in data.get("educations", [])
            if isinstance(edu, dict)
        ]

        interests = [
            Interest(
                name=inst.get("name", "Unknown"),
                category=inst.get("category", "General")
            )
            for inst in data.get("interests", [])
            if isinstance(inst, dict)
        ]

        accomplishments = [
            Accomplishment(
                category=acc.get("category", "General"),
                title=acc.get("title", "Unknown"),
                issuer=acc.get("issuer"),
            )
            for acc in data.get("accomplishments", [])
            if isinstance(acc, dict)
        ]

        contacts = [
            Contact(
                type=cnt.get("type", "Other"),
                value=cnt.get("value", ""),
            )
            for cnt in data.get("contacts", [])
            if isinstance(cnt, dict)
        ]

        return Person(
            linkedin_url=linkedin_url,
            name=data.get("name") or "Unknown",
            headline=data.get("headline"),
            location=data.get("location"),
            profile_picture_url=profile_picture_url,
            connections=data.get("connections"),
            about=data.get("about"),
            open_to_work=bool(data.get("open_to_work", False)),
            experiences=experiences,
            educations=educations,
            interests=interests,
            accomplishments=accomplishments,
            contacts=contacts,
        )
