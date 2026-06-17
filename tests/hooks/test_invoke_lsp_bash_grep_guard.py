#!/usr/bin/env python3
"""Tests for the invoke_lsp_bash_grep_guard PreToolUse hook (ADR-062).

Covers: grep-family detection, code-symbol gating, capability + availability
conditioning, git-grep exemption, LSP_GATE_MODE=warn advisory path, the
SKIP_LSP_GATE kill switch, and EVERY fail-open path (tty, empty stdin, malformed
JSON, missing tool_input, non-dict tool_input, wrong tool_name, missing command,
exception, no provider available, non-code symbol, non-code target, out-of-repo
target, no file target). Exit codes: 0 = allow, 2 = block.

Includes subprocess invocation feeding stdin JSON and a runpy/main() entry-point
test, per the repo hook-test pattern (tests/hooks/test_adr_architect_gate.py).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOK_DIR = str(REPO_ROOT / ".claude" / "hooks" / "PreToolUse")
HOOK_PATH = REPO_ROOT / ".claude" / "hooks" / "PreToolUse" / "invoke_lsp_bash_grep_guard.py"
sys.path.insert(0, HOOK_DIR)

import invoke_lsp_bash_grep_guard as guard  # noqa: E402

# A code-symbol grep on a .py file in this repo. Serena is configured for
# python in .serena/project.yml, so detect_providers returns a provider and the
# guard gates this command when project_dir is the repo root.
_BLOCKING_CMD = 'grep -rn "parseConfig" src/app.py'


def _bash_payload(command: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


# ---------------------------------------------------------------------------
# Pure helpers: _candidate_targets
# ---------------------------------------------------------------------------


class TestCandidateTargets:
    def test_extracts_dotted_file_token(self):
        assert "src/app.py" in guard._candidate_targets('grep "Foo" src/app.py')

    def test_dedupes_repeated_target(self):
        targets = guard._candidate_targets("grep Foo a.py a.py b.ts")
        assert targets == ["a.py", "b.ts"]

    def test_extracts_include_glob_extension(self):
        targets = guard._candidate_targets('rg "Foo" --include=*.py .')
        assert any(t.endswith(".py") for t in targets)

    def test_no_file_token_returns_empty(self):
        assert guard._candidate_targets("echo hi | grep Foo") == []

    def test_pyc_does_not_match_py_extension(self):
        # Word boundary anchors the extension; foo.pyc must not match `.py`.
        assert guard._candidate_targets("grep Foo foo.pyc") == []


# ---------------------------------------------------------------------------
# _navigable_target_with_provider
# ---------------------------------------------------------------------------


class TestNavigableTargetWithProvider:
    def test_returns_first_navigable_with_provider(self):
        result = guard._navigable_target_with_provider(["a.py"], str(REPO_ROOT))
        assert result == "a.py"

    def test_skips_non_navigable_target(self):
        # README.md is overview-capable but NOT symbol-navigation; skip it.
        result = guard._navigable_target_with_provider(["x.md"], str(REPO_ROOT))
        assert result is None

    @patch.object(guard, "detect_providers", return_value=[])
    def test_returns_none_when_no_provider(self, _mock):
        result = guard._navigable_target_with_provider(["a.py"], str(REPO_ROOT))
        assert result is None

    def test_empty_targets_returns_none(self):
        assert guard._navigable_target_with_provider([], str(REPO_ROOT)) is None


# ---------------------------------------------------------------------------
# evaluate_command
# ---------------------------------------------------------------------------


class TestEvaluateCommand:
    def test_blocks_code_symbol_grep_on_py(self):
        decision = guard.evaluate_command(_BLOCKING_CMD, str(REPO_ROOT))
        assert decision is not None
        assert "parseConfig" in decision["symbols"]
        assert decision["target"].endswith(".py")

    def test_allows_git_grep(self):
        cmd = 'git grep "parseConfig" -- src/app.py'
        assert guard.evaluate_command(cmd, str(REPO_ROOT)) is None

    def test_allows_non_grep_command(self):
        assert guard.evaluate_command("ls -la src/app.py", str(REPO_ROOT)) is None

    def test_allows_non_code_symbol(self):
        # "error" is lowercase <= 8 chars: allowlisted, not a code symbol.
        assert guard.evaluate_command('grep -rn "error" src/app.py', str(REPO_ROOT)) is None

    def test_allows_non_code_target(self):
        # PascalCase symbol but the target is markdown (no symbol-navigation).
        assert guard.evaluate_command('grep "ParseConfig" README.md', str(REPO_ROOT)) is None

    def test_allows_when_no_file_target(self):
        # Code symbol but no file target named -> no navigable target -> allow.
        assert guard.evaluate_command('echo x | grep "parseConfig"', str(REPO_ROOT)) is None

    def test_allows_when_no_provider_available(self):
        # A .go file is symbol-navigable for native LSP, but pretend no provider.
        with patch.object(guard, "detect_providers", return_value=[]):
            assert guard.evaluate_command('grep "parseConfig" main.go', str(REPO_ROOT)) is None

    def test_allows_empty_command(self):
        assert guard.evaluate_command("", str(REPO_ROOT)) is None

    def test_allows_non_string_command(self):
        assert guard.evaluate_command(123, str(REPO_ROOT)) is None

    def test_blocks_egrep(self):
        assert guard.evaluate_command('egrep "parseConfig" src/app.py', str(REPO_ROOT)) is not None

    def test_blocks_rg(self):
        assert guard.evaluate_command('rg "parseConfig" src/app.py', str(REPO_ROOT)) is not None


# ---------------------------------------------------------------------------
# Directory / repo-wide scope detection (#2198)
# ---------------------------------------------------------------------------


class TestDirectoryScopeHelpers:
    def test_recursive_flag_is_directory_scope(self):
        assert guard._is_directory_scope('grep -r "Foo" .', str(REPO_ROOT)) is True

    def test_combined_recursive_flag_is_directory_scope_without_path(self):
        assert guard._is_directory_scope('grep -rn "Foo"', str(REPO_ROOT)) is True

    def test_long_recursive_flag_is_directory_scope(self):
        assert (
            guard._is_directory_scope('grep --recursive "Foo" .', str(REPO_ROOT))
            is True
        )

    def test_rg_defaults_recursive(self):
        # ripgrep scans the working tree with no path argument.
        assert guard._is_directory_scope('rg "Foo"', str(REPO_ROOT)) is True

    def test_plain_grep_no_path_is_not_directory_scope(self):
        # A bare grep reads stdin; not a directory scope.
        assert guard._is_directory_scope("echo x | grep Foo", str(REPO_ROOT)) is False

    def test_in_repo_directory_argument_is_scope(self):
        assert (
            guard._is_directory_scope('grep -r "Foo" scripts', str(REPO_ROOT)) is True
        )

    def test_out_of_repo_directory_argument_is_not_scope(self):
        # An explicit out-of-repo directory fixes the scope to out-of-repo.
        assert (
            guard._is_directory_scope('grep -r "Foo" /tmp', str(REPO_ROOT)) is False
        )

    def test_directory_arguments_skips_flags(self):
        assert guard._directory_arguments('grep -rn "Foo" .') == ["."]

    def test_directory_arguments_collects_trailing_slash(self):
        assert guard._directory_arguments("grep -r Foo src/") == ["src/"]

    def test_directory_arguments_collects_parent_relative_path(self):
        assert guard._directory_arguments("grep -r Foo ../other_repo") == [
            "../other_repo"
        ]

    def test_directory_arguments_skips_pattern_with_slash(self):
        assert guard._directory_arguments('rg "import/utils"') == []

    def test_directory_arguments_collects_bare_file_after_pattern(self):
        assert guard._directory_arguments('grep -r "Foo" LICENSE') == ["LICENSE"]

    def test_in_repo_file_argument_is_not_directory_scope(self):
        readme = REPO_ROOT / "README.md"
        assert (
            guard._is_directory_scope(f'grep -r "Foo" {readme}', str(REPO_ROOT))
            is False
        )

    def test_slash_pattern_keeps_recursive_repo_scope(self):
        assert guard._is_directory_scope('rg "import/utils"', str(REPO_ROOT)) is True
        assert guard._is_directory_scope('grep -rn "src/helpers"', str(REPO_ROOT)) is True

    def test_space_separated_flag_value_does_not_hide_recursive_scope(self):
        assert guard._is_directory_scope('grep -r -m 5 "parseConfig"', str(REPO_ROOT)) is True

    def test_space_separated_flag_value_keeps_later_file_path(self):
        assert guard._directory_arguments('grep -r -m 5 "Foo" LICENSE') == ["LICENSE"]

    def test_pattern_option_value_counts_as_pattern(self):
        assert guard._directory_arguments('grep -r -e "Foo" LICENSE') == ["LICENSE"]


class TestEvaluateRepoWideScope:
    def test_blocks_repo_wide_recursive_grep(self):
        # (a) `grep -r Sym .` gates in this repo (python provider configured).
        decision = guard.evaluate_command('grep -r "parseConfig" .', str(REPO_ROOT))
        assert decision is not None
        assert "parseConfig" in decision["symbols"]
        assert decision["target"] == guard._REPO_SCOPE_TARGET

    def test_blocks_rg_no_path(self):
        decision = guard.evaluate_command('rg "parseConfig"', str(REPO_ROOT))
        assert decision is not None
        assert decision["target"] == guard._REPO_SCOPE_TARGET

    def test_allows_out_of_repo_recursive_grep(self):
        # (b) An out-of-repo directory is never gated.
        assert (
            guard.evaluate_command('grep -r "parseConfig" /tmp', str(REPO_ROOT))
            is None
        )

    @patch.object(guard, "repo_has_programming_provider", return_value=False)
    def test_allows_repo_wide_when_provider_less(self, _mock):
        # (c) A provider-less repo: repo-wide grep stays fail-open.
        assert (
            guard.evaluate_command('grep -r "parseConfig" .', str(REPO_ROOT)) is None
        )

    def test_allows_plain_stdin_grep(self):
        # A bare stdin grep names no directory and is not gated.
        assert (
            guard.evaluate_command('echo x | grep "parseConfig"', str(REPO_ROOT))
            is None
        )


# ---------------------------------------------------------------------------
# build_guidance
# ---------------------------------------------------------------------------


class TestBuildGuidance:
    def test_lists_symbols_and_target_extension(self):
        text = guard.build_guidance(["parseConfig", "ParseConfig"], "src/app.py")
        assert "parseConfig" in text
        assert "ParseConfig" in text
        assert ".py" in text
        assert "BLOCKED" in text

    def test_mentions_bypass_envs(self):
        text = guard.build_guidance(["parseConfig"], "src/app.py")
        assert "LSP_GATE_MODE=warn" in text
        assert "SKIP_LSP_GATE=true" in text

    def test_repo_scope_target_renders_repository_wide(self):
        # The <repo> sentinel must not produce an empty "(.suffix)" string.
        text = guard.build_guidance(["parseConfig"], guard._REPO_SCOPE_TARGET)
        assert "repository-wide" in text
        assert "()" not in text


# ---------------------------------------------------------------------------
# main(): block / warn / allow / fail-open paths
# ---------------------------------------------------------------------------


class TestMainBlockAndWarn:
    @patch.object(guard, "get_project_directory", return_value=str(REPO_ROOT))
    def test_blocks_with_exit_2(self, _mock_dir, mock_stdin: Callable[[str], None], capsys):
        mock_stdin(_bash_payload(_BLOCKING_CMD))
        result = guard.main()
        assert result == 2
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out
        assert "blocked grep" in captured.err
        assert "parseConfig" in captured.err

    @patch.object(guard, "get_project_directory", return_value=str(REPO_ROOT))
    def test_warn_mode_exits_0_with_guidance(
        self, _mock_dir, mock_stdin: Callable[[str], None], monkeypatch, capsys
    ):
        monkeypatch.setenv("LSP_GATE_MODE", "warn")
        mock_stdin(_bash_payload(_BLOCKING_CMD))
        result = guard.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "BLOCKED" in captured.out
        assert "warn grep" in captured.err

    @patch.object(guard, "get_project_directory", return_value=str(REPO_ROOT))
    def test_warn_mode_case_insensitive(
        self, _mock_dir, mock_stdin: Callable[[str], None], monkeypatch
    ):
        monkeypatch.setenv("LSP_GATE_MODE", "WARN")
        mock_stdin(_bash_payload(_BLOCKING_CMD))
        assert guard.main() == 0

    @patch.object(guard, "get_project_directory", return_value=str(REPO_ROOT))
    def test_default_mode_blocks(
        self, _mock_dir, mock_stdin: Callable[[str], None], monkeypatch
    ):
        monkeypatch.delenv("LSP_GATE_MODE", raising=False)
        mock_stdin(_bash_payload(_BLOCKING_CMD))
        assert guard.main() == 2


class TestMainLspRuntimeDownFailOpen:
    """LSP_DOWN makes a would-be-blocked grep ALLOW with a one-time warning.

    detect_providers is config-only, so a grep on a configured language still
    gates when the language server has timed out. With the LSP-down signal set,
    the grep gate degrades to ALLOW (issue #2622, ADR-062 Section 5).

    The block decision is forced via a patched ``evaluate_command`` so the gate
    outcome is deterministic regardless of the host MCP config (whether a serena
    provider is "configured" varies by environment; the gate-vs-allow split is
    not what this test exercises, the LSP-down fail-open is).
    """

    _DECISION = {"symbols": ["parseConfig"], "target": "src/app.py"}

    @pytest.fixture(autouse=True)
    def _isolated(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        monkeypatch.delenv("LSP_GATE_MODE", raising=False)
        monkeypatch.delenv("LSP_DOWN", raising=False)
        monkeypatch.delenv("SKIP_LSP_GATE", raising=False)

    @patch.object(guard, "skip_if_consumer_repo", return_value=False)
    @patch.object(guard, "get_project_directory", return_value=str(REPO_ROOT))
    @patch.object(guard, "evaluate_command")
    def test_blocking_grep_allows_when_lsp_down(
        self, mock_eval, _mock_dir, _mock_skip, mock_stdin, monkeypatch, capsys
    ):
        mock_eval.return_value = self._DECISION
        monkeypatch.setenv("LSP_DOWN", "true")
        mock_stdin(_bash_payload(_BLOCKING_CMD))
        assert guard.main() == 0
        assert "LSP runtime is down" in capsys.readouterr().err

    @patch.object(guard, "skip_if_consumer_repo", return_value=False)
    @patch.object(guard, "get_project_directory", return_value=str(REPO_ROOT))
    @patch.object(guard, "evaluate_command")
    def test_lsp_up_still_blocks(
        self, mock_eval, _mock_dir, _mock_skip, mock_stdin, monkeypatch
    ):
        # Negative control: LSP_DOWN unset, the gated grep still blocks.
        mock_eval.return_value = self._DECISION
        monkeypatch.delenv("LSP_DOWN", raising=False)
        mock_stdin(_bash_payload(_BLOCKING_CMD))
        assert guard.main() == 2


class TestMainAllowPaths:
    @patch.object(guard, "get_project_directory", return_value=str(REPO_ROOT))
    def test_allows_git_grep(self, _mock_dir, mock_stdin: Callable[[str], None]):
        mock_stdin(_bash_payload('git grep "parseConfig" -- src/app.py'))
        assert guard.main() == 0

    @patch.object(guard, "get_project_directory", return_value=str(REPO_ROOT))
    def test_allows_non_code_target(self, _mock_dir, mock_stdin: Callable[[str], None]):
        mock_stdin(_bash_payload('grep "ParseConfig" README.md'))
        assert guard.main() == 0

    @patch.object(guard, "get_project_directory", return_value=str(REPO_ROOT))
    def test_allows_non_code_symbol(self, _mock_dir, mock_stdin: Callable[[str], None]):
        mock_stdin(_bash_payload('grep -rn "error" src/app.py'))
        assert guard.main() == 0

    @patch.object(guard, "get_project_directory", return_value=str(REPO_ROOT))
    def test_allows_out_of_repo_target(self, _mock_dir, mock_stdin: Callable[[str], None]):
        # Out-of-repo .py: native LSP extension set still matches, so to prove
        # the out-of-repo / no-provider degradation we drop the provider.
        with patch.object(guard, "detect_providers", return_value=[]):
            mock_stdin(_bash_payload('grep "parseConfig" /tmp/elsewhere.py'))
            assert guard.main() == 0

    @patch.object(guard, "get_project_directory", return_value=str(REPO_ROOT))
    def test_allows_no_file_target(self, _mock_dir, mock_stdin: Callable[[str], None]):
        mock_stdin(_bash_payload('echo x | grep "parseConfig"'))
        assert guard.main() == 0


class TestMainFailOpen:
    def test_kill_switch_skips(self, monkeypatch, mock_stdin: Callable[[str], None]):
        monkeypatch.setenv("SKIP_LSP_GATE", "true")
        # Even a blocking payload is allowed under the kill switch.
        mock_stdin(_bash_payload(_BLOCKING_CMD))
        assert guard.main() == 0

    def test_kill_switch_case_insensitive(self, monkeypatch, mock_stdin: Callable[[str], None]):
        monkeypatch.setenv("SKIP_LSP_GATE", "TRUE")
        mock_stdin(_bash_payload(_BLOCKING_CMD))
        assert guard.main() == 0

    @patch.object(guard, "skip_if_consumer_repo", return_value=True)
    def test_skips_consumer_repo(self, _mock, mock_stdin: Callable[[str], None]):
        mock_stdin(_bash_payload(_BLOCKING_CMD))
        assert guard.main() == 0

    @patch.object(guard, "skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_tty(self, _mock, monkeypatch):
        monkeypatch.setattr("sys.stdin", MagicMock(isatty=lambda: True))
        assert guard.main() == 0

    @patch.object(guard, "skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_empty_input(self, _mock, mock_stdin: Callable[[str], None]):
        mock_stdin("")
        assert guard.main() == 0

    @patch.object(guard, "skip_if_consumer_repo", return_value=False)
    def test_exits_0_on_invalid_json(self, _mock, mock_stdin: Callable[[str], None]):
        mock_stdin("not json")
        assert guard.main() == 0

    @patch.object(guard, "skip_if_consumer_repo", return_value=False)
    def test_exits_0_for_wrong_tool_name(self, _mock, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Grep", "tool_input": {"pattern": "Foo"}}))
        assert guard.main() == 0

    @patch.object(guard, "skip_if_consumer_repo", return_value=False)
    def test_exits_0_for_missing_tool_input(self, _mock, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Bash"}))
        assert guard.main() == 0

    @patch.object(guard, "skip_if_consumer_repo", return_value=False)
    def test_exits_0_for_non_dict_tool_input(self, _mock, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Bash", "tool_input": "string"}))
        assert guard.main() == 0

    @patch.object(guard, "skip_if_consumer_repo", return_value=False)
    def test_exits_0_for_missing_command(self, _mock, mock_stdin: Callable[[str], None]):
        mock_stdin(json.dumps({"tool_name": "Bash", "tool_input": {"command": ""}}))
        assert guard.main() == 0

    @patch.object(guard, "skip_if_consumer_repo", return_value=False)
    @patch.object(guard, "get_project_directory", side_effect=RuntimeError("boom"))
    def test_fails_open_on_exception(
        self, _mock_dir, _mock_skip, mock_stdin: Callable[[str], None], capsys
    ):
        mock_stdin(_bash_payload(_BLOCKING_CMD))
        result = guard.main()
        assert result == 0
        captured = capsys.readouterr()
        assert "lsp-bash-grep-guard error" in captured.err


# ---------------------------------------------------------------------------
# Subprocess (real stdin) + runpy entry-point coverage
# ---------------------------------------------------------------------------


class TestSubprocessAndEntryPoint:
    def _run(self, payload: str, env_extra: dict | None = None):
        import os

        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = str(REPO_ROOT)
        env.pop("SKIP_LSP_GATE", None)
        env.pop("LSP_GATE_MODE", None)
        if env_extra:
            env.update(env_extra)
        return subprocess.run(
            [sys.executable, str(HOOK_PATH)],
            input=payload,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(REPO_ROOT),
            check=False,
        )

    def test_subprocess_blocks_with_exit_2(self):
        proc = self._run(_bash_payload(_BLOCKING_CMD))
        assert proc.returncode == 2
        assert "BLOCKED" in proc.stdout

    def test_subprocess_allows_git_grep(self):
        proc = self._run(_bash_payload('git grep "parseConfig" -- src/app.py'))
        assert proc.returncode == 0

    def test_subprocess_kill_switch(self):
        proc = self._run(_bash_payload(_BLOCKING_CMD), env_extra={"SKIP_LSP_GATE": "true"})
        assert proc.returncode == 0

    def test_subprocess_warn_mode(self):
        proc = self._run(_bash_payload(_BLOCKING_CMD), env_extra={"LSP_GATE_MODE": "warn"})
        assert proc.returncode == 0
        assert "BLOCKED" in proc.stdout

    def test_runpy_entrypoint_exits_0_on_empty(self, monkeypatch, mock_stdin):
        """Exercise the ``if __name__ == '__main__'`` block via runpy."""
        import runpy

        monkeypatch.setenv("SKIP_LSP_GATE", "true")
        mock_stdin("")
        with pytest.raises(SystemExit) as exc:
            runpy.run_path(str(HOOK_PATH), run_name="__main__")
        assert exc.value.code == 0
