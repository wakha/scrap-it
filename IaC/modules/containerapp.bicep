// Container App Module
@description('Location for the container app')
param location string

@description('Tags for the resource')
param tags object

@description('Container App name')
param containerAppName string

@description('Container App Environment resource ID')
param containerAppEnvironmentId string

@description('Container Registry name')
param containerRegistryName string

@description('MySQL host FQDN')
param mysqlHost string

@description('MySQL database name')
param mysqlDatabaseName string

@description('MySQL username')
@secure()
param mysqlUsername string

@description('MySQL password')
@secure()
param mysqlPassword string

@description('Storage account name')
param storageAccountName string

@description('App Insights connection string')
@secure()
param appInsightsConnectionString string

@description('Environment name')
param environment string

@description('Container image name')
param containerImage string = 'scrap-services:latest'

@description('CPU cores')
param cpuCores string = '0.5'

@description('Memory size')
param memorySize string = '1Gi'

@description('Min replicas')
param minReplicas int = 1

@description('Max replicas')
param maxReplicas int = 3

// Get existing Container Registry
resource containerRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: containerRegistryName
}

// Get existing Storage Account
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageAccountName
}

// Container App
resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  tags: tags
  properties: {
    managedEnvironmentId: containerAppEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: containerRegistry.properties.loginServer
          username: containerRegistry.listCredentials().username
          passwordSecretRef: 'registry-password'
        }
      ]
      secrets: [
        {
          name: 'registry-password'
          value: containerRegistry.listCredentials().passwords[0].value
        }
        {
          name: 'mysql-password'
          value: mysqlPassword
        }
        {
          name: 'storage-key'
          value: storageAccount.listKeys().keys[0].value
        }
        {
          name: 'appinsights-connection-string'
          value: appInsightsConnectionString
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'scrap-services'
          image: '${containerRegistry.properties.loginServer}/${containerImage}'
          resources: {
            cpu: json(cpuCores)
            memory: memorySize
          }
          env: [
            {
              name: 'DB_HOST'
              value: mysqlHost
            }
            {
              name: 'DB_PORT'
              value: '3306'
            }
            {
              name: 'DB_USER'
              value: mysqlUsername
            }
            {
              name: 'DB_PASSWORD'
              secretRef: 'mysql-password'
            }
            {
              name: 'DB_NAME'
              value: mysqlDatabaseName
            }
            {
              name: 'STORAGE_ACCOUNT_NAME'
              value: storageAccountName
            }
            {
              name: 'STORAGE_ACCOUNT_KEY'
              secretRef: 'storage-key'
            }
            {
              name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
              secretRef: 'appinsights-connection-string'
            }
            {
              name: 'HEADLESS_MODE'
              value: 'true'
            }
            {
              name: 'LOG_LEVEL'
              value: 'INFO'
            }
            {
              name: 'SCREENSHOT_ENABLED'
              value: 'true'
            }
            {
              name: 'SCRAPE_DELAY'
              value: '2'
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
}

output containerAppId string = containerApp.id
output containerAppName string = containerApp.name
output containerAppFqdn string = containerApp.properties.configuration.ingress.fqdn
output latestRevisionName string = containerApp.properties.latestRevisionName
