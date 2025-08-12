from .scraper import ECFRScraper
from .metadata import MetadataExtractor
from . import normalize  # re-export module for convenience in tests and users

__all__ = ["ECFRScraper", "MetadataExtractor", "normalize"]
__version__ = "0.1.0"
