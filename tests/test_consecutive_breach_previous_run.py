"""The previous main run is the immediately previous one, finished or not (issue #6757).

A main run of pytest.yml stays in_progress until testmon-seed ends, long after
the gate jobs uploaded their breach record. The lookup must read that record
instead of skipping to an older completed run.

Coverage:
* Missed double breach: N-1 is in_progress with a breach record, N-2 is clean.
* False single breach: N-1 is in_progress with a clean record, N-2 breached.
* The record is not uploaded yet: the lookup polls, then reads it.
* Timeout: the record never arrives, the sleep total stays at the cap, fail closed.
* The run finishes without a record, or the run is already finished: no wait.
* API failure, malformed status and unknown status while waiting fail closed.
The API is a virtual timeline and ``sleep`` advances it, so no test waits.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts.ci import consecutive_breach as cb
from tests.test_consecutive_breach import GATE, REPO, WORKFLOW, _record, _zip

CURRENT = 100
PRIOR = 90
OLDER = 80
NAME = cb.artifact_name(GATE)


class Timeline:
    """A fake Actions API whose state changes each time ``sleep`` is called."""

    def __init__(self) -> None:
        self.tick = 0
        self.now = 0.0
        self.latency = 0.0
        self.sleeps: list[float] = []
        self.calls: list[str] = []
        # run id -> (status, tick the record is visible at or None, breached keys)
        self.runs: dict[int, dict[str, Any]] = {}
        # Raised once a sleep has happened, so the first read still works.
        self.fail: dict[str, Exception] = {}
        self.fail_exact: dict[str, Exception] = {}
        self.raw: dict[str, bytes] = {}

    def add_run(
        self,
        run_id: int,
        *,
        status: str | None = "completed",
        visible_at: int | None = 0,
        breached: list[str] | None = None,
        completes_at: int | None = None,
    ) -> None:
        self.runs[run_id] = {
            "status": status,
            "visible_at": visible_at,
            "breached": breached or [],
            "completes_at": completes_at,
        }

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.tick += 1
        self.now += seconds

    def clock(self) -> float:
        return self.now

    def _status(self, run_id: int) -> str | None:
        run = self.runs[run_id]
        done = run["completes_at"]
        if done is not None and self.tick >= done:
            return "completed"
        return run["status"]

    def _visible(self, run_id: int) -> bool:
        at = self.runs[run_id]["visible_at"]
        return at is not None and self.tick >= at

    def __call__(self, endpoint: str) -> bytes:
        self.calls.append(endpoint)
        self.now += self.latency
        self._maybe_fail(endpoint)
        if endpoint in self.raw:
            return self.raw[endpoint]
        if "/workflows/" in endpoint:
            return self._run_listing(endpoint)
        parts = endpoint.split("?")[0].split("/")
        if parts[-2] == "runs":
            status = self._status(int(parts[-1]))
            return json.dumps({} if status is None else {"status": status}).encode()
        if parts[-1] == "artifacts":
            return self._artifact_listing(int(parts[-2]))
        if parts[-1] == "zip":
            run_id = int(parts[-2])
            return _zip(_record(self.runs[run_id]["breached"], run_id))
        raise AssertionError(f"unexpected endpoint {endpoint}")

    def _maybe_fail(self, endpoint: str) -> None:
        if self.tick < 1:
            return
        if endpoint in self.fail_exact:
            raise self.fail_exact[endpoint]
        for needle, exc in self.fail.items():
            if needle in endpoint:
                raise exc

    def _run_listing(self, endpoint: str) -> bytes:
        listing = []
        for run_id in sorted(self.runs, reverse=True):
            status = self._status(run_id)
            if "status=completed" in endpoint and status != "completed":
                continue
            entry: dict[str, Any] = {"id": run_id, "head_branch": "main", "event": "push"}
            if status is not None:
                entry["status"] = status
            listing.append(entry)
        return json.dumps({"workflow_runs": listing}).encode()

    def _artifact_listing(self, run_id: int) -> bytes:
        found = [{"id": run_id, "name": NAME, "expired": False}] if self._visible(run_id) else []
        return json.dumps({"artifacts": found}).encode()


def _policy(tmp_path: Path) -> cb.Policy:
    return cb.Policy(
        name=cb.POLICY_CONSECUTIVE,
        event="push",
        ref=cb.MAIN_REF,
        run_id=CURRENT,
        sha="deadbeef",
        repository=REPO,
        workflow=WORKFLOW,
        record_out=tmp_path / "out" / cb.RECORD_FILE,
    )


def _apply(tmp_path: Path, api: Timeline) -> cb.Verdict:
    return cb.apply_policy(
        GATE, {"m.py": "9s vs 5s"}, _policy(tmp_path), api, sleep=api.sleep, clock=api.clock
    )


def _lookup(api: Timeline) -> cb.PriorLookup:
    return cb.find_previous_record(
        api,
        repository=REPO,
        workflow=WORKFLOW,
        gate=GATE,
        current_run_id=CURRENT,
        sleep=api.sleep,
        clock=api.clock,
    )


class TestImmediatelyPreviousRun:
    def test_the_runs_query_does_not_filter_by_status(self) -> None:
        api = Timeline()
        api.add_run(PRIOR)
        _lookup(api)
        assert "status=" not in api.calls[0]

    def test_an_in_progress_previous_run_with_a_breach_makes_the_second_breach_fail(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # N-2 clean and completed, N-1 breached and still in progress, N breaches.
        api = Timeline()
        api.add_run(OLDER, status="completed", breached=[])
        api.add_run(PRIOR, status="in_progress", breached=["m.py"])
        verdict = _apply(tmp_path, api)
        assert verdict.failing == ("m.py",)
        assert "Breached on run 90 too" in capsys.readouterr().out
        assert not any(f"/runs/{OLDER}/" in call for call in api.calls)
        assert api.sleeps == []

    def test_an_in_progress_previous_run_that_is_clean_keeps_a_first_breach_a_warning(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # N-2 breached and completed, N-1 clean and still in progress, N breaches.
        api = Timeline()
        api.add_run(OLDER, status="completed", breached=["m.py"])
        api.add_run(PRIOR, status="in_progress", breached=[])
        verdict = _apply(tmp_path, api)
        assert verdict.failing == ()
        assert verdict.warning == ("m.py",)
        assert "the previous main run did not breach it" in capsys.readouterr().out
        assert not any(f"/runs/{OLDER}/" in call for call in api.calls)

    def test_the_newest_run_wins_whatever_the_statuses_are(self) -> None:
        api = Timeline()
        api.add_run(70, status="completed", breached=["m.py"])
        api.add_run(OLDER, status="completed", breached=["m.py"])
        api.add_run(PRIOR, status="in_progress", breached=[])
        api.add_run(CURRENT + 5, status="queued", breached=["m.py"])
        lookup = _lookup(api)
        assert lookup.known
        assert lookup.reason == f"run {PRIOR}"
        assert not lookup.breached("m.py")


class TestWaitingForTheRecord:
    def test_it_polls_until_the_running_previous_run_uploads(self, tmp_path: Path) -> None:
        api = Timeline()
        api.add_run(OLDER, breached=[])
        api.add_run(PRIOR, status="in_progress", visible_at=3, breached=["m.py"])
        verdict = _apply(tmp_path, api)
        assert verdict.failing == ("m.py",)
        assert api.sleeps == [cb.WAIT_POLL_SECONDS] * 3

    def test_a_clean_record_that_arrives_late_still_warns(self, tmp_path: Path) -> None:
        api = Timeline()
        api.add_run(PRIOR, status="in_progress", visible_at=2, breached=[])
        verdict = _apply(tmp_path, api)
        assert verdict.failing == ()
        assert verdict.warning == ("m.py",)
        assert len(api.sleeps) == 2

    @pytest.mark.parametrize("status", sorted(cb.PENDING_STATUSES))
    def test_every_pending_status_waits(self, status: str) -> None:
        api = Timeline()
        api.add_run(PRIOR, status=status, visible_at=1, breached=["m.py"])
        lookup = _lookup(api)
        assert lookup.known
        assert len(api.sleeps) == 1

    def test_the_wait_cap_bounds_the_total_sleep_and_fails_closed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        api = Timeline()
        api.add_run(OLDER, breached=[])
        api.add_run(PRIOR, status="in_progress", visible_at=None)
        verdict = _apply(tmp_path, api)
        assert verdict.failing == ("m.py",)
        assert sum(api.sleeps) == cb.WAIT_CAP_SECONDS
        out = capsys.readouterr().out
        assert "failing closed" in out
        assert f"after waiting {cb.WAIT_CAP_SECONDS:.0f}s while the run was in_progress" in out
        # The poll count is bounded, so the API call count is too.
        assert len(api.calls) <= 2 + 2 * len(api.sleeps) + 1

    def test_slow_api_calls_count_against_the_cap(self) -> None:
        # Each poll costs 10s of sleep plus two 12s calls, so far fewer polls fit.
        api = Timeline()
        api.latency = 12.0
        api.add_run(PRIOR, status="in_progress", visible_at=None)
        lookup = _lookup(api)
        assert not lookup.known
        per_poll = cb.WAIT_POLL_SECONDS + 2 * api.latency
        assert len(api.sleeps) <= int(cb.WAIT_CAP_SECONDS // per_poll) + 1
        assert api.now <= cb.WAIT_CAP_SECONDS + per_poll

    def test_a_record_that_lands_on_the_last_allowed_poll_is_read(self) -> None:
        last = int(cb.WAIT_CAP_SECONDS / cb.WAIT_POLL_SECONDS)
        api = Timeline()
        api.add_run(PRIOR, status="in_progress", visible_at=last, breached=["m.py"])
        assert _lookup(api).known

    def test_a_record_one_poll_past_the_cap_is_not_waited_for(self) -> None:
        late = int(cb.WAIT_CAP_SECONDS / cb.WAIT_POLL_SECONDS) + 1
        api = Timeline()
        api.add_run(PRIOR, status="in_progress", visible_at=late, breached=["m.py"])
        assert not _lookup(api).known

    def test_the_wait_stops_when_the_run_finishes_without_a_record(self) -> None:
        api = Timeline()
        api.add_run(PRIOR, status="in_progress", visible_at=None, completes_at=2)
        lookup = _lookup(api)
        assert not lookup.known
        assert lookup.breached("m.py")
        assert len(api.sleeps) == 2
        assert "no live artifact" in lookup.reason

    def test_a_record_uploaded_just_before_the_run_finishes_is_read(self) -> None:
        api = Timeline()
        api.add_run(PRIOR, status="in_progress", visible_at=2, completes_at=2, breached=["m.py"])
        lookup = _lookup(api)
        assert lookup.known
        assert len(api.sleeps) == 2

    def test_a_finished_previous_run_without_a_record_does_not_wait(self) -> None:
        api = Timeline()
        api.add_run(PRIOR, status="completed", visible_at=None)
        lookup = _lookup(api)
        assert not lookup.known
        assert api.sleeps == []

    def test_a_listing_with_no_status_does_not_wait(self) -> None:
        api = Timeline()
        api.add_run(PRIOR, status=None, visible_at=None)
        assert not _lookup(api).known
        assert api.sleeps == []

    def test_no_wait_happens_when_the_current_run_has_no_breach(self, tmp_path: Path) -> None:
        api = Timeline()
        api.add_run(PRIOR, status="in_progress", visible_at=None)
        verdict = cb.apply_policy(
            GATE, {}, _policy(tmp_path), api, sleep=api.sleep, clock=api.clock
        )
        assert verdict == cb.Verdict()
        assert api.calls == []
        assert api.sleeps == []


class TestApiFailureWhileWaiting:
    def test_a_failed_status_read_fails_closed_at_once(self, tmp_path: Path) -> None:
        api = Timeline()
        api.add_run(PRIOR, status="in_progress", visible_at=None)
        api.fail_exact[f"repos/{REPO}/actions/runs/{PRIOR}"] = cb.PriorStateError(
            "gh api failed: HTTP 502"
        )
        verdict = _apply(tmp_path, api)
        assert verdict.failing == ("m.py",)
        assert len(api.sleeps) == 1

    def test_a_failed_artifact_list_while_polling_fails_closed_at_once(self) -> None:
        api = Timeline()
        api.add_run(PRIOR, status="in_progress", visible_at=None)
        api.fail["/artifacts?"] = cb.PriorStateError("gh api failed: HTTP 500")
        lookup = _lookup(api)
        assert not lookup.known
        assert "HTTP 500" in lookup.reason
        assert len(api.sleeps) == 1

    @pytest.mark.parametrize("body", [b"[]", b"not json"])
    def test_a_malformed_status_body_fails_closed(self, body: bytes) -> None:
        api = Timeline()
        api.add_run(PRIOR, status="in_progress", visible_at=None)
        api.raw[f"repos/{REPO}/actions/runs/{PRIOR}"] = body
        lookup = _lookup(api)
        assert not lookup.known
        assert lookup.breached("m.py")

    def test_a_status_body_without_a_status_ends_the_wait(self) -> None:
        api = Timeline()
        api.add_run(PRIOR, status="in_progress", visible_at=None)
        api.raw[f"repos/{REPO}/actions/runs/{PRIOR}"] = b"{}"
        lookup = _lookup(api)
        assert not lookup.known
        assert len(api.sleeps) == 1
