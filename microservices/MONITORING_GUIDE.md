# Prometheus & Grafana Monitoring Guide

## Overview

Your `scrap-it` microservices project is fully instrumented with Prometheus metrics and Grafana dashboards.

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌──────────┐
│  Services   │────>│  Prometheus  │────>│ Grafana  │
│ (Metrics)   │     │  (Scraper)   │     │(Dashboards)│
└─────────────┘     └──────────────┘     └──────────┘
```

## Quick Start

### 1. Start All Services

```powershell
cd C:\Users\waqkh\OneDrive\CodingProjects\scrap-it\microservices
docker-compose up -d
```

### 2. Access Monitoring Tools

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000
  - Username: `admin`
  - Password: `admin123`

### 3. Verify Services are Running

```powershell
docker-compose ps
```

## Available Metrics

### Service Endpoints

All services expose metrics at `/metrics`:

| Service | Metrics Port | URL |
|---------|--------------|-----|
| API Gateway | 9000 | http://localhost:9000/metrics |
| Analyzer Service | 9001 | http://localhost:9001/metrics |
| Scraper Service | 9002 | http://localhost:9002/metrics |
| ETL Service | 9003 | http://localhost:9003/metrics |

### Metric Types

Your services expose these metrics (defined in `shared/metrics.py`):

#### Kafka Metrics
- `kafka_messages_produced_total` - Total messages sent to Kafka
- `kafka_messages_consumed_total` - Total messages consumed from Kafka
- `message_processing_duration_seconds` - Processing time per message

#### Service Metrics
- `service_requests_total` - Total requests by service and status
- `service_request_duration_seconds` - Request latency by operation
- `active_tasks` - Current number of active tasks

#### Scraper Metrics
- `websites_scraped_total` - Total websites scraped (success/failure)
- `products_discovered_total` - Total products found

#### System Metrics (automatically collected)
- `process_resident_memory_bytes` - Memory usage
- `process_cpu_seconds_total` - CPU usage

## Using Prometheus

### 1. Explore Metrics

Visit http://localhost:9090 and try these queries:

#### Request Rate by Service
```promql
sum(rate(service_requests_total[5m])) by (service)
```

#### Error Rate
```promql
sum(rate(service_requests_total{status="error"}[5m])) by (service)
```

#### Message Processing Latency (p95)
```promql
histogram_quantile(0.95, 
  sum(rate(message_processing_duration_seconds_bucket[5m])) by (service, le)
)
```

#### Scraping Success Rate
```promql
sum(rate(websites_scraped_total{status="success"}[5m])) 
/ 
sum(rate(websites_scraped_total[5m])) * 100
```

#### Products Discovered Rate
```promql
rate(products_discovered_total[5m])
```

#### Memory Usage by Service
```promql
process_resident_memory_bytes{job=~".*service.*"} / 1024 / 1024
```

#### Active Tasks
```promql
active_tasks
```

### 2. View Targets

Check if Prometheus is scraping your services:
- Go to http://localhost:9090/targets
- All services should show "UP" status

### 3. Check Configuration

View current config at http://localhost:9090/config

## Using Grafana

### 1. Access Dashboard

1. Open http://localhost:3000
2. Login with `admin` / `admin123`
3. Navigate to **Dashboards** → **Microservices Overview**

### 2. Pre-configured Dashboard

The dashboard includes:
- **Request Rate** - Requests per second by service
- **Latency** - p95 response time
- **Error Rate** - Errors per second with alerts
- **Success Rate** - Overall success percentage
- **Active Connections** - Service health
- **Kafka Messages** - Producer/consumer rates
- **Database Connections** - ETL service DB pool
- **Memory/CPU** - Resource usage by service

### 3. Create Custom Panels

Click **Add Panel** and use PromQL queries like:

**API Gateway Request Distribution**
```promql
sum(rate(service_requests_total{service="api-gateway"}[5m])) by (status)
```

**Scraper Performance**
```promql
rate(websites_scraped_total{service="scraper-service", status="success"}[5m])
```

**ETL Throughput**
```promql
rate(kafka_messages_consumed_total{service="etl-service"}[5m])
```

### 4. Set Up Alerts

1. Edit any panel
2. Click **Alert** tab
3. Configure conditions:

Example - High Error Rate Alert:
```
WHEN avg() OF query(A, 5m, now) IS ABOVE 0.05
```

## Monitoring Your Services

### Test the Monitoring System

#### 1. Generate API Traffic

```powershell
# Send scraping request
curl -X POST http://localhost:8000/scrape `
  -H "X-API-Key: dev-api-key-12345" `
  -H "Content-Type: application/json" `
  -d '{"url": "https://example.com", "product_name": "test"}'
