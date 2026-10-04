"""End-to-end evidence from the branch-wide em/en-dash gate (issue #5636).

`validate_dash_prohibition` is a blocking pre-push job (`dash-prohibition` in
`lefthook.yml`) and a `pre_pr.py` gate. Its typed contract (PR #6057, #6066):
a scan that cannot run is `FAIL` under CI and `SKIP` locally. `test_dash_checks.py`
pins the unit states with mocked subprocess. This file pins what that file does
not: real git repositories, the `git_hook_policy.py branch-dashes` exit codes and
stderr line, and `pre_pr.run_validation` accounting.

Coverage:

- negative: with no base ref or a failing `git diff`, CI fails the handler with
  exit 1 and names the reason on stderr; `pre_pr` records a failure.
- edge: locally the same conditions skip, so the handler exits 0 and `pre_pr`
  does not count a pass.
- positive: a clean scan is `PASS` naming base, scope, and file count.
- boundary: a `git clone --origin upstream` checkout on a branch with no
  upstream misses every candidate the real resolver tries, with nothing pinned.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.validation.evidence import (
    REASON_BASE_REF_UNRESOLVED,
    REASON_DIFF_FAILED,
    EvidenceState,
)
from tests.ci.count_ratchet_git_harness import commit_all, git_checked, git_stdout, init_repo

_VALIDATION_DIR = Path(__file__).resolve().parents[2] / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

import checks_dash  # noqa: E402
import git_hook_policy  # noqa: E402

from scripts.validation.pre_pr import ValidationState, run_validation  # noqa: E402

# Escapes, so this file does not itself carry the prohibited bytes.
EM_DASH = "\u2014"


def _repo_with(tmp_path: Path, files: dict[str, str]) -> Path:
    """A repo whose base commit is clean and whose branch adds ``files``."""
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    commit_all(repo, "base")
    for relpath, text in files.items():
        target = repo / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    commit_all(repo, "branch work")
    return repo


def _clone_without_origin(tmp_path: Path, files: dict[str, str]) -> Path:
    """A clone whose only remote is `upstream`, on a branch that adds ``files``."""
    source = tmp_path / "source"
    source.mkdir()
    init_repo(source)
    (source / "README.md").write_text("base\n", encoding="utf-8")
    commit_all(source, "base")
    repo = tmp_path / "clone"
    subprocess.run(
        ["git", "clone", "-q", "--origin", "upstream", str(source), str(repo)], check=True
    )
    git_checked(repo, "config", "user.email", "t@example.com")
    git_checked(repo, "config", "user.name", "t")
    git_checked(repo, "checkout", "-q", "-b", "feature")
    for relpath, text in files.items():
        target = repo / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    commit_all(repo, "branch work")
    return repo


def _run_handler(repo: Path) -> int:
    return git_hook_policy.main(["--repo-root", str(repo), "branch-dashes"])


def _pin_base(monkeypatch: pytest.MonkeyPatch, resolve: object) -> None:
    monkeypatch.setattr(checks_dash, "_resolve_branch_base_ref", resolve)


@pytest.fixture(autouse=True)
def _local_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test as a local checkout unless it opts into CI."""
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)


