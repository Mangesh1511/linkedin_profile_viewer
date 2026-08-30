"""
Exception classes for LinkedIn Profile Viewer.
"""

class ScrapingError(Exception):
    """Base exception for scraping errors."""
    pass

class AuthenticationError(ScrapingError):
    """Raised when authentication fails or session expires."""
    pass

class RateLimitError(ScrapingError):
    """Raised when LinkedIn rate limits requests."""
    pass

class ElementNotFoundError(ScrapingError):
    """Raised when expected page element is missing."""
    pass
