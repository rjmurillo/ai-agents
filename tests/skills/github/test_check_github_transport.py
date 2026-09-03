"""Tests for check_github_transport.py.

The script exists so a workflow picks its GitHub transport once, from the
environment, instead of discovering a session-wide refusal one failed call at
a time. The cases that matter are therefore the routing decisions, not the
formatting: which status sends the caller to gh, which sends it to the MCP
tools, and which is a real failure that must stop the run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure importability
_project_root = Path(__file__).resolve().parents[3]
_lib_dir = _project_root / ".claude" / "lib"
_scripts_dir = _project_root / ".claude" / "skills" / "github" / "scripts"
for _p in (str(_lib_dir), str(_scripts_dir / "utils")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import check_github_transport as mod
from github_core.api import GhAuthResult, GhAuthStatus


def _auth(status: GhAuthStatus, detail: str = "") -> GhAuthResult:
    return GhAuthResult(status, detail)


def _run(status: GhAuthStatus, detail: str = "", argv: list[str] | None = None):
    """Run main() with a stubbed preflight, returning (exit_code, stdout)."""
    with patch.object(mod, "check_gh_auth", return_value=_auth(status, detail)):
        with patch("sys.stdout") as stdout:
            code = mod.main(argv if argv is not None else ["--output-format", "json"])
    written = "".join(call.args[0] for call in stdout.write.call_args_list if call.args)
    return code, written


class TestTransportRouting:
    def test_working_credential_routes_to_gh(self):
        with patch.object(
            mod, "check_gh_auth", return_value=_auth(GhAuthStatus.AUTHENTICATED)
        ):
            transport, code, status, detail = mod.resolve_transport()
        assert transport == mod.TRANSPORT_GH
        assert code == 0
        assert status == "authenticated"
        assert detail == ""

    def test_session_refusal_routes_to_mcp(self):
        """The whole point: a refused session still has a usable transport."""
        with patch.object(
            mod, "check_gh_auth", return_value=_auth(GhAuthStatus.TRANSPORT_BLOCKED)
        ):
            transport, code, status, detail = mod.resolve_transport()
        assert transport == mod.TRANSPORT_MCP
        assert code == 0
        assert status == "transport_blocked"
        assert "mcp__github__" in detail

    def test_missing_gh_routes_to_mcp(self):
        """Different cause, same consequence: gh is not an option."""
        with patch.object(
            mod, "check_gh_auth", return_value=_auth(GhAuthStatus.MISSING_GH)
        ):
            transport, code, _, _ = mod.resolve_transport()
        assert transport == mod.TRANSPORT_MCP
        assert code == 0

    @pytest.mark.parametrize(
        "status",
        [
            GhAuthStatus.RATE_LIMITED,
            GhAuthStatus.SECONDARY_RATE_LIMITED,
            GhAuthStatus.TRANSIENT_ERROR,
        ],
    )
    def test_retryable_conditions_are_not_routed_away(self, status):
        """Negative control: a quota window is not a reason to change transport.

        gh works fine here in a minute. Routing to MCP would hide a condition
        the caller should wait out, and would keep hiding it.
        """
        with patch.object(mod, "check_gh_auth", return_value=_auth(status)):
            transport, code, _, _ = mod.resolve_transport()
        assert transport == ""
        assert code == 3

    def test_bad_credential_is_still_an_auth_failure(self):
        """Negative control: a fixable token fault must not be routed around."""
        with patch.object(
            mod, "check_gh_auth", return_value=_auth(GhAuthStatus.INVALID_CREDENTIALS)
        ):
            transport, code, _, detail = mod.resolve_transport()
        assert transport == ""
        assert code == 4
        assert "gh auth login" in detail


class TestCliContract:
    def test_gh_transport_exits_zero_with_json_envelope(self):
        code, out = _run(GhAuthStatus.AUTHENTICATED)
        assert code == 0
        payload = json.loads(out)
        assert payload["Success"] is True
        assert payload["Data"]["Transport"] == "gh"
        assert payload["Data"]["Guidance"] == ""

    def test_blocked_transport_exits_zero_and_names_mcp(self):
        """Exit 0 on purpose: the workflow continues, it just changes transport."""
        code, out = _run(GhAuthStatus.TRANSPORT_BLOCKED, detail="HTTP 403")
        assert code == 0
        payload = json.loads(out)
        assert payload["Success"] is True
        assert payload["Data"]["Transport"] == "mcp"
        assert "mcp__github__" in payload["Data"]["Guidance"]

    def test_rate_limited_exits_three_with_error_envelope(self):
        code, out = _run(GhAuthStatus.RATE_LIMITED)
        assert code == 3
        payload = json.loads(out)
        assert payload["Success"] is False
        assert payload["Error"]["Type"] == "ApiError"

    def test_invalid_credentials_exits_four_with_auth_error(self):
        code, out = _run(GhAuthStatus.INVALID_CREDENTIALS)
        assert code == 4
        payload = json.loads(out)
        assert payload["Success"] is False
        assert payload["Error"]["Type"] == "AuthError"

    def test_human_format_names_the_transport(self):
        code, out = _run(
            GhAuthStatus.TRANSPORT_BLOCKED, argv=["--output-format", "human"]
        )
        assert code == 0
        assert "Transport: mcp" in out
