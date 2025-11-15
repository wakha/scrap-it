// Key Vault Module
@description('Location for Key Vault')
param location string

@description('Tags for the resource')
param tags object

@description('Key Vault name')
param keyVaultName string

@description('Environment name')
param environment string

@description('Enable public network access')
param publicNetworkAccess string = 'Disabled'

@description('Tenant ID')
param tenantId string = subscription().tenantId

@description('Object ID of the user/service principal to grant access')
param objectId string

@description('SKU name')
param skuName string = 'standard'

// Key Vault
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: skuName
    }
    tenantId: tenantId
    publicNetworkAccess: publicNetworkAccess
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: true
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Deny'
    }
  }
}

output keyVaultId string = keyVault.id
output keyVaultName string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri
