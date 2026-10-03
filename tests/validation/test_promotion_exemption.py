"""A path-filter skip is accepted as policy.exempt only after it is checked.

Owner decision D26 (issue #5636): "accepted only when the skip is a path-filter
skip on that SHA. Verify the skip against the workflow's path filter and the
diff. Never accept a blanket exemption." Every refusal below leaves the finding
in place, and the drift test pins each table filter key to the real workflow.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.validation.evidence import CheckOutcome, EvidenceState
from scripts.validation.promotion_applicability import Applicability, PathFilter, load_applicability
from scripts.validation.promotion_candidate import (
    CandidateCheckError,
    InvalidCandidateNameError,
    changed_files,
    parent_file,
)
from scripts.validation.promotion_evidence import EvidenceRecord
from scripts.validation.promotion_exemption import (
    GitDiffSource,
    apply_exemption,
    filter_globs,
    is_not_run_skip,
    path_matches,
)
from tests.validation.promotion_gate_helpers import git

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40
WORKFLOW = ".github/workflows/check.yml"
WORKFLOW_TEXT = """
name: Check
jobs:
  check-paths:
    steps:
      - uses: dorny/paths-filter@abc
        with:
          filters: |
            scannable:
              - 'scripts/**'
              - '**/*.py'
            docs:
              - '**.md'
