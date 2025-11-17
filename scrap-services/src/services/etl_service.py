"""
ETL Service
Handles database operations
Accepts ScrapedProduct, returns ProcessedProduct (both Kafka-ready)
"""
import logging
import traceback
import asyncio
from typing import Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import SQLAlchemyError, OperationalError

from src.schemas.messages import ScrapedProduct, ProcessedProduct
from src.database.models import Product, ScraperLog, ShippingProvider
from src.database.config import get_async_db
from src.config import settings
from src.constants import EXPONENTIAL_BACKOFF_BASE

logger = logging.getLogger(__name__)


class ETLService:
    """ETL Service for database operations with retry logic"""

    def __init__(self, max_retries: Optional[int] = None):
        self.max_retries = max_retries or settings.max_retries

    async def save_and_emit(self, scraped_product: ScrapedProduct) -> Optional[ProcessedProduct]:
        """
        Save and emit (wrapper for save_product for compatibility).
        Future: Will also emit to Kafka after saving.
        """
        return await self.save_product(scraped_product, status="success")

    async def save_product(
        self,
        scraped_product: ScrapedProduct,
        status: str = "success"
    ) -> Optional[ProcessedProduct]:
        """
        Save scraped product to database with retry logic.

        Args:
            scraped_product: ScrapedProduct Pydantic schema
            status: Processing status

        Returns:
            ProcessedProduct Pydantic schema or None if failed
        """
        for attempt in range(self.max_retries):
            try:
                return await self._save_product_to_db(scraped_product)
            except OperationalError as e:
                if not await self._handle_retry(e, attempt):
                    return None
            except SQLAlchemyError as e:
                logger.error(f"Database error saving product: {e}")
                logger.debug(f"Stack trace: {traceback.format_exc()}")
                return None
            except Exception as e:
                logger.error(f"Unexpected error saving product: {e}")
                logger.debug(f"Stack trace: {traceback.format_exc()}")
                return None

        return None

    async def _save_product_to_db(
        self,
        scraped_product: ScrapedProduct
    ) -> ProcessedProduct:
        """Save product to database.

        Args:
            scraped_product: Product to save

        Returns:
            ProcessedProduct with database ID
        """
        async with get_async_db() as db:
            # Extract from scraped_product
            metadata = scraped_product.scraper_metadata or {}

            # Create Product model
            product = Product(
                title=scraped_product.title,
                price=scraped_product.price,
                currency=scraped_product.currency,
                url=scraped_product.url,
                source_website=scraped_product.source_website,
                scraped_at=scraped_product.scraped_at,
                screenshot_path=scraped_product.screenshot_path,
                raw_html=None,
            )

            db.add(product)
            await db.flush()  # Flush to get product.id before creating shipping providers

            # Create ShippingProvider models (deduplicate by name)
            self._add_shipping_providers(db, product.id, scraped_product.shipping_providers)

            await db.commit()
            await db.refresh(product)

            logger.info(f" Saved product to database: {product.title}")
            if scraped_product.shipping_providers:
                logger.info(f" Saved {len(scraped_product.shipping_providers)} shipping provider(s)")

            # Create ProcessedProduct schema
            return self._create_processed_product(product, scraped_product)

    def _add_shipping_providers(
        self,
        db: AsyncSession,
        product_id: int,
        providers: List
    ) -> None:
        """Add shipping providers to database, deduplicating by name.

        Args:
            db: Database session
            product_id: Product ID to associate providers with
            providers: List of shipping provider data
        """
        seen_providers = set()
        for sp_data in providers:
            # Skip duplicates
            if sp_data.name in seen_providers:
                continue
            seen_providers.add(sp_data.name)

            shipping_provider = ShippingProvider(
                product_id=product_id,
                name=sp_data.name,
                price=sp_data.price,
                currency=sp_data.currency,
                delivery_time=sp_data.delivery_time,
                delivery_type=sp_data.delivery_type,
                description=sp_data.description,
            )
            db.add(shipping_provider)

    def _create_processed_product(
        self,
        product: Product,
        scraped_product: ScrapedProduct
    ) -> ProcessedProduct:
        """Create ProcessedProduct from saved Product.

        Args:
            product: Saved Product model
            scraped_product: Original scraped product data

        Returns:
            ProcessedProduct schema
        """
        return ProcessedProduct(
            product_id=product.id,
            title=product.title,
            price=product.price,
            currency=product.currency,
            url=product.url,
            source_website=product.source_website,
            scraped_at=product.scraped_at,
            processed_at=datetime.now(),
            is_new=True,
            is_updated=False,
            shipping_provider_count=len(scraped_product.shipping_providers),
        )

    async def _handle_retry(self, error: OperationalError, attempt: int) -> bool:
        """Handle retry logic for operational errors.

        Args:
            error: The operational error
            attempt: Current attempt number

        Returns:
            True if should retry, False otherwise
        """
        logger.warning(
            f"Database connection error (attempt {attempt + 1}/{self.max_retries}): {error}"
        )
        if attempt < self.max_retries - 1:
            wait_time = EXPONENTIAL_BACKOFF_BASE ** attempt
            logger.info(f"Retrying in {wait_time}s...")
            await asyncio.sleep(wait_time)
            return True
        else:
            logger.error("Max database retries reached")
            logger.debug(f"Stack trace: {traceback.format_exc()}")
            return False

    async def save_scraper_log(
        self,
        website: Optional[str] = None,
        source_name: Optional[str] = None,
        status: str = "success",
        message: Optional[str] = None,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        **kwargs,
    ) -> None:
        """
        Save scraper log entry to database with retry logic.

        Args:
            website: Website name
            source_name: Alternative name for website
            status: Scrape status
            message: Optional message
            error_message: Error message if failed
            started_at: When scraping started
            completed_at: When scraping completed
            **kwargs: Additional log fields
        """
        for attempt in range(self.max_retries):
            try:
                await self._save_log_to_db(
                    website or source_name or "unknown",
                    status,
                    error_message or message,
                    started_at,
                    completed_at,
                    **kwargs
                )
                return  # Success, exit function

            except OperationalError as e:
                if not await self._handle_log_retry(e, attempt):
                    break
            except Exception as e:
                logger.error(f"Error saving scraper log: {e}")
                logger.debug(f"Stack trace: {traceback.format_exc()}")
                break  # Don't retry on unexpected errors

    async def _save_log_to_db(
        self,
        name: str,
        status: str,
        error_msg: Optional[str],
        started_at: Optional[datetime],
        completed_at: Optional[datetime],
        **kwargs
    ) -> None:
        """Save log entry to database.

        Args:
            name: Website name
            status: Scrape status
            error_msg: Error message if any
            started_at: Start time
            completed_at: Completion time
            **kwargs: Additional fields
        """
        async with get_async_db() as db:
            log_entry = ScraperLog(
                website=name,
                status=status,
                started_at=started_at or datetime.now(),
                completed_at=completed_at,
                error_message=error_msg,
                products_scraped=kwargs.get("products_scraped", 0),
                robots_txt_allowed=kwargs.get("robots_txt_allowed"),
                robots_txt_message=kwargs.get("robots_txt_message"),
                bot_protection_detected=kwargs.get("bot_protection_detected"),
                protection_types=kwargs.get("protection_types"),
                protection_confidence=kwargs.get("protection_confidence"),
                crawl_delay=kwargs.get("crawl_delay"),
            )

            db.add(log_entry)
            await db.commit()
            logger.info(f"Saved scraper log for {name}: {status}")

    async def _handle_log_retry(self, error: OperationalError, attempt: int) -> bool:
        """Handle retry logic for log save errors.

        Args:
            error: The operational error
            attempt: Current attempt number

        Returns:
            True if should retry, False otherwise
        """
        logger.warning(
            f"Database connection error saving log (attempt {attempt + 1}/{self.max_retries}): {error}"
        )
        if attempt < self.max_retries - 1:
            wait_time = EXPONENTIAL_BACKOFF_BASE ** attempt
            await asyncio.sleep(wait_time)
            return True
        else:
            logger.error("Failed to save scraper log after max retries")
            return False

    async def get_products_by_website(
        self,
        website: str,
        limit: int = 100
    ) -> List[Product]:
        """
        Retrieve products from database by website.

        Args:
            website: Source website name
            limit: Maximum number of products to retrieve

        Returns:
            List of Product model instances
        """
        try:
            async with get_async_db() as db:
                result = await db.execute(
                    select(Product)
                    .where(Product.source_website == website)
                    .order_by(Product.scraped_at.desc())
                    .limit(limit)
                )
                products = result.scalars().all()
                logger.info(f"Retrieved {len(products)} products from {website}")
                return list(products)

        except Exception as e:
            logger.error(f"Error retrieving products: {e}")
            return []
