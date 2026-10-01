"""Tests for scripts/ci/adr101_publisher_execute.py.

Two kinds. Fake-runner tests pin what the stage decides without spawning git or
uv. A real-git test builds an upstream that holds a pull request ref and proves
the head is fetched by ref, compared with the event's SHA, and checked out with
a readable HEAD.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from scripts.ci import adr101_publisher_execute as ex
from scripts.ci.adr101_publisher_inputs import PublisherEnv
from scripts.validation.evidence import EvidenceState

HEAD = "a" * 40
BASE_PYPROJECT = (ex._tool_root() / "pyproject.toml").read_bytes()


def make_env(**overrides: str) -> PublisherEnv:
    values = {
        "ADR101_PUBLISHER_ENABLED": "true",
        "ADR101_TRIGGER_EVENT": "pull_request",
        "ADR101_REPOSITORY": "rjmurillo/ai-agents",
        "ADR101_HEAD_SHA": HEAD,
        "ADR101_PULL_NUMBER": "42",
    }
    values.update(overrides)
    return PublisherEnv.from_environ(values)


@dataclass
class FakeRunner:
    """Stands in for subprocess.run. Records calls; scripts git and the harness."""

    fetched_sha: str = HEAD
    harness_rc: int = 0
    harness_error: Exception | None = None
    symlink_target: Path | None = None
    calls: list[tuple[list[str], dict[str, Any]]] = field(default_factory=list)
    harness_pyproject: bytes | None = None

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((argv, kwargs))
        if argv[0] == "git":
            return self._git(argv, kwargs)
        if self.harness_error is not None:
            raise self.harness_error
        self.harness_pyproject = (Path(kwargs["cwd"]) / "pyproject.toml").read_bytes()
        return subprocess.CompletedProcess(argv, self.harness_rc, "", "")

    def _git(self, argv: list[str], kwargs: dict[str, Any]) -> subprocess.CompletedProcess[str]:
        verb = argv[argv.index("core.fsmonitor=false") + 1]
        if verb == "rev-parse":
            return subprocess.CompletedProcess(argv, 0, f"{self.fetched_sha}\n", "")
        if verb == "worktree":
            dest = Path(argv[argv.index("--force") + 1])
            dest.mkdir(parents=True, exist_ok=True)
            if self.symlink_target is not None:
                (dest / "pyproject.toml").symlink_to(self.symlink_target)
            else:
                (dest / "pyproject.toml").write_text("candidate = true\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, "", "")

    def harness_calls(self) -> list[tuple[list[str], dict[str, Any]]]:
        return [call for call in self.calls if call[0][0] != "git"]


class TestGateAndValidation:
    def test_flag_off_is_skip_and_spawns_nothing(self) -> None:
        runner = FakeRunner()

        outcome = ex.run_execute(make_env(ADR101_PUBLISHER_ENABLED=""), {}, runner)

        assert outcome.state is EvidenceState.SKIP
        assert runner.calls == []

    def test_an_unserved_event_is_skip_and_spawns_nothing(self) -> None:
        runner = FakeRunner()

        outcome = ex.run_execute(make_env(ADR101_TRIGGER_EVENT="push"), {}, runner)

        assert outcome.state is EvidenceState.SKIP
        assert runner.calls == []

    def test_no_pull_request_is_unknown_and_runs_nothing(self) -> None:
        runner = FakeRunner()

        outcome = ex.run_execute(make_env(ADR101_PULL_NUMBER=""), {}, runner)

        assert outcome.state is EvidenceState.UNKNOWN
        assert outcome.reason == "pr.unresolved"
        assert runner.calls == []

    @pytest.mark.parametrize(
        "override",
        [
            {"ADR101_HEAD_SHA": "xyz"},
            {"ADR101_HEAD_SHA": HEAD.upper()},
            {"ADR101_REPOSITORY": "../x"},
            {"ADR101_PULL_NUMBER": "4;id"},
        ],
    )
    def test_malformed_event_values_are_fail_and_run_nothing(
        self, override: dict[str, str]
    ) -> None:
        runner = FakeRunner()

        outcome = ex.run_execute(make_env(**override), {}, runner)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "input.invalid"
        assert runner.calls == []


class TestRun:
    def test_exit_zero_is_pass_bound_to_the_head_and_labelled_as_bounded(
        self, tmp_path: Path
    ) -> None:
        runner = FakeRunner()

        outcome = ex.run_execute(make_env(), {}, runner, tmp_path)

        assert outcome.state is EvidenceState.PASS
        assert outcome.revision == HEAD
        assert "2b" in outcome.detail
        assert "verified" not in outcome.detail.lower()

    def test_nonzero_exit_is_fail(self, tmp_path: Path) -> None:
        outcome = ex.run_execute(make_env(), {}, FakeRunner(harness_rc=1), tmp_path)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "execution.failed"
        assert "1" in outcome.detail

    def test_a_missing_uv_is_blocked(self, tmp_path: Path) -> None:
        runner = FakeRunner(harness_error=FileNotFoundError("uv"))

        outcome = ex.run_execute(make_env(), {}, runner, tmp_path)

        assert outcome.state is EvidenceState.BLOCKED
        assert outcome.reason == "tool.absent"

    def test_a_timeout_is_blocked(self, tmp_path: Path) -> None:
        runner = FakeRunner(harness_error=subprocess.TimeoutExpired("uv", 1))

        outcome = ex.run_execute(make_env(), {}, runner, tmp_path)

        assert outcome.state is EvidenceState.BLOCKED
        assert outcome.reason == "timeout"

    @pytest.mark.parametrize(
        "error, reason",
        [
            (FileNotFoundError("git"), "tool.absent"),
            (subprocess.TimeoutExpired("git", 1), "timeout"),
        ],
    )
    def test_a_missing_git_or_a_git_timeout_is_blocked_not_a_traceback(
        self, tmp_path: Path, error: Exception, reason: str
    ) -> None:
        def broken(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            raise error

        outcome = ex.run_execute(make_env(), {}, broken, tmp_path)

        assert outcome.state is EvidenceState.BLOCKED
        assert outcome.reason == reason

    def test_a_head_that_moved_is_fail_and_the_harness_never_runs(self, tmp_path: Path) -> None:
        runner = FakeRunner(fetched_sha="c" * 40)

        outcome = ex.run_execute(make_env(), {}, runner, tmp_path)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "revision.moved"
        assert runner.harness_calls() == []

    def test_a_git_failure_is_fail_without_running_the_harness(self, tmp_path: Path) -> None:
        def failing(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 128, "", "fatal")

        outcome = ex.run_execute(make_env(), {}, failing, tmp_path)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "execution.failed"

    def test_the_harness_argv_is_base_owned_and_names_no_candidate_value(
        self, tmp_path: Path
    ) -> None:
        runner = FakeRunner()

        ex.run_execute(make_env(), {}, runner, tmp_path)

        argv, kwargs = runner.harness_calls()[0]
        scratch = Path(kwargs["cwd"])
        assert argv == ex.harness_argv(scratch)
        assert argv[argv.index("-c") + 1] == str(scratch / "pyproject.toml")
        assert argv[argv.index("--rootdir") + 1] == str(scratch)
        assert argv[:4] == ["uv", "run", "--frozen", "--no-config"]
        assert str(ex._tool_root()) in argv
        assert HEAD not in argv
        assert kwargs["timeout"] == ex.HARNESS_TIMEOUT_SECONDS

    def test_the_pytest_config_is_the_base_copy_not_the_candidates(self, tmp_path: Path) -> None:
        runner = FakeRunner()

        ex.run_execute(make_env(), {}, runner, tmp_path)

        assert runner.harness_pyproject == BASE_PYPROJECT

    def test_a_symlinked_candidate_pyproject_is_replaced_not_written_through(
        self, tmp_path: Path
    ) -> None:
        outside = tmp_path / "outside.txt"
        outside.write_text("untouched", encoding="utf-8")
        runner = FakeRunner(symlink_target=outside)

        outcome = ex.run_execute(make_env(), {}, runner, tmp_path)

        assert outcome.state is EvidenceState.PASS
        assert outside.read_text(encoding="utf-8") == "untouched"
        assert runner.harness_pyproject == BASE_PYPROJECT

    @pytest.mark.parametrize("name", ["pytest.ini", ".pytest.ini", "tox.ini", "setup.cfg"])
    def test_a_competing_pytest_config_is_removed(self, tmp_path: Path, name: str) -> None:
        seen: dict[str, bool] = {}

        class Spy(FakeRunner):
            def __call__(
                self, argv: list[str], **kwargs: Any
            ) -> subprocess.CompletedProcess[str]:
                if argv[0] != "git":
                    seen["present"] = (Path(kwargs["cwd"]) / name).exists()
                result = super().__call__(argv, **kwargs)
                if argv[0] == "git" and "worktree" in argv:
                    dest = Path(argv[argv.index("--force") + 1])
                    (dest / name).write_text("[pytest]\naddopts = --co\n", encoding="utf-8")
                return result

        ex.run_execute(make_env(), {}, Spy(), tmp_path)

        assert seen == {"present": False}

    def test_the_child_environment_holds_no_token_or_event_value(self, tmp_path: Path) -> None:
        runner = FakeRunner()
        environ = {
            "PATH": "/usr/bin",
            "HOME": "/home/runner",
            "ADR101_READ_TOKEN": "ghs_read",
            "ADR101_APP_TOKEN": "ghs_app",
            "GITHUB_TOKEN": "ghs_gh",
            "ADR101_HEAD_SHA": HEAD,
        }

        ex.run_execute(make_env(), environ, runner, tmp_path)

        child = runner.harness_calls()[0][1]["env"]
        assert child["PATH"] == "/usr/bin"
        assert child["CI"] == "true"
        assert not [name for name in child if "TOKEN" in name or name.startswith("ADR101")]

    def test_git_runs_with_hooks_and_system_config_disabled(self, tmp_path: Path) -> None:
        runner = FakeRunner()

        ex.run_execute(make_env(), {}, runner, tmp_path)

        git_calls = [call for call in runner.calls if call[0][0] == "git"]
        assert git_calls
        for argv, kwargs in git_calls:
            assert "core.hooksPath=/dev/null" in argv
            assert kwargs["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
            assert kwargs["env"]["GIT_CONFIG_GLOBAL"] == "/dev/null"
            assert kwargs["encoding"] == "utf-8"
            assert kwargs["errors"] == "replace"

    def test_the_scratch_tree_is_removed_after_the_run(self, tmp_path: Path) -> None:
        ex.run_execute(make_env(), {}, FakeRunner(), tmp_path)

        assert list(tmp_path.iterdir()) == []


class TestConfigInstall:
    @pytest.mark.parametrize(
        "name", ["pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml", "tox.ini", "setup.cfg"]
    )
    def test_a_directory_with_a_config_name_is_removed_not_fatal(
        self, tmp_path: Path, name: str
    ) -> None:
        scratch = tmp_path / "scratch"
        (scratch / name / "inner").mkdir(parents=True)
        (scratch / "pyproject.toml").mkdir()

        ex._install_base_pytest_config(ex._tool_root(), scratch)

        assert (scratch / "pyproject.toml").read_bytes() == BASE_PYPROJECT
        assert not (scratch / name).exists()

    def test_a_symlink_to_a_directory_is_unlinked_without_touching_the_target(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "target"
        target.mkdir()
        (target / "keep.txt").write_text("keep", encoding="utf-8")
        scratch = tmp_path / "scratch"
        scratch.mkdir()
        (scratch / "tox.ini").symlink_to(target, target_is_directory=True)

        ex._install_base_pytest_config(ex._tool_root(), scratch)

        assert (target / "keep.txt").read_text(encoding="utf-8") == "keep"
        assert not (scratch / "tox.ini").exists()

    def test_an_install_error_is_a_typed_fail_not_a_traceback(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(tool_root: Path, scratch: Path) -> None:
            raise PermissionError("denied")

        monkeypatch.setattr(ex, "_install_base_pytest_config", boom)
        runner = FakeRunner()

        outcome = ex.run_execute(make_env(), {}, runner, tmp_path)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == "execution.failed"
        assert "PermissionError" in outcome.detail
        assert runner.harness_calls() == []


class TestRealGit:
    def _git(self, cwd: Path, *args: str) -> str:
        env = {"PATH": "/usr/bin:/bin", "HOME": str(cwd), "GIT_CONFIG_NOSYSTEM": "1"}
        done = subprocess.run(
            ["git", "-c", "commit.gpgsign=false", *args],
            cwd=cwd,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=True,
        )
        return done.stdout.strip()

    @pytest.fixture
    def upstream(self, tmp_path: Path) -> tuple[Path, str]:
        """A clone whose origin holds ``refs/pull/5/head`` at a known commit."""
        source = tmp_path / "source"
        source.mkdir()
        self._git(source, "init", "-q", "-b", "main")
        self._git(source, "config", "user.email", "t@example.com")
        self._git(source, "config", "user.name", "t")
        (source / "tests").mkdir()
        (source / "tests" / "test_a.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
        (source / ".gitattributes").write_text("tests/ export-ignore\n", encoding="utf-8")
        self._git(source, "add", "-A")
        self._git(source, "commit", "-q", "-m", "head")
        sha = self._git(source, "rev-parse", "HEAD")
        self._git(source, "update-ref", "refs/pull/5/head", sha)
        clone = tmp_path / "tool"
        self._git(tmp_path, "clone", "-q", str(source), str(clone))
        return clone, sha

    def test_the_head_is_fetched_by_ref_and_checked_out_with_a_readable_head(
        self, upstream: tuple[Path, str], tmp_path: Path
    ) -> None:
        clone, sha = upstream
        dest = tmp_path / "out" / "candidate"
        dest.parent.mkdir()

        ex.materialize_head(clone, "5", sha, dest)

        assert (dest / "tests" / "test_a.py").read_text(encoding="utf-8").startswith("def test_a")
        assert self._git(dest, "rev-parse", "HEAD") == sha
        assert self._git(dest, "ls-files").splitlines() == [".gitattributes", "tests/test_a.py"]

    def test_export_ignore_in_the_head_does_not_omit_a_file(
        self, upstream: tuple[Path, str], tmp_path: Path
    ) -> None:
        clone, sha = upstream
        dest = tmp_path / "out" / "candidate"
        dest.parent.mkdir()

        ex.materialize_head(clone, "5", sha, dest)

        assert (dest / "tests" / "test_a.py").exists()

    def test_a_different_event_sha_raises_moved_and_writes_nothing(
        self, upstream: tuple[Path, str], tmp_path: Path
    ) -> None:
        clone, _ = upstream
        dest = tmp_path / "out" / "candidate"

        with pytest.raises(ex.MaterializeError) as caught:
            ex.materialize_head(clone, "5", "f" * 40, dest)

        assert caught.value.moved is True
        assert not dest.exists()

    def test_a_missing_pull_ref_raises_without_the_moved_flag(
        self, upstream: tuple[Path, str], tmp_path: Path
    ) -> None:
        clone, sha = upstream

        with pytest.raises(ex.MaterializeError) as caught:
            ex.materialize_head(clone, "99", sha, tmp_path / "out" / "candidate")

        assert caught.value.moved is False
