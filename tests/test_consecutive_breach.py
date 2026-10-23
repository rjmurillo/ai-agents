"""Tests for the consecutive-main breach policy (issue #6757).

Coverage:
* Positive: a module that breached on the previous main run too fails.
* Negative: a first breach on main warns and passes, and records itself.
* Pull requests and other events always warn and never fail, never look up.
* Fail closed: first main run (no prior run), missing or expired artifact, a
  malformed record, a bad archive and an API failure all count as a breach.
* The lookup picks the newest main push run older than this run, any status.
All GitHub I/O is a fake ``fetch``; nothing reaches the network.
"""

from __future__ import annotations

import io
import json
import zipfile
import zlib
from pathlib import Path
from typing import Any

import pytest

from scripts.ci import consecutive_breach as cb

REPO = "owner/repo"
WORKFLOW = "pytest.yml"
GATE = "demo-gate"
RUNS_URL = (
    f"repos/{REPO}/actions/workflows/{WORKFLOW}/runs?event=push&branch=main&per_page=100&page=1"
)


def _record(breached: Any, run_id: Any = 90, gate: str = GATE, **extra: Any) -> bytes:
    body = {
        "schema": 1,
        "gate": gate,
        "run_id": run_id,
        "head_sha": "abc",
        "breached": breached,
        **extra,
    }
    return json.dumps(body).encode()


def _zip(payload: bytes, name: str = cb.RECORD_FILE) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(name, payload)
    return buffer.getvalue()


def _run(run_id: int, branch: str = "main", event: str = "push") -> dict[str, Any]:
    return {"id": run_id, "head_branch": branch, "event": event}


class FakeApi:
    """Serves canned bodies by endpoint and records every call."""

    def __init__(self, routes: dict[str, bytes | Exception]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, endpoint: str) -> bytes:
        self.calls.append(endpoint)
        result = self.routes[endpoint]
        if isinstance(result, Exception):
            raise result
        return result


def _api(
    breached: list[str] | None,
    *,
    runs: list[dict[str, Any]] | None = None,
    prior_id: int = 90,
    expired: bool = False,
    archive: bytes | None = None,
) -> FakeApi:
    routes: dict[str, bytes | Exception] = {
        RUNS_URL: json.dumps(
            {"workflow_runs": runs if runs is not None else [_run(100), _run(prior_id)]}
        ).encode()
    }
    name = cb.artifact_name(GATE)
    routes[f"repos/{REPO}/actions/runs/{prior_id}/artifacts?name={name}&per_page=100"] = (
        json.dumps({"artifacts": [{"id": 7, "name": name, "expired": expired}]}).encode()
        if breached is not None
        else json.dumps({"artifacts": []}).encode()
    )
    routes[f"repos/{REPO}/actions/artifacts/7/zip"] = (
        archive if archive is not None else _zip(_record(breached or [], prior_id))
    )
    return FakeApi(routes)


def _out(tmp_path: Path) -> Path:
    return tmp_path / "out" / cb.RECORD_FILE


def _policy(tmp_path: Path, event: str = "push", ref: str = cb.MAIN_REF) -> cb.Policy:
    return cb.Policy(
        name=cb.POLICY_CONSECUTIVE,
        event=event,
        ref=ref,
        run_id=100,
        sha="deadbeef",
        repository=REPO,
        workflow=WORKFLOW,
        record_out=_out(tmp_path),
    )


def _apply(policy: cb.Policy, api: FakeApi, breaches: dict[str, str] | None = None) -> cb.Verdict:
    return cb.apply_policy(
        GATE, {"m.py": "9s vs 5s"} if breaches is None else breaches, policy, api
    )


