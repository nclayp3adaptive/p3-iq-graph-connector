# P3 IQ Graph Connector

Microsoft Graph Connector that pushes P3 enrichment content (acronyms, QnA,
methodology cards, glossary entries) into M365 Copilot's native search index,
so Cowork's built-in retrieval ambient-grounds on P3 content wherever a P3
employee is working in Word, Outlook, Teams, etc.

This is the **PUSH** model (synced connector), not federated MCP. Items live in
the tenant's external index; ACL trim, ranking, and conversational surfacing
all happen inside Microsoft Search + Cowork. P3 just owns content authorship
and the periodic sync job.

## Why a Graph Connector (and not just MCP)

P3 already has `p3-iq-mcp-gateway` for federated retrieval into LibreChat and
the P3 IQ CEA. That covers the dedicated "P3 IQ" workflow. But Cowork lives
inside the M365 chrome (Copilot in Word, Outlook, Teams) and grounds on
**Microsoft Search**, not on arbitrary MCP servers. Graph Connectors are the
only supported way to feed Microsoft Search with content from outside the
tenant's first-party stores.

Strategy: ship both. CEA + IQ MCP for the dedicated P3 workflow; Graph
Connector + Skills for ambient discovery via Cowork.

## Architecture

```
P3 content (acronyms, methodology, glossary, QnA)
        |
        |  src/push_items.py (idempotent, runs on cron)
        v
Microsoft Graph  POST /external/connections/{id}/items/{itemId}
        |
        v
Microsoft Search index (tenant-isolated)
        |
        v
M365 Copilot Cowork ambient grounding
        + Microsoft Search vertical
        + SharePoint search
        + Bing-for-business
```

## Schema (FROZEN at v1)

Schemas in this API are essentially immutable: `isRefinable` cannot be added
to an existing property, schemas can't be deleted, and `searchable` +
`refinable` are mutually exclusive on a single property. v1 bakes every
property we might ever filter, facet, or surface on.

| Property             | Type             | Searchable | Refinable | Queryable | Retrievable | Semantic Label                  |
| -------------------- | ---------------- | ---------- | --------- | --------- | ----------- | ------------------------------- |
| title                | String           | yes        | no        | yes       | yes         | title                           |
| url                  | String           | no         | no        | no        | yes         | url                             |
| iconUrl              | String           | no         | no        | no        | yes         | iconUrl                         |
| sourceType           | String           | no         | yes       | yes       | yes         |                                 |
| domain               | String           | no         | yes       | yes       | yes         |                                 |
| tags                 | StringCollection | no         | yes       | yes       | yes         |                                 |
| tier                 | String           | no         | yes       | yes       | yes         |                                 |
| author               | String           | no         | no        | yes       | yes         | createdBy, lastModifiedBy       |
| createdDateTime      | DateTime         | no         | no        | yes       | yes         | createdDateTime                 |
| lastModifiedDateTime | DateTime         | no         | no        | yes       | yes         | lastModifiedDateTime            |
| summary              | String           | yes        | no        | no        | yes         |                                 |

## Repository layout

```
p3-iq-graph-connector/
  README.md               this file
  RUNBOOK.md              operator runbook (one-time setup + every-deploy steps)
  manifest/
    connection.json       POST body for /external/connections
    schema.json           PATCH body for /external/connections/{id}/schema
  src/
    auth.py               cert-based app-only token via msal
    content_builders.py   transform P3 sample dicts -> externalItem shape
    push_items.py         idempotent ingestion script
  content/
    acronyms.sample.json     5 acronyms (DAX, RLS, OBO, MCP, KQL)
    methodology.sample.json  3 methodology cards
    glossary.sample.json     5 P3-specific terms
    qna.sample.json          3 sample QnA pairs
  infra/
    connector-aad-app.bicep  NEW dedicated AAD app + Graph permissions
  scripts/
    register-connection.sh   1-shot: create + schema + first push
    verify-state.sh          poll connection state until ready
  requirements.txt
```

## Quick start (operator)

See `RUNBOOK.md` for the full step-by-step. The TL;DR:

```bash
# 1. cert
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 730 -nodes \
  -subj "/CN=p3-iq-graph-connector"
cat cert.pem key.pem > combined.pem

# 2. AAD app
az deployment sub create -l eastus -f infra/connector-aad-app.bicep

# 3. upload cert + admin-consent (see RUNBOOK)
# 4. set env vars + register
./scripts/register-connection.sh

# 5. tenant admin enables connection in Microsoft Search admin portal
#    https://admin.microsoft.com -> Settings -> Search & intelligence ->
#      Customizations -> Connections -> P3 IQ Enrichment -> Enable
```

## Quotas & constraints

- 50M items per tenant, 5M per connection, 4MB per item, 30 connections per tenant.
- Schema registration is async (5-15 min). Items only ingestable in `ready` state.
- v1 schema is FROZEN. New refinable properties require a new connection.

## Auth model

NEW dedicated AAD app `p3-iq-graph-connector` (NOT the existing IQ app
`970923d5-...`). Application permissions:
`ExternalConnection.ReadWrite.OwnedBy` + `ExternalItem.ReadWrite.OwnedBy`.
Cert-based credential preferred over secret; federated possible if the connector
later runs from a workload-identity host.

## Item ACL

All P3 items are tenant-wide readable: `acl: [{ type: "everyone", value:
"43816816-6496-4583-b2ef-e9ce71856280", accessType: "grant" }]`. P3 doesn't
have row-level security needs on the IQ corpus -- everything in this connector
is internal-or-public knowledge meant for every P3 employee.

If this changes (e.g., Tier-0 secrets), wire ACL onto specific AAD groups via
`type: "group", value: "<group-oid>"`.
