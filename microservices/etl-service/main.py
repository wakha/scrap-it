"""ETL Service - Microservice Entry Point

This service:
1. Consumes ScrapedProduct from Kafka 'scraped-products' topic
2. Transforms and loads data into its own database
3. Publishes ProcessedProduct to Kafka 'processed-products' topic
4. Exposes Prometheus metrics
5. Owns the product database (Database per Service pattern)
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

from shared.schemas import ScrapedProduct, ProcessedProduct
from shared.kafka_client import KafkaProducerClient, KafkaConsumerClient
from shared.metrics import (
    messages_consumed, messages_produced, message_processing_duration,
    start_metrics_server
)
from etl import ETLService

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration from environment
KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
KAFKA_INPUT_TOPIC = 'scraped-products'
KAFKA_OUTPUT_TOPIC = 'processed-products'
CONSUMER_GROUP = 'etl-service-group'
SERVICE_NAME = 'etl-service'
METRICS_PORT = int(os.getenv('METRICS_PORT', '9003'))

# Database configuration (ETL service owns this database)
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '3306'))
DB_USER = os.getenv('DB_USER', 'scraper')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_NAME = os.getenv('DB_NAME', 'scraper_db')

# Kafka clients (module-level)
kafka_producer: Optional[KafkaProducerClient] = None
etl_service: Optional[ETLService] = None


def process_scraped_product_message(message: dict) -> bool:
    """Process scraped product message and save to database.
    
    Args:
        message: Scraped product message from Kafka
        
    Returns:
        True if processing successful, False otherwise
    """
    start_time = datetime.now()
    request_id = message.get('request_id', 'unknown')
    
    try:
        # Parse message to ScrapedProduct
        scraped_product = ScrapedProduct(**message)
        
        logger.info(
            f"[{request_id}] Processing product: {scraped_product.title[:50]} "
            f"from {scraped_product.source_website}"
        )
        
        # Save to database
        import asyncio
        processed_product = asyncio.run(save_product(scraped_product, request_id))
        
        if processed_product:
            # Add request ID for tracing
            processed_product.request_id = request_id
            
            # Publish to Kafka for downstream consumers
            message_dict = processed_product.model_dump(mode='json')
            success = kafka_producer.send(
                topic=KAFKA_OUTPUT_TOPIC,
                message=message_dict,
                key=str(processed_product.product_id)
            )
            
            if success:
                messages_produced.labels(
                    service=SERVICE_NAME,
                    topic=KAFKA_OUTPUT_TOPIC
                ).inc()
                
                duration = (datetime.now() - start_time).total_seconds()
                logger.info(
                    f"[{request_id}] Product saved - "
                    f"ID: {processed_product.product_id}, "
                    f"is_new: {processed_product.is_new}, "
                    f"duration: {duration:.2f}s"
                )
                return True
            else:
                logger.error(f"[{request_id}] Failed to publish processed product to Kafka")
                # Still return True since data is saved to DB
                return True
        else:
            logger.error(f"[{request_id}] Failed to save product to database")
            return False
            
    except Exception as e:
        logger.error(f"[{request_id}] Error processing message: {e}", exc_info=True)
        return False
    finally:
        # Record processing duration
        duration = (datetime.now() - start_time).total_seconds()
        message_processing_duration.labels(
            service=SERVICE_NAME,
            topic=KAFKA_INPUT_TOPIC
        ).observe(duration)
        
        # Track message consumption
        messages_consumed.labels(
            service=SERVICE_NAME,
            topic=KAFKA_INPUT_TOPIC
        ).inc()


async def save_product(scraped_product: ScrapedProduct, request_id: str) -> Optional[ProcessedProduct]:
    """Save scraped product to database.
    
    Args:
        scraped_product: Scraped product data
        request_id: Request ID for tracing
        
    Returns:
        Processed product or None if failed
    """
    try:
        processed_product = await etl_service.save_and_emit(scraped_product)
        return processed_product
    except Exception as e:
        logger.error(f"[{request_id}] ETL error: {e}", exc_info=True)
        return None


def main():
    """Main entry point for ETL service."""
    global kafka_producer, etl_service
    
    logger.info(f"Starting {SERVICE_NAME}")
    logger.info(f"Kafka: {KAFKA_BOOTSTRAP_SERVERS}")
    logger.info(f"Database: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    logger.info(f"Consuming from: {KAFKA_INPUT_TOPIC}")
    logger.info(f"Producing to: {KAFKA_OUTPUT_TOPIC}")
    
    try:
        # Start metrics server
        start_metrics_server(METRICS_PORT)
        logger.info(f"Metrics server started on port {METRICS_PORT}")
        
        # Initialize ETL service
        etl_service = ETLService()
        logger.info("ETL service initialized")
        
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
        kafka_consumer.consume(handler=process_scraped_product_message)
        
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
