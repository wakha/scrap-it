"""Scraper Service - Microservice Entry Point

This service:
1. Consumes AnalysisResult from Kafka 'analysis-results' topic
2. Scrapes product data based on analysis
3. Publishes ScrapedProduct to Kafka 'scraped-products' topic
4. Exposes Prometheus metrics
"""
import os
import sys
import logging
from datetime import datetime
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables only when running locally (not in Docker)
if not os.getenv('RUNNING_IN_DOCKER'):
    env_path = Path(__file__).parent.parent / '.env'
    env_local_path = Path(__file__).parent.parent / '.env.local'
    
    if env_local_path.exists():
        load_dotenv(dotenv_path=env_local_path, override=True)
    elif env_path.exists():
        load_dotenv(dotenv_path=env_path)

# Add parent directory to path for shared imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.schemas import AnalysisResult, ScrapedProduct
from shared.kafka_client import KafkaProducerClient, KafkaConsumerClient
from shared.metrics import (
    messages_consumed, messages_produced, message_processing_duration,
    websites_scraped, products_discovered, start_metrics_server
)
from scraper import ScraperService

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_INPUT_TOPIC = 'analysis-results'
KAFKA_OUTPUT_TOPIC = 'scraped-products'
CONSUMER_GROUP = 'scraper-service-group'
SERVICE_NAME = 'scraper-service'
METRICS_PORT = int(os.getenv('METRICS_PORT', '9002'))

# Headless mode and screenshot settings
HEADLESS_MODE = os.getenv('HEADLESS_MODE', 'True').lower() not in ('false', '0', 'no', 'off')
SCREENSHOT_ENABLED = os.getenv('SCREENSHOT_ENABLED', 'False').lower() in ('true', '1', 'yes', 'on')

# Kafka clients (module-level)
kafka_producer: Optional[KafkaProducerClient] = None


def process_analysis_message(message: dict) -> bool:
    """Process analysis result message and scrape product.
    
    Args:
        message: Analysis result message from Kafka
        
    Returns:
        True if processing successful, False otherwise
    """
    start_time = datetime.now()
    request_id = message.get('request_id', 'unknown')
    
    try:
        # Parse message to AnalysisResult
        analysis = AnalysisResult(**message)
        
        logger.info(
            f"[{request_id}] Processing analysis for {analysis.domain} - "
            f"can_scrape: {analysis.can_scrape}"
        )
        
        # Skip if cannot scrape
        if not analysis.can_scrape:
            logger.warning(f"[{request_id}] Skipping - website cannot be scraped")
            websites_scraped.labels(
                service=SERVICE_NAME,
                status='skipped'
            ).inc()
            return True  # Successfully processed (but skipped)
        
        # Scrape the product
        import asyncio
        scraped_product = asyncio.run(scrape_product(analysis, request_id))
        
        if scraped_product:
            # Add request ID for tracing
            scraped_product.request_id = request_id
            
            # Publish to Kafka
            message_dict = scraped_product.model_dump(mode='json')
            success = kafka_producer.send(
                topic=KAFKA_OUTPUT_TOPIC,
                message=message_dict,
                key=scraped_product.source_website
            )
            
            if success:
                messages_produced.labels(
                    service=SERVICE_NAME,
                    topic=KAFKA_OUTPUT_TOPIC
                ).inc()
                
                websites_scraped.labels(
                    service=SERVICE_NAME,
                    status='success'
                ).inc()
                
                products_discovered.labels(service=SERVICE_NAME).inc()
                
                duration = (datetime.now() - start_time).total_seconds()
                logger.info(
                    f"[{request_id}] Scraping complete - "
                    f"title: {scraped_product.title[:50]}, duration: {duration:.2f}s"
                )
                return True
            else:
                logger.error(f"[{request_id}] Failed to publish scraped product to Kafka")
                return False
        else:
            logger.error(f"[{request_id}] Scraping failed - no product data extracted")
            websites_scraped.labels(
                service=SERVICE_NAME,
                status='failed'
            ).inc()
            return False
            
    except Exception as e:
        logger.error(f"[{request_id}] Error processing message: {e}", exc_info=True)
        websites_scraped.labels(
            service=SERVICE_NAME,
            status='error'
        ).inc()
        return False
    finally:
        # Record processing duration
        duration = (datetime.now() - start_time).total_seconds()
        message_processing_duration.labels(
            service=SERVICE_NAME,
            topic=KAFKA_INPUT_TOPIC
        ).observe(duration)


async def scrape_product(analysis: AnalysisResult, request_id: str) -> Optional[ScrapedProduct]:
    """Scrape product using analysis results.
    
    Args:
        analysis: Website analysis result
        request_id: Request ID for tracing
        
    Returns:
        Scraped product or None if failed
    """
    try:
        async with ScraperService(
            headless=HEADLESS_MODE,
            screenshot=SCREENSHOT_ENABLED
        ) as scraper:
            scraped_product: ScrapedProduct = await scraper.scrape(analysis)
            return scraped_product
            
    except Exception as e:
        logger.error(f"[{request_id}] Scraping error: {e}", exc_info=True)
        return None


def main():
    """Main entry point for scraper service."""
    global kafka_producer
    
    logger.info(f"Starting {SERVICE_NAME}")
    logger.info(f"Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Consuming from: {KAFKA_INPUT_TOPIC}")
    logger.info(f"Producing to: {KAFKA_OUTPUT_TOPIC}")
    logger.info(f"Headless: {HEADLESS_MODE}, Screenshot: {SCREENSHOT_ENABLED}")
    
    try:
        # Start metrics server
        start_metrics_server(METRICS_PORT)
        logger.info(f"Metrics server started on port {METRICS_PORT}")
        
        # Initialize Kafka producer
        kafka_producer = KafkaProducerClient(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            client_id=f"{SERVICE_NAME}-producer"
        )
        
        # Initialize Kafka consumer
        kafka_consumer = KafkaConsumerClient(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            group_id=CONSUMER_GROUP,
            topics=[KAFKA_INPUT_TOPIC],
            client_id=f"{SERVICE_NAME}-consumer",
            auto_offset_reset='earliest'
        )
        
        # Start consuming messages
        logger.info(f"{SERVICE_NAME} ready - waiting for messages...")
        kafka_consumer.consume(handler=process_analysis_message)
        
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.error(f"Service error: {e}", exc_info=True)
    finally:
        if kafka_producer:
            kafka_producer.close()
        logger.info(f"{SERVICE_NAME} shutdown complete")


if __name__ == "__main__":
    main()
