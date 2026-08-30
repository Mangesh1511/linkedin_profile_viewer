"""
Local OCR Person Profile Scraper using RapidOCR / ONNX (100% offline, zero API quota/503 errors).
"""

import io
import logging
import re
from typing import Optional, List, Dict, Any
from urllib.parse import urljoin
from playwright.async_api import Page

from .base import BaseScraper
from ..models import Person, Experience, Education, Accomplishment, Interest, Contact
from ..callbacks import ProgressCallback, SilentCallback
from ..core.exceptions import ScrapingError

logger = logging.getLogger(__name__)


class LocalOCRPersonScraper(BaseScraper):
    """
    Scraper for LinkedIn person profiles using Local CPU/GPU OCR (RapidOCR/ONNX).
    Runs 100% locally in Python without needing Gemini API key or network calls.
    """

    def __init__(
        self,
        page: Page,
        callback: Optional[ProgressCallback] = None,
        include_subpages: bool = True,
    ):
        super().__init__(page, callback)
        self.include_subpages = include_subpages
        self._ocr_engine = None

    def _get_ocr_engine(self):
        """Lazy load RapidOCR engine."""
        if self._ocr_engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                self._ocr_engine = RapidOCR()
            except ImportError as e:
                raise ScrapingError(
                    f"RapidOCR is required for Local OCR. Install with `pip install rapidocr-onnxruntime`: {e}"
                )
        return self._ocr_engine

    async def scrape(self, linkedin_url: str) -> Person:
        """Scrape LinkedIn profile using in-memory screenshots & Local OCR."""
        await self.callback.on_start("local_ocr_person", linkedin_url)

        try:
            ocr = self._get_ocr_engine()
            all_extracted_lines: List[str] = []

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
            main_bytes = await self.page.screenshot(type="png", full_page=True)

            logger.info(f"🔍 Running Local OCR on main profile screenshot ({len(main_bytes):,} bytes)...")
            ocr_result, _ = ocr(main_bytes)
            if ocr_result:
                lines = [box[1] for box in ocr_result if box and len(box) > 1 and box[1].strip()]
                all_extracted_lines.extend(lines)

            profile_picture_url = await self._get_profile_picture_url_fallback()

            # Step 2: Subpages (Experience, Education, Contact Info)
            if self.include_subpages:
                base_url = linkedin_url.rstrip("/") + "/"
                subpages = [
                    ("Experience", urljoin(base_url, "details/experience")),
                    ("Education", urljoin(base_url, "details/education")),
                    ("Contact Info", urljoin(base_url, "overlay/contact-info/")),
                ]

                for label, sub_url in subpages:
                    try:
                        await self.callback.on_progress(f"Capturing {label} subpage for Local OCR", 50)
                        await self.page.goto(sub_url, wait_until="domcontentloaded", timeout=10000)
                        await self.wait_and_focus(1.0)
                        await self.scroll_page_to_bottom(pause_time=0.3, max_scrolls=3)

                        sub_bytes = await self.page.screenshot(type="png", full_page=True)
                        logger.info(f"🔍 Running Local OCR on {label} subpage ({len(sub_bytes):,} bytes)...")
                        sub_ocr, _ = ocr(sub_bytes)
                        if sub_ocr:
                            sub_lines = [box[1] for box in sub_ocr if box and len(box) > 1 and box[1].strip()]
                            all_extracted_lines.extend(sub_lines)
                    except Exception as sub_err:
                        logger.debug(f"Local OCR subpage skipped for {label}: {sub_err}")

            await self.callback.on_progress("Parsing Local OCR extracted text lines", 80)

            person = self._parse_ocr_lines(linkedin_url, all_extracted_lines, profile_picture_url)

            await self.callback.on_progress("Local OCR scraping complete", 100)
            await self.callback.on_complete("local_ocr_person", person)

            return person

        except Exception as e:
            await self.callback.on_error(e)
            raise ScrapingError(f"Local OCR person scraping failed: {e}")

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

    def _is_noise_or_recommendation(self, text: str) -> bool:
        """Check if a text line is sidebar recommendation, nav element, or connection card noise."""
        t = text.lower().strip()
        if not t:
            return True
        
        noise_terms = [
            "3rd+", "3rd", "2nd", "1st", "·3rd", "· 3rd", "- 3rd", "-3rd", "·2nd", "·1st",
            "+ follow", "+ connect", "follow", "connect", "message", "pending",
            "people also viewed", "people similar", "people also", "others also viewed",
            "home", "jobs", "messaging", "notifications", "search",
            "show all", "view full", "skip to", "sign in", "join now",
            "promoted", "ad\n", "advertisement"
        ]
        return any(term in t for term in noise_terms)

    def _parse_ocr_lines(
        self,
        linkedin_url: str,
        lines: List[str],
        profile_picture_url: Optional[str] = None,
    ) -> Person:
        """Parse structured text lines returned by Local OCR with strict section bounding."""
        clean_lines = []
        for l in lines:
            txt = l.strip()
            if not txt:
                continue
            if self._is_noise_or_recommendation(txt):
                if "connections" in txt.lower() or "followers" in txt.lower():
                    clean_lines.append(txt)
                continue
            clean_lines.append(txt)

        name = clean_lines[0] if len(clean_lines) > 0 else "Unknown"
        headline = clean_lines[1] if len(clean_lines) > 1 else None
        location = clean_lines[2] if len(clean_lines) > 2 else None

        connections = None
        about = None
        open_to_work = False

        for idx, line in enumerate(clean_lines):
            if "connections" in line.lower() or "followers" in line.lower():
                connections = line
            if "#open_to_work" in line.lower() or "open to work" in line.lower():
                open_to_work = True
            if line.lower() == "about" and idx + 1 < len(clean_lines):
                about = clean_lines[idx + 1]

        # Extract Experience section
        experiences: List[Experience] = []
        try:
            exp_idx = -1
            for i, l in enumerate(clean_lines):
                if l.lower() == "experience":
                    exp_idx = i
                    break

            if exp_idx != -1:
                exp_lines = []
                for l in clean_lines[exp_idx + 1:]:
                    low = l.lower()
                    if low in ["education", "licenses & certifications", "skills", "projects", "interests", "recommendations", "people also viewed"]:
                        break
                    if self._is_noise_or_recommendation(l):
                        break
                    exp_lines.append(l)

                idx = 0
                while idx < len(exp_lines):
                    title = exp_lines[idx]
                    company = exp_lines[idx + 1] if idx + 1 < len(exp_lines) else "Company"
                    
                    if not self._is_noise_or_recommendation(title) and not self._is_noise_or_recommendation(company):
                        experiences.append(
                            Experience(
                                position_title=title,
                                institution_name=company,
                            )
                        )
                    idx += 2
        except Exception as e:
            logger.debug(f"Error parsing OCR experience block: {e}")

        # Extract Education section
        educations: List[Education] = []
        try:
            edu_idx = -1
            for i, l in enumerate(clean_lines):
                if l.lower() == "education":
                    edu_idx = i
                    break

            if edu_idx != -1:
                edu_lines = []
                for l in clean_lines[edu_idx + 1:]:
                    low = l.lower()
                    if low in ["licenses & certifications", "skills", "projects", "interests", "recommendations", "people also viewed", "experience"]:
                        break
                    if self._is_noise_or_recommendation(l):
                        break
                    edu_lines.append(l)

                idx = 0
                while idx < len(edu_lines):
                    item = edu_lines[idx]
                    
                    is_date_range = bool(re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{4})\s*[-–]?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{4})?', item, re.IGNORECASE))
                    is_grade_or_skill = item.lower().startswith("grade:") or item.lower().startswith("skills:")

                    if (is_date_range or is_grade_or_skill) and len(educations) > 0:
                        last_edu = educations[-1]
                        if is_date_range and not last_edu.from_date:
                            last_edu.from_date = item
                        elif is_grade_or_skill:
                            last_edu.description = f"{last_edu.description or ''} {item}".strip()
                        idx += 1
                        continue

                    school = item
                    degree = edu_lines[idx + 1] if idx + 1 < len(edu_lines) and not self._is_noise_or_recommendation(edu_lines[idx + 1]) else None

                    if not self._is_noise_or_recommendation(school):
                        educations.append(
                            Education(
                                institution_name=school,
                                degree=degree,
                            )
                        )
                        idx += 2 if degree else 1
                    else:
                        idx += 1

        except Exception as e:
            logger.debug(f"Error parsing OCR education block: {e}")

        return Person(
            linkedin_url=linkedin_url,
            name=name,
            headline=headline,
            location=location,
            profile_picture_url=profile_picture_url,
            connections=connections,
            about=about,
            open_to_work=open_to_work,
            experiences=experiences,
            educations=educations,
            interests=[],
            accomplishments=[],
            contacts=[],
        )
