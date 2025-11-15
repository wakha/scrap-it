"""Services package for web scraping (Kafka-ready).

This package contains service classes that handle the scraping pipeline:
- AnalyzerService: Website analysis and product discovery
- ScraperService: Product scraping with Playwright browser automation
- ETLService: Data transformation and database persistence

All services use Pydantic schemas for data validation and are designed
to work with message queues like Kafka for scalable async processing.
"""

from .analyzer_service import AnalyzerService
from .scraper_service import ScraperService
from .etl_service import ETLService

__all__ = [
    "AnalyzerService",
    "ScraperService",
    "ETLService",
]
