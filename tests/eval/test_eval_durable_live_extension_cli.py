"""CLI tests for the extension corpus and first-repeat flags (issue #5768). No claude is started."""

from __future__ import annotations

import json
from typing import Any

import eval_routing_corpus as corpus_cli
import pytest

from tests.eval._durable_live_test_support import cli
from tests.eval._routing_integration_test_support import EXTENSION_CORPUS, TASKS


def _plan(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    plan: dict[str, Any] = json.loads(capsys.readouterr().out)
    return plan


def test_dry_run_with_the_extension_corpus_plans_eight_tasks(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = cli.main(["--extension-corpus", str(EXTENSION_CORPUS), "--repeats", "3"])

    plan = _plan(capsys)
    assert code == cli.EXIT_OK
    assert len(plan["tasks"]) == 8 and set(TASKS) <= set(plan["tasks"])
    assert plan["max_invocations"] == 8 * 2 * 3 * 2
    assert plan["first_repeat"] == 0


def test_the_extension_corpus_is_opt_in(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == cli.EXIT_OK

    assert not set(TASKS) & set(_plan(capsys)["tasks"])


def test_tasks_can_select_an_extension_scenario(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["--extension-corpus", str(EXTENSION_CORPUS), "--tasks", TASKS[0]])

    assert code == cli.EXIT_OK and _plan(capsys)["tasks"] == [TASKS[0]]


def test_the_routing_corpus_as_an_extension_is_a_config_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tests.eval._routing_corpus_test_support import REAL_CORPUS

    code = cli.main(["--extension-corpus", str(REAL_CORPUS)])

    assert code == cli.EXIT_CONFIG
    assert "only post_integration_regression" in capsys.readouterr().err


def test_a_missing_extension_directory_is_a_config_error() -> None:
    assert cli.main(["--extension-corpus", "no-such-dir"]) == cli.EXIT_CONFIG


def test_negative_first_repeat_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--first-repeat", "-1"]) == cli.EXIT_CONFIG
    assert "--first-repeat" in capsys.readouterr().err


def test_first_repeat_appears_in_the_plan(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--first-repeat", "2"]) == cli.EXIT_OK

    assert _plan(capsys)["first_repeat"] == 2


def test_the_routing_corpus_cli_verifies_the_extension_corpus(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = corpus_cli.main(["--corpus", str(EXTENSION_CORPUS), "--extension"])

    report = _plan(capsys)
    assert code == corpus_cli.EXIT_OK
    assert report["examined"] == 2 and report["failed"] == 0


def test_the_routing_corpus_cli_refuses_the_extension_corpus_without_the_flag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = corpus_cli.main(["--corpus", str(EXTENSION_CORPUS)])

    assert code == corpus_cli.EXIT_CORPUS_INVALID
    assert "extension corpus" in capsys.readouterr().err