class TestMainRuns:
    def test_a_second_consecutive_breach_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        verdict = _apply(_policy(tmp_path), _api(["m.py"]))
        assert verdict.failing == ("m.py",)
        assert verdict.warning == ()
        out = capsys.readouterr().out
        assert out.startswith("::error title=demo-gate::m.py: 9s vs 5s.")
        assert "two main runs in a row" in out

    def test_a_first_breach_warns_and_does_not_fail(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        verdict = _apply(_policy(tmp_path), _api([]))
        assert verdict.failing == ()
        assert verdict.warning == ("m.py",)
        assert "::warning title=demo-gate::m.py: 9s vs 5s. First breach on main" in (
            capsys.readouterr().out
        )

    def test_the_decision_is_per_key(self, tmp_path: Path) -> None:
        verdict = _apply(
            _policy(tmp_path),
            _api(["a.py"]),
            {"a.py": "x", "b.py": "y"},
        )
        assert verdict.failing == ("a.py",)
        assert verdict.warning == ("b.py",)

    def test_the_record_lists_this_runs_breaches_even_when_the_gate_passes(
        self, tmp_path: Path
    ) -> None:
        policy = _policy(tmp_path)
        _apply(policy, _api([]))
        written = json.loads(_out(tmp_path).read_text(encoding="utf-8"))
        assert written == {
            "schema": 1,
            "gate": GATE,
            "run_id": 100,
            "head_sha": "deadbeef",
            "breached": ["m.py"],
        }

    def test_no_breach_writes_an_empty_record_and_skips_the_lookup(self, tmp_path: Path) -> None:
        policy = _policy(tmp_path)
        api = _api(["m.py"])
        verdict = _apply(policy, api, {})
        assert verdict == cb.Verdict()
        assert api.calls == []
        assert json.loads(_out(tmp_path).read_text(encoding="utf-8"))["breached"] == []

    def test_the_record_is_written_when_the_gate_fails(self, tmp_path: Path) -> None:
        policy = _policy(tmp_path)
        assert _apply(policy, _api(["m.py"])).failing == ("m.py",)
        assert _out(tmp_path).exists()

    def test_the_record_round_trips_through_the_parser(self, tmp_path: Path) -> None:
        policy = _policy(tmp_path)
        _apply(policy, _api([]), {"b.py": "1", "a.py": "2"})
        parsed = cb.parse_record(_out(tmp_path).read_bytes(), GATE)
        assert parsed.breached == ("a.py", "b.py")


class TestFailClosed:
    @pytest.mark.parametrize(
        ("api", "reason"),
        [
            (_api(None, runs=[_run(100)]), "no main push run"),
            (_api(None), "no live artifact"),
            (_api(["m.py"], expired=True), "no live artifact"),
            (_api(["m.py"], archive=b"not a zip"), "BadZipFile"),
            (_api(["m.py"], archive=_zip(b"{not json")), "JSONDecodeError"),
            (_api(["m.py"], archive=_zip(_record([], gate="other"))), "record is for gate"),
            (_api(["m.py"], archive=_zip(_record([]), name="other.json")), "named breach-record"),
            (_api(["m.py"], archive=_zip(b"[]")), "not a JSON object"),
            (_api(["m.py"], archive=_zip(_record([], schema=2))), "unsupported record schema"),
            (_api(["m.py"], archive=_zip(_record([], run_id="x"))), "run_id"),
            (_api(["m.py"], archive=_zip(_record([], head_sha=7))), "head_sha"),
            (_api(["m.py"], archive=_zip(_record("m.py"))), "breached"),
        ],
    )
    def test_unknown_prior_state_fails_the_gate(
        self, tmp_path: Path, api: FakeApi, reason: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        verdict = _apply(_policy(tmp_path), api)
        assert verdict.failing == ("m.py",)
        out = capsys.readouterr().out
        assert "failing closed" in out
        assert reason in out

    @pytest.mark.parametrize(
        "exc",
        [EOFError("truncated"), zlib.error("bad data"), NotImplementedError("compression")],
    )
    def test_an_unreadable_archive_member_fails_the_gate_instead_of_raising(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc: Exception
    ) -> None:
        def boom(*_a: Any, **_kw: Any) -> bytes:
            raise exc

        monkeypatch.setattr(cb.zipfile.ZipFile, "read", boom)
        assert _apply(_policy(tmp_path), _api(["m.py"])).failing == ("m.py",)

    def test_a_record_naming_another_run_fails_the_gate(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        api = _api(["m.py"], archive=_zip(_record(["m.py"], run_id=85)))
        assert _apply(_policy(tmp_path), api).failing == ("m.py",)
        assert "record names run 85, not the selected run 90" in capsys.readouterr().out

    def test_an_unwritable_record_still_prints_the_verdict_first(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        policy = _policy(tmp_path)
        (tmp_path / "out").write_text("a file where the directory belongs", encoding="utf-8")
        with pytest.raises(OSError):
            _apply(policy, _api(["m.py"]))
        assert "::error title=demo-gate::m.py" in capsys.readouterr().out

    def test_an_api_failure_fails_the_gate(self, tmp_path: Path) -> None:
        api = FakeApi({RUNS_URL: cb.PriorStateError("gh api failed: HTTP 502")})
        assert _apply(_policy(tmp_path), api).failing == ("m.py",)

    def test_a_runs_page_that_is_not_an_object_fails_the_gate(self, tmp_path: Path) -> None:
        api = FakeApi({RUNS_URL: b"[]"})
        assert _apply(_policy(tmp_path), api).failing == ("m.py",)

    def test_a_runs_page_without_a_list_fails_the_gate(self, tmp_path: Path) -> None:
        api = FakeApi({RUNS_URL: b'{"workflow_runs": null}'})
        assert _apply(_policy(tmp_path), api).failing == ("m.py",)

    def test_a_first_ever_main_run_with_a_breach_fails_closed(self, tmp_path: Path) -> None:
        api = _api(None, runs=[])
        assert _apply(_policy(tmp_path), api).failing == ("m.py",)

    def test_an_oversized_archive_fails_the_gate(self, tmp_path: Path) -> None:
        api = _api(["m.py"], archive=b"x" * (cb.MAX_ZIP_BYTES + 1))
        assert _apply(_policy(tmp_path), api).failing == ("m.py",)

    def test_an_oversized_record_fails_the_gate(self, tmp_path: Path) -> None:
        padded = _record([], pad="x" * (cb.MAX_RECORD_BYTES + 1))
        assert _apply(_policy(tmp_path), _api(["m.py"], archive=_zip(padded))).failing == ("m.py",)

    def test_an_unknown_prior_run_with_no_breach_now_still_passes(self, tmp_path: Path) -> None:
        api = _api(None, runs=[])
        assert _apply(_policy(tmp_path), api, {}) == cb.Verdict()


class TestPreviousRunSelection:
    def test_it_takes_the_newest_run_older_than_this_one(self, tmp_path: Path) -> None:
        runs = [_run(105), _run(100), _run(95), _run(90)]
        api = _api(["m.py"], runs=runs, prior_id=95)
        assert _apply(_policy(tmp_path), api).failing == ("m.py",)

    def test_a_run_from_another_branch_or_event_is_never_main(self, tmp_path: Path) -> None:
        runs = [_run(99, branch="feat"), _run(98, event="pull_request"), _run(90)]
        assert _apply(_policy(tmp_path), _api(["m.py"], runs=runs)).failing == ("m.py",)
        only_foreign = [_run(99, branch="feat"), _run(98, event="pull_request")]
        api = _api(["m.py"], runs=only_foreign)
        assert (
            cb.find_previous_record(
                api, repository=REPO, workflow=WORKFLOW, gate=GATE, current_run_id=100
            ).known
            is False
        )

    def test_it_pages_past_a_full_page_of_newer_runs(self) -> None:
        newer = [_run(1000 + i) for i in range(cb.RUNS_PER_PAGE)]
        api = _api(["m.py"])
        api.routes[RUNS_URL] = json.dumps({"workflow_runs": newer}).encode()
        api.routes[RUNS_URL.replace("&page=1", "&page=2")] = json.dumps(
            {"workflow_runs": [_run(90)]}
        ).encode()
        lookup = cb.find_previous_record(
            api, repository=REPO, workflow=WORKFLOW, gate=GATE, current_run_id=100
        )
        assert lookup.known
        assert lookup.breached("m.py")

    def test_it_gives_up_after_the_page_cap_and_fails_closed(self) -> None:
        full = json.dumps({"workflow_runs": [_run(1000 + i) for i in range(cb.RUNS_PER_PAGE)]})
        routes: dict[str, bytes | Exception] = {
            RUNS_URL.replace("&page=1", f"&page={n}"): full.encode()
            for n in range(1, cb.MAX_RUN_PAGES + 1)
        }
        lookup = cb.find_previous_record(
            FakeApi(routes), repository=REPO, workflow=WORKFLOW, gate=GATE, current_run_id=100
        )
        assert not lookup.known
        assert lookup.breached("anything")
        assert "within 2 pages" in lookup.reason

    def test_a_non_integer_or_non_dict_run_entry_is_skipped(self, tmp_path: Path) -> None:
        runs: list[Any] = ["junk", {"id": True, "head_branch": "main", "event": "push"}, _run(90)]
        assert _apply(_policy(tmp_path), _api(["m.py"], runs=runs)).failing == ("m.py",)

    def test_a_non_integer_artifact_id_fails_the_gate(self, tmp_path: Path) -> None:
        api = _api(["m.py"])
        name = cb.artifact_name(GATE)
        api.routes[f"repos/{REPO}/actions/runs/90/artifacts?name={name}&per_page=100"] = json.dumps(
            {"artifacts": [{"id": "7", "name": name}]}
        ).encode()
        assert _apply(_policy(tmp_path), api).failing == ("m.py",)

    def test_an_artifact_listing_without_a_list_fails_the_gate(self, tmp_path: Path) -> None:
        api = _api(["m.py"])
        name = cb.artifact_name(GATE)
        api.routes[f"repos/{REPO}/actions/runs/90/artifacts?name={name}&per_page=100"] = b"{}"
        assert _apply(_policy(tmp_path), api).failing == ("m.py",)


class TestPullRequestsAndOtherEvents:
    @pytest.mark.parametrize(
        ("event", "ref"),
        [
            ("pull_request", "refs/pull/6757/merge"),
            ("merge_group", "refs/heads/gh-readonly-queue/main/pr-1-abc"),
            ("push", "refs/heads/feature"),
            ("workflow_dispatch", cb.MAIN_REF),
        ],
    )
    def test_never_fails_never_looks_up_never_records(
        self, tmp_path: Path, event: str, ref: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        policy = _policy(tmp_path, event=event, ref=ref)
        api = FakeApi({})
        verdict = _apply(policy, api)
        assert verdict.failing == ()
        assert verdict.warning == ("m.py",)
        assert api.calls == []
        assert not _out(tmp_path).exists()
        assert "::warning" in capsys.readouterr().out

    def test_a_pull_request_with_no_breach_prints_nothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        verdict = _apply(_policy(tmp_path, "pull_request", "refs/pull/1/merge"), FakeApi({}), {})
        assert verdict == cb.Verdict()
        assert capsys.readouterr().out == ""


class TestStrictPolicy:
    def test_the_default_policy_fails_every_breach_without_a_lookup(self) -> None:
        api = FakeApi({})
        verdict = cb.apply_policy(GATE, {"a": "1", "b": "2"}, cb.Policy(), api)
        assert verdict.failing == ("a", "b")
        assert api.calls == []

    def test_strict_mode_adds_no_workflow_annotation(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cb.apply_policy(GATE, {"a": "1"}, cb.Policy(), FakeApi({}))
        assert capsys.readouterr().out == ""


class TestAnnotationEscaping:
    def test_message_escapes_percent_and_newlines(self) -> None:
        assert cb.annotation("error", "t", "1\n2%\r") == "::error title=t::1%0A2%25%0D"

    def test_title_also_escapes_colon_and_comma(self) -> None:
        assert cb.annotation("warning", "Wall: a,b", "m") == "::warning title=Wall%3A a%2Cb::m"
