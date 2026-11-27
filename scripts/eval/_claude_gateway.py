"""The Claude gateway pair: `ANTHROPIC_BASE_URL` plus `ANTHROPIC_AUTH_TOKEN`.

A gateway, such as a local CLIProxy hub, takes both. Claude Code ranks the
auth token above `CLAUDE_CODE_OAUTH_TOKEN`, so when both are exported the
gateway is what authenticates. `_claude_cli` resolves it first through
`gateway_preempt` and records the step as `gateway`. `endpoint_host` names the
host a run reached, for reports. Nothing here reads or returns the token.
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit

from _cli_credentials import STEP_GATEWAY, ResolvedCredential

__all__ = [
    "AUTH_TOKEN_ENV",
    "BASE_URL_ENV",
    "DEFAULT_ENDPOINT_HOST",
    "endpoint_host",
    "gateway_configured",
    "gateway_preempt",
]

#: The gateway pair. Both reach the child together or not at all: a base URL
#: alone would send the OAuth seat token to that host.
BASE_URL_ENV = "ANTHROPIC_BASE_URL"
AUTH_TOKEN_ENV = "ANTHROPIC_AUTH_TOKEN"

#: The host a run reaches when no base URL is exported.
DEFAULT_ENDPOINT_HOST = "api.anthropic.com"


def gateway_configured(environ: Mapping[str, str]) -> bool:
    """True when both halves of the gateway pair are set and non-blank."""
    return bool(environ.get(BASE_URL_ENV, "").strip()) and bool(
        environ.get(AUTH_TOKEN_ENV, "").strip()
    )


def gateway_preempt(environ: Mapping[str, str]) -> ResolvedCredential | None:
    """The `preempt` source for the Claude credential spec. Carries no secret."""
    return ResolvedCredential(STEP_GATEWAY) if gateway_configured(environ) else None


def endpoint_host(environ: Mapping[str, str]) -> str:
    """The host, with port, a `claude-cli` run reaches. Never the token or path.

    Userinfo in the URL is dropped, so a credential embedded there is not
    recorded. An unparseable base URL reads as `unparseable`, not as the
    default host, because the default would misstate where the run went.
    """
    raw = environ.get(BASE_URL_ENV, "").strip()
    if not raw:
        return DEFAULT_ENDPOINT_HOST
    try:
        parts = urlsplit(raw)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return "unparseable"
    if not host:
        return "unparseable"
    shown = f"[{host}]" if ":" in host else host
    return f"{shown}:{port}" if port is not None else shown
