"""The leg wall time gate applies the consecutive-main policy (issue #6751).

Coverage:
* Positive: a slow leg on main that the previous main run also had exits 1.
* Negative: a first slow leg on main exits 0 and warns and records; a pull request
  exits 0 and makes no API call; a clean previous run does not count.
* Edge: an unknown previous run on main exits 1 (fail closed), whether the cause
  is no prior run, a missing artifact, or an API failure; no slow leg records a
  clean run; legs that trade places between runs still count as a repeat.
* Config and external paths: unusable policy flags exit 2, an unwritable record
  exits 3, and the default (no flag) keeps the old fail-on-any-slow-leg contract.
* The workflow passes the policy flags, grants ``actions: read`` and uploads the
  record under the name the helper reads back, distinct from the other two gates.
All GitHub I/O is faked.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ci import consecutive_breach as cb
from scripts.testing import duration_gate_check as gate
from scripts.testing import duration_trend, slow_test_budget
from tests.duration_gate_helpers import write_legs

REPO_ROOT = Path(__file__).resolve().parents[1]
PRIOR_RUN = 90
KEY = gate.LEG_WALL_TIME_GATE


def _env(monkeypatch: pytest.MonkeyPatch, event: str, ref: str) -> None:
    for name, value in {
        "GITHUB_EVENT_NAME": event,
        "GITHUB_REF": ref,
        "GITHUB_RUN_ID": "100",
        "GITHUB_SHA": "deadbeef",
        "GITHUB_REPOSITORY": "owner/repo",
    }.items():
        monkeypatch.setenv(name, value)


def _argv(tmp_path: Path, **walls: float) -> list[str]:
    return [
        *write_legs(tmp_path, **walls),
        "--breach-policy",
        "consecutive-main",
        "--workflow",
        "pytest.yml",
        "--breach-record-out",
        str(tmp_path / "rec" / cb.RECORD_FILE),
    ]


def _slow(tmp_path: Path) -> list[str]:
    return _argv(tmp_path, split_1=494.1, split_2=250.0)


def _previous(monkeypatch: pytest.MonkeyPatch, breached: list[str] | None) -> list[str]:
    """Fake ``gh api``. ``None`` makes every call fail; a list is the prior record."""
    calls: list[str] = []

    def fake(endpoint: str) -> bytes:
        calls.append(endpoint)
        if breached is None:
            raise cb.PriorStateError("HTTP 500")
        if "/workflows/" in endpoint:
            return json.dumps(
                {"workflow_runs": [{"id": PRIOR_RUN, "head_branch": "main", "event": "push"}]}
            ).encode()
        if endpoint.endswith("/zip"):
            buffer = io.BytesIO()
            record = cb.BreachRecord(KEY, PRIOR_RUN, "abc", tuple(breached)).to_json()
            with zipfile.ZipFile(buffer, "w") as zf:
                zf.writestr(cb.RECORD_FILE, record)
            return buffer.getvalue()
        name = cb.artifact_name(KEY)
        return json.dumps({"artifacts": [{"id": 5, "name": name, "expired": False}]}).encode()

    monkeypatch.setattr(cb, "gh_fetch", fake)
    return calls


class TestMain:
    def test_a_repeat_slow_leg_on_main_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, [KEY])
        assert gate.main(_slow(tmp_path)) == 1
        out = capsys.readouterr().out
        assert "::error title=Test leg wall time::" in out
        assert "pytest-results-split-1 took 494.1s, above the 480s limit" in out
        assert "two main runs in a row" in out

    def test_a_first_slow_leg_on_main_warns_records_and_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, [])
        assert gate.main(_slow(tmp_path)) == 0
        assert "::warning title=Test leg wall time::" in capsys.readouterr().out
        record = json.loads((tmp_path / "rec" / cb.RECORD_FILE).read_text(encoding="utf-8"))
        assert record["breached"] == [KEY]
        assert record["gate"] == KEY
        assert record["run_id"] == 100

    def test_a_different_leg_on_the_previous_run_still_counts_as_a_repeat(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The run is the unit. Legs trade places, so the previous record names the
        # gate and never a leg, and a rotating slow leg cannot hide a slow suite.
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, [KEY])
        assert gate.main(_argv(tmp_path, split_1=100.0, split_3=500.0)) == 1

    def test_a_pull_request_warns_exits_zero_and_makes_no_api_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "pull_request", "refs/pull/6749/merge")
        calls = _previous(monkeypatch, [KEY])
        assert gate.main(_slow(tmp_path)) == 0
        out = capsys.readouterr().out
        assert "::warning title=Test leg wall time::" in out
        assert "::error" not in out
        assert calls == []
        assert not (tmp_path / "rec").exists()

    def test_workflow_dispatch_on_main_only_warns(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _env(monkeypatch, "workflow_dispatch", cb.MAIN_REF)
        calls = _previous(monkeypatch, [KEY])
        assert gate.main(_slow(tmp_path)) == 0
        assert calls == []

    @pytest.mark.parametrize(
        "prior",
        [None, "no-run", "no-artifact"],
        ids=["api-failure", "no-prior-run", "no-live-artifact"],
    )
    def test_an_unknown_previous_run_on_main_fails_closed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        prior: str | None,
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        if prior is None:
            _previous(monkeypatch, None)
        elif prior == "no-run":
            monkeypatch.setattr(cb, "gh_fetch", lambda _e: b'{"workflow_runs": []}')
        else:

            def fake(endpoint: str) -> bytes:
                if "/workflows/" in endpoint:
                    runs = [{"id": PRIOR_RUN, "head_branch": "main", "event": "push"}]
                    return json.dumps({"workflow_runs": runs}).encode()
                return b'{"artifacts": []}'

            monkeypatch.setattr(cb, "gh_fetch", fake)
        assert gate.main(_slow(tmp_path)) == 1
        assert "failing closed" in capsys.readouterr().out

    def test_no_slow_leg_on_main_exits_zero_and_records_a_clean_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        calls = _previous(monkeypatch, [KEY])
        assert gate.main(_argv(tmp_path, split_1=300.0, split_2=290.0)) == 0
        assert calls == []
        record = json.loads((tmp_path / "rec" / cb.RECORD_FILE).read_text(encoding="utf-8"))
        assert record["breached"] == []

    def test_a_leg_at_the_limit_is_not_a_breach(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        calls = _previous(monkeypatch, [KEY])
        assert gate.main(_argv(tmp_path, split_1=480.0, split_2=470.0)) == 0
        assert calls == []

    def test_no_slow_leg_gives_no_breach(self) -> None:
        assert gate._breaches([], 480.0) == {}

    def test_every_slow_leg_is_named_once_in_one_annotation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "pull_request", "refs/pull/1/merge")
        assert gate.main(_argv(tmp_path, split_1=490.0, split_2=520.0, split_3=100.0)) == 0
        lines = [ln for ln in capsys.readouterr().out.splitlines() if "Test leg wall time" in ln]
        assert len(lines) == 1
        assert lines[0].index("split-2 took 520.0s") < lines[0].index("split-1 took 490.0s")

    def test_the_imbalance_warning_still_prints_under_the_policy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "pull_request", "refs/pull/1/merge")
        assert gate.main(_argv(tmp_path, split_1=200.0, split_2=100.0)) == 0
        assert "::warning title=Split imbalance::" in capsys.readouterr().out

    def test_without_the_flag_a_slow_leg_still_exits_one_on_a_pull_request(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "pull_request", "refs/pull/1/merge")
        calls = _previous(monkeypatch, [])
        assert gate.main(write_legs(tmp_path, split_1=481.0, split_2=470.0)) == 1
        assert "::error title=Test leg wall time::" in capsys.readouterr().out
        assert calls == []

    def test_an_unusable_policy_exits_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        for name in ("GITHUB_EVENT_NAME", "GITHUB_REF", "GITHUB_RUN_ID", "GITHUB_REPOSITORY"):
            monkeypatch.delenv(name, raising=False)
        argv = [*write_legs(tmp_path, split_1=1.0), "--breach-policy", "consecutive-main"]
        assert gate.main(argv) == 2
        assert "bad breach policy" in capsys.readouterr().err

    def test_an_unwritable_record_exits_three(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, [])
        (tmp_path / "rec").write_text("a file where the directory should go", encoding="utf-8")
        assert gate.main(_slow(tmp_path)) == 3
        assert "could not write the breach record" in capsys.readouterr().err

    def test_a_bad_policy_exits_two_even_when_an_input_is_unreadable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        for name in ("GITHUB_EVENT_NAME", "GITHUB_REF", "GITHUB_RUN_ID", "GITHUB_REPOSITORY"):
            monkeypatch.delenv(name, raising=False)
        argv = [str(tmp_path / "absent.xml"), "--breach-policy", "consecutive-main"]
        assert gate.main(argv) == 2
        assert "bad breach policy" in capsys.readouterr().err

    def test_a_report_with_no_test_records_exits_one_before_the_policy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        calls = _previous(monkeypatch, [])
        empty = tmp_path / "empty.xml"
        empty.write_text("<testsuites><testsuite time='1'/></testsuites>", encoding="utf-8")
        argv = [str(empty), *_argv(tmp_path, split_1=1.0)[1:]]
        assert gate.main(argv) == 1
        assert calls == []
        assert not (tmp_path / "rec").exists()


class TestTheWorkflowWiring:
    def _job(self) -> Any:
        text = (REPO_ROOT / ".github/workflows/pytest.yml").read_text(encoding="utf-8")
        return yaml.safe_load(text)["jobs"]["coverage"]

    def _step(self) -> Any:
        return next(s for s in self._job()["steps"] if s.get("name") == "Gate pytest leg wall time")

    def test_the_job_may_read_the_previous_run(self) -> None:
        assert self._job()["permissions"] == {"contents": "read", "actions": "read"}

    def test_the_gate_step_passes_the_policy_and_a_token(self) -> None:
        step = self._step()
        assert step["env"] == {"GH_TOKEN": "${{ github.token }}"}
        run = " ".join(step["run"].split())
        assert "--breach-policy consecutive-main" in run
        assert "--workflow pytest.yml" in run
        assert "--breach-record-out breach-records/leg-wall-time/breach-record.json" in run

    def test_a_failed_budget_step_does_not_skip_the_gate_and_lose_its_record(self) -> None:
        # The default success() would skip this step when the budget step before
        # it fails, so no record is written and the next breach fails closed.
        assert self._step()["if"] == "!cancelled()"

    def test_the_upload_publishes_the_record_the_lookup_reads(self) -> None:
        steps = self._job()["steps"]
        names = [s.get("name") for s in steps]
        upload = next(s for s in steps if s.get("name") == "Upload leg wall time breach record")
        assert names.index(upload["name"]) > steps.index(self._step())
        assert upload["if"] == "always()"
        assert upload["with"]["name"] == cb.artifact_name(KEY)
        assert upload["with"]["path"] == "breach-records/leg-wall-time/"
        assert upload["with"]["if-no-files-found"] == "ignore"
        assert re.fullmatch(r"actions/upload-artifact@[0-9a-f]{40}", upload["uses"])

    def test_the_gate_keys_are_unique_so_records_do_not_collide(self) -> None:
        keys = {slow_test_budget.GATE, duration_trend.GATE, KEY}
        assert keys == {"slow-test-budget", "duration-trend", "leg-wall-time"}
        assert len({cb.artifact_name(k) for k in keys}) == 3
