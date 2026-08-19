"""Tests for plugin-mode hook guard utilities."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.hook_utilities import guards
from scripts.hook_utilities.guards import is_project_repo, skip_if_consumer_repo

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_copilot_pretooluse_has_no_unregistered_matcher_shims() -> None:
    """The distributed plugin contains only manifest-addressable shims.

    ADR-097 retired every tool-call hook, so there is no manifest and no shim
    today. The invariant is unchanged and still armed: what must never ship is a
    shim the manifest does not address. Expressing it as a set comparison that
    tolerates the empty case keeps it firing the moment a hook is re-added,
    rather than deleting a guard whose subject is only temporarily absent.
    """
    event_directory = REPO_ROOT / "src" / "copilot-cli" / "hooks" / "PreToolUse"
    manifest_path = event_directory / "_manifest.json"

    registered: set[str] = set()
    if manifest_path.is_file():
        registered = set(json.loads(manifest_path.read_text(encoding="utf-8"))["shims"])
    generated = {path.name for path in event_directory.glob("*__*.py")}

    assert generated == registered

class TestIsProjectRepo:
    """is_project_repo resolves identity from the env override or git remote (#2610)."""

    def test_env_override_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_AGENTS_PROJECT_REPO", "1")
        assert is_project_repo() is True

    def test_env_override_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_AGENTS_PROJECT_REPO", "0")
        assert is_project_repo() is False

    def test_remote_ai_agents_is_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AI_AGENTS_PROJECT_REPO", raising=False)
        guards._origin_repo_cache.clear()
        monkeypatch.setattr(guards, "_remote_repo_name", lambda _root: "ai-agents")
        assert is_project_repo() is True

    def test_remote_other_repo_is_consumer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A consumer repo with its own .agents/ (e.g. a vendored install) must
        # not be mistaken for the project repo just because that dir exists.
        monkeypatch.delenv("AI_AGENTS_PROJECT_REPO", raising=False)
        guards._origin_repo_cache.clear()
        monkeypatch.setattr(
            guards, "_remote_repo_name", lambda _root: "Wcd.Infra.ConfigurationGeneration2"
        )
        assert is_project_repo() is False

    def test_no_remote_is_not_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AI_AGENTS_PROJECT_REPO", raising=False)
        guards._origin_repo_cache.clear()
        monkeypatch.setattr(guards, "_remote_repo_name", lambda _root: None)
        assert is_project_repo() is False


class TestRemoteRepoName:
    """_remote_repo_name parses the origin URL across HTTPS and SSH forms."""

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://github.com/rjmurillo/ai-agents.git", "ai-agents"),
            ("https://github.com/rjmurillo/ai-agents", "ai-agents"),
            ("git@github.com:rjmurillo/ai-agents.git", "ai-agents"),
            (
                "git@github.com:org/Wcd.Infra.ConfigurationGeneration2.git",
                "Wcd.Infra.ConfigurationGeneration2",
            ),
        ],
    )
    def test_parses_remote_url(
        self, url: str, expected: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(guards.shutil, "which", lambda _name: "git")
        monkeypatch.setattr(
            guards.subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=url + "\n", stderr=""),
        )
        assert guards._remote_repo_name("/repo") == expected

    def test_no_origin_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(guards.shutil, "which", lambda _name: "git")

        def raise_no_origin(*a, **k):
            raise subprocess.CalledProcessError(2, a, stderr="no origin")

        monkeypatch.setattr(guards.subprocess, "run", raise_no_origin)
        assert guards._remote_repo_name("/repo") is None

    def test_origin_lookup_uses_utf8_and_check_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured_kwargs: dict[str, object] = {}

        def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_kwargs.update(kwargs)
            return subprocess.CompletedProcess(
                ["git", "-C", "/repo", "remote", "get-url", "origin"],
                0,
                stdout="ai-agents\n",
                stderr="",
            )

        monkeypatch.setattr(guards.shutil, "which", lambda _name: "git")
        monkeypatch.setattr(guards.subprocess, "run", fake_run)

        assert guards._remote_repo_name("/repo") == "ai-agents"
        assert captured_kwargs["encoding"] == "utf-8"
        assert captured_kwargs["errors"] == "replace"
        assert captured_kwargs["check"] is True

    def test_origin_lookup_timeout_under_host_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The per-tool-call git lookup must finish inside the tightest host timeout.

        ``skip_if_consumer_repo`` calls ``_remote_repo_name`` on every tool use,
        and project-only hooks invoke it. If this git subprocess timeout is
        >= a host hook's timeout, a slow or hung git lets the host SIGKILL the
        whole hook before the caller can fail open, which Copilot surfaces as a
        hard "hook errored" deny of every command (repo-settings Bash-hook
        wedge). Guard the invariant so a future edit cannot reintroduce it:
        git timeout must be strictly under the tightest configured host timeout.
        """
        settings_path = REPO_ROOT / ".claude" / "settings.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        host_timeouts: list[int] = []
        for groups in settings.get("hooks", {}).values():
            for group in groups:
                if not isinstance(group, dict):
                    continue
                for entry in group.get("hooks", []):
                    if isinstance(entry, dict) and isinstance(entry.get("timeout"), int):
                        host_timeouts.append(entry["timeout"])
        assert host_timeouts, "expected explicit hook timeouts in settings.json"
        tightest_host_timeout = min(host_timeouts)

        captured_kwargs: dict[str, object] = {}

        def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_kwargs.update(kwargs)
            return subprocess.CompletedProcess(
                ["git", "-C", "/repo", "remote", "get-url", "origin"],
                0,
                stdout="ai-agents\n",
                stderr="",
            )

        monkeypatch.setattr(guards.shutil, "which", lambda _name: "git")
        monkeypatch.setattr(guards.subprocess, "run", fake_run)

        assert guards._remote_repo_name("/repo") == "ai-agents"
        git_timeout = captured_kwargs.get("timeout")
        assert isinstance(git_timeout, (int, float)), "git lookup must pass a timeout"
        assert git_timeout < tightest_host_timeout, (
            f"git lookup timeout {git_timeout}s must be < tightest host hook "
            f"timeout {tightest_host_timeout}s so a slow git degrades to None "
            "instead of the host SIGKILLing the hook into a 'hook errored' deny"
        )

    def test_git_missing_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(guards.shutil, "which", lambda _name: None)
        assert guards._remote_repo_name("/repo") is None


class TestSkipIfConsumerRepo:
    def test_returns_false_in_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_AGENTS_PROJECT_REPO", "1")
        assert skip_if_consumer_repo("test-hook") is False

    def test_returns_true_in_consumer(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("AI_AGENTS_PROJECT_REPO", "0")
        assert skip_if_consumer_repo("test-hook") is True
        captured = capsys.readouterr()
        assert "[SKIP] test-hook" in captured.err
        assert "consumer repo" in captured.err

    def test_skips_when_repo_identity_unknown(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("AI_AGENTS_PROJECT_REPO", raising=False)
        guards._origin_repo_cache.clear()
        monkeypatch.setattr(guards, "get_project_directory", lambda: "/repo")
        monkeypatch.setattr(guards, "_remote_repo_name", lambda _root: None)

        assert skip_if_consumer_repo("test-hook") is True
        captured = capsys.readouterr()
        assert "[SKIP] test-hook" in captured.err
        assert "cannot verify ai-agents project repo identity" in captured.err


class TestSyncPluginLib:
    """Test the sync_plugin_lib.py script."""

    def test_check_passes_when_in_sync(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "sync_plugin_lib.py"), "--check"],
            capture_output=True,
            text=True, encoding="utf-8",
            cwd=str(REPO_ROOT),
            timeout=10,
        )
        assert result.returncode == 0, (
            f"Sync check failed (files out of sync):\n{result.stdout}\n{result.stderr}"
        )

    def test_check_detects_drift(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Create mismatched src/dst files and verify --check returns 1."""
        import scripts.sync_plugin_lib as sync_mod

        # Build a minimal src package with one Python file
        src_dir = tmp_path / "src_pkg"
        src_dir.mkdir()
        (src_dir / "__init__.py").write_text('"""Original source."""\n', encoding="utf-8")

        # Build a dst directory with stale content (drift)
        dst_dir = tmp_path / "dst_pkg"
        dst_dir.mkdir()
        (dst_dir / "__init__.py").write_text('"""Stale copy."""\n', encoding="utf-8")

        # Patch module-level config to use our temp directories
        monkeypatch.setattr(sync_mod, "REPO_ROOT", tmp_path)
        monkeypatch.setattr(sync_mod, "SYNC_PAIRS", [("src_pkg", "dst_pkg")])
        monkeypatch.setattr(sync_mod, "IMPORT_CONVERSIONS", [])

        result = sync_mod.main(["--check"])
        assert result == 1

    def test_sync_file_creates_missing_dest(self, tmp_path: Path) -> None:
        """sync_file byte-copies the source when the destination is absent."""
        import scripts.sync_plugin_lib as sync_mod

        src = tmp_path / "scripts" / "pkg" / "mod.py"
        src.parent.mkdir(parents=True)
        src.write_text('"""Self-contained module."""\nX = 1\n', encoding="utf-8")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sync_mod, "REPO_ROOT", tmp_path)
            changes, had_errors = sync_mod.sync_file(
                "scripts/pkg/mod.py",
                ".claude/lib/mod.py",
                check_only=False,
            )

        assert had_errors is False, changes
        dst = tmp_path / ".claude" / "lib" / "mod.py"
        # Byte-identical copy: no canonical-note rewrite for top-level files.
        assert dst.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")

    def test_sync_file_check_detects_drift(self, tmp_path: Path) -> None:
        """A drifted top-level lib file makes main(--check) return 1."""
        import scripts.sync_plugin_lib as sync_mod

        src = tmp_path / "scripts" / "pkg" / "mod.py"
        src.parent.mkdir(parents=True)
        src.write_text('"""Canonical."""\nX = 1\n', encoding="utf-8")
        dst = tmp_path / ".claude" / "lib" / "mod.py"
        dst.parent.mkdir(parents=True)
        dst.write_text('"""Stale."""\nX = 2\n', encoding="utf-8")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sync_mod, "REPO_ROOT", tmp_path)
            mp.setattr(sync_mod, "SYNC_PAIRS", [])
            mp.setattr(
                sync_mod,
                "SYNC_FILE_PAIRS",
                [("scripts/pkg/mod.py", ".claude/lib/mod.py")],
            )
            assert sync_mod.main(["--check"]) == 1

    @pytest.mark.parametrize(
        "import_line",
        [
            "from scripts.pkg.other import thing",
            "import scripts.pkg.other",
            "from scripts import other",
            "import scripts",
            "import scripts as s",
            "import os, scripts",
            "import os as o, scripts",
            "import os, \\\n    scripts",
            'x = __import__("scripts.hook_utilities.bootstrap")',
            'import importlib\ny = importlib.import_module("scripts.pkg")',
            'z = __import__("scripts")',
            'import importlib\ny = importlib.import_module(name="scripts.pkg")',
            'w = __import__(name="scripts")',
            'from importlib import import_module\nq = import_module("scripts.pkg")',
        ],
    )
    def test_sync_file_rejects_scripts_import(self, tmp_path: Path, import_line: str) -> None:
        """Any scripts-package import is rejected (a byte copy cannot rewrite it)."""
        import scripts.sync_plugin_lib as sync_mod

        src = tmp_path / "scripts" / "pkg" / "mod.py"
        src.parent.mkdir(parents=True)
        src.write_text(
            f'"""Not self-contained."""\n{import_line}\n',
            encoding="utf-8",
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sync_mod, "REPO_ROOT", tmp_path)
            changes, had_errors = sync_mod.sync_file(
                "scripts/pkg/mod.py",
                ".claude/lib/mod.py",
                check_only=False,
            )

        assert had_errors is True
        assert any("scripts package" in c for c in changes), changes
        assert not (tmp_path / ".claude" / "lib" / "mod.py").exists()

    @pytest.mark.parametrize(
        "import_line",
        [
            "import scripts_helper",
            "from scripts_util import thing",
            "import scriptsfoo",
            'x = __import__("scripts_helper")',
            'import importlib\ny = importlib.import_module("other.pkg")',
        ],
    )
    def test_sync_file_allows_lookalike_module(self, tmp_path: Path, import_line: str) -> None:
        """Modules whose name merely starts with 'scripts' are not the scripts pkg."""
        import scripts.sync_plugin_lib as sync_mod

        src = tmp_path / "scripts" / "pkg" / "mod.py"
        src.parent.mkdir(parents=True)
        src.write_text(
            f'"""Self-contained."""\n{import_line}\n',
            encoding="utf-8",
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sync_mod, "REPO_ROOT", tmp_path)
            changes, had_errors = sync_mod.sync_file(
                "scripts/pkg/mod.py",
                ".claude/lib/mod.py",
                check_only=False,
            )

        assert had_errors is False, changes
        assert (tmp_path / ".claude" / "lib" / "mod.py").read_text(
            encoding="utf-8"
        ) == src.read_text(encoding="utf-8")

    def test_sync_file_missing_source_fails_closed(self, tmp_path: Path) -> None:
        """A registered source that does not exist is an error, not a silent pass."""
        import scripts.sync_plugin_lib as sync_mod

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sync_mod, "REPO_ROOT", tmp_path)
            changes, had_errors = sync_mod.sync_file(
                "scripts/pkg/missing.py",
                ".claude/lib/missing.py",
                check_only=True,
            )

        assert had_errors is True
        assert any("Registered source file missing" in c for c in changes), changes
        assert not (tmp_path / ".claude" / "lib" / "missing.py").exists()

    def test_sync_file_preserves_bytes_and_detects_newline_drift(self, tmp_path: Path) -> None:
        """Copy preserves exact bytes; CRLF-vs-LF is drift, not silent normalization."""
        import scripts.sync_plugin_lib as sync_mod

        src = tmp_path / "scripts" / "pkg" / "mod.py"
        src.parent.mkdir(parents=True)
        src.write_bytes(b'"""Canonical."""\r\nX = 1\r\n')
        dst = tmp_path / ".claude" / "lib" / "mod.py"
        dst.parent.mkdir(parents=True)
        # Same text under universal newlines, but different bytes (LF vs CRLF).
        dst.write_bytes(b'"""Canonical."""\nX = 1\n')

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(sync_mod, "REPO_ROOT", tmp_path)
            # --check must flag the byte drift even though text decodes equal.
            check_changes, check_errors = sync_mod.sync_file(
                "scripts/pkg/mod.py",
                ".claude/lib/mod.py",
                check_only=True,
            )
            assert check_errors is False, check_changes
            assert check_changes, "CRLF/LF byte drift should be detected"
            assert dst.read_bytes() == b'"""Canonical."""\nX = 1\n', (
                "check_only must not mutate the destination"
            )

            # Real sync writes the source bytes verbatim (CRLF preserved).
            sync_mod.sync_file(
                "scripts/pkg/mod.py",
                ".claude/lib/mod.py",
                check_only=False,
            )

        assert dst.read_bytes() == b'"""Canonical."""\r\nX = 1\r\n'

    def test_validate_review_marker_pair_is_registered(self) -> None:
        """sync_file --check now enforces the review marker skill copy."""
        import scripts.sync_plugin_lib as sync_mod

        pair = (
            "scripts/validation/validate_review_marker.py",
            ".claude/skills/review/scripts/validate_review_marker.py",
        )
        assert pair in sync_mod.SYNC_FILE_PAIRS


