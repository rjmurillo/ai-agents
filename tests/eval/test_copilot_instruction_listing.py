"""Tests for the `copilot instruction list --json` preflight (REQ-034 AC4-AC6).

Each case feeds `_verify_copilot_instruction_listing` one listing through a
mock runner, so no real `copilot` binary runs.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from tests.eval._runtime_parity_test_support import (
    FIXTURES,
    parity,
    runtime_harness,
    runtime_parity,
)

INSTALLED = {".github/instructions/voice.instructions.md": b"x"}
VOICE = {"sourcePath": ".github/instructions/voice.instructions.md"}


def _verify(tmp_path: Path, runner: mock.Mock) -> tuple[object, object]:
    fixture = dataclasses.replace(
        runtime_parity.load_fixtures(FIXTURES)[0], instructions=(".claude/rules/voice.md",)
    )
    return parity._verify_copilot_instruction_listing(
        fixture, "copilot", tmp_path, runner, 30, INSTALLED
    )


def _answer(stdout: str, returncode: int = 0) -> mock.Mock:
    return mock.Mock(return_value=subprocess.CompletedProcess([], returncode, stdout, ""))


def test_listing_matching_the_installed_set_returns_it(tmp_path: Path) -> None:
    runner = _answer(json.dumps([VOICE]))

    listing, failure = _verify(tmp_path, runner)

    assert failure is None
    assert listing == [VOICE]
    # The listing must see the same workspace and environment as the model run.
    kwargs = runner.call_args.kwargs
    assert kwargs["cwd"] == tmp_path
    assert kwargs["env"] == runtime_harness.runtime_env(tmp_path, "copilot")


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ([VOICE, {"sourcePath": ".github/copilot-instructions.md"}], "extra="),
        ([], "missing="),
        # An entry the parser cannot read could hide a leaked source.
        ([VOICE, {"path": "AGENTS.md"}], "without a string sourcePath"),
        ([VOICE, {"sourcePath": 7}], "without a string sourcePath"),
        ([VOICE, "AGENTS.md"], "without a string sourcePath"),
    ],
    ids=["extra", "missing", "other-key", "non-string", "non-dict"],
)
def test_listing_that_differs_from_the_installed_set_is_a_config_error(
    tmp_path: Path, entries: list[object], message: str
) -> None:
    with pytest.raises(parity.ParityConfigError, match=message):
        _verify(tmp_path, _answer(json.dumps(entries)))


@pytest.mark.parametrize(
    ("runner", "message"),
    [
        (_answer("", returncode=1), "unavailable: exited 1"),
        (_answer("not json"), "unparsable JSON"),
        (_answer(json.dumps({"sourcePath": "x"})), "not an array"),
        (mock.Mock(side_effect=subprocess.TimeoutExpired(["copilot"], 30)), "timed out"),
    ],
    ids=["nonzero-exit", "bad-json", "non-array", "timeout"],
)
def test_listing_that_cannot_run_or_parse_is_a_failure_record(
    tmp_path: Path, runner: mock.Mock, message: str
) -> None:
    listing, failure = _verify(tmp_path, runner)

    assert listing is None
    assert isinstance(failure, dict)
    assert message in failure["error"]
    assert failure["passed"] is False
