"""Main application entry point.

This demonstrates the concurrent architecture that is Kafka-ready.
All services communicate via Pydantic schemas that can be serialized to Kafka.
"""
import asyncio
import sys
from datetime import datetime
from urllib.parse import urlparse

from src.services.analyzer_service import AnalyzerService
from src.services.scraper_service import ScraperService
from src.services.etl_service import ETLService
from src.database.config import get_async_db
from src.config import settings
from src.utils.logger import logger
from src.schemas.messages import AnalysisResult, ScrapedProduct, ProcessedProduct


async def scrape_url_async(url: str, product_path: str = None, checkout_path: str = None):
    """
    Scrape pipeline demonstrating Kafka-ready architecture.

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
        # Future: This publishes AnalysisResult to 'analysis-results' Kafka topic
        logger.info("=" * 70)
        logger.info("STEP 1: Website Analysis & Product Discovery")
        logger.info("=" * 70)

        async with AnalyzerService(headless=settings.headless_mode) as analyzer:
            analysis: AnalysisResult = await analyzer.analyze_website(
                url, product_path, checkout_path, auto_discover=True
            )

        # Log analysis results
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

        # Check if we should proceed
        if not analysis.can_scrape:
            logger.warning(f"[STOP] Website cannot be scraped")

            # Determine status
            if analysis.bot_protection_detected:
                status = "blocked"
                error_msg = f"Bot protection detected: {', '.join(analysis.protection_types)}"
            elif not analysis.robots_txt_allowed:
                status = "skipped"
                error_msg = f"robots.txt disallows scraping"
            elif not analysis.product_url:
                status = "failure"
                error_msg = "Could not discover any products"
            else:
                status = "failure"
                error_msg = "Website analysis failed"

            # Save log
            async with get_async_db() as db:
                etl = ETLService()
                await etl.save_scraper_log(
                    website=source_name,
                    status=status,
                    started_at=started_at,
                    completed_at=datetime.now(),
                    error_message=error_msg,
                    products_scraped=0,
                    robots_txt_allowed=analysis.robots_txt_allowed,
                    robots_txt_message=analysis.robots_txt_message,
                    bot_protection_detected=analysis.bot_protection_detected,
                    protection_types=", ".join(analysis.protection_types),
                    protection_confidence=analysis.protection_confidence,
                    crawl_delay=analysis.crawl_delay,
                )

            return

        # STEP 2: Scraping (Scraper Service)
        # Future: Consumes from 'analysis-results', publishes ScrapedProduct to 'scraped-products'
        logger.info("\n" + "=" * 70)
        logger.info("STEP 2: Product Scraping")
        logger.info("=" * 70)

        async with ScraperService(headless=settings.headless_mode, screenshot=settings.screenshot_enabled) as scraper:
            scraped_product: ScrapedProduct = await scraper.scrape(analysis)

        if not scraped_product:
            logger.error("[ERROR] Scraping failed")

            async with get_async_db() as db:
                etl = ETLService()
                await etl.save_scraper_log(
                    website=source_name,
                    status="failure",
                    started_at=started_at,
                    completed_at=datetime.now(),
                    error_message="Failed to extract product data",
                    products_scraped=0,
                    robots_txt_allowed=analysis.robots_txt_allowed,
                    bot_protection_detected=analysis.bot_protection_detected,
                )
            return

        logger.info(f"\n[SUCCESS] Scraped Product:")
        logger.info(f"  Title: {scraped_product.title}")
        logger.info(f"  Price: {scraped_product.price} {scraped_product.currency}")
        logger.info(f"  Shipping Providers: {len(scraped_product.shipping_providers)}")

        # STEP 3: ETL Processing (ETL Service)
        # Future: Consumes from 'scraped-products', publishes ProcessedProduct to 'processed-products'
        logger.info("\n" + "=" * 70)
        logger.info("STEP 3: ETL Processing & Storage")
        logger.info("=" * 70)

        async with get_async_db() as db:
            etl = ETLService()

            # Save and emit processed product
            processed_product: ProcessedProduct = await etl.save_and_emit(scraped_product)

            if processed_product:
                logger.info(f"[SUCCESS] Product saved to database (ID: {processed_product.product_id})")
                logger.info(f"  Is New: {processed_product.is_new}")
                logger.info(f"  Processed At: {processed_product.processed_at}")

                # Future: Publish to Kafka topic 'processed-products'
                # await kafka_producer.send('processed-products', processed_product.model_dump_json())

            # Save scraper log
            completed_at = datetime.now()
            duration = (completed_at - started_at).total_seconds()

            await etl.save_scraper_log(
                website=source_name,
                status="success",
                started_at=started_at,
                completed_at=completed_at,
                products_scraped=1 if processed_product else 0,
                robots_txt_allowed=analysis.robots_txt_allowed,
                robots_txt_message=analysis.robots_txt_message,
                bot_protection_detected=analysis.bot_protection_detected,
                protection_types=", ".join(analysis.protection_types) if analysis.protection_types else None,
                protection_confidence=analysis.protection_confidence,
                crawl_delay=analysis.crawl_delay,
            )

        logger.info("\n" + "=" * 70)
        logger.info(f"[COMPLETE] Pipeline Complete! Duration: {duration:.2f}s")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"[ERROR] Error in pipeline: {e}")

        # Save error log
        try:
            async with get_async_db() as db:
                etl = ETLService()
                await etl.save_scraper_log(
                    website=source_name,
                    status="failure",
                    started_at=started_at,
                    completed_at=datetime.now(),
                    error_message=str(e),
                    products_scraped=0,
                )
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


def main():
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
