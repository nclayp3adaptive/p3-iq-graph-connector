#!/usr/bin/env bash
# =============================================================================
# verify-state.sh
#
# Poll the external connection's `state` field until it transitions out of
# `draft` and into `ready` (success), `limitExceeded`, or `obsolete`.
#
# Schema registration is async on the Microsoft side (5-15 minutes). Items
# cannot be ingested while state is `draft`.
#
# Env: P3_CONNECTOR_* per src/auth.py
# Args: optional connection id (default p3iqenrichment)
# =============================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONNECTION_ID="${1:-${CONNECTION_ID:-p3iqenrichment}}"
MAX_WAIT_MIN="${MAX_WAIT_MIN:-20}"
SLEEP_SEC="${SLEEP_SEC:-30}"

deadline=$(( $(date +%s) + MAX_WAIT_MIN * 60 ))
attempt=0

while :; do
  attempt=$(( attempt + 1 ))
  TOKEN="$(python3 -c 'from src.auth import get_graph_token; print(get_graph_token())')"

  STATE="$(curl -sS \
    -H "Authorization: Bearer $TOKEN" \
    "https://graph.microsoft.com/v1.0/external/connections/$CONNECTION_ID" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("state","unknown"))')"

  ts="$(date -u +%H:%M:%S)"
  echo "  [$ts] attempt=$attempt state=$STATE"

  case "$STATE" in
    ready)
      echo "  -> connection is READY"
      exit 0
      ;;
    limitExceeded|obsolete)
      echo "  -> terminal failure state: $STATE" >&2
      exit 2
      ;;
    draft|unknown)
      ;;
    *)
      echo "  -> unexpected state: $STATE" >&2
      ;;
  esac

  if [ "$(date +%s)" -ge "$deadline" ]; then
    echo "  -> timed out after $MAX_WAIT_MIN min, last state=$STATE" >&2
    exit 3
  fi

  sleep "$SLEEP_SEC"
done
