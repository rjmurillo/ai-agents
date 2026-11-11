"""Tests for plugin-mode hook guard utilities."""

from __future__ import annotations

import json
import subprocess
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


def _remote_v(**remotes: str) -> str:
    """Render ``git remote -v`` output for the given name=url pairs."""
    lines: list[str] = []
    for name, url in remotes.items():
        lines.append(f"{name}\t{url} (fetch)")
        lines.append(f"{name}\t{url} (push)")
    return "\n".join(lines) + "\n"


def _stub_remotes(monkeypatch: pytest.MonkeyPatch, **remotes: str) -> None:
    monkeypatch.setattr(guards.shutil, "which", lambda _name: "git")
    monkeypatch.setattr(
        guards.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=_remote_v(**remotes), stderr=""),
    )


class TestIsProjectRepo:
    """is_project_repo resolves identity from the env override or git remote (#2610, #7227)."""

    @pytest.fixture(autouse=True)
    def _fresh_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AI_AGENTS_PROJECT_REPO", raising=False)
        guards._origin_repo_cache.clear()

    def test_env_override_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_AGENTS_PROJECT_REPO", "1")
        assert is_project_repo() is True

    def test_env_override_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_AGENTS_PROJECT_REPO", "0")
        assert is_project_repo() is False

    def test_env_override_true_wins_over_a_foreign_remote(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_remotes(monkeypatch, origin="https://github.com/acme/ai-agents.git")
        monkeypatch.setenv("AI_AGENTS_PROJECT_REPO", "1")
        assert is_project_repo() is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/rjmurillo/ai-agents.git",
            "https://github.com/rjmurillo/ai-agents",
            "git@github.com:rjmurillo/ai-agents.git",
            "ssh://git@github.com/rjmurillo/ai-agents.git",
            "https://github.com/RJMurillo/AI-Agents.git",
        ],
    )
    def test_project_remote_is_project(self, url: str, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_remotes(monkeypatch, origin=url)
        assert is_project_repo() is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://github.com/acme/ai-agents.git",
            "git@github.com:acme/ai-agents.git",
            "ssh://git@github.com/acme/ai-agents.git",
        ],
    )
    def test_same_name_other_owner_is_consumer(
        self, url: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_remotes(monkeypatch, origin=url)
        assert is_project_repo() is False

    def test_remote_other_repo_is_consumer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A consumer repo with its own .agents/ (e.g. a vendored install) must
        # not be mistaken for the project repo just because that dir exists.
        _stub_remotes(
            monkeypatch, origin="git@github.com:org/Wcd.Infra.ConfigurationGeneration2.git"
        )
        assert is_project_repo() is False

    def test_fork_with_project_upstream_is_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_remotes(
            monkeypatch,
            origin="https://github.com/contributor/ai-agents.git",
            upstream="https://github.com/rjmurillo/ai-agents.git",
        )
        assert is_project_repo() is True

    def test_fork_with_foreign_upstream_is_consumer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_remotes(
            monkeypatch,
            origin="https://github.com/contributor/ai-agents.git",
            upstream="https://github.com/acme/ai-agents.git",
        )
        assert is_project_repo() is False

    def test_upstream_alone_without_origin_is_not_project(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_remotes(monkeypatch, upstream="https://github.com/rjmurillo/ai-agents.git")
        assert is_project_repo() is False
        assert guards._project_repo_identity() == "unknown"

    def test_no_remote_is_not_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(guards, "_remote_urls", lambda _root: None)
        assert is_project_repo() is False


class TestRepoSlug:
    """_repo_slug returns lowercase owner/name across HTTPS and SSH forms."""

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://github.com/rjmurillo/ai-agents.git", "rjmurillo/ai-agents"),
            ("https://github.com/rjmurillo/ai-agents", "rjmurillo/ai-agents"),
            ("https://github.com/rjmurillo/ai-agents/", "rjmurillo/ai-agents"),
            ("git@github.com:rjmurillo/ai-agents.git", "rjmurillo/ai-agents"),
            ("ssh://git@github.com:22/rjmurillo/ai-agents.git", "rjmurillo/ai-agents"),
            ("https://token@github.com/Acme/AI-Agents.git", "acme/ai-agents"),
            (
                "git@github.com:org/Wcd.Infra.ConfigurationGeneration2.git",
                "org/wcd.infra.configurationgeneration2",
            ),
            ("/srv/git/ai-agents.git", "git/ai-agents"),
        ],
    )
    def test_parses_remote_url(self, url: str, expected: str) -> None:
        assert guards._repo_slug(url) == expected

    @pytest.mark.parametrize("url", ["", "ai-agents", "https://github.com", "host:ai-agents"])
    def test_url_without_owner_yields_none(self, url: str) -> None:
        assert guards._repo_slug(url) is None


