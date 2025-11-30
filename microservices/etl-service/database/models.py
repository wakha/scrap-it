"""Database models for scraper application."""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from database.config import Base


class Product(Base):
    """Product model representing scraped product information."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    source_website: Mapped[str] = mapped_column(String(100), nullable=False)

    # Metadata
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    screenshot_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    raw_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship to shipping providers
    shipping_providers: Mapped[List["ShippingProvider"]] = relationship(
        "ShippingProvider", back_populates="product", cascade="all, delete-orphan"
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_source_website", "source_website"),
        Index("idx_scraped_at", "scraped_at"),
        Index("idx_title_source", "title", "source_website"),
    )

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, title='{self.title[:30]}...', price={self.price} {self.currency})>"


class ShippingProvider(Base):
    """Shipping provider model representing available shipping options."""

    __tablename__ = "shipping_providers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    product_id: Mapped[int] = mapped_column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    delivery_time: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    delivery_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # home_delivery, store_pickup, parcel_shop, parcel_locker
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)

    # Relationship to product
    product: Mapped["Product"] = relationship("Product", back_populates="shipping_providers")

    # Indexes and constraints
    __table_args__ = (
        Index("idx_product_id", "product_id"),
        Index("idx_provider_name", "name"),
        # Prevent duplicate shipping providers for same product
        UniqueConstraint("product_id", "name", name="uq_product_provider"),
    )

    def __repr__(self) -> str:
        return f"<ShippingProvider(id={self.id}, name='{self.name}', price={self.price})>"


class ScraperLog(Base):
    """Log model for tracking scraper runs and errors."""

    __tablename__ = "scraper_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    website: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)  # success, failure, partial
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    products_scraped: Mapped[int] = mapped_column(Integer, default=0)

    # Bot detection and robots.txt compliance fields
    robots_txt_allowed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    robots_txt_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    bot_protection_detected: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    protection_types: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    protection_confidence: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    crawl_delay: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_website_status", "website", "status"),
        Index("idx_started_at", "started_at"),
        Index("idx_bot_protection", "bot_protection_detected"),
        Index("idx_robots_allowed", "robots_txt_allowed"),
    )

    def __repr__(self) -> str:
        return f"<ScraperLog(id={self.id}, website='{self.website}', status='{self.status}')>"
