// Virtual Network Module
@description('Location for the VNet')
param location string

@description('Tags for the resource')
param tags object

@description('VNet name')
param vnetName string

@description('Environment name')
param environment string

@description('VNet address prefix')
param vnetAddressPrefix string = '10.0.0.0/16'

@description('Subnet configurations')
param subnets array = [
  {
    name: 'snet-mysql'
    addressPrefix: '10.0.1.0/24'
    delegations: [
      {
        name: 'Microsoft.DBforMySQL/flexibleServers'
        properties: {
          serviceName: 'Microsoft.DBforMySQL/flexibleServers'
        }
      }
    ]
  }
  {
    name: 'snet-containerapp'
    addressPrefix: '10.0.2.0/23'
  }
  {
    name: 'snet-privateendpoints'
    addressPrefix: '10.0.4.0/24'
    privateEndpointNetworkPolicies: 'Disabled'
  }
]

// Virtual Network
resource vnet 'Microsoft.Network/virtualNetworks@2023-09-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
    subnets: [for subnet in subnets: {
      name: subnet.name
      properties: {
        addressPrefix: subnet.addressPrefix
        delegations: contains(subnet, 'delegations') ? subnet.delegations : []
        privateEndpointNetworkPolicies: contains(subnet, 'privateEndpointNetworkPolicies') ? subnet.privateEndpointNetworkPolicies : 'Enabled'
      }
    }]
  }
}

output vnetId string = vnet.id
output vnetName string = vnet.name
output mysqlSubnetId string = vnet.properties.subnets[0].id
output containerAppSubnetId string = vnet.properties.subnets[1].id
output privateEndpointSubnetId string = vnet.properties.subnets[2].id
