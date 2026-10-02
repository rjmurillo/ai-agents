"""Build-tier evidence: the emitter, the digest tool, the own-run fetch, and the gate flag.

ADR-113 decision 4: results about the build bind to the commit and the tarball
digest, and "the tarball is built once, in a single job, before the gate runs".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.validation.emit_validator_evidence import EXIT_CONFIG as EMIT_CONFIG
from scripts.validation.emit_validator_evidence import EXIT_OK as EMIT_OK
from scripts.validation.emit_validator_evidence import emits_for
from scripts.validation.emit_validator_evidence import main as emit_main
from scripts.validation.promotion_applicability import Applicability
from scripts.validation.promotion_evidence import Candidate, bind_records, load_evidence_dir
from scripts.validation.promotion_fetch import fetch_build_evidence, fetch_verified_evidence
from scripts.validation.promotion_findings import collect_findings, missing_outcomes
from scripts.validation.promotion_gate import main as gate_main
from scripts.validation.promotion_provenance import build_run_problem
from tests.validation.promotion_fetch_helpers import FakeReader, _artifact, _good, _run, _zip

CANDIDATE = "c" * 40
HEAD = "a" * 40
DIGEST = "d" * 64
WORKFLOW = ".github/workflows/publish.yml"
RUN = 900


class TestEmitterBuildKind:
    @pytest.mark.parametrize(
        ("event", "ref", "expected"),
        [
            ("workflow_dispatch", "refs/heads/main", True),
            ("workflow_dispatch", "refs/heads/feature", False),
            ("workflow_dispatch", "refs/tags/v1", False),
            ("push", "refs/tags/v1", False),
            ("push", "refs/heads/main", False),
            ("pull_request", "refs/pull/1/merge", False),
            ("merge_group", "refs/heads/gh-readonly-queue/main/x", False),
        ],
    )
    def test_only_a_default_branch_dispatch_emits_build_evidence(
        self, event: str, ref: str, expected: bool
    ) -> None:
        assert emits_for(event, ref, "main", "build") is expected

    def test_a_dispatch_run_emits_no_commit_tier_evidence(self) -> None:
        assert emits_for("workflow_dispatch", "refs/heads/main", "main") is False

    def test_no_default_branch_name_emits_nothing(self) -> None:
        assert emits_for("workflow_dispatch", "refs/heads/", "", "build") is False

    def _argv(self, tmp_path: Path, **overrides: str) -> list[str]:
        values = {
            "--validator": "npm_pack_size", "--job-status": "success", "--revision": CANDIDATE,
            "--event": "workflow_dispatch", "--ref": "refs/heads/main", "--default-branch": "main",
            "--job-id": "validate", "--kind": "build", "--digest": DIGEST,
            "--output-dir": str(tmp_path / "out"), "--github-output": str(tmp_path / "go"),
        }  # fmt: skip
        values.update(overrides)
        return [token for pair in values.items() for token in pair if token != ""]

    def test_a_build_record_carries_the_digest_and_binds_on_it(self, tmp_path: Path) -> None:
        assert emit_main(self._argv(tmp_path)) == EMIT_OK
        written = json.loads((tmp_path / "out" / "npm_pack_size.json").read_text("utf-8"))
        assert written["digest"] == DIGEST
        assert written["revision"] == CANDIDATE
        records, rejected = load_evidence_dir(tmp_path / "out")
        assert rejected == ()
        bound = bind_records(records, Candidate(CANDIDATE, DIGEST), frozenset({"npm_pack_size"}))
        assert len(bound.bound) == 1

    def test_a_build_record_for_another_digest_does_not_bind(self, tmp_path: Path) -> None:
        emit_main(self._argv(tmp_path))
        records, _ = load_evidence_dir(tmp_path / "out")
        bound = bind_records(records, Candidate(CANDIDATE, "e" * 64), frozenset({"npm_pack_size"}))
        assert bound.bound == ()

    @pytest.mark.parametrize("digest", ["", "abc", "D" * 64, "g" * 64, "d" * 63])
    def test_a_build_kind_needs_a_valid_digest(self, tmp_path: Path, digest: str) -> None:
        argv = self._argv(tmp_path, **{"--digest": digest})
        if digest == "":
            argv = [a for i, a in enumerate(argv) if a not in ("--digest",)]
            argv = [a for a in argv if a != DIGEST]
        assert emit_main(argv) == EMIT_CONFIG

    def test_a_commit_kind_refuses_a_digest(self, tmp_path: Path) -> None:
        assert emit_main(self._argv(tmp_path, **{"--kind": "commit"})) == EMIT_CONFIG

    def test_a_pull_request_writes_no_build_evidence(self, tmp_path: Path) -> None:
        argv = self._argv(tmp_path, **{"--event": "pull_request", "--ref": "refs/pull/1/merge"})
        assert emit_main(argv) == EMIT_OK
        assert not (tmp_path / "out").exists()


def _own_run(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "id": RUN,
        "status": "in_progress",
        "event": "workflow_dispatch",
        "path": WORKFLOW,
        "head_sha": HEAD,
    }
    fields.update(overrides)
    return _run(**fields)


class TestBuildRunProblem:
    def _problem(self, **overrides: Any) -> str | None:
        return build_run_problem(
            _own_run(**overrides), workflow=WORKFLOW, default_branch="main", run_id=RUN
        )

    def test_the_entry_workflows_own_default_branch_dispatch_run_passes(self) -> None:
        assert self._problem() is None
        assert self._problem(status="completed") is None

    @pytest.mark.parametrize(
        ("overrides", "reason"),
        [
            ({"id": 1}, "run.id_mismatch"),
            ({"status": "queued"}, "run.incomplete"),
            ({"event": "push"}, "run.event_not_promotable"),
            ({"event": "pull_request"}, "run.event_not_promotable"),
            ({"path": ".github/workflows/other.yml"}, "run.workflow_mismatch"),
            ({"head_branch": "feature"}, "run.ref_mismatch"),
            ({"head_branch": None}, "run.ref_mismatch"),
            ({"head_repository": {"id": 9}}, "run.repository_mismatch"),
            ({"repository": None}, "run.repository_mismatch"),
        ],
    )
    def test_each_mismatch_names_its_reason(self, overrides: dict[str, Any], reason: str) -> None:
        assert self._problem(**overrides) == reason

    def test_no_default_branch_name_is_refused(self) -> None:
        got = build_run_problem(_own_run(), workflow=WORKFLOW, default_branch="", run_id=RUN)
        assert got == "run.ref_mismatch"


def _row(validator: str = "npm_pack_size", job: str = "Validate Package") -> Applicability:
    return Applicability(validator, "build", WORKFLOW, job, ("always",), "r")


def _build_evidence(validator: str = "npm_pack_size", **extra: Any) -> str:
    document = {
        "validator": validator,
        "state": "PASS",
        "revision": CANDIDATE,
        "scope": "job v on dispatch",
        "examined": 1,
        "findings": 0,
        "digest": DIGEST,
        **extra,
    }
    return json.dumps(document)


def _build_reader(**overrides: Any) -> FakeReader:
    name = "npm_pack_size"
    reader = _good(
        artifacts={name: [_artifact(name=name, workflow_run={"id": RUN, "head_sha": HEAD})]},
        archives={77: _zip(f"{name}.json", _build_evidence())},
        run_detail=_own_run(),
        **overrides,
    )
    reader.jobs[0].update(name="Validate Package", run_id=RUN)
    reader.checks[0].update(
        name="Validate Package",
        details_url=f"https://github.com/owner/repo/actions/runs/{RUN}/job/{reader.jobs[0]['id']}",
    )
    return reader


def _fetch_build(tmp_path: Path, reader: FakeReader, entries: list[Applicability] | None = None):
    return fetch_build_evidence(
        reader, repo="owner/repo", run_id=RUN, candidate_sha=CANDIDATE, default_branch="main",
        entries=[_row()] if entries is None else entries, evidence_dir=tmp_path / "ev",
    )  # fmt: skip


class TestFetchBuildEvidence:
    def test_the_own_run_evidence_is_written_and_binds_on_sha_and_digest(
        self, tmp_path: Path
    ) -> None:
        (item,) = _fetch_build(tmp_path, _build_reader())
        assert (item.accepted, item.state) == (True, "PASS")
        records, _ = load_evidence_dir(tmp_path / "ev")
        bound = bind_records(records, Candidate(CANDIDATE, DIGEST), frozenset({"npm_pack_size"}))
        assert len(bound.bound) == 1
        assert missing_outcomes(["npm_pack_size"], bound.bound, Candidate(CANDIDATE, DIGEST)) == ()

    def test_a_record_for_another_digest_is_rejected_at_binding(self, tmp_path: Path) -> None:
        _fetch_build(tmp_path, _build_reader())
        records, _ = load_evidence_dir(tmp_path / "ev")
        other = Candidate(CANDIDATE, "e" * 64)
        bound = bind_records(records, other, frozenset({"npm_pack_size"}))
        assert bound.bound == ()
        assert (
            len(
                collect_findings(
                    bound.bound, missing_outcomes(["npm_pack_size"], bound.bound, other)
                )
            )
            == 1
        )

    def test_a_record_for_another_commit_is_recorded_unknown(self, tmp_path: Path) -> None:
        reader = _build_reader()
        reader.archives[77] = _zip("npm_pack_size.json", _build_evidence(revision="b" * 40))
        (item,) = _fetch_build(tmp_path, reader)
        assert (item.reason, item.state) == ("artifact.revision_mismatch", "UNKNOWN")

    @pytest.mark.parametrize(
        "overrides",
        [{"event": "push"}, {"head_branch": "feature"}, {"path": ".github/workflows/x.yml"}],
    )
    def test_a_run_that_fails_provenance_is_never_downloaded(
        self, tmp_path: Path, overrides: dict[str, Any]
    ) -> None:
        reader = _build_reader()
        reader.run_detail = _own_run(**overrides)
        (item,) = _fetch_build(tmp_path, reader)
        assert item.accepted is False
        assert not any("/zip" in call or "/artifacts" in call for call in reader.calls)

    def test_a_failed_build_job_downgrades_the_record(self, tmp_path: Path) -> None:
        reader = _build_reader()
        reader.checks[0]["conclusion"] = "failure"
        _fetch_build(tmp_path, reader)
        written = json.loads((tmp_path / "ev" / f"npm_pack_size.{RUN}.json").read_text("utf-8"))
        assert written["state"] == "FAIL"

    def test_commit_tier_rows_are_not_fetched_here_and_build_rows_not_there(
        self, tmp_path: Path
    ) -> None:
        reader = _build_reader()
        commit_row = Applicability("v", "commit", WORKFLOW, "J", ("always",), "r")
        assert _fetch_build(tmp_path, reader, [commit_row]) == []
        assert reader.calls == []
        assert fetch_verified_evidence(
            reader, repo="owner/repo", candidate_sha=CANDIDATE, default_branch="main",
            entries=[_row()], evidence_dir=tmp_path / "ev2",
        ) == []  # fmt: skip

    @pytest.mark.parametrize("body", [None, [], "x", {"head_sha": "abc"}, {"id": RUN}])
    def test_a_run_payload_with_no_head_sha_raises(self, tmp_path: Path, body: Any) -> None:
        from scripts.validation.promotion_fetch import GitHubApiError

        reader = _build_reader()
        reader.run_detail = body if body is not None else {}
        with pytest.raises(GitHubApiError):
            _fetch_build(tmp_path, reader)

    @pytest.mark.parametrize(
        "kwargs",
        [{"repo": "o/.."}, {"candidate_sha": "abc"}, {"default_branch": "a b"}, {"run_id": 0}],
    )
    def test_bad_inputs_are_refused_before_any_request(
        self, tmp_path: Path, kwargs: dict[str, Any]
    ) -> None:
        reader = _build_reader()
        args: dict[str, Any] = {
            "repo": "owner/repo", "run_id": RUN, "candidate_sha": CANDIDATE,
            "default_branch": "main", "entries": [_row()], "evidence_dir": tmp_path,
        }  # fmt: skip
        args.update(kwargs)
        with pytest.raises(ValueError):
            fetch_build_evidence(reader, **args)
        assert reader.calls == []


class TestGatePromotedOutput:
    """`promoted` is an enforced, digest-bound promote. A tag is not part of it."""

    def _run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *extra: str, build: bool = True
    ) -> list[str]:
        from scripts.validation import promotion_gate as gate

        monkeypatch.setattr(gate, "candidate_files", lambda *_a: ())
        monkeypatch.setattr(gate, "candidate_on_branch", lambda *_a: (True, "ok"))
        ev = tmp_path / "ev"
        ev.mkdir()
        table = tmp_path / ".agents" / "governance" / "promotion-applicability.json"
        table.parent.mkdir(parents=True)
        rows = [
            {"validator": "pytest", "tier": "commit"},
            {"validator": "pack", "tier": "build"},
        ]
        entries = [
            {**row, "workflow": WORKFLOW, "job": "J", "when": "always", "rationale": "r"}
            for row in rows
        ]
        table.write_text(json.dumps({"schema_version": "1", "entries": entries}), encoding="utf-8")
        pytest_doc: dict[str, Any] = {
            "validator": "pytest",
            "state": "PASS",
            "revision": CANDIDATE,
            "scope": "t",
            "examined": 1,
            "findings": 0,
        }
        (ev / "pytest.json").write_text(json.dumps(pytest_doc), encoding="utf-8")
        if build:
            (ev / "pack.json").write_text(_build_evidence("pack"), encoding="utf-8")
        sink = tmp_path / "out"
        argv = [
            "--repo-root", str(tmp_path), "--evidence-dir", str(ev),
            "--candidate-sha", CANDIDATE, "--candidate-digest", DIGEST,
            "--mode", "enforcing", "--ancestor-of", "HEAD",
            "--github-output", str(sink), *extra,
        ]  # fmt: skip
        gate_main(argv)
        return sink.read_text(encoding="utf-8").splitlines()

    def test_an_enforced_digest_bound_promote_is_promoted_without_a_tag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lines = self._run(tmp_path, monkeypatch)
        assert "promoted=true" in lines
        assert "release_eligible=false" in lines

    def test_a_promote_with_no_build_result_is_not_promoted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        assert "promoted=false" in self._run(tmp_path, monkeypatch, build=False)

    def test_an_advisory_promote_is_not_promoted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lines = self._run(tmp_path, monkeypatch, "--mode", "advisory")
        assert "promoted=false" in lines


class TestFetchCliBuildRun:
    def test_the_build_run_id_adds_the_build_tier_dispositions(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from scripts.validation.fetch_promotion_evidence import main as fetch_main
        from scripts.validation.promotion_applicability import APPLICABILITY_RELATIVE_PATH

        table = tmp_path / "root" / APPLICABILITY_RELATIVE_PATH
        table.parent.mkdir(parents=True)
        row = {
            "validator": "npm_pack_size", "tier": "build", "workflow": WORKFLOW,
            "job": "Validate Package", "when": "always", "rationale": "r",
        }  # fmt: skip
        table.write_text(json.dumps({"schema_version": "1", "entries": [row]}), encoding="utf-8")
        argv = [
            "--repo", "owner/repo", "--candidate-sha", CANDIDATE, "--default-branch", "main",
            "--evidence-dir", str(tmp_path / "ev"), "--repo-root", str(tmp_path / "root"),
            "--build-run-id", str(RUN),
        ]  # fmt: skip
        assert fetch_main(argv, _build_reader()) == 0
        out = capsys.readouterr().out
        assert f"provenance: npm_pack_size run {RUN} accepted PASS" in out
        assert (tmp_path / "ev" / f"npm_pack_size.{RUN}.json").is_file()

    def test_without_the_flag_no_build_run_is_read(self, tmp_path: Path) -> None:
        from scripts.validation.fetch_promotion_evidence import main as fetch_main

        reader = _build_reader()
        argv = [
            "--repo", "owner/repo", "--candidate-sha", CANDIDATE, "--default-branch", "main",
            "--evidence-dir", str(tmp_path / "ev"), "--repo-root", str(tmp_path),
        ]  # fmt: skip
        assert fetch_main(argv, reader) == 0
        assert not any(call.endswith(f"/runs/{RUN}") for call in reader.calls)
