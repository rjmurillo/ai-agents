#!/usr/bin/env python3
"""Decide which GitHub transport this session can actually use.

Run this once, before a PR or issue workflow starts making calls. The answer
is a property of the environment, not of the operation, so discovering it per
call costs one failed round trip each time and invites the caller to retry a
condition that has no reset.

Three environments produce three different answers:

- CI and a normal developer machine: ``gh`` holds a working credential, so the
  gh-backed scripts under this skill are the fastest path.
- An agent sandbox that proxies egress: ``gh`` is installed and ``GH_TOKEN``
  is set, but GitHub is refused for the whole session (HTTP 403). The GitHub
  MCP tools still work, so the caller routes to ``mcp__github__*``.
- No ``gh`` at all: same routing as above, for a different reason.

Exit codes follow ADR-035:
    0 - A usable transport was identified (read ``transport`` for which)
    2 - Config error (plugin lib missing)
    3 - External error (quota refusal or transport wobble; retry shortly)
    4 - Auth error (a credential fault the operator can fix)
"""

from __future__ import annotations

import argparse
import os
import sys

# Two rungs, both portable. The plugin-root variables win when the host exports
# them; otherwise walk up from this file to the bundled library.
_plugin_root = os.environ.get("COPILOT_PLUGIN_ROOT") or os.environ.get("CLAUDE_PLUGIN_ROOT")
if _plugin_root and os.path.isdir(os.path.join(_plugin_root, "lib", "github_core")):
    _lib_dir = os.path.join(_plugin_root, "lib")
else:
    _lib_dir = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "lib")
    )
if not os.path.isdir(_lib_dir):
    print(f"Plugin lib directory not found: {_lib_dir}", file=sys.stderr)
    sys.exit(2)  # Config error per ADR-035
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

from github_core.api import (
    GhAuthStatus,
    check_gh_auth,
    describe_gh_auth_failure,
)
from github_core.output import (
    add_output_format_arg,
    write_skill_error,
    write_skill_output,
)

SCRIPT_NAME = "check_github_transport.py"
VERSION = "1.0.0"

TRANSPORT_GH = "gh"
TRANSPORT_MCP = "mcp"

# Statuses that mean gh cannot serve this session no matter what the operator
# does to the token, and that a second transport is expected to cover.
_ROUTE_TO_MCP = frozenset({GhAuthStatus.TRANSPORT_BLOCKED, GhAuthStatus.MISSING_GH})

_MCP_GUIDANCE = (
    "Route GitHub work through the mcp__github__* tools for this session. "
    "The gh-backed scripts under the github skill cannot reach GitHub here, "
    "so calling them wastes a round trip per operation and reports a failure "
    "that is the environment's, not the PR's."
)


def resolve_transport() -> tuple[str, int, str, str]:
    """Return ``(transport, exit_code, status, detail)`` for this session.

    ``MISSING_GH`` is grouped with a session refusal on purpose. The two have
    different causes and the same consequence for a caller: gh is not an
    option, so the decision to route elsewhere is identical.
    """
    result = check_gh_auth()
    if result.status is GhAuthStatus.AUTHENTICATED:
        return TRANSPORT_GH, 0, result.status.value, ""

    message, exit_code, _ = describe_gh_auth_failure(result)
    if result.status in _ROUTE_TO_MCP:
        # A usable transport exists, so this is not a failure to report as one.
        # Exit 0 keeps the caller moving instead of aborting the workflow.
        return TRANSPORT_MCP, 0, result.status.value, message
    return "", exit_code, result.status.value, message


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    add_output_format_arg(parser)
    args = parser.parse_args(argv)

    transport, exit_code, status, detail = resolve_transport()

    if not transport:
        write_skill_error(
            detail,
            exit_code,
            error_type="ApiError" if exit_code == 3 else "AuthError",
            output_format=args.output_format,
            script_name=SCRIPT_NAME,
            version=VERSION,
            extra={"Transport": "", "AuthStatus": status},
        )
        return exit_code

    guidance = _MCP_GUIDANCE if transport == TRANSPORT_MCP else ""
    summary = (
        f"Transport: {transport} (gh auth status: {status})"
        if transport == TRANSPORT_GH
        else f"Transport: {transport} (gh unusable: {status}). {guidance}"
    )
    write_skill_output(
        {
            "Transport": transport,
            "AuthStatus": status,
            "Guidance": guidance,
            "Detail": detail,
        },
        output_format=args.output_format,
        human_summary=summary,
        status="PASS",
        script_name=SCRIPT_NAME,
        version=VERSION,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
