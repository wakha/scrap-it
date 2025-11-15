// Main Bicep file for Scrap-It Infrastructure
targetScope = 'subscription'

@description('Name of the resource group')
param resourceGroupName string

@description('Azure region for resources')
param location string = 'eastus'

@description('Environment name (dev, staging, prod)')
@allowed([
  'dev'
  'staging'
  'prod'
])
param environment string = 'dev'

@description('Tags to apply to all resources')
param tags object = {
  Environment: environment
  Project: 'scrap-it'
  ManagedBy: 'Bicep'
}

@description('MySQL Server administrator login name')
@secure()
param mysqlAdminUsername string

@description('MySQL Server administrator password')
@secure()
param mysqlAdminPassword string

@description('MySQL database name')
param mysqlDatabaseName string = 'scraper_db'

@description('Storage account name for blob storage')
@minLength(3)
@maxLength(24)
param storageAccountName string

@description('Container Registry name')
@minLength(5)
@maxLength(50)
param containerRegistryName string

@description('App Insights name')
param appInsightsName string

@description('Log Analytics Workspace name')
param logAnalyticsWorkspaceName string

@description('Container App Environment name')
param containerAppEnvironmentName string

@description('Container App name')
param containerAppName string

@description('VNet name')
param vnetName string

@description('Key Vault name')
param keyVaultName string

@description('Object ID for Key Vault access (your user/service principal)')
param keyVaultAccessObjectId string

// Create Resource Group
resource rg 'Microsoft.Resources/resourceGroups@2023-07-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

// Deploy Virtual Network
module vnet 'modules/vnet.bicep' = {
  scope: rg
  name: 'vnet-deployment'
  params: {
    location: location
    tags: tags
    vnetName: vnetName
    environment: environment
  }
}

// Deploy Private DNS Zones
module mysqlPrivateDnsZone 'modules/privatedns.bicep' = {
  scope: rg
  name: 'mysql-privatedns-deployment'
  params: {
    zoneName: 'privatelink.mysql.database.azure.com'
    tags: tags
    vnetId: vnet.outputs.vnetId
  }
}

module blobPrivateDnsZone 'modules/privatedns.bicep' = {
  scope: rg
  name: 'blob-privatedns-deployment'
  params: {
    zoneName: 'privatelink.blob.${az.environment().suffixes.storage}'
    tags: tags
    vnetId: vnet.outputs.vnetId
  }
}

module acrPrivateDnsZone 'modules/privatedns.bicep' = {
  scope: rg
  name: 'acr-privatedns-deployment'
  params: {
    zoneName: 'privatelink.azurecr.io'
    tags: tags
    vnetId: vnet.outputs.vnetId
  }
}

module keyVaultPrivateDnsZone 'modules/privatedns.bicep' = {
  scope: rg
  name: 'keyvault-privatedns-deployment'
  params: {
    zoneName: 'privatelink.vaultcore.azure.net'
    tags: tags
    vnetId: vnet.outputs.vnetId
  }
}

// Deploy MySQL Server - COMMENTED OUT DUE TO SUBSCRIPTION REGIONAL LIMITATIONS
// Uncomment when MySQL capacity is available or use external database
// module mysql 'modules/mysql.bicep' = {
//   scope: rg
//   name: 'mysql-deployment'
//   params: {
//     location: location
//     tags: tags
//     administratorLogin: mysqlAdminUsername
//     administratorLoginPassword: mysqlAdminPassword
//     databaseName: mysqlDatabaseName
//     environment: environment
//     delegatedSubnetId: vnet.outputs.mysqlSubnetId
//     privateDnsZoneId: mysqlPrivateDnsZone.outputs.privateDnsZoneId
//   }
//   dependsOn: [
//     mysqlPrivateDnsZone
//   ]
// }

// Deploy Blob Storage
module storage 'modules/storage.bicep' = {
  scope: rg
  name: 'storage-deployment'
  params: {
    location: location
    tags: tags
    storageAccountName: storageAccountName
    environment: environment
    publicNetworkAccess: 'Disabled'
  }
}

// Deploy Storage Private Endpoint
module storagePrivateEndpoint 'modules/privateendpoint.bicep' = {
  scope: rg
  name: 'storage-pe-deployment'
  params: {
    location: location
    tags: tags
    privateEndpointName: 'pe-${storageAccountName}-blob'
    subnetId: vnet.outputs.privateEndpointSubnetId
    privateLinkServiceId: storage.outputs.storageAccountId
    groupIds: ['blob']
    privateDnsZoneId: blobPrivateDnsZone.outputs.privateDnsZoneId
  }
}

