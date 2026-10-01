"""Tests for scripts/ci/spec_coverage_scope.py.

ADR-101 requirement 1: the Validate Spec Coverage job decides its own scope
instead of reading a sibling job's path-filter output. These tests drive real
git repositories, so the three-dot diff and its failure modes are the real ones.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.ci import spec_coverage_scope as scope
from scripts.ci.spec_coverage_scope import EXIT_CONFIG, EXIT_OK, main

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/ai-spec-validation.yml"


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, files: dict[str, str]) -> str:
    for relative, content in files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "change")
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "test@example.invalid")
    _git(tmp_path, "config", "user.name", "Test User")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    _commit(tmp_path, {"README.md": "base\n"})
    return tmp_path


class TestDecide:
    def test_code_change_under_scripts_validates(self, repo: Path) -> None:
        base = _git(repo, "rev-parse", "HEAD")
        head = _commit(repo, {"scripts/tool.py": "x = 1\n", "docs/a.md": "a\n"})

        result = scope.decide("pull_request", base, head, repo)

        assert result.skip is False
        assert "1 of 2" in result.reason

    @pytest.mark.parametrize(
        "path",
        [
            "src/app.py",
            "templates/agents/a.md",
            "scripts/ci/x.py",
            "build/generate.py",
            ".claude/skills/demo/SKILL.md",
        ],
    )
    def test_every_code_prefix_validates(self, repo: Path, path: str) -> None:
        base = _git(repo, "rev-parse", "HEAD")
        head = _commit(repo, {path: "x\n"})

        assert scope.decide("pull_request", base, head, repo).skip is False

    def test_docs_only_change_skips_and_says_how_many_files_were_examined(
        self, repo: Path
    ) -> None:
        base = _git(repo, "rev-parse", "HEAD")
        head = _commit(repo, {"docs/a.md": "a\n", "notes/b.txt": "b\n"})

        result = scope.decide("pull_request", base, head, repo)

        assert result.skip is True
        assert "0 of 2" in result.reason

    def test_prefix_must_match_a_directory_not_a_name_stem(self, repo: Path) -> None:
        base = _git(repo, "rev-parse", "HEAD")
        head = _commit(repo, {"scripts_notes.md": "n\n", "srcfile.md": "n\n"})

        assert scope.decide("pull_request", base, head, repo).skip is True

    def test_empty_diff_skips_with_zero_examined(self, repo: Path) -> None:
        head = _git(repo, "rev-parse", "HEAD")

        result = scope.decide("pull_request", head, head, repo)

        assert result.skip is True
        assert "0 of 0" in result.reason

    def test_manual_dispatch_always_validates(self, repo: Path) -> None:
        result = scope.decide("workflow_dispatch", "", "", repo)

        assert result.skip is False

    @pytest.mark.parametrize(
        ("base", "head"),
        [("", "abc"), ("abc", ""), ("", ""), ("0" * 40, "abc")],
    )
    def test_missing_or_null_shas_never_skip(self, repo: Path, base: str, head: str) -> None:
        result = scope.decide("pull_request", base, head, repo)

        assert result.skip is False
        assert "cannot diff" in result.reason

    @pytest.mark.parametrize(
        "bad",
        ["--output=/tmp/x", "HEAD", "abc123", "A" * 40, "g" * 40, "f" * 39, "f" * 41],
    )
    def test_malformed_sha_never_skips_and_never_reaches_git(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, bad: str
    ) -> None:
        def _no_git(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("git must not run for a malformed SHA")

        monkeypatch.setattr(scope.subprocess, "run", _no_git)
        good = "a" * 40

        for base, head in ((bad, good), (good, bad)):
            result = scope.decide("pull_request", base, head, repo)
            assert result.skip is False
            assert "cannot diff" in result.reason

    def test_newline_in_a_sha_cannot_add_an_output_line(self, repo: Path) -> None:
        result = scope.decide("pull_request", "a" * 40, "b" * 40 + "\nskip=true", repo)

        assert result.skip is False
        assert "\n" not in result.reason

    def test_sha256_object_ids_are_accepted(self, repo: Path) -> None:
        head = _git(repo, "rev-parse", "HEAD")

        assert scope._is_usable_sha(head)
        assert scope._is_usable_sha("f" * 64)

    def test_a_move_out_of_a_code_prefix_validates(self, repo: Path) -> None:
        """`src/x.py` -> `docs/x.py` must not read as a docs-only change."""
        _commit(repo, {"src/x.py": "x = 1\n"})
        base = _git(repo, "rev-parse", "HEAD")
        (repo / "docs").mkdir()
        _git(repo, "mv", "src/x.py", "docs/x.py")
        _git(repo, "commit", "-q", "-m", "move")
        head = _git(repo, "rev-parse", "HEAD")

        result = scope.decide("pull_request", base, head, repo)

        assert result.skip is False
        assert "1 of 2" in result.reason

    def test_unreadable_diff_never_skips(self, repo: Path) -> None:
        head = _git(repo, "rev-parse", "HEAD")

        result = scope.decide("pull_request", "f" * 40, head, repo)

        assert result.skip is False
        assert "could not diff" in result.reason

    def test_not_a_git_repository_never_skips(self, tmp_path: Path) -> None:
        result = scope.decide("pull_request", "a" * 40, "b" * 40, tmp_path)

        assert result.skip is False

    def test_path_with_newline_does_not_smuggle_a_code_prefix(self, repo: Path) -> None:
        """A file named `docs/x\\nscripts/y` must not read as a scripts/ path."""
        base = _git(repo, "rev-parse", "HEAD")
        head = _commit(repo, {"docs/x\nscripts/y.md": "n\n"})

        result = scope.decide("pull_request", base, head, repo)

        assert result.skip is True


class TestChangedFiles:
    def test_returns_none_when_git_is_missing(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*_args: object, **_kwargs: object) -> None:
            raise FileNotFoundError("git")

        monkeypatch.setattr(scope.subprocess, "run", _raise)

        assert scope.changed_files(repo, "a", "b") is None


class TestMain:
    def _run(
        self,
        monkeypatch: pytest.MonkeyPatch,
        repo: Path,
        env: dict[str, str],
        output: Path | None,
    ) -> int:
        for name in ("EVENT_NAME", "BASE_SHA", "HEAD_SHA", "GITHUB_OUTPUT"):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        if output is not None:
            monkeypatch.setenv("GITHUB_OUTPUT", str(output))
        monkeypatch.chdir(repo)
        return main()

    def test_writes_skip_false_for_a_code_change(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        base = _git(repo, "rev-parse", "HEAD")
        head = _commit(repo, {"scripts/a.py": "x\n"})
        output = tmp_path_factory.mktemp("out") / "github_output"

        code = self._run(
            monkeypatch,
            repo,
            {"EVENT_NAME": "pull_request", "BASE_SHA": base, "HEAD_SHA": head},
            output,
        )

        assert code == EXIT_OK
        lines = output.read_text(encoding="utf-8").splitlines()
        assert "skip=false" in lines

    def test_writes_skip_true_for_a_docs_change(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
    ) -> None:
        base = _git(repo, "rev-parse", "HEAD")
        head = _commit(repo, {"docs/a.md": "x\n"})
        output = tmp_path_factory.mktemp("out") / "github_output"

        code = self._run(
            monkeypatch,
            repo,
            {"EVENT_NAME": "pull_request", "BASE_SHA": base, "HEAD_SHA": head},
            output,
        )

        assert code == EXIT_OK
        assert "skip=true" in output.read_text(encoding="utf-8").splitlines()

    def test_prints_without_a_github_output_file(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        code = self._run(monkeypatch, repo, {"EVENT_NAME": "workflow_dispatch"}, None)

        assert code == EXIT_OK
        assert "skip=false" in capsys.readouterr().out

    def test_refuses_without_an_event_name(
        self,
        repo: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        code = self._run(monkeypatch, repo, {}, None)

        assert code == EXIT_CONFIG
        assert "EVENT_NAME" in capsys.readouterr().err

    def test_whitespace_only_event_name_is_refused(
        self, repo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert self._run(monkeypatch, repo, {"EVENT_NAME": "   "}, None) == EXIT_CONFIG


class TestEntrypoint:
    """The workflow runs the file with bare python3, so drive it as a process."""

    def _run(self, repo: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        clean = {"PATH": str(Path(sys.executable).parent), "HOME": str(repo)}
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts/ci/spec_coverage_scope.py")],
            cwd=repo,
            env={**clean, **env},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def test_exit_zero_and_skip_false_for_a_code_change(self, repo: Path) -> None:
        base = _git(repo, "rev-parse", "HEAD")
        head = _commit(repo, {"build/x.py": "x\n"})

        result = self._run(
            repo, {"EVENT_NAME": "pull_request", "BASE_SHA": base, "HEAD_SHA": head}
        )

        assert result.returncode == EXIT_OK
        assert "skip=false" in result.stdout

    def test_exit_two_without_an_event_name(self, repo: Path) -> None:
        result = self._run(repo, {})

        assert result.returncode == EXIT_CONFIG
        assert "skip=" not in result.stdout


class TestWorkflowWiring:
    """The job must run this script itself and take no scope from a sibling job."""

    @staticmethod
    def _job() -> dict[str, object]:
        data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        job = data["jobs"]["validate-spec"]
        assert isinstance(job, dict)
        return job

    def test_no_sibling_path_job_exists(self) -> None:
        data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

        assert "check-paths" not in data["jobs"]

    def test_job_condition_reads_no_path_job_output(self) -> None:
        condition = str(self._job()["if"])

        assert "check-paths" not in condition
        assert "has-code-changes" not in condition

    def test_job_needs_only_the_debounce_ordering_job(self) -> None:
        assert self._job()["needs"] == "debounce"

    def test_scope_step_runs_the_script_with_event_shas(self) -> None:
        steps = self._job()["steps"]
        assert isinstance(steps, list)
        step = next(s for s in steps if s.get("id") == "should-run")

        assert "scripts/ci/spec_coverage_scope.py" in step["run"]
        env = step["env"]
        assert env["EVENT_NAME"] == "${{ github.event_name }}"
        assert env["BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
        assert env["HEAD_SHA"] == "${{ github.event.pull_request.head.sha }}"

    def test_checkout_precedes_the_scope_step_and_is_not_gated(self) -> None:
        steps = self._job()["steps"]
        assert isinstance(steps, list)
        ids = [s.get("id") for s in steps]
        checkout = steps[0]

        assert str(checkout["uses"]).startswith("actions/checkout@")
        assert "if" not in checkout
        assert checkout["with"]["fetch-depth"] == 0
        assert ids.index("should-run") == 1

    def test_no_step_reads_another_jobs_output(self) -> None:
        steps = self._job()["steps"]
        assert isinstance(steps, list)
        for step in steps:
            condition = str(step.get("if", ""))
            assert "needs." not in condition, step.get("name")
