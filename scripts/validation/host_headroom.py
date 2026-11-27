"""Host-wide headroom for heavy pre-push stages (issue #6609).

Caps concurrent heavy stages via ``fcntl.flock`` lock files under the user's
cache directory (not ``/tmp``). A stage waits for host CPU pressure to drop
BEFORE claiming a slot so sleeping waiters never hoard slots, polls with
bounded jitter to avoid lockstep wakeups, prefers Linux ``/proc/pressure/cpu``
(``some avg10``) and ``/proc/stat`` (``procs_running``) over ``loadavg`` so
D-state ``in_iowait`` threads cannot falsely peg the gate, and raises
``HeadroomTimeoutError`` (``SystemExit(3)``) if every slot stays occupied for
``wait_budget`` instead of running uncapped.
"""

from __future__ import annotations

import math
import os
import random
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
MAX_PSI_ENV = "AI_AGENTS_HEAVY_STAGE_MAX_PSI"
SLOT_DIR_ENV = "AI_AGENTS_HEAVY_STAGE_SLOT_DIR"
DEFAULT_SLOTS = 3
DEFAULT_MAX_LOAD_PER_CPU = 1.0
DEFAULT_MAX_CPU_PSI = 25.0
POLL_SECONDS = 5.0
POLL_JITTER_RATIO = 0.5
_CPU_PSI_PATH = Path("/proc/pressure/cpu")
_PROC_STAT_PATH = Path("/proc/stat")

# Slot files this process holds; `other_stages` skips them.
_OWN_SLOTS: set[Path] = set()


@dataclass(frozen=True)
class Settings:
    """Concurrency cap and host CPU pressure limits (0 disables a knob)."""

    slots: int
    max_load: float
    slot_dir: Path
    max_psi: float = DEFAULT_MAX_CPU_PSI


@dataclass(frozen=True)
class Grant:
    """What one stage got: a slot index (or none), and whether it had headroom."""

    slot: int | None
    headroom: bool
    waited: float


class HeadroomTimeoutError(SystemExit):
    """Raised with exit code 3 when every slot stays occupied for ``wait_budget``."""


def default_max_load(cpus: int | None = None) -> float:
    """The load threshold when none is set: ``DEFAULT_MAX_LOAD_PER_CPU`` per CPU."""
    count = cpus if cpus is not None else (os.cpu_count() or 1)
    return DEFAULT_MAX_LOAD_PER_CPU * max(1, count)


def read_settings(env: Mapping[str, str] | None = None, *, cpus: int | None = None) -> Settings:
    """Read gate settings from ``env``; raise ``ValueError`` naming any bad variable."""
    source = os.environ if env is None else env
    raw_slots = source.get(SLOTS_ENV, "").strip()
    if not raw_slots:
        slots = DEFAULT_SLOTS
    elif raw_slots.isdecimal():
        slots = int(raw_slots)
    else:
        raise ValueError(f"{SLOTS_ENV} must be a nonnegative integer, got {raw_slots!r}")
    parsed: dict[str, float] = {}
    for env_name, default in (
        (MAX_LOAD_ENV, default_max_load(cpus)),
        (MAX_PSI_ENV, DEFAULT_MAX_CPU_PSI),
    ):
        raw = source.get(env_name, "").strip()
        if not raw:
            parsed[env_name] = default
            continue
        try:
            value = float(raw)
        except ValueError:
            value = -1.0
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{env_name} must be a nonnegative number, got {raw!r}")
        parsed[env_name] = value
    raw_dir = source.get(SLOT_DIR_ENV, "").strip()
    if raw_dir:
        slot_dir = Path(raw_dir)
    elif cache := source.get("XDG_CACHE_HOME"):
        slot_dir = Path(cache) / "ai-agents" / "heavy-stage-slots"
    else:
        home = source.get("HOME") or str(Path.home())
        slot_dir = Path(home) / ".cache" / "ai-agents" / "heavy-stage-slots"
    return Settings(
        slots=slots,
        max_load=parsed[MAX_LOAD_ENV],
        slot_dir=slot_dir,
        max_psi=parsed[MAX_PSI_ENV],
    )


