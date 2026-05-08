"""Push P3 enrichment items into the Microsoft Graph external connection.

Idempotent: re-running PUTs the same item IDs and overwrites any prior payload.
Retries on 429 with exponential backoff, honoring Retry-After when present.

Usage:
    python -m src.push_items \
        --connection-id p3iqenrichment \
        --content content/acronyms.sample.json content/methodology.sample.json \
                  content/glossary.sample.json content/qna.sample.json

Env vars (see src/auth.py for the full auth set):
    P3_CONNECTOR_TENANT_ID, P3_CONNECTOR_CLIENT_ID,
    P3_CONNECTOR_CERT_PATH, P3_CONNECTOR_CERT_THUMB
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict, List
from urllib.parse import quote

import requests

from auth import get_graph_token
from content_builders import content_to_external_item, items_from_content_files


GRAPH_BASE = "https://graph.microsoft.com/v1.0"
MAX_RETRIES = 5
INITIAL_BACKOFF_SEC = 2.0


class PushError(RuntimeError):
    pass


def _put_item(
    session: requests.Session,
    connection_id: str,
    item_id: str,
    body: Dict[str, Any],
    token: str,
) -> None:
    """PUT a single item, retrying on 429 / 5xx with exponential backoff."""
    url = (
        f"{GRAPH_BASE}/external/connections/{quote(connection_id)}"
        f"/items/{quote(item_id, safe='')}"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    backoff = INITIAL_BACKOFF_SEC
    for attempt in range(1, MAX_RETRIES + 1):
        resp = session.put(url, headers=headers, json=body, timeout=30)
        if resp.status_code in (200, 201, 202, 204):
            print(f"  [ok]   {item_id}  -> HTTP {resp.status_code}")
            return
        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = resp.headers.get("Retry-After")
            wait = float(retry_after) if retry_after else backoff
            print(
                f"  [retry] {item_id}  HTTP {resp.status_code} "
                f"attempt {attempt}/{MAX_RETRIES}, sleeping {wait:.1f}s"
            )
            time.sleep(wait)
            backoff *= 2
            continue
        # Non-retryable
        raise PushError(
            f"PUT {item_id} failed: HTTP {resp.status_code} {resp.text[:500]}"
        )

    raise PushError(f"PUT {item_id} exhausted {MAX_RETRIES} retries")


def push_all(connection_id: str, content_paths: List[str]) -> Dict[str, int]:
    """Load sample files, transform, and PUT each item. Returns counts."""
    items = items_from_content_files(content_paths)
    print(f"Loaded {len(items)} items from {len(content_paths)} file(s)")

    token = get_graph_token()
    session = requests.Session()

    counts = {"total": len(items), "ok": 0, "failed": 0}
    for item in items:
        item_id = item["id"]
        body = content_to_external_item(item)
        try:
            _put_item(session, connection_id, item_id, body, token)
            counts["ok"] += 1
        except PushError as exc:
            print(f"  [FAIL] {item_id}: {exc}", file=sys.stderr)
            counts["failed"] += 1

    print(json.dumps(counts, indent=2))
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Push P3 IQ items into Microsoft Graph external connection")
    parser.add_argument(
        "--connection-id",
        default="p3iqenrichment",
        help="Connection ID (matches manifest/connection.json id)",
    )
    parser.add_argument(
        "--content",
        nargs="+",
        required=True,
        help="One or more content/*.sample.json files",
    )
    args = parser.parse_args()

    counts = push_all(args.connection_id, args.content)
    return 0 if counts["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
