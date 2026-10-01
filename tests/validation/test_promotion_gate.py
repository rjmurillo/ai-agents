"""The promotion gate: bind, classify, report, and exit.

ADR-113 decisions 1, 3, 4, 7, 8, and 9, issue #5636. Every path that could let a
promotion through without evidence has a test asserting the verdict is ``block``,
and the CLI tests assert the exit code, not only the manifest.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts.validation import promotion_gate as gate
from scripts.validation.evidence import EvidenceState
from scripts.validation.promotion_evidence import Candidate
from scripts.validation.promotion_exceptions import (
    EXCEPTIONS_RELATIVE_PATH,
    ExceptionsFileError,
    finding_fingerprint,
)
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
ENFORCING = ("--mode", "enforcing", "--ancestor-of", "HEAD")


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
    @pytest.fixture(autouse=True)
    def _git_answers_yes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Mock the git boundary. test_promotion_candidate.py drives real repositories."""
        monkeypatch.setattr(gate, "candidate_on_branch", lambda *_a: (True, "ok"))
        monkeypatch.setattr(gate, "tag_names_candidate", lambda *_a: (True, "ok"))

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
        assert main(self._args(tmp_path, *ENFORCING)) == EXIT_LOGIC

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
                    "verdict": "promote",
                    "enforced": True,
                    "candidate": {"sha": OTHER},
                    "findings": [
                        {
                            "fingerprint": finding_fingerprint("pytest", "r.x", "tests/", ""),
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
            "--require", "pack-size", *ENFORCING,
        )  # fmt: skip
        assert main(args) == EXIT_OK
        _write(tmp_path / "ev", "pack.json", _evidence(validator="pack-size"))
        assert main(args) == EXIT_LOGIC

    def test_unreadable_evidence_dir_entry_never_promotes(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        (tmp_path / "ev" / "dir.json").mkdir()
        args = self._args(tmp_path, *ENFORCING, "--require", "pytest")
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

    def _eligible_args(self, tmp_path: Path, sink: Path, *extra: str) -> list[str]:
        """Enforced, digest-bound promote with a build-tier result and a tag check."""
        _write(tmp_path / "ev", "pytest.json", _evidence())
        _write(tmp_path / "ev", "pack.json", _evidence(validator="pack", digest=DIGEST))
        return self._args(
            tmp_path, "--github-output", str(sink), "--require", "pytest", "--require", "pack",
            "--build-validator", "pack", "--candidate-digest", DIGEST, *ENFORCING, *extra,
        )  # fmt: skip

    def _lines(self, sink: Path) -> list[str]:
        return sink.read_text(encoding="utf-8").splitlines()

    def test_eligible_only_for_an_enforced_tag_checked_digest_bound_promote(
        self, tmp_path: Path
    ) -> None:
        sink = tmp_path / "out.txt"
        args = self._eligible_args(tmp_path, sink, "--expect-tag", "v1")
        assert main(args) == EXIT_OK
        assert self._lines(sink) == ["verdict=promote", "release_eligible=true"]

    def test_a_commit_only_promote_is_ineligible_without_a_digest(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        sink = tmp_path / "out.txt"
        args = self._args(
            tmp_path, "--github-output", str(sink), "--require", "pytest", *ENFORCING,
            "--expect-tag", "v1",
        )  # fmt: skip
        assert main(args) == EXIT_OK
        assert self._lines(sink) == ["verdict=promote", "release_eligible=false"]

    def test_a_digest_with_no_build_tier_result_is_ineligible(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        sink = tmp_path / "out.txt"
        args = self._args(
            tmp_path, "--github-output", str(sink), "--require", "pytest", *ENFORCING,
            "--expect-tag", "v1", "--candidate-digest", DIGEST,
        )  # fmt: skip
        assert main(args) == EXIT_OK
        assert self._lines(sink) == ["verdict=promote", "release_eligible=false"]

    def test_the_manifest_records_whether_it_is_digest_bound(self, tmp_path: Path) -> None:
        sink = tmp_path / "out.txt"
        out = tmp_path / "m.json"
        args = self._eligible_args(tmp_path, sink, "--output", str(out))
        assert main(args) == EXIT_OK
        assert json.loads(out.read_text(encoding="utf-8"))["digest_bound"] is True

    def test_an_enforced_promote_without_a_tag_check_is_ineligible(self, tmp_path: Path) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence())
        sink = tmp_path / "out.txt"
        args = self._args(tmp_path, "--github-output", str(sink), "--require", "pytest", *ENFORCING)
        assert main(args) == EXIT_OK
        assert sink.read_text(encoding="utf-8").splitlines() == [
            "verdict=promote",
            "release_eligible=false",
        ]

    def test_enforcing_without_ancestor_check_exits_two(self, tmp_path: Path) -> None:
        (tmp_path / "ev").mkdir()
        assert main(self._args(tmp_path, "--mode", "enforcing")) == EXIT_CONFIG

    @pytest.mark.parametrize("flag", ["--require", "--build-validator"])
    @pytest.mark.parametrize("name", ["", "   ", "a\nb"])
    def test_blank_or_unprintable_validator_names_exit_two(
        self, tmp_path: Path, flag: str, name: str
    ) -> None:
        (tmp_path / "ev").mkdir()
        assert main(self._args(tmp_path, flag, name)) == EXIT_CONFIG

    def test_a_pass_that_examined_nothing_does_not_satisfy_a_required_validator(
        self, tmp_path: Path
    ) -> None:
        _write(tmp_path / "ev", "pytest.json", _evidence(examined=0))
        args = self._args(tmp_path, "--require", "pytest", *ENFORCING)
        assert main(args) == EXIT_LOGIC

    def test_github_output_for_a_block_is_ineligible(self, tmp_path: Path) -> None:
        (tmp_path / "ev").mkdir()
        sink = tmp_path / "out.txt"
        main(self._args(tmp_path, "--github-output", str(sink), *ENFORCING))
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
