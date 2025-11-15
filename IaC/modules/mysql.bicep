// MySQL Flexible Server Module
@description('Location for the MySQL server')
param location string

@description('Tags for the resource')
param tags object

@description('MySQL administrator login name')
@secure()
param administratorLogin string

@description('MySQL administrator password')
@secure()
param administratorLoginPassword string

@description('Database name')
param databaseName string

@description('Environment name')
param environment string

@description('MySQL server name')
param serverName string = 'mysql-scrap-it-${environment}-${uniqueString(resourceGroup().id)}'

@description('MySQL version')
param mysqlVersion string = '8.0.21'

@description('Server SKU')
param skuName string = 'Standard_B1ms'

@description('Server tier')
param skuTier string = 'Burstable'

@description('Storage size in GB')
param storageSizeGB int = 20

@description('Backup retention days')
param backupRetentionDays int = 7

@description('Subnet ID for MySQL delegation')
param delegatedSubnetId string

@description('Private DNS zone ID for MySQL')
param privateDnsZoneId string

// MySQL Flexible Server
resource mysqlServer 'Microsoft.DBforMySQL/flexibleServers@2023-12-30' = {
  name: serverName
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorLoginPassword
    version: mysqlVersion
    storage: {
      storageSizeGB: storageSizeGB
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: backupRetentionDays
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      delegatedSubnetResourceId: delegatedSubnetId
      privateDnsZoneResourceId: privateDnsZoneId
    }
  }
}

// MySQL Database
resource database 'Microsoft.DBforMySQL/flexibleServers/databases@2023-12-30' = {
  parent: mysqlServer
  name: databaseName
  properties: {
    charset: 'utf8mb4'
    collation: 'utf8mb4_unicode_ci'
  }
}

output serverId string = mysqlServer.id
output serverName string = mysqlServer.name
output serverFqdn string = mysqlServer.properties.fullyQualifiedDomainName
output databaseName string = database.name
