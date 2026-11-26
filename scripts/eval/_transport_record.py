"""Which transport an eval run used: cell, payer, credential step, endpoint host.

A runner writes this record next to its scores, so a run through a gateway
is never read back as a direct subscription or API run. It carries the
host only, never a token, userinfo, or URL path. `eval-prompt-change.py`
writes it today; another runner on the `claude-cli` cell can adopt it.
"""

from __future__ import annotations

import os

from _billing_matrix import cell_for_provider
from _claude_gateway import DEFAULT_ENDPOINT_HOST, endpoint_host, gateway_configured
from _cli_credentials import STEP_GATEWAY, recorded_steps
from _providers import is_default_anthropic

__all__ = ["transport_line", "transport_record"]


def transport_record(environ: dict[str, str] | None = None) -> dict[str, object]:
    """Which cell, credential step, and endpoint host a run used. Never a token.

    Both variants and the judge run on this one transport (ADR-058), so one
    record covers the run. `payer` is the cell's payer, except that a
    `gateway` run reads `gateway`: the gateway at `endpoint_host` decides who
    pays, so the run is not claimed as a direct one. Off the gateway step the
    `claude-cli` child gets no base URL, so its host is the default.
    `endpoint_host` is None where the record cannot tell where the transport
    sends requests.
    """
    env = dict(os.environ) if environ is None else environ
    selected = env.get("EVAL_PROVIDER", "").strip().lower()
    cell = cell_for_provider(selected or "anthropic")
    steps = recorded_steps()
    claude_cli = cell is not None and cell.provider == "claude-cli"
    # Before any call resolves a step, an exported pair still means the run
    # would go through the gateway, so a failure-path record says so too.
    gateway = claude_cli and (STEP_GATEWAY in steps or (not steps and gateway_configured(env)))
    host: str | None = None
    if gateway:
        host = endpoint_host(env)
    elif claude_cli:
        host = DEFAULT_ENDPOINT_HOST
    elif cell is not None and cell.provider == "anthropic" and is_default_anthropic(selected):
        # The urllib claude/api transport posts to this host whatever
        # ANTHROPIC_BASE_URL says (`_anthropic_api.py`).
        host = DEFAULT_ENDPOINT_HOST
    payer = "gateway" if gateway else (cell.payer if cell is not None else None)
    return {
        "provider": cell.provider if cell is not None else selected or None,
        "harness": cell.harness if cell is not None else None,
        "payer": payer,
        "credential_steps": steps,
        "endpoint_host": host,
    }


def transport_line(transport: dict[str, object]) -> str:
    """One stderr line naming the transport, its host, and its credential step."""
    steps = transport.get("credential_steps")
    step_text = ", ".join(str(step) for step in steps) if isinstance(steps, list) else ""
    host = transport.get("endpoint_host") or "host not recorded"
    return f"{transport.get('provider')} via {host} (credential: {step_text or 'not recorded'})"
