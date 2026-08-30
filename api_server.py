#!/usr/bin/env python3
"""
LinkedIn Profile Viewer REST API Server

FastAPI server exposing REST endpoints for scraping LinkedIn person profiles
using DOM Parsing (v1), Gemini Multimodal Vision AI (v2), and Local CPU OCR (v3).
"""

import asyncio
import logging
import os
import secrets
import sys
import subprocess
from contextlib import asynccontextmanager
from typing import Optional
from pathlib import Path

_DEPENDENCIES_CHECKED = False

def ensure_dependencies():
    """Auto-detect and install any missing required Python packages on startup."""
    global _DEPENDENCIES_CHECKED
    if _DEPENDENCIES_CHECKED:
        return
    _DEPENDENCIES_CHECKED = True

    if sys.argv and ("multiprocessing" in sys.argv[0] or "spawn" in sys.argv[0]):
        return

    required = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn",
        "pydantic": "pydantic",
        "playwright": "playwright",
        "requests": "requests",
        "dotenv": "python-dotenv",
        "rapidocr_onnxruntime": "rapidocr-onnxruntime",
        "PIL": "pillow",
    }
    missing = []
    for module_name, pkg_name in required.items():
        try:
            __import__(module_name)
        except ImportError:
            missing.append(pkg_name)
    if missing:
        print(f"📦 Auto-installing missing dependencies into Python ({sys.executable}): {missing}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing, "--break-system-packages"])
        except Exception:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])

ensure_dependencies()

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from pydantic import BaseModel, HttpUrl
from dotenv import load_dotenv

# Load environment variables from .env file (and .env.example fallback)
load_dotenv()
load_dotenv(".env.example")

from linkedin_profile_viewer.core.browser import BrowserManager
from linkedin_profile_viewer.scrapers.person import PersonScraper
from linkedin_profile_viewer.scrapers.vision_person import VisionPersonScraper
from linkedin_profile_viewer.scrapers.local_ocr_person import LocalOCRPersonScraper
from linkedin_profile_viewer.callbacks import ConsoleCallback
from linkedin_profile_viewer.core.gemini import GeminiError
from linkedin_profile_viewer.core.exceptions import (
    AuthenticationError,
    RateLimitError,
    ScrapingError,
    ElementNotFoundError,
)

# Configure logging to write to both stdout console and api_server.log file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("api_server.log", mode="a", encoding="utf-8"),
    ]
)
logger = logging.getLogger("api_server")

# Global browser manager reference
browser_manager: Optional[BrowserManager] = None
SESSION_FILE = "linkedin_session.json"


