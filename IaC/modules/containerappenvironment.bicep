// Container App Environment Module
@description('Location for the environment')
param location string

@description('Tags for the resource')
param tags object

@description('Container App Environment name')
param environmentName string

@description('Log Analytics workspace resource ID')
param logAnalyticsWorkspaceId string

@description('Environment name')
param environment string

@description('Subnet ID for Container App Environment')
param subnetId string

@description('Enable internal load balancer')
param internal bool = true

// Get Log Analytics workspace
resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: split(logAnalyticsWorkspaceId, '/')[8]
}

// Container App Environment
resource containerAppEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsWorkspace.properties.customerId
        sharedKey: logAnalyticsWorkspace.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: subnetId
      internal: internal
    }
    zoneRedundant: false
  }
}

output environmentId string = containerAppEnvironment.id
output environmentName string = containerAppEnvironment.name
output defaultDomain string = containerAppEnvironment.properties.defaultDomain
