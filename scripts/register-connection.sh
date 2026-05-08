#!/usr/bin/env bash
# =============================================================================
# register-connection.sh
#
# One-shot bootstrap for the P3 IQ Graph Connector:
#   1. Create the external connection (POST /external/connections)
#   2. PATCH the schema (async, returns 202 + Location header)
#   3. Poll the connection state until ready
#   4. Push the initial content batch
#
# Prereqs:
#   - Az CLI logged in as a Global Admin OR scoped role with Graph admin
#   - The dedicated AAD app already provisioned + cert uploaded + admin-consented
#   - Env vars set (see src/auth.py): P3_CONNECTOR_*
#
# Usage:
#   ./scripts/register-connection.sh
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONNECTION_ID="${CONNECTION_ID:-p3iqenrichment}"

echo "=== Step 1: acquire Graph token ==="
TOKEN="$(python3 "$REPO_ROOT/src/auth.py" 2>&1 | tail -1 | sed 's/.*: //; s/\.\.\.$//')"
# Re-acquire cleanly via a small inline python (the printed token is truncated above)
TOKEN="$(python3 -c 'from src.auth import get_graph_token; print(get_graph_token())')"
if [[ -z "$TOKEN" ]]; then
  echo "Failed to acquire Graph token" >&2
  exit 1
fi
echo "  token acquired (length=${#TOKEN})"

echo
echo "=== Step 2: create connection ==="
CONN_BODY="$(cat "$REPO_ROOT/manifest/connection.json")"
CREATE_HTTP="$(curl -sS -o /tmp/conn-create.json -w '%{http_code}' \
  -X POST "https://graph.microsoft.com/v1.0/external/connections" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$CONN_BODY")"
case "$CREATE_HTTP" in
  201) echo "  connection created (HTTP 201)" ;;
  409) echo "  connection already exists (HTTP 409) -- continuing" ;;
  *)   echo "  create failed: HTTP $CREATE_HTTP"; cat /tmp/conn-create.json; exit 1 ;;
esac

echo
echo "=== Step 3: register schema (async, 5-15 min) ==="
SCHEMA_BODY="$(cat "$REPO_ROOT/manifest/schema.json")"
SCHEMA_HTTP="$(curl -sS -o /tmp/schema-resp.json -D /tmp/schema-headers.txt -w '%{http_code}' \
  -X PATCH "https://graph.microsoft.com/v1.0/external/connections/$CONNECTION_ID/schema" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$SCHEMA_BODY")"
case "$SCHEMA_HTTP" in
  202) echo "  schema accepted (HTTP 202, async)" ;;
  204) echo "  schema accepted (HTTP 204)" ;;
  200) echo "  schema accepted (HTTP 200)" ;;
  *)   echo "  schema patch failed: HTTP $SCHEMA_HTTP"; cat /tmp/schema-resp.json; exit 1 ;;
esac

echo
echo "=== Step 4: poll connection state until ready ==="
"$REPO_ROOT/scripts/verify-state.sh"

echo
echo "=== Step 5: push initial content ==="
cd "$REPO_ROOT"
python3 -m src.push_items \
  --connection-id "$CONNECTION_ID" \
  --content content/acronyms.sample.json \
            content/methodology.sample.json \
            content/glossary.sample.json \
            content/qna.sample.json

echo
echo "=== DONE ==="
echo "Next: enable connection in Microsoft Search admin portal (see RUNBOOK.md step 8)"