from linkedin_profile_viewer.core.auth import load_credentials_from_env, login_with_credentials


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage browser lifecycle during application startup and shutdown."""
    global browser_manager
    session_path = Path(SESSION_FILE)

    logger.info("Initializing Playwright BrowserManager for API server...")
    browser_manager = BrowserManager(headless=True)
    await browser_manager.start()

    if session_path.exists():
        await browser_manager.load_session(SESSION_FILE)
        logger.info("✓ Session loaded successfully into browser manager context")
    else:
        email, password = load_credentials_from_env()
        if email and password:
            logger.info(f"🔑 'linkedin_session.json' not found. Performing automated login for {email}...")
            try:
                page = await browser_manager.context.new_page()
                await login_with_credentials(page, email=email, password=password, warm_up=True)
                await browser_manager.save_session(SESSION_FILE)
                await page.close()
                logger.info(f"✓ Created and saved new '{SESSION_FILE}'")
            except Exception as login_err:
                logger.warning(
                    f"Automated login failed on startup: {login_err}. "
                    "Run `python3 create_session.py` to authenticate manually."
                )
        else:
            logger.warning(
                f"Session file '{SESSION_FILE}' not found and credentials not set in .env. "
                "Run `python3 create_session.py` to authenticate."
            )

    yield  # Server runs here

    logger.info("Shutting down Playwright BrowserManager...")
    if browser_manager:
        await browser_manager.close()
    logger.info("✓ Shutdown complete")


app = FastAPI(
    title="LinkedIn Profile Viewer REST API",
    description="REST API for scraping LinkedIn person profiles via DOM (v1), Gemini Vision AI (v2), and Local CPU OCR (v3).",
    version="2.0.0",
    lifespan=lifespan,
)

API_KEY = os.getenv("API_KEY")


async def require_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")):
    """Require an application API key for public scraping routes."""
    if not API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API_KEY is not configured on the server.",
        )
    if not x_api_key or not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid X-API-Key header is required.",
        )


class ScrapeRequest(BaseModel):
    url: str


class VisionScrapeRequest(BaseModel):
    url: str
    gemini_api_key: Optional[str] = None
    model: Optional[str] = None
    save_screenshots: Optional[bool] = True


@app.get("/health")
async def health_check():
    """Healthcheck endpoint."""
    return {
        "status": "healthy",
        "browser_active": browser_manager is not None and browser_manager._browser is not None,
    }


@app.get("/api/profileinfo")
async def get_profile_info(
    profileUrl: str = Query(..., description="LinkedIn profile URL to scrape via DOM (v1)"),
    _api_key: None = Depends(require_api_key),
):
    """
    Scrape a LinkedIn person profile by URL using standard DOM parsing (v1).
    
    Example: `/api/profileinfo?profileUrl=https://www.linkedin.com/in/williamhgates/`
    """
    return await _scrape_profile(profileUrl)


@app.get("/api/v2/profileinfo")
@app.get("/api/profileinfo_vision")
async def get_profile_info_vision(
    profileUrl: str = Query(..., description="LinkedIn profile URL to scrape via Gemini Vision (v2)"),
    geminiApiKey: Optional[str] = Query(None, description="Gemini API Key (optional if GEMINI_API_KEY env var is set)"),
    model: Optional[str] = Query(None, description="Gemini model name (e.g. gemini-3.6-flash)"),
    saveScreenshots: bool = Query(False, description="Save debug screenshot files to debug_screenshots/ folder"),
    _api_key: None = Depends(require_api_key),
):
    """
    Scrape a LinkedIn person profile by URL using Gemini Multimodal Vision API (v2) & in-memory browser screenshots.
    
    Example: `/api/v2/profileinfo?profileUrl=https://www.linkedin.com/in/williamhgates/`
    """
    return await _scrape_profile_vision(profileUrl, gemini_api_key=geminiApiKey, model=model, save_screenshots=saveScreenshots)


@app.post("/api/v2/profileinfo")
async def post_profile_info_vision(
    req: VisionScrapeRequest,
    _api_key: None = Depends(require_api_key),
):
    """
    POST endpoint to scrape a profile using Gemini Vision (v2).
    """
    return await _scrape_profile_vision(req.url, gemini_api_key=req.gemini_api_key, model=req.model, save_screenshots=bool(req.save_screenshots or False))


@app.get("/api/v3/profileinfo")
@app.get("/api/profileinfo_ocr")
async def get_profile_info_ocr(
    profileUrl: str = Query(..., description="LinkedIn profile URL to scrape via 100% Local CPU OCR (v3)"),
    _api_key: None = Depends(require_api_key),
):
    """
    Scrape a LinkedIn person profile using 100% Local CPU OCR (RapidOCR/ONNX) on in-memory screenshots (v3).
    Runs completely offline in Python without external API calls.
    
    Example: `/api/v3/profileinfo?profileUrl=https://www.linkedin.com/in/williamhgates/`
    """
    return await _scrape_profile_ocr(profileUrl)


async def _scrape_profile_ocr(url: str):
    """Execute local OCR person scraping logic using in-memory screenshots."""
    if not browser_manager or not browser_manager.context:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Browser context is not initialized."
        )

    page = None
    try:
        page = await browser_manager.context.new_page()
        scraper = LocalOCRPersonScraper(page, callback=ConsoleCallback())

        logger.info(f"Local OCR API Scrape request received for: {url}")
        person = await scraper.scrape(url)

        return {
            "status": "success",
            "data": person.to_dict(),
        }

    except ScrapingError as e:
        logger.error(f"Local OCR Scraping error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

    except Exception as e:
        logger.error(f"Unexpected error in Local OCR scrape: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while local OCR scraping profile: {e}"
        )

    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


async def _scrape_profile(url: str):
    """Execute person scraping logic using a new page in the shared authenticated context."""
    if not browser_manager or not browser_manager.context:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Browser context is not initialized."
        )

    page = None
    try:
        page = await browser_manager.context.new_page()
        scraper = PersonScraper(page, callback=ConsoleCallback())

        logger.info(f"API Scrape request received for: {url}")
        person = await scraper.scrape(url)

        return {
            "status": "success",
            "data": person.to_dict(),
        }

    except RateLimitError as e:
        logger.error(f"Rate limit error during API scrape: {e}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit detected: {e}"
        )

    except AuthenticationError as e:
        logger.error(f"Authentication error during API scrape: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {e}"
        )

    except ScrapingError as e:
        logger.error(f"Scraping error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while scraping profile: {e}"
        )

    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


async def _scrape_profile_vision(
    url: str,
    gemini_api_key: Optional[str] = None,
    model: Optional[str] = None,
    save_screenshots: bool = True,
):
    """Execute vision person scraping logic using in-memory screenshots and Gemini API."""
    if not browser_manager or not browser_manager.context:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Browser context is not initialized."
        )

    page = None
    try:
        page = await browser_manager.context.new_page()
        scraper = VisionPersonScraper(
            page,
            callback=ConsoleCallback(),
            gemini_api_key=gemini_api_key,
            model=model,
            save_screenshots=save_screenshots,
        )

        logger.info(f"Vision API Scrape request received for: {url}")
        person = await scraper.scrape(url, gemini_api_key=gemini_api_key)

        return {
            "status": "success",
            "data": person.to_dict(),
        }

    except GeminiError as e:
        logger.error(f"Gemini API error during vision scrape: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Gemini API error: {e}"
        )

    except RateLimitError as e:
        logger.error(f"Rate limit error during API scrape: {e}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit detected: {e}"
        )

    except AuthenticationError as e:
        logger.error(f"Authentication error during API scrape: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication error: {e}"
        )

    except ScrapingError as e:
        logger.error(f"Scraping error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while vision scraping profile: {e}"
        )

    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
