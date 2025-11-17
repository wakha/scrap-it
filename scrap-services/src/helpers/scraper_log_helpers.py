"""Helper functions for scraper logging operations."""
from datetime import datetime
from typing import Optional
from src.services.etl_service import ETLService
from src.database.config import get_async_db
from src.constants import STATUS_BLOCKED, STATUS_SKIPPED, STATUS_FAILURE


async def save_blocked_log(
    source_name: str,
    started_at: datetime,
    analysis_result,
    error_msg: str
) -> None:
    """Save log entry for blocked scraping attempts.

    Args:
        source_name: Website source name
        started_at: When scraping started
        analysis_result: The analysis result object
        error_msg: Error message describing why blocked
    """
    async with get_async_db() as db:
        etl = ETLService()
        await etl.save_scraper_log(
            website=source_name,
            status=STATUS_BLOCKED,
            started_at=started_at,
            completed_at=datetime.now(),
            error_message=error_msg,
            products_scraped=0,
            robots_txt_allowed=analysis_result.robots_txt_allowed,
            robots_txt_message=analysis_result.robots_txt_message,
            bot_protection_detected=analysis_result.bot_protection_detected,
            protection_types=", ".join(analysis_result.protection_types),
            protection_confidence=analysis_result.protection_confidence,
            crawl_delay=analysis_result.crawl_delay,
        )


async def save_failure_log(
    source_name: str,
    started_at: datetime,
    error_msg: str,
    robots_txt_allowed: bool = True,
    bot_protection_detected: bool = False
) -> None:
    """Save log entry for failed scraping attempts.

    Args:
        source_name: Website source name
        started_at: When scraping started
        error_msg: Error message describing the failure
        robots_txt_allowed: Whether robots.txt allows scraping
        bot_protection_detected: Whether bot protection was detected
    """
    async with get_async_db() as db:
        etl = ETLService()
        await etl.save_scraper_log(
            website=source_name,
            status=STATUS_FAILURE,
            started_at=started_at,
            completed_at=datetime.now(),
            error_message=error_msg,
            products_scraped=0,
            robots_txt_allowed=robots_txt_allowed,
            bot_protection_detected=bot_protection_detected,
        )


async def save_success_log(
    source_name: str,
    started_at: datetime,
    analysis_result,
    products_scraped: int = 1
) -> None:
    """Save log entry for successful scraping.

    Args:
        source_name: Website source name
        started_at: When scraping started
        analysis_result: The analysis result object
        products_scraped: Number of products successfully scraped
    """
    completed_at = datetime.now()
    async with get_async_db() as db:
        etl = ETLService()
        await etl.save_scraper_log(
            website=source_name,
            status="success",
            started_at=started_at,
            completed_at=completed_at,
            products_scraped=products_scraped,
            robots_txt_allowed=analysis_result.robots_txt_allowed,
            robots_txt_message=analysis_result.robots_txt_message,
            bot_protection_detected=analysis_result.bot_protection_detected,
            protection_types=(
                ", ".join(analysis_result.protection_types)
                if analysis_result.protection_types
                else None
            ),
            protection_confidence=analysis_result.protection_confidence,
            crawl_delay=analysis_result.crawl_delay,
        )


def determine_blocking_status(analysis_result) -> tuple[str, str]:
    """Determine status and error message when scraping is blocked.

    Args:
        analysis_result: The analysis result object

    Returns:
        Tuple of (status, error_message)
    """
    if analysis_result.bot_protection_detected:
        status = STATUS_BLOCKED
        error_msg = f"Bot protection detected: {', '.join(analysis_result.protection_types)}"
    elif not analysis_result.robots_txt_allowed:
        status = STATUS_SKIPPED
        error_msg = "robots.txt disallows scraping"
    elif not analysis_result.product_url:
        status = STATUS_FAILURE
        error_msg = "Could not discover any products"
    else:
        status = STATUS_FAILURE
        error_msg = "Website analysis failed"

    return status, error_msg
