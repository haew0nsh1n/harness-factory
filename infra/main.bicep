targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the azd environment; used to derive resource names and tags.')
param environmentName string

@minLength(1)
@description('Primary location for all resources.')
param location string

@description('Azure OpenAI deployment name the API calls.')
param azureOpenAiDeployment string = 'gpt-5.6-sol'

var tags = { 'azd-env-name': environmentName }
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))

resource resourceGroup 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'resources'
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    azureOpenAiDeployment: azureOpenAiDeployment
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = resourceGroup.name
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.registryLoginServer
output AZURE_CONTAINER_REGISTRY_NAME string = resources.outputs.registryName
output PORTAL_URL string = resources.outputs.portalUrl
output API_INTERNAL_FQDN string = resources.outputs.apiFqdn
