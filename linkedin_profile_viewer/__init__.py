"""
LinkedIn Profile Viewer Package.
"""

from .models import (
    Person,
    Experience,
    Education,
    Accomplishment,
    Interest,
    Contact,
)

from .scrapers import (
    PersonScraper,
    VisionPersonScraper,
    LocalOCRPersonScraper,
)

from .core import (
    BrowserManager,
    GeminiClient,
    GeminiError,
    ScrapingError,
    AuthenticationError,
    RateLimitError,
)

__version__ = "2.0.0"

__all__ = [
    'Person',
    'Experience',
    'Education',
    'Accomplishment',
    'Interest',
    'Contact',
    'PersonScraper',
    'VisionPersonScraper',
    'LocalOCRPersonScraper',
    'BrowserManager',
    'GeminiClient',
    'GeminiError',
    'ScrapingError',
    'AuthenticationError',
    'RateLimitError',
]
