"""Fetching evidence from the API, keeping only runs that pass provenance.

ADR-113 decision 5: "The aggregator never deserializes an artifact from a run
that fails them, per ADR-101." The fake reader records every path it is asked
for, so a test can prove a rejected run's artifact was never requested.
"""

from __future__ import annotations

import io
import json
import subprocess
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts.validation import promotion_fetch as fetch
from scripts.validation.evidence import EvidenceState
from scripts.validation.promotion_applicability import Applicability
from scripts.validation.promotion_evidence import Candidate, bind_records, load_evidence_dir
from scripts.validation.promotion_fetch import (
    MAX_EVIDENCE_BYTES,
    GhCliReader,
    GitHubApiError,
    fetch_verified_evidence,
    paginate,
    read_evidence_member,
)
from scripts.validation.promotion_findings import overall_state
from tests.validation.promotion_fetch_helpers import (
    REPO,
    RUN,
    SHA,
    FakeReader,
    _artifact,
    _entry,
    _evidence,
    _good,
    _run,
    _zip,
)


def _fetch(reader: FakeReader, tmp_path: Path, entries: list[Applicability] | None = None):
    return fetch_verified_evidence(
        reader, repo=REPO, candidate_sha=SHA, default_branch="main",
        entries=entries if entries is not None else [_entry()], evidence_dir=tmp_path / "ev",
    )  # fmt: skip


def _written(tmp_path: Path) -> list[str]:
    directory = tmp_path / "ev"
    return sorted(p.name for p in directory.iterdir()) if directory.exists() else []


class TestAccepted:
    def test_a_verified_run_writes_a_file_the_gate_can_load_and_bind(self, tmp_path: Path) -> None:
        (item,) = _fetch(_good(), tmp_path)
        assert (item.accepted, item.reason, item.run_id) == (True, "accepted", RUN)
        records, rejected = load_evidence_dir(tmp_path / "ev")
        assert rejected == ()
        bound = bind_records(records, Candidate(SHA), frozenset())
        assert [r.outcome.state for r in bound.bound] == [EvidenceState.PASS]

    def test_the_file_is_named_for_the_validator_and_the_run(self, tmp_path: Path) -> None:
        _fetch(_good(), tmp_path)
        assert _written(tmp_path) == [f"run_python_tests.{RUN}.json"]

    def test_a_failing_check_run_downgrades_the_written_record(self, tmp_path: Path) -> None:
        reader = _good()
        reader.checks[0]["conclusion"] = "failure"
        _fetch(reader, tmp_path)
        written = json.loads((tmp_path / "ev" / f"run_python_tests.{RUN}.json").read_text("utf-8"))
        assert (written["state"], written["reason"]) == ("FAIL", "checkrun.failure")

    def test_an_absent_check_run_downgrades_a_passing_artifact_to_unknown(
        self, tmp_path: Path
    ) -> None:
        reader = _good(checks=[])
        _fetch(reader, tmp_path)
        written = json.loads((tmp_path / "ev" / f"run_python_tests.{RUN}.json").read_text("utf-8"))
        assert written["state"] == "UNKNOWN"

    def test_a_failing_artifact_is_kept_as_it_is(self, tmp_path: Path) -> None:
        archive = _zip("run_python_tests.json", _evidence(state="FAIL"))
        _fetch(_good(archives={77: archive}), tmp_path)
        written = json.loads((tmp_path / "ev" / f"run_python_tests.{RUN}.json").read_text("utf-8"))
        assert written["state"] == "FAIL"

    def test_the_digest_and_failed_items_survive_the_round_trip(self, tmp_path: Path) -> None:
        text = json.dumps(
            {
                "validator": "run_python_tests", "state": "FAIL", "revision": SHA, "scope": "x",
                "reason": "job.failed", "digest": "c" * 64, "items": ["a.py", "b.py"],
            }
        )  # fmt: skip
        _fetch(_good(archives={77: _zip("run_python_tests.json", text)}), tmp_path)
        written = json.loads((tmp_path / "ev" / f"run_python_tests.{RUN}.json").read_text("utf-8"))
        assert (written["digest"], written["items"]) == ("c" * 64, ["a.py", "b.py"])

    def test_build_tier_rows_are_not_fetched(self, tmp_path: Path) -> None:
        reader = _good()
        assert (
            _fetch(reader, tmp_path, [_entry("npm_pack_size", "Validate Package", "build")]) == []
        )
        assert reader.calls == []

    def test_an_empty_table_makes_no_request(self, tmp_path: Path) -> None:
        reader = _good()
        assert _fetch(reader, tmp_path, []) == []
        assert reader.calls == []

    def test_a_run_of_another_workflow_is_ignored_and_the_gap_is_reported(
        self, tmp_path: Path
    ) -> None:
        reader = FakeReader([_run(path=".github/workflows/other.yml")])
        (item,) = _fetch(reader, tmp_path)
        assert (item.accepted, item.reason, item.run_id) == (False, "run.absent", 0)
        assert not any(call.endswith("/artifacts") for call in reader.calls)

    def test_a_never_row_is_not_fetched_and_makes_no_request(self, tmp_path: Path) -> None:
        reader = _good()
        row = Applicability(
            "pr_only", "commit", ".github/workflows/pr.yml", "PR", ("never",), "PR-only"
        )
        assert _fetch(reader, tmp_path, [row]) == []
        assert reader.calls == []

    def test_a_candidate_with_no_runs_at_all_reports_each_validator_absent(
        self, tmp_path: Path
    ) -> None:
        items = _fetch(FakeReader([]), tmp_path)
        assert [(i.validator, i.reason) for i in items] == [("run_python_tests", "run.absent")]

    def test_two_validators_in_one_run_each_get_a_file(self, tmp_path: Path) -> None:
        reader = _good()
        reader.artifacts["check_ratchets"] = [_artifact(id=78, name="check_ratchets")]
        reader.archives[78] = _zip("check_ratchets.json", _evidence("check_ratchets"))
        reader.jobs.append({"id": 5002, "name": "Ratchets", "run_id": RUN, "status": "completed"})
        reader.checks.append({**reader.checks[0], "id": 5002, "name": "Ratchets",
            "details_url": f"https://github.com/{REPO}/actions/runs/{RUN}/job/5002"})  # fmt: skip
        items = _fetch(reader, tmp_path, [_entry(), _entry("check_ratchets", "Ratchets")])
        assert [i.accepted for i in items] == [True, True]
        assert len(_written(tmp_path)) == 2


