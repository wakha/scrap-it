"""Shared Pydantic schemas for inter-service communication via Kafka.

These schemas serve as:
1. Type-safe contracts between microservices
2. JSON serialization for Kafka messages
3. Validation layer for the pipeline

Kafka Topics:
- 'analysis-results' → Analyzer publishes, Scraper consumes
- 'scraped-products' → Scraper publishes, ETL consumes
- 'processed-products' → ETL publishes, downstream services consume
"""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ShippingProvider(BaseModel):
    """Shipping provider information."""

    name: str
    price: Optional[float] = None
    currency: Optional[str] = None
    delivery_time: Optional[str] = None
    delivery_type: Optional[str] = None
    description: Optional[str] = None


class AnalysisResult(BaseModel):
    """Website analysis result published to 'analysis-results' topic."""

    # Discovery
    domain: str
    product_url: Optional[str] = None
    source_website: str
    can_scrape: bool

    # Selectors
    selectors: Dict[str, Optional[str]] = Field(default_factory=dict)

    # Configuration
    use_stealth: bool = Field(default=False)
    scrape_delay: int = Field(default=3)
    requires_login: bool = Field(default=False)

    # Robots.txt
    robots_txt_allowed: bool = Field(default=True)
    robots_txt_message: str = Field(default="")
    crawl_delay: Optional[int] = None

    # Bot protection
    bot_protection_detected: bool = Field(default=False)
    protection_types: List[str] = Field(default_factory=list)
    protection_confidence: str = Field(default="low")

    # Metadata
    analyzed_at: datetime = Field(default_factory=datetime.now)
    request_id: str = Field(default="")  # For tracing


class ScrapedProduct(BaseModel):
    """Scraped product data published to 'scraped-products' topic."""

    # Product data
    title: str
    price: float
    currency: str
    url: str
    source_website: str

    # Shipping
    shipping_providers: List[ShippingProvider] = Field(default_factory=list)

    # Metadata
    screenshot_path: Optional[str] = None
    scraped_at: datetime = Field(default_factory=datetime.now)
    scraper_metadata: Dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(default="")  # For tracing


class ProcessedProduct(BaseModel):
    """Processed product published to 'processed-products' topic."""

    # Database ID
    product_id: int

    # Product data
    title: str
    price: float
    currency: str
    url: str
    source_website: str

    # Status
    is_new: bool
    is_updated: bool = Field(default=False)
    previous_price: Optional[float] = None

    # Metadata
    scraped_at: datetime
    processed_at: datetime = Field(default_factory=datetime.now)
    shipping_provider_count: int = Field(default=0)
    request_id: str = Field(default="")  # For tracing
