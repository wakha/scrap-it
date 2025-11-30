# Web Scraper Microservices - AKS Deployment Guide

## Architecture Overview

This is a complete microservices implementation of the web scraping system, designed for deployment on Azure Kubernetes Service (AKS).

### Services Architecture

```
                    ┌─────────────────┐
                    │   API Gateway   │ (External Entry Point)
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Analyzer       │
                    │  Service        │
                    └────────┬────────┘
                             │ Kafka: analysis-results
                    ┌────────▼────────┐
                    │  Scraper        │
                    │  Service (×3)   │
                    └────────┬────────┘
                             │ Kafka: scraped-products
                    ┌────────▼────────┐
                    │  ETL Service    │
                    │  + MySQL DB     │
                    └────────┬────────┘
                             │ Kafka: processed-products
                    ┌────────▼────────┐
                    │  Downstream     │
                    │  Consumers      │
                    └─────────────────┘

    Monitoring: Prometheus + Grafana
    Message Broker: Kafka + Zookeeper
```

### Key Features

✅ **True Microservices**: Each service runs independently with network communication  
✅ **Kafka Messaging**: Async communication between services  
✅ **Database per Service**: ETL service owns MySQL database  
✅ **Horizontal Scaling**: Independent scaling of each service  
✅ **Prometheus Metrics**: Real-time monitoring of all services  
✅ **Grafana Dashboards**: Visual monitoring and alerting  
✅ **Health Checks**: Kubernetes liveness/readiness probes  
✅ **Auto-scaling**: HPA for dynamic resource allocation  

## Prerequisites

### Local Development
- Docker Desktop
- Docker Compose
- Python 3.11+

### AKS Deployment
- Azure CLI (`az`)
- kubectl
- Azure Container Registry (ACR)
- Active Azure subscription

## Quick Start - Local Development

### 1. Configure Environment Variables

```bash
cd microservices

# Copy example env file and customize
cp .env.example .env

# Edit .env with your local values
# Important: Never commit .env to Git!
```

### 2. Start All Services with Docker Compose

```bash
# Build and start all services
docker-compose up --build

# Or run in detached mode
docker-compose up -d --build
```

### 3. Verify Services are Running

```bash
# Check all containers
docker-compose ps

# View logs
docker-compose logs -f analyzer-service
docker-compose logs -f scraper-service
docker-compose logs -f etl-service
```

### 3. Test the API

```bash
# Initiate a scrape
curl -X POST http://localhost:8000/api/v1/scrape \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key-12345" \
  -d '{
    "url": "http://books.toscrape.com",
    "auto_discover": true
  }'
```

### 4. Access Monitoring

- **API Gateway**: http://localhost:8000
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin123)

### Services Metrics Endpoints
- API Gateway: http://localhost:9000/metrics
- Analyzer: http://localhost:9001/metrics
- Scraper: http://localhost:9002/metrics
- ETL: http://localhost:9003/metrics

## AKS Deployment

### Step 1: Create Azure Resources

```bash
# Set variables
RESOURCE_GROUP="scraper-microservices-rg"
LOCATION="eastus"
AKS_CLUSTER="scraper-aks-cluster"
ACR_NAME="scrapermicroservicesacr"  # Must be globally unique

# Login to Azure
az login

# Create resource group
az group create --name $RESOURCE_GROUP --location $LOCATION

# Create Azure Container Registry
az acr create \
  --resource-group $RESOURCE_GROUP \
  --name $ACR_NAME \
  --sku Standard

# Create AKS cluster with ACR integration
az aks create \
  --resource-group $RESOURCE_GROUP \
  --name $AKS_CLUSTER \
  --node-count 3 \
  --node-vm-size Standard_D4s_v3 \
  --enable-managed-identity \
  --attach-acr $ACR_NAME \
  --generate-ssh-keys

# Get AKS credentials
az aks get-credentials --resource-group $RESOURCE_GROUP --name $AKS_CLUSTER
```

### Step 2: Build and Push Docker Images

```bash
cd microservices

# Login to ACR
az acr login --name $ACR_NAME

# Build and push each service
# Analyzer Service
docker build -t $ACR_NAME.azurecr.io/analyzer-service:latest ./analyzer-service
docker push $ACR_NAME.azurecr.io/analyzer-service:latest

# Scraper Service
docker build -t $ACR_NAME.azurecr.io/scraper-service:latest ./scraper-service
docker push $ACR_NAME.azurecr.io/scraper-service:latest

# ETL Service
docker build -t $ACR_NAME.azurecr.io/etl-service:latest ./etl-service
docker push $ACR_NAME.azurecr.io/etl-service:latest

# API Gateway
docker build -t $ACR_NAME.azurecr.io/api-gateway:latest ./api-gateway
docker push $ACR_NAME.azurecr.io/api-gateway:latest
```

### Step 3: Update Kubernetes Manifests

Update image names in deployment files:

```bash
# Replace <your-acr-name> with your actual ACR name
sed -i "s/<your-acr-name>/$ACR_NAME/g" k8s/*-deployment.yaml
```

### Step 4: Deploy to AKS

