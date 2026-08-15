"""Tests for the observations-push pre-push subcommand (issue #5071).

The observation-sync-advisory job used lefthook's {push_files}, whose
first-push fallback includes upstream-only files. That fed every tracked
observation file to the sync; without a reachable Forgetful service each file
burns a 10s MCP timeout, so the corpus overran the job's 5m cap and the
timeout kill blocked the push. The subcommand derives the real push range
from the pre-push stdin refs instead (same pattern as issue #4492).

Repo helpers mirror tests/test_push_range_filter.py.
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "validation"
sys.path.insert(0, str(_SCRIPTS))

from scripts.validation import git_hook_policy  # noqa: E402


def _init_repo(root: Path) -> str:
    """Initialise a repo with one empty commit; return the initial commit SHA."""
    for args in (
        ("init", "-q", "-b", "main"),
        ("-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-q", "--allow-empty", "-m", "init"),
    ):
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(root), *args],
            check=True, capture_output=True,
        )
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()


def _commit(root: Path, filename: str, content: str = "x") -> str:
    (root / filename).write_text(content, encoding="utf-8")
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(root),
         "add", filename],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(root),
         "commit", "-qm", f"add {filename}"],
        check=True, capture_output=True,
    )
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout.strip()

class TestHandleObservationsPush:
    """observations-push scopes the advisory sync to the real push range.

    Refs #5071: the {push_files} first-push fallback fed every tracked
    observation file to the sync, and each file burns a 10s MCP timeout when
    no Forgetful service is reachable, overrunning the job's 5m cap.
    """

    def _stdin(self, head: str, base: str) -> io.StringIO:
        return io.StringIO(f"refs/heads/feature {head} refs/heads/feature {base}\n")

    def _handler_args(self, tmp_path: Path) -> Any:
        import argparse

        return argparse.Namespace(repo_root=str(tmp_path))

    def test_syncs_observation_file_in_push_range(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Positive: an observation file changed by the push is synced."""
        base_sha = _init_repo(tmp_path)
        (tmp_path / ".serena" / "memories" / "adr").mkdir(parents=True)
        head_sha = _commit(tmp_path, ".serena/memories/adr/adr-observations.md")
        synced: list[str] = []

        def fake_sync(paths: Any, repo_root: Any) -> int:
            synced.extend(paths)
            return 0

        monkeypatch.setattr(git_hook_policy, "sync_observations", fake_sync)
        monkeypatch.setattr("sys.stdin", self._stdin(head_sha, base_sha))

        rc = git_hook_policy._handle_observations_push(self._handler_args(tmp_path))

        assert rc == 0
        assert synced == [".serena/memories/adr/adr-observations.md"]

    def test_top_level_observation_file_matches(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Edge: fnmatch needs the extra top-level pattern; prove it works."""
        base_sha = _init_repo(tmp_path)
        (tmp_path / ".serena" / "memories").mkdir(parents=True)
        head_sha = _commit(tmp_path, ".serena/memories/heuristics-observations.md")
        synced: list[str] = []

        def fake_sync(paths: Any, repo_root: Any) -> int:
            synced.extend(paths)
            return 0

        monkeypatch.setattr(git_hook_policy, "sync_observations", fake_sync)
        monkeypatch.setattr("sys.stdin", self._stdin(head_sha, base_sha))

        rc = git_hook_policy._handle_observations_push(self._handler_args(tmp_path))

        assert rc == 0
        assert synced == [".serena/memories/heuristics-observations.md"]

    def test_non_observation_change_syncs_nothing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Negative: a push with no observation files never invokes the sync."""
        base_sha = _init_repo(tmp_path)
        head_sha = _commit(tmp_path, "scripts_only.py")
        called = {"n": 0}

        def fake_sync(paths: Any, repo_root: Any) -> int:
            called["n"] += 1
            return 0

        monkeypatch.setattr(git_hook_policy, "sync_observations", fake_sync)
        monkeypatch.setattr("sys.stdin", self._stdin(head_sha, base_sha))

        rc = git_hook_policy._handle_observations_push(self._handler_args(tmp_path))

        assert rc == 0
        assert called["n"] == 0
        # Scope report names both counts (ci-scripts: report examined size).
        assert "0 observation file(s)" in capsys.readouterr().out

    def test_unresolvable_push_range_skips_advisory(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Edge: unresolvable refs skip the advisory sync instead of failing
        open into the full-corpus scan that overruns the lefthook cap."""
        called = {"n": 0}

        def fake_sync(paths: Any, repo_root: Any) -> int:
            called["n"] += 1
            return 0

        monkeypatch.setattr(git_hook_policy, "sync_observations", fake_sync)
        monkeypatch.setattr("sys.stdin", io.StringIO("malformed stdin\n"))

        rc = git_hook_policy._handle_observations_push(self._handler_args(tmp_path))

        assert rc == 0
        assert called["n"] == 0
        assert "skipped" in capsys.readouterr().out.lower()

    def test_deleted_observation_file_is_not_synced(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Edge: a file in the push range but absent on disk cannot be synced."""
        base_sha = _init_repo(tmp_path)
        (tmp_path / ".serena" / "memories").mkdir(parents=True)
        _commit(tmp_path, ".serena/memories/gone-observations.md")
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(tmp_path),
             "rm", "-q", ".serena/memories/gone-observations.md"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-C", str(tmp_path),
             "commit", "-qm", "remove observations"],
            check=True, capture_output=True,
        )
        head_sha = subprocess.run(
            ["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, encoding="utf-8",
        ).stdout.strip()
        called = {"n": 0}

        def fake_sync(paths: Any, repo_root: Any) -> int:
            called["n"] += 1
            return 0

        monkeypatch.setattr(git_hook_policy, "sync_observations", fake_sync)
        monkeypatch.setattr("sys.stdin", self._stdin(head_sha, base_sha))

        rc = git_hook_policy._handle_observations_push(self._handler_args(tmp_path))

        assert rc == 0
        assert called["n"] == 0

    def test_cli_main_propagates_sync_exit_code(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """CLI exit contract: drive main(argv); a failing sync exits nonzero."""
        base_sha = _init_repo(tmp_path)
        (tmp_path / ".serena" / "memories").mkdir(parents=True)
        head_sha = _commit(tmp_path, ".serena/memories/adr-observations.md")
        monkeypatch.setattr(git_hook_policy, "sync_observations", lambda *_a: 3)
        monkeypatch.setattr("sys.stdin", self._stdin(head_sha, base_sha))
        argv = ["--repo-root", str(tmp_path), "observations-push"]

        assert git_hook_policy.main(argv) == 3

        monkeypatch.setattr(git_hook_policy, "sync_observations", lambda *_a: 0)
        monkeypatch.setattr("sys.stdin", self._stdin(head_sha, base_sha))
        assert git_hook_policy.main(argv) == 0
