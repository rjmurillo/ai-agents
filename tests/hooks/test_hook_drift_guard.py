#!/usr/bin/env python3
"""Tests for invoke_hook_drift_guard.

Covers _validate behavior (the core decision function the push_guard_base
adapter invokes) across the six branches that matter:

- generator import failure -> fail-open (no block message)
- generator raises -> fail-open
- generator non-zero rc -> fail-open
- no drift -> empty block message (allow)
- drift on hook paths -> non-empty block message (block)
- drift outside hook paths -> empty block message (allow)

Tests run against the real .claude/hooks/PreToolUse/invoke_hook_drift_guard.py
module to keep coverage honest. Subprocess + generator are mocked so the
suite stays fast and deterministic.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

HOOK_DIR = str(
    Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"
)
sys.path.insert(0, HOOK_DIR)

import invoke_hook_drift_guard as guard  # noqa: E402


class TestValidate:
    """Tests for _validate (the core decision function)."""

    def test_returns_empty_when_import_fails(self, monkeypatch):
        # _import_generator returns None on any infra failure (build tree
        # absent, import error, missing config). _validate must fail-open
        # so consumer-repo checkouts and degraded environments do not
        # block legitimate pushes.
        monkeypatch.setattr(guard, "_import_generator", lambda: None)
        assert guard._validate([], []) == []

    def test_returns_empty_when_generator_raises(self, monkeypatch):
        # Defensive: an unexpected exception inside generate_hooks must
        # not crash the guard. Fail-open with an EVENT (emitted inside
        # the guard; we only assert the empty-block contract here).
        gh = SimpleNamespace()
        gh.generate_hooks = MagicMock(side_effect=RuntimeError("boom"))
        monkeypatch.setattr(
            guard,
            "_import_generator",
            lambda: (gh, Path("/repo/cfg.yaml"), Path("/repo")),
        )
        assert guard._validate([], []) == []

    def test_returns_empty_when_generator_returns_nonzero(self, monkeypatch):
        # Generator returned a non-zero rc. We do not know whether the
        # output is consistent; fail-open and let CI's full-build check
        # surface the real failure.
        gh = SimpleNamespace()
        gh.generate_hooks = MagicMock(return_value=(1, SimpleNamespace(written=0)))
        monkeypatch.setattr(
            guard,
            "_import_generator",
            lambda: (gh, Path("/repo/cfg.yaml"), Path("/repo")),
        )
        monkeypatch.setattr(guard, "_hook_diff_paths", lambda _root: [])
        assert guard._validate([], []) == []

    def test_returns_empty_when_no_diff(self, monkeypatch):
        # Happy path: generator ran cleanly, no diff on hook paths.
        gh = SimpleNamespace()
        gh.generate_hooks = MagicMock(return_value=(0, SimpleNamespace(written=37)))
        monkeypatch.setattr(
            guard,
            "_import_generator",
            lambda: (gh, Path("/repo/cfg.yaml"), Path("/repo")),
        )
        monkeypatch.setattr(guard, "_hook_diff_paths", lambda _root: [])
        assert guard._validate([], []) == []

    def test_returns_block_message_on_hook_path_drift(self, monkeypatch):
        # Real drift: generator wrote new content on disk and git diff
        # reports two src/copilot-cli/hooks/ paths changed. The block
        # message must name the paths and offer a remediation hint.
        gh = SimpleNamespace()
        gh.generate_hooks = MagicMock(return_value=(0, SimpleNamespace(written=37)))
        monkeypatch.setattr(
            guard,
            "_import_generator",
            lambda: (gh, Path("/repo/cfg.yaml"), Path("/repo")),
        )
        monkeypatch.setattr(
            guard,
            "_hook_diff_paths",
            lambda _root: [
                "src/copilot-cli/hooks/preToolUse/invoke_x__Bash_abc.py",
                "src/copilot-cli/hooks/postToolUse/invoke_y__Edit_def.py",
            ],
        )
        out = guard._validate([], [])
        assert out
        # First line names the failure mode.
        assert "Hook-shim drift detected" in out[0]
        # Drifted paths are listed verbatim.
        assert any(
            "preToolUse/invoke_x__Bash_abc.py" in line for line in out
        )
        assert any(
            "postToolUse/invoke_y__Edit_def.py" in line for line in out
        )
        # Remediation hint cites the canonical fix command.
        assert any("build_all.py" in line for line in out)
        # ADR-061 reference points the reader at the institutional record.
        assert any("ADR-061" in line for line in out)


class TestHookDiffPaths:
    """Tests for _hook_diff_paths (subprocess git-diff parsing)."""

    def test_filters_only_hook_paths(self):
        fake = MagicMock()
        fake.returncode = 0
        fake.stdout = (
            "src/copilot-cli/hooks/preToolUse/invoke_x__Bash_abc.py\n"
            "src/copilot-cli/agents/architect.agent.md\n"
            ".github/workflows/test.yml\n"
            "src/copilot-cli/hooks/postToolUse/invoke_y__Edit_def.py\n"
        )
        with patch.object(guard.subprocess, "run", return_value=fake):
            paths = guard._hook_diff_paths(Path("/repo"))
        assert paths == [
            "src/copilot-cli/hooks/preToolUse/invoke_x__Bash_abc.py",
            "src/copilot-cli/hooks/postToolUse/invoke_y__Edit_def.py",
        ]

    def test_returns_empty_on_git_failure(self):
        fake = MagicMock()
        fake.returncode = 128
        fake.stdout = ""
        with patch.object(guard.subprocess, "run", return_value=fake):
            assert guard._hook_diff_paths(Path("/repo")) == []

    def test_returns_empty_on_missing_git_binary(self):
        with patch.object(
            guard.subprocess, "run", side_effect=FileNotFoundError
        ):
            assert guard._hook_diff_paths(Path("/repo")) == []

    def test_returns_empty_on_git_timeout(self):
        import subprocess as _sp

        with patch.object(
            guard.subprocess,
            "run",
            side_effect=_sp.TimeoutExpired(cmd="git", timeout=10),
        ):
            assert guard._hook_diff_paths(Path("/repo")) == []


class TestGuardWiring:
    """Smoke tests for module-level wiring."""

    def test_guard_name_is_stable(self):
        # Telemetry depends on this string; an accidental rename would
        # break dashboards. Pin it explicitly.
        assert guard.GUARD_NAME == "hook-drift"

    def test_globs_cover_canonical_and_install(self):
        # Globs must cover both ends of the parity: canonical sources
        # under .claude/hooks/ and generated install copies under
        # src/copilot-cli/hooks/. A push that only touches settings.json
        # must also wake the guard (matcher registration change).
        globs = set(guard._GLOBS)
        assert any("claude/hooks" in g for g in globs)
        assert any("copilot-cli/hooks" in g for g in globs)
        assert ".claude/settings.json" in globs

    def test_main_calls_run_guard(self):
        # main() is a one-line shim over run_guard. Verify it actually
        # calls run_guard with the right args (validator, globs, name,
        # include_deletions=False so a deletion-only push does not
        # block).
        with patch.object(guard, "run_guard", return_value=0) as rg:
            rc = guard.main()
        assert rc == 0
        rg.assert_called_once()
        args, kwargs = rg.call_args
        assert args[0] is guard._validate
        assert args[1] == list(guard._GLOBS)
        assert args[2] == guard.GUARD_NAME
        assert kwargs.get("include_deletions") is False