// Deploy Key Vault
module keyVault 'modules/keyvault.bicep' = {
  scope: rg
  name: 'keyvault-deployment'
  params: {
    location: location
    tags: tags
    keyVaultName: keyVaultName
    environment: environment
    publicNetworkAccess: 'Disabled'
    objectId: keyVaultAccessObjectId
  }
}

// Deploy Key Vault Private Endpoint
module keyVaultPrivateEndpoint 'modules/privateendpoint.bicep' = {
  scope: rg
  name: 'keyvault-pe-deployment'
  params: {
    location: location
    tags: tags
    privateEndpointName: 'pe-${keyVaultName}'
    subnetId: vnet.outputs.privateEndpointSubnetId
    privateLinkServiceId: keyVault.outputs.keyVaultId
    groupIds: ['vault']
    privateDnsZoneId: keyVaultPrivateDnsZone.outputs.privateDnsZoneId
  }
}

// Deploy Log Analytics Workspace (required for App Insights)
module logAnalytics 'modules/loganalytics.bicep' = {
  scope: rg
  name: 'loganalytics-deployment'
  params: {
    location: location
    tags: tags
    workspaceName: logAnalyticsWorkspaceName
    environment: environment
  }
}

// Deploy App Insights
module appInsights 'modules/appinsights.bicep' = {
  scope: rg
  name: 'appinsights-deployment'
  params: {
    location: location
    tags: tags
    appInsightsName: appInsightsName
    logAnalyticsWorkspaceId: logAnalytics.outputs.workspaceId
    environment: environment
  }
}

// Deploy Container Registry
module containerRegistry 'modules/containerregistry.bicep' = {
  scope: rg
  name: 'acr-deployment'
  params: {
    location: location
    tags: tags
    containerRegistryName: containerRegistryName
    environment: environment
    publicNetworkAccess: 'Disabled'
  }
}

// Deploy ACR Private Endpoint
module acrPrivateEndpoint 'modules/privateendpoint.bicep' = {
  scope: rg
  name: 'acr-pe-deployment'
  params: {
    location: location
    tags: tags
    privateEndpointName: 'pe-${containerRegistryName}'
    subnetId: vnet.outputs.privateEndpointSubnetId
    privateLinkServiceId: containerRegistry.outputs.registryId
    groupIds: ['registry']
    privateDnsZoneId: acrPrivateDnsZone.outputs.privateDnsZoneId
  }
}

// Deploy Container App Environment
module containerAppEnv 'modules/containerappenvironment.bicep' = {
  scope: rg
  name: 'containerappenv-deployment'
  params: {
    location: location
    tags: tags
    environmentName: containerAppEnvironmentName
    logAnalyticsWorkspaceId: logAnalytics.outputs.workspaceId
    environment: environment
    subnetId: vnet.outputs.containerAppSubnetId
    internal: true
  }
}

// Deploy Container App
module containerApp 'modules/containerapp.bicep' = {
  scope: rg
  name: 'containerapp-deployment'
  params: {
    location: location
    tags: tags
    containerAppName: containerAppName
    containerAppEnvironmentId: containerAppEnv.outputs.environmentId
    containerRegistryName: containerRegistryName
    mysqlHost: 'external-mysql-host' // Configure external MySQL or add later
    mysqlDatabaseName: mysqlDatabaseName
    mysqlUsername: mysqlAdminUsername
    mysqlPassword: mysqlAdminPassword
    storageAccountName: storageAccountName
    appInsightsConnectionString: appInsights.outputs.connectionString
    environment: environment
  }
  dependsOn: [
    containerRegistry
  ]
}

// Outputs
output resourceGroupName string = rg.name
output vnetName string = vnet.outputs.vnetName
// MySQL not deployed due to subscription regional limitations
// output mysqlServerFqdn string = mysql.outputs.serverFqdn
output storageAccountName string = storage.outputs.storageAccountName
output keyVaultName string = keyVault.outputs.keyVaultName
output keyVaultUri string = keyVault.outputs.keyVaultUri
output containerRegistryLoginServer string = containerRegistry.outputs.loginServer
output containerAppFqdn string = containerApp.outputs.containerAppFqdn
output appInsightsInstrumentationKey string = appInsights.outputs.instrumentationKey
