"""Gitignore-aware behavior of the path normalization scanner.

Split from test_validate_path_normalization.py: these classes cover the
git check-ignore filtering and its fail-open timeout handling, and the
combined file crossed the 500-line taste ceiling.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Add build/scripts to path for imports
_BUILD_SCRIPTS = Path(__file__).resolve().parent.parent / "build" / "scripts"
sys.path.insert(0, str(_BUILD_SCRIPTS))

import validate_path_normalization as vpn  # noqa: E402
from validate_path_normalization import collect_files, main  # noqa: E402


class TestGitIgnoredFilesAreSkipped:
    """Ignored trees hold transient artifacts, not authored documentation.

    A `.pytest_cache/basetemp/` fixture containing a deliberate `/home/runner`
    string failed the push gate for every contributor. Naming each cache
    directory in the exclude list is a blocklist that loses to the next tool,
    so the scanner asks Git instead. Refs #3686.
    """

    @staticmethod
    def _init_repo(root: Path) -> None:
        subprocess.run(
            ["git", "init", "-q", str(root)],
            check=True,
            capture_output=True,
        )

    def test_an_ignored_file_is_not_collected(self, tmp_path: Path) -> None:
        self._init_repo(tmp_path)
        (tmp_path / ".gitignore").write_text(".pytest_cache/\n", encoding="utf-8")
        cache = tmp_path / ".pytest_cache"
        cache.mkdir()
        (cache / "artifact.md").write_text("leaked /home/runner/cache\n", encoding="utf-8")

        collected = collect_files(tmp_path, [".md"], [])

        assert cache / "artifact.md" not in collected

    def test_a_tracked_file_is_still_collected(self, tmp_path: Path) -> None:
        self._init_repo(tmp_path)
        (tmp_path / ".gitignore").write_text(".pytest_cache/\n", encoding="utf-8")
        kept = tmp_path / "doc.md"
        kept.write_text("relative/path.md\n", encoding="utf-8")

        assert kept in collect_files(tmp_path, [".md"], [])

    def test_an_ignored_violation_does_not_fail_the_gate(self, tmp_path: Path) -> None:
        self._init_repo(tmp_path)
        (tmp_path / ".gitignore").write_text("cache/\n", encoding="utf-8")
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "artifact.md").write_text("leaked /home/runner/x\n", encoding="utf-8")

        assert main(["--path", str(tmp_path), "--fail-on-violation"]) == 0

    def test_a_tracked_violation_still_fails_the_gate(self, tmp_path: Path) -> None:
        self._init_repo(tmp_path)
        (tmp_path / "doc.md").write_text("leaked /home/runner/x\n", encoding="utf-8")

        assert main(["--path", str(tmp_path), "--fail-on-violation"]) == 1

    def test_a_directory_outside_any_repository_scans_everything(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`git check-ignore` exits 128 outside a repo. Scan rather than skip."""
        monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
        (tmp_path / "doc.md").write_text("leaked /home/runner/x\n", encoding="utf-8")

        assert tmp_path / "doc.md" in collect_files(tmp_path, [".md"], [])

    def test_an_unavailable_git_binary_scans_everything(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import validate_path_normalization as module

        def _raise(*_args: object, **_kwargs: object) -> None:
            raise OSError("git missing")

        monkeypatch.setattr(module.subprocess, "run", _raise)
        (tmp_path / "doc.md").write_text("leaked /home/runner/x\n", encoding="utf-8")

        assert tmp_path / "doc.md" in collect_files(tmp_path, [".md"], [])

    def test_an_empty_candidate_list_makes_no_subprocess_call(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import validate_path_normalization as module

        def _fail(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("git should not run for an empty candidate list")

        monkeypatch.setattr(module.subprocess, "run", _fail)

        assert collect_files(tmp_path, [".md"], []) == []


class TestGitCheckIgnoreCannotHangThePush:
    """A blocked `git check-ignore` must not stall the pre-push hook.

    `collect_files` shells out to git on every push. Without a timeout, a git
    that blocks on an index lock leaves the contributor staring at a hung
    terminal with no output and no way to tell what is wrong. The gate would
    rather scan an ignored file than never finish.
    """

    def test_a_timeout_is_passed_to_git(self, tmp_path: Path, monkeypatch) -> None:
        (tmp_path / "doc.md").write_text("ok\n", encoding="utf-8")
        seen: dict[str, object] = {}
        real_run = subprocess.run

        def capture(*args, **kwargs):
            if "check-ignore" in args[0]:
                seen.update(kwargs)
            return real_run(*args, **kwargs)  # subprocess-encoding: strict-ok

        monkeypatch.setattr(vpn.subprocess, "run", capture)
        collect_files(tmp_path, [".md"], [])

        assert seen.get("timeout") == vpn.GIT_CHECK_IGNORE_TIMEOUT_SECONDS

    def test_a_hung_git_fails_open_instead_of_raising(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        kept = tmp_path / "doc.md"
        kept.write_text("ok\n", encoding="utf-8")

        def hang(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd="git", timeout=1)

        monkeypatch.setattr(vpn.subprocess, "run", hang)

        assert collect_files(tmp_path, [".md"], []) == [kept]

    def test_any_subprocess_error_fails_open(self, tmp_path: Path, monkeypatch) -> None:
        kept = tmp_path / "doc.md"
        kept.write_text("ok\n", encoding="utf-8")

        def explode(*args, **kwargs):
            raise subprocess.SubprocessError("git died")

        monkeypatch.setattr(vpn.subprocess, "run", explode)

        assert collect_files(tmp_path, [".md"], []) == [kept]

    def test_a_missing_git_binary_still_fails_open(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        kept = tmp_path / "doc.md"
        kept.write_text("ok\n", encoding="utf-8")

        def missing(*args, **kwargs):
            raise FileNotFoundError("git")

        monkeypatch.setattr(vpn.subprocess, "run", missing)

        assert collect_files(tmp_path, [".md"], []) == [kept]

    def test_the_timeout_does_not_disable_filtering(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
        (tmp_path / ".gitignore").write_text("cache/\n", encoding="utf-8")
        cache = tmp_path / "cache"
        cache.mkdir()
        (cache / "artifact.md").write_text("x\n", encoding="utf-8")
        kept = tmp_path / "doc.md"
        kept.write_text("ok\n", encoding="utf-8")

        assert collect_files(tmp_path, [".md"], []) == [kept]
