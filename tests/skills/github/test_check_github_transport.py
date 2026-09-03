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

    def test_missing_gh_is_never_told_to_run_gh_auth_login(self):
        """The library message covers both causes of MISSING_GH in one sentence.

        It ends "Run 'gh auth login' first", which is right for an
        unauthenticated gh and false for an absent one: logging in cannot
        install a binary. Routing on that text reproduces the misdiagnosis this
        script exists to end, one status over (Copilot review on PR #5509).
        """
        with patch.object(
            mod, "check_gh_auth", return_value=_auth(GhAuthStatus.MISSING_GH)
        ):
            _, _, _, detail = mod.resolve_transport()

        assert "gh auth login" not in detail
        assert "not on PATH" in detail
        assert "mcp__github__" in detail

    def test_a_real_credential_fault_still_says_to_authenticate(self):
        """Control: the remedy is only wrong for the status it is wrong for.

        Without this, MISSING_GH's detail could be swapped in everywhere and
        the assertion above would still pass while an operator with a genuinely
        bad token lost the one instruction that fixes it.
        """
        with patch.object(
            mod, "check_gh_auth", return_value=_auth(GhAuthStatus.INVALID_CREDENTIALS)
        ):
            transport, code, _, detail = mod.resolve_transport()

        assert transport == ""
        assert code == 4
        assert "gh auth login" in detail

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
        assert payload["Data"]["Transport"] == "gh_unusable"
        assert "MCP" in payload["Data"]["Guidance"]
        # The verdict must not assert an alternative it never probed.
        assert "does not assert one is present" in payload["Data"]["Guidance"]

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
        assert "Transport: gh_unusable" in out


