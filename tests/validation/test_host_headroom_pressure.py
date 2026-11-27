"""Linux CPU pressure signals, jittered polling, and bounded concurrency for host_headroom.

Covers:
- Jittered polling bounds and non-lockstep wakeups across waiters.
- Linux `/proc/pressure/cpu` (`some avg10`) and `/proc/stat` (`procs_running`)
  parsing and Ghostty D-state (`in_iowait` / `procs_blocked`) immunity.
- Fallback to `os.getloadavg()` when `/proc` files are unavailable.
- Bounded concurrency under multi-threaded slot contention and simultaneous
  timeout under persistent external load.
"""

from __future__ import annotations

import io
import math
import random
import sys
import threading
from pathlib import Path

import pytest

from scripts.validation import host_headroom
from tests.validation.test_host_headroom import _Clock, _foreign_hold, _midpoint, _settings

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the slot lock uses fcntl.flock, which Windows lacks"
)


# --- jittered polling ---


def test_polling_applies_jitter_within_bounds(tmp_path: Path) -> None:
    """AC: poll intervals are jittered within configured bounds and clamped to remaining."""
    settings = _settings(tmp_path, slots=1)
    low = host_headroom.POLL_SECONDS * (1.0 - host_headroom.POLL_JITTER_RATIO)
    high = host_headroom.POLL_SECONDS * (1.0 + host_headroom.POLL_JITTER_RATIO)
    clock_a = _Clock()
    clock_b = _Clock()
    with _foreign_hold(settings, 0):
        with pytest.raises(host_headroom.HeadroomTimeoutError):
            with host_headroom.heavy_stage_slot(
                "waiter-a",
                60.0,
                settings=settings,
                clock=clock_a,
                sleep=clock_a.sleep,
                load=lambda: 1.0,
                jitter=random.Random(1).uniform,
                stream=io.StringIO(),
            ):
                pass
        with pytest.raises(host_headroom.HeadroomTimeoutError):
            with host_headroom.heavy_stage_slot(
                "waiter-b",
                60.0,
                settings=settings,
                clock=clock_b,
                sleep=clock_b.sleep,
                load=lambda: 1.0,
                jitter=random.Random(2).uniform,
                stream=io.StringIO(),
            ):
                pass
    assert len(clock_a.sleeps) >= 5
    for delay in clock_a.sleeps[:-1]:
        assert low <= delay <= high
    assert 0 < clock_a.sleeps[-1] <= high
    assert clock_a.sleeps != clock_b.sleeps
    assert len(set(clock_a.sleeps[:-1])) > 1


@pytest.mark.parametrize("bad_delay", [0.0, -1.0, math.nan, math.inf])
def test_bad_jitter_return_falls_back_to_lower_bound(tmp_path: Path, bad_delay: float) -> None:
    settings = _settings(tmp_path, slots=1)
    low = host_headroom.POLL_SECONDS * (1.0 - host_headroom.POLL_JITTER_RATIO)
    clock = _Clock()
    with _foreign_hold(settings, 0):
        with pytest.raises(host_headroom.HeadroomTimeoutError):
            with host_headroom.heavy_stage_slot(
                "waiter",
                low * 2.0,
                settings=settings,
                clock=clock,
                sleep=clock.sleep,
                load=lambda: 1.0,
                jitter=lambda _lo, _hi: bad_delay,
                stream=io.StringIO(),
            ):
                pass
    assert clock.sleeps == [pytest.approx(low), pytest.approx(low)]


# --- Linux PSI / procs_running headroom signal and Ghostty D-state immunity ---


def test_cpu_psi_avg10_parses_proc_pressure_and_rejects_bad_input(tmp_path: Path) -> None:
    psi_file = tmp_path / "cpu"
    psi_file.write_text(
        "some avg10=12.75 avg60=4.50 avg300=1.20 total=999\n"
        "full avg10=0.00 avg60=0.00 avg300=0.00 total=0\n",
        encoding="utf-8",
    )
    assert host_headroom.cpu_psi_avg10(psi_file) == pytest.approx(12.75)

    for bad in (
        "some avg10=nan avg60=0.00\n",
        "some avg10=abc avg60=0.00\n",
        "some avg10=-1.0 avg60=0.00\n",
        "full avg10=1.00\n",
    ):
        psi_file.write_text(bad, encoding="utf-8")
        assert host_headroom.cpu_psi_avg10(psi_file) is None

    assert host_headroom.cpu_psi_avg10(tmp_path / "missing") is None


