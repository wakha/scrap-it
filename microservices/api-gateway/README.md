# API Gateway

## Overview
Unified entry point for all microservices. Routes external requests to appropriate backend services.

## Responsibilities
- Provide unified REST API for external clients
- Route requests to analyzer, scraper, ETL services
- Handle authentication via API keys
- Rate limiting and request validation
- Expose Prometheus metrics
- CORS handling

## API Endpoints

### POST /api/v1/scrape
Initiate a scraping job.

**Headers:**
- `X-API-Key`: Your API key

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
  "status": "processing",
  "message": "Scraping job initiated"
}
```

### GET /api/v1/status/{request_id}
Get status of a scraping job (future implementation).

### GET /health
Health check endpoint.

### GET /
Service information.

## Environment Variables
- `SERVICE_PORT` - Gateway HTTP port (default: 8000)
- `METRICS_PORT` - Prometheus metrics port (default: 9000)
- `API_KEY` - API key for authentication (default: your-api-key-here)
- `ANALYZER_SERVICE_URL` - Analyzer service URL (default: http://localhost:8001)

## Metrics Exposed
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
docker build -t api-gateway:latest .
```

## Kubernetes Deployment
See `k8s/api-gateway-deployment.yaml`
