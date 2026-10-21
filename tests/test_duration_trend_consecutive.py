"""The duration trend applies the consecutive-main policy (issue #6796).

Coverage:
* Positive: a regression on main that the previous main run also had exits 1.
* Negative: a first regression on main exits 0 and warns; a pull request exits 0
  and makes no API call; a different module on the previous run does not count.
* Edge: an unknown previous run on main exits 1 (fail closed), whether the
  cause is no prior run, a missing artifact, or an API failure; no regression
  records a clean run; the suite regression is a key like any module.
* Config and external paths: unusable policy flags exit 2, an unwritable record
  exits 3 after the history is written, and the default (no flag) keeps the
  old contract.
* The workflow passes the policy flags, grants ``actions: read`` and uploads the
  record under the name the helper reads back.
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
from scripts.testing import duration_trend as trend
from tests.duration_test_helpers import write_history, write_junit

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE = "tests/test_alpha.py"
PRIOR_RUN = 90


def _env(monkeypatch: pytest.MonkeyPatch, event: str, ref: str) -> None:
    for key, value in {
        "GITHUB_EVENT_NAME": event,
        "GITHUB_REF": ref,
        "GITHUB_RUN_ID": "100",
        "GITHUB_SHA": "deadbeef",
        "GITHUB_REPOSITORY": "owner/repo",
    }.items():
        monkeypatch.setenv(key, value)


def _argv(tmp_path: Path, event: str, ref: str, *extra: str) -> list[str]:
    report = write_junit(tmp_path, "p", {"tests.test_alpha": [20.0, 20.0]}, 40.0)
    return [
        str(report),
        "--history",
        str(write_history(tmp_path, [10.0, 12.0])),
        "--event",
        event,
        "--ref",
        ref,
        "--breach-policy",
        "consecutive-main",
        "--workflow",
        "pytest.yml",
        "--breach-record-out",
        str(tmp_path / "rec" / cb.RECORD_FILE),
        *extra,
    ]


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
            record = cb.BreachRecord(trend.GATE, PRIOR_RUN, "abc", tuple(breached)).to_json()
            with zipfile.ZipFile(buffer, "w") as zf:
                zf.writestr(cb.RECORD_FILE, record)
            return buffer.getvalue()
        name = cb.artifact_name(trend.GATE)
        return json.dumps({"artifacts": [{"id": 5, "name": name, "expired": False}]}).encode()

    monkeypatch.setattr(cb, "gh_fetch", fake)
    return calls


class TestMain:
    def test_a_repeat_regression_on_main_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, [MODULE])
        assert trend.main(_argv(tmp_path, "push", cb.MAIN_REF)) == 1
        out = capsys.readouterr().out
        assert f"::error title=Test duration trend::{MODULE}: took 40.0s" in out
        assert "two main runs in a row" in out

    def test_a_first_regression_on_main_warns_records_and_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, [])
        assert trend.main(_argv(tmp_path, "push", cb.MAIN_REF)) == 0
        assert f"::warning title=Test duration trend::{MODULE}: took 40.0s" in (
            capsys.readouterr().out
        )
        record = json.loads((tmp_path / "rec" / cb.RECORD_FILE).read_text(encoding="utf-8"))
        assert record["gate"] == "duration-trend"
        assert record["run_id"] == 100
        assert record["breached"] == [MODULE]

    def test_a_different_module_on_the_previous_run_does_not_count(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, ["tests/test_other.py"])
        assert trend.main(_argv(tmp_path, "push", cb.MAIN_REF)) == 0

    def test_a_pull_request_warns_exits_zero_and_makes_no_api_call(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "pull_request", "refs/pull/6796/merge")
        calls = _previous(monkeypatch, [MODULE])
        summary = tmp_path / "summary.md"
        argv = _argv(tmp_path, "pull_request", "refs/pull/6796/merge", "--summary", str(summary))
        assert trend.main(argv) == 0
        captured = capsys.readouterr()
        assert "::warning title=Test duration trend::" in captured.out
        assert "::error" not in captured.out
        assert "advisory on event=pull_request" in captured.err
        assert "Advisory run (pull_request on refs/pull/6796/merge)" in (
            summary.read_text(encoding="utf-8")
        )
        assert calls == []
        assert not (tmp_path / "rec").exists()

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
        assert trend.main(_argv(tmp_path, "push", cb.MAIN_REF)) == 1
        assert "failing closed" in capsys.readouterr().out

    def test_no_regression_on_main_exits_zero_and_records_a_clean_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        calls = _previous(monkeypatch, [MODULE])
        report = write_junit(tmp_path, "q", {"tests.test_alpha": [5.0, 5.0]}, 10.0)
        argv = _argv(tmp_path, "push", cb.MAIN_REF)
        argv[0] = str(report)
        assert trend.main(argv) == 0
        assert calls == []
        record = json.loads((tmp_path / "rec" / cb.RECORD_FILE).read_text(encoding="utf-8"))
        assert record["breached"] == []

    def test_the_suite_regression_is_a_key_like_a_module(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, ["suite"])
        argv = _argv(tmp_path, "push", cb.MAIN_REF)
        argv[0] = str(write_junit(tmp_path, "q", {"tests.test_alpha": [90.0]}, 90.0))
        argv[2] = str(write_history(tmp_path, [10.0, 12.0], tests=1))
        assert trend.main(argv) == 1
        record = json.loads((tmp_path / "rec" / cb.RECORD_FILE).read_text(encoding="utf-8"))
        assert "suite" in record["breached"]

    def test_a_main_run_names_the_policy_in_the_summary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, [])
        summary = tmp_path / "summary.md"
        assert trend.main(_argv(tmp_path, "push", cb.MAIN_REF, "--summary", str(summary))) == 0
        text = summary.read_text(encoding="utf-8")
        assert "cannot be established (issue #6796)" in text
        assert "Advisory run" not in text

    def test_the_record_takes_its_sha_from_the_environment_when_no_flag_is_given(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, [])
        assert trend.main(_argv(tmp_path, "push", cb.MAIN_REF)) == 0
        record = json.loads((tmp_path / "rec" / cb.RECORD_FILE).read_text(encoding="utf-8"))
        assert record["head_sha"] == "deadbeef"

    def test_an_explicit_sha_wins_over_the_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, [])
        assert trend.main(_argv(tmp_path, "push", cb.MAIN_REF, "--sha", "c0ffee")) == 0
        record = json.loads((tmp_path / "rec" / cb.RECORD_FILE).read_text(encoding="utf-8"))
        assert record["head_sha"] == "c0ffee"

    def test_without_the_flag_a_regression_on_main_still_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = _previous(monkeypatch, [])
        argv = _argv(tmp_path, "push", cb.MAIN_REF)[:7]
        assert trend.main(argv) == 1
        assert calls == []

    def test_an_unusable_policy_exits_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        for name in ("GITHUB_RUN_ID", "GITHUB_REPOSITORY"):
            monkeypatch.delenv(name, raising=False)
        argv = _argv(tmp_path, "push", cb.MAIN_REF)
        del argv[argv.index("--workflow") : argv.index("--workflow") + 2]
        assert trend.main(argv) == 2
        assert "bad breach policy" in capsys.readouterr().err

    def test_an_unwritable_record_exits_three_after_the_history_is_written(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, [])
        (tmp_path / "rec").write_text("a file where the directory should go", encoding="utf-8")
        out = tmp_path / "out.json"
        argv = _argv(tmp_path, "push", cb.MAIN_REF, "--write-history", str(out))
        assert trend.main(argv) == 3
        assert out.exists()
        assert "could not write the breach record" in capsys.readouterr().out


class TestTheWorkflowWiring:
    def _job(self) -> Any:
        text = (REPO_ROOT / ".github/workflows/pytest.yml").read_text(encoding="utf-8")
        return yaml.safe_load(text)["jobs"]["test-durations"]

    def test_the_job_may_read_the_previous_run(self) -> None:
        assert self._job()["permissions"] == {"contents": "read", "actions": "read"}

    def test_the_trend_step_passes_the_policy_and_a_token(self) -> None:
        steps = self._job()["steps"]
        gate = next(s for s in steps if s.get("id") == "duration-trend")
        assert gate["env"]["GH_TOKEN"] == "${{ github.token }}"
        run = " ".join(gate["run"].split())
        assert "--breach-policy consecutive-main" in run
        assert "--workflow pytest.yml" in run
        assert "--breach-record-out breach-records/duration-trend/breach-record.json" in run

    def test_the_upload_publishes_the_record_the_lookup_reads(self) -> None:
        steps = self._job()["steps"]
        names = [s.get("name") for s in steps]
        upload = next(s for s in steps if s.get("name") == "Upload duration trend breach record")
        gate = next(s for s in steps if s.get("id") == "duration-trend")
        assert names.index(upload["name"]) > steps.index(gate)
        assert upload["if"] == "always()"
        assert upload["with"]["name"] == cb.artifact_name(trend.GATE)
        assert upload["with"]["path"] == "breach-records/duration-trend/"
        assert upload["with"]["if-no-files-found"] == "ignore"
        assert re.fullmatch(r"actions/upload-artifact@[0-9a-f]{40}", upload["uses"])

    def test_the_gate_names_do_not_collide(self) -> None:
        assert trend.GATE == "duration-trend"
        assert trend.GATE != "slow-test-budget"
