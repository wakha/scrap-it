# Microservices Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           External Users / API Clients                       │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
                                     │ HTTPS
                                     │
                    ┌────────────────▼──────────────────┐
                    │    Azure Load Balancer            │
                    │    (External IP)                  │
                    └────────────────┬──────────────────┘
                                     │
                    ┌────────────────▼──────────────────┐
                    │    API Gateway Service            │
                    │    - Authentication               │
                    │    - Rate Limiting                │
                    │    - Request Routing              │
                    │    Port: 8000                     │
                    │    Metrics: 9000                  │
                    └────────────────┬──────────────────┘
                                     │
                                     │ HTTP
                                     │
                    ┌────────────────▼──────────────────┐
                    │    Analyzer Service               │
                    │    - Website Analysis             │
                    │    - Bot Detection                │
                    │    - Product Discovery            │
                    │    Replicas: 2-5 (Auto-scaled)   │
                    │    Port: 8001, Metrics: 9001     │
                    └────────────────┬──────────────────┘
                                     │
                                     │ Kafka Topic: analysis-results
                                     │
                    ┌────────────────▼──────────────────┐
                    │    Kafka Cluster                  │
                    │    - Message Broker               │
                    │    - Topics: 3                    │
                    │    - Partitions: Auto             │
                    │    Port: 9092                     │
                    └────────────────┬──────────────────┘
                                     │
                                     │ Kafka Topic: analysis-results
                                     │
                    ┌────────────────▼──────────────────┐
                    │    Scraper Service                │
                    │    - Product Scraping             │
                    │    - Screenshot Capture           │
                    │    - Shipping Data Extraction     │
                    │    Replicas: 3-10 (Auto-scaled)  │
                    │    Metrics: 9002                  │
                    └────────────────┬──────────────────┘
                                     │
                                     │ Kafka Topic: scraped-products
                                     │
                    ┌────────────────▼──────────────────┐
                    │    Kafka Cluster                  │
                    └────────────────┬──────────────────┘
                                     │
                                     │ Kafka Topic: scraped-products
                                     │
                    ┌────────────────▼──────────────────┐
                    │    ETL Service                    │
                    │    - Data Transformation          │
                    │    - Database Writes              │
                    │    - Duplicate Detection          │
                    │    Replicas: 2-5 (Auto-scaled)   │
                    │    Metrics: 9003                  │
                    └────────────────┬──────────────────┘
                                     │
                    ┌────────────────▼──────────────────┐
                    │    MySQL Database                 │
                    │    - Products Table               │
                    │    - Shipping Providers Table     │
                    │    - Scraper Logs Table           │
                    │    Owned by ETL Service           │
                    │    Port: 3306                     │
                    │    Storage: 20Gi Premium SSD      │
                    └───────────────────────────────────┘
                                     │
                                     │ Kafka Topic: processed-products
                                     │
                    ┌────────────────▼──────────────────┐
                    │    Downstream Consumers           │
                    │    - Analytics Service            │
                    │    - Notification Service         │
                    │    - Reporting Service            │
                    └───────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           Monitoring & Observability                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│   ┌─────────────────────┐         ┌──────────────────────┐                 │
│   │   Prometheus         │────────▶│     Grafana          │                 │
│   │   - Metrics Storage  │         │     - Dashboards     │                 │
│   │   - Alerting         │         │     - Visualization  │                 │
│   │   Port: 9090         │         │     Port: 3000       │                 │
│   └──────────┬───────────┘         └──────────────────────┘                 │
│              │                                                                │
│              │ Scrapes Metrics from All Services                             │
│              │                                                                │
│   ┌──────────▼───────────────────────────────────────────────┐              │
│   │  Service Metrics (Prometheus Format)                     │              │
│   │  - kafka_messages_produced_total                         │              │
│   │  - kafka_messages_consumed_total                         │              │
│   │  - service_requests_total                                │              │
│   │  - message_processing_duration_seconds                   │              │
│   │  - websites_scraped_total                                │              │
│   └──────────────────────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### 1. Request Initiation
```
External Client → API Gateway
  Headers: X-API-Key, Content-Type
  Body: { url, product_path, checkout_path }
```

