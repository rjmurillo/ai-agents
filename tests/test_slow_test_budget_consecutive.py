"""The slow-test budget applies the consecutive-main policy (issue #6757).

Coverage:
* Positive: a breach on main that the previous main run also had exits 1.
* Negative: a first breach on main exits 0 and warns; a pull request exits 0.
* Edge: an unknown previous run on main exits 1 (fail closed); no breach exits 0.
* Config and external paths: unusable policy flags exit 2, an unwritable record
  exits 3, and the default (no flag) keeps the old fail-on-any-overrun contract.
* The workflow passes the policy flags, grants ``actions: read`` and uploads the
  record under the name the helper reads back.
All GitHub I/O is faked.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.ci import consecutive_breach as cb
from scripts.testing import slow_test_budget as budget_gate

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE = "tests/test_alpha.py"

_JUNIT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" tests="1">
<testcase classname="tests.test_alpha" name="test_one" time="11.000" />
</testsuite></testsuites>
"""


def _inputs(tmp_path: Path, limit: float) -> list[str]:
    junit = tmp_path / "junit.xml"
    junit.write_text(_JUNIT, encoding="utf-8")
    toml = tmp_path / "budget.toml"
    toml.write_text(f'[tool.slow-test-budget]\n"{MODULE}" = {limit}\n', encoding="utf-8")
    return [str(junit), "--budget", str(toml)]


def _env(monkeypatch: pytest.MonkeyPatch, event: str, ref: str) -> None:
    for key, value in {
        "GITHUB_EVENT_NAME": event,
        "GITHUB_REF": ref,
        "GITHUB_RUN_ID": "100",
        "GITHUB_SHA": "deadbeef",
        "GITHUB_REPOSITORY": "owner/repo",
    }.items():
        monkeypatch.setenv(key, value)


def _policy_flags(tmp_path: Path) -> list[str]:
    return [
        "--breach-policy",
        "consecutive-main",
        "--workflow",
        "pytest.yml",
        "--breach-record-out",
        str(tmp_path / "rec" / cb.RECORD_FILE),
    ]


def _previous(monkeypatch: pytest.MonkeyPatch, breached: list[str] | None) -> list[str]:
    calls: list[str] = []

    def fake(endpoint: str) -> bytes:
        calls.append(endpoint)
        if breached is None:
            raise cb.PriorStateError("HTTP 500")
        if "/workflows/" in endpoint:
            return json.dumps(
                {"workflow_runs": [{"id": 90, "head_branch": "main", "event": "push"}]}
            ).encode()
        if endpoint.endswith("/zip"):
            import io
            import zipfile

            buffer = io.BytesIO()
            record = cb.BreachRecord("slow-test-budget", 90, "abc", tuple(breached)).to_json()
            with zipfile.ZipFile(buffer, "w") as zf:
                zf.writestr(cb.RECORD_FILE, record)
            return buffer.getvalue()
        name = cb.artifact_name("slow-test-budget")
        return json.dumps({"artifacts": [{"id": 5, "name": name, "expired": False}]}).encode()

    monkeypatch.setattr(cb, "gh_fetch", fake)
    return calls


