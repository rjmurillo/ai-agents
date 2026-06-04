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

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

_HOOK_DIR = Path(__file__).resolve().parents[2] / ".claude" / "hooks" / "PreToolUse"


def _load_guard_module():
    """Import invoke_hook_drift_guard without polluting sys.path globally."""
    module_path = _HOOK_DIR / "invoke_hook_drift_guard.py"
    # Temporarily add the hook dir to sys.path for the import, then remove it.
    hook_dir_str = str(_HOOK_DIR)
    already_present = hook_dir_str in sys.path
    if not already_present:
        sys.path.insert(0, hook_dir_str)
    try:
        if "invoke_hook_drift_guard" in sys.modules:
            return sys.modules["invoke_hook_drift_guard"]
        spec = importlib.util.spec_from_file_location(
            "invoke_hook_drift_guard", module_path
        )
        assert spec is not None
        assert spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        sys.modules["invoke_hook_drift_guard"] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if not already_present and hook_dir_str in sys.path:
            sys.path.remove(hook_dir_str)


guard = _load_guard_module()


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
        # _hook_diff_paths is called twice: pre-existing snapshot then post-run.
        diff_calls: list[int] = []

        def no_diff(_root):
            diff_calls.append(1)
            return []

        monkeypatch.setattr(guard, "_hook_diff_paths", no_diff)
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
        # _hook_diff_paths called twice: both return empty (no pre-existing, no drift).
        diff_calls: list[int] = []

        def no_diff(_root):
            diff_calls.append(1)
            return []

        monkeypatch.setattr(guard, "_hook_diff_paths", no_diff)
        assert guard._validate([], []) == []
        assert len(diff_calls) == 2, "expected pre+post snapshot calls"

    def test_returns_block_message_on_hook_path_drift(self, monkeypatch):
        # Real drift: generator wrote new content on disk. First call
        # returns empty (no pre-existing changes); second call returns the
        # drifted paths introduced by the generator run.
        gh = SimpleNamespace()
        gh.generate_hooks = MagicMock(return_value=(0, SimpleNamespace(written=37)))
        monkeypatch.setattr(
            guard,
            "_import_generator",
            lambda: (gh, Path("/repo/cfg.yaml"), Path("/repo")),
        )
        drifted_paths = [
            "src/copilot-cli/hooks/preToolUse/invoke_x__Bash_abc.py",
            "src/copilot-cli/hooks/postToolUse/invoke_y__Edit_def.py",
        ]
        diff_calls: list[int] = []

        def staged_diff(_root):
            diff_calls.append(1)
            if len(diff_calls) == 1:
                # Pre-existing snapshot: no prior changes.
                return []
            return drifted_paths

        monkeypatch.setattr(guard, "_hook_diff_paths", staged_diff)
        # K1 (REQ-008-09): a drift block is the raw K1 signal. Capture the
        # emission so the test pins that a block records exactly one K1
        # event carrying the drifted paths.
        k1_calls: list[str] = []
        monkeypatch.setattr(guard, "_emit_k1", lambda detail: k1_calls.append(detail))
        out = guard._validate([], [])
        assert out
        # Exactly one K1 event, listing the drifted paths.
        assert len(k1_calls) == 1
        assert "invoke_x__Bash_abc.py" in k1_calls[0]
        assert "invoke_y__Edit_def.py" in k1_calls[0]
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

    def test_pre_existing_changes_do_not_cause_false_positive(self, monkeypatch):
        # If hook paths already have local modifications before the generator
        # runs, those must not be reported as generator-introduced drift.
        gh = SimpleNamespace()
        gh.generate_hooks = MagicMock(return_value=(0, SimpleNamespace(written=37)))
        monkeypatch.setattr(
            guard,
            "_import_generator",
            lambda: (gh, Path("/repo/cfg.yaml"), Path("/repo")),
        )
        pre_existing = ["src/copilot-cli/hooks/preToolUse/unrelated.py"]
        diff_calls: list[int] = []

        def same_diff(_root):
            diff_calls.append(1)
            # Both pre and post snapshots return the same pre-existing path.
            return pre_existing

        monkeypatch.setattr(guard, "_hook_diff_paths", same_diff)
        assert guard._validate([], []) == []


