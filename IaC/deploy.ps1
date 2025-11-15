# PowerShell Deployment Script for Scrap-It Infrastructure

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('dev', 'staging', 'prod')]
    [string]$Environment,
    
    [Parameter(Mandatory=$false)]
    [string]$Location = 'eastus',
    
    [Parameter(Mandatory=$true)]
    [SecureString]$MysqlPassword,
    
    [Parameter(Mandatory=$false)]
    [string]$SubscriptionId,
    
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroupName = "rg-scrap-it-$Environment",
    
    [Parameter(Mandatory=$false)]
    [string]$StorageAccountName = "stscrapit$Environment$(Get-Random -Minimum 100 -Maximum 999)",
    
    [Parameter(Mandatory=$false)]
    [string]$ContainerRegistryName = "acrscrapit$Environment$(Get-Random -Minimum 100 -Maximum 999)",
    
    [Parameter(Mandatory=$false)]
    [string]$VNetName = "vnet-scrap-it-$Environment",
    
    [Parameter(Mandatory=$false)]
    [string]$KeyVaultName = "kv-scrapit$Environment$(Get-Random -Minimum 100 -Maximum 999)",
    
    [Parameter(Mandatory=$true)]
    [string]$KeyVaultAccessObjectId
)

# Set error action preference
$ErrorActionPreference = 'Stop'

Write-Host "Starting Scrap-It Infrastructure Deployment (Private Networking)" -ForegroundColor Cyan
Write-Host "Environment: $Environment" -ForegroundColor Yellow
Write-Host "Location: $Location" -ForegroundColor Yellow

# Set subscription if provided
if ($SubscriptionId) {
    Write-Host "Setting subscription: $SubscriptionId" -ForegroundColor Green
    az account set --subscription $SubscriptionId
}

# Get current subscription
$currentSub = az account show --query name -o tsv
Write-Host "Using subscription: $currentSub" -ForegroundColor Green

# Convert SecureString to plain text for deployment
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($MysqlPassword)
$plainPassword = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)

# Validate Bicep files
Write-Host ""
Write-Host "Validating Bicep templates..." -ForegroundColor Cyan
az bicep build --file main.bicep

if ($LASTEXITCODE -ne 0) {
    Write-Error "Bicep validation failed!"
    exit 1
}

Write-Host "Bicep templates are valid" -ForegroundColor Green

# Deploy infrastructure
Write-Host ""
Write-Host "Deploying infrastructure..." -ForegroundColor Cyan

$deploymentName = "scrap-it-deployment-$(Get-Date -Format 'yyyyMMddHHmmss')"

az deployment sub create `
    --name $deploymentName `
    --location $Location `
    --template-file main.bicep `
    --parameters resourceGroupName=$ResourceGroupName `
    --parameters location=$Location `
    --parameters environment=$Environment `
    --parameters mysqlAdminUsername='sqladmin' `
    --parameters mysqlAdminPassword="$plainPassword" `
    --parameters storageAccountName=$StorageAccountName `
    --parameters containerRegistryName=$ContainerRegistryName `
    --parameters appInsightsName="appi-scrap-it-$Environment" `
    --parameters logAnalyticsWorkspaceName="law-scrap-it-$Environment" `
    --parameters containerAppEnvironmentName="cae-scrap-it-$Environment" `
    --parameters containerAppName="ca-scrap-services-$Environment" `
    --parameters vnetName=$VNetName `
    --parameters keyVaultName=$KeyVaultName `
    --parameters keyVaultAccessObjectId=$KeyVaultAccessObjectId `
    --verbose

if ($LASTEXITCODE -ne 0) {
    Write-Error "Deployment failed!"
    exit 1
}

Write-Host ""
Write-Host "Deployment completed successfully!" -ForegroundColor Green

# Get deployment outputs
Write-Host ""
Write-Host "Deployment Outputs:" -ForegroundColor Cyan

$outputs = az deployment sub show `
    --name $deploymentName `
    --query properties.outputs `
    -o json | ConvertFrom-Json

Write-Host "Resource Group: $($outputs.resourceGroupName.value)" -ForegroundColor Yellow
Write-Host "VNet: $($outputs.vnetName.value)" -ForegroundColor Yellow
Write-Host "MySQL Server FQDN: $($outputs.mysqlServerFqdn.value) (Private)" -ForegroundColor Yellow
Write-Host "Storage Account: $($outputs.storageAccountName.value) (Private)" -ForegroundColor Yellow
Write-Host "Key Vault: $($outputs.keyVaultName.value) (Private)" -ForegroundColor Yellow
Write-Host "Key Vault URI: $($outputs.keyVaultUri.value)" -ForegroundColor Yellow
Write-Host "Container Registry: $($outputs.containerRegistryLoginServer.value) (Private)" -ForegroundColor Yellow
Write-Host "Container App URL: https://$($outputs.containerAppFqdn.value) (Internal)" -ForegroundColor Yellow

# Save outputs to file
$outputsFile = "deployment-outputs-$Environment.json"
$outputs | ConvertTo-Json -Depth 10 | Out-File $outputsFile
Write-Host ""
Write-Host "Outputs saved to: $outputsFile" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "1. All resources are in a private network - no public access" -ForegroundColor White
Write-Host "2. Access resources via VPN, Bastion, or VNet peering" -ForegroundColor White
Write-Host "3. Store secrets in Key Vault: $KeyVaultName" -ForegroundColor White
Write-Host "4. Build and push Docker image to private ACR" -ForegroundColor White
Write-Host "5. Container App is internal - accessible only within VNet" -ForegroundColor White
Write-Host ""
Write-Host "Deployment Complete!" -ForegroundColor Green
