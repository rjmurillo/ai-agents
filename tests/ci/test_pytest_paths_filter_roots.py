"""Every non-extension root in `pytest.yml`'s filter must be named by a test.

Named, not read. The check below searches for a textual mention anywhere under
`tests/`, a comment included, so a passing root is evidence of intent and not
of a runtime dependency. The looseness is deliberate: a strict-path version
produced a false negative on a package tree reached by import. Review on
PR #5319 asked for this paragraph, because the wording above it promised proof
the implementation does not deliver.

`.github/workflows/pytest.yml` gates the whole pytest matrix behind a
`dorny/paths-filter`. A diff matching nothing in that filter skips every
partition, and the aggregate check still reports the same required name, so a
green `Run Python Tests` does not by itself mean tests ran.

That makes the filter's non-extension entries load-bearing in a way the
extension globs are not. `**/*.py` justifies itself. `.claude/skills/**` is a
claim: that some test names that tree and would not otherwise run. Issue #5315
added several such roots on exactly that claim, after pre-push stopped
executing the suite locally for non-Python changes (ADR-104) and left the
delegation with nowhere to land at PR time.

A claim nobody checks decays. A root can outlive the test that motivated it,
or be pruned as noise by someone who cannot tell which tests depend on it, and
either way the failure is silent: the suite skips and the check goes green.

Coverage:

- positive: every non-extension root in the filter is referenced by at least
  one file under `tests/`.
- negative: a root nothing references fails, with the root named.
- edge: extension globs and single files are exempt by construction, and the
  test asserts the roster it checks is non-empty so it cannot pass vacuously.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pytest.yml"
_TESTS = REPO_ROOT / "tests"

# Entries that justify themselves and need no reader: a suffix glob matches by
# file type rather than by location, so there is no tree to go stale.
_EXTENSION_GLOB = re.compile(r"^\*\*/\*\.[A-Za-z0-9]+$")


def _filter_entries() -> list[str]:
    """The `python:` filter's patterns, read from the workflow as data."""
    config = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    for job in config["jobs"].values():
        for step in job.get("steps", []):
            if not isinstance(step, dict):
                continue
            if not str(step.get("uses", "")).startswith("dorny/paths-filter"):
                continue
            filters = yaml.safe_load(step["with"]["filters"])
            return [str(entry) for entry in filters["python"]]
    raise AssertionError("pytest.yml no longer declares a dorny/paths-filter step.")


def _tree_roots() -> list[str]:
    """Filter entries that name a directory tree rather than a file type."""
    return [
        entry
        for entry in _filter_entries()
        if entry.endswith("/**") and not _EXTENSION_GLOB.match(entry)
    ]


def _tests_reference(root: str) -> bool:
    """True when any file under `tests/` mentions this root, in either form.

    Matches the path prefix rather than the glob, so a test naming a concrete
    file inside the tree counts. It also matches the dotted module form,
    because a tree of Python packages is usually read by importing it rather
    than by opening a path: `scripts/memory_enhancement/**` is referenced as
    `scripts.memory_enhancement`, and checking only the slash form reported a
    real root as unreferenced.

    This module is excluded from the scan. It necessarily contains every root
    it checks, so including it would make the check true by construction.
    """
    prefix = root[: -len("/**")]
    forms = (prefix, prefix.replace("/", "."))
    for path in _TESTS.rglob("*.py"):
        if path.resolve() == Path(__file__).resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:  # pragma: no cover - unreadable file under tests/
            continue
        if any(form in text for form in forms):
            return True
    return False


def test_there_are_tree_roots_to_check() -> None:
    """Vacuity guard: the parametrization below must quantify over something."""
    assert _tree_roots(), (
        "pytest.yml's python filter declares no directory-tree roots. If the "
        "filter became extension-only on purpose, delete this module with it."
    )


@pytest.mark.parametrize("root", sorted(set(_tree_roots())))
def test_every_tree_root_is_referenced_by_a_test(root: str) -> None:
    assert _tests_reference(root), (
        f"{root!r} is in pytest.yml's python filter but no file under tests/ "
        "mentions it. Either a test that justified it was removed, in which "
        "case drop the root, or the root was added speculatively, in which "
        "case it widens CI for nothing. A root whose reader is gone makes the "
        "suite run on changes nothing tests, and hides that the reverse case "
        "(a tested tree missing from the filter) is the one that goes silent."
    )


def test_the_reader_check_can_fail() -> None:
    """Negative control: a root nothing references is reported as unreferenced.

    Without this, the parametrized assertion passing says nothing about
    whether `_tests_reference` is capable of returning False.
    """
    assert not _tests_reference("this/tree/does/not/exist/anywhere/**")
