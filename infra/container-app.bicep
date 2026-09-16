@description('Generic Container App used for the portal, api, and worker services.')
param name string
param location string
param tags object

@description('Resource id of the Container Apps managed environment.')
param environmentId string

@description('Login server of the Azure Container Registry the app pulls from.')
param registryServer string

@description('Resource id of the user-assigned identity used for registry pull and Azure auth.')
param identityId string

@description('Full image reference. Empty uses a placeholder until azd deploy pushes the real image.')
param imageName string = ''

param targetPort int = 80
param ingressEnabled bool = true
param external bool = false

param env array = []
param secrets array = []
param command array = []
param volumes array = []
param volumeMounts array = []

param minReplicas int = 1
param maxReplicas int = 1
param cpu string = '0.25'
param memory string = '0.5Gi'

var placeholderImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
var image = empty(imageName) ? placeholderImage : imageName

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: ingressEnabled ? {
        external: external
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: false
      } : null
      registries: [
        {
          server: registryServer
          identity: identityId
        }
      ]
      secrets: secrets
    }
    template: {
      containers: [
        {
          name: name
          image: image
          command: empty(command) ? null : command
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: env
          volumeMounts: volumeMounts
        }
      ]
      volumes: volumes
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

output name string = app.name
output fqdn string = ingressEnabled ? app.properties.configuration.ingress.fqdn : ''