def test_procs_running_parses_proc_stat_and_ignores_procs_blocked(tmp_path: Path) -> None:
    stat_file = tmp_path / "stat"
    stat_file.write_text(
        "cpu  10 20 30 40\nprocs_running 4\nprocs_blocked 10\n",
        encoding="utf-8",
    )
    assert host_headroom.procs_running(stat_file) == 4

    for bad in (
        "cpu  10 20 30 40\nprocs_blocked 10\n",
        "procs_running two\n",
        "procs_running   \n",
    ):
        stat_file.write_text(bad, encoding="utf-8")
        assert host_headroom.procs_running(stat_file) is None

    assert host_headroom.procs_running(tmp_path / "missing") is None


def test_ghostty_d_state_threads_do_not_block_headroom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC: +10 Ghostty in_iowait (D-state) floor in loadavg does not falsely peg the gate."""
    psi_file = tmp_path / "pressure_cpu"
    psi_file.write_text(
        "some avg10=0.40 avg60=0.50 avg300=0.35 total=100\n",
        encoding="utf-8",
    )
    stat_file = tmp_path / "proc_stat"
    stat_file.write_text(
        "procs_running 6\nprocs_blocked 10\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(host_headroom, "_CPU_PSI_PATH", psi_file)
    monkeypatch.setattr(host_headroom, "_PROC_STAT_PATH", stat_file)
    monkeypatch.setattr(host_headroom, "load_average", lambda: 58.0)

    clock = _Clock()
    stream = io.StringIO()
    with host_headroom.heavy_stage_slot(
        "pre-pr-validation",
        300.0,
        settings=_settings(tmp_path, slots=3, max_load=48.0),
        clock=clock,
        sleep=clock.sleep,
        stream=stream,
    ) as grant:
        assert grant.slot == 0
        assert grant.headroom is True
        assert grant.waited == 0.0
    assert clock.sleeps == []
    assert stream.getvalue() == ""


def test_max_psi_zero_and_missing_psi_still_use_procs_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """max_psi=0 disables PSI while procs_running still guards CPU contention."""
    psi_file = tmp_path / "pressure_cpu"
    psi_file.write_text("some avg10=95.00\n", encoding="utf-8")
    stat_file = tmp_path / "proc_stat"
    stat_file.write_text("procs_running 4\nprocs_blocked 10\n", encoding="utf-8")
    monkeypatch.setattr(host_headroom, "_CPU_PSI_PATH", psi_file)
    monkeypatch.setattr(host_headroom, "_PROC_STAT_PATH", stat_file)
    monkeypatch.setattr(host_headroom, "load_average", lambda: 58.0)

    settings_no_psi = host_headroom.Settings(
        slots=2, max_load=48.0, slot_dir=tmp_path / "slots", max_psi=0.0
    )
    with host_headroom.heavy_stage_slot(
        "pytest", 10.0, settings=settings_no_psi, stream=io.StringIO()
    ) as grant:
        assert grant.headroom is True
        assert grant.slot == 0

    # Kernel without CONFIG_PSI (/proc/pressure/cpu absent) still uses /proc/stat.
    monkeypatch.setattr(host_headroom, "_CPU_PSI_PATH", tmp_path / "no-psi")
    with host_headroom.heavy_stage_slot(
        "pytest", 10.0, settings=_settings(tmp_path, slots=2, max_load=48.0), stream=io.StringIO()
    ) as grant:
        assert grant.headroom is True
        assert grant.slot == 0


def test_high_cpu_psi_waits_even_when_procs_running_is_low(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC: elevated Linux CPU PSI avg10 blocks until pressure drops."""
    psi_file = tmp_path / "pressure_cpu"
    stat_file = tmp_path / "proc_stat"
    stat_file.write_text("procs_running 3\nprocs_blocked 10\n", encoding="utf-8")
    psi_readings = iter([42.0, 30.0, 8.0])

    def write_next_psi(seconds: float) -> None:
        clock.sleep(seconds)
        psi_file.write_text(f"some avg10={next(psi_readings):.2f}\n", encoding="utf-8")

    psi_file.write_text(f"some avg10={next(psi_readings):.2f}\n", encoding="utf-8")
    monkeypatch.setattr(host_headroom, "_CPU_PSI_PATH", psi_file)
    monkeypatch.setattr(host_headroom, "_PROC_STAT_PATH", stat_file)

    clock = _Clock()
    stream = io.StringIO()
    with host_headroom.heavy_stage_slot(
        "pytest",
        600.0,
        settings=_settings(tmp_path, slots=2, max_load=48.0),
        clock=clock,
        sleep=write_next_psi,
        jitter=_midpoint,
        stream=stream,
    ) as grant:
        assert grant.slot == 0
        assert grant.headroom is True
        assert len(clock.sleeps) == 2
    assert "cpu psi avg10 42.0%" in stream.getvalue()


