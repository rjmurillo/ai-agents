"""pr_wait.py waits between polls through github_core.api.wait_for_pr_event."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

_helpers = sys.modules.get("_pr_wait_helpers")
if _helpers is None:
    _spec = importlib.util.spec_from_file_location(
        "_pr_wait_helpers", Path(__file__).with_name("_pr_wait_helpers.py")
    )
    assert _spec and _spec.loader
    _helpers = importlib.util.module_from_spec(_spec)
    sys.modules["_pr_wait_helpers"] = _helpers
    _spec.loader.exec_module(_helpers)
_gate = _helpers.gate_payload
_pr = _helpers.pr_payload
pw = _helpers.pw
# pr_wait.py binds github_core.api at import and reads its attributes at call time,
# so patching this module object (the lib copy on sys.path) applies.
gh_api = importlib.import_module("github_core.api")


def test_watch_waits_on_all_pr_events_between_polls(
    isolated_state: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gates = iter([_gate(PendingRequired=["ci"], OverallState="PENDING"), _gate()])
    monkeypatch.setattr(pw, "fetch_snapshot", lambda *_a: (_pr(mergeStateStatus="CLEAN"), "me"))
    monkeypatch.setattr(pw, "fetch_gate", lambda *_a: next(gates))
    waits: list[tuple[Any, ...]] = []

    def fake_wait(url: str, events: Any, seconds: float, **kw: float) -> str:
        waits.append((url, tuple(events), seconds, kw))
        return "event"

    monkeypatch.setattr(gh_api, "wait_for_pr_event", fake_wait)

    assert pw.main(["5", "--repo", "o/r", "--until", "green", "--interval", "45"]) == 0
    assert waits == [
        (
            "https://github.com/o/r/pull/5",
            gh_api.ALL_PR_EVENTS,
            45,
            {"min_seconds": pw.MIN_INTERVAL},
        )
    ]