### 2. Analysis Phase
```
API Gateway → Analyzer Service (HTTP)
  ↓
Analyzer performs:
  - robots.txt check
  - Bot protection detection
  - Product page discovery
  ↓
Publishes to Kafka: analysis-results topic
  Message: AnalysisResult (JSON)
  Key: domain
```

### 3. Scraping Phase
```
Scraper Service consumes from Kafka: analysis-results
  ↓
Scraper performs:
  - Playwright browser automation
  - Product data extraction
  - Shipping information collection
  - Screenshot capture (optional)
  ↓
Publishes to Kafka: scraped-products topic
  Message: ScrapedProduct (JSON)
  Key: source_website
```

### 4. ETL Phase
```
ETL Service consumes from Kafka: scraped-products
  ↓
ETL performs:
  - Data validation
  - Duplicate detection
  - Price change tracking
  - Database insertion
  ↓
Publishes to Kafka: processed-products topic
  Message: ProcessedProduct (JSON)
  Key: product_id
```

### 5. Storage & Downstream
```
MySQL Database (owned by ETL service)
  Tables: products, shipping_providers, scraper_logs
  ↓
Processed-products topic consumed by:
  - Analytics Service
  - Notification Service
  - Reporting Service
```

## Message Schemas

### AnalysisResult (Kafka: analysis-results)
```json
{
  "domain": "books.toscrape.com",
  "product_url": "http://books.toscrape.com/catalogue/book_1000/index.html",
  "source_website": "books.toscrape.com",
  "can_scrape": true,
  "selectors": {
    "product_title_xpath": "//h1",
    "product_price_xpath": "//p[@class='price_color']"
  },
  "robots_txt_allowed": true,
  "bot_protection_detected": false,
  "analyzed_at": "2025-11-27T10:00:00Z",
  "request_id": "uuid"
}
```

### ScrapedProduct (Kafka: scraped-products)
```json
{
  "title": "A Light in the Attic",
  "price": 51.77,
  "currency": "GBP",
  "url": "http://books.toscrape.com/catalogue/book_1000/index.html",
  "source_website": "books.toscrape.com",
  "shipping_providers": [
    {
      "name": "Standard Shipping",
      "price": 5.99,
      "currency": "GBP",
      "delivery_time": "3-5 days"
    }
  ],
  "scraped_at": "2025-11-27T10:01:00Z",
  "request_id": "uuid"
}
```

### ProcessedProduct (Kafka: processed-products)
```json
{
  "product_id": 123,
  "title": "A Light in the Attic",
  "price": 51.77,
  "currency": "GBP",
  "url": "http://books.toscrape.com/catalogue/book_1000/index.html",
  "source_website": "books.toscrape.com",
  "is_new": true,
  "is_updated": false,
  "processed_at": "2025-11-27T10:01:05Z",
  "shipping_provider_count": 1,
  "request_id": "uuid"
}
```

## Service Communication Patterns

### Synchronous Communication (HTTP)
- External Client → API Gateway
- API Gateway → Analyzer Service

### Asynchronous Communication (Kafka)
- Analyzer → Scraper (via analysis-results topic)
- Scraper → ETL (via scraped-products topic)
- ETL → Downstream (via processed-products topic)

## Deployment Topology

### Kubernetes Namespace: scraper-microservices

#### Deployments
- `api-gateway`: 2-10 replicas (HPA)
- `analyzer-service`: 2-5 replicas (HPA)
- `scraper-service`: 3-10 replicas (HPA)
- `etl-service`: 2-5 replicas (HPA)
- `kafka`: 1 replica (stateful)
- `zookeeper`: 1 replica (stateful)
- `mysql`: 1 replica (stateful)
- `prometheus`: 1 replica
- `grafana`: 1 replica