class TestRemoteUrls:
    """_remote_urls reads fetch URLs from one bounded ``git remote -v`` call."""

    def test_parses_fetch_lines_by_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _stub_remotes(
            monkeypatch,
            origin="https://github.com/a/b.git",
            upstream="git@github.com:rjmurillo/ai-agents.git",
        )
        assert guards._remote_urls("/repo") == {
            "origin": "https://github.com/a/b.git",
            "upstream": "git@github.com:rjmurillo/ai-agents.git",
        }

    def test_repository_with_no_remotes_returns_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(guards.shutil, "which", lambda _name: "git")
        monkeypatch.setattr(
            guards.subprocess,
            "run",
            lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout="", stderr=""),
        )
        assert guards._remote_urls("/repo") == {}

    def test_git_failure_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(guards.shutil, "which", lambda _name: "git")

        def raise_not_a_repo(*a, **k):
            raise subprocess.CalledProcessError(128, a, stderr="not a git repository")

        monkeypatch.setattr(guards.subprocess, "run", raise_not_a_repo)
        assert guards._remote_urls("/repo") is None

    def test_git_timeout_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(guards.shutil, "which", lambda _name: "git")

        def hang(*a, **k):
            raise subprocess.TimeoutExpired(a, 1)

        monkeypatch.setattr(guards.subprocess, "run", hang)
        assert guards._remote_urls("/repo") is None

    def test_lookup_runs_one_subprocess(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[object] = []
        monkeypatch.setattr(guards.shutil, "which", lambda _name: "git")

        def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            return subprocess.CompletedProcess(
                ["git", "remote", "-v"],
                0,
                stdout=_remote_v(origin="https://github.com/a/b.git"),
                stderr="",
            )

        monkeypatch.setattr(guards.subprocess, "run", fake_run)
        guards._origin_repo_cache.clear()
        monkeypatch.delenv("AI_AGENTS_PROJECT_REPO", raising=False)
        guards._project_remote_identity("/repo")
        assert len(calls) == 1

    def test_origin_lookup_uses_utf8_and_check_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured_kwargs: dict[str, object] = {}

        def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            captured_kwargs.update(kwargs)
            return subprocess.CompletedProcess(
                ["git", "-C", "/repo", "remote", "-v"],
                0,
                stdout=_remote_v(origin="https://github.com/rjmurillo/ai-agents.git"),
                stderr="",
            )

        monkeypatch.setattr(guards.shutil, "which", lambda _name: "git")
        monkeypatch.setattr(guards.subprocess, "run", fake_run)

        assert guards._remote_urls("/repo") == {
            "origin": "https://github.com/rjmurillo/ai-agents.git"
        }
        assert captured_kwargs["encoding"] == "utf-8"
        assert captured_kwargs["errors"] == "replace"
        assert captured_kwargs["check"] is True

    def test_origin_lookup_timeout_under_host_budget(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The per-tool-call git lookup must finish inside the tightest host timeout.

        ``skip_if_consumer_repo`` calls ``_remote_urls`` on every tool use,
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
                ["git", "-C", "/repo", "remote", "-v"],
                0,
                stdout=_remote_v(origin="https://github.com/rjmurillo/ai-agents.git"),
                stderr="",
            )

        monkeypatch.setattr(guards.shutil, "which", lambda _name: "git")
        monkeypatch.setattr(guards.subprocess, "run", fake_run)

        assert guards._remote_urls("/repo") is not None
        git_timeout = captured_kwargs.get("timeout")
        assert isinstance(git_timeout, (int, float)), "git lookup must pass a timeout"
        assert git_timeout < tightest_host_timeout, (
            f"git lookup timeout {git_timeout}s must be < tightest host hook "
            f"timeout {tightest_host_timeout}s so a slow git degrades to None "
            "instead of the host SIGKILLing the hook into a 'hook errored' deny"
        )

    def test_git_missing_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(guards.shutil, "which", lambda _name: None)
        assert guards._remote_urls("/repo") is None


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
        monkeypatch.setattr(guards, "_remote_urls", lambda _root: None)

        assert skip_if_consumer_repo("test-hook") is True
        captured = capsys.readouterr()
        assert "[SKIP] test-hook" in captured.err
        assert "cannot verify ai-agents project repo identity" in captured.err


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
        monkeypatch.setattr(guards, "_remote_urls", lambda _root: None)

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
