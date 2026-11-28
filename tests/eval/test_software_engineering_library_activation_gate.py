"""Tests for the software-engineering-library activation rollback gate."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval" / "software_engineering_library_activation_gate.py"
CI_SCRIPT_PATH = REPO_ROOT / "scripts" / "eval" / "software_engineering_library_activation_ci.py"


def _ok():
    """A stand-in CompletedProcess for monkeypatched `run` calls."""
    return subprocess.CompletedProcess(args=[], returncode=0)


def _record(sink: list, value):
    """Record `value` and return the stand-in result a monkeypatched `run` owes."""
    sink.append(value)
    return _ok()


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_gate_module():
    return _load_module("software_engineering_library_activation_gate", SCRIPT_PATH)


def _load_ci_module():
    return _load_module("software_engineering_library_activation_ci", CI_SCRIPT_PATH)


def _passing_results() -> dict[str, object]:
    return {
        "rules": {
            reference_id: {"summary": {"verdict": "PASS"}}
            for reference_id in _load_gate_module().MOVED_REFERENCE_IDS
        }
    }


def test_state_tracks_each_moved_reference_and_resets_passes(tmp_path: Path):
    gate = _load_gate_module()
    existing = {
        "references": {
            "refactoring": {
                "consecutive_activation_failures": 1,
                "last_verdict": "FAIL_THRESHOLD",
            }
        }
    }

    state = gate.update_state(
        existing,
        _passing_results(),
        run_id="12345",
        checked_at="2026-07-28T16:00:00Z",
    )

    assert state["owner"] == "agent-qa"
    assert state["cadence"] == "manual, see scripts/eval/README.md"
    assert sorted(state["references"]) == sorted(gate.MOVED_REFERENCE_IDS)
    assert state["references"]["refactoring"]["consecutive_activation_failures"] == 0
    assert state["references"]["refactoring"]["last_verdict"] == "PASS"


def test_state_increments_consecutive_failures_and_reports_threshold():
    gate = _load_gate_module()
    results = _passing_results()
    results["rules"]["release-it"] = {"summary": {"verdict": "FAIL_THRESHOLD"}}

    state = gate.update_state(
        {"references": {"release-it": {"consecutive_activation_failures": 1}}},
        results,
        run_id="12346",
        checked_at="2026-07-28T16:00:00Z",
    )
    report = gate.evaluate_thresholds(state, threshold=2)

    assert state["references"]["release-it"]["consecutive_activation_failures"] == 2
    assert state["references"]["release-it"]["last_verdict"] == "FAIL_THRESHOLD"
    assert report["threshold_exceeded"] is True
    assert report["references_at_threshold"] == ["release-it"]


def test_judge_errors_do_not_increment_activation_failure_streak():
    gate = _load_gate_module()
    results = _passing_results()
    results["rules"]["clean-architecture"] = {"summary": {"verdict": "FAIL_JUDGE_ERRORS"}}

    state = gate.update_state(
        {"references": {"clean-architecture": {"consecutive_activation_failures": 1}}},
        results,
        run_id="12347",
        checked_at="2026-07-28T16:00:00Z",
    )

    reference_state = state["references"]["clean-architecture"]
    assert reference_state["consecutive_activation_failures"] == 1
    assert reference_state["last_verdict"] == "FAIL_JUDGE_ERRORS"
    assert reference_state["last_result_counted_for_rollback"] is False


def test_ci_wrapper_covers_all_moved_reference_scenarios():
    ci = _load_ci_module()

    assert sorted(ci.SCENARIOS) == [
        f"tests/evals/rule-scenarios/{reference_id}.json"
        for reference_id in sorted(_load_gate_module().MOVED_REFERENCE_IDS)
    ]


def test_documentation_names_owner_cadence_state_and_restoration_pr_policy():
    readme = (REPO_ROOT / "scripts" / "eval" / "README.md").read_text(encoding="utf-8")

    assert "Owner: `agent-qa`" in readme
    assert "Cadence: manual" in readme
    assert "consecutive_activation_failures" in readme
    assert "restoration PR" in readme


class TestValuesThatBecomeArgvAreNumericByContract:
    """A run id and an issue number are numbers, so anything else is refused.

    Semgrep flags `subprocess.run(command)` here as command injection. That
    specific claim does not hold: every call is list form with `shell=False`,
    so no shell parses the arguments and metacharacters stay literal. Measured
    directly, `subprocess.run(["echo", "hi; id"])` writes `hi; id` and runs
    nothing. Its suggested remediation, `shlex.quote()`, would make things
    worse by embedding literal quote characters into an argument that no shell
    will ever strip.

    What survives the correction is a smaller and real risk: argument
    injection, not command injection. `GITHUB_RUN_ID` and the issue number
    read from `gh` stdout are spliced into argv, and a value beginning with a
    dash is read by the receiving parser as a flag rather than as a value. So
    the fix is to enforce the contract those two values already have. Both are
    decimal integers; anything else is refused rather than forwarded.
    """

    def test_a_run_id_is_passed_through_when_it_is_a_number(self):
        ci = _load_ci_module()

        assert ci._numeric_or("30416078819", "unknown") == "30416078819"

    @pytest.mark.parametrize(
        "hostile",
        ["--fail-on-threshold", "-rf", "--output=/etc/passwd", "1 --flag", "", "  "],
    )
    def test_a_value_that_is_not_a_number_is_replaced(self, hostile: str):
        """A leading dash is the argument-injection primitive; refuse the lot."""
        assert _load_ci_module()._numeric_or(hostile, "unknown") == "unknown"

    @pytest.mark.parametrize("digits", ["\u0661\u0662\u0663", "\uff11\uff12\uff13", "\u00b2"])
    def test_a_non_ascii_digit_is_not_a_number_here(self, digits: str):
        """The edge a bare `isdigit` guard forwards.

        `"\u0661\u0662\u0663".isdigit()` is `True` and `int()` reads it as 123, so
        Python agrees it is a number while every program receiving it on argv
        sees a different token. The guard tests ASCII as well for that reason.
        """
        assert digits.isdigit()
        assert _load_ci_module()._numeric_or(digits, "unknown") == "unknown"

    def test_the_run_id_reaching_argv_is_the_sanitised_one(self, monkeypatch):
        """The end-to-end path, not just the helper in isolation."""
        ci = _load_ci_module()
        monkeypatch.setenv("GITHUB_RUN_ID", "--fail-on-threshold")

        assert ci.run_id() == "unknown"

    def test_a_numeric_environment_run_id_survives(self, monkeypatch):
        """Negative control: sanitising must not discard the real value."""
        ci = _load_ci_module()
        monkeypatch.setenv("GITHUB_RUN_ID", "30416078819")

        assert ci.run_id() == "30416078819"

    def test_a_non_numeric_issue_number_is_not_forwarded_to_argv(self, monkeypatch, tmp_path: Path):
        """`gh` stdout is process output, so it is data and not yet trusted."""
        ci = _load_ci_module()
        commands: list[list[str]] = []
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(ci, "open_issue_number", lambda: "--body-file")
        monkeypatch.setattr(ci, "run", lambda command, **kwargs: _record(commands, list(command)))

        ci.alert_issue()

        assert all("--body-file" != command[2] for command in commands if len(command) > 2)
        assert any("create" in command for command in commands)

    def test_a_numeric_issue_number_is_still_commented_on(self, monkeypatch, tmp_path: Path):
        """Negative control: the guard must not break the ordinary path."""
        ci = _load_ci_module()
        commands: list[list[str]] = []
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(ci, "open_issue_number", lambda: "3701")
        monkeypatch.setattr(ci, "run", lambda command, **kwargs: _record(commands, list(command)))

        ci.alert_issue()

        assert len(commands) == 1
        assert commands[0][:5] == ["gh", "issue", "comment", "3701", "--body-file"]
        assert len(commands[0]) == 6
        assert Path(commands[0][5]).name == "comment-body.md"

    def test_no_call_hands_a_string_to_a_shell(self):
        """The structural property that makes the injection claim unreachable.

        Every invocation must stay list form with `shell=False`. A future edit
        to `shell=True` reintroduces the vulnerability Semgrep named, and this
        is what would catch it.
        """
        source = CI_SCRIPT_PATH.read_text(encoding="utf-8")

        assert "shell=True" not in source


class TestTheAlertBodyIsScratchAndNotRepositoryState:
    """The `gh` body file is an argument-passing detail, not an output.

    It once resolved relative to the caller, so every suite run from the
    repository root left `issue-body.md` and `comment-body.md` there as
    untracked files. A validator that reads repository contents cannot tell
    that leftover apart from real state, so the write must land outside the
    caller's directory and be removed once `gh` has read it.
    """

    @staticmethod
    def _body_path(command: list[str]) -> Path:
        return Path(command[command.index("--body-file") + 1])

    def test_alert_issue_leaves_the_working_directory_empty(self, monkeypatch, tmp_path: Path):
        """The regression guard. `create_issue` runs on the unopened path."""
        ci = _load_ci_module()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(ci, "open_issue_number", lambda: "")
        monkeypatch.setattr(ci, "run", lambda command, **kwargs: _ok())

        ci.alert_issue()

        assert list(tmp_path.iterdir()) == []

    def test_commenting_also_leaves_the_working_directory_empty(self, monkeypatch, tmp_path: Path):
        """The other branch. An open issue is commented on rather than created."""
        ci = _load_ci_module()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(ci, "open_issue_number", lambda: "3701")
        monkeypatch.setattr(ci, "run", lambda command, **kwargs: _ok())

        ci.alert_issue()

        assert list(tmp_path.iterdir()) == []

    def test_the_body_file_is_readable_while_gh_is_running(self, monkeypatch, tmp_path: Path):
        """Negative control: moving the write must not break the feature.

        A path that no longer exists when `gh` opens it would still satisfy the
        two emptiness assertions above, so the content has to be read from the
        argv path at the moment of the call.
        """
        ci = _load_ci_module()
        seen: list[str] = []
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(ci, "open_issue_number", lambda: "3701")
        monkeypatch.setattr(
            ci,
            "run",
            lambda command, **kwargs: _record(
                seen, self._body_path(command).read_text(encoding="utf-8")
            ),
        )

        ci.alert_issue()

        assert seen and "activation gate failed again" in seen[0]

    def test_the_body_file_is_gone_once_gh_has_returned(self, monkeypatch, tmp_path: Path):
        """Scratch is removed rather than relocated to another litter site."""
        ci = _load_ci_module()
        paths: list[Path] = []
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(ci, "open_issue_number", lambda: "3701")
        monkeypatch.setattr(
            ci, "run", lambda command, **kwargs: _record(paths, self._body_path(command))
        )

        ci.alert_issue()

        assert paths and not paths[0].exists()


class TestTheAlertBodyNamesWhereTheRunHappened:
    """No workflow runs this gate since 2026-11-25, so most runs are manual.

    A manual run has no run page and uploads nothing. The body must not print a
    dead `actions/runs/unknown` link or send the reader to an uploaded artifact.
    """

    @staticmethod
    def _bodies(monkeypatch, tmp_path: Path, open_issue: str) -> list[str]:
        ci = _load_ci_module()
        seen: list[str] = []
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(ci, "open_issue_number", lambda: open_issue)
        monkeypatch.setattr(
            ci,
            "run",
            lambda command, **kwargs: _record(
                seen, Path(command[command.index("--body-file") + 1]).read_text(encoding="utf-8")
            ),
        )
        ci.alert_issue()
        return seen

    @pytest.mark.parametrize("open_issue", ["", "3701"], ids=["create", "comment"])
    def test_a_manual_run_prints_no_run_link(self, monkeypatch, tmp_path: Path, open_issue: str):
        monkeypatch.delenv("GITHUB_RUN_ID", raising=False)

        (body,) = self._bodies(monkeypatch, tmp_path, open_issue)

        assert "Run: manual, outside GitHub Actions." in body
        assert "actions/runs/" not in body
        assert "uploaded" not in body
        assert "`activation-gate-report.md`" in body

    @pytest.mark.parametrize("open_issue", ["", "3701"], ids=["create", "comment"])
    def test_a_numeric_run_id_still_prints_the_run_link(
        self, monkeypatch, tmp_path: Path, open_issue: str
    ):
        """Negative control: a run inside Actions keeps its link."""
        monkeypatch.setenv("GITHUB_RUN_ID", "30416078819")
        monkeypatch.setenv("GITHUB_SERVER_URL", "https://github.com")
        monkeypatch.setenv("GITHUB_REPOSITORY", "rjmurillo/ai-agents")

        (body,) = self._bodies(monkeypatch, tmp_path, open_issue)

        expected = "https://github.com/rjmurillo/ai-agents/actions/runs/30416078819"
        assert f"Workflow run: {expected}" in body
        assert "Run: manual" not in body

    @pytest.mark.parametrize("hostile", ["--repo", "12 34", "", "١٢٣"])
    def test_a_run_id_that_is_not_a_number_reads_as_manual(self, monkeypatch, hostile: str):
        """Edge: a refused run id must not reach the body as a link."""
        monkeypatch.setenv("GITHUB_RUN_ID", hostile)

        source = _load_ci_module().run_source()

        assert source.startswith("Run: manual")
        assert "unknown" not in source


class TestAMeasurementFailureDoesNotCountAsRuleUnderperformance:
    """Only a verdict about the rule may advance the rollback streak.

    `FAIL_ROUTE_MISSED_TARGET` says the run never opened the target reference,
    so it carries no evidence about the rule at all. Counting it would retire a
    rule for the harness's routing imprecision. The same reasoning already
    keeps the coverage and over-activation verdicts out of the set.
    """

    MEASUREMENT_VERDICTS = (
        "FAIL_ROUTE_MISSED_TARGET",
        "FAIL_POSITIVE_INCOMPLETE",
        "FAIL_NEGATIVE_INCOMPLETE",
        "FAIL_OVER_ACTIVATION",
        "FAIL_JUDGE_ERRORS",
        # Asymmetric with NO_POSITIVE_CASES on purpose, and the asymmetry is
        # the rollback action rather than the verdict shape. Rollback restores
        # the always-on rule. That remediates "we cannot show the skill
        # activates". It cannot remediate "we cannot show the skill restrains",
        # because an always-on rule fires on everything and is the least
        # restrained state available. Counting it would retire a skill for a
        # missing scenario, in the direction that makes the concern worse.
        "NO_NEGATIVE_CASES",
    )

    @pytest.mark.parametrize("verdict", MEASUREMENT_VERDICTS)
    def test_a_measurement_verdict_never_advances_the_streak(self, verdict):
        gate = _load_gate_module()
        assert verdict not in gate.ROLLBACK_VERDICTS

    def test_a_verdict_about_the_rule_still_advances_the_streak(self):
        """Guard against a fix that empties the set instead of scoping it."""
        gate = _load_gate_module()
        assert {"FAIL_THRESHOLD", "FAIL_NO_DELTA"} <= gate.ROLLBACK_VERDICTS