class TestRejectedBeforeDownload:
    @pytest.mark.parametrize(
        ("overrides", "reason"),
        [
            ({"head_branch": "feature"}, "run.ref_mismatch"),
            ({"event": "pull_request"}, "run.event_not_promotable"),
            ({"head_sha": "b" * 40}, "run.sha_mismatch"),
            ({"status": "in_progress"}, "run.incomplete"),
            ({"head_repository": {"id": 9}}, "run.repository_mismatch"),
        ],
    )
    def test_a_run_that_fails_provenance_is_never_downloaded(
        self, tmp_path: Path, overrides: dict[str, Any], reason: str
    ) -> None:
        reader = _good()
        reader.runs = [_run(**overrides)]
        (item,) = _fetch(reader, tmp_path)
        assert (item.accepted, item.reason) == (False, reason)
        assert not any("/artifacts" in call for call in reader.calls)
        assert _written(tmp_path) == []

    def test_a_run_with_no_id_is_rejected(self, tmp_path: Path) -> None:
        reader = _good()
        reader.runs = [_run(id="900")]
        (item,) = _fetch(reader, tmp_path)
        assert (item.accepted, item.reason, item.run_id) == (False, "run.malformed", 0)


def _record_file(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "ev" / f"run_python_tests.{RUN}.json").read_text("utf-8"))