def _parse_events(stderr_text: str) -> list[dict[str, Any]]:
    return [
        json.loads(line[len("EVENT=") :])
        for line in stderr_text.splitlines()
        if line.startswith("EVENT=")
    ]


class TestUnknownIdentityCorroboration:
    """Finding 4 (#2806): when the git origin is unavailable, corroborate project
    identity via pyproject [project].name before skipping every guard, and emit a
    structured fail_open EVENT when the whole-surface skip still happens."""

    def _force_unknown(self, monkeypatch: pytest.MonkeyPatch, project_dir: Path) -> None:
        monkeypatch.delenv("AI_AGENTS_PROJECT_REPO", raising=False)
        guards._origin_repo_cache.clear()
        monkeypatch.setattr(guards, "get_project_directory", lambda: str(project_dir))
        monkeypatch.setattr(guards, "_remote_repo_name", lambda _root: None)

    def test_pyproject_name_corroborates_project_repo(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "ai-agents"\n')
        self._force_unknown(monkeypatch, tmp_path)
        assert skip_if_consumer_repo("test-hook") is False

    def test_other_pyproject_name_skips_and_emits_event(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "other-repo"\n')
        self._force_unknown(monkeypatch, tmp_path)
        assert skip_if_consumer_repo("test-hook") is True
        events = _parse_events(capsys.readouterr().err)
        assert len(events) == 1
        assert events[0]["outcome"] == "fail_open"
        assert events[0]["reason"] == "identity_unknown"
        assert events[0]["guard"] == "test-hook"
        assert events[0]["code"] == "E_TEST_HOOK"

    def test_missing_pyproject_skips_and_emits_event(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._force_unknown(monkeypatch, tmp_path)
        assert skip_if_consumer_repo("test-hook") is True
        events = _parse_events(capsys.readouterr().err)
        assert len(events) == 1
        assert events[0]["reason"] == "identity_unknown"


class TestProjectRepoCorroborated:
    """_project_repo_corroborated reads pyproject [project].name defensively."""

    def test_true_for_ai_agents_name(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "ai-agents"\n')
        assert guards._project_repo_corroborated(str(tmp_path)) is True

    def test_false_for_other_name(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n')
        assert guards._project_repo_corroborated(str(tmp_path)) is False

    def test_false_when_missing(self, tmp_path: Path) -> None:
        assert guards._project_repo_corroborated(str(tmp_path)) is False

    def test_false_when_malformed(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[project\nname = broken")
        assert guards._project_repo_corroborated(str(tmp_path)) is False

    def test_false_when_no_project_table(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[tool.other]\nkey = "v"\n')
        assert guards._project_repo_corroborated(str(tmp_path)) is False
