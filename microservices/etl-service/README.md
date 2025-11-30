# ETL Service

## Overview
Microservice responsible for Extract-Transform-Load operations. Owns the product database and is the **only service** that writes to it (Database per Service pattern).

## Responsibilities
- Consume ScrapedProduct from Kafka topic `scraped-products`
- Transform and validate product data
- Load data into its own MySQL database
- Detect duplicate products and price changes
- Publish ProcessedProduct to Kafka topic `processed-products`
- Expose Prometheus metrics

## Database Ownership
This service **owns** the product database. No other service should directly access this database. All data access must go through this service or via Kafka topics.

## Message Flow
```
Kafka: scraped-products → ETL Service → Database
                                     ↓
                         Kafka: processed-products
```

## Environment Variables
- `KAFKA_BOOTSTRAP_SERVERS` - Kafka broker address (default: localhost:9092)
- `DB_HOST` - Database host (default: localhost)
- `DB_PORT` - Database port (default: 3306)
- `DB_USER` - Database user (default: scraper)
- `DB_PASSWORD` - Database password (default: password)
- `DB_NAME` - Database name (default: scraper_db)
- `METRICS_PORT` - Prometheus metrics port (default: 9003)

## Metrics Exposed
- `kafka_messages_consumed_total` - Total messages consumed
- `kafka_messages_produced_total` - Total messages published
- `message_processing_duration_seconds` - Message processing time

## Database Schema
The service manages:
- `products` table - Product information
- `shipping_providers` table - Shipping provider details
- `scraper_logs` table - Execution logs

## Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set up database (see database/init.sql)
mysql -u root -p < database/init.sql

# Run service
python main.py
```

## Docker Build
```bash
docker build -t etl-service:latest .
```

## Kubernetes Deployment
See `k8s/etl-deployment.yaml`

## Retry Logic
The service implements exponential backoff for database operations to handle transient failures gracefully.

## Data Consistency
- Uses database transactions for ACID guarantees
- Manual Kafka offset commits only after successful DB writes
- Prevents data loss through at-least-once delivery semantics