class TestUnusableArtifact:
    """A verified run with no usable artifact writes UNKNOWN, never nothing."""

    @pytest.mark.parametrize(
        ("artifacts", "reason"),
        [
            ([], "artifact.absent"),
            ([_artifact(name="other")], "artifact.absent"),
            (["junk"], "artifact.absent"),
            ([_artifact(), _artifact(id=78)], "artifact.ambiguous"),
            ([_artifact(expired=True)], "artifact.expired"),
            ([_artifact(expired=None)], "artifact.expired"),
            ([_artifact(workflow_run={"id": 1, "head_sha": SHA})], "artifact.run_mismatch"),
            ([_artifact(workflow_run={"id": RUN, "head_sha": "b" * 40})], "artifact.run_mismatch"),
            ([_artifact(workflow_run=None)], "artifact.run_mismatch"),
            ([_artifact(id="77")], "artifact.run_mismatch"),
            ([_artifact(size_in_bytes=10**9)], "artifact.too_large"),
            ([_artifact(size_in_bytes=None)], "artifact.too_large"),
            ([_artifact(created_at="2026-10-01T09:59:59Z")], "artifact.stale"),
            ([_artifact(created_at="2026-10-01T10:00:00Z")], "artifact.stale"),
            ([_artifact(created_at=None)], "artifact.stale"),
            ([_artifact(created_at="yesterday")], "artifact.stale"),
            ([_artifact(created_at="2026-10-01T10:05:00")], "artifact.stale"),
        ],
    )
    def test_each_unusable_artifact_is_recorded_unknown_with_its_reason(
        self, tmp_path: Path, artifacts: list[Any], reason: str
    ) -> None:
        reader = _good(artifacts={"run_python_tests": artifacts})
        (item,) = _fetch(reader, tmp_path)
        assert (item.accepted, item.reason, item.state) == (False, reason, "UNKNOWN")
        assert not any("/zip" in call for call in reader.calls)
        written = _record_file(tmp_path)
        assert (written["state"], written["reason"], written["revision"]) == (
            "UNKNOWN",
            reason,
            SHA,
        )

    @pytest.mark.parametrize(
        "archive",
        [
            pytest.param(b"not a zip", id="not-a-zip"),
            pytest.param(_zip("other.json", _evidence()), id="wrong-member-name"),
            pytest.param(_zip("run_python_tests.json", "{"), id="truncated-json"),
            pytest.param(
                _zip("run_python_tests.json", _evidence("someone_else")), id="other-validator"
            ),
            pytest.param(
                _zip("run_python_tests.json", json.dumps({"validator": "run_python_tests"})),
                id="missing-fields",
            ),
            pytest.param(
                _zip(
                    "run_python_tests.json", '{"validator": "run_python_tests", "validator": "x"}'
                ),
                id="duplicate-key",
            ),
            pytest.param(_zip("run_python_tests.json", "[" * 5000 + "]" * 5000), id="deep-nesting"),
        ],
    )
    def test_an_artifact_that_is_not_evidence_is_recorded_unknown(
        self, tmp_path: Path, archive: bytes
    ) -> None:
        (item,) = _fetch(_good(archives={77: archive}), tmp_path)
        assert (item.accepted, item.reason, item.state) == (False, "artifact.malformed", "UNKNOWN")
        assert _record_file(tmp_path)["reason"] == "artifact.malformed"

    def test_an_artifact_cannot_carry_the_exempt_reason(self, tmp_path: Path) -> None:
        text = json.dumps(
            {"validator": "run_python_tests", "state": "SKIP", "revision": SHA, "scope": "s",
             "reason": "policy.exempt"}
        )  # fmt: skip
        archive = _zip("run_python_tests.json", text)
        (item,) = _fetch(_good(archives={77: archive}), tmp_path)
        assert (item.reason, item.state) == ("artifact.malformed", "UNKNOWN")

    def test_a_download_that_is_not_the_listed_size_is_recorded_unknown(
        self, tmp_path: Path
    ) -> None:
        reader = _good()
        reader.artifacts["run_python_tests"] = [_artifact(size_in_bytes=1)]
        (item,) = _fetch(reader, tmp_path)
        assert (item.reason, item.state) == ("artifact.malformed", "UNKNOWN")

    def test_a_record_for_another_commit_is_recorded_unknown(self, tmp_path: Path) -> None:
        archive = _zip("run_python_tests.json", _evidence(revision="b" * 40))
        (item,) = _fetch(_good(archives={77: archive}), tmp_path)
        assert (item.accepted, item.reason, item.state) == (
            False,
            "artifact.revision_mismatch",
            "UNKNOWN",
        )
        assert _record_file(tmp_path)["revision"] == SHA

    def test_a_failed_sibling_run_cannot_be_hidden_by_a_passing_one(self, tmp_path: Path) -> None:
        """Two verified runs of one workflow: the one with no artifact must still count."""
        reader = _good()
        reader.runs = [
            _run(),
            _run(id=901, event="merge_group", head_branch="gh-readonly-queue/main/pr-1"),
        ]
        reader.artifacts["run_python_tests"] = [_artifact()]
        items = _fetch(reader, tmp_path)
        assert [(i.run_id, i.state) for i in items] == [(RUN, "PASS"), (901, "UNKNOWN")]
        records, _ = load_evidence_dir(tmp_path / "ev")
        bound = bind_records(records, Candidate(SHA), frozenset())
        assert overall_state(r.outcome for r in bound.bound).state is EvidenceState.UNKNOWN


