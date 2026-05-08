# P3 IQ Graph Connector - Operator Runbook

End-to-end runbook for provisioning and operating the P3 IQ Graph Connector.
Audience: tenant Global Admin (one-time setup) + on-call engineer (every-deploy
content sync).

> **Tenant**: P3 Adaptive (`43816816-6496-4583-b2ef-e9ce71856280`)
> **Connection ID**: `p3iqenrichment`
> **AAD app**: `p3-iq-graph-connector` (NEW, dedicated)

---

## 1. Prerequisites

- Az CLI >= 2.60, logged in as a **Global Admin** or **Application Admin** with
  `Microsoft.Graph` extension installed (`az extension add --name graph`).
- Python >= 3.10, with `pip install -r requirements.txt` from this repo.
- OpenSSL (any modern version) for cert generation.
- Network egress to `graph.microsoft.com` and `login.microsoftonline.com`.

```bash
az login --tenant 43816816-6496-4583-b2ef-e9ce71856280
az account set --subscription <p3-azure-subscription-id>
```

---

## 2. Generate the cert

```bash
mkdir -p ~/.p3-connector-secrets
cd ~/.p3-connector-secrets

openssl req -x509 -newkey rsa:4096 \
  -keyout key.pem -out cert.pem -days 730 -nodes \
  -subj "/CN=p3-iq-graph-connector"

# Concat for msal
cat cert.pem key.pem > combined.pem

# Capture the SHA1 thumbprint (uppercase hex, no colons)
openssl x509 -in cert.pem -noout -fingerprint -sha1 \
  | sed 's/.*=//;s/://g'
```

Store the thumbprint -- you'll need it for the MSAL config below.

---

## 3. Deploy the AAD app

```bash
cd p3-iq-graph-connector

az deployment sub create \
  -l eastus \
  -f infra/connector-aad-app.bicep
```

Capture the outputs:

```bash
APP_ID=$(az deployment sub show -n connector-aad-app \
  --query 'properties.outputs.appId.value' -o tsv)
TENANT_ID=43816816-6496-4583-b2ef-e9ce71856280
echo "AppId=$APP_ID  Tenant=$TENANT_ID"
```

> **If your az CLI doesn't have the Microsoft.Graph Bicep extension**, fall
> back to Az CLI commands (this is the official documented alternative):
>
> ```bash
> az ad app create \
>   --display-name p3-iq-graph-connector \
>   --identifier-uris api://p3-iq-graph-connector \
>   --required-resource-accesses '[{
>     "resourceAppId": "00000003-0000-0000-c000-000000000000",
>     "resourceAccess": [
>       {"id": "f431331c-49a6-499f-be1c-62af19c34a9d", "type": "Role"},
>       {"id": "8116ae0f-55c2-452d-9944-d18420f5b2c8", "type": "Role"}
>     ]}]'
> APP_ID=$(az ad app list --display-name p3-iq-graph-connector \
>   --query '[0].appId' -o tsv)
> az ad sp create --id $APP_ID
> ```

---

## 4. Upload the cert to the AAD app

```bash
az ad app credential reset \
  --id $APP_ID \
  --cert @$HOME/.p3-connector-secrets/cert.pem \
  --append
```

---

## 5. Admin-consent the Graph permissions

```bash
az ad app permission admin-consent --id $APP_ID
```

Verify the grant flipped to `Granted for P3 Adaptive`:

```bash
az ad app permission list-grants --id $APP_ID --show-resource-name
```

---

## 6. Set env vars

```bash
export P3_CONNECTOR_TENANT_ID=43816816-6496-4583-b2ef-e9ce71856280
export P3_CONNECTOR_CLIENT_ID=$APP_ID
export P3_CONNECTOR_CERT_PATH=$HOME/.p3-connector-secrets/combined.pem
export P3_CONNECTOR_CERT_THUMB=<SHA1 thumbprint from step 2>
```

For long-term ops, drop these into a `.env` file consumed by your scheduler
(systemd, GitHub Actions secrets, etc.). Never commit `combined.pem` or the
thumbprint.

