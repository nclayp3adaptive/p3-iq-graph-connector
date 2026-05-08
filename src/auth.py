"""Cert-based app-only Microsoft Graph token acquisition for the P3 IQ Graph Connector.

The connector is provisioned as a NEW dedicated AAD app (NOT the existing IQ app
970923d5-...). Microsoft prefers federated > certificate > secret credentials;
we use certificate auth here because the connector typically runs from a host
(VM, container, GitHub Actions) that does not have a managed identity.

Required env vars:
    P3_CONNECTOR_TENANT_ID    Tenant GUID (43816816-6496-4583-b2ef-e9ce71856280 for P3)
    P3_CONNECTOR_CLIENT_ID    AppId of the new dedicated AAD app
    P3_CONNECTOR_CERT_PATH    Path to the PEM-encoded private key (concat: cert + private key)
    P3_CONNECTOR_CERT_THUMB   SHA1 thumbprint of the public cert (uppercase hex, no colons)

Returns: a bearer token string scoped to https://graph.microsoft.com/.default
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import msal


GRAPH_SCOPE = ["https://graph.microsoft.com/.default"]


class AuthConfigError(RuntimeError):
    """Raised when required auth env vars are missing or unreadable."""


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise AuthConfigError(
            f"Missing required env var: {name}. "
            "See src/auth.py docstring for the full list."
        )
    return val


def _load_cert_pem(path: str) -> str:
    p = Path(path)
    if not p.exists():
        raise AuthConfigError(f"Cert file not found at {path}")
    return p.read_text(encoding="utf-8")


def get_graph_token(
    tenant_id: Optional[str] = None,
    client_id: Optional[str] = None,
    cert_path: Optional[str] = None,
    cert_thumbprint: Optional[str] = None,
) -> str:
    """Acquire an app-only access token for Microsoft Graph using cert auth.

    All four args fall back to env vars if not supplied. The resulting token is
    cacheable in-memory; MSAL's ConfidentialClientApplication handles renewal
    when called again.
    """
    tenant_id = tenant_id or _require_env("P3_CONNECTOR_TENANT_ID")
    client_id = client_id or _require_env("P3_CONNECTOR_CLIENT_ID")
    cert_path = cert_path or _require_env("P3_CONNECTOR_CERT_PATH")
    cert_thumbprint = cert_thumbprint or _require_env("P3_CONNECTOR_CERT_THUMB")

    private_key_pem = _load_cert_pem(cert_path)

    authority = f"https://login.microsoftonline.com/{tenant_id}"

    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        authority=authority,
        client_credential={
            "thumbprint": cert_thumbprint,
            "private_key": private_key_pem,
        },
    )

    result = app.acquire_token_for_client(scopes=GRAPH_SCOPE)
    if not result or "access_token" not in result:
        err = result.get("error_description") if result else "no result"
        raise RuntimeError(f"Failed to acquire Graph token: {err}")
    return result["access_token"]


if __name__ == "__main__":  # pragma: no cover
    token = get_graph_token()
    print(f"Acquired token, length={len(token)} chars (truncated): {token[:24]}...")
