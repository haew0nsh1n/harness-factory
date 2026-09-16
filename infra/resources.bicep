@description('All resources for the Harness Factory Container Apps deployment.')
param location string
param tags object
param resourceToken string

param azureOpenAiDeployment string = 'gpt-5.6-sol'

// Postgres admin password is regenerated per deployment and stored only as a
// Container App secret; it is never emitted as an output.
@secure()
param databasePassword string = newGuid()

@secure()
param portalAuthSecret string = newGuid()

var pgAdminLogin = 'hfadmin'
var pgDatabaseName = 'harness_factory'
var artifactShareName = 'artifacts'
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${resourceToken}'
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: 'acr${resourceToken}'
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${resourceToken}'
  location: location
  tags: tags
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, acrPullRoleId)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'st${resourceToken}'
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}

resource fileServices 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource artifactShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileServices
  name: artifactShareName
  properties: {
    shareQuota: 5
  }
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: 'psql-${resourceToken}'
  location: location
  tags: tags
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: pgAdminLogin
    administratorLoginPassword: databasePassword
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: {
      publicNetworkAccess: 'Enabled'
    }
  }
}

resource pgFirewallAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAllAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource pgDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: pgDatabaseName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${resourceToken}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource artifactStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: containerEnv
  name: artifactShareName
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: artifactShareName
      accessMode: 'ReadWrite'
    }
  }
}

module openAi 'openai.bicep' = {
  name: 'openai'
  params: {
    name: 'aif-${resourceToken}'
    location: location
    tags: tags
    deploymentName: azureOpenAiDeployment
    principalId: identity.properties.principalId
  }
}

var effectiveOpenAiEndpoint = openAi.outputs.endpoint

var databaseUrl = 'postgresql+psycopg://${pgAdminLogin}:${databasePassword}@${postgres.properties.fullyQualifiedDomainName}:5432/${pgDatabaseName}?sslmode=require'

var backendEnv = [
  { name: 'HF_AUTH_MODE', value: 'development' }
  { name: 'HF_ALLOW_INSECURE_DEVELOPMENT_AUTH', value: 'true' }
  { name: 'HF_DEVELOPMENT_ORGANIZATION_ID', value: 'local-dev' }
  { name: 'HF_DEVELOPMENT_SUBJECT_ID', value: 'portal-dev' }
  { name: 'HF_DEVELOPMENT_ROLES', value: 'author,reviewer,registry-admin,developer,org-admin' }
  { name: 'HF_CATALOG_ROOT', value: '/app/catalog' }
  { name: 'HF_ARTIFACT_ROOT', value: '/artifacts' }
  { name: 'HF_DATABASE_URL', secretRef: 'hf-database-url' }
]

var openAiEnv = empty(effectiveOpenAiEndpoint) ? [] : [
  { name: 'HF_AZURE_OPENAI_ENDPOINT', value: effectiveOpenAiEndpoint }
  { name: 'HF_AZURE_OPENAI_DEPLOYMENT', value: azureOpenAiDeployment }
  { name: 'HF_AZURE_MANAGED_IDENTITY_CLIENT_ID', value: identity.properties.clientId }
]

var backendSecrets = [
  { name: 'hf-database-url', value: databaseUrl }
]

var artifactVolumes = [
  { name: 'artifacts', storageType: 'AzureFile', storageName: artifactShareName }
]

var artifactMounts = [
  { volumeName: 'artifacts', mountPath: '/artifacts' }
]

var apiCommand = [
  'sh'
  '-c'
  'alembic upgrade head && python -m web.api.organizations.bootstrap --with-sample-designs && uvicorn web.api.main:create_app --factory --host 0.0.0.0 --port 8000'
]

var workerCommand = [
  'sh'
  '-c'
  'python -m web.api.organizations.bootstrap && python -m web.api.builds.worker'
]

module api 'container-app.bicep' = {
  name: 'ca-api'
  params: {
    name: 'ca-api-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'api' })
    environmentId: containerEnv.id
    registryServer: registry.properties.loginServer
    identityId: identity.id
    targetPort: 8000
    ingressEnabled: true
    external: false
    env: concat(backendEnv, openAiEnv)
    secrets: backendSecrets
    command: apiCommand
    minReplicas: 0
    maxReplicas: 1
  }
  dependsOn: [
    acrPull
  ]
}

module worker 'container-app.bicep' = {
  name: 'ca-worker'
  params: {
    name: 'ca-worker-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'worker' })
    environmentId: containerEnv.id
    registryServer: registry.properties.loginServer
    identityId: identity.id
    ingressEnabled: false
    env: concat(backendEnv, openAiEnv)
    secrets: backendSecrets
    command: workerCommand
    minReplicas: 1
    maxReplicas: 1
  }
  dependsOn: [
    acrPull
  ]
}

var portalEnv = [
  { name: 'NODE_ENV', value: 'production' }
  { name: 'NEXT_TELEMETRY_DISABLED', value: '1' }
  { name: 'NEXT_PUBLIC_HF_AUTH_MODE', value: 'development' }
  { name: 'HF_API_BASE_URL', value: 'https://${api.outputs.fqdn}' }
  { name: 'HF_DEV_ORGANIZATION', value: 'local-dev' }
  { name: 'HF_DEV_SUBJECT', value: 'portal-dev' }
  { name: 'HF_DEV_ROLES', value: 'author,reviewer,registry-admin,developer,org-admin' }
  { name: 'AUTH_SECRET', secretRef: 'auth-secret' }
]

var portalSecrets = [
  { name: 'auth-secret', value: portalAuthSecret }
]

module portal 'container-app.bicep' = {
  name: 'ca-portal'
  params: {
    name: 'ca-portal-${resourceToken}'
    location: location
    tags: union(tags, { 'azd-service-name': 'portal' })
    environmentId: containerEnv.id
    registryServer: registry.properties.loginServer
    identityId: identity.id
    targetPort: 3000
    ingressEnabled: true
    external: true
    env: portalEnv
    secrets: portalSecrets
    minReplicas: 0
    maxReplicas: 2
  }
  dependsOn: [
    acrPull
  ]
}

output registryLoginServer string = registry.properties.loginServer
output registryName string = registry.name
output portalUrl string = 'https://${portal.outputs.fqdn}'
output apiFqdn string = api.outputs.fqdn
