"""Host-wide headroom for heavy pre-push stages (issue #6609).

About 16 agents pushed from one host at once. Clean pushes failed on a testmon
SQLite lock, the 180s pytest budget, and a semgrep-core target failure, then
passed unchanged once the host was quiet. `host_headroom` caps how many heavy
stages run at once and waits for load to drop before a stage starts its clock.

Coverage:

- positive: a free slot and low load grant at once, with no wait and no output.
- negative: a full slot set or high load makes the stage wait, and an exhausted
  wait runs the stage anyway (never skips it) with a warning naming load.
- edge: bad settings are config errors, a slot frees on release, a zero budget
  never sleeps, an unknown load never blocks, and the note names the load.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from scripts.validation import host_headroom

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the slot lock uses fcntl.flock, which Windows lacks"
)


class _Clock:
    """A fake monotonic clock that `sleep` advances, so no test really waits."""

    def __init__(self) -> None:
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _settings(tmp_path: Path, *, slots: int = 2, max_load: float = 8.0) -> host_headroom.Settings:
    return host_headroom.Settings(slots=slots, max_load=max_load, slot_dir=tmp_path / "slots")


def test_free_slot_and_low_load_grant_at_once(tmp_path: Path) -> None:
    clock = _Clock()
    stream = io.StringIO()
    with host_headroom.heavy_stage_slot(
        "pytest",
        60,
        settings=_settings(tmp_path),
        clock=clock,
        sleep=clock.sleep,
        load=lambda: 1.0,
        stream=stream,
    ) as grant:
        assert grant.slot == 0
        assert grant.headroom is True
        assert grant.waited == 0
    assert clock.sleeps == []
    assert stream.getvalue() == ""


def test_full_slots_wait_then_run_anyway_with_a_load_warning(tmp_path: Path) -> None:
    settings = _settings(tmp_path, slots=1)
    clock = _Clock()
    stream = io.StringIO()
    with host_headroom.heavy_stage_slot(
        "other", 0, settings=settings, load=lambda: 1.0, stream=io.StringIO()
    ) as held:
        assert held.slot == 0
        with host_headroom.heavy_stage_slot(
            "pytest",
            30,
            settings=settings,
            clock=clock,
            sleep=clock.sleep,
            load=lambda: 1.0,
            stream=stream,
        ) as grant:
            assert grant.slot is None
            assert grant.headroom is False
            assert grant.waited >= 30
    assert sum(clock.sleeps) >= 30
    output = stream.getvalue()
    assert "waiting" in output
    assert "running pytest anyway" in output
    assert "load" in output


def test_a_released_slot_is_free_again(tmp_path: Path) -> None:
    settings = _settings(tmp_path, slots=1)
    for _ in range(2):
        with host_headroom.heavy_stage_slot(
            "pytest", 0, settings=settings, load=lambda: 1.0, stream=io.StringIO()
        ) as grant:
            assert grant.slot == 0


def test_high_load_waits_until_it_drops(tmp_path: Path) -> None:
    clock = _Clock()
    readings = iter([12.0, 11.0, 3.0])
    stream = io.StringIO()
    with host_headroom.heavy_stage_slot(
        "semgrep",
        600,
        settings=_settings(tmp_path),
        clock=clock,
        sleep=clock.sleep,
        load=lambda: next(readings),
        stream=stream,
    ) as grant:
        assert grant.headroom is True
        assert grant.slot == 0
        assert grant.waited == pytest.approx(2 * host_headroom.POLL_SECONDS)
    output = stream.getvalue()
    assert "load average 12.0" in output
    assert "8.0" in output


def test_zero_wait_budget_never_sleeps(tmp_path: Path) -> None:
    clock = _Clock()
    stream = io.StringIO()
    with host_headroom.heavy_stage_slot(
        "pytest",
        0,
        settings=_settings(tmp_path),
        clock=clock,
        sleep=clock.sleep,
        load=lambda: 50.0,
        stream=stream,
    ) as grant:
        assert grant.headroom is False
    assert clock.sleeps == []
    assert "running pytest anyway" in stream.getvalue()


def test_unknown_load_never_blocks(tmp_path: Path) -> None:
    with host_headroom.heavy_stage_slot(
        "pytest", 60, settings=_settings(tmp_path), load=lambda: None, stream=io.StringIO()
    ) as grant:
        assert grant.headroom is True


def test_disabled_gate_grants_without_a_slot(tmp_path: Path) -> None:
    settings = _settings(tmp_path, slots=0, max_load=0)
    with host_headroom.heavy_stage_slot(
        "pytest", 60, settings=settings, load=lambda: 99.0, stream=io.StringIO()
    ) as grant:
        assert grant.slot is None
        assert grant.headroom is True
    assert not settings.slot_dir.exists()


def test_unwritable_slot_dir_does_not_block_the_stage(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a directory", encoding="utf-8")
    settings = host_headroom.Settings(slots=2, max_load=8.0, slot_dir=blocker / "slots")
    stream = io.StringIO()
    with host_headroom.heavy_stage_slot(
        "pytest", 60, settings=settings, load=lambda: 1.0, stream=stream
    ) as grant:
        assert grant.slot is None
    assert "WARNING" in stream.getvalue()


def test_read_settings_defaults(tmp_path: Path) -> None:
    settings = host_headroom.read_settings({"HOME": str(tmp_path)})
    assert settings.slots == host_headroom.DEFAULT_SLOTS
    assert settings.max_load == host_headroom.default_max_load()
    assert settings.slot_dir == tmp_path / ".cache" / "ai-agents" / "heavy-stage-slots"


def test_read_settings_overrides(tmp_path: Path) -> None:
    settings = host_headroom.read_settings(
        {
            host_headroom.SLOTS_ENV: "4",
            host_headroom.MAX_LOAD_ENV: "5.5",
            host_headroom.SLOT_DIR_ENV: str(tmp_path),
        }
    )
    assert settings == host_headroom.Settings(slots=4, max_load=5.5, slot_dir=tmp_path)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        (host_headroom.SLOTS_ENV, "-1"),
        (host_headroom.SLOTS_ENV, "three"),
        (host_headroom.MAX_LOAD_ENV, "-2"),
        (host_headroom.MAX_LOAD_ENV, "nan"),
        (host_headroom.MAX_LOAD_ENV, "high"),
    ],
)
def test_bad_settings_are_config_errors(name: str, value: str) -> None:
    with pytest.raises(ValueError, match=name):
        host_headroom.read_settings({name: value})


def test_load_note_blames_load_above_the_threshold() -> None:
    note = host_headroom.load_note("pytest", load=lambda: 12.5, max_load=8.0, cpus=48)
    assert "12.5" in note
    assert "48 CPUs" in note
    assert "likely load" in note


def test_load_note_clears_load_below_the_threshold() -> None:
    note = host_headroom.load_note("pytest", load=lambda: 2.0, max_load=8.0, cpus=48)
    assert "2.0" in note
    assert "not the likely cause" in note


def test_load_note_says_when_load_is_unknown() -> None:
    note = host_headroom.load_note("semgrep", load=lambda: None, max_load=8.0, cpus=4)
    assert "unavailable" in note


# --- review round 1: a slot bounds concurrency even when load is high ---


def test_high_load_still_takes_a_free_slot(tmp_path: Path) -> None:
    """A stage that waits on load holds a slot, so an overdue stage counts toward the cap."""
    clock = _Clock()
    stream = io.StringIO()
    with host_headroom.heavy_stage_slot(
        "pytest",
        30,
        settings=_settings(tmp_path, slots=1),
        clock=clock,
        sleep=clock.sleep,
        load=lambda: 50.0,
        stream=stream,
    ) as grant:
        assert grant.slot == 0
        assert grant.headroom is False
    assert "running pytest anyway" in stream.getvalue()


def test_an_overdue_stage_keeps_later_stages_out_of_its_slot(tmp_path: Path) -> None:
    settings = _settings(tmp_path, slots=1)
    with host_headroom.heavy_stage_slot(
        "first", 0, settings=settings, load=lambda: 50.0, stream=io.StringIO()
    ) as first:
        assert first.slot == 0
        with host_headroom.heavy_stage_slot(
            "second", 0, settings=settings, load=lambda: 1.0, stream=io.StringIO()
        ) as second:
            assert second.slot is None
            assert second.headroom is False


def test_a_slot_is_held_while_the_stage_waits_for_load(tmp_path: Path) -> None:
    settings = _settings(tmp_path, slots=1)
    clock = _Clock()
    seen: list[int | None] = []
    readings = iter([20.0, 20.0, 2.0])

    def load() -> float:
        # A rival stage probes the slot while this one waits on load.
        with host_headroom.heavy_stage_slot(
            "rival", 0, settings=settings, load=lambda: 1.0, stream=io.StringIO()
        ) as rival:
            seen.append(rival.slot)
        return next(readings)

    with host_headroom.heavy_stage_slot(
        "pytest",
        60,
        settings=settings,
        clock=clock,
        sleep=clock.sleep,
        load=load,
        stream=io.StringIO(),
    ) as grant:
        assert grant.slot == 0
        assert grant.headroom is True
    assert seen[1:] == [None] * (len(seen) - 1)


# --- review round 1: the default load threshold scales with the CPU count ---


@pytest.mark.parametrize("cpus", [4, 48])
def test_default_max_load_scales_with_cpus(tmp_path: Path, cpus: int) -> None:
    settings = host_headroom.read_settings({"HOME": str(tmp_path)}, cpus=cpus)
    assert settings.max_load == pytest.approx(cpus * host_headroom.DEFAULT_MAX_LOAD_PER_CPU)


def test_an_explicit_max_load_ignores_the_cpu_count(tmp_path: Path) -> None:
    settings = host_headroom.read_settings({host_headroom.MAX_LOAD_ENV: "5"}, cpus=48)
    assert settings.max_load == 5.0


def test_load_note_default_threshold_uses_the_cpu_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(host_headroom.MAX_LOAD_ENV, raising=False)
    busy = host_headroom.load_note("pytest", load=lambda: 12.0, cpus=4)
    quiet = host_headroom.load_note("pytest", load=lambda: 12.0, cpus=48)
    assert "likely load" in busy
    assert "not the likely cause" in quiet