class TestHookDiffPaths:
    """Tests for _hook_diff_paths (subprocess git-diff parsing)."""

    def _make_run_side_effect(self, diff_stdout: str, untracked_stdout: str):
        """Return a side_effect callable that dispatches by command args."""
        def run_side_effect(cmd, **kwargs):
            fake = MagicMock()
            fake.returncode = 0
            if "ls-files" in cmd:
                fake.stdout = untracked_stdout
            else:
                fake.stdout = diff_stdout
            return fake

        return run_side_effect

    def test_filters_only_hook_paths(self):
        side_effect = self._make_run_side_effect(
            diff_stdout=(
                "src/copilot-cli/hooks/preToolUse/invoke_x__Bash_abc.py\n"
                "src/copilot-cli/agents/architect.agent.md\n"
                ".github/workflows/test.yml\n"
                "src/copilot-cli/hooks/postToolUse/invoke_y__Edit_def.py\n"
            ),
            untracked_stdout="",
        )
        with patch.object(guard.subprocess, "run", side_effect=side_effect):
            paths = guard._hook_diff_paths(Path("/repo"))
        assert "src/copilot-cli/hooks/preToolUse/invoke_x__Bash_abc.py" in paths
        assert "src/copilot-cli/hooks/postToolUse/invoke_y__Edit_def.py" in paths
        assert "src/copilot-cli/agents/architect.agent.md" not in paths
        assert ".github/workflows/test.yml" not in paths

    def test_includes_untracked_shim_files(self):
        # generate_hooks may create new shim files that are untracked.
        # _hook_diff_paths must include them so drift is not missed.
        side_effect = self._make_run_side_effect(
            diff_stdout="",
            untracked_stdout=(
                "src/copilot-cli/hooks/preToolUse/invoke_new__Bash_xyz.py\n"
            ),
        )
        with patch.object(guard.subprocess, "run", side_effect=side_effect):
            paths = guard._hook_diff_paths(Path("/repo"))
        assert "src/copilot-cli/hooks/preToolUse/invoke_new__Bash_xyz.py" in paths

    def test_returns_empty_on_git_failure(self):
        def failing_run(cmd, **kwargs):
            fake = MagicMock()
            fake.returncode = 128
            fake.stdout = ""
            return fake

        with patch.object(guard.subprocess, "run", side_effect=failing_run):
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
            side_effect=_sp.TimeoutExpired(cmd="git", timeout=5),
        ):
            assert guard._hook_diff_paths(Path("/repo")) == []

    def test_returns_empty_when_git_not_on_path(self):
        # shutil.which("git") returns None when git is not on PATH.
        # The guard must fail-open (return []) without calling subprocess.
        with patch.object(guard.shutil, "which", return_value=None):
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


class TestEmitK1:
    """Tests for _emit_k1 (REQ-008-09 K1 telemetry, fail-open)."""

    def test_loads_emitter_and_records_k1(self, monkeypatch, tmp_path):
        # _emit_k1 loads scripts/metrics/kill_criteria.py by file path and
        # calls emit_event("K1", detail). The fake emitter records its
        # arguments to a marker file so the test reads what was passed
        # after the module was exec'd inside the helper.
        marker = tmp_path / "k1.marker"
        emitter = tmp_path / "scripts" / "metrics" / "kill_criteria.py"
        emitter.parent.mkdir(parents=True)
        emitter.write_text(
            "from pathlib import Path\n"
            f"_MARKER = Path({str(marker)!r})\n"
            "def emit_event(kind, detail):\n"
            "    _MARKER.write_text(f'{kind}\\t{detail}', encoding='utf-8')\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(guard, "get_project_directory", lambda: str(tmp_path))

        guard._emit_k1("a/b.py,c/d.py")

        assert marker.is_file(), "emitter was not invoked"
        kind, detail = marker.read_text(encoding="utf-8").split("\t", 1)
        assert kind == "K1"
        assert detail == "a/b.py,c/d.py"

    def test_fail_open_when_emitter_missing(self, monkeypatch, tmp_path):
        # No scripts/metrics/kill_criteria.py under the project dir: must
        # not raise. A telemetry gap can never block a push.
        monkeypatch.setattr(guard, "get_project_directory", lambda: str(tmp_path))
        guard._emit_k1("x/y.py")  # no exception == pass

    def test_fail_open_when_emitter_raises(self, monkeypatch, tmp_path):
        # An emitter that raises on import must be swallowed.
        emitter = tmp_path / "scripts" / "metrics" / "kill_criteria.py"
        emitter.parent.mkdir(parents=True)
        emitter.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
        monkeypatch.setattr(guard, "get_project_directory", lambda: str(tmp_path))
        guard._emit_k1("x/y.py")  # no exception == pass

    def test_fail_open_when_get_project_directory_raises(self, monkeypatch):
        # Even a failure resolving the project dir must not propagate.
        def boom() -> str:
            raise OSError("no cwd")

        monkeypatch.setattr(guard, "get_project_directory", boom)
        guard._emit_k1("x/y.py")  # no exception == pass