class TestShippedArtifactRuntimeContract:
    """Execute the artifact consumers actually get, not the canonical module.

    The tests above import the `.claude` copy and mock its auth probe, which
    proves the routing logic and nothing about whether the shipped file can
    locate its bundled library from an install path. Those are different
    failures: a bootstrap regression leaves the logic correct and the script
    unrunnable (Copilot review on PR #5509).
    """

    SHIPPED = (
        _project_root
        / "src"
        / "copilot-cli"
        / "skills"
        / "github"
        / "scripts"
        / "utils"
        / "check_github_transport.py"
    )

    @staticmethod
    def _stub_gh(tmp_path):
        """A deterministic `gh` that reports a healthy auth, first on PATH.

        Without this the test runs the real preflight, which shells out to
        `gh auth status` and can reach the network. Its verdict would then
        depend on the developer's or runner's token, the proxy policy, and the
        timeout, so a test meant to prove plugin-root resolution would report
        on the environment instead (Copilot review on PR #5509).
        """
        bin_dir = tmp_path / "stub-bin"
        bin_dir.mkdir(exist_ok=True)
        gh = bin_dir / "gh"
        gh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        gh.chmod(0o755)
        return bin_dir

    def _run(self, cwd, env_extra, *, stub_bin=None):
        import os
        import subprocess

        env = dict(os.environ)
        for leaked in (
            "COPILOT_PLUGIN_ROOT",
            "CLAUDE_PLUGIN_ROOT",
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "GH_HOST",
        ):
            env.pop(leaked, None)
        if stub_bin is not None:
            env["PATH"] = f"{stub_bin}{os.pathsep}{env.get('PATH', '')}"
        env.update(env_extra)
        return subprocess.run(
            [sys.executable, str(self.SHIPPED), "--output-format", "json"],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def _assert_reached_the_body(self, result):
        """Prove the entrypoint ran and produced the verdict the stub implies.

        Asserting `returncode != 2` passes for any startup crash: an
        ImportError exits 1 and would have certified an artifact that never
        emitted anything. With a stubbed `gh` reporting healthy auth the
        answer is fully determined, so assert the exact exit and the exact
        verdict rather than a range that the ambient token could move
        (Copilot review on PR #5509).
        """
        import json

        assert result.returncode == 0, (
            f"expected exit 0 with a healthy stub gh, got {result.returncode}: "
            f"{result.stdout}{result.stderr}"
        )
        assert "Plugin lib directory not found" not in result.stderr
        payload = json.loads(result.stdout)
        assert payload["Success"] is True
        assert payload["Metadata"]["Script"] == "check_github_transport.py"
        assert payload["Data"]["Transport"] == "gh"

    def test_shipped_copy_exists(self):
        assert self.SHIPPED.is_file(), f"{self.SHIPPED} is not in the tree"

    def test_resolves_its_library_from_a_foreign_cwd_via_plugin_root(self, tmp_path):
        """The install case: run from elsewhere, with the host root exported."""
        plugin_root = _project_root / "src" / "copilot-cli"
        result = self._run(
            tmp_path,
            {"COPILOT_PLUGIN_ROOT": str(plugin_root)},
            stub_bin=self._stub_gh(tmp_path),
        )
        self._assert_reached_the_body(result)

    def test_claude_plugin_root_resolves_the_same_way(self, tmp_path):
        """Both host variables are honored, not just the Copilot one."""
        result = self._run(
            tmp_path,
            {"CLAUDE_PLUGIN_ROOT": str(_project_root / "src" / "copilot-cli")},
            stub_bin=self._stub_gh(tmp_path),
        )
        self._assert_reached_the_body(result)

    def test_bare_relative_path_from_a_foreign_cwd_is_the_failing_control(
        self, tmp_path
    ):
        """Negative control: without a root, a relative invocation cannot resolve.

        This is what the bare `.claude/skills/...` form the review flagged
        would do in a plugin install. If this ever starts passing, the
        positive cases above have stopped proving anything.
        """
        import os
        import subprocess

        env = dict(os.environ)
        env.pop("COPILOT_PLUGIN_ROOT", None)
        env.pop("CLAUDE_PLUGIN_ROOT", None)
        result = subprocess.run(
            [
                sys.executable,
                ".claude/skills/github/scripts/utils/check_github_transport.py",
            ],
            cwd=str(tmp_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode != 0


class TestConfiguredLaunchersRun:
    """Execute the launcher strings the workflows actually dispatch.

    `TestShippedArtifactRuntimeContract` above runs the shipped file with
    `sys.executable`, which proves the module resolves its library from a
    foreign cwd and nothing about the command that reaches it. Broken quoting,
    the wrong harness map, or a wrong script path inside
    `pr-review-config.yaml` all leave that class green (Copilot review on
    PR #5509). These run the config's own value, from a foreign cwd, against
    the shipped Copilot tree, with a deterministic `gh` first on PATH.

    Known gap: the PowerShell branch resolves `python3` on this runner. The
    `py -3` rung it falls back to exists only on Windows, so that arm is
    unexercised here and no Windows runner is available to exercise it.
    """

    CONFIG = _project_root / ".claude" / "commands" / "pr-review-config.yaml"
    PLUGIN_ROOT = _project_root / "src" / "copilot-cli"

    @staticmethod
    def _command(harness):
        import yaml

        config = yaml.safe_load(
            TestConfiguredLaunchersRun.CONFIG.read_text(encoding="utf-8")
        )
        return config["scripts"][harness]["check_transport"]

    def _env(self, tmp_path, **extra):
        import os

        env = dict(os.environ)
        for leaked in (
            "COPILOT_PLUGIN_ROOT",
            "CLAUDE_PLUGIN_ROOT",
            "GH_TOKEN",
            "GITHUB_TOKEN",
            "GH_HOST",
        ):
            env.pop(leaked, None)
        stub = TestShippedArtifactRuntimeContract._stub_gh(tmp_path)
        env["PATH"] = f"{stub}{os.pathsep}{env.get('PATH', '')}"
        env.update(extra)
        return env

    def _run(self, harness, tmp_path, **env_extra):
        import subprocess

        return subprocess.run(
            ["bash", "-c", self._command(harness)],
            cwd=str(tmp_path),
            env=self._env(tmp_path, **env_extra),
            capture_output=True,
            text=True,
            timeout=120,
        )

    @pytest.mark.parametrize("harness", ["claude_code", "copilot"])
    def test_the_configured_command_runs_from_a_foreign_cwd(self, harness, tmp_path):
        import json
        import shutil

        if harness == "copilot" and shutil.which("pwsh") is None:
            pytest.skip("pwsh is not installed on this runner")

        result = self._run(
            harness, tmp_path, COPILOT_PLUGIN_ROOT=str(self.PLUGIN_ROOT)
        )

        assert result.returncode == 0, (
            f"{harness} launcher failed: {result.stdout}{result.stderr}"
        )
        payload = json.loads(result.stdout)
        assert payload["Data"]["Transport"] == "gh"
        assert payload["Metadata"]["Script"] == "check_github_transport.py"

    @pytest.mark.parametrize("harness", ["claude_code", "copilot"])
    def test_the_configured_command_fails_without_a_plugin_root(
        self, harness, tmp_path
    ):
        """Negative control: the same command, minus the only thing that resolves it.

        Both launchers fall back to a bare `.claude`, which does not exist in a
        foreign cwd. Without this, a command that hardcoded an absolute path on
        the developer's machine would pass the case above.
        """
        import shutil

        if harness == "copilot" and shutil.which("pwsh") is None:
            pytest.skip("pwsh is not installed on this runner")

        result = self._run(harness, tmp_path)

        assert result.returncode != 0, (
            f"{harness} launcher resolved with no plugin root: {result.stdout}"
        )

    def test_both_harness_maps_define_the_preflight(self):
        """The key `transport_preflight.command_key` resolves against.

        A map missing it leaves that harness unable to dispatch Step 0 at all,
        which is how the Copilot entry was absent in an earlier round.
        """
        import yaml

        config = yaml.safe_load(self.CONFIG.read_text(encoding="utf-8"))
        key = config["transport_preflight"]["command_key"]
        for harness in ("claude_code", "copilot"):
            assert key in config["scripts"][harness], f"{harness} cannot dispatch {key}"