class TestScanThatCannotRunUnderCi:
    def test_unresolved_base_ref_fails_the_pre_push_handler(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The committed dash is real; only the base ref is missing."""
        monkeypatch.setenv("CI", "true")
        repo = _repo_with(tmp_path, {"docs/guide.md": f"one{EM_DASH}two\n"})
        _pin_base(monkeypatch, lambda _root: None)

        outcome = checks_dash.validate_dash_prohibition(repo)
        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == REASON_BASE_REF_UNRESOLVED
        assert outcome.examined is None, "nothing was scanned, so no count may be claimed"
        capsys.readouterr()

        assert _run_handler(repo) == 1

        err = capsys.readouterr().err
        assert "[FAIL]" in err
        assert f"reason={REASON_BASE_REF_UNRESOLVED}" in err

    def test_real_checkout_with_no_base_ref_fails_with_no_pinning(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Nothing is monkeypatched: the real resolver returns None here.

        `git clone --origin upstream` leaves no `origin/main`, no
        `refs/remotes/origin/HEAD`, and, on a new branch, no `@{u}`; the
        remote is a local path, so `gh pr view` has no GitHub host to ask.
        """
        monkeypatch.setenv("CI", "true")
        monkeypatch.delenv("GH_REPO", raising=False)  # gh would otherwise skip the remotes
        repo = _clone_without_origin(tmp_path, {"docs/guide.md": f"one{EM_DASH}two\n"})
        assert checks_dash._resolve_branch_base_ref(repo) is None

        outcome = checks_dash.validate_dash_prohibition(repo)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == REASON_BASE_REF_UNRESOLVED
        capsys.readouterr()
        assert _run_handler(repo) == 1
        assert f"reason={REASON_BASE_REF_UNRESOLVED}" in capsys.readouterr().err

    def test_failed_git_diff_fails_the_handler(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A base that names no revision makes the real `git diff` exit 128."""
        monkeypatch.setenv("CI", "true")
        repo = _repo_with(tmp_path, {"docs/guide.md": f"one{EM_DASH}two\n"})
        _pin_base(monkeypatch, lambda _root: "refs/heads/no-such-branch")

        outcome = checks_dash.validate_dash_prohibition(repo)
        assert outcome.state is EvidenceState.FAIL
        assert outcome.reason == REASON_DIFF_FAILED
        capsys.readouterr()
        assert _run_handler(repo) == 1
        assert f"reason={REASON_DIFF_FAILED}" in capsys.readouterr().err

    def test_pre_pr_records_the_unrunnable_scan_as_a_failure(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("CI", "true")
        repo = _repo_with(tmp_path, {"docs/guide.md": "plain\n"})
        _pin_base(monkeypatch, lambda _root: None)
        state = ValidationState()

        accepted = run_validation(
            "Em/en-dash Prohibition",
            state,
            lambda: checks_dash.validate_dash_prohibition(repo),
        )

        assert accepted is False
        assert (state.failed, state.passed) == (1, 0)
        assert "reason=base_ref.unresolved" in capsys.readouterr().out


class TestScanThatCannotRunLocally:
    def test_unresolved_base_ref_skips_and_the_handler_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _repo_with(tmp_path, {"docs/guide.md": f"one{EM_DASH}two\n"})
        _pin_base(monkeypatch, lambda _root: None)

        outcome = checks_dash.validate_dash_prohibition(repo)

        assert outcome.state is EvidenceState.SKIP
        assert outcome.reason == REASON_BASE_REF_UNRESOLVED
        assert _run_handler(repo) == 0

    def test_pre_pr_does_not_count_a_local_skip_as_a_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _repo_with(tmp_path, {"docs/guide.md": "plain\n"})
        _pin_base(monkeypatch, lambda _root: None)
        state = ValidationState()

        run_validation(
            "Em/en-dash Prohibition",
            state,
            lambda: checks_dash.validate_dash_prohibition(repo),
        )

        assert state.passed == 0
        assert state.failed == 0


class TestScanThatRanReportsWhatItExamined:
    def test_clean_branch_is_pass_with_base_scope_and_count(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _repo_with(tmp_path, {"docs/a.md": "plain\n", "docs/b.md": "plain\n"})
        _pin_base(monkeypatch, lambda root: git_stdout(root, "rev-parse", "HEAD~1"))

        outcome = checks_dash.validate_dash_prohibition(repo)

        assert outcome.state is EvidenceState.PASS
        assert outcome.examined == 2
        assert outcome.findings == 0
        assert outcome.revision == "HEAD"
        assert outcome.scope
        assert _run_handler(repo) == 0

    def test_committed_dash_is_fail_with_a_finding_count(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _repo_with(
            tmp_path, {"docs/a.md": f"x{EM_DASH}y\nz{EM_DASH}w\n", "docs/b.md": "plain\n"}
        )
        _pin_base(monkeypatch, lambda root: git_stdout(root, "rev-parse", "HEAD~1"))

        outcome = checks_dash.validate_dash_prohibition(repo)

        assert outcome.state is EvidenceState.FAIL
        assert outcome.findings == 2
        assert outcome.examined == 2
        assert _run_handler(repo) == 1

    def test_no_markdown_on_the_branch_is_pass_with_zero_examined(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _repo_with(tmp_path, {"src/mod.py": f"# x{EM_DASH}y\n"})
        _pin_base(monkeypatch, lambda root: git_stdout(root, "rev-parse", "HEAD~1"))

        outcome = checks_dash.validate_dash_prohibition(repo)

        assert outcome.state is EvidenceState.PASS
        assert outcome.examined == 0
