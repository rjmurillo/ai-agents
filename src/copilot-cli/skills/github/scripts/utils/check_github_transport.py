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
  MCP operations still work, so the caller routes there (spelled
  ``mcp__github__*`` in Claude Code, ``github/*`` in Copilot CLI).
- No ``gh`` at all: same routing as above, for a different reason.

Exit codes follow ADR-035:
    0 - The gh capability check completed; read ``transport`` for the verdict
    2 - Config error (plugin lib missing)
    3 - External error (quota refusal or transport wobble; retry shortly)
    4 - Auth error (a credential fault the operator can fix)

Exit 0 is not a promise that a usable transport exists. It says this check ran
and reached a verdict about ``gh``. ``gh_unusable`` in particular is a
statement about gh alone: this script cannot see an MCP server and never
probes for one, so a caller that reads exit 0 as "the workflow can run" will
treat an unavailable workflow as runnable. Confirming the operations you need
are exposed is the caller's job, and ``Data.Guidance`` says so at runtime.
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
# Named for what was measured. "mcp" would assert an alternative this script
# never probed; the caller verifies that before relying on it.
TRANSPORT_MCP = "gh_unusable"

# Statuses that mean gh cannot serve this session no matter what the operator
# does to the token, and that a second transport is expected to cover.
_ROUTE_TO_MCP = frozenset({GhAuthStatus.TRANSPORT_BLOCKED, GhAuthStatus.MISSING_GH})

# The absent-binary half of MISSING_GH, stated without the auth remedy that
# shares its status in the library's combined message.
_MISSING_GH_DETAIL = (
    "The GitHub CLI (gh) is not on PATH, so every gh-backed script under this "
    "skill will fail to launch. No credential change helps: there is nothing "
    "to authenticate. Use the GitHub MCP operations for this work (spelled "
    "mcp__github__* in Claude Code, github/* in Copilot CLI), install gh, or "
    "run this where gh is present, such as CI."
)

# This script can only observe gh. It cannot see whether a GitHub MCP server
# is configured, nor whether the operations a workflow needs are among the
# tools that server exposes: a read-only toolset would still leave a PR
# workflow unable to reply, resolve, or merge. So the verdict is scoped to
# what was measured, gh being unusable, and verifying the alternative is
# named as the caller's job (Copilot review on PR #5509).
_MCP_GUIDANCE = (
    "gh cannot reach GitHub for this session, so the gh-backed scripts under "
    "the github skill will fail on every call. Before routing work through the "
    "GitHub MCP tools, confirm the operations you need are actually exposed: "
    "this check cannot see the MCP server and does not assert one is present. "
    "If the needed tools are missing, report the operation as unavailable "
    "rather than reporting a failure that is the environment's, not the PR's."
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
        # gh is not an option, so this is not a failure to report as one. Exit
        # 0 keeps the caller moving instead of aborting the workflow.
        #
        # MISSING_GH takes its own detail. describe_gh_auth_failure covers both
        # of its causes in one sentence ending "Run 'gh auth login' first",
        # which is the right half for an unauthenticated gh and false for an
        # absent one: logging in cannot install a binary. Routing on that text
        # reproduces the misdiagnosis this script exists to end, one status
        # over (Copilot review on PR #5509).
        detail = _MISSING_GH_DETAIL if result.status is GhAuthStatus.MISSING_GH else message
        return TRANSPORT_MCP, 0, result.status.value, detail
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
