"""Host and per-repetition load telemetry (REQ-027 D2 fix).

``HostProfile.load_average`` and ``HookRun.load_before``/``load_after`` are
what make two latency figures comparable: ci-scripts.md MUST-16 records
6.83s standalone against 92.87s in a real push, same job, same day, and
without load telemetry a reader cannot tell whether a slow capture is the
gate or a contended machine. ``os.getloadavg`` is POSIX-only (absent on
Windows) and can raise ``OSError`` even where present; both are guarded the
same way ``gate_latency_io.py``'s ``hasattr(os, "fchmod")`` guards a
Windows-absent stdlib API.
"""

from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

import pytest

from scripts.metrics import gate_latency_io as gl_io
from scripts.metrics import gate_latency_probe as gl_probe
from scripts.metrics.gate_latency_models import GateLatencyReport, HookRun, HostProfile
from tests.metrics.gate_latency_helpers import (
    REAL_CAPTURED_STDOUT,
    run_one_repetition,
    stub_lefthook,
)

# --- _load_average / _one_minute_load (unit) ----------------------------------


def test_positive_load_average_reads_os_getloadavg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "getloadavg", lambda: (1.5, 2.5, 3.5))
    assert gl_probe._load_average() == [1.5, 2.5, 3.5]


def test_negative_load_average_is_none_when_getloadavg_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows has no ``os.getloadavg`` attribute at all."""
    monkeypatch.delattr(os, "getloadavg", raising=False)
    assert gl_probe._load_average() is None


def test_negative_load_average_is_none_when_getloadavg_raises_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The load average can be unobtainable even where the attribute exists.

    ``os.getloadavg``'s own documented behavior is to raise ``OSError`` when
    the load average is unobtainable, distinct from the attribute being
    absent altogether.
    """

    def _raise() -> tuple[float, float, float]:
        raise OSError("load average unobtainable")

    monkeypatch.setattr(os, "getloadavg", _raise)
    assert gl_probe._load_average() is None


def test_edge_one_minute_load_is_none_when_load_average_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(os, "getloadavg", raising=False)
    assert gl_probe._one_minute_load() is None


def test_positive_one_minute_load_is_the_first_element(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(os, "getloadavg", lambda: (0.5, 1.0, 1.5))
    assert gl_probe._one_minute_load() == 0.5


# --- _host_profile: no traceback either way, on a platform with cpu_count ----


def test_negative_host_profile_load_average_is_none_when_attribute_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delattr(os, "getloadavg", raising=False)

    profile = gl_probe._host_profile()

    assert profile.load_average is None
    assert profile.cpu_count >= 1


def test_negative_host_profile_load_average_is_none_on_oserror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise() -> tuple[float, float, float]:
        raise OSError("unavailable")

    monkeypatch.setattr(os, "getloadavg", _raise)

    profile = gl_probe._host_profile()

    assert profile.load_average is None


def test_positive_host_profile_load_average_present_when_getloadavg_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "getloadavg", lambda: (0.1, 0.2, 0.3))

    profile = gl_probe._host_profile()

    assert profile.load_average == [0.1, 0.2, 0.3]


# --- HookRun.load_before / load_after (via _run_repetition) ------------------


def test_positive_run_repetition_samples_load_before_and_after(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    monkeypatch.setattr(os, "getloadavg", lambda: (2.0, 2.0, 2.0))
    stub_lefthook(monkeypatch, REAL_CAPTURED_STDOUT)

    run = run_one_repetition(repo)

    assert run.load_before == 2.0
    assert run.load_after == 2.0


def test_negative_run_repetition_load_is_none_when_unavailable(
    monkeypatch: pytest.MonkeyPatch, repo: Path
) -> None:
    monkeypatch.delattr(os, "getloadavg", raising=False)
    stub_lefthook(monkeypatch, REAL_CAPTURED_STDOUT)

    run = run_one_repetition(repo)

    assert run.load_before is None
    assert run.load_after is None


# --- JSON/markdown round trip --------------------------------------------------

_BASE_HOST = HostProfile(
    captured_at="2026-01-01T00:00:00+00:00",
    cpu_count=4,
    platform="test-platform",
    python_version="3.14.0",
)

_BASE_RUN = HookRun(
    repetition_index=0,
    exit_code=0,
    wall_clock_seconds=1.0,
    lefthook_reported_seconds=1.0,
    jobs_parsed=1,
    tree_mutated=False,
    unknown_status_count=0,
    samples=[],
    status="complete",
    load_before=1.0,
    load_after=1.2,
)

_BASE_REPORT = GateLatencyReport(
    commit_sha="deadbeef",
    captured_at="2026-01-01T00:00:00+00:00",
    command="cmd",
    hook="pre-commit",
    change_class="none",
    files=[],
    repetitions=1,
    host=_BASE_HOST,
    runs=[_BASE_RUN],
    summaries=[],
    declared_budget_seconds=None,
    percentile_note=None,
    stdin_ref_line_supplied=False,
    hook_args=[],
    forced=False,
    exclusions=[],
    run_status_counts={"complete": 1},
)


def test_positive_load_average_round_trips_through_json(tmp_path: Path) -> None:
    report = dataclasses.replace(
        _BASE_REPORT, host=dataclasses.replace(_BASE_HOST, load_average=[1.0, 2.0, 3.0])
    )
    path = tmp_path / "out.json"

    gl_io.write_json(report, path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["host"]["load_average"] == [1.0, 2.0, 3.0]
    assert data["runs"][0]["load_before"] == 1.0
    assert data["runs"][0]["load_after"] == 1.2


def test_positive_load_average_appears_in_markdown_with_per_cpu(tmp_path: Path) -> None:
    report = dataclasses.replace(
        _BASE_REPORT, host=dataclasses.replace(_BASE_HOST, load_average=[1.0, 2.0, 3.0])
    )
    path = tmp_path / "out.md"

    gl_io.write_markdown(report, path)

    body = path.read_text(encoding="utf-8")
    assert "1.00, 2.00, 3.00 (1/5/15 min)" in body
    assert "0.25 per CPU" in body  # 1.0 / 4 cpus


def test_negative_markdown_states_load_unavailable_when_none(tmp_path: Path) -> None:
    report = dataclasses.replace(
        _BASE_REPORT, host=dataclasses.replace(_BASE_HOST, load_average=None)
    )
    path = tmp_path / "out.md"

    gl_io.write_markdown(report, path)

    body = path.read_text(encoding="utf-8")
    assert "not available on this platform" in body


def test_positive_markdown_load_line_points_to_must_16(tmp_path: Path) -> None:
    path = tmp_path / "out.md"

    gl_io.write_markdown(_BASE_REPORT, path)

    body = path.read_text(encoding="utf-8")
    assert "MUST-16" in body
