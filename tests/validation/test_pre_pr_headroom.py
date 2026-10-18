"""pre-pr-validation waits for host headroom in the hook only (issue #6725).

- positive: in the hook context a slot is taken with the bounded wait, and the
  run happens inside it.
- negative: a direct run, CI, and a container take no slot and wait zero.
- edge: an expired wait still runs the gates; the lefthook timeout is the run
  budget plus the wait.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts.validation import host_headroom, pre_pr, pre_pr_headroom

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv(pre_pr_headroom.FAST_STAGE_RAN_ENV, raising=False)
    monkeypatch.setattr(pre_pr_headroom, "_in_container", lambda: False)


def _recording_slot(events: list[Any], *, headroom: bool = True) -> Any:
    @contextmanager
    def fake(stage: str, wait_budget: float, **_kwargs: Any) -> Iterator[host_headroom.Grant]:
        events.append(("enter", stage, wait_budget))
        try:
            yield host_headroom.Grant(slot=0, headroom=headroom, waited=0.0)
        finally:
            events.append(("exit", stage))

    return fake


def _hook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(pre_pr_headroom.FAST_STAGE_RAN_ENV, "1")


def test_hook_context_takes_a_slot_with_the_bounded_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _hook(monkeypatch)
    events: list[Any] = []
    monkeypatch.setattr(pre_pr_headroom, "_heavy_stage_slot", _recording_slot(events))
    with pre_pr_headroom.headroom_stage() as waited:
        events.append(("run",))
    assert waited is True
    assert events == [
        ("enter", "pre-pr-validation", pre_pr_headroom.HEADROOM_WAIT_SECONDS),
        ("run",),
        ("exit", "pre-pr-validation"),
    ]


def test_wait_restarts_the_outer_cap_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    _hook(monkeypatch)
    gate = pre_pr_headroom.check_generated_staleness
    monkeypatch.setattr(gate, "_PROCESS_START", 0.0)
    monkeypatch.setattr(pre_pr_headroom, "_heavy_stage_slot", _recording_slot([]))
    with pre_pr_headroom.headroom_stage():
        assert gate._PROCESS_START > 0.0


def test_direct_run_takes_no_slot_and_waits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[Any] = []
    monkeypatch.setattr(pre_pr_headroom, "_heavy_stage_slot", _recording_slot(events))
    assert pre_pr_headroom.wait_seconds() == 0
    with pre_pr_headroom.headroom_stage() as waited:
        pass
    assert waited is False
    assert events == []


@pytest.mark.parametrize("off", ["ci", "container"])
def test_ci_and_container_take_no_slot(monkeypatch: pytest.MonkeyPatch, off: str) -> None:
    _hook(monkeypatch)
    events: list[Any] = []
    monkeypatch.setattr(pre_pr_headroom, "_heavy_stage_slot", _recording_slot(events))
    if off == "ci":
        monkeypatch.setenv("CI", "true")
    else:
        monkeypatch.setattr(pre_pr_headroom, "_in_container", lambda: True)
    assert pre_pr_headroom.wait_seconds() == 0
    with pre_pr_headroom.headroom_stage():
        pass
    assert events == []


def test_bad_headroom_setting_still_runs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _hook(monkeypatch)
    monkeypatch.setenv(pre_pr_headroom.host_headroom.SLOTS_ENV, "not-a-number")
    ran: list[bool] = []
    with pre_pr_headroom.headroom_stage() as waited:
        ran.append(True)
    assert ran == [True]
    assert waited is False
    assert "running without a wait" in capsys.readouterr().err


def test_expired_wait_still_runs_and_names_load(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The real slot, a saturated host, and a zero-length wait: the body runs."""
    _hook(monkeypatch)
    monkeypatch.setattr(pre_pr_headroom, "HEADROOM_WAIT_SECONDS", 0.001)
    # pre_pr_headroom imports host_headroom by bare name, a different module
    # object from the package import above, so patch through it.
    real = pre_pr_headroom.host_headroom
    settings = real.Settings(slots=0, max_load=1.0, slot_dir=Path("."))
    monkeypatch.setattr(real, "read_settings", lambda *_a, **_k: settings)
    monkeypatch.setattr(
        pre_pr_headroom,
        "_heavy_stage_slot",
        lambda stage, wait, **kw: real.heavy_stage_slot(
            stage, wait, load=lambda: 999.0, sleep=lambda _s: None, **kw
        ),
    )
    ran: list[bool] = []
    with pre_pr_headroom.headroom_stage():
        ran.append(True)
    assert ran == [True]
    err = capsys.readouterr().err
    assert "running pre-pr-validation anyway" in err
    assert "likely load" in err


def test_main_runs_the_gates_inside_the_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    # pre_pr imports the module by bare name; patch that instance.
    bare = sys.modules["pre_pr_headroom"]
    events: list[Any] = []
    monkeypatch.setattr(bare, "_heavy_stage_slot", _recording_slot(events))
    monkeypatch.setattr(bare, "_in_container", lambda: False)
    monkeypatch.setenv(bare.FAST_STAGE_RAN_ENV, "1")
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setattr(pre_pr, "_main", lambda argv: events.append(("run", argv)) or 7)
    assert pre_pr.main(["--quick"]) == 7
    assert events[0][0] == "enter"
    assert events[1] == ("run", ["--quick"])
    assert events[2] == ("exit", "pre-pr-validation")


def test_lefthook_timeout_is_the_run_budget_plus_the_wait() -> None:
    config = yaml.safe_load((_REPO_ROOT / "lefthook.yml").read_text(encoding="utf-8"))

    def walk(jobs: list[dict[str, Any]]) -> dict[str, Any] | None:
        for job in jobs:
            if job.get("name") == "pre-pr-validation":
                return job
            nested = job.get("group", {}).get("jobs")
            if nested and (found := walk(nested)):
                return found
        return None

    job = walk(config["pre-push"]["jobs"])
    assert job is not None
    timeout = str(job["timeout"])
    assert timeout.endswith("m")
    budget = float(job["env"]["PRE_PR_OUTER_CAP_SECONDS"])
    assert int(timeout[:-1]) * 60 == budget + pre_pr_headroom.HEADROOM_WAIT_SECONDS
