// Parameters file for main.bicep
using './main.bicep'

param resourceGroupName = 'rg-scrap-it-dev'
param location = 'eastus'
param environment = 'dev'

param tags = {
  Environment: 'dev'
  Project: 'scrap-it'
  ManagedBy: 'Bicep'
  CostCenter: 'Engineering'
  Owner: 'DevOps Team'
}

// MySQL Parameters
param mysqlAdminUsername = 'sqladmin'
param mysqlAdminPassword = '' // Set via Azure CLI or KeyVault reference
param mysqlDatabaseName = 'scraper_db'

// Storage Parameters
param storageAccountName = 'stscrapitdev001'

// Container Registry Parameters
param containerRegistryName = 'acrscrapitdev001'

// Monitoring Parameters
param appInsightsName = 'appi-scrap-it-dev'
param logAnalyticsWorkspaceName = 'law-scrap-it-dev'

// Container App Parameters
param containerAppEnvironmentName = 'cae-scrap-it-dev'
param containerAppName = 'ca-scrap-services-dev'

// Networking Parameters
param vnetName = 'vnet-scrap-it-dev'

// Key Vault Parameters
param keyVaultName = 'kv-scrap-it-dev-001'
param keyVaultAccessObjectId = '' // Set your Azure AD Object ID