```

#### 2. Watch Metrics Update

In Prometheus:
- Query: `rate(service_requests_total[1m])`
- See request count increase

In Grafana:
- Dashboard auto-refreshes every 10s
- Watch graphs update in real-time

### View Logs

```powershell
# View specific service logs
docker-compose logs -f scraper-service

# View all logs
docker-compose logs -f

# View Prometheus logs
docker-compose logs prometheus

# View Grafana logs
docker-compose logs grafana
```

## Key PromQL Queries for Your Services

### API Gateway Monitoring
```promql
# Request rate
rate(service_requests_total{service="api-gateway"}[5m])

# Average response time
rate(service_request_duration_seconds_sum{service="api-gateway"}[5m]) 
/ 
rate(service_request_duration_seconds_count{service="api-gateway"}[5m])
```

### Scraper Service Monitoring
```promql
# Scraping success rate
sum(rate(websites_scraped_total{status="success"}[5m])) 
/ 
sum(rate(websites_scraped_total[5m])) * 100

# Products per minute
rate(products_discovered_total[1m]) * 60

# Active scraping tasks
active_tasks{service="scraper-service"}
```

### ETL Service Monitoring
```promql
# Messages consumed per second
rate(kafka_messages_consumed_total{service="etl-service"}[5m])

# Processing latency
histogram_quantile(0.99, 
  sum(rate(message_processing_duration_seconds_bucket{service="etl-service"}[5m])) by (le)
)
```

### Kafka Monitoring
```promql
# Total message flow
sum(rate(kafka_messages_produced_total[5m]))
sum(rate(kafka_messages_consumed_total[5m]))

# Message lag (produced - consumed)
sum(kafka_messages_produced_total) - sum(kafka_messages_consumed_total)
```

## Troubleshooting

### Services Not Showing in Prometheus

1. Check service health:
```powershell
docker-compose ps
```

2. Verify metrics endpoint:
```powershell
curl http://localhost:9001/metrics  # Analyzer
curl http://localhost:9002/metrics  # Scraper
```

3. Check Prometheus targets:
http://localhost:9090/targets

### Grafana Dashboard Not Loading

1. Verify data source:
   - **Configuration** → **Data Sources** → **Prometheus**
   - Test connection

2. Restart Grafana:
```powershell
docker-compose restart grafana
```

### No Data in Graphs

1. Ensure services are receiving traffic
2. Check time range in Grafana (top-right)
3. Verify PromQL query in panel editor

## Advanced Features

### Export Dashboard

1. Open dashboard
2. Click **Share** → **Export**
3. Save JSON file
4. Import on another Grafana instance

### Create Alerts

Edit `monitoring/prometheus.yml` to add alert rules:

```yaml
rule_files:
  - "alerts.yml"
```

Create `monitoring/alerts.yml`:
```yaml
groups:
  - name: scraper_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(service_requests_total{status="error"}[5m]) > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate on {{ $labels.service }}"
```

### Aggregate Data from Multiple Scrapers

```promql
sum(rate(websites_scraped_total[5m])) by (status)
```

## Best Practices

1. **Monitor Key Metrics**:
   - Request rate (throughput)
   - Error rate (reliability)
   - Latency (performance)
   - Resource usage (capacity)

2. **Set Alerts** for:
   - Error rate > 5%
   - Response time > 5s
   - Memory usage > 80%
   - Service down

3. **Dashboard Organization**:
   - Create separate dashboards per service
   - Group related metrics
   - Use consistent time ranges

4. **Retention**:
   - Default: 15 days
   - Adjust in `prometheus.yml`:
   ```yaml
   command:
     - '--storage.tsdb.retention.time=30d'
   ```

## Cleanup

### Stop Services
```powershell
docker-compose down
```

### Remove Data (Reset)
```powershell
docker-compose down -v  # Removes volumes
```

### View Disk Usage
```powershell
docker system df
```

## Next Steps

1. ✅ Services are instrumented
2. ✅ Prometheus is collecting metrics
3. ✅ Grafana dashboard is configured
4. **Add custom metrics** to your services
5. **Set up alerts** for critical issues
6. **Export dashboards** for team sharing

## Resources

- Prometheus Query Language: https://prometheus.io/docs/prometheus/latest/querying/basics/
- Grafana Dashboards: https://grafana.com/grafana/dashboards/
- Your Metrics Code: `microservices/shared/metrics.py`
- Prometheus Config: `microservices/monitoring/prometheus.yml`
