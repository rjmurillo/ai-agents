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

    ADR-097 left no manifest and no shim. The invariant is unchanged and still
    armed for a re-add: tolerating the empty case beats deleting a guard whose
    subject is only temporarily absent.
    """
    event_directory = REPO_ROOT / "src" / "copilot-cli" / "hooks" / "PreToolUse"
    manifest_path = event_directory / "_manifest.json"
    registered: set[str] = (
        set(json.loads(manifest_path.read_text(encoding="utf-8"))["shims"])
        if manifest_path.is_file()
        else set()
    )
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


class TestSyncPluginLibShim:
    """ADR-109 B5: sync_plugin_lib.py is a thin shim over lib_mirror.compile_all.

    The copy logic itself (`sync_pair`, `sync_file`, `IMPORT_CONVERSIONS`,
    the AST self-containment check) moved to `build/scripts/lib_mirror.py`
    and is exercised there (`tests/build_scripts/test_lib_mirror.py`). This
    class only proves the shim still delegates correctly, since
    `.github/workflows/validate-generated-agents.yml` still calls it
    directly (workflow files are out of scope for the PR that retired the
    rest of this script).
    """

    def test_check_passes_when_in_sync(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "sync_plugin_lib.py"), "--check"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=str(REPO_ROOT),
            timeout=10,
        )
        assert result.returncode == 0, (
            f"Sync check failed (files out of sync):\n{result.stdout}\n{result.stderr}"
        )

    def test_check_detects_drift(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A drifted plugin-tree file makes the shim's --check return 1.

        Every registered package source (PACKAGES: hook_utilities,
        github_core, ai_review_common) must exist, or lib_mirror's
        fail-closed missing-source-directory error also returns 1
        (CodeRabbit, PR #5787 review), and this test would keep passing
        even if the drift check itself were removed or broken. Asserting
        the specific "out of sync" message and the drifted path, not just
        the exit code, closes that gap.
        """
        import scripts.sync_plugin_lib as sync_mod

        for package in ("hook_utilities", "github_core", "ai_review_common"):
            pkg_src = tmp_path / "scripts" / package
            pkg_src.mkdir(parents=True)
            (pkg_src / "__init__.py").write_text("", encoding="utf-8")
        (tmp_path / "scripts" / "hook_utilities" / "bootstrap.py").write_text(
            '"""Bootstrap."""\n', encoding="utf-8"
        )
        (tmp_path / "scripts" / "validation").mkdir(parents=True)
        (tmp_path / "scripts" / "validation" / "validate_review_marker.py").write_text(
            '"""Marker."""\n', encoding="utf-8"
        )
        drifted = tmp_path / "src" / "claude" / "lib" / "hook_utilities"
        drifted.mkdir(parents=True)
        (drifted / "__init__.py").write_text("stale\n", encoding="utf-8")

        monkeypatch.setattr(sync_mod, "_REPO_ROOT", tmp_path)

        rc = sync_mod.main(["--check"])

        assert rc == 1
        stderr = capsys.readouterr().err
        assert "Plugin lib copies are out of sync:" in stderr
        assert "src/claude/lib/hook_utilities/__init__.py" in stderr

    def test_reexports_registry_used_by_validate_sync_registry(self) -> None:
        """SYNC_PAIRS stays importable at its historical name (backward compat)."""
        import scripts.sync_plugin_lib as sync_mod

        assert ("scripts/hook_utilities", ".claude/lib/hook_utilities") in sync_mod.SYNC_PAIRS

    def test_validate_review_marker_pair_is_registered(self) -> None:
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
