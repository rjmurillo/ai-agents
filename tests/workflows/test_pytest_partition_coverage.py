"""Every test file runs in exactly one pytest partition kind (issues #4854, #6239)."""

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
        # The split groups share one pool; which group runs a file depends on
        # the durations file, so ownership is by kind: the pool, or a dedicated leg.
        kinds = {
            ("split" if name in run_pytest_partition.split_names() else name): args
            for name, args in full_args.items()
        }
        unowned: list[str] = []
        doubled: list[str] = []
        for rel in files:
            owners = [kind for kind, args in kinds.items() if _selects(args, rel)]
            if not owners:
                unowned.append(rel)
            elif len(owners) > 1:
                doubled.append(f"{rel}: {owners}")
        assert not doubled, doubled
        assert set(unowned) <= run_pytest_partition._UNPARTITIONED_TESTS

    def test_split_groups_select_the_same_files(self) -> None:
        """Groups differ in `--group` only, so no file is in one group's pool and not another's."""
        names = run_pytest_partition.split_names()
        full_args = run_pytest_partition._PARTITION_FULL_ARGS
        tracked = subprocess.run(
            ["git", "-C", str(_REPO), "ls-files", "-z", "--", "tests"],
            capture_output=True,
            check=True,
        ).stdout.decode("utf-8")
        files = [f for f in tracked.split("\0") if f.endswith(".py")]
        for rel in files:
            verdicts = {_selects(full_args[name], rel) for name in names}
            assert len(verdicts) == 1, rel
