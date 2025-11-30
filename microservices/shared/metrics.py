"""Prometheus metrics for monitoring microservices."""
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import logging

logger = logging.getLogger(__name__)

# Kafka metrics
messages_produced = Counter(
    'kafka_messages_produced_total',
    'Total messages produced to Kafka',
    ['service', 'topic']
)

messages_consumed = Counter(
    'kafka_messages_consumed_total',
    'Total messages consumed from Kafka',
    ['service', 'topic']
)

message_processing_duration = Histogram(
    'message_processing_duration_seconds',
    'Time spent processing messages',
    ['service', 'topic']
)

# Service-specific metrics
service_requests = Counter(
    'service_requests_total',
    'Total service requests',
    ['service', 'status']
)

service_duration = Histogram(
    'service_request_duration_seconds',
    'Service request duration',
    ['service', 'operation']
)

active_tasks = Gauge(
    'active_tasks',
    'Number of active tasks being processed',
    ['service']
)

# Scraper metrics
websites_scraped = Counter(
    'websites_scraped_total',
    'Total websites scraped',
    ['service', 'status']
)

products_discovered = Counter(
    'products_discovered_total',
    'Total products discovered',
    ['service']
)


def start_metrics_server(port: int = 8000):
    """Start Prometheus metrics HTTP server.
    
    Args:
        port: Port number for metrics endpoint
    """
    try:
        start_http_server(port)
        logger.info(f"Metrics server started on port {port}")
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")
