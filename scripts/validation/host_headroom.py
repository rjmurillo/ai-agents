"""Host-wide headroom for heavy pre-push stages (issue #6609).

About 16 agents ran pre-push on one host at the same time. Clean pushes failed
on a testmon SQLite lock, on the 180s pytest budget, and on a semgrep-core
target failure. The same pushes passed unchanged once load fell. The hook
reported each failure as a defect in the diff, so an agent could not tell load
from a broken change.

This module caps how many heavy stages run on one host at once. A stage takes
one of ``slots`` lock files before it starts its clock. It also waits for the
1-minute load average to fall below ``max_load`` before it takes a slot, so
waiting stages do not all start the moment load dips.

The wait is bounded by the caller, which knows its lefthook cap. When the wait
runs out, the stage still runs: a skipped gate looks green and proves nothing.
The warning it prints names load, so a timeout that follows reads as load.

Slots are ``fcntl.flock`` locks. The kernel drops a lock when its holder dies,
so a crashed push never leaks a slot. The slot files live under the user's
cache directory, not ``/tmp``, for the reason ``push-lock.md`` gives: a ``/tmp``
wipe splits one lock name into two inodes. This is a concurrency cap across
branches. It does not replace the per-branch push lock, which serializes one
branch's ref update.

Where ``fcntl`` is missing (Windows), or the slot directory cannot be created,
the stage runs without a slot. A cap that can block the push it protects is
worse than no cap.
"""

from __future__ import annotations

import math
import os
import sys
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

_HAS_FLOCK = sys.platform != "win32"
if _HAS_FLOCK:
    import fcntl

SLOTS_ENV = "AI_AGENTS_HEAVY_STAGE_SLOTS"
MAX_LOAD_ENV = "AI_AGENTS_HEAVY_STAGE_MAX_LOAD"
SLOT_DIR_ENV = "AI_AGENTS_HEAVY_STAGE_SLOT_DIR"
# Issue #6609 asks for 3 to 4 slots. Three is the figure the operator memory
# `ci-concurrent-pre-push-gates-must-wait-not-skip` uses for heavy pushes today.
DEFAULT_SLOTS = 3
# Observed on a 48-thread host: pushes failed at load average 10 to 13 and
# passed at about 2. The operator's standing rule waits for load below 8.
DEFAULT_MAX_LOAD = 8.0
POLL_SECONDS = 5.0


@dataclass(frozen=True)
class Settings:
    """How many heavy stages may run at once, and the load they wait below.

    ``slots`` of 0 turns the slot cap off. ``max_load`` of 0 turns the load
    wait off.
    """

    slots: int
    max_load: float
    slot_dir: Path


@dataclass(frozen=True)
class Grant:
    """What one stage got: a slot index (or none), and whether it had headroom."""

    slot: int | None
    headroom: bool
    waited: float


def _default_slot_dir(env: Mapping[str, str]) -> Path:
    cache = env.get("XDG_CACHE_HOME")
    if cache:
        return Path(cache) / "ai-agents" / "heavy-stage-slots"
    home = env.get("HOME") or str(Path.home())
    return Path(home) / ".cache" / "ai-agents" / "heavy-stage-slots"