---

## 7. Register the connection + schema + push initial content

```bash
cd p3-iq-graph-connector
pip install -r requirements.txt

./scripts/register-connection.sh
```

This single script does:

1. POST `/external/connections` with `manifest/connection.json` -> 201/409.
2. PATCH `/external/connections/p3iqenrichment/schema` with
   `manifest/schema.json` -> 202 + Location header (async).
3. Poll connection state via `verify-state.sh` until `ready` (5-15 min).
4. PUT each item in `content/*.sample.json` via `src/push_items.py`.

---

## 8. Tenant admin enables the connection

Until a Global Admin enables the connection in the Microsoft Search admin
portal, items are ingested but not surfaced to users.

1. Go to https://admin.microsoft.com.
2. **Settings** -> **Search & intelligence** -> **Customizations** -> **Connections**.
3. Click **P3 IQ Enrichment**.
4. **Manage** -> **Enable in All vertical** (or scope to specific verticals if
   we want a P3-only search vertical later).
5. Confirm.

Allow 5-30 minutes for the index to propagate before testing.

---

## 9. Verification

### Microsoft Search (immediate)
- Go to https://www.office.com -> search bar -> query "RLS at P3".
- The acronym card should appear under "Other".

### Cowork ambient grounding (5-30 min after enable)
- In M365 Cowork chat: ask "what is RLS at P3?".
- Cowork should ground on the pushed acronym item and cite the
  `https://p3ai.ai/iq/acronym/rls` URL.

### Graph API state check
```bash
curl -sS \
  -H "Authorization: Bearer $(python3 -c 'from src.auth import get_graph_token; print(get_graph_token())')" \
  https://graph.microsoft.com/v1.0/external/connections/p3iqenrichment | jq
```

Expect `"state": "ready"`, `"itemsAvailableForSearch": >0` once items have indexed.

---

## 10. Ongoing operation

### Re-running the sync
`push_items.py` is idempotent. PUT on the same item ID overwrites. Schedule the
sync however your ops prefer:

```bash
# example cron line
0 3 * * * cd /opt/p3-iq-graph-connector && python3 -m src.push_items \
  --content content/*.sample.json >> /var/log/p3-iq-connector.log 2>&1
```

### Adding new content
1. Drop a new `content/<topic>.sample.json` file (or extend an existing one).
2. Re-run the sync.

### Deleting items
DELETE `https://graph.microsoft.com/v1.0/external/connections/p3iqenrichment/items/{itemId}`
with the same auth.

### Rotating the cert
Generate a new pair via step 2, run `az ad app credential reset --append`,
update `P3_CONNECTOR_CERT_PATH` + `P3_CONNECTOR_CERT_THUMB`. Old cert can be
revoked once the new one is verified.

---

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `403 Insufficient privileges` on POST /external/connections | Admin consent not granted | Re-run step 5; verify with `az ad app permission list-grants` |
| Connection stuck in `draft` >20 min | Schema validation server-side failed silently | GET the connection, check operations endpoint: `GET /external/connections/{id}/operations` |
| `400 Property X not in schema` on item PUT | Item has a property not declared in schema.json | Add to schema (note: refinable can't be added later -- bake it now) or strip from item |
| 429 Too Many Requests bursts | Hit Graph throttle | push_items.py already retries with exponential backoff; reduce batch size if persistent |
| Items ingested but not in Search results | Tenant admin hasn't enabled in admin portal | Step 8 |
| Cowork doesn't ground on items | <5 min since admin enable, OR semantic labels misaligned | Wait; verify schema labels against Microsoft's labels list |

---

## Reference

- [Graph Connectors API overview](https://learn.microsoft.com/en-us/graph/connecting-external-content-connectors-api-overview)
- [Schema property reference](https://learn.microsoft.com/en-us/graph/api/resources/externalconnectors-schema)
- [Semantic labels](https://learn.microsoft.com/en-us/graph/api/resources/externalconnectors-property)
- [Item ACL types](https://learn.microsoft.com/en-us/graph/api/resources/externalconnectors-acl)
