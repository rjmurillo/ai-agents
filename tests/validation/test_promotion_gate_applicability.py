"""The gate derives its required validators from the applicability table.

ADR-113 decision 3, issue #5636. A candidate that contains a workflow file must
show the validators the table maps to workflow files, and a deleted or invalid
table must block, not excuse.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.promotion_applicability import APPLICABILITY_RELATIVE_PATH
from scripts.validation.promotion_candidate import (
    CandidateCheckError,
    candidate_files,
)
from scripts.validation.promotion_gate import EXIT_CONFIG, EXIT_EXTERNAL, EXIT_LOGIC, EXIT_OK, main
from tests.validation.promotion_gate_helpers import git, make_clone

TODAY = date(2026, 10, 1)
MODE = ("--mode", "enforcing", "--ancestor-of", "HEAD")


def _entry(validator: str, when: Any = "always", tier: str = "commit") -> dict[str, Any]:
    return {
        "validator": validator,
        "tier": tier,
        "workflow": ".github/workflows/x.yml",
        "job": validator,
        "when": when,
        "rationale": "test row",
    }


def _table(repo: Path, *entries: dict[str, Any]) -> None:
    path = repo / APPLICABILITY_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "1", "entries": list(entries)}), encoding="utf-8")


def _evidence(repo: Path, sha: str, validator: str, **extra: Any) -> None:
    ev = repo.parent / "ev"
    ev.mkdir(exist_ok=True)
    doc = {
        "validator": validator,
        "state": "PASS",
        "revision": sha,
        "scope": "s",
        "examined": 3,
        **extra,
    }
    (ev / f"{validator}.json").write_text(json.dumps(doc), encoding="utf-8")


def _run(repo: Path, sha: str, *extra: str) -> int:
    ev = repo.parent / "ev"
    ev.mkdir(exist_ok=True)
    args = ["--repo-root", str(repo), "--evidence-dir", str(ev), "--candidate-sha", sha, *extra]
    return main(args)


@pytest.fixture
def clone(tmp_path: Path) -> tuple[Path, str, str]:
    return make_clone(tmp_path)


class TestCandidateFiles:
    def test_lists_the_commit_tree_not_the_working_tree(
        self,
        clone: tuple[Path, str, str],
    ) -> None:
        repo, first, side = clone
        (repo / "untracked.txt").write_text("x", encoding="utf-8")
        assert candidate_files(repo, first) == ("a",)
        assert candidate_files(repo, side) == ("a", "b")

    def test_a_path_with_a_newline_stays_one_path(self, tmp_path: Path) -> None:
        repo = tmp_path / "r"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        (repo / "a\nb").write_text("x", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "m")
        assert candidate_files(repo, git(repo, "rev-parse", "HEAD")) == ("a\nb",)

    @pytest.mark.parametrize("sha", ["--all", "abc", "A" * 40, "", "f" * 39])
    def test_a_non_sha_is_refused_before_git_runs(
        self, clone: tuple[Path, str, str], sha: str
    ) -> None:
        repo, _, _ = clone
        with pytest.raises(ValueError, match="40-character"):
            candidate_files(repo, sha)

    def test_unknown_commit_raises(self, clone: tuple[Path, str, str]) -> None:
        repo, _, _ = clone
        with pytest.raises(CandidateCheckError, match="ls-tree"):
            candidate_files(repo, "f" * 40)


class TestTableDrivesRequired:
    def test_all_applicable_validators_passing_promotes(
        self,
        clone: tuple[Path, str, str],
    ) -> None:
        repo, first, _ = clone
        _table(repo, _entry("always_one"), _entry("only_py", when=["*.py"]))
        _evidence(repo, first, "always_one")
        assert _run(repo, first, *MODE) == EXIT_OK

    def test_a_path_conditional_validator_is_required_when_the_file_exists(
        self,
        clone: tuple[Path, str, str],
    ) -> None:
        repo, _, _ = clone
        (repo / "tool.py").write_text("x", encoding="utf-8")
        git(repo, "add", "tool.py")
        git(repo, "commit", "-q", "-m", "py")
        sha = git(repo, "rev-parse", "HEAD")
        _table(repo, _entry("always_one"), _entry("only_py", when=["*.py"]))
        _evidence(repo, sha, "always_one")
        assert _run(repo, sha, *MODE) == EXIT_LOGIC
        _evidence(repo, sha, "only_py")
        assert _run(repo, sha, *MODE) == EXIT_OK

    def test_a_missing_applicable_result_is_not_a_pass(
        self,
        clone: tuple[Path, str, str],
    ) -> None:
        repo, first, _ = clone
        _table(repo, _entry("always_one"), _entry("always_two"))
        _evidence(repo, first, "always_one")
        assert _run(repo, first, *MODE) == EXIT_LOGIC

    def test_build_tier_rows_bind_on_the_digest(
        self,
        clone: tuple[Path, str, str],
    ) -> None:
        repo, first, _ = clone
        digest = "c" * 64
        _table(repo, _entry("pack", tier="build"))
        _evidence(repo, first, "pack")
        assert _run(repo, first, "--candidate-digest", digest, *MODE) == EXIT_LOGIC
        _evidence(repo, first, "pack", digest=digest)
        assert _run(repo, first, "--candidate-digest", digest, *MODE) == EXIT_OK

    def test_command_line_names_add_to_the_table(
        self,
        clone: tuple[Path, str, str],
    ) -> None:
        repo, first, _ = clone
        _table(repo, _entry("always_one"))
        _evidence(repo, first, "always_one")
        assert _run(repo, first, "--require", "extra", *MODE) == EXIT_LOGIC

    def test_a_deleted_table_blocks_instead_of_excusing(
        self,
        clone: tuple[Path, str, str],
    ) -> None:
        repo, first, _ = clone
        _evidence(repo, first, "always_one")
        assert _run(repo, first, *MODE) == EXIT_LOGIC

    def test_a_short_require_list_cannot_stand_in_for_a_deleted_table(
        self, clone: tuple[Path, str, str]
    ) -> None:
        repo, first, _ = clone
        _evidence(repo, first, "only_one")
        assert _run(repo, first, "--require", "only_one", *MODE) == EXIT_LOGIC

    def test_an_empty_table_with_a_require_list_blocks(self, clone: tuple[Path, str, str]) -> None:
        repo, first, _ = clone
        _table(repo)
        _evidence(repo, first, "only_one")
        out = repo.parent / "m.json"
        assert _run(repo, first, "--require", "only_one", "--output", str(out), *MODE) == EXIT_LOGIC
        manifest = json.loads(out.read_text(encoding="utf-8"))
        assert manifest["findings"][0]["reason"] == "applicability.absent"

    def test_an_invalid_table_exits_two(self, clone: tuple[Path, str, str]) -> None:
        repo, first, _ = clone
        path = repo / APPLICABILITY_RELATIVE_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{nope", encoding="utf-8")
        assert _run(repo, first) == EXIT_CONFIG

    def test_a_candidate_git_cannot_read_exits_three(
        self,
        clone: tuple[Path, str, str],
    ) -> None:
        repo, _, _ = clone
        _table(repo, _entry("always_one"))
        assert _run(repo, "f" * 40) == EXIT_EXTERNAL


class TestNotApplicable:
    def _repo_with_python(self, repo: Path) -> str:
        (repo / "tool.py").write_text("x", encoding="utf-8")
        git(repo, "add", "tool.py")
        git(repo, "commit", "-q", "-m", "py")
        return git(repo, "rev-parse", "HEAD")

    def test_a_failing_result_from_a_not_applicable_validator_is_not_consulted(
        self, clone: tuple[Path, str, str]
    ) -> None:
        repo, first, _ = clone
        _table(repo, _entry("always_one"), _entry("only_ps", when=["*.ps1"]))
        _evidence(repo, first, "always_one")
        _evidence(repo, first, "only_ps", state="FAIL", reason="x.y", findings=1)
        out = repo.parent / "m.json"
        assert _run(repo, first, "--output", str(out), *MODE) == EXIT_OK
        manifest = json.loads(out.read_text(encoding="utf-8"))
        assert manifest["not_applicable"] == ["only_ps"]

    def test_the_same_validator_blocks_once_its_files_are_present(
        self, clone: tuple[Path, str, str]
    ) -> None:
        repo, _, _ = clone
        sha = self._repo_with_python(repo)
        _table(repo, _entry("always_one"), _entry("only_py", when=["*.py"]))
        _evidence(repo, sha, "always_one")
        _evidence(repo, sha, "only_py", state="FAIL", reason="x.y", findings=1)
        assert _run(repo, sha, *MODE) == EXIT_LOGIC

    def test_a_validator_the_table_does_not_list_is_still_consulted(
        self, clone: tuple[Path, str, str]
    ) -> None:
        repo, first, _ = clone
        _table(repo, _entry("always_one"))
        _evidence(repo, first, "always_one")
        _evidence(repo, first, "stranger", state="FAIL", reason="x.y", findings=1)
        assert _run(repo, first, *MODE) == EXIT_LOGIC

    def test_a_not_applicable_build_result_cannot_make_the_manifest_digest_bound(
        self, clone: tuple[Path, str, str]
    ) -> None:
        repo, first, _ = clone
        digest = "c" * 64
        _table(repo, _entry("always_one"), _entry("pack", tier="build", when=["*.tgz"]))
        _evidence(repo, first, "always_one")
        _evidence(repo, first, "pack", digest=digest)
        out = repo.parent / "m.json"
        assert _run(repo, first, "--candidate-digest", digest, "--output", str(out), *MODE) == (
            EXIT_OK
        )
        assert json.loads(out.read_text(encoding="utf-8"))["digest_bound"] is False

    def test_a_malformed_file_naming_a_not_applicable_validator_is_not_consulted(
        self, clone: tuple[Path, str, str]
    ) -> None:
        repo, first, _ = clone
        _table(repo, _entry("always_one"), _entry("only_ps", when=["*.ps1"]))
        _evidence(repo, first, "always_one")
        (repo.parent / "ev" / "ps.json").write_text(
            json.dumps({"validator": "only_ps", "state": "bogus"}), encoding="utf-8"
        )
        assert _run(repo, first, *MODE) == EXIT_OK
