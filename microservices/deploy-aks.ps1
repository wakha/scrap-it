# Deployment script for AKS (PowerShell)
# Usage: .\deploy-aks.ps1 -AcrName <name> -ResourceGroup <rg> -AksCluster <cluster>

param(
    [Parameter(Mandatory=$true)]
    [string]$AcrName,
    
    [Parameter(Mandatory=$true)]
    [string]$ResourceGroup,
    
    [Parameter(Mandatory=$true)]
    [string]$AksCluster
)

$ErrorActionPreference = "Stop"

Write-Host "================================================" -ForegroundColor Green
Write-Host "Deploying Scraper Microservices to AKS" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host "ACR: $AcrName" -ForegroundColor Cyan
Write-Host "Resource Group: $ResourceGroup" -ForegroundColor Cyan
Write-Host "AKS Cluster: $AksCluster" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Green

# Step 1: Login to Azure
Write-Host "`nStep 1: Logging in to Azure..." -ForegroundColor Yellow
az login

# Step 2: Get AKS credentials
Write-Host "`nStep 2: Getting AKS credentials..." -ForegroundColor Yellow
az aks get-credentials --resource-group $ResourceGroup --name $AksCluster --overwrite-existing

# Step 3: Login to ACR
Write-Host "`nStep 3: Logging in to ACR..." -ForegroundColor Yellow
az acr login --name $AcrName

# Step 4: Build and push images
Write-Host "`nStep 4: Building and pushing Docker images..." -ForegroundColor Yellow

Write-Host "  Building analyzer-service..." -ForegroundColor Cyan
docker build -t "$AcrName.azurecr.io/analyzer-service:latest" ./analyzer-service
docker push "$AcrName.azurecr.io/analyzer-service:latest"

Write-Host "  Building scraper-service..." -ForegroundColor Cyan
docker build -t "$AcrName.azurecr.io/scraper-service:latest" ./scraper-service
docker push "$AcrName.azurecr.io/scraper-service:latest"

Write-Host "  Building etl-service..." -ForegroundColor Cyan
docker build -t "$AcrName.azurecr.io/etl-service:latest" ./etl-service
docker push "$AcrName.azurecr.io/etl-service:latest"

Write-Host "  Building api-gateway..." -ForegroundColor Cyan
docker build -t "$AcrName.azurecr.io/api-gateway:latest" ./api-gateway
docker push "$AcrName.azurecr.io/api-gateway:latest"

# Step 5: Update Kubernetes manifests
Write-Host "`nStep 5: Updating Kubernetes manifests with ACR name..." -ForegroundColor Yellow
Push-Location k8s
Get-ChildItem *-deployment.yaml | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    $content = $content -replace '<your-acr-name>', $AcrName
    Set-Content $_.FullName -Value $content
}
Pop-Location

# Step 6: Deploy to Kubernetes
Write-Host "`nStep 6: Deploying to Kubernetes..." -ForegroundColor Yellow

Write-Host "  Creating namespace..." -ForegroundColor Cyan
kubectl apply -f k8s/namespace.yaml

Write-Host "  Deploying ConfigMaps and Secrets..." -ForegroundColor Cyan
kubectl apply -f k8s/configmaps-secrets.yaml

Write-Host "  Deploying Kafka infrastructure..." -ForegroundColor Cyan
kubectl apply -f k8s/kafka-deployment.yaml

Write-Host "  Waiting for Kafka to be ready..." -ForegroundColor Cyan
Start-Sleep -Seconds 30

Write-Host "  Deploying MySQL database..." -ForegroundColor Cyan
kubectl apply -f k8s/mysql-deployment.yaml

Write-Host "  Waiting for MySQL to be ready..." -ForegroundColor Cyan
Start-Sleep -Seconds 30

Write-Host "  Deploying microservices..." -ForegroundColor Cyan
kubectl apply -f k8s/analyzer-deployment.yaml
kubectl apply -f k8s/scraper-deployment.yaml
kubectl apply -f k8s/etl-deployment.yaml
kubectl apply -f k8s/api-gateway-deployment.yaml

Write-Host "  Deploying monitoring stack..." -ForegroundColor Cyan
kubectl apply -f k8s/prometheus-deployment.yaml
kubectl apply -f k8s/grafana-deployment.yaml

# Step 7: Wait for deployments
Write-Host "`nStep 7: Waiting for deployments to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 60

# Step 8: Display service information
Write-Host "`n================================================" -ForegroundColor Green
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green

Write-Host "`nGetting service endpoints..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

$apiGatewayIp = kubectl get svc api-gateway -n scraper-microservices -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>$null
$prometheusIp = kubectl get svc prometheus -n scraper-microservices -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>$null
$grafanaIp = kubectl get svc grafana -n scraper-microservices -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>$null

if ([string]::IsNullOrEmpty($apiGatewayIp)) { $apiGatewayIp = "pending..." }
if ([string]::IsNullOrEmpty($prometheusIp)) { $prometheusIp = "pending..." }
if ([string]::IsNullOrEmpty($grafanaIp)) { $grafanaIp = "pending..." }

Write-Host "`nAPI Gateway: http://$apiGatewayIp" -ForegroundColor Cyan
Write-Host "Prometheus: http://${prometheusIp}:9090" -ForegroundColor Cyan
Write-Host "Grafana: http://${grafanaIp}:3000 (admin/admin123)" -ForegroundColor Cyan

Write-Host "`nTo check pod status:" -ForegroundColor Yellow
Write-Host "  kubectl get pods -n scraper-microservices"

Write-Host "`nTo view logs:" -ForegroundColor Yellow
Write-Host "  kubectl logs -f deployment/analyzer-service -n scraper-microservices"

Write-Host "`n================================================" -ForegroundColor Green
Write-Host "Note: External IPs may take a few minutes to be assigned." -ForegroundColor Yellow
Write-Host "Run 'kubectl get svc -n scraper-microservices' to check status." -ForegroundColor Yellow
Write-Host "================================================" -ForegroundColor Green
