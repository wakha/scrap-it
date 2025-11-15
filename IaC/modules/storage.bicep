// Storage Account Module
@description('Location for the storage account')
param location string

@description('Tags for the resource')
param tags object

@description('Storage account name')
@minLength(3)
@maxLength(24)
param storageAccountName string

@description('Environment name')
param environment string

@description('Storage account SKU')
param skuName string = 'Standard_LRS'

@description('Storage account kind')
param kind string = 'StorageV2'

@description('Container names to create')
param containerNames array = [
  'screenshots'
  'exports'
  'logs'
]

@description('Enable public network access')
param publicNetworkAccess string = 'Disabled'

// Storage Account
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  kind: kind
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: publicNetworkAccess
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
    }
  }
}

// Blob Service
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

// Create containers
resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = [for containerName in containerNames: {
  parent: blobService
  name: containerName
  properties: {
    publicAccess: 'None'
  }
}]

output storageAccountId string = storageAccount.id
output storageAccountName string = storageAccount.name
output blobEndpoint string = storageAccount.properties.primaryEndpoints.blob
output storageAccountKey string = storageAccount.listKeys().keys[0].value
