"""Every test file runs in exactly one pytest partition (issue #4854)."""

from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path

from scripts.ci import run_pytest_partition

_REPO = Path(__file__).resolve().parents[2]


def _selects(args: list[str], rel: str) -> bool:
    """Whether a partition's full argument list would collect ``rel``."""
    ignored = {t.removeprefix("--ignore=") for t in args if t.startswith("--ignore=")}
    globs = [t.removeprefix("--ignore-glob=") for t in args if t.startswith("--ignore-glob=")]
    if rel in ignored or any(fnmatch.fnmatch(rel, g) for g in globs):
        return False
    roots = [t.rstrip("/") for t in args if t.startswith("tests/")]
    return any(rel == root or rel.startswith(f"{root}/") for root in roots)


class TestPartitionsCoverEveryTestFileOnce:
    """Each test file runs in exactly one partition, or in a named pin step."""

    def test_every_test_file_has_exactly_one_owner(self) -> None:
        repo = _REPO
        tracked = (
            subprocess.run(
                ["git", "-C", str(repo), "ls-files", "-z", "--", "tests"],
                capture_output=True,
                check=True,
            )
            .stdout.decode("utf-8")
            .split("\0")
        )
        files = sorted(f for f in tracked if f.endswith(".py") and Path(f).name.startswith("test_"))
        assert files, "no tracked test files found"
        full_args = run_pytest_partition._PARTITION_FULL_ARGS
        unowned: list[str] = []
        doubled: list[str] = []
        for rel in files:
            owners = [name for name, args in full_args.items() if _selects(args, rel)]
            if not owners:
                unowned.append(rel)
            elif len(owners) > 1:
                doubled.append(f"{rel}: {owners}")
        assert not doubled, doubled
        assert set(unowned) <= run_pytest_partition._UNPARTITIONED_TESTS