"""


class FakeSource:
    def __init__(self, changed: tuple[str, ...] = (), text: str | None = WORKFLOW_TEXT) -> None:
        self.changed, self.text = changed, text

    def changed_paths(self, sha: str) -> tuple[str, ...]:
        return self.changed

    def parent_text(self, sha: str, path: str) -> str | None:
        return self.text


class BrokenSource(FakeSource):
    def changed_paths(self, sha: str) -> tuple[str, ...]:
        raise CandidateCheckError("git failed")


FILTER = PathFilter("scannable")


def _entry(path_filter: PathFilter | None = FILTER) -> Applicability:
    return Applicability("v", "commit", WORKFLOW, "Job", ("always",), "r", path_filter)


def _record(
    state: EvidenceState = EvidenceState.SKIP, reason: str = "validator.not_run"
) -> EvidenceRecord:
    outcome = CheckOutcome(
        "v", state, revision=SHA, scope="job", reason=reason,
        findings=None, examined=None,
    )  # fmt: skip
    return EvidenceRecord(outcome=outcome, source="v.json")


class TestApply:
    def test_a_skip_with_no_changed_path_in_the_filter_is_exempt(self) -> None:
        got = apply_exemption(_record(), _entry(), SHA, FakeSource(("README.txt", "notes/a.txt")))
        assert (got.outcome.state, got.outcome.reason) == (EvidenceState.SKIP, "policy.exempt")
        assert "none of the 2 changed paths" in got.outcome.detail
        assert got.outcome.revision == SHA

    def test_an_empty_diff_is_exempt(self) -> None:
        assert (
            apply_exemption(_record(), _entry(), SHA, FakeSource(())).outcome.reason
            == "policy.exempt"
        )

    @pytest.mark.parametrize(
        "changed", [("scripts/a.sh",), ("x/y/z.py",), ("top.py",), ("a.txt", "b.py")]
    )
    def test_a_changed_path_the_filter_matches_declines(self, changed: tuple[str, ...]) -> None:
        record = _record()
        assert apply_exemption(record, _entry(), SHA, FakeSource(changed)) is record

    def test_a_row_with_no_path_filter_has_no_exemption(self) -> None:
        record = _record()
        assert apply_exemption(record, _entry(None), SHA, FakeSource(("a.txt",))) is record

    @pytest.mark.parametrize(
        "record",
        [
            _record(EvidenceState.FAIL, "job.failed"),
            _record(EvidenceState.UNKNOWN, "artifact.absent"),
            _record(EvidenceState.BLOCKED, "validator.not_run"),
            _record(EvidenceState.SKIP, "other.reason"),
            _record(EvidenceState.SKIP, "policy.exempt"),
        ],
    )
    def test_only_a_not_run_skip_can_be_exempted(self, record: EvidenceRecord) -> None:
        assert apply_exemption(record, _entry(), SHA, FakeSource(("a.txt",))) is record

    def test_a_pass_is_never_touched(self) -> None:
        passed = EvidenceRecord(CheckOutcome.passed("v", revision=SHA, scope="s", examined=1))
        assert apply_exemption(passed, _entry(), SHA, FakeSource(("a.txt",))) is passed

    @pytest.mark.parametrize(
        "text",
        [None, "", "not: [valid", "jobs: {}", WORKFLOW_TEXT.replace("scannable", "other")],
    )
    def test_an_unreadable_or_keyless_parent_workflow_declines(self, text: str | None) -> None:
        record = _record()
        assert apply_exemption(record, _entry(), SHA, FakeSource(("a.txt",), text)) is record

    def test_a_git_failure_declines(self) -> None:
        record = _record()
        assert apply_exemption(record, _entry(), SHA, BrokenSource(("a.txt",))) is record

    def test_an_invalid_name_declines(self) -> None:
        class Bad(FakeSource):
            def parent_text(self, sha: str, path: str) -> str | None:
                raise InvalidCandidateNameError("bad")

        record = _record()
        assert apply_exemption(record, _entry(), SHA, Bad(("a.txt",))) is record

    def test_is_not_run_skip_reads_state_and_reason(self) -> None:
        assert is_not_run_skip(_record())
        assert not is_not_run_skip(_record(EvidenceState.SKIP, "x.y"))


class TestFilterGlobs:
    def test_reads_the_named_key(self) -> None:
        assert filter_globs(WORKFLOW_TEXT, "scannable") == ("scripts/**", "**/*.py")
        assert filter_globs(WORKFLOW_TEXT, "docs") == ("**.md",)

    @pytest.mark.parametrize(
        "glob", ["src/{a,b}/**", "!docs/**", "a/**/b", "x/(a|b)", "a+(b)", "@(a)", "[ab]/**", "a|b"]
    )
    def test_a_glob_the_matcher_could_read_narrower_than_the_action_refuses_the_filter(
        self, glob: str
    ) -> None:
        text = (
            "jobs:\n  j:\n    steps:\n      - uses: dorny/paths-filter@x\n        with:\n"
            "          filters: |\n            scannable:\n"
            f"              - '{glob}'\n              - 'scripts/**'\n"
        )
        assert filter_globs(text, "scannable") is None

    def test_deeply_nested_yaml_declines_instead_of_crashing(self) -> None:
        assert filter_globs("[" * 50000, "scannable") is None

    def test_a_missing_key_is_none(self) -> None:
        assert filter_globs(WORKFLOW_TEXT, "nope") is None

    @pytest.mark.parametrize(
        "body",
        [
            "scannable: []",
            "scannable: 'x'",
            "scannable: [1, 2]",
            "- not a mapping",
            'scannable: ["a"\n  bad: [',
        ],
    )
    def test_a_malformed_filter_is_none(self, body: str) -> None:
        text = (
            "jobs:\n  j:\n    steps:\n      - uses: dorny/paths-filter@x\n        with:\n"
            "          filters: |\n"
            + "".join(f"            {line}\n" for line in body.splitlines())
        )
        assert filter_globs(text, "scannable") is None

    def test_two_definitions_of_one_key_are_ambiguous(self) -> None:
        extra = (
            "jobs:\n  other:\n    steps:\n      - uses: dorny/paths-filter@x\n"
            "        with:\n          filters: |\n"
            "            scannable:\n              - 'a/**'"
        )
        doubled = WORKFLOW_TEXT.replace("jobs:", extra)
        assert filter_globs(doubled, "scannable") is None

    @pytest.mark.parametrize(
        "text", ["", "[", "jobs: 5", "jobs:\n  j: 5", "jobs:\n  j:\n    steps: 5"]
    )
    def test_a_workflow_that_does_not_fit_is_none(self, text: str) -> None:
        assert filter_globs(text, "scannable") is None

    def test_a_step_that_is_not_the_paths_filter_is_ignored(self) -> None:
        text = (
            "jobs:\n  j:\n    steps:\n      - uses: other/action@x\n        with:\n"
            "          filters: 'scannable: [a]'\n      - run: x\n      - 5\n"
        )
        assert filter_globs(text, "scannable") is None

    def test_a_paths_filter_step_without_a_filters_string_is_ignored(self) -> None:
        text = (
            "jobs:\n  j:\n    steps:\n      - uses: dorny/paths-filter@x\n"
            "      - uses: dorny/paths-filter@x\n        with: {filters: 5}\n"
        )
        assert filter_globs(text, "scannable") is None


class TestPathMatches:
    @pytest.mark.parametrize(
        ("path", "globs", "expected"),
        [
            ("scripts/a/b.sh", ["scripts/**"], True),
            ("top.py", ["**/*.py"], True),
            ("a/b/c.py", ["**/*.py"], True),
            ("a.md", ["**.md"], True),
            ("x/a.md", ["**.md"], True),
            ("docs/a.txt", ["scripts/**", "**/*.py"], False),
            ("scriptsx/a", ["scripts/**"], False),
            ("", ["scripts/**"], False),
        ],
    )
    def test_matching(self, path: str, globs: list[str], expected: bool) -> None:
        assert path_matches(path, globs) is expected


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "r"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    workflow = repo / WORKFLOW
    workflow.parent.mkdir(parents=True)
    workflow.write_text(WORKFLOW_TEXT, encoding="utf-8")
    (repo / "a.txt").write_text("1", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "one")
    (repo / "notes").mkdir()
    (repo / "notes" / "n.txt").write_text("2", encoding="utf-8")
    (repo / "weird\nname").write_text("3", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "two")
    return repo, git(repo, "rev-parse", "HEAD")


class TestGit:
    def test_changed_files_lists_the_first_parent_diff(self, tmp_path: Path) -> None:
        repo, sha = _repo(tmp_path)
        assert sorted(changed_files(repo, sha)) == ["notes/n.txt", "weird\nname"]

    def test_a_rename_lists_both_the_old_and_the_new_path(self, tmp_path: Path) -> None:
        repo, _ = _repo(tmp_path)
        (repo / "scripts").mkdir()
        (repo / "scripts" / "a.py").write_text("print('a')\n" * 20, encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "add")
        git(repo, "mv", "scripts/a.py", "elsewhere.txt")
        git(repo, "commit", "-q", "-m", "rename out of the filtered path")
        head = git(repo, "rev-parse", "HEAD")
        assert sorted(changed_files(repo, head)) == ["elsewhere.txt", "scripts/a.py"]
        record = _record()
        assert apply_exemption(record, _entry(), head, GitDiffSource(repo)) is record

    def test_a_root_commit_has_no_diff_to_read(self, tmp_path: Path) -> None:
        repo, _ = _repo(tmp_path)
        root = git(repo, "rev-list", "--max-parents=0", "HEAD")
        with pytest.raises(CandidateCheckError):
            changed_files(repo, root)

    @pytest.mark.parametrize("sha", ["--all", "abc", "A" * 40, ""])
    def test_a_non_sha_is_refused(self, tmp_path: Path, sha: str) -> None:
        repo, _ = _repo(tmp_path)
        with pytest.raises(InvalidCandidateNameError):
            changed_files(repo, sha)
        with pytest.raises(InvalidCandidateNameError):
            parent_file(repo, sha, WORKFLOW)

    def test_parent_file_reads_the_parent_copy(self, tmp_path: Path) -> None:
        repo, sha = _repo(tmp_path)
        (repo / WORKFLOW).write_text("changed", encoding="utf-8")
        git(repo, "commit", "-q", "-am", "three")
        head = git(repo, "rev-parse", "HEAD")
        assert parent_file(repo, head, WORKFLOW) == WORKFLOW_TEXT
        assert parent_file(repo, sha, "notes/n.txt") is None
        assert parent_file(repo, sha, "never/existed.txt") is None

    @pytest.mark.parametrize("path", ["/etc/passwd", "-x", "../x", "a/../b"])
    def test_parent_file_refuses_a_path_that_leaves_the_repository(
        self, tmp_path: Path, path: str
    ) -> None:
        repo, sha = _repo(tmp_path)
        with pytest.raises(InvalidCandidateNameError):
            parent_file(repo, sha, path)

    def test_parent_file_of_a_root_commit_raises(self, tmp_path: Path) -> None:
        repo, _ = _repo(tmp_path)
        root = git(repo, "rev-list", "--max-parents=0", "HEAD")
        with pytest.raises(CandidateCheckError):
            parent_file(repo, root, WORKFLOW)

    def test_a_real_clone_exempts_a_skip_and_declines_a_matching_diff(self, tmp_path: Path) -> None:
        repo, sha = _repo(tmp_path)
        source = GitDiffSource(repo)
        assert apply_exemption(_record(), _entry(), sha, source).outcome.reason == "policy.exempt"
        (repo / "tool.py").write_text("x", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "py")
        head = git(repo, "rev-parse", "HEAD")
        record = _record()
        assert apply_exemption(record, _entry(), head, source) is record

    def test_a_commit_cannot_narrow_its_own_filter_to_excuse_itself(self, tmp_path: Path) -> None:
        repo, _ = _repo(tmp_path)
        narrowed = WORKFLOW_TEXT.replace(
            "- 'scripts/**'\n              - '**/*.py'", "- 'nothing/**'"
        )
        (repo / WORKFLOW).write_text(narrowed, encoding="utf-8")
        (repo / "tool.py").write_text("x", encoding="utf-8")
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "narrow and change")
        head = git(repo, "rev-parse", "HEAD")
        record = _record()
        assert apply_exemption(record, _entry(), head, GitDiffSource(repo)) is record


class TestTableDrift:
    """Each filter key in the shipped table must resolve in the workflow it names."""

    def _rows(self) -> list[Applicability]:
        return [r for r in load_applicability(ROOT) if r.path_filter]

    def test_the_table_has_rows_with_a_path_filter(self) -> None:
        assert {r.validator for r in self._rows()} >= {
            "analyze_actions", "analyze_python", "validate_generated_files",
            "validate_path_normalization", "validate_plugin_version_bump",
        }  # fmt: skip

    def test_every_filter_key_resolves_in_its_workflow(self) -> None:
        for row in self._rows():
            assert row.path_filter is not None
            text = (ROOT / row.workflow).read_text(encoding="utf-8")
            assert filter_globs(text, row.path_filter.key), (row.validator, row.path_filter.key)

    def test_the_two_pr_only_rows_have_no_exemption_path(self) -> None:
        by_name: dict[str, Any] = {r.validator: r for r in load_applicability(ROOT)}
        assert by_name["validate_pr"].path_filter is None
        assert by_name["validate_pr_title"].path_filter is None

    def test_a_workflow_touching_change_matches_every_shipped_filter(self) -> None:
        """Editing the workflow itself must never read as an irrelevant diff."""
        for row in self._rows():
            assert row.path_filter is not None
            text = (ROOT / row.workflow).read_text(encoding="utf-8")
            globs = filter_globs(text, row.path_filter.key) or ()
            assert path_matches(row.workflow, globs), row.validator


# ---- through the fetch and the gate -------------------------------------------------

import json

from scripts.validation.emit_validator_evidence import build_outcome
from scripts.validation.promotion_evidence import (
    Candidate,
    bind_records,
    load_evidence_dir,
)
from scripts.validation.promotion_fetch import fetch_verified_evidence
from scripts.validation.promotion_findings import collect_findings, missing_outcomes
from tests.validation.promotion_fetch_helpers import FakeReader, _good, _zip

NAME = "run_python_tests"


def _skip_reader(job_name: str = "Run Python Tests", succeeded: bool = True) -> FakeReader:
    outcome = build_outcome(
        validator=NAME, job_status="success", ran=False, revision=SHA, scope="job j on push"
    )
    reader = _good(archives={77: _zip(f"{NAME}.json", json.dumps(outcome.to_dict()))})
    reader.jobs[0]["name"] = job_name
    reader.checks[0]["name"] = job_name
    if not succeeded:
        reader.checks[0]["conclusion"] = "skipped"
    return reader


def _through_the_gate(tmp_path: Path, reader: FakeReader, entry: Applicability, source: Any):
    fetch_verified_evidence(
        reader, repo="owner/repo", candidate_sha=SHA, default_branch="main",
        entries=[entry], evidence_dir=tmp_path / "ev", exemption_source=source,
    )  # fmt: skip
    records, _ = load_evidence_dir(tmp_path / "ev")
    bound = bind_records(records, Candidate(SHA), frozenset())
    synthesized = missing_outcomes([NAME], bound.bound, Candidate(SHA))
    return bound, collect_findings(bound.bound, synthesized)


def _row(path_filter: PathFilter | None, job: str = "Run Python Tests") -> Applicability:
    return Applicability(
        NAME, "commit", ".github/workflows/pytest.yml", job, ("always",), "r", path_filter
    )


class TestThroughTheFetch:
    def test_a_verified_path_filter_skip_is_no_finding_at_the_gate(self, tmp_path: Path) -> None:
        bound, findings = _through_the_gate(
            tmp_path, _skip_reader(), _row(FILTER), FakeSource(("README.txt",))
        )
        assert [r.outcome.reason for r in bound.bound] == ["policy.exempt"]
        assert findings == ()

    def test_a_skip_whose_diff_matches_the_filter_stays_a_finding(self, tmp_path: Path) -> None:
        bound, findings = _through_the_gate(
            tmp_path, _skip_reader(), _row(FILTER), FakeSource(("scripts/a.sh",))
        )
        assert [r.outcome.reason for r in bound.bound] == ["validator.not_run"]
        assert len(findings) == 1

    def test_a_row_with_no_path_filter_stays_a_finding(self, tmp_path: Path) -> None:
        _, findings = _through_the_gate(tmp_path, _skip_reader(), _row(None), FakeSource(("x",)))
        assert len(findings) == 1

    def test_no_diff_source_means_no_exemption(self, tmp_path: Path) -> None:
        _, findings = _through_the_gate(tmp_path, _skip_reader(), _row(FILTER), None)
        assert len(findings) == 1

    def test_the_skip_job_corroborates_when_the_main_job_is_skipped(self, tmp_path: Path) -> None:
        reader = _skip_reader(job_name="Skipped Variant")
        row = _row(PathFilter("scannable", "Skipped Variant"), job="Main Job")
        bound, findings = _through_the_gate(tmp_path, reader, row, FakeSource(("README.txt",)))
        assert [r.outcome.reason for r in bound.bound] == ["policy.exempt"]
        assert findings == ()

    def test_a_skip_job_that_did_not_succeed_is_not_exempt(self, tmp_path: Path) -> None:
        reader = _skip_reader(job_name="Skipped Variant", succeeded=False)
        row = _row(PathFilter("scannable", "Skipped Variant"), job="Main Job")
        bound, findings = _through_the_gate(tmp_path, reader, row, FakeSource(("README.txt",)))
        assert [r.outcome.state for r in bound.bound] == [EvidenceState.UNKNOWN]
        assert len(findings) == 1

    def test_a_skip_with_the_main_job_skipped_and_no_skip_job_is_not_exempt(
        self, tmp_path: Path
    ) -> None:
        reader = _skip_reader(succeeded=False)
        bound, findings = _through_the_gate(tmp_path, reader, _row(FILTER), FakeSource(("x",)))
        assert [r.outcome.state for r in bound.bound] == [EvidenceState.UNKNOWN]
        assert len(findings) == 1

    def test_a_failed_job_is_never_softened(self, tmp_path: Path) -> None:
        outcome = build_outcome(
            validator=NAME, job_status="failure", ran=False, revision=SHA, scope="s"
        )
        reader = _good(archives={77: _zip(f"{NAME}.json", json.dumps(outcome.to_dict()))})
        bound, findings = _through_the_gate(tmp_path, reader, _row(FILTER), FakeSource(("x",)))
        assert [r.outcome.state for r in bound.bound] == [EvidenceState.FAIL]
        assert len(findings) == 1