class TestApiFailures:
    def test_a_reader_error_propagates(self, tmp_path: Path) -> None:
        reader = _good()
        with (
            patch.object(reader, "get_json", side_effect=GitHubApiError("boom")),
            pytest.raises(GitHubApiError),
        ):
            _fetch(reader, tmp_path)

    def test_a_download_error_propagates(self, tmp_path: Path) -> None:
        reader = _good()
        with (
            patch.object(reader, "get_bytes", side_effect=GitHubApiError("boom")),
            pytest.raises(GitHubApiError),
        ):
            _fetch(reader, tmp_path)

    @pytest.mark.parametrize(
        ("repo", "sha", "branch"),
        [
            ("owner", SHA, "main"),
            ("../..", SHA, "main"),
            ("o/..", SHA, "main"),
            ("o/.", SHA, "main"),
            ("./.", SHA, "main"),
            ("./r", SHA, "main"),
            ("o/r", "abc", "main"),
            ("o/r", SHA, ""),
            ("o/r", SHA, "ma in"),
            ("o/r", "A" * 40, "main"),
        ],
    )
    def test_bad_inputs_are_refused_before_any_request(
        self, tmp_path: Path, repo: str, sha: str, branch: str
    ) -> None:
        reader = _good()
        with pytest.raises(ValueError):
            fetch_verified_evidence(
                reader, repo=repo, candidate_sha=sha, default_branch=branch,
                entries=[_entry()], evidence_dir=tmp_path,
            )  # fmt: skip
        assert reader.calls == []


class _Pages:
    def __init__(self, pages: list[object]) -> None:
        self.pages = pages
        self.asked: list[str] = []

    def get_json(self, path: str, params: Mapping[str, str] | None = None) -> object:
        self.asked.append((params or {})["page"])
        return self.pages[min(len(self.asked), len(self.pages)) - 1]

    def get_bytes(self, path: str, accept: str | None = None) -> bytes:  # pragma: no cover - unused
        raise AssertionError


class TestPaginate:
    def test_a_short_page_ends_the_listing(self) -> None:
        pages = _Pages([{"items": [1, 2]}])
        assert paginate(pages, "p", "items", {}) == [1, 2]
        assert pages.asked == ["1"]

    def test_full_pages_are_followed(self) -> None:
        full = {"items": list(range(100))}
        pages = _Pages([full, {"items": [7]}])
        assert len(paginate(pages, "p", "items", {})) == 101
        assert pages.asked == ["1", "2"]

    def test_hitting_the_page_limit_with_full_pages_fails_closed(self) -> None:
        with pytest.raises(GitHubApiError, match="more than"):
            paginate(_Pages([{"items": list(range(100))}]), "p", "items", {})

    @pytest.mark.parametrize(
        "body", [[], None, "x", {"other": []}, {"items": "no"}, {"items": None}]
    )
    def test_a_malformed_page_is_refused(self, body: object) -> None:
        with pytest.raises(GitHubApiError, match="items"):
            paginate(_Pages([body]), "p", "items", {})


