#!/usr/bin/env python3
"""K3 emission point: detect vendored-install breakage and record it.

K3 (REQ-008-09) fires when a downstream installer reports that ``/review``
fails to run after a project-toolkit plugin update. This script is the
machine-checkable proxy for that signal: it runs the vendored-install
contract suite (``tests/integration/test_vendored_install.py``), and if
any test fails it emits a single K3 kill-criteria event through the
canonical emitter, then exits non-zero so a CI job or a pre-release gate
surfaces the breakage.

Why a dedicated script and not a pytest assertion: a K3 event means
"production install is broken", not "a unit test failed during local
development". Emitting from inside the test suite would fire K3 on every
red local run. Gating emission behind an explicit invocation keeps the
signal meaningful: run this in CI or before a plugin release, not on every
``pytest`` call.

Exit Codes (ADR-035):
    0 = vendored install suite passed (no K3)
    1 = vendored install suite failed (K3 emitted)
    3 = could not run the suite (external failure; no K3, state unknown)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[1]

sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from kill_criteria import emit_event  # noqa: E402
from redact_secrets import redact  # noqa: E402

VENDORED_TEST = "tests/integration/test_vendored_install.py"

_PYTEST_TIMEOUT = 300


def _run_vendored_suite() -> subprocess.CompletedProcess[str]:
    """Run the vendored-install pytest suite and capture the result."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", VENDORED_TEST, "-q"],
        cwd=str(_PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=_PYTEST_TIMEOUT,
        check=False,
    )


def main() -> int:
    """Run the vendored suite; emit K3 and fail when it breaks."""
    try:
        result = _run_vendored_suite()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        print(
            f"error: could not run vendored-install suite: {exc}",
            file=sys.stderr,
        )
        return 3

    if result.returncode == 0:
        print("vendored-install suite passed; no K3 event emitted.")
        return 0

    tail = (result.stdout or result.stderr).strip().splitlines()[-1:]
    summary = tail[0] if tail else "vendored-install suite failed"
    detail = redact(f"vendored install breakage: {summary}").text
    try:
        emit_event("K3", detail)
    except OSError as exc:
        print(
            f"warning: vendored-install suite failed; could not emit K3 event: {exc}",
            file=sys.stderr,
        )
        return 1
    print(
        "vendored-install suite FAILED; K3 kill-criteria event emitted.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
