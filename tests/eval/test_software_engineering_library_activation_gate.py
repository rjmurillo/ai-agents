"""Tests for the software-engineering-library activation rollback gate."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "eval" / "software_engineering_library_activation_gate.py"
CI_SCRIPT_PATH = REPO_ROOT / "scripts" / "eval" / "software_engineering_library_activation_ci.py"
ADR006_SCANNER_PATH = REPO_ROOT / "scripts" / "ci" / "adr006_run_block_scanner.py"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "software-engineering-library-activation.yml"


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


def _load_adr006_scanner():
    return _load_module("adr006_run_block_scanner", ADR006_SCANNER_PATH)


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
    assert state["cadence"] == "weekly Monday 06:30 UTC and pull_request dry-run gate"
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
    results["rules"]["clean-architecture"] = {
        "summary": {"verdict": "FAIL_JUDGE_ERRORS"}
    }

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


def test_workflow_runs_weekly_and_invokes_ci_wrapper():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    triggers = workflow[True]

    assert triggers["schedule"] == [{"cron": "30 6 * * 1"}]
    assert workflow["permissions"] == {
        "contents": "read",
        "issues": "write",
        "actions": "read",
    }

    run_eval_step = next(
        step
        for step in workflow["jobs"]["activation-gate"]["steps"]
        if step["name"] == "Run live activation eval"
    )
    alert_step = next(
        step
        for step in workflow["jobs"]["activation-gate"]["steps"]
        if step["name"] == "Create or update rollback alert issue"
    )

    assert run_eval_step["run"] == (
        "uv run python scripts/eval/software_engineering_library_activation_ci.py live-eval"
    )
    assert alert_step["run"] == (
        "uv run python scripts/eval/software_engineering_library_activation_ci.py alert-issue"
    )


def test_ci_wrapper_covers_all_moved_reference_scenarios():
    ci = _load_ci_module()

    assert sorted(ci.SCENARIOS) == [
        f"tests/evals/rule-scenarios/{reference_id}.json"
        for reference_id in sorted(_load_gate_module().MOVED_REFERENCE_IDS)
    ]


def test_workflow_does_not_add_adr006_run_block_violations():
    scanner = _load_adr006_scanner()
    blocks = scanner.scan_text(WORKFLOW_PATH.read_text(encoding="utf-8"))

    assert [block.line for block in blocks if scanner.is_violation(block, 10)] == []


def test_documentation_names_owner_cadence_state_and_restoration_pr_policy():
    readme = (REPO_ROOT / "scripts" / "eval" / "README.md").read_text(
        encoding="utf-8"
    )

    assert "Owner: `agent-qa`" in readme
    assert "Cadence: weekly Monday 06:30 UTC" in readme
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
        monkeypatch.setattr(
            ci, "run", lambda command, **kwargs: _record(commands, list(command))
        )

        ci.alert_issue()

        assert all("--body-file" != command[2] for command in commands if len(command) > 2)
        assert any("create" in command for command in commands)

    def test_a_numeric_issue_number_is_still_commented_on(self, monkeypatch, tmp_path: Path):
        """Negative control: the guard must not break the ordinary path."""
        ci = _load_ci_module()
        commands: list[list[str]] = []
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(ci, "open_issue_number", lambda: "3701")
        monkeypatch.setattr(
            ci, "run", lambda command, **kwargs: _record(commands, list(command))
        )

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