def test_high_procs_running_waits_even_when_psi_is_low(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC: high runnable tasks in /proc/stat block until runnable tasks drop below max_load."""
    psi_file = tmp_path / "pressure_cpu"
    psi_file.write_text("some avg10=1.00\n", encoding="utf-8")
    stat_file = tmp_path / "proc_stat"
    runnable_readings = iter([52, 10])

    def write_next_stat(seconds: float) -> None:
        clock.sleep(seconds)
        stat_file.write_text(
            f"procs_running {next(runnable_readings)}\nprocs_blocked 10\n",
            encoding="utf-8",
        )

    stat_file.write_text(
        f"procs_running {next(runnable_readings)}\nprocs_blocked 10\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(host_headroom, "_CPU_PSI_PATH", psi_file)
    monkeypatch.setattr(host_headroom, "_PROC_STAT_PATH", stat_file)

    clock = _Clock()
    stream = io.StringIO()
    with host_headroom.heavy_stage_slot(
        "semgrep",
        600.0,
        settings=_settings(tmp_path, slots=2, max_load=48.0),
        clock=clock,
        sleep=write_next_stat,
        jitter=_midpoint,
        stream=stream,
    ) as grant:
        assert grant.slot == 0
        assert grant.headroom is True
        assert len(clock.sleeps) == 1
    assert "runnable tasks 51" in stream.getvalue()


def test_single_cpu_idle_host_not_blocked_by_self_in_procs_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC: procs_running=1 (only the reading process) passes on a 1-CPU host (max_load=1.0)."""
    psi_file = tmp_path / "pressure_cpu"
    psi_file.write_text("some avg10=0.00\n", encoding="utf-8")
    stat_file = tmp_path / "proc_stat"
    stat_file.write_text("procs_running 1\nprocs_blocked 10\n", encoding="utf-8")
    monkeypatch.setattr(host_headroom, "_CPU_PSI_PATH", psi_file)
    monkeypatch.setattr(host_headroom, "_PROC_STAT_PATH", stat_file)

    clock = _Clock()
    with host_headroom.heavy_stage_slot(
        "pytest",
        60.0,
        settings=_settings(tmp_path, slots=1, max_load=1.0),
        clock=clock,
        sleep=clock.sleep,
        stream=io.StringIO(),
    ) as grant:
        assert grant.slot == 0
        assert grant.headroom is True
    assert clock.sleeps == []


def test_falls_back_to_load_average_when_proc_files_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC: platforms without /proc/pressure/cpu or /proc/stat fall back to load_average."""
    monkeypatch.setattr(host_headroom, "_CPU_PSI_PATH", tmp_path / "no-psi")
    monkeypatch.setattr(host_headroom, "_PROC_STAT_PATH", tmp_path / "no-stat")
    readings = iter([12.0, 2.0])
    monkeypatch.setattr(host_headroom, "load_average", lambda: next(readings))

    clock = _Clock()
    stream = io.StringIO()
    with host_headroom.heavy_stage_slot(
        "pytest",
        60.0,
        settings=_settings(tmp_path, slots=2, max_load=8.0),
        clock=clock,
        sleep=clock.sleep,
        jitter=_midpoint,
        stream=stream,
    ) as grant:
        assert grant.slot == 0
        assert grant.headroom is True
        assert len(clock.sleeps) == 1
    assert "load average 12.0" in stream.getvalue()


# --- bounded concurrency under contention ---


def test_bounded_concurrency_under_slot_contention_no_stampede(tmp_path: Path) -> None:
    """AC: concurrent contenders never exceed configured slots, even when waiters time out."""
    total = 6
    settings = _settings(tmp_path, slots=2, max_load=48.0)
    expected_timeouts = total - settings.slots
    gate = threading.Barrier(total)
    release_holders = threading.Event()
    state_lock = threading.Lock()
    active = 0
    peak_active = 0
    completed = 0
    timed_out = 0
    errors: list[BaseException] = []

    def worker() -> None:
        nonlocal active, peak_active, completed, timed_out
        try:
            gate.wait(timeout=5.0)
            with host_headroom.heavy_stage_slot(
                "pytest",
                0.05,
                settings=settings,
                load=lambda: 1.0,
                jitter=lambda _lo, _hi: 0.01,
                stream=io.StringIO(),
            ) as grant:
                assert grant.slot is not None
                with state_lock:
                    active += 1
                    peak_active = max(peak_active, active)
                assert release_holders.wait(timeout=5.0), "contenders never finished timing out"
                with state_lock:
                    active -= 1
                    completed += 1
        except host_headroom.HeadroomTimeoutError as exc:
            if exc.code != 3:
                with state_lock:
                    errors.append(AssertionError(f"expected exit 3, got {exc.code}"))
                release_holders.set()
                return
            with state_lock:
                timed_out += 1
                if timed_out == expected_timeouts:
                    release_holders.set()
        except BaseException as exc:  # pragma: no cover - surfaced to main thread
            with state_lock:
                errors.append(exc)
            release_holders.set()

    threads = [threading.Thread(target=worker) for _ in range(total)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10.0)
        assert not thread.is_alive()

    assert errors == []
    assert peak_active <= settings.slots
    assert completed == settings.slots
    assert timed_out == expected_timeouts


def test_simultaneous_timeout_under_high_load_caps_at_slots(tmp_path: Path) -> None:
    """AC: waiters timing out together under external high load still cap execution at slots."""
    total = 5
    settings = _settings(tmp_path, slots=2, max_load=8.0)
    expected_timeouts = total - settings.slots
    gate = threading.Barrier(total)
    hold_inside = threading.Event()
    state_lock = threading.Lock()
    active = 0
    peak_active = 0
    entered: list[int | None] = []
    timed_out = 0
    errors: list[BaseException] = []

    def worker() -> None:
        nonlocal active, peak_active, timed_out
        try:
            gate.wait(timeout=5.0)
            with host_headroom.heavy_stage_slot(
                "pre-pr-validation",
                0.0,
                settings=settings,
                load=lambda: 99.0,
                stream=io.StringIO(),
            ) as grant:
                with state_lock:
                    active += 1
                    peak_active = max(peak_active, active)
                    entered.append(grant.slot)
                assert hold_inside.wait(timeout=5.0), "contenders never finished timing out"
                with state_lock:
                    active -= 1
        except host_headroom.HeadroomTimeoutError as exc:
            if exc.code != 3:
                with state_lock:
                    errors.append(AssertionError(f"expected exit 3, got {exc.code}"))
                hold_inside.set()
                return
            with state_lock:
                timed_out += 1
                if timed_out == expected_timeouts:
                    hold_inside.set()
        except BaseException as exc:  # pragma: no cover - surfaced to main thread
            with state_lock:
                errors.append(exc)
            hold_inside.set()

    threads = [threading.Thread(target=worker) for _ in range(total)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10.0)
        assert not thread.is_alive()

    assert errors == []
    assert peak_active <= settings.slots
    assert len(entered) == settings.slots
    assert all(slot is not None for slot in entered)
    assert timed_out == expected_timeouts
