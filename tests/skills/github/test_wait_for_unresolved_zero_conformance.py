"""Conformance of wait_for_unresolved_zero.py to get_unresolved_review_threads.py (#5399).

The wrapper reads two fields of the underlying script's JSON output. These
tests run the real underlying ``main`` and pass its stdout through the
wrapper's reader, so renaming or retyping either field fails here instead of
leaving a copied contract in the wrapper docstring stale.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any
from unittest import mock
from unittest.mock import patch

import pytest

from scripts.github_core.api import RepoInfo

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_DIR = REPO_ROOT / ".claude" / "skills" / "github" / "scripts" / "pr"
sys.path.insert(0, str(SCRIPT_DIR))

import wait_for_unresolved_zero as wfz


def _load_underlying() -> Any:
    name = "get_unresolved_review_threads"
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


underlying = _load_underlying()


def _underlying_stdout(nodes: list[dict], *, complete: bool, capsys: pytest.CaptureFixture) -> str:
    """Run the real underlying main with a stubbed fetch and return its stdout."""
    with (
        patch.object(underlying, "assert_gh_authenticated"),
        patch.object(underlying, "resolve_repo_params", return_value=RepoInfo("o", "r")),
        patch.object(
            underlying, "fetch_unresolved_threads_paginated", return_value=(nodes, complete)
        ),
    ):
        assert underlying.main(["--pull-request", "42"]) == 0
    return capsys.readouterr().out


def _read_through_wrapper(stdout: str) -> tuple[int, bool, int]:
    def runner(*_args: Any, **_kwargs: Any) -> Any:
        return mock.Mock(returncode=0, stdout=stdout, stderr="")

    return wfz._invoke_underlying(Path("/unused.py"), 42, "", "", runner=runner)


@pytest.mark.parametrize(
    ("nodes", "complete", "expected"),
    [
        ([], True, (0, True, 0)),
        ([{"id": "t1", "isResolved": False}], True, (1, True, 0)),
        ([], False, (0, False, 0)),
    ],
)
def test_wrapper_reads_underlying_output_conformance(
    nodes: list[dict],
    complete: bool,
    expected: tuple[int, bool, int],
    capsys: pytest.CaptureFixture,
) -> None:
    stdout = _underlying_stdout(nodes, complete=complete, capsys=capsys)

    # The wrapper coerces both fields, so pin the raw types the owner emits.
    payload = json.loads(stdout)
    assert type(payload["unresolved_count"]) is int
    assert type(payload["fetched_pages_complete"]) is bool
    assert _read_through_wrapper(stdout) == expected


def test_renamed_field_is_caught_by_the_wrapper_reader(capsys: pytest.CaptureFixture) -> None:
    """Negative control: a payload that renames a field reads as the failure sentinel."""
    payload = json.loads(_underlying_stdout([], complete=True, capsys=capsys))
    payload["unresolved_total"] = payload.pop("unresolved_count")

    count, complete, _ = _read_through_wrapper(json.dumps(payload))

    assert count == -1
    assert complete is True
