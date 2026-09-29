"""Typed evidence from the branch-wide em/en-dash gate (issue #5636).

`validate_dash_prohibition` is a blocking pre-push job (`dash-prohibition` in
`lefthook.yml`) and a `pre_pr.py` gate. Before this change it printed a
warning and returned `True` when no base ref resolved or `git diff` failed, so
a gate that scanned nothing recorded `PASS` and exited 0 for a branch that
carried a committed dash. `checks_mypy.validate_mypy_changed_files` reports the
same two conditions as `BLOCKED` and `UNKNOWN`; this gate now does too.

Coverage:

- positive: a clean scan is `PASS` and names its base, scope, and file count.
- negative: an unresolved base ref and a failed `git diff` are not `PASS`, the
  `git_hook_policy.py branch-dashes` handler exits 1 for both, and `pre_pr`
  records them as blocking.
- edge: no markdown on the branch is `PASS` with `examined=0`, and an unreadable
  file lowers `examined` instead of counting as checked.
- boundary: real git repositories, not mocked subprocess, for the two
  not-run cases, so the exit code is decided by what git actually returned.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.validation.evidence import (
    REASON_BASE_REF_UNRESOLVED,
    REASON_DIFF_FAILED,
    EvidenceState,
    default_pre_pr_policy,
)
from tests.ci.count_ratchet_git_harness import commit_all, git_stdout, init_repo

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


def _run_handler(repo: Path) -> int:
    return git_hook_policy.main(["--repo-root", str(repo), "branch-dashes"])


def _pin_base(monkeypatch: pytest.MonkeyPatch, resolve: object) -> None:
    monkeypatch.setattr(checks_dash, "_resolve_branch_base_ref", resolve)


class TestScanThatCannotRunIsNotAPass:
    def test_unresolved_base_ref_is_blocked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo = _repo_with(tmp_path, {"docs/guide.md": f"one{EM_DASH}two\n"})
        _pin_base(monkeypatch, lambda _root: None)

        outcome = checks_dash.validate_dash_prohibition(repo)

        assert outcome.state is EvidenceState.BLOCKED
        assert outcome.reason == REASON_BASE_REF_UNRESOLVED
        assert outcome.examined is None, "nothing was scanned, so no count may be claimed"

    def test_unresolved_base_ref_fails_the_pre_push_handler(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """The committed dash is real; only the base ref is missing."""
        repo = _repo_with(tmp_path, {"docs/guide.md": f"one{EM_DASH}two\n"})
        _pin_base(monkeypatch, lambda _root: None)

        assert _run_handler(repo) == 1

        err = capsys.readouterr().err
        assert "[BLOCKED]" in err
        assert f"reason={REASON_BASE_REF_UNRESOLVED}" in err

    def test_failed_git_diff_is_unknown_and_fails_the_handler(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A base that names no revision makes the real `git diff` exit 128."""
        repo = _repo_with(tmp_path, {"docs/guide.md": f"one{EM_DASH}two\n"})
        _pin_base(monkeypatch, lambda _root: "refs/heads/no-such-branch")

        outcome = checks_dash.validate_dash_prohibition(repo)
        assert outcome.state is EvidenceState.UNKNOWN
        assert outcome.reason == REASON_DIFF_FAILED
        assert _run_handler(repo) == 1
        assert "[UNKNOWN]" in capsys.readouterr().err

    def test_pre_pr_records_the_unrunnable_scan_as_blocking(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        repo = _repo_with(tmp_path, {"docs/guide.md": "plain\n"})
        _pin_base(monkeypatch, lambda _root: None)
        state = ValidationState()

        accepted = run_validation(
            "Em/en-dash Prohibition",
            state,
            lambda: checks_dash.validate_dash_prohibition(repo),
        )

        assert accepted is False
        assert (state.blocked, state.passed) == (1, 0)
        assert "reason=base_ref.unresolved" in capsys.readouterr().out

    def test_the_default_policy_licenses_neither_state(self, tmp_path: Path) -> None:
        """The exit code comes from the policy, so pin what the policy says."""
        policy = default_pre_pr_policy()
        with patch("checks_dash._resolve_branch_base_ref", return_value=None):
            blocked = checks_dash.validate_dash_prohibition(tmp_path)
        with (
            patch("checks_dash._resolve_branch_base_ref", return_value="origin/main"),
            patch("checks_dash._run_subprocess", return_value=(128, "", "fatal: nope")),
        ):
            unknown = checks_dash.validate_dash_prohibition(tmp_path)
        assert not policy.accepts(blocked)
        assert not policy.accepts(unknown)


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
        assert outcome.revision.endswith("...HEAD")
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

    def test_an_unreadable_file_lowers_examined_instead_of_counting_as_checked(
        self, tmp_path: Path
    ) -> None:
        with (
            patch("checks_dash._resolve_branch_base_ref", return_value="origin/main"),
            patch("checks_dash._run_subprocess") as run,
        ):
            run.side_effect = [
                (0, "clean.md\nunreadable.md\n", ""),  # git diff
                (0, "no dashes here\n", ""),  # clean.md
                (128, "", "fatal: bad object"),  # unreadable.md
            ]
            outcome = checks_dash.validate_dash_prohibition(tmp_path)

        assert outcome.state is EvidenceState.PASS
        assert outcome.examined == 1
        assert "1 of 2" in outcome.detail
