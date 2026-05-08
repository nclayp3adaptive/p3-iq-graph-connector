"""Transform P3 content sample dicts into Microsoft Graph externalItem shape.

The pushed shape (per Microsoft Graph spec):
{
    "acl": [{ "type": "everyone", "value": "<tenant-guid>", "accessType": "grant" }],
    "properties": {
        "title": "...", "url": "...", "iconUrl": "...",
        "sourceType": "...", "domain": "...", "tags": [...], "tier": "...",
        "author": "...", "createdDateTime": "...", "lastModifiedDateTime": "...",
        "summary": "..."
    },
    "content": { "value": "<html or text body>", "type": "html" | "text" }
}

The schema we registered (manifest/schema.json) defines exactly these property
names. Anything we put in `properties` must match the schema or the PUT 400s.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List


# P3 tenant GUID -- "everyone in P3" access pattern uses the tenant id as the value.
P3_TENANT_ID = os.environ.get(
    "P3_CONNECTOR_TENANT_ID",
    "43816816-6496-4583-b2ef-e9ce71856280",
)


SCHEMA_PROPERTY_NAMES = {
    "title",
    "url",
    "iconUrl",
    "sourceType",
    "domain",
    "tags",
    "tier",
    "author",
    "createdDateTime",
    "lastModifiedDateTime",
    "summary",
}


def _default_acl(tenant_id: str = P3_TENANT_ID) -> List[Dict[str, str]]:
    """Item-level ACL: grant access to everyone in the P3 tenant."""
    return [
        {
            "type": "everyone",
            "value": tenant_id,
            "accessType": "grant",
        }
    ]


def _build_properties(item: Dict[str, Any]) -> Dict[str, Any]:
    """Pull only the schema-defined fields, in the right shape."""
    props: Dict[str, Any] = {}
    for key in SCHEMA_PROPERTY_NAMES:
        if key in item and item[key] is not None:
            props[key] = item[key]
    return props


def content_to_external_item(
    item: Dict[str, Any],
    tenant_id: str = P3_TENANT_ID,
) -> Dict[str, Any]:
    """Convert a P3 content sample dict to the Graph externalItem PUT body.

    Required input keys: id, title, summary, content. Optional: everything else
    in the schema. The `id` is consumed at the URL level (PUT /items/{id}) and
    is NOT included in the body.
    """
    if "id" not in item:
        raise ValueError("content item missing required 'id' field")
    if "content" not in item:
        raise ValueError(f"content item {item['id']!r} missing required 'content' field")

    body_value = item["content"]
    body_type = "html" if "<" in body_value and ">" in body_value else "text"

    return {
        "acl": _default_acl(tenant_id),
        "properties": _build_properties(item),
        "content": {
            "value": body_value,
            "type": body_type,
        },
    }


def items_from_content_files(paths: List[str]) -> List[Dict[str, Any]]:
    """Load a list of P3 content sample JSON files, return a flat item list."""
    import json

    out: List[Dict[str, Any]] = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as fh:
            chunk = json.load(fh)
        if not isinstance(chunk, list):
            raise ValueError(f"{path} must contain a JSON array of items")
        out.extend(chunk)
    return out


if __name__ == "__main__":  # pragma: no cover
    sample = {
        "id": "test",
        "title": "Test",
        "summary": "x",
        "content": "x",
        "sourceType": "acronym",
        "domain": "powerbi",
        "author": "p3",
        "url": "https://p3ai.ai",
        "iconUrl": "https://p3ai.ai/i",
        "createdDateTime": "2026-05-08T00:00:00Z",
        "lastModifiedDateTime": "2026-05-08T00:00:00Z",
        "tags": ["x"],
        "tier": "internal",
    }
    import json as _json

    print(_json.dumps(content_to_external_item(sample), indent=2))
