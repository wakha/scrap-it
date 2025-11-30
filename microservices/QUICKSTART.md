# Quick Start Guide

## Local Development (Fastest Way to Start)

### Prerequisites
- Docker Desktop installed and running
- 8GB+ RAM available

### Start Everything

```bash
cd microservices
docker-compose up -d
```

Wait 2-3 minutes for all services to start, then:

### Test the System

```bash
# Test API
curl -X POST http://localhost:8000/api/v1/scrape \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key-12345" \
  -d '{"url": "http://books.toscrape.com", "auto_discover": true}'
```

### View the Pipeline

1. **Check Prometheus metrics**: http://localhost:9090
2. **Open Grafana dashboards**: http://localhost:3000 (admin/admin123)
3. **View Kafka messages**:
   ```bash
   docker exec -it kafka kafka-console-consumer \
     --bootstrap-server localhost:9092 \
     --topic analysis-results \
     --from-beginning
   ```

### Watch It Work

```bash
# Terminal 1: Analyzer logs
docker-compose logs -f analyzer-service

# Terminal 2: Scraper logs
docker-compose logs -f scraper-service

# Terminal 3: ETL logs
docker-compose logs -f etl-service
```

You'll see:
1. Analyzer receives URL → publishes to Kafka
2. Scraper consumes from Kafka → scrapes → publishes to Kafka
3. ETL consumes from Kafka → saves to database → publishes to Kafka

### Stop Everything

```bash
docker-compose down -v
```

## Azure Deployment (Production)

### Prerequisites
- Azure CLI installed
- Active Azure subscription
- kubectl installed

### One-Command Deployment

```bash
# 1. Create Azure resources (one-time)
az group create --name scraper-rg --location eastus
az acr create --name myscrapperacr --resource-group scraper-rg --sku Standard
az aks create --name scraper-aks --resource-group scraper-rg --node-count 3 --attach-acr myscrapperacr

# 2. Deploy everything
cd microservices
./deploy-aks.ps1 -AcrName myscrapperacr -ResourceGroup scraper-rg -AksCluster scraper-aks
```

Wait 10-15 minutes for deployment to complete.

### Access Production System

```bash
# Get external IPs
kubectl get svc -n scraper-microservices

# Test API
curl -X POST http://<API-GATEWAY-IP>/api/v1/scrape \
  -H "Content-Type: application/json" \
  -H "X-API-Key: production-api-key-change-me" \
  -d '{"url": "http://books.toscrape.com", "auto_discover": true}'
```

## What You Built

### Before (Monolith)
```
Single Container
  ├── Analyzer (function)
  ├── Scraper (function)
  └── ETL (function)
```

### After (Microservices)
```
Analyzer Service (Container 1) 
  ↓ Kafka
Scraper Service (Containers 2-4) 
  ↓ Kafka
ETL Service (Container 5) → MySQL (Container 6)
  ↓ Kafka
Downstream Services
```

### Benefits You Got

✅ **Independent Scaling**: Scale scraper to 10 instances, keep analyzer at 2  
✅ **Fault Isolation**: Scraper crash ≠ analyzer crash  
✅ **Zero Downtime**: Deploy analyzer without stopping scraper  
✅ **Technology Freedom**: Can rewrite analyzer in Go, keep scraper in Python  
✅ **Team Autonomy**: Different teams can own different services  
✅ **Monitoring**: Prometheus + Grafana for all services  

## Architecture Highlights

### Database per Service Pattern
- **ETL service owns MySQL database**
- No other service can directly access it
- All data access through Kafka messages
- Prevents coupling and maintains autonomy

### Kafka Message Flow
```
analysis-results → scraped-products → processed-products
```

### Monitoring Stack
- Each service exposes Prometheus metrics
- Grafana visualizes metrics
- Health checks for Kubernetes
- Auto-scaling based on CPU/memory

## Common Tasks

### Scale a Service
```bash
kubectl scale deployment scraper-service --replicas=10 -n scraper-microservices
```

### View Logs
```bash
kubectl logs -f deployment/scraper-service -n scraper-microservices
```

### Check Kafka Topics
```bash
kubectl exec -it deployment/kafka -n scraper-microservices -- \
  kafka-topics --list --bootstrap-server localhost:9092
```

### Access Database
```bash
kubectl port-forward svc/mysql 3306:3306 -n scraper-microservices
mysql -h 127.0.0.1 -u scraper -p scraper_db
```

## Troubleshooting

### Services Not Starting
```bash
# Check pod status
kubectl get pods -n scraper-microservices

# Check specific pod
kubectl describe pod <pod-name> -n scraper-microservices

# View logs
kubectl logs <pod-name> -n scraper-microservices
```

### Kafka Connection Issues
```bash
# Check Kafka is running
kubectl get pods -l app=kafka -n scraper-microservices

# Test Kafka connectivity
kubectl exec -it deployment/kafka -n scraper-microservices -- \
  kafka-broker-api-versions --bootstrap-server localhost:9092
```

### Database Connection Issues
```bash
# Check MySQL is running
kubectl get pods -l app=mysql -n scraper-microservices

# Test connection
kubectl exec -it deployment/mysql -n scraper-microservices -- \
  mysql -u scraper -p scraper_db
```

## Next Steps

1. **Configure CI/CD**: Automate deployments with GitHub Actions
2. **Add HTTPS**: Configure ingress with TLS certificates
3. **Set up Alerts**: Create Prometheus alerting rules
4. **Implement Tracing**: Add Jaeger for distributed tracing
5. **Cost Optimization**: Use spot instances for scraper service

## Cost Estimates

### Local Development
- **Free** (uses your local machine)

### AKS Production
- **AKS Cluster**: ~$200-400/month (3 D4s_v3 nodes)
- **ACR**: ~$5/month (Standard tier)
- **Load Balancers**: ~$18/month each (3 total)
- **Storage**: ~$10/month
- **Total**: ~$250-450/month

### Cost Optimization
- Use smaller node sizes for dev
- Scale down when not in use
- Use Azure Spot VMs for scraper
- Set up budget alerts

## Support

For detailed documentation, see:
- [Main README](README.md) - Complete deployment guide
- [analyzer-service/README.md](analyzer-service/README.md)
- [scraper-service/README.md](scraper-service/README.md)
- [etl-service/README.md](etl-service/README.md)
- [api-gateway/README.md](api-gateway/README.md)
