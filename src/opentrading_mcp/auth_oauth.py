"""OAuth 2.1 resource-server token validation (Phase 2).

This server never issues tokens — it only validates JWTs minted by an
external authorization server (issuer/audience/scope/expiry + RS256
signature via JWKS). Team bearer tokens (auth.py) stay valid for
internal use.
"""

from __future__ import annotations

import os
import time
from typing import Any

_JWKS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_JWKS_TTL_SECONDS = 600.0


class JwtError(Exception):
    """Token missing, malformed, expired or failing policy checks."""


def is_configured() -> bool:
    return bool(os.environ.get("MCP_JWT_ISSUER", "").strip())


def _jwks_url() -> str:
    explicit = os.environ.get("MCP_JWT_JWKS_URL", "").strip()
    if explicit:
        return explicit
    issuer = os.environ.get("MCP_JWT_ISSUER", "").strip().rstrip("/")
    return f"{issuer}/.well-known/jwks.json"


def _fetch_jwks(url: str) -> dict[str, Any]:
    import httpx

    now = time.monotonic()
    cached = _JWKS_CACHE.get(url)
    if cached and now - cached[0] < _JWKS_TTL_SECONDS:
        return cached[1]
    try:
        response = httpx.get(url, timeout=10)
        response.raise_for_status()
        body = response.json()
    except Exception as exc:
        raise JwtError(f"cannot fetch JWKS: {exc}") from exc
    if not isinstance(body, dict) or not isinstance(body.get("keys"), list):
        raise JwtError("malformed JWKS document")
    _JWKS_CACHE[url] = (now, body)
    return body


def _key_for(jwks: dict[str, Any], kid: str | None) -> dict[str, Any]:
    keys = [k for k in jwks.get("keys", []) if isinstance(k, dict)]
    if kid:
        for key in keys:
            if key.get("kid") == kid:
                return key
        raise JwtError("unknown key id")
    if len(keys) == 1:
        first = keys[0]
        assert isinstance(first, dict)
        return first
    raise JwtError("missing key id")


def validate_jwt(token: str) -> dict[str, Any]:
    """Validate a bearer JWT; return its claims or raise JwtError."""
    import jwt as pyjwt

    issuer = os.environ.get("MCP_JWT_ISSUER", "").strip()
    audience = os.environ.get("MCP_JWT_AUDIENCE", "").strip()
    if not issuer:
        raise JwtError("JWT validation not configured")
    jwks = _fetch_jwks(_jwks_url())
    try:
        header = pyjwt.get_unverified_header(token)
    except pyjwt.PyJWTError as exc:
        raise JwtError(f"malformed token: {exc}") from exc
    key = _key_for(jwks, header.get("kid") if isinstance(header, dict) else None)
    try:
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
        from jwt.algorithms import RSAAlgorithm

        public_key = RSAAlgorithm.from_jwk(key)
        if not isinstance(public_key, RSAPublicKey):
            raise JwtError("unsupported key type")
        claims = pyjwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=audience or None,
            options={"require": ["exp", "iss", "sub"]},
        )
    except pyjwt.ExpiredSignatureError as exc:
        raise JwtError("token expired") from exc
    except pyjwt.InvalidAudienceError as exc:
        raise JwtError("wrong audience") from exc
    except pyjwt.InvalidIssuerError as exc:
        raise JwtError("wrong issuer") from exc
    except pyjwt.PyJWTError as exc:
        raise JwtError(f"invalid token: {exc}") from exc
    required_scope = os.environ.get("MCP_JWT_REQUIRED_SCOPE", "").strip()
    if required_scope:
        scopes = str(claims.get("scope", "")).split()
        if required_scope not in scopes:
            raise JwtError("missing required scope")
    if not isinstance(claims, dict):
        raise JwtError("invalid claims")
    return claims
