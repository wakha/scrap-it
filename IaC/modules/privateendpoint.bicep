// Private Endpoint Module
@description('Location for the private endpoint')
param location string

@description('Tags for the resource')
param tags object

@description('Private endpoint name')
param privateEndpointName string

@description('Subnet ID for private endpoint')
param subnetId string

@description('Resource ID to create private endpoint for')
param privateLinkServiceId string

@description('Group IDs for the private endpoint')
param groupIds array

@description('Private DNS zone ID')
param privateDnsZoneId string

// Private Endpoint
resource privateEndpoint 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: privateEndpointName
  location: location
  tags: tags
  properties: {
    subnet: {
      id: subnetId
    }
    privateLinkServiceConnections: [
      {
        name: privateEndpointName
        properties: {
          privateLinkServiceId: privateLinkServiceId
          groupIds: groupIds
        }
      }
    ]
  }
}

// Private DNS Zone Group
resource privateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-09-01' = {
  parent: privateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'config1'
        properties: {
          privateDnsZoneId: privateDnsZoneId
        }
      }
    ]
  }
}

output privateEndpointId string = privateEndpoint.id
output privateEndpointName string = privateEndpoint.name