def load_average() -> float | None:
    """The 1-minute load average, or None where the platform has none."""
    if not hasattr(os, "getloadavg"):
        return None
    try:
        return float(os.getloadavg()[0])
    except OSError:
        return None


def cpu_psi_avg10(path: Path | None = None) -> float | None:
    """Linux CPU PSI ``some avg10`` percentage from ``/proc/pressure/cpu``, or None."""
    target = _CPU_PSI_PATH if path is None else path
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        fields = line.split()
        if not fields or fields[0] != "some":
            continue
        for token in fields[1:]:
            if not token.startswith("avg10="):
                continue
            try:
                value = float(token.partition("=")[2])
            except ValueError:
                return None
            return value if math.isfinite(value) and value >= 0 else None
    return None


def procs_running(path: Path | None = None) -> int | None:
    """Runnable task count from ``/proc/stat`` (excludes D-state ``procs_blocked``)."""
    target = _PROC_STAT_PATH if path is None else path
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0] == "procs_running":
            return int(fields[1]) if fields[1].isdecimal() else None
    return None


def _check_pressure(
    config: Settings, load: Callable[[], float | None] | None
) -> tuple[bool, str | None]:
    """Return ``(has_headroom, description)`` for current host CPU pressure."""
    if config.max_load <= 0:
        return True, None
    if load is None:
        psi = cpu_psi_avg10() if config.max_psi > 0 else None
        running = procs_running()
        if psi is not None or running is not None:
            parts: list[str] = []
            ok = True
            if psi is not None:
                ok = ok and psi < config.max_psi
                parts.append(f"cpu psi avg10 {psi:.1f}% (threshold {config.max_psi:.1f}%)")
            if running is not None:
                other_runnable = max(0, running - 1)
                ok = ok and other_runnable < config.max_load
                parts.append(f"runnable tasks {other_runnable} (threshold {config.max_load:.1f})")
            return ok, ", ".join(parts)
    current = (load_average if load is None else load)()
    if current is None:
        return True, "load average unavailable"
    ok = current < config.max_load
    relation = "below" if ok else "is at or above"
    return ok, f"load average {current:.1f} {relation} {config.max_load:.1f}"


def load_note(
    stage: str,
    *,
    load: Callable[[], float | None] | None = None,
    max_load: float | None = None,
    cpus: int | None = None,
    settings: Settings | None = None,
) -> str:
    """One line that says whether host load likely caused a stage failure."""
    count = cpus if cpus is not None else (os.cpu_count() or 1)
    if settings is None:
        try:
            settings = read_settings(cpus=count)
        except ValueError:
            settings = None
    threshold = (
        max_load
        if max_load is not None
        else (default_max_load(count) if settings is None else settings.max_load)
    )
    current = (load_average if load is None else load)()
    if current is None:
        return (
            f"NOTE: {stage}: host load average is unavailable here, so load "
            "cannot be ruled in or out as the cause."
        )
    others = 0 if settings is None else other_stages(settings)
    measured = f"host load average is {current:.1f} on {count} CPUs"
    if others:
        verb = "is" if others == 1 else "are"
        plural = "" if others == 1 else "s"
        return (
            f"NOTE: {stage}: {measured}, and {others} other heavy pre-push "
            f"stage{plural} {verb} running on this host. This failure is likely "
            "load from other work on the host, not this diff. Retry when load drops."
        )
    if threshold > 0 and current >= threshold:
        return (
            f"NOTE: {stage}: {measured}, at or above the {threshold:.1f} headroom "
            "threshold. This failure is likely load from other work on the "
            "host, not this diff. Retry when load drops."
        )
    return (
        f"NOTE: {stage}: {measured} and no other heavy pre-push stage holds a "
        "slot, so host load is not the likely cause."
    )


def other_stages(settings: Settings) -> int:
    """How many heavy-stage slots other processes hold right now."""
    if settings.slots <= 0 or not _HAS_FLOCK:
        return 0
    held = 0
    for index in range(settings.slots):
        path = settings.slot_dir / f"slot-{index}.lock"
        if path in _OWN_SLOTS:
            continue
        try:
            fd = os.open(path, os.O_RDWR)
        except OSError:
            continue
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            held += 1
        except OSError:
            pass
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
    return held


