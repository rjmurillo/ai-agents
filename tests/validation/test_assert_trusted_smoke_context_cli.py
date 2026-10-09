"""CLI contract tests for the trusted-context gate (issue #2231 item 3, REQ-047).

The CLI prints ``true`` or ``false`` on stdout and exits 0 for both decisions;
only a usage error exits non-zero. Decision logic is covered in
``test_assert_trusted_smoke_context.py``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "validation"
    / "assert_trusted_smoke_context.py"
)
_spec = importlib.util.spec_from_file_location("assert_trusted_smoke_context", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

_REPO = "rjmurillo/ai-agents"
_REF = "refs/heads/main"
_PR_REF = "refs/pull/7/merge"
_DISPATCH = ["--event-name", "workflow_dispatch", "--repository", _REPO, "--ref", _REF]
_PULL_REQUEST = ["--event-name", "pull_request", "--repository", _REPO, "--ref", _PR_REF]


@pytest.mark.parametrize(
    ("argv", "decision"),
    [
        (_DISPATCH, "true"),
        ([*_DISPATCH, "--expected-repo", _REPO, "--expected-ref", _REF], "true"),
        ([*_PULL_REQUEST, "--head-repository", _REPO], "true"),
        ([*_PULL_REQUEST, "--head-repository", "fork/ai-agents"], "false"),
        (_PULL_REQUEST, "false"),
    ],
    ids=["default-expected", "explicit-expected", "same-repo-pr", "fork-pr", "pr-no-head"],
)
def test_main_prints_the_decision_and_exits_zero(
    argv: list[str], decision: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code = gate.main(argv)

    assert code == gate.EXIT_OK
    assert capsys.readouterr().out.strip() == decision


def test_main_logs_a_trusted_decision_on_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    gate.main(_DISPATCH)

    assert "trusted-context gate" in capsys.readouterr().err


def test_main_does_not_echo_untrusted_values_on_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = ["--event-name", "workflow_dispatch", "--repository", "fork/ai-agents"]
    gate.main([*argv, "--ref", _REF, "--expected-repo", _REPO])

    err = capsys.readouterr().err
    assert "fork/ai-agents" not in err
    assert _REPO not in err


def test_main_exits_two_when_required_arg_missing() -> None:
    with pytest.raises(SystemExit) as exc:
        gate.main(["--event-name", "workflow_dispatch"])

    assert exc.value.code == gate.EXIT_USAGE
