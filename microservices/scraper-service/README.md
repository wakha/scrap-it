# Scraper Service

## Overview
Microservice responsible for scraping product data from websites based on analysis results.

## Responsibilities
- Consume AnalysisResult from Kafka topic `analysis-results`
- Scrape product information (title, price, shipping)
- Handle different website structures and checkout flows
- Publish ScrapedProduct to Kafka topic `scraped-products`
- Expose Prometheus metrics

## Message Flow
```
Kafka: analysis-results → Scraper Service → Kafka: scraped-products
```

## Environment Variables
- `KAFKA_BOOTSTRAP_SERVERS` - Kafka broker address (default: localhost:9092)
- `HEADLESS_MODE` - Run browser in headless mode (default: true)
- `SCREENSHOT_ENABLED` - Capture screenshots (default: false)
- `METRICS_PORT` - Prometheus metrics port (default: 9002)

## Metrics Exposed
- `kafka_messages_consumed_total` - Total messages consumed
- `kafka_messages_produced_total` - Total messages published
- `message_processing_duration_seconds` - Message processing time
- `websites_scraped_total` - Total websites scraped
- `products_discovered_total` - Total products discovered

## Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Run service
python main.py
```

## Docker Build
```bash
docker build -t scraper-service:latest .
```

## Kubernetes Deployment
See `k8s/scraper-deployment.yaml`

## Scaling
This service can be horizontally scaled by running multiple instances. Each instance will be part of the same Kafka consumer group and will process messages in parallel.

```bash
kubectl scale deployment scraper-service --replicas=5
```