def _claim_slot(stage: str, config: Settings, out: TextIO) -> tuple[tuple[int, int] | None, bool]:
    """Lock the first free slot file; disable slots with a warning on OS errors."""
    try:
        config.slot_dir.mkdir(parents=True, exist_ok=True)
        for index in range(config.slots):
            path = config.slot_dir / f"slot-{index}.lock"
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                continue
            except OSError:
                os.close(fd)
                raise
            _OWN_SLOTS.add(path)
            return (index, fd), True
    except OSError as error:
        print(
            f"WARNING: {stage}: cannot use heavy-stage slots in "
            f"{config.slot_dir} ({error}); running without the host-wide cap.",
            file=out,
        )
        return None, False
    return None, True


@contextmanager
def heavy_stage_slot(
    stage: str,
    wait_budget: float,
    *,
    settings: Settings | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    load: Callable[[], float | None] | None = None,
    jitter: Callable[[float, float], float] = random.uniform,
    stream: TextIO | None = None,
) -> Iterator[Grant]:
    """Hold a heavy-stage slot for the ``with`` body, waiting up to ``wait_budget``.

    Slots are never hoarded while waiting on CPU pressure. If ``wait_budget``
    expires with all configured slots occupied, raises ``HeadroomTimeoutError``
    (exit 3) instead of running uncapped.
    """
    out = sys.stderr if stream is None else stream
    config = read_settings() if settings is None else settings
    use_slots = config.slots > 0 and _HAS_FLOCK
    start = clock()
    announced = False
    taken: tuple[int, int] | None = None
    headroom = False
    low = POLL_SECONDS * (1.0 - POLL_JITTER_RATIO)
    high = POLL_SECONDS * (1.0 + POLL_JITTER_RATIO)
    try:
        while True:
            pressure_ok, summary = _check_pressure(config, load)
            if pressure_ok:
                if use_slots:
                    taken, use_slots = _claim_slot(stage, config, out)
                if not use_slots or taken is not None:
                    headroom = True
                    break
            remaining = wait_budget - (clock() - start)
            if remaining <= 0:
                break
            if not announced:
                reason = (
                    summary
                    if not pressure_ok and summary
                    else f"all {config.slots} heavy-stage slots are in use"
                )
                print(
                    f"{stage}: waiting up to {wait_budget:g}s for host headroom: {reason}.",
                    file=out,
                )
                announced = True
            delay = jitter(low, high)
            sleep(min(delay if math.isfinite(delay) and delay > 0 else low, remaining))
        waited = clock() - start
        if not headroom:
            if use_slots and taken is None:
                taken, use_slots = _claim_slot(stage, config, out)
            _, final_summary = _check_pressure(config, load)
            detail = final_summary or "host pressure unavailable"
            if use_slots and taken is None:
                print(
                    f"ERROR: {stage}: no free heavy-stage slot after {waited:g}s "
                    f"(all {config.slots} slots in use; {detail}). Refusing to run "
                    f"{stage} uncapped to prevent a host contention stampede; "
                    "retry when host load drops.",
                    file=out,
                )
                raise HeadroomTimeoutError(3)
            slot_note = f"holding slot {taken[0]}" if taken is not None else "slots disabled"
            print(
                f"WARNING: {stage}: no host headroom after {waited:g}s ({detail}, "
                f"{config.slots} slots, {slot_note}); running {stage} anyway, since "
                "a gate is never skipped. A timeout or crash below is likely load, "
                "not this diff.",
                file=out,
            )
        elif announced:
            print(f"{stage}: host headroom after {waited:g}s; starting.", file=out)
        yield Grant(slot=None if taken is None else taken[0], headroom=headroom, waited=waited)
    finally:
        if taken is not None:
            _OWN_SLOTS.discard(config.slot_dir / f"slot-{taken[0]}.lock")
            try:
                fcntl.flock(taken[1], fcntl.LOCK_UN)
            finally:
                os.close(taken[1])
