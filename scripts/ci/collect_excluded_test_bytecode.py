#!/usr/bin/env python3
"""Collect the test modules outside every split group without running them.

Split legs ignore these modules because dedicated legs or pin steps own them.
Collection imports and assertion-rewrites them, so the primary split leg can
save one complete bytecode cache while remaining the only cache writer.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.ci import run_pytest_non_tmp  # noqa: E402
from scripts.ci import run_pytest_partition as runner  # noqa: E402


def excluded_test_paths() -> list[str]:
    """The dedicated and unpartitioned test files, in stable order."""
    return sorted(runner._UNPARTITIONED_TESTS | runner._SAFE_PUSH_TESTS | runner._PR_AUTOFIX_TESTS)


def main(argv: list[str] | None = None) -> int:
    """Collect the excluded modules and return pytest's exit code."""
    _ = argv
    return run_pytest_non_tmp.main(
        [*runner.PYTEST_CONFIG_ARGS, "--collect-only", "-q", *excluded_test_paths()]
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
