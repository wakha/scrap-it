"""Main application entry point.

All services communicate via Pydantic schemas that can be serialized to Kafka, when required.
"""
import asyncio
import sys
from datetime import datetime
from urllib.parse import urlparse
from typing import Optional

from src.services.analyzer_service import AnalyzerService
from src.services.scraper_service import ScraperService
from src.services.etl_service import ETLService
from src.database.config import get_async_db
from src.config import settings
from src.utils.logger import logger
from src.schemas.messages import AnalysisResult, ScrapedProduct, ProcessedProduct
from src.constants import LOG_SEPARATOR, STATUS_SUCCESS
from src.helpers.scraper_log_helpers import (
    save_blocked_log,
    save_failure_log,
    save_success_log,
    determine_blocking_status,
)


async def scrape_url_async(
    url: str,
    product_path: Optional[str] = None,
    checkout_path: Optional[str] = None
) -> None:
    """
    Scrape pipeline for scraping a url.

    Pipeline Flow (Current):
        URL → Analyzer → AnalysisResult → Scraper → ScrapedProduct → ETL → ProcessedProduct

    Pipeline Flow (Future with Kafka):
        URL → Analyzer → [analysis-results topic]
                    ↓
              Scraper (consumer) → [scraped-products topic]
                    ↓
              ETL (consumer) → [processed-products topic]
                    ↓
              Downstream consumers (analytics, notifications, etc.)

    Args:
        url: Base URL to scrape
        product_path: Optional product page path
        checkout_path: Optional checkout page path
    """
    logger.info(f"Starting scraping for: {url}")
    logger.info(f"[CONFIG] Headless mode: {settings.headless_mode}")
    logger.info(f"[CONFIG] Screenshot enabled: {settings.screenshot_enabled}")

    started_at = datetime.now()
    source_name = urlparse(url).netloc or url

    try:
        # STEP 1: Website Analysis (Analyzer Service)
        logger.info(LOG_SEPARATOR)
        logger.info("STEP 1: Website Analysis & Product Discovery")
        logger.info(LOG_SEPARATOR)

        async with AnalyzerService(headless=settings.headless_mode) as analyzer:
            analysis: AnalysisResult = await analyzer.analyze_website(
                url, product_path, checkout_path, auto_discover=True
            )

        # Log analysis results
        _log_analysis_results(analysis)

        # Check if we should proceed
        if not analysis.can_scrape:
            await _handle_blocked_scraping(source_name, started_at, analysis)
            return

        # STEP 2: Scraping (Scraper Service)
        # Future: Consumes from 'analysis-results', publishes ScrapedProduct to 'scraped-products'
        logger.info(f"\n{LOG_SEPARATOR}")
        logger.info("STEP 2: Product Scraping")
        logger.info(LOG_SEPARATOR)

        async with ScraperService(
            headless=settings.headless_mode,
            screenshot=settings.screenshot_enabled
        ) as scraper:
            scraped_product: ScrapedProduct = await scraper.scrape(analysis)

        if not scraped_product:
            await _handle_scraping_failure(source_name, started_at, analysis)
            return

        logger.info(f"\n[SUCCESS] Scraped Product:")
        logger.info(f"  Title: {scraped_product.title}")
        logger.info(f"  Price: {scraped_product.price} {scraped_product.currency}")
        logger.info(f"  Shipping Providers: {len(scraped_product.shipping_providers)}")

        # STEP 3: ETL Processing (ETL Service)
        # Future: Consumes from 'scraped-products', publishes ProcessedProduct to 'processed-products'
        logger.info(f"\n{LOG_SEPARATOR}")
        logger.info("STEP 3: ETL Processing & Storage")
        logger.info(LOG_SEPARATOR)

        async with get_async_db() as db:
            etl = ETLService()
            processed_product: ProcessedProduct = await etl.save_and_emit(scraped_product)

            if processed_product:
                _log_processed_product(processed_product)
                # Future: Publish to Kafka topic 'processed-products'
                # await kafka_producer.send('processed-products', processed_product.model_dump_json())

            await save_success_log(
                source_name,
                started_at,
                analysis,
                products_scraped=1 if processed_product else 0
            )

        duration = (datetime.now() - started_at).total_seconds()
        logger.info(f"\n{LOG_SEPARATOR}")
        logger.info(f"[COMPLETE] Pipeline Complete! Duration: {duration:.2f}s")
        logger.info(LOG_SEPARATOR)

    except Exception as e:
        logger.error(f"[ERROR] Error in pipeline: {e}")
        await _handle_pipeline_error(source_name, started_at, e)


