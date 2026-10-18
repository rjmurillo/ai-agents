"""Host headroom for the pre-push ``pre-pr-validation`` job (issue #6725).

On a loaded shared host the job's fixed lefthook timeout killed a clean diff
partway through light gates. The other heavy stages already take one host-wide
slot and wait for load to drop before their clock starts (issue #6609,
``host_headroom``). This module gives ``pre_pr.py`` the same wait.

The wait runs in the hook context only, the one that sets
``AI_AGENTS_PRE_PR_FAST_STAGE_RAN``. Direct runs, CI, and managed containers
keep the current behavior. When the wait runs out the gates still run and a
warning names load, so a timeout that follows reads as load.

``HEADROOM_WAIT_SECONDS`` is added to the lefthook ``timeout:`` for this job.
``PRE_PR_OUTER_CAP_SECONDS`` stays the run budget left after the wait, so the
wait restarts the generated-staleness outer-cap clock.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

# Siblings import by bare name, as pre_pr.py does, so the outer-cap clock reset
# lands on the module instance the gate reads.
_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import check_generated_staleness  # noqa: E402
import host_headroom  # noqa: E402

FAST_STAGE_RAN_ENV = "AI_AGENTS_PRE_PR_FAST_STAGE_RAN"
HEADROOM_WAIT_SECONDS = 300

# Seam for tests: they replace the slot with a recorder.
_heavy_stage_slot = host_headroom.heavy_stage_slot


def _in_container() -> bool:
    try:
        from run_workflow_local_test import _is_remote_container
    except ImportError:
        return False
    return bool(_is_remote_container())


def wait_seconds() -> float:
    """The bounded wait: zero outside the hook, in CI, and in a container."""
    if os.environ.get(FAST_STAGE_RAN_ENV) != "1" or os.environ.get("CI") or _in_container():
        return 0.0
    return float(HEADROOM_WAIT_SECONDS)


@contextmanager
def headroom_stage(on_error: Callable[[str], None] | None = None) -> Iterator[bool]:
    """Hold a heavy-stage slot, wait for headroom, then restart the outer clock.

    Yields False without waiting when the wait is zero, and False when the
    ``AI_AGENTS_HEAVY_STAGE_*`` settings are bad (the error goes to stderr and
    the job runs, since a gate is never skipped); True once the wait finished.
    """
    wait = wait_seconds()
    if wait <= 0:
        yield False
        return
    try:
        settings = host_headroom.read_settings()
    except ValueError as error:
        print(f"WARNING: pre-pr-validation: {error}; running without a wait.", file=sys.stderr)
        yield False
        return
    with _heavy_stage_slot("pre-pr-validation", wait, settings=settings):
        # The run budget starts now, not at process start.
        check_generated_staleness._PROCESS_START = time.monotonic()
        yield True