def read_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Read the gate's settings from ``env``.

    Raises:
        ValueError: a setting is not a nonnegative number. The message names
            the variable.
    """
    source = os.environ if env is None else env
    raw_slots = source.get(SLOTS_ENV, "").strip()
    if not raw_slots:
        slots = DEFAULT_SLOTS
    elif raw_slots.isdecimal():
        slots = int(raw_slots)
    else:
        raise ValueError(f"{SLOTS_ENV} must be a nonnegative integer, got {raw_slots!r}")
    raw_load = source.get(MAX_LOAD_ENV, "").strip()
    if not raw_load:
        max_load = DEFAULT_MAX_LOAD
    else:
        try:
            max_load = float(raw_load)
        except ValueError:
            max_load = -1.0
        if not math.isfinite(max_load) or max_load < 0:
            raise ValueError(f"{MAX_LOAD_ENV} must be a nonnegative number, got {raw_load!r}")
    raw_dir = source.get(SLOT_DIR_ENV, "").strip()
    slot_dir = Path(raw_dir) if raw_dir else _default_slot_dir(source)
    return Settings(slots=slots, max_load=max_load, slot_dir=slot_dir)


def load_average() -> float | None:
    """The 1-minute load average, or None where the platform has none."""
    if not hasattr(os, "getloadavg"):
        return None
    try:
        return float(os.getloadavg()[0])
    except OSError:
        return None


def _configured_max_load() -> float:
    try:
        return read_settings().max_load
    except ValueError:
        return DEFAULT_MAX_LOAD


def load_note(
    stage: str,
    *,
    load: Callable[[], float | None] | None = None,
    max_load: float | None = None,
    cpus: int | None = None,
) -> str:
    """One line that says whether host load likely caused a stage failure."""
    threshold = _configured_max_load() if max_load is None else max_load
    count = cpus if cpus is not None else (os.cpu_count() or 1)
    current = (load_average if load is None else load)()
    if current is None:
        return (
            f"NOTE: {stage}: host load average is unavailable here, so load "
            "cannot be ruled in or out as the cause."
        )
    measured = f"host load average is {current:.1f} on {count} CPUs"
    if threshold > 0 and current >= threshold:
        return (
            f"NOTE: {stage}: {measured}, at or above the {threshold:.1f} headroom "
            "threshold. This failure is likely load from other work on the "
            "host, not this diff. Retry when load drops."
        )
    return f"NOTE: {stage}: {measured}, so host load is not the likely cause."


def _try_slot(settings: Settings) -> tuple[int, int] | None:
    """Lock the first free slot file; return (index, fd), or None when all are held.

    Raises:
        OSError: the slot directory or a slot file cannot be opened.
    """
    settings.slot_dir.mkdir(parents=True, exist_ok=True)
    for index in range(settings.slots):
        path = settings.slot_dir / f"slot-{index}.lock"
        fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            continue
        except OSError:
            os.close(fd)
            raise
        return index, fd
    return None


def _release(fd: int) -> None:
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


@contextmanager
def heavy_stage_slot(
    stage: str,
    wait_budget: float,
    *,
    settings: Settings | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    load: Callable[[], float | None] = load_average,
    stream: TextIO | None = None,
) -> Iterator[Grant]:
    """Hold a heavy-stage slot for the ``with`` body, waiting up to ``wait_budget``.

    The body always runs. ``Grant.headroom`` is False when the wait ran out,
    and a warning naming load was printed.

    Raises:
        ValueError: ``settings`` is None and the environment holds a bad value.
    """
    out = sys.stderr if stream is None else stream
    config = read_settings() if settings is None else settings
    use_slots = config.slots > 0 and _HAS_FLOCK
    start = clock()
    announced = False
    fd: int | None = None
    index: int | None = None
    headroom = False
    while True:
        current = load()
        load_ok = config.max_load <= 0 or current is None or current < config.max_load
        if load_ok:
            if not use_slots:
                headroom = True
                break
            try:
                taken = _try_slot(config)
            except OSError as error:
                print(
                    f"WARNING: {stage}: cannot use heavy-stage slots in "
                    f"{config.slot_dir} ({error}); running without the host-wide cap.",
                    file=out,
                )
                headroom = True
                break
            if taken is not None:
                index, fd = taken
                headroom = True
                break
        remaining = wait_budget - (clock() - start)
        if remaining <= 0:
            break
        if not announced:
            reasons = []
            if not load_ok:
                reasons.append(f"load average {current:.1f} is at or above {config.max_load:.1f}")
            else:
                reasons.append(f"all {config.slots} heavy-stage slots are in use")
            print(
                f"{stage}: waiting up to {wait_budget:g}s for host headroom: {'; '.join(reasons)}.",
                file=out,
            )
            announced = True
        sleep(min(POLL_SECONDS, remaining))
    waited = clock() - start
    if not headroom:
        current = load()
        shown = "unavailable" if current is None else f"{current:.1f}"
        print(
            f"WARNING: {stage}: no host headroom after {waited:g}s (load average "
            f"{shown}, threshold {config.max_load:.1f}, {config.slots} slots); "
            f"running {stage} anyway, since a gate is never skipped. A timeout or "
            "crash below is likely load, not this diff.",
            file=out,
        )
    elif announced:
        print(f"{stage}: host headroom after {waited:g}s; starting.", file=out)
    try:
        yield Grant(slot=index, headroom=headroom, waited=waited)
    finally:
        if fd is not None:
            _release(fd)
