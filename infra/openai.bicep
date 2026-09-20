@description('Azure AI Foundry account, project, and model deployment for the interview feature.')
param name string
param location string
param tags object
param deploymentName string

@description('Foundry project name created under the account.')
param projectName string = 'hf-interview'

@description('Backing model for the interview deployment. Must support reasoning.effort and text.verbosity.')
param modelName string = 'gpt-5.6-luna'

@description('Backing model version.')
param modelVersion string = '2026-07-09'

@description('Principal id granted the Cognitive Services OpenAI User role (keyless access).')
param principalId string

// Azure AI Foundry resource: an AI Services account with project management enabled.
resource account 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: name
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: name
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-04-01-preview' = {
  parent: account
  name: projectName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: projectName
    description: 'Harness Factory interview project'
  }
}

// Model deployment is account-scoped and surfaced in the Foundry project.
// Deployment name is what the app calls; the backing model is a reasoning model
// (gpt-5.x) so the interview proposal step can use reasoning.effort and verbosity.
resource deployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: account
  name: deploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 30
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: modelVersion
    }
  }
  dependsOn: [
    project
  ]
}

var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource openAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, principalId, openAiUserRoleId)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

output endpoint string = account.properties.endpoint
output projectName string = project.name
