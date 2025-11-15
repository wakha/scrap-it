# Azure Infrastructure as Code - Scrap-It

This folder contains Bicep templates for deploying the Scrap-It infrastructure to Azure with **private networking** and **security best practices**.

## Resources Deployed

1. **Virtual Network (VNet)** - Private network with subnets for isolation
2. **MySQL Flexible Server** - Database with VNet integration (no public access)
3. **Blob Storage** - Storage with private endpoint (no public access)
4. **Key Vault** - Secure secrets management with private endpoint
5. **Container Registry** - Private Docker registry with private endpoint
6. **Log Analytics Workspace** - Centralized logging
7. **Application Insights** - Application monitoring and telemetry
8. **Container App Environment** - Internal load balancer in VNet
9. **Container App** - Runs the scraper service in private network
10. **Private DNS Zones** - DNS resolution for private endpoints
11. **Private Endpoints** - Secure connectivity to Azure services

## Security Architecture

### Private Networking
- **All public access disabled** on MySQL, Storage, ACR, and Key Vault
- **VNet Integration**: All resources communicate through private IPs
- **Private Endpoints**: Secure connectivity without internet exposure
- **Private DNS Zones**: Automatic DNS resolution for private resources
- **Internal Load Balancer**: Container App accessible only within VNet

### Network Topology
```
VNet (10.0.0.0/16)
├── snet-mysql (10.0.1.0/24)           - MySQL delegated subnet
├── snet-containerapp (10.0.2.0/23)    - Container Apps subnet
└── snet-privateendpoints (10.0.4.0/24) - Private endpoints subnet
```

## Prerequisites

- Azure CLI installed and logged in
- Azure subscription with Contributor role
- Bicep CLI (comes with Azure CLI)
- Your Azure AD Object ID for Key Vault access

### Get Your Object ID
```powershell
# Get your Object ID
az ad signed-in-user show --query id -o tsv
```

## File Structure

```
IaC/
├── main.bicep                          # Main orchestration file
├── main.bicepparam                     # Parameters file
├── modules/
│   ├── vnet.bicep                      # Virtual Network
│   ├── mysql.bicep                     # MySQL Flexible Server (VNet integrated)
│   ├── storage.bicep                   # Blob Storage (private)
│   ├── keyvault.bicep                  # Key Vault (private)
│   ├── loganalytics.bicep              # Log Analytics Workspace
│   ├── appinsights.bicep               # Application Insights
│   ├── containerregistry.bicep         # Container Registry (private)
│   ├── containerappenvironment.bicep   # Container App Environment (internal)
│   ├── containerapp.bicep              # Container App
│   ├── privatedns.bicep                # Private DNS Zone
│   └── privateendpoint.bicep           # Private Endpoint
└── deploy.ps1                          # Deployment script
```

## Parameters

Key parameters to configure in `main.bicepparam`:

- `resourceGroupName` - Name of the resource group
- `location` - Azure region (default: eastus)
- `environment` - dev/staging/prod
- `tags` - Resource tags
- `vnetName` - Virtual Network name
- `keyVaultName` - Key Vault name
- `keyVaultAccessObjectId` - Your Azure AD Object ID
- `mysqlAdminUsername` - MySQL admin username
- `mysqlAdminPassword` - MySQL admin password (use secure method)
- `storageAccountName` - Unique storage account name
- `containerRegistryName` - Unique ACR name

## Deployment

### Option 1: Using Azure CLI with Parameter File

```powershell
# Get your Object ID first
$objectId = az ad signed-in-user show --query id -o tsv

# Deploy to Azure
az deployment sub create `
  --location eastus `
  --template-file main.bicep `
  --parameters main.bicepparam `
  --parameters mysqlAdminPassword='YourSecurePassword!' `
  --parameters keyVaultAccessObjectId=$objectId
```

### Option 2: Using the Deployment Script

```powershell
# Get your Object ID
$objectId = az ad signed-in-user show --query id -o tsv

# Run the deployment script
.\deploy.ps1 `
  -Environment dev `
  -Location eastus `
  -MysqlPassword (ConvertTo-SecureString 'YourSecurePassword!' -AsPlainText -Force) `
  -KeyVaultAccessObjectId $objectId
```

### Option 3: Deploy with Inline Parameters

```powershell
az deployment sub create `
  --location eastus `
  --template-file main.bicep `
  --parameters resourceGroupName='rg-scrap-it-dev' `
  --parameters location='eastus' `
  --parameters environment='dev' `
  --parameters mysqlAdminUsername='sqladmin' `
  --parameters mysqlAdminPassword='YourSecurePassword!' `
  --parameters storageAccountName='stscrapitdev001' `
  --parameters containerRegistryName='acrscrapitdev001'
```

## Post-Deployment Steps

1. **Push Docker Image to ACR**
   ```powershell
   # Login to ACR
   az acr login --name acrscrapitdev001
   
   # Build and push image
   cd ../scrap-services
   docker build -t acrscrapitdev001.azurecr.io/scrap-services:latest .
   docker push acrscrapitdev001.azurecr.io/scrap-services:latest
   ```

2. **Update Container App** (if needed after initial deployment)
   ```powershell
   az containerapp update `
     --name ca-scrap-services-dev `
     --resource-group rg-scrap-it-dev `
     --image acrscrapitdev001.azurecr.io/scrap-services:latest
   ```

3. **Initialize Database Schema**
   ```powershell
   # Connect to MySQL and run init.sql
   mysql -h <server-fqdn> -u sqladmin -p scraper_db < ../scrap-services/init.sql
   ```

## Outputs

After deployment, you'll get:

- `resourceGroupName` - Resource group name
- `mysqlServerFqdn` - MySQL server FQDN
- `storageAccountName` - Storage account name
- `containerRegistryLoginServer` - ACR login server
- `containerAppFqdn` - Container App URL
- `appInsightsInstrumentationKey` - App Insights instrumentation key

## Security Best Practices

1. **Never commit passwords** - Use Azure Key Vault or secure parameter input
2. **Enable managed identities** - For Container App to access other Azure resources
3. **Use network restrictions** - Configure VNet integration for production
4. **Enable diagnostic settings** - Send logs to Log Analytics
5. **Rotate secrets regularly** - Update passwords and keys periodically

## Clean Up

```powershell
# Delete the resource group and all resources
az group delete --name rg-scrap-it-dev --yes --no-wait
```

## Cost Optimization

- Use **Burstable** tier for MySQL in dev (Standard_B1ms)
- Use **Basic** SKU for Container Registry in dev
- Configure **auto-scaling** for Container Apps
- Set **retention policies** for logs and storage

## Troubleshooting

1. **Deployment fails**: Check Azure CLI version and Bicep version
   ```powershell
   az version
   az bicep version
   ```

2. **Name conflicts**: Ensure storage and ACR names are globally unique

3. **Permission errors**: Ensure you have Contributor role on the subscription

4. **View deployment logs**:
   ```powershell
   az deployment sub show --name <deployment-name>
   ```
