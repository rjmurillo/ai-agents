"""Run the test suites that ship inside skill bundles.

`pyproject.toml` sets `testpaths = ["tests"]`, so nothing under
`.claude/skills/*/tests` or `src/copilot-cli/skills/*/tests` is collected by a
plain `pytest` run. Those directories held 2052 test functions across 118 files
that CI had never executed; six of them were failing, including a read path that
created a directory as a side effect (issue #3371).

Adding the bundle roots to `testpaths` does not work. Both trees carry a skill
named `memory` whose `tests/` package resolves to the same dotted module name,
so a single invocation dies with `ValueError: Plugin already registered under a
different name`. `--import-mode=importlib` does not help: pytest derives the
module name from the `__init__.py` chain regardless of import mode, and
`consider_namespace_packages` cannot disambiguate because `.claude` is not a
legal Python identifier.

Skill names are unique *within* a tree, so one subprocess per tree collides with
nothing. Each tree runs in about ten seconds.

`test_every_bundle_suite_on_disk_is_listed` is the converse guard: a new bundle
suite under a tree root this module does not know about would otherwise go dark
exactly the way these 82 directories did.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from tests.external_scratch import outside_every_repository

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Tree roots whose `*/tests` directories this module runs. Each root is executed
# in its own pytest subprocess; see the module docstring for why one combined
# invocation cannot work.
_BUNDLE_TREE_ROOTS = (
    Path(".claude") / "skills",
    Path("src") / "copilot-cli" / "skills",
)

# Directories that look like skill trees but hold no shipped suite. The converse
# scan reads tracked paths from git, so local agent worktrees and scratch
# checkouts are excluded by construction rather than by a name blocklist.
_SKILL_MD_PATTERN = re.compile(r"(?:^|/)skills/[^/]+/SKILL\.md$")


def _suite_dirs(root: Path) -> list[Path]:
    """Return the `<root>/*/tests` directories that exist, sorted."""
    absolute = _REPO_ROOT / root
    if not absolute.is_dir():
        return []
    return sorted(p for p in absolute.glob("*/tests") if p.is_dir())


def _run_tree(root: Path) -> subprocess.CompletedProcess[str]:
    """Run every bundle suite under one tree root in a dedicated subprocess."""
    targets = [str(p.relative_to(_REPO_ROOT)) for p in _suite_dirs(root)]
    temp_root = (
        outside_every_repository(_REPO_ROOT)
        / f".pytest-external-{_REPO_ROOT.name}"
        / uuid.uuid4().hex
    )
    env = os.environ.copy()
    # tempfile consults TMPDIR, TEMP, and TMP (Windows tools may ignore TMPDIR);
    # set all three so isolation holds across platforms.
    env["TMPDIR"] = env["TEMP"] = env["TMP"] = str(temp_root)
    try:
        temp_root.mkdir(parents=True)
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                *targets,
                "-q",
                "--no-header",
                "-p",
                "no:cacheprovider",
            ],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=900,
            check=False,
            env=env,
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@pytest.mark.parametrize("root", _BUNDLE_TREE_ROOTS, ids=lambda p: p.as_posix())
def test_bundle_tree_has_suites(root: Path) -> None:
    """Each configured tree root still carries bundle suites to run.

    Guards the inverse of a dark suite: if a refactor moved every bundle test
    out from under a root, the run below would pass vacuously.
    """
    assert _suite_dirs(root), (
        f"no */tests directories under {root.as_posix()}; "
        "remove the root from _BUNDLE_TREE_ROOTS or restore the suites"
    )


@pytest.mark.parametrize("root", _BUNDLE_TREE_ROOTS, ids=lambda p: p.as_posix())
def test_bundle_tree_suite_passes(root: Path) -> None:
    """Every test shipped inside a skill bundle under this root passes."""
    result = _run_tree(root)
    assert result.returncode == 0, (
        f"bundle suites under {root.as_posix()} failed "
        f"(exit {result.returncode}):\n{result.stdout}\n{result.stderr}"
    )


@pytest.mark.parametrize("root", _BUNDLE_TREE_ROOTS, ids=lambda p: p.as_posix())
def test_bundle_tree_collects_tests(root: Path) -> None:
    """The run collected tests rather than passing on an empty selection.

    `pytest` exits 0 when it collects nothing under some configurations, so an
    exit code alone cannot prove the suites ran.
    """
    result = _run_tree(root)
    assert "passed" in result.stdout, (
        f"bundle run under {root.as_posix()} reported no passing tests; "
        f"collection likely selected nothing:\n{result.stdout}"
    )


def test_every_bundle_suite_on_disk_is_listed() -> None:
    """No tracked skill-bundle test directory sits outside the configured roots.

    The converse of the runs above. Without it a suite added under a new tree
    (for example `src/vs-code-agents/skills/*/tests`) would never execute and
    nothing would report the gap, which is exactly how 82 directories went dark.

    Scans tracked paths only. An untracked local worktree is a developer's
    scratch checkout, not a shipped bundle, and must not fail this guard.
    """
    listed = {p.resolve() for root in _BUNDLE_TREE_ROOTS for p in _suite_dirs(root)}

    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "*/SKILL.md", "SKILL.md"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=True,
    )

    on_disk = set()
    for rel in tracked.stdout.split("\0"):
        if not rel or not _SKILL_MD_PATTERN.search(rel):
            continue
        tests_dir = _REPO_ROOT / rel
        tests_dir = tests_dir.parent / "tests"
        if tests_dir.is_dir():
            on_disk.add(tests_dir.resolve())

    assert on_disk, "found no tracked skill bundles; the git scan is broken"

    unlisted = sorted(p.relative_to(_REPO_ROOT).as_posix() for p in on_disk - listed)
    assert not unlisted, (
        f"{len(unlisted)} skill-bundle test directories are not covered by "
        f"_BUNDLE_TREE_ROOTS and would never run:\n  " + "\n  ".join(unlisted)
    )


def test_listed_tree_roots_exist() -> None:
    """Every configured tree root is a real directory.

    A root renamed out from under this module would otherwise silently
    contribute zero suites.
    """
    missing = [root.as_posix() for root in _BUNDLE_TREE_ROOTS if not (_REPO_ROOT / root).is_dir()]
    assert not missing, f"configured bundle tree roots do not exist: {missing}"