class TestArchive:
    def test_a_single_named_member_is_read(self) -> None:
        assert read_evidence_member(_zip("v.json", "{}"), "v") == "{}"

    @pytest.mark.parametrize(
        "name", ["../v.json", "dir/v.json", "/v.json", "v.json/", "V.json", "v.JSON"]
    )
    def test_any_other_member_name_is_refused(self, name: str) -> None:
        with pytest.raises(ValueError, match="exactly one"):
            read_evidence_member(_zip(name, "{}"), "v")

    def test_two_members_are_refused(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr("v.json", "{}")
            bundle.writestr("w.json", "{}")
        with pytest.raises(ValueError, match="exactly one"):
            read_evidence_member(buffer.getvalue(), "v")

    def test_an_empty_archive_is_refused(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w"):
            pass
        with pytest.raises(ValueError, match="exactly one"):
            read_evidence_member(buffer.getvalue(), "v")

    def test_a_member_over_the_size_cap_is_refused(self) -> None:
        with pytest.raises(ValueError, match="too large"):
            read_evidence_member(_zip("v.json", "x" * (MAX_EVIDENCE_BYTES + 1)), "v")

    def test_an_archive_over_the_size_cap_is_refused(self) -> None:
        with pytest.raises(ValueError, match="too large"):
            read_evidence_member(b"0" * (4 * MAX_EVIDENCE_BYTES + 1), "v")

    @pytest.mark.parametrize(
        "error", [NotImplementedError("compression"), RuntimeError("encrypted"), EOFError()]
    )
    def test_an_unreadable_member_is_a_value_error_not_a_crash(self, error: Exception) -> None:
        archive = _zip("v.json", "{}")
        with (
            patch.object(zipfile.ZipFile, "open", side_effect=error),
            pytest.raises(ValueError, match="cannot be read"),
        ):
            read_evidence_member(archive, "v")

    def test_a_non_utf8_member_is_refused(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as bundle:
            bundle.writestr("v.json", b"\xff\xfe")
        with pytest.raises(ValueError):
            read_evidence_member(buffer.getvalue(), "v")


class TestGhCliReader:
    def _completed(self, code: int = 0, out: bytes = b"{}", err: bytes = b"") -> Any:
        return subprocess.CompletedProcess(["gh"], code, stdout=out, stderr=err)

    def test_json_is_decoded_and_params_become_query_fields(self) -> None:
        with patch.object(subprocess, "run", return_value=self._completed(out=b'{"a": 1}')) as run:
            assert GhCliReader().get_json("repos/o/r/x", {"page": "2"}) == {"a": 1}
        argv = run.call_args.args[0]
        assert argv[:4] == ["gh", "api", "--method", "GET"]
        assert argv[4:] == ["repos/o/r/x", "-f", "page=2"]
        assert run.call_args.kwargs.get("shell") is None

    def test_bytes_are_returned_raw(self) -> None:
        with patch.object(subprocess, "run", return_value=self._completed(out=b"\x00\x01")):
            assert GhCliReader().get_bytes("repos/o/r/zip") == b"\x00\x01"

    def test_a_nonzero_exit_raises_with_a_bounded_message(self) -> None:
        done = self._completed(code=1, err=b"x" * 500)
        with (
            patch.object(subprocess, "run", return_value=done),
            pytest.raises(GitHubApiError) as caught,
        ):
            GhCliReader().get_json("p")
        assert len(str(caught.value)) < 260

    @pytest.mark.parametrize("error", [OSError("no gh"), subprocess.TimeoutExpired("gh", 1)])
    def test_a_spawn_failure_or_timeout_raises(self, error: Exception) -> None:
        with patch.object(subprocess, "run", side_effect=error), pytest.raises(GitHubApiError):
            GhCliReader().get_bytes("p")

    def test_invalid_json_raises(self) -> None:
        with patch.object(subprocess, "run", return_value=self._completed(out=b"<html>")):
            with pytest.raises(GitHubApiError, match="invalid JSON"):
                GhCliReader().get_json("p")


def test_a_disposition_line_names_the_validator_run_and_reason() -> None:
    line = fetch.Disposition("v", 5, False, "run.ref_mismatch").line()
    assert line == "provenance: v run 5 rejected run.ref_mismatch"
