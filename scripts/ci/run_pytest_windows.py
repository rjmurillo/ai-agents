#!/usr/bin/env python3
"""Run the `windows_path` marker suite without collecting the whole test tree.

`pytest -m windows_path` has to import every module under `tests/` before the
marker can deselect one, so the Windows job pays for a full-tree collection to
run a fraction of it. Measured on this checkout: 33,326 items collected to
select 1,115, 26.70s wall and 417MB peak RSS, against 1,764 collected, 1.67s
and 69MB when pytest is handed only the files whose text names the marker. Both
invocations collect the same 1,115 node IDs (issue #5380).

Discovery stays textual rather than registered, so a new marked file is picked
up with no list to update. That is the property issue #4299 established and
`tests/test_windows_path_marker_discovery.py` pins. `-m windows_path` is still
passed to pytest, so a file that names the marker in a comment or an assertion
is collected and then deselected, contributing nothing.

The backstop for the one way this can under-select, a marker applied to a file
that never spells it, is `tests/ci/test_run_pytest_windows.py`: it collects
both ways and fails when the node-ID sets disagree.

Exit codes (AGENTS.md contract): 0 ok, 2 config, 3 external. Any other code is
pytest's own and is passed through unchanged.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

MARKER = "windows_path"
TESTS_DIR = "tests"

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_EXTERNAL = 3


class DiscoveryError(Exception):
    """A module under ``tests/`` could not be read, so discovery is incomplete."""


def marked_files(repo_root: Path) -> list[str]:
    """Repo-relative test modules whose text names :data:`MARKER`.

    Over-matching is safe and under-matching is not, so the test is a plain
    substring over the file rather than an AST walk for a decorator: a match in
    a comment costs one imported module, while a decorator shape this did not
    model would silently drop a Windows test from the only job that runs it.

    Raises:
        DiscoveryError: a module under ``tests/`` could not be read. Skipping it
            would drop whatever Windows contract it holds while the remaining
            files still let the job report success, which is the silent pass
            `ci-scripts.md` MUST-11 forbids. The caller turns this into a
            non-zero exit.
    """
    tests_root = repo_root / TESTS_DIR
    found = []
    for path in sorted(tests_root.rglob("test_*.py")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise DiscoveryError(
                f"could not read {path.relative_to(repo_root).as_posix()}: {exc}"
            ) from exc
        if MARKER in text:
            found.append(path.relative_to(repo_root).as_posix())
    return found


def main(argv: list[str] | None = None) -> int:
    passthrough = list(sys.argv[1:] if argv is None else argv)

    try:
        files = marked_files(PROJECT_ROOT)
    except DiscoveryError as exc:
        print(f"discovery is incomplete, refusing to run a partial suite: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL
    print(f"marker={MARKER} candidate_files={len(files)}", file=sys.stderr)
    if not files:
        print(
            f"no module under {TESTS_DIR}/ names {MARKER!r}; refusing to run zero tests",
            file=sys.stderr,
        )
        return EXIT_CONFIG

    command = [sys.executable, "-m", "pytest", "-m", MARKER, *passthrough, *files]
    try:
        # The child inherits fd 1, so anything this process queued would print
        # after pytest's own output. tests/test_stdout_flush_before_spawn.py.
        #
        # No `timeout=` here on purpose. The bound on this call is the job's own
        # `timeout-minutes: 10` in pytest.yml. An inner cap would need a number
        # sized from a loaded Windows runner, which nobody has measured yet, and
        # `ci-scripts.md` MUST-16 is explicit that a cap sized from anything else
        # is a cap a real run can exceed. A too-low guess turns a healthy slow
        # runner red, which is worse than the outer cap this already has.
        sys.stdout.flush()
        return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode
    except OSError as exc:
        print(f"could not start pytest: {exc}", file=sys.stderr)
        return EXIT_EXTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
