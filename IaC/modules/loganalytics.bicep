// Log Analytics Workspace Module
@description('Location for the workspace')
param location string

@description('Tags for the resource')
param tags object

@description('Log Analytics workspace name')
param workspaceName string

@description('Environment name')
param environment string

@description('SKU name')
param skuName string = 'PerGB2018'

@description('Retention in days')
param retentionInDays int = 30

// Log Analytics Workspace
resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  tags: tags
  properties: {
    sku: {
      name: skuName
    }
    retentionInDays: retentionInDays
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    workspaceCapping: {
      dailyQuotaGb: 1
    }
  }
}

output workspaceId string = logAnalyticsWorkspace.id
output workspaceName string = logAnalyticsWorkspace.name
output customerId string = logAnalyticsWorkspace.properties.customerId