#### Services (ClusterIP)
- `api-gateway`: Port 80 (LoadBalancer)
- `analyzer-service`: Port 8001
- `scraper-service`: Port 9002 (metrics only)
- `etl-service`: Port 9003 (metrics only)
- `kafka`: Ports 9092, 9093
- `zookeeper`: Port 2181
- `mysql`: Port 3306
- `prometheus`: Port 9090 (LoadBalancer)
- `grafana`: Port 3000 (LoadBalancer)

#### Persistent Volumes
- `kafka-pvc`: 10Gi (Premium SSD)
- `mysql-pvc`: 20Gi (Premium SSD)
- `prometheus-pvc`: 50Gi (Premium SSD)
- `grafana-pvc`: 10Gi (Premium SSD)

## Scaling Strategy

### Horizontal Pod Autoscaler (HPA)

#### API Gateway
- Min: 2, Max: 10
- CPU: 70%, Memory: 80%

#### Analyzer Service
- Min: 2, Max: 5
- CPU: 70%, Memory: 80%

#### Scraper Service
- Min: 3, Max: 10
- CPU: 70%, Memory: 80%
- **Most resource-intensive** (browser automation)

#### ETL Service
- Min: 2, Max: 5
- CPU: 70%

### Manual Scaling Example
```bash
# Scale scraper for high load
kubectl scale deployment scraper-service --replicas=10 -n scraper-microservices

# Scale down for cost savings
kubectl scale deployment scraper-service --replicas=1 -n scraper-microservices
```

## Monitoring & Alerting

### Prometheus Metrics

#### Service-Level Metrics
- `service_requests_total{service, status}`
- `service_request_duration_seconds{service, operation}`

#### Kafka Metrics
- `kafka_messages_produced_total{service, topic}`
- `kafka_messages_consumed_total{service, topic}`
- `message_processing_duration_seconds{service, topic}`

#### Business Metrics
- `websites_scraped_total{service, status}`
- `products_discovered_total{service}`
- `active_tasks{service}`

### Grafana Dashboards
1. **Service Overview**: Request rates, error rates, latencies
2. **Kafka Pipeline**: Message throughput, consumer lag
3. **Resource Usage**: CPU, memory, disk per service
4. **Business Metrics**: Products scraped, success rates

## Fault Tolerance

### Service-Level
- Health checks (liveness & readiness probes)
- Automatic pod restart on failure
- Circuit breaker patterns (future)

### Message-Level
- Kafka message persistence
- At-least-once delivery semantics
- Manual offset commits after processing
- Dead letter queues (future)

### Database-Level
- Connection pooling
- Exponential backoff retry logic
- Transaction-based writes

## Security

### Network Security
- Services communicate via internal ClusterIP
- Only API Gateway, Prometheus, Grafana exposed externally
- Network policies (future)

### Authentication
- API Gateway: X-API-Key header validation
- Internal services: No auth (trusted network)
- Azure AD integration (future)

### Secrets Management
- Kubernetes secrets for sensitive data
- Azure Key Vault integration (recommended)
- Rotate secrets regularly

## Cost Optimization

### Development Environment
- Use smaller node sizes (D2s_v3)
- Reduce replica counts
- Scale to zero when not in use

### Production Environment
- Azure Spot VMs for scraper service (70% cost savings)
- Reserved instances for stable workloads
- Cluster autoscaler for dynamic node management
- Monitor costs with Azure Cost Management

## Future Enhancements

1. **Service Mesh** (Istio/Linkerd)
   - Advanced traffic management
   - mTLS between services
   - Distributed tracing

2. **API Gateway** (Azure API Management)
   - Advanced rate limiting
   - API versioning
   - Developer portal

3. **Caching Layer** (Redis)
   - Cache analysis results
   - Session management
   - Rate limit counters

4. **Event Sourcing**
   - Store all events
   - Replay capability
   - Audit trail

5. **ML Integration**
   - Price prediction models
   - Anomaly detection
   - Smart retry strategies
