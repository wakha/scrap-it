"""Logging configuration for the application."""
import logging
import os
from datetime import datetime
from pathlib import Path


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """
    Set up application logging.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Generate log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d")
    log_file = log_dir / f"scraper_{timestamp}.log"

    # Configure logging format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Set up root logger
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )

    # Get logger
    # pylint: disable=redefined-outer-name
    logger = logging.getLogger("scraper")
    logger.setLevel(getattr(logging, log_level.upper()))

    return logger


# Create default logger
logger = setup_logging(os.getenv("LOG_LEVEL", "INFO"))
