"""Re-select the tests testmon cannot link to a changed data file (pre-push gap).

pytest-testmon 2.2.0 records which Python lines each test runs
(`testmon/testmon_core.py::is_python_file`). A test that reads
``tests/evals/<corpus>.json`` has no Python dependency on it, so editing the
corpus selects nothing. Measured on this repository: a corpus edit that breaks
``tests/test_profile_behavior_fixtures.py`` left testmon at "132 deselected, 0
selected", and four failing tests reached a push on PR #7126.

This module finds the paths changed since the merge base with ``origin/main``,
keeps those under ``tests/evals/``, finds the test modules that mention them,
and removes those modules from testmon's deselection. Over-selecting is the
safe direction: a module that only mentions a corpus runs one extra time.

Detection is textual, so it has known limits: a test that reaches a corpus only
through a subprocess or a computed path is not found, and a helper module is
followed one hop (a test module that mentions the helper's name counts).

A second rule covers tests that scan the whole tracked tree through a ``git``
subprocess (``git grep``, ``git ls-files``), directly or through a helper module
(one hop, as for corpus readers). Such a test has no Python
dependency on any Markdown file, and a brand-new file is named by no test, so
the name match above cannot find it. Issue #7286: a new ``docs/`` page broke
a decommission-scope test (it greps every tracked file) in CI while pre-push
selected nothing. When the diff holds a Markdown file, every tree-scanner module is
re-selected. The cost is one run of those modules (87 modules, 57 s at
``-n 4`` measured 2026-11-11, inside the 180 s pre-push budget), paid only on a diff that
touches Markdown.

Fail-safe: when git cannot name a base or the changed paths, every corpus is
treated as changed and every tree scanner is re-selected, so the readers run.
CI runs the whole suite regardless (ADR-104).

`testmon_scoped_sync` calls `reselect` from its selection hooks.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Collection, Iterable, Mapping
from pathlib import Path, PurePosixPath
from typing import Protocol

DATA_ROOT = "tests/evals/"
TEST_ROOT = "tests"
BASE_REFS = ("origin/main", "main")
GIT_TIMEOUT_SECONDS = 10
MARKDOWN_PATHSPEC = "*.md"
_TEST_MODULE = re.compile(r"(?:test_.*|.*_test)\.py")
# A test that runs git over the tree names the subcommand as a quoted argv item.
_TREE_SCAN = re.compile(r"""["'](?:grep|ls-files)["']""")


class _Selection(Protocol):
    deselected_files: Collection[str]
    deselected_tests: Collection[str]


def _git(root: Path, *args: str) -> bytes | None:
    """Return stdout of a bounded git call, or None on any failure."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _merge_base(root: Path) -> str | None:
    for ref in BASE_REFS:
        out = _git(root, "merge-base", ref, "HEAD")
        if out and out.strip():
            return out.decode("utf-8", errors="replace").strip()
    return None


def changed_data_inputs(root: Path) -> list[str] | None:
    """Return changed paths under `DATA_ROOT` since the merge base, or None when unknown.

    The diff runs from the merge base to the working tree, so staged, unstaged
    and committed edits all count.
    """
    base = _merge_base(root)
    if base is None:
        return None
    out = _git(root, "diff", "--name-only", "-z", base, "--", DATA_ROOT)
    if out is None:
        return None
    paths = (raw.decode("utf-8", errors="replace") for raw in out.split(b"\0") if raw)
    return [path for path in paths if not path.endswith(".py")]


def changed_markdown(root: Path) -> list[str] | None:
    """Return changed Markdown paths since the merge base, or None when unknown."""
    base = _merge_base(root)
    if base is None:
        return None
    out = _git(root, "diff", "--name-only", "-z", base, "--", MARKDOWN_PATHSPEC)
    if out is None:
        return None
    return [raw.decode("utf-8", errors="replace") for raw in out.split(b"\0") if raw]


def all_data_inputs(root: Path) -> list[str]:
    """Return every non-Python file under `DATA_ROOT`, the fail-safe for an unknown diff."""
    base = root / DATA_ROOT
    if not base.is_dir():
        return []
    return sorted(
        path.relative_to(root).as_posix()
        for path in base.rglob("*")
        if path.is_file() and path.suffix != ".py"
    )


def _needles(changed: Iterable[str]) -> tuple[set[str], set[str]]:
    """Return (names, dirs): file names to find, and directory names to find beside 'evals'."""
    names: set[str] = set()
    dirs: set[str] = set()
    for path in changed:
        relative = PurePosixPath(path[len(DATA_ROOT) :] if path.startswith(DATA_ROOT) else path)
        names.add(relative.name)
        if relative.parent.name:
            dirs.add(relative.parent.name)
    return names, dirs


def _mentions(text: str, names: Collection[str], dirs: Collection[str]) -> bool:
    if any(name in text for name in names):
        return True
    return "evals" in text and any(name in text for name in dirs)


def reader_modules(changed: Iterable[str], sources: Mapping[str, str]) -> set[str]:
    """Return the test modules (keys of `sources`) that read a changed data file.

    `sources` maps a repository-relative ``.py`` path to its text. A non-test
    module that mentions a changed file is a helper; a test module that mentions
    the helper's module name counts too (one hop).
    """
    names, dirs = _needles(changed)
    if not names:
        return set()
    helpers = {
        PurePosixPath(rel).stem
        for rel, text in sources.items()
        if not _TEST_MODULE.fullmatch(PurePosixPath(rel).name) and _mentions(text, names, dirs)
    }
    return {
        rel
        for rel, text in sources.items()
        if _TEST_MODULE.fullmatch(PurePosixPath(rel).name)
        and (_mentions(text, names, dirs) or any(helper in text for helper in helpers))
    }


def tree_scanner_modules(sources: Mapping[str, str]) -> set[str]:
    """Return the test modules (keys of `sources`) that scan the tracked tree through git.

    A test module counts when it names ``git grep`` or ``git ls-files`` itself,
    or mentions the module name of a non-test helper that does (one hop, as in
    `reader_modules`). Textual and over-inclusive on purpose: a module that
    names either subcommand but scans one directory runs one extra time.
    """
    helpers = {
        PurePosixPath(rel).stem
        for rel, text in sources.items()
        if not _TEST_MODULE.fullmatch(PurePosixPath(rel).name) and _TREE_SCAN.search(text)
    }
    return {
        rel
        for rel, text in sources.items()
        if _TEST_MODULE.fullmatch(PurePosixPath(rel).name)
        and (_TREE_SCAN.search(text) or any(helper in text for helper in helpers))
    }


def _read_sources(root: Path) -> dict[str, str]:
    sources: dict[str, str] = {}
    for path in sorted((root / TEST_ROOT).rglob("*.py")):
        try:
            sources[path.relative_to(root).as_posix()] = path.read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            continue
    return sources


def _home_file(test_name: str) -> str:
    return test_name.split("::", 1)[0]


def reselect(select: _Selection, root: Path) -> set[str]:
    """Remove the readers of changed data files from testmon's deselection.

    Two rules feed it: tests that mention a changed eval corpus, and, when the
    diff holds a Markdown file, tests that scan the tracked tree. Returns the
    modules re-selected. Does nothing when neither rule applies.
    """
    changed = changed_data_inputs(root)
    if changed is None:
        changed = all_data_inputs(root)
    markdown = changed_markdown(root)
    if not changed and markdown is not None and not markdown:
        return set()
    sources = _read_sources(root)
    readers = reader_modules(changed, sources) if changed else set()
    if markdown is None or markdown:
        readers |= tree_scanner_modules(sources)
    if not readers:
        return set()
    select.deselected_files = [f for f in select.deselected_files if f not in readers]
    select.deselected_tests = [t for t in select.deselected_tests if _home_file(t) not in readers]
    return readers