class TestMain:
    def test_a_repeat_breach_on_main_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, [MODULE])
        argv = [*_inputs(tmp_path, 5.0), *_policy_flags(tmp_path)]
        assert budget_gate.main(argv) == 1
        captured = capsys.readouterr()
        assert f"::error title=Slow-test budget::{MODULE}: recorded 11.00s against 5.00s" in (
            captured.out
        )
        assert "over budget: tests/test_alpha.py" in captured.err

    def test_a_first_breach_on_main_warns_and_records(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, [])
        assert budget_gate.main([*_inputs(tmp_path, 5.0), *_policy_flags(tmp_path)]) == 0
        assert "::warning title=Slow-test budget::" in capsys.readouterr().out
        record = json.loads((tmp_path / "rec" / cb.RECORD_FILE).read_text(encoding="utf-8"))
        assert record["breached"] == [MODULE]
        assert record["gate"] == "slow-test-budget"

    def test_a_pull_request_breach_warns_and_exits_zero_without_a_lookup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "pull_request", "refs/pull/6479/merge")
        calls = _previous(monkeypatch, [MODULE])
        assert budget_gate.main([*_inputs(tmp_path, 5.0), *_policy_flags(tmp_path)]) == 0
        assert "::warning" in capsys.readouterr().out
        assert calls == []
        assert not (tmp_path / "rec").exists()

    def test_an_unknown_previous_run_on_main_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, None)
        assert budget_gate.main([*_inputs(tmp_path, 5.0), *_policy_flags(tmp_path)]) == 1
        assert "failing closed" in capsys.readouterr().out

    def test_no_breach_on_main_exits_zero_and_records_a_clean_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        calls = _previous(monkeypatch, [MODULE])
        assert budget_gate.main([*_inputs(tmp_path, 50.0), *_policy_flags(tmp_path)]) == 0
        assert calls == []
        record = json.loads((tmp_path / "rec" / cb.RECORD_FILE).read_text(encoding="utf-8"))
        assert record["breached"] == []

    def test_without_the_flag_any_overrun_still_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _env(monkeypatch, "pull_request", "refs/pull/1/merge")
        assert budget_gate.main(_inputs(tmp_path, 5.0)) == 1

    def test_an_unusable_policy_exits_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        for name in ("GITHUB_EVENT_NAME", "GITHUB_REF", "GITHUB_RUN_ID", "GITHUB_REPOSITORY"):
            monkeypatch.delenv(name, raising=False)
        argv = [*_inputs(tmp_path, 5.0), "--breach-policy", "consecutive-main"]
        assert budget_gate.main(argv) == 2
        assert "bad breach policy" in capsys.readouterr().err

    def test_an_unwritable_record_exits_three(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _env(monkeypatch, "push", cb.MAIN_REF)
        _previous(monkeypatch, [])
        blocker = tmp_path / "rec"
        blocker.write_text("a file where the directory should go", encoding="utf-8")
        assert budget_gate.main([*_inputs(tmp_path, 5.0), *_policy_flags(tmp_path)]) == 3
        assert "could not write the breach record" in capsys.readouterr().err


class TestTheWorkflowWiring:
    def _coverage_job(self) -> Any:
        text = (REPO_ROOT / ".github/workflows/pytest.yml").read_text(encoding="utf-8")
        return yaml.safe_load(text)["jobs"]["coverage"]

    def test_the_job_may_read_the_previous_run(self) -> None:
        job = self._coverage_job()
        assert job["permissions"] == {"contents": "read", "actions": "read"}

    def test_the_gate_step_passes_the_policy_and_a_token(self) -> None:
        steps = self._coverage_job()["steps"]
        gate = next(s for s in steps if "slow_test_budget.py" in str(s.get("run", "")))
        assert gate["env"] == {"GH_TOKEN": "${{ github.token }}"}
        run = " ".join(gate["run"].split())
        assert "--breach-policy consecutive-main" in run
        assert "--workflow pytest.yml" in run
        assert "--breach-record-out breach-records/slow-test-budget/breach-record.json" in run

    def test_a_failed_coverage_step_does_not_skip_the_gate_and_lose_its_record(self) -> None:
        # The default success() would skip this step when Combine coverage data
        # or the coverage upload before it fails, so no record is written and
        # the next main breach fails closed.
        steps = self._coverage_job()["steps"]
        gate = next(s for s in steps if "slow_test_budget.py" in str(s.get("run", "")))
        assert gate["if"] == "!cancelled()"

    def test_the_gate_is_not_gated_on_success_of_an_earlier_step(self) -> None:
        # Negative: a condition that names success(), a step outcome, or a
        # status of an earlier step would bring the skip back.
        steps = self._coverage_job()["steps"]
        gate = next(s for s in steps if "slow_test_budget.py" in str(s.get("run", "")))
        condition = str(gate["if"])
        assert "success()" not in condition
        assert "steps." not in condition
        assert "outcome" not in condition

    def test_the_upload_publishes_the_record_the_lookup_reads(self) -> None:
        steps = self._coverage_job()["steps"]
        names = [s.get("name") for s in steps]
        upload = next(s for s in steps if s.get("name") == "Upload slow-test budget breach record")
        gate = next(s for s in steps if "slow_test_budget.py" in str(s.get("run", "")))
        assert names.index(upload["name"]) > steps.index(gate)
        assert upload["if"] == "always()"
        assert upload["with"]["name"] == cb.artifact_name(budget_gate.GATE)
        assert upload["with"]["path"] == "breach-records/slow-test-budget/"
        assert upload["with"]["if-no-files-found"] == "ignore"
        assert re.fullmatch(r"actions/upload-artifact@[0-9a-f]{40}", upload["uses"])
