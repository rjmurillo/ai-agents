"""Semgrep's MCP token verifier works on the pyjwt the override forces.

semgrep declares ``pyjwt[crypto]~=2.13.0``. pyproject.toml overrides it to
2.15.0 to clear the 2.13.0 CVEs (issue #6028). Semgrep calls pyjwt only in
``semgrep.mcp.utilities.token_verifier``: ``PyJWKClient.get_signing_key_from_jwt``
then ``jwt.decode``. These tests drive that path with a local RSA key, so a
pyjwt API change under the override fails here instead of in an MCP session.
The JWKS fetch is replaced with an in-memory key set, so no network is used.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import pytest

token_verifier = pytest.importorskip("semgrep.mcp.utilities.token_verifier")
jwt = pytest.importorskip("jwt")
rsa = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")

KID = "test-key"
SERVER_URL = "https://mcp.example.test/mcp"


def _private_key() -> Any:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks(private_key: Any) -> dict[str, Any]:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": KID, "alg": "RS256", "use": "sig"})
    return {"keys": [jwk]}


def _token(private_key: Any, **claims: Any) -> str:
    payload = {"client_id": "client-1", "scope": "read write", "exp": int(time.time()) + 300}
    payload.update(claims)
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": KID})


def _verify(token: str, published_key: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    keys = _jwks(published_key)
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: keys)
    verifier = token_verifier.IntrospectionTokenVerifier(
        introspection_endpoint="https://auth.example.test/introspect",
        jwks_uri="https://auth.example.test/jwks",
        server_url=SERVER_URL,
    )
    return asyncio.run(verifier.verify_token(token))


def test_the_override_is_the_installed_pyjwt() -> None:
    assert jwt.__version__ == "2.15.0"


def test_a_valid_token_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    key = _private_key()

    access = _verify(_token(key), key, monkeypatch)

    assert access is not None
    assert access.client_id == "client-1"
    assert access.scopes == ["read", "write"]


def test_a_token_signed_by_another_key_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    published, attacker = _private_key(), _private_key()

    assert _verify(_token(attacker), published, monkeypatch) is None


def test_an_expired_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    key = _private_key()

    assert _verify(_token(key, exp=int(time.time()) - 60), key, monkeypatch) is None


def test_a_tampered_payload_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    key = _private_key()
    header, _, signature = _token(key).split(".")
    forged = jwt.utils.base64url_encode(json.dumps({"client_id": "admin"}).encode()).decode()

    assert _verify(f"{header}.{forged}.{signature}", key, monkeypatch) is None