```bash
cd k8s

# Create namespace
kubectl apply -f namespace.yaml

# Option 1: Use hardcoded ConfigMaps/Secrets (Development only)
kubectl apply -f configmaps-secrets.yaml

# Option 2: Use Azure Key Vault (Production - Recommended)
# See k8s/AZURE_KEYVAULT_SETUP.md for complete guide
# 1. Create Azure Key Vault
# 2. Store secrets in Key Vault
# 3. Enable CSI driver on AKS
# 4. Configure Workload Identity
# 5. Apply Key Vault integration
kubectl apply -f azure-keyvault-integration.yaml
kubectl apply -f etl-deployment-keyvault.yaml
kubectl apply -f api-gateway-deployment-keyvault.yaml

# Deploy infrastructure (Zookeeper, Kafka, MySQL)
kubectl apply -f kafka-deployment.yaml
kubectl apply -f mysql-deployment.yaml

# Wait for infrastructure to be ready
kubectl wait --for=condition=ready pod -l app=kafka -n scraper-microservices --timeout=300s
kubectl wait --for=condition=ready pod -l app=mysql -n scraper-microservices --timeout=300s

# Deploy microservices
kubectl apply -f analyzer-deployment.yaml
kubectl apply -f scraper-deployment.yaml
kubectl apply -f etl-deployment.yaml
kubectl apply -f api-gateway-deployment.yaml

# Deploy monitoring
kubectl apply -f prometheus-deployment.yaml
kubectl apply -f grafana-deployment.yaml
```

### Step 5: Verify Deployment

```bash
# Check all pods
kubectl get pods -n scraper-microservices

# Check services
kubectl get svc -n scraper-microservices

# Get external IP for API Gateway
kubectl get svc api-gateway -n scraper-microservices

# View logs
kubectl logs -f deployment/analyzer-service -n scraper-microservices
kubectl logs -f deployment/scraper-service -n scraper-microservices
kubectl logs -f deployment/etl-service -n scraper-microservices
```

### Step 6: Access Services

```bash
# Get external IPs
API_GATEWAY_IP=$(kubectl get svc api-gateway -n scraper-microservices -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
PROMETHEUS_IP=$(kubectl get svc prometheus -n scraper-microservices -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
GRAFANA_IP=$(kubectl get svc grafana -n scraper-microservices -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

echo "API Gateway: http://$API_GATEWAY_IP"
echo "Prometheus: http://$PROMETHEUS_IP:9090"
echo "Grafana: http://$GRAFANA_IP:3000"

# Test API
curl -X POST http://$API_GATEWAY_IP/api/v1/scrape \
  -H "Content-Type: application/json" \
  -H "X-API-Key: production-api-key-change-me" \
  -d '{
    "url": "http://books.toscrape.com",
    "auto_discover": true
  }'
```

## Scaling Services

```bash
# Scale scraper service for high load
kubectl scale deployment scraper-service --replicas=10 -n scraper-microservices

# Auto-scaling is already configured via HPA
kubectl get hpa -n scraper-microservices

# View current scaling status
kubectl describe hpa scraper-service-hpa -n scraper-microservices
```

## Monitoring

### Prometheus Queries

Access Prometheus at the external IP and try these queries:

- **Total messages produced**: `kafka_messages_produced_total`
- **Message processing duration**: `message_processing_duration_seconds`
- **Service request rate**: `rate(service_requests_total[5m])`
- **Active tasks**: `active_tasks`

### Grafana Dashboards

1. Access Grafana (admin/admin123)
2. Add Prometheus datasource (already configured)
3. Import dashboards:
   - Kubernetes Cluster Monitoring
   - Kafka Metrics
   - Service-specific dashboards

## Troubleshooting

### Check Pod Status
```bash
kubectl get pods -n scraper-microservices
kubectl describe pod <pod-name> -n scraper-microservices
```

### View Logs
```bash
kubectl logs -f <pod-name> -n scraper-microservices
kubectl logs -f deployment/scraper-service -n scraper-microservices --all-containers
```

### Check Kafka Topics
```bash
# Exec into Kafka pod
kubectl exec -it deployment/kafka -n scraper-microservices -- bash

# List topics
kafka-topics --list --bootstrap-server localhost:9092

# View messages
kafka-console-consumer --bootstrap-server localhost:9092 --topic analysis-results --from-beginning
```

### Database Access
```bash
# Port forward MySQL
kubectl port-forward svc/mysql 3306:3306 -n scraper-microservices

# Connect from local machine
mysql -h 127.0.0.1 -u scraper -p scraper_db
```

## Cost Optimization

### Development Environment
```bash
# Use smaller node sizes
--node-vm-size Standard_D2s_v3

# Reduce replicas
kubectl scale deployment scraper-service --replicas=1 -n scraper-microservices
```

### Production Environment
- Use Azure Spot VMs for scraper service
- Configure cluster autoscaler
- Set resource requests/limits appropriately
- Use Azure Monitor for cost tracking

## Cleanup

### Delete AKS Resources
```bash
# Delete namespace (removes all resources)
kubectl delete namespace scraper-microservices

# Or delete entire resource group
az group delete --name $RESOURCE_GROUP --yes --no-wait
```

### Local Cleanup
```bash
cd microservices
docker-compose down -v
```

## Architecture Benefits

### vs. Original Monolith

| Aspect | Monolith | Microservices |
|--------|----------|---------------|
| **Scaling** | All-or-nothing | Independent per service |
| **Deployment** | Single unit | Deploy services separately |
| **Fault Isolation** | One crash = total failure | Services continue running |
| **Technology** | Locked to Python | Can use different languages |
| **Database** | Shared schema | Database per service |
| **Team Autonomy** | Coordination required | Independent teams |

## Next Steps

1. **Configure production secrets** in Azure Key Vault
2. **Set up CI/CD** with Azure DevOps or GitHub Actions
3. **Configure ingress** controller for HTTPS
4. **Add authentication** (Azure AD, OAuth)
5. **Implement distributed tracing** (Jaeger)
6. **Set up alerting** rules in Prometheus/Grafana
7. **Configure backup** strategy for MySQL

## Support

For issues or questions:
- Check individual service README files
- Review Kubernetes events: `kubectl get events -n scraper-microservices`
- Check Prometheus metrics
- Review service logs

## License

[Your License Here]
