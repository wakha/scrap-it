"""Pydantic schemas for inter-service communication.

These schemas serve as:
1. Type-safe contracts between services
2. JSON serialization for future Kafka messages  
3. Validation layer for the pipeline

Future Kafka Topics:
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
    delivery_type: Optional[str] = None  # "home_delivery", "store_pickup", "parcel_shop", "parcel_locker"
    description: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Standard Shipping",
                "price": 5.99,
                "currency": "USD",
                "delivery_time": "3-5 business days",
                "delivery_type": "home_delivery"
            }
        }


class AnalysisResult(BaseModel):
    """Website analysis result (Analyzer → Scraper).
    
    Future Kafka Topic: 'analysis-results'
    Producer: AnalyzerService
    Consumer: ScraperService
    """
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
    
    def to_scraper_config(self) -> Dict[str, Any]:
        """Convert to scraper configuration dict."""
        return {
            "product_url": self.product_url,
            "source_website": self.source_website,
            "use_stealth": self.use_stealth or self.bot_protection_detected,
            "selectors": self.selectors,
            "requires_login": self.requires_login,
            "scrape_delay": max(self.scrape_delay, self.crawl_delay or 0)
        }
    
    class Config:
        json_schema_extra = {
            "example": {
                "domain": "books.toscrape.com",
                "product_url": "http://books.toscrape.com/catalogue/book_1000/index.html",
                "source_website": "books.toscrape.com",
                "can_scrape": True,
                "selectors": {
                    "product_title_xpath": "//h1",
                    "product_price_xpath": "//p[@class='price_color']"
                },
                "use_stealth": False,
                "robots_txt_allowed": True,
                "bot_protection_detected": False
            }
        }


class ScrapedProduct(BaseModel):
    """Scraped product data (Scraper → ETL).
    
    Future Kafka Topic: 'scraped-products'
    Producer: ScraperService
    Consumer: ETLService
    """
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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for ETL service."""
        return {
            "title": self.title,
            "price": self.price,
            "currency": self.currency,
            "url": self.url,
            "source_website": self.source_website,
            "shipping_providers": [sp.model_dump() for sp in self.shipping_providers],
            "screenshot_path": self.screenshot_path,
            "scraped_at": self.scraped_at
        }
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "A Light in the Attic",
                "price": 51.77,
                "currency": "GBP",
                "url": "http://books.toscrape.com/catalogue/book_1000/index.html",
                "source_website": "books.toscrape.com",
                "shipping_providers": [],
                "scraped_at": "2025-11-13T10:30:00Z"
            }
        }


class ProcessedProduct(BaseModel):
    """Processed product after ETL (ETL → Consumers).
    
    Future Kafka Topic: 'processed-products'
    Producer: ETLService
    Consumer: Analytics, Notifications, etc.
    """
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
    
    class Config:
        json_schema_extra = {
            "example": {
                "product_id": 123,
                "title": "A Light in the Attic",
                "price": 51.77,
                "currency": "GBP",
                "url": "http://books.toscrape.com/catalogue/book_1000/index.html",
                "source_website": "books.toscrape.com",
                "is_new": True,
                "scraped_at": "2025-11-13T10:30:00Z",
                "processed_at": "2025-11-13T10:30:05Z",
                "shipping_provider_count": 0
            }
        }


class ScraperLog(BaseModel):
    """Scraper execution log.
    
    Future Kafka Topic: 'scraper-logs'
    Producer: All services
    Consumer: Monitoring, Analytics
    """
    website: str
    status: str  # success, failure, skipped, blocked
    started_at: datetime
    completed_at: datetime
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    products_discovered: int = Field(default=0)
    products_scraped: int = Field(default=0)
    
    # Bot detection metadata
    robots_txt_allowed: Optional[bool] = None
    robots_txt_message: Optional[str] = None
    bot_protection_detected: Optional[bool] = None
    protection_types: Optional[str] = None
    protection_confidence: Optional[str] = None
    crawl_delay: Optional[int] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "website": "books.toscrape.com",
                "status": "success",
                "started_at": "2025-11-13T10:30:00Z",
                "completed_at": "2025-11-13T10:35:00Z",
                "duration_seconds": 300.0,
                "products_discovered": 1,
                "products_scraped": 1,
                "robots_txt_allowed": True,
                "bot_protection_detected": False
            }
        }
