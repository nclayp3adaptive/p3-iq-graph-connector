// =============================================================================
// p3-iq-graph-connector AAD app provisioning
// =============================================================================
//
// Deploys a NEW dedicated AAD application registration named
// "p3-iq-graph-connector" with the two Graph application permissions required
// by the Microsoft Graph Connector PUSH API:
//
//   - ExternalConnection.ReadWrite.OwnedBy
//   - ExternalItem.ReadWrite.OwnedBy
//
// The app is provisioned WITHOUT credentials. After deployment, the operator
// uploads a PFX/PEM cert via:
//
//   az ad app credential reset --id <appId> --cert @cert.pem --append
//
// Then admin-consents the Graph permissions:
//
//   az ad app permission admin-consent --id <appId>
//
// Federated credentials (preferred over cert) can be added post-creation if the
// connector ends up running from GitHub Actions or a workload identity host.
//
// Deploy:
//   az deployment sub create -l eastus -f infra/connector-aad-app.bicep
//
// NOTE: requires the Microsoft.Graph Bicep extension
// (https://learn.microsoft.com/en-us/graph/templates/overview-bicep-templates-for-graph).
// If the local az CLI doesn't have it, run:
//   az extension add --name graph
// or fall back to the AZ CLI commands documented in RUNBOOK.md.
// =============================================================================

targetScope = 'subscription'

extension microsoftGraphV1

@description('Display name for the new AAD application')
param appDisplayName string = 'p3-iq-graph-connector'

@description('Publisher domain (must be a verified domain on the tenant)')
param publisherDomain string = 'p3adaptive.com'

@description('Identifier URI for the app (api://<guid> or https://...)')
param identifierUri string = 'api://p3-iq-graph-connector'

// Microsoft Graph resource appId is fixed across all tenants
var graphResourceAppId = '00000003-0000-0000-c000-000000000000'

// Application-permission IDs on Microsoft Graph (fixed GUIDs)
// Source: https://learn.microsoft.com/en-us/graph/permissions-reference
var externalConnectionReadWriteOwnedByRoleId = 'f431331c-49a6-499f-be1c-62af19c34a9d'
var externalItemReadWriteOwnedByRoleId = '8116ae0f-55c2-452d-9944-d18420f5b2c8'

resource connectorApp 'Microsoft.Graph/applications@v1.0' = {
  uniqueName: appDisplayName
  displayName: appDisplayName
  signInAudience: 'AzureADMyOrg'
  identifierUris: [identifierUri]
  requiredResourceAccess: [
    {
      resourceAppId: graphResourceAppId
      resourceAccess: [
        {
          id: externalConnectionReadWriteOwnedByRoleId
          type: 'Role'
        }
        {
          id: externalItemReadWriteOwnedByRoleId
          type: 'Role'
        }
      ]
    }
  ]
}

resource connectorSp 'Microsoft.Graph/servicePrincipals@v1.0' = {
  appId: connectorApp.appId
}

output appId string = connectorApp.appId
output objectId string = connectorApp.id
output servicePrincipalId string = connectorSp.id
output identifierUri string = identifierUri
output tenantNote string = 'After deploy: upload cert + admin-consent Graph perms (see RUNBOOK.md)'
