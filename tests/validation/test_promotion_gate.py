"""The promotion gate: bind, classify, report, and exit.

ADR-113 decisions 1, 3, 4, 7, 8, and 9, issue #5636. Every path that could let a
promotion through without evidence has a test asserting the verdict is ``block``,
and the CLI tests assert the exit code, not only the manifest.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.evidence import EvidenceState
from scripts.validation.promotion_evidence import Candidate
from scripts.validation.promotion_exceptions import EXCEPTIONS_RELATIVE_PATH, ExceptionsFileError
from scripts.validation.promotion_findings import Finding, PreviousFinding, PreviousManifest
from scripts.validation.promotion_gate import (
    EXIT_CONFIG,
    EXIT_EXTERNAL,
    EXIT_LOGIC,
    EXIT_OK,
    MODE_ENFORCING,
    main,
    run_gate,
)

SHA = "a" * 40
OTHER = "b" * 40
DIGEST = "c" * 64
TODAY = date(2026, 10, 1)


def _evidence(**overrides: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "validator": "pytest",
        "state": "PASS",
        "revision": SHA,
        "scope": "tests/",
        "examined": 5,
        "findings": 0,
    }
    doc.update(overrides)
    return doc


def _fail(**overrides: Any) -> dict[str, Any]:
    return _evidence(state="FAIL", reason="tests.failed", findings=1, **overrides)


def _write(directory: Path, name: str, doc: dict[str, Any] | str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    text = doc if isinstance(doc, str) else json.dumps(doc)
    (directory / name).write_text(text, encoding="utf-8")


def _exception_file(root: Path, **overrides: Any) -> None:
    entry: dict[str, Any] = {
        "validator": "pytest",
        "reason": "tests.failed",
        "scope": "tests/",
        "rationale": "Tracked flaky test.",
        "owner": "rjmurillo",
        "approval": {"pr": 1, "reviewer": "second"},
        "expires": "2026-12-31",
        "remediate_by": "2026-11-30",
    }
    entry.update(overrides)
    path = root / EXCEPTIONS_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "1", "entries": [entry]}), encoding="utf-8")


def _run(tmp_path: Path, **kwargs: Any):
    return run_gate(
        repo_root=tmp_path,
        evidence_dir=tmp_path / "ev",
        candidate=kwargs.pop("candidate", Candidate(SHA)),
        today=TODAY,
        **kwargs,
    )


class TestVerdict:
    def test_clean_evidence_promotes(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        result = _run(tmp_path, required=["pytest"])
        assert result.manifest["verdict"] == "promote"
        assert result.manifest["state"] == "PASS"
        assert result.exit_code == EXIT_OK

    def test_empty_evidence_blocks(self, tmp_path: Path) -> None:
        (tmp_path / "ev").mkdir()
        result = _run(tmp_path, mode=MODE_ENFORCING)
        assert result.manifest["verdict"] == "block"
        assert result.manifest["state"] == "UNKNOWN"
        assert result.manifest["findings"][0]["reason"] == "applicability.absent"
        assert result.exit_code == EXIT_LOGIC

    def test_missing_required_validator_blocks(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        result = _run(tmp_path, required=["pytest", "semgrep"], mode=MODE_ENFORCING)
        reasons = {f["validator"]: f["reason"] for f in result.manifest["findings"]}
        assert reasons == {"semgrep": "evidence.missing"}
        assert result.exit_code == EXIT_LOGIC

    def test_failing_validator_blocks_as_unresolved(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _fail())
        result = _run(tmp_path, required=["pytest"], mode=MODE_ENFORCING)
        assert result.manifest["counts"]["unresolved"] == 1
        assert result.exit_code == EXIT_LOGIC

    def test_evidence_for_another_sha_is_rejected_and_counts_as_missing(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence(revision=OTHER))
        result = _run(tmp_path, required=["pytest"], mode=MODE_ENFORCING)
        assert result.manifest["evidence"]["bound"] == 0
        assert result.manifest["evidence"]["rejected"][0]["reason"] == "binding.revision_mismatch"
        assert result.manifest["verdict"] == "block"

    def test_build_validator_needs_the_digest(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pack.json", _evidence(validator="pack-size", digest=DIGEST))
        ok = _run(
            tmp_path,
            candidate=Candidate(SHA, DIGEST),
            required=["pack-size"],
            build_validators=frozenset({"pack-size"}),
        )
        assert ok.manifest["verdict"] == "promote"
        bad = _run(
            tmp_path,
            candidate=Candidate(SHA, "d" * 64),
            required=["pack-size"],
            build_validators=frozenset({"pack-size"}),
        )
        assert bad.manifest["verdict"] == "block"

    def test_malformed_evidence_file_blocks(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        _write(tmp_path / "ev", "junk.json", "{nope")
        result = _run(tmp_path)
        assert result.manifest["verdict"] == "block"
        assert result.manifest["findings"][0]["reason"] == "evidence.malformed"

    def test_exempt_skip_on_an_unrequired_validator_does_not_block(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        _write(
            tmp_path / "ev",
            "lint.json",
            _evidence(validator="lint", state="SKIP", reason="policy.exempt"),
        )
        assert _run(tmp_path, required=["pytest"]).manifest["verdict"] == "promote"

    def test_a_required_validator_showing_only_an_exempt_skip_blocks(self, tmp_path: Path) -> None:
        """The record is candidate-writable, so it cannot exempt itself."""
        _write(tmp_path / "ev", "pytest.json", _evidence(state="SKIP", reason="policy.exempt"))
        result = _run(tmp_path, required=["pytest"], mode=MODE_ENFORCING)
        assert result.manifest["verdict"] == "block"
        assert result.manifest["findings"][0]["reason"] == "evidence.missing"
        assert result.exit_code == EXIT_LOGIC

    def test_one_unrelated_pass_with_no_required_set_blocks(self, tmp_path: Path) -> None:
        """An empty required set is not a clean sheet."""
        _write(tmp_path / "ev", "other.json", _evidence(validator="other"))
        result = _run(tmp_path, mode=MODE_ENFORCING)
        assert result.manifest["verdict"] == "block"
        assert result.manifest["findings"][0]["reason"] == "applicability.absent"
        assert result.exit_code == EXIT_LOGIC

    def test_other_skip_blocks(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence(state="SKIP", reason="policy.quick_mode"))
        assert _run(tmp_path).manifest["verdict"] == "block"


class TestExceptions:
    def test_an_exception_is_not_honoured_without_a_second_approver(self, tmp_path: Path) -> None:
        """Decision 7: deny_all_approvals leaves the finding unresolved."""
        _write(tmp_path / "ev", "pytest.json", _fail())
        _exception_file(tmp_path)
        result = _run(tmp_path, mode=MODE_ENFORCING)
        finding = result.manifest["findings"][0]
        assert finding["class"] == "unresolved"
        assert "unapproved" in finding["note"]
        assert result.exit_code == EXIT_LOGIC
        assert result.manifest["exceptions"]["loaded"] == 1

    def test_a_lapsed_exception_makes_the_finding_expired(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _fail())
        _exception_file(tmp_path, expires="2026-09-30", remediate_by="2026-09-30")
        result = _run(tmp_path, mode=MODE_ENFORCING)
        assert result.manifest["findings"][0]["class"] == "expired"
        assert result.manifest["counts"]["expired"] == 1
        assert result.exit_code == EXIT_LOGIC

    def test_invalid_exceptions_file_raises(self, tmp_path: Path) -> None:
        (tmp_path / "ev").mkdir()
        path = tmp_path / EXCEPTIONS_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        path.write_text("{nope", encoding="utf-8")
        with pytest.raises(ExceptionsFileError):
            _run(tmp_path)


class TestRemediated:
    def _previous(self, fingerprint: str) -> PreviousManifest:
        finding = PreviousFinding(fingerprint, "pytest", "r.x", "tests/", "")
        return PreviousManifest(OTHER, (finding,))

    def test_first_promotion_reports_no_remediated(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        assert _run(tmp_path).manifest["remediated"] == []

    def test_a_finding_gone_since_the_last_promotion_is_remediated(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        result = _run(tmp_path, previous=self._previous("gone"), required=["pytest"])
        (entry,) = result.manifest["remediated"]
        assert entry["fixed_between"] == f"{OTHER}..{SHA}"
        assert result.manifest["counts"]["remediated"] == 1
        assert result.manifest["verdict"] == "promote"

    def test_a_finding_whose_validator_did_not_re_run_is_not_remediated(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path / "ev", "other.json", _evidence(validator="other"))
        result = _run(tmp_path, previous=self._previous("gone"), required=["other"])
        assert result.manifest["remediated"] == []

    def test_a_finding_whose_evidence_was_rejected_is_not_remediated(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence(revision=OTHER))
        result = _run(tmp_path, previous=self._previous("gone"), required=["pytest"])
        assert result.manifest["remediated"] == []

    def test_a_finding_that_still_reproduces_is_not_remediated(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _fail())
        same = Finding("pytest", "tests.failed", "tests/", "", EvidenceState.FAIL).fingerprint
        result = _run(tmp_path, previous=self._previous(same))
        assert result.manifest["remediated"] == []


class TestAdvisory:
    def test_advisory_blocked_run_exits_zero_and_says_so(self, tmp_path: Path) -> None:
        (tmp_path / "ev").mkdir()
        result = _run(tmp_path)
        assert result.manifest["verdict"] == "block"
        assert result.manifest["enforced"] is False
        assert result.manifest["mode"] == "advisory"
        assert result.exit_code == EXIT_OK

    def test_enforcing_manifest_says_enforced(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        assert _run(tmp_path, mode=MODE_ENFORCING).manifest["enforced"] is True


class TestCli:
    def _args(self, tmp_path: Path, *extra: str) -> list[str]:
        return [
            "--repo-root", str(tmp_path),
            "--evidence-dir", str(tmp_path / "ev"),
            "--candidate-sha", SHA,
            "--today", TODAY.isoformat(),
            *extra,
        ]  # fmt: skip

    def test_clean_run_exits_zero_and_writes_the_manifest(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        out = tmp_path / "manifest.json"
        code = main(self._args(tmp_path, "--output", str(out), "--require", "pytest"))
        assert code == EXIT_OK
        assert json.loads(out.read_text(encoding="utf-8"))["verdict"] == "promote"
        assert "promotion gate: promote" in capsys.readouterr().out

    def test_enforcing_block_exits_one(self, tmp_path: Path) -> None:
        (tmp_path / "ev").mkdir()
        assert main(self._args(tmp_path, "--mode", "enforcing")) == EXIT_LOGIC

    def test_advisory_block_prints_would_block_and_exits_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "ev").mkdir()
        assert main(self._args(tmp_path)) == EXIT_OK
        assert "WOULD BLOCK" in capsys.readouterr().out

    def test_bad_sha_exits_two(self, tmp_path: Path) -> None:
        args = self._args(tmp_path)
        args[args.index(SHA)] = "abc"
        assert main(args) == EXIT_CONFIG

    def test_bad_digest_exits_two(self, tmp_path: Path) -> None:
        assert main(self._args(tmp_path, "--candidate-digest", "xyz")) == EXIT_CONFIG

    def test_invalid_exceptions_file_exits_two(self, tmp_path: Path) -> None:
        (tmp_path / "ev").mkdir()
        path = tmp_path / EXCEPTIONS_RELATIVE_PATH
        path.parent.mkdir(parents=True)
        path.write_text("{nope", encoding="utf-8")
        assert main(self._args(tmp_path)) == EXIT_CONFIG

    def test_missing_evidence_dir_exits_three(self, tmp_path: Path) -> None:
        assert main(self._args(tmp_path)) == EXIT_EXTERNAL

    def test_bad_previous_manifest_exits_two(self, tmp_path: Path) -> None:
        (tmp_path / "ev").mkdir()
        previous = tmp_path / "prev.json"
        previous.write_text("{nope", encoding="utf-8")
        assert main(self._args(tmp_path, "--previous-manifest", str(previous))) == EXIT_CONFIG

    def test_missing_previous_manifest_exits_two(self, tmp_path: Path) -> None:
        (tmp_path / "ev").mkdir()
        absent = tmp_path / "absent.json"
        assert main(self._args(tmp_path, "--previous-manifest", str(absent))) == EXIT_CONFIG

    def test_previous_manifest_feeds_remediated(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        previous = tmp_path / "prev.json"
        previous.write_text(
            json.dumps(
                {
                    "schema_version": "1",
                    "candidate": {"sha": OTHER},
                    "findings": [
                        {
                            "fingerprint": "gone",
                            "class": "unresolved",
                            "validator": "pytest",
                            "reason": "r.x",
                            "scope": "tests/",
                            "item": "",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        out = tmp_path / "m.json"
        args = self._args(tmp_path, "--previous-manifest", str(previous), "--output", str(out))
        assert main([*args, "--require", "pytest"]) == EXIT_OK
        assert json.loads(out.read_text(encoding="utf-8"))["counts"]["remediated"] == 1

    def test_build_validator_flag_binds_on_digest(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pack.json", _evidence(validator="pack-size", digest=DIGEST))
        args = self._args(
            tmp_path, "--candidate-digest", DIGEST, "--build-validator", "pack-size",
            "--require", "pack-size", "--mode", "enforcing",
        )  # fmt: skip
        assert main(args) == EXIT_OK
        _write(tmp_path / "ev", "pack.json", _evidence(validator="pack-size"))
        assert main(args) == EXIT_LOGIC

    def test_unreadable_evidence_dir_entry_never_promotes(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        (tmp_path / "ev" / "dir.json").mkdir()
        args = self._args(tmp_path, "--mode", "enforcing", "--require", "pytest")
        assert main(args) == EXIT_LOGIC

    def test_github_output_is_advisory_ineligible_even_when_the_verdict_is_promote(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        sink = tmp_path / "out.txt"
        args = self._args(tmp_path, "--github-output", str(sink), "--require", "pytest")
        assert main(args) == EXIT_OK
        assert sink.read_text(encoding="utf-8").splitlines() == [
            "verdict=promote",
            "release_eligible=false",
        ]

    def test_github_output_is_eligible_only_for_an_enforced_promote(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        sink = tmp_path / "out.txt"
        args = self._args(
            tmp_path, "--github-output", str(sink), "--require", "pytest", "--mode", "enforcing"
        )
        assert main(args) == EXIT_OK
        assert sink.read_text(encoding="utf-8").splitlines() == [
            "verdict=promote",
            "release_eligible=true",
        ]

    def test_github_output_for_a_block_is_ineligible(self, tmp_path: Path) -> None:
        (tmp_path / "ev").mkdir()
        sink = tmp_path / "out.txt"
        main(self._args(tmp_path, "--github-output", str(sink), "--mode", "enforcing"))
        assert sink.read_text(encoding="utf-8").splitlines() == [
            "verdict=block",
            "release_eligible=false",
        ]

    def test_unwritable_output_exits_three(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        bad = tmp_path / "no-such-dir" / "m.json"
        args = self._args(tmp_path, "--output", str(bad), "--require", "pytest")
        assert main(args) == EXIT_EXTERNAL

    def test_unwritable_github_output_exits_three(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        bad = tmp_path / "no-such-dir" / "out.txt"
        args = self._args(tmp_path, "--github-output", str(bad), "--require", "pytest")
        assert main(args) == EXIT_EXTERNAL


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
        env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
             "PATH": os.environ["PATH"], "HOME": str(repo)},
    )  # fmt: skip
    return result.stdout.strip()


@pytest.fixture
def clone(tmp_path: Path) -> tuple[Path, str, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    (repo / "a").write_text("1", encoding="utf-8")
    _git(repo, "add", "a")
    _git(repo, "commit", "-q", "-m", "one")
    first = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "-b", "side")
    (repo / "b").write_text("2", encoding="utf-8")
    _git(repo, "add", "b")
    _git(repo, "commit", "-q", "-m", "side")
    side = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "main")
    _git(repo, "tag", "v1", first)
    return repo, first, side


class TestCandidatePlacement:
    def _args(self, repo: Path, sha: str, *extra: str) -> list[str]:
        ev = repo.parent / "ev"
        ev.mkdir(exist_ok=True)
        return [
            "--repo-root", str(repo), "--evidence-dir", str(ev), "--candidate-sha", sha,
            "--today", TODAY.isoformat(), *extra,
        ]  # fmt: skip

    def test_an_ancestor_of_main_is_accepted(self, clone: tuple[Path, str, str]) -> None:
        repo, first, _ = clone
        assert main(self._args(repo, first, "--ancestor-of", "main")) == EXIT_OK

    def test_a_commit_not_on_main_is_refused(self, clone: tuple[Path, str, str]) -> None:
        repo, _, side = clone
        assert main(self._args(repo, side, "--ancestor-of", "main")) == EXIT_CONFIG

    def test_a_tag_naming_the_candidate_is_accepted(self, clone: tuple[Path, str, str]) -> None:
        repo, first, _ = clone
        assert main(self._args(repo, first, "--expect-tag", "v1")) == EXIT_OK

    def test_a_tag_naming_another_commit_is_refused(self, clone: tuple[Path, str, str]) -> None:
        repo, _, side = clone
        assert main(self._args(repo, side, "--expect-tag", "v1")) == EXIT_CONFIG

    def test_a_missing_tag_is_refused(self, clone: tuple[Path, str, str]) -> None:
        repo, first, _ = clone
        assert main(self._args(repo, first, "--expect-tag", "v9")) == EXIT_CONFIG

    def test_a_flag_shaped_ref_exits_three(self, clone: tuple[Path, str, str]) -> None:
        repo, first, _ = clone
        assert main(self._args(repo, first, "--ancestor-of=--all")) == EXIT_EXTERNAL

    def test_a_flag_shaped_tag_exits_three(self, clone: tuple[Path, str, str]) -> None:
        repo, first, _ = clone
        assert main(self._args(repo, first, "--expect-tag=-v1")) == EXIT_EXTERNAL

    def test_an_unknown_ref_exits_three(self, clone: tuple[Path, str, str]) -> None:
        repo, first, _ = clone
        assert main(self._args(repo, first, "--ancestor-of", "nope")) == EXIT_EXTERNAL

    def test_a_non_repository_exits_three(self, tmp_path: Path) -> None:
        sha = "a" * 40
        args = ["--repo-root", str(tmp_path), "--evidence-dir", str(tmp_path),
                "--candidate-sha", sha, "--ancestor-of", "main"]  # fmt: skip
        assert main(args) == EXIT_EXTERNAL


class TestGitFailures:
    def test_git_that_cannot_run_exits_three(
        self, clone: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, first, _ = clone

        def boom(*_a: Any, **_k: Any) -> None:
            raise subprocess.TimeoutExpired("git", 1)

        monkeypatch.setattr(subprocess, "run", boom)
        args = ["--repo-root", str(repo), "--evidence-dir", str(repo), "--candidate-sha", first,
                "--ancestor-of", "main"]  # fmt: skip
        assert main(args) == EXIT_EXTERNAL

    def test_rev_parse_failure_other_than_missing_exits_three(
        self, clone: tuple[Path, str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, first, _ = clone

        def failing(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess([], 128, "", "fatal")

        monkeypatch.setattr(subprocess, "run", failing)
        args = ["--repo-root", str(repo), "--evidence-dir", str(repo), "--candidate-sha", first,
                "--expect-tag", "v1"]  # fmt: skip
        assert main(args) == EXIT_EXTERNAL
