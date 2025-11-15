// Container Registry Module
@description('Location for the container registry')
param location string

@description('Tags for the resource')
param tags object

@description('Container registry name')
@minLength(5)
@maxLength(50)
param containerRegistryName string

@description('Environment name')
param environment string

@description('SKU name')
param skuName string = 'Premium'

@description('Enable admin user')
param adminUserEnabled bool = true

@description('Enable public network access')
param publicNetworkAccess string = 'Disabled'

// Container Registry
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: containerRegistryName
  location: location
  tags: tags
  sku: {
    name: skuName
  }
  properties: {
    adminUserEnabled: adminUserEnabled
    publicNetworkAccess: publicNetworkAccess
    networkRuleBypassOptions: 'AzureServices'
    policies: {
      retentionPolicy: {
        days: 7
        status: 'enabled'
      }
    }
  }
}

output registryId string = containerRegistry.id
output registryName string = containerRegistry.name
output loginServer string = containerRegistry.properties.loginServer
output adminUsername string = containerRegistry.listCredentials().username
output adminPassword string = containerRegistry.listCredentials().passwords[0].value