def _log_analysis_results(analysis: AnalysisResult) -> None:
    """Log analysis results in a formatted way.
    
    Args:
        analysis: The analysis result to log
    """
    logger.info(f"\nAnalysis Results for {analysis.domain}:")
    logger.info(f"  Can Scrape: {analysis.can_scrape}")
    logger.info(f"  Product URL: {analysis.product_url or 'N/A'}")
    logger.info(f"  robots.txt: {analysis.robots_txt_message}")
    logger.info(f"  Bot Protection: {analysis.bot_protection_detected}")

    if analysis.bot_protection_detected:
        logger.info(f"    Types: {', '.join(analysis.protection_types)}")
        logger.info(f"    Confidence: {analysis.protection_confidence}")

    detected_selectors = sum(1 for v in analysis.selectors.values() if v)
    logger.info(f"  Selectors Detected: {detected_selectors}/6")


async def _handle_blocked_scraping(
    source_name: str,
    started_at: datetime,
    analysis: AnalysisResult
) -> None:
    """Handle blocked scraping scenario.
    
    Args:
        source_name: Website source name
        started_at: When scraping started
        analysis: The analysis result
    """
    logger.warning("[STOP] Website cannot be scraped")
    status, error_msg = determine_blocking_status(analysis)
    await save_blocked_log(source_name, started_at, analysis, error_msg)


async def _handle_scraping_failure(
    source_name: str,
    started_at: datetime,
    analysis: AnalysisResult
) -> None:
    """Handle scraping failure scenario.
    
    Args:
        source_name: Website source name
        started_at: When scraping started
        analysis: The analysis result
    """
    logger.error("[ERROR] Scraping failed")
    await save_failure_log(
        source_name,
        started_at,
        "Failed to extract product data",
        robots_txt_allowed=analysis.robots_txt_allowed,
        bot_protection_detected=analysis.bot_protection_detected
    )


def _log_processed_product(processed_product: ProcessedProduct) -> None:
    """Log processed product information.
    
    Args:
        processed_product: The processed product to log
    """
    logger.info(f"[SUCCESS] Product saved to database (ID: {processed_product.product_id})")
    logger.info(f"  Is New: {processed_product.is_new}")
    logger.info(f"  Processed At: {processed_product.processed_at}")


async def _handle_pipeline_error(
    source_name: str,
    started_at: datetime,
    error: Exception
) -> None:
    """Handle pipeline error by logging it.
    
    Args:
        source_name: Website source name
        started_at: When scraping started
        error: The exception that occurred
    """
    try:
        await save_failure_log(source_name, started_at, str(error))
    except Exception as log_error:
        logger.error(f"Could not save error log: {log_error}")


async def scrape_multiple_urls_async(urls: list[str]):
    """
    Scrape multiple URLs concurrently.

    This demonstrates the power of async architecture:
    - All URLs analyzed concurrently
    - All products scraped concurrently
    - All ETL operations run concurrently

    Args:
        urls: List of URLs to scrape
    """
    logger.info(f"[CONCURRENT] Starting concurrent scraping of {len(urls)} websites")

    # Run all scrapes concurrently
    tasks = [scrape_url_async(url) for url in urls]
    await asyncio.gather(*tasks, return_exceptions=True)

    logger.info(f"[COMPLETE] All {len(urls)} websites processed concurrently")


def main() -> None:
    """
    Entry point for scraper.

    Command-line interface for running the scraper. Supports single URL scraping
    or concurrent scraping of multiple URLs.

    Usage:
        python -m src.main --url <url>
        python -m src.main --urls <url1> <url2> ...
    """
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Single URL:    python -m src.main --url <url>")
        print("  Multiple URLs: python -m src.main --urls <url1> <url2> ...")
        print("\nExamples:")
        print('  python -m src.main --url "http://books.toscrape.com"')
        print('  python -m src.main --urls "http://site1.com" "http://site2.com"')
        sys.exit(1)

    if "--url" in sys.argv:
        url_index = sys.argv.index("--url") + 1
        url = sys.argv[url_index]
        asyncio.run(scrape_url_async(url))

    elif "--urls" in sys.argv:
        urls_index = sys.argv.index("--urls") + 1
        urls = sys.argv[urls_index:]
        asyncio.run(scrape_multiple_urls_async(urls))

    else:
        print("Error: Must specify --url or --urls")
        sys.exit(1)


if __name__ == "__main__":
    main()
