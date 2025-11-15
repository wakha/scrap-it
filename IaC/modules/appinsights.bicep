// Application Insights Module
@description('Location for App Insights')
param location string

@description('Tags for the resource')
param tags object

@description('Application Insights name')
param appInsightsName string

@description('Log Analytics workspace resource ID')
param logAnalyticsWorkspaceId string

@description('Environment name')
param environment string

@description('Application type')
param applicationType string = 'web'

// Application Insights
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  tags: tags
  kind: applicationType
  properties: {
    Application_Type: applicationType
    WorkspaceResourceId: logAnalyticsWorkspaceId
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

output appInsightsId string = appInsights.id
output appInsightsName string = appInsights.name
output instrumentationKey string = appInsights.properties.InstrumentationKey
output connectionString string = appInsights.properties.ConnectionString
