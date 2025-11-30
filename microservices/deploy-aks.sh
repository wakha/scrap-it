#!/bin/bash

# Deployment script for AKS
# Usage: ./deploy-aks.sh <acr-name> <resource-group> <aks-cluster>

set -e

ACR_NAME=$1
RESOURCE_GROUP=$2
AKS_CLUSTER=$3

if [ -z "$ACR_NAME" ] || [ -z "$RESOURCE_GROUP" ] || [ -z "$AKS_CLUSTER" ]; then
    echo "Usage: ./deploy-aks.sh <acr-name> <resource-group> <aks-cluster>"
    echo "Example: ./deploy-aks.sh myscrapperacr scraper-rg scraper-aks"
    exit 1
fi

echo "================================================"
echo "Deploying Scraper Microservices to AKS"
echo "================================================"
echo "ACR: $ACR_NAME"
echo "Resource Group: $RESOURCE_GROUP"
echo "AKS Cluster: $AKS_CLUSTER"
echo "================================================"

# Step 1: Login to Azure
echo "Step 1: Logging in to Azure..."
az login

# Step 2: Get AKS credentials
echo "Step 2: Getting AKS credentials..."
az aks get-credentials --resource-group $RESOURCE_GROUP --name $AKS_CLUSTER --overwrite-existing

# Step 3: Login to ACR
echo "Step 3: Logging in to ACR..."
az acr login --name $ACR_NAME

# Step 4: Build and push images
echo "Step 4: Building and pushing Docker images..."

echo "  Building analyzer-service..."
docker build -t $ACR_NAME.azurecr.io/analyzer-service:latest ./analyzer-service
docker push $ACR_NAME.azurecr.io/analyzer-service:latest

echo "  Building scraper-service..."
docker build -t $ACR_NAME.azurecr.io/scraper-service:latest ./scraper-service
docker push $ACR_NAME.azurecr.io/scraper-service:latest

echo "  Building etl-service..."
docker build -t $ACR_NAME.azurecr.io/etl-service:latest ./etl-service
docker push $ACR_NAME.azurecr.io/etl-service:latest

echo "  Building api-gateway..."
docker build -t $ACR_NAME.azurecr.io/api-gateway:latest ./api-gateway
docker push $ACR_NAME.azurecr.io/api-gateway:latest

# Step 5: Update Kubernetes manifests
echo "Step 5: Updating Kubernetes manifests with ACR name..."
cd k8s
for file in *-deployment.yaml; do
    sed -i.bak "s/<your-acr-name>/$ACR_NAME/g" $file
    rm -f $file.bak
done

# Step 6: Deploy to Kubernetes
echo "Step 6: Deploying to Kubernetes..."

echo "  Creating namespace..."
kubectl apply -f namespace.yaml

echo "  Deploying ConfigMaps and Secrets..."
kubectl apply -f configmaps-secrets.yaml

echo "  Deploying Kafka infrastructure..."
kubectl apply -f kafka-deployment.yaml

echo "  Waiting for Kafka to be ready..."
kubectl wait --for=condition=ready pod -l app=kafka -n scraper-microservices --timeout=300s || true

echo "  Deploying MySQL database..."
kubectl apply -f mysql-deployment.yaml

echo "  Waiting for MySQL to be ready..."
kubectl wait --for=condition=ready pod -l app=mysql -n scraper-microservices --timeout=300s || true

echo "  Deploying microservices..."
kubectl apply -f analyzer-deployment.yaml
kubectl apply -f scraper-deployment.yaml
kubectl apply -f etl-deployment.yaml
kubectl apply -f api-gateway-deployment.yaml

echo "  Deploying monitoring stack..."
kubectl apply -f prometheus-deployment.yaml
kubectl apply -f grafana-deployment.yaml

# Step 7: Wait for deployments
echo "Step 7: Waiting for all deployments to be ready..."
kubectl wait --for=condition=available deployment --all -n scraper-microservices --timeout=600s || true

# Step 8: Display service information
echo ""
echo "================================================"
echo "Deployment Complete!"
echo "================================================"

echo ""
echo "Getting service endpoints..."
echo ""

API_GATEWAY_IP=$(kubectl get svc api-gateway -n scraper-microservices -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "pending...")
PROMETHEUS_IP=$(kubectl get svc prometheus -n scraper-microservices -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "pending...")
GRAFANA_IP=$(kubectl get svc grafana -n scraper-microservices -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "pending...")

echo "API Gateway: http://$API_GATEWAY_IP"
echo "Prometheus: http://$PROMETHEUS_IP:9090"
echo "Grafana: http://$GRAFANA_IP:3000 (admin/admin123)"
echo ""

echo "To check pod status:"
echo "  kubectl get pods -n scraper-microservices"
echo ""

echo "To view logs:"
echo "  kubectl logs -f deployment/analyzer-service -n scraper-microservices"
echo ""

echo "To test the API (once external IP is available):"
echo "  curl -X POST http://\$API_GATEWAY_IP/api/v1/scrape \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -H 'X-API-Key: production-api-key-change-me' \\"
echo "    -d '{\"url\": \"http://books.toscrape.com\", \"auto_discover\": true}'"
echo ""

echo "================================================"
echo "Note: External IPs may take a few minutes to be assigned."
echo "Run 'kubectl get svc -n scraper-microservices' to check status."
echo "================================================"
