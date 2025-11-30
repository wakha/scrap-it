# Analyzer Service

## Overview
Microservice responsible for analyzing websites to determine scrapability, detecting bot protection, and discovering product pages.

## Responsibilities
- Receive analysis requests via HTTP API
- Analyze website structure and anti-bot measures
- Check robots.txt compliance
- Discover product pages
- Publish AnalysisResult to Kafka topic `analysis-results`
- Expose Prometheus metrics

## API Endpoints

### POST /analyze
Analyze a website and publish results to Kafka.

**Request:**
```json
{
  "url": "https://example.com",
  "product_path": "/products/item",
  "checkout_path": "/checkout",
  "auto_discover": true
}
```

**Response:**
```json
{
  "request_id": "uuid",
  "status": "success",
  "message": "Analysis published to Kafka",
  "analysis": { ... }
}
```

### GET /health
Health check endpoint for Kubernetes liveness/readiness probes.

### GET /
Service info endpoint.

## Environment Variables
- `KAFKA_BOOTSTRAP_SERVERS` - Kafka broker address (default: localhost:9092)
- `SERVICE_PORT` - HTTP service port (default: 8001)
- `METRICS_PORT` - Prometheus metrics port (default: 9001)

## Metrics Exposed
- `kafka_messages_produced_total` - Total messages published
- `service_requests_total` - Total API requests
- `service_request_duration_seconds` - Request processing time

## Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run service
python main.py
```

## Docker Build
```bash
docker build -t analyzer-service:latest .
```

## Kubernetes Deployment
See `k8s/analyzer-deployment.yaml`
